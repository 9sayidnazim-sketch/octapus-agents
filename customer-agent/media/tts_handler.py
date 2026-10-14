"""Text-to-Speech (TTS) Voice Synthesis Module.

Supports:
1. ElevenLabs API (primary): https://api.elevenlabs.io/v1/text-to-speech/{voice_id}
   - Model: eleven_multilingual_v2 (supports English, Arabic, Malayalam script, and Manglish)
   - Output: audio/mpeg streams formatted as data URIs (data:audio/mpeg;base64,...)
2. Bounded retries, text sanitization (stripping Markdown, internal headers, and false capability denials),
   and structured delivery results.
"""
from __future__ import annotations

import base64
import logging
import os
import re
import time
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

DEFAULT_ELEVENLABS_VOICE_ID = "JBFqnCBsd6RMkjVDRZzb"  # George (premade multilingual voice)
DEFAULT_ELEVENLABS_MODEL = "eleven_multilingual_v2"
DEFAULT_SARVAM_MODEL = "bulbul:v3"
DEFAULT_SARVAM_SPEAKER = "kavitha"
DEFAULT_SARVAM_URL = "https://api.sarvam.ai/text-to-speech"
DEFAULT_TIMEOUT = 15.0

MALAYALAM_SCRIPT_PATTERN = re.compile(r"[\u0D00-\u0D7F]")

MANGLISH_TERMS = {
    # Pronouns & Pointers
    "njan", "njanum", "njanundu", "njangal", "nammal", "namukku", "namukk",
    "nee", "ninakku", "ninakk", "ningal", "ningalkku", "ningalkk", "pulli", "pullikku",
    "ithu", "athu", "ithil", "athil", "ithinte", "athinte", "ithokke", "athokke",
    # Question & Relative Words
    "entha", "enthe", "enthoru", "enthina", "enthinanu", "enthokke", "enthoke",
    "engane", "enganeya", "enganeyanu", "evide", "evideya", "evideyanu", "aarannu", "aaranu",
    "eppol", "eppozha", "eppozhanu",
    # Original Slang & Casual Vernacular
    "pwoli", "poli", "poliyalle", "kidu", "kidilam", "adipoli", "adipoliyayi",
    "scene", "sceneilla", "sceneillallo", "sceneaano", "sceneaakkanda",
    "machane", "machan", "aliya", "bro", "changathi", "kootukara",
    "set", "setaakkam", "setaakki", "setaakkiko",
    "pinneentha", "pinnalla", "pinneyentha", "pinne", "pinneyum",
    "vibe", "mass", "theerkkam", "nokkikolam", "nokkam", "nokku",
    "karyam", "karyangal", "kollam", "kollaam", "kollallo",
    "paranjolu", "parayedo", "parayeda", "parayoo", "parayu", "parayaam", "parayumo", "paranjath", "paranjathu",
    "chettan", "chetta", "chechi", "itha", "ikka",
    "kozhappam", "kozhappamilla", "prashnam", "prashnamilla",
    "chumma", "aatto", "ketto", "kettoda", "thakarkkam", "polikkam", "valya", "nalla",
    "ippo", "ippozhe", "ippol", "udane", "nerathe", "neram",
    # Auxiliaries, Verbs & Affirmations
    "aanu", "aano", "aayirunnu", "aayirikkum", "alla", "allallo", "alle", "aatto",
    "undo", "illa", "illallo", "ille", "undallo",
    "cheyyam", "cheyyaam", "cheyyo", "cheyyu", "cheyyoo", "cheyyan", "cheythath", "cheytho", "cheythu",
    "pattilla", "pattum", "pattumo",
    "shari", "sheri", "sheriya", "sheriyanu", "sherikkum",
    "ravile", "vaikitt", "vaikittu", "uchakk", "uchakku", "innu", "naale", "nale", "mattanale",
    "vishesham", "visheshangal", "sugham", "sukham", "sukhamano", "sughamano",
    "kurachu", "oru", "athe", "athano", "athinu", "athre",
    "venam", "venda", "koodi", "kooduthal", "tharam", "tharaam", "thayo",
    "namaskaram", "swagatham", "sugamano", "santhosham",
}


