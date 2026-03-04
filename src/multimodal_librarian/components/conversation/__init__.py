"""
Conversation Management Component.

This component handles conversation threads, message processing, and conversion
of conversational content into knowledge chunks equivalent to book content.
"""

from .conversation_manager import (
    ConversationManager, ConversationContext, MultimediaInput, ProcessedInput
)
from .context_processor import (
    ContextProcessor, ConversationFlow, ConversationDocument, TemporalChunk
)

__all__ = [
    "ConversationManager", "ConversationContext", "MultimediaInput", "ProcessedInput",
    "ContextProcessor", "ConversationFlow", "ConversationDocument", "TemporalChunk"
]