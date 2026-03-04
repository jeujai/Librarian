"""
Database-Specific Connection Pool Optimizers

This module provides specialized connection pool optimizers for each database type
used in local development: PostgreSQL, Neo4j, and Milvus. Each optimizer implements
database-specific optimization strategies and monitoring.
"""

import asyncio
import logging
import time
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta

import structlog
from sqlalchemy import text
from sqlalchemy.pool import QueuePool

from .connection_pool_optimizer import (
    ConnectionPoolOptimizer, OptimizationStrategy, PoolOptimizationMetrics,
    OptimizationRecommendation
)

logger = structlog.get_logger(__name__)


class PostgreSQLPoolOptimizer(ConnectionPoolOptimizer):
    """
    PostgreSQL-specific connection pool optimizer.
    
    Provides PostgreSQL-specific optimizations including:
    - Query performance analysis
    - Connection pool sizing based on PostgreSQL best practices
    - Lock contention monitoring
    - Vacuum and maintenance scheduling awareness
    """
    
    def __init__(
        self,
        postgresql_client,
        optimization_strategy: OptimizationStrategy = OptimizationStrategy.BALANCED,
        **kwargs
    ):
        """
        Initialize PostgreSQL pool optimizer.
        
        Args:
            postgresql_client: LocalPostgreSQLClient instance
            optimization_strategy: Optimization strategy
            **kwargs: Additional optimizer parameters
        """
        super().__init__(
            pool_name="postgresql",
            optimization_strategy=optimization_strategy,
            **kwargs
        )
        self.postgresql_client = postgresql_client
        self._query_stats: Dict[str, Any] = {}
        self._lock_stats: Dict[str, Any] = {}
        
    async def _collect_metrics(self) -> None:
        """Collect PostgreSQL-specific metrics."""
        await super()._collect_metrics()
        
        try:
            if not self.postgresql_client or not self.postgresql_client.engine:
                return
            
            # Get pool status from SQLAlchemy
            pool_status = self.postgresql_client.get_pool_status()
            
            with self._lock:
                # Update basic pool metrics
                self.current_metrics.pool_size = pool_status.get("size", 0)
                self.current_metrics.checked_out = pool_status.get("checked_out", 0)
                self.current_metrics.checked_in = pool_status.get("checked_in", 0)
                self.current_metrics.overflow_count = pool_status.get("overflow", 0)
                self.current_metrics.invalid_count = pool_status.get("invalid", 0)
                
                # Calculate utilization
                if self.current_metrics.pool_size > 0:
                    self.current_metrics.utilization_percentage = (
                        self.current_metrics.checked_out / self.current_metrics.pool_size
                    ) * 100
                
                # Update timing metrics
                if self.checkout_times:
                    self.current_metrics.average_checkout_time = sum(self.checkout_times) / len(self.checkout_times)
                
                if self.checkin_times:
                    self.current_metrics.average_checkin_time = sum(self.checkin_times) / len(self.checkin_times)
                
                # Update health metrics
                healthy_connections = sum(
                    1 for conn in self.connection_metrics.values() if conn.is_healthy
                )
                self.current_metrics.healthy_connections = healthy_connections
                self.current_metrics.unhealthy_connections = len(self.connection_metrics) - healthy_connections
            
            # Collect PostgreSQL-specific statistics
            await self._collect_postgresql_stats()
            
        except Exception as e:
            logger.error(
                "Error collecting PostgreSQL metrics",
                error=str(e)
            )
    
    async def _collect_postgresql_stats(self) -> None:
        """Collect PostgreSQL-specific statistics."""
        try:
            async with self.postgresql_client.get_async_session() as session:
                # Get connection statistics
                conn_stats_query = """
                SELECT 
                    state,
                    COUNT(*) as count,
                    AVG(EXTRACT(EPOCH FROM (now() - state_change))) as avg_duration
                FROM pg_stat_activity 
                WHERE datname = current_database()
                GROUP BY state
                """
                
                result = await session.execute(text(conn_stats_query))
                conn_stats = {row[0]: {"count": row[1], "avg_duration": row[2]} for row in result}
                
                # Get lock statistics
                lock_stats_query = """
                SELECT 
                    mode,
                    COUNT(*) as count
                FROM pg_locks l
                JOIN pg_stat_activity a ON l.pid = a.pid
                WHERE a.datname = current_database()
                GROUP BY mode
                """
                
                result = await session.execute(text(lock_stats_query))
                lock_stats = {row[0]: row[1] for row in result}
                
                # Get database size and statistics
                db_stats_query = """
                SELECT 
                    pg_database_size(current_database()) as db_size,
                    (SELECT COUNT(*) FROM pg_stat_activity WHERE datname = current_database()) as active_connections,
                    (SELECT setting::int FROM pg_settings WHERE name = 'max_connections') as max_connections
                """
                
                result = await session.execute(text(db_stats_query))
                db_stats = result.fetchone()
                
                # Store statistics
                self._query_stats = {
                    "connection_states": conn_stats,
                    "database_size": db_stats[0] if db_stats else 0,
                    "active_connections": db_stats[1] if db_stats else 0,
                    "max_connections": db_stats[2] if db_stats else 100,
                    "collected_at": datetime.now()
                }
                
                self._lock_stats = {
                    "locks_by_mode": lock_stats,
                    "total_locks": sum(lock_stats.values()),
                    "collected_at": datetime.now()
                }
                
        except Exception as e:
            logger.warning(
                "Could not collect PostgreSQL statistics",
                error=str(e)
            )
    
    def get_optimization_recommendations(self) -> List[OptimizationRecommendation]:
        """Get PostgreSQL-specific optimization recommendations."""
        recommendations = super().get_optimization_recommendations()
        
        # Add PostgreSQL-specific recommendations
        if self._query_stats:
            active_connections = self._query_stats.get("active_connections", 0)
            max_connections = self._query_stats.get("max_connections", 100)
            
            # Check if we're approaching PostgreSQL connection limits
            connection_usage = (active_connections / max_connections) * 100
            if connection_usage > 80:
                recommendations.append(OptimizationRecommendation(
                    type="postgresql_connection_limit",
                    priority="high",
                    description=f"PostgreSQL connection usage is {connection_usage:.1f}%",
                    current_value=active_connections,
                    recommended_value=max_connections,
                    expected_impact="Prevent connection exhaustion",
                    implementation_complexity="medium",
                    estimated_improvement=20.0,
                    risks=["May need to increase max_connections in PostgreSQL"],
                    prerequisites=["Check PostgreSQL configuration", "Monitor system resources"]
                ))
        
        if self._lock_stats:
            total_locks = self._lock_stats.get("total_locks", 0)
            if total_locks > 1000:  # Arbitrary threshold
                recommendations.append(OptimizationRecommendation(
                    type="postgresql_lock_contention",
                    priority="medium",
                    description=f"High lock count detected: {total_locks}",
                    current_value=total_locks,
                    recommended_value=500,
                    expected_impact="Reduced lock contention and improved performance",
                    implementation_complexity="high",
                    estimated_improvement=15.0,
                    risks=["May require query optimization", "Application changes needed"],
                    prerequisites=["Analyze slow queries", "Review transaction patterns"]
                ))
        
        return recommendations
    
    async def _apply_optimization(self, recommendation: OptimizationRecommendation) -> Dict[str, Any]:
        """Apply PostgreSQL-specific optimizations."""
        if recommendation.type == "increase_pool_size":
            try:
                # For PostgreSQL, we need to be careful not to exceed connection limits
                current_pool_size = self.current_metrics.pool_size
                recommended_size = min(
                    recommendation.recommended_value,
                    self._query_stats.get("max_connections", 100) // 2  # Use half of max connections
                )
                
                if recommended_size > current_pool_size:
                    # This would require reconfiguring the SQLAlchemy engine
                    # For now, we'll just log the recommendation
                    logger.info(
                        "PostgreSQL pool size increase recommended",
                        current_size=current_pool_size,
                        recommended_size=recommended_size
                    )
                    
                    return {
                        "success": True,
                        "type": recommendation.type,
                        "message": f"Recommended increasing pool size from {current_pool_size} to {recommended_size}",
                        "old_value": current_pool_size,
                        "new_value": recommended_size,
                        "action_required": "Manual configuration update needed"
                    }
                
            except Exception as e:
                return {
                    "success": False,
                    "type": recommendation.type,
                    "error": str(e)
                }
        
        return await super()._apply_optimization(recommendation)
    
    def get_postgresql_performance_report(self) -> Dict[str, Any]:
        """Get PostgreSQL-specific performance report."""
        base_report = self.get_performance_report()
        
        # Add PostgreSQL-specific metrics
        postgresql_metrics = {
            "query_stats": self._query_stats,
            "lock_stats": self._lock_stats,
            "pool_efficiency": {
                "connections_per_request": (
                    self.current_metrics.pool_size / max(1, self.current_metrics.total_connection_requests)
                ),
                "average_connection_lifetime": self._calculate_average_connection_lifetime(),
                "pool_turnover_rate": self._calculate_pool_turnover_rate()
            }
        }
        
        base_report["postgresql_specific"] = postgresql_metrics
        return base_report
    
    def _calculate_average_connection_lifetime(self) -> float:
        """Calculate average connection lifetime."""
        if not self.connection_metrics:
            return 0.0
        
        now = datetime.now()
        lifetimes = [
            (now - conn.created_at).total_seconds()
            for conn in self.connection_metrics.values()
        ]
        
        return sum(lifetimes) / len(lifetimes) if lifetimes else 0.0
    
    def _calculate_pool_turnover_rate(self) -> float:
        """Calculate pool turnover rate (connections created per hour)."""
        if not self.connection_metrics:
            return 0.0
        
        # Count connections created in the last hour
        one_hour_ago = datetime.now() - timedelta(hours=1)
        recent_connections = sum(
            1 for conn in self.connection_metrics.values()
            if conn.created_at > one_hour_ago
        )
        
        return recent_connections


