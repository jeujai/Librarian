# Local Development Performance Tuning Guide

## Overview

This guide provides comprehensive performance tuning strategies specifically for the local development conversion of the Multimodal Librarian application. It focuses on meeting the performance requirements defined in the local-development-conversion specification:

- **Memory usage**: < 8GB total for all services
- **Query performance**: Within 20% of AWS setup
- **Startup time**: < 2 minutes for local setup
- **CPU usage**: Reasonable on development machines

## Performance Requirements Summary

| Component | Memory Target | Performance Target | Startup Target |
|-----------|---------------|-------------------|----------------|
| PostgreSQL | ~1GB | Within 20% of AWS RDS | < 30s |
| Neo4j | ~1.5GB | Within 20% of AWS Neptune | < 90s |
| Milvus | ~2GB | Within 20% of AWS OpenSearch | < 60s |
| Application | ~2GB | Comparable to production | < 30s |
| Admin Tools | ~1.5GB | Development-optimized | < 60s |
| **Total** | **< 8GB** | **< 2 minutes** | **Production-comparable** |

## System-Level Performance Tuning

### Docker Engine Optimization

#### Docker Daemon Configuration

```json
// ~/.docker/daemon.json
{
  "storage-driver": "overlay2",
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "10m",
    "max-file": "3"
  },
  "default-ulimits": {
    "memlock": {
      "Hard": -1,
      "Name": "memlock", 
      "Soft": -1
    }
  },
  "experimental": false,
  "features": {
    "buildkit": true
  },
  "max-concurrent-downloads": 6,
  "max-concurrent-uploads": 5
}
```

#### Container Resource Limits

```yaml
# docker-compose.local.yml - Optimized resource allocation
services:
  postgres:
    deploy:
      resources:
        limits:
          memory: 1G
          cpus: '1.0'
        reservations:
          memory: 512M
          cpus: '0.5'
  neo4j:
    deploy:
      resources:
        limits:
          memory: 1.5G
          cpus: '1.5'
        reservations:
          memory: 1G
          cpus: '0.5'

  milvus:
    deploy:
      resources:
        limits:
          memory: 2G
          cpus: '2.0'
        reservations:
          memory: 1G
          cpus: '0.5'

  multimodal-librarian:
    deploy:
      resources:
        limits:
          memory: 2G
          cpus: '2.0'
        reservations:
          memory: 1G
          cpus: '1.0'
```

### Host System Optimization

#### Memory Management

```bash
# Increase vm.max_map_count for Milvus/Elasticsearch
echo 'vm.max_map_count=262144' | sudo tee -a /etc/sysctl.conf
sudo sysctl -p

# Optimize swappiness for development
echo 'vm.swappiness=10' | sudo tee -a /etc/sysctl.conf

# Increase file descriptor limits
echo '* soft nofile 65536' | sudo tee -a /etc/security/limits.conf
echo '* hard nofile 65536' | sudo tee -a /etc/security/limits.conf
```

#### CPU Optimization

```bash
# Set CPU governor to performance (if needed)
echo 'performance' | sudo tee /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor

# Disable CPU frequency scaling for consistent performance
echo 'performance' | sudo tee /sys/devices/system/cpu/cpufreq/policy*/scaling_governor
```

## Database Performance Tuning

### PostgreSQL Optimization

#### Memory Configuration
```sql
-- Optimized for 1GB memory allocation
shared_buffers = 256MB                    -- 25% of allocated memory
work_mem = 8MB                           -- Increased for better sort performance
maintenance_work_mem = 128MB             -- For VACUUM, CREATE INDEX
autovacuum_work_mem = 64MB              -- Separate autovacuum memory
effective_cache_size = 1GB              -- OS cache estimate
```

#### Query Optimization
```sql
-- SSD-optimized settings
random_page_cost = 2.0                  -- Reduced from 4.0 for SSD
seq_page_cost = 1.0                     -- Sequential read cost
cpu_tuple_cost = 0.01                   -- CPU processing cost
cpu_index_tuple_cost = 0.005            -- Index CPU cost
cpu_operator_cost = 0.0025              -- Operator CPU cost
```

