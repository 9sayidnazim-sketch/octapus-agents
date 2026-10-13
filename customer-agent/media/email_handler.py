"""Email Delivery Module using Resend API.

Supports:
1. Dispatching transactional and notification emails via POST https://api.resend.com/emails
2. Checking email delivery status via GET https://api.resend.com/emails/{email_id}
3. HTML and plain text template generation for Octapus proposals, receipts, and confirmations
"""
from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import httpx

logger = logging.getLogger("octapus.media.email")

BASE_DIR = Path(__file__).resolve().parent.parent
for env_path in (BASE_DIR / ".env", BASE_DIR.parent / ".env"):
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip("'\""))

DEFAULT_RESEND_API_URL = "https://api.resend.com"
DEFAULT_RESEND_FROM = "Octapus AI <onboarding@resend.dev>"
DEFAULT_TIMEOUT = 15.0

EMAIL_REGEX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class EmailHandler:
    def __init__(
        self,
        api_key: Optional[str] = None,
        default_from: Optional[str] = None,
        api_url: Optional[str] = None,
        timeout: float = DEFAULT_TIMEOUT,
    ):
        if api_key is not None:
            self.api_key = api_key
        else:
            self.api_key = os.environ.get("RESEND_API_KEY") or os.environ.get("EMAIL_API_KEY") or ""

        self.default_from = (
            default_from
            or os.environ.get("RESEND_FROM")
            or DEFAULT_RESEND_FROM
        )
        self.api_url = (
            api_url
            or os.environ.get("RESEND_API_URL")
            or DEFAULT_RESEND_API_URL
        ).rstrip("/")
        self.timeout = timeout

    @property
    def is_configured(self) -> bool:
        """Check if Resend API key is configured."""
        return bool(self.api_key)

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def _clean_recipient_list(self, recipients: Union[str, List[str]]) -> List[str]:
        if isinstance(recipients, str):
            raw = [r.strip() for r in recipients.split(",") if r.strip()]
        elif isinstance(recipients, list):
            raw = [str(r).strip() for r in recipients if str(r).strip()]
        else:
            raw = []

        valid = []
        for email in raw:
            # Strip display names like "Name <email@domain.com>" if present
            if "<" in email and email.endswith(">"):
                email = email[email.find("<") + 1 : -1].strip()
            if EMAIL_REGEX.match(email):
                valid.append(email)
        return valid

    def send_email(
        self,
        to: Union[str, List[str]],
        subject: str,
        text: Optional[str] = None,
        html: Optional[str] = None,
        from_email: Optional[str] = None,
        reply_to: Optional[str] = None,
        cc: Optional[Union[str, List[str]]] = None,
        bcc: Optional[Union[str, List[str]]] = None,
    ) -> Dict[str, Any]:
        """
        Send an email via Resend API.
        """
        if not self.is_configured:
            return {"status": "error", "message": "Resend API key is not configured"}

        recipients = self._clean_recipient_list(to)
        if not recipients:
            return {"status": "error", "message": f"No valid recipient email address found in: {to}"}

        clean_subject = (subject or "").strip()
        if not clean_subject:
            return {"status": "error", "message": "Email subject cannot be empty"}

        if not text and not html:
            return {"status": "error", "message": "Email must contain text or html body content"}

        # Build clean HTML container if only plain text provided
        final_html = html
        if not final_html and text:
            escaped_text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br>")
            final_html = (
                f'<div style="font-family: Arial, sans-serif; font-size: 15px; color: #1e293b; line-height: 1.6; max-width: 600px; margin: 0 auto; padding: 24px; border: 1px solid #e2e8f0; border-radius: 8px;">'
                f'<div style="font-size: 18px; font-weight: bold; color: #0284c7; margin-bottom: 16px;">Octapus LLC</div>'
                f'<div style="margin-bottom: 24px;">{escaped_text}</div>'
                f'<hr style="border: none; border-top: 1px solid #e2e8f0; margin: 20px 0;">'
                f'<div style="font-size: 12px; color: #64748b;">Octapus LLC • UAE Software & Digital Automation • <a href="https://octapus.ae" style="color: #0284c7;">octapus.ae</a></div>'
                f'</div>'
            )

        payload: Dict[str, Any] = {
            "from": from_email or self.default_from,
            "to": recipients,
            "subject": clean_subject,
        }
        if text:
            payload["text"] = text
        if final_html:
            payload["html"] = final_html
        if reply_to:
            payload["reply_to"] = reply_to

        if cc:
            clean_cc = self._clean_recipient_list(cc)
            if clean_cc:
                payload["cc"] = clean_cc

        if bcc:
            clean_bcc = self._clean_recipient_list(bcc)
            if clean_bcc:
                payload["bcc"] = clean_bcc

        try:
            url = f"{self.api_url}/emails"
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.post(url, json=payload, headers=self._headers())
                if resp.status_code in (200, 201):
                    data = resp.json()
                    logger.info("Resend successfully sent email '%s' to %s (id: %s)", clean_subject, recipients, data.get("id"))
                    return {
                        "status": "success",
                        "id": data.get("id"),
                        "to": recipients,
                        "subject": clean_subject,
                        "data": data,
                    }
                else:
                    logger.warning("Resend email failed HTTP %d: %s", resp.status_code, resp.text[:200])
                    return {
                        "status": "error",
                        "code": resp.status_code,
                        "message": resp.text[:200],
                    }
        except Exception as exc:
            logger.error("Resend email request exception: %s", exc)
            return {"status": "error", "message": str(exc)}

    def get_email_status(self, email_id: str) -> Dict[str, Any]:
        """
        Retrieve email status from Resend.
        """
        if not self.is_configured:
            return {"status": "error", "message": "Resend API key is not configured"}
        if not email_id:
            return {"status": "error", "message": "email_id is required"}

        try:
            url = f"{self.api_url}/emails/{email_id}"
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.get(url, headers=self._headers())
                if resp.status_code == 200:
                    return resp.json()
                return {"status": "error", "code": resp.status_code, "message": resp.text[:200]}
        except Exception as exc:
            logger.error("Error retrieving Resend email %s: %s", email_id, exc)
            return {"status": "error", "message": str(exc)}
