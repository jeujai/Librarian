#!/usr/bin/env python3
"""
YAGO Import Performance Benchmark Script

This script benchmarks the YAGO Neo4j loader with different batch sizes
to determine optimal throughput and verify query latency requirements.

Usage:
    python scripts/benchmark_yago_import.py [--batch-sizes 100,500,1000,2000,5000] [--entity-count 10000]
"""

import asyncio
import json
import logging
import statistics
import sys
import time
from dataclasses import dataclass
from typing import List, Optional

# Add src to path for imports
sys.path.insert(0, "src")

from multimodal_librarian.clients.neo4j_client import Neo4jClient
from multimodal_librarian.components.yago.loader import YagoNeo4jLoader
from multimodal_librarian.components.yago.models import FilteredEntity

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("yago_benchmark")


@dataclass
class BenchmarkResult:
    """Result of a single benchmark run."""
    batch_size: int
    entity_count: int
    duration_seconds: float
    entities_per_second: float
    avg_query_latency_ms: float
    min_query_latency_ms: float
    max_query_latency_ms: float
    p95_query_latency_ms: float
    p99_query_latency_ms: float
    success: bool
    error_message: Optional[str] = None


@dataclass
class BatchSizeBenchmark:
    """Benchmark results for a specific batch size."""
    batch_size: int
    runs: List[BenchmarkResult]
    
    @property
    def avg_entities_per_second(self) -> float:
        """Calculate average entities per second across all runs."""
        valid_runs = [r for r in self.runs if r.success]
        if not valid_runs:
            return 0.0
        return statistics.mean(r.entities_per_second for r in valid_runs)
    
    @property
    def avg_query_latency_ms(self) -> float:
        """Calculate average query latency across all runs."""
        valid_runs = [r for r in self.runs if r.success]
        if not valid_runs:
            return 0.0
        return statistics.mean(r.avg_query_latency_ms for r in valid_runs)
    
    @property
    def max_query_latency_ms(self) -> float:
        """Get maximum query latency across all runs."""
        valid_runs = [r for r in self.runs if r.success]
        if not valid_runs:
            return 0.0
        return max(r.max_query_latency_ms for r in valid_runs)


def generate_test_entities(count: int) -> List[FilteredEntity]:
    """Generate test entities for benchmarking."""
    entities = []
    for i in range(count):
        entity_id = f"Q{i + 1}"
        entities.append(
            FilteredEntity(
                entity_id=entity_id,
                label=f"Test Entity {i + 1}",
                description=f"This is a test entity with ID {entity_id}",
                instance_of=["Q1", "Q2"] if i % 3 == 0 else ["Q3"],
                subclass_of=["Q5"] if i % 2 == 0 else [],
                aliases=[f"Alias {i}", f"Test {i}"],
                see_also=[f"Q{i + 10}"] if i % 5 == 0 else [],
            )
        )
    return entities


async def ensure_yago_indexes(neo4j_client: Neo4jClient) -> None:
    """Ensure required indexes exist for YAGO data."""
    index_statements = [
        # Index on entity_id for fast lookups
        "CREATE INDEX yago_entity_id_index IF NOT EXISTS "
        "FOR (e:YagoEntity) ON (e.entity_id)",
        # Index on label for search
        "CREATE INDEX yago_entity_label_index IF NOT EXISTS "
        "FOR (e:YagoEntity) ON (e.label)",
        # Index on Alias label
        "CREATE INDEX alias_label_index IF NOT EXISTS "
        "FOR (a:Alias) ON (a.label)",
    ]
    
    try:
        async with neo4j_client.driver.session(
            database=neo4j_client.database
        ) as session:
            for statement in index_statements:
                try:
                    await session.run(statement)
                    logger.debug(f"Index ensured: {statement[:50]}...")
                except Exception as e:
                    # Index may already exist
                    logger.debug(f"Index creation note: {e}")
        logger.info("YAGO indexes ensured successfully")
    except Exception as e:
        logger.error(f"Failed to ensure indexes: {e}")
        raise


