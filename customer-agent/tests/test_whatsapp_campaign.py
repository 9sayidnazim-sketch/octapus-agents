import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

import db
from app import app
from campaigns import (
    CampaignWorkflowManager,
    RecipientValidator,
    WhatsAppGateway,
    SendResult,
)
from campaigns.validator import DEFAULT_ALLOWED_RECIPIENTS



@pytest.fixture(autouse=True)
def setup_test_db(tmp_path, monkeypatch):
    test_db = tmp_path / "test_campaign.db"
    monkeypatch.setenv("DATABASE_URL", str(test_db))
    db.init_db()
    yield


@pytest.fixture
def client():
    return TestClient(app)


def test_validate_all_eight_team_numbers():
    """Verify all 8 designated team numbers validate correctly with country and formatting."""
    recipients = RecipientValidator.load_team_recipients(DEFAULT_ALLOWED_RECIPIENTS)
    assert len(recipients) == 8

    expected_countries = {
        "+918157070717": "India",
        "+971508621612": "United Arab Emirates",
        "+971545696499": "United Arab Emirates",
        "+918089170148": "India",
        "+918590851447": "India",
        "+919745482646": "India",
        "+919746283316": "India",
        "+971544556613": "United Arab Emirates",
    }

    for r in recipients:
        assert r.is_valid is True, f"Number {r.phone_number} should be valid"
        assert r.country == expected_countries[r.phone_number]
        assert r.clean_number.isdigit()
        assert r.formatted.startswith("+")
        assert len(r.clean_number) == 12


def test_validator_rejects_invalid_numbers():
    """Verify malformed or too short numbers are flagged as invalid."""
    invalid_short = RecipientValidator.validate_and_format("12345")
    assert invalid_short.is_valid is False
    assert "Invalid phone number length" in (invalid_short.validation_error or "")

    empty = RecipientValidator.validate_and_format("")
    assert empty.is_valid is False


def test_workflow_initial_test_mode_state():
    """Verify campaign is initialized in safe test mode with default Horus introduction."""
    manager = CampaignWorkflowManager(campaign_id="test-camp-init")
    state = manager.get_workflow_state()

    assert state["test_mode"] is True
    assert state["test_approved"] is False
    assert state["status"] == "draft"
    assert len(state["recipients"]) == 8
    assert "Good morning! ☀️" in state["message_template"]
    assert "— Horus AI 🤖" in state["message_template"]
    assert state["stats"]["delivered"] == 0


def test_workflow_update_template_and_tone():
    """Verify updating template and tone settings."""
    manager = CampaignWorkflowManager(campaign_id="test-camp-tpl")
    state = manager.update_template(
        template="Custom good morning message",
        tone="warm_professional",
    )
    assert state["message_template"] == "Custom good morning message"

    # Tone switch preset
    state_energetic = manager.update_template(template="", tone="energetic")
    assert "team! ☀️🚀" in state_energetic["message_template"]


def test_test_recipient_configuration():
    """Verify configuring explicit test recipient."""
    manager = CampaignWorkflowManager(campaign_id="test-camp-recip")
    rec = manager.set_test_recipient("+971508621612")
    assert rec.phone_number == "+971508621612"
    assert rec.country == "United Arab Emirates"

    state = manager.get_workflow_state()
    assert state["test_recipient"] == "+971508621612"

    with pytest.raises(ValueError):
        manager.set_test_recipient("invalid_num")


def test_send_test_message_safeguards():
    """Verify test message dispatches ONLY to test recipient and records delivery log."""
    mock_gateway = MagicMock(spec=WhatsAppGateway)
    mock_gateway.check_connection.return_value = {"is_online": True, "token_configured": True}
    mock_gateway.send_message.return_value = SendResult(
        success=True,
        recipient="+971508621612",
        clean_number="971508621612",
        timestamp="2026-10-13T10:00:00Z",
        status="delivered",
        status_code=200,
        message_id="msg_test_001",
        latency_ms=120.5,
    )

    manager = CampaignWorkflowManager(campaign_id="test-camp-send", gateway=mock_gateway)
    manager.set_test_recipient("+971508621612")

    result = manager.send_test_message()
    assert result.success is True
    assert result.status == "delivered"
    assert mock_gateway.send_message.call_count == 1

    # Verify log recorded
    state = manager.get_workflow_state()
    assert len(state["logs"]) == 1
    log = state["logs"][0]
    assert log["is_test"] == 1
    assert log["status"] == "delivered"
    assert log["phone_number"] == "+971508621612"


