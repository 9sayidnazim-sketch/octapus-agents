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
    if os.environ.get("VERCEL") or not os.access(BASE_DIR, os.W_OK):
        return Path("/tmp/staff_assistant.db")
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

            -- Agent Training Center Tables
            CREATE TABLE IF NOT EXISTS training_instructions (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                priority INTEGER DEFAULT 1,
                active INTEGER DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS training_knowledge (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                tags TEXT DEFAULT '',
                source TEXT DEFAULT 'pasted',
                chunk_index INTEGER DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS training_skills (
                skill_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                enabled INTEGER DEFAULT 1,
                extra_instructions TEXT DEFAULT '',
                tone TEXT DEFAULT 'Professional',
                language TEXT DEFAULT 'auto',
                templates TEXT DEFAULT '',
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS training_logs (
                id TEXT PRIMARY KEY,
                user TEXT NOT NULL DEFAULT 'admin',
                action TEXT NOT NULL,
                entity_type TEXT NOT NULL,
                entity_id TEXT,
                details TEXT,
                snapshot TEXT,
                timestamp TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS training_corrections (
                id TEXT PRIMARY KEY,
                query TEXT NOT NULL,
                bot_reply TEXT NOT NULL,
                correction TEXT NOT NULL,
                rating TEXT DEFAULT '',
                instruction_id TEXT,
                created_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_training_inst_active ON training_instructions(active, priority);
            CREATE INDEX IF NOT EXISTS idx_training_know_source ON training_knowledge(source);
            CREATE INDEX IF NOT EXISTS idx_training_logs_time ON training_logs(timestamp);
        """)

        # Seed initial skills if not present
        default_skills = [
            ("transcription", "Audio transcription", 1, "Download incoming audio notes, transcribe faithfully, and retain original audio metadata.", "Neutral", "auto", ""),
            ("understanding", "Reply understanding", 1, "Detect language, determine intent (question, complaint, order, other), and detect sentiment before answering.", "Analytical", "auto", ""),
            ("answering", "Answering", 1, "Answer questions strictly using saved knowledge. If an answer cannot be determined from saved knowledge, state that you will check with the team instead of guessing.", "Helpful", "auto", "I don't have that specific detail in our verified knowledge base yet. I will check with our team and verify for you."),
            ("designing", "Designing", 1, "Generate design briefs, UI layouts, color palettes, and clean HTML/SVG mockups upon user request.", "Creative", "auto", ""),
            ("documenting", "Documenting", 1, "Generate structured executive summaries, business reports, and itemized invoice documents upon user request.", "Formal", "auto", "")
        ]
        for sid, sname, en, extra, tone, lang, tmpl in default_skills:
            conn.execute("""
                INSERT OR IGNORE INTO training_skills (skill_id, name, enabled, extra_instructions, tone, language, templates, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (sid, sname, en, extra, tone, lang, tmpl, now_iso()))
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
        "default_model": "claude-sonnet-5-5",
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


# ============================================================================
# Agent Training Center CRUD & Operations
# ============================================================================

# --- 1. Instructions CRUD ---

def list_training_instructions(active_only: bool = False, db_path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Retrieve all instructions or only active instructions ordered by priority."""
    conn = get_connection(db_path)
    query = """
        SELECT id, title, content, priority, active, created_at, updated_at
        FROM training_instructions
    """
    if active_only:
        query += " WHERE active = 1"
    query += " ORDER BY priority ASC, created_at ASC"
    rows = conn.execute(query).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_training_instruction(inst_id: str, db_path: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    """Retrieve a single instruction by ID."""
    conn = get_connection(db_path)
    row = conn.execute("SELECT * FROM training_instructions WHERE id = ?", (inst_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def create_training_instruction(
    title: str,
    content: str,
    priority: int = 1,
    active: int = 1,
    user: str = "admin",
    db_path: Optional[Path] = None
) -> Dict[str, Any]:
    """Create a new training instruction and record audit log."""
    inst_id = str(uuid.uuid4())
    now = now_iso()
    clean_title = title.strip()
    clean_content = content.strip()
    conn = get_connection(db_path)
    with conn:
        conn.execute("""
            INSERT INTO training_instructions (id, title, content, priority, active, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (inst_id, clean_title, clean_content, int(priority), int(active), now, now))
    conn.close()

    created = {
        "id": inst_id,
        "title": clean_title,
        "content": clean_content,
        "priority": int(priority),
        "active": int(active),
        "created_at": now,
        "updated_at": now
    }
    add_training_log(
        user=user,
        action="create_instruction",
        entity_type="instruction",
        entity_id=inst_id,
        details=f"Created instruction: '{clean_title}' (priority {priority})",
        snapshot={"after": created},
        db_path=db_path
    )
    return created


def update_training_instruction(
    inst_id: str,
    title: str,
    content: str,
    priority: int = 1,
    active: int = 1,
    user: str = "admin",
    db_path: Optional[Path] = None
) -> Optional[Dict[str, Any]]:
    """Update an existing training instruction and record audit log."""
    before = get_training_instruction(inst_id, db_path)
    if not before:
        return None
    now = now_iso()
    clean_title = title.strip()
    clean_content = content.strip()
    conn = get_connection(db_path)
    with conn:
        conn.execute("""
            UPDATE training_instructions
            SET title = ?, content = ?, priority = ?, active = ?, updated_at = ?
            WHERE id = ?
        """, (clean_title, clean_content, int(priority), int(active), now, inst_id))
    conn.close()

    after = {
        "id": inst_id,
        "title": clean_title,
        "content": clean_content,
        "priority": int(priority),
        "active": int(active),
        "created_at": before.get("created_at", now),
        "updated_at": now
    }
    add_training_log(
        user=user,
        action="update_instruction",
        entity_type="instruction",
        entity_id=inst_id,
        details=f"Updated instruction: '{clean_title}'",
        snapshot={"before": before, "after": after},
        db_path=db_path
    )
    return after


def delete_training_instruction(inst_id: str, user: str = "admin", db_path: Optional[Path] = None) -> bool:
    """Delete a training instruction and record audit log."""
    before = get_training_instruction(inst_id, db_path)
    if not before:
        return False
    conn = get_connection(db_path)
    with conn:
        conn.execute("DELETE FROM training_instructions WHERE id = ?", (inst_id,))
    conn.close()
    add_training_log(
        user=user,
        action="delete_instruction",
        entity_type="instruction",
        entity_id=inst_id,
        details=f"Deleted instruction: '{before.get('title', inst_id)}'",
        snapshot={"before": before},
        db_path=db_path
    )
    return True


# --- 2. Knowledge / Studies Chunker & CRUD ---

def chunk_text(text: str, chunk_size: int = 600, overlap: int = 100) -> List[str]:
    """Split text into natural chunks preserving paragraphs and sentences."""
    clean = text.strip()
    if not clean:
        return []
    if len(clean) <= chunk_size:
        return [clean]

    # Split into paragraphs first
    paragraphs = clean.split("\n\n")
    chunks: List[str] = []
    current_chunk: List[str] = []
    current_len = 0

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        # If single paragraph exceeds chunk_size, split by sentences or spaces
        if len(para) > chunk_size:
            if current_chunk:
                chunks.append("\n\n".join(current_chunk))
                current_chunk = []
                current_len = 0
            # Sentence split
            sentences = para.replace(". ", ".\n").splitlines()
            s_accum = ""
            for s in sentences:
                s = s.strip()
                if not s:
                    continue
                if len(s_accum) + len(s) + 1 <= chunk_size:
                    s_accum = f"{s_accum} {s}".strip() if s_accum else s
                else:
                    if s_accum:
                        chunks.append(s_accum)
                    s_accum = s
            if s_accum:
                chunks.append(s_accum)
            continue

        if current_len + len(para) + 2 <= chunk_size:
            current_chunk.append(para)
            current_len += len(para) + 2
        else:
            chunks.append("\n\n".join(current_chunk))
            current_chunk = [para]
            current_len = len(para)

    if current_chunk:
        chunks.append("\n\n".join(current_chunk))

    return [c.strip() for c in chunks if c.strip()]


def add_training_knowledge(
    title: str,
    text: str,
    tags: str = "",
    source: str = "pasted",
    user: str = "admin",
    db_path: Optional[Path] = None
) -> List[Dict[str, Any]]:
    """Split text into chunks, save each chunk with metadata, and record audit log."""
    chunks = chunk_text(text)
    if not chunks:
        chunks = [text.strip()]
    now = now_iso()
    saved: List[Dict[str, Any]] = []
    conn = get_connection(db_path)
    with conn:
        for idx, chunk in enumerate(chunks):
            cid = str(uuid.uuid4())
            conn.execute("""
                INSERT INTO training_knowledge (id, title, content, tags, source, chunk_index, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (cid, title.strip(), chunk, tags.strip(), source.strip(), idx, now, now))
            saved.append({
                "id": cid,
                "title": title.strip(),
                "content": chunk,
                "tags": tags.strip(),
                "source": source.strip(),
                "chunk_index": idx,
                "created_at": now,
                "updated_at": now
            })
    conn.close()

    add_training_log(
        user=user,
        action="add_knowledge",
        entity_type="knowledge",
        entity_id=saved[0]["id"] if saved else None,
        details=f"Added knowledge '{title}' ({len(chunks)} chunks from source '{source}')",
        snapshot={"after": saved},
        db_path=db_path
    )
    return saved


def list_training_knowledge(query: Optional[str] = None, limit: int = 100, db_path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Search and list knowledge chunks."""
    conn = get_connection(db_path)
    if query and query.strip():
        term = f"%{query.strip().lower()}%"
        sql = """
            SELECT * FROM training_knowledge
            WHERE LOWER(title) LIKE ? OR LOWER(content) LIKE ? OR LOWER(tags) LIKE ? OR LOWER(source) LIKE ?
            ORDER BY created_at DESC
            LIMIT ?
        """
        rows = conn.execute(sql, (term, term, term, term, limit)).fetchall()
    else:
        sql = "SELECT * FROM training_knowledge ORDER BY created_at DESC LIMIT ?"
        rows = conn.execute(sql, (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_training_knowledge(know_id: str, db_path: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    """Retrieve single knowledge chunk."""
    conn = get_connection(db_path)
    row = conn.execute("SELECT * FROM training_knowledge WHERE id = ?", (know_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def delete_training_knowledge(know_id: str, user: str = "admin", db_path: Optional[Path] = None) -> bool:
    """Delete a single knowledge chunk."""
    before = get_training_knowledge(know_id, db_path)
    if not before:
        return False
    conn = get_connection(db_path)
    with conn:
        conn.execute("DELETE FROM training_knowledge WHERE id = ?", (know_id,))
    conn.close()
    add_training_log(
        user=user,
        action="delete_knowledge",
        entity_type="knowledge",
        entity_id=know_id,
        details=f"Deleted knowledge chunk: '{before.get('title', know_id)}' (chunk {before.get('chunk_index', 0)})",
        snapshot={"before": before},
        db_path=db_path
    )
    return True


def delete_training_knowledge_by_source(source: str, user: str = "admin", db_path: Optional[Path] = None) -> int:
    """Delete all knowledge chunks belonging to a specific source file."""
    conn = get_connection(db_path)
    rows = conn.execute("SELECT * FROM training_knowledge WHERE source = ?", (source,)).fetchall()
    if not rows:
        conn.close()
        return 0
    before_items = [dict(r) for r in rows]
    with conn:
        conn.execute("DELETE FROM training_knowledge WHERE source = ?", (source,))
    conn.close()
    add_training_log(
        user=user,
        action="delete_knowledge_source",
        entity_type="knowledge",
        entity_id=source,
        details=f"Deleted {len(before_items)} chunks for source '{source}'",
        snapshot={"before": before_items},
        db_path=db_path
    )
    return len(before_items)


def get_top_matching_knowledge(query_text: str, limit: int = 4, db_path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Retrieve top relevant knowledge chunks using term overlap scoring."""
    tokens = [t.lower() for t in query_text.replace("?", " ").replace("!", " ").replace(".", " ").replace(",", " ").split() if len(t) > 2]
    all_chunks = list_training_knowledge(limit=250, db_path=db_path)
    if not all_chunks:
        return []

    if not tokens:
        return all_chunks[:limit]

    scored = []
    for item in all_chunks:
        score = 0
        title_lower = (item.get("title") or "").lower()
        content_lower = (item.get("content") or "").lower()
        tags_lower = (item.get("tags") or "").lower()

        for token in tokens:
            if token in title_lower:
                score += 3
            if token in tags_lower:
                score += 3
            if token in content_lower:
                score += 1
        if score > 0:
            scored.append((score, item))

    # Sort descending by score
    scored.sort(key=lambda x: x[0], reverse=True)
    results = [item for _, item in scored[:limit]]
    # If no keyword matches, fallback to first recent items
    return results if results else all_chunks[:min(limit, 2)]


# --- 3. Skills Configuration CRUD ---

def list_training_skills(db_path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Retrieve all skill settings and configurations."""
    conn = get_connection(db_path)
    rows = conn.execute("SELECT * FROM training_skills ORDER BY skill_id ASC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_training_skill(skill_id: str, db_path: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    """Retrieve single skill setting."""
    conn = get_connection(db_path)
    row = conn.execute("SELECT * FROM training_skills WHERE skill_id = ?", (skill_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def update_training_skill(
    skill_id: str,
    enabled: int,
    extra_instructions: str,
    tone: str,
    language: str,
    templates: str,
    user: str = "admin",
    db_path: Optional[Path] = None
) -> Optional[Dict[str, Any]]:
    """Update skill configuration (toggle, tone, language, extra_instructions, templates)."""
    before = get_training_skill(skill_id, db_path)
    if not before:
        return None
    now = now_iso()
    conn = get_connection(db_path)
    with conn:
        conn.execute("""
            UPDATE training_skills
            SET enabled = ?, extra_instructions = ?, tone = ?, language = ?, templates = ?, updated_at = ?
            WHERE skill_id = ?
        """, (int(enabled), extra_instructions.strip(), tone.strip(), language.strip(), templates.strip(), now, skill_id))
    conn.close()

    after = {
        "skill_id": skill_id,
        "name": before.get("name", skill_id),
        "enabled": int(enabled),
        "extra_instructions": extra_instructions.strip(),
        "tone": tone.strip(),
        "language": language.strip(),
        "templates": templates.strip(),
        "updated_at": now
    }
    add_training_log(
        user=user,
        action="update_skill",
        entity_type="skill",
        entity_id=skill_id,
        details=f"Updated skill '{after['name']}': enabled={bool(enabled)}, tone={tone}",
        snapshot={"before": before, "after": after},
        db_path=db_path
    )
    return after


# --- 4. Training Logs & Restore ---

def add_training_log(
    user: str,
    action: str,
    entity_type: str,
    entity_id: Optional[str],
    details: str,
    snapshot: Optional[Dict[str, Any]] = None,
    db_path: Optional[Path] = None
) -> Dict[str, Any]:
    """Append a log entry tracking who, when, and what changed with optional state snapshot."""
    log_id = str(uuid.uuid4())
    now = now_iso()
    snapshot_json = json.dumps(snapshot, ensure_ascii=False) if snapshot else ""
    conn = get_connection(db_path)
    with conn:
        conn.execute("""
            INSERT INTO training_logs (id, user, action, entity_type, entity_id, details, snapshot, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (log_id, user, action, entity_type, entity_id or "", details, snapshot_json, now))
    conn.close()
    return {
        "id": log_id,
        "user": user,
        "action": action,
        "entity_type": entity_type,
        "entity_id": entity_id or "",
        "details": details,
        "timestamp": now
    }


def list_training_logs(limit: int = 100, db_path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Retrieve training audit history ordered chronologically."""
    conn = get_connection(db_path)
    rows = conn.execute("SELECT * FROM training_logs ORDER BY timestamp DESC LIMIT ?", (limit,)).fetchall()
    conn.close()
    logs = []
    for r in rows:
        d = dict(r)
        if d.get("snapshot"):
            try:
                d["snapshot_data"] = json.loads(d["snapshot"])
            except Exception:
                d["snapshot_data"] = None
        logs.append(d)
    return logs


def restore_training_log(log_id: str, user: str = "admin", db_path: Optional[Path] = None) -> Dict[str, Any]:
    """Restore a previous version based on a log entry snapshot."""
    conn = get_connection(db_path)
    row = conn.execute("SELECT * FROM training_logs WHERE id = ?", (log_id,)).fetchone()
    conn.close()
    if not row:
        raise ValueError(f"Log entry '{log_id}' not found.")

    log_entry = dict(row)
    snapshot_raw = log_entry.get("snapshot") or ""
    if not snapshot_raw:
        raise ValueError(f"No reversible snapshot data exists for log '{log_id}'.")

    snapshot = json.loads(snapshot_raw)
    action = log_entry.get("action", "")
    entity_type = log_entry.get("entity_type", "")
    restored_info = {}

    conn = get_connection(db_path)
    with conn:
        if entity_type == "instruction":
            # If deleted, restore 'before' state
            if "delete" in action and "before" in snapshot:
                b = snapshot["before"]
                conn.execute("""
                    INSERT OR REPLACE INTO training_instructions (id, title, content, priority, active, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (b["id"], b["title"], b["content"], b["priority"], b["active"], b["created_at"], now_iso()))
                restored_info = {"restored_instruction": b["id"]}
            # If created, delete or deactivate
            elif "create" in action and "after" in snapshot:
                a = snapshot["after"]
                conn.execute("DELETE FROM training_instructions WHERE id = ?", (a["id"],))
                restored_info = {"removed_instruction": a["id"]}
            # If updated, restore 'before' state
            elif "update" in action and "before" in snapshot:
                b = snapshot["before"]
                conn.execute("""
                    UPDATE training_instructions
                    SET title = ?, content = ?, priority = ?, active = ?, updated_at = ?
                    WHERE id = ?
                """, (b["title"], b["content"], b["priority"], b["active"], now_iso(), b["id"]))
                restored_info = {"reverted_instruction": b["id"]}

        elif entity_type == "skill" and "before" in snapshot:
            b = snapshot["before"]
            conn.execute("""
                UPDATE training_skills
                SET enabled = ?, extra_instructions = ?, tone = ?, language = ?, templates = ?, updated_at = ?
                WHERE skill_id = ?
            """, (b["enabled"], b["extra_instructions"], b["tone"], b["language"], b["templates"], now_iso(), b["skill_id"]))
            restored_info = {"reverted_skill": b["skill_id"]}

        elif entity_type == "knowledge":
            if "delete" in action and "before" in snapshot:
                b = snapshot["before"]
                items = b if isinstance(b, list) else [b]
                for item in items:
                    conn.execute("""
                        INSERT OR REPLACE INTO training_knowledge (id, title, content, tags, source, chunk_index, created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """, (item["id"], item["title"], item["content"], item.get("tags", ""), item.get("source", "pasted"), item.get("chunk_index", 0), item["created_at"], now_iso()))
                restored_info = {"restored_knowledge_count": len(items)}
            elif "add" in action and "after" in snapshot:
                a = snapshot["after"]
                items = a if isinstance(a, list) else [a]
                for item in items:
                    conn.execute("DELETE FROM training_knowledge WHERE id = ?", (item["id"],))
                restored_info = {"removed_knowledge_count": len(items)}

    conn.close()

    add_training_log(
        user=user,
        action="restore_version",
        entity_type=entity_type,
        entity_id=log_entry.get("entity_id"),
        details=f"Restored version from log entry {log_id[:8]} ({action})",
        snapshot={"restored_from": log_id},
        db_path=db_path
    )
    return {"status": "ok", "restored": restored_info, "log_id": log_id}


# --- 5. Corrections CRUD ---

def add_training_correction(
    query: str,
    bot_reply: str,
    correction: str,
    rating: str = "",
    create_instruction: bool = False,
    user: str = "admin",
    db_path: Optional[Path] = None
) -> Dict[str, Any]:
    """Save user test chat correction and optionally create an active instruction."""
    cid = str(uuid.uuid4())
    now = now_iso()
    instruction_id = None

    if create_instruction and correction.strip():
        inst_title = f"Correction: {query[:35]}..." if len(query) > 35 else f"Correction: {query}"
        inst_content = (
            f"When the user asks: \"{query.strip()}\"\n"
            f"Do NOT say: \"{bot_reply.strip()[:200]}\"\n"
            f"Instead, answer: \"{correction.strip()}\""
        )
        new_inst = create_training_instruction(
            title=inst_title,
            content=inst_content,
            priority=1,
            active=1,
            user=user,
            db_path=db_path
        )
        instruction_id = new_inst["id"]

    conn = get_connection(db_path)
    with conn:
        conn.execute("""
            INSERT INTO training_corrections (id, query, bot_reply, correction, rating, instruction_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (cid, query.strip(), bot_reply.strip(), correction.strip(), rating.strip(), instruction_id, now))
    conn.close()

    add_training_log(
        user=user,
        action="correction",
        entity_type="correction",
        entity_id=cid,
        details=f"Saved reply correction (rating='{rating}', new_instruction={bool(instruction_id)})",
        snapshot={"query": query, "correction": correction, "instruction_id": instruction_id},
        db_path=db_path
    )

    return {
        "id": cid,
        "query": query,
        "bot_reply": bot_reply,
        "correction": correction,
        "rating": rating,
        "instruction_id": instruction_id,
        "created_at": now
    }


def list_training_corrections(limit: int = 50, db_path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Retrieve history of saved corrections."""
    conn = get_connection(db_path)
    rows = conn.execute("SELECT * FROM training_corrections ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

