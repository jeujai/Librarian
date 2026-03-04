"""
Connection Pool Manager for Local Development

This module provides a centralized manager for all database connection pools
in the local development environment. It coordinates optimization across
PostgreSQL, Neo4j, and Milvus connection pools.
"""

import asyncio
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime
from contextlib import asynccontextmanager

import structlog

from .connection_pool_optimizer import OptimizationStrategy
from .database_pool_optimizers import create_pool_optimizer, ConnectionPoolOptimizer
from .local_config import LocalDatabaseConfig

logger = structlog.get_logger(__name__)


class ConnectionPoolManager:
    """
    Centralized manager for all database connection pools.
    
    This manager coordinates optimization across all database types and provides
    a unified interface for monitoring and managing connection pools.
    """
    
    def __init__(self, config: LocalDatabaseConfig):
        """
        Initialize connection pool manager.
        
        Args:
            config: Local database configuration
        """
        self.config = config
        self.optimizers: Dict[str, ConnectionPoolOptimizer] = {}
        self.clients: Dict[str, Any] = {}
        self._monitoring_task: Optional[asyncio.Task] = None
        self._shutdown_event = asyncio.Event()
        
        # Parse optimization strategy
        strategy_map = {
            "conservative": OptimizationStrategy.CONSERVATIVE,
            "balanced": OptimizationStrategy.BALANCED,
            "aggressive": OptimizationStrategy.AGGRESSIVE,
            "custom": OptimizationStrategy.CUSTOM
        }
        self.optimization_strategy = strategy_map.get(
            config.pool_optimization_strategy.lower(),
            OptimizationStrategy.BALANCED
        )
        
        logger.info(
            "Connection pool manager initialized",
            strategy=self.optimization_strategy.value,
            auto_optimization=config.enable_auto_pool_optimization
        )
    
    async def register_client(self, database_type: str, client: Any) -> None:
        """
        Register a database client for pool optimization.
        
        Args:
            database_type: Type of database ("postgresql", "neo4j", "milvus")
            client: Database client instance
        """
        if not self.config.enable_pool_optimization:
            logger.info(f"Pool optimization disabled, skipping {database_type} client registration")
            return
        
        try:
            # Store client reference
            self.clients[database_type] = client
            
            # Create optimizer for this database type
            optimizer = create_pool_optimizer(
                database_type=database_type,
                client=client,
                optimization_strategy=self.optimization_strategy,
                monitoring_interval=self.config.pool_monitoring_interval,
                optimization_interval=self.config.pool_optimization_interval,
                enable_auto_optimization=self.config.enable_auto_pool_optimization,
                target_utilization=self.config.pool_target_utilization,
                connection_timeout_threshold=self.config.pool_connection_timeout_threshold,
                stale_connection_threshold=self.config.pool_stale_connection_threshold
            )
            
            self.optimizers[database_type] = optimizer
            
            # Start monitoring if enabled
            if self.config.enable_pool_health_monitoring:
                await optimizer.start_monitoring()
            
            logger.info(
                f"Registered {database_type} client for pool optimization",
                database_type=database_type,
                monitoring_enabled=self.config.enable_pool_health_monitoring
            )
            
        except Exception as e:
            logger.error(
                f"Failed to register {database_type} client",
                database_type=database_type,
                error=str(e)
            )
    
    async def unregister_client(self, database_type: str) -> None:
        """
        Unregister a database client.
        
        Args:
            database_type: Type of database to unregister
        """
        if database_type in self.optimizers:
            try:
                await self.optimizers[database_type].stop_monitoring()
                del self.optimizers[database_type]
                
                if database_type in self.clients:
                    del self.clients[database_type]
                
                logger.info(f"Unregistered {database_type} client", database_type=database_type)
                
            except Exception as e:
                logger.error(
                    f"Error unregistering {database_type} client",
                    database_type=database_type,
                    error=str(e)
                )
    
    async def start_monitoring(self) -> None:
        """Start centralized monitoring for all registered optimizers."""
        if self._monitoring_task is not None:
            logger.warning("Pool monitoring already started")
            return
        
        if not self.config.enable_pool_health_monitoring:
            logger.info("Pool health monitoring disabled")
            return
        
        logger.info("Starting centralized pool monitoring")
        self._monitoring_task = asyncio.create_task(self._monitoring_loop())
    
    async def stop_monitoring(self) -> None:
        """Stop centralized monitoring."""
        logger.info("Stopping centralized pool monitoring")
        
        # Signal shutdown
        self._shutdown_event.set()
        
        # Stop individual optimizers
        for database_type, optimizer in self.optimizers.items():
            try:
                await optimizer.stop_monitoring()
            except Exception as e:
                logger.error(
                    f"Error stopping {database_type} optimizer",
                    database_type=database_type,
                    error=str(e)
                )
        
        # Cancel monitoring task
        if self._monitoring_task:
            self._monitoring_task.cancel()
            try:
                await self._monitoring_task
            except asyncio.CancelledError:
                pass
            self._monitoring_task = None
        
        logger.info("Centralized pool monitoring stopped")
    
    async def _monitoring_loop(self) -> None:
        """Centralized monitoring loop."""
        while not self._shutdown_event.is_set():
            try:
                # Collect metrics from all optimizers
                await self._collect_aggregate_metrics()
                
                # Check for cross-database optimization opportunities
                await self._analyze_cross_database_optimization()
                
                # Generate system-wide recommendations
                await self._generate_system_recommendations()
                
                # Wait for next monitoring cycle
                await asyncio.sleep(self.config.pool_health_check_interval)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Error in centralized monitoring loop", error=str(e))
                await asyncio.sleep(self.config.pool_health_check_interval)
    
    async def _collect_aggregate_metrics(self) -> None:
        """Collect and aggregate metrics from all optimizers."""
        total_connections = 0
        total_utilization = 0.0
        total_errors = 0
        active_optimizers = 0
        
        for database_type, optimizer in self.optimizers.items():
            try:
                metrics = optimizer.current_metrics
                total_connections += metrics.pool_size
                total_utilization += metrics.utilization_percentage
                total_errors += metrics.connection_errors
                active_optimizers += 1
                
            except Exception as e:
                logger.warning(
                    f"Could not collect metrics from {database_type} optimizer",
                    database_type=database_type,
                    error=str(e)
                )
        
        if active_optimizers > 0:
            avg_utilization = total_utilization / active_optimizers
            
            # Log aggregate metrics
            logger.debug(
                "Aggregate pool metrics",
                total_connections=total_connections,
                average_utilization=avg_utilization,
                total_errors=total_errors,
                active_optimizers=active_optimizers
            )
    
    async def _analyze_cross_database_optimization(self) -> None:
        """Analyze optimization opportunities across databases."""
        if len(self.optimizers) < 2:
            return  # Need at least 2 databases for cross-analysis
        
        try:
            # Check for resource contention between databases
            high_utilization_dbs = []
            low_utilization_dbs = []
            
            for database_type, optimizer in self.optimizers.items():
                utilization = optimizer.current_metrics.utilization_percentage
                
                if utilization > 80:
                    high_utilization_dbs.append((database_type, utilization))
                elif utilization < 30:
                    low_utilization_dbs.append((database_type, utilization))
            
            # Log potential resource rebalancing opportunities
            if high_utilization_dbs and low_utilization_dbs:
                logger.info(
                    "Cross-database optimization opportunity detected",
                    high_utilization=high_utilization_dbs,
                    low_utilization=low_utilization_dbs
                )
                
        except Exception as e:
            logger.error("Error in cross-database optimization analysis", error=str(e))
    
    async def _generate_system_recommendations(self) -> None:
        """Generate system-wide optimization recommendations."""
        try:
            all_recommendations = []
            
            for database_type, optimizer in self.optimizers.items():
                recommendations = optimizer.get_optimization_recommendations()
                for rec in recommendations:
                    rec.database_type = database_type  # Add database type to recommendation
                all_recommendations.extend(recommendations)
            
            # Sort by priority and impact
            priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
            all_recommendations.sort(
                key=lambda r: (priority_order.get(r.priority, 4), -r.estimated_improvement)
            )
            
            # Log top recommendations
            if all_recommendations:
                top_recommendations = all_recommendations[:3]  # Top 3
                logger.info(
                    "Top system optimization recommendations",
                    recommendations=[
                        {
                            "database": getattr(rec, 'database_type', 'unknown'),
                            "type": rec.type,
                            "priority": rec.priority,
                            "description": rec.description,
                            "improvement": rec.estimated_improvement
                        }
                        for rec in top_recommendations
                    ]
                )
                
        except Exception as e:
            logger.error("Error generating system recommendations", error=str(e))
    
    def get_system_status(self) -> Dict[str, Any]:
        """Get overall system status for all connection pools."""
        status = {
            "timestamp": datetime.now().isoformat(),
            "optimization_enabled": self.config.enable_pool_optimization,
            "auto_optimization_enabled": self.config.enable_auto_pool_optimization,
            "monitoring_enabled": self.config.enable_pool_health_monitoring,
            "strategy": self.optimization_strategy.value,
            "databases": {},
            "system_metrics": {
                "total_pools": len(self.optimizers),
                "total_connections": 0,
                "average_utilization": 0.0,
                "total_errors": 0,
                "healthy_pools": 0
            }
        }
        
        total_utilization = 0.0
        active_pools = 0
        
        for database_type, optimizer in self.optimizers.items():
            try:
                metrics = optimizer.current_metrics
                performance_report = optimizer.get_performance_report()
                
                status["databases"][database_type] = {
                    "pool_size": metrics.pool_size,
                    "utilization_percentage": metrics.utilization_percentage,
                    "connection_errors": metrics.connection_errors,
                    "connection_timeouts": metrics.connection_timeouts,
                    "healthy_connections": metrics.healthy_connections,
                    "unhealthy_connections": metrics.unhealthy_connections,
                    "overall_score": performance_report.get("overall_score", 0),
                    "last_optimization": optimizer.last_optimization.isoformat(),
                    "recommendations_count": len(optimizer.get_optimization_recommendations())
                }
                
                # Update system metrics
                status["system_metrics"]["total_connections"] += metrics.pool_size
                total_utilization += metrics.utilization_percentage
                status["system_metrics"]["total_errors"] += metrics.connection_errors
                
                if performance_report.get("overall_score", 0) > 70:
                    status["system_metrics"]["healthy_pools"] += 1
                
                active_pools += 1
                
            except Exception as e:
                status["databases"][database_type] = {
                    "error": str(e),
                    "status": "unavailable"
                }
        
        if active_pools > 0:
            status["system_metrics"]["average_utilization"] = total_utilization / active_pools
        
        return status
    
    def get_optimization_report(self) -> Dict[str, Any]:
        """Get comprehensive optimization report for all databases."""
        report = {
            "timestamp": datetime.now().isoformat(),
            "system_overview": self.get_system_status(),
            "database_reports": {},
            "cross_database_analysis": {},
            "system_recommendations": []
        }
        
        # Get individual database reports
        for database_type, optimizer in self.optimizers.items():
            try:
                if hasattr(optimizer, f'get_{database_type}_performance_report'):
                    # Use database-specific report if available
                    db_report = getattr(optimizer, f'get_{database_type}_performance_report')()
                else:
                    # Use generic performance report
                    db_report = optimizer.get_performance_report()
                
                report["database_reports"][database_type] = db_report
                
            except Exception as e:
                report["database_reports"][database_type] = {
                    "error": str(e),
                    "status": "report_unavailable"
                }
        
        # Add cross-database analysis
        report["cross_database_analysis"] = self._generate_cross_database_analysis()
        
        # Collect all recommendations
        all_recommendations = []
        for database_type, optimizer in self.optimizers.items():
            try:
                recommendations = optimizer.get_optimization_recommendations()
                for rec in recommendations:
                    all_recommendations.append({
                        "database": database_type,
                        "type": rec.type,
                        "priority": rec.priority,
                        "description": rec.description,
                        "current_value": rec.current_value,
                        "recommended_value": rec.recommended_value,
                        "expected_impact": rec.expected_impact,
                        "estimated_improvement": rec.estimated_improvement,
                        "implementation_complexity": rec.implementation_complexity,
                        "risks": rec.risks,
                        "prerequisites": rec.prerequisites
                    })
            except Exception as e:
                logger.error(f"Error collecting recommendations for {database_type}", error=str(e))
        
        # Sort recommendations by priority and impact
        priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        all_recommendations.sort(
            key=lambda r: (priority_order.get(r["priority"], 4), -r["estimated_improvement"])
        )
        
        report["system_recommendations"] = all_recommendations
        
        return report
    
    def _generate_cross_database_analysis(self) -> Dict[str, Any]:
        """Generate cross-database analysis."""
        analysis = {
            "resource_distribution": {},
            "utilization_balance": {},
            "performance_correlation": {},
            "optimization_opportunities": []
        }
        
        try:
            # Analyze resource distribution
            total_connections = 0
            db_connections = {}
            
            for database_type, optimizer in self.optimizers.items():
                connections = optimizer.current_metrics.pool_size
                db_connections[database_type] = connections
                total_connections += connections
            
            # Calculate resource distribution percentages
            if total_connections > 0:
                for database_type, connections in db_connections.items():
                    percentage = (connections / total_connections) * 100
                    analysis["resource_distribution"][database_type] = {
                        "connections": connections,
                        "percentage": round(percentage, 1)
                    }
            
            # Analyze utilization balance
            utilizations = {}
            for database_type, optimizer in self.optimizers.items():
                utilizations[database_type] = optimizer.current_metrics.utilization_percentage
            
            if utilizations:
                avg_utilization = sum(utilizations.values()) / len(utilizations)
                analysis["utilization_balance"] = {
                    "average": round(avg_utilization, 1),
                    "by_database": {k: round(v, 1) for k, v in utilizations.items()},
                    "variance": round(
                        sum((v - avg_utilization) ** 2 for v in utilizations.values()) / len(utilizations),
                        2
                    )
                }
            
            # Identify optimization opportunities
            high_util_dbs = [db for db, util in utilizations.items() if util > 80]
            low_util_dbs = [db for db, util in utilizations.items() if util < 30]
            
            if high_util_dbs and low_util_dbs:
                analysis["optimization_opportunities"].append({
                    "type": "resource_rebalancing",
                    "description": f"Consider rebalancing resources between {high_util_dbs} and {low_util_dbs}",
                    "high_utilization": high_util_dbs,
                    "low_utilization": low_util_dbs
                })
            
        except Exception as e:
            analysis["error"] = str(e)
        
        return analysis
    
    async def optimize_all_pools(self) -> Dict[str, Any]:
        """Run optimization on all registered pools."""
        results = {
            "timestamp": datetime.now().isoformat(),
            "optimization_results": {},
            "summary": {
                "total_pools": len(self.optimizers),
                "successful_optimizations": 0,
                "failed_optimizations": 0,
                "total_recommendations": 0,
                "applied_optimizations": 0
            }
        }
        
        for database_type, optimizer in self.optimizers.items():
            try:
                optimization_result = await optimizer.optimize_pool()
                results["optimization_results"][database_type] = optimization_result
                
                if optimization_result.get("success", True):
                    results["summary"]["successful_optimizations"] += 1
                else:
                    results["summary"]["failed_optimizations"] += 1
                
                results["summary"]["total_recommendations"] += optimization_result.get("recommendations_generated", 0)
                results["summary"]["applied_optimizations"] += len(optimization_result.get("optimizations_applied", []))
                
            except Exception as e:
                results["optimization_results"][database_type] = {
                    "error": str(e),
                    "success": False
                }
                results["summary"]["failed_optimizations"] += 1
        
        logger.info(
            "Pool optimization completed for all databases",
            successful=results["summary"]["successful_optimizations"],
            failed=results["summary"]["failed_optimizations"],
            recommendations=results["summary"]["total_recommendations"],
            applied=results["summary"]["applied_optimizations"]
        )
        
        return results
    
    @asynccontextmanager
    async def managed_lifecycle(self):
        """Context manager for managing the complete lifecycle of the pool manager."""
        try:
            await self.start_monitoring()
            yield self
        finally:
            await self.stop_monitoring()


# Global pool manager instance
_pool_manager: Optional[ConnectionPoolManager] = None


def get_pool_manager(config: Optional[LocalDatabaseConfig] = None) -> ConnectionPoolManager:
    """Get or create global pool manager instance."""
    global _pool_manager
    
    if _pool_manager is None:
        if config is None:
            from .local_config import get_local_config
            config = get_local_config()
        
        _pool_manager = ConnectionPoolManager(config)
    
    return _pool_manager


async def initialize_pool_manager(config: LocalDatabaseConfig) -> ConnectionPoolManager:
    """Initialize and start the global pool manager."""
    global _pool_manager
    
    _pool_manager = ConnectionPoolManager(config)
    await _pool_manager.start_monitoring()
    
    return _pool_manager


async def shutdown_pool_manager() -> None:
    """Shutdown the global pool manager."""
    global _pool_manager
    
    if _pool_manager is not None:
        await _pool_manager.stop_monitoring()
        _pool_manager = None