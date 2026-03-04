#!/usr/bin/env python3
"""
Multi-Level Cache System Demonstration

This script demonstrates the multi-level caching system with L1, L2, L3 caches,
session caching, and cache warming strategies.
"""

import asyncio
import json
import logging
import random
import time
from datetime import datetime
from typing import Dict, Any

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Import cache services
try:
    from src.multimodal_librarian.services.multi_level_cache_manager import (
        MultiLevelCacheManager, get_multi_level_cache_manager
    )
    from src.multimodal_librarian.services.session_cache_service import (
        SessionCacheService, get_session_cache_service
    )
    from src.multimodal_librarian.services.cache_warming_service import (
        CacheWarmingService, get_cache_warming_service, WarmingStrategy
    )
except ImportError as e:
    logger.error(f"Import error: {e}")
    logger.info("Running in mock mode - some features may not work")


class MultiLevelCacheDemo:
    """Demonstration of multi-level caching system."""
    
    def __init__(self):
        """Initialize the demo."""
        self.cache_manager = None
        self.session_cache = None
        self.warming_service = None
        self.demo_data = self._generate_demo_data()
    
    def _generate_demo_data(self) -> Dict[str, Any]:
        """Generate sample data for demonstration."""
        return {
            'users': [
                {'id': 'user1', 'name': 'Alice Johnson', 'role': 'researcher'},
                {'id': 'user2', 'name': 'Bob Smith', 'role': 'developer'},
                {'id': 'user3', 'name': 'Carol Davis', 'role': 'analyst'}
            ],
            'documents': [
                {'id': 'doc1', 'title': 'Machine Learning Basics', 'content': 'Introduction to ML...'},
                {'id': 'doc2', 'title': 'Python Programming', 'content': 'Python fundamentals...'},
                {'id': 'doc3', 'title': 'Data Science Guide', 'content': 'Data analysis techniques...'}
            ],
            'search_queries': [
                'machine learning algorithms',
                'python data structures',
                'statistical analysis',
                'neural networks',
                'data visualization',
                'web development',
                'database design',
                'software architecture'
            ]
        }
    
    async def initialize(self):
        """Initialize all cache services."""
        logger.info("🚀 Initializing Multi-Level Cache System...")
        
        try:
            # Initialize cache manager
            config = {
                'l1_maxsize': 100,
                'l1_ttl': 300,  # 5 minutes
                'l2_ttl': 3600,  # 1 hour
                'l3_ttl': 86400,  # 24 hours
                'redis': {
                    'host': 'localhost',
                    'port': 6379,
                    'db': 1,
                    'password': None
                }
            }
            
            self.cache_manager = MultiLevelCacheManager(config)
            await self.cache_manager.initialize()
            logger.info("✅ Multi-level cache manager initialized")
            
            # Initialize session cache
            self.session_cache = SessionCacheService(session_ttl=7200)  # 2 hours
            await self.session_cache.initialize()
            logger.info("✅ Session cache service initialized")
            
            # Initialize cache warming
            self.warming_service = CacheWarmingService()
            await self.warming_service.initialize()
            logger.info("✅ Cache warming service initialized")
            
        except Exception as e:
            logger.error(f"❌ Initialization failed: {e}")
            logger.info("🔄 Running in mock mode")
            await self._initialize_mock_mode()
    
    async def _initialize_mock_mode(self):
        """Initialize mock services for demonstration."""
        from unittest.mock import AsyncMock, MagicMock
        
        # Mock cache manager
        self.cache_manager = MagicMock()
        self.cache_manager.get = AsyncMock()
        self.cache_manager.set = AsyncMock(return_value=True)
        self.cache_manager.delete = AsyncMock(return_value=True)
        self.cache_manager.get_comprehensive_stats = AsyncMock(return_value={
            'overall': {'total_hits': 150, 'total_misses': 50, 'hit_rate_percent': 75.0},
            'l1_memory': {'hits': 100, 'misses': 20, 'hit_rate_percent': 83.3, 'size': 45},
            'l2_redis': {'hits': 30, 'misses': 15, 'hit_rate_percent': 66.7, 'size': 120},
            'l3_database': {'hits': 20, 'misses': 15, 'hit_rate_percent': 57.1, 'size': 500}
        })
        self.cache_manager.health_check = AsyncMock(return_value={'status': 'healthy'})
        
        # Mock session cache
        self.session_cache = MagicMock()
        self.session_cache.create_session = MagicMock(return_value='session_123')
        self.session_cache.get = AsyncMock()
        self.session_cache.set = AsyncMock(return_value=True)
        self.session_cache.get_comprehensive_stats = MagicMock(return_value={
            'sessions': {'currently_active': 5, 'total_created': 25},
            'cache': {'total_entries': 50, 'hit_rate_percent': 80.0}
        })
        
        # Mock warming service
        self.warming_service = MagicMock()
        self.warming_service.warm_specific_queries = AsyncMock()
        self.warming_service.get_all_patterns_stats = MagicMock(return_value={
            'patterns': {'popular_queries': {'success_rate_percent': 95.0}},
            'global_stats': {'total_warming_runs': 10}
        })
    
    async def demonstrate_basic_caching(self):
        """Demonstrate basic multi-level caching operations."""
        logger.info("\n📦 Demonstrating Basic Multi-Level Caching")
        logger.info("=" * 50)
        
        # Test cache operations
        test_data = [
            ('user:user1', self.demo_data['users'][0]),
            ('doc:doc1', self.demo_data['documents'][0]),
            ('search:ml_query', {'query': 'machine learning', 'results': ['doc1', 'doc2']})
        ]
        
        for key, value in test_data:
            logger.info(f"🔄 Setting cache key: {key}")
            
            # Set value in cache
            success = await self.cache_manager.set(key, value, ttl=1800)
            logger.info(f"   ✅ Set successful: {success}")
            
            # Get value from cache
            cached_value = await self.cache_manager.get(key)
            if cached_value:
                logger.info(f"   🎯 Cache hit! Retrieved: {type(cached_value).__name__}")
            else:
                logger.info(f"   ❌ Cache miss for key: {key}")
            
            await asyncio.sleep(0.1)  # Small delay for demonstration
    
    async def demonstrate_cache_promotion(self):
        """Demonstrate cache level promotion."""
        logger.info("\n⬆️ Demonstrating Cache Level Promotion")
        logger.info("=" * 50)
        
        # Simulate L3 -> L2 -> L1 promotion
        promotion_key = "promotion_test:data"
        promotion_value = {"data": "This will be promoted through cache levels"}
        
        logger.info(f"🔄 Simulating cache promotion for key: {promotion_key}")
        
        # In a real scenario, this would:
        # 1. Miss L1, miss L2, hit L3
        # 2. Promote to L2 and L1
        # 3. Next access hits L1 directly
        
        await self.cache_manager.set(promotion_key, promotion_value)
        logger.info("   📝 Data stored in all cache levels")
        
        # Simulate multiple accesses to show promotion benefits
        for i in range(3):
            start_time = time.time()
            value = await self.cache_manager.get(promotion_key)
            access_time = (time.time() - start_time) * 1000
            
            if value:
                logger.info(f"   🎯 Access {i+1}: Retrieved in {access_time:.2f}ms")
            else:
                logger.info(f"   ❌ Access {i+1}: Cache miss")
            
            await asyncio.sleep(0.05)
    
    async def demonstrate_session_caching(self):
        """Demonstrate session-based caching."""
        logger.info("\n👤 Demonstrating Session-Based Caching")
        logger.info("=" * 50)
        
        # Create user sessions
        sessions = []
        for user in self.demo_data['users']:
            session_id = self.session_cache.create_session(
                user_id=user['id'],
                ip_address=f"192.168.1.{random.randint(1, 100)}",
                user_agent="DemoClient/1.0"
            )
            sessions.append((session_id, user))
            logger.info(f"👤 Created session for {user['name']}: {session_id[:8]}...")
        
        # Store session-specific data
        for session_id, user in sessions:
            # Store user preferences
            preferences = {
                'theme': random.choice(['light', 'dark']),
                'language': random.choice(['en', 'es', 'fr']),
                'notifications': random.choice([True, False])
            }
            
            await self.session_cache.set(session_id, 'preferences', preferences)
            logger.info(f"   💾 Stored preferences for {user['name']}")
            
            # Store recent searches
            recent_searches = random.sample(self.demo_data['search_queries'], 3)
            await self.session_cache.set(session_id, 'recent_searches', recent_searches)
            logger.info(f"   🔍 Stored recent searches for {user['name']}")
        
        # Retrieve session data
        logger.info("\n📖 Retrieving session data:")
        for session_id, user in sessions:
            preferences = await self.session_cache.get(session_id, 'preferences')
            searches = await self.session_cache.get(session_id, 'recent_searches')
            
            if preferences and searches:
                logger.info(f"   👤 {user['name']}: {preferences['theme']} theme, {len(searches)} recent searches")
            else:
                logger.info(f"   ❌ No session data found for {user['name']}")
    
    async def demonstrate_cache_warming(self):
        """Demonstrate cache warming strategies."""
        logger.info("\n🔥 Demonstrating Cache Warming Strategies")
        logger.info("=" * 50)
        
        # Warm cache with popular queries
        popular_queries = self.demo_data['search_queries'][:5]
        logger.info(f"🔥 Warming cache with {len(popular_queries)} popular queries...")
        
        try:
            result = await self.warming_service.warm_specific_queries(popular_queries)
            logger.info(f"   ✅ Warmed {result.queries_successful}/{result.queries_attempted} queries")
            logger.info(f"   📊 Success rate: {result.success_rate:.1f}%")
            logger.info(f"   ⏱️ Duration: {result.duration_seconds:.2f}s")
        except Exception as e:
            logger.info(f"   🔥 Simulated warming of {len(popular_queries)} queries")
            logger.info(f"   📊 Success rate: 95.0% (simulated)")
        
        # Show warming patterns
        try:
            patterns_stats = self.warming_service.get_all_patterns_stats()
            logger.info(f"\n📈 Active warming patterns:")
            for pattern_name, stats in patterns_stats.get('patterns', {}).items():
                if stats:
                    logger.info(f"   🎯 {pattern_name}: {stats.get('success_rate_percent', 0):.1f}% success rate")
        except Exception:
            logger.info(f"   🎯 popular_queries: 95.0% success rate (simulated)")
            logger.info(f"   🎯 recent_searches: 88.0% success rate (simulated)")
    
    async def demonstrate_performance_monitoring(self):
        """Demonstrate cache performance monitoring."""
        logger.info("\n📊 Demonstrating Performance Monitoring")
        logger.info("=" * 50)
        
        # Get comprehensive statistics
        try:
            cache_stats = await self.cache_manager.get_comprehensive_stats()
            
            logger.info("🎯 Multi-Level Cache Performance:")
            overall = cache_stats.get('overall', {})
            logger.info(f"   Overall Hit Rate: {overall.get('hit_rate_percent', 0):.1f}%")
            logger.info(f"   Total Hits: {overall.get('total_hits', 0)}")
            logger.info(f"   Total Misses: {overall.get('total_misses', 0)}")
            logger.info(f"   Avg Access Time: {overall.get('avg_access_time_ms', 0):.2f}ms")
            
            logger.info("\n📈 Cache Level Breakdown:")
            for level in ['l1_memory', 'l2_redis', 'l3_database']:
                level_stats = cache_stats.get(level, {})
                logger.info(f"   {level.upper()}: {level_stats.get('hit_rate_percent', 0):.1f}% hit rate, "
                           f"{level_stats.get('size', 0)} entries")
            
        except Exception:
            logger.info("🎯 Multi-Level Cache Performance (simulated):")
            logger.info("   Overall Hit Rate: 75.0%")
            logger.info("   Total Hits: 150")
            logger.info("   Total Misses: 50")
            logger.info("   Avg Access Time: 2.5ms")
            
            logger.info("\n📈 Cache Level Breakdown:")
            logger.info("   L1_MEMORY: 83.3% hit rate, 45 entries")
            logger.info("   L2_REDIS: 66.7% hit rate, 120 entries")
            logger.info("   L3_DATABASE: 57.1% hit rate, 500 entries")
        
        # Session cache statistics
        try:
            session_stats = self.session_cache.get_comprehensive_stats()
            
            logger.info("\n👥 Session Cache Performance:")
            sessions = session_stats.get('sessions', {})
            cache = session_stats.get('cache', {})
            logger.info(f"   Active Sessions: {sessions.get('currently_active', 0)}")
            logger.info(f"   Total Cache Entries: {cache.get('total_entries', 0)}")
            logger.info(f"   Session Hit Rate: {cache.get('hit_rate_percent', 0):.1f}%")
            
        except Exception:
            logger.info("\n👥 Session Cache Performance (simulated):")
            logger.info("   Active Sessions: 5")
            logger.info("   Total Cache Entries: 50")
            logger.info("   Session Hit Rate: 80.0%")
    
    async def demonstrate_health_monitoring(self):
        """Demonstrate health monitoring capabilities."""
        logger.info("\n🏥 Demonstrating Health Monitoring")
        logger.info("=" * 50)
        
        # Check cache manager health
        try:
            health = await self.cache_manager.health_check()
            logger.info(f"🏥 Cache Manager Health: {health.get('status', 'unknown').upper()}")
            
            levels = health.get('levels', {})
            for level_name, level_health in levels.items():
                status = level_health.get('status', 'unknown')
                available = level_health.get('available', False)
                size = level_health.get('size', 0)
                logger.info(f"   {level_name}: {status.upper()} ({'available' if available else 'unavailable'}), {size} entries")
                
        except Exception:
            logger.info("🏥 Cache Manager Health: HEALTHY (simulated)")
            logger.info("   l1_memory: HEALTHY (available), 45 entries")
            logger.info("   l2_redis: HEALTHY (available), 120 entries")
            logger.info("   l3_database: HEALTHY (available), 500 entries")
        
        # Check session cache health
        try:
            session_health = await self.session_cache.health_check()
            logger.info(f"\n👥 Session Cache Health: {session_health.get('status', 'unknown').upper()}")
            logger.info(f"   Active Sessions: {session_health.get('active_sessions', 0)}")
            logger.info(f"   Cleanup Running: {session_health.get('cleanup_running', False)}")
            
        except Exception:
            logger.info("\n👥 Session Cache Health: HEALTHY (simulated)")
            logger.info("   Active Sessions: 5")
            logger.info("   Cleanup Running: True")
        
        # Check warming service health
        try:
            warming_health = await self.warming_service.health_check()
            logger.info(f"\n🔥 Cache Warming Health: {warming_health.get('status', 'unknown').upper()}")
            logger.info(f"   Running: {warming_health.get('running', False)}")
            logger.info(f"   Enabled Patterns: {warming_health.get('enabled_patterns', 0)}")
            logger.info(f"   Total Runs: {warming_health.get('total_warming_runs', 0)}")
            
        except Exception:
            logger.info("\n🔥 Cache Warming Health: HEALTHY (simulated)")
            logger.info("   Running: True")
            logger.info("   Enabled Patterns: 4")
            logger.info("   Total Runs: 10")
    
    async def demonstrate_cache_cleanup(self):
        """Demonstrate cache cleanup operations."""
        logger.info("\n🧹 Demonstrating Cache Cleanup")
        logger.info("=" * 50)
        
        # Cleanup expired entries
        try:
            cleanup_results = await self.cache_manager.cleanup_expired()
            logger.info("🧹 Expired Cache Cleanup Results:")
            for level, count in cleanup_results.items():
                if count > 0:
                    logger.info(f"   {level}: {count} entries cleaned")
                else:
                    logger.info(f"   {level}: No expired entries")
                    
        except Exception:
            logger.info("🧹 Expired Cache Cleanup Results (simulated):")
            logger.info("   l1: No expired entries")
            logger.info("   l2: No expired entries")
            logger.info("   l3: 15 entries cleaned")
            logger.info("   sessions: 2 expired sessions cleaned")
        
        # Session cleanup
        try:
            session_cleanup = await self.session_cache.cleanup_expired_sessions()
            logger.info(f"\n👥 Session Cleanup Results:")
            logger.info(f"   Expired Sessions: {session_cleanup.get('expired_sessions', 0)}")
            logger.info(f"   Cleared Cache Entries: {session_cleanup.get('cleared_cache_entries', 0)}")
            
        except Exception:
            logger.info("\n👥 Session Cleanup Results (simulated):")
            logger.info("   Expired Sessions: 2")
            logger.info("   Cleared Cache Entries: 8")
    
    async def run_comprehensive_demo(self):
        """Run the complete multi-level cache demonstration."""
        logger.info("🎬 Starting Multi-Level Cache System Demonstration")
        logger.info("=" * 60)
        
        try:
            await self.initialize()
            
            # Run all demonstrations
            await self.demonstrate_basic_caching()
            await asyncio.sleep(1)
            
            await self.demonstrate_cache_promotion()
            await asyncio.sleep(1)
            
            await self.demonstrate_session_caching()
            await asyncio.sleep(1)
            
            await self.demonstrate_cache_warming()
            await asyncio.sleep(1)
            
            await self.demonstrate_performance_monitoring()
            await asyncio.sleep(1)
            
            await self.demonstrate_health_monitoring()
            await asyncio.sleep(1)
            
            await self.demonstrate_cache_cleanup()
            
            logger.info("\n🎉 Multi-Level Cache System Demonstration Complete!")
            logger.info("=" * 60)
            
            # Final summary
            logger.info("\n📋 Summary of Demonstrated Features:")
            logger.info("   ✅ Multi-level caching (L1, L2, L3)")
            logger.info("   ✅ Cache level promotion")
            logger.info("   ✅ Session-based caching")
            logger.info("   ✅ Cache warming strategies")
            logger.info("   ✅ Performance monitoring")
            logger.info("   ✅ Health monitoring")
            logger.info("   ✅ Automatic cleanup")
            
        except Exception as e:
            logger.error(f"❌ Demo failed: {e}")
            import traceback
            traceback.print_exc()


async def main():
    """Main function to run the demonstration."""
    demo = MultiLevelCacheDemo()
    await demo.run_comprehensive_demo()


if __name__ == "__main__":
    asyncio.run(main())