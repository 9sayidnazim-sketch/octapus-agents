import os
import tempfile
from pathlib import Path
import pytest
from unittest.mock import MagicMock

from tools.registry import CapabilityRegistry, CapabilityTool, create_default_registry
from tools.document_generator import DocumentGenerator
from reminders.service import ReminderService
import db


@pytest.fixture(autouse=True)
def setup_test_db(tmp_path, monkeypatch):
    test_db = tmp_path / "test_registry.db"
    monkeypatch.setenv("DATABASE_URL", str(test_db))
    db.init_db()
    yield


def test_registry_registration_and_schemas():
    mock_reminders = MagicMock()
    mock_doc = MagicMock()
    mock_bland = MagicMock()
    mock_bland.is_configured = True
    mock_email = MagicMock()
    mock_email.is_configured = False

    registry = create_default_registry(
        reminder_service=mock_reminders,
        db_module=db,
        doc_generator=mock_doc,
        bland_handler=mock_bland,
        email_handler=mock_email,
    )

    anthropic_tools = registry.get_anthropic_tools()
    tool_names = [t["name"] for t in anthropic_tools]

    assert "create_reminder" in tool_names
    assert "save_memory" in tool_names
    assert "get_memory" in tool_names
    assert "generate_document" in tool_names
    assert "make_phone_call" in tool_names
    # send_email is unconfigured, so it should NOT be in operational anthropic_tools
    assert "send_email" not in tool_names

    status = registry.get_status_report()
    assert status["send_email"]["operational"] is False
    assert "Resend API key" in status["send_email"]["reason"]
    assert status["create_reminder"]["operational"] is True


def test_registry_argument_validation():
    mock_reminders = MagicMock()
    mock_doc = MagicMock()
    mock_bland = MagicMock()
    mock_email = MagicMock()

    registry = create_default_registry(
        reminder_service=mock_reminders,
        db_module=db,
        doc_generator=mock_doc,
        bland_handler=mock_bland,
        email_handler=mock_email,
    )

    # Missing required 'title' in create_reminder
    res = registry.execute_tool("create_reminder", {}, context={"user_id": "test_user"})
    assert res["status"] == "error"
    assert "Missing required property 'title'" in res["error"]


def test_persistent_memory_tools():
    mock_reminders = MagicMock()
    mock_doc = MagicMock()
    mock_bland = MagicMock()
    mock_email = MagicMock()

    registry = create_default_registry(
        reminder_service=mock_reminders,
        db_module=db,
        doc_generator=mock_doc,
        bland_handler=mock_bland,
        email_handler=mock_email,
    )

    ctx = {"user_id": "user_42"}

    # 1. Save memory
    save_res = registry.execute_tool(
        "save_memory",
        {"key": "preferred_language", "value": "Manglish", "category": "preference"},
        context=ctx,
    )
    assert save_res["status"] == "saved"

    # 2. Get memory
    get_res = registry.execute_tool("get_memory", {"key": "preferred_language"}, context=ctx)
    assert get_res["status"] == "found"
    assert get_res["memory"]["value"] == "Manglish"

    # 3. Security test: refuse storing credentials
    sec_res = registry.execute_tool(
        "save_memory",
        {"key": "db_password", "value": "super_secret_123"},
        context=ctx,
    )
    assert sec_res["status"] == "security_violation"

    # 4. List memories
    list_res = registry.execute_tool("list_memories", {}, context=ctx)
    assert list_res["status"] == "success"
    assert list_res["count"] == 1

    # 5. Delete memory
    del_res = registry.execute_tool("delete_memory", {"key": "preferred_language"}, context=ctx)
    assert del_res["status"] == "deleted"

    # Verify deleted
    get_again = registry.execute_tool("get_memory", {"key": "preferred_language"}, context=ctx)
    assert get_again["status"] == "not_found"


def test_document_generation_tool(tmp_path):
    doc_gen = DocumentGenerator(output_dir=tmp_path)
    mock_reminders = MagicMock()
    mock_bland = MagicMock()
    mock_email = MagicMock()

    registry = create_default_registry(
        reminder_service=mock_reminders,
        db_module=db,
        doc_generator=doc_gen,
        bland_handler=mock_bland,
        email_handler=mock_email,
    )

    res = registry.execute_tool(
        "generate_document",
        {
            "title": "Quarterly Service Summary",
            "format": "md",
            "content": "# Octapus Quarterly Report\nAll services operational.",
        },
        context={"user_id": "user_1"},
    )

    assert res["status"] in ("success", "generated")
    assert Path(res["file_path"]).exists()
    assert "Octapus Quarterly Report" in Path(res["file_path"]).read_text()
    assert res["download_url"].startswith("/static/generated_docs/")
