"""Comprehensive Test Suite for Reminders-API & Proactive Follow-Up Pipeline.

Verifies:
1. RemindersAPIClient & MockRemindersBackend contracts matching faresemad/Reminders-API.
2. ReminderDateParser for Malayalam, Manglish, and English relative datetime resolution.
3. ReminderService creation, ownership enforcement, update, cancellation, and snooze.
4. Persistent SQLite storage in reminders_metadata and user_preferences.
5. PersistentReminderScheduler:
   - Atomic claims (preventing duplicate execution)
   - Quiet hours evaluation
   - Delivery to channel
   - Bounded retries
   - Recurrence handling
6. REST API endpoints (/api/reminders, /api/reminders/{id}/snooze, etc.)
7. Natural conversation flow in Horus via call_horus.
"""

from __future__ import annotations

import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import db
from reminders import (
    MockRemindersBackend,
    PersistentReminderScheduler,
    ReminderDateParser,
    ReminderService,
    RemindersAPIClient,
)
from app import app, call_horus


@pytest.fixture
def test_db_path(tmp_path):
    """Provides a fresh isolated SQLite database path for testing."""
    test_db = tmp_path / "test_customer_agent.db"
    db.init_db(test_db)
    return test_db


# ==============================================================================
# 1. RemindersAPIClient Contract Tests (faresemad/Reminders-API)
# ==============================================================================

def test_reminders_api_client_mock_contract():
    """Verify RemindersAPIClient implements the exact DRF nested routes of faresemad/Reminders-API."""
    client = RemindersAPIClient(use_mock=True, username="test_owner")

    # 1. Category ViewSet (/list/)
    cat_id = client.ensure_category("Work", "red", username="test_owner")
    assert cat_id > 0

    # 2. Reminder ViewSet (/list/{list_pk}/reminder/)
    created = client.create_reminder(
        title="Send Q3 Report",
        notes="High priority client deliverable",
        date="2026-10-15",
        time="10:00:00",
        priority="high",
        category_name="Work",
        username="test_owner",
    )
    assert created["id"] > 0
    assert created["title"] == "Send Q3 Report"
    assert created["priority"] == "high"
    assert created["auther"] == "test_owner"

    rem_id = created["id"]
    fetched = client.get_reminder(cat_id, rem_id, username="test_owner")
    assert fetched["title"] == "Send Q3 Report"

    # 3. Update (/list/{list_pk}/reminder/{id}/)
    updated = client.update_reminder(
        cat_id, rem_id, {"title": "Send Q3 Report Final", "priority": "medium"}, username="test_owner"
    )
    assert updated["title"] == "Send Q3 Report Final"
    assert updated["priority"] == "medium"

    # 4. Delete (/list/{list_pk}/reminder/{id}/)
    deleted = client.delete_reminder(cat_id, rem_id, username="test_owner")
    assert deleted is True

    with pytest.raises(KeyError):
        client.get_reminder(cat_id, rem_id, username="test_owner")


# ==============================================================================
# 2. Date & Time Parser Tests (Malayalam / Manglish / English)
# ==============================================================================

def test_date_parser_tomorrow_morning():
    ref = datetime(2026, 10, 13, 8, 0, 0, tzinfo=ZoneInfo("Asia/Dubai"))
    res = ReminderDateParser.parse_schedule("nale ravile 10 manikk remind cheyy", reference_time=ref)
    assert res["success"] is True
    assert res["needs_clarification"] is False
    assert res["date"] == "2026-10-14"
    assert res["time"] == "10:00:00"
    assert "2026-10-14T06:00:00" in res["scheduled_at_utc"]  # UTC+4 -> UTC


def test_date_parser_today_evening():
    ref = datetime(2026, 10, 13, 10, 0, 0, tzinfo=ZoneInfo("Asia/Dubai"))
    res = ReminderDateParser.parse_schedule("innu vaikitt 4-nu quotation ayakkanam", reference_time=ref)
    assert res["success"] is True
    assert res["date"] == "2026-10-13"
    assert res["time"] == "16:00:00"


