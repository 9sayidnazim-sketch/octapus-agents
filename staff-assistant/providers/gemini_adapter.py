"""Google Gemini Provider Adapter for generateContent API with function declarations."""

from __future__ import annotations

import os
import uuid
from typing import Any, Dict, List, Optional

import httpx

from providers.base import ModelInfo, ProviderAdapter, ProviderResponse, ToolCall

DEFAULT_GEMINI_MODELS = [
    ModelInfo(
        id="gemini-1.5-pro",
        name="Gemini 1.5 Pro",
        provider="gemini",
        context_window=2000000,
        supports_tools=True,
        supports_vision=True,
        supports_streaming=True,
        description="Massive 2M context window, high reasoning capability.",
    ),
    ModelInfo(
        id="gemini-1.5-flash",
        name="Gemini 1.5 Flash",
        provider="gemini",
        context_window=1000000,
        supports_tools=True,
        supports_vision=True,
        supports_streaming=True,
        description="Fast and lightweight multimodal model.",
    ),
    ModelInfo(
        id="gemini-2.0-flash",
        name="Gemini 2.0 Flash",
        provider="gemini",
        context_window=1000000,
        supports_tools=True,
        supports_vision=True,
        supports_streaming=True,
        description="Next-gen ultra-fast flash model.",
    ),
]


def convert_tools_to_gemini(tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Convert tool list to Gemini function_declarations format."""
    declarations = []
    for t in tools:
        declarations.append({
            "name": t.get("name", ""),
            "description": t.get("description", ""),
            "parameters": t.get("input_schema") or t.get("parameters") or {"type": "object", "properties": {}},
        })
    return [{"function_declarations": declarations}] if declarations else []


class GeminiAdapter(ProviderAdapter):
    name = "gemini"
    supports_tools = True

    def list_models(
        self, api_key: Optional[str] = None, base_url: Optional[str] = None
    ) -> List[ModelInfo]:
        key = api_key or os.environ.get("GEMINI_API_KEY")
        if not key:
            return DEFAULT_GEMINI_MODELS

        try:
            with httpx.Client(timeout=6.0) as client:
                resp = client.get(
                    f"https://generativelanguage.googleapis.com/v1beta/models?key={key}"
                )
                if resp.status_code == 200:
                    models = resp.json().get("models", [])
                    res = []
                    for m in models:
                        mid = m.get("name", "").replace("models/", "")
                        if "gemini" in mid:
                            res.append(
                                ModelInfo(
                                    id=mid,
                                    name=m.get("displayName", mid),
                                    provider="gemini",
                                    context_window=m.get("inputTokenLimit", 1000000),
                                    supports_tools=True,
                                    supports_vision=True,
                                    supports_streaming=True,
                                    description=m.get("description", ""),
                                )
                            )
                    return res or DEFAULT_GEMINI_MODELS
        except Exception:
            pass
        return DEFAULT_GEMINI_MODELS

    def test_connection(
        self, api_key: Optional[str] = None, base_url: Optional[str] = None
    ) -> Dict[str, Any]:
        key = api_key or os.environ.get("GEMINI_API_KEY")
        if not key:
            return {"ok": False, "model_count": 0, "error": "API key is missing"}

        try:
            with httpx.Client(timeout=8.0) as client:
                resp = client.get(
                    f"https://generativelanguage.googleapis.com/v1beta/models?key={key}"
                )
                if resp.status_code == 200:
                    models = resp.json().get("models", [])
                    gemini_models = [m for m in models if "gemini" in m.get("name", "")]
                    return {"ok": True, "model_count": len(gemini_models) or len(models), "error": None}
                elif resp.status_code in (400, 403):
                    return {"ok": False, "model_count": 0, "error": "Invalid API key or unauthorized"}
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
        key = api_key or os.environ.get("GEMINI_API_KEY")
        if not key:
            return ProviderResponse(error="Google Gemini API key is not configured")

        model_name = model or "gemini-1.5-flash"
        params = params or {}

        # Format messages for Gemini contents
        contents = []
        for m in messages:
            role = "user" if m.get("role") in ("user", "system") else "model"
            content = m.get("content", "")
            if isinstance(content, list):
                text_parts = [p.get("text", "") for p in content if isinstance(p, dict) and "text" in p]
                content = "\n".join(text_parts)
            contents.append({"role": role, "parts": [{"text": str(content)}]})

        payload: Dict[str, Any] = {"contents": contents}
        if system:
            payload["system_instruction"] = {"parts": [{"text": system}]}

        gen_config: Dict[str, Any] = {
            "maxOutputTokens": params.get("max_output_tokens", 1200),
        }
        if "temperature" in params:
            gen_config["temperature"] = float(params["temperature"])
        if "top_p" in params:
            gen_config["topP"] = float(params["top_p"])
        payload["generationConfig"] = gen_config

        if tools and self.supports_tools:
            gemini_tools = convert_tools_to_gemini(tools)
            if gemini_tools:
                payload["tools"] = gemini_tools

        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={key}"
            with httpx.Client(timeout=30.0) as client:
                resp = client.post(url, json=payload)
                if resp.status_code != 200:
                    return ProviderResponse(error=f"Gemini API error ({resp.status_code}): {resp.text[:300]}")

                data = resp.json()
                candidate = data.get("candidates", [{}])[0]
                parts = candidate.get("content", {}).get("parts", [])

                text_parts = []
                tool_calls: List[ToolCall] = []

                for p in parts:
                    if "text" in p:
                        text_parts.append(p["text"])
                    elif "functionCall" in p:
                        fc = p["functionCall"]
                        tool_calls.append(
                            ToolCall(
                                id=f"gemini-{uuid.uuid4().hex[:8]}",
                                name=fc.get("name", ""),
                                input=fc.get("args", {}),
                            )
                        )

                meta = data.get("usageMetadata", {})
                return ProviderResponse(
                    text="".join(text_parts),
                    tool_calls=tool_calls,
                    usage={
                        "input_tokens": meta.get("promptTokenCount", 0),
                        "output_tokens": meta.get("candidatesTokenCount", 0),
                    },
                    raw=data,
                )
        except Exception as e:
            return ProviderResponse(error=f"Error communicating with Gemini: {str(e)}")
