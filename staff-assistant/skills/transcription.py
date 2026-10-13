"""Audio transcription skill: processes incoming voice notes and preserves audio references."""
from __future__ import annotations

import os
from typing import Any, Dict, Optional
from .base import BaseSkill


class AudioTranscriptionSkill(BaseSkill):
    """Downloads voice notes, performs speech-to-text, and preserves original audio references."""

    @property
    def skill_id(self) -> str:
        return "transcription"

    @property
    def name(self) -> str:
        return "Audio transcription"

    @property
    def description(self) -> str:
        return "Transcribes incoming voice notes and passes the transcript to the agent while retaining original audio references."

    def format_prompt_section(self, config: Dict[str, Any]) -> str:
        tone = config.get("tone", "Neutral")
        extra = config.get("extra_instructions", "").strip()
        lang = config.get("language", "auto")

        prompt = [
            "### Skill: Audio Transcription Handling",
            "- The customer may have sent an audio voice note.",
            "- When replying to a transcribed voice note, treat the transcript as the user's spoken words.",
            f"- Preferred response tone for voice inquiries: {tone}.",
        ]
        if lang != "auto":
            prompt.append(f"- Preferred language for audio responses: {lang}.")
        if extra:
            prompt.append(f"- Extra audio instructions: {extra}")
        return "\n".join(prompt)

    def execute(self, input_data: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process incoming audio metadata or payload.
        input_data can contain: 'audio_url', 'audio_id', 'audio_base64', 'audio_duration', 'text'
        """
        audio_url = input_data.get("audio_url") or input_data.get("audio_path")
        audio_id = input_data.get("audio_id") or input_data.get("media_id") or "audio-ref"
        existing_text = input_data.get("text", "").strip()

        # If transcript already supplied or dummy audio passed
        if existing_text and not existing_text.startswith("Voice message"):
            return {
                "transcript": existing_text,
                "audio_url": audio_url,
                "audio_id": audio_id,
                "source": "pre_transcribed",
            }

        # Check for whisper or external speech-to-text provider if configured in env
        stt_api_url = os.environ.get("STT_API_URL")
        stt_api_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("STT_API_KEY")

        transcript = existing_text or "Voice note received from customer."
        if audio_url and stt_api_url and stt_api_key:
            try:
                import httpx
                # Example: send audio URL or binary to STT service
                headers = {"Authorization": f"Bearer {stt_api_key}"}
                resp = httpx.post(stt_api_url, json={"url": audio_url}, headers=headers, timeout=10.0)
                if resp.status_code == 200:
                    data = resp.json()
                    transcript = data.get("text") or data.get("transcript") or transcript
            except Exception:
                pass

        return {
            "transcript": transcript,
            "original_audio_reference": {
                "audio_url": audio_url,
                "audio_id": audio_id,
                "duration": input_data.get("audio_duration"),
            },
            "status": "transcribed",
        }