class Neo4jPoolOptimizer(ConnectionPoolOptimizer):
    """
    Neo4j-specific connection pool optimizer.
    
    Provides Neo4j-specific optimizations including:
    - Cypher query performance analysis
    - Transaction management optimization
    - Memory usage monitoring
    - Cluster health monitoring (if applicable)
    """
    
    def __init__(
        self,
        neo4j_client,
        optimization_strategy: OptimizationStrategy = OptimizationStrategy.BALANCED,
        **kwargs
    ):
        """
        Initialize Neo4j pool optimizer.
        
        Args:
            neo4j_client: Neo4jClient instance
            optimization_strategy: Optimization strategy
            **kwargs: Additional optimizer parameters
        """
        super().__init__(
            pool_name="neo4j",
            optimization_strategy=optimization_strategy,
            **kwargs
        )
        self.neo4j_client = neo4j_client
        self._cypher_stats: Dict[str, Any] = {}
        self._transaction_stats: Dict[str, Any] = {}
    
    async def _collect_metrics(self) -> None:
        """Collect Neo4j-specific metrics."""
        await super()._collect_metrics()
        
        try:
            if not self.neo4j_client or not self.neo4j_client.driver:
                return
            
            # Collect Neo4j-specific statistics
            await self._collect_neo4j_stats()
            
            # Update metrics based on Neo4j driver status
            with self._lock:
                # Neo4j doesn't expose pool metrics directly like SQLAlchemy
                # We'll estimate based on our tracking
                self.current_metrics.pool_size = self.neo4j_client.max_connection_pool_size
                
                # Estimate utilization based on active connections
                active_connections = len([
                    conn for conn in self.connection_metrics.values()
                    if (datetime.now() - conn.last_used).total_seconds() < 60
                ])
                
                self.current_metrics.checked_out = active_connections
                self.current_metrics.checked_in = self.current_metrics.pool_size - active_connections
                
                if self.current_metrics.pool_size > 0:
                    self.current_metrics.utilization_percentage = (
                        active_connections / self.current_metrics.pool_size
                    ) * 100
                
                # Update timing metrics
                if self.checkout_times:
                    self.current_metrics.average_checkout_time = sum(self.checkout_times) / len(self.checkout_times)
                
        except Exception as e:
            logger.error(
                "Error collecting Neo4j metrics",
                error=str(e)
            )
    
    async def _collect_neo4j_stats(self) -> None:
        """Collect Neo4j-specific statistics."""
        try:
            # Get database statistics
            stats_queries = {
                "node_count": "MATCH (n) RETURN count(n) as count",
                "relationship_count": "MATCH ()-[r]->() RETURN count(r) as count",
                "label_count": "CALL db.labels() YIELD label RETURN count(label) as count"
            }
            
            stats = {}
            for stat_name, query in stats_queries.items():
                try:
                    result = await self.neo4j_client.execute_query(query)
                    stats[stat_name] = result[0]["count"] if result else 0
                except Exception as e:
                    logger.warning(f"Could not collect {stat_name}", error=str(e))
                    stats[stat_name] = -1
            
            # Try to get system information
            try:
                system_result = await self.neo4j_client.execute_query("CALL dbms.components() YIELD name, versions, edition")
                stats["components"] = system_result
            except Exception:
                stats["components"] = []
            
            self._cypher_stats = {
                **stats,
                "collected_at": datetime.now()
            }
            
        except Exception as e:
            logger.warning(
                "Could not collect Neo4j statistics",
                error=str(e)
            )
    
    def get_optimization_recommendations(self) -> List[OptimizationRecommendation]:
        """Get Neo4j-specific optimization recommendations."""
        recommendations = super().get_optimization_recommendations()
        
        # Add Neo4j-specific recommendations
        if self._cypher_stats:
            node_count = self._cypher_stats.get("node_count", 0)
            relationship_count = self._cypher_stats.get("relationship_count", 0)
            
            # Check for large graph size that might need optimization
            if node_count > 1000000:  # 1M nodes
                recommendations.append(OptimizationRecommendation(
                    type="neo4j_large_graph",
                    priority="medium",
                    description=f"Large graph detected: {node_count:,} nodes",
                    current_value=node_count,
                    recommended_value="optimized",
                    expected_impact="Better query performance for large graphs",
                    implementation_complexity="high",
                    estimated_improvement=25.0,
                    risks=["May require query optimization", "Index creation needed"],
                    prerequisites=["Analyze query patterns", "Create appropriate indexes"]
                ))
            
            # Check relationship to node ratio
            if node_count > 0:
                rel_to_node_ratio = relationship_count / node_count
                if rel_to_node_ratio > 10:  # High connectivity
                    recommendations.append(OptimizationRecommendation(
                        type="neo4j_high_connectivity",
                        priority="medium",
                        description=f"High connectivity graph: {rel_to_node_ratio:.1f} relationships per node",
                        current_value=rel_to_node_ratio,
                        recommended_value=5.0,
                        expected_impact="Optimized traversal performance",
                        implementation_complexity="medium",
                        estimated_improvement=20.0,
                        risks=["May need query pattern changes"],
                        prerequisites=["Review graph model", "Optimize traversal queries"]
                    ))
        
        return recommendations
    
    async def _apply_optimization(self, recommendation: OptimizationRecommendation) -> Dict[str, Any]:
        """Apply Neo4j-specific optimizations."""
        if recommendation.type == "increase_pool_size":
            try:
                current_pool_size = self.current_metrics.pool_size
                recommended_size = recommendation.recommended_value
                
                # Neo4j pool size changes require driver reconfiguration
                logger.info(
                    "Neo4j pool size increase recommended",
                    current_size=current_pool_size,
                    recommended_size=recommended_size
                )
                
                return {
                    "success": True,
                    "type": recommendation.type,
                    "message": f"Recommended increasing Neo4j pool size from {current_pool_size} to {recommended_size}",
                    "old_value": current_pool_size,
                    "new_value": recommended_size,
                    "action_required": "Driver reconfiguration needed"
                }
                
            except Exception as e:
                return {
                    "success": False,
                    "type": recommendation.type,
                    "error": str(e)
                }
        
        return await super()._apply_optimization(recommendation)
    
    def get_neo4j_performance_report(self) -> Dict[str, Any]:
        """Get Neo4j-specific performance report."""
        base_report = self.get_performance_report()
        
        # Add Neo4j-specific metrics
        neo4j_metrics = {
            "cypher_stats": self._cypher_stats,
            "transaction_stats": self._transaction_stats,
            "graph_metrics": {
                "nodes_per_connection": (
                    self._cypher_stats.get("node_count", 0) / max(1, self.current_metrics.pool_size)
                ),
                "relationships_per_connection": (
                    self._cypher_stats.get("relationship_count", 0) / max(1, self.current_metrics.pool_size)
                ),
                "graph_density": self._calculate_graph_density()
            }
        }
        
        base_report["neo4j_specific"] = neo4j_metrics
        return base_report
    
    def _calculate_graph_density(self) -> float:
        """Calculate graph density (relationships / possible relationships)."""
        node_count = self._cypher_stats.get("node_count", 0)
        relationship_count = self._cypher_stats.get("relationship_count", 0)
        
        if node_count < 2:
            return 0.0
        
        max_relationships = node_count * (node_count - 1)  # Directed graph
        return relationship_count / max_relationships if max_relationships > 0 else 0.0


