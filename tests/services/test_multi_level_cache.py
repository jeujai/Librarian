"""
Tests for Multi-Level Cache System

This module tests the multi-level caching implementation including
L1, L2, L3 caches, session caching, and cache warming strategies.
"""

import asyncio
import pytest
import time
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from src.multimodal_librarian.services.multi_level_cache_manager import (
    MultiLevelCacheManager,
    LRUCache,
    RedisCache,
    DatabaseCache,
    CacheStats,
    CacheEntry
)
from src.multimodal_librarian.services.session_cache_service import (
    SessionCacheService,
    SessionInfo,
    SessionCacheStats
)
from src.multimodal_librarian.services.cache_warming_service import (
    CacheWarmingService,
    WarmingPattern,
    WarmingStrategy,
    WarmingResult
)


class TestLRUCache:
    """Test L1 LRU cache implementation."""
    
    def test_lru_cache_basic_operations(self):
        """Test basic LRU cache operations."""
        cache = LRUCache(maxsize=3)
        
        # Test set and get
        assert cache.set("key1", "value1") is True
        assert cache.get("key1") == "value1"
        
        # Test miss
        assert cache.get("nonexistent") is None
        
        # Test delete
        assert cache.delete("key1") is True
        assert cache.get("key1") is None
        assert cache.delete("nonexistent") is False
    
    def test_lru_cache_eviction(self):
        """Test LRU cache eviction policy."""
        cache = LRUCache(maxsize=2)
        
        # Fill cache
        cache.set("key1", "value1")
        cache.set("key2", "value2")
        
        # Access key1 to make it most recently used
        cache.get("key1")
        
        # Add key3, should evict key2
        cache.set("key3", "value3")
        
        assert cache.get("key1") == "value1"  # Still there
        assert cache.get("key2") is None      # Evicted
        assert cache.get("key3") == "value3"  # New entry
    
    def test_lru_cache_ttl(self):
        """Test LRU cache TTL functionality."""
        cache = LRUCache(maxsize=10)
        
        # Set with very short TTL
        cache.set("key1", "value1", ttl=1)
        assert cache.get("key1") == "value1"
        
        # Wait for expiration
        time.sleep(1.1)
        assert cache.get("key1") is None
    
    def test_lru_cache_stats(self):
        """Test LRU cache statistics."""
        cache = LRUCache(maxsize=2)
        
        # Generate some hits and misses
        cache.set("key1", "value1")
        cache.get("key1")  # Hit
        cache.get("key2")  # Miss
        
        stats = cache.get_stats()
        assert stats['hits'] == 1
        assert stats['misses'] == 1
        assert stats['size'] == 1


class TestRedisCache:
    """Test L2 Redis cache implementation."""
    
    @pytest.fixture
    def mock_redis(self):
        """Mock Redis client."""
        mock_client = AsyncMock()
        mock_client.ping = AsyncMock()
        mock_client.get = AsyncMock()
        mock_client.setex = AsyncMock()
        mock_client.delete = AsyncMock()
        mock_client.scan_iter = AsyncMock()
        return mock_client
    
    @pytest.mark.asyncio
    async def test_redis_cache_connection(self, mock_redis):
        """Test Redis cache connection."""
        cache = RedisCache(mock_redis)
        
        # Test successful connection
        mock_redis.ping.return_value = True
        success = await cache.connect()
        assert success is True
        assert cache.is_available is True
        
        # Test failed connection
        mock_redis.ping.side_effect = Exception("Connection failed")
        cache.is_available = False
        success = await cache.connect()
        assert success is False
    
    @pytest.mark.asyncio
    async def test_redis_cache_operations(self, mock_redis):
        """Test Redis cache operations."""
        cache = RedisCache(mock_redis)
        cache.is_available = True
        
        # Test get
        mock_redis.get.return_value = b'pickled_value'
        with patch('pickle.loads', return_value="test_value"):
            result = await cache.get("test_key")
            assert result == "test_value"
            mock_redis.get.assert_called_with("l2:test_key")
        
        # Test set
        with patch('pickle.dumps', return_value=b'pickled_value'):
            success = await cache.set("test_key", "test_value", 3600)
            assert success is True
            mock_redis.setex.assert_called_with("l2:test_key", 3600, b'pickled_value')
        
        # Test delete
        mock_redis.delete.return_value = 1
        success = await cache.delete("test_key")
        assert success is True
        mock_redis.delete.assert_called_with("l2:test_key")