#### Connection and Concurrency
```sql
max_connections = 100                    -- Reasonable for development
max_parallel_workers_per_gather = 2     -- Limit parallel workers
max_parallel_maintenance_workers = 2    -- Maintenance parallelism
max_parallel_workers = 4                -- Total parallel workers
```

#### Docker Compose Configuration
```yaml
postgres:
  environment:
    # Performance tuning for development
    - POSTGRES_SHARED_PRELOAD_LIBRARIES=pg_stat_statements
    - POSTGRES_MAX_CONNECTIONS=100
    - POSTGRES_SHARED_BUFFERS=256MB
    - POSTGRES_EFFECTIVE_CACHE_SIZE=1GB
  command: >
    postgres
    -c shared_preload_libraries=pg_stat_statements
    -c max_connections=100
    -c shared_buffers=256MB
    -c effective_cache_size=1GB
    -c maintenance_work_mem=64MB
    -c checkpoint_completion_target=0.9
    -c wal_buffers=16MB
    -c default_statistics_target=100
```

### Neo4j Performance Tuning

#### Memory Configuration
```yaml
# Heap memory (JVM)
- NEO4J_server_memory_heap_initial__size=512m
- NEO4J_server_memory_heap_max__size=1G

# Page cache (graph data)
- NEO4J_server_memory_pagecache_size=512m

# Off-heap memory
- NEO4J_server_memory_off__heap_max__size=256m
```

#### Query Performance
```yaml
# Query optimization
- NEO4J_cypher_default__language__version=5
- NEO4J_cypher_runtime=parallel
- NEO4J_cypher_planner=cost

# Cache configuration
- NEO4J_dbms_query__cache__size=1000
- NEO4J_cypher_query__plan__cache__size=1000
```

#### Transaction Optimization
```yaml
# Transaction settings
- NEO4J_db_tx__log_rotation_retention__policy=1G size
- NEO4J_db_tx__log_rotation_size=100M
- NEO4J_dbms_transaction_timeout=60s
```

#### Docker Compose Configuration
```yaml
neo4j:
  environment:
    # Memory settings for development
    - NEO4J_dbms_memory_heap_initial__size=512m
    - NEO4J_dbms_memory_heap_max__size=1G
    - NEO4J_dbms_memory_pagecache_size=512m
    - NEO4J_dbms_tx__log_rotation_retention__policy=1G size
```

### Milvus Performance Tuning

#### Index Optimization
```python
# Automatic index selection based on collection size
def get_optimal_index_config(vector_count: int, dimension: int) -> dict:
    if vector_count < 10000:
        return {"index_type": "FLAT", "metric_type": "L2"}
    elif vector_count < 100000:
        return {
            "index_type": "IVF_FLAT",
            "metric_type": "L2",
            "params": {"nlist": min(4096, vector_count // 39)}
        }
    else:
        return {
            "index_type": "HNSW",
            "metric_type": "L2",
            "params": {"M": 16, "efConstruction": 200}
        }
```

#### Search Parameter Optimization
```python
# Dynamic search parameters
def get_optimal_search_params(index_type: str, k: int, vector_count: int) -> dict:
    if index_type == "IVF_FLAT":
        nprobe = min(max(k * 2, 10), vector_count // 1000)
        return {"nprobe": nprobe}
    elif index_type == "HNSW":
        ef = max(k * 8, 64)
        return {"ef": ef}
    return {}
```

#### Docker Compose Configuration
```yaml
milvus:
  environment:
    # Milvus performance tuning
    - MILVUS_QUERY_NODE_GRACEFUL_TIME=10
    - MILVUS_QUERY_NODE_STATS_TASK_DELAY_EXECUTE=10
```

## Application Performance Tuning

### FastAPI Optimization

