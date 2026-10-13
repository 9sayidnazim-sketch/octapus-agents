"""Unit tests for WhatsApp Voice Note & Audio Pipeline."""
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from media.audio_handler import AudioHandler, convert_audio_if_needed


def test_convert_audio_without_ffmpeg_returns_original():
    with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as f:
        f.write(b"dummy ogg audio data")
        temp_path = Path(f.name)

    try:
        with patch("shutil.which", return_value=None):
            out_path, converted = convert_audio_if_needed(temp_path)
            assert out_path == temp_path
            assert converted is False
    finally:
        temp_path.unlink(missing_ok=True)


def test_transcribe_audio_missing_key_raises_value_error():
    handler = AudioHandler(stt_api_key="", stt_api_url="https://api.openai.com/v1/audio/transcriptions")
    with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as f:
        f.write(b"audio data")
        temp_path = Path(f.name)

    try:
        with pytest.raises(ValueError, match="missing STT_API_KEY"):
            handler.transcribe_audio(temp_path)
    finally:
        temp_path.unlink(missing_ok=True)


def test_transcribe_audio_success_mock():
    handler = AudioHandler(stt_api_key="test-key", stt_api_url="https://api.mock.test/transcribe")
    with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as f:
        f.write(b"voice note audio bytes")
        temp_path = Path(f.name)

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"text": "I would like to inquire about your ERP tailoring solution."}

    try:
        with patch("httpx.Client.post", return_value=mock_resp):
            transcript = handler.transcribe_audio(temp_path)
            assert "[Voice note transcript]:" in transcript
            assert "ERP tailoring solution" in transcript
    finally:
        temp_path.unlink(missing_ok=True)


def test_transcribe_audio_empty_audio_fallback():
    handler = AudioHandler(stt_api_key="test-key")
    with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as f:
        f.write(b"silent bytes")
        temp_path = Path(f.name)

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"text": ""}

    try:
        with patch("httpx.Client.post", return_value=mock_resp):
            transcript = handler.transcribe_audio(temp_path)
            assert "[Inaudible / Empty audio]" in transcript
    finally:
        temp_path.unlink(missing_ok=True)
