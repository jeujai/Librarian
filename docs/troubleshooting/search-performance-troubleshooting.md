# Search and Performance Troubleshooting Guide

## Overview

This guide focuses specifically on troubleshooting search functionality and performance issues in the Multimodal Librarian system. It covers the search service architecture, fallback mechanisms, and performance optimization strategies.

## Search Service Architecture

### Current Implementation
The system uses a dual-service architecture with automatic fallback:

```
Search Request → Search Manager → Complex Search Service (primary)
                               ↓ (on failure)
                               → Simple Search Service (fallback)
```

### Service Detection
```python
# Check which search service is active
curl http://localhost:8000/api/monitoring/metrics | jq '.search.service_type'

# Expected responses:
# "complex" - Complex search service active
# "simple" - Simple search service active (fallback mode)
```

## Common Search Issues

### 1. Search Service Fallback Activation

#### Issue: System automatically switches to simple search
**Symptoms:**
- Search responses include `"fallback_mode": true`
- Reduced search quality
- Missing advanced features (reranking, analytics)

**Diagnostic Steps:**
```bash
# Check search service status
curl http://localhost:8000/health/detailed | jq '.components.search_service'

# Check fallback statistics
curl http://localhost:8000/api/monitoring/metrics | jq '.search.fallback_rate'

# Check error logs for search failures
grep -i "search.*failed\|fallback" /var/log/multimodal-librarian/app.log | tail -20
```

**Common Causes:**

1. **Complex Search Import Failure**
   ```bash
   # Test complex search import
   python -c "
   import sys
   sys.path.insert(0, 'src')
   try:
       from multimodal_librarian.components.vector_store.search_service_complex import ComplexSearchService
       print('Complex search available')
   except ImportError as e:
       print(f'Complex search unavailable: {e}')
   "
   ```

2. **Vector Store Connection Issues**
   ```bash
   # Test vector store connectivity
   curl http://localhost:8000/health/detailed | jq '.components.vector_store'
   
   # For Milvus
   curl http://localhost:19121/health
   
   # For OpenSearch
   curl http://localhost:9200/_cluster/health
   ```

3. **Performance Threshold Exceeded**
   ```bash
   # Check search performance metrics
   curl http://localhost:8000/api/monitoring/metrics | jq '.search.avg_latency_ms'
   
   # If > 1000ms, fallback may activate
   ```

**Resolution Steps:**

1. **Reset Search Service**
   ```bash
   # Force search service reset
   curl -X POST http://localhost:8000/api/search/reset
   
   # Restart application if needed
   sudo systemctl restart multimodal-librarian
   ```

2. **Fix Vector Store Connection**
   ```bash
   # Restart vector store service
   sudo systemctl restart milvus-standalone
   # or
   sudo systemctl restart opensearch
   
   # Verify connectivity
   curl http://localhost:8000/health/detailed | jq '.components.vector_store.status'
   ```

3. **Clear Search Cache**
   ```bash
   # Clear search result cache
   curl -X DELETE http://localhost:8000/api/cache/search
   
   # Verify cache is cleared
   curl http://localhost:8000/api/monitoring/metrics | jq '.cache.size_mb'
   ```

### 2. Search Performance Issues

#### Issue: Slow search responses (>500ms)
**Symptoms:**
- Search takes longer than 500ms
- Timeout errors
- High CPU usage during searches

**Performance Benchmarking:**
```bash
# Test search performance
time curl -X POST http://localhost:8000/api/search \
  -H "Content-Type: application/json" \
  -d '{"query": "machine learning", "limit": 10}'

# Run multiple searches to get average
for i in {1..10}; do
  time curl -s -X POST http://localhost:8000/api/search \
    -H "Content-Type: application/json" \
    -d '{"query": "test query '$i'", "limit": 10}' > /dev/null
done
```

**Diagnostic Steps:**
```bash
# Check search performance metrics
curl http://localhost:8000/api/monitoring/metrics | jq '.search'

# Monitor resource usage during search
top -p $(pgrep -f multimodal-librarian)

# Check vector store performance
curl http://localhost:19121/metrics | grep -i latency  # Milvus
curl http://localhost:9200/_nodes/stats | jq '.nodes[].indices.search'  # OpenSearch
```

