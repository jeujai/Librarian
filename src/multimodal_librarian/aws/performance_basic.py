#!/usr/bin/env python3
"""
Basic Performance Optimization Module for AWS Learning Deployment

This module provides basic performance optimization features including:
- Database connection pooling
- Query optimization helpers
- Caching utilities
- Performance monitoring integration
- Cost optimization strategies
"""

import os
import time
import asyncio
import threading
from typing import Dict, Any, Optional, List, Callable
from datetime import datetime, timedelta
from dataclasses import dataclass
from functools import wraps
import json

import boto3
import redis
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..config import get_settings
from ..logging_config import get_logger
from ..database.connection import db_manager


@dataclass
class PerformanceMetrics:
    """Performance metrics data structure."""
    timestamp: datetime
    response_time_ms: float
    query_time_ms: float
    cache_hit_rate: float
    memory_usage_mb: float
    cpu_usage_percent: float
    active_connections: int


class DatabaseOptimizer:
    """Database performance optimization utilities."""
    
    def __init__(self):
        self.logger = get_logger("database_optimizer")
        self.settings = get_settings()
        
        # Query performance cache
        self._query_stats = {}
        self._slow_queries = []
        
    def optimize_connection_pool(self) -> Dict[str, Any]:
        """Optimize database connection pool settings."""
        try:
            # Get current pool status
            if not db_manager.engine:
                return {"error": "Database not initialized"}
            
            pool = db_manager.engine.pool
            
            current_stats = {
                "pool_size": pool.size(),
                "checked_out": pool.checkedout(),
                "overflow": pool.overflow(),
                "checked_in": pool.checkedin(),
            }
            
            # Calculate optimal pool size based on usage
            optimal_size = max(5, min(20, current_stats["checked_out"] * 2))
            
            recommendations = []
            
            if current_stats["checked_out"] > current_stats["pool_size"] * 0.8:
                recommendations.append("Consider increasing pool size")
            
            if current_stats["overflow"] > 0:
                recommendations.append("Pool overflow detected - increase max_overflow")
            
            self.logger.info(f"Connection pool stats: {current_stats}")
            
            return {
                "current_stats": current_stats,
                "optimal_pool_size": optimal_size,
                "recommendations": recommendations,
                "status": "healthy" if not recommendations else "needs_attention"
            }
            
        except Exception as e:
            self.logger.error(f"Error optimizing connection pool: {e}")
            return {"error": str(e)}
    
    def analyze_slow_queries(self, threshold_ms: float = 1000) -> Dict[str, Any]:
        """Analyze slow queries and provide optimization suggestions."""
        try:
            with db_manager.get_session() as session:
                # Enable query logging for analysis
                slow_queries = []
                
                # Query to find slow queries (PostgreSQL specific)
                slow_query_sql = text("""
                    SELECT 
                        query,
                        calls,
                        total_time,
                        mean_time,
                        rows
                    FROM pg_stat_statements 
                    WHERE mean_time > :threshold
                    ORDER BY mean_time DESC 
                    LIMIT 10
                """)
                
                try:
                    result = session.execute(slow_query_sql, {"threshold": threshold_ms})
                    for row in result:
                        slow_queries.append({
                            "query": row.query[:200] + "..." if len(row.query) > 200 else row.query,
                            "calls": row.calls,
                            "total_time_ms": round(row.total_time, 2),
                            "mean_time_ms": round(row.mean_time, 2),
                            "rows_affected": row.rows
                        })
                except Exception as e:
                    # pg_stat_statements might not be enabled
                    self.logger.warning(f"Could not query pg_stat_statements: {e}")
                    slow_queries = []
                
                # Generate optimization suggestions
                suggestions = self._generate_query_suggestions(slow_queries)
                
                return {
                    "threshold_ms": threshold_ms,
                    "slow_queries": slow_queries,
                    "total_slow_queries": len(slow_queries),
                    "optimization_suggestions": suggestions
                }
                
        except Exception as e:
            self.logger.error(f"Error analyzing slow queries: {e}")
            return {"error": str(e)}
    
    def _generate_query_suggestions(self, slow_queries: List[Dict]) -> List[str]:
        """Generate optimization suggestions based on slow queries."""
        suggestions = []
        
        if not slow_queries:
            suggestions.append("No slow queries detected - performance looks good!")
            return suggestions
        
        # Common optimization suggestions
        suggestions.extend([
            "Consider adding indexes on frequently queried columns",
            "Review WHERE clauses for optimization opportunities",
            "Consider query result caching for frequently accessed data",
            "Analyze table statistics and consider VACUUM ANALYZE",
            "Review JOIN operations for efficiency"
        ])
        
        # Query-specific suggestions
        for query in slow_queries:
            if query["mean_time_ms"] > 5000:
                suggestions.append(f"Critical: Query taking {query['mean_time_ms']:.0f}ms needs immediate attention")
            
            if "SELECT *" in query["query"].upper():
                suggestions.append("Avoid SELECT * - specify only needed columns")
            
            if query["calls"] > 1000:
                suggestions.append(f"High-frequency query ({query['calls']} calls) - consider caching")
        
        return list(set(suggestions))  # Remove duplicates
    
    def create_performance_indexes(self) -> Dict[str, Any]:
        """Create recommended performance indexes."""
        try:
            with db_manager.get_session() as session:
                indexes_created = []
                
                # Common performance indexes for the application
                index_queries = [
                    # Conversations table indexes
                    "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_conversations_user_id ON conversations(user_id)",
                    "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_conversations_created_at ON conversations(created_at)",
                    "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_conversations_status ON conversations(status)",
                    
                    # Messages table indexes
                    "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_messages_conversation_id ON messages(conversation_id)",
                    "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_messages_timestamp ON messages(timestamp)",
                    "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_messages_message_type ON messages(message_type)",
                    
                    # Documents table indexes
                    "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_documents_user_id ON documents(user_id)",
                    "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_documents_created_at ON documents(created_at)",
                    "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_documents_status ON documents(status)",
                    
                    # Composite indexes for common queries
                    "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_conversations_user_status ON conversations(user_id, status)",
                    "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_messages_conv_timestamp ON messages(conversation_id, timestamp)",
                ]
                
                for index_query in index_queries:
                    try:
                        session.execute(text(index_query))
                        index_name = index_query.split("idx_")[1].split(" ")[0] if "idx_" in index_query else "unknown"
                        indexes_created.append(index_name)
                        self.logger.info(f"Created index: {index_name}")
                    except Exception as e:
                        self.logger.warning(f"Could not create index: {e}")
                
                session.commit()
                
                return {
                    "indexes_created": indexes_created,
                    "total_created": len(indexes_created),
                    "status": "success"
                }
                
        except Exception as e:
            self.logger.error(f"Error creating performance indexes: {e}")
            return {"error": str(e)}


