from __future__ import annotations

import datetime
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
import urllib.request
import urllib.error
import json

from .models import SendResult
from .validator import RecipientValidator

logger = logging.getLogger("octapus.campaigns.gateway")

BASE_DIR = Path(__file__).resolve().parent.parent
for env_path in (BASE_DIR / ".env", BASE_DIR.parent / ".env"):
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip("'\""))



class WhatsAppGateway:
    """Authorized WhatsApp Gateway client interfacing with the connected Orbit Gateway service."""

    def __init__(
        self,
        api_url: Optional[str] = None,
        instance_token: Optional[str] = None,
        admin_key: Optional[str] = None,
    ):
        self.api_url = (
            api_url
            or os.environ.get("ORBIT_API_URL")
            or os.environ.get("GATEWAY_URL")
            or "http://localhost:8098"
        ).rstrip("/")
        self.instance_token = (
            instance_token
            or os.environ.get("ORBIT_INSTANCE_TOKEN")
            or os.environ.get("GATEWAY_API_KEY")
            or os.environ.get("WA_API_KEY")
            or ""
        )
        self.admin_key = (
            admin_key
            or os.environ.get("ORBIT_GLOBAL_API_KEY")
            or os.environ.get("ORBIT_ADMIN_KEY")
            or ""
        )
        self._cached_active_token: Optional[str] = None
        self._last_token_check: float = 0.0

    def get_active_token(self) -> str:
        """Resolve the currently connected WhatsApp instance token from the gateway."""
        now = time.time()
        if self._cached_active_token and (now - self._last_token_check < 30):
            return self._cached_active_token

        if not self.admin_key:
            return self.instance_token

        try:
            url = f"{self.api_url}/instance/all"
            req = urllib.request.Request(
                url,
                headers={"apikey": self.admin_key, "User-Agent": "HorusAI-CampaignManager/1.0"},
                method="GET",
            )
            with urllib.request.urlopen(req, timeout=3) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode("utf-8"))
                    instances = data.get("data") or []
                    for inst in instances:
                        if inst.get("connected") is True and inst.get("token"):
                            self._cached_active_token = inst.get("token")
                            self._last_token_check = now
                            return self._cached_active_token
        except Exception as e:
            logger.debug("Failed checking active token from gateway: %s", e)

        return self.instance_token

    def check_connection(self) -> Dict[str, Any]:
        """Check the health and authorization status of the WhatsApp gateway."""
        token = self.get_active_token()
        gateway_online = False
        connected_phone = None
        instance_id = os.environ.get("ORBIT_INSTANCE_ID") or None

        try:
            url = f"{self.api_url}/instance/all" if self.admin_key else f"{self.api_url}/health"
            headers = {"apikey": self.admin_key} if self.admin_key else {}
            req = urllib.request.Request(url, headers=headers, method="GET")
            with urllib.request.urlopen(req, timeout=3) as resp:
                if resp.status in (200, 204):
                    gateway_online = True
                    if self.admin_key:
                        data = json.loads(resp.read().decode("utf-8"))
                        instances = data.get("data") or []
                        for inst in instances:
                            if inst.get("connected") is True:
                                connected_phone = inst.get("phone") or inst.get("ownerJid")
                                instance_id = inst.get("instanceId") or inst.get("id") or instance_id
                                break
        except Exception as e:
            logger.warning("Gateway check error: %s", e)

        return {
            "gateway_url": self.api_url,
            "is_online": gateway_online,
            "token_configured": bool(token),
            "connected_phone": connected_phone or os.environ.get("ORBIT_PHONE_NUMBER"),
            "instance_id": instance_id,
            "method": "Orbit WhatsApp REST Gateway (Authorized Instance)",
        }

    def send_message(self, recipient_number: str, message_text: str) -> SendResult:
        """
        Dispatches an individual WhatsApp message to the authorized gateway.
        Strictly adheres to safety rules:
        - Evaluates response code and confirms delivery with the gateway.
        - Identifies rate limiting (429) and account restriction/auth failures (401/403).
        - Records timestamp, latency, status code, and detailed error messages.
        """
        now_ts = datetime.datetime.now(datetime.timezone.utc).isoformat()
        start_time = time.time()
        is_group = recipient_number.endswith("@g.us")
        if is_group:
            clean_num = recipient_number
            target_phone = recipient_number
        else:
            recipient = RecipientValidator.validate_and_format(recipient_number)
            clean_num = recipient.clean_number
            target_phone = recipient.phone_number
            if not recipient.is_valid or not clean_num:
                return SendResult(
                    success=False,
                    recipient=recipient_number,
                    clean_number=clean_num,
                    timestamp=now_ts,
                    status="failed",
                    error_details=f"Invalid recipient phone format: {recipient.validation_error}",
                )

        token = self.get_active_token()
        if not token:
            return SendResult(
                success=False,
                recipient=target_phone,
                clean_number=clean_num,
                timestamp=now_ts,
                status="failed",
                error_details="No authorized WhatsApp instance token configured in environment.",
                is_restricted=True,
            )

        endpoint = f"{self.api_url}/send/text"
        payload = json.dumps({"number": clean_num, "text": message_text}).encode("utf-8")
        headers = {
            "apikey": token,
            "Content-Type": "application/json",
            "User-Agent": "HorusAI-CampaignManager/1.0",
        }

        try:
            req = urllib.request.Request(endpoint, data=payload, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=10) as resp:
                latency = round((time.time() - start_time) * 1000, 2)
                resp_body = resp.read().decode("utf-8")
                status_code = resp.status

                if status_code in (200, 201):
                    msg_id = None
                    try:
                        resp_json = json.loads(resp_body)
                        msg_id = (
                            resp_json.get("key", {}).get("id")
                            or resp_json.get("id")
                            or resp_json.get("messageId")
                        )
                    except Exception:
                        pass

                    return SendResult(
                        success=True,
                        recipient=target_phone,
                        clean_number=clean_num,
                        timestamp=now_ts,
                        status="delivered",
                        status_code=status_code,
                        message_id=msg_id,
                        latency_ms=latency,
                    )
                else:
                    return SendResult(
                        success=False,
                        recipient=target_phone,
                        clean_number=clean_num,
                        timestamp=now_ts,
                        status="failed",
                        status_code=status_code,
                        error_details=f"Gateway responded with unexpected HTTP {status_code}: {resp_body[:200]}",
                        latency_ms=latency,
                    )

        except urllib.error.HTTPError as he:
            latency = round((time.time() - start_time) * 1000, 2)
            err_body = he.read().decode("utf-8", errors="replace")
            is_429 = he.code == 429
            is_restr = (
                he.code in (401, 403)
                or "banned" in err_body.lower()
                or "restricted" in err_body.lower()
            )
            return SendResult(
                success=False,
                recipient=target_phone,
                clean_number=clean_num,
                timestamp=now_ts,
                status="failed",
                status_code=he.code,
                error_details=f"HTTP {he.code}: {err_body[:300]}",
                is_rate_limited=is_429,
                is_restricted=is_restr,
                latency_ms=latency,
            )

        except urllib.error.URLError as ue:
            latency = round((time.time() - start_time) * 1000, 2)
            return SendResult(
                success=False,
                recipient=target_phone,
                clean_number=clean_num,
                timestamp=now_ts,
                status="failed",
                error_details=f"Network/Gateway connection error: {ue.reason}",
                latency_ms=latency,
            )

        except Exception as e:
            latency = round((time.time() - start_time) * 1000, 2)
            return SendResult(
                success=False,
                recipient=target_phone,
                clean_number=clean_num,
                timestamp=now_ts,
                status="failed",
                error_details=f"Unexpected error: {str(e)}",
                latency_ms=latency,
            )
