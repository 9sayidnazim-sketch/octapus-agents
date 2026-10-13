"""Dynamic Prompt Builder: constructs prompt from base prompt + active instructions + enabled skill settings + matching knowledge chunks."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    from . import db
    from .skills.registry import skill_registry
except ImportError:
    import db
    from skills.registry import skill_registry


def build_dynamic_prompt(
    user_message: str,
    assistant_settings: Optional[Dict[str, Any]] = None,
    db_path: Optional[Path] = None,
) -> Tuple[str, Dict[str, Any]]:
    """
    Constructs the system prompt dynamically on every incoming message.
    Components:
    1. Base prompt (assistant identity, tone, default rules)
    2. Active instructions (ordered by priority, title, content)
    3. Enabled skill settings (extra instructions, tone, language, templates)
    4. Top matching knowledge chunks for user_message
    """
    # 1. Base Prompt Settings
    settings = assistant_settings or db.get_setting("assistant", db.DEFAULT_SETTINGS.get("assistant", {}), db_path=db_path) or {}
    name = settings.get("name", "Octapus Assistant")
    personality = settings.get("personality", "Professional")
    base_instructions = settings.get("custom_instructions", "").strip()

    prompt_parts: List[str] = [
        f"You are {name}, a premier AI assistant.",
        f"Personality: {personality}.",
        "Provide accurate, courteous, and efficient assistance.",
    ]
    if base_instructions:
        prompt_parts.append(f"\n### Core Guidelines\n{base_instructions}")

    # 2. Active Instructions from Agent Training Center
    active_instructions = db.list_training_instructions(active_only=True, db_path=db_path)
    used_instructions_meta: List[Dict[str, Any]] = []

    if active_instructions:
        inst_lines = ["\n### Active Rules & Personality Instructions (High Priority)"]
        for inst in active_instructions:
            inst_lines.append(f"- **{inst['title']}** (Priority {inst.get('priority', 1)}): {inst['content']}")
            used_instructions_meta.append({
                "id": inst["id"],
                "title": inst["title"],
                "priority": inst.get("priority", 1),
            })
        prompt_parts.append("\n".join(inst_lines))

    # 3. Enabled Skills Configuration
    all_skills = db.list_training_skills(db_path=db_path)
    enabled_skills_meta: List[Dict[str, Any]] = []
    skill_prompts: List[str] = []

    for s_config in all_skills:
        if s_config.get("enabled", 1):
            sid = s_config["skill_id"]
            skill_obj = skill_registry.get(sid)
            if skill_obj:
                section = skill_obj.format_prompt_section(s_config)
                if section:
                    skill_prompts.append(section)
                enabled_skills_meta.append({
                    "skill_id": sid,
                    "name": s_config.get("name", sid),
                    "tone": s_config.get("tone", "default"),
                })

    if skill_prompts:
        prompt_parts.append("\n### Active Skill Modules & Behaviors\n" + "\n\n".join(skill_prompts))

    # 4. Top Matching Knowledge Chunks for the incoming query
    matching_chunks = db.get_top_matching_knowledge(user_message, limit=4, db_path=db_path)
    used_knowledge_meta: List[Dict[str, Any]] = []

    if matching_chunks:
        know_lines = ["\n### Verified Reference Knowledge & Studies"]
        know_lines.append("Use the following knowledge snippets to ground and formulate your answer:")
        for idx, chunk in enumerate(matching_chunks, start=1):
            title = chunk.get("title", f"Document Chunk {idx}")
            src = chunk.get("source", "knowledge_base")
            content = chunk.get("content", "").strip()
            know_lines.append(f"\n[Source: {src} | Title: {title}]\n{content}")
            used_knowledge_meta.append({
                "id": chunk["id"],
                "title": title,
                "source": src,
                "chunk_index": chunk.get("chunk_index", 0),
            })
        prompt_parts.append("\n".join(know_lines))
    else:
        prompt_parts.append("\n### Verified Reference Knowledge & Studies\n[No specific knowledge chunks found for this query.]")

    full_system_prompt = "\n\n".join(prompt_parts)

    metadata: Dict[str, Any] = {
        "used_instructions": used_instructions_meta,
        "used_knowledge_chunks": used_knowledge_meta,
        "enabled_skills": enabled_skills_meta,
    }

    return full_system_prompt, metadata