def is_malayalam_or_manglish(text: str) -> bool:
    """Detect whether input text contains Malayalam Unicode script or common Manglish words."""
    if not text:
        return False
    if MALAYALAM_SCRIPT_PATTERN.search(text):
        return True
    words = re.findall(r"\b[a-zA-Z]+\b", text.lower())
    match_count = sum(1 for w in words if w in MANGLISH_TERMS)
    return match_count >= 1


def sanitize_for_speech(text: str, user_lang: str = "en") -> str:
    """Prepares raw AI model output for natural, clean Text-to-Speech synthesis.

    Strictly strips:
    - Raw JSON / JSON objects (e.g. {"status": "ok", ...}, {"reply": ...})
    - Code blocks (```...```) and inline backticks
    - Technical tags, HTML/XML tags, internal system tags ([Voice note transcript:...], [From Verified Management...])
    - Markdown headings (#), bold/italics (**, __, *, _), strikethrough (~~), blockquotes (>), tables (|), dividers (---)
    - Markdown links [Label](url) -> converted to just Label
    - Bare URLs (https://... or http://...)
    - Bullet markers (- , * , • ) and list numbers (1. , 2. )
    - Emojis and non-spoken unicode symbols
    - Literal technical artifacts ("undefined", "null", "NaN", "{question}", "${...}")
    - Technical error strings (HTTP 403, Traceback, Exception, APIError, Insufficient account balance)
    - Accidental capability denials ("I cannot generate audio")

    Enforces:
    - Clean conversational sentence structure (1-3 sentences maximum for voice)
    - Graceful non-empty spoken fallback: If empty or inaudible, returns "Sorry, could you repeat that?"
      (or Malayalam if Malayalam detected: "Kshamikkanam, onnukoodi parayaamo?")
    """
    if not text:
        return "Kshamikkanam, onnukoodi parayaamo?" if user_lang in ("ml", "manglish") else "Sorry, could you repeat that?"

    s = str(text).strip()

    # 1. Catch technical error traces or API error dictionaries
    if re.search(r"\b(?:traceback|error code:\s*\d+|api[_\s]?error|insufficient[_\s]?balance|internal server error|http\s*(?:40\d|50\d))\b", s, re.I):
        return (
            "Kshamikkanam, oru technical issue undayi. Onnukoodi parayaamo?"
            if user_lang in ("ml", "manglish")
            else "I am sorry, I encountered a temporary technical issue. Could you please repeat your question?"
        )

    # 2. Extract content from JSON if the response is wrapped in JSON
    if s.startswith("{") and s.endswith("}"):
        try:
            import json as _json
            parsed = _json.loads(s)
            for k in ("reply", "message", "answer", "text", "content", "response"):
                if k in parsed and isinstance(parsed[k], str) and parsed[k].strip():
                    s = parsed[k].strip()
                    break
        except Exception:
            pass

    # 3. Strip code blocks ``` ... ```
    s = re.sub(r"```[\s\S]*?```", "", s)
    # Strip inline code backticks `code` -> code
    s = re.sub(r"`([^`]+)`", r"\1", s)

    # 4. Strip bracketed system tags
    s = re.sub(r"\[(?:Voice note transcript|From Verified Management|Vision OCR|Vision Analysis|Tool Result|Inaudible)[^\]]*\]:?\s*", "", s, re.I)

    # 5. Handle Markdown links [Label](url) -> Label
    s = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", s)

    # 6. Convert emails: info@octapus.ae -> info at octapus dot a e
    s = re.sub(r"\b([a-zA-Z0-9_.+-]+)@([a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)\b", r"\1 at \2", s)
    s = re.sub(r"\.([a-z]{2,4})\b", r" dot \1", s)

    # 7. Strip bare URLs (http://... or https://...)
    s = re.sub(r"https?://\S+", "", s)

    # 8. Strip markdown headings (#)
    s = re.sub(r"^\s*#+\s*", "", s, flags=re.MULTILINE)

    # 9. Strip bold/italic (**text**, __text__, *text*, _text_)
    s = re.sub(r"(\*\*|__)(.*?)\1", r"\2", s)
    s = re.sub(r"(\*|_)(.*?)\1", r"\2", s)
    s = re.sub(r"~~(.*?)~~", r"\1", s)

    # 10. Strip blockquotes (>) and table formatting (|)
    s = re.sub(r"^\s*>\s*", "", s, flags=re.MULTILINE)
    s = re.sub(r"\|", " ", s)
    s = re.sub(r"[-=]{3,}", "", s)

    # 11. Normalize bullet points and numbered lists to pauses / periods
    s = re.sub(r"^\s*[-*•]\s+", "", s, flags=re.MULTILINE)
    s = re.sub(r"^\s*\d+\.\s+", "", s, flags=re.MULTILINE)

    # 12. Strip literal technical artifacts and placeholders
    s = re.sub(r"\b(?:undefined|null|NaN|\[object Object\])\b", "", s, re.I)
    s = re.sub(r"\{[a-zA-Z0-9_\s-]+\}", "", s)  # {question}, {user_message}
    s = re.sub(r"\$\{[^}]+\}", "", s)

    # 13. Strip HTML / XML tags (<tag> ... </tag> or <tag/>)
    s = re.sub(r"<[^>]+>", "", s)

    # 14. Strip emojis and decorative symbols
    s = re.sub(r"[\U00010000-\U0010ffff]", "", s)
    s = re.sub(r"[\u2600-\u27bf]", "", s)

    # 15. Clean stray brackets and braces
    s = re.sub(r"[{}\[\]\(\)]", " ", s)

    # 16. Strip accidental false capability denials
    s = re.sub(
        r"\b(?:I cannot generate audio|I am unable to generate audio|I cannot speak|I do not have a voice|Enikku audio generate cheyyaan pattilla)[^.]*\.\s*",
        "",
        s,
        flags=re.IGNORECASE,
    )

    # 17. Normalize spaces and multiple punctuation
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n+", ". ", s)
    s = re.sub(r"\.{2,}", ".", s)
    s = re.sub(r"\s+([.,!?])", r"\1", s)
    s = s.strip(" \t\n\r")

    # 18. Ensure 1-3 natural spoken sentences
    sentences = [sent.strip() for sent in re.split(r"(?<=[.!?])\s+", s) if sent.strip()]
    if len(sentences) > 3:
        s = " ".join(sentences[:3])
    elif sentences:
        s = " ".join(sentences)

    if not s or len(s.strip(" .!?")) < 2:
        return "Kshamikkanam, onnukoodi parayaamo?" if user_lang in ("ml", "manglish") else "Sorry, could you repeat that?"

    return s


