"""WhatsApp Outgoing Messaging API & Webhook Pipeline.

Provides the canonical sendMessage(number, text) function and incoming webhook pipeline.
SECURITY: WA_API_KEY is never logged, exposed to frontend, or stored in the prompt/database.
"""
from __future__ import annotations

import logging
import os
import re
import time
from typing import Any, Dict, Optional
from pathlib import Path

import httpx

logger = logging.getLogger("octapus.messaging")

# Load environment configuration if not already set
_BASE_DIR = Path(__file__).resolve().parent
for _env_path in (_BASE_DIR / ".env", _BASE_DIR.parent / ".env"):
    if _env_path.exists():
        for _line in _env_path.read_text(encoding="utf-8").splitlines():
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _v = _line.split("=", 1)
                _k_strip = _k.strip()
                if _k_strip not in os.environ:
                    os.environ[_k_strip] = _v.strip().strip("'\"")



def normalize_phone_number(number: str) -> str:
    """
    Validate and normalize phone numbers into international format without leading '+' or '00'.
    - Handles UAE standard '05xxxxxxxx' -> '9715xxxxxxxx'.
    - Removes non-numeric symbols (+, -, spaces, parentheses).
    - Enforces international E.164 length (8 to 15 digits).
    """
    if not number or not isinstance(number, str):
        raise ValueError("Phone number must be a non-empty string.")

    # Remove all non-digits
    cleaned = re.sub(r"[^\d]", "", number.strip())

    # Handle leading double zeros
    if cleaned.startswith("00"):
        cleaned = cleaned[2:]

    # Handle local UAE mobile prefix 05... (10 digits) -> 9715...
    if cleaned.startswith("05") and len(cleaned) == 10:
        cleaned = "971" + cleaned[1:]

    # International phone validation: 8 to 15 digits
    if len(cleaned) < 8 or len(cleaned) > 15:
        raise ValueError(
            f"Invalid phone number length ({len(cleaned)} digits). "
            "Phone numbers must have 8-15 digits including country code."
        )

    return cleaned


def sendMessage(number: str, text: str, max_retries: int = 3) -> Dict[str, Any]:
    """
    Single unified function for all agent replies sent via WhatsApp API.

    Specification:
    - POST to URL in env var WA_API_URL
    - headers: 'apikey': env var WA_API_KEY, 'Content-Type': 'application/json'
    - body: {'number': '<number with country code>', 'text': '<message>'}
    - Validate and normalize phone format
    - Retries and error handling
    - Safe logging (WA_API_KEY is never logged or exposed)
    """
    if not text or not str(text).strip():
        raise ValueError("Message text cannot be empty.")

    clean_text = str(text).strip()
    normalized_number = normalize_phone_number(number)

    api_url = os.environ.get("WA_API_URL", "").strip().strip("'\"")
    api_key = os.environ.get("WA_API_KEY", "").strip().strip("'\"")

    # If WA_API_URL is not set, log warning safely and return dry-run
    if not api_url:
        logger.warning(
            "WA_API_URL is not set in environment. Message to %s queued in dry-run mode.",
            normalized_number,
        )
        return {
            "status": "dry_run",
            "number": normalized_number,
            "text": clean_text,
            "message": "WA_API_URL is not configured. Message simulated in dry-run mode.",
        }

    payload = {
        "number": normalized_number,
        "text": clean_text,
    }

    headers = {
        "apikey": api_key,
        "Content-Type": "application/json",
    }

    attempt = 0
    last_error: Optional[str] = None

    while attempt < max_retries:
        attempt += 1
        try:
            with httpx.Client(timeout=15.0) as client:
                response = client.post(api_url, json=payload, headers=headers)

                if response.status_code in (200, 201, 202):
                    logger.info("Successfully delivered WhatsApp message to %s", normalized_number)
                    try:
                        resp_data = response.json()
                    except Exception:
                        resp_data = {"raw": response.text}
                    return {
                        "status": "sent",
                        "number": normalized_number,
                        "status_code": response.status_code,
                        "response": resp_data,
                    }
                else:
                    last_error = f"HTTP {response.status_code}: {response.text[:150]}"
                    logger.error(
                        "WhatsApp delivery to %s failed (attempt %d/%d): status %d",
                        normalized_number,
                        attempt,
                        max_retries,
                        response.status_code,
                    )
        except Exception as exc:
            last_error = str(exc)
            logger.error(
                "WhatsApp network error to %s (attempt %d/%d): %s",
                normalized_number,
                attempt,
                max_retries,
                last_error,
            )

        if attempt < max_retries:
            time.sleep(0.5 * (2 ** (attempt - 1)))  # Exponential backoff: 0.5s, 1.0s

    logger.critical(
        "Failed to deliver message to %s after %d attempts. Error: %s",
        normalized_number,
        max_retries,
        last_error,
    )
    return {
        "status": "failed",
        "number": normalized_number,
        "error": last_error,
        "attempts": attempt,
    }
