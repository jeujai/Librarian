"""
AI Service — DeepSeek-backed (Gemini removed).

This module used to be the Gemini-only AI provider. Gemini has been removed;
chat is served by ``DeepSeekAIService``. The shared response types
(``AIResponse``, ``AIProvider``) live in ``ai_types`` and are re-exported here
so existing importers keep working, and ``AIService`` is retained as a name
alias for ``DeepSeekAIService`` for the remaining type-hint and fallback
call sites (recovery manager, minimal server, CachedAIService).
"""

from .ai_types import AIProvider, AIResponse
from .deepseek_ai_service import DeepSeekAIService

# ``AIService`` is kept as an alias so that existing ``from ...ai_service
# import AIService`` imports and ``AIService()`` instantiations continue to
# resolve to the DeepSeek implementation without touching every call site.
AIService = DeepSeekAIService

__all__ = ["AIService", "AIProvider", "AIResponse"]