#### Application Configuration
```python
# main.py optimizations
app = FastAPI(
    title="Multimodal Librarian",
    docs_url="/docs" if settings.environment == "local" else None,
    redoc_url="/redoc" if settings.environment == "local" else None,
    openapi_url="/openapi.json" if settings.environment == "local" else None,
)

# Optimize middleware order
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.environment == "local" else settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

#### Connection Pooling
```python
# Connection pool configuration
DATABASE_POOL_CONFIG = {
    "postgresql": {
        "min_size": 5,
        "max_size": 20,
        "max_queries": 50000,
        "max_inactive_connection_lifetime": 300.0,
        "timeout": 60.0,
    },
    "neo4j": {
        "max_connection_lifetime": 30 * 60,  # 30 minutes
        "max_connection_pool_size": 50,
        "connection_acquisition_timeout": 60,
        "keep_alive": True,
    },
    "milvus": {
        "pool_size": 10,
        "timeout": 60,
        "retry_on_failure": True,
        "max_retry_attempts": 3,
    }
}
```

### Startup Optimization

#### Service Startup Orchestration
```yaml
# docker-compose.local.yml health check optimization
services:
  postgres:
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ml_user -d multimodal_librarian"]
      interval: 5s
      timeout: 3s
      retries: 5
      start_period: 10s

  neo4j:
    healthcheck:
      test: ["CMD-SHELL", "cypher-shell -u neo4j -p ml_password 'RETURN 1'"]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 30s

  milvus:
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:9091/healthz"]
      interval: 15s
      timeout: 10s
      retries: 3
      start_period: 45s
```

#### Parallel Service Initialization
```bash
#!/bin/bash
# scripts/optimized-startup.sh

# Start infrastructure services in parallel
docker-compose -f docker-compose.local.yml up -d etcd minio &
INFRA_PID=$!

# Start databases in dependency order
docker-compose -f docker-compose.local.yml up -d postgres &
POSTGRES_PID=$!

# Wait for infrastructure
wait $INFRA_PID

# Start Milvus (depends on etcd/minio)
docker-compose -f docker-compose.local.yml up -d milvus &
MILVUS_PID=$!

# Start Neo4j (independent)
docker-compose -f docker-compose.local.yml up -d neo4j &
NEO4J_PID=$!

# Wait for all databases
wait $POSTGRES_PID $MILVUS_PID $NEO4J_PID

# Start application
docker-compose -f docker-compose.local.yml up -d multimodal-librarian

# Start admin tools
docker-compose -f docker-compose.local.yml up -d pgadmin attu
```

#### Progressive Model Loading
```python
# Load models progressively based on priority
LOADING_PRIORITIES = {
    "essential": ["sentence_transformer", "basic_nlp"],
    "important": ["advanced_nlp", "image_processor"],
    "optional": ["specialized_models", "analytics_models"]
}

async def progressive_model_loading():
    # Load essential models first (blocking)
    await load_models(LOADING_PRIORITIES["essential"])
    
    # Load important models in background
    asyncio.create_task(load_models(LOADING_PRIORITIES["important"]))
    
    # Load optional models when system is idle
    asyncio.create_task(load_models_when_idle(LOADING_PRIORITIES["optional"]))
```

## Performance Monitoring and Optimization

### Real-time Performance Monitoring

#### System Resource Monitoring
```python
# Performance monitoring service
class PerformanceMonitor:
    def __init__(self):
        self.metrics = {}
        self.thresholds = {
            "memory_usage_percent": 80,
            "cpu_usage_percent": 70,
            "disk_usage_percent": 85,
            "query_latency_ms": 100,
        }
    
    async def collect_metrics(self):
        return {
            "system": await self.get_system_metrics(),
            "docker": await self.get_docker_metrics(),
            "database": await self.get_database_metrics(),
            "application": await self.get_application_metrics(),
        }
    
    async def check_performance_alerts(self):
        metrics = await self.collect_metrics()
        alerts = []
        
        for metric, threshold in self.thresholds.items():
            if metrics.get(metric, 0) > threshold:
                alerts.append({
                    "metric": metric,
                    "value": metrics[metric],
                    "threshold": threshold,
                    "severity": "warning" if metrics[metric] < threshold * 1.2 else "critical"
                })
        
        return alerts
