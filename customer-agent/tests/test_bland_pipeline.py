"""Unit tests for Bland.ai conversational phone calling pipeline."""
import unittest
from unittest.mock import MagicMock, patch

from media.bland_handler import BlandHandler


class TestBlandPipeline(unittest.TestCase):
    def test_bland_initialization(self):
        handler = BlandHandler(
            api_key="test-org-key",
            api_url="https://api.bland.ai/v1",
            default_voice="maya",
        )
        self.assertTrue(handler.is_configured)
        self.assertEqual(handler.api_key, "test-org-key")
        self.assertEqual(handler.api_url, "https://api.bland.ai/v1")
        self.assertEqual(handler.default_voice, "maya")

    def test_bland_unconfigured(self):
        handler = BlandHandler(api_key="")
        self.assertFalse(handler.is_configured)
        res = handler.send_call(phone_number="+971525919933", task="Call customer")
        self.assertEqual(res.get("status"), "error")
        self.assertIn("not configured", res.get("message", ""))
        self.assertEqual(handler.get_account_info(), {"status": "unconfigured"})
        self.assertEqual(handler.list_calls(), [])

    def test_bland_send_call_invalid_phone(self):
        handler = BlandHandler(api_key="test-key")
        res1 = handler.send_call(phone_number="", task="Call client")
        self.assertEqual(res1.get("status"), "error")
        self.assertIn("Invalid phone number", res1.get("message", ""))

        res2 = handler.send_call(phone_number="123", task="Call client")
        self.assertEqual(res2.get("status"), "error")
        self.assertIn("Invalid phone number", res2.get("message", ""))

    def test_bland_send_call_empty_task(self):
        handler = BlandHandler(api_key="test-key")
        res = handler.send_call(phone_number="+971525919933", task="")
        self.assertEqual(res.get("status"), "error")
        self.assertIn("cannot be empty", res.get("message", ""))

    @patch("httpx.Client")
    def test_bland_send_call_success(self, mock_client_cls):
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "success",
            "call_id": "call_abc123xyz",
            "message": "Call queued",
        }
        mock_client.post.return_value = mock_response
        mock_client_cls.return_value.__enter__.return_value = mock_client

        handler = BlandHandler(api_key="test-key")
        res = handler.send_call(
            phone_number="971525919933",
            task="You are calling on behalf of Octapus LLC.",
            first_sentence="Hello from Octapus",
            language="en",
        )

        self.assertEqual(res.get("status"), "success")
        self.assertEqual(res.get("call_id"), "call_abc123xyz")
        mock_client.post.assert_called_once()
        args, kwargs = mock_client.post.call_args
        self.assertIn("/calls", args[0])
        self.assertEqual(kwargs["json"]["phone_number"], "+971525919933")
        self.assertEqual(kwargs["json"]["language"], "en")
        self.assertEqual(kwargs["json"]["first_sentence"], "Hello from Octapus")

    @patch("httpx.Client")
    def test_bland_get_call_details(self, mock_client_cls):
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "call_id": "call_123",
            "status": "completed",
            "concatenated_transcript": "Customer confirmed order",
        }
        mock_client.get.return_value = mock_response
        mock_client_cls.return_value.__enter__.return_value = mock_client

        handler = BlandHandler(api_key="test-key")
        res = handler.get_call_details("call_123")
        self.assertEqual(res.get("call_id"), "call_123")
        self.assertEqual(res.get("status"), "completed")

    @patch("httpx.Client")
    def test_bland_get_account_info(self, mock_client_cls):
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "active",
            "billing": {"current_balance": 2},
        }
        mock_client.get.return_value = mock_response
        mock_client_cls.return_value.__enter__.return_value = mock_client

        handler = BlandHandler(api_key="test-key")
        res = handler.get_account_info()
        self.assertEqual(res.get("status"), "active")
        self.assertEqual(res.get("billing", {}).get("current_balance"), 2)

    @patch("httpx.Client")
    def test_bland_api_error_handling(self, mock_client_cls):
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.text = '{"message":"Country not supported"}'
        mock_client.post.return_value = mock_response
        mock_client_cls.return_value.__enter__.return_value = mock_client

        handler = BlandHandler(api_key="test-key")
        res = handler.send_call(phone_number="+971525919933", task="Call")
        self.assertEqual(res.get("status"), "error")
        self.assertEqual(res.get("code"), 400)
        self.assertIn("Country not supported", res.get("message", ""))


if __name__ == "__main__":
    unittest.main()
