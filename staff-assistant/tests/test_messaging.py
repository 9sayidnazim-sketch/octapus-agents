"""Tests for WhatsApp phone normalization and sendMessage API."""
import os
import pytest
import httpx
from messaging import normalize_phone_number, sendMessage


def test_normalize_phone_number_uae_local():
    assert normalize_phone_number("0528724090") == "971528724090"
    assert normalize_phone_number("0501234567") == "971501234567"


def test_normalize_phone_number_international():
    assert normalize_phone_number("+971 52 872 4090") == "971528724090"
    assert normalize_phone_number("00971528724090") == "971528724090"
    assert normalize_phone_number("+1 (555) 234-5678") == "15552345678"
    assert normalize_phone_number("447911123456") == "447911123456"


def test_normalize_phone_number_invalid():
    with pytest.raises(ValueError):
        normalize_phone_number("")
    with pytest.raises(ValueError):
        normalize_phone_number("abc")
    with pytest.raises(ValueError):
        normalize_phone_number("123")  # Too short (< 8)
    with pytest.raises(ValueError):
        normalize_phone_number("12345678901234567")  # Too long (> 15)


def test_send_message_dry_run_when_no_url(monkeypatch):
    monkeypatch.delenv("WA_API_URL", raising=False)
    monkeypatch.setenv("WA_API_KEY", "super-secret-key-12345")
    res = sendMessage("+971 52 872 4090", "Hello from Horus")
    assert res["status"] == "dry_run"
    assert res["number"] == "971528724090"
    assert res["text"] == "Hello from Horus"


def test_send_message_success(monkeypatch):
    monkeypatch.setenv("WA_API_URL", "https://api.mock-whatsapp.com/send")
    monkeypatch.setenv("WA_API_KEY", "test-api-key-999")

    captured = {}

    def mock_post(url, json, headers, **kwargs):
        captured["url"] = url
        captured["payload"] = json
        captured["headers"] = headers
        return httpx.Response(200, json={"status": "delivered", "id": "msg-123"})

    monkeypatch.setattr(httpx.Client, "post", lambda self, url, **kwargs: mock_post(url, **kwargs))

    res = sendMessage("0528724090", "Your invoice is ready.")
    assert res["status"] == "sent"
    assert captured["url"] == "https://api.mock-whatsapp.com/send"
    assert captured["headers"]["apikey"] == "test-api-key-999"
    assert captured["headers"]["Content-Type"] == "application/json"
    assert captured["payload"]["number"] == "971528724090"
    assert captured["payload"]["text"] == "Your invoice is ready."


def test_send_message_retry_and_key_not_leaked(monkeypatch, caplog):
    monkeypatch.setenv("WA_API_URL", "https://api.mock-whatsapp.com/send")
    monkeypatch.setenv("WA_API_KEY", "SECRET_KEY_NEVER_LOGGED_999")

    attempts = {"count": 0}

    def mock_post_fail(url, **kwargs):
        attempts["count"] += 1
        return httpx.Response(500, text="Internal gateway error")

    monkeypatch.setattr(httpx.Client, "post", lambda self, url, **kwargs: mock_post_fail(url, **kwargs))

    res = sendMessage("971528724090", "Testing failure retry", max_retries=2)
    assert res["status"] == "failed"
    assert attempts["count"] == 2
    # Ensure secret key is NEVER present in error logs or result
    assert "SECRET_KEY_NEVER_LOGGED_999" not in caplog.text
    assert "SECRET_KEY_NEVER_LOGGED_999" not in str(res)
