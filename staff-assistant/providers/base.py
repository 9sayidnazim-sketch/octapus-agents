"""Base abstractions and unified models for AI Providers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ToolCall:
    """Normalized tool call representation."""
    id: str
    name: str
    input: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ProviderResponse:
    """Normalized response from any AI provider."""
    text: str = ""
    tool_calls: List[ToolCall] = field(default_factory=list)
    usage: Dict[str, int] = field(default_factory=lambda: {"input_tokens": 0, "output_tokens": 0})
    error: Optional[str] = None
    raw: Any = None


@dataclass
class ModelInfo:
    """Information and capabilities of a provider model."""
    id: str
    name: str
    provider: str
    context_window: int = 128000
    supports_tools: bool = True
    supports_vision: bool = False
    supports_streaming: bool = True
    description: str = ""


class ProviderAdapter(ABC):
    """Abstract Base Class for AI Provider Adapters."""

    name: str
    supports_tools: bool = True

    @abstractmethod
    def list_models(
        self, api_key: Optional[str] = None, base_url: Optional[str] = None
    ) -> List[ModelInfo]:
        """List models supported by this provider."""
        pass

    @abstractmethod
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
        """Execute a chat completion request and normalize response."""
        pass

    @abstractmethod
    def test_connection(
        self, api_key: Optional[str] = None, base_url: Optional[str] = None
    ) -> Dict[str, Any]:
        """Test provider connectivity and credentials.

        Returns:
            {"ok": bool, "model_count": int, "error": Optional[str]}
        """
        pass
