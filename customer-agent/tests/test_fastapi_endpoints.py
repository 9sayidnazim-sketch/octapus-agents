from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch
import pytest

import db
from app import app


@pytest.fixture(autouse=True)
def setup_test_db(tmp_path, monkeypatch):
    test_db = tmp_path / "test_api.db"
    monkeypatch.setenv("DATABASE_URL", str(test_db))
    db.init_db()
    yield


client = TestClient(app)


def test_health_and_capabilities_endpoints():
    res_health = client.get("/health")
    assert res_health.status_code == 200
    data = res_health.json()
    assert data["status"] == "ok"
    assert "capabilities" in data

    res_cap = client.get("/api/capabilities")
    assert res_cap.status_code == 200
    cap_data = res_cap.json()
    assert "tools" in cap_data
    assert "create_reminder" in cap_data["tools"]
    assert "generate_document" in cap_data["tools"]
    assert "save_memory" in cap_data["tools"]


def test_chat_endpoint_with_image_and_text():
    sample_b64 = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="

    with patch("app.call_horus", return_value="Sheri, image kandu.") as mock_horus:
        res = client.post(
            "/chat",
            json={
                "message": "Inspect this receipt",
                "image_data": sample_b64,
                "session_id": "sess_101",
            },
        )
        assert res.status_code == 200
        json_out = res.json()
        assert json_out["reply"] == "Sheri, image kandu."
        assert json_out["session_id"] == "sess_101"
        assert mock_horus.called
        assert mock_horus.call_args[1]["image_data"] == sample_b64