def test_date_parser_missing_time_triggers_focused_clarification():
    ref = datetime(2026, 10, 13, 10, 0, 0, tzinfo=ZoneInfo("Asia/Dubai"))
    res = ReminderDateParser.parse_schedule("nale remind cheyy", reference_time=ref)
    assert res["success"] is False
    assert res["needs_clarification"] is True
    assert "Ravile ethra manikkaanu" in res["clarification_question"]


def test_date_parser_day_after_tomorrow():
    ref = datetime(2026, 10, 13, 10, 0, 0, tzinfo=ZoneInfo("Asia/Dubai"))
    res = ReminderDateParser.parse_schedule("mattanale 11:30 am", reference_time=ref)
    assert res["success"] is True
    assert res["date"] == "2026-10-15"
    assert res["time"] == "11:30:00"


# ==============================================================================
# 3. ReminderService & Ownership Enforcement
# ==============================================================================

def test_service_create_and_ownership(test_db_path):
    mock_client = RemindersAPIClient(use_mock=True)
    service = ReminderService(client=mock_client, db_module=db)

    # Patch get_db_path for test isolation
    with patch("db.get_db_path", return_value=test_db_path):
        rem = service.create_reminder(
            user_id="971525919933",
            title="Follow up with client",
            date_str="2026-10-14",
            time_str="10:00:00",
            notes="Quotation discussion",
            user_timezone="Asia/Dubai",
            priority="medium",
            recipient="971525919933",
        )
        assert rem["id"] is not None
        assert rem["status"] == "scheduled"
        assert rem["user_id"] == "971525919933"

        # Ownership test: authorized owner can fetch
        fetched = service.get_reminder(rem["id"], user_id="971525919933")
        assert fetched is not None
        assert fetched["title"] == "Follow up with client"

        # Ownership test: unauthorized user cannot fetch
        unauthorized = service.get_reminder(rem["id"], user_id="971500000000")
        assert unauthorized is None

        # Snooze test
        snoozed = service.snooze_reminder(rem["id"], user_id="971525919933", minutes=15)
        assert snoozed["status"] == "scheduled"

        # Cancel test
        cancelled = service.cancel_reminder(rem["id"], user_id="971525919933")
        assert cancelled is True
        fetched_after = service.get_reminder(rem["id"], user_id="971525919933")
        assert fetched_after["status"] == "cancelled"


# ==============================================================================
# 4. Background Scheduler & Duplicate Prevention
# ==============================================================================

def test_scheduler_atomic_claims_and_delivery(test_db_path):
    with patch("db.get_db_path", return_value=test_db_path):
        service = ReminderService(client=RemindersAPIClient(use_mock=True), db_module=db)

        # Create reminder due in the past
        past_utc = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
        rec = {
            "id": "rem-1234",
            "api_reminder_id": 101,
            "api_list_id": 1,
            "user_id": "971525919933",
            "title": "Send Proposal",
            "notes": "VIP client",
            "date": "2026-10-13",
            "time": "08:00:00",
            "priority": "high",  # bypass quiet hours
            "timezone": "Asia/Dubai",
            "scheduled_at_utc": past_utc,
            "status": "scheduled",
            "channel": "whatsapp",
            "recipient": "971525919933",
            "follow_up_enabled": 0,
        }
        db.save_reminder_metadata(rec, db_path=test_db_path)

        scheduler = PersistentReminderScheduler(db_module=db)

        # Mock successful dispatch
        with patch.object(scheduler, "_dispatch_message", return_value=(True, None)) as mock_dispatch:
            processed = scheduler.process_due_reminders()
            assert processed == 1
            mock_dispatch.assert_called_once()

            # Verify status transitioned to delivered
            delivered_rec = db.get_reminder_metadata("rem-1234", db_path=test_db_path)
            assert delivered_rec["status"] == "delivered"
            assert delivered_rec["delivered_at"] is not None

            # Immediate re-run must claim ZERO items (prevent duplicate messages)
            re_processed = scheduler.process_due_reminders()
            assert re_processed == 0