```

#### Database Performance Monitoring
```python
# Database-specific performance monitoring
async def monitor_database_performance():
    postgres_stats = await get_postgres_performance_stats()
    neo4j_stats = await get_neo4j_performance_stats()
    milvus_stats = await get_milvus_performance_stats()
    
    return {
        "postgresql": {
            "query_latency_avg": postgres_stats["avg_query_time"],
            "connection_count": postgres_stats["active_connections"],
            "buffer_hit_ratio": postgres_stats["buffer_hit_ratio"],
            "memory_usage": postgres_stats["memory_usage_mb"],
        },
        "neo4j": {
            "query_latency_avg": neo4j_stats["avg_query_time"],
            "memory_usage": neo4j_stats["heap_usage_mb"],
            "page_cache_hit_ratio": neo4j_stats["page_cache_hit_ratio"],
            "transaction_count": neo4j_stats["active_transactions"],
        },
        "milvus": {
            "search_latency_avg": milvus_stats["avg_search_time"],
            "memory_usage": milvus_stats["memory_usage_mb"],
            "index_efficiency": milvus_stats["index_efficiency"],
            "collection_count": milvus_stats["collection_count"],
        }
    }
```

### Automated Performance Optimization

#### Dynamic Resource Allocation
```python
# Automatic resource optimization based on usage patterns
class ResourceOptimizer:
    def __init__(self):
        self.usage_history = []
        self.optimization_rules = {
            "high_memory_usage": self.optimize_memory_usage,
            "high_cpu_usage": self.optimize_cpu_usage,
            "slow_queries": self.optimize_query_performance,
            "high_startup_time": self.optimize_startup_performance,
        }
    
    async def optimize_performance(self):
        current_metrics = await self.collect_current_metrics()
        issues = await self.identify_performance_issues(current_metrics)
        
        for issue in issues:
            if issue["type"] in self.optimization_rules:
                await self.optimization_rules[issue["type"]](issue)
    
    async def optimize_memory_usage(self, issue):
        # Reduce cache sizes, optimize connection pools
        if issue["component"] == "postgresql":
            await self.reduce_postgres_memory_usage()
        elif issue["component"] == "neo4j":
            await self.reduce_neo4j_memory_usage()
        elif issue["component"] == "milvus":
            await self.optimize_milvus_memory_usage()
```

## Performance Benchmarking

### Automated Performance Testing

#### Benchmark Suite
```python
# Performance benchmark suite
class PerformanceBenchmark:
    def __init__(self):
        self.benchmarks = {
            "database_operations": self.benchmark_database_operations,
            "search_performance": self.benchmark_search_performance,
            "api_endpoints": self.benchmark_api_endpoints,
            "system_resources": self.benchmark_system_resources,
        }
    
    async def run_full_benchmark(self):
        results = {}
        for name, benchmark in self.benchmarks.items():
            print(f"Running {name} benchmark...")
            results[name] = await benchmark()
        
        return self.generate_benchmark_report(results)
    
    async def benchmark_database_operations(self):
        # Test database query performance
        start_time = time.time()
        
        # PostgreSQL operations
        postgres_results = await self.test_postgres_operations()
        
        # Neo4j operations
        neo4j_results = await self.test_neo4j_operations()
        
        # Milvus operations
        milvus_results = await self.test_milvus_operations()
        
        total_time = time.time() - start_time
        
        return {
            "total_time": total_time,
            "postgresql": postgres_results,
            "neo4j": neo4j_results,
            "milvus": milvus_results,
        }
```

#### Performance Regression Testing
```python
# Automated performance regression detection
class PerformanceRegressionDetector:
    def __init__(self):
        self.baseline_file = "performance_baseline.json"
        self.regression_threshold = 0.2  # 20% performance degradation
    
    async def check_for_regressions(self, current_results):
        baseline = self.load_baseline()
        regressions = []
        
        for metric, current_value in current_results.items():
            if metric in baseline:
                baseline_value = baseline[metric]
                if current_value > baseline_value * (1 + self.regression_threshold):
                    regressions.append({
                        "metric": metric,
                        "baseline": baseline_value,
                        "current": current_value,
                        "degradation_percent": ((current_value - baseline_value) / baseline_value) * 100
                    })
        
        return regressions
