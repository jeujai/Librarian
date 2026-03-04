# Local Development Performance Benchmarks

This directory contains comprehensive performance benchmarking tests for the local development conversion, validating that the local database setup meets all performance requirements specified in the local development conversion specification.

## Overview

The local development performance benchmarks validate:

- **Database Connection Performance**: Connection establishment, pooling, and concurrent access
- **Query Performance**: SQL, Cypher, and vector search query performance across all databases
- **Resource Usage**: Memory consumption, CPU usage, and system resource efficiency
- **End-to-End Performance**: Complete application workflows and processing pipelines
- **NFR Compliance**: Validation against Non-Functional Requirements from the spec

## Requirements Validated

### NFR-1: Performance Requirements
- ✅ Local setup startup time < 2 minutes
- ✅ Query performance within 20% of AWS setup
- ✅ Memory usage < 8GB total for all services
- ✅ CPU usage reasonable on development machines

### NFR-2: Reliability Requirements
- ✅ Services restart automatically on failure
- ✅ Data persistence across container restarts
- ✅ Graceful shutdown and cleanup
- ✅ Error handling and logging

## Test Structure

```
tests/performance/
├── test_local_development_benchmarks.py    # Main benchmark test suite
├── run_local_development_benchmarks.py     # Benchmark runner script
├── benchmark_config.json                   # Configuration file
├── README_LOCAL_DEVELOPMENT_BENCHMARKS.md  # This documentation
└── benchmark_reports/                      # Generated reports (created at runtime)
    ├── local_development_benchmarks_*.json # JSON results
    └── local_development_benchmark_report_*.html # HTML reports
```

## Test Classes

### TestDatabaseConnectionPerformance
Tests database connection establishment and pooling performance across all database types.

**Tests:**
- `test_postgresql_connection_performance`: PostgreSQL connection establishment
- `test_neo4j_connection_performance`: Neo4j connection establishment  
- `test_milvus_connection_performance`: Milvus connection establishment
- `test_concurrent_connection_performance`: Concurrent connections across all databases

**Validates:**
- Connection establishment time < 5 seconds
- Connection success rate > 95%
- Memory usage during connections < 100MB
- CPU usage during connections < 50%

### TestQueryPerformance
Tests database query performance across different database types and query complexities.

**Tests:**
- `test_postgresql_simple_query_performance`: Basic SQL query performance
- `test_neo4j_simple_query_performance`: Basic Cypher query performance
- `test_milvus_vector_search_performance`: Vector similarity search performance
- `test_concurrent_query_performance`: Concurrent query execution

**Validates:**
- Simple query response time < 100ms
- Vector search response time < 500ms
- Query success rate > 95%
- Concurrent query handling

### TestSystemResourcePerformance
Tests system resource usage and performance characteristics during typical operations.

**Tests:**
- `test_memory_usage_benchmark`: Memory consumption during workloads
- `test_cpu_usage_benchmark`: CPU usage during intensive operations
- `test_startup_time_benchmark`: Application startup time simulation

**Validates:**
- Memory usage stays within reasonable bounds
- CPU usage doesn't exceed 80% sustained
- Startup time meets NFR requirements

### TestEndToEndPerformance
Tests complete application workflows and processing pipelines.

**Tests:**
- `test_document_processing_pipeline_performance`: End-to-end document processing
- `test_search_and_retrieval_performance`: Search and retrieval operations

**Validates:**
- End-to-end processing performance
- Pipeline throughput and latency
- Complete workflow success rates

## Running the Benchmarks

### Quick Start

```bash
# Run all benchmarks with default settings
python tests/performance/run_local_development_benchmarks.py

# Run in quick mode (abbreviated test suite)
python tests/performance/run_local_development_benchmarks.py --quick-mode

# Skip resource-intensive tests
python tests/performance/run_local_development_benchmarks.py --skip-resource-tests
```

### Advanced Usage

```bash
# Run with custom configuration
python tests/performance/run_local_development_benchmarks.py \
    --config-file tests/performance/benchmark_config.json \
    --output-dir ./benchmark_results \
    --baseline-file aws_baseline.json

# Run in CI/CD mode with exit codes
python tests/performance/run_local_development_benchmarks.py \
    --ci-mode \
    --no-html \
    --timeout 900

# Run specific test classes only
python -m pytest tests/performance/test_local_development_benchmarks.py::TestDatabaseConnectionPerformance -v -s
```

### Using pytest directly

```bash
# Run all benchmark tests
python -m pytest tests/performance/test_local_development_benchmarks.py -v -s

# Run specific test categories
python -m pytest tests/performance/test_local_development_benchmarks.py::TestQueryPerformance -v -s

# Run with custom markers
python -m pytest tests/performance/test_local_development_benchmarks.py -m "not slow" -v -s
```

## Configuration

### Benchmark Configuration File

The `benchmark_config.json` file contains:

- **Performance Thresholds**: Maximum acceptable values for duration, memory, CPU usage
- **Test Suite Configuration**: Which tests to run in different modes
- **Database Configuration**: Connection parameters for local databases
- **Reporting Options**: Output format and detail level preferences

### Environment Variables

```bash
# Database connection settings
export ML_POSTGRES_HOST=localhost
export ML_NEO4J_HOST=localhost  
export ML_MILVUS_HOST=localhost

# Performance test settings
export BENCHMARK_TIMEOUT=1800
export BENCHMARK_QUICK_MODE=false
export BENCHMARK_SKIP_RESOURCE_TESTS=false
```

