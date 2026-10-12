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

            CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id);
            CREATE INDEX IF NOT EXISTS idx_messages_created ON messages(created_at ASC);
            CREATE INDEX IF NOT EXISTS idx_sessions_updated ON sessions(updated_at DESC);
            CREATE INDEX IF NOT EXISTS idx_sessions_phone ON sessions(customer_phone);
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
