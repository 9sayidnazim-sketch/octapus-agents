import sys
from pathlib import Path
import httpx
import pytest

# Ensure staff-assistant is in sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from api_client import OctapusApiClient
from tools import dispatch_tool


def test_get_client_success():
    """Test successful client retrieval with mock transport."""
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == "/v1/clients/c-123"
        assert request.headers.get("x-api-key") == "test-key"
        return httpx.Response(
            200,
            json={"id": "c-123", "name": "Babul Matheen", "status": "active"},
        )

    transport = httpx.MockTransport(handler)
    client = OctapusApiClient(base_url="https://api.example.com/v1", api_key="test-key", transport=transport)
    result = client.get_client("c-123")

    assert result == {"id": "c-123", "name": "Babul Matheen", "status": "active"}


def test_get_client_401():
    """Test 401 Unauthorized error handling."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "Invalid API key"})

    transport = httpx.MockTransport(handler)
    client = OctapusApiClient(base_url="https://api.example.com/v1", api_key="wrong-key", transport=transport)
    result = client.get_client("c-123")

    assert "error" in result
    assert "401" in result["error"]


def test_get_client_404():
    """Test 404 Resource Not Found error handling."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"detail": "Not found"})

    transport = httpx.MockTransport(handler)
    client = OctapusApiClient(base_url="https://api.example.com/v1", api_key="test-key", transport=transport)
    result = client.get_client("c-unknown")

    assert "error" in result
    assert "404" in result["error"]
    assert "/clients/c-unknown" in result["error"]


def test_get_projects_timeout():
    """Test request timeout error handling."""
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("Connection timed out after 10.0s")

    transport = httpx.MockTransport(handler)
    client = OctapusApiClient(base_url="https://api.example.com/v1", api_key="test-key", transport=transport)
    result = client.get_projects(status="open")

    assert "error" in result
    assert "timed out" in result["error"].lower()


def test_write_requires_confirmation():
    """Test that write operation requires user confirmation before calling API."""
    called_api = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        called_api["count"] += 1
        assert request.method == "POST"
        assert request.url.path == "/v1/leads"
        return httpx.Response(201, json={"id": "lead-999", "name": "Castle Craft", "status": "created"})

    transport = httpx.MockTransport(handler)
    client = OctapusApiClient(base_url="https://api.example.com/v1", api_key="test-key", transport=transport)
    session = {}

    lead_payload = {
        "name": "Castle Craft Contracting LLC",
        "service": "Website revamp",
        "contact": "ajay@octapus.ae",
    }

    # Step 1: Initial tool call without explicit confirmation
    result_step1 = dispatch_tool(
        name="create_lead",
        tool_input=lead_payload,
        api_client=client,
        session=session,
        is_confirmed=False,
    )

    # Verify write was NOT sent to API yet
    assert called_api["count"] == 0
    assert result_step1["status"] == "pending_confirmation"
    assert result_step1["requires_confirmation"] is True
    assert "pending_action" in session
    assert session["pending_action"]["tool_name"] == "create_lead"
    assert session["pending_action"]["tool_input"] == lead_payload

    # Step 2: Confirmation explicitly granted in next user interaction
    result_step2 = dispatch_tool(
        name="create_lead",
        tool_input=session["pending_action"]["tool_input"],
        api_client=client,
        session=session,
        is_confirmed=True,
    )

    # Verify write WAS sent to API
    assert called_api["count"] == 1
    assert result_step2 == {"id": "lead-999", "name": "Castle Craft", "status": "created"}
    assert session["pending_action"] is None