class TestDatabaseCache:
    """Test L3 database cache implementation."""
    
    @pytest.fixture
    def mock_db(self):
        """Mock database connection."""
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock()
        mock_db.fetch_one = AsyncMock()
        mock_db.fetch_all = AsyncMock()
        return mock_db
    
    @pytest.mark.asyncio
    async def test_database_cache_table_creation(self, mock_db):
        """Test database cache table creation."""
        cache = DatabaseCache()
        
        with patch('src.multimodal_librarian.services.multi_level_cache_manager.get_database_connection', return_value=mock_db):
            await cache._ensure_table_exists()
            
            # Should create table and index
            assert mock_db.execute.call_count >= 2
            assert cache.is_available is True
    
    @pytest.mark.asyncio
    async def test_database_cache_operations(self, mock_db):
        """Test database cache operations."""
        cache = DatabaseCache()
        cache.is_available = True
        
        with patch('src.multimodal_librarian.services.multi_level_cache_manager.get_database_connection', return_value=mock_db):
            # Test get
            mock_db.fetch_one.return_value = {'cache_value': b'pickled_value'}
            with patch('pickle.loads', return_value="test_value"):
                result = await cache.get("test_key")
                assert result == "test_value"
            
            # Test set
            with patch('pickle.dumps', return_value=b'pickled_value'):
                success = await cache.set("test_key", "test_value", 3600)
                assert success is True
            
            # Test delete
            mock_db.execute.return_value = 1
            success = await cache.delete("test_key")
            assert success is True


class TestMultiLevelCacheManager:
    """Test multi-level cache manager."""
    
    @pytest.fixture
    def cache_manager(self):
        """Create cache manager with mocked components."""
        config = {
            'l1_maxsize': 100,
            'l1_ttl': 300,
            'l2_ttl': 3600,
            'l3_ttl': 86400,
            'redis': {
                'host': 'localhost',
                'port': 6379,
                'db': 1
            }
        }
        return MultiLevelCacheManager(config)
    
    @pytest.mark.asyncio
    async def test_cache_manager_initialization(self, cache_manager):
        """Test cache manager initialization."""
        with patch.object(cache_manager.l2_cache, 'connect', return_value=True):
            with patch.object(cache_manager.l3_cache, '_ensure_table_exists'):
                await cache_manager.initialize()
                assert cache_manager.is_initialized is True
    
    @pytest.mark.asyncio
    async def test_cache_manager_get_with_promotion(self, cache_manager):
        """Test cache get with level promotion."""
        cache_manager.is_initialized = True
        
        # Mock L1 miss, L2 hit
        cache_manager.l1_cache.get = MagicMock(return_value=None)
        cache_manager.l2_cache.get = AsyncMock(return_value="test_value")
        cache_manager.l1_cache.set = MagicMock(return_value=True)
        
        result = await cache_manager.get("test_key")
        
        assert result == "test_value"
        assert cache_manager.stats.l1_misses == 1
        assert cache_manager.stats.l2_hits == 1
        cache_manager.l1_cache.set.assert_called_once()  # Promoted to L1
    
    @pytest.mark.asyncio
    async def test_cache_manager_set_all_levels(self, cache_manager):
        """Test cache set to all levels."""
        cache_manager.is_initialized = True
        
        # Mock all levels
        cache_manager.l1_cache.set = MagicMock(return_value=True)
        cache_manager.l2_cache.set = AsyncMock(return_value=True)
        cache_manager.l3_cache.set = AsyncMock(return_value=True)
        
        success = await cache_manager.set("test_key", "test_value", 1800)
        
        assert success is True
        assert cache_manager.stats.total_sets == 1
        cache_manager.l1_cache.set.assert_called_with("test_key", "test_value", 1800)
        cache_manager.l2_cache.set.assert_called_with("test_key", "test_value", 1800)
        cache_manager.l3_cache.set.assert_called_with("test_key", "test_value", 1800)
    
    @pytest.mark.asyncio
    async def test_cache_manager_comprehensive_stats(self, cache_manager):
        """Test comprehensive statistics collection."""
        cache_manager.is_initialized = True
        
        # Mock cache sizes
        cache_manager.l1_cache.size = MagicMock(return_value=10)
        cache_manager.l2_cache.size = AsyncMock(return_value=50)
        cache_manager.l3_cache.size = AsyncMock(return_value=100)
        cache_manager.l1_cache.get_stats = MagicMock(return_value={'memory_bytes': 1024})
        
        stats = await cache_manager.get_comprehensive_stats()
        
        assert 'overall' in stats
        assert 'l1_memory' in stats
        assert 'l2_redis' in stats
        assert 'l3_database' in stats
        assert stats['l1_memory']['size'] == 10
        assert stats['l2_redis']['size'] == 50
        assert stats['l3_database']['size'] == 100