**Optimization Strategies:**

1. **Enable Search Result Caching**
   ```bash
   # Enable caching if not already enabled
   curl -X POST http://localhost:8000/api/search/cache/enable
   
   # Check cache hit rate
   curl http://localhost:8000/api/monitoring/metrics | jq '.search.cache_hit_rate'
   
   # Target: >70% cache hit rate
   ```

2. **Optimize Vector Store**
   ```bash
   # For Milvus - optimize collection
   curl -X POST http://localhost:8000/api/vector-store/optimize
   
   # For OpenSearch - force merge segments
   curl -X POST http://localhost:9200/_forcemerge?max_num_segments=1
   ```

3. **Tune Search Parameters**
   ```bash
   # Reduce search scope for better performance
   curl -X POST http://localhost:8000/api/search \
     -H "Content-Type: application/json" \
     -d '{
       "query": "test",
       "limit": 5,
       "similarity_threshold": 0.3,
       "options": {
         "enable_reranking": false,
         "enable_analytics": false
       }
     }'
   ```

#### Issue: Memory usage increases during searches
**Symptoms:**
- Memory usage grows with each search
- Out of memory errors
- Application becomes unresponsive

**Memory Profiling:**
```bash
# Check memory usage
curl http://localhost:8000/api/monitoring/metrics | jq '.resources.memory_usage_mb'

# Profile memory usage during search
python -m memory_profiler -c "
import requests
for i in range(10):
    requests.post('http://localhost:8000/api/search', 
                  json={'query': f'test {i}', 'limit': 10})
"
```

**Memory Optimization:**
```bash
# Enable memory optimization
curl -X POST http://localhost:8000/api/memory-optimization/enable

# Force garbage collection
curl -X POST http://localhost:8000/api/memory-optimization/gc

# Monitor memory usage
watch -n 5 'curl -s http://localhost:8000/api/monitoring/metrics | jq ".resources.memory_usage_mb"'
```

### 3. Search Quality Issues

#### Issue: Poor search results or empty responses
**Symptoms:**
- No results for valid queries
- Irrelevant results
- Low similarity scores

**Diagnostic Steps:**
```bash
# Check document count
curl http://localhost:8000/api/documents/ | jq '.total_count'

# Check if documents are processed
curl http://localhost:8000/api/analytics/documents | jq '.document_stats.total_processed'

# Test with simple query
curl -X POST http://localhost:8000/api/search \
  -H "Content-Type: application/json" \
  -d '{"query": "the", "limit": 5, "similarity_threshold": 0.0}'
```

**Common Causes:**

1. **No Documents Indexed**
   ```bash
   # Check processing status
   curl http://localhost:8000/api/documents/ | jq '.documents[] | select(.processing_status != "completed")'
   
   # Reprocess failed documents
   curl -X POST http://localhost:8000/api/documents/reprocess-failed
   ```

2. **High Similarity Threshold**
   ```bash
   # Test with lower threshold
   curl -X POST http://localhost:8000/api/search \
     -H "Content-Type: application/json" \
     -d '{"query": "your query", "similarity_threshold": 0.1}'
   ```

3. **Vector Store Index Issues**
   ```bash
   # Check vector store status
   curl http://localhost:8000/health/detailed | jq '.components.vector_store'
   
   # Rebuild index if needed
   curl -X POST http://localhost:8000/api/vector-store/rebuild-index
   ```

## Performance Optimization Guide

### 1. Search Result Caching

#### Simple Search Service Caching
The simple search service includes advanced caching:

```python
# Cache configuration
CACHE_SIZE = 1000  # Number of queries to cache
CACHE_TTL_SECONDS = 1800  # 30 minutes
AUTO_OPTIMIZE_ENABLED = True
```

**Cache Management:**
```bash
# Check cache statistics
curl http://localhost:8000/api/search/cache/stats

# Expected response:
{
  "total_entries": 150,
  "hit_rate": 0.72,
  "avg_access_count": 2.3,
  "cache_utilization": 0.15
}

# Clear cache if needed
curl -X DELETE http://localhost:8000/api/search/cache/clear

# Optimize cache settings
curl -X PUT http://localhost:8000/api/search/cache/config \
  -H "Content-Type: application/json" \
  -d '{
    "cache_size": 2000,
    "ttl_seconds": 3600,
    "auto_optimize": true
  }'
```

