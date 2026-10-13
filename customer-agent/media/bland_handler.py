"""Bland.ai Conversational Voice Agent Calling Integration.

Provides autonomous AI phone calling capabilities:
1. Outbound phone calls via POST https://api.bland.ai/v1/calls
2. Call status and transcript monitoring via GET https://api.bland.ai/v1/calls/{call_id}
3. Account / balance / concurrency inspection via GET https://api.bland.ai/v1/me
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger("octapus.media.bland")

BASE_DIR = Path(__file__).resolve().parent.parent
for env_path in (BASE_DIR / ".env", BASE_DIR.parent / ".env"):
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip("'\""))

DEFAULT_BLAND_API_URL = "https://api.bland.ai/v1"
DEFAULT_BLAND_VOICE = "maya"
DEFAULT_TIMEOUT = 15.0


class BlandHandler:
    def __init__(
        self,
        api_key: Optional[str] = None,
        api_url: Optional[str] = None,
        default_voice: Optional[str] = None,
        default_agent_id: Optional[str] = None,
        default_agent_version: Optional[str] = None,
        timeout: float = DEFAULT_TIMEOUT,
    ):
        if api_key is not None:
            self.api_key = api_key
        else:
            self.api_key = os.environ.get("BLAND_API_KEY") or os.environ.get("BLAND_AI_API_KEY") or ""

        self.api_url = (
            api_url
            or os.environ.get("BLAND_API_URL")
            or DEFAULT_BLAND_API_URL
        ).rstrip("/")
        self.default_voice = (
            default_voice
            or os.environ.get("BLAND_DEFAULT_VOICE")
            or DEFAULT_BLAND_VOICE
        )
        if default_agent_id is not None:
            self.default_agent_id = default_agent_id
        else:
            self.default_agent_id = (
                os.environ.get("BLAND_AGENT_ID")
                or os.environ.get("BLAND_DEFAULT_AGENT_ID")
                or ""
            )

        if default_agent_version is not None:
            self.default_agent_version = default_agent_version
        else:
            self.default_agent_version = (
                os.environ.get("BLAND_AGENT_VERSION")
                or os.environ.get("BLAND_DEFAULT_AGENT_VERSION")
                or ""
            )
        self.timeout = timeout

    @property
    def is_configured(self) -> bool:
        """Check if Bland.ai authorization key is configured."""
        return bool(self.api_key)

    def _headers(self) -> Dict[str, str]:
        return {
            "authorization": self.api_key,
            "Content-Type": "application/json",
        }

    def _clean_phone(self, phone: str) -> str:
        """Normalize phone number to international E.164 format."""
        raw = (phone or "").strip()
        digits = "".join(ch for ch in raw if ch.isdigit() or ch == "+")
        if not digits:
            return ""
        if not digits.startswith("+"):
            digits = "+" + digits
        return digits

    def send_call(
        self,
        phone_number: str,
        task: Optional[str] = None,
        agent_id: Optional[str] = None,
        agent_version: Optional[str] = None,
        first_sentence: Optional[str] = None,
        language: str = "en",
        voice: Optional[str] = None,
        wait_for_greeting: bool = True,
        record: bool = True,
        max_duration: int = 10,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Initiate an outbound conversational AI phone call via Bland.ai.
        Supports both task prompt-driven calls and pre-configured agent_id / agent_version calls.
        """
        if not self.is_configured:
            return {"status": "error", "message": "Bland.ai API key is not configured"}

        clean_phone = self._clean_phone(phone_number)
        if not clean_phone or len(clean_phone) < 8:
            return {"status": "error", "message": f"Invalid phone number: {phone_number}"}

        target_agent_id = agent_id or self.default_agent_id
        target_agent_version = agent_version or self.default_agent_version

        if not target_agent_id and (not task or not task.strip()):
            return {"status": "error", "message": "Call task prompt or agent_id cannot be empty"}

        payload: Dict[str, Any] = {
            "phone_number": clean_phone,
            "language": language or "en",
            "voice": voice or self.default_voice,
            "wait_for_greeting": wait_for_greeting,
            "record": record,
            "max_duration": max_duration,
        }

        if task and task.strip():
            payload["task"] = task.strip()

        if target_agent_id:
            payload["agent_id"] = target_agent_id
        if target_agent_version:
            payload["agent_version"] = target_agent_version

        if first_sentence and first_sentence.strip():
            payload["first_sentence"] = first_sentence.strip()

        if metadata:
            payload["metadata"] = metadata

        try:
            url = f"{self.api_url}/calls"
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.post(url, json=payload, headers=self._headers())
                if resp.status_code in (200, 201):
                    data = resp.json()
                    logger.info("Bland.ai initiated call to %s (call_id: %s, agent_id: %s)", clean_phone, data.get("call_id"), target_agent_id or "default")
                    return {"status": "success", "call_id": data.get("call_id"), "data": data}
                else:
                    logger.warning("Bland.ai call initiation failed HTTP %d: %s", resp.status_code, resp.text[:200])
                    return {
                        "status": "error",
                        "code": resp.status_code,
                        "message": resp.text[:200],
                    }
        except Exception as exc:
            logger.error("Bland.ai request exception for %s: %s", clean_phone, exc)
            return {"status": "error", "message": str(exc)}

    def get_agent_details(self, agent_id: Optional[str] = None) -> Dict[str, Any]:
        """Fetch details of a configured Bland.ai agent."""
        if not self.is_configured:
            return {"status": "error", "message": "Bland.ai API key is not configured"}
        target_id = agent_id or self.default_agent_id
        if not target_id:
            return {"status": "error", "message": "agent_id is required"}
        try:
            url = f"{self.api_url}/agents/{target_id}"
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.get(url, headers=self._headers())
                if resp.status_code == 200:
                    return {"status": "success", "data": resp.json()}
                return {"status": "error", "code": resp.status_code, "message": resp.text[:200]}
        except Exception as exc:
            logger.error("Error retrieving Bland.ai agent %s: %s", target_id, exc)
            return {"status": "error", "message": str(exc)}

    def get_call_details(self, call_id: str) -> Dict[str, Any]:
        """
        Retrieve call status, transcript, and audio recording URL for a specific call.
        """
        if not self.is_configured:
            return {"status": "error", "message": "Bland.ai API key is not configured"}
        if not call_id:
            return {"status": "error", "message": "call_id is required"}

        try:
            url = f"{self.api_url}/calls/{call_id}"
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.get(url, headers=self._headers())
                if resp.status_code == 200:
                    return resp.json()
                return {"status": "error", "code": resp.status_code, "message": resp.text[:200]}
        except Exception as exc:
            logger.error("Error retrieving Bland.ai call %s: %s", call_id, exc)
            return {"status": "error", "message": str(exc)}
    def download_recording(self, call_id: str, dest_dir: Optional[Path] = None) -> Optional[Path]:
        """Fetch and cache call audio recording (.wav) using Bland API credentials."""
        if not self.is_configured or not call_id:
            return None
        target_dir = dest_dir or (BASE_DIR / "media" / "recordings")
        target_dir.mkdir(parents=True, exist_ok=True)
        target_file = target_dir / f"{call_id}.wav"
        if target_file.exists() and target_file.stat().st_size > 1000:
            return target_file
        try:
            url = f"{self.api_url}/recordings/{call_id}"
            with httpx.Client(timeout=30.0) as client:
                resp = client.get(url, headers=self._headers(), follow_redirects=True)
                if resp.status_code == 200 and len(resp.content) > 100:
                    target_file.write_bytes(resp.content)
                    return target_file
                logger.warning("Bland.ai recording fetch failed HTTP %d for %s", resp.status_code, call_id)
        except Exception as exc:
            logger.error("Error downloading Bland.ai recording %s: %s", call_id, exc)
        return None

    def list_calls(self, limit: int = 20) -> List[Dict[str, Any]]:
        """List recent calls made through this Bland.ai account."""
        if not self.is_configured:
            return []
        try:
            url = f"{self.api_url}/calls"
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.get(url, headers=self._headers())
                if resp.status_code == 200:
                    data = resp.json()
                    return data.get("calls", [])
        except Exception as exc:
            logger.error("Error listing Bland.ai calls: %s", exc)
        return []

    def get_account_info(self) -> Dict[str, Any]:
        """Fetch account status, balance, and concurrency information."""
        if not self.is_configured:
            return {"status": "unconfigured"}
        try:
            url = f"{self.api_url}/me"
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.get(url, headers=self._headers())
                if resp.status_code == 200:
                    return resp.json()
                return {"status": "error", "code": resp.status_code, "message": resp.text[:200]}
        except Exception as exc:
            logger.error("Error checking Bland.ai account info: %s", exc)
            return {"status": "error", "message": str(exc)}
