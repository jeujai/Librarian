"""
Multi-Level Cache Manager for System Integration and Stability

This module implements a comprehensive multi-level caching system with:
- L1 Cache: In-memory LRU cache for fastest access
- L2 Cache: Redis distributed cache for shared access
- L3 Cache: Database persistent cache for long-term storage

Features:
- Automatic cache promotion between levels
- Intelligent cache warming strategies
- Session-based caching
- Cache statistics and monitoring
- Graceful degradation when cache levels are unavailable
"""

import asyncio
import hashlib
import json
import logging
import pickle
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Set, Tuple, Union
from enum import Enum
import weakref
import threading

try:
    import redis.asyncio as redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    redis = None

from ..config import get_settings
from ..database.connection import get_database_connection

logger = logging.getLogger(__name__)


class CacheLevel(str, Enum):
    """Cache level enumeration."""
    L1_MEMORY = "l1_memory"
    L2_REDIS = "l2_redis"
    L3_DATABASE = "l3_database"


@dataclass
class CacheStats:
    """Cache statistics for monitoring and optimization."""
    l1_hits: int = 0
    l1_misses: int = 0
    l2_hits: int = 0
    l2_misses: int = 0
    l3_hits: int = 0
    l3_misses: int = 0
    total_sets: int = 0
    total_deletes: int = 0
    total_evictions: int = 0
    l1_size: int = 0
    l2_size: int = 0
    l3_size: int = 0
    memory_usage_mb: float = 0.0
    avg_access_time_ms: float = 0.0
    cache_warming_runs: int = 0
    last_warming_time: Optional[datetime] = None
    
    @property
    def total_hits(self) -> int:
        return self.l1_hits + self.l2_hits + self.l3_hits
    
    @property
    def total_misses(self) -> int:
        return self.l1_misses + self.l2_misses + self.l3_misses
    
    @property
    def hit_rate(self) -> float:
        total = self.total_hits + self.total_misses
        return (self.total_hits / total * 100) if total > 0 else 0.0
    
    @property
    def l1_hit_rate(self) -> float:
        total = self.l1_hits + self.l1_misses
        return (self.l1_hits / total * 100) if total > 0 else 0.0
    
    @property
    def l2_hit_rate(self) -> float:
        total = self.l2_hits + self.l2_misses
        return (self.l2_hits / total * 100) if total > 0 else 0.0
    
    @property
    def l3_hit_rate(self) -> float:
        total = self.l3_hits + self.l3_misses
        return (self.l3_hits / total * 100) if total > 0 else 0.0


@dataclass
class CacheEntry:
    """Cache entry with metadata."""
    key: str
    value: Any
    created_at: datetime
    last_accessed: datetime
    access_count: int = 0
    ttl_seconds: Optional[int] = None
    size_bytes: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def is_expired(self) -> bool:
        """Check if entry has expired."""
        if self.ttl_seconds is None:
            return False
        return (datetime.now() - self.created_at).total_seconds() > self.ttl_seconds
    
    def touch(self):
        """Update last accessed time and increment access count."""
        self.last_accessed = datetime.now()
        self.access_count += 1