def clean_for_speech(text: str) -> str:
    """Prepare raw assistant output for spoken audio synthesis (backward-compatible wrapper)."""
    lang = "ml" if is_malayalam_or_manglish(text) else "en"
    return sanitize_for_speech(text, user_lang=lang)


VOICE_REQUEST_TRIGGERS = [
    # Manglish / Malayalam triggers (including authentic casual slang triggers)
    r"\bvoice\s*aay[it]*\b",
    r"\baudio\s*aay[it]*\b",
    r"\bvoice[-\s]*il\b",
    r"\baudio[-\s]*il\b",
    r"\bvoice\s*(?:note\s*)?ayakk\b",
    r"\baudio\s*(?:note\s*)?ayakk\b",
    r"\bvoice\s*para\b",
    r"\baudio\s*para\b",
    r"\bparay[uu]*\s*voice\b",
    r"\bvoice\s*note\b",
    r"\baudio\s*note\b",
    r"\bvoice\s*message\b",
    r"\baudio\s*message\b",
    r"\bvoice\s*tharaamo\b",
    r"\bvoice\s*parayaamo\b",
    r"\baudio\s*tharaamo\b",
    r"\bvoice\s*reply\b",
    r"\baudio\s*reply\b",
    r"\bvoice\s*(?:note\s*)?(?:thaa|tharu|vidu|parayoo|paraye|therumo)\b",
    r"\b(?:oru\s*)?voice\s*(?:note|msg|message)\b",
    r"\bvoice\s*aayitt\s*(?:para|parayoo|parayaam)\b",
    r"\bvoice[-\s]*il\s*(?:para|parayoo|paraye|therumo)\b",
    r"\baudio\s*(?:note\s*)?(?:vidu|thaa|parayu|parayoo)\b",
    r"\bshabdathil\s*(?:para|parayoo)\b",
    # English triggers
    r"\bread\s*(?:this\s*)?(?:out\s*)?aloud\b",
    r"\breply\s*in\s*voice\b",
    r"\breply\s*in\s*audio\b",
    r"\breply\s*with\s*(?:voice|audio)\b",
    r"\banswer\s*in\s*(?:voice|audio)\b",
    r"\b(?:speak|talk)\s*(?:to\s*me|aloud|out\s*loud|this)\b",
    r"\b(?:speak|talk)\s*in\s*(?:voice|audio)\b",
    r"\bsend\s*(?:a\s*)?(?:voice|audio)(?:\s*note|\s*message)?\b",
    r"\bcan\s*you\s*(?:reply|speak|answer|talk)\s*in\s*(?:audio|voice)\b",
    r"\bcan\s*you\s*(?:speak|talk)\b",
    r"\bcan\s*you\s*send\s*(?:audio|voice)\b",
    r"\bdo\s*you\s*have\s*(?:a\s*)?voice\b",
    # Malayalam script
    r"വോയ്സ്\s*ആയി",
    r"വോയ്സ്\s*നോട്ട്",
    r"വോയ്സ്\s*അയക്കൂ",
    r"വോയ്സ്\s*അയക്ക്",
    r"ഓഡിയോ\s*അയക്കൂ",
    r"ഓഡിയോ\s*അയക്ക്",
    r"ശബ്ദത്തിൽ\s*പറയൂ",
    r"വായിച്ചു\s*കേൾപ്പിക്കൂ",
    r"സംസാരിക്കൂ",
    r"ഓഡിയോ",
]


