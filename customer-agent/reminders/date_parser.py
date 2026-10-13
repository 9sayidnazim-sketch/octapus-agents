"""Date & Time Parser for Malayalam, Manglish, and English Reminder Requests.

Resolves relative dates and times:
- 'nale ravile 10 manikk' -> Tomorrow 10:00 AM local time
- 'innu vaikitt 4-nu' -> Today 16:00 local time
- 'mattanale' -> Day after tomorrow
- Timezone-aware conversion to UTC ISO-8601
- Detects incomplete requests and provides a single, focused clarification question.
"""

from __future__ import annotations

import re
from datetime import datetime, time, timedelta, timezone
from typing import Dict, Optional, Tuple
from zoneinfo import ZoneInfo


class ReminderDateParser:
    """Parses natural language relative and absolute reminder schedules."""

    DEFAULT_TIMEZONE = "Asia/Dubai"

    # Default period mappings when explicit hour is omitted
    PERIOD_DEFAULTS = {
        "morning": (9, 0),     # 09:00 AM
        "noon": (13, 0),       # 01:00 PM
        "afternoon": (14, 0),  # 02:00 PM
        "evening": (17, 0),    # 05:00 PM
        "night": (20, 0),      # 08:00 PM
    }

    @classmethod
    def parse_schedule(
        cls,
        text: str,
        user_timezone: Optional[str] = None,
        reference_time: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """Parse natural language schedule and resolve to exact date, time, and UTC ISO timestamp.

        Returns dict:
        {
            "success": bool,
            "needs_clarification": bool,
            "clarification_question": Optional[str],
            "date": Optional[str],        # YYYY-MM-DD
            "time": Optional[str],        # HH:MM:SS
            "scheduled_at_utc": Optional[str],  # ISO 8601 UTC
            "timezone": str,
            "clean_title": str,           # Task title with timing phrases stripped
        }
        """
        tz_name = user_timezone or cls.DEFAULT_TIMEZONE
        try:
            tz = ZoneInfo(tz_name)
        except Exception:
            tz = ZoneInfo(cls.DEFAULT_TIMEZONE)
            tz_name = cls.DEFAULT_TIMEZONE

        now_local = reference_time.astimezone(tz) if reference_time else datetime.now(tz)
        norm = text.lower().strip()

        # 1. Determine Target Date
        target_date = None
        date_explicit = False

        if any(w in norm for w in ["mattanallu", "mattanale", "mattanall", "day after tomorrow"]):
            target_date = (now_local + timedelta(days=2)).date()
            date_explicit = True
        elif any(w in norm for w in ["nale", "naale", "tomorrow", "tmrw"]):
            target_date = (now_local + timedelta(days=1)).date()
            date_explicit = True
        elif any(w in norm for w in ["innu", "today", "tonight"]):
            target_date = now_local.date()
            date_explicit = True
        else:
            # Check ISO date YYYY-MM-DD or DD-MM-YYYY
            iso_match = re.search(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b", norm)
            if iso_match:
                try:
                    y, m, d = int(iso_match.group(1)), int(iso_match.group(2)), int(iso_match.group(3))
                    target_date = datetime(y, m, d).date()
                    date_explicit = True
                except Exception:
                    pass

        # 2. Determine Period & Hour
        period = None
        if any(w in norm for w in ["ravile", "ravila", "morning", "prabhatham"]):
            period = "morning"
        elif any(w in norm for w in ["uchakku", "uchaykk", "uchaykku", "noon", "afternoon"]):
            period = "noon"
        elif any(w in norm for w in ["vaikitt", "vaikittu", "vaikunneram", "evening", "sandhya"]):
            period = "evening"
        elif any(w in norm for w in ["rathri", "night", "raathri"]):
            period = "night"

        # Look for explicit hour / minutes
        # Matches: "10 manikk", "10:30 am", "10:30", "4 pm", "16:00", "7-nu"
        hour: Optional[int] = None
        minute: int = 0
        has_explicit_time = False

        # Pattern A: 10:30 am / 10:30
        time_colon = re.search(r"\b(\d{1,2}):(\d{2})(?:\s*(am|pm))?\b", norm)
        if time_colon:
            h = int(time_colon.group(1))
            m = int(time_colon.group(2))
            meridiem = time_colon.group(3)
            if meridiem == "pm" and h < 12:
                h += 12
            elif meridiem == "am" and h == 12:
                h = 0
            hour, minute = h, m
            has_explicit_time = True
        else:
            # Pattern B: "10 manikk", "10 mani", "10 am", "4 pm", "7 manik"
            time_match = re.search(r"\b(\d{1,2})(?:\s*(?:manikk|manik|mani|-nu|nu|am|pm))\b", norm)
            if time_match:
                h = int(time_match.group(1))
                # Adjust based on period or am/pm
                if "pm" in norm and h < 12:
                    h += 12
                elif "am" in norm and h == 12:
                    h = 0
                elif period in ("evening", "night") and h <= 12:
                    h = h + 12 if h < 12 else h
                elif period == "noon" and h <= 3:
                    h = h + 12
                hour, minute = h, 0
                has_explicit_time = True

        # If period exists without explicit hour:
        if not has_explicit_time and period:
            # Check if this was just "nale ravile remind cheyy"
            # It's better to default or ask clarification if date was specified without specific hour
            if date_explicit and not has_explicit_time:
                def_h, def_m = cls.PERIOD_DEFAULTS[period]
                hour, minute = def_h, def_m
                has_explicit_time = True

        # Check if date is known but time is completely missing
        if date_explicit and not has_explicit_time:
            return {
                "success": False,
                "needs_clarification": True,
                "clarification_question": "Ravile ethra manikkaanu remind cheyyendath?",
                "date": target_date.strftime("%Y-%m-%d") if target_date else None,
                "time": None,
                "scheduled_at_utc": None,
                "timezone": tz_name,
                "clean_title": cls._extract_title(norm),
            }

        # If date is not explicit but time is: default to today if in future, else tomorrow
        if not target_date and has_explicit_time:
            assert hour is not None
            sched_today = now_local.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if sched_today > now_local:
                target_date = now_local.date()
            else:
                target_date = (now_local + timedelta(days=1)).date()

        # If neither date nor time could be inferred:
        if not target_date or hour is None:
            return {
                "success": False,
                "needs_clarification": True,
                "clarification_question": "Eppozhaanu remind cheyyendath? (e.g. naale ravile 10 manikk)",
                "date": None,
                "time": None,
                "scheduled_at_utc": None,
                "timezone": tz_name,
                "clean_title": cls._extract_title(norm),
            }

        # Construct local scheduled datetime
        target_time = time(hour=hour, minute=minute, second=0)
        scheduled_local = datetime.combine(target_date, target_time, tzinfo=tz)

        # Convert to UTC ISO
        scheduled_utc = scheduled_local.astimezone(timezone.utc)

        return {
            "success": True,
            "needs_clarification": False,
            "clarification_question": None,
            "date": target_date.strftime("%Y-%m-%d"),
            "time": target_time.strftime("%H:%M:%S"),
            "scheduled_at_utc": scheduled_utc.isoformat(),
            "timezone": tz_name,
            "clean_title": cls._extract_title(text),
        }

    @classmethod
    def _extract_title(cls, text: str) -> str:
        """Strip reminder trigger words to get a clean title/task name."""
        t = text.strip()
        # Remove common prefixes/suffixes
        t = re.sub(r"(?i)\b(remind\s*me\s*to|remind\s*me|remind\s*cheyy|remind\s*cheyyu|remind|set\s*reminder\s*for)\b", "", t)
        t = re.sub(r"(?i)\b(nale|naale|tomorrow|innu|today|mattanale|mattanallu)\b", "", t)
        t = re.sub(r"(?i)\b(ravile|ravila|morning|uchakku|uchaykk|vaikitt|vaikunneram|rathri|night)\b", "", t)
        t = re.sub(r"(?i)\b(\d{1,2}:\d{2}(\s*(am|pm))?|\d{1,2}\s*(manikk|manik|mani|-nu|nu|am|pm))\b", "", t)
        t = re.sub(r"(?i)\b(meeting|call|quote|quotation)?\s*(undu|und|aano|aanu|venam)?\b", "", t)
        clean = " ".join(t.split()).strip(" ,.-:")
        return clean or text.strip()
