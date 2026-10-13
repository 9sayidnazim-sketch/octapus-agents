import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import time
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock
import pytest

import db
from reminders.service import ReminderService
from reminders.scheduler import PersistentReminderScheduler


@pytest.fixture(autouse=True)
def setup_test_db(tmp_path, monkeypatch):
    test_db = tmp_path / "test_delivery.db"
    monkeypatch.setenv("DATABASE_URL", str(test_db))
    db.init_db()
    yield


def test_real_short_delay_reminder_delivery_and_cancellation():
    """Verify that a due reminder is delivered through the channel, while a cancelled reminder is never delivered."""
    delivered_calls = []

    def mock_delivery_sender(channel, recipient, text):
        delivered_calls.append({
            "channel": channel,
            "recipient": recipient,
            "text": text,
        })
        return True, None

    service = ReminderService()
    scheduler = PersistentReminderScheduler(dispatch_sender=mock_delivery_sender)

    # 1. Create a reminder due immediately
    now = datetime.now(timezone.utc)
    due_time = now - timedelta(seconds=2)  # Due 2 seconds ago

    rem1 = service.create_reminder(
        user_id="user_test_99",
        title="Immediate Test Alert",
        date_str=due_time.strftime("%Y-%m-%d"),
        time_str=due_time.strftime("%H:%M:%S"),
        channel="web",
        recipient="user_test_99",
    )
    rem1_id = rem1["id"]

    # 2. Create a second reminder that will be cancelled
    rem2 = service.create_reminder(
        user_id="user_test_99",
        title="Cancelled Test Alert",
        date_str=due_time.strftime("%Y-%m-%d"),
        time_str=due_time.strftime("%H:%M:%S"),
        channel="web",
        recipient="user_test_99",
    )
    rem2_id = rem2["id"]

    # Cancel reminder 2 before scheduler tick
    cancel_success = service.cancel_reminder(rem2_id, user_id="user_test_99")
    assert cancel_success is True

    # 3. Trigger scheduler processing tick
    delivered_count = scheduler.process_due_reminders()

    # 4. Confirm exactly 1 reminder was delivered (rem1), and rem2 was NOT delivered
    assert delivered_count == 1
    assert len(delivered_calls) == 1
    assert delivered_calls[0]["recipient"] == "user_test_99"
    assert "Immediate Test Alert" in delivered_calls[0]["text"]

    # Confirm rem2 was never delivered
    cancelled_delivered = [c for c in delivered_calls if "Cancelled Test Alert" in c["text"]]
    assert len(cancelled_delivered) == 0

    # Verify status in database
    rem1_fetched = service.get_reminder(rem1_id, user_id="user_test_99")
    assert rem1_fetched["status"] in ("delivered", "awaiting_reply")
    assert rem1_fetched.get("delivered_at") is not None

    rem2_fetched = service.get_reminder(rem2_id, user_id="user_test_99")
    assert rem2_fetched["status"] == "cancelled"


def test_restart_recovery_and_persistence(tmp_path, monkeypatch):
    """Confirm reminders and user context survive server restarts."""
    service1 = ReminderService()
    now = datetime.now(timezone.utc) + timedelta(hours=2)

    rem = service1.create_reminder(
        user_id="user_restart",
        title="Meeting with Client",
        date_str=now.strftime("%Y-%m-%d"),
        time_str=now.strftime("%H:%M:%S"),
        notes="Discuss AI Assistant roadmap",
    )
    rem_id = rem["id"]

    # Save memory in service 1
    db.save_memory("user_restart", "office_location", "Dubai Silicon Oasis", "preference")

    # Simulate restart by instantiating new service instances
    service2 = ReminderService()
    recovered_rem = service2.get_reminder(rem_id, user_id="user_restart")
    assert recovered_rem is not None
    assert recovered_rem["title"] == "Meeting with Client"
    assert recovered_rem["notes"] == "Discuss AI Assistant roadmap"

    recovered_mem = db.get_memory("user_restart", "office_location")
    assert recovered_mem is not None
    assert recovered_mem["value"] == "Dubai Silicon Oasis"
