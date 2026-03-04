# Performance Tuning Guide

## Overview

This guide provides comprehensive performance tuning recommendations for the Multimodal Librarian system. It covers optimization strategies for all major components including search services, database operations, caching, and system resources.

## Performance Targets

### Response Time Targets
- **Search Operations**: < 500ms (95th percentile)
- **Document Upload**: < 2 minutes per MB
- **AI Chat Response**: < 3 seconds
- **Health Checks**: < 100ms
- **API Endpoints**: < 200ms (95th percentile)

### Throughput Targets
- **Concurrent Users**: 50+ simultaneous users
- **Search Requests**: 100+ searches per minute
- **Document Processing**: 10+ documents per minute
- **API Requests**: 1000+ requests per minute

### Resource Utilization Targets
- **Memory Usage**: < 2GB baseline, < 4GB peak
- **CPU Usage**: < 70% average, < 90% peak
- **Disk I/O**: < 80% utilization
- **Network I/O**: < 80% bandwidth utilization
- **Database Connections**: < 80% of pool size

## System Architecture Performance Considerations

### Component Performance Hierarchy
1. **Search Service Manager** - Primary performance bottleneck
2. **Vector Store Operations** - Secondary bottleneck
3. **Database Queries** - Tertiary bottleneck
4. **AI Service Calls** - External dependency
5. **Caching Layer** - Performance multiplier

### Performance Flow Analysis
```
User Request → Load Balancer → API Gateway → Search Manager → Vector Store
                                    ↓
                              Cache Layer ← Database ← AI Services
```

## Search Service Performance Tuning

### 1. Search Service Manager Optimization

#### Configuration Tuning
```python
# Optimal SearchServiceManager configuration
SEARCH_CONFIG = {
    "fallback_threshold": 3,          # Failures before fallback
    "health_check_interval": 30,      # Seconds between health checks
    "recovery_timeout": 300,          # Seconds before retry
    "max_concurrent_searches": 50,    # Concurrent search limit
    "search_timeout": 5000,           # Search timeout in ms
    "result_cache_ttl": 1800,         # Cache TTL in seconds
}
```

#### Performance Monitoring
```bash
# Monitor search performance
./scripts/monitor-search-performance.py --real-time

# Analyze search latency patterns
./scripts/analyze-search-latency.py --period=24h

# Check search service health
curl http://localhost:8000/health/search
```

### 2. Vector Store Optimization

#### Milvus Configuration Tuning
```yaml
# milvus.yaml optimization
server:
  address: 0.0.0.0
  port: 19530
  
etcd:
  endpoints:
    - etcd:2379
  
minio:
  address: minio
  port: 9000
  
# Performance optimizations
queryNode:
  cacheSize: 2048  # MB
  
indexNode:
  buildParallel: 4
  
dataNode:
  flushInsertBufferSize: 256  # MB
  
# Search performance
search:
  nprobe: 16
  searchTimeoutMs: 5000
```

#### Vector Operations Optimization
```python
# Optimize vector search parameters
VECTOR_SEARCH_CONFIG = {
    "nprobe": 16,                    # Search probe count
    "top_k": 10,                     # Results to return
    "search_timeout": 5000,          # Timeout in ms
    "batch_size": 100,               # Batch processing size
    "index_type": "IVF_FLAT",        # Index type for performance
    "metric_type": "L2",             # Distance metric
}

# Batch processing for better throughput
async def batch_vector_search(queries, batch_size=10):
    results = []
    for i in range(0, len(queries), batch_size):
        batch = queries[i:i + batch_size]
        batch_results = await vector_store.batch_search(batch)
        results.extend(batch_results)
    return results
```

### 3. Hybrid Search Optimization

#### Search Strategy Tuning
```python
# Optimal hybrid search configuration
HYBRID_SEARCH_CONFIG = {
    "vector_weight": 0.7,            # Vector search weight
    "keyword_weight": 0.3,           # Keyword search weight
    "min_score_threshold": 0.5,      # Minimum relevance score
    "max_results": 50,               # Maximum results to process
    "rerank_top_k": 20,              # Results to rerank
}
```

## Database Performance Tuning

### 1. PostgreSQL Optimization

#### Connection Pool Configuration
```python
# Optimal connection pool settings
DATABASE_CONFIG = {
    "pool_size": 20,                 # Base connection pool size
    "max_overflow": 30,              # Additional connections
    "pool_timeout": 30,              # Connection timeout
    "pool_recycle": 3600,            # Connection recycle time
    "pool_pre_ping": True,           # Validate connections
}
```

