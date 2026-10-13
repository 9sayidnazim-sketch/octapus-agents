from __future__ import annotations

import json
from typing import Any
from api_client import OctapusApiClient

# Claude tool definitions for Anthropic API
TOOLS = [
    {
        "name": "get_client",
        "description": "Look up information about a specific client by their ID or identifier from the Octapus API.",
        "input_schema": {
            "type": "object",
            "properties": {
                "client_id": {
                    "type": "string",
                    "description": "The unique client ID or identifier (e.g. '123' or 'babul-matheen').",
                }
            },
            "required": ["client_id"],
        },
    },
    {
        "name": "get_projects",
        "description": "Retrieve projects from the Octapus API, optionally filtered by status (default is 'open').",
        "input_schema": {
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "description": "Project status filter: 'open', 'completed', or 'all'.",
                    "default": "open",
                }
            },
        },
    },
    {
        "name": "create_lead",
        "description": (
            "Create a new client lead in the Octapus CRM/API. "
            "Call this tool when a user requests to create a lead; "
            "the system will stage the action so you can present the payload to the user for confirmation."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Client or company name.",
                },
                "service": {
                    "type": "string",
                    "description": "Requested service (e.g. 'Website design', 'Payment integration', 'ERP', 'WhatsApp integration').",
                },
                "source": {
                    "type": "string",
                    "description": "Lead source (e.g. Facebook, Instagram, Web, Referral, WhatsApp, Direct).",
                },
                "contact": {
                    "type": "string",
                    "description": "Contact person, phone number, or email.",
                },
                "notes": {
                    "type": "string",
                    "description": "Additional requirements or background notes.",
                },
            },
            "required": ["name"],
        },
    },
    {
        "name": "make_phone_call",
        "description": "Trigger an autonomous outbound AI phone call to a client or lead using Bland.ai.",
        "input_schema": {
            "type": "object",
            "properties": {
                "phone_number": {
                    "type": "string",
                    "description": "The client's phone number with international country code (e.g. +971525919933).",
                },
                "task": {
                    "type": "string",
                    "description": "Detailed instructions and objective for the AI phone agent during the call.",
                },
                "first_sentence": {
                    "type": "string",
                    "description": "Optional opening sentence when the client answers.",
                },
                "language": {
                    "type": "string",
                    "description": "Language for the call (e.g. 'en', 'ml', 'ar').",
                    "default": "en",
                },
            },
            "required": ["phone_number", "task"],
        },
    },
    {
        "name": "send_email",
        "description": "Send an email to a client, lead, or staff member using Resend.",
        "input_schema": {
            "type": "object",
            "properties": {
                "to": {
                    "type": "string",
                    "description": "Recipient email address (e.g. client@example.com).",
                },
                "subject": {
                    "type": "string",
                    "description": "Subject line of the email.",
                },
                "body": {
                    "type": "string",
                    "description": "Plain text content of the email.",
                },
                "html": {
                    "type": "string",
                    "description": "Optional HTML formatted content for the email.",
                },
            },
            "required": ["to", "subject", "body"],
        },
    },
]

WRITE_TOOLS = {"create_lead", "make_phone_call", "send_email"}


def is_affirmative(text: str) -> bool:
    cleaned = text.strip().lower()
    return cleaned in {
        "yes",
        "y",
        "yes please",
        "confirm",
        "proceed",
        "sure",
        "approved",
        "ok",
        "okay",
        "yes, proceed",
        "yes proceed",
    } or cleaned.startswith("yes")


def is_negative(text: str) -> bool:
    cleaned = text.strip().lower()
    return cleaned in {"no", "n", "cancel", "stop", "abort", "don't", "dont", "no don't"} or cleaned.startswith("no")