async def benchmark_import(
    loader: YagoNeo4jLoader,
    entities: List[FilteredEntity],
    batch_size: int,
) -> BenchmarkResult:
    """
    Benchmark entity import with a specific batch size.
    
    Args:
        loader: YagoNeo4jLoader instance
        entities: List of entities to import
        batch_size: Batch size to use
        
    Returns:
        BenchmarkResult with timing and latency metrics
    """
    start_time = time.time()
    
    try:
        # Create async iterator from entities
        async def entity_iterator():
            for entity in entities:
                yield entity
        
        # Import entities
        result = await loader.import_entities(
            entity_iterator(),
            total_entities=len(entities)
        )
        
        duration = time.time() - start_time
        entities_per_second = len(entities) / duration if duration > 0 else 0
        
        # Measure query latency
        latencies = await measure_query_latency(loader, sample_size=min(100, len(entities)))
        
        return BenchmarkResult(
            batch_size=batch_size,
            entity_count=len(entities),
            duration_seconds=duration,
            entities_per_second=entities_per_second,
            avg_query_latency_ms=statistics.mean(latencies),
            min_query_latency_ms=min(latencies),
            max_query_latency_ms=max(latencies),
            p95_query_latency_ms=sorted(latencies)[int(len(latencies) * 0.95)] if latencies else 0,
            p99_query_latency_ms=sorted(latencies)[int(len(latencies) * 0.99)] if latencies else 0,
            success=True,
        )
        
    except Exception as e:
        duration = time.time() - start_time
        logger.error(f"Benchmark failed for batch size {batch_size}: {e}")
        return BenchmarkResult(
            batch_size=batch_size,
            entity_count=len(entities),
            duration_seconds=duration,
            entities_per_second=0,
            avg_query_latency_ms=0,
            min_query_latency_ms=0,
            max_query_latency_ms=0,
            p95_query_latency_ms=0,
            p99_query_latency_ms=0,
            success=False,
            error_message=str(e),
        )


async def measure_query_latency(
    loader: YagoNeo4jLoader,
    sample_size: int = 100,
) -> List[float]:
    """
    Measure query latency for various YAGO queries.
    
    Args:
        loader: YagoNeo4jLoader instance
        sample_size: Number of queries to run
        
    Returns:
        List of latency measurements in milliseconds
    """
    latencies = []
    
    # Test 1: Entity lookup by ID
    for i in range(min(sample_size, 10)):
        entity_id = f"Q{i + 1}"
        start = time.time()
        try:
            await loader._neo4j_client.execute_query(
                "MATCH (e:YagoEntity {entity_id: $entity_id}) "
                "RETURN e.entity_id, e.label, e.description",
                {"entity_id": entity_id}
            )
        except Exception:
            pass
        latencies.append((time.time() - start) * 1000)
    
    # Test 2: Label search
    for i in range(min(sample_size, 10)):
        query = f"Test Entity {i + 1}"
        start = time.time()
        try:
            await loader._neo4j_client.execute_query(
                "MATCH (e:YagoEntity) "
                "WHERE e.label CONTAINS $query "
                "RETURN e.entity_id, e.label LIMIT 5",
                {"query": query}
            )
        except Exception:
            pass
        latencies.append((time.time() - start) * 1000)
    
    # Test 3: Instance-of query
    for i in range(min(sample_size, 10)):
        start = time.time()
        try:
            await loader._neo4j_client.execute_query(
                "MATCH (e:YagoEntity)-[:INSTANCE_OF]->(c:YagoEntity {entity_id: $class_id}) "
                "RETURN e.entity_id LIMIT 10",
                {"class_id": "Q1"}
            )
        except Exception:
            pass
        latencies.append((time.time() - start) * 1000)
    
    # Test 4: Count query
    for i in range(min(sample_size, 10)):
        start = time.time()
        try:
            await loader._neo4j_client.execute_query(
                "MATCH (e:YagoEntity) RETURN count(e) as count"
            )
        except Exception:
            pass
        latencies.append((time.time() - start) * 1000)
    
    return latencies


async def run_batch_size_benchmark(
    neo4j_client: Neo4jClient,
    batch_sizes: List[int],
    entity_count: int = 5000,
    runs_per_size: int = 3,
) -> List[BatchSizeBenchmark]:
    """
    Run benchmarks for multiple batch sizes.
    
    Args:
        neo4j_client: Neo4j client instance
        batch_sizes: List of batch sizes to test
        entity_count: Number of entities to import per run
        runs_per_size: Number of runs per batch size for averaging
        
    Returns:
        List of BatchSizeBenchmark results
    """
    results = []
    
    for batch_size in batch_sizes:
        logger.info(f"\n{'='*60}")
        logger.info(f"Benchmarking batch size: {batch_size}")
        logger.info(f"{'='*60}")
        
        batch_results = []
        
        for run in range(runs_per_size):
            logger.info(f"  Run {run + 1}/{runs_per_size}")
            
            # Create fresh loader with specified batch size
            loader = YagoNeo4jLoader(
                neo4j_client=neo4j_client,
                batch_size=batch_size,
            )
            
            # Ensure indexes exist
            await ensure_yago_indexes(neo4j_client)
            
            # Clear existing data for clean benchmark
            await loader.clear_all()
            
            # Generate test entities
            entities = generate_test_entities(entity_count)
            
            # Run benchmark
            result = await benchmark_import(loader, entities, batch_size)
            batch_results.append(result)
            
            if result.success:
                logger.info(f"    Entities: {result.entity_count}, "
                          f"Duration: {result.duration_seconds:.2f}s, "
                          f"Rate: {result.entities_per_second:.0f} entities/s, "
                          f"Avg Latency: {result.avg_query_latency_ms:.2f}ms")
            else:
                logger.error(f"    FAILED: {result.error_message}")
        
        results.append(BatchSizeBenchmark(batch_size=batch_size, runs=batch_results))
    
    return results