#### Query Optimization
```sql
-- Index optimization for common queries
CREATE INDEX CONCURRENTLY idx_documents_created_at ON documents(created_at);
CREATE INDEX CONCURRENTLY idx_documents_status ON documents(status);
CREATE INDEX CONCURRENTLY idx_search_queries_timestamp ON search_queries(timestamp);

-- Partial indexes for better performance
CREATE INDEX CONCURRENTLY idx_documents_active 
ON documents(id) WHERE status = 'active';

-- Composite indexes for complex queries
CREATE INDEX CONCURRENTLY idx_documents_user_status 
ON documents(user_id, status, created_at);
```

#### Database Configuration Tuning
```postgresql
# postgresql.conf optimizations
shared_buffers = 256MB              # 25% of RAM
effective_cache_size = 1GB          # 75% of RAM
work_mem = 4MB                      # Per-operation memory
maintenance_work_mem = 64MB         # Maintenance operations
checkpoint_completion_target = 0.9   # Checkpoint spread
wal_buffers = 16MB                  # WAL buffer size
random_page_cost = 1.1              # SSD optimization
effective_io_concurrency = 200      # Concurrent I/O
```

### 2. Query Performance Optimization

#### Slow Query Analysis
```bash
# Enable slow query logging
echo "log_min_duration_statement = 1000" >> postgresql.conf

# Analyze slow queries
./scripts/analyze-slow-queries.py --threshold=1000ms

# Generate query optimization recommendations
./scripts/optimize-database-queries.py
```

#### Query Optimization Techniques
```python
# Use prepared statements
async def optimized_search_query(query_text, limit=10):
    stmt = await conn.prepare("""
        SELECT id, title, content, score
        FROM documents 
        WHERE to_tsvector('english', content) @@ plainto_tsquery($1)
        ORDER BY ts_rank(to_tsvector('english', content), plainto_tsquery($1)) DESC
        LIMIT $2
    """)
    return await stmt.fetch(query_text, limit)

# Use connection pooling
from sqlalchemy.pool import QueuePool
engine = create_async_engine(
    DATABASE_URL,
    poolclass=QueuePool,
    pool_size=20,
    max_overflow=30,
    pool_pre_ping=True
)
```

## Caching Performance Tuning

### 1. Multi-Level Cache Optimization

#### Cache Configuration
```python
# Optimal cache configuration
CACHE_CONFIG = {
    "l1_cache": {
        "type": "memory",
        "size": 1000,               # Number of items
        "ttl": 300,                 # 5 minutes
    },
    "l2_cache": {
        "type": "redis",
        "host": "redis",
        "port": 6379,
        "db": 0,
        "ttl": 1800,                # 30 minutes
        "max_connections": 50,
    },
    "l3_cache": {
        "type": "database",
        "ttl": 3600,                # 1 hour
    }
}
```

#### Cache Strategy Optimization
```python
# Implement cache warming
async def warm_cache():
    # Pre-load frequently accessed data
    popular_queries = await get_popular_queries(limit=100)
    for query in popular_queries:
        await cache_manager.warm_cache(query)

# Implement intelligent cache invalidation
async def smart_cache_invalidation(document_id):
    # Find related cache entries
    related_keys = await find_related_cache_keys(document_id)
    
    # Invalidate in batches
    for batch in batch_keys(related_keys, batch_size=10):
        await cache_manager.delete_batch(batch)
```

### 2. Redis Optimization

#### Redis Configuration
```redis
# redis.conf optimizations
maxmemory 1gb
maxmemory-policy allkeys-lru
save 900 1
save 300 10
save 60 10000

# Network optimizations
tcp-keepalive 300
timeout 0

# Performance optimizations
hash-max-ziplist-entries 512
hash-max-ziplist-value 64
list-max-ziplist-size -2
set-max-intset-entries 512
```

#### Cache Hit Rate Optimization
```python
# Monitor cache performance
async def monitor_cache_performance():
    stats = await cache_manager.get_stats()
    hit_rate = stats['hits'] / (stats['hits'] + stats['misses'])
    
    if hit_rate < 0.7:  # Target 70% hit rate
        await optimize_cache_strategy()

# Optimize cache keys
def generate_cache_key(query, filters=None):
    # Create consistent, hierarchical cache keys
    key_parts = [
        "search",
        hashlib.md5(query.encode()).hexdigest()[:8],
        str(sorted(filters.items())) if filters else "no_filters"
    ]
    return ":".join(key_parts)
```