class MilvusPoolOptimizer(ConnectionPoolOptimizer):
    """
    Milvus-specific connection pool optimizer.
    
    Provides Milvus-specific optimizations including:
    - Vector search performance analysis
    - Index optimization recommendations
    - Memory usage monitoring
    - Collection management optimization
    """
    
    def __init__(
        self,
        milvus_client,
        optimization_strategy: OptimizationStrategy = OptimizationStrategy.BALANCED,
        **kwargs
    ):
        """
        Initialize Milvus pool optimizer.
        
        Args:
            milvus_client: MilvusClient instance
            optimization_strategy: Optimization strategy
            **kwargs: Additional optimizer parameters
        """
        super().__init__(
            pool_name="milvus",
            optimization_strategy=optimization_strategy,
            **kwargs
        )
        self.milvus_client = milvus_client
        self._collection_stats: Dict[str, Any] = {}
        self._search_stats: Dict[str, Any] = {}
    
    async def _collect_metrics(self) -> None:
        """Collect Milvus-specific metrics."""
        await super()._collect_metrics()
        
        try:
            if not self.milvus_client or not self.milvus_client._connected:
                return
            
            # Collect Milvus-specific statistics
            await self._collect_milvus_stats()
            
            # Update metrics based on Milvus connection status
            with self._lock:
                # Milvus uses internal connection pooling
                # We'll estimate metrics based on our tracking
                estimated_pool_size = 10  # Default Milvus pool size
                self.current_metrics.pool_size = estimated_pool_size
                
                # Estimate utilization based on recent activity
                recent_activity = len([
                    event for event in list(self.connection_events)[-100:]
                    if (datetime.now() - event["timestamp"]).total_seconds() < 60
                ])
                
                self.current_metrics.utilization_percentage = min(100, (recent_activity / 10) * 100)
                
                # Update timing metrics
                if self.checkout_times:
                    self.current_metrics.average_checkout_time = sum(self.checkout_times) / len(self.checkout_times)
                
        except Exception as e:
            logger.error(
                "Error collecting Milvus metrics",
                error=str(e)
            )
    
    async def _collect_milvus_stats(self) -> None:
        """Collect Milvus-specific statistics."""
        try:
            # Get collection statistics
            collections = await self.milvus_client.list_collections()
            
            collection_stats = {}
            total_vectors = 0
            
            for collection_name in collections:
                try:
                    # Get collection info
                    collection_info = await self.milvus_client.get_collection_stats(collection_name)
                    collection_stats[collection_name] = collection_info
                    total_vectors += collection_info.get("row_count", 0)
                except Exception as e:
                    logger.warning(f"Could not get stats for collection {collection_name}", error=str(e))
            
            self._collection_stats = {
                "collections": collection_stats,
                "total_collections": len(collections),
                "total_vectors": total_vectors,
                "collected_at": datetime.now()
            }
            
        except Exception as e:
            logger.warning(
                "Could not collect Milvus statistics",
                error=str(e)
            )
    
    def get_optimization_recommendations(self) -> List[OptimizationRecommendation]:
        """Get Milvus-specific optimization recommendations."""
        recommendations = super().get_optimization_recommendations()
        
        # Add Milvus-specific recommendations
        if self._collection_stats:
            total_vectors = self._collection_stats.get("total_vectors", 0)
            total_collections = self._collection_stats.get("total_collections", 0)
            
            # Check for large vector collections that might need optimization
            if total_vectors > 1000000:  # 1M vectors
                recommendations.append(OptimizationRecommendation(
                    type="milvus_large_collection",
                    priority="medium",
                    description=f"Large vector collection detected: {total_vectors:,} vectors",
                    current_value=total_vectors,
                    recommended_value="optimized",
                    expected_impact="Better search performance for large collections",
                    implementation_complexity="medium",
                    estimated_improvement=30.0,
                    risks=["Index rebuild may take time", "Temporary search degradation"],
                    prerequisites=["Analyze search patterns", "Optimize index parameters"]
                ))
            
            # Check for too many small collections
            if total_collections > 10 and total_vectors / total_collections < 1000:
                recommendations.append(OptimizationRecommendation(
                    type="milvus_collection_consolidation",
                    priority="low",
                    description=f"Many small collections detected: {total_collections} collections",
                    current_value=total_collections,
                    recommended_value=max(1, total_collections // 2),
                    expected_impact="Reduced overhead and better resource utilization",
                    implementation_complexity="high",
                    estimated_improvement=15.0,
                    risks=["Data migration required", "Application changes needed"],
                    prerequisites=["Review collection usage patterns", "Plan data migration"]
                ))
        
        return recommendations
    
    async def _apply_optimization(self, recommendation: OptimizationRecommendation) -> Dict[str, Any]:
        """Apply Milvus-specific optimizations."""
        if recommendation.type == "milvus_large_collection":
            try:
                # For large collections, we might recommend index optimization
                logger.info(
                    "Milvus collection optimization recommended",
                    total_vectors=recommendation.current_value
                )
                
                return {
                    "success": True,
                    "type": recommendation.type,
                    "message": f"Recommended optimizing large collection with {recommendation.current_value:,} vectors",
                    "old_value": recommendation.current_value,
                    "new_value": "optimized",
                    "action_required": "Index optimization and parameter tuning needed"
                }
                
            except Exception as e:
                return {
                    "success": False,
                    "type": recommendation.type,
                    "error": str(e)
                }
        
        return await super()._apply_optimization(recommendation)
    
    def get_milvus_performance_report(self) -> Dict[str, Any]:
        """Get Milvus-specific performance report."""
        base_report = self.get_performance_report()
        
        # Add Milvus-specific metrics
        milvus_metrics = {
            "collection_stats": self._collection_stats,
            "search_stats": self._search_stats,
            "vector_metrics": {
                "vectors_per_collection": (
                    self._collection_stats.get("total_vectors", 0) / 
                    max(1, self._collection_stats.get("total_collections", 1))
                ),
                "collection_efficiency": self._calculate_collection_efficiency(),
                "search_performance": self._calculate_search_performance()
            }
        }
        
        base_report["milvus_specific"] = milvus_metrics
        return base_report
    
    def _calculate_collection_efficiency(self) -> float:
        """Calculate collection efficiency score."""
        if not self._collection_stats:
            return 0.0
        
        total_vectors = self._collection_stats.get("total_vectors", 0)
        total_collections = self._collection_stats.get("total_collections", 1)
        
        # Efficiency based on vectors per collection (more vectors per collection is generally better)
        vectors_per_collection = total_vectors / total_collections
        
        # Score from 0-100 based on vectors per collection
        if vectors_per_collection > 100000:
            return 100.0
        elif vectors_per_collection > 10000:
            return 80.0
        elif vectors_per_collection > 1000:
            return 60.0
        elif vectors_per_collection > 100:
            return 40.0
        else:
            return 20.0
    
    def _calculate_search_performance(self) -> Dict[str, float]:
        """Calculate search performance metrics."""
        if not self.checkout_times:
            return {"average_search_time": 0.0, "search_efficiency": 0.0}
        
        avg_search_time = sum(self.checkout_times) / len(self.checkout_times)
        
        # Search efficiency score (lower time is better)
        if avg_search_time < 0.1:  # 100ms
            efficiency = 100.0
        elif avg_search_time < 0.5:  # 500ms
            efficiency = 80.0
        elif avg_search_time < 1.0:  # 1s
            efficiency = 60.0
        elif avg_search_time < 2.0:  # 2s
            efficiency = 40.0
        else:
            efficiency = 20.0
        
        return {
            "average_search_time": avg_search_time,
            "search_efficiency": efficiency
        }


# Factory function to create appropriate optimizer
def create_pool_optimizer(
    database_type: str,
    client,
    optimization_strategy: OptimizationStrategy = OptimizationStrategy.BALANCED,
    **kwargs
) -> ConnectionPoolOptimizer:
    """
    Create appropriate pool optimizer for database type.
    
    Args:
        database_type: Type of database ("postgresql", "neo4j", "milvus")
        client: Database client instance
        optimization_strategy: Optimization strategy to use
        **kwargs: Additional optimizer parameters
        
    Returns:
        Appropriate pool optimizer instance
    """
    if database_type.lower() == "postgresql":
        return PostgreSQLPoolOptimizer(client, optimization_strategy, **kwargs)
    elif database_type.lower() == "neo4j":
        return Neo4jPoolOptimizer(client, optimization_strategy, **kwargs)
    elif database_type.lower() == "milvus":
        return MilvusPoolOptimizer(client, optimization_strategy, **kwargs)
    else:
        raise ValueError(f"Unsupported database type: {database_type}")