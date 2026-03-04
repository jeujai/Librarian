#!/usr/bin/env python3
"""
Milvus Performance Optimization Script

This script optimizes Milvus collections for better search performance by:
1. Analyzing collection characteristics
2. Recommending optimal index configurations
3. Creating or updating indexes with optimal parameters
4. Tuning search parameters for best performance
5. Providing performance benchmarks and recommendations

Usage:
    python scripts/optimize-milvus-performance.py [options]

Options:
    --collection NAME    Optimize specific collection (default: all collections)
    --dry-run           Show recommendations without applying changes
    --benchmark         Run performance benchmarks
    --target-latency MS Target search latency in milliseconds (default: 100)
    --memory-limit MB   Memory limit in MB (default: no limit)
    --priority PRIORITY Optimization priority: speed, accuracy, memory, balanced (default: balanced)
"""

import asyncio
import argparse
import sys
import time
import json
from pathlib import Path
from typing import Dict, List, Any, Optional
import logging

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "src"))

from multimodal_librarian.clients.milvus_client import MilvusClient
from multimodal_librarian.config.local_config import LocalDatabaseConfig
sys.path.insert(0, str(project_root / "database"))
from milvus.optimization_config import (
    MilvusOptimizationConfig, 
    get_recommended_index_params,
    get_recommended_search_params
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class MilvusOptimizer:
    """Milvus performance optimizer."""
    
    def __init__(self, config: LocalDatabaseConfig):
        """Initialize optimizer with configuration."""
        self.config = config
        self.client = MilvusClient(
            host=config.milvus_host,
            port=config.milvus_port,
            user=config.milvus_user,
            password=config.milvus_password
        )
        self.results = {
            "collections_analyzed": 0,
            "optimizations_applied": 0,
            "performance_improvements": {},
            "recommendations": [],
            "errors": []
        }
    
    async def __aenter__(self):
        """Async context manager entry."""
        await self.client.connect()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.client.disconnect()
    
    async def optimize_all_collections(
        self,
        dry_run: bool = False,
        target_latency_ms: float = 100.0,
        memory_limit_mb: Optional[int] = None,
        priority: str = "balanced"
    ) -> Dict[str, Any]:
        """
        Optimize all collections in the Milvus database.
        
        Args:
            dry_run: If True, only show recommendations without applying changes
            target_latency_ms: Target search latency in milliseconds
            memory_limit_mb: Memory limit in MB
            priority: Optimization priority
            
        Returns:
            Dictionary with optimization results
        """
        logger.info("Starting Milvus performance optimization")
        logger.info(f"Configuration: dry_run={dry_run}, target_latency={target_latency_ms}ms, "
                   f"memory_limit={memory_limit_mb}MB, priority={priority}")
        
        try:
            # Get all collections
            collections = await self.client.list_collections()
            logger.info(f"Found {len(collections)} collections to analyze")
            
            if not collections:
                logger.warning("No collections found in Milvus database")
                return self.results
            
            # Optimize each collection
            for collection_name in collections:
                try:
                    await self.optimize_collection(
                        collection_name,
                        dry_run=dry_run,
                        target_latency_ms=target_latency_ms,
                        memory_limit_mb=memory_limit_mb,
                        priority=priority
                    )
                    self.results["collections_analyzed"] += 1
                    
                except Exception as e:
                    error_msg = f"Failed to optimize collection '{collection_name}': {e}"
                    logger.error(error_msg)
                    self.results["errors"].append(error_msg)
            
            # Generate summary report
            await self._generate_summary_report()
            
            return self.results
            
        except Exception as e:
            error_msg = f"Failed to optimize collections: {e}"
            logger.error(error_msg)
            self.results["errors"].append(error_msg)
            return self.results
    
    async def optimize_collection(
        self,
        collection_name: str,
        dry_run: bool = False,
        target_latency_ms: float = 100.0,
        memory_limit_mb: Optional[int] = None,
        priority: str = "balanced"
    ) -> Dict[str, Any]:
        """
        Optimize a specific collection.
        
        Args:
            collection_name: Name of the collection to optimize
            dry_run: If True, only show recommendations without applying changes
            target_latency_ms: Target search latency in milliseconds
            memory_limit_mb: Memory limit in MB
            priority: Optimization priority
            
        Returns:
            Dictionary with optimization results for this collection
        """
        logger.info(f"Analyzing collection '{collection_name}'")
        
        collection_results = {
            "collection_name": collection_name,
            "current_stats": {},
            "recommendations": [],
            "optimizations_applied": [],
            "performance_before": {},
            "performance_after": {},
            "errors": []
        }
        
        try:
            # Get current collection statistics
            stats = await self.client.get_collection_stats(collection_name)
            collection_results["current_stats"] = stats
            
            vector_count = stats.get("vector_count", 0)
            dimension = stats.get("dimension", 384)
            current_index_type = stats.get("index_type", "none")
            memory_usage_mb = stats.get("memory_usage", 0) / (1024 * 1024)
            
            logger.info(f"  Collection stats: {vector_count} vectors, {dimension}D, "
                       f"index: {current_index_type}, memory: {memory_usage_mb:.1f}MB")
            
            if vector_count == 0:
                logger.warning(f"  Collection '{collection_name}' is empty, skipping optimization")
                return collection_results
            
            # Get optimization recommendations
            recommendations = await self.client.get_optimization_recommendations(collection_name)
            collection_results["recommendations"] = recommendations["recommendations"]
            
            # Get optimal configuration
            optimal_config = MilvusOptimizationConfig.get_optimal_index_config(
                vector_count, dimension, memory_limit_mb, priority
            )
            
            logger.info(f"  Recommended index: {optimal_config.index_type.value}")
            logger.info(f"  Current priority: {priority}")
            
            # Measure current performance if collection has data
            if vector_count > 100:
                try:
                    current_performance = await self._measure_collection_performance(collection_name)
                    collection_results["performance_before"] = current_performance
                    logger.info(f"  Current performance: {current_performance.get('avg_latency_ms', 'N/A')}ms avg latency")
                except Exception as e:
                    logger.warning(f"  Failed to measure current performance: {e}")
            
            # Apply optimizations if not dry run
            if not dry_run:
                optimizations_applied = await self._apply_optimizations(
                    collection_name, optimal_config, target_latency_ms
                )
                collection_results["optimizations_applied"] = optimizations_applied
                
                if optimizations_applied:
                    self.results["optimizations_applied"] += len(optimizations_applied)
                    
                    # Measure performance after optimization
                    if vector_count > 100:
                        try:
                            await asyncio.sleep(2)  # Wait for index to be ready
                            new_performance = await self._measure_collection_performance(collection_name)
                            collection_results["performance_after"] = new_performance
                            
                            # Calculate improvement
                            if collection_results["performance_before"]:
                                before_latency = collection_results["performance_before"]["avg_latency_ms"]
                                after_latency = new_performance["avg_latency_ms"]
                                improvement = (before_latency - after_latency) / before_latency * 100
                                
                                self.results["performance_improvements"][collection_name] = improvement
                                logger.info(f"  Performance improvement: {improvement:.1f}%")
                        except Exception as e:
                            logger.warning(f"  Failed to measure performance after optimization: {e}")
            else:
                logger.info("  Dry run mode - no changes applied")
            
            # Store results
            self.results["recommendations"].extend(collection_results["recommendations"])
            
            return collection_results
            
        except Exception as e:
            error_msg = f"Failed to optimize collection '{collection_name}': {e}"
            logger.error(error_msg)
            collection_results["errors"].append(error_msg)
            return collection_results
    
    async def _measure_collection_performance(
        self, 
        collection_name: str,
        num_queries: int = 5
    ) -> Dict[str, float]:
        """Measure search performance for a collection."""
        try:
            # Generate test queries
            test_queries = await self.client._generate_test_queries(collection_name, num_queries)
            
            if not test_queries:
                return {"avg_latency_ms": 0, "error": "No test queries generated"}
            
            # Measure performance
            performance = await self.client._measure_search_performance(
                collection_name, test_queries
            )
            
            return performance
            
        except Exception as e:
            logger.warning(f"Failed to measure performance for '{collection_name}': {e}")
            return {"avg_latency_ms": float('inf'), "error": str(e)}
    
    async def _apply_optimizations(
        self,
        collection_name: str,
        optimal_config,
        target_latency_ms: float
    ) -> List[Dict[str, Any]]:
        """Apply optimizations to a collection."""
        optimizations = []
        
        try:
            # Get current index info
            current_indexes = await self.client.get_index_info(collection_name)
            current_index_type = None
            
            if current_indexes:
                current_index_type = current_indexes[0].get("index_type", "none")
            
            # Create or update index if needed
            if (not current_indexes or 
                current_index_type != optimal_config.index_type.value):
                
                logger.info(f"  Creating/updating index to {optimal_config.index_type.value}")
                
                # Drop existing index if present
                if current_indexes:
                    await self.client.drop_index(collection_name, "vector")
                    optimizations.append({
                        "type": "drop_index",
                        "description": f"Dropped existing {current_index_type} index"
                    })
                
                # Create new optimized index
                index_params = {
                    "index_type": optimal_config.index_type.value,
                    "metric_type": optimal_config.metric_type.value,
                    "params": optimal_config.params
                }
                
                success = await self.client.create_index(
                    collection_name, "vector", index_params
                )
                
                if success:
                    optimizations.append({
                        "type": "create_index",
                        "description": f"Created {optimal_config.index_type.value} index",
                        "parameters": index_params
                    })
                    logger.info(f"  ✓ Index created successfully")
                else:
                    logger.error(f"  ✗ Failed to create index")
            
            # Run general collection optimization
            try:
                await self.client.optimize_collection(collection_name)
                optimizations.append({
                    "type": "optimize_collection",
                    "description": "Applied general collection optimizations"
                })
                logger.info(f"  ✓ Collection optimization completed")
            except Exception as e:
                logger.warning(f"  Collection optimization failed: {e}")
            
            return optimizations
            
        except Exception as e:
            logger.error(f"Failed to apply optimizations: {e}")
            return optimizations
    
    async def _generate_summary_report(self) -> None:
        """Generate and log summary report."""
        logger.info("\n" + "=" * 60)
        logger.info("MILVUS OPTIMIZATION SUMMARY")
        logger.info("=" * 60)
        
        logger.info(f"Collections analyzed: {self.results['collections_analyzed']}")
        logger.info(f"Optimizations applied: {self.results['optimizations_applied']}")
        
        if self.results["performance_improvements"]:
            logger.info("\nPerformance improvements:")
            for collection, improvement in self.results["performance_improvements"].items():
                logger.info(f"  {collection}: {improvement:+.1f}%")
        
        if self.results["recommendations"]:
            logger.info(f"\nTotal recommendations: {len(self.results['recommendations'])}")
            
            # Group recommendations by priority
            high_priority = [r for r in self.results["recommendations"] if r.get("priority") == "high"]
            medium_priority = [r for r in self.results["recommendations"] if r.get("priority") == "medium"]
            
            if high_priority:
                logger.info(f"  High priority: {len(high_priority)}")
            if medium_priority:
                logger.info(f"  Medium priority: {len(medium_priority)}")
        
        if self.results["errors"]:
            logger.warning(f"\nErrors encountered: {len(self.results['errors'])}")
            for error in self.results["errors"]:
                logger.warning(f"  {error}")
        
        logger.info("=" * 60)
    
    async def run_performance_benchmark(
        self,
        collection_name: Optional[str] = None,
        num_queries: int = 20
    ) -> Dict[str, Any]:
        """
        Run performance benchmark on collections.
        
        Args:
            collection_name: Specific collection to benchmark (None for all)
            num_queries: Number of test queries to run
            
        Returns:
            Benchmark results
        """
        logger.info("Running Milvus performance benchmark")
        
        benchmark_results = {
            "timestamp": time.time(),
            "num_queries": num_queries,
            "collections": {},
            "summary": {}
        }
        
        try:
            # Get collections to benchmark
            if collection_name:
                collections = [collection_name]
            else:
                collections = await self.client.list_collections()
            
            logger.info(f"Benchmarking {len(collections)} collection(s)")
            
            total_latencies = []
            
            for coll_name in collections:
                logger.info(f"  Benchmarking collection '{coll_name}'")
                
                try:
                    # Get collection stats
                    stats = await self.client.get_collection_stats(coll_name)
                    vector_count = stats.get("vector_count", 0)
                    
                    if vector_count < 10:
                        logger.warning(f"    Skipping '{coll_name}' - too few vectors ({vector_count})")
                        continue
                    
                    # Run benchmark
                    performance = await self._measure_collection_performance(coll_name, num_queries)
                    
                    benchmark_results["collections"][coll_name] = {
                        "vector_count": vector_count,
                        "performance": performance,
                        "index_type": stats.get("index_type", "none")
                    }
                    
                    if "avg_latency_ms" in performance:
                        total_latencies.append(performance["avg_latency_ms"])
                        logger.info(f"    Average latency: {performance['avg_latency_ms']:.2f}ms")
                    
                except Exception as e:
                    logger.error(f"    Benchmark failed for '{coll_name}': {e}")
            
            # Calculate summary statistics
            if total_latencies:
                benchmark_results["summary"] = {
                    "avg_latency_ms": sum(total_latencies) / len(total_latencies),
                    "min_latency_ms": min(total_latencies),
                    "max_latency_ms": max(total_latencies),
                    "collections_tested": len(total_latencies)
                }
                
                logger.info(f"\nBenchmark Summary:")
                logger.info(f"  Collections tested: {len(total_latencies)}")
                logger.info(f"  Average latency: {benchmark_results['summary']['avg_latency_ms']:.2f}ms")
                logger.info(f"  Min latency: {benchmark_results['summary']['min_latency_ms']:.2f}ms")
                logger.info(f"  Max latency: {benchmark_results['summary']['max_latency_ms']:.2f}ms")
            
            return benchmark_results
            
        except Exception as e:
            logger.error(f"Benchmark failed: {e}")
            benchmark_results["error"] = str(e)
            return benchmark_results


async def main():
    """Main function."""
    parser = argparse.ArgumentParser(
        description="Optimize Milvus collections for better performance"
    )
    parser.add_argument(
        "--collection", 
        help="Optimize specific collection (default: all collections)"
    )
    parser.add_argument(
        "--dry-run", 
        action="store_true",
        help="Show recommendations without applying changes"
    )
    parser.add_argument(
        "--benchmark", 
        action="store_true",
        help="Run performance benchmarks"
    )
    parser.add_argument(
        "--target-latency", 
        type=float, 
        default=100.0,
        help="Target search latency in milliseconds (default: 100)"
    )
    parser.add_argument(
        "--memory-limit", 
        type=int,
        help="Memory limit in MB"
    )
    parser.add_argument(
        "--priority", 
        choices=["speed", "accuracy", "memory", "balanced"],
        default="balanced",
        help="Optimization priority (default: balanced)"
    )
    parser.add_argument(
        "--output", 
        help="Save results to JSON file"
    )
    parser.add_argument(
        "--verbose", 
        action="store_true",
        help="Enable verbose logging"
    )
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    try:
        # Load configuration
        config = LocalDatabaseConfig()
        
        # Create optimizer
        async with MilvusOptimizer(config) as optimizer:
            
            # Run benchmark if requested
            if args.benchmark:
                benchmark_results = await optimizer.run_performance_benchmark(
                    collection_name=args.collection,
                    num_queries=20
                )
                
                if args.output:
                    benchmark_file = Path(args.output).with_suffix('.benchmark.json')
                    with open(benchmark_file, 'w') as f:
                        json.dump(benchmark_results, f, indent=2)
                    logger.info(f"Benchmark results saved to {benchmark_file}")
            
            # Run optimization
            if args.collection:
                # Optimize specific collection
                results = await optimizer.optimize_collection(
                    args.collection,
                    dry_run=args.dry_run,
                    target_latency_ms=args.target_latency,
                    memory_limit_mb=args.memory_limit,
                    priority=args.priority
                )
            else:
                # Optimize all collections
                results = await optimizer.optimize_all_collections(
                    dry_run=args.dry_run,
                    target_latency_ms=args.target_latency,
                    memory_limit_mb=args.memory_limit,
                    priority=args.priority
                )
            
            # Save results if requested
            if args.output:
                output_file = Path(args.output)
                with open(output_file, 'w') as f:
                    json.dump(results, f, indent=2, default=str)
                logger.info(f"Results saved to {output_file}")
            
            # Exit with appropriate code
            if results.get("errors"):
                logger.error("Optimization completed with errors")
                return 1
            else:
                logger.info("Optimization completed successfully")
                return 0
    
    except Exception as e:
        logger.error(f"Optimization failed: {e}")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)