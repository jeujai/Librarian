#!/usr/bin/env python3
"""
Vector Database Test Data Generator - Performance Testing Vectors

This script generates large-scale vector datasets specifically designed for
performance testing, benchmarking, and stress testing of the Milvus vector
database in local development environments.

The script creates:
- Large collections with varying sizes (1K, 10K, 100K+ vectors)
- Different vector dimensions (128, 384, 768, 1536)
- Batch insertion performance tests
- Search performance benchmarks
- Memory usage and scalability tests
- Index optimization scenarios
- Concurrent access patterns

Usage:
    python scripts/seed-vector-performance-data.py [--scale SCALE] [--dimensions DIM] [--reset] [--verbose]
    
    --scale SCALE: Performance test scale (small/medium/large) (default: medium)
    --dimensions DIM: Vector dimensions to test (default: 384)
    --reset: Clear existing performance data before generating new data
    --verbose: Enable detailed performance monitoring and logging
"""

import asyncio
import argparse
import logging
import sys
import time
import psutil
import gc
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
import random
import json
import numpy as np
from concurrent.futures import ThreadPoolExecutor
import threading

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from multimodal_librarian.config.config_factory import get_database_config
from multimodal_librarian.clients.database_client_factory import DatabaseClientFactory

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class PerformanceDataGenerator:
    """Generator for large-scale performance testing vector datasets."""
    
    def __init__(self, verbose: bool = False):
        """Initialize the performance data generator."""
        self.verbose = verbose
        if verbose:
            logger.setLevel(logging.DEBUG)
        
        # Performance test configurations
        self.test_scales = {
            "small": {
                "collections": [
                    {"name": "perf_small_1k", "size": 1000, "dimension": 384},
                    {"name": "perf_small_5k", "size": 5000, "dimension": 384},
                ],
                "batch_sizes": [100, 500, 1000],
                "search_queries": 100,
                "concurrent_threads": 2
            },
            "medium": {
                "collections": [
                    {"name": "perf_medium_10k", "size": 10000, "dimension": 384},
                    {"name": "perf_medium_50k", "size": 50000, "dimension": 384},
                    {"name": "perf_medium_multi_dim", "size": 10000, "dimension": 768},
                ],
                "batch_sizes": [500, 1000, 2000, 5000],
                "search_queries": 500,
                "concurrent_threads": 4
            },
            "large": {
                "collections": [
                    {"name": "perf_large_100k", "size": 100000, "dimension": 384},
                    {"name": "perf_large_500k", "size": 500000, "dimension": 384},
                    {"name": "perf_large_high_dim", "size": 50000, "dimension": 1536},
                ],
                "batch_sizes": [1000, 5000, 10000],
                "search_queries": 1000,
                "concurrent_threads": 8
            }
        }
        
        # Performance test scenarios
        self.test_scenarios = [
            {
                "name": "Batch Insertion Performance",
                "description": "Test vector insertion performance with different batch sizes",
                "type": "insertion",
                "metrics": ["throughput", "latency", "memory_usage", "cpu_usage"]
            },
            {
                "name": "Search Performance Scaling",
                "description": "Test search performance as collection size increases",
                "type": "search",
                "metrics": ["query_latency", "recall_accuracy", "throughput", "memory_usage"]
            },
            {
                "name": "Concurrent Access Performance",
                "description": "Test performance under concurrent read/write operations",
                "type": "concurrent",
                "metrics": ["concurrent_throughput", "contention_latency", "error_rate"]
            },
            {
                "name": "Memory Usage Scaling",
                "description": "Test memory usage patterns with increasing data size",
                "type": "memory",
                "metrics": ["memory_per_vector", "memory_growth_rate", "gc_frequency"]
            },
            {
                "name": "Index Performance Impact",
                "description": "Test performance impact of different index configurations",
                "type": "indexing",
                "metrics": ["index_build_time", "search_speedup", "memory_overhead"]
            },
            {
                "name": "Dimension Scaling Performance",
                "description": "Test performance impact of different vector dimensions",
                "type": "dimension_scaling",
                "metrics": ["dimension_latency_scaling", "memory_scaling", "accuracy_impact"]
            }
        ]
        
        # Content templates for generating diverse vectors
        self.content_domains = [
            "technology", "science", "business", "education", "healthcare",
            "finance", "entertainment", "sports", "travel", "food",
            "art", "music", "literature", "history", "politics"
        ]
        
        # Performance monitoring
        self.performance_metrics = {
            "generation_start_time": None,
            "memory_usage_samples": [],
            "cpu_usage_samples": [],
            "generation_times": [],
            "batch_times": [],
            "vector_counts": []
        }
    
    def start_performance_monitoring(self):
        """Start monitoring system performance during generation."""
        self.performance_metrics["generation_start_time"] = time.time()
        self.performance_metrics["memory_usage_samples"] = []
        self.performance_metrics["cpu_usage_samples"] = []
    
    def sample_system_metrics(self):
        """Sample current system metrics."""
        process = psutil.Process()
        
        # Memory usage
        memory_info = process.memory_info()
        memory_mb = memory_info.rss / 1024 / 1024
        
        # CPU usage
        cpu_percent = process.cpu_percent()
        
        # System memory
        system_memory = psutil.virtual_memory()
        
        self.performance_metrics["memory_usage_samples"].append({
            "timestamp": time.time(),
            "process_memory_mb": memory_mb,
            "system_memory_percent": system_memory.percent,
            "cpu_percent": cpu_percent
        })
    
    def generate_performance_vector(self, vector_id: str, dimension: int, domain: str = None) -> List[float]:
        """
        Generate a performance test vector with realistic characteristics.
        
        Args:
            vector_id: Unique identifier for reproducibility
            dimension: Vector dimension
            domain: Content domain for clustering patterns
            
        Returns:
            Normalized vector embedding
        """
        # Use vector_id for reproducible generation
        seed = hash(vector_id) % (2**32)
        np.random.seed(seed)
        
        # Generate base vector with normal distribution
        vector = np.random.normal(0, 0.1, dimension)
        
        # Add domain-specific clustering if specified
        if domain:
            domain_seed = hash(domain) % dimension
            # Add domain-specific pattern
            for i in range(min(10, dimension)):
                idx = (domain_seed + i) % dimension
                vector[idx] += np.random.normal(0, 0.05)
        
        # Add some structure to make vectors more realistic
        # Simulate word embedding patterns
        if dimension >= 100:
            # Add some sparsity (common in real embeddings)
            sparse_indices = np.random.choice(dimension, size=dimension//10, replace=False)
            vector[sparse_indices] *= 0.1
            
            # Add some clustering in certain dimensions
            cluster_start = np.random.randint(0, dimension - 20)
            vector[cluster_start:cluster_start+20] += np.random.normal(0, 0.02, 20)
        
        # Normalize the vector
        norm = np.linalg.norm(vector)
        if norm > 0:
            vector = vector / norm
        
        return vector.tolist()
    
    def generate_batch_vectors(
        self, 
        batch_size: int, 
        dimension: int, 
        start_id: int = 0,
        domain_distribution: Optional[Dict[str, float]] = None
    ) -> List[Dict[str, Any]]:
        """
        Generate a batch of vectors for performance testing.
        
        Args:
            batch_size: Number of vectors to generate
            dimension: Vector dimension
            start_id: Starting ID for vector numbering
            domain_distribution: Distribution of domains for clustering
            
        Returns:
            List of vector documents with metadata
        """
        if domain_distribution is None:
            domain_distribution = {domain: 1.0/len(self.content_domains) for domain in self.content_domains}
        
        vectors = []
        
        for i in range(batch_size):
            vector_id = f"perf_vec_{start_id + i:08d}"
            
            # Select domain based on distribution
            domain = np.random.choice(
                list(domain_distribution.keys()),
                p=list(domain_distribution.values())
            )
            
            # Generate vector
            vector_embedding = self.generate_performance_vector(vector_id, dimension, domain)
            
            # Create metadata
            metadata = {
                "vector_id": vector_id,
                "domain": domain,
                "dimension": dimension,
                "batch_id": start_id // batch_size,
                "generation_timestamp": time.time(),
                "content_type": "performance_test",
                "quality_score": np.random.uniform(0.5, 1.0),
                "synthetic": True
            }
            
            vectors.append({
                "id": vector_id,
                "vector": vector_embedding,
                "metadata": metadata
            })
        
        return vectors
    
    async def generate_collection_data(
        self, 
        collection_config: Dict[str, Any],
        batch_size: int = 1000
    ) -> Dict[str, Any]:
        """
        Generate performance test data for a single collection.
        
        Args:
            collection_config: Configuration for the collection
            batch_size: Size of batches for generation
            
        Returns:
            Collection data with performance metrics
        """
        collection_name = collection_config["name"]
        total_size = collection_config["size"]
        dimension = collection_config["dimension"]
        
        logger.info(f"Generating {total_size:,} vectors for collection '{collection_name}' (dim={dimension})")
        
        # Performance tracking
        start_time = time.time()
        all_vectors = []
        batch_times = []
        
        # Generate domain distribution for realistic clustering
        domain_distribution = {}
        for domain in self.content_domains:
            # Some domains are more common than others
            weight = np.random.exponential(1.0)
            domain_distribution[domain] = weight
        
        # Normalize distribution
        total_weight = sum(domain_distribution.values())
        domain_distribution = {k: v/total_weight for k, v in domain_distribution.items()}
        
        # Generate vectors in batches
        num_batches = (total_size + batch_size - 1) // batch_size
        
        for batch_idx in range(num_batches):
            batch_start_time = time.time()
            
            start_id = batch_idx * batch_size
            current_batch_size = min(batch_size, total_size - start_id)
            
            # Generate batch
            batch_vectors = self.generate_batch_vectors(
                current_batch_size, 
                dimension, 
                start_id,
                domain_distribution
            )
            
            all_vectors.extend(batch_vectors)
            
            batch_time = time.time() - batch_start_time
            batch_times.append(batch_time)
            
            # Sample system metrics
            self.sample_system_metrics()
            
            # Progress reporting
            if self.verbose and (batch_idx + 1) % 10 == 0:
                progress = (batch_idx + 1) / num_batches * 100
                avg_batch_time = np.mean(batch_times[-10:])
                logger.debug(
                    f"  Progress: {progress:.1f}% "
                    f"(batch {batch_idx + 1}/{num_batches}, "
                    f"avg batch time: {avg_batch_time:.2f}s)"
                )
            
            # Memory management for large collections
            if len(all_vectors) > 50000:
                # Force garbage collection to manage memory
                gc.collect()
        
        total_time = time.time() - start_time
        
        # Calculate performance metrics
        vectors_per_second = total_size / total_time if total_time > 0 else 0
        avg_batch_time = np.mean(batch_times) if batch_times else 0
        memory_per_vector = self._estimate_memory_per_vector(dimension)
        
        collection_data = {
            "collection_name": collection_name,
            "vectors": all_vectors,
            "config": collection_config,
            "performance_metrics": {
                "total_vectors": len(all_vectors),
                "generation_time_seconds": total_time,
                "vectors_per_second": vectors_per_second,
                "average_batch_time": avg_batch_time,
                "batch_times": batch_times,
                "memory_per_vector_bytes": memory_per_vector,
                "estimated_total_memory_mb": (memory_per_vector * len(all_vectors)) / (1024 * 1024),
                "domain_distribution": domain_distribution
            }
        }
        
        logger.info(
            f"Generated {len(all_vectors):,} vectors in {total_time:.2f}s "
            f"({vectors_per_second:.0f} vectors/sec)"
        )
        
        return collection_data
    
    def _estimate_memory_per_vector(self, dimension: int) -> int:
        """Estimate memory usage per vector in bytes."""
        # Vector data: dimension * 4 bytes (float32)
        vector_size = dimension * 4
        
        # Metadata overhead (estimated)
        metadata_size = 200  # JSON metadata
        
        # ID string overhead
        id_size = 50
        
        # Python object overhead
        object_overhead = 100
        
        return vector_size + metadata_size + id_size + object_overhead
    
    async def generate_search_queries(
        self, 
        collection_data: Dict[str, Any], 
        num_queries: int
    ) -> List[Dict[str, Any]]:
        """
        Generate search queries for performance testing.
        
        Args:
            collection_data: Collection data to generate queries for
            num_queries: Number of queries to generate
            
        Returns:
            List of search queries with expected performance characteristics
        """
        vectors = collection_data["vectors"]
        dimension = collection_data["config"]["dimension"]
        
        if not vectors:
            return []
        
        queries = []
        
        for i in range(num_queries):
            query_type = np.random.choice([
                "exact_match",      # Query very similar to existing vector
                "cluster_search",   # Query within a domain cluster
                "random_search",    # Random query vector
                "edge_case"         # Edge case query (all zeros, very sparse, etc.)
            ], p=[0.3, 0.4, 0.2, 0.1])
            
            if query_type == "exact_match" and vectors:
                # Use existing vector with small noise
                base_vector = np.array(random.choice(vectors)["vector"])
                noise = np.random.normal(0, 0.01, dimension)
                query_vector = base_vector + noise
                query_vector = query_vector / np.linalg.norm(query_vector)
                expected_results = 10  # Should find many similar results
                
            elif query_type == "cluster_search":
                # Generate vector similar to a domain cluster
                domain = random.choice(self.content_domains)
                query_vector = np.array(self.generate_performance_vector(f"query_{i}", dimension, domain))
                expected_results = 5  # Should find some results in the domain
                
            elif query_type == "random_search":
                # Completely random vector
                query_vector = np.random.normal(0, 0.1, dimension)
                query_vector = query_vector / np.linalg.norm(query_vector)
                expected_results = 2  # May find few results
                
            else:  # edge_case
                # Edge case vectors
                edge_type = random.choice(["zeros", "sparse", "extreme"])
                if edge_type == "zeros":
                    query_vector = np.zeros(dimension)
                    query_vector[0] = 1.0  # Avoid zero vector
                elif edge_type == "sparse":
                    query_vector = np.zeros(dimension)
                    sparse_indices = np.random.choice(dimension, size=5, replace=False)
                    query_vector[sparse_indices] = np.random.normal(0, 1, 5)
                    query_vector = query_vector / np.linalg.norm(query_vector)
                else:  # extreme
                    query_vector = np.random.uniform(-1, 1, dimension)
                    query_vector = query_vector / np.linalg.norm(query_vector)
                
                expected_results = 1  # Edge cases may find very few results
            
            queries.append({
                "id": f"query_{i:04d}",
                "vector": query_vector.tolist(),
                "query_type": query_type,
                "expected_results": expected_results,
                "k": random.choice([5, 10, 20, 50]),  # Different k values for testing
                "metadata": {
                    "collection": collection_data["collection_name"],
                    "query_type": query_type,
                    "generation_timestamp": time.time()
                }
            })
        
        return queries
    
    async def generate_performance_datasets(self, scale: str) -> Dict[str, Any]:
        """
        Generate complete performance testing datasets.
        
        Args:
            scale: Performance test scale (small/medium/large)
            
        Returns:
            Complete performance testing dataset
        """
        if scale not in self.test_scales:
            raise ValueError(f"Unknown scale '{scale}'. Available: {list(self.test_scales.keys())}")
        
        scale_config = self.test_scales[scale]
        
        logger.info(f"Generating performance datasets for '{scale}' scale")
        logger.info(f"Collections: {len(scale_config['collections'])}")
        
        # Start performance monitoring
        self.start_performance_monitoring()
        
        datasets = {
            "scale": scale,
            "config": scale_config,
            "collections": [],
            "queries": [],
            "performance_summary": {},
            "generation_metadata": {
                "start_time": datetime.now().isoformat(),
                "generator_version": "1.0.0",
                "scale": scale
            }
        }
        
        # Generate collections
        total_vectors = 0
        total_generation_time = 0
        
        for collection_config in scale_config["collections"]:
            collection_start_time = time.time()
            
            # Generate collection data
            collection_data = await self.generate_collection_data(
                collection_config,
                batch_size=scale_config["batch_sizes"][0]  # Use first batch size as default
            )
            
            # Generate search queries for this collection
            queries = await self.generate_search_queries(
                collection_data,
                scale_config["search_queries"]
            )
            
            collection_data["queries"] = queries
            datasets["collections"].append(collection_data)
            datasets["queries"].extend(queries)
            
            collection_time = time.time() - collection_start_time
            total_vectors += len(collection_data["vectors"])
            total_generation_time += collection_time
            
            logger.info(
                f"Completed collection '{collection_config['name']}': "
                f"{len(collection_data['vectors']):,} vectors, "
                f"{len(queries)} queries in {collection_time:.2f}s"
            )
        
        # Calculate overall performance summary
        datasets["performance_summary"] = {
            "total_vectors": total_vectors,
            "total_queries": len(datasets["queries"]),
            "total_generation_time": total_generation_time,
            "overall_vectors_per_second": total_vectors / total_generation_time if total_generation_time > 0 else 0,
            "memory_usage_samples": self.performance_metrics["memory_usage_samples"],
            "estimated_total_memory_mb": sum(
                col["performance_metrics"]["estimated_total_memory_mb"] 
                for col in datasets["collections"]
            ),
            "generation_end_time": datetime.now().isoformat()
        }
        
        return datasets
    
    def print_performance_summary(self, datasets: Dict[str, Any]):
        """Print a comprehensive summary of generated performance datasets."""
        print(f"\n📊 Performance Test Datasets Generated ({datasets['scale']} scale)")
        print("=" * 80)
        
        summary = datasets["performance_summary"]
        
        print(f"📈 Overall Statistics:")
        print(f"   • Total vectors: {summary['total_vectors']:,}")
        print(f"   • Total queries: {summary['total_queries']:,}")
        print(f"   • Collections: {len(datasets['collections'])}")
        print(f"   • Generation time: {summary['total_generation_time']:.2f} seconds")
        print(f"   • Generation rate: {summary['overall_vectors_per_second']:.0f} vectors/second")
        print(f"   • Estimated memory: {summary['estimated_total_memory_mb']:.1f} MB")
        
        print(f"\n📋 Collection Details:")
        for i, collection in enumerate(datasets["collections"]):
            config = collection["config"]
            metrics = collection["performance_metrics"]
            
            print(f"\n   {i+1}. {config['name']}")
            print(f"      Size: {metrics['total_vectors']:,} vectors")
            print(f"      Dimension: {config['dimension']}")
            print(f"      Generation time: {metrics['generation_time_seconds']:.2f}s")
            print(f"      Rate: {metrics['vectors_per_second']:.0f} vectors/sec")
            print(f"      Memory: {metrics['estimated_total_memory_mb']:.1f} MB")
            print(f"      Queries: {len(collection['queries'])} test queries")
        
        print(f"\n🎯 Performance Test Scenarios:")
        for i, scenario in enumerate(self.test_scenarios):
            print(f"   {i+1}. {scenario['name']}")
            print(f"      Type: {scenario['type']}")
            print(f"      Metrics: {', '.join(scenario['metrics'])}")
        
        # Memory usage analysis
        if summary.get("memory_usage_samples"):
            memory_samples = summary["memory_usage_samples"]
            if memory_samples:
                max_memory = max(s["process_memory_mb"] for s in memory_samples)
                avg_memory = np.mean([s["process_memory_mb"] for s in memory_samples])
                
                print(f"\n💾 Memory Usage Analysis:")
                print(f"   • Peak memory: {max_memory:.1f} MB")
                print(f"   • Average memory: {avg_memory:.1f} MB")
                print(f"   • Memory samples: {len(memory_samples)}")


async def main():
    """Main function to generate performance testing datasets."""
    parser = argparse.ArgumentParser(description="Generate performance testing vectors for vector database")
    parser.add_argument("--scale", choices=["small", "medium", "large"], default="medium", 
                       help="Performance test scale")
    parser.add_argument("--dimensions", type=int, help="Override vector dimensions for all collections")
    parser.add_argument("--reset", action="store_true", help="Clear existing performance data")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose performance monitoring")
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    print("🚀 Performance Testing Vector Generator")
    print("=" * 60)
    print(f"Scale: {args.scale}")
    if args.dimensions:
        print(f"Override dimensions: {args.dimensions}")
    if args.reset:
        print("⚠️  Reset mode: Will clear existing performance data")
    print()
    
    try:
        # Initialize generator
        generator = PerformanceDataGenerator(verbose=args.verbose)
        
        # Override dimensions if specified
        if args.dimensions:
            for scale_config in generator.test_scales.values():
                for collection_config in scale_config["collections"]:
                    collection_config["dimension"] = args.dimensions
        
        # Generate performance datasets
        start_time = time.time()
        datasets = await generator.generate_performance_datasets(args.scale)
        total_time = time.time() - start_time
        
        # Print comprehensive summary
        generator.print_performance_summary(datasets)
        
        print(f"\n⏱️  Total generation time: {total_time:.2f} seconds")
        
        # Save datasets metadata (vectors are too large for JSON)
        output_dir = Path(__file__).parent.parent / "test_data" / "performance"
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Save summary and configuration
        summary_file = output_dir / f"performance_summary_{args.scale}.json"
        summary_data = {
            "scale": datasets["scale"],
            "config": datasets["config"],
            "performance_summary": datasets["performance_summary"],
            "generation_metadata": datasets["generation_metadata"],
            "collections_summary": [
                {
                    "name": col["collection_name"],
                    "config": col["config"],
                    "performance_metrics": col["performance_metrics"],
                    "query_count": len(col["queries"])
                }
                for col in datasets["collections"]
            ],
            "test_scenarios": generator.test_scenarios
        }
        
        with open(summary_file, 'w') as f:
            json.dump(summary_data, f, indent=2, default=str)
        
        # Save sample vectors for inspection
        sample_file = output_dir / f"sample_vectors_{args.scale}.json"
        sample_data = []
        
        for collection in datasets["collections"]:
            if collection["vectors"]:
                # Save first 5 vectors as samples
                for vector_doc in collection["vectors"][:5]:
                    sample = vector_doc.copy()
                    # Truncate vector for readability
                    sample["vector"] = sample["vector"][:10] + ["..."] + [f"({len(vector_doc['vector'])} total)"]
                    sample_data.append(sample)
        
        with open(sample_file, 'w') as f:
            json.dump(sample_data, f, indent=2, default=str)
        
        print(f"\n💾 Performance data saved:")
        print(f"   • Summary: {summary_file}")
        print(f"   • Samples: {sample_file}")
        
        # TODO: Store actual vectors in Milvus when client is available
        print(f"\n🎯 Ready for Performance Testing:")
        print(f"   • Collections: {len(datasets['collections'])}")
        print(f"   • Total test vectors: {datasets['performance_summary']['total_vectors']:,}")
        print(f"   • Search queries: {datasets['performance_summary']['total_queries']:,}")
        print(f"   • Test scenarios: {len(generator.test_scenarios)}")
        
        print("\n✅ Performance testing datasets generation completed successfully!")
        
        return 0
        
    except KeyboardInterrupt:
        print("\n⚠️  Generation interrupted by user")
        return 1
    except Exception as e:
        logger.error(f"Generation failed: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)