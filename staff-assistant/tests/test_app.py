import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from app import app, pending_actions
from providers.base import ProviderResponse


@pytest.fixture
def client():
    return TestClient(app)


def test_index_page(client):
    """Verify that index.html is served and contains streaming logic."""
    response = client.get("/")
    assert response.status_code == 200
    assert "Octapus Staff Assistant" in response.text
    assert "createBotMessagePlaceholder" in response.text
    assert "text/event-stream" in response.text


def test_chat_unauthorized(client):
    """Verify 401 is returned when password is missing or wrong."""
    response = client.post("/chat", json={"message": "hello"})
    assert response.status_code == 401

    response = client.post(
        "/chat",
        headers={"X-Staff-Password": "wrong-password"},
        json={"message": "hello"},
    )
    assert response.status_code == 401


def test_chat_stream_immediate_cancellation(client):
    """Verify SSE streaming for immediate cancellation replies."""
    conv_id = "test-session-cancel"
    pending_actions[conv_id] = {
        "tool_name": "create_lead",
        "tool_input": {"name": "Test Client"},
    }

    response = client.post(
        "/chat",
        headers={"X-Staff-Password": "octapus-dev-staff-2026"},
        json={"message": "no", "conversation_id": conv_id, "stream": True},
    )

    assert response.status_code == 200
    assert "text/event-stream" in response.headers.get("content-type", "")

    # Parse SSE events from response text
    lines = [line for line in response.text.split("\n") if line.startswith("data: ")]
    events = [json.loads(line[6:]) for line in lines]

    assert len(events) >= 2
    assert "cancelled" in events[0].get("delta", "").lower()
    assert events[-1].get("done") is True


def test_chat_stream_response(client):
    """Verify SSE streaming with mocked provider adapter."""
    conv_id = "test-session-stream"

    mock_resp = ProviderResponse(
        text="Hello world!",
        usage={"input_tokens": 12, "output_tokens": 4},
    )

    with patch("providers.anthropic_adapter.AnthropicAdapter.chat", return_value=mock_resp):
        response = client.post(
            "/chat",
            headers={"X-Staff-Password": "octapus-dev-staff-2026"},
            json={"message": "Hi there", "conversation_id": conv_id, "stream": True},
        )

        assert response.status_code == 200
        assert "text/event-stream" in response.headers.get("content-type", "")

        lines = [line for line in response.text.split("\n") if line.startswith("data: ")]
        events = [json.loads(line[6:]) for line in lines]

        # Verify streaming deltas
        deltas = [e["delta"] for e in events if "delta" in e]
        assert len(deltas) > 0
        assert "".join(deltas).strip() == "Hello world!"

        # Verify done event
        done_events = [e for e in events if e.get("done") is True]
        assert len(done_events) == 1
        assert done_events[0]["reply"] == "Hello world!"
