#!/usr/bin/env python3
"""
Milvus Optimization Configuration

This module provides configuration and utilities for optimizing Milvus
performance in local development environments. It includes:

- Index type selection based on collection size
- Search parameter optimization
- Performance monitoring and tuning
- Memory usage optimization
- Development-specific optimizations

The configuration is designed to balance performance, accuracy, and resource
usage for local development workflows.
"""

from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class IndexType(Enum):
    """Supported Milvus index types with their characteristics."""
    
    FLAT = "FLAT"           # Exact search, best accuracy, slowest for large datasets
    IVF_FLAT = "IVF_FLAT"   # Good balance of speed and accuracy
    IVF_SQ8 = "IVF_SQ8"     # Memory optimized version of IVF_FLAT
    IVF_PQ = "IVF_PQ"       # Product quantization, very memory efficient
    HNSW = "HNSW"           # Best for large datasets, fastest search
    ANNOY = "ANNOY"         # Tree-based, good for static datasets


class MetricType(Enum):
    """Supported distance metrics."""
    
    L2 = "L2"               # Euclidean distance
    IP = "IP"               # Inner product (for normalized vectors)
    COSINE = "COSINE"       # Cosine similarity


@dataclass
class IndexConfig:
    """Configuration for a specific index type."""
    
    index_type: IndexType
    metric_type: MetricType
    params: Dict[str, Any]
    min_vectors: int = 0
    max_vectors: int = float('inf')
    memory_multiplier: float = 1.0
    search_speed: str = "medium"  # slow, medium, fast
    accuracy: str = "high"        # low, medium, high
    description: str = ""


@dataclass
class SearchConfig:
    """Configuration for search parameters."""
    
    index_type: IndexType
    params: Dict[str, Any]
    description: str = ""


