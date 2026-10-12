"""Anthropic Provider Adapter for Messages API and tool use."""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

import anthropic
import httpx

from providers.base import ModelInfo, ProviderAdapter, ProviderResponse, ToolCall

DEFAULT_ANTHROPIC_MODELS = [
    ModelInfo(
        id="claude-sonnet-5-5",
        name="Claude 3.7 Sonnet (Hybrid/5.5)",
        provider="anthropic",
        context_window=200000,
        supports_tools=True,
        supports_vision=True,
        supports_streaming=True,
        description="Most intelligent model, balanced speed and reasoning.",
    ),
    ModelInfo(
        id="claude-3-7-sonnet-20250219",
        name="Claude 3.7 Sonnet",
        provider="anthropic",
        context_window=200000,
        supports_tools=True,
        supports_vision=True,
        supports_streaming=True,
        description="High intelligence with hybrid reasoning.",
    ),
    ModelInfo(
        id="claude-3-5-haiku-20241022",
        name="Claude 3.5 Haiku",
        provider="anthropic",
        context_window=200000,
        supports_tools=True,
        supports_vision=True,
        supports_streaming=True,
        description="Fastest model for responsive chat and quick tasks.",
    ),
    ModelInfo(
        id="claude-3-opus-20240229",
        name="Claude 3 Opus",
        provider="anthropic",
        context_window=200000,
        supports_tools=True,
        supports_vision=True,
        supports_streaming=True,
        description="Top-level complex analysis and deep writing.",
    ),
]


class AnthropicAdapter(ProviderAdapter):
    name = "anthropic"
    supports_tools = True

    def list_models(
        self, api_key: Optional[str] = None, base_url: Optional[str] = None
    ) -> List[ModelInfo]:
        return DEFAULT_ANTHROPIC_MODELS

    def test_connection(
        self, api_key: Optional[str] = None, base_url: Optional[str] = None
    ) -> Dict[str, Any]:
        key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            return {"ok": False, "model_count": 0, "error": "API key is missing"}

        url = (base_url or os.environ.get("ANTHROPIC_BASE_URL") or "https://api.anthropic.com").rstrip("/")
        headers = {
            "x-api-key": key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }

        try:
            with httpx.Client(timeout=10.0) as client:
                # Test minimal call
                resp = client.post(
                    f"{url}/v1/messages",
                    headers=headers,
                    json={
                        "model": "claude-3-5-haiku-20241022",
                        "max_tokens": 1,
                        "messages": [{"role": "user", "content": "ping"}],
                    },
                )
                if resp.status_code == 200:
                    return {"ok": True, "model_count": len(DEFAULT_ANTHROPIC_MODELS), "error": None}
                elif resp.status_code == 401:
                    return {"ok": False, "model_count": 0, "error": "Invalid API key (401 Unauthorized)"}
                elif resp.status_code == 429:
                    return {"ok": False, "model_count": 0, "error": "Rate limited (429 Too Many Requests)"}
                else:
                    try:
                        err_json = resp.json()
                        msg = err_json.get("error", {}).get("message", resp.text)
                    except Exception:
                        msg = resp.text
                    # If model not found or similar, but key authenticated
                    if "model" in msg.lower() and resp.status_code != 401:
                        return {"ok": True, "model_count": len(DEFAULT_ANTHROPIC_MODELS), "error": None}
                    return {"ok": False, "model_count": 0, "error": f"API error ({resp.status_code}): {msg}"}
        except httpx.TimeoutException:
            return {"ok": False, "model_count": 0, "error": "Connection timed out"}
        except Exception as e:
            return {"ok": False, "model_count": 0, "error": f"Connection error: {str(e)}"}

    def chat(
        self,
        messages: List[Dict[str, Any]],
        system: str = "",
        tools: Optional[List[Dict[str, Any]]] = None,
        model: str = "",
        params: Optional[Dict[str, Any]] = None,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
    ) -> ProviderResponse:
        key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            return ProviderResponse(error="Anthropic API key is not configured")

        url = base_url or os.environ.get("ANTHROPIC_BASE_URL") or "https://api.anthropic.com"
        client = anthropic.Anthropic(api_key=key, base_url=url)
        params = params or {}
        model_name = model or "claude-sonnet-5-5"
        max_tokens = params.get("max_output_tokens", 1200)

        kwargs: Dict[str, Any] = {
            "model": model_name,
            "max_tokens": max_tokens,
            "messages": messages,
        }
        if system:
            kwargs["system"] = system
        if tools and self.supports_tools:
            kwargs["tools"] = tools
        if "temperature" in params:
            kwargs["temperature"] = float(params["temperature"])
        if "top_p" in params:
            kwargs["top_p"] = float(params["top_p"])

        try:
            msg = client.messages.create(**kwargs)
            text_blocks = [b.text for b in msg.content if getattr(b, "type", None) == "text"]
            tool_calls: List[ToolCall] = []
            for b in msg.content:
                if getattr(b, "type", None) == "tool_use":
                    tool_calls.append(ToolCall(id=b.id, name=b.name, input=b.input))

            return ProviderResponse(
                text="".join(text_blocks),
                tool_calls=tool_calls,
                usage={
                    "input_tokens": getattr(msg.usage, "input_tokens", 0),
                    "output_tokens": getattr(msg.usage, "output_tokens", 0),
                },
                raw=msg,
            )
        except anthropic.APIError as e:
            return ProviderResponse(error=f"Anthropic API error: {e.message}")
        except Exception as e:
            return ProviderResponse(error=f"Error communicating with Anthropic: {str(e)}")
