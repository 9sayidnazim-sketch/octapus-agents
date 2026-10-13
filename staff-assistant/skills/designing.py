"""Designing skill: generates design briefs, layout wireframes, and clean HTML/SVG mockups."""
from __future__ import annotations

from typing import Any, Dict
from .base import BaseSkill


class DesigningSkill(BaseSkill):
    """Produces design briefs, layout structures, and clean inline HTML/SVG mockups upon request."""

    @property
    def skill_id(self) -> str:
        return "designing"

    @property
    def name(self) -> str:
        return "Designing"

    @property
    def description(self) -> str:
        return "Produces design briefs, UI layouts, color palettes, or clean HTML/SVG designs on request."

    def format_prompt_section(self, config: Dict[str, Any]) -> str:
        tone = config.get("tone", "Creative")
        extra = config.get("extra_instructions", "").strip()
        templates = config.get("templates", "").strip()

        lines = [
            "### Skill: Design & Creative Direction",
            "- When asked for visual designs, layout concepts, logos, or UI layouts:",
            "  * Provide a structured Design Brief (Theme, Color Palette with Hex codes, Typography, Visual Hierarchy).",
            "  * If requested to draw or visualize, produce self-contained, responsive inline SVG or clean modern HTML/CSS.",
            "  * Ensure high aesthetics: subtle gradients, dark mode support, and clean modern spacing.",
            f"- Design tone: {tone}.",
        ]
        if templates:
            lines.append(f"- Preferred design framework/templates: {templates}")
        if extra:
            lines.append(f"- Extra design instructions: {extra}")
        return "\n".join(lines)

    def execute(self, input_data: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "status": "ready",
            "capabilities": ["design_brief", "wireframe_layout", "svg_generation", "html_mockup"],
        }