## Application Performance Tuning

### 1. FastAPI Optimization

#### Application Configuration
```python
# Optimal FastAPI configuration
app = FastAPI(
    title="Multimodal Librarian",
    docs_url="/docs" if DEBUG else None,  # Disable docs in production
    redoc_url=None,                       # Disable redoc
    openapi_url="/openapi.json" if DEBUG else None,
)

# Add performance middleware
app.add_middleware(
    GZipMiddleware,
    minimum_size=1000
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)
```

#### Async Optimization
```python
# Use async/await properly
async def optimized_search_endpoint(query: SearchQuery):
    # Parallel execution for independent operations
    search_task = asyncio.create_task(search_service.search(query))
    cache_task = asyncio.create_task(cache_service.get(query.cache_key))
    
    # Wait for both operations
    search_result, cached_result = await asyncio.gather(
        search_task, cache_task, return_exceptions=True
    )
    
    return process_results(search_result, cached_result)
```

### 2. Memory Management

#### Memory Optimization
```python
# Implement memory monitoring
import psutil
import gc

async def monitor_memory_usage():
    process = psutil.Process()
    memory_info = process.memory_info()
    
    if memory_info.rss > MAX_MEMORY_USAGE:
        # Force garbage collection
        gc.collect()
        
        # Clear caches if needed
        await cache_manager.clear_expired()

# Use memory-efficient data structures
from collections import deque
from weakref import WeakValueDictionary

# Use weak references for temporary objects
temp_objects = WeakValueDictionary()

# Use deque for fixed-size collections
recent_queries = deque(maxlen=1000)
```

### 3. CPU Optimization

#### CPU Usage Optimization
```python
# Use process pools for CPU-intensive tasks
from concurrent.futures import ProcessPoolExecutor
import multiprocessing

# Configure process pool
cpu_count = multiprocessing.cpu_count()
process_pool = ProcessPoolExecutor(max_workers=cpu_count - 1)

# Offload CPU-intensive operations
async def process_document_async(document):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        process_pool, 
        cpu_intensive_processing, 
        document
    )
```

## System Resource Optimization

### 1. Operating System Tuning

#### Linux Kernel Parameters
```bash
# /etc/sysctl.conf optimizations
# Network optimizations
net.core.somaxconn = 65535
net.core.netdev_max_backlog = 5000
net.ipv4.tcp_max_syn_backlog = 65535
net.ipv4.tcp_keepalive_time = 600

# Memory optimizations
vm.swappiness = 10
vm.dirty_ratio = 15
vm.dirty_background_ratio = 5

# File system optimizations
fs.file-max = 2097152
```

#### File System Optimization
```bash
# Mount options for performance
/dev/sda1 /data ext4 noatime,nodiratime,data=writeback 0 0

# I/O scheduler optimization
echo mq-deadline > /sys/block/sda/queue/scheduler
```

### 2. Container Optimization

#### Docker Configuration
```dockerfile
# Multi-stage build for smaller images
FROM python:3.9-slim as builder
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

FROM python:3.9-slim
WORKDIR /app
COPY --from=builder /usr/local/lib/python3.9/site-packages /usr/local/lib/python3.9/site-packages
COPY . .

# Optimize for production
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
```

#### Docker Compose Optimization
```yaml
version: '3.8'
services:
  app:
    image: multimodal-librarian:latest
    deploy:
      resources:
        limits:
          cpus: '2.0'
          memory: 4G
        reservations:
          cpus: '1.0'
          memory: 2G
    environment:
      - WORKERS=4
      - WORKER_CLASS=uvicorn.workers.UvicornWorker
```

## Monitoring and Profiling

### 1. Performance Monitoring

#### Application Metrics
```python
# Implement custom metrics
from prometheus_client import Counter, Histogram, Gauge

# Define metrics
search_requests = Counter('search_requests_total', 'Total search requests')
search_duration = Histogram('search_duration_seconds', 'Search duration')
active_connections = Gauge('active_connections', 'Active connections')

# Use metrics in code
@search_duration.time()
async def timed_search(query):
    search_requests.inc()
    return await search_service.search(query)
```

#### System Monitoring
```bash
# Monitor system performance
./scripts/monitor-system-performance.py --interval=60

# Generate performance reports
./scripts/generate-performance-report.py --period=24h

# Set up automated alerts
./scripts/setup-performance-alerts.py
```

