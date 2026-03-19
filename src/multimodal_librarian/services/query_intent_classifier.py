"""
Query Intent Classifier for Librarian

Classifies user queries to determine if they require full RAG pipeline
(knowledge queries) or can be handled with a direct LLM response (conversational).

This prevents irrelevant citations for purely conversational messages like
"Good Morning!" or "Thanks!" that don't need document retrieval.
"""

import logging
import re
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional

logger = logging.getLogger(__name__)


class QueryIntent(Enum):
    """Classification of user query intent."""
    CONVERSATIONAL = "conversational"  # Greetings, acknowledgments, meta-questions
    KNOWLEDGE = "knowledge"            # Questions requiring document retrieval


@dataclass
class IntentClassification:
    """Result of intent classification."""
    intent: QueryIntent
    confidence: float  # 0.0 to 1.0
    reason: str
    matched_pattern: Optional[str] = None


class QueryIntentClassifier:
    """
    Classifies user queries to determine appropriate response strategy.
    
    Uses fast heuristic patterns first, with optional LLM fallback for
    ambiguous cases. This allows conversational messages to bypass the
    full RAG pipeline and get direct LLM responses.
    """
    
    # Greeting patterns - high confidence conversational
    GREETING_PATTERNS = [
        r'^(hi|hello|hey|howdy|hiya|yo)[\s!.,?]*$',
        r'^good\s+(morning|afternoon|evening|night)[\s!.,?]*$',
        r'^(greetings|salutations)[\s!.,?]*$',
        r'^what\'?s\s+up[\s!.,?]*$',
        r'^sup[\s!.,?]*$',
    ]
    
    # Acknowledgment patterns - high confidence conversational
    ACKNOWLEDGMENT_PATTERNS = [
        r'^(thanks|thank\s+you|thx|ty)[\s!.,?]*$',
        r'^(ok|okay|k|got\s+it|understood|i\s+see)[\s!.,?]*$',
        r'^(great|awesome|perfect|excellent|nice|cool)[\s!.,?]*$',
        r'^(yes|yeah|yep|yup|no|nope|nah)[\s!.,?]*$',
        r'^(sure|alright|right)[\s!.,?]*$',
    ]
    
    # Farewell patterns - high confidence conversational
    FAREWELL_PATTERNS = [
        r'^(bye|goodbye|see\s+you|later|cya)[\s!.,?]*$',
        r'^(good\s*bye|take\s+care)[\s!.,?]*$',
        r'^(have\s+a\s+(good|nice|great)\s+(day|one))[\s!.,?]*$',
    ]
    
    # Meta-questions about the assistant - conversational
    META_PATTERNS = [
        r'^(who|what)\s+are\s+you[\s!.,?]*$',
        r'^what\s+is\s+your\s+name[\s!.,?]*$',
        r'^what\'?s\s+your\s+name[\s!.,?]*$',
        r'^(do\s+you\s+have\s+a\s+name)[\s!.,?]*$',
        r'^(how\s+are\s+you|how\'?s\s+it\s+going)[\s!.,?]*$',
        r'^what\s+can\s+you\s+do[\s!.,?]*$',
        r'^(help|help\s+me)[\s!.,?]*$',
        r'^are\s+you\s+(there|alive|awake|real)[\s!.,?]*$',
        r'^(tell\s+me\s+about\s+yourself)[\s!.,?]*$',
        r'^(who\s+made\s+you|who\s+created\s+you|who\s+built\s+you)[\s!.,?]*$',
    ]
    
    # Small talk patterns - conversational
    SMALL_TALK_PATTERNS = [
        r'^(lol|haha|hehe|lmao)[\s!.,?]*$',
        r'^(wow|whoa|oh|ah|hmm|hm)[\s!.,?]*$',
        r'^(interesting|i\s+see|makes\s+sense)[\s!.,?]*$',
        r'^\?+$',  # Just question marks
        r'^\.+$',  # Just periods
    ]
    
    # Knowledge query indicators - these suggest RAG is needed
    KNOWLEDGE_INDICATORS = [
        r'\b(what|who|where|when|why|how|which|whose)\b.*\?',  # WH-questions
        r'\b(explain|describe|tell\s+me\s+about|summarize)\b',
        r'\b(define|definition\s+of)\b',
        r'\b(compare|contrast|difference\s+between)\b',
        r'\b(according\s+to|based\s+on|in\s+the)\b',
        r'\b(document|book|paper|article|chapter|section|page)\b',
        r'\b(find|search|look\s+up|locate)\b',
        r'\b(quote|citation|reference|source)\b',
    ]
    
    def __init__(self, use_llm_fallback: bool = False, ai_service=None):
        """
        Initialize the intent classifier.
        
        Args:
            use_llm_fallback: Whether to use LLM for ambiguous cases
            ai_service: AI service for LLM fallback (required if use_llm_fallback=True)
        """
        self.use_llm_fallback = use_llm_fallback
        self.ai_service = ai_service
        
        # Compile all patterns for efficiency
        self._greeting_re = [re.compile(p, re.IGNORECASE) for p in self.GREETING_PATTERNS]
        self._ack_re = [re.compile(p, re.IGNORECASE) for p in self.ACKNOWLEDGMENT_PATTERNS]
        self._farewell_re = [re.compile(p, re.IGNORECASE) for p in self.FAREWELL_PATTERNS]
        self._meta_re = [re.compile(p, re.IGNORECASE) for p in self.META_PATTERNS]
        self._small_talk_re = [re.compile(p, re.IGNORECASE) for p in self.SMALL_TALK_PATTERNS]
        self._knowledge_re = [re.compile(p, re.IGNORECASE) for p in self.KNOWLEDGE_INDICATORS]
    
    def _check_patterns(
        self, 
        query: str, 
        patterns: List[re.Pattern], 
        category: str
    ) -> Optional[IntentClassification]:
        """Check if query matches any pattern in the list."""
        for pattern in patterns:
            if pattern.search(query):
                return IntentClassification(
                    intent=QueryIntent.CONVERSATIONAL,
                    confidence=0.95,
                    reason=f"Matched {category} pattern",
                    matched_pattern=pattern.pattern
                )
        return None
    
    def _has_knowledge_indicators(self, query: str) -> bool:
        """Check if query has indicators suggesting knowledge retrieval is needed."""
        for pattern in self._knowledge_re:
            if pattern.search(query):
                return True
        return False
    
    async def classify(self, query: str) -> IntentClassification:
        """
        Classify the intent of a user query.
        
        Args:
            query: The user's message
            
        Returns:
            IntentClassification with intent type, confidence, and reason
        """
        # Normalize query
        query_clean = query.strip()
        query_lower = query_clean.lower()
        
        # Very short queries (1-2 words) are likely conversational
        word_count = len(query_clean.split())
        
        # Check greeting patterns
        result = self._check_patterns(query_clean, self._greeting_re, "greeting")
        if result:
            logger.debug(f"Query '{query_clean}' classified as greeting")
            return result
        
        # Check acknowledgment patterns
        result = self._check_patterns(query_clean, self._ack_re, "acknowledgment")
        if result:
            logger.debug(f"Query '{query_clean}' classified as acknowledgment")
            return result
        
        # Check farewell patterns
        result = self._check_patterns(query_clean, self._farewell_re, "farewell")
        if result:
            logger.debug(f"Query '{query_clean}' classified as farewell")
            return result
        
        # Check meta-questions
        result = self._check_patterns(query_clean, self._meta_re, "meta-question")
        if result:
            logger.debug(f"Query '{query_clean}' classified as meta-question")
            return result
        
        # Check small talk
        result = self._check_patterns(query_clean, self._small_talk_re, "small talk")
        if result:
            logger.debug(f"Query '{query_clean}' classified as small talk")
            return result
        
        # Check for knowledge indicators
        if self._has_knowledge_indicators(query_clean):
            logger.debug(f"Query '{query_clean}' has knowledge indicators")
            return IntentClassification(
                intent=QueryIntent.KNOWLEDGE,
                confidence=0.9,
                reason="Contains knowledge query indicators"
            )
        
        # Very short queries without knowledge indicators are likely conversational
        if word_count <= 2:
            logger.debug(f"Query '{query_clean}' is very short, treating as conversational")
            return IntentClassification(
                intent=QueryIntent.CONVERSATIONAL,
                confidence=0.7,
                reason="Very short query without knowledge indicators"
            )
        
        # Default: assume knowledge query for longer messages
        # This is the safe default - better to search and find nothing
        # than to skip search for a legitimate question
        logger.debug(f"Query '{query_clean}' defaulting to knowledge query")
        return IntentClassification(
            intent=QueryIntent.KNOWLEDGE,
            confidence=0.6,
            reason="Default classification for substantive query"
        )


# Singleton instance for reuse
_classifier_instance: Optional[QueryIntentClassifier] = None


def get_intent_classifier() -> QueryIntentClassifier:
    """Get or create the singleton intent classifier instance."""
    global _classifier_instance
    if _classifier_instance is None:
        _classifier_instance = QueryIntentClassifier()
    return _classifier_instance