class TestSessionCacheService:
    """Test session cache service."""
    
    @pytest.fixture
    def session_cache(self):
        """Create session cache service."""
        return SessionCacheService(session_ttl=3600)
    
    def test_session_creation(self, session_cache):
        """Test session creation."""
        session_id = session_cache.create_session(
            user_id="user123",
            ip_address="192.168.1.1",
            user_agent="TestAgent/1.0"
        )
        
        assert session_id is not None
        assert len(session_id) == 36  # UUID format
        
        session_info = session_cache.get_session(session_id)
        assert session_info is not None
        assert session_info.user_id == "user123"
        assert session_info.ip_address == "192.168.1.1"
    
    def test_session_expiration(self, session_cache):
        """Test session expiration."""
        # Create session with short TTL
        session_cache.session_ttl = 1
        session_id = session_cache.create_session(user_id="user123")
        
        # Should be valid initially
        assert session_cache.is_session_valid(session_id) is True
        
        # Wait for expiration
        time.sleep(1.1)
        
        # Should be expired now
        assert session_cache.is_session_valid(session_id) is False
    
    @pytest.mark.asyncio
    async def test_session_cache_operations(self, session_cache):
        """Test session cache operations."""
        session_cache.cache_manager = AsyncMock()
        session_id = session_cache.create_session(user_id="user123")
        
        # Test set
        session_cache.cache_manager.set = AsyncMock(return_value=True)
        success = await session_cache.set(session_id, "test_key", "test_value")
        assert success is True
        
        # Test get
        session_cache.cache_manager.get = AsyncMock(return_value="test_value")
        value = await session_cache.get(session_id, "test_key")
        assert value == "test_value"
        
        # Test delete
        session_cache.cache_manager.delete = AsyncMock(return_value=True)
        success = await session_cache.delete(session_id, "test_key")
        assert success is True
    
    @pytest.mark.asyncio
    async def test_session_cleanup(self, session_cache):
        """Test expired session cleanup."""
        session_cache.cache_manager = AsyncMock()
        session_cache.cache_manager.delete = AsyncMock(return_value=True)
        
        # Create expired session
        session_cache.session_ttl = 1
        session_id = session_cache.create_session(user_id="user123")
        
        # Add cache entry
        await session_cache.set(session_id, "test_key", "test_value")
        
        # Wait for expiration
        time.sleep(1.1)
        
        # Run cleanup
        results = await session_cache.cleanup_expired_sessions()
        
        assert results['expired_sessions'] == 1
        assert session_id not in session_cache.sessions


