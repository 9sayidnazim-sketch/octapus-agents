"""Unit tests for Resend Email Delivery pipeline."""
import unittest
from unittest.mock import MagicMock, patch

from media.email_handler import EmailHandler


class TestEmailPipeline(unittest.TestCase):
    def test_email_initialization(self):
        handler = EmailHandler(
            api_key="test-resend-key",
            default_from="Octapus <test@octapus.ae>",
        )
        self.assertTrue(handler.is_configured)
        self.assertEqual(handler.api_key, "test-resend-key")
        self.assertEqual(handler.default_from, "Octapus <test@octapus.ae>")

    def test_email_unconfigured(self):
        handler = EmailHandler(api_key="")
        self.assertFalse(handler.is_configured)
        res = handler.send_email(to="client@example.com", subject="Test", text="Hello")
        self.assertEqual(res.get("status"), "error")
        self.assertIn("not configured", res.get("message", ""))
        self.assertEqual(handler.get_email_status("email_123"), {"status": "error", "message": "Resend API key is not configured"})

    def test_email_invalid_recipient(self):
        handler = EmailHandler(api_key="test-key")
        res1 = handler.send_email(to="", subject="Test", text="Hello")
        self.assertEqual(res1.get("status"), "error")
        self.assertIn("No valid recipient", res1.get("message", ""))

        res2 = handler.send_email(to="invalid-email", subject="Test", text="Hello")
        self.assertEqual(res2.get("status"), "error")
        self.assertIn("No valid recipient", res2.get("message", ""))

    def test_email_empty_subject_or_content(self):
        handler = EmailHandler(api_key="test-key")
        res1 = handler.send_email(to="test@example.com", subject="", text="Hello")
        self.assertEqual(res1.get("status"), "error")
        self.assertIn("cannot be empty", res1.get("message", ""))

        res2 = handler.send_email(to="test@example.com", subject="Hello", text="")
        self.assertEqual(res2.get("status"), "error")
        self.assertIn("must contain text or html", res2.get("message", ""))

    @patch("httpx.Client")
    def test_email_send_success(self, mock_client_cls):
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"id": "resend_msg_123"}
        mock_client.post.return_value = mock_response
        mock_client_cls.return_value.__enter__.return_value = mock_client

        handler = EmailHandler(api_key="test-key")
        res = handler.send_email(
            to="client@example.com",
            subject="Proposal from Octapus",
            text="Here is your proposal details.",
        )

        self.assertEqual(res.get("status"), "success")
        self.assertEqual(res.get("id"), "resend_msg_123")
        self.assertEqual(res.get("to"), ["client@example.com"])
        mock_client.post.assert_called_once()
        args, kwargs = mock_client.post.call_args
        self.assertIn("/emails", args[0])
        self.assertEqual(kwargs["json"]["to"], ["client@example.com"])
        self.assertEqual(kwargs["json"]["subject"], "Proposal from Octapus")
        self.assertIn("Octapus LLC", kwargs["json"]["html"])

    @patch("httpx.Client")
    def test_email_get_status(self, mock_client_cls):
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": "email_abc",
            "last_event": "delivered",
        }
        mock_client.get.return_value = mock_response
        mock_client_cls.return_value.__enter__.return_value = mock_client

        handler = EmailHandler(api_key="test-key")
        res = handler.get_email_status("email_abc")
        self.assertEqual(res.get("id"), "email_abc")
        self.assertEqual(res.get("last_event"), "delivered")

    @patch("httpx.Client")
    def test_email_api_error_handling(self, mock_client_cls):
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 422
        mock_response.text = '{"message":"Domain not verified"}'
        mock_client.post.return_value = mock_response
        mock_client_cls.return_value.__enter__.return_value = mock_client

        handler = EmailHandler(api_key="test-key")
        res = handler.send_email(to="client@example.com", subject="Test", text="Hello")
        self.assertEqual(res.get("status"), "error")
        self.assertEqual(res.get("code"), 422)
        self.assertIn("Domain not verified", res.get("message", ""))


if __name__ == "__main__":
    unittest.main()
