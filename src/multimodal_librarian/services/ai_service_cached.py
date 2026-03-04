"""
Cached AI Service - Enhanced AI service with comprehensive caching

This service extends the base AI service with intelligent caching for embeddings,
responses, and other AI operations to dramatically improve performance and reduce costs.
"""

import hashlib
import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from .ai_service import AIProvider, AIResponse, AIService
from .cache_service import CacheService, CacheType, get_cache_service

logger = logging.getLogger(__name__)

class CachedAIService(AIService):
    """
    Enhanced AI service with comprehensive caching capabilities.
    
    Features:
    - Embedding caching with content-based keys
    - Response caching for similar queries
    - Provider-specific caching strategies
    - Cache warming and precomputation
    - Cost optimization through cache hits
    """
    
    def __init__(self):
        """Initialize cached AI service."""
        super().__init__()
        self.cache_service: Optional[CacheService] = None
        self._cache_initialized = False
        
        # Cache configuration
        self.embedding_cache_ttl = 86400  # 24 hours
        self.response_cache_ttl = 1800    # 30 minutes
        self.enable_response_cache = True
        self.enable_embedding_cache = True
        
        # Performance tracking
        self.cache_stats = {
            'embedding_hits': 0,
            'embedding_misses': 0,
            'response_hits': 0,
            'response_misses': 0,
            'total_cost_saved': 0.0
        }
        
        logger.info("Cached AI service initialized")
    
    async def _ensure_cache_initialized(self):
        """Ensure cache service is initialized."""
        if not self._cache_initialized:
            try:
                self.cache_service = await get_cache_service()
                self._cache_initialized = True
                logger.info("Cache service connected for AI operations")
            except Exception as e:
                logger.warning(f"Failed to initialize cache service: {e}")
                self.cache_service = None
    
    def _generate_embedding_cache_key(self, texts: List[str], provider: str) -> str:
        """Generate cache key for embeddings."""
        # Create deterministic key based on content and provider
        content_hash = hashlib.sha256(
            json.dumps(sorted(texts), ensure_ascii=False).encode()
        ).hexdigest()[:16]
        
        return f"{provider}:{content_hash}"
    
    def _generate_response_cache_key(
        self, 
        messages: List[Dict[str, str]], 
        context: Optional[str],
        provider: str,
        temperature: float,
        max_tokens: int
    ) -> str:
        """Generate cache key for AI responses."""
        # Create deterministic key based on all parameters
        cache_data = {
            'messages': messages,
            'context': context,
            'provider': provider,
            'temperature': temperature,
            'max_tokens': max_tokens
        }
        
        content_hash = hashlib.sha256(
            json.dumps(cache_data, sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest()[:16]
        
        return f"{provider}:response:{content_hash}"
    
    async def generate_embeddings(
        self, 
        texts: List[str],
        preferred_provider: Optional[AIProvider] = None
    ) -> List[List[float]]:
        """Generate embeddings with caching support."""
        if not self.enable_embedding_cache:
            return await super().generate_embeddings(texts, preferred_provider)
        
        await self._ensure_cache_initialized()
        
        # Determine provider
        provider_name = "unknown"
        if preferred_provider and preferred_provider in self.providers:
            provider_name = preferred_provider.value
        elif self.primary_provider:
            provider_name = self.primary_provider.value
        
        # Generate cache key
        cache_key = self._generate_embedding_cache_key(texts, provider_name)
        
        # Try to get from cache
        if self.cache_service:
            try:
                cached_embeddings = await self.cache_service.get(
                    CacheType.EMBEDDING, 
                    cache_key
                )
                
                if cached_embeddings is not None:
                    self.cache_stats['embedding_hits'] += 1
                    logger.debug(f"Embedding cache hit for {len(texts)} texts")
                    return cached_embeddings
                    
            except Exception as e:
                logger.warning(f"Embedding cache get failed: {e}")
        
        # Cache miss - generate embeddings
        self.cache_stats['embedding_misses'] += 1
        
        try:
            embeddings = await super().generate_embeddings(texts, preferred_provider)
            
            # Cache the results
            if self.cache_service and embeddings:
                try:
                    await self.cache_service.set(
                        CacheType.EMBEDDING,
                        cache_key,
                        embeddings,
                        ttl=self.embedding_cache_ttl
                    )
                    logger.debug(f"Cached embeddings for {len(texts)} texts")
                    
                except Exception as e:
                    logger.warning(f"Embedding cache set failed: {e}")
            
            return embeddings
            
        except Exception as e:
            logger.error(f"Embedding generation failed: {e}")
            raise
    
    async def generate_response(
        self, 
        messages: List[Dict[str, str]], 
        context: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        preferred_provider: Optional[AIProvider] = None
    ) -> AIResponse:
        """Generate AI response with caching support."""
        if not self.enable_response_cache:
            return await super().generate_response(
                messages, context, temperature, max_tokens, preferred_provider
            )
        
        await self._ensure_cache_initialized()
        
        # Determine provider
        provider_name = "unknown"
        if preferred_provider and preferred_provider in self.providers:
            provider_name = preferred_provider.value
        elif self.primary_provider:
            provider_name = self.primary_provider.value
        
        # Generate cache key
        cache_key = self._generate_response_cache_key(
            messages, context, provider_name, temperature, max_tokens
        )
        
        # Try to get from cache
        if self.cache_service:
            try:
                cached_response = await self.cache_service.get(
                    CacheType.AI_RESPONSE, 
                    cache_key
                )
                
                if cached_response is not None:
                    self.cache_stats['response_hits'] += 1
                    logger.debug(f"AI response cache hit for provider {provider_name}")
                    
                    # Add cache metadata
                    cached_response.metadata = cached_response.metadata or {}
                    cached_response.metadata['cached'] = True
                    cached_response.metadata['cache_hit_time'] = datetime.utcnow().isoformat()
                    
                    return cached_response
                    
            except Exception as e:
                logger.warning(f"AI response cache get failed: {e}")
        
        # Cache miss - generate response
        self.cache_stats['response_misses'] += 1
        
        try:
            response = await super().generate_response(
                messages, context, temperature, max_tokens, preferred_provider
            )
            
            # Cache the response (only if successful)
            if self.cache_service and response and response.content:
                try:
                    # Add cache metadata
                    response.metadata = response.metadata or {}
                    response.metadata['cached'] = False
                    response.metadata['cache_set_time'] = datetime.utcnow().isoformat()
                    
                    await self.cache_service.set(
                        CacheType.AI_RESPONSE,
                        cache_key,
                        response,
                        ttl=self.response_cache_ttl
                    )
                    logger.debug(f"Cached AI response for provider {provider_name}")
                    
                except Exception as e:
                    logger.warning(f"AI response cache set failed: {e}")
            
            return response
            
        except Exception as e:
            logger.error(f"AI response generation failed: {e}")
            raise
    
    async def batch_generate_embeddings(
        self,
        text_batches: List[List[str]],
        preferred_provider: Optional[AIProvider] = None
    ) -> List[List[List[float]]]:
        """
        Generate embeddings for multiple batches with intelligent caching.
        
        Args:
            text_batches: List of text batches to process
            preferred_provider: Preferred AI provider
            
        Returns:
            List of embedding batches
        """
        await self._ensure_cache_initialized()
        
        results = []
        cache_hits = 0
        cache_misses = 0
        
        for batch in text_batches:
            try:
                embeddings = await self.generate_embeddings(batch, preferred_provider)
                results.append(embeddings)
                
                # Track cache performance (approximate)
                if self.cache_service:
                    cache_hits += 1 if len(embeddings) > 0 else 0
                
            except Exception as e:
                logger.error(f"Batch embedding generation failed: {e}")
                results.append([])
                cache_misses += 1
        
        logger.info(f"Batch embeddings: {cache_hits} cache hits, {cache_misses} misses")
        return results
    
    async def warm_embedding_cache(
        self,
        common_texts: List[str],
        providers: Optional[List[AIProvider]] = None
    ) -> Dict[str, int]:
        """
        Warm the embedding cache with commonly used texts.
        
        Args:
            common_texts: List of texts to pre-cache
            providers: List of providers to cache for (defaults to all available)
            
        Returns:
            Dictionary with cache warming results
        """
        await self._ensure_cache_initialized()
        
        if not self.cache_service:
            return {"error": "Cache service not available"}
        
        if providers is None:
            providers = list(self.providers.keys())
        
        results = {
            "texts_processed": 0,
            "embeddings_cached": 0,
            "errors": 0,
            "providers": []
        }
        
        for provider in providers:
            if provider not in self.providers:
                continue
                
            provider_results = {
                "provider": provider.value,
                "cached": 0,
                "errors": 0
            }
            
            try:
                # Generate embeddings for all texts
                embeddings = await self.generate_embeddings(common_texts, provider)
                
                if embeddings:
                    provider_results["cached"] = len(embeddings)
                    results["embeddings_cached"] += len(embeddings)
                    
            except Exception as e:
                logger.error(f"Cache warming failed for provider {provider.value}: {e}")
                provider_results["errors"] += 1
                results["errors"] += 1
            
            results["providers"].append(provider_results)
        
        results["texts_processed"] = len(common_texts)
        
        logger.info(f"Cache warming completed: {results['embeddings_cached']} embeddings cached")
        return results
    
    async def clear_ai_cache(self, cache_type: Optional[str] = None) -> Dict[str, int]:
        """
        Clear AI-related cache entries.
        
        Args:
            cache_type: Type of cache to clear ('embedding', 'response', or None for both)
            
        Returns:
            Dictionary with clearing results
        """
        await self._ensure_cache_initialized()
        
        if not self.cache_service:
            return {"error": "Cache service not available"}
        
        results = {"cleared": 0, "types": []}
        
        try:
            if cache_type is None or cache_type == "embedding":
                embedding_cleared = await self.cache_service.clear_by_type(CacheType.EMBEDDING)
                results["cleared"] += embedding_cleared
                results["types"].append(f"embedding: {embedding_cleared}")
            
            if cache_type is None or cache_type == "response":
                response_cleared = await self.cache_service.clear_by_type(CacheType.AI_RESPONSE)
                results["cleared"] += response_cleared
                results["types"].append(f"response: {response_cleared}")
            
            logger.info(f"Cleared {results['cleared']} AI cache entries")
            
        except Exception as e:
            logger.error(f"AI cache clearing failed: {e}")
            results["error"] = str(e)
        
        return results
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Get AI service cache statistics."""
        total_embedding_requests = self.cache_stats['embedding_hits'] + self.cache_stats['embedding_misses']
        total_response_requests = self.cache_stats['response_hits'] + self.cache_stats['response_misses']
        
        embedding_hit_rate = (
            self.cache_stats['embedding_hits'] / total_embedding_requests 
            if total_embedding_requests > 0 else 0.0
        )
        
        response_hit_rate = (
            self.cache_stats['response_hits'] / total_response_requests 
            if total_response_requests > 0 else 0.0
        )
        
        return {
            "cache_enabled": {
                "embeddings": self.enable_embedding_cache,
                "responses": self.enable_response_cache
            },
            "cache_initialized": self._cache_initialized,
            "embedding_cache": {
                "hits": self.cache_stats['embedding_hits'],
                "misses": self.cache_stats['embedding_misses'],
                "hit_rate": round(embedding_hit_rate, 3),
                "ttl_seconds": self.embedding_cache_ttl
            },
            "response_cache": {
                "hits": self.cache_stats['response_hits'],
                "misses": self.cache_stats['response_misses'],
                "hit_rate": round(response_hit_rate, 3),
                "ttl_seconds": self.response_cache_ttl
            },
            "performance": {
                "total_requests": total_embedding_requests + total_response_requests,
                "total_cache_hits": self.cache_stats['embedding_hits'] + self.cache_stats['response_hits'],
                "overall_hit_rate": round(
                    (self.cache_stats['embedding_hits'] + self.cache_stats['response_hits']) / 
                    max(1, total_embedding_requests + total_response_requests), 3
                ),
                "estimated_cost_saved": self.cache_stats['total_cost_saved']
            }
        }
    
    async def get_enhanced_status(self) -> Dict[str, Any]:
        """Get enhanced AI service status with cache information."""
        base_status = self.get_provider_status()
        cache_stats = self.get_cache_stats()
        
        # Add cache health check
        cache_health = {"status": "disabled"}
        if self.cache_service:
            cache_health = await self.cache_service.health_check()
        
        return {
            "ai_providers": base_status,
            "cache_service": cache_health,
            "cache_statistics": cache_stats,
            "features": {
                "multi_provider_fallback": True,
                "embedding_caching": self.enable_embedding_cache,
                "response_caching": self.enable_response_cache,
                "batch_processing": True,
                "cache_warming": True,
                "cost_optimization": True
            }
        }

# DEPRECATED: Module-level singleton pattern removed in favor of FastAPI DI
# Use api/dependencies/services.py get_cached_ai_service_di() instead
#
# Migration guide:
#   Old: from .ai_service_cached import get_cached_ai_service
#        service = get_cached_ai_service()
#
#   New: from ..api.dependencies import get_cached_ai_service_di
#        # In FastAPI endpoint:
#        async def endpoint(service = Depends(get_cached_ai_service_di)):
#            ...


# Compatibility shim for code that still uses the old pattern
# This is a temporary solution - code should be migrated to use DI
_cached_ai_service_instance = None

def get_cached_ai_service() -> CachedAIService:
    """
    Get a cached AI service instance.
    
    DEPRECATED: Use get_cached_ai_service_di() from api/dependencies/services.py instead.
    This function is kept for backward compatibility with existing code.
    """
    global _cached_ai_service_instance
    if _cached_ai_service_instance is None:
        _cached_ai_service_instance = CachedAIService()
    return _cached_ai_service_instance
