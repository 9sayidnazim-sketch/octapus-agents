"""Documenting skill: generates clean summaries, executive reports, and itemized invoice documents."""
from __future__ import annotations

from typing import Any, Dict
from .base import BaseSkill


class DocumentingSkill(BaseSkill):
    """Produces structured executive summaries, business reports, and invoice documents."""

    @property
    def skill_id(self) -> str:
        return "documenting"

    @property
    def name(self) -> str:
        return "Documenting"

    @property
    def description(self) -> str:
        return "Produces summaries, business reports, and invoices as clean documents on request."

    def format_prompt_section(self, config: Dict[str, Any]) -> str:
        tone = config.get("tone", "Formal")
        extra = config.get("extra_instructions", "").strip()
        templates = config.get("templates", "").strip()

        lines = [
            "### Skill: Document Generation (Reports, Summaries & Invoices)",
            "- When asked to summarize or document:",
            "  * Summaries: Present TL;DR, Key Findings, Action Items, and Next Steps.",
            "  * Business Reports: Include Executive Summary, Metrics/Analysis, and Recommendations.",
            "  * Invoices: Format in clean markdown tables containing: Item Description, Qty, Rate, Total, Subtotal, VAT (5% in UAE), and Final Amount, plus Payment Terms.",
            f"- Document presentation tone: {tone}.",
        ]
        if templates:
            lines.append(f"- Document format templates: {templates}")
        if extra:
            lines.append(f"- Extra documenting rules: {extra}")
        return "\n".join(lines)

    def execute(self, input_data: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "status": "ready",
            "formats": ["summary", "report", "invoice_table"],
        }