class TestCacheWarmingService:
    """Test cache warming service."""
    
    @pytest.fixture
    def warming_service(self):
        """Create cache warming service."""
        return CacheWarmingService()
    
    @pytest.mark.asyncio
    async def test_warming_service_initialization(self, warming_service):
        """Test warming service initialization."""
        warming_service.cache_manager = AsyncMock()
        
        await warming_service.initialize()
        
        # Should have default patterns registered
        assert len(warming_service.warming_patterns) > 0
        assert "popular_queries" in warming_service.warming_patterns
        assert "recent_searches" in warming_service.warming_patterns
    
    def test_warming_pattern_registration(self, warming_service):
        """Test warming pattern registration."""
        async def test_generator(max_queries):
            return ["test query 1", "test query 2"]
        
        warming_service.register_warming_pattern(
            name="test_pattern",
            strategy=WarmingStrategy.SCHEDULED,
            query_generator=test_generator,
            interval_minutes=30,
            max_queries=50
        )
        
        assert "test_pattern" in warming_service.warming_patterns
        pattern = warming_service.warming_patterns["test_pattern"]
        assert pattern.strategy == WarmingStrategy.SCHEDULED
        assert pattern.interval_minutes == 30
        assert pattern.max_queries == 50
    
    def test_pattern_enable_disable(self, warming_service):
        """Test pattern enable/disable functionality."""
        async def test_generator(max_queries):
            return ["test query"]
        
        warming_service.register_warming_pattern(
            name="test_pattern",
            strategy=WarmingStrategy.SCHEDULED,
            query_generator=test_generator
        )
        
        # Test disable
        success = warming_service.disable_pattern("test_pattern")
        assert success is True
        assert warming_service.warming_patterns["test_pattern"].enabled is False
        
        # Test enable
        success = warming_service.enable_pattern("test_pattern")
        assert success is True
        assert warming_service.warming_patterns["test_pattern"].enabled is True
    
    @pytest.mark.asyncio
    async def test_query_warming(self, warming_service):
        """Test warming specific queries."""
        warming_service.cache_manager = AsyncMock()
        warming_service.cache_manager.get = AsyncMock(return_value=None)  # Cache miss
        warming_service.cache_manager.set = AsyncMock(return_value=True)
        
        queries = ["test query 1", "test query 2", "test query 3"]
        result = await warming_service.warm_specific_queries(queries)
        
        assert result.queries_attempted == 3
        assert result.queries_successful == 3
        assert result.queries_failed == 0
        assert result.success_rate == 100.0
    
    @pytest.mark.asyncio
    async def test_popular_queries_generation(self, warming_service):
        """Test popular queries generation."""
        mock_db = AsyncMock()
        mock_db.fetch_all = AsyncMock(return_value=[
            {'query_text': 'machine learning'},
            {'query_text': 'artificial intelligence'},
            {'query_text': 'data science'}
        ])
        
        with patch('src.multimodal_librarian.services.cache_warming_service.get_database_connection', return_value=mock_db):
            queries = await warming_service._generate_popular_queries(10)
            
            assert len(queries) == 3
            assert 'machine learning' in queries
            assert 'artificial intelligence' in queries
            assert 'data science' in queries
    
    @pytest.mark.asyncio
    async def test_warming_pattern_execution(self, warming_service):
        """Test warming pattern execution."""
        warming_service.cache_manager = AsyncMock()
        warming_service.cache_manager.get = AsyncMock(return_value=None)
        warming_service.cache_manager.set = AsyncMock(return_value=True)
        warming_service.cache_manager.get_comprehensive_stats = AsyncMock(return_value={
            'overall': {'total_hits': 100}
        })
        
        async def test_generator(max_queries):
            return ["test query 1", "test query 2"]
        
        warming_service.register_warming_pattern(
            name="test_pattern",
            strategy=WarmingStrategy.SCHEDULED,
            query_generator=test_generator,
            max_queries=2
        )
        
        result = await warming_service._run_warming_pattern("test_pattern")
        
        assert result.pattern_name == "test_pattern"
        assert result.queries_attempted == 2
        assert result.queries_successful == 2
        
        # Check pattern stats updated
        pattern = warming_service.warming_patterns["test_pattern"]
        assert pattern.total_runs == 1
        assert pattern.success_count == 2
    
    def test_warming_service_stats(self, warming_service):
        """Test warming service statistics."""
        async def test_generator(max_queries):
            return ["test query"]
        
        warming_service.register_warming_pattern(
            name="test_pattern",
            strategy=WarmingStrategy.POPULAR_QUERIES,
            query_generator=test_generator
        )
        
        stats = warming_service.get_all_patterns_stats()
        
        assert 'patterns' in stats
        assert 'global_stats' in stats
        assert 'test_pattern' in stats['patterns']
        assert stats['global_stats']['total_patterns'] >= 1


