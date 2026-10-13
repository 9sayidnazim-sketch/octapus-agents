"""Reminder Service Layer.

Orchestrates:
1. faresemad/Reminders-API client (Category & Reminder CRUD)
2. Persistent local metadata in SQLite (reminders_metadata & user_preferences)
3. Timezone resolution & UTC scheduling
4. User ownership and authorization verification
5. Follow-up plans, quiet hours, and status tracking (saved -> scheduled -> delivered)
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

from .client import RemindersAPIClient
from .date_parser import ReminderDateParser

logger = logging.getLogger(__name__)

# Configured VIP / Management numbers authorized for automated messaging
AUTHORIZED_VIP_NUMBERS = {"971525919933", "971508621612", "+971525919933", "+971508621612"}


class ReminderService:
    """Business logic for creating, tracking, and modifying reminders."""

    def __init__(self, client: Optional[RemindersAPIClient] = None, db_module: Any = None):
        self.client = client or RemindersAPIClient()
        if db_module:
            self.db = db_module
        else:
            import db as default_db
            self.db = default_db

    def _normalize_phone(self, phone: str) -> str:
        return "".join(c for c in phone if c.isdigit() or c == "+")

    def create_reminder(
        self,
        user_id: str,
        title: str,
        date_str: str,
        time_str: str,
        notes: str = "",
        user_timezone: Optional[str] = None,
        priority: str = "low",
        recurrence: str = "none",
        channel: str = "whatsapp",
        recipient: Optional[str] = None,
        follow_up_enabled: bool = True,
        max_follow_ups: int = 2,
        follow_up_interval_minutes: int = 60,
    ) -> Dict[str, Any]:
        """Create and schedule a reminder.

        Enforces user ownership, creates upstream record in Reminders-API,
        and saves complete scheduling metadata to SQLite.
        """
        target_recipient = recipient or user_id
        # Normalize recipient phone if whatsapp
        if channel == "whatsapp":
            target_recipient = self._normalize_phone(target_recipient)

        # Get user confirmed timezone or default
        user_prefs = self.db.get_user_preferences(user_id)
        tz_name = user_timezone or user_prefs.get("timezone", "Asia/Dubai")

        try:
            tz = ZoneInfo(tz_name)
        except Exception:
            tz = ZoneInfo("Asia/Dubai")
            tz_name = "Asia/Dubai"

        # Calculate exact UTC timestamp
        try:
            # Parse YYYY-MM-DD and HH:MM[:SS]
            parts_d = [int(p) for p in date_str.split("-")]
            parts_t = [int(p) for p in time_str.split(":")]
            local_dt = datetime(
                year=parts_d[0],
                month=parts_d[1],
                day=parts_d[2],
                hour=parts_t[0],
                minute=parts_t[1],
                second=parts_t[2] if len(parts_t) > 2 else 0,
                tzinfo=tz,
            )
            scheduled_at_utc = local_dt.astimezone(timezone.utc).isoformat()
        except Exception as e:
            raise ValueError(f"Invalid date ({date_str}) or time ({time_str}): {e}")

        # Step 1: Create in faresemad/Reminders-API
        # Map user_id to upstream username for ownership enforcement in DRF
        upstream_user = f"user_{self._normalize_phone(user_id)}"
        api_res = self.client.create_reminder(
            title=title,
            notes=notes,
            date=date_str,
            time=time_str,
            priority=priority,
            category_name="General",
            username=upstream_user,
        )

        api_reminder_id = api_res.get("id")
        api_list_id = api_res.get("category_id")

        # Step 2: Save persistent metadata in SQLite
        reminder_uuid = str(uuid.uuid4())
        record = {
            "id": reminder_uuid,
            "api_reminder_id": api_reminder_id,
            "api_list_id": api_list_id,
            "user_id": user_id,
            "title": title.strip(),
            "notes": notes.strip(),
            "date": date_str,
            "time": time_str,
            "priority": priority if priority in ("low", "medium", "high") else "low",
            "timezone": tz_name,
            "scheduled_at_utc": scheduled_at_utc,
            "status": "scheduled",
            "recurrence": recurrence,
            "channel": channel,
            "recipient": target_recipient,
            "follow_up_enabled": follow_up_enabled,
            "max_follow_ups": max_follow_ups,
            "follow_up_count": 0,
            "follow_up_interval_minutes": follow_up_interval_minutes,
            "next_follow_up_at_utc": None,
            "delivery_attempts": 0,
            "last_delivery_error": None,
            "delivered_at": None,
        }

        saved_record = self.db.save_reminder_metadata(record)
        logger.info(f"Successfully scheduled reminder {reminder_uuid} for {user_id} at {scheduled_at_utc}")
        return saved_record

    def create_from_natural_text(
        self,
        user_id: str,
        text: str,
        default_title: Optional[str] = None,
        channel: str = "whatsapp",
        recipient: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Parse casual Malayalam / Manglish / English text and create reminder or prompt for clarification."""
        user_prefs = self.db.get_user_preferences(user_id)
        tz_name = user_prefs.get("timezone", "Asia/Dubai")

        parsed = ReminderDateParser.parse_schedule(text, user_timezone=tz_name)
        if parsed.get("needs_clarification") or not parsed.get("success"):
            return {
                "success": False,
                "needs_clarification": True,
                "clarification_question": parsed.get("clarification_question"),
                "clean_title": parsed.get("clean_title"),
            }

        title = default_title or parsed.get("clean_title") or "Reminder"
        res = self.create_reminder(
            user_id=user_id,
            title=title,
            date_str=parsed["date"],
            time_str=parsed["time"],
            notes=f"Created from request: {text}",
            user_timezone=tz_name,
            channel=channel,
            recipient=recipient or user_id,
        )
        return {
            "success": True,
            "needs_clarification": False,
            "reminder": res,
        }

    def list_reminders(
        self,
        user_id: str,
        status: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """List all reminders owned by the user."""
        return self.db.list_reminders_metadata(user_id=user_id, status=status)

    def get_reminder(self, reminder_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve reminder, strictly enforcing user ownership."""
        rec = self.db.get_reminder_metadata(reminder_id)
        if not rec or rec.get("user_id") != user_id:
            return None
        return rec

    def cancel_reminder(self, reminder_id: str, user_id: str) -> bool:
        """Cancel an existing reminder."""
        rec = self.get_reminder(reminder_id, user_id)
        if not rec:
            return False

        # Delete upstream if api_reminder_id is present
        api_rem_id = rec.get("api_reminder_id")
        api_list_id = rec.get("api_list_id")
        if api_rem_id and api_list_id:
            upstream_user = f"user_{self._normalize_phone(user_id)}"
            try:
                self.client.delete_reminder(api_list_id, api_rem_id, username=upstream_user)
            except Exception as e:
                logger.warning(f"Could not delete upstream reminder {api_rem_id}: {e}")

        # Update local status to cancelled
        return self.db.cancel_reminder_metadata(reminder_id)

    def snooze_reminder(self, reminder_id: str, user_id: str, minutes: int = 15) -> Optional[Dict[str, Any]]:
        """Snooze a reminder by postponing its scheduled UTC time."""
        rec = self.get_reminder(reminder_id, user_id)
        if not rec:
            return None

        tz = ZoneInfo(rec.get("timezone", "Asia/Dubai"))
        new_local = datetime.now(tz) + timedelta(minutes=minutes)
        new_utc = new_local.astimezone(timezone.utc).isoformat()

        self.db.update_reminder_metadata(
            reminder_id,
            {
                "status": "scheduled",
                "scheduled_at_utc": new_utc,
                "date": new_local.strftime("%Y-%m-%d"),
                "time": new_local.strftime("%H:%M:%S"),
            },
        )
        return self.get_reminder(reminder_id, user_id)

    def complete_reminder(self, reminder_id: str, user_id: str) -> bool:
        """Mark a reminder as completed and stop follow-ups."""
        rec = self.get_reminder(reminder_id, user_id)
        if not rec:
            return False
        return self.db.update_reminder_metadata(
            reminder_id,
            {"status": "completed", "follow_up_enabled": 0},
        )

    def stop_follow_up(self, reminder_id: str, user_id: str) -> bool:
        """Stop proactive checking and follow-ups for a reminder."""
        rec = self.get_reminder(reminder_id, user_id)
        if not rec:
            return False
        return self.db.update_reminder_metadata(
            reminder_id,
            {"follow_up_enabled": 0, "status": "completed"},
        )

    def get_user_preferences(self, user_id: str) -> Dict[str, Any]:
        return self.db.get_user_preferences(user_id)

    def save_user_preferences(self, user_id: str, prefs: Dict[str, Any]) -> Dict[str, Any]:
        prefs["user_id"] = user_id
        return self.db.save_user_preferences(prefs)
