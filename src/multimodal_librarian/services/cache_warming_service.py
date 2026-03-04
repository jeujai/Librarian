"""
Cache Warming Service for Proactive Cache Population

This module provides intelligent cache warming strategies to proactively
populate caches with frequently accessed data, improving system performance.
"""

import asyncio
import hashlib
import json
import logging
import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from ..database.connection import get_database_connection
from ..models.search_types import SearchQuery
from .multi_level_cache_manager import get_multi_level_cache_manager

logger = logging.getLogger(__name__)


class WarmingStrategy(str, Enum):
    """Cache warming strategy types."""
    POPULAR_QUERIES = "popular_queries"
    RECENT_SEARCHES = "recent_searches"
    USER_PATTERNS = "user_patterns"
    DOCUMENT_BASED = "document_based"
    PREDICTIVE = "predictive"
    SCHEDULED = "scheduled"


@dataclass
class WarmingPattern:
    """Cache warming pattern configuration."""
    name: str
    strategy: WarmingStrategy
    query_generator: Callable
    interval_minutes: int = 60
    max_queries: int = 100
    priority: int = 1  # 1=high, 2=medium, 3=low
    enabled: bool = True
    last_run: Optional[datetime] = None
    total_runs: int = 0
    success_count: int = 0
    failure_count: int = 0
    avg_duration_seconds: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def success_rate(self) -> float:
        total = self.success_count + self.failure_count
        return (self.success_count / total * 100) if total > 0 else 0.0
    
    @property
    def next_run(self) -> Optional[datetime]:
        if self.last_run:
            return self.last_run + timedelta(minutes=self.interval_minutes)
        return datetime.now()


@dataclass
class WarmingResult:
    """Result of a cache warming operation."""
    pattern_name: str
    strategy: WarmingStrategy
    queries_attempted: int
    queries_successful: int
    queries_failed: int
    duration_seconds: float
    errors: List[str] = field(default_factory=list)
    cache_hits_before: int = 0
    cache_hits_after: int = 0
    
    @property
    def success_rate(self) -> float:
        return (self.queries_successful / self.queries_attempted * 100) if self.queries_attempted > 0 else 0.0


