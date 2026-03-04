"""
Enrichment Cache with LRU eviction and TTL expiration.

This module provides caching for YAGO and ConceptNet query responses
to minimize lookups and improve performance.
"""

import logging
import threading
import time
from collections import OrderedDict
from typing import TYPE_CHECKING, List, Optional

from ..models.enrichment import CacheEntry, CacheStats, ConceptNetRelation

if TYPE_CHECKING:
    from ..components.yago.models import YagoEntityData

logger = logging.getLogger(__name__)


class EnrichmentCache:
    """
    LRU cache with TTL for enrichment data.
    
    Features:
    - Separate caches for YAGO and ConceptNet data
    - TTL-based expiration (default 24 hours)
    - LRU eviction when max size exceeded
    - Thread-safe operations
    """
    
    def __init__(
        self,
        max_size: int = 10000,
        ttl_seconds: int = 86400  # 24 hours
    ):
        """
        Initialize the enrichment cache.
        
        Args:
            max_size: Maximum entries per cache (YAGO and ConceptNet each)
            ttl_seconds: Time-to-live for cache entries in seconds
        """
        self.max_size = max_size
        self.ttl = ttl_seconds
        
        # Separate caches for each data type
        self._yago_cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self._conceptnet_cache: OrderedDict[str, CacheEntry] = OrderedDict()
        
        # Statistics tracking
        self._yago_hits = 0
        self._yago_misses = 0
        self._conceptnet_hits = 0
        self._conceptnet_misses = 0
        self._evictions = 0
        
        # Thread safety
        self._lock = threading.RLock()
        
        logger.info(f"EnrichmentCache initialized with max_size={max_size}, ttl={ttl_seconds}s")
    
    # =========================================================================
    # YAGO Cache Operations
    # =========================================================================
    
    def get_yago(self, concept_name: str) -> Optional["YagoEntityData"]:
        """
        Get cached YAGO entity for a concept.
        
        Args:
            concept_name: Name of the concept to look up
            
        Returns:
            YagoEntityData if found and not expired, None otherwise
        """
        normalized_key = self._normalize_key(concept_name)
        
        with self._lock:
            entry = self._yago_cache.get(normalized_key)
            
            if entry is None:
                self._yago_misses += 1
                return None
            
            # Check TTL expiration
            if entry.is_expired(self.ttl):
                # Remove expired entry
                del self._yago_cache[normalized_key]
                self._yago_misses += 1
                logger.debug(f"YAGO cache entry expired for: {concept_name}")
                return None
            
            # Update LRU order by moving to end
            self._yago_cache.move_to_end(normalized_key)
            entry.touch()
            
            self._yago_hits += 1
            logger.debug(f"YAGO cache hit for: {concept_name}")
            return entry.data
    
    def set_yago(self, concept_name: str, entity: "YagoEntityData") -> None:
        """
        Cache a YAGO entity for a concept.
        
        Args:
            concept_name: Name of the concept
            entity: YagoEntityData to cache
        """
        normalized_key = self._normalize_key(concept_name)
        
        with self._lock:
            # Check if we need to evict
            if normalized_key not in self._yago_cache and len(self._yago_cache) >= self.max_size:
                self._evict_lru(self._yago_cache)
            
            # Add or update entry
            self._yago_cache[normalized_key] = CacheEntry(data=entity)
            self._yago_cache.move_to_end(normalized_key)
            
            logger.debug(f"YAGO cache set for: {concept_name} -> {entity.entity_id}")
    
    # =========================================================================
    # ConceptNet Cache Operations
    # =========================================================================
    
    def get_conceptnet(self, concept_name: str) -> Optional[List[ConceptNetRelation]]:
        """
        Get cached ConceptNet relationships for a concept.
        
        Args:
            concept_name: Name of the concept to look up
            
        Returns:
            List of ConceptNetRelation if found and not expired, None otherwise
        """
        normalized_key = self._normalize_key(concept_name)
        
        with self._lock:
            entry = self._conceptnet_cache.get(normalized_key)
            
            if entry is None:
                self._conceptnet_misses += 1
                return None
            
            # Check TTL expiration
            if entry.is_expired(self.ttl):
                # Remove expired entry
                del self._conceptnet_cache[normalized_key]
                self._conceptnet_misses += 1
                logger.debug(f"ConceptNet cache entry expired for: {concept_name}")
                return None
            
            # Update LRU order by moving to end
            self._conceptnet_cache.move_to_end(normalized_key)
            entry.touch()
            
            self._conceptnet_hits += 1
            logger.debug(f"ConceptNet cache hit for: {concept_name}")
            return entry.data
    
    def set_conceptnet(self, concept_name: str, relations: List[ConceptNetRelation]) -> None:
        """
        Cache ConceptNet relationships for a concept.
        
        Args:
            concept_name: Name of the concept
            relations: List of ConceptNetRelation to cache
        """
        normalized_key = self._normalize_key(concept_name)
        
        with self._lock:
            # Check if we need to evict
            if normalized_key not in self._conceptnet_cache and len(self._conceptnet_cache) >= self.max_size:
                self._evict_lru(self._conceptnet_cache)
            
            # Add or update entry
            self._conceptnet_cache[normalized_key] = CacheEntry(data=relations)
            self._conceptnet_cache.move_to_end(normalized_key)
            
            logger.debug(f"ConceptNet cache set for: {concept_name} -> {len(relations)} relations")
    
    # =========================================================================
    # Cache Management
    # =========================================================================
    
    def clear(self) -> None:
        """Clear all caches and reset statistics."""
        with self._lock:
            self._yago_cache.clear()
            self._conceptnet_cache.clear()
            self._yago_hits = 0
            self._yago_misses = 0
            self._conceptnet_hits = 0
            self._conceptnet_misses = 0
            self._evictions = 0
            
        logger.info("EnrichmentCache cleared")
    
    def get_stats(self) -> CacheStats:
        """
        Get cache statistics.
        
        Returns:
            CacheStats with current cache state
        """
        with self._lock:
            return CacheStats(
                yago_size=len(self._yago_cache),
                conceptnet_size=len(self._conceptnet_cache),
                yago_hits=self._yago_hits,
                yago_misses=self._yago_misses,
                conceptnet_hits=self._conceptnet_hits,
                conceptnet_misses=self._conceptnet_misses,
                evictions=self._evictions
            )
    
    def cleanup_expired(self) -> int:
        """
        Remove all expired entries from both caches.
        
        Returns:
            Number of entries removed
        """
        removed = 0
        
        with self._lock:
            # Clean YAGO cache
            expired_keys = [
                key for key, entry in self._yago_cache.items()
                if entry.is_expired(self.ttl)
            ]
            for key in expired_keys:
                del self._yago_cache[key]
                removed += 1
            
            # Clean ConceptNet cache
            expired_keys = [
                key for key, entry in self._conceptnet_cache.items()
                if entry.is_expired(self.ttl)
            ]
            for key in expired_keys:
                del self._conceptnet_cache[key]
                removed += 1
        
        if removed > 0:
            logger.info(f"Cleaned up {removed} expired cache entries")
        
        return removed
    
    # =========================================================================
    # Private Methods
    # =========================================================================
    
    def _normalize_key(self, concept_name: str) -> str:
        """
        Normalize concept name for cache key.
        
        Args:
            concept_name: Raw concept name
            
        Returns:
            Normalized lowercase key
        """
        return concept_name.lower().strip()
    
    def _evict_lru(self, cache: OrderedDict) -> None:
        """
        Evict the least recently used entry from a cache.
        
        Args:
            cache: The OrderedDict cache to evict from
        """
        if cache:
            # Pop the first item (least recently used)
            evicted_key, _ = cache.popitem(last=False)
            self._evictions += 1
            logger.debug(f"Evicted LRU cache entry: {evicted_key}")


# Global cache instance
_enrichment_cache: Optional[EnrichmentCache] = None


def get_enrichment_cache() -> EnrichmentCache:
    """
    Get or create the global enrichment cache instance.
    
    Returns:
        EnrichmentCache singleton instance
    """
    global _enrichment_cache
    
    if _enrichment_cache is None:
        _enrichment_cache = EnrichmentCache()
    
    return _enrichment_cache


def clear_enrichment_cache() -> None:
    """Clear the global enrichment cache."""
    global _enrichment_cache
    
    if _enrichment_cache is not None:
        _enrichment_cache.clear()
