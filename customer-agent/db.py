"""SQLite Database Layer for Octapus Customer Agent.

Provides persistent storage for:
- Customer chat sessions (Web and WhatsApp)
- Full conversation message history
- Customer inquiries and lead tracking
"""

from __future__ import annotations

import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_DB_PATH = BASE_DIR / "customer_agent.db"


def get_db_path() -> Path:
    """Resolve SQLite database path from DATABASE_URL or default."""
    db_url = os.environ.get("DATABASE_URL")
    if db_url and db_url.startswith("sqlite:///"):
        return Path(db_url.replace("sqlite:///", ""))
    if db_url and not db_url.startswith("sqlite://"):
        return Path(db_url)
    if os.environ.get("VERCEL") or not os.access(BASE_DIR, os.W_OK):
        return Path("/tmp/customer_agent.db")
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
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                channel TEXT NOT NULL DEFAULT 'web',
                customer_phone TEXT,
                customer_name TEXT,
                message_count INTEGER DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS messages (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS leads (
                id TEXT PRIMARY KEY,
                session_id TEXT,
                phone TEXT,
                name TEXT,
                notes TEXT,
                status TEXT DEFAULT 'new',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS reminders_metadata (
                id TEXT PRIMARY KEY,
                api_reminder_id INTEGER,
                api_list_id INTEGER,
                user_id TEXT NOT NULL,
                title TEXT NOT NULL,
                notes TEXT,
                date TEXT NOT NULL,
                time TEXT NOT NULL,
                priority TEXT NOT NULL DEFAULT 'low',
                timezone TEXT NOT NULL DEFAULT 'Asia/Dubai',
                scheduled_at_utc TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'scheduled',
                recurrence TEXT NOT NULL DEFAULT 'none',
                channel TEXT NOT NULL DEFAULT 'whatsapp',
                recipient TEXT NOT NULL,
                follow_up_enabled INTEGER NOT NULL DEFAULT 1,
                max_follow_ups INTEGER NOT NULL DEFAULT 2,
                follow_up_count INTEGER NOT NULL DEFAULT 0,
                follow_up_interval_minutes INTEGER NOT NULL DEFAULT 60,
                next_follow_up_at_utc TEXT,
                delivery_attempts INTEGER NOT NULL DEFAULT 0,
                last_delivery_error TEXT,
                delivered_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS user_preferences (
                user_id TEXT PRIMARY KEY,
                timezone TEXT NOT NULL DEFAULT 'Asia/Dubai',
                quiet_hours_start TEXT NOT NULL DEFAULT '22:00',
                quiet_hours_end TEXT NOT NULL DEFAULT '08:00',
                max_follow_ups_per_day INTEGER NOT NULL DEFAULT 3,
                proactive_checkins_enabled INTEGER NOT NULL DEFAULT 1,
                important_dates TEXT NOT NULL DEFAULT '{}',
                routines TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id);
            CREATE INDEX IF NOT EXISTS idx_messages_created ON messages(created_at ASC);
            CREATE INDEX IF NOT EXISTS idx_sessions_updated ON sessions(updated_at DESC);
            CREATE INDEX IF NOT EXISTS idx_sessions_phone ON sessions(customer_phone);
            CREATE INDEX IF NOT EXISTS idx_reminders_status ON reminders_metadata(status, scheduled_at_utc);
            CREATE INDEX IF NOT EXISTS idx_reminders_user ON reminders_metadata(user_id, status);
            CREATE INDEX IF NOT EXISTS idx_reminders_recipient ON reminders_metadata(recipient);
        """)
    conn.close()


def save_message(
    session_id: str,
    role: str,
    content: str,
    channel: str = "web",
    customer_phone: Optional[str] = None,
    customer_name: Optional[str] = None,
    db_path: Optional[Path] = None,
) -> str:
    """Insert a message and update or create its session record."""
    # Infer channel and phone from session_id if applicable
    if session_id.startswith("whatsapp-"):
        channel = "whatsapp"
        if not customer_phone:
            customer_phone = session_id.replace("whatsapp-", "")

    mid = str(uuid.uuid4())
    now = now_iso()
    conn = get_connection(db_path)
    with conn:
        # Upsert session
        cur = conn.execute("SELECT id, message_count FROM sessions WHERE id = ?", (session_id,))
        existing = cur.fetchone()
        if existing:
            new_count = (existing["message_count"] or 0) + 1
            conn.execute(
                """
                UPDATE sessions 
                SET message_count = ?, updated_at = ?,
                    customer_phone = COALESCE(customer_phone, ?),
                    customer_name = COALESCE(customer_name, ?)
                WHERE id = ?
                """,
                (new_count, now, customer_phone, customer_name, session_id),
            )
        else:
            conn.execute(
                """
                INSERT INTO sessions (id, channel, customer_phone, customer_name, message_count, created_at, updated_at)
                VALUES (?, ?, ?, ?, 1, ?, ?)
                """,
                (session_id, channel, customer_phone, customer_name, now, now),
            )

        # Insert message
        conn.execute(
            """
            INSERT INTO messages (id, session_id, role, content, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (mid, session_id, role, content, now),
        )
    conn.close()
    return mid


def get_history(session_id: str, limit: int = 20, db_path: Optional[Path] = None) -> List[Dict[str, str]]:
    """Retrieve message history for LLM consumption in chronological order."""
    conn = get_connection(db_path)
    # Get last N messages in ascending order
    query = """
        SELECT role, content FROM (
            SELECT role, content, created_at 
            FROM messages 
            WHERE session_id = ? 
            ORDER BY created_at DESC 
            LIMIT ?
        ) ORDER BY created_at ASC
    """
    cur = conn.execute(query, (session_id, limit))
    rows = [{"role": row["role"], "content": row["content"]} for row in cur.fetchall()]
    conn.close()
    return rows


def delete_last_message(session_id: str, db_path: Optional[Path] = None) -> bool:
    """Delete the most recent message in a session (used for rollbacks on API failure)."""
    conn = get_connection(db_path)
    with conn:
        cur = conn.execute(
            "SELECT id FROM messages WHERE session_id = ? ORDER BY created_at DESC LIMIT 1",
            (session_id,),
        )
        row = cur.fetchone()
        if row:
            conn.execute("DELETE FROM messages WHERE id = ?", (row["id"],))
            conn.execute(
                "UPDATE sessions SET message_count = MAX(0, message_count - 1), updated_at = ? WHERE id = ?",
                (now_iso(), session_id),
            )
            conn.close()
            return True
    conn.close()
    return False


def clear_session(session_id: str, db_path: Optional[Path] = None) -> bool:
    """Delete all messages for a session."""
    conn = get_connection(db_path)
    with conn:
        conn.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
        cur = conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        deleted = cur.rowcount > 0
    conn.close()
    return deleted


def list_sessions(limit: int = 50, db_path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """List recent sessions with their last message."""
    conn = get_connection(db_path)
    cur = conn.execute(
        """
        SELECT 
            s.id, s.channel, s.customer_phone, s.customer_name, s.message_count, s.created_at, s.updated_at,
            (SELECT content FROM messages WHERE session_id = s.id ORDER BY created_at DESC LIMIT 1) as last_message,
            (SELECT role FROM messages WHERE session_id = s.id ORDER BY created_at DESC LIMIT 1) as last_role
        FROM sessions s
        ORDER BY s.updated_at DESC
        LIMIT ?
        """,
        (limit,),
    )
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def get_db_stats(db_path: Optional[Path] = None) -> Dict[str, Any]:
    """Return database statistics."""
    path = db_path or get_db_path()
    conn = get_connection(path)
    cur_sessions = conn.execute("SELECT COUNT(*) as cnt FROM sessions")
    total_sessions = cur_sessions.fetchone()["cnt"]

    cur_messages = conn.execute("SELECT COUNT(*) as cnt FROM messages")
    total_messages = cur_messages.fetchone()["cnt"]

    cur_whatsapp = conn.execute("SELECT COUNT(*) as cnt FROM sessions WHERE channel = 'whatsapp'")
    whatsapp_sessions = cur_whatsapp.fetchone()["cnt"]

    cur_web = conn.execute("SELECT COUNT(*) as cnt FROM sessions WHERE channel = 'web'")
    web_sessions = cur_web.fetchone()["cnt"]

    conn.close()

    return {
        "status": "connected",
        "engine": "sqlite",
        "db_path": str(path),
        "total_sessions": total_sessions,
        "total_messages": total_messages,
        "whatsapp_sessions": whatsapp_sessions,
        "web_sessions": web_sessions,
    }


# ==============================================================================
# REMINDER METADATA & PROACTIVE CARE HELPERS
# ==============================================================================

def save_reminder_metadata(record: Dict[str, Any], db_path: Optional[Path] = None) -> Dict[str, Any]:
    """Insert or update reminder metadata in SQLite."""
    conn = get_connection(db_path)
    now = now_iso()
    r_id = record.get("id") or str(uuid.uuid4())
    created = record.get("created_at") or now
    with conn:
        conn.execute(
            """
            INSERT INTO reminders_metadata (
                id, api_reminder_id, api_list_id, user_id, title, notes,
                date, time, priority, timezone, scheduled_at_utc, status,
                recurrence, channel, recipient, follow_up_enabled, max_follow_ups,
                follow_up_count, follow_up_interval_minutes, next_follow_up_at_utc,
                delivery_attempts, last_delivery_error, delivered_at, created_at, updated_at
            ) VALUES (
                ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?,
                ?, ?, ?,
                ?, ?, ?, ?, ?
            )
            ON CONFLICT(id) DO UPDATE SET
                api_reminder_id = excluded.api_reminder_id,
                api_list_id = excluded.api_list_id,
                title = excluded.title,
                notes = excluded.notes,
                date = excluded.date,
                time = excluded.time,
                priority = excluded.priority,
                timezone = excluded.timezone,
                scheduled_at_utc = excluded.scheduled_at_utc,
                status = excluded.status,
                recurrence = excluded.recurrence,
                follow_up_enabled = excluded.follow_up_enabled,
                max_follow_ups = excluded.max_follow_ups,
                follow_up_count = excluded.follow_up_count,
                next_follow_up_at_utc = excluded.next_follow_up_at_utc,
                delivery_attempts = excluded.delivery_attempts,
                last_delivery_error = excluded.last_delivery_error,
                delivered_at = excluded.delivered_at,
                updated_at = excluded.updated_at
            """,
            (
                r_id,
                record.get("api_reminder_id"),
                record.get("api_list_id"),
                record["user_id"],
                record["title"],
                record.get("notes", ""),
                record["date"],
                record["time"],
                record.get("priority", "low"),
                record.get("timezone", "Asia/Dubai"),
                record["scheduled_at_utc"],
                record.get("status", "scheduled"),
                record.get("recurrence", "none"),
                record.get("channel", "whatsapp"),
                record["recipient"],
                1 if record.get("follow_up_enabled", True) else 0,
                record.get("max_follow_ups", 2),
                record.get("follow_up_count", 0),
                record.get("follow_up_interval_minutes", 60),
                record.get("next_follow_up_at_utc"),
                record.get("delivery_attempts", 0),
                record.get("last_delivery_error"),
                record.get("delivered_at"),
                created,
                now,
            ),
        )
    conn.close()
    return get_reminder_metadata(r_id, db_path=db_path) or record


def get_reminder_metadata(reminder_id: str, db_path: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    """Retrieve reminder metadata by its UUID."""
    conn = get_connection(db_path)
    cur = conn.execute("SELECT * FROM reminders_metadata WHERE id = ?", (reminder_id,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def list_reminders_metadata(
    user_id: Optional[str] = None,
    status: Optional[str] = None,
    db_path: Optional[Path] = None,
) -> List[Dict[str, Any]]:
    """List reminder metadata filtered by user and/or status."""
    conn = get_connection(db_path)
    query = "SELECT * FROM reminders_metadata WHERE 1=1"
    params: List[Any] = []
    if user_id:
        query += " AND user_id = ?"
        params.append(user_id)
    if status:
        query += " AND status = ?"
        params.append(status)
    query += " ORDER BY scheduled_at_utc ASC"
    cur = conn.execute(query, params)
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def update_reminder_metadata(
    reminder_id: str,
    updates: Dict[str, Any],
    db_path: Optional[Path] = None,
) -> bool:
    """Update fields on an existing reminder record."""
    conn = get_connection(db_path)
    updates["updated_at"] = now_iso()
    set_clauses = [f"{k} = ?" for k in updates.keys()]
    values = list(updates.values()) + [reminder_id]
    with conn:
        cur = conn.execute(
            f"UPDATE reminders_metadata SET {', '.join(set_clauses)} WHERE id = ?",
            values,
        )
        updated = cur.rowcount > 0
    conn.close()
    return updated


def cancel_reminder_metadata(reminder_id: str, db_path: Optional[Path] = None) -> bool:
    """Mark reminder as cancelled in SQLite."""
    return update_reminder_metadata(reminder_id, {"status": "cancelled"}, db_path=db_path)


def claim_due_reminders(now_utc_iso: str, limit: int = 10, db_path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Atomically find and claim due reminders to prevent duplicate execution across workers."""
    conn = get_connection(db_path)
    rows: List[Dict[str, Any]] = []
    with conn:
        cur = conn.execute(
            """
            SELECT id FROM reminders_metadata
            WHERE (
                (status = 'scheduled' AND scheduled_at_utc <= ?)
                OR
                (status = 'awaiting_reply' AND next_follow_up_at_utc IS NOT NULL AND next_follow_up_at_utc <= ?)
            )
            LIMIT ?
            """,
            (now_utc_iso, now_utc_iso, limit),
        )
        ids = [row["id"] for row in cur.fetchall()]
        if ids:
            placeholders = ",".join("?" for _ in ids)
            conn.execute(
                f"""
                UPDATE reminders_metadata
                SET status = 'in_flight', updated_at = ?
                WHERE id IN ({placeholders})
                """,
                [now_utc_iso] + ids,
            )
            cur = conn.execute(f"SELECT * FROM reminders_metadata WHERE id IN ({placeholders})", ids)
            rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def get_user_preferences(user_id: str, db_path: Optional[Path] = None) -> Dict[str, Any]:
    """Get proactive care and timezone preferences for a user."""
    conn = get_connection(db_path)
    cur = conn.execute("SELECT * FROM user_preferences WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    conn.close()
    if row:
        return dict(row)
    # Default preferences
    return {
        "user_id": user_id,
        "timezone": "Asia/Dubai",
        "quiet_hours_start": "22:00",
        "quiet_hours_end": "08:00",
        "max_follow_ups_per_day": 3,
        "proactive_checkins_enabled": 1,
        "important_dates": "{}",
        "routines": "{}",
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }


def save_user_preferences(prefs: Dict[str, Any], db_path: Optional[Path] = None) -> Dict[str, Any]:
    """Save or update user proactive preferences."""
    conn = get_connection(db_path)
    now = now_iso()
    u_id = prefs["user_id"]
    with conn:
        conn.execute(
            """
            INSERT INTO user_preferences (
                user_id, timezone, quiet_hours_start, quiet_hours_end,
                max_follow_ups_per_day, proactive_checkins_enabled,
                important_dates, routines, created_at, updated_at
            ) VALUES (
                ?, ?, ?, ?,
                ?, ?,
                ?, ?, ?, ?
            )
            ON CONFLICT(user_id) DO UPDATE SET
                timezone = excluded.timezone,
                quiet_hours_start = excluded.quiet_hours_start,
                quiet_hours_end = excluded.quiet_hours_end,
                max_follow_ups_per_day = excluded.max_follow_ups_per_day,
                proactive_checkins_enabled = excluded.proactive_checkins_enabled,
                important_dates = excluded.important_dates,
                routines = excluded.routines,
                updated_at = excluded.updated_at
            """,
            (
                u_id,
                prefs.get("timezone", "Asia/Dubai"),
                prefs.get("quiet_hours_start", "22:00"),
                prefs.get("quiet_hours_end", "08:00"),
                prefs.get("max_follow_ups_per_day", 3),
                1 if prefs.get("proactive_checkins_enabled", True) else 0,
                prefs.get("important_dates", "{}"),
                prefs.get("routines", "{}"),
                prefs.get("created_at", now),
                now,
            ),
        )
    conn.close()
    return get_user_preferences(u_id, db_path=db_path)