def detect_voice_intent(
    text: str,
    is_incoming_audio: bool = False,
    force_voice: Optional[bool] = None,
    tts_mode: Optional[str] = None,
) -> bool:
    """Determine whether the turn should produce an audio response."""
    if force_voice is not None:
        return bool(force_voice)

    mode = (tts_mode or os.environ.get("TTS_MODE", "voice_on_voice")).lower()
    if mode == "always":
        return True

    if is_incoming_audio and mode == "voice_on_voice":
        return True

    if not text:
        return False

    norm = text.lower().strip()
    for pattern in VOICE_REQUEST_TRIGGERS:
        if re.search(pattern, norm, flags=re.IGNORECASE):
            return True

    return False


class TTSHandler:
    """Manages AI Voice synthesis (Sarvam AI for Malayalam/Indic, ElevenLabs for multilingual)."""

    def __init__(
        self,
        elevenlabs_api_key: Optional[str] = None,
        voice_id: Optional[str] = None,
        model_id: Optional[str] = None,
        sarvam_api_key: Optional[str] = None,
        sarvam_speaker: Optional[str] = None,
        sarvam_model: Optional[str] = None,
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

        # Sarvam AI (Malayalam Voice)
        if sarvam_api_key is not None:
            self.sarvam_api_key = sarvam_api_key
        elif elevenlabs_api_key is not None and elevenlabs_api_key == "":
            self.sarvam_api_key = ""
        else:
            self.sarvam_api_key = (
                os.environ.get("SARVAM_API_KEY")
                or os.environ.get("MALAYALAM_TTS_API_KEY")
                or ""
            )
        self.sarvam_speaker = (
            sarvam_speaker
            or os.environ.get("SARVAM_DEFAULT_SPEAKER")
            or os.environ.get("SARVAM_SPEAKER")
            or DEFAULT_SARVAM_SPEAKER
        )
        self.sarvam_model = (
            sarvam_model
            or os.environ.get("SARVAM_DEFAULT_MODEL")
            or os.environ.get("SARVAM_MODEL")
            or DEFAULT_SARVAM_MODEL
        )
        self.sarvam_url = os.environ.get("SARVAM_TTS_URL", DEFAULT_SARVAM_URL)
        self.timeout = timeout

    @property
    def is_configured(self) -> bool:
        """Check if either Sarvam AI or ElevenLabs TTS provider key is configured."""
        has_eleven = bool(self.elevenlabs_api_key and len(self.elevenlabs_api_key.strip()) > 5)
        has_sarvam = bool(self.sarvam_api_key and len(self.sarvam_api_key.strip()) > 5)
        return has_eleven or has_sarvam

    def _synthesize_sarvam(
        self,
        clean_text: str,
        speaker: Optional[str] = None,
        model: Optional[str] = None,
    ) -> Optional[Tuple[bytes, str]]:
        """Synthesize Malayalam or Indic speech using Sarvam AI Bulbul."""
        if not self.sarvam_api_key:
            return None

        target_speaker = speaker or self.sarvam_speaker
        target_model = model or self.sarvam_model
        headers = {
            "api-subscription-key": self.sarvam_api_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        payload: Dict[str, Any] = {
            "inputs": [clean_text],
            "target_language_code": "ml-IN",
            "speaker": target_speaker,
            "model": target_model,
        }

        max_attempts = 2
        for attempt in range(1, max_attempts + 1):
            try:
                with httpx.Client(timeout=self.timeout) as client:
                    resp = client.post(self.sarvam_url, json=payload, headers=headers)
                    if resp.status_code == 200:
                        data = resp.json()
                        audios = data.get("audios") or []
                        if audios and isinstance(audios[0], str):
                            raw_bytes = base64.b64decode(audios[0])
                            logger.info(
                                "Sarvam AI synthesized %d audio bytes (Malayalam speaker: %s) on attempt %d",
                                len(raw_bytes),
                                target_speaker,
                                attempt,
                            )
                            return raw_bytes, "audio/wav"
                    else:
                        logger.warning(
                            "Sarvam AI returned HTTP %d (attempt %d/%d): %s",
                            resp.status_code,
                            attempt,
                            max_attempts,
                            resp.text[:120],
                        )
            except Exception as exc:
                logger.warning(
                    "Sarvam AI request error on attempt %d/%d: %s",
                    attempt,
                    max_attempts,
                    exc,
                )

            if attempt < max_attempts:
                time.sleep(0.5)

        logger.error("Sarvam AI Malayalam TTS synthesis failed after %d attempts.", max_attempts)
        return None

    def _synthesize_elevenlabs(
        self,
        clean_text: str,
        voice_id: Optional[str] = None,
        model_id: Optional[str] = None,
    ) -> Optional[Tuple[bytes, str]]:
        """Synthesize multilingual speech using ElevenLabs."""
        if not self.elevenlabs_api_key:
            return None

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
                "use_speaker_boost": True,
            },
        }

        max_attempts = 2
        for attempt in range(1, max_attempts + 1):
            try:
                with httpx.Client(timeout=self.timeout) as client:
                    resp = client.post(url, json=payload, headers=headers)
                    if resp.status_code == 200 and resp.content:
                        logger.info(
                            "ElevenLabs TTS synthesized %d audio bytes for text (%d chars) on attempt %d",
                            len(resp.content),
                            len(clean_text),
                            attempt,
                        )
                        return resp.content, "audio/mpeg"
                    else:
                        logger.warning(
                            "ElevenLabs TTS returned HTTP %d (attempt %d/%d): %s",
                            resp.status_code,
                            attempt,
                            max_attempts,
                            resp.text[:120],
                        )
            except Exception as exc:
                logger.warning(
                    "ElevenLabs TTS request error on attempt %d/%d: %s",
                    attempt,
                    max_attempts,
                    exc,
                )

            if attempt < max_attempts:
                time.sleep(0.5)

        logger.error("ElevenLabs TTS synthesis failed after %d attempts.", max_attempts)
        return None

    def synthesize_speech(
        self,
        text: str,
        voice_id: Optional[str] = None,
        model_id: Optional[str] = None,
    ) -> Optional[Tuple[bytes, str]]:
        """Convert input text into spoken audio bytes with provider selection.
        Prioritizes Sarvam AI for Malayalam script and Manglish text, and ElevenLabs
        for English/general speech, with automatic graceful fallback.
        """
        clean_text = clean_for_speech(text)
        if not clean_text:
            return None

        if not self.is_configured:
            logger.debug("TTS synthesis skipped: No TTS provider configured.")
            return None

        # 1. Check if the text is Malayalam or Manglish
        is_ml = is_malayalam_or_manglish(clean_text)

        # 2. If Malayalam/Manglish and Sarvam is configured, prioritize Sarvam AI
        if is_ml and self.sarvam_api_key:
            res = self._synthesize_sarvam(clean_text)
            if res:
                return res
            logger.warning("Sarvam Malayalam synthesis failed; attempting ElevenLabs fallback.")

        # 3. ElevenLabs synthesis (primary for English, or fallback for Malayalam)
        if self.elevenlabs_api_key:
            res = self._synthesize_elevenlabs(clean_text, voice_id=voice_id, model_id=model_id)
            if res:
                return res

        # 4. Fallback to Sarvam AI if ElevenLabs was unconfigured or failed
        if self.sarvam_api_key and not is_ml:
            return self._synthesize_sarvam(clean_text)

        return None

    def synthesize_with_status(
        self,
        text: str,
        voice_id: Optional[str] = None,
    ) -> Tuple[Optional[str], str, Optional[str]]:
        """Synthesize text and return structured result: (data_url, audio_status, error_message).

        audio_status values:
        - 'delivered': Successfully generated audio payload
        - 'generation_failed': Attempted synthesis but API/network failed
        - 'unconfigured': Voice synthesis is not configured on this server
        """
        if not self.is_configured:
            return None, "unconfigured", "ElevenLabs API key is not configured in environment."

        clean_text = clean_for_speech(text)
        if not clean_text:
            return None, "empty_text", "No speech content to synthesize."

        res = self.synthesize_speech(clean_text, voice_id=voice_id)
        if not res:
            return None, "generation_failed", "ElevenLabs audio synthesis request failed."

        audio_bytes, mimetype = res
        b64 = base64.b64encode(audio_bytes).decode("ascii")
        data_url = f"data:{mimetype};base64,{b64}"
        return data_url, "delivered", None

    def synthesize_data_url(
        self,
        text: str,
        voice_id: Optional[str] = None,
    ) -> Optional[str]:
        """Synthesize text to audio and return a base64 data URI string."""
        data_url, status, _ = self.synthesize_with_status(text, voice_id=voice_id)
        return data_url

    def synthesize_raw_base64(
        self,
        text: str,
        voice_id: Optional[str] = None,
    ) -> Optional[Tuple[str, str]]:
        """Synthesizes text to audio and returns (raw_base64_string, mimetype)."""
        result = self.synthesize_speech(text, voice_id=voice_id)
        if not result:
            return None

        audio_bytes, mimetype = result
        b64 = base64.b64encode(audio_bytes).decode("ascii")
        return b64, mimetype