```

## Troubleshooting Performance Issues

### Common Performance Problems

#### High Memory Usage
```bash
# Diagnose memory issues
docker stats --format "table {{.Container}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.MemPerc}}"

# Check individual service memory
docker exec postgres ps aux --sort=-%mem | head -10
docker exec neo4j ps aux --sort=-%mem | head -10
docker exec milvus ps aux --sort=-%mem | head -10
```

**Solutions:**
1. Reduce database cache sizes
2. Optimize connection pool sizes
3. Implement memory-efficient algorithms
4. Use streaming for large data processing

#### Slow Query Performance
```bash
# PostgreSQL slow query analysis
docker exec postgres psql -U ml_user -d multimodal_librarian -c "
SELECT query, mean_exec_time, calls, total_exec_time 
FROM pg_stat_statements 
ORDER BY mean_exec_time DESC 
LIMIT 10;"

# Neo4j query profiling
docker exec neo4j cypher-shell -u neo4j -p ml_password "
PROFILE MATCH (n) RETURN count(n);"

# Milvus search performance
python scripts/benchmark-milvus-search.py
```

**Solutions:**
1. Add database indexes
2. Optimize query structure
3. Use query caching
4. Implement connection pooling

#### High CPU Usage
```bash
# Monitor CPU usage by service
docker stats --format "table {{.Container}}\t{{.CPUPerc}}\t{{.PIDs}}"

# Profile application CPU usage
python -m cProfile -o profile.stats scripts/performance-test.py
```

**Solutions:**
1. Optimize CPU-intensive algorithms
2. Use async operations
3. Implement caching
4. Reduce container CPU limits

### Performance Optimization Tools

#### Makefile Commands
```makefile
# Performance optimization commands
.PHONY: perf-optimize perf-test perf-monitor perf-benchmark

perf-optimize:
	@echo "Running performance optimization..."
	python scripts/optimize-local-performance.py
	docker-compose -f docker-compose.local.yml restart

perf-test:
	@echo "Running performance tests..."
	pytest tests/performance/ -v --benchmark-only

perf-monitor:
	@echo "Starting performance monitoring..."
	python scripts/monitor-local-performance.py

perf-benchmark:
	@echo "Running performance benchmark..."
	python scripts/run-performance-benchmark.py
```

#### Automated Optimization Scripts
```bash
#!/bin/bash
# scripts/auto-optimize-performance.sh

echo "Starting automated performance optimization..."

# Check current performance
python scripts/check-performance-metrics.py > /tmp/current_metrics.json

# Identify bottlenecks
python scripts/identify-performance-bottlenecks.py /tmp/current_metrics.json

# Apply optimizations
python scripts/apply-performance-optimizations.py

# Restart services if needed
if [ "$RESTART_REQUIRED" = "true" ]; then
    docker-compose -f docker-compose.local.yml restart
fi

# Verify improvements
python scripts/verify-performance-improvements.py

echo "Performance optimization completed!"
```

## Best Practices

### Development Workflow
1. **Monitor regularly**: Use performance monitoring tools daily
2. **Optimize incrementally**: Make small, measurable improvements
3. **Test thoroughly**: Validate optimizations with benchmarks
4. **Document changes**: Keep track of optimization decisions
5. **Profile before optimizing**: Identify actual bottlenecks

### Resource Management
1. **Set appropriate limits**: Use Docker resource constraints
2. **Monitor resource usage**: Track memory, CPU, and disk usage
3. **Optimize for development**: Balance performance with resource usage
4. **Clean up regularly**: Remove unused containers and volumes

### Performance Testing
1. **Establish baselines**: Measure performance before changes
2. **Test realistic scenarios**: Use representative data and queries
3. **Automate testing**: Include performance tests in CI/CD
4. **Monitor trends**: Track performance over time

## Configuration Templates

### Optimized Docker Compose Configuration

```yaml
# docker-compose.local.yml - Complete optimized configuration
version: '3.8'

