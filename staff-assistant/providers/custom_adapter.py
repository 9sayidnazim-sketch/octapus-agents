"""Custom OpenAI-compatible Provider Adapter with strict URL validation."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import httpx

from providers.base import ModelInfo, ProviderAdapter, ProviderResponse, ToolCall
from providers.openai_adapter import convert_tools_to_openai


def validate_base_url(url: Optional[str]) -> bool:
    """Validate that custom base_url is HTTPS or localhost."""
    if not url:
        return False
    parsed = urlparse(url)
    if parsed.scheme == "https":
        return True
    if parsed.scheme == "http" and (parsed.hostname in ("localhost", "127.0.0.1", "::1")):
        return True
    return False


DEFAULT_CUSTOM_MODELS = [
    ModelInfo(
        id="default-model",
        name="Custom Model",
        provider="custom",
        context_window=128000,
        supports_tools=True,
        supports_vision=False,
        supports_streaming=True,
    )
]


class CustomAdapter(ProviderAdapter):
    name = "custom"
    supports_tools = True

    def list_models(
        self, api_key: Optional[str] = None, base_url: Optional[str] = None
    ) -> List[ModelInfo]:
        if not base_url or not validate_base_url(base_url):
            return DEFAULT_CUSTOM_MODELS

        url = base_url.rstrip("/")
        headers = {}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        try:
            with httpx.Client(timeout=6.0) as client:
                resp = client.get(f"{url}/models", headers=headers)
                if resp.status_code == 200:
                    models = resp.json().get("data", [])
                    res = []
                    for m in models:
                        mid = m.get("id", "")
                        res.append(
                            ModelInfo(
                                id=mid,
                                name=mid,
                                provider="custom",
                                context_window=128000,
                                supports_tools=True,
                                supports_vision=False,
                                supports_streaming=True,
                            )
                        )
                    return res or DEFAULT_CUSTOM_MODELS
        except Exception:
            pass
        return DEFAULT_CUSTOM_MODELS

    def test_connection(
        self, api_key: Optional[str] = None, base_url: Optional[str] = None
    ) -> Dict[str, Any]:
        if not base_url:
            return {"ok": False, "model_count": 0, "error": "Base URL is required"}
        if not validate_base_url(base_url):
            return {
                "ok": False,
                "model_count": 0,
                "error": "Security validation failed: Base URL must use HTTPS (or HTTP localhost only)",
            }

        url = base_url.rstrip("/")
        headers = {}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        try:
            with httpx.Client(timeout=8.0) as client:
                resp = client.get(f"{url}/models", headers=headers)
                if resp.status_code == 200:
                    models = resp.json().get("data", [])
                    return {"ok": True, "model_count": len(models), "error": None}
                elif resp.status_code == 401:
                    return {"ok": False, "model_count": 0, "error": "Invalid API key (401 Unauthorized)"}
                elif resp.status_code == 429:
                    return {"ok": False, "model_count": 0, "error": "Rate limited (429 Too Many Requests)"}
                else:
                    return {"ok": False, "model_count": 0, "error": f"Endpoint error ({resp.status_code}): {resp.text[:200]}"}
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
        if not base_url or not validate_base_url(base_url):
            return ProviderResponse(error="Invalid or non-HTTPS base URL provided")

        url = base_url.rstrip("/")
        model_name = model or "default-model"
        params = params or {}

        formatted_messages = []
        if system:
            formatted_messages.append({"role": "system", "content": system})

        for m in messages:
            role = m.get("role", "user")
            content = m.get("content", "")
            if isinstance(content, list):
                text_parts = [p.get("text", "") for p in content if isinstance(p, dict) and "text" in p]
                content = "\n".join(text_parts)
            formatted_messages.append({"role": role, "content": str(content)})

        payload: Dict[str, Any] = {
            "model": model_name,
            "messages": formatted_messages,
            "max_tokens": params.get("max_output_tokens", 1200),
        }
        if "temperature" in params:
            payload["temperature"] = float(params["temperature"])
        if "top_p" in params:
            payload["top_p"] = float(params["top_p"])

        if tools and self.supports_tools:
            payload["tools"] = convert_tools_to_openai(tools)

        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        try:
            with httpx.Client(timeout=35.0) as client:
                resp = client.post(f"{url}/chat/completions", headers=headers, json=payload)
                if resp.status_code != 200:
                    return ProviderResponse(error=f"Custom endpoint error ({resp.status_code}): {resp.text[:300]}")

                data = resp.json()
                choice = data.get("choices", [{}])[0]
                message = choice.get("message", {})
                text = message.get("content") or ""

                tool_calls: List[ToolCall] = []
                for tc in message.get("tool_calls", []):
                    fn = tc.get("function", {})
                    fn_name = fn.get("name", "")
                    fn_args = {}
                    try:
                        fn_args = json.loads(fn.get("arguments", "{}"))
                    except Exception:
                        pass
                    tool_calls.append(ToolCall(id=tc.get("id", ""), name=fn_name, input=fn_args))

                usage_data = data.get("usage", {})
                return ProviderResponse(
                    text=text,
                    tool_calls=tool_calls,
                    usage={
                        "input_tokens": usage_data.get("prompt_tokens", 0),
                        "output_tokens": usage_data.get("completion_tokens", 0),
                    },
                    raw=data,
                )
        except Exception as e:
            return ProviderResponse(error=f"Error communicating with custom endpoint: {str(e)}")
