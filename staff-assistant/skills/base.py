"""Base classes and interfaces for modular agent skills."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional


class BaseSkill(ABC):
    """Abstract base class for all modular agent skills."""

    @property
    @abstractmethod
    def skill_id(self) -> str:
        """Unique slug identifier for the skill (e.g. 'transcription')."""
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable display name."""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """Short description of what the skill provides."""
        pass

    @property
    def default_config(self) -> Dict[str, Any]:
        """Default configuration settings."""
        return {
            "enabled": True,
            "extra_instructions": "",
            "tone": "Professional",
            "language": "auto",
            "templates": "",
        }

    @abstractmethod
    def format_prompt_section(self, config: Dict[str, Any]) -> str:
        """Generate the prompt guidance to inject into the dynamic prompt when enabled."""
        pass

    def execute(self, input_data: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
        """Execute the skill on input data if applicable (e.g. audio processing, intent parsing)."""
        return {"status": "noop", "skill": self.skill_id}
