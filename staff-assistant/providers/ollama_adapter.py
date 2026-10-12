"""Ollama Provider Adapter for local models (no API key required)."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

import httpx

from providers.base import ModelInfo, ProviderAdapter, ProviderResponse, ToolCall
from providers.openai_adapter import convert_tools_to_openai

DEFAULT_OLLAMA_MODELS = [
    ModelInfo(
        id="llama3.2:latest",
        name="Llama 3.2 (Local)",
        provider="ollama",
        context_window=128000,
        supports_tools=True,
        supports_vision=False,
        supports_streaming=True,
        description="Local lightweight Llama model with tool calling.",
    ),
    ModelInfo(
        id="qwen2.5:latest",
        name="Qwen 2.5 (Local)",
        provider="ollama",
        context_window=32000,
        supports_tools=True,
        supports_vision=False,
        supports_streaming=True,
        description="Local performant multilingual model.",
    ),
    ModelInfo(
        id="mistral:latest",
        name="Mistral 7B (Local)",
        provider="ollama",
        context_window=32000,
        supports_tools=True,
        supports_vision=False,
        supports_streaming=True,
        description="Fast local instruct model.",
    ),
]


class OllamaAdapter(ProviderAdapter):
    name = "ollama"
    supports_tools = True

    def list_models(
        self, api_key: Optional[str] = None, base_url: Optional[str] = None
    ) -> List[ModelInfo]:
        url = (base_url or "http://localhost:11434").rstrip("/")
        try:
            with httpx.Client(timeout=4.0) as client:
                resp = client.get(f"{url}/api/tags")
                if resp.status_code == 200:
                    models = resp.json().get("models", [])
                    res = []
                    for m in models:
                        m_name = m.get("name", "")
                        res.append(
                            ModelInfo(
                                id=m_name,
                                name=m_name,
                                provider="ollama",
                                context_window=32000,
                                supports_tools=True,
                                supports_vision="llava" in m_name,
                                supports_streaming=True,
                            )
                        )
                    return res or DEFAULT_OLLAMA_MODELS
        except Exception:
            pass
        return DEFAULT_OLLAMA_MODELS

    def test_connection(
        self, api_key: Optional[str] = None, base_url: Optional[str] = None
    ) -> Dict[str, Any]:
        url = (base_url or "http://localhost:11434").rstrip("/")
        try:
            with httpx.Client(timeout=4.0) as client:
                resp = client.get(f"{url}/api/tags")
                if resp.status_code == 200:
                    models = resp.json().get("models", [])
                    return {"ok": True, "model_count": len(models), "error": None}
                return {"ok": False, "model_count": 0, "error": f"Ollama returned status {resp.status_code}"}
        except Exception as e:
            return {
                "ok": False,
                "model_count": 0,
                "error": f"Could not connect to Ollama at {url}. Make sure Ollama is running.",
            }

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
        url = (base_url or "http://localhost:11434").rstrip("/")
        model_name = model.strip()
        if not model_name:
            raise ValueError("A model name must be configured in Settings.")
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
            "stream": False,
        }
        if "temperature" in params:
            payload["options"] = {"temperature": float(params["temperature"])}

        if tools and self.supports_tools:
            payload["tools"] = convert_tools_to_openai(tools)

        try:
            # Use Ollama's OpenAI-compatible endpoint or native /api/chat
            with httpx.Client(timeout=60.0) as client:
                resp = client.post(f"{url}/v1/chat/completions", json=payload)
                if resp.status_code != 200:
                    # Retry without tools if model doesn't support tools
                    if "tools" in payload:
                        payload.pop("tools")
                        resp = client.post(f"{url}/v1/chat/completions", json=payload)
                        if resp.status_code != 200:
                            return ProviderResponse(error=f"Ollama error ({resp.status_code}): {resp.text[:300]}")
                    else:
                        return ProviderResponse(error=f"Ollama error ({resp.status_code}): {resp.text[:300]}")

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
            return ProviderResponse(error=f"Error communicating with local Ollama: {str(e)}")
