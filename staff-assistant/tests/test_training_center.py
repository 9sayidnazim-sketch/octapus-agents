"""Tests for the Agent Training Center API endpoints and admin authorization."""
import pytest
from fastapi.testclient import TestClient
from app import app
from db import init_db

AUTH_HEADERS = {"x-staff-password": "octapus-dev-staff-2026"}


@pytest.fixture
def client(monkeypatch, tmp_path):
    test_db = tmp_path / "test_training.db"
    init_db(test_db)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{test_db}")
    monkeypatch.setenv("STAFF_PASSWORD", "octapus-dev-staff-2026")
    return TestClient(app)


def test_training_endpoints_require_admin_auth(client):
    # Unauthenticated requests must receive 401
    assert client.get("/training/instructions").status_code == 401
    assert client.post("/training/instructions", json={"title": "T", "content": "C"}).status_code == 401
    assert client.get("/training/knowledge").status_code == 401
    assert client.get("/training/skills").status_code == 401
    assert client.get("/training/logs").status_code == 401
    assert client.post("/training/test-chat", json={"message": "hi"}).status_code == 401


def test_instructions_crud(client):
    # 1. Create
    res = client.post(
        "/training/instructions",
        headers=AUTH_HEADERS,
        json={"title": "Concise Tone", "content": "Answer in under 2 sentences.", "priority": 1, "active": 1}
    )
    assert res.status_code == 200
    inst = res.json()["instruction"]
    inst_id = inst["id"]
    assert inst["title"] == "Concise Tone"

    # 2. List
    list_res = client.get("/training/instructions", headers=AUTH_HEADERS)
    assert list_res.status_code == 200
    items = list_res.json()["instructions"]
    assert any(i["id"] == inst_id for i in items)

    # 3. Update
    up_res = client.put(
        f"/training/instructions/{inst_id}",
        headers=AUTH_HEADERS,
        json={"title": "Ultra Concise", "content": "1 sentence only.", "priority": 2, "active": 1}
    )
    assert up_res.status_code == 200
    assert up_res.json()["instruction"]["title"] == "Ultra Concise"

    # 4. Delete
    del_res = client.delete(f"/training/instructions/{inst_id}", headers=AUTH_HEADERS)
    assert del_res.status_code == 200


def test_knowledge_text_and_search(client):
    res = client.post(
        "/training/knowledge",
        headers=AUTH_HEADERS,
        json={
            "title": "UAE Corporate Tax Overview",
            "content": "UAE Corporate tax is levied at 9% on taxable net profit exceeding AED 375,000. Businesses under AED 375,000 enjoy a 0% rate.",
            "tags": "tax, uae, finance",
            "source": "ministry_guide.pdf"
        }
    )
    assert res.status_code == 200
    chunks = res.json()["chunks"]
    assert len(chunks) >= 1
    chunk_id = chunks[0]["id"]

    # Search
    search_res = client.get("/training/knowledge?q=Corporate+tax", headers=AUTH_HEADERS)
    assert search_res.status_code == 200
    assert len(search_res.json()["knowledge"]) >= 1

    # Delete
    del_res = client.delete(f"/training/knowledge/{chunk_id}", headers=AUTH_HEADERS)
    assert del_res.status_code == 200


def test_skills_listing_and_update(client):
    # List skills
    res = client.get("/training/skills", headers=AUTH_HEADERS)
    assert res.status_code == 200
    skills = res.json()["skills"]
    assert len(skills) >= 5
    assert any(s["skill_id"] == "answering" for s in skills)

    # Update skill
    up_res = client.put(
        "/training/skills/answering",
        headers=AUTH_HEADERS,
        json={
            "enabled": 1,
            "extra_instructions": "Always verify against latest policies.",
            "tone": "Warm & Professional",
            "language": "auto",
            "templates": "Let me double-check that with management."
        }
    )
    assert up_res.status_code == 200
    assert up_res.json()["skill"]["tone"] == "Warm & Professional"


def test_test_chat_and_correction_flow(client):
    # Add instruction and knowledge
    client.post(
        "/training/instructions",
        headers=AUTH_HEADERS,
        json={"title": "Official Hours", "content": "Office hours are Monday to Friday 9am to 6pm.", "priority": 1, "active": 1}
    )
    client.post(
        "/training/knowledge",
        headers=AUTH_HEADERS,
        json={"title": "HQ Location", "content": "Octapus HQ is situated in Business Bay, Dubai.", "tags": "location", "source": "docs"}
    )

    # Test Chat sandbox call
    chat_res = client.post(
        "/training/test-chat",
        headers=AUTH_HEADERS,
        json={"message": "Where is your office located?"}
    )
    assert chat_res.status_code == 200
    data = chat_res.json()
    assert "reply" in data
    assert any(i["title"] == "Official Hours" for i in data["used_instructions"])
    assert any(k["title"] == "HQ Location" for k in data["used_knowledge_chunks"])

    # Submit correction with create_instruction=True
    corr_res = client.post(
        "/training/corrections",
        headers=AUTH_HEADERS,
        json={
            "query": "Where is your office?",
            "bot_reply": "I am not sure.",
            "correction": "Our headquarters is in Business Bay, Dubai.",
            "rating": "down",
            "create_instruction": True
        }
    )
    assert corr_res.status_code == 200
    assert corr_res.json()["correction"]["instruction_id"] is not None


def test_training_logs_and_restore(client):
    # 1. Create instruction
    res = client.post(
        "/training/instructions",
        headers=AUTH_HEADERS,
        json={"title": "Original Rule", "content": "Rule text", "priority": 1, "active": 1}
    )
    inst_id = res.json()["instruction"]["id"]

    # 2. Delete it (which logs delete_instruction)
    client.delete(f"/training/instructions/{inst_id}", headers=AUTH_HEADERS)

    # 3. Check logs
    logs_res = client.get("/training/logs", headers=AUTH_HEADERS)
    assert logs_res.status_code == 200
    logs = logs_res.json()["logs"]
    delete_log = next((l for l in logs if l["action"] == "delete_instruction"), None)
    assert delete_log is not None

    # 4. Restore the deleted instruction from the log
    restore_res = client.post(f"/training/logs/{delete_log['id']}/restore", headers=AUTH_HEADERS)
    assert restore_res.status_code == 200

    # 5. Verify the instruction is back in the list
    list_res = client.get("/training/instructions", headers=AUTH_HEADERS)
    assert any(i["id"] == inst_id for i in list_res.json()["instructions"])
