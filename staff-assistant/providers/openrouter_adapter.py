"""OpenRouter Provider Adapter (OpenAI-compatible) with model-specific tool support."""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

import httpx

from providers.base import ModelInfo, ProviderAdapter, ProviderResponse, ToolCall
from providers.openai_adapter import convert_tools_to_openai

DEFAULT_OPENROUTER_MODELS = [
    ModelInfo(
        id="anthropic/claude-3.5-sonnet",
        name="Claude 3.5 Sonnet (OpenRouter)",
        provider="openrouter",
        context_window=200000,
        supports_tools=True,
        supports_vision=True,
        supports_streaming=True,
    ),
    ModelInfo(
        id="openai/gpt-4o",
        name="GPT-4o (OpenRouter)",
        provider="openrouter",
        context_window=128000,
        supports_tools=True,
        supports_vision=True,
        supports_streaming=True,
    ),
    ModelInfo(
        id="meta-llama/llama-3.3-70b-instruct",
        name="Llama 3.3 70B (OpenRouter)",
        provider="openrouter",
        context_window=128000,
        supports_tools=True,
        supports_vision=False,
        supports_streaming=True,
    ),
    ModelInfo(
        id="deepseek/deepseek-r1",
        name="DeepSeek R1 (OpenRouter)",
        provider="openrouter",
        context_window=64000,
        supports_tools=False,
        supports_vision=False,
        supports_streaming=True,
        description="Reasoning model without standard tool support.",
    ),
]


class OpenRouterAdapter(ProviderAdapter):
    name = "openrouter"
    supports_tools = True

    def list_models(
        self, api_key: Optional[str] = None, base_url: Optional[str] = None
    ) -> List[ModelInfo]:
        key = api_key or os.environ.get("OPENROUTER_API_KEY")
        url = (base_url or "https://openrouter.ai/api/v1").rstrip("/")
        if not key:
            return DEFAULT_OPENROUTER_MODELS

        try:
            with httpx.Client(timeout=8.0) as client:
                resp = client.get(
                    f"{url}/models",
                    headers={"Authorization": f"Bearer {key}", "HTTP-Referer": "https://octapus.llc"},
                )
                if resp.status_code == 200:
                    models = resp.json().get("data", [])
                    res = []
                    for m in models[:40]:  # Cap to top 40 popular
                        mid = m.get("id", "")
                        supported_params = m.get("supported_parameters", [])
                        has_tools = "tools" in supported_params or "functions" in supported_params
                        res.append(
                            ModelInfo(
                                id=mid,
                                name=m.get("name", mid),
                                provider="openrouter",
                                context_window=m.get("context_length", 128000),
                                supports_tools=has_tools,
                                supports_vision="image" in str(m.get("architecture", {})),
                                supports_streaming=True,
                                description=m.get("description", "")[:120],
                            )
                        )
                    return res or DEFAULT_OPENROUTER_MODELS
        except Exception:
            pass
        return DEFAULT_OPENROUTER_MODELS

    def test_connection(
        self, api_key: Optional[str] = None, base_url: Optional[str] = None
    ) -> Dict[str, Any]:
        key = api_key or os.environ.get("OPENROUTER_API_KEY")
        if not key:
            return {"ok": False, "model_count": 0, "error": "API key is missing"}

        url = (base_url or "https://openrouter.ai/api/v1").rstrip("/")
        try:
            with httpx.Client(timeout=8.0) as client:
                resp = client.get(
                    f"{url}/models",
                    headers={"Authorization": f"Bearer {key}", "HTTP-Referer": "https://octapus.llc"},
                )
                if resp.status_code == 200:
                    models = resp.json().get("data", [])
                    return {"ok": True, "model_count": len(models), "error": None}
                elif resp.status_code == 401:
                    return {"ok": False, "model_count": 0, "error": "Invalid API key (401 Unauthorized)"}
                elif resp.status_code == 429:
                    return {"ok": False, "model_count": 0, "error": "Rate limited (429 Too Many Requests)"}
                else:
                    return {"ok": False, "model_count": 0, "error": f"API error ({resp.status_code}): {resp.text[:200]}"}
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
        key = api_key or os.environ.get("OPENROUTER_API_KEY")
        if not key:
            return ProviderResponse(error="OpenRouter API key is not configured")

        url = (base_url or "https://openrouter.ai/api/v1").rstrip("/")
        model_name = model.strip()
        if not model_name:
            raise ValueError("A model name must be configured in Settings.")
        params = params or {}

        # Check if the chosen model supports tools
        model_supports_tools = True
        if "deepseek-r1" in model_name.lower():
            model_supports_tools = False

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

        if tools and model_supports_tools:
            payload["tools"] = convert_tools_to_openai(tools)

        try:
            with httpx.Client(timeout=35.0) as client:
                resp = client.post(
                    f"{url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {key}",
                        "Content-Type": "application/json",
                        "HTTP-Referer": "https://octapus.llc",
                        "X-Title": "Octapus Staff Assistant",
                    },
                    json=payload,
                )
                if resp.status_code != 200:
                    return ProviderResponse(error=f"OpenRouter error ({resp.status_code}): {resp.text[:300]}")

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
            return ProviderResponse(error=f"Error communicating with OpenRouter: {str(e)}")
