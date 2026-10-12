import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from app import app
from db import init_db


@pytest.fixture
def client(tmp_path, monkeypatch):
    """Setup test client with isolated SQLite database and MASTER_KEY."""
    test_db = tmp_path / "test_api.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{test_db}")
    monkeypatch.setenv("MASTER_KEY", "test-master-key-encryption-passphrase")
    monkeypatch.setenv("STAFF_PASSWORD", "octapus-dev-staff-2026")
    init_db(test_db)
    return TestClient(app)


AUTH_HEADER = {"X-Staff-Password": "octapus-dev-staff-2026"}


def test_auth_protection_on_all_settings_endpoints(client):
    """Verify that all settings endpoints return 401 without valid staff password."""
    assert client.get("/settings").status_code == 401
    assert client.get("/providers").status_code == 401
    assert client.get("/models").status_code == 401
    assert client.get("/assistant").status_code == 401
    assert client.get("/memory/facts").status_code == 401
    assert client.get("/conversations").status_code == 401
    assert client.get("/usage").status_code == 401
    assert client.post("/data/export").status_code == 401
    assert client.post("/data/clear", json={"confirmation": "DELETE ALL DATA"}).status_code == 401


def test_provider_key_crud_lifecycle_and_masking(client):
    """Verify adding, listing, testing, and deleting keys with masking and encryption."""
    with patch("providers.openai_adapter.OpenAIAdapter.test_connection") as mock_test:
        mock_test.return_value = {"ok": True, "model_count": 5, "error": None}

        # 1. Add OpenAI Key
        res = client.post(
            "/providers",
            headers=AUTH_HEADER,
            json={
                "provider": "openai",
                "label": "Work Key",
                "api_key": "sk-proj-1234567890abcdef",
                "is_default": True,
            },
        )
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "ok"
        assert "sk-proj" not in data["masked_key"]
        assert data["masked_key"] == "••••••••cdef"
        key_id = data["id"]

        # 2. List Providers - full key must NEVER appear
        res_list = client.get("/providers", headers=AUTH_HEADER)
        assert res_list.status_code == 200
        providers = res_list.json()["providers"]
        assert len(providers) == 1
        assert providers[0]["masked_key"] == "••••••••cdef"
        assert "1234567890" not in json.dumps(res_list.json())

        # 3. Test Connection
        res_test = client.post(f"/providers/{key_id}/test", headers=AUTH_HEADER)
        assert res_test.status_code == 200
        assert res_test.json()["ok"] is True

        # 4. Delete Key
        res_del = client.delete(f"/providers/{key_id}", headers=AUTH_HEADER)
        assert res_del.status_code == 200

        # Verify key is gone
        res_list2 = client.get("/providers", headers=AUTH_HEADER)
        assert len(res_list2.json()["providers"]) == 0


def test_missing_master_key_blocks_key_saving(client, monkeypatch):
    """Verify that saving keys is refused when MASTER_KEY is not configured."""
    monkeypatch.delenv("MASTER_KEY", raising=False)

    res = client.post(
        "/providers",
        headers=AUTH_HEADER,
        json={"provider": "openai", "label": "Test", "api_key": "sk-123456"},
    )
    assert res.status_code == 400
    assert "MASTER_KEY" in res.json()["detail"]


def test_memory_facts_approval_workflow(client):
    """Verify memory fact proposing, approving, editing, and deleting."""
    # 1. Propose fact (unapproved by default)
    res = client.post(
        "/memory/facts",
        headers=AUTH_HEADER,
        json={"fact": "Client preferred contact is Telegram", "source": "chat", "is_approved": False},
    )
    assert res.status_code == 200
    fact_id = res.json()["id"]

    # 2. List facts
    facts = client.get("/memory/facts", headers=AUTH_HEADER).json()["facts"]
    assert len(facts) == 1
    assert facts[0]["is_approved"] == 0

    # 3. Approve fact
    res_app = client.post(f"/memory/facts/{fact_id}/approve", headers=AUTH_HEADER)
    assert res_app.status_code == 200

    # Verify approved
    facts2 = client.get("/memory/facts", headers=AUTH_HEADER).json()["facts"]
    assert facts2[0]["is_approved"] == 1

    # 4. Delete fact
    res_del = client.delete(f"/memory/facts/{fact_id}", headers=AUTH_HEADER)
    assert res_del.status_code == 200


def test_data_clear_typed_confirmation(client):
    """Verify typed confirmation required to clear all data."""
    # Wrong confirmation text -> 400
    res_bad = client.post(
        "/data/clear",
        headers=AUTH_HEADER,
        json={"confirmation": "delete please"},
    )
    assert res_bad.status_code == 400
    assert "typed confirmation mismatch" in res_bad.json()["detail"].lower()

    # Correct confirmation text -> 200
    res_good = client.post(
        "/data/clear",
        headers=AUTH_HEADER,
        json={"confirmation": "DELETE ALL DATA"},
    )
    assert res_good.status_code == 200
    assert res_good.json()["status"] == "ok"
