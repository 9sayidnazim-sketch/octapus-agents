"""Message Type Detector and Payload Sanitizer for WhatsApp messages.

Detects message types: text, image, audio (ptt / voice note), video, document, sticker.
Sanitizes raw payloads by redacting sensitive tokens and credentials before logging.
"""
from __future__ import annotations

import copy
import logging
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger("octapus.media.detector")

# Keys that may contain secrets in webhook payloads
SENSITIVE_KEYS = {
    "apikey",
    "api_key",
    "token",
    "secret",
    "password",
    "authorization",
    "auth",
    "key",
    "mediakey",
    "media_key",
}


def sanitize_payload(obj: Any) -> Any:
    """
    Recursively redact sensitive tokens, API keys, and auth headers from payload dictionaries.
    Returns a safe copy for logging and diagnostics.
    """
    if isinstance(obj, dict):
        sanitized = {}
        for k, v in obj.items():
            k_lower = str(k).lower()
            if any(s in k_lower for s in SENSITIVE_KEYS):
                if isinstance(v, str) and len(v) > 8:
                    sanitized[k] = f"{v[:4]}...[REDACTED]"
                else:
                    sanitized[k] = "[REDACTED]"
            else:
                sanitized[k] = sanitize_payload(v)
        return sanitized
    elif isinstance(obj, list):
        return [sanitize_payload(item) for item in obj]
    return obj


def detect_message_type(payload: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
    """
    Detect the WhatsApp message type from the incoming payload.

    Supported types:
    - "text": standard conversation or extendedTextMessage
    - "image": imageMessage
    - "audio": audioMessage (voice note / ptt)
    - "video": videoMessage
    - "document": documentMessage
    - "sticker": stickerMessage
    - "unknown": unrecognized media or unsupported event

    Returns (message_type, metadata_dict) where metadata_dict contains
    type-specific details (mimetype, caption, filename, is_ptt, url, etc.).
    """
    if not isinstance(payload, dict):
        return "unknown", {}

    # Orbit/Evolution wraps inside data.Message or message
    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    msg = data.get("Message") or data.get("message") or {}

    if not isinstance(msg, dict):
        # Top-level fallback
        msg = payload

    # 1. Image
    image_msg = msg.get("imageMessage")
    if image_msg and isinstance(image_msg, dict):
        return "image", {
            "mimetype": image_msg.get("mimetype", "image/jpeg"),
            "caption": image_msg.get("caption", "").strip(),
            "url": image_msg.get("url", ""),
            "file_length": image_msg.get("fileLength", 0),
            "media_key": image_msg.get("mediaKey", ""),
            "direct_path": image_msg.get("directPath", ""),
            "raw_message": image_msg,
        }

    # 2. Audio / Voice Note (PTT)
    audio_msg = msg.get("audioMessage")
    if audio_msg and isinstance(audio_msg, dict):
        is_ptt = bool(audio_msg.get("ptt", False))
        return "audio", {
            "mimetype": audio_msg.get("mimetype", "audio/ogg; codecs=opus"),
            "is_ptt": is_ptt,
            "seconds": audio_msg.get("seconds", 0),
            "url": audio_msg.get("url", ""),
            "file_length": audio_msg.get("fileLength", 0),
            "media_key": audio_msg.get("mediaKey", ""),
            "direct_path": audio_msg.get("directPath", ""),
            "raw_message": audio_msg,
        }

    # 3. Document
    doc_msg = msg.get("documentMessage")
    if doc_msg and isinstance(doc_msg, dict):
        filename = doc_msg.get("fileName") or doc_msg.get("title") or "document"
        return "document", {
            "mimetype": doc_msg.get("mimetype", "application/octet-stream"),
            "filename": filename,
            "caption": doc_msg.get("caption", "").strip(),
            "page_count": doc_msg.get("pageCount", 0),
            "url": doc_msg.get("url", ""),
            "file_length": doc_msg.get("fileLength", 0),
            "media_key": doc_msg.get("mediaKey", ""),
            "direct_path": doc_msg.get("directPath", ""),
            "raw_message": doc_msg,
        }

    # 4. Video
    video_msg = msg.get("videoMessage")
    if video_msg and isinstance(video_msg, dict):
        return "video", {
            "mimetype": video_msg.get("mimetype", "video/mp4"),
            "caption": video_msg.get("caption", "").strip(),
            "seconds": video_msg.get("seconds", 0),
            "url": video_msg.get("url", ""),
            "raw_message": video_msg,
        }

    # 5. Sticker
    sticker_msg = msg.get("stickerMessage")
    if sticker_msg and isinstance(sticker_msg, dict):
        return "sticker", {
            "mimetype": sticker_msg.get("mimetype", "image/webp"),
            "url": sticker_msg.get("url", ""),
            "raw_message": sticker_msg,
        }

    # 6. Text
    if "conversation" in msg and isinstance(msg["conversation"], str):
        return "text", {"text": msg["conversation"]}
    if "extendedTextMessage" in msg and isinstance(msg["extendedTextMessage"], dict):
        return "text", {"text": msg["extendedTextMessage"].get("text", "")}
    if "text" in payload and isinstance(payload["text"], str):
        return "text", {"text": payload["text"]}

    return "unknown", {}
