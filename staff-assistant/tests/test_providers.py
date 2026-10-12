import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch
import httpx
import pytest

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from providers import (
    AnthropicAdapter,
    OpenAIAdapter,
    GeminiAdapter,
    OpenRouterAdapter,
    OllamaAdapter,
    CustomAdapter,
    get_adapter,
)
from providers.custom_adapter import validate_base_url


def test_provider_registry():
    """Verify provider factory returns correct adapter instances."""
    assert isinstance(get_adapter("anthropic"), AnthropicAdapter)
    assert isinstance(get_adapter("openai"), OpenAIAdapter)
    assert isinstance(get_adapter("gemini"), GeminiAdapter)
    assert isinstance(get_adapter("openrouter"), OpenRouterAdapter)
    assert isinstance(get_adapter("ollama"), OllamaAdapter)
    assert isinstance(get_adapter("custom"), CustomAdapter)

    with pytest.raises(ValueError):
        get_adapter("unknown-provider")


def test_openai_adapter_mocked_chat():
    """Verify OpenAI adapter chat format and response normalization."""
    adapter = OpenAIAdapter()

    sample_response = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "Hello there!",
                    "tool_calls": [
                        {
                            "id": "call_123",
                            "type": "function",
                            "function": {
                                "name": "get_client",
                                "arguments": json.dumps({"id": "c-99"}),
                            },
                        }
                    ],
                }
            }
        ],
        "usage": {"prompt_tokens": 42, "completion_tokens": 15},
    }

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert "/chat/completions" in str(request.url)
        body = json.loads(request.read())
        assert body["model"] == "gpt-4o"
        assert "tools" in body
        assert body["tools"][0]["function"]["name"] == "get_client"
        return httpx.Response(200, json=sample_response)

    tools = [
        {
            "name": "get_client",
            "description": "Fetch client info",
            "input_schema": {"type": "object", "properties": {"id": {"type": "string"}}},
        }
    ]

    with patch("httpx.Client") as mock_client:
        mock_instance = MagicMock()
        mock_instance.post.return_value = httpx.Response(200, json=sample_response)
        mock_client.return_value.__enter__.return_value = mock_instance

        res = adapter.chat(
            messages=[{"role": "user", "content": "Fetch client c-99"}],
            tools=tools,
            model="gpt-4o",
            api_key="sk-test-key",
        )

        assert res.text == "Hello there!"
        assert len(res.tool_calls) == 1
        assert res.tool_calls[0].name == "get_client"
        assert res.tool_calls[0].input == {"id": "c-99"}
        assert res.usage["input_tokens"] == 42
        assert res.usage["output_tokens"] == 15
        assert res.error is None


def test_gemini_adapter_mocked_chat():
    """Verify Gemini adapter request mapping and response normalization."""
    adapter = GeminiAdapter()

    sample_response = {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {"text": "Searching client..."},
                        {
                            "functionCall": {
                                "name": "get_client",
                                "args": {"id": "c-88"},
                            }
                        },
                    ]
                }
            }
        ],
        "usageMetadata": {"promptTokenCount": 35, "candidatesTokenCount": 20},
    }

    with patch("httpx.Client") as mock_client:
        mock_instance = MagicMock()
        mock_instance.post.return_value = httpx.Response(200, json=sample_response)
        mock_client.return_value.__enter__.return_value = mock_instance

        res = adapter.chat(
            messages=[{"role": "user", "content": "Find client"}],
            tools=[{"name": "get_client", "description": "find", "input_schema": {}}],
            model="gemini-1.5-flash",
            api_key="gm-test-key",
        )

        assert res.text == "Searching client..."
        assert len(res.tool_calls) == 1
        assert res.tool_calls[0].name == "get_client"
        assert res.tool_calls[0].input == {"id": "c-88"}
        assert res.usage["input_tokens"] == 35
        assert res.usage["output_tokens"] == 20


def test_provider_test_connection_scenarios():
    """Verify provider test_connection for success, 401 invalid key, and timeout."""
    openai = OpenAIAdapter()

    # 1. Success
    with patch("httpx.Client") as mock_client:
        mock_instance = MagicMock()
        mock_instance.get.return_value = httpx.Response(200, json={"data": [{"id": "gpt-4o"}]})
        mock_client.return_value.__enter__.return_value = mock_instance

        result = openai.test_connection(api_key="sk-valid-key")
        assert result["ok"] is True
        assert result["model_count"] == 1
        assert result["error"] is None

    # 2. 401 Invalid Key
    with patch("httpx.Client") as mock_client:
        mock_instance = MagicMock()
        mock_instance.get.return_value = httpx.Response(401, json={"error": {"message": "Invalid API key"}})
        mock_client.return_value.__enter__.return_value = mock_instance

        result = openai.test_connection(api_key="sk-bad-key")
        assert result["ok"] is False
        assert "401" in result["error"]

    # 3. Timeout
    with patch("httpx.Client") as mock_client:
        mock_instance = MagicMock()
        mock_instance.get.side_effect = httpx.TimeoutException("Read timed out")
        mock_client.return_value.__enter__.return_value = mock_instance

        result = openai.test_connection(api_key="sk-timeout-key")
        assert result["ok"] is False
        assert "timed out" in result["error"].lower()


def test_custom_adapter_url_security():
    """Verify security rule: custom base URLs must be HTTPS or localhost."""
    assert validate_base_url("https://api.my-enterprise-ai.com/v1") is True
    assert validate_base_url("http://localhost:8000/v1") is True
    assert validate_base_url("http://127.0.0.1:11434/v1") is True

    # Insecure external HTTP URLs rejected
    assert validate_base_url("http://insecure-external-server.com/v1") is False
    assert validate_base_url("ftp://something.com") is False
    assert validate_base_url(None) is False

    custom = CustomAdapter()
    test_res = custom.test_connection(base_url="http://insecure-external-server.com/v1")
    assert test_res["ok"] is False
    assert "Security validation failed" in test_res["error"]


def test_ollama_fallback_when_tools_fail():
    """Verify Ollama adapter retries without tools if tools are not supported."""
    ollama = OllamaAdapter()

    # First attempt with tools returns 400 (unsupported), second attempt without tools succeeds
    with patch("httpx.Client") as mock_client:
        mock_instance = MagicMock()
        res_fail = httpx.Response(400, text="tools not supported on this model")
        res_ok = httpx.Response(
            200,
            json={
                "choices": [{"message": {"role": "assistant", "content": "Plain response without tools"}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5},
            },
        )
        mock_instance.post.side_effect = [res_fail, res_ok]
        mock_client.return_value.__enter__.return_value = mock_instance

        res = ollama.chat(
            messages=[{"role": "user", "content": "Hello"}],
            tools=[{"name": "test_tool", "description": "demo", "input_schema": {}}],
            model="llama3:latest",
        )

        assert res.text == "Plain response without tools"
        assert res.tool_calls == []
        assert res.error is None
