"""Unit tests for Unified WhatsApp Media Pipeline & Error Handling."""
import base64
import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from media.pipeline import FALLBACK_ERROR_MESSAGE, MediaPipeline


def test_pipeline_text_message():
    pipeline = MediaPipeline()
    payload = {
        "data": {
            "Info": {"Sender": "971525919933@s.whatsapp.net"},
            "Message": {"conversation": "What is the price of web design?"},
        }
    }
    res = pipeline.process_incoming_payload(payload)
    assert res["status"] == "success"
    assert res["type"] == "text"
    assert res["message"] == "What is the price of web design?"
    assert res["clean_number"] == "971525919933"


def test_pipeline_unsupported_video_message():
    pipeline = MediaPipeline()
    payload = {
        "data": {
            "Info": {"Sender": "971525919933@s.whatsapp.net"},
            "Message": {"videoMessage": {"mimetype": "video/mp4", "caption": "Check video"}},
        }
    }
    res = pipeline.process_incoming_payload(payload)
    assert res["status"] == "unsupported"
    assert "video" in res["message"]
    assert "text, voice notes, photos, and PDF/Word documents" in res["message"]


def test_pipeline_image_success():
    mock_downloader = MagicMock()
    fake_img = b"fake-raw-image-bytes"
    mock_downloader.download_media.return_value = (fake_img, None, "image/jpeg")

    pipeline = MediaPipeline(downloader=mock_downloader)
    payload = {
        "data": {
            "Info": {"Sender": "971525919933@s.whatsapp.net"},
            "Message": {"imageMessage": {"mimetype": "image/jpeg", "caption": "App mockup screenshot"}},
        }
    }
    res = pipeline.process_incoming_payload(payload)
    assert res["status"] == "success"
    assert res["type"] == "image"
    assert res["content_blocks"] is not None
    assert len(res["content_blocks"]) == 2
    assert res["content_blocks"][0]["type"] == "image"
    assert res["content_blocks"][1]["text"] == "App mockup screenshot"


def test_pipeline_download_failure_returns_friendly_fallback():
    mock_downloader = MagicMock()
    mock_downloader.download_media.side_effect = IOError("Download link expired")

    pipeline = MediaPipeline(downloader=mock_downloader)
    payload = {
        "data": {
            "Info": {"Sender": "971525919933@s.whatsapp.net"},
            "Message": {"imageMessage": {"mimetype": "image/jpeg"}},
        }
    }
    res = pipeline.process_incoming_payload(payload)
    assert res["status"] == "fallback"
    assert res["message"] == FALLBACK_ERROR_MESSAGE
    assert "expired" in res["error"]
