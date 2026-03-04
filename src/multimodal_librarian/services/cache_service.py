"""
Cache Service - Redis-based caching for performance optimization

This service provides comprehensive caching capabilities for embeddings, search results,
conversation context, AI responses, and database queries to dramatically improve system performance.
"""

import json
import time
import hashlib
import logging
from typing import Dict, List, Optional, Any, Union, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
from enum import Enum
import asyncio
import pickle
import gzip

try:
    import redis.asyncio as redis
    from redis.asyncio import Redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    redis = None
    Redis = None

from ..config import get_settings

logger = logging.getLogger(__name__)

class CacheType(str, Enum):
    """Cache type enumeration."""
    EMBEDDING = "embedding"
    SEARCH_RESULT = "search_result"
    CONVERSATION = "conversation"
    AI_RESPONSE = "ai_response"
    DATABASE_QUERY = "database_query"
    ANALYTICS = "analytics"
    KNOWLEDGE_GRAPH = "knowledge_graph"

@dataclass
class CacheEntry:
    """Cache entry with metadata."""
    key: str
    value: Any
    cache_type: CacheType
    created_at: datetime
    expires_at: Optional[datetime] = None
    access_count: int = 0
    last_accessed: Optional[datetime] = None
    size_bytes: int = 0
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}

@dataclass
class CacheStats:
    """Cache statistics."""
    total_entries: int
    total_size_bytes: int
    hit_rate: float
    miss_rate: float
    eviction_count: int
    memory_usage_mb: float
    entries_by_type: Dict[str, int]
    avg_access_time_ms: float

class CacheConfig:
    """Cache configuration settings."""
    
    def __init__(self):
        self.settings = get_settings()
        
        # Redis connection settings
        self.redis_host = getattr(self.settings, 'redis_host', 'localhost')
        self.redis_port = getattr(self.settings, 'redis_port', 6379)
        self.redis_db = getattr(self.settings, 'redis_db', 0)
        self.redis_password = getattr(self.settings, 'redis_password', None)
        self.redis_ssl = getattr(self.settings, 'redis_ssl', False)
        
        # Cache TTL settings (in seconds)
        self.embedding_ttl = getattr(self.settings, 'cache_embedding_ttl', 86400)  # 24 hours
        self.search_result_ttl = getattr(self.settings, 'cache_search_result_ttl', 3600)  # 1 hour
        self.conversation_ttl = getattr(self.settings, 'cache_conversation_ttl', 7200)  # 2 hours
        self.ai_response_ttl = getattr(self.settings, 'cache_ai_response_ttl', 1800)  # 30 minutes
        self.database_query_ttl = getattr(self.settings, 'cache_database_query_ttl', 600)  # 10 minutes
        self.analytics_ttl = getattr(self.settings, 'cache_analytics_ttl', 300)  # 5 minutes
        self.knowledge_graph_ttl = getattr(self.settings, 'cache_knowledge_graph_ttl', 3600)  # 1 hour
        
        # Cache size limits
        self.max_memory_mb = getattr(self.settings, 'cache_max_memory_mb', 512)
        self.max_entries_per_type = getattr(self.settings, 'cache_max_entries_per_type', 10000)
        
        # Performance settings
        self.compression_enabled = getattr(self.settings, 'cache_compression_enabled', True)
        self.compression_threshold = getattr(self.settings, 'cache_compression_threshold', 1024)  # bytes
        self.batch_size = getattr(self.settings, 'cache_batch_size', 100)
        
        # Feature flags
        self.enable_embedding_cache = getattr(self.settings, 'cache_enable_embedding', True)
        self.enable_search_cache = getattr(self.settings, 'cache_enable_search', True)
        self.enable_conversation_cache = getattr(self.settings, 'cache_enable_conversation', True)
        self.enable_ai_response_cache = getattr(self.settings, 'cache_enable_ai_response', True)
        self.enable_database_cache = getattr(self.settings, 'cache_enable_database', True)
        self.enable_analytics_cache = getattr(self.settings, 'cache_enable_analytics', True)
        self.enable_knowledge_graph_cache = getattr(self.settings, 'cache_enable_knowledge_graph', True)

