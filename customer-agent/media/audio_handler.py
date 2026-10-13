"""Audio & Voice Note Handler for WhatsApp.

Handles incoming voice notes (ogg/opus), performs audio conversion via ffmpeg if available,
dispatches to Speech-To-Text (Whisper or OpenAI-compatible service) with auto language detection,
and formats the resulting transcript for the Horus agent.
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
from pathlib import Path
from typing import Optional, Tuple

import httpx

logger = logging.getLogger("octapus.media.audio")

DEFAULT_STT_URL = "https://api.openai.com/v1/audio/transcriptions"
DEFAULT_STT_MODEL = "whisper-1"


def convert_audio_if_needed(input_path: Path, target_format: str = "mp3") -> Tuple[Path, bool]:
    """
    Attempt to convert audio file to target format (mp3 or wav) using ffmpeg if installed.
    If ffmpeg is not installed or conversion fails, returns the original path.
    """
    ffmpeg_bin = shutil.which("ffmpeg")
    if not ffmpeg_bin:
        logger.debug("ffmpeg binary not found on PATH; passing original audio directly to STT.")
        return input_path, False

    output_path = input_path.with_suffix(f".{target_format}")
    if output_path.exists():
        return output_path, True

    try:
        cmd = [
            ffmpeg_bin,
            "-y",
            "-i",
            str(input_path),
            "-vn",
            "-ar",
            "16000",
            "-ac",
            "1",
            "-b:a",
            "64k",
            str(output_path),
        ]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=15)
        if res.returncode == 0 and output_path.exists():
            logger.info("Successfully converted voice note to %s via ffmpeg", target_format)
            return output_path, True
        else:
            logger.warning("ffmpeg conversion failed (code %d): %s", res.returncode, res.stderr.decode()[:120])
    except Exception as exc:
        logger.warning("ffmpeg conversion error: %s", exc)

    return input_path, False


class AudioHandler:
    def __init__(
        self,
        stt_api_url: Optional[str] = None,
        stt_api_key: Optional[str] = None,
        stt_model: Optional[str] = None,
    ):
        self.stt_url = (
            stt_api_url
            or os.environ.get("STT_API_URL")
            or DEFAULT_STT_URL
        ).strip()
        self.stt_key = (
            stt_api_key
            or os.environ.get("STT_API_KEY")
            or os.environ.get("OPENAI_API_KEY")
            or ""
        ).strip()
        self.stt_model = (
            stt_model
            or os.environ.get("STT_MODEL")
            or DEFAULT_STT_MODEL
        ).strip()

    def transcribe_audio(self, audio_path: Path, mimetype: str = "audio/ogg") -> str:
        """
        Transcribe an audio file using configured STT service.
        Returns formatted transcript: '[Voice note transcript]: ...'
        """
        if not audio_path.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        # Check for conversion if it's an ogg/opus file
        active_audio_path, converted = convert_audio_if_needed(audio_path, target_format="mp3")

        if not self.stt_key:
            logger.error("STT_API_KEY is not configured in environment.")
            raise ValueError("STT service is not configured (missing STT_API_KEY).")

        headers = {
            "Authorization": f"Bearer {self.stt_key}",
        }

        # Determine MIME type and filename for multipart upload
        filename = active_audio_path.name
        content_type = "audio/mpeg" if filename.endswith(".mp3") else mimetype.split(";")[0].strip()

        logger.info("Submitting voice note to STT (%s, model: %s)...", self.stt_url, self.stt_model)

        with open(active_audio_path, "rb") as audio_file:
            files = {
                "file": (filename, audio_file, content_type),
            }
            data = {
                "model": self.stt_model,
            }

            try:
                with httpx.Client(timeout=30.0) as client:
                    resp = client.post(self.stt_url, headers=headers, files=files, data=data)

                    if resp.status_code == 200:
                        res_data = resp.json()
                        raw_transcript = (res_data.get("text") or "").strip()
                        if not raw_transcript:
                            raw_transcript = "[Inaudible / Empty audio]"
                        logger.info("STT Transcription success (%d chars)", len(raw_transcript))
                        return f"[Voice note transcript]: {raw_transcript}"
                    else:
                        err_text = resp.text[:150]
                        logger.error("STT API failed (HTTP %d): %s", resp.status_code, err_text)
                        raise IOError(f"STT service error (HTTP {resp.status_code}): {err_text}")
            finally:
                # Clean up converted file if a temporary converted file was created
                if converted and active_audio_path != audio_path and active_audio_path.exists():
                    active_audio_path.unlink(missing_ok=True)
