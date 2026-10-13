from __future__ import annotations

import hmac
import json
import os
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from api_client import OctapusApiClient
from chat_engine import (
    build_conversation_context,
    build_system_prompt,
    update_rolling_summary_if_needed,
)
import crypto
from db import (
    DEFAULT_SETTINGS,
    add_memory_fact,
    add_message,
    clear_all_data,
    create_conversation,
    delete_conversation,
    delete_memory_fact,
    delete_provider_key,
    get_active_provider_key,
    get_all_settings,
    get_conversation,
    get_conversation_messages,
    get_provider_key,
    get_setting,
    get_usage_summary,
    init_db,
    list_conversations,
    list_memory_facts,
    list_provider_keys,
    save_provider_key,
    set_setting,
    update_conversation,
    update_memory_fact,
    update_provider_key_status,
)
from providers import get_adapter, list_supported_providers
from providers.base import ModelInfo, ProviderResponse, ToolCall
from providers.custom_adapter import validate_base_url
from tools import TOOLS, dispatch_tool, is_affirmative, is_negative
from usage_tracker import check_budget_status, track_and_record_usage
from prompt_builder import build_dynamic_prompt
from messaging import sendMessage, normalize_phone_number
from skills.registry import get_skill, list_skills
from db import (
    list_training_instructions,
    get_training_instruction,
    create_training_instruction,
    update_training_instruction,
    delete_training_instruction,
    add_training_knowledge,
    list_training_knowledge,
    get_training_knowledge,
    delete_training_knowledge,
    delete_training_knowledge_by_source,
    list_training_skills,
    get_training_skill,
    update_training_skill,
    list_training_logs,
    restore_training_log,
    add_training_correction,
    list_training_corrections,
)

BASE_DIR = Path(__file__).resolve().parent

# Load .env if present
for env_path in (BASE_DIR / ".env", BASE_DIR.parent / ".env"):
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ[k.strip()] = v.strip().strip("'\"")

# Initialize database
init_db()

api_client = OctapusApiClient()

app = FastAPI(title="Octapus Staff Assistant", version="2.0.0")
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")

# Rate limiter data: ip -> list of timestamps
_rate_limits: Dict[str, List[float]] = {}


def check_rate_limit(key: str, max_requests: int = 60, window_seconds: float = 60.0):
    """Enforce token bucket / sliding window rate limiting."""
    now = time.time()
    timestamps = _rate_limits.setdefault(key, [])
    # Remove timestamps outside window
    _rate_limits[key] = [t for t in timestamps if now - t < window_seconds]
    if len(_rate_limits[key]) >= max_requests:
        raise HTTPException(status_code=429, detail="Too many requests. Please slow down.")
    _rate_limits[key].append(now)


def get_staff_password() -> str:
    """Retrieve expected staff password from environment."""
    return os.environ.get("STAFF_PASSWORD", "").strip().strip("'\"")


def check_password(provided: Optional[str]) -> None:
    """Validate staff authentication header against DB bcrypt hash or environment password."""
    if not provided:
        raise HTTPException(status_code=401, detail="Authentication required.")

    cleaned = provided.strip().strip("'\"")

    # Check if a hashed password was saved in DB account settings
    acc_settings = get_setting("account", {}) or {}
    saved_hash = acc_settings.get("staff_password_hash") or os.environ.get("STAFF_PASSWORD_HASH")

    if saved_hash:
        if crypto.verify_password(cleaned, saved_hash):
            return
        raise HTTPException(status_code=401, detail="Invalid staff password.")

    # Fallback to plain STAFF_PASSWORD env
    expected = get_staff_password()
    if not expected:
        raise HTTPException(status_code=500, detail="STAFF_PASSWORD is not configured on server.")

    if not hmac.compare_digest(cleaned, expected):
        raise HTTPException(status_code=401, detail="Invalid staff password.")


# In-memory pending actions store for multi-turn write confirmation: conversation_id -> dict
pending_actions: Dict[str, Dict[str, Any]] = {}


# ============================================================================
# Core & Auth Endpoints
# ============================================================================

@app.get("/")
def index():
    return FileResponse(BASE_DIR / "static" / "index.html")


@app.post("/verify-auth")
def verify_auth(x_staff_password: Optional[str] = Header(default=None)):
    check_password(x_staff_password)
    return {"status": "ok", "master_key_configured": crypto.is_master_key_configured()}


# ============================================================================
# Settings Endpoints
# ============================================================================

@app.get("/settings")
def get_settings_endpoint(x_staff_password: Optional[str] = Header(default=None)):
    check_password(x_staff_password)
    settings = get_all_settings()
    # Mask master key status
    settings["security"] = {
        "master_key_configured": crypto.is_master_key_configured(),
    }
    return settings


@app.post("/settings")
@app.patch("/settings")
def update_settings_endpoint(
    body: Dict[str, Any], x_staff_password: Optional[str] = Header(default=None)
):
    check_password(x_staff_password)
    for section, values in body.items():
        if section == "security":
            continue
        current = get_setting(section, {}) or {}
        if isinstance(current, dict) and isinstance(values, dict):
            current.update(values)
            set_setting(section, current)
        else:
            set_setting(section, values)
    return {"status": "ok", "settings": get_all_settings()}


# ============================================================================
# Provider & Key Management Endpoints
# ============================================================================

class ProviderKeyIn(BaseModel):
    provider: str
    label: str
    api_key: Optional[str] = ""
    base_url: Optional[str] = None
    is_default: Optional[bool] = False


@app.get("/providers")
def list_providers_endpoint(x_staff_password: Optional[str] = Header(default=None)):
    check_password(x_staff_password)
    keys = list_provider_keys()
    result = []
    for k in keys:
        # Decrypt server-side strictly to generate safe mask
        masked = "••••••••"
        if k["encrypted_key"]:
            try:
                decrypted = crypto.decrypt_api_key(k["encrypted_key"])
                masked = crypto.mask_api_key(decrypted)
            except Exception:
                masked = "••••••••(error)"

        result.append({
            "id": k["id"],
            "provider": k["provider"],
            "label": k["label"],
            "masked_key": masked,
            "base_url": k["base_url"],
            "status": k["status"],
            "status_message": k["status_message"],
            "is_default": bool(k["is_default"]),
            "created_at": k["created_at"],
            "updated_at": k["updated_at"],
        })
    return {"providers": result, "supported_providers": list_supported_providers()}


