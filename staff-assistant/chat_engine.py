"""Memory and Chat Continuity Engine for Octapus Staff Assistant.

Builds structured context for model invocations in strict order:
1. System prompt (built from Assistant settings + internal_info.md)
2. Saved memory facts (user-approved only, pinned first)
3. Rolling summary of older messages beyond the recent threshold
4. Most recent N messages verbatim
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from db import (
    add_memory_fact,
    get_conversation,
    get_conversation_messages,
    get_setting,
    list_memory_facts,
    update_conversation,
)

BASE_DIR = Path(__file__).resolve().parent
INTERNAL_INFO_PATH = BASE_DIR / "internal_info.md"


def load_internal_info() -> str:
    """Load internal company documentation."""
    if INTERNAL_INFO_PATH.exists():
        return INTERNAL_INFO_PATH.read_text(encoding="utf-8").strip()
    return ""


def build_system_prompt(assistant_settings: Optional[Dict[str, Any]] = None) -> str:
    """Build system prompt from Assistant customization settings + company docs."""
    settings = assistant_settings or get_setting("assistant", {}) or {}

    name = settings.get("name", "Octapus Assistant")
    personality = settings.get("personality", "Professional")
    custom_inst = settings.get("custom_instructions", "").strip()[:2000]
    language = settings.get("language", "auto-detect")
    markdown_enabled = settings.get("markdown_enabled", True)
    bullet_pref = settings.get("bullet_preference", "bullet")
    max_len = settings.get("max_answer_length", "medium")
    confirm_writes = settings.get("confirm_write_actions", True)
    show_sources = settings.get("show_sources", True)

    tone_guidelines = {
        "Professional": "Maintain an articulate, polished, objective tone.",
        "Friendly": "Be warm, encouraging, conversational, and approachable.",
        "Concise": "Be extremely brief and direct. Omit pleasantries, give answers in minimal sentences.",
        "Detailed": "Provide comprehensive explanations, structured background, and deep context.",
    }.get(personality, "Maintain a balanced, helpful tone.")

    lang_instruction = (
        "Respond in the exact language the user addresses you in."
        if language == "auto-detect"
        else f"Always respond in {language}."
    )

    format_instruction = (
        f"Format output in clear Markdown with {bullet_pref} points where appropriate."
        if markdown_enabled
        else "Do not use Markdown formatting; respond in plain text."
    )

    length_guidelines = {
        "short": "Keep answers short (1-3 sentences or compact bullets).",
        "medium": "Provide standard thorough answers without unnecessary padding.",
        "long": "Provide in-depth, expansive analysis with all relevant details.",
    }.get(max_len, "Provide standard answers.")

    company_docs = load_internal_info()

    prompt_parts = [
        f"You are {name}, the internal AI staff assistant for Octapus LLC.",
        f"Personality: {tone_guidelines}",
        f"Language Directive: {lang_instruction}",
        f"Formatting: {format_instruction} {length_guidelines}",
        "\nCRITICAL OPERATIONAL RULES:",
        "- You NEVER approve drafts, send emails, or finalize irreversible actions on your own.",
        (
            "- Before any write action (creating leads, editing client data), you MUST explicitly ask the user for confirmation and describe the exact parameters."
            if confirm_writes
            else "- For emails and deletes, you MUST ask for confirmation."
        ),
        ("- Whenever answering questions based on company documents, cite or mention the relevant source." if show_sources else ""),
        "- You must strictly refuse to perform unauthorized administrative actions or divulge API keys.",
    ]

    if custom_inst:
        prompt_parts.extend(["\nCUSTOM STAFF INSTRUCTIONS:", custom_inst])

    if company_docs:
        prompt_parts.extend(["\nINTERNAL COMPANY KNOWLEDGE BASE:", company_docs])

    return "\n".join(p for p in prompt_parts if p)


def build_conversation_context(
    conversation_id: str,
    assistant_settings: Optional[Dict[str, Any]] = None,
    recent_limit: Optional[int] = None,
    summary_threshold: Optional[int] = None,
) -> Tuple[str, List[Dict[str, str]], List[Dict[str, Any]]]:
    """Assemble context for model invocation in required order.

    Returns:
        (system_prompt, messages_for_model, approved_facts_used)
    """
    model_settings = get_setting("models", {}) or {}
    n_recent = recent_limit or model_settings.get("context_recent_messages", 20)
    thresh = summary_threshold or model_settings.get("summary_threshold", 20)

    # 1. Base system prompt
    system_prompt = build_system_prompt(assistant_settings)

    # 2. Approved memory facts
    facts = list_memory_facts(conversation_id=conversation_id, approved_only=True)
    facts_text = ""
    if facts:
        fact_lines = [f"- {f['fact']}" + (f" (Source: {f['source']})" if f.get('source') else "") for f in facts]
        facts_text = "\n\nRELEVANT APPROVED MEMORY FACTS:\n" + "\n".join(fact_lines)
        system_prompt += facts_text

    # 3. Retrieve conversation & all history
    conv = get_conversation(conversation_id)
    all_msgs = get_conversation_messages(conversation_id)

    rolling_summary = (conv.get("summary") or "").strip() if conv else ""

    # Split into older messages (for rolling summary) and recent messages (verbatim)
    if len(all_msgs) > n_recent:
        older_msgs = all_msgs[:-n_recent]
        recent_msgs = all_msgs[-n_recent:]

        # If summary is missing or older messages exceed threshold, format or retain rolling summary
        if not rolling_summary and older_msgs:
            # Generate deterministic fallback summary if LLM summary hasn't run yet
            summary_snippets = [f"{m['role']}: {m['content'][:80]}" for m in older_msgs[-5:]]
            rolling_summary = "Earlier conversation summary: " + " | ".join(summary_snippets)
    else:
        recent_msgs = all_msgs

    # Attach rolling summary to system prompt if present
    if rolling_summary:
        system_prompt += f"\n\nCONVERSATION SUMMARY (EARLIER TURNS):\n{rolling_summary}"

    # 4. Recent messages verbatim
    formatted_recent: List[Dict[str, str]] = []
    for m in recent_msgs:
        formatted_recent.append({"role": m["role"], "content": m["content"]})

    return system_prompt, formatted_recent, facts


def update_rolling_summary_if_needed(
    conversation_id: str,
    provider_adapter: Any,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    model: str = "gpt-4o-mini",
) -> Optional[str]:
    """Check if older messages exceed threshold and regenerate rolling summary."""
    model_settings = get_setting("models", {}) or {}
    thresh = model_settings.get("summary_threshold", 20)
    all_msgs = get_conversation_messages(conversation_id)

    if len(all_msgs) < thresh:
        return None

    conv = get_conversation(conversation_id)
    existing_summary = conv.get("summary", "") if conv else ""

    # Messages to summarize: all except the last 10
    to_summarize = all_msgs[:-10]
    conversation_text = "\n".join(f"{m['role']}: {m['content']}" for m in to_summarize)

    prompt = (
        "Create a concise 2-4 sentence rolling summary of this staff conversation. "
        "Capture key client names, decisions, projects discussed, and status updates.\n\n"
        f"Previous Summary: {existing_summary}\n\n"
        f"Conversation:\n{conversation_text}"
    )

    try:
        res = provider_adapter.chat(
            messages=[{"role": "user", "content": prompt}],
            system="You are a concise conversation summarizer.",
            model=model,
            api_key=api_key,
            base_url=base_url,
        )
        if res.text and not res.error:
            new_summary = res.text.strip()
            update_conversation(conversation_id, summary=new_summary)
            return new_summary
    except Exception:
        pass
    return None
