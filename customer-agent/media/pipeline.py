"""Unified Media Pipeline for WhatsApp.

Orchestrates detection, payload logging, immediate media download,
handler dispatch (audio, image, document), error handling with friendly fallbacks,
and automatic temp file cleanup.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional, Tuple, Union

from .audio_handler import AudioHandler
from .detector import detect_message_type, sanitize_payload
from .document_handler import DocumentHandler
from .downloader import MediaDownloader
from .image_handler import ImageHandler

logger = logging.getLogger("octapus.media.pipeline")

FALLBACK_ERROR_MESSAGE = "I couldn't open that file, can you send it again?"


class MediaPipeline:
    def __init__(
        self,
        downloader: Optional[MediaDownloader] = None,
        audio_handler: Optional[AudioHandler] = None,
        image_handler: Optional[ImageHandler] = None,
        document_handler: Optional[DocumentHandler] = None,
    ):
        self.downloader = downloader or MediaDownloader()
        self.audio_handler = audio_handler or AudioHandler()
        self.image_handler = image_handler or ImageHandler()
        self.document_handler = document_handler or DocumentHandler()

    def process_incoming_payload(
        self,
        payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Process any incoming webhook payload.

        Returns a dictionary:
        {
            "status": "success" | "fallback" | "unsupported" | "ignored",
            "type": "text" | "image" | "audio" | "document" | "video" | "sticker" | "unknown",
            "message": str,                 # Prompt string or formatted user inquiry
            "content_blocks": Optional[list], # Anthropic multimodal content blocks (for vision)
            "clean_number": str,
            "error": Optional[str],
            "sanitized_payload": dict,
        }
        """
        sanitized = sanitize_payload(payload)
        msg_type, meta = detect_message_type(payload)

        # Log incoming structure safely
        logger.info(
            "📩 [WhatsApp Detected] type: %s | Payload: %s",
            msg_type,
            json.dumps(sanitized)[:300],
        )

        # Extract sender phone number
        clean_number = self._extract_clean_number(payload)

        # 1. TEXT
        if msg_type == "text":
            text = (meta.get("text") or "").strip()
            return {
                "status": "success",
                "type": "text",
                "message": text,
                "content_blocks": None,
                "clean_number": clean_number,
                "error": None,
                "sanitized_payload": sanitized,
            }

        # 2. VIDEO OR STICKER
        if msg_type in ("video", "sticker"):
            caption = meta.get("caption", "")
            return {
                "status": "unsupported",
                "type": msg_type,
                "message": (
                    f"I received your {msg_type}! Currently I understand text, voice notes, photos, and PDF/Word documents. "
                    + (f"Regarding your note '{caption}': How can I assist you with Octapus services?" if caption else "How can I assist you?")
                ),
                "content_blocks": None,
                "clean_number": clean_number,
                "error": None,
                "sanitized_payload": sanitized,
            }

        if msg_type not in ("image", "audio", "document"):
            return {
                "status": "ignored",
                "type": msg_type,
                "message": "",
                "content_blocks": None,
                "clean_number": clean_number,
                "error": None,
                "sanitized_payload": sanitized,
            }

        # 3. DOWNLOAD & DISPATCH MEDIA (IMAGE, AUDIO, DOCUMENT)
        temp_path: Optional[Path] = None
        try:
            content_bytes, temp_path, mimetype = self.downloader.download_media(
                media_type=msg_type,
                metadata=meta,
                raw_message_wrapper=payload,
            )

            # A. AUDIO / VOICE NOTE
            if msg_type == "audio":
                transcript = self.audio_handler.transcribe_audio(temp_path, mimetype=mimetype)
                return {
                    "status": "success",
                    "type": "audio",
                    "message": transcript,
                    "content_blocks": None,
                    "clean_number": clean_number,
                    "error": None,
                    "sanitized_payload": sanitized,
                }

            # B. IMAGE
            elif msg_type == "image":
                caption = meta.get("caption", "")
                img_result = self.image_handler.process_image(
                    image_bytes=content_bytes,
                    mimetype=mimetype,
                    caption=caption,
                )
                return {
                    "status": "success",
                    "type": "image",
                    "message": img_result["caption"],
                    "content_blocks": img_result["content_blocks"],
                    "clean_number": clean_number,
                    "error": None,
                    "sanitized_payload": sanitized,
                }

            # C. DOCUMENT
            elif msg_type == "document":
                filename = meta.get("filename", "document.pdf")
                caption = meta.get("caption", "")
                doc_text = self.document_handler.extract_text(
                    content_bytes=content_bytes,
                    filename=filename,
                    mimetype=mimetype,
                    caption=caption,
                )
                return {
                    "status": "success",
                    "type": "document",
                    "message": doc_text,
                    "content_blocks": None,
                    "clean_number": clean_number,
                    "error": None,
                    "sanitized_payload": sanitized,
                }

        except Exception as exc:
            logger.error("❌ Media processing error for %s (%s): %s", clean_number, msg_type, exc)
            return {
                "status": "fallback",
                "type": msg_type,
                "message": FALLBACK_ERROR_MESSAGE,
                "content_blocks": None,
                "clean_number": clean_number,
                "error": str(exc),
                "sanitized_payload": sanitized,
            }
        finally:
            if temp_path:
                self.downloader.cleanup_temp_file(temp_path)

        return {
            "status": "fallback",
            "type": msg_type,
            "message": FALLBACK_ERROR_MESSAGE,
            "content_blocks": None,
            "clean_number": clean_number,
            "error": "Unhandled media state",
            "sanitized_payload": sanitized,
        }

    @staticmethod
    def _extract_clean_number(payload: Dict[str, Any]) -> str:
        data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
        info = data.get("Info") or data.get("info") or {}
        raw = (
            info.get("Sender")
            or info.get("Chat")
            or payload.get("from")
            or payload.get("number")
            or payload.get("sender")
            or ""
        )
        clean = str(raw).split("@")[0].split(":")[0]
        digits = "".join(c for c in clean if c.isdigit())
        if digits.startswith("05") and len(digits) == 10:
            digits = "971" + digits[1:]
        return digits
