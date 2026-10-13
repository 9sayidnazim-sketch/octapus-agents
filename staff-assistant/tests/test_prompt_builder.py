"""Tests for the dynamic prompt builder."""
from pathlib import Path
import pytest
from db import (
    init_db,
    create_training_instruction,
    update_training_instruction,
    add_training_knowledge,
    update_training_skill,
)
from prompt_builder import build_dynamic_prompt


@pytest.fixture
def test_db_path(tmp_path: Path):
    db_file = tmp_path / "test_prompt.db"
    init_db(db_file)
    return db_file


def test_prompt_builder_basic(test_db_path):
    prompt, meta = build_dynamic_prompt("hello", db_path=test_db_path)
    assert "Octapus Assistant" in prompt
    assert isinstance(meta["used_instructions"], list)
    assert isinstance(meta["used_knowledge_chunks"], list)
    assert isinstance(meta["enabled_skills"], list)


def test_prompt_builder_active_instructions_immediate_update(test_db_path):
    # 1. Initially no custom instructions
    prompt1, meta1 = build_dynamic_prompt("test query", db_path=test_db_path)
    assert "Rule Alpha" not in prompt1

    # 2. Add an active instruction
    inst = create_training_instruction(
        title="Rule Alpha",
        content="Always greet customers with 'Welcome to Octapus Dubai!'",
        priority=1,
        active=1,
        db_path=test_db_path
    )
    prompt2, meta2 = build_dynamic_prompt("test query", db_path=test_db_path)
    assert "Rule Alpha" in prompt2
    assert "Welcome to Octapus Dubai!" in prompt2
    assert any(i["id"] == inst["id"] for i in meta2["used_instructions"])

    # 3. Deactivate instruction - must immediately vanish without redeploy
    update_training_instruction(
        inst_id=inst["id"],
        title="Rule Alpha",
        content="Always greet customers with 'Welcome to Octapus Dubai!'",
        priority=1,
        active=0,
        db_path=test_db_path
    )
    prompt3, meta3 = build_dynamic_prompt("test query", db_path=test_db_path)
    assert "Rule Alpha" not in prompt3
    assert not any(i["id"] == inst["id"] for i in meta3["used_instructions"])


def test_prompt_builder_knowledge_chunk_matching(test_db_path):
    add_training_knowledge(
        title="Tailoring ERP Specs",
        text="The Octapus Tailoring ERP supports measurement recording, tailor assignment, and WhatsApp PDF invoices.",
        tags="erp, tailoring",
        source="specs.pdf",
        db_path=test_db_path
    )

    prompt, meta = build_dynamic_prompt("How does your tailoring ERP work?", db_path=test_db_path)
    assert "Tailoring ERP Specs" in prompt
    assert "WhatsApp PDF invoices" in prompt
    assert len(meta["used_knowledge_chunks"]) > 0


def test_prompt_builder_skill_settings(test_db_path):
    update_training_skill(
        skill_id="answering",
        enabled=1,
        extra_instructions="Do not disclose employee personal numbers under any circumstances.",
        tone="Strict",
        language="auto",
        templates="Please consult management.",
        db_path=test_db_path
    )

    prompt, meta = build_dynamic_prompt("Can I speak to someone?", db_path=test_db_path)
    assert "Do not disclose employee personal numbers" in prompt
    assert any(s["skill_id"] == "answering" for s in meta["enabled_skills"])