services:
  # Application
  multimodal-librarian:
    build: .
    ports:
      - "8000:8000"
    environment:
      - DATABASE_TYPE=local
      - POSTGRES_HOST=postgres
      - NEO4J_HOST=neo4j
      - MILVUS_HOST=milvus
    depends_on:
      postgres:
        condition: service_healthy
      neo4j:
        condition: service_healthy
      milvus:
        condition: service_healthy
    volumes:
      - ./uploads:/app/uploads
      - ./logs:/app/logs
    deploy:
      resources:
        limits:
          memory: 2G
          cpus: '2.0'
        reservations:
          memory: 1G
          cpus: '1.0'

  # PostgreSQL for metadata and configuration
  postgres:
    image: postgres:15-alpine
    environment:
      POSTGRES_DB: multimodal_librarian
      POSTGRES_USER: ml_user
      POSTGRES_PASSWORD: ml_password
      # Performance tuning
      POSTGRES_SHARED_PRELOAD_LIBRARIES: pg_stat_statements
      POSTGRES_MAX_CONNECTIONS: 100
      POSTGRES_SHARED_BUFFERS: 256MB
      POSTGRES_EFFECTIVE_CACHE_SIZE: 1GB
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./database/init_db.sql:/docker-entrypoint-initdb.d/init.sql
    command: >
      postgres
      -c shared_preload_libraries=pg_stat_statements
      -c max_connections=100
      -c shared_buffers=256MB
      -c effective_cache_size=1GB
      -c maintenance_work_mem=64MB
      -c checkpoint_completion_target=0.9
      -c wal_buffers=16MB
      -c default_statistics_target=100
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ml_user -d multimodal_librarian"]
      interval: 5s
      timeout: 3s
      retries: 5
      start_period: 10s
    deploy:
      resources:
        limits:
          memory: 1G
          cpus: '1.0'
        reservations:
          memory: 512M
          cpus: '0.5'

  # Neo4j for knowledge graph
  neo4j:
    image: neo4j:5.15-community
    environment:
      NEO4J_AUTH: neo4j/ml_password
      NEO4J_PLUGINS: '["gds", "apoc"]'
      NEO4J_dbms_security_procedures_unrestricted: gds.*,apoc.*
      # Memory settings for development
      NEO4J_dbms_memory_heap_initial__size: 512m
      NEO4J_dbms_memory_heap_max__size: 1G
      NEO4J_dbms_memory_pagecache_size: 512m
      NEO4J_dbms_tx__log_rotation_retention__policy: 1G size
    ports:
      - "7474:7474"  # HTTP
      - "7687:7687"  # Bolt
    volumes:
      - neo4j_data:/data
      - neo4j_logs:/logs
    healthcheck:
      test: ["CMD-SHELL", "cypher-shell -u neo4j -p ml_password 'RETURN 1'"]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 30s
    deploy:
      resources:
        limits:
          memory: 1.5G
          cpus: '1.5'
        reservations:
          memory: 1G
          cpus: '0.5'

  # Milvus for vector similarity search
  milvus:
    image: milvusdb/milvus:v2.3.4
    command: ["milvus", "run", "standalone"]
    environment:
      ETCD_ENDPOINTS: etcd:2379
      MINIO_ADDRESS: minio:9000
      # Milvus performance tuning
      MILVUS_QUERY_NODE_GRACEFUL_TIME: 10
      MILVUS_QUERY_NODE_STATS_TASK_DELAY_EXECUTE: 10
    ports:
      - "19530:19530"
    depends_on:
      - etcd
      - minio
    volumes:
      - milvus_data:/var/lib/milvus
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:9091/healthz"]
      interval: 15s
      timeout: 10s
      retries: 3
      start_period: 45s
    deploy:
      resources:
        limits:
          memory: 2G
          cpus: '2.0'
        reservations:
          memory: 1G
          cpus: '0.5'

  # Milvus dependencies
  etcd:
    image: quay.io/coreos/etcd:v3.5.5
    environment:
      - ETCD_AUTO_COMPACTION_MODE=revision
      - ETCD_AUTO_COMPACTION_RETENTION=1000
      - ETCD_QUOTA_BACKEND_BYTES=4294967296
      - ETCD_SNAPSHOT_COUNT=50000
    volumes:
      - etcd_data:/etcd
    command: etcd -advertise-client-urls=http://127.0.0.1:2379 -listen-client-urls http://0.0.0.0:2379 --data-dir /etcd

  minio:
    image: minio/minio:RELEASE.2023-03-20T20-16-18Z
    environment:
      MINIO_ACCESS_KEY: minioadmin
      MINIO_SECRET_KEY: minioadmin
    ports:
      - "9001:9001"
    volumes:
      - minio_data:/data
    command: minio server /data --console-address ":9001"
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:9000/minio/health/live"]
      interval: 30s
      timeout: 20s
      retries: 3

  # Database administration tools
  pgadmin:
    image: dpage/pgadmin4:latest
    environment:
      PGADMIN_DEFAULT_EMAIL: admin@multimodal-librarian.com
      PGADMIN_DEFAULT_PASSWORD: admin
    ports:
      - "5050:80"
    depends_on:
      - postgres
    deploy:
      resources:
        limits:
          memory: 512M
          cpus: '0.5'

  # Milvus administration
  attu:
    image: zilliz/attu:v2.3.4
    environment:
      MILVUS_URL: milvus:19530
    ports:
      - "3000:3000"
    depends_on:
      - milvus
    deploy:
      resources:
        limits:
          memory: 512M
          cpus: '0.5'

