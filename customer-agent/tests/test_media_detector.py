"""Unit tests for WhatsApp Message Type Detection and Payload Sanitization."""
import sys
from pathlib import Path

# Add customer-agent to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from media.detector import detect_message_type, sanitize_payload


def test_detect_text_message():
    payload = {
        "event": "MESSAGE",
        "data": {
            "Info": {"ID": "txt-1", "Sender": "971501234567@s.whatsapp.net"},
            "Message": {"conversation": "Hello Horus"},
        },
    }
    mtype, meta = detect_message_type(payload)
    assert mtype == "text"
    assert meta["text"] == "Hello Horus"


def test_detect_image_message():
    payload = {
        "event": "MESSAGE",
        "data": {
            "Info": {"ID": "img-1", "Sender": "971501234567@s.whatsapp.net"},
            "Message": {
                "imageMessage": {
                    "mimetype": "image/jpeg",
                    "caption": "Look at this sample design",
                    "fileLength": 10240,
                    "url": "https://example.com/media/img.jpg",
                }
            },
        },
    }
    mtype, meta = detect_message_type(payload)
    assert mtype == "image"
    assert meta["mimetype"] == "image/jpeg"
    assert meta["caption"] == "Look at this sample design"


def test_detect_voice_note_ptt():
    payload = {
        "event": "MESSAGE",
        "data": {
            "Info": {"ID": "aud-1", "Sender": "971501234567@s.whatsapp.net"},
            "Message": {
                "audioMessage": {
                    "mimetype": "audio/ogg; codecs=opus",
                    "ptt": True,
                    "seconds": 12,
                    "url": "https://example.com/media/audio.ogg",
                }
            },
        },
    }
    mtype, meta = detect_message_type(payload)
    assert mtype == "audio"
    assert meta["is_ptt"] is True
    assert meta["seconds"] == 12


def test_detect_document_message():
    payload = {
        "event": "MESSAGE",
        "data": {
            "Info": {"ID": "doc-1", "Sender": "971501234567@s.whatsapp.net"},
            "Message": {
                "documentMessage": {
                    "mimetype": "application/pdf",
                    "fileName": "tailoring_catalog.pdf",
                    "pageCount": 4,
                    "caption": "Please check this catalog",
                }
            },
        },
    }
    mtype, meta = detect_message_type(payload)
    assert mtype == "document"
    assert meta["filename"] == "tailoring_catalog.pdf"
    assert meta["page_count"] == 4


def test_detect_video_and_sticker():
    payload_vid = {"data": {"Message": {"videoMessage": {"mimetype": "video/mp4", "seconds": 30}}}}
    mtype_v, _ = detect_message_type(payload_vid)
    assert mtype_v == "video"

    payload_stk = {"data": {"Message": {"stickerMessage": {"mimetype": "image/webp"}}}}
    mtype_s, _ = detect_message_type(payload_stk)
    assert mtype_s == "sticker"


def test_sanitize_payload_redacts_secrets():
    payload = {
        "apikey": "secret-api-key-12345678",
        "token": "bearer-token-abc",
        "user": {
            "name": "Alex",
            "password": "supersecretpassword",
            "media_key": "raw_media_key_bytes",
        },
        "message": {"text": "Safe message content"},
    }
    sanitized = sanitize_payload(payload)
    assert "secret-api-key-12345678" not in str(sanitized)
    assert "supersecretpassword" not in str(sanitized)
    assert sanitized["user"]["name"] == "Alex"
    assert sanitized["message"]["text"] == "Safe message content"
    assert "[REDACTED]" in sanitized["apikey"]