def print_benchmark_summary(results: List[BatchSizeBenchmark]) -> None:
    """Print a formatted summary of benchmark results."""
    print("\n" + "=" * 80)
    print("YAGO IMPORT PERFORMANCE BENCHMARK SUMMARY")
    print("=" * 80)
    print(f"\n{'Batch Size':<12} {'Avg Rate (ent/s)':<18} {'Avg Latency':<14} {'Max Latency':<14} {'Status':<10}")
    print("-" * 80)
    
    optimal_batch_size = None
    optimal_rate = 0
    
    for benchmark in results:
        rate = benchmark.avg_entities_per_second
        latency = benchmark.avg_query_latency_ms
        max_latency = benchmark.max_query_latency_ms
        success_count = sum(1 for r in benchmark.runs if r.success)
        
        status = "✓ PASS" if max_latency < 100 else "✗ FAIL"
        
        print(f"{benchmark.batch_size:<12} {rate:<18.0f} {latency:<14.2f} {max_latency:<14.2f} {status:<10}")
        
        # Track optimal batch size (highest rate with latency < 100ms)
        if rate > optimal_rate and max_latency < 100:
            optimal_rate = rate
            optimal_batch_size = benchmark.batch_size
    
    print("-" * 80)
    
    if optimal_batch_size:
        print(f"\n✓ OPTIMAL BATCH SIZE: {optimal_batch_size} "
              f"(achieving {optimal_rate:.0f} entities/second with latency < 100ms)")
    else:
        # Find best performing even if over latency target
        best = max(results, key=lambda b: b.avg_entities_per_second)
        print(f"\n⚠ No batch size achieved <100ms latency target")
        print(f"  Best performing: batch_size={best.batch_size} "
              f"at {best.avg_entities_per_second:.0f} entities/s")
        print(f"  Max latency: {best.max_query_latency_ms:.2f}ms")
    
    print("\n" + "=" * 80)
    print("REQUIREMENTS VERIFICATION")
    print("=" * 80)
    
    # Check requirements
    all_pass = True
    for benchmark in results:
        max_latency = benchmark.max_query_latency_ms
        rate = benchmark.avg_entities_per_second
        
        if max_latency < 100:
            print(f"  ✓ Query latency < 100ms: PASS (batch_size={benchmark.batch_size}, "
                  f"max_latency={max_latency:.2f}ms)")
        else:
            print(f"  ✗ Query latency < 100ms: FAIL (batch_size={benchmark.batch_size}, "
                  f"max_latency={max_latency:.2f}ms)")
            all_pass = False
        
        if rate >= 1000:
            print(f"  ✓ Import rate >= 1000 ent/s: PASS (batch_size={benchmark.batch_size}, "
                  f"rate={rate:.0f} ent/s)")
        else:
            print(f"  ⚠ Import rate >= 1000 ent/s: BELOW TARGET (batch_size={benchmark.batch_size}, "
                  f"rate={rate:.0f} ent/s)")
    
    print("=" * 80)
    
    if all_pass:
        print("\n✓ All performance requirements met!")
    else:
        print("\n⚠ Some performance requirements not met - see above for details")