## Performance Thresholds

### Connection Establishment
- **Max Duration**: 5000ms
- **Min Throughput**: 1.0 ops/sec
- **Max Memory**: 100MB
- **Max CPU**: 50%
- **Min Success Rate**: 95%

### Simple Queries
- **Max Duration**: 100ms
- **Min Throughput**: 10.0 ops/sec
- **Max Memory**: 50MB
- **Max CPU**: 30%
- **Min Success Rate**: 99%

### Vector Search
- **Max Duration**: 500ms
- **Min Throughput**: 2.0 ops/sec
- **Max Memory**: 300MB
- **Max CPU**: 60%
- **Min Success Rate**: 98%

### Concurrent Operations
- **Max Duration**: 2000ms
- **Min Throughput**: 5.0 ops/sec
- **Max Memory**: 500MB
- **Max CPU**: 80%
- **Min Success Rate**: 90%

## Output and Reporting

### JSON Reports
Detailed benchmark results in JSON format including:
- Individual test results and timings
- Resource usage metrics
- NFR compliance validation
- Performance recommendations

### HTML Reports
Visual performance reports with:
- Executive summary and performance grade
- Test result tables and charts
- Resource usage graphs
- NFR compliance dashboard
- Optimization recommendations

### Console Output
Real-time progress and results during execution:
```
🚀 LOCAL DEVELOPMENT PERFORMANCE BENCHMARKS
============================================
📅 Started: 2024-01-24T10:30:00
📁 Output Directory: tests/performance/benchmark_reports
⚡ Quick Mode: No
🔧 Resource Tests: Included

📋 [1/4] DATABASE CONNECTION BENCHMARKS
   Testing connection establishment and pooling performance
--------------------------------------------------------------------------------
🔗 Testing PostgreSQL connection performance...
   ✓ 10/10 connections successful
   ✓ Total time: 1250.5ms
   ✓ Average per connection: 125.1ms
   ✓ Throughput: 8.0 connections/sec
```

## Integration with CI/CD

### Exit Codes
- **0**: All benchmarks passed, excellent performance
- **1**: Benchmarks passed with warnings, good performance
- **2**: Some benchmarks failed, performance issues detected
- **3**: Benchmark execution error

### GitHub Actions Integration
```yaml
- name: Run Performance Benchmarks
  run: |
    python tests/performance/run_local_development_benchmarks.py \
      --ci-mode \
      --quick-mode \
      --output-dir ./benchmark-results
  
- name: Upload Benchmark Results
  uses: actions/upload-artifact@v3
  with:
    name: benchmark-results
    path: ./benchmark-results/
```

## Troubleshooting

### Common Issues

**Connection Failures**
```bash
# Check if local services are running
docker-compose -f docker-compose.local.yml ps

# Restart services if needed
docker-compose -f docker-compose.local.yml restart
```

**Memory Issues**
```bash
# Check available memory
free -h

# Adjust Docker memory limits
docker system prune -f
```

**Timeout Issues**
```bash
# Increase timeout for slow systems
python run_local_development_benchmarks.py --timeout 3600
```

### Debug Mode
```bash
# Run with verbose logging
python -m pytest tests/performance/test_local_development_benchmarks.py -v -s --log-cli-level=DEBUG
```

## Performance Optimization Tips

### Database Optimization
1. **PostgreSQL**: Tune `shared_buffers`, `effective_cache_size`, and connection pooling
2. **Neo4j**: Adjust heap size and page cache settings
3. **Milvus**: Optimize index parameters and collection settings

### System Optimization
1. **Memory**: Ensure sufficient RAM (8GB+ recommended)
2. **CPU**: Use systems with multiple cores for concurrent operations
3. **Storage**: Use SSD storage for better I/O performance
4. **Network**: Ensure low-latency network for container communication

### Docker Optimization
1. **Resource Limits**: Set appropriate CPU and memory limits
2. **Volume Mounts**: Use named volumes for better performance
3. **Network**: Use custom networks for service isolation
4. **Image Optimization**: Use optimized base images

## Baseline Comparison

### AWS Baseline Data
When available, benchmarks can compare against AWS-native performance:

```json
{
  "aws_baseline": {
    "connection_establishment_ms": 120,
    "simple_query_ms": 45,
    "vector_search_ms": 280,
    "memory_usage_mb": 200,
    "cpu_usage_percent": 35
  }
}
```

### Acceptable Performance Degradation
- **Connection Time**: Within 20% of AWS baseline
- **Query Performance**: Within 20% of AWS baseline  
- **Resource Usage**: Within reasonable bounds for local development

## Contributing

### Adding New Benchmarks
1. Add test methods to appropriate test classes
2. Update performance thresholds in `benchmark_config.json`
3. Update documentation in this README
4. Ensure tests follow the established patterns

### Performance Threshold Updates
1. Update thresholds based on empirical testing
2. Consider different hardware configurations
3. Balance between performance and accessibility
4. Document rationale for threshold changes

## Related Documentation

- [Local Development Conversion Spec](../../.kiro/specs/local-development-conversion/)
- [Database Client Factory](../../src/multimodal_librarian/clients/database_client_factory.py)
- [Local Configuration](../../src/multimodal_librarian/config/local_config.py)
- [Docker Compose Setup](../../docker-compose.local.yml)