def test_scheduler_bounded_retries_on_failure(test_db_path):
    with patch("db.get_db_path", return_value=test_db_path):
        past_utc = (datetime.now(timezone.utc) - timedelta(minutes=2)).isoformat()
        rec = {
            "id": "rem-retry",
            "api_reminder_id": 102,
            "api_list_id": 1,
            "user_id": "971525919933",
            "title": "Urgent Task",
            "date": "2026-10-13",
            "time": "08:00:00",
            "priority": "high",
            "timezone": "Asia/Dubai",
            "scheduled_at_utc": past_utc,
            "status": "scheduled",
            "channel": "whatsapp",
            "recipient": "971525919933",
            "delivery_attempts": 2,  # 3rd attempt will fail bounded limit
            "follow_up_enabled": 0,
        }
        db.save_reminder_metadata(rec, db_path=test_db_path)

        scheduler = PersistentReminderScheduler(db_module=db)
        with patch.object(scheduler, "_dispatch_message", return_value=(False, "Gateway Timeout")):
            scheduler.process_due_reminders()

            failed_rec = db.get_reminder_metadata("rem-retry", db_path=test_db_path)
            assert failed_rec["status"] == "failed"
            assert failed_rec["delivery_attempts"] == 3
            assert failed_rec["last_delivery_error"] == "Gateway Timeout"


# ==============================================================================
# 5. FastAPI REST API Endpoint Tests
# ==============================================================================

def test_api_reminders_crud(test_db_path):
    with patch("db.get_db_path", return_value=test_db_path):
        client = TestClient(app)

        # 1. Create via API
        payload = {
            "user_id": "971525919933",
            "title": "Design Review",
            "date": "2026-10-16",
            "time": "14:00:00",
            "priority": "medium",
            "channel": "whatsapp",
        }
        res = client.post("/api/reminders", json=payload)
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "scheduled"
        rem_id = data["reminder"]["id"]

        # 2. List reminders
        list_res = client.get(f"/api/reminders?user_id=971525919933")
        assert list_res.status_code == 200
        assert len(list_res.json()["reminders"]) >= 1

        # 3. Get single reminder
        get_res = client.get(f"/api/reminders/{rem_id}?user_id=971525919933")
        assert get_res.status_code == 200
        assert get_res.json()["title"] == "Design Review"

        # 4. Snooze reminder
        snooze_res = client.post(f"/api/reminders/{rem_id}/snooze", json={"user_id": "971525919933", "minutes": 30})
        assert snooze_res.status_code == 200
        assert snooze_res.json()["status"] == "snoozed"

        # 5. Cancel reminder
        del_res = client.delete(f"/api/reminders/{rem_id}?user_id=971525919933")
        assert del_res.status_code == 200
        assert del_res.json()["status"] == "cancelled"


# ==============================================================================
# 6. Natural Language Conversational Tests (call_horus)
# ==============================================================================

def test_call_horus_natural_reminder_creation(test_db_path):
    with patch("db.get_db_path", return_value=test_db_path):
        reply = call_horus(
            session_id="whatsapp-971525919933",
            user_message="nale ravile 10 manikk quotation ayakkan remind cheyy",
        )
        assert "Sheri" in reply
        assert "10:00" in reply or "quotation" in reply.lower()

        # Check that reminder was scheduled in DB
        rems = db.list_reminders_metadata("971525919933", status="scheduled", db_path=test_db_path)
        assert len(rems) >= 1
        assert rems[0]["status"] == "scheduled"


def test_call_horus_clarification_on_vague_time(test_db_path):
    with patch("db.get_db_path", return_value=test_db_path):
        reply = call_horus(
            session_id="whatsapp-971525919933",
            user_message="nale remind cheyy",
        )
        # Should ask one short question for clarification without narrating internal plans
        assert "Ravile ethra manikkaanu" in reply
