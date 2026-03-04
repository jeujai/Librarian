# Vector Database Test Data

This directory contains test data generated for vector database testing, similarity search validation, and performance benchmarking in the local development environment.

## Generated Test Data

### Document Embeddings (`document_embeddings.json`)
- Realistic document embeddings with diverse metadata
- Multiple domains: ML, software engineering, data science, AI ethics, education
- Varied document types: research papers, technical docs, tutorials, case studies
- Rich metadata: authors, institutions, publication dates, keywords
- Vector dimension: 384 (compatible with sentence-transformers)

### Similarity Search Scenarios (`similarity_scenarios.json`)
- Comprehensive test scenarios for similarity search validation
- Scenario types:
  - **Exact Match**: Near-identical documents with high similarity
  - **Semantic Match**: Semantically similar but textually different content
  - **Domain Clustering**: Documents within the same domain
  - **Cross-Domain**: Similarity across different domains
  - **Hierarchical**: Parent-child document relationships
  - **Negative Similarity**: Unrelated or opposite content
  - **Multilingual**: Cross-language similarity testing
  - **Temporal Evolution**: Documents showing evolution over time

### Performance Testing Data (`performance/`)
- Large-scale datasets for performance benchmarking
- Multiple collection sizes: 1K, 10K, 50K, 100K+ vectors
- Different vector dimensions: 384, 768, 1536
- Performance test scenarios:
  - Batch insertion performance
  - Search performance scaling
  - Concurrent access patterns
  - Memory usage analysis
  - Index optimization impact

## Test Data Profiles

### Development Profile
- **Document Embeddings**: 25 documents
- **Similarity Scenarios**: 10 test scenarios
- **Performance Data**: Small scale (1K-5K vectors)
- **Purpose**: Daily development and basic testing

### Testing Profile
- **Document Embeddings**: 100 documents
- **Similarity Scenarios**: 25 test scenarios
- **Performance Data**: Medium scale (10K-50K vectors)
- **Purpose**: Integration testing and validation

### Performance Profile
- **Document Embeddings**: 500 documents
- **Similarity Scenarios**: 50 test scenarios
- **Performance Data**: Large scale (100K+ vectors)
- **Purpose**: Performance benchmarking and stress testing

## Usage

### Generate All Test Data
```bash
# Development profile (default)
python scripts/seed-all-vector-test-data.py

# Testing profile
python scripts/seed-all-vector-test-data.py --profile testing

# Performance profile
python scripts/seed-all-vector-test-data.py --profile performance

# Reset existing data
python scripts/seed-all-vector-test-data.py --reset --verbose
```

### Generate Specific Test Data Types
```bash
# Document embeddings only
python scripts/seed-vector-document-embeddings.py --count 50

# Similarity scenarios only
python scripts/seed-vector-similarity-scenarios.py --scenarios 20

# Performance data only
python scripts/seed-vector-performance-data.py --scale medium
```

### Test Vector Operations
```bash
# Test similarity search
python scripts/test-vector-similarity-search.py

# Performance benchmarks
python scripts/benchmark-vector-performance.py

# Validate test scenarios
python scripts/validate-similarity-scenarios.py
```

## File Structure

```
test_data/
├── README.md                           # This file
├── generation_results.json             # Generation metadata and results
├── document_embeddings.json            # Sample document embeddings (truncated)
├── similarity_scenarios.json           # Similarity test scenarios (truncated)
└── performance/
    ├── performance_summary_small.json  # Small scale performance summary
    ├── performance_summary_medium.json # Medium scale performance summary
    ├── performance_summary_large.json  # Large scale performance summary
    ├── sample_vectors_small.json       # Sample vectors for inspection
    ├── sample_vectors_medium.json      # Sample vectors for inspection
    └── sample_vectors_large.json       # Sample vectors for inspection
```

## Vector Database Schema

### Collections Created

1. **document_embeddings**
   - Primary key: `document_id` (VARCHAR)
   - Vector field: `embedding` (FLOAT_VECTOR, dim=384)
   - Metadata: Document title, author, type, domain, etc.

2. **knowledge_chunks**
   - Primary key: `id` (VARCHAR)
   - Vector field: `vector` (FLOAT_VECTOR, dim=384)
   - Metadata: Content, source_id, chunk_index, etc.

3. **similarity_test_vectors**
   - Primary key: `id` (VARCHAR)
   - Vector field: `vector` (FLOAT_VECTOR, dim=384)
   - Metadata: Scenario type, expected similarity, etc.

4. **performance_test_vectors**
   - Primary key: `id` (VARCHAR)
   - Vector field: `vector` (FLOAT_VECTOR, configurable dimension)
   - Metadata: Domain, batch_id, generation timestamp, etc.

## Test Validation

### Similarity Search Validation
- **Exact Match**: Expected similarity > 0.95
- **Semantic Match**: Expected similarity 0.65-0.85
- **Domain Clustering**: Expected similarity 0.55-0.75
- **Negative Similarity**: Expected similarity < 0.30
- **Hierarchical**: Parent-child similarity 0.60-0.80

### Performance Benchmarks
- **Insertion Rate**: Target > 1000 vectors/second
- **Search Latency**: Target < 100ms for 10K collection
- **Memory Usage**: Target < 500 bytes per vector
- **Concurrent Throughput**: Target > 100 queries/second

## Troubleshooting

### Common Issues

1. **Memory Errors During Generation**
   - Reduce batch sizes in performance data generation
   - Use smaller test profiles (development instead of performance)
   - Ensure sufficient system memory (8GB+ recommended)

2. **Slow Generation Performance**
   - Check system resources (CPU, memory)
   - Reduce concurrent thread count
   - Use SSD storage for better I/O performance

3. **Vector Dimension Mismatches**
   - Ensure consistent dimensions across all test data
   - Check embedding model compatibility
   - Validate collection schemas before insertion

4. **Similarity Test Failures**
   - Check vector normalization
   - Validate distance metric configuration (L2, IP, COSINE)
   - Review expected similarity thresholds

### Performance Optimization

1. **Faster Generation**
   - Use development profile for quick testing
   - Enable batch processing for large datasets
   - Utilize multiple CPU cores for parallel generation

2. **Memory Optimization**
   - Generate data in smaller batches
   - Clear intermediate results regularly
   - Use streaming for large collections

3. **Storage Optimization**
   - Compress vector data when not in use
   - Use appropriate index types for search patterns
   - Monitor disk space usage during generation

## Contributing

When adding new test data generators:

1. Follow the existing naming convention: `seed-vector-{type}.py`
2. Include comprehensive metadata and validation
3. Support different scales and configurations
4. Add performance monitoring and progress reporting
5. Update this README with new test data descriptions

## Related Documentation

- [Local Development Setup](../docs/local-development-setup.md)
- [Vector Database Configuration](../database/milvus/README.md)
- [Performance Testing Guide](../docs/performance-testing.md)
- [Similarity Search Testing](../docs/similarity-search-testing.md)