def dispatch_tool(
    name: str,
    tool_input: dict[str, Any],
    api_client: OctapusApiClient,
    session: dict[str, Any],
    is_confirmed: bool = False,
) -> dict[str, Any]:
    """Execute tool or stage it if it's an unconfirmed write operation."""
    if name == "get_client":
        client_id = str(tool_input.get("client_id", "")).strip()
        return api_client.get_client(client_id)

    if name == "get_projects":
        status = str(tool_input.get("status", "open")).strip()
        return api_client.get_projects(status=status)

    if name == "create_lead":
        if not is_confirmed:
            # Stage write operation and require user confirmation
            session["pending_action"] = {
                "tool_name": "create_lead",
                "tool_input": tool_input,
            }
            return {
                "status": "pending_confirmation",
                "requires_confirmation": True,
                "message": (
                    "Write operation staged. Do NOT execute yet. "
                    "You MUST state the exact payload to the user and ask for confirmation with an explicit 'yes'."
                ),
                "payload": tool_input,
            }
        else:
            session["pending_action"] = None
            return api_client.create_lead(tool_input)

    if name == "make_phone_call":
        if not is_confirmed:
            session["pending_action"] = {
                "tool_name": "make_phone_call",
                "tool_input": tool_input,
            }
            return {
                "status": "pending_confirmation",
                "requires_confirmation": True,
                "message": (
                    "Phone call staged. Do NOT execute yet. "
                    "You MUST state the target phone number and call objective to the user and ask for confirmation with an explicit 'yes'."
                ),
                "payload": tool_input,
            }
        else:
            session["pending_action"] = None
            import os
            import httpx

            bland_key = os.environ.get("BLAND_API_KEY", "")
            if not bland_key:
                return {"error": "Bland.ai API key is not configured"}
            bland_url = os.environ.get("BLAND_API_URL", "https://api.bland.ai/v1").rstrip("/")
            phone = str(tool_input.get("phone_number", "")).strip()
            if not phone.startswith("+"):
                phone = "+" + phone
            task = str(tool_input.get("task", "")).strip()
            first_sent = tool_input.get("first_sentence")
            lang = tool_input.get("language", "en")
            payload = {
                "phone_number": phone,
                "task": task,
                "language": lang,
                "wait_for_greeting": True,
                "record": True,
            }
            if first_sent:
                payload["first_sentence"] = first_sent
            try:
                with httpx.Client(timeout=15.0) as client:
                    resp = client.post(
                        f"{bland_url}/calls",
                        json=payload,
                        headers={"authorization": bland_key, "Content-Type": "application/json"},
                    )
                    if resp.status_code in (200, 201):
                        data = resp.json()
                        return {"status": "success", "call_id": data.get("call_id"), "message": "Call initiated successfully"}
                    return {"status": "error", "code": resp.status_code, "message": resp.text[:200]}
            except Exception as exc:
                return {"status": "error", "message": str(exc)}

    if name == "send_email":
        if not is_confirmed:
            session["pending_action"] = {
                "tool_name": "send_email",
                "tool_input": tool_input,
            }
            return {
                "status": "pending_confirmation",
                "requires_confirmation": True,
                "message": (
                    "Email staged. Do NOT send yet. "
                    "You MUST show the recipient, subject, and message preview to the user and ask for confirmation with an explicit 'yes'."
                ),
                "payload": tool_input,
            }
        else:
            session["pending_action"] = None
            import os
            import httpx

            resend_key = os.environ.get("RESEND_API_KEY", "")
            if not resend_key:
                return {"error": "Resend API key is not configured"}
            from_email = os.environ.get("RESEND_FROM", "Octapus AI <onboarding@resend.dev>")
            to_email = str(tool_input.get("to", "")).strip()
            subject = str(tool_input.get("subject", "")).strip()
            body_text = str(tool_input.get("body", "")).strip()
            html_text = tool_input.get("html")
            payload = {
                "from": from_email,
                "to": [to_email],
                "subject": subject,
                "text": body_text,
            }
            if html_text:
                payload["html"] = html_text
            try:
                with httpx.Client(timeout=15.0) as client:
                    resp = client.post(
                        "https://api.resend.com/emails",
                        json=payload,
                        headers={"Authorization": f"Bearer {resend_key}", "Content-Type": "application/json"},
                    )
                    if resp.status_code in (200, 201):
                        data = resp.json()
                        return {"status": "success", "id": data.get("id"), "message": f"Email successfully sent to {to_email}"}
                    return {"status": "error", "code": resp.status_code, "message": resp.text[:200]}
            except Exception as exc:
                return {"status": "error", "message": str(exc)}

    return {"error": f"Unknown tool: {name}"}


