"""AI Provider registry and factory."""

from __future__ import annotations

from typing import Dict, List, Optional, Type

from providers.anthropic_adapter import AnthropicAdapter
from providers.base import ModelInfo, ProviderAdapter, ProviderResponse, ToolCall
from providers.custom_adapter import CustomAdapter
from providers.gemini_adapter import GeminiAdapter
from providers.ollama_adapter import OllamaAdapter
from providers.openai_adapter import OpenAIAdapter
from providers.openrouter_adapter import OpenRouterAdapter

_ADAPTER_REGISTRY: Dict[str, Type[ProviderAdapter]] = {
    "anthropic": AnthropicAdapter,
    "openai": OpenAIAdapter,
    "gemini": GeminiAdapter,
    "openrouter": OpenRouterAdapter,
    "ollama": OllamaAdapter,
    "custom": CustomAdapter,
}


def get_adapter(provider: str) -> ProviderAdapter:
    """Return an instantiated adapter for the specified provider."""
    provider_clean = provider.strip().lower()
    adapter_cls = _ADAPTER_REGISTRY.get(provider_clean)
    if not adapter_cls:
        raise ValueError(
            f"Unsupported provider '{provider}'. Supported: {', '.join(_ADAPTER_REGISTRY.keys())}"
        )
    return adapter_cls()


def list_supported_providers() -> List[str]:
    """Return list of supported provider names."""
    return list(_ADAPTER_REGISTRY.keys())


__all__ = [
    "ProviderAdapter",
    "ProviderResponse",
    "ToolCall",
    "ModelInfo",
    "AnthropicAdapter",
    "OpenAIAdapter",
    "GeminiAdapter",
    "OpenRouterAdapter",
    "OllamaAdapter",
    "CustomAdapter",
    "get_adapter",
    "list_supported_providers",
]