class LRUCache:
    """Thread-safe LRU cache implementation."""
    
    def __init__(self, maxsize: int = 1000):
        self.maxsize = maxsize
        self.cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self.lock = threading.RLock()
        self._stats = {'hits': 0, 'misses': 0, 'evictions': 0}
    
    def get(self, key: str) -> Optional[Any]:
        """Get value from cache."""
        with self.lock:
            if key in self.cache:
                entry = self.cache[key]
                if entry.is_expired:
                    del self.cache[key]
                    self._stats['misses'] += 1
                    return None
                
                # Move to end (most recently used)
                self.cache.move_to_end(key)
                entry.touch()
                self._stats['hits'] += 1
                return entry.value
            
            self._stats['misses'] += 1
            return None
    
    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """Set value in cache."""
        with self.lock:
            try:
                # Calculate size
                size_bytes = len(pickle.dumps(value))
                
                # Create entry
                entry = CacheEntry(
                    key=key,
                    value=value,
                    created_at=datetime.now(),
                    last_accessed=datetime.now(),
                    ttl_seconds=ttl,
                    size_bytes=size_bytes
                )
                
                # Remove if exists
                if key in self.cache:
                    del self.cache[key]
                
                # Add new entry
                self.cache[key] = entry
                
                # Evict if over capacity
                while len(self.cache) > self.maxsize:
                    oldest_key = next(iter(self.cache))
                    del self.cache[oldest_key]
                    self._stats['evictions'] += 1
                
                return True
                
            except Exception as e:
                logger.error(f"L1 cache set failed: {e}")
                return False
    
    def delete(self, key: str) -> bool:
        """Delete key from cache."""
        with self.lock:
            if key in self.cache:
                del self.cache[key]
                return True
            return False
    
    def clear(self):
        """Clear all entries."""
        with self.lock:
            self.cache.clear()
    
    def size(self) -> int:
        """Get cache size."""
        with self.lock:
            return len(self.cache)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        with self.lock:
            total_size = sum(entry.size_bytes for entry in self.cache.values())
            return {
                'size': len(self.cache),
                'max_size': self.maxsize,
                'memory_bytes': total_size,
                'hits': self._stats['hits'],
                'misses': self._stats['misses'],
                'evictions': self._stats['evictions']
            }


class RedisCache:
    """Redis-based L2 cache."""
    
    def __init__(self, redis_client=None):
        self.redis_client = redis_client
        self.is_available = False
        self._stats = {'hits': 0, 'misses': 0, 'sets': 0, 'deletes': 0}
    
    async def connect(self, host: str = 'localhost', port: int = 6379, db: int = 1, password: str = None):
        """Connect to Redis."""
        if not REDIS_AVAILABLE:
            logger.warning("Redis not available for L2 cache")
            return False
        
        try:
            if not self.redis_client:
                self.redis_client = redis.Redis(
                    host=host,
                    port=port,
                    db=db,
                    password=password,
                    decode_responses=False,
                    socket_connect_timeout=5,
                    socket_timeout=5
                )
            
            await self.redis_client.ping()
            self.is_available = True
            logger.info(f"L2 Redis cache connected to {host}:{port}")
            return True
            
        except Exception as e:
            logger.warning(f"L2 Redis cache connection failed: {e}")
            self.is_available = False
            return False
    
    async def get(self, key: str) -> Optional[Any]:
        """Get value from Redis cache."""
        if not self.is_available:
            self._stats['misses'] += 1
            return None
        
        try:
            data = await self.redis_client.get(f"l2:{key}")
            if data is None:
                self._stats['misses'] += 1
                return None
            
            value = pickle.loads(data)
            self._stats['hits'] += 1
            return value
            
        except Exception as e:
            logger.error(f"L2 cache get failed: {e}")
            self._stats['misses'] += 1
            return None
    
    async def set(self, key: str, value: Any, ttl: int = 3600) -> bool:
        """Set value in Redis cache."""
        if not self.is_available:
            return False
        
        try:
            data = pickle.dumps(value)
            await self.redis_client.setex(f"l2:{key}", ttl, data)
            self._stats['sets'] += 1
            return True
            
        except Exception as e:
            logger.error(f"L2 cache set failed: {e}")
            return False
    
    async def delete(self, key: str) -> bool:
        """Delete key from Redis cache."""
        if not self.is_available:
            return False
        
        try:
            result = await self.redis_client.delete(f"l2:{key}")
            if result > 0:
                self._stats['deletes'] += 1
                return True
            return False
            
        except Exception as e:
            logger.error(f"L2 cache delete failed: {e}")
            return False
    
    async def clear(self) -> int:
        """Clear all L2 cache entries."""
        if not self.is_available:
            return 0
        
        try:
            keys = []
            async for key in self.redis_client.scan_iter(match="l2:*"):
                keys.append(key)
            
            if keys:
                return await self.redis_client.delete(*keys)
            return 0
            
        except Exception as e:
            logger.error(f"L2 cache clear failed: {e}")
            return 0
    
    async def size(self) -> int:
        """Get cache size."""
        if not self.is_available:
            return 0
        
        try:
            count = 0
            async for _ in self.redis_client.scan_iter(match="l2:*"):
                count += 1
            return count
            
        except Exception as e:
            logger.error(f"L2 cache size check failed: {e}")
            return 0
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        return {
            'available': self.is_available,
            'hits': self._stats['hits'],
            'misses': self._stats['misses'],
            'sets': self._stats['sets'],
            'deletes': self._stats['deletes']
        }


