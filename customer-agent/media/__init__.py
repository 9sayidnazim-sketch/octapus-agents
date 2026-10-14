"""Octapus Customer Agent Media Processing Package.

Modules:
- detector: detect message types (text, image, audio, doc, video, sticker) and sanitize payloads
- downloader: immediate download with retries, timeouts, and temp file management
- audio_handler: voice notes transcription and conversion
- image_handler: vision content blocks, OCR, and product/invoice analysis
- document_handler: text extraction from PDF, DOCX, TXT with safe truncation
- pipeline: unified media pipeline orchestrating all handlers
"""
from .audio_handler import AudioHandler
from .detector import detect_message_type, sanitize_payload
from .document_handler import DocumentHandler
from .downloader import MediaDownloader
from .image_handler import ImageHandler
from .bland_handler import BlandHandler
from .email_handler import EmailHandler
from .pipeline import FALLBACK_ERROR_MESSAGE, MediaPipeline
from .tts_handler import (
    TTSHandler,
    clean_for_speech,
    detect_voice_intent,
    is_malayalam_or_manglish,
    sanitize_for_speech,
)

__all__ = [
    "detect_message_type",
    "sanitize_payload",
    "MediaDownloader",
    "AudioHandler",
    "ImageHandler",
    "DocumentHandler",
    "MediaPipeline",
    "TTSHandler",
    "clean_for_speech",
    "sanitize_for_speech",
    "is_malayalam_or_manglish",
    "detect_voice_intent",
    "BlandHandler",
    "EmailHandler",
    "FALLBACK_ERROR_MESSAGE",
]


