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
]

WRITE_TOOLS = {"create_lead"}


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

    return {"error": f"Unknown tool: {name}"}