class DatabaseCache:
    """Database-based L3 cache for persistent storage."""
    
    def __init__(self):
        self.is_available = False
        self._stats = {'hits': 0, 'misses': 0, 'sets': 0, 'deletes': 0}
        self._table_created = False
    
    async def _ensure_table_exists(self):
        """Ensure cache table exists."""
        if self._table_created:
            return
        
        try:
            db = await get_database_connection()
            await db.execute("""
                CREATE TABLE IF NOT EXISTS cache_l3 (
                    cache_key VARCHAR(255) PRIMARY KEY,
                    cache_value BYTEA NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    expires_at TIMESTAMP,
                    access_count INTEGER DEFAULT 0,
                    last_accessed TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Create index for expiration cleanup
            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_cache_l3_expires_at 
                ON cache_l3(expires_at) WHERE expires_at IS NOT NULL
            """)
            
            self._table_created = True
            self.is_available = True
            logger.info("L3 database cache table initialized")
            
        except Exception as e:
            logger.error(f"L3 cache table creation failed: {e}")
            self.is_available = False
    
    async def get(self, key: str) -> Optional[Any]:
        """Get value from database cache."""
        await self._ensure_table_exists()
        
        if not self.is_available:
            self._stats['misses'] += 1
            return None
        
        try:
            db = await get_database_connection()
            
            # Get entry and update access stats
            result = await db.fetch_one("""
                UPDATE cache_l3 
                SET access_count = access_count + 1, last_accessed = CURRENT_TIMESTAMP
                WHERE cache_key = $1 
                AND (expires_at IS NULL OR expires_at > CURRENT_TIMESTAMP)
                RETURNING cache_value
            """, key)
            
            if result is None:
                self._stats['misses'] += 1
                return None
            
            value = pickle.loads(result['cache_value'])
            self._stats['hits'] += 1
            return value
            
        except Exception as e:
            logger.error(f"L3 cache get failed: {e}")
            self._stats['misses'] += 1
            return None
    
    async def set(self, key: str, value: Any, ttl: int = 86400) -> bool:
        """Set value in database cache."""
        await self._ensure_table_exists()
        
        if not self.is_available:
            return False
        
        try:
            db = await get_database_connection()
            data = pickle.dumps(value)
            expires_at = datetime.now() + timedelta(seconds=ttl) if ttl else None
            
            await db.execute("""
                INSERT INTO cache_l3 (cache_key, cache_value, expires_at)
                VALUES ($1, $2, $3)
                ON CONFLICT (cache_key) 
                DO UPDATE SET 
                    cache_value = EXCLUDED.cache_value,
                    expires_at = EXCLUDED.expires_at,
                    last_accessed = CURRENT_TIMESTAMP
            """, key, data, expires_at)
            
            self._stats['sets'] += 1
            return True
            
        except Exception as e:
            logger.error(f"L3 cache set failed: {e}")
            return False
    
    async def delete(self, key: str) -> bool:
        """Delete key from database cache."""
        await self._ensure_table_exists()
        
        if not self.is_available:
            return False
        
        try:
            db = await get_database_connection()
            result = await db.execute("DELETE FROM cache_l3 WHERE cache_key = $1", key)
            
            if result:
                self._stats['deletes'] += 1
                return True
            return False
            
        except Exception as e:
            logger.error(f"L3 cache delete failed: {e}")
            return False
    
    async def clear(self) -> int:
        """Clear all L3 cache entries."""
        await self._ensure_table_exists()
        
        if not self.is_available:
            return 0
        
        try:
            db = await get_database_connection()
            result = await db.execute("DELETE FROM cache_l3")
            return result or 0
            
        except Exception as e:
            logger.error(f"L3 cache clear failed: {e}")
            return 0
    
    async def cleanup_expired(self) -> int:
        """Clean up expired entries."""
        await self._ensure_table_exists()
        
        if not self.is_available:
            return 0
        
        try:
            db = await get_database_connection()
            result = await db.execute("""
                DELETE FROM cache_l3 
                WHERE expires_at IS NOT NULL AND expires_at < CURRENT_TIMESTAMP
            """)
            
            if result and result > 0:
                logger.info(f"Cleaned up {result} expired L3 cache entries")
            
            return result or 0
            
        except Exception as e:
            logger.error(f"L3 cache cleanup failed: {e}")
            return 0
    
    async def size(self) -> int:
        """Get cache size."""
        await self._ensure_table_exists()
        
        if not self.is_available:
            return 0
        
        try:
            db = await get_database_connection()
            result = await db.fetch_one("SELECT COUNT(*) as count FROM cache_l3")
            return result['count'] if result else 0
            
        except Exception as e:
            logger.error(f"L3 cache size check failed: {e}")
            return 0
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        return {
            'available': self.is_available,
            'hits': self._stats['hits'],
            'misses': self._stats['misses'],
            'sets': self._stats['sets'],
            'deletes': self._stats['deletes']
        }


