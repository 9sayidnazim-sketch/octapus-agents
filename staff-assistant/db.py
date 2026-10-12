"""SQLite Database Layer for Octapus Staff Assistant.

Manages persistent storage for:
- Encrypted provider keys
- Conversations and message histories
- Long-term memory facts (with approval states)
- Aggregated token usage and cost tracking
- Global assistant, appearance, notification, and privacy settings
"""

from __future__ import annotations

import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_DB_PATH = BASE_DIR / "staff_assistant.db"


def get_db_path() -> Path:
    """Resolve SQLite database path from DATABASE_URL or default."""
    db_url = os.environ.get("DATABASE_URL")
    if db_url and db_url.startswith("sqlite:///"):
        return Path(db_url.replace("sqlite:///", ""))
    if db_url and not db_url.startswith("sqlite://"):
        return Path(db_url)
    return DEFAULT_DB_PATH


def get_connection(db_path: Optional[Path] = None) -> sqlite3.Connection:
    """Return a thread-safe SQLite connection with Row factory."""
    path = db_path or get_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def now_iso() -> str:
    """Return current UTC timestamp in ISO 8601 format."""
    return datetime.now(timezone.utc).isoformat()


def init_db(db_path: Optional[Path] = None) -> None:
    """Initialize SQLite tables and indexes."""
    conn = get_connection(db_path)
    with conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS provider_keys (
                id TEXT PRIMARY KEY,
                provider TEXT NOT NULL,
                label TEXT NOT NULL,
                encrypted_key TEXT NOT NULL,
                base_url TEXT,
                status TEXT DEFAULT 'not_set',
                status_message TEXT DEFAULT '',
                is_default INTEGER DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS conversations (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                provider TEXT,
                model TEXT,
                summary TEXT DEFAULT '',
                archived INTEGER DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS messages (
                id TEXT PRIMARY KEY,
                conversation_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                provider TEXT,
                model TEXT,
                input_tokens INTEGER DEFAULT 0,
                output_tokens INTEGER DEFAULT 0,
                cost REAL DEFAULT 0.0,
                created_at TEXT NOT NULL,
                FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS memory_facts (
                id TEXT PRIMARY KEY,
                conversation_id TEXT,
                fact TEXT NOT NULL,
                source TEXT DEFAULT '',
                confidence REAL DEFAULT 1.0,
                is_approved INTEGER DEFAULT 0,
                is_pinned INTEGER DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS usage_records (
                id TEXT PRIMARY KEY,
                conversation_id TEXT,
                provider TEXT NOT NULL,
                model TEXT NOT NULL,
                input_tokens INTEGER DEFAULT 0,
                output_tokens INTEGER DEFAULT 0,
                cost REAL DEFAULT 0.0,
                created_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_messages_conv ON messages(conversation_id);
            CREATE INDEX IF NOT EXISTS idx_usage_created ON usage_records(created_at);
            CREATE INDEX IF NOT EXISTS idx_usage_provider ON usage_records(provider);
            CREATE INDEX IF NOT EXISTS idx_memory_approved ON memory_facts(is_approved);
        """)
    conn.close()


# ============================================================================
# Settings CRUD
# ============================================================================

DEFAULT_SETTINGS: Dict[str, Any] = {
    "assistant": {
        "name": "Octapus Assistant",
        "personality": "Professional",
        "custom_instructions": "",
        "language": "auto-detect",
        "markdown_enabled": True,
        "bullet_preference": "bullet",
        "max_answer_length": "medium",
        "confirm_write_actions": True,
        "show_sources": True,
        "show_token_cost": False,
    },
    "models": {
        "default_provider": "anthropic",
        "default_model": "",
        "temperature": 0.7,
        "max_output_tokens": 1200,
        "top_p": 1.0,
        "summary_threshold": 20,
        "context_recent_messages": 20,
    },
    "pricing": {
        # Per million tokens (input / output)
        "claude-sonnet-5-5": {"input": 3.0, "output": 15.0},
        "claude-3-7-sonnet": {"input": 3.0, "output": 15.0},
        "claude-3-5-haiku": {"input": 0.8, "output": 4.0},
        "gpt-4o": {"input": 2.5, "output": 10.0},
        "gpt-4o-mini": {"input": 0.15, "output": 0.6},
        "gemini-1.5-pro": {"input": 1.25, "output": 5.0},
        "gemini-1.5-flash": {"input": 0.075, "output": 0.3},
        "default": {"input": 2.0, "output": 8.0},
    },
    "budget": {
        "monthly_budget": 0.0,  # 0.0 means no budget limit
        "hard_stop": True,
        "user_overridden": False,
    },
    "appearance": {
        "theme": "system",
        "font_size": "medium",
        "spacing": "comfortable",
        "show_timestamps": True,
        "sidebar_open": True,
    },
    "notifications": {
        "in_app_badges": True,
        "email_reminders": False,
    },
    "privacy": {
        "retention_period": "forever",  # forever, 1_year, 90_days, 30_days
    },
    "account": {
        "staff_password_hash": None,
    },
}


def get_setting(key: str, default: Any = None, db_path: Optional[Path] = None) -> Any:
    """Retrieve setting value by key."""
    conn = get_connection(db_path)
    cur = conn.execute("SELECT value FROM settings WHERE key = ?", (key,))
    row = cur.fetchone()
    conn.close()
    if row:
        try:
            return json.loads(row["value"])
        except Exception:
            return row["value"]
    return default if default is not None else DEFAULT_SETTINGS.get(key)


def set_setting(key: str, value: Any, db_path: Optional[Path] = None) -> None:
    """Store or update setting value by key."""
    conn = get_connection(db_path)
    val_str = json.dumps(value) if not isinstance(value, str) else value
    with conn:
        conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, val_str),
        )
    conn.close()


def get_all_settings(db_path: Optional[Path] = None) -> Dict[str, Any]:
    """Retrieve all settings combined with defaults."""
    result = {k: v.copy() if isinstance(v, dict) else v for k, v in DEFAULT_SETTINGS.items()}
    conn = get_connection(db_path)
    for row in conn.execute("SELECT key, value FROM settings"):
        key = row["key"]
        try:
            val = json.loads(row["value"])
        except Exception:
            val = row["value"]
        if isinstance(result.get(key), dict) and isinstance(val, dict):
            result[key].update(val)
        else:
            result[key] = val
    conn.close()
    return result


# ============================================================================
# Provider Keys CRUD
# ============================================================================

def list_provider_keys(db_path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """List all provider keys."""
    conn = get_connection(db_path)
    cur = conn.execute("SELECT * FROM provider_keys ORDER BY created_at ASC")
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def get_provider_key(key_id: str, db_path: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    """Get single provider key by ID."""
    conn = get_connection(db_path)
    cur = conn.execute("SELECT * FROM provider_keys WHERE id = ?", (key_id,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def get_active_provider_key(provider: str, db_path: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    """Get the default or first active key for a provider."""
    conn = get_connection(db_path)
    cur = conn.execute(
        "SELECT * FROM provider_keys WHERE provider = ? ORDER BY is_default DESC, created_at ASC LIMIT 1",
        (provider,),
    )
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def save_provider_key(
    provider: str,
    label: str,
    encrypted_key: str,
    base_url: Optional[str] = None,
    is_default: bool = False,
    status: str = "connected",
    status_message: str = "",
    key_id: Optional[str] = None,
    db_path: Optional[Path] = None,
) -> str:
    """Insert or update a provider key."""
    conn = get_connection(db_path)
    kid = key_id or str(uuid.uuid4())
    now = now_iso()
    with conn:
        if is_default:
            conn.execute("UPDATE provider_keys SET is_default = 0 WHERE provider = ?", (provider,))
        conn.execute("""
            INSERT INTO provider_keys (
                id, provider, label, encrypted_key, base_url, status, status_message, is_default, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                label = excluded.label,
                encrypted_key = excluded.encrypted_key,
                base_url = excluded.base_url,
                status = excluded.status,
                status_message = excluded.status_message,
                is_default = excluded.is_default,
                updated_at = excluded.updated_at
        """, (kid, provider, label, encrypted_key, base_url, status, status_message, 1 if is_default else 0, now, now))
    conn.close()
    return kid


def update_provider_key_status(
    key_id: str, status: str, status_message: str = "", db_path: Optional[Path] = None
) -> None:
    """Update status of a provider key."""
    conn = get_connection(db_path)
    now = now_iso()
    with conn:
        conn.execute(
            "UPDATE provider_keys SET status = ?, status_message = ?, updated_at = ? WHERE id = ?",
            (status, status_message, now, key_id),
        )
    conn.close()


def delete_provider_key(key_id: str, db_path: Optional[Path] = None) -> bool:
    """Delete a provider key and update default references if needed."""
    conn = get_connection(db_path)
    with conn:
        cur = conn.execute("DELETE FROM provider_keys WHERE id = ?", (key_id,))
        deleted = cur.rowcount > 0
    conn.close()
    return deleted


# ============================================================================
# Conversations and Messages CRUD
# ============================================================================

def create_conversation(
    conv_id: Optional[str] = None,
    title: str = "New Chat",
    provider: Optional[str] = None,
    model: Optional[str] = None,
    db_path: Optional[Path] = None,
) -> str:
    """Create a new conversation record."""
    cid = conv_id or str(uuid.uuid4())
    conn = get_connection(db_path)
    now = now_iso()
    with conn:
        conn.execute("""
            INSERT INTO conversations (id, title, provider, model, summary, archived, created_at, updated_at)
            VALUES (?, ?, ?, ?, '', 0, ?, ?)
            ON CONFLICT(id) DO UPDATE SET updated_at = excluded.updated_at
        """, (cid, title, provider, model, now, now))
    conn.close()
    return cid


def get_conversation(conv_id: str, db_path: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    """Retrieve conversation by ID."""
    conn = get_connection(db_path)
    cur = conn.execute("SELECT * FROM conversations WHERE id = ?", (conv_id,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def list_conversations(include_archived: bool = False, db_path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """List conversations ordered by updated_at desc."""
    conn = get_connection(db_path)
    query = "SELECT * FROM conversations "
    if not include_archived:
        query += "WHERE archived = 0 "
    query += "ORDER BY updated_at DESC"
    cur = conn.execute(query)
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def update_conversation(
    conv_id: str,
    title: Optional[str] = None,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    summary: Optional[str] = None,
    archived: Optional[bool] = None,
    db_path: Optional[Path] = None,
) -> bool:
    """Update conversation fields."""
    conn = get_connection(db_path)
    updates = ["updated_at = ?"]
    params: List[Any] = [now_iso()]
    if title is not None:
        updates.append("title = ?")
        params.append(title)
    if provider is not None:
        updates.append("provider = ?")
        params.append(provider)
    if model is not None:
        updates.append("model = ?")
        params.append(model)
    if summary is not None:
        updates.append("summary = ?")
        params.append(summary)
    if archived is not None:
        updates.append("archived = ?")
        params.append(1 if archived else 0)
    params.append(conv_id)
    with conn:
        cur = conn.execute(f"UPDATE conversations SET {', '.join(updates)} WHERE id = ?", params)
        updated = cur.rowcount > 0
    conn.close()
    return updated


def delete_conversation(conv_id: str, db_path: Optional[Path] = None) -> bool:
    """Delete conversation and its associated messages."""
    conn = get_connection(db_path)
    with conn:
        conn.execute("DELETE FROM messages WHERE conversation_id = ?", (conv_id,))
        cur = conn.execute("DELETE FROM conversations WHERE id = ?", (conv_id,))
        deleted = cur.rowcount > 0
    conn.close()
    return deleted


def add_message(
    conversation_id: str,
    role: str,
    content: str,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    input_tokens: int = 0,
    output_tokens: int = 0,
    cost: float = 0.0,
    db_path: Optional[Path] = None,
) -> str:
    """Add a message to a conversation."""
    mid = str(uuid.uuid4())
    now = now_iso()
    conn = get_connection(db_path)
    with conn:
        conn.execute("""
            INSERT INTO messages (
                id, conversation_id, role, content, provider, model, input_tokens, output_tokens, cost, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (mid, conversation_id, role, content, provider, model, input_tokens, output_tokens, cost, now))
        conn.execute("UPDATE conversations SET updated_at = ? WHERE id = ?", (now, conversation_id))
    conn.close()
    return mid


def get_conversation_messages(conversation_id: str, limit: Optional[int] = None, db_path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Retrieve messages for a conversation ordered chronologically."""
    conn = get_connection(db_path)
    query = "SELECT * FROM messages WHERE conversation_id = ? ORDER BY created_at ASC"
    if limit is not None:
        query += f" LIMIT {limit}"
    cur = conn.execute(query, (conversation_id,))
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


# ============================================================================
# Memory Facts CRUD
# ============================================================================

def list_memory_facts(
    conversation_id: Optional[str] = None,
    approved_only: bool = False,
    db_path: Optional[Path] = None,
) -> List[Dict[str, Any]]:
    """List memory facts."""
    conn = get_connection(db_path)
    conditions = []
    params: List[Any] = []
    if conversation_id:
        conditions.append("(conversation_id = ? OR conversation_id IS NULL)")
        params.append(conversation_id)
    if approved_only:
        conditions.append("is_approved = 1")

    query = "SELECT * FROM memory_facts "
    if conditions:
        query += "WHERE " + " AND ".join(conditions) + " "
    query += "ORDER BY is_pinned DESC, created_at DESC"

    cur = conn.execute(query, params)
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def add_memory_fact(
    fact: str,
    source: str = "",
    confidence: float = 1.0,
    is_approved: bool = False,
    is_pinned: bool = False,
    conversation_id: Optional[str] = None,
    db_path: Optional[Path] = None,
) -> str:
    """Propose or save a memory fact."""
    fid = str(uuid.uuid4())
    now = now_iso()
    conn = get_connection(db_path)
    with conn:
        conn.execute("""
            INSERT INTO memory_facts (
                id, conversation_id, fact, source, confidence, is_approved, is_pinned, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (fid, conversation_id, fact, source, confidence, 1 if is_approved else 0, 1 if is_pinned else 0, now, now))
    conn.close()
    return fid


def update_memory_fact(
    fact_id: str,
    fact: Optional[str] = None,
    is_approved: Optional[bool] = None,
    is_pinned: Optional[bool] = None,
    db_path: Optional[Path] = None,
) -> bool:
    """Update memory fact content, approval, or pinned state."""
    conn = get_connection(db_path)
    updates = ["updated_at = ?"]
    params: List[Any] = [now_iso()]
    if fact is not None:
        updates.append("fact = ?")
        params.append(fact)
    if is_approved is not None:
        updates.append("is_approved = ?")
        params.append(1 if is_approved else 0)
    if is_pinned is not None:
        updates.append("is_pinned = ?")
        params.append(1 if is_pinned else 0)
    params.append(fact_id)
    with conn:
        cur = conn.execute(f"UPDATE memory_facts SET {', '.join(updates)} WHERE id = ?", params)
        updated = cur.rowcount > 0
    conn.close()
    return updated


def delete_memory_fact(fact_id: str, db_path: Optional[Path] = None) -> bool:
    """Delete a memory fact."""
    conn = get_connection(db_path)
    with conn:
        cur = conn.execute("DELETE FROM memory_facts WHERE id = ?", (fact_id,))
        deleted = cur.rowcount > 0
    conn.close()
    return deleted


# ============================================================================
# Usage Tracking CRUD
# ============================================================================

def record_usage(
    provider: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    cost: float,
    conversation_id: Optional[str] = None,
    db_path: Optional[Path] = None,
) -> str:
    """Record token usage and estimated cost."""
    rid = str(uuid.uuid4())
    now = now_iso()
    conn = get_connection(db_path)
    with conn:
        conn.execute("""
            INSERT INTO usage_records (
                id, conversation_id, provider, model, input_tokens, output_tokens, cost, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (rid, conversation_id, provider, model, input_tokens, output_tokens, cost, now))
    conn.close()
    return rid


def get_usage_summary(db_path: Optional[Path] = None) -> Dict[str, Any]:
    """Calculate usage totals per day, week, month, provider, and model."""
    conn = get_connection(db_path)
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    # 7 days ago
    from datetime import timedelta
    week_start = (now - timedelta(days=7)).isoformat()
    month_start = (now - timedelta(days=30)).isoformat()
    current_month_prefix = now.strftime("%Y-%m")

    # Day totals
    cur_day = conn.execute(
        "SELECT SUM(input_tokens) as inp, SUM(output_tokens) as outp, SUM(cost) as cost FROM usage_records WHERE created_at >= ?",
        (today_start,),
    )
    r_day = cur_day.fetchone()

    # Week totals
    cur_week = conn.execute(
        "SELECT SUM(input_tokens) as inp, SUM(output_tokens) as outp, SUM(cost) as cost FROM usage_records WHERE created_at >= ?",
        (week_start,),
    )
    r_week = cur_week.fetchone()

    # Month totals (last 30 days)
    cur_month = conn.execute(
        "SELECT SUM(input_tokens) as inp, SUM(output_tokens) as outp, SUM(cost) as cost FROM usage_records WHERE created_at >= ?",
        (month_start,),
    )
    r_month = cur_month.fetchone()

    # Calendar month total (for budget enforcement)
    cur_cal_month = conn.execute(
        "SELECT SUM(cost) as cost FROM usage_records WHERE created_at LIKE ?",
        (f"{current_month_prefix}%",),
    )
    r_cal = cur_cal_month.fetchone()
    calendar_month_cost = float(r_cal["cost"] or 0.0) if r_cal else 0.0

    # Per Provider
    cur_prov = conn.execute("""
        SELECT provider, SUM(input_tokens) as inp, SUM(output_tokens) as outp, SUM(cost) as cost
        FROM usage_records
        GROUP BY provider
    """)
    by_provider = {r["provider"]: {"input_tokens": r["inp"] or 0, "output_tokens": r["outp"] or 0, "cost": round(r["cost"] or 0.0, 4)} for r in cur_prov.fetchall()}

    # Per Model
    cur_mod = conn.execute("""
        SELECT model, SUM(input_tokens) as inp, SUM(output_tokens) as outp, SUM(cost) as cost
        FROM usage_records
        GROUP BY model
    """)
    by_model = {r["model"]: {"input_tokens": r["inp"] or 0, "output_tokens": r["outp"] or 0, "cost": round(r["cost"] or 0.0, 4)} for r in cur_mod.fetchall()}

    conn.close()

    return {
        "day": {"input_tokens": r_day["inp"] or 0, "output_tokens": r_day["outp"] or 0, "cost": round(r_day["cost"] or 0.0, 4)},
        "week": {"input_tokens": r_week["inp"] or 0, "output_tokens": r_week["outp"] or 0, "cost": round(r_week["cost"] or 0.0, 4)},
        "month": {"input_tokens": r_month["inp"] or 0, "output_tokens": r_month["outp"] or 0, "cost": round(r_month["cost"] or 0.0, 4)},
        "calendar_month_cost": round(calendar_month_cost, 4),
        "by_provider": by_provider,
        "by_model": by_model,
    }


def clear_all_data(db_path: Optional[Path] = None) -> None:
    """Clear all chat messages, conversations, usage records, and memory facts."""
    conn = get_connection(db_path)
    with conn:
        conn.execute("DELETE FROM messages")
        conn.execute("DELETE FROM conversations")
        conn.execute("DELETE FROM memory_facts")
        conn.execute("DELETE FROM usage_records")
    conn.close()
