import sys
from pathlib import Path
import pytest

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from db import (
    add_memory_fact,
    add_message,
    create_conversation,
    get_conversation,
    get_conversation_messages,
    init_db,
    update_conversation,
)
from chat_engine import build_conversation_context


@pytest.fixture(autouse=True)
def setup_test_db(tmp_path, monkeypatch):
    """Isolate database for memory engine tests."""
    test_db = tmp_path / "test_memory.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{test_db}")
    init_db(test_db)
    yield


def test_context_builder_order_and_approved_facts():
    """Verify context builder includes approved facts only and formats recent messages."""
    conv_id = create_conversation(title="Client Alpha Discussion")

    # Add 1 approved fact and 1 unapproved fact
    f_approved = add_memory_fact(
        fact="Client Alpha budget is $50,000",
        source="Kickoff meeting",
        is_approved=True,
        conversation_id=conv_id,
    )
    f_pending = add_memory_fact(
        fact="Client Alpha might switch vendors",
        source="Rumor",
        is_approved=False,
        conversation_id=conv_id,
    )

    # Add messages
    add_message(conv_id, role="user", content="What is Alpha's budget?")
    add_message(conv_id, role="assistant", content="Alpha's budget is $50k.")

    sys_prompt, messages, facts_used = build_conversation_context(
        conversation_id=conv_id, recent_limit=10
    )

    # Approved fact must be in context
    assert "Client Alpha budget is $50,000" in sys_prompt
    assert len(facts_used) == 1
    assert facts_used[0]["id"] == f_approved

    # Unapproved fact must NOT be in context
    assert "Client Alpha might switch vendors" not in sys_prompt

    # Messages verbatim
    assert len(messages) == 2
    assert messages[0]["content"] == "What is Alpha's budget?"


def test_conversation_continuity_and_recent_limit():
    """Verify older messages are capped by recent_limit and rolling summary is preserved."""
    conv_id = create_conversation(title="Long Project Discussion")
    update_conversation(conv_id, summary="Client previously agreed to milestone 1.")

    # Add 25 messages
    for i in range(25):
        role = "user" if i % 2 == 0 else "assistant"
        add_message(conv_id, role=role, content=f"Message turn number {i}")

    sys_prompt, messages, _ = build_conversation_context(
        conversation_id=conv_id, recent_limit=10
    )

    # Only last 10 messages should be returned verbatim
    assert len(messages) == 10
    assert messages[-1]["content"] == "Message turn number 24"
    assert messages[0]["content"] == "Message turn number 15"

    # Rolling summary is preserved in system prompt
    assert "Client previously agreed to milestone 1." in sys_prompt


def test_model_switching_preserves_history():
    """Verify that switching models preserves full conversation history."""
    conv_id = create_conversation(title="Model Switch Chat", provider="anthropic", model="claude-sonnet-5-5")

    add_message(conv_id, role="user", content="Step 1 details")
    add_message(conv_id, role="assistant", content="Here are step 1 details")

    # Switch conversation model to openai gpt-4o
    update_conversation(conv_id, provider="openai", model="gpt-4o")

    # Verify updated model
    conv = get_conversation(conv_id)
    assert conv["model"] == "gpt-4o"
    assert conv["provider"] == "openai"

    # Context builder still receives the exact same complete history
    _, messages, _ = build_conversation_context(conv_id)
    assert len(messages) == 2
    assert messages[0]["content"] == "Step 1 details"
