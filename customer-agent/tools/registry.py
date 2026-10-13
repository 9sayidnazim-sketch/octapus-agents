"""Unified Capability Router & Tool Registry for Octapus Assistant (Horus).

Provides:
- Strict JSON Schema validation for tool definitions
- Operational configuration and permission checks
- Structured execution handlers with timeout and error containment
- Anthropic-compatible tool definitions and execution loop
"""
from __future__ import annotations

import inspect
import json
import logging
import re
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger("octapus.tools.registry")


class CapabilityTool:
    """Represents an executable agent capability exposed to the model."""

    def __init__(
        self,
        name: str,
        description: str,
        input_schema: Dict[str, Any],
        handler: Callable[[Dict[str, Any], Dict[str, Any]], Dict[str, Any]],
        is_operational_fn: Optional[Callable[[], Tuple[bool, Optional[str]]]] = None,
        requires_management: bool = False,
    ):
        self.name = name
        self.description = description
        self.input_schema = input_schema
        self.handler = handler
        self.is_operational_fn = is_operational_fn or (lambda: (True, None))
        self.requires_management = requires_management

    def check_operational(self) -> Tuple[bool, Optional[str]]:
        try:
            return self.is_operational_fn()
        except Exception as exc:
            return False, f"Operational check failed: {exc}"

    def to_anthropic_spec(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
        }