class MilvusOptimizationConfig:
    """
    Milvus optimization configuration manager.
    
    This class provides optimized configurations for different scenarios:
    - Development vs production environments
    - Small vs large datasets
    - Speed vs accuracy trade-offs
    - Memory usage optimization
    """
    
    # Index configurations for different collection sizes
    INDEX_CONFIGS = [
        IndexConfig(
            index_type=IndexType.FLAT,
            metric_type=MetricType.L2,
            params={},
            min_vectors=0,
            max_vectors=10000,
            memory_multiplier=1.0,
            search_speed="slow",
            accuracy="high",
            description="Exact search for small collections"
        ),
        IndexConfig(
            index_type=IndexType.IVF_FLAT,
            metric_type=MetricType.L2,
            params={"nlist": 128},
            min_vectors=1000,
            max_vectors=100000,
            memory_multiplier=1.2,
            search_speed="medium",
            accuracy="high",
            description="Balanced performance for medium collections"
        ),
        IndexConfig(
            index_type=IndexType.IVF_SQ8,
            metric_type=MetricType.L2,
            params={"nlist": 256},
            min_vectors=10000,
            max_vectors=500000,
            memory_multiplier=0.6,
            search_speed="medium",
            accuracy="medium",
            description="Memory-optimized for medium-large collections"
        ),
        IndexConfig(
            index_type=IndexType.HNSW,
            metric_type=MetricType.L2,
            params={"M": 16, "efConstruction": 200},
            min_vectors=50000,
            max_vectors=float('inf'),
            memory_multiplier=1.5,
            search_speed="fast",
            accuracy="high",
            description="High-performance for large collections"
        )
    ]
    
    # Search parameter configurations
    SEARCH_CONFIGS = {
        IndexType.IVF_FLAT: [
            SearchConfig(
                index_type=IndexType.IVF_FLAT,
                params={"nprobe": 1},
                description="Fastest search, lowest accuracy"
            ),
            SearchConfig(
                index_type=IndexType.IVF_FLAT,
                params={"nprobe": 10},
                description="Balanced speed and accuracy"
            ),
            SearchConfig(
                index_type=IndexType.IVF_FLAT,
                params={"nprobe": 50},
                description="Higher accuracy, slower search"
            )
        ],
        IndexType.IVF_SQ8: [
            SearchConfig(
                index_type=IndexType.IVF_SQ8,
                params={"nprobe": 1},
                description="Fastest search, lowest accuracy"
            ),
            SearchConfig(
                index_type=IndexType.IVF_SQ8,
                params={"nprobe": 16},
                description="Balanced speed and accuracy"
            ),
            SearchConfig(
                index_type=IndexType.IVF_SQ8,
                params={"nprobe": 64},
                description="Higher accuracy, slower search"
            )
        ],
        IndexType.HNSW: [
            SearchConfig(
                index_type=IndexType.HNSW,
                params={"ef": 16},
                description="Fastest search, lowest accuracy"
            ),
            SearchConfig(
                index_type=IndexType.HNSW,
                params={"ef": 64},
                description="Balanced speed and accuracy"
            ),
            SearchConfig(
                index_type=IndexType.HNSW,
                params={"ef": 256},
                description="Higher accuracy, slower search"
            )
        ]
    }
    
    # Development-specific optimizations
    DEVELOPMENT_OPTIMIZATIONS = {
        "small_dataset": {
            "description": "Optimizations for datasets < 10K vectors",
            "index_type": IndexType.FLAT,
            "search_params": {},
            "memory_limit_mb": 512,
            "enable_caching": True
        },
        "medium_dataset": {
            "description": "Optimizations for datasets 10K-100K vectors",
            "index_type": IndexType.IVF_FLAT,
            "search_params": {"nprobe": 10},
            "memory_limit_mb": 2048,
            "enable_caching": True
        },
        "large_dataset": {
            "description": "Optimizations for datasets > 100K vectors",
            "index_type": IndexType.HNSW,
            "search_params": {"ef": 64},
            "memory_limit_mb": 4096,
            "enable_caching": False  # Disable for large datasets
        }
    }
    
    @classmethod
    def get_optimal_index_config(
        cls, 
        vector_count: int,
        dimension: int = 384,
        memory_limit_mb: Optional[int] = None,
        priority: str = "balanced"  # "speed", "accuracy", "memory", "balanced"
    ) -> IndexConfig:
        """
        Get optimal index configuration for given constraints.
        
        Args:
            vector_count: Number of vectors in the collection
            dimension: Vector dimension
            memory_limit_mb: Memory limit in MB (optional)
            priority: Optimization priority
            
        Returns:
            Optimal index configuration
        """
        # Filter configs by vector count
        suitable_configs = [
            config for config in cls.INDEX_CONFIGS
            if config.min_vectors <= vector_count <= config.max_vectors
        ]
        
        if not suitable_configs:
            # Fallback to IVF_FLAT for any size
            return IndexConfig(
                index_type=IndexType.IVF_FLAT,
                metric_type=MetricType.L2,
                params={"nlist": min(max(vector_count // 100, 128), 4096)},
                description="Fallback configuration"
            )
        
        # Apply memory constraints if specified
        if memory_limit_mb:
            estimated_memory_mb = vector_count * dimension * 4 / (1024 * 1024)  # 4 bytes per float
            
            suitable_configs = [
                config for config in suitable_configs
                if estimated_memory_mb * config.memory_multiplier <= memory_limit_mb
            ]
        
        # Select based on priority
        if priority == "speed":
            return max(suitable_configs, key=lambda c: c.search_speed == "fast")
        elif priority == "accuracy":
            return max(suitable_configs, key=lambda c: c.accuracy == "high")
        elif priority == "memory":
            return min(suitable_configs, key=lambda c: c.memory_multiplier)
        else:  # balanced
            # Score based on multiple factors
            def score_config(config):
                speed_score = {"slow": 1, "medium": 2, "fast": 3}[config.search_speed]
                accuracy_score = {"low": 1, "medium": 2, "high": 3}[config.accuracy]
                memory_score = 3 - min(config.memory_multiplier, 3)  # Lower is better
                return speed_score + accuracy_score + memory_score
            
            return max(suitable_configs, key=score_config)
    
    @classmethod
    def get_optimal_search_params(
        cls,
        index_type: IndexType,
        k: int = 10,
        target_latency_ms: float = 100.0,
        accuracy_preference: str = "balanced"  # "speed", "accuracy", "balanced"
    ) -> Dict[str, Any]:
        """
        Get optimal search parameters for given constraints.
        
        Args:
            index_type: Type of index being used
            k: Number of results requested
            target_latency_ms: Target search latency
            accuracy_preference: Speed vs accuracy preference
            
        Returns:
            Optimal search parameters
        """
        if index_type not in cls.SEARCH_CONFIGS:
            return {}
        
        configs = cls.SEARCH_CONFIGS[index_type]
        
        if accuracy_preference == "speed":
            return configs[0].params
        elif accuracy_preference == "accuracy":
            return configs[-1].params
        else:  # balanced
            # Choose middle configuration, adjusted for k
            middle_idx = len(configs) // 2
            params = configs[middle_idx].params.copy()
            
            # Adjust parameters based on k
            if index_type in [IndexType.IVF_FLAT, IndexType.IVF_SQ8]:
                if "nprobe" in params:
                    # Increase nprobe for larger k
                    params["nprobe"] = min(params["nprobe"] * max(1, k // 10), 100)
            elif index_type == IndexType.HNSW:
                if "ef" in params:
                    # Increase ef for larger k
                    params["ef"] = max(params["ef"], k * 2)
            
            return params
    
    @classmethod
    def get_development_optimization(
        cls,
        vector_count: int
    ) -> Dict[str, Any]:
        """
        Get development-specific optimization configuration.
        
        Args:
            vector_count: Number of vectors in the collection
            
        Returns:
            Development optimization configuration
        """
        if vector_count < 10000:
            return cls.DEVELOPMENT_OPTIMIZATIONS["small_dataset"]
        elif vector_count < 100000:
            return cls.DEVELOPMENT_OPTIMIZATIONS["medium_dataset"]
        else:
            return cls.DEVELOPMENT_OPTIMIZATIONS["large_dataset"]
    
    @classmethod
    def estimate_memory_usage(
        cls,
        vector_count: int,
        dimension: int,
        index_config: IndexConfig
    ) -> Dict[str, float]:
        """
        Estimate memory usage for given configuration.
        
        Args:
            vector_count: Number of vectors
            dimension: Vector dimension
            index_config: Index configuration
            
        Returns:
            Memory usage estimates in MB
        """
        # Base vector storage (4 bytes per float)
        base_memory_mb = vector_count * dimension * 4 / (1024 * 1024)
        
        # Index overhead varies by type
        if index_config.index_type == IndexType.FLAT:
            index_overhead = 0.1  # Minimal overhead
        elif index_config.index_type in [IndexType.IVF_FLAT, IndexType.IVF_SQ8]:
            index_overhead = 0.2  # Moderate overhead
        elif index_config.index_type == IndexType.HNSW:
            index_overhead = 0.5  # Higher overhead for graph structure
        else:
            index_overhead = 0.3  # Default estimate
        
        total_memory_mb = base_memory_mb * (1 + index_overhead) * index_config.memory_multiplier
        
        return {
            "base_vectors_mb": base_memory_mb,
            "index_overhead_mb": base_memory_mb * index_overhead,
            "total_estimated_mb": total_memory_mb,
            "memory_multiplier": index_config.memory_multiplier
        }
    
    @classmethod
    def get_performance_recommendations(
        cls,
        vector_count: int,
        dimension: int,
        current_index_type: Optional[str] = None,
        avg_search_latency_ms: Optional[float] = None,
        memory_usage_mb: Optional[float] = None
    ) -> List[Dict[str, Any]]:
        """
        Get performance optimization recommendations.
        
        Args:
            vector_count: Number of vectors
            dimension: Vector dimension
            current_index_type: Current index type (if any)
            avg_search_latency_ms: Current average search latency
            memory_usage_mb: Current memory usage
            
        Returns:
            List of optimization recommendations
        """
        recommendations = []
        
        # Get optimal configuration
        optimal_config = cls.get_optimal_index_config(vector_count, dimension)
        
        # Index type recommendations
        if current_index_type is None:
            recommendations.append({
                "type": "create_index",
                "priority": "high",
                "description": f"Create {optimal_config.index_type.value} index for optimal performance",
                "expected_improvement": "10-100x faster searches",
                "action": f"Create index with type {optimal_config.index_type.value}"
            })
        elif current_index_type != optimal_config.index_type.value:
            recommendations.append({
                "type": "upgrade_index",
                "priority": "medium",
                "description": f"Upgrade from {current_index_type} to {optimal_config.index_type.value}",
                "expected_improvement": "2-5x performance improvement",
                "action": f"Recreate index with type {optimal_config.index_type.value}"
            })
        
        # Latency recommendations
        if avg_search_latency_ms and avg_search_latency_ms > 100:
            recommendations.append({
                "type": "optimize_search_params",
                "priority": "medium",
                "description": f"High search latency detected ({avg_search_latency_ms:.1f}ms)",
                "expected_improvement": "20-50% latency reduction",
                "action": "Tune search parameters for better speed/accuracy balance"
            })
        
        # Memory recommendations
        if memory_usage_mb and memory_usage_mb > 2048:  # > 2GB
            recommendations.append({
                "type": "reduce_memory",
                "priority": "medium",
                "description": f"High memory usage detected ({memory_usage_mb:.0f}MB)",
                "expected_improvement": "50-75% memory reduction",
                "action": "Consider using quantized index (IVF_SQ8) or dimension reduction"
            })
        
        # Collection size specific recommendations
        if vector_count > 1000000:  # > 1M vectors
            recommendations.append({
                "type": "scale_optimization",
                "priority": "high",
                "description": "Large collection detected - consider advanced optimizations",
                "expected_improvement": "Better scalability and performance",
                "action": "Implement collection partitioning or distributed indexing"
            })
        
        return recommendations


# Convenience functions for common operations
def get_recommended_index_params(vector_count: int, dimension: int = 384) -> Dict[str, Any]:
    """Get recommended index parameters for a collection."""
    config = MilvusOptimizationConfig.get_optimal_index_config(vector_count, dimension)
    return {
        "index_type": config.index_type.value,
        "metric_type": config.metric_type.value,
        "params": config.params
    }


def get_recommended_search_params(
    index_type: str, 
    k: int = 10, 
    preference: str = "balanced"
) -> Dict[str, Any]:
    """Get recommended search parameters."""
    try:
        index_enum = IndexType(index_type.upper())
        params = MilvusOptimizationConfig.get_optimal_search_params(
            index_enum, k, accuracy_preference=preference
        )
        return {
            "metric_type": "L2",
            "params": params
        }
    except ValueError:
        # Fallback for unknown index types
        return {
            "metric_type": "L2",
            "params": {"nprobe": min(max(k * 2, 10), 100)}
        }


if __name__ == "__main__":
    # Example usage
    print("Milvus Optimization Configuration Examples")
    print("=" * 50)
    
    # Small collection example
    small_config = MilvusOptimizationConfig.get_optimal_index_config(5000, 384)
    print(f"Small collection (5K vectors): {small_config.index_type.value}")
    print(f"  Parameters: {small_config.params}")
    print(f"  Description: {small_config.description}")
    
    # Medium collection example
    medium_config = MilvusOptimizationConfig.get_optimal_index_config(50000, 384)
    print(f"\nMedium collection (50K vectors): {medium_config.index_type.value}")
    print(f"  Parameters: {medium_config.params}")
    print(f"  Description: {medium_config.description}")
    
    # Large collection example
    large_config = MilvusOptimizationConfig.get_optimal_index_config(500000, 384)
    print(f"\nLarge collection (500K vectors): {large_config.index_type.value}")
    print(f"  Parameters: {large_config.params}")
    print(f"  Description: {large_config.description}")
    
    # Memory estimation
    memory_est = MilvusOptimizationConfig.estimate_memory_usage(100000, 384, medium_config)
    print(f"\nMemory estimation for 100K vectors:")
    print(f"  Base vectors: {memory_est['base_vectors_mb']:.1f}MB")
    print(f"  Total estimated: {memory_est['total_estimated_mb']:.1f}MB")