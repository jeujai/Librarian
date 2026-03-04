"""
Conversation Cache Service - Enhanced conversation management with caching

This service provides intelligent caching for conversation context, summaries,
and user session data to improve chat performance and reduce AI API calls.
"""

import hashlib
import json
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from dataclasses import dataclass

from .cache_service import get_cache_service, CacheType, CacheService
from .ai_service_cached import get_cached_ai_service

logger = logging.getLogger(__name__)

@dataclass
class CachedConversationSummary:
    """Cached conversation summary with metadata."""
    user_id: str
    summary: str
    message_count: int
    created_at: datetime
    updated_at: datetime
    importance_score: float
    key_topics: List[str]
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}

@dataclass
class CachedContextWindow:
    """Cached conversation context window."""
    user_id: str
    connection_id: str
    messages: List[Dict[str, Any]]
    summary: Optional[str]
    created_at: datetime
    last_updated: datetime
    total_tokens: int
    importance_scores: List[float]

class ConversationCacheService:
    """
    Enhanced conversation caching service for performance optimization.
    
    Features:
    - Conversation summary caching
    - Context window caching
    - User session data caching
    - Intelligent cache invalidation
    - Performance metrics tracking
    """
    
    def __init__(self):
        """Initialize conversation cache service."""
        self.cache_service: Optional[CacheService] = None
        self.ai_service = get_cached_ai_service()
        self._cache_initialized = False
        
        # Cache configuration
        self.summary_cache_ttl = 7200      # 2 hours
        self.context_cache_ttl = 3600      # 1 hour
        self.session_cache_ttl = 1800      # 30 minutes
        
        # Performance tracking
        self.cache_stats = {
            'summary_hits': 0,
            'summary_misses': 0,
            'context_hits': 0,
            'context_misses': 0,
            'session_hits': 0,
            'session_misses': 0,
            'ai_calls_saved': 0
        }
        
        logger.info("Conversation cache service initialized")
    
    async def _ensure_cache_initialized(self):
        """Ensure cache service is initialized."""
        if not self._cache_initialized:
            try:
                self.cache_service = await get_cache_service()
                self._cache_initialized = True
                logger.info("Cache service connected for conversation operations")
            except Exception as e:
                logger.warning(f"Failed to initialize cache service: {e}")
                self.cache_service = None
    
    def _generate_summary_cache_key(self, user_id: str) -> str:
        """Generate cache key for conversation summary."""
        return f"summary:{user_id}"
    
    def _generate_context_cache_key(self, user_id: str, connection_id: str) -> str:
        """Generate cache key for context window."""
        return f"context:{user_id}:{connection_id}"
    
    def _generate_session_cache_key(self, user_id: str, session_type: str = "default") -> str:
        """Generate cache key for session data."""
        return f"session:{user_id}:{session_type}"
    
    async def get_conversation_summary(
        self, 
        user_id: str,
        force_refresh: bool = False
    ) -> Optional[CachedConversationSummary]:
        """
        Get cached conversation summary for user.
        
        Args:
            user_id: User identifier
            force_refresh: Force refresh from database
            
        Returns:
            Cached conversation summary or None
        """
        await self._ensure_cache_initialized()
        
        if not self.cache_service or force_refresh:
            return None
        
        try:
            cache_key = self._generate_summary_cache_key(user_id)
            
            cached_summary = await self.cache_service.get(
                CacheType.CONVERSATION,
                cache_key
            )
            
            if cached_summary is not None:
                self.cache_stats['summary_hits'] += 1
                logger.debug(f"Conversation summary cache hit for user {user_id}")
                return cached_summary
            
            self.cache_stats['summary_misses'] += 1
            return None
            
        except Exception as e:
            logger.error(f"Failed to get conversation summary from cache: {e}")
            return None
    
    async def set_conversation_summary(
        self, 
        user_id: str, 
        summary: str,
        message_count: int,
        importance_score: float = 0.5,
        key_topics: Optional[List[str]] = None
    ) -> bool:
        """
        Cache conversation summary for user.
        
        Args:
            user_id: User identifier
            summary: Conversation summary text
            message_count: Number of messages summarized
            importance_score: Importance score (0.0 to 1.0)
            key_topics: List of key topics discussed
            
        Returns:
            True if successful, False otherwise
        """
        await self._ensure_cache_initialized()
        
        if not self.cache_service:
            return False
        
        try:
            cache_key = self._generate_summary_cache_key(user_id)
            
            cached_summary = CachedConversationSummary(
                user_id=user_id,
                summary=summary,
                message_count=message_count,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
                importance_score=importance_score,
                key_topics=key_topics or [],
                metadata={
                    "cache_version": "1.0",
                    "generated_by": "conversation_cache_service"
                }
            )
            
            success = await self.cache_service.set(
                CacheType.CONVERSATION,
                cache_key,
                cached_summary,
                ttl=self.summary_cache_ttl
            )
            
            if success:
                logger.debug(f"Cached conversation summary for user {user_id}")
            
            return success
            
        except Exception as e:
            logger.error(f"Failed to cache conversation summary: {e}")
            return False
    
    async def get_context_window(
        self, 
        user_id: str, 
        connection_id: str
    ) -> Optional[CachedContextWindow]:
        """
        Get cached context window for user session.
        
        Args:
            user_id: User identifier
            connection_id: Connection identifier
            
        Returns:
            Cached context window or None
        """
        await self._ensure_cache_initialized()
        
        if not self.cache_service:
            return None
        
        try:
            cache_key = self._generate_context_cache_key(user_id, connection_id)
            
            cached_context = await self.cache_service.get(
                CacheType.CONVERSATION,
                cache_key
            )
            
            if cached_context is not None:
                self.cache_stats['context_hits'] += 1
                logger.debug(f"Context window cache hit for user {user_id}")
                return cached_context
            
            self.cache_stats['context_misses'] += 1
            return None
            
        except Exception as e:
            logger.error(f"Failed to get context window from cache: {e}")
            return None
    
    async def set_context_window(
        self, 
        user_id: str, 
        connection_id: str,
        messages: List[Dict[str, Any]],
        summary: Optional[str] = None,
        total_tokens: int = 0,
        importance_scores: Optional[List[float]] = None
    ) -> bool:
        """
        Cache context window for user session.
        
        Args:
            user_id: User identifier
            connection_id: Connection identifier
            messages: List of conversation messages
            summary: Optional conversation summary
            total_tokens: Total token count
            importance_scores: Importance scores for messages
            
        Returns:
            True if successful, False otherwise
        """
        await self._ensure_cache_initialized()
        
        if not self.cache_service:
            return False
        
        try:
            cache_key = self._generate_context_cache_key(user_id, connection_id)
            
            cached_context = CachedContextWindow(
                user_id=user_id,
                connection_id=connection_id,
                messages=messages,
                summary=summary,
                created_at=datetime.utcnow(),
                last_updated=datetime.utcnow(),
                total_tokens=total_tokens,
                importance_scores=importance_scores or []
            )
            
            success = await self.cache_service.set(
                CacheType.CONVERSATION,
                cache_key,
                cached_context,
                ttl=self.context_cache_ttl
            )
            
            if success:
                logger.debug(f"Cached context window for user {user_id}")
            
            return success
            
        except Exception as e:
            logger.error(f"Failed to cache context window: {e}")
            return False
    
    async def generate_and_cache_summary(
        self,
        user_id: str,
        messages: List[Dict[str, Any]],
        force_regenerate: bool = False
    ) -> Optional[str]:
        """
        Generate and cache conversation summary using AI.
        
        Args:
            user_id: User identifier
            messages: List of conversation messages
            force_regenerate: Force regeneration even if cached
            
        Returns:
            Generated summary or None
        """
        await self._ensure_cache_initialized()
        
        # Check for existing summary first
        if not force_regenerate:
            existing_summary = await self.get_conversation_summary(user_id)
            if existing_summary and existing_summary.message_count >= len(messages) - 5:
                # Use existing summary if it's recent enough
                return existing_summary.summary
        
        if len(messages) < 3:
            return None  # Not enough messages to summarize
        
        try:
            # Prepare conversation text for summarization
            conversation_text = "\n".join([
                f"{msg.get('role', 'user')}: {msg.get('content', '')}"
                for msg in messages[-20:]  # Last 20 messages
            ])
            
            # Generate summary using AI
            summary_prompt = [
                {
                    "role": "user",
                    "content": f"""Please provide a concise summary of this conversation, focusing on:
1. Main topics discussed
2. Key questions asked
3. Important information shared
4. User's primary interests or needs

Conversation:
{conversation_text}

Provide a summary in 2-3 sentences that captures the essence of the conversation."""
                }
            ]
            
            ai_response = await self.ai_service.generate_response(
                messages=summary_prompt,
                temperature=0.3,
                max_tokens=200
            )
            
            if ai_response and ai_response.content:
                summary = ai_response.content.strip()
                
                # Extract key topics (simple keyword extraction)
                key_topics = self._extract_key_topics(conversation_text)
                
                # Calculate importance score based on message length and content
                importance_score = self._calculate_importance_score(messages)
                
                # Cache the summary
                await self.set_conversation_summary(
                    user_id=user_id,
                    summary=summary,
                    message_count=len(messages),
                    importance_score=importance_score,
                    key_topics=key_topics
                )
                
                self.cache_stats['ai_calls_saved'] += 1
                logger.info(f"Generated and cached conversation summary for user {user_id}")
                
                return summary
            
        except Exception as e:
            logger.error(f"Failed to generate conversation summary: {e}")
        
        return None
    
    def _extract_key_topics(self, conversation_text: str) -> List[str]:
        """Extract key topics from conversation text."""
        # Simple keyword extraction
        common_words = {
            'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 
            'of', 'with', 'by', 'is', 'are', 'was', 'were', 'be', 'been', 'being',
            'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could', 
            'should', 'can', 'may', 'might', 'must', 'shall', 'this', 'that',
            'these', 'those', 'i', 'you', 'he', 'she', 'it', 'we', 'they',
            'me', 'him', 'her', 'us', 'them', 'my', 'your', 'his', 'her', 'its',
            'our', 'their', 'what', 'when', 'where', 'why', 'how', 'who'
        }
        
        words = conversation_text.lower().split()
        word_freq = {}
        
        for word in words:
            clean_word = word.strip('.,!?;:"()[]{}').lower()
            if len(clean_word) > 3 and clean_word not in common_words:
                word_freq[clean_word] = word_freq.get(clean_word, 0) + 1
        
        # Get top 5 most frequent words as key topics
        sorted_words = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)
        return [word for word, freq in sorted_words[:5] if freq > 1]
    
    def _calculate_importance_score(self, messages: List[Dict[str, Any]]) -> float:
        """Calculate importance score for conversation."""
        if not messages:
            return 0.0
        
        score = 0.5  # Base score
        
        # Increase score for longer conversations
        if len(messages) > 10:
            score += 0.2
        elif len(messages) > 5:
            score += 0.1
        
        # Increase score for messages with questions
        question_count = sum(1 for msg in messages if '?' in msg.get('content', ''))
        score += min(question_count * 0.05, 0.2)
        
        # Increase score for longer messages (more detailed)
        avg_length = sum(len(msg.get('content', '')) for msg in messages) / len(messages)
        if avg_length > 100:
            score += 0.1
        
        return max(0.1, min(1.0, score))
    
    async def invalidate_user_cache(self, user_id: str) -> Dict[str, int]:
        """
        Invalidate all cached data for a user.
        
        Args:
            user_id: User identifier
            
        Returns:
            Dictionary with invalidation results
        """
        await self._ensure_cache_initialized()
        
        if not self.cache_service:
            return {"error": "Cache service not available"}
        
        results = {"invalidated": 0, "types": []}
        
        try:
            # Invalidate summary
            summary_key = self._generate_summary_cache_key(user_id)
            if await self.cache_service.delete(CacheType.CONVERSATION, summary_key):
                results["invalidated"] += 1
                results["types"].append("summary")
            
            # Note: Context windows have connection_id, so we can't easily invalidate all
            # This would require a more sophisticated cache key pattern or separate tracking
            
            logger.info(f"Invalidated {results['invalidated']} cache entries for user {user_id}")
            
        except Exception as e:
            logger.error(f"Cache invalidation failed for user {user_id}: {e}")
            results["error"] = str(e)
        
        return results
    
    async def get_session_data(
        self, 
        user_id: str, 
        session_type: str = "default"
    ) -> Optional[Dict[str, Any]]:
        """
        Get cached session data for user.
        
        Args:
            user_id: User identifier
            session_type: Type of session data
            
        Returns:
            Cached session data or None
        """
        await self._ensure_cache_initialized()
        
        if not self.cache_service:
            return None
        
        try:
            cache_key = self._generate_session_cache_key(user_id, session_type)
            
            session_data = await self.cache_service.get(
                CacheType.CONVERSATION,
                cache_key
            )
            
            if session_data is not None:
                self.cache_stats['session_hits'] += 1
                logger.debug(f"Session data cache hit for user {user_id}")
                return session_data
            
            self.cache_stats['session_misses'] += 1
            return None
            
        except Exception as e:
            logger.error(f"Failed to get session data from cache: {e}")
            return None
    
    async def set_session_data(
        self, 
        user_id: str, 
        session_data: Dict[str, Any],
        session_type: str = "default"
    ) -> bool:
        """
        Cache session data for user.
        
        Args:
            user_id: User identifier
            session_data: Session data to cache
            session_type: Type of session data
            
        Returns:
            True if successful, False otherwise
        """
        await self._ensure_cache_initialized()
        
        if not self.cache_service:
            return False
        
        try:
            cache_key = self._generate_session_cache_key(user_id, session_type)
            
            # Add metadata
            enhanced_data = {
                **session_data,
                "_cache_metadata": {
                    "cached_at": datetime.utcnow().isoformat(),
                    "cache_version": "1.0"
                }
            }
            
            success = await self.cache_service.set(
                CacheType.CONVERSATION,
                cache_key,
                enhanced_data,
                ttl=self.session_cache_ttl
            )
            
            if success:
                logger.debug(f"Cached session data for user {user_id}")
            
            return success
            
        except Exception as e:
            logger.error(f"Failed to cache session data: {e}")
            return False
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Get conversation cache statistics."""
        total_summary = self.cache_stats['summary_hits'] + self.cache_stats['summary_misses']
        total_context = self.cache_stats['context_hits'] + self.cache_stats['context_misses']
        total_session = self.cache_stats['session_hits'] + self.cache_stats['session_misses']
        
        return {
            "cache_initialized": self._cache_initialized,
            "summary_cache": {
                "hits": self.cache_stats['summary_hits'],
                "misses": self.cache_stats['summary_misses'],
                "hit_rate": round(self.cache_stats['summary_hits'] / max(1, total_summary), 3),
                "ttl_seconds": self.summary_cache_ttl
            },
            "context_cache": {
                "hits": self.cache_stats['context_hits'],
                "misses": self.cache_stats['context_misses'],
                "hit_rate": round(self.cache_stats['context_hits'] / max(1, total_context), 3),
                "ttl_seconds": self.context_cache_ttl
            },
            "session_cache": {
                "hits": self.cache_stats['session_hits'],
                "misses": self.cache_stats['session_misses'],
                "hit_rate": round(self.cache_stats['session_hits'] / max(1, total_session), 3),
                "ttl_seconds": self.session_cache_ttl
            },
            "performance": {
                "total_requests": total_summary + total_context + total_session,
                "total_hits": (self.cache_stats['summary_hits'] + 
                              self.cache_stats['context_hits'] + 
                              self.cache_stats['session_hits']),
                "overall_hit_rate": round(
                    (self.cache_stats['summary_hits'] + 
                     self.cache_stats['context_hits'] + 
                     self.cache_stats['session_hits']) / 
                    max(1, total_summary + total_context + total_session), 3
                ),
                "ai_calls_saved": self.cache_stats['ai_calls_saved']
            }
        }
    
    async def health_check(self) -> Dict[str, Any]:
        """Perform conversation cache service health check."""
        await self._ensure_cache_initialized()
        
        health_data = {
            "status": "healthy" if self._cache_initialized else "unhealthy",
            "cache_initialized": self._cache_initialized,
            "features": {
                "conversation_summary_caching": True,
                "context_window_caching": True,
                "session_data_caching": True,
                "ai_powered_summarization": True,
                "intelligent_cache_invalidation": True
            },
            "cache_stats": self.get_cache_stats()
        }
        
        if self.cache_service:
            cache_health = await self.cache_service.health_check()
            health_data["cache_service"] = cache_health
        
        return health_data

# Global conversation cache service instance
_conversation_cache_service = None

def get_conversation_cache_service() -> ConversationCacheService:
    """Get global conversation cache service instance."""
    global _conversation_cache_service
    if _conversation_cache_service is None:
        _conversation_cache_service = ConversationCacheService()
    return _conversation_cache_service