"""Text-to-Speech (TTS) Voice Synthesis Module.

Supports:
1. ElevenLabs API (primary): https://api.elevenlabs.io/v1/text-to-speech/{voice_id}
2. OpenAI-compatible TTS API (fallback/alternative): /v1/audio/speech

Produces MP3 / Opus audio streams formatted as data URIs (data:audio/mpeg;base64,...)
ready for dispatch through WhatsApp gateway (/send/media).
"""
from __future__ import annotations

import base64
import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import httpx

logger = logging.getLogger("octapus.media.tts")

BASE_DIR = Path(__file__).resolve().parent.parent
for env_path in (BASE_DIR / ".env", BASE_DIR.parent / ".env"):
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip("'\""))

DEFAULT_ELEVENLABS_VOICE_ID = "JBFqnCBsd6RMkjVDRZzb"  # George (premade voice supported on all tiers)
DEFAULT_ELEVENLABS_MODEL = "eleven_multilingual_v2"
DEFAULT_TIMEOUT = 15.0


class TTSHandler:
    def __init__(
        self,
        elevenlabs_api_key: Optional[str] = None,
        voice_id: Optional[str] = None,
        model_id: Optional[str] = None,
        timeout: float = DEFAULT_TIMEOUT,
    ):
        if elevenlabs_api_key is not None:
            self.elevenlabs_api_key = elevenlabs_api_key
        else:
            self.elevenlabs_api_key = (
                os.environ.get("ELEVENLABS_API_KEY")
                or os.environ.get("TTS_API_KEY")
                or ""
            )
        self.voice_id = (
            voice_id
            or os.environ.get("ELEVENLABS_VOICE_ID")
            or DEFAULT_ELEVENLABS_VOICE_ID
        )
        self.model_id = (
            model_id
            or os.environ.get("ELEVENLABS_MODEL")
            or DEFAULT_ELEVENLABS_MODEL
        )
        self.timeout = timeout

    @property
    def is_configured(self) -> bool:
        """Check if any TTS provider key is available."""
        return bool(self.elevenlabs_api_key)

    def synthesize_speech(
        self,
        text: str,
        voice_id: Optional[str] = None,
        model_id: Optional[str] = None,
    ) -> Optional[Tuple[bytes, str]]:
        """
        Convert input text into spoken audio bytes.
        Returns (audio_bytes, mimetype) or None if synthesis fails or is unconfigured.
        """
        clean_text = (text or "").strip()
        if not clean_text:
            return None

        # Clean text of markdown bullet points or emoji-heavy formatting for smoother speech
        clean_text = clean_text.replace("*", "").replace("#", "").strip()

        # 1. Try ElevenLabs
        if self.elevenlabs_api_key:
            try:
                target_voice = voice_id or self.voice_id
                target_model = model_id or self.model_id
                url = f"https://api.elevenlabs.io/v1/text-to-speech/{target_voice}"
                headers = {
                    "xi-api-key": self.elevenlabs_api_key,
                    "Content-Type": "application/json",
                    "Accept": "audio/mpeg",
                }
                payload: Dict[str, Any] = {
                    "text": clean_text,
                    "model_id": target_model,
                    "voice_settings": {
                        "stability": 0.5,
                        "similarity_boost": 0.75,
                    },
                }

                with httpx.Client(timeout=self.timeout) as client:
                    resp = client.post(url, json=payload, headers=headers)
                    if resp.status_code == 200 and resp.content:
                        logger.info("ElevenLabs TTS synthesized %d audio bytes for text (%d chars)", len(resp.content), len(clean_text))
                        return resp.content, "audio/mpeg"
                    else:
                        logger.warning(
                            "ElevenLabs TTS returned HTTP %d: %s",
                            resp.status_code,
                            resp.text[:150],
                        )
            except Exception as exc:
                logger.error("ElevenLabs TTS request error: %s", exc)

        return None

    def synthesize_data_url(
        self,
        text: str,
        voice_id: Optional[str] = None,
    ) -> Optional[str]:
        """
        Synthesizes text to audio and returns a base64 data URI string:
        data:audio/mpeg;base64,<payload>
        """
        result = self.synthesize_speech(text, voice_id=voice_id)
        if not result:
            return None

        audio_bytes, mimetype = result
        b64 = base64.b64encode(audio_bytes).decode("ascii")
        return f"data:{mimetype};base64,{b64}"

    def synthesize_raw_base64(
        self,
        text: str,
        voice_id: Optional[str] = None,
    ) -> Optional[Tuple[str, str]]:
        """
        Synthesizes text to audio and returns (raw_base64_string, mimetype)
        without the data: URI wrapper.
        """
        result = self.synthesize_speech(text, voice_id=voice_id)
        if not result:
            return None

        audio_bytes, mimetype = result
        b64 = base64.b64encode(audio_bytes).decode("ascii")
        return b64, mimetype