#### Multi-Level Caching Strategy
```bash
# L1 Cache (Memory) - fastest, smallest
# L2 Cache (Redis) - fast, distributed
# L3 Cache (Database) - slower, persistent

# Check cache levels
curl http://localhost:8000/api/cache/levels | jq '.'

# Expected response:
{
  "l1": {"hit_rate": 0.85, "size_mb": 64},
  "l2": {"hit_rate": 0.65, "size_mb": 256},
  "l3": {"hit_rate": 0.45, "size_mb": 1024}
}
```

### 2. Vector Operations Optimization

#### Batch Processing
```bash
# Enable batch processing for embeddings
curl -X POST http://localhost:8000/api/vector-store/batch-config \
  -H "Content-Type: application/json" \
  -d '{
    "batch_size": 100,
    "parallel_workers": 4,
    "enable_batching": true
  }'

# Monitor batch performance
curl http://localhost:8000/api/vector-store/batch-stats
```

#### Connection Pooling
```bash
# Configure vector store connection pool
curl -X PUT http://localhost:8000/api/vector-store/connection-pool \
  -H "Content-Type: application/json" \
  -d '{
    "pool_size": 10,
    "max_overflow": 20,
    "pool_timeout": 30
  }'

# Check pool status
curl http://localhost:8000/api/vector-store/connection-pool/status
```

### 3. Database Query Optimization

#### Query Performance Analysis
```bash
# Check slow queries
psql -c "
SELECT query, mean_time, calls, total_time 
FROM pg_stat_statements 
ORDER BY mean_time DESC 
LIMIT 10;
"

# Analyze specific query
psql -c "EXPLAIN ANALYZE SELECT * FROM documents WHERE title ILIKE '%search%';"
```

#### Index Optimization
```bash
# Check missing indexes
psql -c "
SELECT schemaname, tablename, attname, n_distinct, correlation 
FROM pg_stats 
WHERE schemaname = 'public' 
ORDER BY n_distinct DESC;
"

# Create indexes for common queries
psql -c "
CREATE INDEX CONCURRENTLY idx_documents_title_gin 
ON documents USING gin(to_tsvector('english', title));
"
```

### 4. Auto-Optimization Features

#### Simple Search Service Auto-Optimization
The simple search service includes automatic optimization:

```python
# Auto-optimization triggers
- Cache hit rate < 30% → Increase cache size
- Cache hit rate > 80% → Decrease cache size  
- High access frequency → Increase TTL
- Low access frequency → Decrease TTL
```

**Monitor Auto-Optimization:**
```bash
# Check optimization status
curl http://localhost:8000/api/search/optimization/status

# Expected response:
{
  "auto_optimize_enabled": true,
  "last_optimization": "2026-01-10T10:30:00Z",
  "optimization_count": 5,
  "current_settings": {
    "cache_size": 1200,
    "ttl_seconds": 2100
  }
}

# Force optimization
curl -X POST http://localhost:8000/api/search/optimization/trigger
```

## Monitoring and Alerting

### 1. Performance Monitoring
```bash
# Set up continuous monitoring
watch -n 10 'curl -s http://localhost:8000/api/monitoring/metrics | jq "{
  search_latency: .search.avg_latency_ms,
  cache_hit_rate: .search.cache_hit_rate,
  memory_usage: .resources.memory_usage_mb,
  fallback_rate: .search.fallback_rate
}"'
```

### 2. Alert Configuration
```bash
# Configure performance alerts
curl -X POST http://localhost:8000/api/monitoring/alerts \
  -H "Content-Type: application/json" \
  -d '{
    "search_latency_threshold_ms": 500,
    "cache_hit_rate_threshold": 0.7,
    "fallback_rate_threshold": 0.05,
    "memory_threshold_mb": 2048
  }'

# Test alert system
curl -X POST http://localhost:8000/api/monitoring/alerts/test
```

