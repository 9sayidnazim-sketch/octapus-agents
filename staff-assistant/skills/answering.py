"""Answering skill: answers strictly from saved knowledge or defers responsibly."""
from __future__ import annotations

from typing import Any, Dict
from .base import BaseSkill


class AnsweringSkill(BaseSkill):
    """Enforces truthful answers from verified knowledge; defers without guessing if unknown."""

    @property
    def skill_id(self) -> str:
        return "answering"

    @property
    def name(self) -> str:
        return "Answering"

    @property
    def description(self) -> str:
        return "Answers questions strictly using saved knowledge. If not found in knowledge, says it will check instead of guessing."

    def format_prompt_section(self, config: Dict[str, Any]) -> str:
        tone = config.get("tone", "Helpful")
        extra = config.get("extra_instructions", "").strip()
        templates = config.get("templates", "").strip()
        fallback_msg = templates or (
            "I don't have that specific detail in our verified knowledge base yet. "
            "I will check with our team and verify this for you."
        )

        lines = [
            "### Skill: Strict Knowledge Answering",
            "- Rely ONLY on the provided Reference Knowledge and verified company documents.",
            "- If the answer to the customer's question is NOT found in the saved knowledge:",
            f"  * DO NOT guess, fabricate, or make up policies, prices, or answers.",
            f"  * Say that you will check instead of guessing (e.g.: \"{fallback_msg}\").",
            f"- Tone: {tone}.",
        ]
        if extra:
            lines.append(f"- Extra answering constraints: {extra}")
        return "\n".join(lines)

    def execute(self, input_data: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
        """Provides fallback message template if needed."""
        fallback = config.get("templates") or "I will check with our team regarding this and get back to you."
        return {
            "policy": "strict_grounding",
            "fallback_message": fallback,
        }