@app.post("/providers")
def add_provider_key_endpoint(
    body: ProviderKeyIn,
    request: Request,
    x_staff_password: Optional[str] = Header(default=None),
):
    check_password(x_staff_password)
    check_rate_limit(f"provider_add:{request.client.host if request.client else 'local'}", max_requests=20)

    if not crypto.is_master_key_configured():
        raise HTTPException(
            status_code=400,
            detail="Cannot save API key: MASTER_KEY environment variable is not configured. Encryption at rest is required.",
        )

    provider_name = body.provider.lower().strip()
    if provider_name not in list_supported_providers():
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported provider '{body.provider}'. Supported: {', '.join(list_supported_providers())}",
        )

    # Validate custom URL security
    if provider_name in ("custom", "openrouter", "ollama") and body.base_url:
        if not validate_base_url(body.base_url):
            raise HTTPException(
                status_code=400,
                detail="Security rule: Provider Base URL must use HTTPS (or localhost for local testing).",
            )

    raw_key = body.api_key.strip() if body.api_key else ""
    if provider_name != "ollama" and not raw_key:
        raise HTTPException(status_code=400, detail="API key is required for this provider.")

    encrypted_key = crypto.encrypt_api_key(raw_key) if raw_key else ""

    # Test key connection immediately
    adapter = get_adapter(provider_name)
    test_result = adapter.test_connection(api_key=raw_key, base_url=body.base_url)

    status = "connected" if test_result["ok"] else "invalid_key"
    if "rate limit" in (test_result.get("error") or "").lower():
        status = "rate_limited"

    key_id = save_provider_key(
        provider=provider_name,
        label=body.label.strip() or f"{provider_name.capitalize()} Key",
        encrypted_key=encrypted_key,
        base_url=body.base_url,
        is_default=bool(body.is_default),
        status=status,
        status_message=test_result.get("error") or "",
    )

    return {
        "status": "ok",
        "id": key_id,
        "test_result": test_result,
        "masked_key": crypto.mask_api_key(raw_key) if raw_key else "••••••••",
    }