### 3. Performance Baselines
```bash
# Establish performance baselines
curl -X POST http://localhost:8000/api/monitoring/baseline/create

# Compare current performance to baseline
curl http://localhost:8000/api/monitoring/baseline/compare

# Expected response:
{
  "baseline_date": "2026-01-10T00:00:00Z",
  "current_performance": {
    "search_latency_ms": 245.7,
    "cache_hit_rate": 0.72,
    "memory_usage_mb": 1024.5
  },
  "baseline_performance": {
    "search_latency_ms": 230.5,
    "cache_hit_rate": 0.68,
    "memory_usage_mb": 980.2
  },
  "performance_delta": {
    "search_latency_change": "+6.6%",
    "cache_hit_rate_change": "+5.9%",
    "memory_usage_change": "+4.5%"
  }
}
```

## Emergency Procedures

### 1. Search Service Recovery
```bash
# Emergency search service restart
curl -X POST http://localhost:8000/api/search/emergency-restart

# Force fallback to simple search
curl -X POST http://localhost:8000/api/search/force-fallback

# Reset all search caches
curl -X DELETE http://localhost:8000/api/cache/search/all
```

### 2. Performance Recovery
```bash
# Emergency performance optimization
curl -X POST http://localhost:8000/api/performance/emergency-optimize

# Reduce system load
curl -X PUT http://localhost:8000/api/config/performance \
  -H "Content-Type: application/json" \
  -d '{
    "max_concurrent_searches": 5,
    "search_timeout_ms": 1000,
    "cache_aggressive_mode": true
  }'
```

### 3. Rollback Procedures
```bash
# Rollback to previous search configuration
curl -X POST http://localhost:8000/api/search/rollback

# Restore from backup
curl -X POST http://localhost:8000/api/search/restore \
  -H "Content-Type: application/json" \
  -d '{"backup_id": "backup_20260110_100000"}'
```

## Performance Testing Scripts

### 1. Load Testing
```bash
#!/bin/bash
# load_test_search.sh

echo "Starting search load test..."

# Test parameters
CONCURRENT_USERS=10
REQUESTS_PER_USER=50
BASE_URL="http://localhost:8000"

# Function to perform search
perform_search() {
    local user_id=$1
    local request_num=$2
    
    curl -s -w "%{time_total}\n" -o /dev/null \
        -X POST "$BASE_URL/api/search" \
        -H "Content-Type: application/json" \
        -d "{\"query\": \"test query $user_id $request_num\", \"limit\": 10}"
}

# Run concurrent searches
for user in $(seq 1 $CONCURRENT_USERS); do
    (
        for req in $(seq 1 $REQUESTS_PER_USER); do
            perform_search $user $req
        done
    ) &
done

wait
echo "Load test completed"
```

### 2. Performance Regression Testing
```bash
#!/bin/bash
# performance_regression_test.sh

echo "Running performance regression test..."

# Baseline performance test
echo "Establishing baseline..."
BASELINE=$(curl -s -w "%{time_total}" -o /dev/null \
    -X POST http://localhost:8000/api/search \
    -H "Content-Type: application/json" \
    -d '{"query": "performance test", "limit": 10}')

echo "Baseline response time: ${BASELINE}s"

# Run multiple tests
TOTAL_TIME=0
TEST_COUNT=20

for i in $(seq 1 $TEST_COUNT); do
    RESPONSE_TIME=$(curl -s -w "%{time_total}" -o /dev/null \
        -X POST http://localhost:8000/api/search \
        -H "Content-Type: application/json" \
        -d "{\"query\": \"test $i\", \"limit\": 10}")
    
    TOTAL_TIME=$(echo "$TOTAL_TIME + $RESPONSE_TIME" | bc)
done

AVERAGE_TIME=$(echo "scale=3; $TOTAL_TIME / $TEST_COUNT" | bc)
echo "Average response time: ${AVERAGE_TIME}s"

# Check for regression (>20% slower than baseline)
THRESHOLD=$(echo "scale=3; $BASELINE * 1.2" | bc)
if (( $(echo "$AVERAGE_TIME > $THRESHOLD" | bc -l) )); then
    echo "REGRESSION DETECTED: Average time ($AVERAGE_TIME) exceeds threshold ($THRESHOLD)"
    exit 1
else
    echo "Performance test PASSED"
fi
```

---

*This search and performance troubleshooting guide is maintained as part of the system documentation. Update when search architecture or performance characteristics change. Last updated: January 2026*