"""Media Downloader for WhatsApp attachments.

Downloads images, voice notes, and documents immediately upon receipt.
Supports:
1. Orbit / Evolution Gateway download endpoint: POST /message/downloadmedia
2. Direct authenticated media URLs with 'apikey' header
3. Embedded base64 payloads

Enforces maximum file size limit, timeouts, retries, and temporary file lifecycle.
"""
from __future__ import annotations

import base64
import logging
import os
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import httpx

logger = logging.getLogger("octapus.media.downloader")

DEFAULT_MAX_MEDIA_BYTES = 25 * 1024 * 1024  # 25MB limit
DEFAULT_DOWNLOAD_TIMEOUT = 10.0  # seconds


class MediaDownloader:
    def __init__(
        self,
        gateway_url: Optional[str] = None,
        api_key: Optional[str] = None,
        max_bytes: Optional[int] = None,
        timeout: float = DEFAULT_DOWNLOAD_TIMEOUT,
    ):
        self.gateway_url = (gateway_url or os.environ.get("ORBIT_API_URL") or os.environ.get("GATEWAY_URL") or "http://localhost:8098").rstrip("/")
        self.api_key = api_key or os.environ.get("ORBIT_INSTANCE_TOKEN") or os.environ.get("GATEWAY_API_KEY") or os.environ.get("WA_API_KEY") or ""
        self.max_bytes = max_bytes or int(os.environ.get("MAX_MEDIA_BYTES", DEFAULT_MAX_MEDIA_BYTES))
        self.timeout = timeout

    def download_media(
        self,
        media_type: str,
        metadata: Dict[str, Any],
        raw_message_wrapper: Optional[Dict[str, Any]] = None,
        max_retries: int = 3,
    ) -> Tuple[bytes, Path, str]:
        """
        Download media payload and return (content_bytes, temp_file_path, mimetype).
        Raises ValueError or IOError if download fails or exceeds size limit.
        """
        raw_message = metadata.get("raw_message", {})
        mimetype = metadata.get("mimetype", "application/octet-stream")
        url = metadata.get("url", "")

        content_bytes: Optional[bytes] = None
        last_error: Optional[str] = None

        # 1. Check if payload already contains base64 data
        if "data" in metadata and isinstance(metadata["data"], str):
            try:
                content_bytes = base64.b64decode(metadata["data"])
            except Exception as e:
                logger.debug("Failed to decode base64 from metadata['data']: %s", e)

        if not content_bytes and "base64" in metadata and isinstance(metadata["base64"], str):
            try:
                content_bytes = base64.b64decode(metadata["base64"])
            except Exception as e:
                logger.debug("Failed to decode base64 from metadata['base64']: %s", e)

        # 2. Try Orbit downloadmedia endpoint if gateway URL is available
        if not content_bytes and self.gateway_url and raw_message:
            download_url = f"{self.gateway_url}/message/downloadmedia"
            headers = {
                "apikey": self.api_key,
                "Content-Type": "application/json",
            }
            # Orbit expects {"message": {"imageMessage": ...}} or {"message": raw_message}
            # Wrap based on media_type
            type_wrapper_key = f"{media_type}Message"
            if type_wrapper_key not in raw_message:
                payload = {"message": {type_wrapper_key: raw_message}}
            else:
                payload = {"message": raw_message}

            for attempt in range(1, max_retries + 1):
                try:
                    with httpx.Client(timeout=self.timeout) as client:
                        resp = client.post(download_url, json=payload, headers=headers)
                        if resp.status_code == 200:
                            data = resp.json()
                            b64_data = data.get("data") or data.get("base64")
                            if b64_data:
                                content_bytes = base64.b64decode(b64_data)
                                mimetype = data.get("mimetype", mimetype)
                                break
                            elif resp.content:
                                content_bytes = resp.content
                                break
                        else:
                            last_error = f"Gateway downloadmedia failed (HTTP {resp.status_code}): {resp.text[:120]}"
                except Exception as exc:
                    last_error = f"Gateway download error: {exc}"

                if attempt < max_retries:
                    time.sleep(0.2 * (2 ** (attempt - 1)))

        # 3. Try direct media URL if available
        if not content_bytes and url and url.startswith("http"):
            headers = {}
            if self.api_key:
                headers["apikey"] = self.api_key

            for attempt in range(1, max_retries + 1):
                try:
                    with httpx.Client(timeout=self.timeout, follow_redirects=True) as client:
                        resp = client.get(url, headers=headers)
                        if resp.status_code == 200:
                            content_bytes = resp.content
                            if "content-type" in resp.headers:
                                mimetype = resp.headers["content-type"].split(";")[0].strip()
                            break
                        else:
                            last_error = f"Direct URL download failed (HTTP {resp.status_code})"
                except Exception as exc:
                    last_error = f"Direct URL network error: {exc}"

                if attempt < max_retries:
                    time.sleep(0.2 * (2 ** (attempt - 1)))

        if not content_bytes:
            raise IOError(f"Could not download {media_type} attachment: {last_error or 'No download method succeeded'}")

        # Check maximum file size
        if len(content_bytes) > self.max_bytes:
            raise ValueError(
                f"Media attachment ({len(content_bytes)} bytes) exceeds maximum allowed size ({self.max_bytes} bytes)."
            )

        # Determine file suffix
        suffix = self._get_suffix_from_mimetype(mimetype, media_type, metadata.get("filename"))

        # Save to temporary file
        fd, temp_path_str = tempfile.mkstemp(prefix=f"whatsapp_{media_type}_", suffix=suffix)
        temp_path = Path(temp_path_str)
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(content_bytes)
        except Exception:
            if temp_path.exists():
                temp_path.unlink(missing_ok=True)
            raise

        return content_bytes, temp_path, mimetype

    @staticmethod
    def cleanup_temp_file(path: Optional[Path]) -> None:
        """Safely delete a temporary file if it exists."""
        if path and isinstance(path, Path) and path.exists():
            try:
                path.unlink(missing_ok=True)
            except Exception as e:
                logger.warning("Failed to remove temporary media file %s: %s", path, e)

    @staticmethod
    def _get_suffix_from_mimetype(mimetype: str, media_type: str, filename: Optional[str]) -> str:
        if filename and "." in filename:
            return Path(filename).suffix.lower()

        mime_map = {
            "image/jpeg": ".jpg",
            "image/png": ".png",
            "image/webp": ".webp",
            "image/gif": ".gif",
            "audio/ogg": ".ogg",
            "audio/opus": ".opus",
            "audio/mpeg": ".mp3",
            "audio/mp3": ".mp3",
            "audio/wav": ".wav",
            "audio/m4a": ".m4a",
            "application/pdf": ".pdf",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
            "application/msword": ".doc",
            "text/plain": ".txt",
        }
        clean_mime = mimetype.split(";")[0].strip().lower()
        if clean_mime in mime_map:
            return mime_map[clean_mime]

        if media_type == "image":
            return ".jpg"
        elif media_type == "audio":
            return ".ogg"
        elif media_type == "document":
            return ".pdf"
        return ".bin"