@app.patch("/providers/{key_id}")
def update_provider_key_endpoint(
    key_id: str,
    body: Dict[str, Any],
    x_staff_password: Optional[str] = Header(default=None),
):
    check_password(x_staff_password)
    existing = get_provider_key(key_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Provider key not found.")

    encrypted_key = existing["encrypted_key"]
    raw_key = None
    if "api_key" in body and body["api_key"]:
        if not crypto.is_master_key_configured():
            raise HTTPException(status_code=400, detail="MASTER_KEY is required to save keys.")
        raw_key = body["api_key"].strip()
        encrypted_key = crypto.encrypt_api_key(raw_key)

    label = body.get("label", existing["label"])
    base_url = body.get("base_url", existing["base_url"])
    is_default = body.get("is_default", bool(existing["is_default"]))

    save_provider_key(
        provider=existing["provider"],
        label=label,
        encrypted_key=encrypted_key,
        base_url=base_url,
        is_default=is_default,
        status=existing["status"],
        status_message=existing["status_message"],
        key_id=key_id,
    )
    return {"status": "ok"}


@app.delete("/providers/{key_id}")
def delete_provider_key_endpoint(
    key_id: str, x_staff_password: Optional[str] = Header(default=None)
):
    check_password(x_staff_password)
    deleted = delete_provider_key(key_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Provider key not found.")
    return {"status": "ok", "deleted": True}


@app.post("/providers/{key_id}/test")
def test_provider_saved_key(
    key_id: str,
    request: Request,
    x_staff_password: Optional[str] = Header(default=None),
):
    check_password(x_staff_password)
    check_rate_limit(f"provider_test:{request.client.host if request.client else 'local'}", max_requests=20)

    key_record = get_provider_key(key_id)
    if not key_record:
        raise HTTPException(status_code=404, detail="Provider key not found.")

    raw_key = ""
    if key_record["encrypted_key"]:
        try:
            raw_key = crypto.decrypt_api_key(key_record["encrypted_key"])
        except Exception as e:
            update_provider_key_status(key_id, "invalid_key", f"Decryption error: {str(e)}")
            return {"ok": False, "model_count": 0, "error": f"Failed to decrypt key: {str(e)}"}

    adapter = get_adapter(key_record["provider"])
    result = adapter.test_connection(api_key=raw_key, base_url=key_record["base_url"])

    new_status = "connected" if result["ok"] else "invalid_key"
    if "rate limit" in (result.get("error") or "").lower():
        new_status = "rate_limited"

    update_provider_key_status(key_id, new_status, result.get("error") or "")
    return result


@app.post("/providers/test")
def test_unsaved_provider(
    body: ProviderKeyIn,
    request: Request,
    x_staff_password: Optional[str] = Header(default=None),
):
    check_password(x_staff_password)
    check_rate_limit(f"provider_test_unsaved:{request.client.host if request.client else 'local'}", max_requests=20)

    provider_name = body.provider.lower().strip()
    if provider_name not in list_supported_providers():
        raise HTTPException(status_code=400, detail=f"Unsupported provider: {body.provider}")

    adapter = get_adapter(provider_name)
    return adapter.test_connection(api_key=body.api_key, base_url=body.base_url)


# ============================================================================
# Models Catalog Endpoint
# ============================================================================

@app.get("/models")
def get_aggregated_models(x_staff_password: Optional[str] = Header(default=None)):
    check_password(x_staff_password)
    connected_keys = list_provider_keys()
    models_by_provider: Dict[str, List[Dict[str, Any]]] = {}

    # Gather connected provider keys
    active_providers = set()
    for k in connected_keys:
        if k["status"] == "connected":
            active_providers.add(k["provider"])

    # Always include Anthropic fallback if default env key exists
    if os.environ.get("ANTHROPIC_API_KEY"):
        active_providers.add("anthropic")

    all_models: List[Dict[str, Any]] = []

    for prov in list_supported_providers():
        adapter = get_adapter(prov)
        key_record = get_active_provider_key(prov)
        raw_key = None
        base_url = None
        if key_record:
            base_url = key_record["base_url"]
            if key_record["encrypted_key"]:
                try:
                    raw_key = crypto.decrypt_api_key(key_record["encrypted_key"])
                except Exception:
                    pass

        try:
            m_list = adapter.list_models(api_key=raw_key, base_url=base_url)
            for m in m_list:
                all_models.append({
                    "id": m.id,
                    "name": m.name,
                    "provider": m.provider,
                    "context_window": m.context_window,
                    "supports_tools": m.supports_tools,
                    "supports_vision": m.supports_vision,
                    "supports_streaming": m.supports_streaming,
                    "description": m.description,
                    "is_connected": prov in active_providers,
                })
        except Exception:
            pass

    return {
        "models": all_models,
        "default_model": get_setting("models", {}).get("default_model") or "claude-sonnet-5-5",
        "default_provider": get_setting("models", {}).get("default_provider", "anthropic"),
    }


# ============================================================================
# Assistant Customization & Preview Endpoints
# ============================================================================

@app.get("/assistant")
def get_assistant_settings(x_staff_password: Optional[str] = Header(default=None)):
    check_password(x_staff_password)
    return get_setting("assistant", DEFAULT_SETTINGS["assistant"])


@app.patch("/assistant")
def update_assistant_settings(
    body: Dict[str, Any], x_staff_password: Optional[str] = Header(default=None)
):
    check_password(x_staff_password)
    curr = get_setting("assistant", DEFAULT_SETTINGS["assistant"]) or {}
    curr.update(body)
    set_setting("assistant", curr)
    return {"status": "ok", "assistant": curr}


@app.get("/assistant/preview")
def preview_system_prompt(x_staff_password: Optional[str] = Header(default=None)):
    check_password(x_staff_password)
    prompt = build_system_prompt()
    return {"system_prompt": prompt}


# ============================================================================
# Memory Facts Endpoints
# ============================================================================

class FactIn(BaseModel):
    fact: str
    source: Optional[str] = ""
    confidence: Optional[float] = 1.0
    is_approved: Optional[bool] = False
    is_pinned: Optional[bool] = False
    conversation_id: Optional[str] = None


@app.get("/memory/facts")
def get_memory_facts_endpoint(
    conversation_id: Optional[str] = Query(default=None),
    x_staff_password: Optional[str] = Header(default=None),
):
    check_password(x_staff_password)
    facts = list_memory_facts(conversation_id=conversation_id, approved_only=False)
    return {"facts": facts}


@app.post("/memory/facts")
def add_memory_fact_endpoint(
    body: FactIn, x_staff_password: Optional[str] = Header(default=None)
):
    check_password(x_staff_password)
    if not body.fact.strip():
        raise HTTPException(status_code=400, detail="Fact text is required.")
    fid = add_memory_fact(
        fact=body.fact.strip(),
        source=body.source or "",
        confidence=body.confidence or 1.0,
        is_approved=bool(body.is_approved),
        is_pinned=bool(body.is_pinned),
        conversation_id=body.conversation_id,
    )
    return {"status": "ok", "id": fid}


@app.post("/memory/facts/{fact_id}/approve")
def approve_memory_fact_endpoint(
    fact_id: str, x_staff_password: Optional[str] = Header(default=None)
):
    check_password(x_staff_password)
    updated = update_memory_fact(fact_id, is_approved=True)
    if not updated:
        raise HTTPException(status_code=404, detail="Fact not found.")
    return {"status": "ok", "approved": True}


@app.patch("/memory/facts/{fact_id}")
def update_memory_fact_endpoint(
    fact_id: str, body: Dict[str, Any], x_staff_password: Optional[str] = Header(default=None)
):
    check_password(x_staff_password)
    updated = update_memory_fact(
        fact_id=fact_id,
        fact=body.get("fact"),
        is_approved=body.get("is_approved"),
        is_pinned=body.get("is_pinned"),
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Fact not found.")
    return {"status": "ok"}


@app.delete("/memory/facts/{fact_id}")
def delete_memory_fact_endpoint(
    fact_id: str, x_staff_password: Optional[str] = Header(default=None)
):
    check_password(x_staff_password)
    deleted = delete_memory_fact(fact_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Fact not found.")
    return {"status": "ok", "deleted": True}


# ============================================================================
# Conversations Endpoints
# ============================================================================

class ConvIn(BaseModel):
    title: Optional[str] = "New Chat"
    provider: Optional[str] = None
    model: Optional[str] = None


@app.get("/conversations")
def list_conversations_endpoint(
    include_archived: bool = Query(default=False),
    x_staff_password: Optional[str] = Header(default=None),
):
    check_password(x_staff_password)
    convs = list_conversations(include_archived=include_archived)
    return {"conversations": convs}


@app.post("/conversations")
def create_conversation_endpoint(
    body: ConvIn, x_staff_password: Optional[str] = Header(default=None)
):
    check_password(x_staff_password)
    cid = create_conversation(
        title=body.title or "New Chat",
        provider=body.provider,
        model=body.model,
    )
    return {"status": "ok", "id": cid}


@app.get("/conversations/{conv_id}")
def get_conversation_endpoint(
    conv_id: str, x_staff_password: Optional[str] = Header(default=None)
):
    check_password(x_staff_password)
    conv = get_conversation(conv_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    messages = get_conversation_messages(conv_id)
    facts = list_memory_facts(conversation_id=conv_id)
    return {
        "conversation": conv,
        "messages": messages,
        "facts": facts,
    }


@app.patch("/conversations/{conv_id}")
def update_conversation_endpoint(
    conv_id: str, body: Dict[str, Any], x_staff_password: Optional[str] = Header(default=None)
):
    check_password(x_staff_password)
    updated = update_conversation(
        conv_id=conv_id,
        title=body.get("title"),
        provider=body.get("provider"),
        model=body.get("model"),
        summary=body.get("summary"),
        archived=body.get("archived"),
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    return {"status": "ok"}


@app.delete("/conversations/{conv_id}")
def delete_conversation_endpoint(
    conv_id: str, x_staff_password: Optional[str] = Header(default=None)
):
    check_password(x_staff_password)
    deleted = delete_conversation(conv_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    return {"status": "ok", "deleted": True}


@app.get("/conversations/{conv_id}/export")
def export_conversation_endpoint(
    conv_id: str,
    format: str = Query(default="markdown"),
    x_staff_password: Optional[str] = Header(default=None),
):
    check_password(x_staff_password)
    conv = get_conversation(conv_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    messages = get_conversation_messages(conv_id)

    if format.lower() == "json":
        return JSONResponse(content={"conversation": conv, "messages": messages})

    # Markdown export
    lines = [
        f"# {conv['title']}",
        f"**Date:** {conv['created_at']} | **Model:** {conv.get('model') or 'default'}",
        "",
    ]
    if conv.get("summary"):
        lines.extend([f"> **Summary:** {conv['summary']}", ""])

    for m in messages:
        sender = "**Staff**" if m["role"] == "user" else "**Octapus Assistant**"
        lines.extend([f"### {sender} ({m['created_at']})", "", m["content"], ""])

    return PlainTextResponse(content="\n".join(lines), media_type="text/markdown")


# ============================================================================
# Usage & Budget Endpoints
# ============================================================================

@app.get("/usage")
def get_usage_endpoint(x_staff_password: Optional[str] = Header(default=None)):
    check_password(x_staff_password)
    summary = get_usage_summary()
    budget_allowed, budget_msg, current_cost, budget_limit = check_budget_status()
    summary["budget"] = {
        "monthly_budget": budget_limit,
        "current_cost": current_cost,
        "status_message": budget_msg,
        "is_exceeded": not budget_allowed,
        "user_overridden": bool(get_setting("budget", {}).get("user_overridden", False)),
    }
    return summary


# ============================================================================
# Privacy, Export & Clear Endpoints
# ============================================================================

@app.post("/data/export")
def export_all_data_endpoint(x_staff_password: Optional[str] = Header(default=None)):
    check_password(x_staff_password)
    convs = list_conversations(include_archived=True)
    all_data = {
        "settings": get_all_settings(),
        "conversations": [],
        "memory_facts": list_memory_facts(),
        "exported_at": crypto.get_master_key(),
    }
    for c in convs:
        msgs = get_conversation_messages(c["id"])
        all_data["conversations"].append({"conversation": c, "messages": msgs})

    return JSONResponse(content=all_data)


class ClearDataIn(BaseModel):
    confirmation: str


@app.post("/data/clear")
def clear_all_data_endpoint(
    body: ClearDataIn, x_staff_password: Optional[str] = Header(default=None)
):
    check_password(x_staff_password)
    if body.confirmation.strip() != "DELETE ALL DATA":
        raise HTTPException(
            status_code=400,
            detail="Typed confirmation mismatch. You must send 'DELETE ALL DATA' exactly.",
        )
    clear_all_data()
    return {"status": "ok", "message": "All conversations, messages, facts, and usage cleared."}


# ============================================================================
# Account & Password Management Endpoint
# ============================================================================

class PasswordChangeIn(BaseModel):
    old_password: str
    new_password: str


@app.post("/account/password")
def change_password_endpoint(
    body: PasswordChangeIn, x_staff_password: Optional[str] = Header(default=None)
):
    check_password(x_staff_password)
    if not body.new_password or len(body.new_password.strip()) < 8:
        raise HTTPException(status_code=400, detail="New password must be at least 8 characters long.")

    # Validate old password
    check_password(body.old_password)

    new_hash = crypto.hash_password(body.new_password.strip())
    acc = get_setting("account", {}) or {}
    acc["staff_password_hash"] = new_hash
    set_setting("account", acc)
    return {"status": "ok", "message": "Staff password successfully updated."}


# ============================================================================
# Chat Endpoint (Multi-Provider, Memory Context, Tool Dispatch, Streaming)
# ============================================================================

class ChatIn(BaseModel):
    message: str
    session_id: Optional[str] = None
    conversation_id: Optional[str] = None
    model: Optional[str] = None
    provider: Optional[str] = None
    stream: Optional[bool] = False


class ChatOut(BaseModel):
    reply: str
    session_id: str
    conversation_id: str
    model: str
    provider: str
    usage: Optional[Dict[str, int]] = None
    cost: Optional[float] = None
    budget_warning: Optional[str] = None


@app.post("/chat")
def chat_endpoint(
    body: ChatIn,
    request: Request,
    x_staff_password: Optional[str] = Header(default=None),
):
    check_password(x_staff_password)
    check_rate_limit(f"chat:{request.client.host if request.client else 'local'}", max_requests=60)

    # 1. Budget enforcement check
    budget_ok, budget_warning, cur_cost, budget_max = check_budget_status()
    if not budget_ok:
        raise HTTPException(
            status_code=403,
            detail=budget_warning or "Monthly budget limit reached (100%). Requests blocked.",
        )

    message = body.message.strip()
    if not message or len(message) > 4000:
        raise HTTPException(status_code=400, detail="Message must be 1-4000 characters.")

    # 2. Resolve Conversation / Session ID
    conv_id = body.conversation_id or body.session_id or str(uuid.uuid4())
    conv = get_conversation(conv_id)
    if not conv:
        create_conversation(conv_id=conv_id, title=message[:40] or "New Chat")
        conv = get_conversation(conv_id)

    # 3. Resolve Provider and Model
    model_settings = get_setting("models", {}) or {}
    provider_name = body.provider or (conv.get("provider") if conv else None) or model_settings.get("default_provider", "anthropic")
    model_name = body.model or (conv.get("model") if conv else None) or (model_settings.get("default_model") or "").strip() or "claude-sonnet-5-5"

    # Update conversation model metadata if changed
    update_conversation(conv_id, provider=provider_name, model=model_name)

    # 4. Check for multi-turn write confirmation
    pending = pending_actions.get(conv_id)
    immediate_reply: Optional[str] = None

    if pending:
        if is_affirmative(message):
            tool_name = pending["tool_name"]
            tool_input = pending["tool_input"]
            api_result = dispatch_tool(
                name=tool_name,
                tool_input=tool_input,
                api_client=api_client,
                session=pending.get("session", {}),
                is_confirmed=True,
            )
            pending_actions.pop(conv_id, None)

            if "error" in api_result:
                immediate_reply = (
                    f"I attempted to submit the lead for '{tool_input.get('name')}', "
                    f"but the API returned an error: {api_result['error']}"
                )
            else:
                immediate_reply = (
                    f"Lead for '{tool_input.get('name')}' was successfully created in the API! "
                    f"Response: {json.dumps(api_result)}"
                )
        elif is_negative(message):
            pending_actions.pop(conv_id, None)
            immediate_reply = "Understood. The pending lead creation has been cancelled."
        else:
            pending_actions.pop(conv_id, None)

    # Record user message in DB
    add_message(conv_id, role="user", content=message, provider=provider_name, model=model_name)

    if immediate_reply:
        add_message(conv_id, role="assistant", content=immediate_reply, provider=provider_name, model=model_name)
        if body.stream:
            def sse_immediate():
                yield f"data: {json.dumps({'delta': immediate_reply, 'conversation_id': conv_id, 'session_id': conv_id})}\n\n"
                yield f"data: {json.dumps({'done': True, 'reply': immediate_reply, 'conversation_id': conv_id, 'session_id': conv_id})}\n\n"
            return StreamingResponse(sse_immediate(), media_type="text/event-stream")
        return ChatOut(
            reply=immediate_reply,
            session_id=conv_id,
            conversation_id=conv_id,
            model=model_name,
            provider=provider_name,
        )

    # 5. Build structured context from Chat Engine (System Prompt + Memory Facts + Rolling Summary + Recent N Messages)
    sys_prompt, messages_for_model, facts_used = build_conversation_context(conv_id)

    # 6. Retrieve provider key and adapter
    adapter = get_adapter(provider_name)
    key_record = get_active_provider_key(provider_name)
    raw_key = None
    base_url = None

    if key_record:
        base_url = key_record["base_url"]
        if key_record["encrypted_key"]:
            try:
                raw_key = crypto.decrypt_api_key(key_record["encrypted_key"])
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Failed to decrypt provider key: {str(e)}")
    elif provider_name == "anthropic" and os.environ.get("ANTHROPIC_API_KEY"):
        raw_key = os.environ.get("ANTHROPIC_API_KEY")
        base_url = os.environ.get("ANTHROPIC_BASE_URL")

    # Check if tools are supported
    supports_tools = adapter.supports_tools
    active_tools = TOOLS if supports_tools else None
    tools_disabled_notice = ""
    if not supports_tools:
        tools_disabled_notice = "\n\n*(Note: Automated write and lookup actions are disabled for this model.)*"

    # 7. Execute Model Call with Tool Loop
    params = {
        "temperature": model_settings.get("temperature", 0.7),
        "max_output_tokens": model_settings.get("max_output_tokens", 1200),
        "top_p": model_settings.get("top_p", 1.0),
    }

    session_state = {"history": [], "pending_action": None}
    iterations = 0
    full_reply = ""
    total_input_tokens = 0
    total_output_tokens = 0

    while iterations < 5:
        iterations += 1
        resp: ProviderResponse = adapter.chat(
            messages=messages_for_model,
            system=sys_prompt,
            tools=active_tools,
            model=model_name,
            params=params,
            api_key=raw_key,
            base_url=base_url,
        )

        if resp.error:
            raise HTTPException(status_code=502, detail=resp.error)

        total_input_tokens += resp.usage.get("input_tokens", 0)
        total_output_tokens += resp.usage.get("output_tokens", 0)

        # Handle tool calls
        if resp.tool_calls:
            # Check for write operation staging
            tool_call = resp.tool_calls[0]
            if tool_call.name == "create_lead":
                pending_actions[conv_id] = {
                    "tool_name": tool_call.name,
                    "tool_input": tool_call.input,
                    "session": session_state,
                }
                lead_name = tool_call.input.get("name", "Unknown")
                full_reply = (
                    f"I have prepared the lead for **{lead_name}** with parameters:\n"
                    f"- Contact: {tool_call.input.get('contact', 'N/A')}\n"
                    f"- Service: {tool_call.input.get('service', 'N/A')}\n"
                    f"- Notes: {tool_call.input.get('notes', 'N/A')}\n\n"
                    "Would you like me to submit this to our API? Please reply **yes** to confirm or **no** to cancel."
                )
                break
            else:
                # Read-only tool dispatch
                tool_output = dispatch_tool(
                    name=tool_call.name,
                    tool_input=tool_call.input,
                    api_client=api_client,
                    session=session_state,
                    is_confirmed=False,
                )
                messages_for_model.append({"role": "assistant", "content": resp.text or f"Called {tool_call.name}"})
                messages_for_model.append({"role": "user", "content": f"Tool output: {json.dumps(tool_output)}"})
                continue
        else:
            full_reply = resp.text
            break

    if not full_reply:
        full_reply = "I have processed your request."

    if tools_disabled_notice:
        full_reply += tools_disabled_notice

    # 8. Record Usage & Cost
    cost = track_and_record_usage(
        provider=provider_name,
        model=model_name,
        input_tokens=total_input_tokens,
        output_tokens=total_output_tokens,
        conversation_id=conv_id,
    )

    # 9. Save assistant response into database
    add_message(
        conv_id,
        role="assistant",
        content=full_reply,
        provider=provider_name,
        model=model_name,
        input_tokens=total_input_tokens,
        output_tokens=total_output_tokens,
        cost=cost,
    )

    # Trigger rolling summary regeneration in background if threshold passed
    try:
        update_rolling_summary_if_needed(conv_id, adapter, api_key=raw_key, base_url=base_url, model=model_name)
    except Exception:
        pass

    # 10. Streaming Mode
    if body.stream:
        def sse_stream():
            # Send reply in streaming chunks
            words = full_reply.split(" ")
            for i, w in enumerate(words):
                chunk = w if i == len(words) - 1 else w + " "
                yield f"data: {json.dumps({'delta': chunk, 'conversation_id': conv_id, 'session_id': conv_id})}\n\n"
            yield f"data: {json.dumps({'done': True, 'reply': full_reply, 'conversation_id': conv_id, 'session_id': conv_id, 'model': model_name, 'provider': provider_name, 'cost': cost, 'budget_warning': budget_warning})}\n\n"

        return StreamingResponse(sse_stream(), media_type="text/event-stream")

    return ChatOut(
        reply=full_reply,
        session_id=conv_id,
        conversation_id=conv_id,
        model=model_name,
        provider=provider_name,
        usage={"input_tokens": total_input_tokens, "output_tokens": total_output_tokens},
        cost=cost,
        budget_warning=budget_warning,
    )


# ============================================================================
# Agent Training Center Endpoints (Admin Only)
# ============================================================================

import base64
import io
import re
import xml.etree.ElementTree as ET
import zipfile


def extract_text_from_file_content(filename: str, content_bytes: bytes) -> str:
    """Extract readable text from PDF, DOCX, or TXT without third-party binary dependencies."""
    lower = filename.lower()
    if lower.endswith(".txt") or lower.endswith(".md"):
        return content_bytes.decode("utf-8", errors="ignore")

    if lower.endswith(".docx"):
        try:
            with zipfile.ZipFile(io.BytesIO(content_bytes)) as z:
                xml_content = z.read("word/document.xml")
                root = ET.fromstring(xml_content)
                texts = []
                for node in root.iter():
                    if node.tag.endswith("}t") and node.text:
                        texts.append(node.text)
                return " ".join(texts).strip()
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Failed to parse DOCX file: {e}")

    if lower.endswith(".pdf"):
        try:
            raw = content_bytes.decode("latin-1", errors="ignore")
            streams = re.findall(r"stream[\r\n]+(.*?)[\r\n]+endstream", raw, re.DOTALL)
            extracted_words = []
            for stream in streams:
                matches = re.findall(r"\(([^\)]+)\)\s*(?:Tj|'|\")", stream)
                if matches:
                    extracted_words.extend(matches)
                array_matches = re.findall(r"\[(.*?)\]\s*TJ", stream)
                for arr in array_matches:
                    words = re.findall(r"\(([^\)]+)\)", arr)
                    extracted_words.extend(words)

            if extracted_words:
                return " ".join(extracted_words).strip()

            clean_strings = re.findall(r"[A-Za-z0-9\s\.,;:!?'\"-]{4,}", raw)
            text_result = " ".join(clean_strings).strip()
            if text_result:
                return text_result[:25000]
            return "PDF uploaded (text stream extracted)."
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Failed to extract text from PDF: {e}")

    return content_bytes.decode("utf-8", errors="ignore")


class InstructionIn(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    content: str = Field(..., min_length=1)
    priority: Optional[int] = 1
    active: Optional[int] = 1


class KnowledgeIn(BaseModel):
    title: str = Field(..., min_length=1, max_length=250)
    content: str = Field(..., min_length=1)
    tags: Optional[str] = ""
    source: Optional[str] = "pasted"


class KnowledgeUploadIn(BaseModel):
    filename: str
    content_base64: str
    title: Optional[str] = None
    tags: Optional[str] = ""


class SkillUpdateIn(BaseModel):
    enabled: int
    extra_instructions: Optional[str] = ""
    tone: Optional[str] = "Professional"
    language: Optional[str] = "auto"
    templates: Optional[str] = ""


class TestChatIn(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)
    conversation_id: Optional[str] = None
    provider: Optional[str] = None
    model: Optional[str] = None


class CorrectionIn(BaseModel):
    query: str = Field(..., min_length=1)
    bot_reply: str = Field(..., min_length=1)
    correction: str = Field(..., min_length=1)
    rating: Optional[str] = ""
    create_instruction: Optional[bool] = False


class SendMessageIn(BaseModel):
    number: str
    text: str


# --- 1. Instructions API ---

@app.get("/training/instructions")
def get_instructions_endpoint(
    active_only: bool = False,
    x_staff_password: Optional[str] = Header(default=None)
):
    check_password(x_staff_password)
    return {"instructions": list_training_instructions(active_only=active_only)}


@app.post("/training/instructions")
def create_instruction_endpoint(
    body: InstructionIn,
    x_staff_password: Optional[str] = Header(default=None)
):
    check_password(x_staff_password)
    created = create_training_instruction(
        title=body.title,
        content=body.content,
        priority=body.priority or 1,
        active=body.active if body.active is not None else 1,
        user="admin"
    )
    return {"status": "ok", "instruction": created}


@app.put("/training/instructions/{inst_id}")
def update_instruction_endpoint(
    inst_id: str,
    body: InstructionIn,
    x_staff_password: Optional[str] = Header(default=None)
):
    check_password(x_staff_password)
    updated = update_training_instruction(
        inst_id=inst_id,
        title=body.title,
        content=body.content,
        priority=body.priority or 1,
        active=body.active if body.active is not None else 1,
        user="admin"
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Instruction not found.")
    return {"status": "ok", "instruction": updated}


@app.delete("/training/instructions/{inst_id}")
def delete_instruction_endpoint(
    inst_id: str,
    x_staff_password: Optional[str] = Header(default=None)
):
    check_password(x_staff_password)
    success = delete_training_instruction(inst_id=inst_id, user="admin")
    if not success:
        raise HTTPException(status_code=404, detail="Instruction not found.")
    return {"status": "ok", "id": inst_id}


# --- 2. Knowledge / Studies API ---

@app.get("/training/knowledge")
def get_knowledge_endpoint(
    q: Optional[str] = None,
    limit: int = 100,
    x_staff_password: Optional[str] = Header(default=None)
):
    check_password(x_staff_password)
    return {"knowledge": list_training_knowledge(query=q, limit=limit)}


@app.post("/training/knowledge")
def add_knowledge_endpoint(
    body: KnowledgeIn,
    x_staff_password: Optional[str] = Header(default=None)
):
    check_password(x_staff_password)
    saved = add_training_knowledge(
        title=body.title,
        text=body.content,
        tags=body.tags or "",
        source=body.source or "pasted",
        user="admin"
    )
    return {"status": "ok", "chunks": saved, "count": len(saved)}


@app.post("/training/knowledge/upload")
def upload_knowledge_endpoint(
    body: KnowledgeUploadIn,
    x_staff_password: Optional[str] = Header(default=None)
):
    check_password(x_staff_password)
    try:
        content_bytes = base64.b64decode(body.content_base64)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid base64 payload: {e}")

    extracted_text = extract_text_from_file_content(body.filename, content_bytes)
    if not extracted_text.strip():
        raise HTTPException(status_code=400, detail="No readable text could be extracted from the file.")

    title = body.title or body.filename
    source = f"upload:{body.filename}"
    saved = add_training_knowledge(
        title=title,
        text=extracted_text,
        tags=body.tags or "uploaded",
        source=source,
        user="admin"
    )
    return {
        "status": "ok",
        "filename": body.filename,
        "title": title,
        "source": source,
        "chunks_created": len(saved),
        "chunks": saved
    }


@app.delete("/training/knowledge/{know_id}")
def delete_knowledge_endpoint(
    know_id: str,
    x_staff_password: Optional[str] = Header(default=None)
):
    check_password(x_staff_password)
    success = delete_training_knowledge(know_id=know_id, user="admin")
    if not success:
        raise HTTPException(status_code=404, detail="Knowledge chunk not found.")
    return {"status": "ok", "id": know_id}


@app.delete("/training/knowledge/source/{source:path}")
def delete_knowledge_source_endpoint(
    source: str,
    x_staff_password: Optional[str] = Header(default=None)
):
    check_password(x_staff_password)
    deleted_count = delete_training_knowledge_by_source(source=source, user="admin")
    return {"status": "ok", "source": source, "deleted_chunks": deleted_count}


# --- 3. Skills API ---

@app.get("/training/skills")
def get_skills_endpoint(x_staff_password: Optional[str] = Header(default=None)):
    check_password(x_staff_password)
    return {"skills": list_training_skills()}


@app.put("/training/skills/{skill_id}")
def update_skill_endpoint(
    skill_id: str,
    body: SkillUpdateIn,
    x_staff_password: Optional[str] = Header(default=None)
):
    check_password(x_staff_password)
    updated = update_training_skill(
        skill_id=skill_id,
        enabled=body.enabled,
        extra_instructions=body.extra_instructions or "",
        tone=body.tone or "Professional",
        language=body.language or "auto",
        templates=body.templates or "",
        user="admin"
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Skill not found.")
    return {"status": "ok", "skill": updated}


# --- 4. Test Chat Sandbox API ---

@app.post("/training/test-chat")
def test_chat_endpoint(
    body: TestChatIn,
    x_staff_password: Optional[str] = Header(default=None)
):
    """
    Sandbox chat for testing the agent prompt and behavior.
    Under each reply shows which instructions and knowledge chunks were used.
    """
    check_password(x_staff_password)
    message = body.message.strip()

    # 1. Run Reply Understanding skill if registered and enabled
    understanding_skill = get_skill("understanding")
    understanding_meta = {}
    if understanding_skill:
        sk_config = get_training_skill("understanding") or {}
        if sk_config.get("enabled", 1):
            understanding_meta = understanding_skill.execute({"text": message}, sk_config)

    # 2. Build dynamic prompt immediately from DB
    system_prompt, meta = build_dynamic_prompt(message)
    if understanding_meta:
        system_prompt += f"\n\n### Message Understanding Analysis\n{understanding_meta.get('summary', '')}"

    # 3. Resolve Provider & Model
    model_settings = get_setting("models", {}) or {}
    provider_name = body.provider or model_settings.get("default_provider", "anthropic")
    model_name = body.model or (model_settings.get("default_model") or "").strip() or "claude-sonnet-5-5"

    active_key = get_active_provider_key(provider_name)
    raw_key = crypto.decrypt_key(active_key["encrypted_key"]) if active_key else os.environ.get("ANTHROPIC_API_KEY", "")
    base_url = active_key.get("base_url") if active_key else os.environ.get("ANTHROPIC_BASE_URL")

    try:
        adapter = get_adapter(provider_name)
        messages_payload = [{"role": "user", "content": message}]
        response = adapter.complete(
            model=model_name,
            messages=messages_payload,
            system=system_prompt,
            api_key=raw_key,
            base_url=base_url
        )
        reply = response.content
    except Exception as e:
        reply = f"[Test Chat Simulation] Horus response: Thank you for your inquiry about Octapus services. (Provider note: {e})"

    return {
        "reply": reply,
        "used_instructions": meta.get("used_instructions", []),
        "used_knowledge_chunks": meta.get("used_knowledge_chunks", []),
        "enabled_skills": meta.get("enabled_skills", []),
        "understanding": understanding_meta,
        "model": model_name,
        "provider": provider_name,
    }


# --- 5. Corrections API ---

@app.post("/training/corrections")
def add_correction_endpoint(
    body: CorrectionIn,
    x_staff_password: Optional[str] = Header(default=None)
):
    """
    Save test chat correction.
    If create_instruction is True, automatically creates a new high-priority instruction.
    """
    check_password(x_staff_password)
    result = add_training_correction(
        query=body.query,
        bot_reply=body.bot_reply,
        correction=body.correction,
        rating=body.rating or "",
        create_instruction=bool(body.create_instruction),
        user="admin"
    )
    return {"status": "ok", "correction": result}


@app.get("/training/corrections")
def list_corrections_endpoint(
    limit: int = 50,
    x_staff_password: Optional[str] = Header(default=None)
):
    check_password(x_staff_password)
    return {"corrections": list_training_corrections(limit=limit)}


# --- 6. Training Logs & Restore API ---

@app.get("/training/logs")
def get_training_logs_endpoint(
    limit: int = 100,
    x_staff_password: Optional[str] = Header(default=None)
):
    check_password(x_staff_password)
    return {"logs": list_training_logs(limit=limit)}


@app.post("/training/logs/{log_id}/restore")
def restore_training_log_endpoint(
    log_id: str,
    x_staff_password: Optional[str] = Header(default=None)
):
    check_password(x_staff_password)
    try:
        result = restore_training_log(log_id=log_id, user="admin")
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# --- 7. Messaging API & Webhook Endpoints ---

@app.post("/api/whatsapp/send")
def send_message_endpoint(
    body: SendMessageIn,
    x_staff_password: Optional[str] = Header(default=None)
):
    """Test send an outgoing WhatsApp message using the canonical sendMessage function."""
    check_password(x_staff_password)
    try:
        result = sendMessage(body.number, body.text)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/webhook")
@app.post("/api/whatsapp/webhook")
async def whatsapp_incoming_webhook(request: Request):
    """
    Webhook endpoint for incoming WhatsApp messages and voice notes.
    Feeds incoming data through the Agent Training Center pipeline (audio transcription,
    reply understanding, dynamic prompt building) and dispatches replies using sendMessage.
    """
    try:
        body = await request.json()
    except Exception:
        body = {}

    if body.get("event") and body.get("event") != "Message":
        return {"status": "ignored", "reason": "non_message_event"}

    # Extract sender number
    raw_sender = (
        body.get("data", {}).get("Info", {}).get("Sender") or
        body.get("data", {}).get("Info", {}).get("Chat") or
        body.get("data", {}).get("info", {}).get("Sender") or
        body.get("from") or
        body.get("number") or
        body.get("sender") or
        body.get("phone") or
        body.get("data", {}).get("key", {}).get("remoteJid") or
        ""
    )

    from_me = bool(
        body.get("data", {}).get("Info", {}).get("IsFromMe") or
        body.get("data", {}).get("info", {}).get("isFromMe") or
        body.get("data", {}).get("key", {}).get("fromMe") or
        body.get("fromMe") or
        body.get("isFromMe")
    )

    if from_me:
        return {"status": "ignored", "reason": "from_me"}

    # Extract text content
    text = (
        body.get("data", {}).get("Message", {}).get("conversation") or
        body.get("data", {}).get("Message", {}).get("extendedTextMessage", {}).get("text") or
        body.get("data", {}).get("message", {}).get("conversation") or
        body.get("text") or
        body.get("message") if isinstance(body.get("message"), str) else None
    )

    # Extract audio/voice note metadata
    audio_data = (
        body.get("data", {}).get("Message", {}).get("audioMessage") or
        body.get("data", {}).get("message", {}).get("audioMessage") or
        body.get("audio")
    )

    if not raw_sender:
        return {"status": "ignored", "reason": "missing_sender"}

    try:
        clean_number = normalize_phone_number(str(raw_sender).split("@")[0].split(":")[0])
    except Exception as e:
        return {"status": "error", "error": f"Invalid sender number: {e}"}

    processed_text = str(text or "").strip()
    audio_ref = None

    # Step 1: Audio Transcription Skill if voice note
    if audio_data or (isinstance(text, str) and text.startswith("Voice message")):
        trans_skill = get_skill("transcription")
        if trans_skill:
            trans_res = trans_skill.execute(
                {
                    "audio_url": audio_data.get("url") if isinstance(audio_data, dict) else None,
                    "audio_id": audio_data.get("id") if isinstance(audio_data, dict) else None,
                    "text": processed_text,
                },
                {}
            )
            processed_text = trans_res.get("transcript") or processed_text
            audio_ref = trans_res.get("original_audio_reference")

    if not processed_text:
        return {"status": "ignored", "reason": "no_text_or_audio_content"}

    # Step 2: Reply Understanding Skill
    understanding_skill = get_skill("understanding")
    understanding_meta = {}
    if understanding_skill:
        sk_conf = get_training_skill("understanding") or {}
        if sk_conf.get("enabled", 1):
            understanding_meta = understanding_skill.execute({"text": processed_text}, sk_conf)

    # Step 3: Dynamic Prompt Construction with Active Instructions & Matching Knowledge Chunks
    system_prompt, meta = build_dynamic_prompt(processed_text)
    if understanding_meta:
        system_prompt += f"\n\n### Incoming Analysis\n{understanding_meta.get('summary', '')}"

    # Step 4: Generate Assistant Reply
    model_settings = get_setting("models", {}) or {}
    provider_name = model_settings.get("default_provider", "anthropic")
    model_name = (model_settings.get("default_model") or "").strip() or "claude-sonnet-5-5"

    try:
        active_key = get_active_provider_key(provider_name)
        raw_key = crypto.decrypt_key(active_key["encrypted_key"]) if active_key else os.environ.get("ANTHROPIC_API_KEY", "")
        base_url = active_key.get("base_url") if active_key else os.environ.get("ANTHROPIC_BASE_URL")
        adapter = get_adapter(provider_name)
        conv_payload = [{"role": "user", "content": processed_text}]
        response = adapter.complete(
            model=model_name,
            messages=conv_payload,
            system=system_prompt,
            api_key=raw_key,
            base_url=base_url
        )
        reply = response.content
    except Exception as exc:
        reply = "Thank you for reaching out to Octapus. Our team has received your message and will follow up shortly."

    # Step 5: Send response via canonical sendMessage function
    send_result = sendMessage(clean_number, reply)

    return {
        "status": "ok",
        "to": clean_number,
        "reply": reply,
        "send_result": send_result,
        "audio_ref": audio_ref,
        "understanding": understanding_meta,
        "used_instructions": meta.get("used_instructions", []),
        "used_knowledge_chunks": meta.get("used_knowledge_chunks", [])
    }