class CacheWarmingService:
    """
    Intelligent cache warming service for proactive cache population.
    
    Features:
    - Multiple warming strategies (popular queries, recent searches, user patterns)
    - Configurable warming patterns with scheduling
    - Priority-based warming execution
    - Performance monitoring and optimization
    - Adaptive warming based on cache hit rates
    - Integration with search analytics
    """
    
    def __init__(self):
        """Initialize cache warming service."""
        self.cache_manager = None
        self.warming_patterns: Dict[str, WarmingPattern] = {}
        self.warming_tasks: Set[asyncio.Task] = set()
        self.is_running = False
        self.stats = {
            'total_warming_runs': 0,
            'total_queries_warmed': 0,
            'total_failures': 0,
            'avg_warming_time': 0.0,
            'last_warming_time': None
        }
        
        logger.info("Cache warming service initialized")
    
    async def initialize(self):
        """Initialize the cache warming service."""
        if self.cache_manager is None:
            self.cache_manager = await get_multi_level_cache_manager()
        
        # Register default warming patterns
        await self._register_default_patterns()
        
        logger.info("Cache warming service initialized with default patterns")
    
    async def _register_default_patterns(self):
        """Register default cache warming patterns."""
        # Popular queries pattern
        self.register_warming_pattern(
            name="popular_queries",
            strategy=WarmingStrategy.POPULAR_QUERIES,
            query_generator=self._generate_popular_queries,
            interval_minutes=30,
            max_queries=50,
            priority=1
        )
        
        # Recent searches pattern
        self.register_warming_pattern(
            name="recent_searches",
            strategy=WarmingStrategy.RECENT_SEARCHES,
            query_generator=self._generate_recent_searches,
            interval_minutes=15,
            max_queries=25,
            priority=2
        )
        
        # Document-based pattern
        self.register_warming_pattern(
            name="document_based",
            strategy=WarmingStrategy.DOCUMENT_BASED,
            query_generator=self._generate_document_based_queries,
            interval_minutes=120,
            max_queries=75,
            priority=2
        )
        
        # User patterns
        self.register_warming_pattern(
            name="user_patterns",
            strategy=WarmingStrategy.USER_PATTERNS,
            query_generator=self._generate_user_pattern_queries,
            interval_minutes=60,
            max_queries=40,
            priority=3
        )
    
    def register_warming_pattern(
        self,
        name: str,
        strategy: WarmingStrategy,
        query_generator: Callable,
        interval_minutes: int = 60,
        max_queries: int = 100,
        priority: int = 2,
        enabled: bool = True,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """
        Register a cache warming pattern.
        
        Args:
            name: Unique pattern name
            strategy: Warming strategy type
            query_generator: Async function to generate queries
            interval_minutes: How often to run the pattern
            max_queries: Maximum queries per run
            priority: Pattern priority (1=high, 2=medium, 3=low)
            enabled: Whether pattern is enabled
            metadata: Additional pattern metadata
        """
        pattern = WarmingPattern(
            name=name,
            strategy=strategy,
            query_generator=query_generator,
            interval_minutes=interval_minutes,
            max_queries=max_queries,
            priority=priority,
            enabled=enabled,
            metadata=metadata or {}
        )
        
        self.warming_patterns[name] = pattern
        logger.info(f"Registered warming pattern: {name} ({strategy.value})")
    
    def unregister_warming_pattern(self, name: str) -> bool:
        """Unregister a warming pattern."""
        if name in self.warming_patterns:
            del self.warming_patterns[name]
            logger.info(f"Unregistered warming pattern: {name}")
            return True
        return False
    
    def enable_pattern(self, name: str) -> bool:
        """Enable a warming pattern."""
        if name in self.warming_patterns:
            self.warming_patterns[name].enabled = True
            logger.info(f"Enabled warming pattern: {name}")
            return True
        return False
    
    def disable_pattern(self, name: str) -> bool:
        """Disable a warming pattern."""
        if name in self.warming_patterns:
            self.warming_patterns[name].enabled = False
            logger.info(f"Disabled warming pattern: {name}")
            return True
        return False
    
    async def start_warming(self):
        """Start the cache warming scheduler."""
        if self.is_running:
            return
        
        if not self.cache_manager:
            await self.initialize()
        
        self.is_running = True
        
        # Start warming tasks for each pattern
        for pattern_name, pattern in self.warming_patterns.items():
            if pattern.enabled:
                task = asyncio.create_task(
                    self._warming_loop(pattern_name)
                )
                self.warming_tasks.add(task)
        
        logger.info(f"Cache warming started with {len(self.warming_tasks)} active patterns")
    
    async def stop_warming(self):
        """Stop the cache warming scheduler."""
        self.is_running = False
        
        # Cancel all warming tasks
        for task in self.warming_tasks:
            task.cancel()
        
        # Wait for tasks to complete
        if self.warming_tasks:
            await asyncio.gather(*self.warming_tasks, return_exceptions=True)
        
        self.warming_tasks.clear()
        logger.info("Cache warming stopped")
    
    async def _warming_loop(self, pattern_name: str):
        """Main warming loop for a specific pattern."""
        pattern = self.warming_patterns.get(pattern_name)
        if not pattern:
            return
        
        while self.is_running and pattern.enabled:
            try:
                # Calculate next run time
                if pattern.last_run:
                    next_run = pattern.last_run + timedelta(minutes=pattern.interval_minutes)
                    wait_seconds = (next_run - datetime.now()).total_seconds()
                    
                    if wait_seconds > 0:
                        await asyncio.sleep(min(wait_seconds, 60))  # Check every minute
                        continue
                
                # Run warming for this pattern
                await self._run_warming_pattern(pattern_name)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Warming loop error for pattern {pattern_name}: {e}")
                await asyncio.sleep(60)  # Wait before retrying
    
    async def _run_warming_pattern(self, pattern_name: str) -> WarmingResult:
        """Run warming for a specific pattern."""
        pattern = self.warming_patterns.get(pattern_name)
        if not pattern or not pattern.enabled:
            return WarmingResult(
                pattern_name=pattern_name,
                strategy=WarmingStrategy.SCHEDULED,
                queries_attempted=0,
                queries_successful=0,
                queries_failed=0,
                duration_seconds=0.0,
                errors=["Pattern not found or disabled"]
            )
        
        start_time = datetime.now()
        logger.info(f"Starting cache warming for pattern: {pattern_name}")
        
        try:
            # Get cache stats before warming
            cache_stats_before = await self.cache_manager.get_comprehensive_stats()
            hits_before = cache_stats_before.get('overall', {}).get('total_hits', 0)
            
            # Generate queries using the pattern's generator
            queries = await pattern.query_generator(pattern.max_queries)
            
            # Warm cache with generated queries
            result = await self._warm_queries(queries, pattern_name, pattern.strategy)
            
            # Get cache stats after warming
            cache_stats_after = await self.cache_manager.get_comprehensive_stats()
            hits_after = cache_stats_after.get('overall', {}).get('total_hits', 0)
            
            result.cache_hits_before = hits_before
            result.cache_hits_after = hits_after
            
            # Update pattern statistics
            duration = (datetime.now() - start_time).total_seconds()
            pattern.last_run = start_time
            pattern.total_runs += 1
            pattern.success_count += result.queries_successful
            pattern.failure_count += result.queries_failed
            
            # Update average duration
            if pattern.total_runs > 1:
                pattern.avg_duration_seconds = (
                    (pattern.avg_duration_seconds * (pattern.total_runs - 1) + duration) / 
                    pattern.total_runs
                )
            else:
                pattern.avg_duration_seconds = duration
            
            # Update global stats
            self.stats['total_warming_runs'] += 1
            self.stats['total_queries_warmed'] += result.queries_successful
            self.stats['total_failures'] += result.queries_failed
            self.stats['last_warming_time'] = start_time
            
            logger.info(f"Completed warming for {pattern_name}: {result.queries_successful}/{result.queries_attempted} successful")
            return result
            
        except Exception as e:
            logger.error(f"Warming pattern {pattern_name} failed: {e}")
            pattern.failure_count += 1
            
            return WarmingResult(
                pattern_name=pattern_name,
                strategy=pattern.strategy,
                queries_attempted=0,
                queries_successful=0,
                queries_failed=1,
                duration_seconds=(datetime.now() - start_time).total_seconds(),
                errors=[str(e)]
            )
    
    async def _warm_queries(
        self, 
        queries: List[str], 
        pattern_name: str, 
        strategy: WarmingStrategy
    ) -> WarmingResult:
        """Warm cache with a list of queries."""
        start_time = datetime.now()
        successful = 0
        failed = 0
        errors = []
        
        for query in queries:
            try:
                # Generate cache key for the query
                cache_key = self._generate_query_cache_key(query)
                
                # Check if already cached
                cached_value = await self.cache_manager.get(cache_key)
                if cached_value is not None:
                    successful += 1
                    continue
                
                # Simulate search operation to warm cache
                # In a real implementation, this would call the actual search service
                search_result = await self._simulate_search(query)
                
                if search_result:
                    # Cache the result
                    await self.cache_manager.set(cache_key, search_result, ttl=3600)
                    successful += 1
                    logger.debug(f"Warmed cache for query: '{query}'")
                else:
                    failed += 1
                    errors.append(f"No results for query: '{query}'")
                
            except Exception as e:
                failed += 1
                errors.append(f"Query '{query}': {str(e)}")
                logger.warning(f"Failed to warm cache for query '{query}': {e}")
        
        duration = (datetime.now() - start_time).total_seconds()
        
        return WarmingResult(
            pattern_name=pattern_name,
            strategy=strategy,
            queries_attempted=len(queries),
            queries_successful=successful,
            queries_failed=failed,
            duration_seconds=duration,
            errors=errors
        )
    
    def _generate_query_cache_key(self, query: str) -> str:
        """Generate cache key for a query."""
        query_hash = hashlib.sha256(query.encode()).hexdigest()[:16]
        return f"search_result:{query_hash}"
    
    async def _simulate_search(self, query: str) -> Optional[Dict[str, Any]]:
        """Simulate search operation for cache warming."""
        # This is a placeholder - in real implementation, this would
        # call the actual search service
        await asyncio.sleep(0.01)  # Simulate search time
        
        return {
            'query': query,
            'results': [
                {
                    'content': f"Sample result for query: {query}",
                    'score': 0.8,
                    'source': 'warming_simulation'
                }
            ],
            'total_results': 1,
            'search_time_ms': 10.0
        }
    
    async def _generate_popular_queries(self, max_queries: int) -> List[str]:
        """Generate popular queries based on search analytics."""
        try:
            db = await get_database_connection()
            
            # Get most frequent search queries from the last 7 days
            result = await db.fetch_all("""
                SELECT query_text, COUNT(*) as frequency
                FROM search_analytics 
                WHERE created_at > NOW() - INTERVAL '7 days'
                AND query_text IS NOT NULL
                GROUP BY query_text
                ORDER BY frequency DESC
                LIMIT $1
            """, max_queries)
            
            queries = [row['query_text'] for row in result]
            
            # Add some default popular queries if database is empty
            if not queries:
                queries = [
                    "machine learning",
                    "artificial intelligence",
                    "data science",
                    "python programming",
                    "web development",
                    "database design",
                    "software architecture",
                    "cloud computing",
                    "cybersecurity",
                    "mobile development"
                ]
            
            return queries[:max_queries]
            
        except Exception as e:
            logger.warning(f"Failed to generate popular queries: {e}")
            return ["machine learning", "artificial intelligence", "data science"]
    
    async def _generate_recent_searches(self, max_queries: int) -> List[str]:
        """Generate recent search queries."""
        try:
            db = await get_database_connection()
            
            # Get recent unique search queries from the last 24 hours
            result = await db.fetch_all("""
                SELECT DISTINCT query_text
                FROM search_analytics 
                WHERE created_at > NOW() - INTERVAL '24 hours'
                AND query_text IS NOT NULL
                ORDER BY created_at DESC
                LIMIT $1
            """, max_queries)
            
            queries = [row['query_text'] for row in result]
            
            # Add some recent-style queries if database is empty
            if not queries:
                queries = [
                    "latest trends in AI",
                    "recent developments",
                    "current best practices",
                    "new technologies 2024",
                    "updated documentation"
                ]
            
            return queries[:max_queries]
            
        except Exception as e:
            logger.warning(f"Failed to generate recent searches: {e}")
            return ["recent developments", "latest updates"]
    
    async def _generate_document_based_queries(self, max_queries: int) -> List[str]:
        """Generate queries based on document content."""
        try:
            db = await get_database_connection()
            
            # Get keywords from recently uploaded documents
            result = await db.fetch_all("""
                SELECT title, metadata->>'content_preview' as content_preview
                FROM multimodal_librarian.knowledge_sources 
                WHERE created_at > NOW() - INTERVAL '30 days'
                ORDER BY created_at DESC
                LIMIT $1
            """, max_queries // 2)
            
            queries = []
            for row in result:
                # Extract keywords from title and content
                title_words = row['title'].split()[:3] if row['title'] else []
                if title_words:
                    queries.append(' '.join(title_words))
                
                # Extract from content preview
                if row['content_preview']:
                    content_words = row['content_preview'].split()[:2]
                    if content_words:
                        queries.append(' '.join(content_words))
            
            # Add some document-based queries if database is empty
            if not queries:
                queries = [
                    "document analysis",
                    "content extraction",
                    "text processing",
                    "information retrieval",
                    "document management"
                ]
            
            return queries[:max_queries]
            
        except Exception as e:
            logger.warning(f"Failed to generate document-based queries: {e}")
            return ["document analysis", "content extraction"]
    
    async def _generate_user_pattern_queries(self, max_queries: int) -> List[str]:
        """Generate queries based on user search patterns."""
        try:
            db = await get_database_connection()
            
            # Get queries from users with high activity
            result = await db.fetch_all("""
                SELECT query_text, COUNT(*) as user_frequency
                FROM search_analytics sa
                JOIN (
                    SELECT user_id, COUNT(*) as total_searches
                    FROM search_analytics
                    WHERE created_at > NOW() - INTERVAL '7 days'
                    GROUP BY user_id
                    HAVING COUNT(*) > 5
                ) active_users ON sa.user_id = active_users.user_id
                WHERE sa.created_at > NOW() - INTERVAL '7 days'
                GROUP BY query_text
                ORDER BY user_frequency DESC
                LIMIT $1
            """, max_queries)
            
            queries = [row['query_text'] for row in result]
            
            # Add some pattern-based queries if database is empty
            if not queries:
                queries = [
                    "how to implement",
                    "best practices for",
                    "tutorial on",
                    "examples of",
                    "guide to"
                ]
            
            return queries[:max_queries]
            
        except Exception as e:
            logger.warning(f"Failed to generate user pattern queries: {e}")
            return ["how to implement", "best practices"]
    
    async def warm_specific_queries(self, queries: List[str]) -> WarmingResult:
        """Warm cache with specific queries."""
        return await self._warm_queries(queries, "manual", WarmingStrategy.SCHEDULED)
    
    async def warm_pattern_now(self, pattern_name: str) -> WarmingResult:
        """Immediately run warming for a specific pattern."""
        return await self._run_warming_pattern(pattern_name)
    
    def get_pattern_stats(self, pattern_name: str) -> Optional[Dict[str, Any]]:
        """Get statistics for a specific warming pattern."""
        pattern = self.warming_patterns.get(pattern_name)
        if not pattern:
            return None
        
        return {
            'name': pattern.name,
            'strategy': pattern.strategy.value,
            'enabled': pattern.enabled,
            'priority': pattern.priority,
            'interval_minutes': pattern.interval_minutes,
            'max_queries': pattern.max_queries,
            'total_runs': pattern.total_runs,
            'success_count': pattern.success_count,
            'failure_count': pattern.failure_count,
            'success_rate_percent': pattern.success_rate,
            'avg_duration_seconds': pattern.avg_duration_seconds,
            'last_run': pattern.last_run.isoformat() if pattern.last_run else None,
            'next_run': pattern.next_run.isoformat() if pattern.next_run else None
        }
    
    def get_all_patterns_stats(self) -> Dict[str, Any]:
        """Get statistics for all warming patterns."""
        patterns_stats = {}
        for name in self.warming_patterns:
            patterns_stats[name] = self.get_pattern_stats(name)
        
        return {
            'patterns': patterns_stats,
            'global_stats': {
                'total_patterns': len(self.warming_patterns),
                'enabled_patterns': sum(1 for p in self.warming_patterns.values() if p.enabled),
                'running': self.is_running,
                'active_tasks': len(self.warming_tasks),
                **self.stats
            }
        }
    
    async def health_check(self) -> Dict[str, Any]:
        """Perform health check on cache warming service."""
        enabled_patterns = sum(1 for p in self.warming_patterns.values() if p.enabled)
        
        health = {
            'status': 'healthy',
            'running': self.is_running,
            'cache_manager_available': self.cache_manager is not None,
            'total_patterns': len(self.warming_patterns),
            'enabled_patterns': enabled_patterns,
            'active_tasks': len(self.warming_tasks),
            'total_warming_runs': self.stats['total_warming_runs'],
            'last_warming': self.stats['last_warming_time'].isoformat() if self.stats['last_warming_time'] else None
        }
        
        # Check for issues
        if not self.is_running and enabled_patterns > 0:
            health['status'] = 'degraded'
            health['warning'] = 'Warming service not running but patterns are enabled'
        
        if self.cache_manager is None:
            health['status'] = 'unhealthy'
            health['error'] = 'Cache manager not available'
        
        return health


# Global cache warming service instance
_cache_warming_service = None

async def get_cache_warming_service() -> CacheWarmingService:
    """Get global cache warming service instance."""
    global _cache_warming_service
    if _cache_warming_service is None:
        _cache_warming_service = CacheWarmingService()
        await _cache_warming_service.initialize()
    return _cache_warming_service