class CacheManager:
    """Redis cache management for performance optimization."""
    
    def __init__(self):
        self.logger = get_logger("cache_manager")
        self.settings = get_settings()
        
        # Initialize Redis connection
        self.redis_client = None
        self._initialize_redis()
        
        # Cache statistics
        self._cache_stats = {
            "hits": 0,
            "misses": 0,
            "sets": 0,
            "deletes": 0
        }
    
    def _initialize_redis(self):
        """Initialize Redis connection."""
        try:
            redis_host = os.getenv("REDIS_HOST", "localhost")
            redis_port = int(os.getenv("REDIS_PORT", "6379"))
            redis_db = int(os.getenv("REDIS_DB", "0"))
            
            self.redis_client = redis.Redis(
                host=redis_host,
                port=redis_port,
                db=redis_db,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5,
                retry_on_timeout=True,
                health_check_interval=30
            )
            
            # Test connection
            self.redis_client.ping()
            self.logger.info("Redis cache connection established")
            
        except Exception as e:
            self.logger.warning(f"Could not connect to Redis: {e}")
            self.redis_client = None
    
    def get(self, key: str) -> Optional[Any]:
        """Get value from cache."""
        if not self.redis_client:
            return None
        
        try:
            value = self.redis_client.get(key)
            if value is not None:
                self._cache_stats["hits"] += 1
                return json.loads(value)
            else:
                self._cache_stats["misses"] += 1
                return None
        except Exception as e:
            self.logger.error(f"Cache get error: {e}")
            self._cache_stats["misses"] += 1
            return None
    
    def set(self, key: str, value: Any, ttl: int = 3600) -> bool:
        """Set value in cache with TTL."""
        if not self.redis_client:
            return False
        
        try:
            serialized_value = json.dumps(value, default=str)
            result = self.redis_client.setex(key, ttl, serialized_value)
            if result:
                self._cache_stats["sets"] += 1
            return result
        except Exception as e:
            self.logger.error(f"Cache set error: {e}")
            return False
    
    def delete(self, key: str) -> bool:
        """Delete value from cache."""
        if not self.redis_client:
            return False
        
        try:
            result = self.redis_client.delete(key)
            if result:
                self._cache_stats["deletes"] += 1
            return bool(result)
        except Exception as e:
            self.logger.error(f"Cache delete error: {e}")
            return False
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache performance statistics."""
        if not self.redis_client:
            return {"error": "Redis not available"}
        
        try:
            # Get Redis info
            redis_info = self.redis_client.info()
            
            # Calculate hit rate
            total_requests = self._cache_stats["hits"] + self._cache_stats["misses"]
            hit_rate = (self._cache_stats["hits"] / max(1, total_requests)) * 100
            
            return {
                "cache_stats": self._cache_stats,
                "hit_rate_percent": round(hit_rate, 2),
                "redis_info": {
                    "connected_clients": redis_info.get("connected_clients", 0),
                    "used_memory_human": redis_info.get("used_memory_human", "0B"),
                    "keyspace_hits": redis_info.get("keyspace_hits", 0),
                    "keyspace_misses": redis_info.get("keyspace_misses", 0),
                    "total_commands_processed": redis_info.get("total_commands_processed", 0)
                },
                "status": "healthy"
            }
        except Exception as e:
            self.logger.error(f"Error getting cache stats: {e}")
            return {"error": str(e)}
    
    def clear_cache(self, pattern: Optional[str] = None) -> Dict[str, Any]:
        """Clear cache entries matching pattern."""
        if not self.redis_client:
            return {"error": "Redis not available"}
        
        try:
            if pattern:
                keys = self.redis_client.keys(pattern)
                if keys:
                    deleted = self.redis_client.delete(*keys)
                    return {"deleted_keys": deleted, "pattern": pattern}
                else:
                    return {"deleted_keys": 0, "pattern": pattern}
            else:
                self.redis_client.flushdb()
                return {"action": "flushed_all", "status": "success"}
        except Exception as e:
            self.logger.error(f"Error clearing cache: {e}")
            return {"error": str(e)}


def cache_result(ttl: int = 3600, key_prefix: str = ""):
    """Decorator to cache function results."""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Create cache key
            cache_key = f"{key_prefix}:{func.__name__}:{hash(str(args) + str(kwargs))}"
            
            # Try to get from cache
            cache_manager = CacheManager()
            cached_result = cache_manager.get(cache_key)
            
            if cached_result is not None:
                return cached_result
            
            # Execute function and cache result
            result = func(*args, **kwargs)
            cache_manager.set(cache_key, result, ttl)
            
            return result
        return wrapper
    return decorator


class PerformanceOptimizer:
    """Main performance optimization coordinator."""
    
    def __init__(self):
        self.logger = get_logger("performance_optimizer")
        self.settings = get_settings()
        
        # Initialize components
        self.db_optimizer = DatabaseOptimizer()
        self.cache_manager = CacheManager()
        
        # Performance monitoring
        self._metrics_history = []
        self._monitoring_active = False
    
    def run_performance_analysis(self) -> Dict[str, Any]:
        """Run comprehensive performance analysis."""
        self.logger.info("Starting performance analysis...")
        
        analysis_results = {
            "timestamp": datetime.now().isoformat(),
            "database_analysis": {},
            "cache_analysis": {},
            "system_analysis": {},
            "recommendations": []
        }
        
        try:
            # Database analysis
            analysis_results["database_analysis"] = {
                "connection_pool": self.db_optimizer.optimize_connection_pool(),
                "slow_queries": self.db_optimizer.analyze_slow_queries(),
            }
            
            # Cache analysis
            analysis_results["cache_analysis"] = self.cache_manager.get_cache_stats()
            
            # System analysis
            analysis_results["system_analysis"] = self._analyze_system_performance()
            
            # Generate recommendations
            analysis_results["recommendations"] = self._generate_performance_recommendations(analysis_results)
            
            self.logger.info("Performance analysis completed")
            
        except Exception as e:
            self.logger.error(f"Error in performance analysis: {e}")
            analysis_results["error"] = str(e)
        
        return analysis_results
    
    def _analyze_system_performance(self) -> Dict[str, Any]:
        """Analyze system-level performance metrics."""
        try:
            import psutil
            
            # Get system metrics
            cpu_percent = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')
            
            # Get process-specific metrics
            process = psutil.Process()
            process_memory = process.memory_info()
            
            return {
                "cpu_usage_percent": cpu_percent,
                "memory_usage_percent": memory.percent,
                "memory_available_gb": round(memory.available / (1024**3), 2),
                "disk_usage_percent": disk.percent,
                "disk_free_gb": round(disk.free / (1024**3), 2),
                "process_memory_mb": round(process_memory.rss / (1024**2), 2),
                "load_average": os.getloadavg() if hasattr(os, 'getloadavg') else None,
                "status": "healthy"
            }
        except Exception as e:
            self.logger.error(f"Error analyzing system performance: {e}")
            return {"error": str(e)}
    
    def _generate_performance_recommendations(self, analysis: Dict[str, Any]) -> List[str]:
        """Generate performance optimization recommendations."""
        recommendations = []
        
        try:
            # Database recommendations
            db_analysis = analysis.get("database_analysis", {})
            if db_analysis.get("connection_pool", {}).get("recommendations"):
                recommendations.extend(db_analysis["connection_pool"]["recommendations"])
            
            if db_analysis.get("slow_queries", {}).get("optimization_suggestions"):
                recommendations.extend(db_analysis["slow_queries"]["optimization_suggestions"][:3])  # Top 3
            
            # Cache recommendations
            cache_analysis = analysis.get("cache_analysis", {})
            if cache_analysis.get("hit_rate_percent", 0) < 50:
                recommendations.append("Cache hit rate is low - review caching strategy")
            
            # System recommendations
            system_analysis = analysis.get("system_analysis", {})
            if system_analysis.get("cpu_usage_percent", 0) > 80:
                recommendations.append("High CPU usage - consider scaling or optimization")
            
            if system_analysis.get("memory_usage_percent", 0) > 85:
                recommendations.append("High memory usage - review memory leaks and consider scaling")
            
            if system_analysis.get("disk_usage_percent", 0) > 85:
                recommendations.append("High disk usage - clean up logs and temporary files")
            
            # General recommendations
            if not recommendations:
                recommendations.append("System performance looks good - no immediate optimizations needed")
            
        except Exception as e:
            self.logger.error(f"Error generating recommendations: {e}")
            recommendations.append("Error generating recommendations - check logs")
        
        return recommendations
    
    def optimize_application_performance(self) -> Dict[str, Any]:
        """Apply automatic performance optimizations."""
        self.logger.info("Applying performance optimizations...")
        
        results = {
            "timestamp": datetime.now().isoformat(),
            "optimizations_applied": [],
            "errors": []
        }
        
        try:
            # Create database indexes
            index_result = self.db_optimizer.create_performance_indexes()
            if "error" not in index_result:
                results["optimizations_applied"].append({
                    "type": "database_indexes",
                    "details": index_result
                })
            else:
                results["errors"].append(f"Database indexing: {index_result['error']}")
            
            # Clear old cache entries
            cache_clear_result = self.cache_manager.clear_cache("temp:*")
            if "error" not in cache_clear_result:
                results["optimizations_applied"].append({
                    "type": "cache_cleanup",
                    "details": cache_clear_result
                })
            else:
                results["errors"].append(f"Cache cleanup: {cache_clear_result['error']}")
            
            self.logger.info(f"Applied {len(results['optimizations_applied'])} optimizations")
            
        except Exception as e:
            self.logger.error(f"Error applying optimizations: {e}")
            results["errors"].append(str(e))
        
        return results
    
    def get_performance_summary(self) -> Dict[str, Any]:
        """Get a summary of current performance status."""
        try:
            # Get current metrics
            analysis = self.run_performance_analysis()
            
            # Calculate overall health score
            health_score = self._calculate_health_score(analysis)
            
            return {
                "timestamp": datetime.now().isoformat(),
                "overall_health_score": health_score,
                "status": "healthy" if health_score > 80 else "degraded" if health_score > 60 else "critical",
                "key_metrics": {
                    "database_pool_utilization": analysis.get("database_analysis", {}).get("connection_pool", {}).get("current_stats", {}).get("checked_out", 0),
                    "cache_hit_rate": analysis.get("cache_analysis", {}).get("hit_rate_percent", 0),
                    "cpu_usage": analysis.get("system_analysis", {}).get("cpu_usage_percent", 0),
                    "memory_usage": analysis.get("system_analysis", {}).get("memory_usage_percent", 0)
                },
                "recommendations_count": len(analysis.get("recommendations", [])),
                "top_recommendations": analysis.get("recommendations", [])[:3]
            }
        except Exception as e:
            self.logger.error(f"Error getting performance summary: {e}")
            return {"error": str(e)}
    
    def _calculate_health_score(self, analysis: Dict[str, Any]) -> int:
        """Calculate overall system health score (0-100)."""
        try:
            score = 100
            
            # Database health
            db_analysis = analysis.get("database_analysis", {})
            if db_analysis.get("connection_pool", {}).get("recommendations"):
                score -= 10
            
            slow_queries = db_analysis.get("slow_queries", {}).get("total_slow_queries", 0)
            if slow_queries > 5:
                score -= 15
            elif slow_queries > 0:
                score -= 5
            
            # Cache health
            cache_hit_rate = analysis.get("cache_analysis", {}).get("hit_rate_percent", 100)
            if cache_hit_rate < 50:
                score -= 20
            elif cache_hit_rate < 70:
                score -= 10
            
            # System health
            system_analysis = analysis.get("system_analysis", {})
            cpu_usage = system_analysis.get("cpu_usage_percent", 0)
            memory_usage = system_analysis.get("memory_usage_percent", 0)
            
            if cpu_usage > 90:
                score -= 25
            elif cpu_usage > 80:
                score -= 15
            elif cpu_usage > 70:
                score -= 5
            
            if memory_usage > 95:
                score -= 25
            elif memory_usage > 85:
                score -= 15
            elif memory_usage > 75:
                score -= 5
            
            return max(0, score)
            
        except Exception as e:
            self.logger.error(f"Error calculating health score: {e}")
            return 50  # Default to moderate health


# Global performance optimizer instance
performance_optimizer = PerformanceOptimizer()


# Convenience functions
def get_performance_summary() -> Dict[str, Any]:
    """Get current performance summary."""
    return performance_optimizer.get_performance_summary()


def run_performance_analysis() -> Dict[str, Any]:
    """Run comprehensive performance analysis."""
    return performance_optimizer.run_performance_analysis()


def optimize_performance() -> Dict[str, Any]:
    """Apply automatic performance optimizations."""
    return performance_optimizer.optimize_application_performance()