def test_rollout_blocked_without_test_approval():
    """Verify Phase 3 rollout is strictly blocked if test is not approved."""
    manager = CampaignWorkflowManager(campaign_id="test-camp-block")

    with pytest.raises(ValueError, match="Rollout requires explicit confirmation"):
        manager.execute_rollout(confirm=False)

    with pytest.raises(ValueError, match="Test message has not been approved yet"):
        manager.execute_rollout(confirm=True)


def test_approve_test_and_controlled_rollout():
    """Verify end-to-end flow: test sent -> approved -> controlled rollout with deduplication."""
    mock_gateway = MagicMock(spec=WhatsAppGateway)
    mock_gateway.check_connection.return_value = {"is_online": True, "token_configured": True}
    mock_gateway.send_message.return_value = SendResult(
        success=True,
        recipient="+971508621612",
        clean_number="971508621612",
        timestamp="2026-10-13T10:00:00Z",
        status="delivered",
        status_code=200,
        message_id="msg_test_002",
        latency_ms=110.0,
    )

    manager = CampaignWorkflowManager(campaign_id="test-camp-flow", gateway=mock_gateway)
    manager.set_test_recipient("+971508621612")
    manager.send_test_message()

    # Approve test
    appr_state = manager.approve_test()
    assert appr_state["test_approved"] is True

    # Execute rollout
    rollout_state = manager.execute_rollout(confirm=True, delay_seconds=0.0)
    assert rollout_state["status"] == "completed"
    assert rollout_state["dispatched_count"] == 8
    assert mock_gateway.send_message.call_count == 9  # 1 test + 8 rollout

    # Test deduplication: running rollout again should skip all 8
    rollout_again = manager.execute_rollout(confirm=True, delay_seconds=0.0)
    assert rollout_again["dispatched_count"] == 0
    assert mock_gateway.send_message.call_count == 9  # No new gateway calls


def test_rollout_halts_on_rate_limit():
    """Verify rollout halts immediately upon encountering rate limit (HTTP 429)."""
    mock_gateway = MagicMock(spec=WhatsAppGateway)
    mock_gateway.check_connection.return_value = {"is_online": True, "token_configured": True}

    # First call test succeeds
    mock_gateway.send_message.side_effect = [
        SendResult(
            success=True,
            recipient="+971508621612",
            clean_number="971508621612",
            timestamp="2026-10-13T10:00:00Z",
            status="delivered",
            status_code=200,
        ),
        # First rollout call succeeds
        SendResult(
            success=True,
            recipient="+918157070717",
            clean_number="918157070717",
            timestamp="2026-10-13T10:01:00Z",
            status="delivered",
            status_code=200,
        ),
        # Second rollout call encounters rate limit (429)
        SendResult(
            success=False,
            recipient="+971508621612",
            clean_number="971508621612",
            timestamp="2026-10-13T10:01:01Z",
            status="failed",
            status_code=429,
            error_details="HTTP 429: Too Many Requests",
            is_rate_limited=True,
        ),
    ]

    manager = CampaignWorkflowManager(campaign_id="test-camp-rate-limit", gateway=mock_gateway)
    manager.set_test_recipient("+971508621612")
    manager.send_test_message()
    manager.approve_test()

    res = manager.execute_rollout(confirm=True, delay_seconds=0.0)
    assert res["status"] == "paused"
    assert "WhatsApp rate limit (HTTP 429)" in res["aborted_reason"]
    # Ensure it halted and did not call remaining 6 contacts
    assert mock_gateway.send_message.call_count == 3


def test_fastapi_campaign_endpoints(client):
    """Test campaign REST endpoints via TestClient."""
    # 1. Get workflow
    res = client.get("/api/campaign/workflow")
    assert res.status_code == 200
    data = res.json()
    assert data["test_mode"] is True
    assert len(data["recipients"]) == 8

    # 2. Configure test recipient
    res_rec = client.post(
        "/api/campaign/test-recipient",
        json={"phone_number": "+971508621612"},
    )
    assert res_rec.status_code == 200
    assert res_rec.json()["recipient"]["clean_number"] == "971508621612"

    # 3. Update template
    res_tpl = client.put(
        "/api/campaign/template",
        json={"template": "Updated message test", "tone": "concise"},
    )
    assert res_tpl.status_code == 200
    assert res_tpl.json()["message_template"] == "Updated message test"
