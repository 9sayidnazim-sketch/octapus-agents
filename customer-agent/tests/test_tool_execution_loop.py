import json
from unittest.mock import MagicMock, patch
import pytest

import db
from app import call_horus, capability_registry


@pytest.fixture(autouse=True)
def setup_test_db(tmp_path, monkeypatch):
    test_db = tmp_path / "test_loop.db"
    monkeypatch.setenv("DATABASE_URL", str(test_db))
    db.init_db()
    yield


def test_call_horus_tool_execution_loop():
    """Verify Horus calls tool, executes it, receives tool_result, and gives final text."""
    # First turn: model returns tool_use block
    mock_tool_block = MagicMock()
    mock_tool_block.type = "tool_use"
    mock_tool_block.id = "tool_123"
    mock_tool_block.name = "save_memory"
    mock_tool_block.input = {"key": "favorite_color", "value": "Blue", "category": "general"}

    first_response = MagicMock()
    first_response.stop_reason = "tool_use"
    first_response.content = [mock_tool_block]

    # Second turn: model returns final text after seeing tool_result
    mock_text_block = MagicMock()
    mock_text_block.type = "text"
    mock_text_block.text = "Sheri, njan Blue color remember cheythu."

    second_response = MagicMock()
    second_response.stop_reason = "end_turn"
    second_response.content = [mock_text_block]

    mock_client = MagicMock()
    mock_client.messages.create.side_effect = [first_response, second_response]

    with patch("app.get_client", return_value=mock_client):
        reply = call_horus(
            session_id="test_session_1",
            user_message="Enikku Blue color aanu ishtam, athu remember cheyy.",
        )

    assert "Blue" in reply
    assert mock_client.messages.create.call_count == 2

    # Verify that the tool was actually executed in the database!
    saved = db.get_memory(user_id="test_session_1", key="favorite_color")
    assert saved is not None
    assert saved["value"] == "Blue"


def test_call_horus_vision_and_reminder_tool():
    """Verify image attachment triggers multimodal block and executes create_reminder tool."""
    # Model detects due date from bill image and schedules reminder
    mock_tool_block = MagicMock()
    mock_tool_block.type = "tool_use"
    mock_tool_block.id = "tool_bill_999"
    mock_tool_block.name = "create_reminder"
    mock_tool_block.input = {
        "title": "Pay DEWA Bill (AED 350)",
        "date": "2026-10-24",
        "time": "09:00",
        "notes": "Due date is 2026-10-25",
    }

    first_resp = MagicMock()
    first_resp.stop_reason = "tool_use"
    first_resp.content = [mock_tool_block]

    mock_text_block = MagicMock()
    mock_text_block.type = "text"
    mock_text_block.text = "Sheri, bill amount AED 350 aanu. Due date-nu munp October 24-nu reminder set cheythu."

    second_resp = MagicMock()
    second_resp.stop_reason = "end_turn"
    second_resp.content = [mock_text_block]

    mock_client = MagicMock()
    mock_client.messages.create.side_effect = [first_resp, second_resp]

    # Sample 1x1 transparent PNG base64
    sample_b64 = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="

    with patch("app.get_client", return_value=mock_client):
        reply = call_horus(
            session_id="test_session_bill",
            user_message="Read this bill and remind me before the due date",
            image_data=sample_b64,
        )

    assert "AED 350" in reply
    assert mock_client.messages.create.call_count == 2

    # Verify initial user message contained multimodal image block
    first_call_args = mock_client.messages.create.call_args_list[0][1]
    messages_sent = first_call_args["messages"]
    user_msg = messages_sent[0]
    assert isinstance(user_msg["content"], list)
    assert any(b.get("type") == "image" for b in user_msg["content"])
