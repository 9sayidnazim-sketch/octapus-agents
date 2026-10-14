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

    def test_malayalam_detection(self):
        from media.tts_handler import is_malayalam_or_manglish
        self.assertTrue(is_malayalam_or_manglish("നമസ്കാരം, സുഖമാണോ?"))
        self.assertTrue(is_malayalam_or_manglish("Njan Horus AI aanu. Entha vishesham?"))
        self.assertTrue(is_malayalam_or_manglish("Sheri, nale ravile remind cheyyam."))
        self.assertTrue(is_malayalam_or_manglish("Pwoli machane, scene illa! Ippo thanne set aakkam."))
        self.assertTrue(is_malayalam_or_manglish("Kidu vibe aanu bro, karyam paranjolu."))
        self.assertTrue(is_malayalam_or_manglish("Pinneentha aliya, nammal katta support aanu!"))
        self.assertFalse(is_malayalam_or_manglish("Good morning, how are you today?"))

    @patch("httpx.Client")
    def test_sarvam_malayalam_synthesis_success(self, mock_client_cls):
        import base64
        fake_wav = b"RIFFfake-wav-audio-content"
        fake_b64 = base64.b64encode(fake_wav).decode("ascii")

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"audios": [fake_b64]}
        mock_client.post.return_value = mock_response
        mock_client_cls.return_value.__enter__.return_value = mock_client

        handler = TTSHandler(
            elevenlabs_api_key="eleven-key",
            sarvam_api_key="sk_5eq58rm8_IihroaTx4qkEM2bdLpL2khJS",
        )
        res = handler.synthesize_speech("നമസ്കാരം, സുഖമാണോ?")
        self.assertIsNotNone(res)
        audio_bytes, mimetype = res
        self.assertEqual(audio_bytes, fake_wav)
        self.assertEqual(mimetype, "audio/wav")

        # Verify Sarvam endpoint was called with ml-IN and kavitha
        mock_client.post.assert_called_once()
        call_args = mock_client.post.call_args
        self.assertIn("sarvam.ai", call_args[0][0])
        payload = call_args[1]["json"]
        self.assertEqual(payload["target_language_code"], "ml-IN")
        self.assertEqual(payload["speaker"], "kavitha")

    @patch("httpx.Client")
    def test_sarvam_fallback_to_elevenlabs_on_error(self, mock_client_cls):
        mock_client = MagicMock()
        # First call (Sarvam) fails with 500
        mock_resp_sarvam = MagicMock()
        mock_resp_sarvam.status_code = 500
        mock_resp_sarvam.text = "Internal Server Error"

        # Second call (ElevenLabs fallback) succeeds
        mock_resp_eleven = MagicMock()
        mock_resp_eleven.status_code = 200
        mock_resp_eleven.content = b"eleven-audio-fallback"

        mock_client.post.side_effect = [
            mock_resp_sarvam,
            mock_resp_sarvam,  # retry 2
            mock_resp_eleven,  # elevenlabs
        ]
        mock_client_cls.return_value.__enter__.return_value = mock_client

        handler = TTSHandler(
            elevenlabs_api_key="eleven-key",
            sarvam_api_key="sarvam-key",
        )
        res = handler.synthesize_speech("നമസ്കാരം")
        self.assertIsNotNone(res)
        audio_bytes, mimetype = res
        self.assertEqual(audio_bytes, b"eleven-audio-fallback")
        self.assertEqual(mimetype, "audio/mpeg")


if __name__ == "__main__":
    unittest.main()