class CacheWarmingScheduler:
    """Scheduler for cache warming operations."""
    
    def __init__(self):
        self.warming_patterns: Dict[str, Dict[str, Any]] = {}
        self.warming_tasks: Set[asyncio.Task] = set()
        self.is_running = False
    
    def add_warming_pattern(
        self, 
        pattern_name: str, 
        query_generator, 
        interval_minutes: int = 60,
        max_queries: int = 100
    ):
        """Add a cache warming pattern."""
        self.warming_patterns[pattern_name] = {
            'query_generator': query_generator,
            'interval_minutes': interval_minutes,
            'max_queries': max_queries,
            'last_run': None,
            'total_runs': 0
        }
        logger.info(f"Added cache warming pattern: {pattern_name}")
    
    async def start_warming(self, cache_manager):
        """Start cache warming scheduler."""
        if self.is_running:
            return
        
        self.is_running = True
        logger.info("Cache warming scheduler started")
        
        for pattern_name, config in self.warming_patterns.items():
            task = asyncio.create_task(
                self._warming_loop(pattern_name, config, cache_manager)
            )
            self.warming_tasks.add(task)
    
    async def stop_warming(self):
        """Stop cache warming scheduler."""
        self.is_running = False
        
        for task in self.warming_tasks:
            task.cancel()
        
        await asyncio.gather(*self.warming_tasks, return_exceptions=True)
        self.warming_tasks.clear()
        logger.info("Cache warming scheduler stopped")
    
    async def _warming_loop(self, pattern_name: str, config: Dict[str, Any], cache_manager):
        """Cache warming loop for a specific pattern."""
        while self.is_running:
            try:
                await asyncio.sleep(config['interval_minutes'] * 60)
                
                if not self.is_running:
                    break
                
                logger.info(f"Starting cache warming for pattern: {pattern_name}")
                
                # Generate queries
                queries = await config['query_generator'](config['max_queries'])
                
                # Warm cache
                warmed_count = 0
                for query in queries[:config['max_queries']]:
                    try:
                        # This would be implemented by the specific cache manager
                        await cache_manager.warm_query(query)
                        warmed_count += 1
                    except Exception as e:
                        logger.warning(f"Cache warming failed for query '{query}': {e}")
                
                config['last_run'] = datetime.now()
                config['total_runs'] += 1
                
                logger.info(f"Cache warming completed for {pattern_name}: {warmed_count} queries warmed")
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Cache warming error for {pattern_name}: {e}")
                await asyncio.sleep(60)  # Wait before retrying


