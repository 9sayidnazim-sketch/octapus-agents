"""OpenAI Provider Adapter for Chat Completions API with tool calling."""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

import httpx

from providers.base import ModelInfo, ProviderAdapter, ProviderResponse, ToolCall

DEFAULT_OPENAI_MODELS = [
    ModelInfo(
        id="gpt-4o",
        name="GPT-4o",
        provider="openai",
        context_window=128000,
        supports_tools=True,
        supports_vision=True,
        supports_streaming=True,
        description="Flagship multimodal model with high intelligence.",
    ),
    ModelInfo(
        id="gpt-4o-mini",
        name="GPT-4o mini",
        provider="openai",
        context_window=128000,
        supports_tools=True,
        supports_vision=True,
        supports_streaming=True,
        description="Affordable, fast model for lightweight tasks.",
    ),
    ModelInfo(
        id="o3-mini",
        name="o3-mini",
        provider="openai",
        context_window=200000,
        supports_tools=True,
        supports_vision=False,
        supports_streaming=True,
        description="Reasoning model for math and technical tasks.",
    ),
    ModelInfo(
        id="gpt-4-turbo",
        name="GPT-4 Turbo",
        provider="openai",
        context_window=128000,
        supports_tools=True,
        supports_vision=True,
        supports_streaming=True,
        description="Previous generation high intelligence model.",
    ),
]


def convert_tools_to_openai(tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Convert Anthropic tool schemas to OpenAI function calling format."""
    openai_tools = []
    for t in tools:
        schema = t.get("input_schema") or t.get("parameters") or {"type": "object", "properties": {}}
        openai_tools.append({
            "type": "function",
            "function": {
                "name": t.get("name", ""),
                "description": t.get("description", ""),
                "parameters": schema,
            },
        })
    return openai_tools


class OpenAIAdapter(ProviderAdapter):
    name = "openai"
    supports_tools = True

    def list_models(
        self, api_key: Optional[str] = None, base_url: Optional[str] = None
    ) -> List[ModelInfo]:
        key = api_key or os.environ.get("OPENAI_API_KEY")
        url = (base_url or os.environ.get("OPENAI_BASE_URL") or "https://api.openai.com/v1").rstrip("/")
        if not key:
            return DEFAULT_OPENAI_MODELS

        try:
            with httpx.Client(timeout=6.0) as client:
                resp = client.get(f"{url}/models", headers={"Authorization": f"Bearer {key}"})
                if resp.status_code == 200:
                    data = resp.json().get("data", [])
                    chat_models = []
                    for m in data:
                        mid = m.get("id", "")
                        if "gpt" in mid or "o1" in mid or "o3" in mid:
                            chat_models.append(
                                ModelInfo(
                                    id=mid,
                                    name=mid,
                                    provider="openai",
                                    context_window=128000,
                                    supports_tools=True,
                                    supports_vision="vision" in mid or "4o" in mid,
                                    supports_streaming=True,
                                )
                            )
                    return chat_models or DEFAULT_OPENAI_MODELS
        except Exception:
            pass
        return DEFAULT_OPENAI_MODELS

    def test_connection(
        self, api_key: Optional[str] = None, base_url: Optional[str] = None
    ) -> Dict[str, Any]:
        key = api_key or os.environ.get("OPENAI_API_KEY")
        if not key:
            return {"ok": False, "model_count": 0, "error": "API key is missing"}

        url = (base_url or os.environ.get("OPENAI_BASE_URL") or "https://api.openai.com/v1").rstrip("/")
        try:
            with httpx.Client(timeout=8.0) as client:
                resp = client.get(f"{url}/models", headers={"Authorization": f"Bearer {key}"})
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
        key = api_key or os.environ.get("OPENAI_API_KEY")
        if not key:
            return ProviderResponse(error="OpenAI API key is not configured")

        url = (base_url or os.environ.get("OPENAI_BASE_URL") or "https://api.openai.com/v1").rstrip("/")
        model_name = model.strip()
        if not model_name:
            raise ValueError("A model name must be configured in Settings.")
        params = params or {}

        # Prepare messages
        formatted_messages = []
        if system:
            formatted_messages.append({"role": "system", "content": system})

        for m in messages:
            role = m.get("role", "user")
            content = m.get("content", "")
            if isinstance(content, list):
                # Handle possible tool results or content lists
                text_parts = []
                for part in content:
                    if isinstance(part, dict) and "text" in part:
                        text_parts.append(part["text"])
                    elif isinstance(part, dict) and part.get("type") == "tool_result":
                        text_parts.append(part.get("content", ""))
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

        try:
            with httpx.Client(timeout=30.0) as client:
                resp = client.post(
                    f"{url}/chat/completions",
                    headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                    json=payload,
                )
                if resp.status_code != 200:
                    return ProviderResponse(error=f"OpenAI error ({resp.status_code}): {resp.text[:300]}")

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
            return ProviderResponse(error=f"Error communicating with OpenAI: {str(e)}")