class TestCacheIntegration:
    """Integration tests for the complete caching system."""
    
    @pytest.mark.asyncio
    async def test_end_to_end_caching_flow(self):
        """Test complete caching flow from session to warming."""
        # This would be a comprehensive integration test
        # that tests the interaction between all cache components
        
        # Create cache manager
        cache_manager = MultiLevelCacheManager({
            'l1_maxsize': 10,
            'l1_ttl': 300,
            'l2_ttl': 3600,
            'l3_ttl': 86400
        })
        
        # Mock the underlying cache implementations
        cache_manager.l1_cache = MagicMock()
        cache_manager.l2_cache = AsyncMock()
        cache_manager.l3_cache = AsyncMock()
        cache_manager.is_initialized = True
        
        # Test cache operations
        cache_manager.l1_cache.get.return_value = None
        cache_manager.l2_cache.get.return_value = None
        cache_manager.l3_cache.get.return_value = None
        
        # Should return None for cache miss
        result = await cache_manager.get("test_key")
        assert result is None
        
        # Set value
        cache_manager.l1_cache.set.return_value = True
        cache_manager.l2_cache.set.return_value = True
        cache_manager.l3_cache.set.return_value = True
        
        success = await cache_manager.set("test_key", "test_value")
        assert success is True
        
        # Verify all levels were called
        cache_manager.l1_cache.set.assert_called_once()
        cache_manager.l2_cache.set.assert_called_once()
        cache_manager.l3_cache.set.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_cache_performance_under_load(self):
        """Test cache performance under concurrent load."""
        cache = LRUCache(maxsize=100)
        
        async def cache_operations():
            """Perform cache operations."""
            for i in range(100):
                cache.set(f"key_{i}", f"value_{i}")
                cache.get(f"key_{i}")
        
        # Run concurrent operations
        tasks = [cache_operations() for _ in range(10)]
        await asyncio.gather(*tasks)
        
        # Verify cache is still functional
        stats = cache.get_stats()
        assert stats['size'] <= 100  # Respects max size
        assert stats['hits'] > 0
    
    @pytest.mark.asyncio
    async def test_cache_warming_effectiveness(self):
        """Test cache warming effectiveness."""
        warming_service = CacheWarmingService()
        warming_service.cache_manager = AsyncMock()
        
        # Mock cache operations
        warming_service.cache_manager.get = AsyncMock(return_value=None)  # Always miss initially
        warming_service.cache_manager.set = AsyncMock(return_value=True)
        warming_service.cache_manager.get_comprehensive_stats = AsyncMock(return_value={
            'overall': {'total_hits': 0}
        })
        
        # Warm cache with queries
        queries = ["query1", "query2", "query3", "query4", "query5"]
        result = await warming_service.warm_specific_queries(queries)
        
        # Verify warming was effective
        assert result.queries_attempted == 5
        assert result.queries_successful == 5
        assert result.success_rate == 100.0
        
        # Verify cache was populated
        assert warming_service.cache_manager.set.call_count == 5


if __name__ == "__main__":
    pytest.main([__file__, "-v"])