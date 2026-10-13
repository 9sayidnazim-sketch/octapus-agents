"""Reminders-API Client Layer.

Directly integrates with the https://github.com/faresemad/Reminders-API repository architecture:
- Nested DRF router:
    CategoryViewSet: /list/
    ReminderViewSet: /list/{list_pk}/reminder/
- Models:
    Category: name, color ('red', 'blue', 'green', 'yellow'), auther
    Reminder: auther, title, notes, date, time, priority ('low', 'medium', 'high'), category
- Authentication:
    SessionAuth / HTTP BasicAuth / Token
- In-process MockRemindersBackend:
    Implements the exact DRF endpoints and validation contract for offline resilience and tests.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional
import urllib.request
import urllib.parse
import json

logger = logging.getLogger(__name__)


class MockRemindersBackend:
    """In-process mock implementing the exact schema and endpoints of faresemad/Reminders-API."""

    def __init__(self, default_username: str = "horus_user"):
        self.default_username = default_username
        self.categories: Dict[int, Dict[str, Any]] = {}
        self.reminders: Dict[int, Dict[str, Any]] = {}
        self._cat_id_seq = 1
        self._rem_id_seq = 1
        # Pre-populate default 'General' category
        self.create_category("General", "blue", self.default_username)

    def list_categories(self, username: Optional[str] = None) -> List[Dict[str, Any]]:
        user = username or self.default_username
        return [c for c in self.categories.values() if c.get("auther") == user]

    def create_category(self, name: str, color: str = "blue", username: Optional[str] = None) -> Dict[str, Any]:
        user = username or self.default_username
        cat_id = self._cat_id_seq
        self._cat_id_seq += 1
        rec = {
            "id": cat_id,
            "name": name,
            "color": color,
            "auther": user,
        }
        self.categories[cat_id] = rec
        return rec

    def list_reminders(self, list_pk: int, username: Optional[str] = None) -> List[Dict[str, Any]]:
        user = username or self.default_username
        return [
            r for r in self.reminders.values()
            if r.get("category_id") == list_pk and r.get("auther") == user
        ]

    def create_reminder(
        self,
        list_pk: int,
        title: str,
        notes: str = "",
        date: Optional[str] = None,
        time: Optional[str] = None,
        priority: str = "low",
        username: Optional[str] = None,
    ) -> Dict[str, Any]:
        user = username or self.default_username
        cat = self.categories.get(list_pk)
        if not cat or cat.get("auther") != user:
            raise KeyError(f"Category {list_pk} not found for user {user}")

        rem_id = self._rem_id_seq
        self._rem_id_seq += 1
        rec = {
            "id": rem_id,
            "auther": user,
            "category": cat["name"],
            "category_id": list_pk,
            "title": title[:100],
            "notes": notes,
            "date": date,
            "time": time,
            "priority": priority if priority in ("low", "medium", "high") else "low",
        }
        self.reminders[rem_id] = rec
        return rec

    def get_reminder(self, list_pk: int, reminder_id: int, username: Optional[str] = None) -> Dict[str, Any]:
        user = username or self.default_username
        r = self.reminders.get(reminder_id)
        if not r or r.get("category_id") != list_pk or r.get("auther") != user:
            raise KeyError(f"Reminder {reminder_id} not found in list {list_pk} for user {user}")
        return r

    def update_reminder(
        self,
        list_pk: int,
        reminder_id: int,
        data: Dict[str, Any],
        username: Optional[str] = None,
    ) -> Dict[str, Any]:
        r = self.get_reminder(list_pk, reminder_id, username)
        if "title" in data:
            r["title"] = str(data["title"])[:100]
        if "notes" in data:
            r["notes"] = str(data["notes"])
        if "date" in data:
            r["date"] = data["date"]
        if "time" in data:
            r["time"] = data["time"]
        if "priority" in data and data["priority"] in ("low", "medium", "high"):
            r["priority"] = data["priority"]
        return r

    def delete_reminder(self, list_pk: int, reminder_id: int, username: Optional[str] = None) -> bool:
        r = self.get_reminder(list_pk, reminder_id, username)
        del self.reminders[reminder_id]
        return True


class RemindersAPIClient:
    """Client for faresemad/Reminders-API connecting over HTTP or fallback in-memory mock."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        token: Optional[str] = None,
        use_mock: Optional[bool] = None,
    ):
        self.base_url = (base_url or os.environ.get("REMINDERS_API_URL", "mock")).rstrip("/")
        self.username = username or os.environ.get("REMINDERS_API_USERNAME", "horus")
        self.password = password or os.environ.get("REMINDERS_API_PASSWORD", "horus_secret")
        self.token = token or os.environ.get("REMINDERS_API_TOKEN")

        if use_mock is not None:
            self.use_mock = use_mock
        else:
            self.use_mock = self.base_url.lower() == "mock" or not self.base_url.startswith("http")

        self._mock = MockRemindersBackend(default_username=self.username) if self.use_mock else None

    def _headers(self) -> Dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if self.token:
            headers["Authorization"] = f"Token {self.token}"
        elif self.username and self.password:
            import base64
            cred = base64.b64encode(f"{self.username}:{self.password}".encode()).decode()
            headers["Authorization"] = f"Basic {cred}"
        return headers

    def ensure_category(self, name: str = "General", color: str = "blue", username: Optional[str] = None) -> int:
        """Find or create a category in Reminders-API (route /list/) and return its ID."""
        user = username or self.username
        if self.use_mock:
            cats = self._mock.list_categories(user)
            for c in cats:
                if c.get("name", "").lower() == name.lower():
                    return c["id"]
            new_cat = self._mock.create_category(name=name, color=color, username=user)
            return new_cat["id"]

        url = f"{self.base_url}/list/"
        try:
            req = urllib.request.Request(url, headers=self._headers(), method="GET")
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode())
                if isinstance(data, list):
                    for c in data:
                        if c.get("name", "").lower() == name.lower():
                            return c["id"]
            
            # Create if not found
            post_req = urllib.request.Request(
                url,
                data=json.dumps({"name": name, "color": color}).encode(),
                headers=self._headers(),
                method="POST",
            )
            with urllib.request.urlopen(post_req, timeout=5) as resp:
                created = json.loads(resp.read().decode())
                return created["id"]
        except Exception as e:
            logger.warning(f"Reminders-API unreachable ({e}), falling back to in-memory mock")
            if not self._mock:
                self._mock = MockRemindersBackend(default_username=user)
            self.use_mock = True
            return self.ensure_category(name, color, username)

    def create_reminder(
        self,
        title: str,
        notes: str = "",
        date: Optional[str] = None,
        time: Optional[str] = None,
        priority: str = "low",
        category_name: str = "General",
        category_id: Optional[int] = None,
        username: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a reminder under /list/{list_pk}/reminder/ following Reminders-API DRF viewset."""
        user = username or self.username
        list_pk = category_id or self.ensure_category(category_name, username=user)

        if self.use_mock:
            return self._mock.create_reminder(
                list_pk=list_pk,
                title=title,
                notes=notes,
                date=date,
                time=time,
                priority=priority,
                username=user,
            )

        url = f"{self.base_url}/list/{list_pk}/reminder/"
        payload = {
            "title": title[:100],
            "notes": notes,
            "date": date,
            "time": time,
            "priority": priority if priority in ("low", "medium", "high") else "low",
            "category": list_pk,
        }
        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode(),
                headers=self._headers(),
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                return json.loads(resp.read().decode())
        except Exception as e:
            logger.warning(f"Failed to create reminder via HTTP ({e}), falling back to mock")
            if not self._mock:
                self._mock = MockRemindersBackend(default_username=user)
            self.use_mock = True
            return self.create_reminder(title, notes, date, time, priority, category_name, list_pk, username)

    def get_reminder(self, list_pk: int, reminder_id: int, username: Optional[str] = None) -> Dict[str, Any]:
        user = username or self.username
        if self.use_mock:
            return self._mock.get_reminder(list_pk, reminder_id, user)

        url = f"{self.base_url}/list/{list_pk}/reminder/{reminder_id}/"
        req = urllib.request.Request(url, headers=self._headers(), method="GET")
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read().decode())

    def update_reminder(
        self,
        list_pk: int,
        reminder_id: int,
        data: Dict[str, Any],
        username: Optional[str] = None,
    ) -> Dict[str, Any]:
        user = username or self.username
        if self.use_mock:
            return self._mock.update_reminder(list_pk, reminder_id, data, user)

        url = f"{self.base_url}/list/{list_pk}/reminder/{reminder_id}/"
        req = urllib.request.Request(
            url,
            data=json.dumps(data).encode(),
            headers=self._headers(),
            method="PUT",
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read().decode())

    def delete_reminder(self, list_pk: int, reminder_id: int, username: Optional[str] = None) -> bool:
        user = username or self.username
        if self.use_mock:
            return self._mock.delete_reminder(list_pk, reminder_id, user)

        url = f"{self.base_url}/list/{list_pk}/reminder/{reminder_id}/"
        req = urllib.request.Request(url, headers=self._headers(), method="DELETE")
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status in (200, 204)
