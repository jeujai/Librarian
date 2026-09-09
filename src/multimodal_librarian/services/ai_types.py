"""
Shared AI data types used across providers.

These types are provider-agnostic and must not import any specific provider
implementation. They live in their own module so that both ``ai_service``
(compatibility surface) and ``deepseek_ai_service`` can import them without
creating an import cycle.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Optional


class AIProvider(str, Enum):
    """Supported AI providers."""

    DEEPSEEK = "deepseek"
    OPENAI = "openai"
    ANTHROPIC = "anthropic"


@dataclass
class AIResponse:
    """Standardized AI response format."""

    content: str
    provider: str
    model: str
    tokens_used: int
    processing_time_ms: int
    confidence_score: float = 1.0
    metadata: Optional[Dict[str, Any]] = None

    def __post_init__(self) -> None:
        if self.metadata is None:
            self.metadata = {}