volumes:
  postgres_data:
  neo4j_data:
  neo4j_logs:
  milvus_data:
  etcd_data:
  minio_data:
```

### Environment Configuration

```bash
# .env.local - Optimized environment configuration
# Database Configuration
ML_ENVIRONMENT=local
ML_DATABASE_TYPE=local

# PostgreSQL Configuration
ML_POSTGRES_HOST=localhost
ML_POSTGRES_PORT=5432
ML_POSTGRES_DB=multimodal_librarian
ML_POSTGRES_USER=ml_user
ML_POSTGRES_PASSWORD=ml_password
ML_POSTGRES_POOL_SIZE=20
ML_POSTGRES_MAX_OVERFLOW=10
ML_POSTGRES_POOL_TIMEOUT=30

# Neo4j Configuration
ML_NEO4J_HOST=localhost
ML_NEO4J_PORT=7687
ML_NEO4J_USER=neo4j
ML_NEO4J_PASSWORD=ml_password
ML_NEO4J_MAX_CONNECTION_LIFETIME=1800
ML_NEO4J_MAX_CONNECTION_POOL_SIZE=50

# Milvus Configuration
ML_MILVUS_HOST=localhost
ML_MILVUS_PORT=19530
ML_MILVUS_POOL_SIZE=10
ML_MILVUS_TIMEOUT=60

# Performance Configuration
ML_ENABLE_PERFORMANCE_MONITORING=true
ML_LOG_LEVEL=INFO
ML_CACHE_ENABLED=true
ML_CACHE_TTL=3600

# Development Configuration
ML_DEBUG=true
ML_HOT_RELOAD=true
ML_ENABLE_DOCS=true
```

## Conclusion

This performance tuning guide provides comprehensive strategies for optimizing the local development environment to meet the requirements specified in the local-development-conversion specification. By following these guidelines, you can achieve:

- **Memory efficiency**: Stay within the 8GB total memory limit
- **Good performance**: Maintain query performance within 20% of AWS setup
- **Fast startup**: Achieve < 2 minutes total startup time
- **Reasonable resource usage**: Optimize CPU and disk usage for development machines

Regular monitoring and incremental optimization will help maintain optimal performance as the application evolves. Use the provided benchmarking tools and monitoring scripts to track performance over time and identify areas for improvement.

### Quick Reference Commands

```bash
# Start optimized local environment
make dev-local

# Run performance benchmarks
make perf-benchmark

# Monitor performance
make perf-monitor

# Optimize performance
make perf-optimize

# Check resource usage
docker stats

# View performance logs
docker-compose -f docker-compose.local.yml logs -f
```

For additional performance optimization strategies, refer to the related documentation:
- [Local Development Performance Optimization Guide](local-development-performance-optimization-guide.md)
- [Development Workflow Performance Guide](development-workflow-performance-guide.md)
- [Docker Compose Performance Optimization Guide](docker-compose-performance-optimization-guide.md)