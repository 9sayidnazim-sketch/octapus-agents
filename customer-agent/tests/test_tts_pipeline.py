"""Unit tests for Text-to-Speech (TTS) synthesis pipeline."""
import unittest
from unittest.mock import patch, MagicMock

from media.tts_handler import TTSHandler


class TestTTSPipeline(unittest.TestCase):
    def test_tts_initialization(self):
        handler = TTSHandler(
            elevenlabs_api_key="test-key",
            voice_id="test-voice-id",
            model_id="eleven_multilingual_v2",
        )
        self.assertTrue(handler.is_configured)
        self.assertEqual(handler.voice_id, "test-voice-id")
        self.assertEqual(handler.model_id, "eleven_multilingual_v2")

    def test_tts_unconfigured(self):
        handler = TTSHandler(elevenlabs_api_key="")
        self.assertFalse(handler.is_configured)
        self.assertIsNone(handler.synthesize_speech("Hello"))
        self.assertIsNone(handler.synthesize_data_url("Hello"))

    def test_tts_empty_text(self):
        handler = TTSHandler(elevenlabs_api_key="test-key")
        self.assertIsNone(handler.synthesize_speech(""))
        self.assertIsNone(handler.synthesize_speech("   "))

    @patch("httpx.Client")
    def test_tts_synthesize_success(self, mock_client_cls):
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b"fake-mp3-audio-bytes"
        mock_client.post.return_value = mock_response
        mock_client_cls.return_value.__enter__.return_value = mock_client

        handler = TTSHandler(elevenlabs_api_key="test-key")
        res = handler.synthesize_speech("Hello from Horus")

        self.assertIsNotNone(res)
        audio_bytes, mimetype = res
        self.assertEqual(audio_bytes, b"fake-mp3-audio-bytes")
        self.assertEqual(mimetype, "audio/mpeg")

    @patch("httpx.Client")
    def test_tts_synthesize_data_url(self, mock_client_cls):
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b"mp3data"
        mock_client.post.return_value = mock_response
        mock_client_cls.return_value.__enter__.return_value = mock_client

        handler = TTSHandler(elevenlabs_api_key="test-key")
        data_url = handler.synthesize_data_url("Hello")

        self.assertIsNotNone(data_url)
        self.assertTrue(data_url.startswith("data:audio/mpeg;base64,"))

    @patch("httpx.Client")
    def test_tts_synthesize_raw_base64(self, mock_client_cls):
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b"mp3data"
        mock_client.post.return_value = mock_response
        mock_client_cls.return_value.__enter__.return_value = mock_client

        handler = TTSHandler(elevenlabs_api_key="test-key")
        res = handler.synthesize_raw_base64("Hello")

        self.assertIsNotNone(res)
        b64, mime = res
        self.assertEqual(mime, "audio/mpeg")
        self.assertFalse(b64.startswith("data:"))


    @patch("httpx.Client")
    def test_tts_api_error_graceful_handling(self, mock_client_cls):
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.text = '{"detail":{"message":"Missing permission"}}'
        mock_client.post.return_value = mock_response
        mock_client_cls.return_value.__enter__.return_value = mock_client

        handler = TTSHandler(elevenlabs_api_key="test-key")
        res = handler.synthesize_speech("Hello")

        # Never crashes, gracefully returns None
        self.assertIsNone(res)
        self.assertIsNone(handler.synthesize_data_url("Hello"))


if __name__ == "__main__":
    unittest.main()
