"""Centralized Skill Registry: registers all skills in one place for easy extension."""
from __future__ import annotations

from typing import Dict, List, Optional
from .base import BaseSkill
from .transcription import AudioTranscriptionSkill
from .understanding import ReplyUnderstandingSkill
from .answering import AnsweringSkill
from .designing import DesigningSkill
from .documenting import DocumentingSkill


class SkillRegistry:
    """Registry managing available agent skills."""

    def __init__(self) -> None:
        self._skills: Dict[str, BaseSkill] = {}
        # Register default skills
        self.register(AudioTranscriptionSkill())
        self.register(ReplyUnderstandingSkill())
        self.register(AnsweringSkill())
        self.register(DesigningSkill())
        self.register(DocumentingSkill())

    def register(self, skill: BaseSkill) -> None:
        """Register a new modular skill."""
        self._skills[skill.skill_id] = skill

    def get(self, skill_id: str) -> Optional[BaseSkill]:
        """Look up skill by ID."""
        return self._skills.get(skill_id)

    def list_all(self) -> List[BaseSkill]:
        """List all registered skills."""
        return list(self._skills.values())

    def list_ids(self) -> List[str]:
        """List all registered skill IDs."""
        return list(self._skills.keys())


# Global singleton registry
skill_registry = SkillRegistry()


def get_skill(skill_id: str) -> Optional[BaseSkill]:
    """Helper to retrieve a skill from the global registry."""
    return skill_registry.get(skill_id)


def list_skills() -> List[BaseSkill]:
    """Helper to list all skills from the global registry."""
    return skill_registry.list_all()