async def verify_indexes_exist(neo4j_client: Neo4jClient) -> bool:
    """Verify that required indexes exist."""
    try:
        async with neo4j_client.driver.session(
            database=neo4j_client.database
        ) as session:
            # Check for YagoEntity indexes
            result = await session.run(
                "SHOW INDEXES WHERE labels = ['YagoEntity'] "
                "YIELD name, properties, type"
            )
            indexes = []
            async for record in result:
                indexes.append({
                    "name": record["name"],
                    "properties": record["properties"],
                    "type": record["type"]
                })
            
            logger.info(f"Found {len(indexes)} YagoEntity indexes:")
            for idx in indexes:
                logger.info(f"  - {idx['name']}: {idx['properties']} ({idx['type']})")
            
            # Check for entity_id index
            entity_id_idx = any(
                "entity_id" in idx["properties"] 
                for idx in indexes
            )
            # Check for label index
            label_idx = any(
                "label" in idx["properties"] 
                for idx in indexes
            )
            
            if entity_id_idx and label_idx:
                logger.info("✓ Both entity_id and label indexes exist")
                return True
            else:
                logger.warning(f"✗ Missing indexes: entity_id={entity_id_idx}, label={label_idx}")
                return False
                
    except Exception as e:
        logger.error(f"Failed to verify indexes: {e}")
        return False


async def main():
    """Main entry point for the benchmark script."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="YAGO Import Performance Benchmark"
    )
    parser.add_argument(
        "--batch-sizes",
        type=str,
        default="100,500,1000,2000,5000",
        help="Comma-separated list of batch sizes to test"
    )
    parser.add_argument(
        "--entity-count",
        type=int,
        default=5000,
        help="Number of entities to import per benchmark run"
    )
    parser.add_argument(
        "--runs",
        type=int,
        default=3,
        help="Number of runs per batch size"
    )
    parser.add_argument(
        "--uri",
        type=str,
        default="bolt://localhost:7687",
        help="Neo4j connection URI"
    )
    parser.add_argument(
        "--user",
        type=str,
        default="neo4j",
        help="Neo4j username"
    )
    parser.add_argument(
        "--password",
        type=str,
        default="password",
        help="Neo4j password"
    )
    parser.add_argument(
        "--database",
        type=str,
        default="neo4j",
        help="Neo4j database name"
    )
    
    args = parser.parse_args()
    
    # Parse batch sizes
    batch_sizes = [int(s.strip()) for s in args.batch_sizes.split(",")]
    
    logger.info("=" * 60)
    logger.info("YAGO IMPORT PERFORMANCE BENCHMARK")
    logger.info("=" * 60)
    logger.info(f"Batch sizes to test: {batch_sizes}")
    logger.info(f"Entities per run: {args.entity_count}")
    logger.info(f"Runs per batch size: {args.runs}")
    logger.info("=" * 60)
    
    # Create Neo4j client
    neo4j_client = Neo4jClient(
        uri=args.uri,
        user=args.user,
        password=args.password,
        database=args.database,
    )
    
    try:
        # Connect to Neo4j
        logger.info("Connecting to Neo4j...")
        await neo4j_client.connect()
        logger.info("✓ Connected to Neo4j")
        
        # Verify indexes exist
        logger.info("\nVerifying YAGO indexes...")
        await verify_indexes_exist(neo4j_client)
        
        # Run benchmarks
        logger.info("\nStarting batch size benchmarks...")
        results = await run_batch_size_benchmark(
            neo4j_client=neo4j_client,
            batch_sizes=batch_sizes,
            entity_count=args.entity_count,
            runs_per_size=args.runs,
        )
        
        # Print summary
        print_benchmark_summary(results)
        
        # Save results to JSON
        output_file = "benchmark_results.json"
        output_data = {
            "batch_sizes_tested": batch_sizes,
            "entities_per_run": args.entity_count,
            "runs_per_size": args.runs,
            "results": [
                {
                    "batch_size": b.batch_size,
                    "avg_entities_per_second": b.avg_entities_per_second,
                    "avg_query_latency_ms": b.avg_query_latency_ms,
                    "max_query_latency_ms": b.max_query_latency_ms,
                    "runs": [
                        {
                            "entity_count": r.entity_count,
                            "duration_seconds": r.duration_seconds,
                            "entities_per_second": r.entities_per_second,
                            "avg_query_latency_ms": r.avg_query_latency_ms,
                            "max_query_latency_ms": r.max_query_latency_ms,
                            "success": r.success,
                        }
                        for r in b.runs
                    ]
                }
                for b in results
            ]
        }
        
        with open(output_file, "w") as f:
            json.dump(output_data, f, indent=2)
        logger.info(f"\nBenchmark results saved to: {output_file}")
        
    except Exception as e:
        logger.error(f"Benchmark failed: {e}")
        raise
    finally:
        # Disconnect
        await neo4j_client.disconnect()
        logger.info("Disconnected from Neo4j")


if __name__ == "__main__":
    asyncio.run(main())