# Milvus Indexing and Search Optimization Guide

This guide covers the Milvus indexing and search optimization features implemented for local development environments. The optimization system automatically selects optimal index types and search parameters based on collection characteristics to provide the best balance of performance, accuracy, and resource usage.

## Overview

The Milvus optimization system provides:

- **Dynamic Index Selection**: Automatically chooses the best index type based on collection size
- **Optimized Search Parameters**: Dynamically adjusts search parameters for optimal performance
- **Performance Monitoring**: Measures and tracks search performance metrics
- **Memory Optimization**: Balances performance with memory usage constraints
- **Automated Recommendations**: Provides actionable optimization suggestions

## Index Types and Selection

### Automatic Index Selection

The system automatically selects the optimal index type based on collection size:

| Collection Size | Recommended Index | Characteristics |
|----------------|-------------------|-----------------|
| < 10K vectors  | FLAT             | Exact search, best accuracy |
| 10K - 100K     | IVF_FLAT         | Balanced speed and accuracy |
| 100K - 500K    | IVF_SQ8          | Memory optimized |
| > 500K         | HNSW             | Best performance for large datasets |

### Index Types Explained

#### FLAT Index
- **Use Case**: Small collections (< 10K vectors)
- **Characteristics**: Exact search, 100% accuracy, slower for large datasets
- **Memory Usage**: 1x vector data size
- **Search Speed**: Slow for large datasets, fast for small ones

#### IVF_FLAT Index
- **Use Case**: Medium collections (10K - 100K vectors)
- **Characteristics**: Good balance of speed and accuracy
- **Memory Usage**: ~1.2x vector data size
- **Search Speed**: Medium
- **Parameters**: `nlist` (number of clusters)

#### IVF_SQ8 Index
- **Use Case**: Memory-constrained environments
- **Characteristics**: Quantized vectors, reduced memory usage
- **Memory Usage**: ~0.6x vector data size
- **Search Speed**: Medium
- **Parameters**: `nlist` (number of clusters)

#### HNSW Index
- **Use Case**: Large collections (> 100K vectors)
- **Characteristics**: Hierarchical graph structure, excellent performance
- **Memory Usage**: ~1.5x vector data size
- **Search Speed**: Fast
- **Parameters**: `M` (connections per node), `efConstruction` (build quality)

## Search Parameter Optimization

### Dynamic Parameter Tuning

Search parameters are automatically optimized based on:

- **Collection size**: Larger collections need different parameters
- **Index type**: Each index type has specific parameters
- **Number of results (k)**: More results require adjusted parameters
- **Performance targets**: Balance between speed and accuracy

### IVF Index Parameters

For IVF_FLAT and IVF_SQ8 indexes:

```python
# nprobe calculation based on collection size and k
if vector_count < 10000:
    nprobe = min(max(k * 2, 10), nlist // 4)
elif vector_count < 100000:
    nprobe = min(max(k * 3, 20), nlist // 2)
else:
    nprobe = min(max(k * 4, 50), nlist)
```

### HNSW Index Parameters

For HNSW indexes:

```python
# ef calculation based on k and accuracy requirements
if k <= 10:
    ef = max(k * 8, 64)  # Higher accuracy for small k
elif k <= 50:
    ef = max(k * 6, 100)
else:
    ef = max(k * 4, 200)
```

## Configuration

### Environment Variables

Configure Milvus optimization through environment variables:

```bash
# Index configuration
MILVUS_INDEX_TYPE=AUTO          # AUTO for dynamic selection
MILVUS_METRIC_TYPE=L2           # Distance metric
MILVUS_NLIST=1024              # IVF index parameter
MILVUS_NPROBE=10               # IVF search parameter
MILVUS_EF=64                   # HNSW search parameter
MILVUS_M=16                    # HNSW index parameter
MILVUS_EF_CONSTRUCTION=200     # HNSW build parameter

# Optimization settings
MILVUS_AUTO_OPTIMIZE=true      # Enable automatic optimization
MILVUS_OPTIMIZATION_INTERVAL=3600  # Check interval in seconds
```

### Local Configuration

In your `.env.local` file:

```bash
# Milvus optimization settings
MILVUS_INDEX_TYPE=AUTO
MILVUS_AUTO_OPTIMIZE=true
MILVUS_OPTIMIZATION_INTERVAL=3600

# Performance tuning
MILVUS_NLIST=1024
MILVUS_NPROBE=10
MILVUS_EF=64
```

## Usage

### Automatic Optimization

The MilvusClient automatically optimizes collections when:

1. Creating indexes (selects optimal type)
2. Performing searches (uses optimal parameters)
3. Storing embeddings (creates indexes if needed)

```python
from multimodal_librarian.clients.milvus_client import MilvusClient

async with MilvusClient() as client:
    # Automatically creates optimized index
    await client.store_embeddings(chunks)
    
    # Uses optimized search parameters
    results = await client.semantic_search("query", top_k=10)
```

### Manual Optimization

You can manually optimize collections:

```python
# Optimize a specific collection
await client.optimize_collection("my_collection")

# Get optimization recommendations
recommendations = await client.get_optimization_recommendations("my_collection")

# Run performance optimization
results = await client.optimize_search_performance(
    "my_collection",
    target_latency_ms=50.0,
    accuracy_threshold=0.95
)
```

### Using the Optimization Script

Run the optimization script to analyze and optimize all collections:

```bash
# Analyze all collections (dry run)
python scripts/optimize-milvus-performance.py --dry-run

# Optimize all collections
python scripts/optimize-milvus-performance.py

# Optimize specific collection
python scripts/optimize-milvus-performance.py --collection my_collection

# Run with specific targets
python scripts/optimize-milvus-performance.py \
    --target-latency 50 \
    --memory-limit 2048 \
    --priority speed

# Run performance benchmark
python scripts/optimize-milvus-performance.py --benchmark
```

## Performance Monitoring

### Built-in Metrics

The system tracks:

- **Search Latency**: Average and P95 response times
- **Memory Usage**: Estimated memory consumption
- **Index Efficiency**: Index build and search performance
- **Accuracy**: Search result quality metrics

### Performance Measurement

```python
# Measure current performance
performance = await client._measure_search_performance(
    collection_name, test_queries
)

print(f"Average latency: {performance['avg_latency_ms']:.2f}ms")
print(f"P95 latency: {performance['p95_latency_ms']:.2f}ms")
```

### Health Monitoring

```python
# Check Milvus health and performance
health = await client.health_check()
print(f"Status: {health['status']}")
print(f"Response time: {health['response_time']:.3f}s")
print(f"Collections: {health['collection_count']}")
print(f"Total vectors: {health['total_vectors']}")
```

## Optimization Strategies

### Development Environment

For local development, the system optimizes for:

- **Fast startup**: Quick index creation
- **Reasonable memory usage**: < 8GB total
- **Good search performance**: < 100ms average latency
- **Easy debugging**: Clear error messages and logging

### Collection Size Strategies

#### Small Collections (< 10K vectors)
- Use FLAT index for exact search
- No complex parameters needed
- Focus on accuracy over speed

#### Medium Collections (10K - 100K vectors)
- Use IVF_FLAT for balanced performance
- Optimize nlist based on collection size
- Balance speed and accuracy

#### Large Collections (> 100K vectors)
- Use HNSW for best performance
- Optimize graph parameters (M, ef)
- Prioritize search speed

### Memory Optimization

When memory is constrained:

1. **Use quantized indexes**: IVF_SQ8 reduces memory by ~40%
2. **Reduce dimensions**: Consider PCA or other reduction techniques
3. **Partition collections**: Split large collections into smaller ones
4. **Optimize parameters**: Lower nlist/M values use less memory

## Troubleshooting

### Common Issues

#### Slow Search Performance
```bash
# Check current performance
python scripts/optimize-milvus-performance.py --benchmark --collection my_collection

# Optimize search parameters
python scripts/optimize-milvus-performance.py --collection my_collection --priority speed
```

#### High Memory Usage
```bash
# Optimize for memory
python scripts/optimize-milvus-performance.py --memory-limit 2048 --priority memory

# Check memory usage
python -c "
import asyncio
from src.multimodal_librarian.clients.milvus_client import MilvusClient
async def check():
    async with MilvusClient() as client:
        stats = await client.get_performance_stats()
        print(f'Memory usage: {stats[\"memory_usage\"] / 1024 / 1024:.1f}MB')
asyncio.run(check())
"
```

#### Index Creation Failures
```bash
# Check collection stats
python -c "
import asyncio
from src.multimodal_librarian.clients.milvus_client import MilvusClient
async def check():
    async with MilvusClient() as client:
        stats = await client.get_collection_stats('my_collection')
        print(f'Vectors: {stats[\"vector_count\"]}')
        print(f'Dimension: {stats[\"dimension\"]}')
        print(f'Index: {stats[\"index_type\"]}')
asyncio.run(check())
"
```

### Performance Tuning Tips

1. **Monitor regularly**: Use the benchmark script to track performance
2. **Adjust parameters**: Fine-tune based on your specific use case
3. **Consider trade-offs**: Balance speed, accuracy, and memory usage
4. **Test with real data**: Use representative queries for optimization
5. **Update regularly**: Re-optimize as collections grow

## Advanced Configuration

### Custom Index Parameters

Override automatic selection with custom parameters:

```python
# Custom IVF_FLAT index
custom_params = {
    "index_type": "IVF_FLAT",
    "metric_type": "L2",
    "params": {"nlist": 2048}
}

await client.create_index("my_collection", "vector", custom_params)
```

### Performance Targets

Set specific performance targets:

```python
# Optimize for specific latency target
await client.optimize_search_performance(
    "my_collection",
    target_latency_ms=25.0,  # Very fast
    accuracy_threshold=0.90   # Good accuracy
)
```

### Memory Constraints

Optimize within memory limits:

```python
from database.milvus.optimization_config import MilvusOptimizationConfig

# Get memory-optimized configuration
config = MilvusOptimizationConfig.get_optimal_index_config(
    vector_count=100000,
    dimension=384,
    memory_limit_mb=1024,  # 1GB limit
    priority="memory"
)
```

## Best Practices

1. **Start with defaults**: Let the system auto-optimize initially
2. **Monitor performance**: Use built-in metrics and benchmarks
3. **Optimize incrementally**: Make small adjustments based on measurements
4. **Test thoroughly**: Validate optimizations with real workloads
5. **Document changes**: Keep track of custom optimizations
6. **Regular maintenance**: Re-optimize as data and usage patterns change

## Integration with Application

The optimization features integrate seamlessly with the existing application:

```python
# High-level semantic search (automatically optimized)
results = await client.semantic_search("machine learning", top_k=10)

# Store embeddings (automatically creates optimized indexes)
await client.store_embeddings(document_chunks)

# Get performance insights
recommendations = await client.get_optimization_recommendations("documents")
```

The system handles all optimization automatically while providing manual controls for advanced use cases.