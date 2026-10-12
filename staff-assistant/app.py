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
        "default_model": get_setting("models", {}).get("default_model", "claude-sonnet-5-5"),
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
    model_name = body.model or (conv.get("model") if conv else None) or model_settings.get("default_model", "claude-sonnet-5-5")

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