### 2. Profiling and Debugging

#### Application Profiling
```python
# Use cProfile for performance profiling
import cProfile
import pstats

def profile_function(func):
    def wrapper(*args, **kwargs):
        pr = cProfile.Profile()
        pr.enable()
        result = func(*args, **kwargs)
        pr.disable()
        
        stats = pstats.Stats(pr)
        stats.sort_stats('cumulative')
        stats.print_stats(10)  # Top 10 functions
        
        return result
    return wrapper

# Profile critical functions
@profile_function
async def critical_search_function(query):
    return await search_service.search(query)
```

#### Memory Profiling
```python
# Use memory_profiler for memory analysis
from memory_profiler import profile

@profile
def memory_intensive_function():
    # Function implementation
    pass

# Monitor memory usage over time
./scripts/monitor-memory-usage.py --interval=300
```

## Performance Testing

### 1. Load Testing

#### Load Test Configuration
```python
# locustfile.py for load testing
from locust import HttpUser, task, between

class SearchUser(HttpUser):
    wait_time = between(1, 3)
    
    @task(3)
    def search_documents(self):
        self.client.post("/search", json={
            "query": "test query",
            "limit": 10
        })
    
    @task(1)
    def health_check(self):
        self.client.get("/health")
```

#### Performance Benchmarking
```bash
# Run load tests
locust -f locustfile.py --host=http://localhost:8000 -u 50 -r 5 -t 300s

# Run specific performance tests
./scripts/run-performance-tests.py --concurrent-users=50 --duration=300

# Generate performance baseline
./scripts/generate-performance-baseline.py
```

### 2. Stress Testing

#### Stress Test Scenarios
```bash
# CPU stress test
./scripts/stress-test-cpu.py --duration=300

# Memory stress test
./scripts/stress-test-memory.py --max-memory=3GB

# I/O stress test
./scripts/stress-test-io.py --duration=300

# Network stress test
./scripts/stress-test-network.py --connections=1000
```

## Performance Optimization Checklist

### Daily Performance Checks
- [ ] Monitor response times
- [ ] Check error rates
- [ ] Verify cache hit rates
- [ ] Monitor resource usage
- [ ] Review performance alerts

### Weekly Performance Reviews
- [ ] Analyze performance trends
- [ ] Review slow queries
- [ ] Optimize cache strategies
- [ ] Update performance baselines
- [ ] Plan performance improvements

### Monthly Performance Audits
- [ ] Comprehensive performance testing
- [ ] Resource capacity planning
- [ ] Performance optimization implementation
- [ ] Performance documentation updates
- [ ] Team performance training

## Troubleshooting Performance Issues

### Common Performance Problems

#### High Response Times
1. Check database query performance
2. Verify cache hit rates
3. Monitor CPU and memory usage
4. Review network latency
5. Analyze application bottlenecks

#### High Memory Usage
1. Check for memory leaks
2. Review cache sizes
3. Monitor garbage collection
4. Analyze object retention
5. Optimize data structures

#### High CPU Usage
1. Profile CPU-intensive functions
2. Optimize algorithms
3. Use async/await properly
4. Implement caching
5. Scale horizontally

#### Database Performance Issues
1. Analyze slow queries
2. Check index usage
3. Monitor connection pools
4. Review database configuration
5. Optimize query patterns

## Performance Optimization Tools

### Monitoring Tools
- **Prometheus + Grafana**: Metrics collection and visualization
- **New Relic**: Application performance monitoring
- **DataDog**: Infrastructure and application monitoring
- **Sentry**: Error tracking and performance monitoring

### Profiling Tools
- **cProfile**: Python code profiling
- **py-spy**: Sampling profiler for Python
- **memory_profiler**: Memory usage profiling
- **line_profiler**: Line-by-line profiling

### Load Testing Tools
- **Locust**: Python-based load testing
- **Apache JMeter**: Java-based load testing
- **Artillery**: Node.js load testing
- **k6**: JavaScript load testing

### Database Tools
- **pg_stat_statements**: PostgreSQL query statistics
- **EXPLAIN ANALYZE**: Query execution analysis
- **pgBadger**: PostgreSQL log analyzer
- **pg_top**: Real-time PostgreSQL monitoring

---

**Document Version**: 1.0  
**Last Updated**: $(date)  
**Next Review**: $(date -d "+3 months")  
**Performance Baseline**: Available in monitoring dashboard