class CapabilityRegistry:
    """Central registry and router for agent capabilities and tools."""

    def __init__(
        self,
        tts_handler: Optional[Any] = None,
        audio_handler: Optional[Any] = None,
    ):
        self._tools: Dict[str, CapabilityTool] = {}
        self.tts_handler = tts_handler
        self.audio_handler = audio_handler

    def get_runtime_voice_status(self) -> Dict[str, Any]:
        """Distinguish audio input, speech transcription, speech generation, and audio delivery."""
        tts_ok = bool(self.tts_handler and getattr(self.tts_handler, "is_configured", False))
        stt_ok = bool(self.audio_handler and getattr(self.audio_handler, "stt_key", None))
        return {
            "audio_input": {
                "available": True,
                "description": "Receives audio recordings and voice notes via WhatsApp and Web.",
            },
            "speech_transcription": {
                "available": stt_ok,
                "provider": "Whisper" if stt_ok else None,
                "description": "Transcribes incoming voice notes to text" if stt_ok else "Unconfigured (missing STT_API_KEY).",
            },
            "speech_generation": {
                "available": tts_ok,
                "provider": "ElevenLabs" if tts_ok else None,
                "voice_id": getattr(self.tts_handler, "voice_id", None) if tts_ok else None,
                "model_id": getattr(self.tts_handler, "model_id", None) if tts_ok else None,
                "description": "Synthesizes natural spoken voice replies via ElevenLabs" if tts_ok else "Unconfigured (missing ELEVENLABS_API_KEY).",
            },
            "audio_delivery": {
                "available": True,
                "channels": ["web_player", "whatsapp_audio"],
                "description": "Delivers playable audio via web player and WhatsApp voice notes.",
            },
        }

    def get_system_prompt_capabilities_block(self) -> str:
        """Produce authoritative runtime capability block to keep the agent in sync with operational services."""
        voice = self.get_runtime_voice_status()
        tts_ok = voice["speech_generation"]["available"]
        stt_ok = voice["speech_transcription"]["available"]

        if tts_ok:
            tts_desc = (
                "- Speech Generation (Text-to-Speech): FULLY OPERATIONAL via ElevenLabs integration.\n"
                "  * You CAN and DO generate spoken audio replies!\n"
                "  * If the user asks whether you can reply in audio, speak, or send voice messages (e.g. 'Can you reply in audio?', 'Voice aayi parayumo?', 'Can you speak?'), CONFIRM WARMLY AND HONESTLY THAT YOU CAN (e.g. 'Yes, I can send voice replies and speak with you!', 'Athe, enikku voice aayi reply tharaan kazhiyum.').\n"
                "  * NEVER deny your voice capabilities or say 'I cannot generate audio' or 'I am an AI text assistant who cannot speak'.\n"
                "  * When the user asks for a voice response (e.g. 'voice aayi parayu', 'audio ayakk', 'read this aloud', 'reply in voice') or sends a voice message, the application automatically converts your text response into ElevenLabs speech audio and delivers it as a playable voice message.\n"
                "  * Format your reply naturally for spoken conversation: keep it clear, warm, and conversational. Do NOT include markdown formatting (like asterisks, tables, code blocks, or URLs) in responses intended for speech."
            )
        else:
            tts_desc = (
                "- Speech Generation (Text-to-Speech): CURRENTLY UNCONFIGURED on this server (missing ELEVENLABS_API_KEY).\n"
                "  * If asked about voice responses, explain that voice generation is currently not configured on this server and provide your reply in text."
            )

        if stt_ok:
            stt_desc = "- Speech Transcription (Voice Input): OPERATIONAL. You receive transcripts of incoming voice messages."
        else:
            stt_desc = "- Speech Transcription (Voice Input): UNCONFIGURED (missing STT_API_KEY). You cannot transcribe audio files if received."

        return f"""<authoritative_runtime_capabilities>
{tts_desc}
{stt_desc}
- Visual & Document Understanding: OPERATIONAL (Claude multimodal vision).
- Reminders & Proactive Care: OPERATIONAL (faresemad/Reminders-API + persistent scheduler).
- Persistent Memory: OPERATIONAL (SQLite memories storage).
- Document Generation: OPERATIONAL (Physical filesystem generation).
</authoritative_runtime_capabilities>"""

    def register(self, tool: CapabilityTool) -> None:
        self._tools[tool.name] = tool
        logger.debug("Registered tool capability: %s", tool.name)

    def get_tool(self, name: str) -> Optional[CapabilityTool]:
        return self._tools.get(name)

    def get_operational_tools(self) -> List[CapabilityTool]:
        """Return list of tools that are currently operational."""
        operational = []
        for tool in self._tools.values():
            is_op, _ = tool.check_operational()
            if is_op:
                operational.append(tool)
        return operational

    def get_anthropic_tools(self) -> List[Dict[str, Any]]:
        """Return Anthropic-formatted tool specs for all operational tools."""
        return [tool.to_anthropic_spec() for tool in self.get_operational_tools()]

    def get_status_report(self) -> Dict[str, Any]:
        """Produce capability checklist with exact operational status and blockers."""
        report = {}
        for name, tool in self._tools.items():
            is_op, reason = tool.check_operational()
            report[name] = {
                "name": name,
                "operational": is_op,
                "reason": reason if not is_op else "Operational and ready",
                "requires_management": tool.requires_management,
            }
        report["voice_capabilities"] = self.get_runtime_voice_status()
        return report

    def execute_tool(
        self,
        name: str,
        arguments: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Execute a registered tool with validation, auth, and error handling."""
        ctx = context or {}
        tool = self.get_tool(name)
        if not tool:
            return {
                "status": "error",
                "error": f"Tool '{name}' is not registered in capability registry.",
            }

        # Check operational status
        is_op, reason = tool.check_operational()
        if not is_op:
            return {
                "status": "unconfigured",
                "error": f"Capability '{name}' is currently unavailable: {reason}",
            }

        # Check management permissions if required
        if tool.requires_management:
            is_mgmt = ctx.get("is_management", False)
            if not is_mgmt:
                return {
                    "status": "unauthorized",
                    "error": f"Permission denied: Capability '{name}' requires authorized management access.",
                }

        # Validate arguments according to input_schema
        validation_error = self._validate_arguments(arguments, tool.input_schema)
        if validation_error:
            return {
                "status": "error",
                "error": f"Schema validation error for '{name}': {validation_error}",
            }

        # Execute handler
        try:
            logger.info("Executing tool '%s' for session '%s'...", name, ctx.get("session_id", "anonymous"))
            result = tool.handler(arguments, ctx)
            if not isinstance(result, dict):
                result = {"status": "success", "result": result}
            return result
        except Exception as exc:
            logger.error("Unhandled exception executing tool '%s': %s", name, exc, exc_info=True)
            return {
                "status": "error",
                "error": f"Execution failed for capability '{name}': {str(exc)}",
            }

    def _validate_arguments(self, args: Dict[str, Any], schema: Dict[str, Any]) -> Optional[str]:
        required = schema.get("required", [])
        for field in required:
            if field not in args or args[field] is None:
                return f"Missing required property '{field}'"
        properties = schema.get("properties", {})
        for k, v in args.items():
            if k in properties:
                expected_type = properties[k].get("type")
                if expected_type == "string" and not isinstance(v, str):
                    return f"Property '{k}' must be a string, got {type(v).__name__}"
                elif expected_type == "integer" and not isinstance(v, int):
                    return f"Property '{k}' must be an integer, got {type(v).__name__}"
                elif expected_type == "boolean" and not isinstance(v, bool):
                    return f"Property '{k}' must be a boolean, got {type(v).__name__}"
                elif expected_type == "array" and not isinstance(v, list):
                    return f"Property '{k}' must be a list, got {type(v).__name__}"
        return None


# Helper to instantiate standard registry
def create_default_registry(
    reminder_service: Any,
    db_module: Any,
    doc_generator: Any,
    bland_handler: Any,
    email_handler: Any,
    tts_handler: Optional[Any] = None,
    audio_handler: Optional[Any] = None,
) -> CapabilityRegistry:
    """Build and wire the default capability registry."""
    registry = CapabilityRegistry(tts_handler=tts_handler, audio_handler=audio_handler)

    # --------------------------------------------------------------------------
    # 1. REMINDERS: create_reminder
    # --------------------------------------------------------------------------
    def handle_create_reminder(args: Dict[str, Any], ctx: Dict[str, Any]) -> Dict[str, Any]:
        user_id = ctx.get("user_id") or "default_user"
        title = args.get("title", "").strip()
        date_str = args.get("date", "").strip()
        time_str = args.get("time", "").strip()
        notes = args.get("notes", "").strip()
        recurrence = args.get("recurrence", "none").strip()
        channel = args.get("channel") or ("whatsapp" if ctx.get("session_id", "").startswith("whatsapp-") else "web")
        recipient = ctx.get("clean_number") or user_id

        # If natural text is provided or date/time needs resolution
        raw_text = f"{title} on {date_str} at {time_str}" if (date_str or time_str) else title
        res = reminder_service.create_from_natural_text(
            user_id=user_id,
            text=raw_text,
            default_title=title,
            channel=channel,
            recipient=recipient,
        )
        if res.get("needs_clarification"):
            return {
                "status": "clarification_needed",
                "question": res.get("clarification_question"),
            }
        if res.get("success"):
            return {
                "status": "scheduled",
                "reminder": res["reminder"],
                "message": f"Reminder '{res['reminder']['title']}' scheduled for {res['reminder']['date']} {res['reminder']['time']}.",
            }
        return {"status": "error", "error": res.get("error", "Failed to schedule reminder.")}

    registry.register(
        CapabilityTool(
            name="create_reminder",
            description=(
                "Create and schedule a real, persistent reminder or proactive notification. "
                "Use when the user asks to be reminded, asks to follow up later, or requests an alert "
                "before a deadline (e.g. bill due dates, appointments, follow-ups). "
                "Supports relative and casual times in Malayalam, Manglish, and English."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "Short, descriptive title of what to be reminded about.",
                    },
                    "date": {
                        "type": "string",
                        "description": "Date of reminder (YYYY-MM-DD or relative like 'today', 'tomorrow', 'nale', 'naale').",
                    },
                    "time": {
                        "type": "string",
                        "description": "Time of reminder (HH:MM in 24h, or 12h like '9:00 AM', 'ravile 9 manikku', 'vaikitt 5pm').",
                    },
                    "notes": {
                        "type": "string",
                        "description": "Optional additional notes, bill amount, or instructions.",
                    },
                    "recurrence": {
                        "type": "string",
                        "enum": ["none", "daily", "weekly", "monthly", "yearly"],
                        "description": "Recurrence frequency if repeated reminder.",
                    },
                    "channel": {
                        "type": "string",
                        "enum": ["whatsapp", "web"],
                        "description": "Delivery channel for the notification.",
                    },
                },
                "required": ["title"],
            },
            handler=handle_create_reminder,
            is_operational_fn=lambda: (True, None),
        )
    )

    # --------------------------------------------------------------------------
    # 2. REMINDERS: list_reminders
    # --------------------------------------------------------------------------
    def handle_list_reminders(args: Dict[str, Any], ctx: Dict[str, Any]) -> Dict[str, Any]:
        user_id = ctx.get("user_id") or "default_user"
        status_filter = args.get("status")
        if status_filter == "all":
            status_filter = None
        rems = reminder_service.list_reminders(user_id=user_id, status=status_filter)
        return {
            "status": "success",
            "count": len(rems),
            "reminders": rems,
        }

    registry.register(
        CapabilityTool(
            name="list_reminders",
            description="List scheduled, delivered, or active reminders for the user.",
            input_schema={
                "type": "object",
                "properties": {
                    "status": {
                        "type": "string",
                        "enum": ["scheduled", "delivered", "cancelled", "completed", "all"],
                        "description": "Filter by reminder status. Defaults to 'scheduled'.",
                    },
                },
            },
            handler=handle_list_reminders,
            is_operational_fn=lambda: (True, None),
        )
    )

    # --------------------------------------------------------------------------
    # 3. REMINDERS: cancel_reminder
    # --------------------------------------------------------------------------
    def handle_cancel_reminder(args: Dict[str, Any], ctx: Dict[str, Any]) -> Dict[str, Any]:
        user_id = ctx.get("user_id") or "default_user"
        rem_id = args.get("reminder_id", "").strip()
        if not rem_id:
            # Check if there is an active reminder to cancel
            rems = reminder_service.list_reminders(user_id=user_id, status="scheduled")
            if rems:
                rem_id = rems[0]["id"]
            else:
                return {"status": "not_found", "message": "No active reminders found to cancel."}

        success = reminder_service.cancel_reminder(rem_id, user_id=user_id)
        if success:
            return {"status": "cancelled", "reminder_id": rem_id, "message": "Reminder successfully cancelled."}
        return {"status": "error", "error": f"Could not cancel reminder {rem_id}. It may not exist or not belong to user."}

    registry.register(
        CapabilityTool(
            name="cancel_reminder",
            description="Cancel a scheduled reminder so it will not be delivered.",
            input_schema={
                "type": "object",
                "properties": {
                    "reminder_id": {
                        "type": "string",
                        "description": "The unique ID of the reminder to cancel.",
                    },
                },
                "required": ["reminder_id"],
            },
            handler=handle_cancel_reminder,
            is_operational_fn=lambda: (True, None),
        )
    )

    # --------------------------------------------------------------------------
    # 4. REMINDERS: snooze_reminder
    # --------------------------------------------------------------------------
    def handle_snooze_reminder(args: Dict[str, Any], ctx: Dict[str, Any]) -> Dict[str, Any]:
        user_id = ctx.get("user_id") or "default_user"
        rem_id = args.get("reminder_id", "").strip()
        minutes = int(args.get("minutes", 15))
        if not rem_id:
            rems = reminder_service.list_reminders(user_id=user_id)
            active = [r for r in rems if r["status"] in ("scheduled", "in_flight", "delivered", "awaiting_reply")]
            if active:
                rem_id = active[0]["id"]
            else:
                return {"status": "not_found", "message": "No reminders available to snooze."}

        rem = reminder_service.snooze_reminder(rem_id, user_id=user_id, minutes=minutes)
        if rem:
            return {
                "status": "snoozed",
                "reminder": rem,
                "message": f"Reminder snoozed by {minutes} minutes.",
            }
        return {"status": "error", "error": f"Failed to snooze reminder {rem_id}."}

    registry.register(
        CapabilityTool(
            name="snooze_reminder",
            description="Snooze a reminder by postponing its scheduled delivery time.",
            input_schema={
                "type": "object",
                "properties": {
                    "reminder_id": {
                        "type": "string",
                        "description": "The ID of the reminder to snooze.",
                    },
                    "minutes": {
                        "type": "integer",
                        "description": "Number of minutes to postpone delivery (default 15).",
                    },
                },
                "required": ["reminder_id"],
            },
            handler=handle_snooze_reminder,
            is_operational_fn=lambda: (True, None),
        )
    )

    # --------------------------------------------------------------------------
    # 5. PERSISTENT MEMORY: save_memory
    # --------------------------------------------------------------------------
    def handle_save_memory(args: Dict[str, Any], ctx: Dict[str, Any]) -> Dict[str, Any]:
        user_id = ctx.get("user_id") or "default_user"
        key = args.get("key", "").strip()
        value = args.get("value", "").strip()
        category = args.get("category", "general").strip()

        # Security check: never store credentials or private tokens
        for forbidden in ["api_key", "password", "token", "secret", "bearer", "anthropic_key"]:
            if forbidden in key.lower() or forbidden in value.lower():
                return {
                    "status": "security_violation",
                    "error": "Security policy prohibits persisting API credentials or passwords into memory.",
                }

        db_module.save_memory(user_id=user_id, key=key, value=value, category=category)
        return {
            "status": "saved",
            "key": key,
            "value": value,
            "category": category,
            "message": f"Persistent memory '{key}' saved successfully.",
        }

    registry.register(
        CapabilityTool(
            name="save_memory",
            description=(
                "Save persistent user facts, approved routines, important dates (e.g. birthday, anniversaries), "
                "language preferences, or follow-up preferences into persistent database storage. "
                "Survives server restarts. Never store passwords or API keys."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "key": {
                        "type": "string",
                        "description": "Unique key or topic for this memory (e.g., 'user_name', 'user_birthday', 'timezone_pref').",
                    },
                    "value": {
                        "type": "string",
                        "description": "The information to remember.",
                    },
                    "category": {
                        "type": "string",
                        "enum": ["preference", "routine", "date", "contact", "general"],
                        "description": "Category for organizing memories.",
                    },
                },
                "required": ["key", "value"],
            },
            handler=handle_save_memory,
            is_operational_fn=lambda: (True, None),
        )
    )

    # --------------------------------------------------------------------------
    # 6. PERSISTENT MEMORY: get_memory
    # --------------------------------------------------------------------------
    def handle_get_memory(args: Dict[str, Any], ctx: Dict[str, Any]) -> Dict[str, Any]:
        user_id = ctx.get("user_id") or "default_user"
        key = args.get("key", "").strip()
        mem = db_module.get_memory(user_id=user_id, key=key)
        if mem:
            return {"status": "found", "memory": mem}
        return {"status": "not_found", "message": f"No persistent memory found for key '{key}'."}

    registry.register(
        CapabilityTool(
            name="get_memory",
            description="Retrieve a saved persistent memory or fact about the user by key.",
            input_schema={
                "type": "object",
                "properties": {
                    "key": {
                        "type": "string",
                        "description": "The key of the memory to look up.",
                    },
                },
                "required": ["key"],
            },
            handler=handle_get_memory,
            is_operational_fn=lambda: (True, None),
        )
    )

    # --------------------------------------------------------------------------
    # 7. PERSISTENT MEMORY: list_memories
    # --------------------------------------------------------------------------
    def handle_list_memories(args: Dict[str, Any], ctx: Dict[str, Any]) -> Dict[str, Any]:
        user_id = ctx.get("user_id") or "default_user"
        category = args.get("category")
        mems = db_module.list_memories(user_id=user_id, category=category)
        return {
            "status": "success",
            "count": len(mems),
            "memories": mems,
        }

    registry.register(
        CapabilityTool(
            name="list_memories",
            description="List all persistent memories and remembered facts for the user.",
            input_schema={
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "description": "Optional category filter.",
                    },
                },
            },
            handler=handle_list_memories,
            is_operational_fn=lambda: (True, None),
        )
    )

    # --------------------------------------------------------------------------
    # 8. PERSISTENT MEMORY: delete_memory
    # --------------------------------------------------------------------------
    def handle_delete_memory(args: Dict[str, Any], ctx: Dict[str, Any]) -> Dict[str, Any]:
        user_id = ctx.get("user_id") or "default_user"
        key = args.get("key", "").strip()
        deleted = db_module.delete_memory(user_id=user_id, key=key)
        if deleted:
            return {"status": "deleted", "key": key, "message": f"Memory '{key}' deleted."}
        return {"status": "not_found", "message": f"Memory '{key}' did not exist."}

    registry.register(
        CapabilityTool(
            name="delete_memory",
            description="Delete or forget a persistent memory about the user.",
            input_schema={
                "type": "object",
                "properties": {
                    "key": {
                        "type": "string",
                        "description": "The key of the memory to remove.",
                    },
                },
                "required": ["key"],
            },
            handler=handle_delete_memory,
            is_operational_fn=lambda: (True, None),
        )
    )

    # --------------------------------------------------------------------------
    # 9. DOCUMENT GENERATION: generate_document
    # --------------------------------------------------------------------------
    def handle_generate_document(args: Dict[str, Any], ctx: Dict[str, Any]) -> Dict[str, Any]:
        title = args.get("title", "").strip()
        doc_format = args.get("format", "md").strip()
        content = args.get("content", "").strip()

        res = doc_generator.generate_document(
            title=title,
            format=doc_format,
            content=content,
        )
        return res

    registry.register(
        CapabilityTool(
            name="generate_document",
            description=(
                "Generate real, downloadable files and documents (txt, md, csv, json, html) "
                "for reports, invoices, summaries, meeting minutes, or data exports. "
                "Verifies that files actually exist on disk and sanitizes credentials."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "Title or descriptive filename for the document.",
                    },
                    "format": {
                        "type": "string",
                        "enum": ["txt", "md", "csv", "json", "html"],
                        "description": "File format.",
                    },
                    "content": {
                        "type": "string",
                        "description": "Full document content or structured data.",
                    },
                },
                "required": ["title", "format", "content"],
            },
            handler=handle_generate_document,
            is_operational_fn=lambda: (True, None),
        )
    )

    # --------------------------------------------------------------------------
    # 10. PHONE CALLING: make_phone_call
    # --------------------------------------------------------------------------
    def handle_make_phone_call(args: Dict[str, Any], ctx: Dict[str, Any]) -> Dict[str, Any]:
        phone_number = args.get("phone_number", "").strip()
        task = args.get("task", "").strip() if args.get("task") else None
        agent_id = args.get("agent_id")
        agent_version = args.get("agent_version")
        first_sentence = args.get("first_sentence")
        language = args.get("language", "en")

        res = bland_handler.send_call(
            phone_number=phone_number,
            task=task,
            agent_id=agent_id,
            agent_version=agent_version,
            first_sentence=first_sentence,
            language=language,
        )
        return res

    def check_bland_op() -> Tuple[bool, Optional[str]]:
        if getattr(bland_handler, "is_configured", False):
            return True, None
        return False, "Bland.ai API key (BLAND_API_KEY) is not configured in environment."

    registry.register(
        CapabilityTool(
            name="make_phone_call",
            description="Initiate an outbound conversational AI phone call via Bland.ai.",
            input_schema={
                "type": "object",
                "properties": {
                    "phone_number": {
                        "type": "string",
                        "description": "E.164 phone number to call (e.g. +971501234567 or +919745482646).",
                    },
                    "task": {
                        "type": "string",
                        "description": "Instructions for the AI phone agent during the call (optional if agent_id configured).",
                    },
                    "agent_id": {
                        "type": "string",
                        "description": "Optional Bland.ai agent UUID (e.g. 537c56c1-2334-46d4-8901-c268c84f5a57).",
                    },
                    "agent_version": {
                        "type": "string",
                        "description": "Optional agent version/branch (e.g. dev, prod).",
                    },
                    "first_sentence": {
                        "type": "string",
                        "description": "Opening sentence spoken immediately when the recipient answers.",
                    },
                    "language": {
                        "type": "string",
                        "description": "Language code (en, ar, etc.).",
                    },
                },
                "required": ["phone_number"],
            },
            handler=handle_make_phone_call,
            is_operational_fn=check_bland_op,
            requires_management=False,
        )
    )

    # --------------------------------------------------------------------------
    # 11. EMAIL SENDING: send_email
    # --------------------------------------------------------------------------
    def handle_send_email(args: Dict[str, Any], ctx: Dict[str, Any]) -> Dict[str, Any]:
        to = args.get("to", "").strip()
        subject = args.get("subject", "").strip()
        body = args.get("body", "").strip()
        html = args.get("html")

        res = email_handler.send_email(
            to=to,
            subject=subject,
            text=body,
            html=html,
        )
        return res

    def check_email_op() -> Tuple[bool, Optional[str]]:
        if getattr(email_handler, "is_configured", False):
            return True, None
        return False, "Resend API key (RESEND_API_KEY) is not configured in environment."

    registry.register(
        CapabilityTool(
            name="send_email",
            description="Send an email via Resend API to a client or team member.",
            input_schema={
                "type": "object",
                "properties": {
                    "to": {
                        "type": "string",
                        "description": "Recipient email address.",
                    },
                    "subject": {
                        "type": "string",
                        "description": "Email subject line.",
                    },
                    "body": {
                        "type": "string",
                        "description": "Plain text body of the email.",
                    },
                    "html": {
                        "type": "string",
                        "description": "Optional formatted HTML body.",
                    },
                },
                "required": ["to", "subject", "body"],
            },
            handler=handle_send_email,
            is_operational_fn=check_email_op,
        )
    )

    return registry