class CacheService:
    """
    Comprehensive Redis-based caching service for performance optimization.
    
    Features:
    - Multi-type caching (embeddings, search results, conversations, AI responses)
    - Automatic compression for large values
    - TTL management with type-specific expiration
    - Cache statistics and monitoring
    - Batch operations for efficiency
    - Memory management and eviction policies
    - Async/await support for non-blocking operations
    """
    
    def __init__(self, config: Optional[CacheConfig] = None):
        """Initialize cache service."""
        self.config = config or CacheConfig()
        self.redis_client: Optional[Redis] = None
        self.is_connected = False
        self.stats = {
            'hits': 0,
            'misses': 0,
            'sets': 0,
            'deletes': 0,
            'evictions': 0,
            'total_access_time_ms': 0.0,
            'access_count': 0
        }
        
        # TTL mapping
        self.ttl_mapping = {
            CacheType.EMBEDDING: self.config.embedding_ttl,
            CacheType.SEARCH_RESULT: self.config.search_result_ttl,
            CacheType.CONVERSATION: self.config.conversation_ttl,
            CacheType.AI_RESPONSE: self.config.ai_response_ttl,
            CacheType.DATABASE_QUERY: self.config.database_query_ttl,
            CacheType.ANALYTICS: self.config.analytics_ttl,
            CacheType.KNOWLEDGE_GRAPH: self.config.knowledge_graph_ttl
        }
        
        # Feature flags mapping
        self.feature_flags = {
            CacheType.EMBEDDING: self.config.enable_embedding_cache,
            CacheType.SEARCH_RESULT: self.config.enable_search_cache,
            CacheType.CONVERSATION: self.config.enable_conversation_cache,
            CacheType.AI_RESPONSE: self.config.enable_ai_response_cache,
            CacheType.DATABASE_QUERY: self.config.enable_database_cache,
            CacheType.ANALYTICS: self.config.enable_analytics_cache,
            CacheType.KNOWLEDGE_GRAPH: self.config.enable_knowledge_graph_cache
        }
        
        logger.info("Cache service initialized")
    
    async def connect(self) -> bool:
        """Connect to Redis server."""
        if not REDIS_AVAILABLE:
            logger.warning("Redis not available - caching disabled")
            return False
        
        try:
            self.redis_client = redis.Redis(
                host=self.config.redis_host,
                port=self.config.redis_port,
                db=self.config.redis_db,
                password=self.config.redis_password,
                ssl=self.config.redis_ssl,
                decode_responses=False,  # We handle encoding ourselves
                socket_connect_timeout=5,
                socket_timeout=5,
                retry_on_timeout=True,
                health_check_interval=30
            )
            
            # Test connection
            await self.redis_client.ping()
            self.is_connected = True
            
            logger.info(f"Connected to Redis at {self.config.redis_host}:{self.config.redis_port}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            self.is_connected = False
            return False
    
    async def disconnect(self):
        """Disconnect from Redis server."""
        if self.redis_client:
            await self.redis_client.close()
            self.is_connected = False
            logger.info("Disconnected from Redis")
    
    def _generate_cache_key(self, cache_type: CacheType, identifier: str, **kwargs) -> str:
        """Generate cache key with type prefix and optional parameters."""
        # Create base key
        base_key = f"{cache_type.value}:{identifier}"
        
        # Add parameters if provided
        if kwargs:
            # Sort kwargs for consistent key generation
            sorted_params = sorted(kwargs.items())
            param_str = "|".join(f"{k}={v}" for k, v in sorted_params)
            base_key += f":{param_str}"
        
        # Hash long keys to keep them manageable
        if len(base_key) > 200:
            hash_obj = hashlib.sha256(base_key.encode())
            base_key = f"{cache_type.value}:hash:{hash_obj.hexdigest()[:16]}"
        
        return base_key
    
    def _serialize_value(self, value: Any) -> bytes:
        """Serialize value with optional compression."""
        try:
            # Serialize to bytes
            serialized = pickle.dumps(value)
            
            # Compress if enabled and value is large enough
            if (self.config.compression_enabled and 
                len(serialized) > self.config.compression_threshold):
                compressed = gzip.compress(serialized)
                # Only use compression if it actually reduces size
                if len(compressed) < len(serialized):
                    return b'COMPRESSED:' + compressed
            
            return b'RAW:' + serialized
            
        except Exception as e:
            logger.error(f"Failed to serialize value: {e}")
            raise
    
    def _deserialize_value(self, data: bytes) -> Any:
        """Deserialize value with decompression support."""
        try:
            if data.startswith(b'COMPRESSED:'):
                compressed_data = data[11:]  # Remove 'COMPRESSED:' prefix
                decompressed = gzip.decompress(compressed_data)
                return pickle.loads(decompressed)
            elif data.startswith(b'RAW:'):
                raw_data = data[4:]  # Remove 'RAW:' prefix
                return pickle.loads(raw_data)
            else:
                # Legacy format - try direct pickle
                return pickle.loads(data)
                
        except Exception as e:
            logger.error(f"Failed to deserialize value: {e}")
            raise
    
    async def get(
        self, 
        cache_type: CacheType, 
        identifier: str, 
        **kwargs
    ) -> Optional[Any]:
        """
        Get value from cache.
        
        Args:
            cache_type: Type of cache entry
            identifier: Unique identifier for the cached item
            **kwargs: Additional parameters for key generation
            
        Returns:
            Cached value or None if not found
        """
        if not self.is_connected or not self.feature_flags.get(cache_type, True):
            return None
        
        start_time = time.time()
        
        try:
            cache_key = self._generate_cache_key(cache_type, identifier, **kwargs)
            
            # Get value from Redis
            data = await self.redis_client.get(cache_key)
            
            if data is None:
                self.stats['misses'] += 1
                return None
            
            # Deserialize value
            value = self._deserialize_value(data)
            
            # Update statistics
            self.stats['hits'] += 1
            access_time = (time.time() - start_time) * 1000
            self.stats['total_access_time_ms'] += access_time
            self.stats['access_count'] += 1
            
            logger.debug(f"Cache hit for {cache_type.value}:{identifier} ({access_time:.1f}ms)")
            return value
            
        except Exception as e:
            logger.error(f"Cache get failed for {cache_type.value}:{identifier}: {e}")
            self.stats['misses'] += 1
            return None
    
    async def set(
        self, 
        cache_type: CacheType, 
        identifier: str, 
        value: Any, 
        ttl: Optional[int] = None,
        **kwargs
    ) -> bool:
        """
        Set value in cache.
        
        Args:
            cache_type: Type of cache entry
            identifier: Unique identifier for the cached item
            value: Value to cache
            ttl: Time to live in seconds (uses default if not specified)
            **kwargs: Additional parameters for key generation
            
        Returns:
            True if successful, False otherwise
        """
        if not self.is_connected or not self.feature_flags.get(cache_type, True):
            return False
        
        start_time = time.time()
        
        try:
            cache_key = self._generate_cache_key(cache_type, identifier, **kwargs)
            
            # Use default TTL if not specified
            if ttl is None:
                ttl = self.ttl_mapping.get(cache_type, 3600)
            
            # Serialize value
            serialized_data = self._serialize_value(value)
            
            # Set in Redis with TTL
            await self.redis_client.setex(cache_key, ttl, serialized_data)
            
            # Update statistics
            self.stats['sets'] += 1
            access_time = (time.time() - start_time) * 1000
            self.stats['total_access_time_ms'] += access_time
            self.stats['access_count'] += 1
            
            logger.debug(f"Cache set for {cache_type.value}:{identifier} (TTL: {ttl}s, {access_time:.1f}ms)")
            return True
            
        except Exception as e:
            logger.error(f"Cache set failed for {cache_type.value}:{identifier}: {e}")
            return False
    
    async def delete(
        self, 
        cache_type: CacheType, 
        identifier: str, 
        **kwargs
    ) -> bool:
        """
        Delete value from cache.
        
        Args:
            cache_type: Type of cache entry
            identifier: Unique identifier for the cached item
            **kwargs: Additional parameters for key generation
            
        Returns:
            True if successful, False otherwise
        """
        if not self.is_connected:
            return False
        
        try:
            cache_key = self._generate_cache_key(cache_type, identifier, **kwargs)
            
            # Delete from Redis
            result = await self.redis_client.delete(cache_key)
            
            # Update statistics
            if result > 0:
                self.stats['deletes'] += 1
                logger.debug(f"Cache delete for {cache_type.value}:{identifier}")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Cache delete failed for {cache_type.value}:{identifier}: {e}")
            return False
    
    async def exists(
        self, 
        cache_type: CacheType, 
        identifier: str, 
        **kwargs
    ) -> bool:
        """
        Check if key exists in cache.
        
        Args:
            cache_type: Type of cache entry
            identifier: Unique identifier for the cached item
            **kwargs: Additional parameters for key generation
            
        Returns:
            True if key exists, False otherwise
        """
        if not self.is_connected:
            return False
        
        try:
            cache_key = self._generate_cache_key(cache_type, identifier, **kwargs)
            result = await self.redis_client.exists(cache_key)
            return result > 0
            
        except Exception as e:
            logger.error(f"Cache exists check failed for {cache_type.value}:{identifier}: {e}")
            return False
    
    async def get_or_set(
        self,
        cache_type: CacheType,
        identifier: str,
        value_factory,
        ttl: Optional[int] = None,
        **kwargs
    ) -> Any:
        """
        Get value from cache or set it using a factory function.
        
        Args:
            cache_type: Type of cache entry
            identifier: Unique identifier for the cached item
            value_factory: Async function to generate value if not cached
            ttl: Time to live in seconds
            **kwargs: Additional parameters for key generation
            
        Returns:
            Cached or newly generated value
        """
        # Try to get from cache first
        cached_value = await self.get(cache_type, identifier, **kwargs)
        if cached_value is not None:
            return cached_value
        
        # Generate new value
        try:
            if asyncio.iscoroutinefunction(value_factory):
                new_value = await value_factory()
            else:
                new_value = value_factory()
            
            # Cache the new value
            await self.set(cache_type, identifier, new_value, ttl, **kwargs)
            
            return new_value
            
        except Exception as e:
            logger.error(f"Value factory failed for {cache_type.value}:{identifier}: {e}")
            raise
    
    async def clear_by_type(self, cache_type: CacheType) -> int:
        """
        Clear all cache entries of a specific type.
        
        Args:
            cache_type: Type of cache entries to clear
            
        Returns:
            Number of entries cleared
        """
        if not self.is_connected:
            return 0
        
        try:
            # Find all keys with the type prefix
            pattern = f"{cache_type.value}:*"
            keys = []
            
            async for key in self.redis_client.scan_iter(match=pattern, count=1000):
                keys.append(key)
            
            if not keys:
                return 0
            
            # Delete keys in batches
            deleted_count = 0
            batch_size = self.config.batch_size
            
            for i in range(0, len(keys), batch_size):
                batch = keys[i:i + batch_size]
                deleted = await self.redis_client.delete(*batch)
                deleted_count += deleted
            
            logger.info(f"Cleared {deleted_count} cache entries of type {cache_type.value}")
            return deleted_count
            
        except Exception as e:
            logger.error(f"Failed to clear cache type {cache_type.value}: {e}")
            return 0
    
    async def clear_all(self) -> bool:
        """
        Clear all cache entries.
        
        Returns:
            True if successful, False otherwise
        """
        if not self.is_connected:
            return False
        
        try:
            await self.redis_client.flushdb()
            logger.info("Cleared all cache entries")
            return True
            
        except Exception as e:
            logger.error(f"Failed to clear all cache: {e}")
            return False
    
    async def get_stats(self) -> CacheStats:
        """
        Get cache statistics.
        
        Returns:
            Cache statistics object
        """
        if not self.is_connected:
            return CacheStats(
                total_entries=0,
                total_size_bytes=0,
                hit_rate=0.0,
                miss_rate=0.0,
                eviction_count=0,
                memory_usage_mb=0.0,
                entries_by_type={},
                avg_access_time_ms=0.0
            )
        
        try:
            # Get Redis info
            info = await self.redis_client.info('memory')
            memory_usage_mb = info.get('used_memory', 0) / (1024 * 1024)
            
            # Calculate hit/miss rates
            total_requests = self.stats['hits'] + self.stats['misses']
            hit_rate = self.stats['hits'] / total_requests if total_requests > 0 else 0.0
            miss_rate = self.stats['misses'] / total_requests if total_requests > 0 else 0.0
            
            # Calculate average access time
            avg_access_time = (
                self.stats['total_access_time_ms'] / self.stats['access_count'] 
                if self.stats['access_count'] > 0 else 0.0
            )
            
            # Count entries by type
            entries_by_type = {}
            for cache_type in CacheType:
                pattern = f"{cache_type.value}:*"
                count = 0
                async for _ in self.redis_client.scan_iter(match=pattern, count=100):
                    count += 1
                entries_by_type[cache_type.value] = count
            
            total_entries = sum(entries_by_type.values())
            
            return CacheStats(
                total_entries=total_entries,
                total_size_bytes=info.get('used_memory', 0),
                hit_rate=hit_rate,
                miss_rate=miss_rate,
                eviction_count=self.stats['evictions'],
                memory_usage_mb=memory_usage_mb,
                entries_by_type=entries_by_type,
                avg_access_time_ms=avg_access_time
            )
            
        except Exception as e:
            logger.error(f"Failed to get cache stats: {e}")
            return CacheStats(
                total_entries=0,
                total_size_bytes=0,
                hit_rate=0.0,
                miss_rate=0.0,
                eviction_count=0,
                memory_usage_mb=0.0,
                entries_by_type={},
                avg_access_time_ms=0.0
            )
    
    async def health_check(self) -> Dict[str, Any]:
        """
        Perform cache service health check.
        
        Returns:
            Health check results
        """
        health_data = {
            "status": "unhealthy",
            "redis_available": REDIS_AVAILABLE,
            "connected": self.is_connected,
            "config": {
                "host": self.config.redis_host,
                "port": self.config.redis_port,
                "db": self.config.redis_db,
                "compression_enabled": self.config.compression_enabled,
                "max_memory_mb": self.config.max_memory_mb
            },
            "features": {
                cache_type.value: enabled 
                for cache_type, enabled in self.feature_flags.items()
            },
            "error": None
        }
        
        if not REDIS_AVAILABLE:
            health_data["error"] = "Redis library not available"
            return health_data
        
        if not self.is_connected:
            health_data["error"] = "Not connected to Redis"
            return health_data
        
        try:
            # Test Redis connection
            start_time = time.time()
            await self.redis_client.ping()
            ping_time = (time.time() - start_time) * 1000
            
            # Get basic stats
            stats = await self.get_stats()
            
            health_data.update({
                "status": "healthy",
                "ping_time_ms": round(ping_time, 2),
                "memory_usage_mb": stats.memory_usage_mb,
                "total_entries": stats.total_entries,
                "hit_rate": stats.hit_rate,
                "avg_access_time_ms": stats.avg_access_time_ms
            })
            
        except Exception as e:
            health_data["status"] = "unhealthy"
            health_data["error"] = str(e)
        
        return health_data

# Global cache service instance
_cache_service = None

async def get_cache_service() -> CacheService:
    """Get global cache service instance."""
    global _cache_service
    if _cache_service is None:
        _cache_service = CacheService()
        await _cache_service.connect()
    return _cache_service

def get_cache_service_sync() -> CacheService:
    """Get global cache service instance (synchronous)."""
    global _cache_service
    if _cache_service is None:
        _cache_service = CacheService()
    return _cache_service