class SessionCache:
    """Session-based caching for user-specific data."""
    
    def __init__(self, cache_manager):
        self.cache_manager = cache_manager
        self.session_ttl = 7200  # 2 hours
        self.active_sessions: Dict[str, datetime] = {}
        self.session_lock = threading.RLock()
    
    def _get_session_key(self, session_id: str, key: str) -> str:
        """Generate session-specific cache key."""
        return f"session:{session_id}:{key}"
    
    async def get(self, session_id: str, key: str) -> Optional[Any]:
        """Get value from session cache."""
        if not self._is_session_active(session_id):
            return None
        
        session_key = self._get_session_key(session_id, key)
        return await self.cache_manager.get(session_key)
    
    async def set(self, session_id: str, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """Set value in session cache."""
        self._update_session_activity(session_id)
        
        session_key = self._get_session_key(session_id, key)
        return await self.cache_manager.set(session_key, value, ttl or self.session_ttl)
    
    async def delete(self, session_id: str, key: str) -> bool:
        """Delete value from session cache."""
        session_key = self._get_session_key(session_id, key)
        return await self.cache_manager.delete(session_key)
    
    async def clear_session(self, session_id: str) -> int:
        """Clear all cache entries for a session."""
        pattern = f"session:{session_id}:*"
        return await self.cache_manager.delete_pattern(pattern)
    
    def _is_session_active(self, session_id: str) -> bool:
        """Check if session is still active."""
        with self.session_lock:
            if session_id not in self.active_sessions:
                return False
            
            last_activity = self.active_sessions[session_id]
            if (datetime.now() - last_activity).total_seconds() > self.session_ttl:
                del self.active_sessions[session_id]
                return False
            
            return True
    
    def _update_session_activity(self, session_id: str):
        """Update session activity timestamp."""
        with self.session_lock:
            self.active_sessions[session_id] = datetime.now()
    
    async def cleanup_expired_sessions(self) -> int:
        """Clean up expired session data."""
        expired_sessions = []
        
        with self.session_lock:
            now = datetime.now()
            for session_id, last_activity in list(self.active_sessions.items()):
                if (now - last_activity).total_seconds() > self.session_ttl:
                    expired_sessions.append(session_id)
                    del self.active_sessions[session_id]
        
        # Clear cache data for expired sessions
        total_cleared = 0
        for session_id in expired_sessions:
            cleared = await self.clear_session(session_id)
            total_cleared += cleared
        
        if total_cleared > 0:
            logger.info(f"Cleaned up {total_cleared} cache entries from {len(expired_sessions)} expired sessions")
        
        return total_cleared


class MultiLevelCacheManager:
    """
    Multi-level cache manager implementing L1, L2, and L3 caching strategy.
    
    Features:
    - L1: In-memory LRU cache for fastest access
    - L2: Redis distributed cache for shared access
    - L3: Database persistent cache for long-term storage
    - Automatic cache promotion between levels
    - Session-based caching
    - Cache warming strategies
    - Comprehensive statistics and monitoring
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize multi-level cache manager."""
        self.config = config or {}
        
        # Initialize cache levels
        self.l1_cache = LRUCache(maxsize=self.config.get('l1_maxsize', 1000))
        self.l2_cache = RedisCache()
        self.l3_cache = DatabaseCache()
        
        # Cache configuration
        self.l1_ttl = self.config.get('l1_ttl', 300)  # 5 minutes
        self.l2_ttl = self.config.get('l2_ttl', 3600)  # 1 hour
        self.l3_ttl = self.config.get('l3_ttl', 86400)  # 24 hours
        
        # Statistics
        self.stats = CacheStats()
        self.access_times: List[float] = []
        
        # Session cache
        self.session_cache = SessionCache(self)
        
        # Cache warming
        self.warming_scheduler = CacheWarmingScheduler()
        
        # State
        self.is_initialized = False
        
        logger.info("Multi-level cache manager initialized")
    
    async def initialize(self):
        """Initialize all cache levels."""
        if self.is_initialized:
            return
        
        # Initialize L2 Redis cache
        redis_config = self.config.get('redis', {})
        await self.l2_cache.connect(
            host=redis_config.get('host', 'localhost'),
            port=redis_config.get('port', 6379),
            db=redis_config.get('db', 1),
            password=redis_config.get('password')
        )
        
        # Initialize L3 database cache
        await self.l3_cache._ensure_table_exists()
        
        self.is_initialized = True
        logger.info("Multi-level cache manager initialized successfully")
    
    async def get(self, key: str) -> Optional[Any]:
        """
        Get value from cache with fallback through levels.
        
        Tries L1 -> L2 -> L3 and promotes values up the hierarchy.
        """
        start_time = time.time()
        
        try:
            # Try L1 cache first
            value = self.l1_cache.get(key)
            if value is not None:
                self.stats.l1_hits += 1
                self._record_access_time(start_time)
                logger.debug(f"L1 cache hit for key: {key}")
                return value
            
            self.stats.l1_misses += 1
            
            # Try L2 cache
            value = await self.l2_cache.get(key)
            if value is not None:
                self.stats.l2_hits += 1
                # Promote to L1
                self.l1_cache.set(key, value, self.l1_ttl)
                self._record_access_time(start_time)
                logger.debug(f"L2 cache hit for key: {key} (promoted to L1)")
                return value
            
            self.stats.l2_misses += 1
            
            # Try L3 cache
            value = await self.l3_cache.get(key)
            if value is not None:
                self.stats.l3_hits += 1
                # Promote to L2 and L1
                await self.l2_cache.set(key, value, self.l2_ttl)
                self.l1_cache.set(key, value, self.l1_ttl)
                self._record_access_time(start_time)
                logger.debug(f"L3 cache hit for key: {key} (promoted to L2 and L1)")
                return value
            
            self.stats.l3_misses += 1
            self._record_access_time(start_time)
            return None
            
        except Exception as e:
            logger.error(f"Cache get failed for key {key}: {e}")
            return None
    
    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """Set value in all cache levels."""
        try:
            # Use provided TTL or defaults
            l1_ttl = ttl or self.l1_ttl
            l2_ttl = ttl or self.l2_ttl
            l3_ttl = ttl or self.l3_ttl
            
            # Set in all levels
            l1_success = self.l1_cache.set(key, value, l1_ttl)
            l2_success = await self.l2_cache.set(key, value, l2_ttl)
            l3_success = await self.l3_cache.set(key, value, l3_ttl)
            
            self.stats.total_sets += 1
            
            # Consider successful if at least one level succeeded
            success = l1_success or l2_success or l3_success
            
            if success:
                logger.debug(f"Cache set for key: {key} (L1: {l1_success}, L2: {l2_success}, L3: {l3_success})")
            
            return success
            
        except Exception as e:
            logger.error(f"Cache set failed for key {key}: {e}")
            return False
    
    async def delete(self, key: str) -> bool:
        """Delete key from all cache levels."""
        try:
            l1_deleted = self.l1_cache.delete(key)
            l2_deleted = await self.l2_cache.delete(key)
            l3_deleted = await self.l3_cache.delete(key)
            
            self.stats.total_deletes += 1
            
            # Consider successful if deleted from any level
            success = l1_deleted or l2_deleted or l3_deleted
            
            if success:
                logger.debug(f"Cache delete for key: {key}")
            
            return success
            
        except Exception as e:
            logger.error(f"Cache delete failed for key {key}: {e}")
            return False
    
    async def delete_pattern(self, pattern: str) -> int:
        """Delete keys matching pattern from all levels."""
        total_deleted = 0
        
        try:
            # L1 cache pattern deletion (simple implementation)
            keys_to_delete = []
            for key in list(self.l1_cache.cache.keys()):
                if self._matches_pattern(key, pattern):
                    keys_to_delete.append(key)
            
            for key in keys_to_delete:
                if self.l1_cache.delete(key):
                    total_deleted += 1
            
            # L2 cache pattern deletion
            if self.l2_cache.is_available:
                redis_pattern = pattern.replace('*', '*')  # Ensure Redis pattern format
                keys = []
                async for key in self.l2_cache.redis_client.scan_iter(match=f"l2:{redis_pattern}"):
                    keys.append(key)
                
                if keys:
                    deleted = await self.l2_cache.redis_client.delete(*keys)
                    total_deleted += deleted
            
            # L3 cache pattern deletion (would need SQL LIKE pattern)
            # For now, skip L3 pattern deletion as it's complex with SQL
            
            logger.info(f"Deleted {total_deleted} cache entries matching pattern: {pattern}")
            return total_deleted
            
        except Exception as e:
            logger.error(f"Pattern deletion failed for {pattern}: {e}")
            return total_deleted
    
    def _matches_pattern(self, key: str, pattern: str) -> bool:
        """Simple pattern matching for cache keys."""
        import fnmatch
        return fnmatch.fnmatch(key, pattern)
    
    async def clear_all(self) -> Dict[str, int]:
        """Clear all cache levels."""
        results = {}
        
        try:
            # Clear L1
            self.l1_cache.clear()
            results['l1'] = 0  # L1 doesn't return count
            
            # Clear L2
            results['l2'] = await self.l2_cache.clear()
            
            # Clear L3
            results['l3'] = await self.l3_cache.clear()
            
            logger.info(f"Cleared all cache levels: {results}")
            return results
            
        except Exception as e:
            logger.error(f"Cache clear all failed: {e}")
            return results
    
    async def get_comprehensive_stats(self) -> Dict[str, Any]:
        """Get comprehensive cache statistics."""
        try:
            # Update cache sizes
            self.stats.l1_size = self.l1_cache.size()
            self.stats.l2_size = await self.l2_cache.size()
            self.stats.l3_size = await self.l3_cache.size()
            
            # Calculate memory usage
            l1_stats = self.l1_cache.get_stats()
            self.stats.memory_usage_mb = l1_stats['memory_bytes'] / (1024 * 1024)
            
            # Calculate average access time
            if self.access_times:
                self.stats.avg_access_time_ms = sum(self.access_times) / len(self.access_times) * 1000
            
            return {
                'overall': {
                    'total_hits': self.stats.total_hits,
                    'total_misses': self.stats.total_misses,
                    'hit_rate_percent': self.stats.hit_rate,
                    'avg_access_time_ms': self.stats.avg_access_time_ms,
                    'total_sets': self.stats.total_sets,
                    'total_deletes': self.stats.total_deletes
                },
                'l1_memory': {
                    'hits': self.stats.l1_hits,
                    'misses': self.stats.l1_misses,
                    'hit_rate_percent': self.stats.l1_hit_rate,
                    'size': self.stats.l1_size,
                    'memory_mb': self.stats.memory_usage_mb,
                    **l1_stats
                },
                'l2_redis': {
                    'hits': self.stats.l2_hits,
                    'misses': self.stats.l2_misses,
                    'hit_rate_percent': self.stats.l2_hit_rate,
                    'size': self.stats.l2_size,
                    **self.l2_cache.get_stats()
                },
                'l3_database': {
                    'hits': self.stats.l3_hits,
                    'misses': self.stats.l3_misses,
                    'hit_rate_percent': self.stats.l3_hit_rate,
                    'size': self.stats.l3_size,
                    **self.l3_cache.get_stats()
                },
                'cache_warming': {
                    'runs': self.stats.cache_warming_runs,
                    'last_run': self.stats.last_warming_time.isoformat() if self.stats.last_warming_time else None,
                    'active_patterns': len(self.warming_scheduler.warming_patterns)
                }
            }
            
        except Exception as e:
            logger.error(f"Failed to get cache stats: {e}")
            return {'error': str(e)}
    
    def _record_access_time(self, start_time: float):
        """Record access time for statistics."""
        access_time = time.time() - start_time
        self.access_times.append(access_time)
        
        # Keep only recent access times (last 1000)
        if len(self.access_times) > 1000:
            self.access_times = self.access_times[-1000:]
    
    async def warm_query(self, query: str) -> bool:
        """Warm cache for a specific query (to be implemented by subclasses)."""
        # This is a placeholder - specific implementations would override this
        logger.debug(f"Cache warming requested for query: {query}")
        return True
    
    async def health_check(self) -> Dict[str, Any]:
        """Perform comprehensive health check."""
        health = {
            'status': 'healthy',
            'initialized': self.is_initialized,
            'levels': {
                'l1_memory': {
                    'status': 'healthy',
                    'available': True,
                    'size': self.l1_cache.size()
                },
                'l2_redis': {
                    'status': 'healthy' if self.l2_cache.is_available else 'unhealthy',
                    'available': self.l2_cache.is_available,
                    'size': await self.l2_cache.size() if self.l2_cache.is_available else 0
                },
                'l3_database': {
                    'status': 'healthy' if self.l3_cache.is_available else 'unhealthy',
                    'available': self.l3_cache.is_available,
                    'size': await self.l3_cache.size() if self.l3_cache.is_available else 0
                }
            },
            'session_cache': {
                'active_sessions': len(self.session_cache.active_sessions)
            },
            'cache_warming': {
                'scheduler_running': self.warming_scheduler.is_running,
                'active_patterns': len(self.warming_scheduler.warming_patterns)
            }
        }
        
        # Determine overall status
        if not self.l2_cache.is_available and not self.l3_cache.is_available:
            health['status'] = 'degraded'
        elif not self.is_initialized:
            health['status'] = 'unhealthy'
        
        return health
    
    async def cleanup_expired(self) -> Dict[str, int]:
        """Clean up expired entries from all levels."""
        results = {}
        
        try:
            # L1 cleanup happens automatically via TTL checks
            results['l1'] = 0
            
            # L2 cleanup happens automatically via Redis TTL
            results['l2'] = 0
            
            # L3 cleanup needs manual intervention
            results['l3'] = await self.l3_cache.cleanup_expired()
            
            # Session cleanup
            results['sessions'] = await self.session_cache.cleanup_expired_sessions()
            
            total_cleaned = sum(results.values())
            if total_cleaned > 0:
                logger.info(f"Cleanup completed: {results}")
            
            return results
            
        except Exception as e:
            logger.error(f"Cache cleanup failed: {e}")
            return results


# Global cache manager instance
_cache_manager = None

async def get_multi_level_cache_manager() -> MultiLevelCacheManager:
    """Get global multi-level cache manager instance."""
    global _cache_manager
    if _cache_manager is None:
        settings = get_settings()
        config = {
            'l1_maxsize': getattr(settings, 'cache_l1_maxsize', 1000),
            'l1_ttl': getattr(settings, 'cache_l1_ttl', 300),
            'l2_ttl': getattr(settings, 'cache_l2_ttl', 3600),
            'l3_ttl': getattr(settings, 'cache_l3_ttl', 86400),
            'redis': {
                'host': getattr(settings, 'redis_host', 'localhost'),
                'port': getattr(settings, 'redis_port', 6379),
                'db': getattr(settings, 'redis_db', 1),
                'password': getattr(settings, 'redis_password', None)
            }
        }
        _cache_manager = MultiLevelCacheManager(config)
        await _cache_manager.initialize()
    return _cache_manager