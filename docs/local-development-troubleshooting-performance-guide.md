# Local Development Troubleshooting Performance Guide

## Overview

This guide provides comprehensive troubleshooting strategies for performance issues in the local development environment. It covers common performance problems, diagnostic techniques, and optimization solutions to maintain the performance requirements of the local-development-conversion spec.

## Performance Requirements Recap

| Requirement | Target | Critical Threshold |
|-------------|--------|-------------------|
| Total Memory Usage | < 8GB | > 10GB |
| Startup Time | < 2 minutes | > 3 minutes |
| Query Performance | Within 20% of AWS | > 50% slower |
| CPU Usage | Reasonable | > 80% sustained |

## Common Performance Issues

### 1. High Memory Usage

#### Symptoms
- Docker containers consuming excessive memory
- System becoming unresponsive
- Out of memory errors
- Swap usage increasing

#### Diagnostic Commands

```bash
# Check overall memory usage
free -h

# Check Docker container memory usage
docker stats --format "table {{.Container}}\t{{.MemUsage}}\t{{.MemPerc}}"

# Check memory usage by process
ps aux --sort=-%mem | head -20

# Check system memory pressure
cat /proc/meminfo | grep -E "(MemTotal|MemFree|MemAvailable|Cached|Buffers)"
```

#### Diagnostic Script

```python
# scripts/diagnose-memory-usage.py
import docker
import psutil
import json
from datetime import datetime

class MemoryDiagnostic:
    def __init__(self):
        self.client = docker.from_env()
        
    def diagnose_system_memory(self):
        """Diagnose system-level memory usage."""
        memory = psutil.virtual_memory()
        swap = psutil.swap_memory()
        
        return {
            "system_memory": {
                "total_gb": memory.total / 1024**3,
                "available_gb": memory.available / 1024**3,
                "used_gb": memory.used / 1024**3,
                "percent_used": memory.percent,
                "cached_gb": getattr(memory, 'cached', 0) / 1024**3,
                "buffers_gb": getattr(memory, 'buffers', 0) / 1024**3,
            },
            "swap_memory": {
                "total_gb": swap.total / 1024**3,
                "used_gb": swap.used / 1024**3,
                "percent_used": swap.percent,
            }
        }
    
    def diagnose_container_memory(self):
        """Diagnose Docker container memory usage."""
        containers = {}
        
        for container in self.client.containers.list():
            if 'local-development-conversion' in container.name:
                try:
                    stats = container.stats(stream=False)
                    memory_usage = stats['memory_stats']['usage']
                    memory_limit = stats['memory_stats']['limit']
                    
                    containers[container.name] = {
                        "memory_usage_mb": memory_usage / 1024**2,
                        "memory_limit_mb": memory_limit / 1024**2,
                        "memory_percent": (memory_usage / memory_limit) * 100,
                        "status": container.status,
                    }
                except Exception as e:
                    containers[container.name] = {"error": str(e)}
        
        return containers
    
    def identify_memory_issues(self):
        """Identify potential memory issues."""
        system_info = self.diagnose_system_memory()
        container_info = self.diagnose_container_memory()
        
        issues = []
        recommendations = []
        
        # Check system memory
        if system_info["system_memory"]["percent_used"] > 80:
            issues.append("High system memory usage")
            recommendations.append("Consider closing other applications or increasing system RAM")
        
        if system_info["swap_memory"]["percent_used"] > 10:
            issues.append("Swap memory being used")
            recommendations.append("System is using swap, which will slow performance")
        
        # Check container memory
        total_container_memory = 0
        for name, stats in container_info.items():
            if "error" not in stats:
                memory_mb = stats["memory_usage_mb"]
                total_container_memory += memory_mb
                
                if stats["memory_percent"] > 90:
                    issues.append(f"Container {name} using {stats['memory_percent']:.1f}% of allocated memory")
                    recommendations.append(f"Optimize {name} memory usage or increase memory limit")
        
        total_container_gb = total_container_memory / 1024
        if total_container_gb > 8:
            issues.append(f"Total container memory usage ({total_container_gb:.1f}GB) exceeds 8GB target")
            recommendations.append("Reduce container memory limits or optimize application memory usage")
        
        return {
            "timestamp": datetime.now().isoformat(),
            "system_info": system_info,
            "container_info": container_info,
            "issues": issues,
            "recommendations": recommendations,
            "total_container_memory_gb": total_container_gb,
        }

def main():
    diagnostic = MemoryDiagnostic()
    result = diagnostic.identify_memory_issues()
    
    print("=== MEMORY DIAGNOSTIC REPORT ===")
    print(f"Timestamp: {result['timestamp']}")
    print(f"Total Container Memory: {result['total_container_memory_gb']:.1f}GB")
    
    if result['issues']:
        print("\n🚨 ISSUES FOUND:")
        for issue in result['issues']:
            print(f"  • {issue}")
    
    if result['recommendations']:
        print("\n💡 RECOMMENDATIONS:")
        for rec in result['recommendations']:
            print(f"  • {rec}")
    
    # Save detailed report
    with open('memory_diagnostic_report.json', 'w') as f:
        json.dump(result, f, indent=2)
    
    print(f"\nDetailed report saved to memory_diagnostic_report.json")

if __name__ == "__main__":
    main()
```

#### Solutions

**Immediate Actions:**
```bash
# Restart containers with lower memory limits
docker-compose -f docker-compose.local.yml down
docker-compose -f docker-compose.local.yml up -d

# Clear Docker system cache
docker system prune -f
docker volume prune -f

# Clear system cache (Linux)
sudo sync && sudo sysctl vm.drop_caches=3
```

**Configuration Optimizations:**
```yaml
# docker-compose.local.yml - Reduced memory limits
services:
  postgres:
    deploy:
      resources:
        limits:
          memory: 768M  # Reduced from 1G
    environment:
      - POSTGRES_SHARED_BUFFERS=192MB  # Reduced from 256MB
      - POSTGRES_WORK_MEM=4MB          # Reduced from 8MB

  neo4j:
    deploy:
      resources:
        limits:
          memory: 1G    # Reduced from 1.5G
    environment:
      - NEO4J_server_memory_heap_max__size=768m  # Reduced from 1G
      - NEO4J_server_memory_pagecache_size=256m  # Reduced from 512m

  milvus:
    deploy:
      resources:
        limits:
          memory: 1.5G  # Reduced from 2G
```

### 2. Slow Startup Performance

#### Symptoms
- Services taking longer than 2 minutes to start
- Health checks timing out
- Application not responding after startup

#### Diagnostic Commands

```bash
# Monitor startup time
time docker-compose -f docker-compose.local.yml up -d

# Check service startup logs
docker-compose -f docker-compose.local.yml logs --timestamps

# Monitor health check status
watch -n 2 'docker-compose -f docker-compose.local.yml ps'

# Check container resource usage during startup
docker stats --format "table {{.Container}}\t{{.CPUPerc}}\t{{.MemUsage}}"
```

#### Startup Performance Analyzer

```python
# scripts/analyze-startup-performance.py
import time
import docker
import subprocess
from datetime import datetime, timedelta

class StartupPerformanceAnalyzer:
    def __init__(self):
        self.client = docker.from_env()
        self.startup_times = {}
        
    def measure_startup_time(self):
        """Measure complete startup time."""
        print("Starting performance measurement...")
        
        # Stop all services first
        subprocess.run([
            "docker-compose", "-f", "docker-compose.local.yml", "down"
        ], capture_output=True)
        
        # Start timing
        start_time = time.time()
        
        # Start services
        result = subprocess.run([
            "docker-compose", "-f", "docker-compose.local.yml", "up", "-d"
        ], capture_output=True, text=True)
        
        if result.returncode != 0:
            print(f"Failed to start services: {result.stderr}")
            return None
        
        # Wait for all services to be healthy
        services = ["postgres", "neo4j", "milvus", "multimodal-librarian"]
        service_ready_times = {}
        
        for service in services:
            service_start = time.time()
            
            while True:
                try:
                    container = self.client.containers.get(f"local-development-conversion-{service}-1")
                    
                    if container.status == "running":
                        # Check health status
                        health_status = container.attrs.get("State", {}).get("Health", {}).get("Status")
                        
                        if health_status == "healthy" or not health_status:
                            service_ready_times[service] = time.time() - service_start
                            print(f"✓ {service} ready in {service_ready_times[service]:.1f}s")
                            break
                    
                    time.sleep(1)
                    
                    # Timeout after 5 minutes
                    if time.time() - service_start > 300:
                        service_ready_times[service] = None
                        print(f"✗ {service} timed out after 5 minutes")
                        break
                        
                except docker.errors.NotFound:
                    time.sleep(1)
                    continue
        
        total_time = time.time() - start_time
        
        return {
            "total_startup_time": total_time,
            "service_times": service_ready_times,
            "timestamp": datetime.now().isoformat(),
        }
    
    def analyze_startup_bottlenecks(self, results):
        """Analyze startup performance bottlenecks."""
        if not results:
            return {"error": "No results to analyze"}
        
        bottlenecks = []
        recommendations = []
        
        # Check total startup time
        if results["total_startup_time"] > 120:  # 2 minutes
            bottlenecks.append(f"Total startup time ({results['total_startup_time']:.1f}s) exceeds 2-minute target")
        
        # Check individual service times
        for service, startup_time in results["service_times"].items():
            if startup_time is None:
                bottlenecks.append(f"{service} failed to start within timeout")
                recommendations.append(f"Check {service} logs and configuration")
            elif startup_time > 60:  # 1 minute per service
                bottlenecks.append(f"{service} took {startup_time:.1f}s to start")
                recommendations.append(f"Optimize {service} startup configuration")
        
        # Service-specific recommendations
        service_times = results["service_times"]
        
        if service_times.get("postgres", 0) > 30:
            recommendations.append("Reduce PostgreSQL shared_buffers or work_mem")
        
        if service_times.get("neo4j", 0) > 60:
            recommendations.append("Reduce Neo4j heap size or disable unnecessary plugins")
        
        if service_times.get("milvus", 0) > 90:
            recommendations.append("Check Milvus dependencies (etcd, minio) startup time")
        
        return {
            "bottlenecks": bottlenecks,
            "recommendations": recommendations,
            "performance_grade": self.calculate_performance_grade(results),
        }
    
    def calculate_performance_grade(self, results):
        """Calculate performance grade based on startup times."""
        total_time = results["total_startup_time"]
        
        if total_time <= 60:
            return "A (Excellent)"
        elif total_time <= 90:
            return "B (Good)"
        elif total_time <= 120:
            return "C (Acceptable)"
        elif total_time <= 180:
            return "D (Poor)"
        else:
            return "F (Unacceptable)"

def main():
    analyzer = StartupPerformanceAnalyzer()
    
    print("Measuring startup performance...")
    results = analyzer.measure_startup_time()
    
    if results:
        analysis = analyzer.analyze_startup_bottlenecks(results)
        
        print(f"\n=== STARTUP PERFORMANCE REPORT ===")
        print(f"Total Startup Time: {results['total_startup_time']:.1f}s")
        print(f"Performance Grade: {analysis['performance_grade']}")
        
        print(f"\nService Startup Times:")
        for service, time_taken in results["service_times"].items():
            if time_taken:
                print(f"  {service}: {time_taken:.1f}s")
            else:
                print(f"  {service}: TIMEOUT")
        
        if analysis["bottlenecks"]:
            print(f"\n🚨 BOTTLENECKS:")
            for bottleneck in analysis["bottlenecks"]:
                print(f"  • {bottleneck}")
        
        if analysis["recommendations"]:
            print(f"\n💡 RECOMMENDATIONS:")
            for rec in analysis["recommendations"]:
                print(f"  • {rec}")
        
        # Save report
        import json
        report = {**results, **analysis}
        with open('startup_performance_report.json', 'w') as f:
            json.dump(report, f, indent=2)
        
        print(f"\nDetailed report saved to startup_performance_report.json")

if __name__ == "__main__":
    main()
```

#### Solutions

**Parallel Startup Optimization:**
```bash
#!/bin/bash
# scripts/optimized-parallel-startup.sh

echo "Starting optimized parallel startup..."

# Start infrastructure services first (parallel)
echo "Starting infrastructure services..."
docker-compose -f docker-compose.local.yml up -d etcd minio &
INFRA_PID=$!

# Start PostgreSQL (independent)
echo "Starting PostgreSQL..."
docker-compose -f docker-compose.local.yml up -d postgres &
POSTGRES_PID=$!

# Wait for infrastructure
wait $INFRA_PID
echo "Infrastructure services started"

# Start Milvus (depends on etcd/minio)
echo "Starting Milvus..."
docker-compose -f docker-compose.local.yml up -d milvus &
MILVUS_PID=$!

# Start Neo4j (independent)
echo "Starting Neo4j..."
docker-compose -f docker-compose.local.yml up -d neo4j &
NEO4J_PID=$!

# Wait for databases
wait $POSTGRES_PID $MILVUS_PID $NEO4J_PID
echo "Database services started"

# Start application
echo "Starting application..."
docker-compose -f docker-compose.local.yml up -d multimodal-librarian

echo "Startup completed!"
```

**Health Check Optimization:**
```yaml
# Faster health checks
services:
  postgres:
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ml_user"]
      interval: 3s      # Reduced from 5s
      timeout: 2s       # Reduced from 3s
      retries: 3        # Reduced from 5
      start_period: 5s  # Reduced from 10s

  neo4j:
    healthcheck:
      test: ["CMD-SHELL", "cypher-shell -u neo4j -p ml_password 'RETURN 1' --format plain"]
      interval: 5s      # Reduced from 10s
      timeout: 3s       # Reduced from 5s
      retries: 3        # Reduced from 5
      start_period: 15s # Reduced from 30s
```

### 3. Poor Query Performance

#### Symptoms
- Database queries taking longer than expected
- API responses slower than 20% of AWS performance
- High CPU usage during queries

#### Diagnostic Commands

```bash
# PostgreSQL query performance
docker exec local-development-conversion-postgres-1 psql -U ml_user -d multimodal_librarian -c "
SELECT query, mean_exec_time, calls, total_exec_time 
FROM pg_stat_statements 
ORDER BY mean_exec_time DESC 
LIMIT 10;"

# Neo4j query performance
docker exec local-development-conversion-neo4j-1 cypher-shell -u neo4j -p ml_password "
CALL dbms.queryJmx('org.neo4j:instance=kernel#0,name=Transactions') 
YIELD attributes 
RETURN attributes.NumberOfOpenTransactions;"

# Milvus collection stats
python -c "
from pymilvus import connections, Collection
connections.connect(host='localhost', port=19530)
collections = Collection.list()
for name in collections:
    col = Collection(name)
    print(f'{name}: {col.num_entities} entities')
"
```

#### Query Performance Analyzer

```python
# scripts/analyze-query-performance.py
import asyncio
import time
import asyncpg
from pymilvus import connections, Collection
from neo4j import GraphDatabase

class QueryPerformanceAnalyzer:
    def __init__(self):
        self.results = {}
        
    async def test_postgresql_performance(self):
        """Test PostgreSQL query performance."""
        conn = await asyncpg.connect(
            host="localhost",
            port=5432,
            user="ml_user",
            password="ml_password",
            database="multimodal_librarian"
        )
        
        tests = {
            "simple_select": "SELECT 1",
            "count_query": "SELECT COUNT(*) FROM information_schema.tables",
            "join_query": """
                SELECT t1.table_name, t2.column_name 
                FROM information_schema.tables t1 
                JOIN information_schema.columns t2 ON t1.table_name = t2.table_name 
                LIMIT 10
            """,
        }
        
        results = {}
        
        for test_name, query in tests.items():
            times = []
            
            for _ in range(5):  # Run 5 times
                start = time.time()
                await conn.fetch(query)
                duration = time.time() - start
                times.append(duration)
            
            results[test_name] = {
                "avg_time": sum(times) / len(times),
                "min_time": min(times),
                "max_time": max(times),
            }
        
        await conn.close()
        return results
    
    def test_neo4j_performance(self):
        """Test Neo4j query performance."""
        driver = GraphDatabase.driver("bolt://localhost:7687", auth=("neo4j", "ml_password"))
        
        tests = {
            "simple_return": "RETURN 1",
            "node_count": "MATCH (n) RETURN count(n)",
            "relationship_query": "MATCH (n)-[r]->(m) RETURN count(r) LIMIT 1000",
        }
        
        results = {}
        
        with driver.session() as session:
            for test_name, query in tests.items():
                times = []
                
                for _ in range(5):  # Run 5 times
                    start = time.time()
                    try:
                        session.run(query).consume()
                        duration = time.time() - start
                        times.append(duration)
                    except Exception as e:
                        times.append(float('inf'))  # Mark as failed
                
                valid_times = [t for t in times if t != float('inf')]
                
                if valid_times:
                    results[test_name] = {
                        "avg_time": sum(valid_times) / len(valid_times),
                        "min_time": min(valid_times),
                        "max_time": max(valid_times),
                        "success_rate": len(valid_times) / len(times),
                    }
                else:
                    results[test_name] = {"error": "All queries failed"}
        
        driver.close()
        return results
    
    def test_milvus_performance(self):
        """Test Milvus query performance."""
        connections.connect(host="localhost", port=19530)
        
        # Create test collection if it doesn't exist
        collection_name = "performance_test"
        
        try:
            collection = Collection(collection_name)
        except Exception:
            # Collection doesn't exist, create it
            from pymilvus import FieldSchema, CollectionSchema, DataType
            
            fields = [
                FieldSchema(name="id", dtype=DataType.INT64, is_primary=True, auto_id=True),
                FieldSchema(name="vector", dtype=DataType.FLOAT_VECTOR, dim=128)
            ]
            schema = CollectionSchema(fields, "Performance test collection")
            collection = Collection(collection_name, schema)
        
        # Insert test data if collection is empty
        if collection.num_entities == 0:
            import random
            vectors = [[random.random() for _ in range(128)] for _ in range(1000)]
            collection.insert([vectors])
            collection.flush()
            
            # Create index
            index_params = {
                "metric_type": "L2",
                "index_type": "IVF_FLAT",
                "params": {"nlist": 128}
            }
            collection.create_index("vector", index_params)
        
        collection.load()
        
        # Test search performance
        search_params = {"metric_type": "L2", "params": {"nprobe": 10}}
        query_vector = [[random.random() for _ in range(128)]]
        
        times = []
        for _ in range(5):
            start = time.time()
            results = collection.search(query_vector, "vector", search_params, limit=10)
            duration = time.time() - start
            times.append(duration)
        
        return {
            "search_performance": {
                "avg_time": sum(times) / len(times),
                "min_time": min(times),
                "max_time": max(times),
                "collection_size": collection.num_entities,
            }
        }
    
    async def run_comprehensive_test(self):
        """Run comprehensive query performance test."""
        print("Testing PostgreSQL performance...")
        postgres_results = await self.test_postgresql_performance()
        
        print("Testing Neo4j performance...")
        neo4j_results = self.test_neo4j_performance()
        
        print("Testing Milvus performance...")
        milvus_results = self.test_milvus_performance()
        
        return {
            "postgresql": postgres_results,
            "neo4j": neo4j_results,
            "milvus": milvus_results,
            "timestamp": time.time(),
        }
    
    def analyze_performance_issues(self, results):
        """Analyze performance test results for issues."""
        issues = []
        recommendations = []
        
        # PostgreSQL analysis
        pg_results = results.get("postgresql", {})
        for test_name, metrics in pg_results.items():
            if metrics.get("avg_time", 0) > 0.1:  # 100ms threshold
                issues.append(f"PostgreSQL {test_name} slow: {metrics['avg_time']:.3f}s")
                recommendations.append("Check PostgreSQL configuration and add indexes")
        
        # Neo4j analysis
        neo4j_results = results.get("neo4j", {})
        for test_name, metrics in neo4j_results.items():
            if "error" in metrics:
                issues.append(f"Neo4j {test_name} failed: {metrics['error']}")
                recommendations.append("Check Neo4j connectivity and configuration")
            elif metrics.get("avg_time", 0) > 0.2:  # 200ms threshold
                issues.append(f"Neo4j {test_name} slow: {metrics['avg_time']:.3f}s")
                recommendations.append("Optimize Neo4j memory settings and create indexes")
        
        # Milvus analysis
        milvus_results = results.get("milvus", {})
        search_perf = milvus_results.get("search_performance", {})
        if search_perf.get("avg_time", 0) > 0.1:  # 100ms threshold
            issues.append(f"Milvus search slow: {search_perf['avg_time']:.3f}s")
            recommendations.append("Optimize Milvus index parameters and search settings")
        
        return {
            "issues": issues,
            "recommendations": recommendations,
            "performance_summary": self.generate_performance_summary(results),
        }
    
    def generate_performance_summary(self, results):
        """Generate performance summary."""
        summary = {}
        
        # PostgreSQL summary
        pg_results = results.get("postgresql", {})
        if pg_results:
            avg_times = [metrics.get("avg_time", 0) for metrics in pg_results.values()]
            summary["postgresql_avg"] = sum(avg_times) / len(avg_times) if avg_times else 0
        
        # Neo4j summary
        neo4j_results = results.get("neo4j", {})
        if neo4j_results:
            avg_times = [
                metrics.get("avg_time", 0) 
                for metrics in neo4j_results.values() 
                if "error" not in metrics
            ]
            summary["neo4j_avg"] = sum(avg_times) / len(avg_times) if avg_times else 0
        
        # Milvus summary
        milvus_results = results.get("milvus", {})
        search_perf = milvus_results.get("search_performance", {})
        summary["milvus_search_avg"] = search_perf.get("avg_time", 0)
        
        return summary

async def main():
    analyzer = QueryPerformanceAnalyzer()
    
    print("Running comprehensive query performance test...")
    results = await analyzer.run_comprehensive_test()
    
    print("Analyzing results...")
    analysis = analyzer.analyze_performance_issues(results)
    
    print("\n=== QUERY PERFORMANCE REPORT ===")
    
    # Print summary
    summary = analysis["performance_summary"]
    print(f"PostgreSQL Average: {summary.get('postgresql_avg', 0):.3f}s")
    print(f"Neo4j Average: {summary.get('neo4j_avg', 0):.3f}s")
    print(f"Milvus Search Average: {summary.get('milvus_search_avg', 0):.3f}s")
    
    # Print issues
    if analysis["issues"]:
        print(f"\n🚨 PERFORMANCE ISSUES:")
        for issue in analysis["issues"]:
            print(f"  • {issue}")
    
    # Print recommendations
    if analysis["recommendations"]:
        print(f"\n💡 RECOMMENDATIONS:")
        for rec in analysis["recommendations"]:
            print(f"  • {rec}")
    
    # Save detailed report
    import json
    report = {**results, **analysis}
    with open('query_performance_report.json', 'w') as f:
        json.dump(report, f, indent=2, default=str)
    
    print(f"\nDetailed report saved to query_performance_report.json")

if __name__ == "__main__":
    asyncio.run(main())
```

#### Solutions

**PostgreSQL Optimization:**
```sql
-- Add indexes for common queries
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_documents_user_id ON documents(user_id);
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_conversations_user_id ON conversations(user_id);
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_messages_conversation_id ON messages(conversation_id);

-- Update statistics
ANALYZE;

-- Vacuum if needed
VACUUM ANALYZE;
```

**Neo4j Optimization:**
```cypher
// Create indexes for common queries
CREATE INDEX FOR (d:Document) ON (d.id);
CREATE INDEX FOR (u:User) ON (u.id);
CREATE INDEX FOR (c:Concept) ON (c.name);

// Update query cache
CALL db.clearQueryCaches();
```

**Milvus Optimization:**
```python
# Optimize Milvus index parameters
index_params = {
    "metric_type": "L2",
    "index_type": "IVF_FLAT",
    "params": {"nlist": min(4096, collection.num_entities // 39)}
}

# Optimize search parameters
search_params = {
    "metric_type": "L2",
    "params": {"nprobe": min(max(10, k * 2), nlist // 4)}
}
```

### 4. High CPU Usage

#### Symptoms
- Sustained high CPU usage (>80%)
- System becoming unresponsive
- Fan noise increasing
- Thermal throttling

#### Diagnostic Commands

```bash
# Check CPU usage by process
top -o %CPU

# Check CPU usage by Docker container
docker stats --format "table {{.Container}}\t{{.CPUPerc}}\t{{.PIDs}}"

# Check system load average
uptime

# Monitor CPU usage over time
iostat -c 1 10
```

#### CPU Performance Analyzer

```python
# scripts/analyze-cpu-performance.py
import psutil
import docker
import time
import json
from datetime import datetime

class CPUPerformanceAnalyzer:
    def __init__(self):
        self.client = docker.from_env()
        
    def monitor_cpu_usage(self, duration_minutes=5):
        """Monitor CPU usage for specified duration."""
        print(f"Monitoring CPU usage for {duration_minutes} minutes...")
        
        end_time = time.time() + (duration_minutes * 60)
        measurements = []
        
        while time.time() < end_time:
            # System CPU usage
            cpu_percent = psutil.cpu_percent(interval=1, percpu=True)
            system_avg = sum(cpu_percent) / len(cpu_percent)
            
            # Container CPU usage
            container_stats = {}
            for container in self.client.containers.list():
                if 'local-development-conversion' in container.name:
                    try:
                        stats = container.stats(stream=False)
                        
                        # Calculate CPU percentage
                        cpu_delta = stats['cpu_stats']['cpu_usage']['total_usage'] - \
                                   stats['precpu_stats']['cpu_usage']['total_usage']
                        system_delta = stats['cpu_stats']['system_cpu_usage'] - \
                                      stats['precpu_stats']['system_cpu_usage']
                        
                        cpu_percent_container = 0.0
                        if system_delta > 0:
                            cpu_percent_container = (cpu_delta / system_delta) * 100.0
                        
                        container_stats[container.name] = cpu_percent_container
                        
                    except Exception as e:
                        container_stats[container.name] = 0.0
            
            measurement = {
                "timestamp": time.time(),
                "system_cpu_avg": system_avg,
                "system_cpu_per_core": cpu_percent,
                "container_cpu": container_stats,
            }
            
            measurements.append(measurement)
            
            # Print current status
            print(f"System CPU: {system_avg:.1f}% | Containers: {', '.join([f'{k.split('-')[-2]}: {v:.1f}%' for k, v in container_stats.items()])}")
            
            time.sleep(10)  # Measure every 10 seconds
        
        return measurements
    
    def analyze_cpu_issues(self, measurements):
        """Analyze CPU measurements for issues."""
        if not measurements:
            return {"error": "No measurements to analyze"}
        
        issues = []
        recommendations = []
        
        # Calculate averages
        system_cpu_avg = sum(m["system_cpu_avg"] for m in measurements) / len(measurements)
        system_cpu_max = max(m["system_cpu_avg"] for m in measurements)
        
        # Analyze system CPU usage
        if system_cpu_avg > 70:
            issues.append(f"High average CPU usage: {system_cpu_avg:.1f}%")
            recommendations.append("Reduce container CPU limits or optimize application performance")
        
        if system_cpu_max > 90:
            issues.append(f"CPU usage spikes detected: {system_cpu_max:.1f}%")
            recommendations.append("Investigate CPU-intensive operations and optimize algorithms")
        
        # Analyze container CPU usage
        container_averages = {}
        container_maximums = {}
        
        # Get all container names
        all_containers = set()
        for m in measurements:
            all_containers.update(m["container_cpu"].keys())
        
        for container in all_containers:
            cpu_values = [m["container_cpu"].get(container, 0) for m in measurements]
            container_averages[container] = sum(cpu_values) / len(cpu_values)
            container_maximums[container] = max(cpu_values)
            
            if container_averages[container] > 50:
                issues.append(f"High CPU usage in {container}: {container_averages[container]:.1f}%")
                
                # Container-specific recommendations
                if "postgres" in container:
                    recommendations.append("Optimize PostgreSQL queries and reduce max_connections")
                elif "neo4j" in container:
                    recommendations.append("Optimize Neo4j queries and reduce heap size")
                elif "milvus" in container:
                    recommendations.append("Optimize Milvus index parameters and search settings")
                elif "multimodal-librarian" in container:
                    recommendations.append("Profile application code and optimize CPU-intensive operations")
        
        # Check for CPU core imbalance
        core_usage_samples = [m["system_cpu_per_core"] for m in measurements]
        if core_usage_samples:
            avg_core_usage = []
            for core_idx in range(len(core_usage_samples[0])):
                core_values = [sample[core_idx] for sample in core_usage_samples]
                avg_core_usage.append(sum(core_values) / len(core_values))
            
            max_core_usage = max(avg_core_usage)
            min_core_usage = min(avg_core_usage)
            
            if max_core_usage - min_core_usage > 30:  # 30% difference
                issues.append(f"CPU core imbalance detected: {min_core_usage:.1f}% - {max_core_usage:.1f}%")
                recommendations.append("Consider CPU affinity settings for containers")
        
        return {
            "issues": issues,
            "recommendations": recommendations,
            "summary": {
                "system_cpu_avg": system_cpu_avg,
                "system_cpu_max": system_cpu_max,
                "container_averages": container_averages,
                "container_maximums": container_maximums,
                "measurement_count": len(measurements),
                "duration_minutes": (measurements[-1]["timestamp"] - measurements[0]["timestamp"]) / 60,
            }
        }

def main():
    analyzer = CPUPerformanceAnalyzer()
    
    # Monitor CPU usage
    measurements = analyzer.monitor_cpu_usage(duration_minutes=2)  # 2 minutes for quick test
    
    # Analyze results
    analysis = analyzer.analyze_cpu_issues(measurements)
    
    print("\n=== CPU PERFORMANCE REPORT ===")
    
    if "error" in analysis:
        print(f"Error: {analysis['error']}")
        return
    
    summary = analysis["summary"]
    print(f"Average CPU Usage: {summary['system_cpu_avg']:.1f}%")
    print(f"Peak CPU Usage: {summary['system_cpu_max']:.1f}%")
    print(f"Monitoring Duration: {summary['duration_minutes']:.1f} minutes")
    
    print(f"\nContainer CPU Usage (Average):")
    for container, avg_cpu in summary["container_averages"].items():
        service_name = container.split('-')[-2] if '-' in container else container
        print(f"  {service_name}: {avg_cpu:.1f}%")
    
    if analysis["issues"]:
        print(f"\n🚨 CPU ISSUES:")
        for issue in analysis["issues"]:
            print(f"  • {issue}")
    
    if analysis["recommendations"]:
        print(f"\n💡 RECOMMENDATIONS:")
        for rec in analysis["recommendations"]:
            print(f"  • {rec}")
    
    # Save detailed report
    report = {
        "measurements": measurements,
        "analysis": analysis,
        "timestamp": datetime.now().isoformat(),
    }
    
    with open('cpu_performance_report.json', 'w') as f:
        json.dump(report, f, indent=2)
    
    print(f"\nDetailed report saved to cpu_performance_report.json")

if __name__ == "__main__":
    main()
```

#### Solutions

**Container CPU Limits:**
```yaml
# docker-compose.local.yml - CPU optimization
services:
  postgres:
    deploy:
      resources:
        limits:
          cpus: '0.5'    # Limit to 0.5 CPU cores
    
  neo4j:
    deploy:
      resources:
        limits:
          cpus: '1.0'    # Limit to 1 CPU core
    
  milvus:
    deploy:
      resources:
        limits:
          cpus: '1.5'    # Limit to 1.5 CPU cores
```

**Application Optimization:**
```python
# Optimize CPU-intensive operations
import asyncio
from concurrent.futures import ThreadPoolExecutor

# Use thread pool for CPU-intensive tasks
executor = ThreadPoolExecutor(max_workers=2)

async def cpu_intensive_task(data):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(executor, process_data, data)

# Optimize database queries
async def optimized_query():
    # Use connection pooling
    # Batch operations
    # Use indexes
    pass
```

## Performance Monitoring Scripts

### Comprehensive Performance Monitor

```bash
#!/bin/bash
# scripts/comprehensive-performance-monitor.sh

echo "=== COMPREHENSIVE PERFORMANCE MONITOR ==="
echo "Timestamp: $(date)"

# System overview
echo -e "\n📊 SYSTEM OVERVIEW"
echo "CPU Cores: $(nproc)"
echo "Total Memory: $(free -h | grep '^Mem:' | awk '{print $2}')"
echo "Available Memory: $(free -h | grep '^Mem:' | awk '{print $7}')"
echo "Load Average: $(uptime | awk -F'load average:' '{print $2}')"

# Docker system info
echo -e "\n🐳 DOCKER SYSTEM"
docker system df

# Container resource usage
echo -e "\n📈 CONTAINER RESOURCES"
docker stats --no-stream --format "table {{.Container}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.MemPerc}}\t{{.NetIO}}\t{{.BlockIO}}"

# Service health status
echo -e "\n🏥 SERVICE HEALTH"
docker-compose -f docker-compose.local.yml ps

# Database-specific checks
echo -e "\n🗄️ DATABASE STATUS"

# PostgreSQL
echo "PostgreSQL:"
docker exec local-development-conversion-postgres-1 pg_isready -U ml_user -d multimodal_librarian 2>/dev/null && echo "  ✓ Connected" || echo "  ✗ Connection failed"

# Neo4j
echo "Neo4j:"
docker exec local-development-conversion-neo4j-1 cypher-shell -u neo4j -p ml_password "RETURN 1" 2>/dev/null >/dev/null && echo "  ✓ Connected" || echo "  ✗ Connection failed"

# Milvus
echo "Milvus:"
curl -s -f http://localhost:19530/healthz >/dev/null && echo "  ✓ Healthy" || echo "  ✗ Unhealthy"

# Performance recommendations
echo -e "\n💡 QUICK RECOMMENDATIONS"

# Check memory usage
MEMORY_USAGE=$(free | grep '^Mem:' | awk '{printf "%.0f", $3/$2 * 100}')
if [ "$MEMORY_USAGE" -gt 80 ]; then
    echo "  ⚠️ High memory usage (${MEMORY_USAGE}%) - consider reducing container limits"
fi

# Check CPU load
LOAD_AVG=$(uptime | awk -F'load average:' '{print $2}' | awk -F',' '{print $1}' | tr -d ' ')
CPU_CORES=$(nproc)
if (( $(echo "$LOAD_AVG > $CPU_CORES" | bc -l) )); then
    echo "  ⚠️ High CPU load ($LOAD_AVG) - consider optimizing applications"
fi

# Check disk usage
DISK_USAGE=$(df / | tail -1 | awk '{print $5}' | sed 's/%//')
if [ "$DISK_USAGE" -gt 80 ]; then
    echo "  ⚠️ High disk usage (${DISK_USAGE}%) - consider cleaning up Docker resources"
fi

echo -e "\nMonitoring completed!"
```

### Automated Performance Alerts

```python
# scripts/performance-alerts.py
import time
import psutil
import docker
import smtplib
from email.mime.text import MIMEText
from datetime import datetime

class PerformanceAlertSystem:
    def __init__(self):
        self.client = docker.from_env()
        self.thresholds = {
            "memory_percent": 85,
            "cpu_percent": 80,
            "disk_percent": 85,
            "container_memory_mb": 1500,
            "container_cpu_percent": 70,
        }
        self.alert_cooldown = 300  # 5 minutes between alerts
        self.last_alerts = {}
        
    def check_system_performance(self):
        """Check system performance metrics."""
        alerts = []
        
        # Memory check
        memory = psutil.virtual_memory()
        if memory.percent > self.thresholds["memory_percent"]:
            alerts.append({
                "type": "system_memory",
                "message": f"High system memory usage: {memory.percent:.1f}%",
                "severity": "warning" if memory.percent < 90 else "critical",
            })
        
        # CPU check
        cpu_percent = psutil.cpu_percent(interval=1)
        if cpu_percent > self.thresholds["cpu_percent"]:
            alerts.append({
                "type": "system_cpu",
                "message": f"High system CPU usage: {cpu_percent:.1f}%",
                "severity": "warning" if cpu_percent < 90 else "critical",
            })
        
        # Disk check
        disk = psutil.disk_usage('/')
        disk_percent = (disk.used / disk.total) * 100
        if disk_percent > self.thresholds["disk_percent"]:
            alerts.append({
                "type": "system_disk",
                "message": f"High disk usage: {disk_percent:.1f}%",
                "severity": "warning" if disk_percent < 95 else "critical",
            })
        
        return alerts
    
    def check_container_performance(self):
        """Check container performance metrics."""
        alerts = []
        
        for container in self.client.containers.list():
            if 'local-development-conversion' in container.name:
                try:
                    stats = container.stats(stream=False)
                    
                    # Memory check
                    memory_usage = stats['memory_stats']['usage']
                    memory_limit = stats['memory_stats']['limit']
                    memory_mb = memory_usage / 1024**2
                    memory_percent = (memory_usage / memory_limit) * 100
                    
                    if memory_mb > self.thresholds["container_memory_mb"]:
                        alerts.append({
                            "type": "container_memory",
                            "message": f"High memory usage in {container.name}: {memory_mb:.1f}MB ({memory_percent:.1f}%)",
                            "severity": "warning" if memory_percent < 95 else "critical",
                        })
                    
                    # CPU check
                    cpu_delta = stats['cpu_stats']['cpu_usage']['total_usage'] - \
                               stats['precpu_stats']['cpu_usage']['total_usage']
                    system_delta = stats['cpu_stats']['system_cpu_usage'] - \
                                  stats['precpu_stats']['system_cpu_usage']
                    
                    cpu_percent = 0.0
                    if system_delta > 0:
                        cpu_percent = (cpu_delta / system_delta) * 100.0
                    
                    if cpu_percent > self.thresholds["container_cpu_percent"]:
                        alerts.append({
                            "type": "container_cpu",
                            "message": f"High CPU usage in {container.name}: {cpu_percent:.1f}%",
                            "severity": "warning" if cpu_percent < 90 else "critical",
                        })
                
                except Exception as e:
                    alerts.append({
                        "type": "container_error",
                        "message": f"Error checking {container.name}: {str(e)}",
                        "severity": "warning",
                    })
        
        return alerts
    
    def should_send_alert(self, alert_type):
        """Check if alert should be sent based on cooldown."""
        now = time.time()
        last_alert_time = self.last_alerts.get(alert_type, 0)
        
        if now - last_alert_time > self.alert_cooldown:
            self.last_alerts[alert_type] = now
            return True
        
        return False
    
    def send_alert(self, alerts):
        """Send performance alerts (print to console for now)."""
        if not alerts:
            return
        
        print(f"\n🚨 PERFORMANCE ALERTS - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        for alert in alerts:
            if self.should_send_alert(alert["type"]):
                severity_icon = "🔴" if alert["severity"] == "critical" else "🟡"
                print(f"{severity_icon} {alert['message']}")
        
        print()
    
    def monitor_continuously(self, check_interval=60):
        """Monitor performance continuously."""
        print("Starting continuous performance monitoring...")
        print(f"Check interval: {check_interval} seconds")
        print("Press Ctrl+C to stop")
        
        try:
            while True:
                # Check system performance
                system_alerts = self.check_system_performance()
                
                # Check container performance
                container_alerts = self.check_container_performance()
                
                # Send alerts if any
                all_alerts = system_alerts + container_alerts
                self.send_alert(all_alerts)
                
                # Wait for next check
                time.sleep(check_interval)
                
        except KeyboardInterrupt:
            print("\nPerformance monitoring stopped.")

def main():
    alert_system = PerformanceAlertSystem()
    
    # Run one-time check
    print("Running performance check...")
    
    system_alerts = alert_system.check_system_performance()
    container_alerts = alert_system.check_container_performance()
    
    all_alerts = system_alerts + container_alerts
    
    if all_alerts:
        alert_system.send_alert(all_alerts)
    else:
        print("✅ No performance issues detected")
    
    # Ask if user wants continuous monitoring
    response = input("\nStart continuous monitoring? (y/N): ")
    if response.lower() == 'y':
        alert_system.monitor_continuously()

if __name__ == "__main__":
    main()
```

## Makefile Integration

### Performance Troubleshooting Commands

```makefile
# Performance troubleshooting targets
.PHONY: perf-diagnose perf-fix perf-monitor perf-alerts

# Comprehensive performance diagnosis
perf-diagnose:
	@echo "Running comprehensive performance diagnosis..."
	@./scripts/comprehensive-performance-monitor.sh
	@echo "Running memory diagnostic..."
	@python scripts/diagnose-memory-usage.py
	@echo "Running startup performance test..."
	@python scripts/analyze-startup-performance.py
	@echo "Running query performance test..."
	@python scripts/analyze-query-performance.py
	@echo "Running CPU performance analysis..."
	@python scripts/analyze-cpu-performance.py

# Quick performance fixes
perf-fix:
	@echo "Applying quick performance fixes..."
	@echo "Restarting containers with optimized settings..."
	docker-compose -f docker-compose.local.yml down
	docker-compose -f docker-compose.local.yml up -d
	@echo "Cleaning up Docker resources..."
	docker system prune -f
	@echo "Optimizing database performance..."
	@$(MAKE) postgres-analyze-tables
	@echo "Performance fixes applied!"

# Start performance monitoring
perf-monitor:
	@echo "Starting performance monitoring..."
	python scripts/performance-alerts.py

# Check for performance alerts
perf-alerts:
	@echo "Checking for performance alerts..."
	python scripts/performance-alerts.py --check-once

# Emergency performance recovery
perf-emergency:
	@echo "🚨 Emergency performance recovery..."
	@echo "Stopping all services..."
	docker-compose -f docker-compose.local.yml down
	@echo "Cleaning up resources..."
	docker system prune -af
	docker volume prune -f
	@echo "Restarting with minimal configuration..."
	docker-compose -f docker-compose.local.yml up -d postgres neo4j
	@echo "Waiting for databases..."
	@sleep 30
	@echo "Starting application..."
	docker-compose -f docker-compose.local.yml up -d multimodal-librarian
	@echo "Emergency recovery completed!"

# Performance optimization help
perf-help:
	@echo "Performance Troubleshooting Commands:"
	@echo "  perf-diagnose    - Run comprehensive performance diagnosis"
	@echo "  perf-fix         - Apply quick performance fixes"
	@echo "  perf-monitor     - Start continuous performance monitoring"
	@echo "  perf-alerts      - Check for current performance alerts"
	@echo "  perf-emergency   - Emergency performance recovery"
	@echo ""
	@echo "Individual diagnostic commands:"
	@echo "  python scripts/diagnose-memory-usage.py"
	@echo "  python scripts/analyze-startup-performance.py"
	@echo "  python scripts/analyze-query-performance.py"
	@echo "  python scripts/analyze-cpu-performance.py"
```

## Best Practices

### Performance Troubleshooting Workflow
1. **Identify symptoms**: Use monitoring tools to identify performance issues
2. **Run diagnostics**: Use specific diagnostic scripts for detailed analysis
3. **Apply targeted fixes**: Address specific issues with appropriate solutions
4. **Validate improvements**: Re-run diagnostics to confirm fixes
5. **Monitor continuously**: Use ongoing monitoring to prevent future issues

### Preventive Measures
1. **Regular monitoring**: Run performance checks daily during development
2. **Resource limits**: Set appropriate Docker resource constraints
3. **Optimization maintenance**: Regularly optimize database configurations
4. **Performance testing**: Include performance tests in development workflow
5. **Documentation**: Keep track of performance optimizations and issues

### Emergency Procedures
1. **Quick recovery**: Use emergency recovery procedures for critical issues
2. **Resource cleanup**: Regularly clean up Docker resources
3. **Service restart**: Restart services with optimized configurations
4. **Escalation path**: Know when to seek additional help or resources

## Conclusion

This troubleshooting performance guide provides comprehensive strategies for diagnosing and resolving performance issues in the local development environment. By following these guidelines and using the provided diagnostic tools, you can:

- **Quickly identify performance bottlenecks**
- **Apply targeted solutions to specific issues**
- **Monitor performance continuously**
- **Prevent future performance problems**
- **Maintain optimal development environment performance**

Regular use of these troubleshooting techniques will help maintain a high-performance local development environment that meets the requirements of the local-development-conversion spec.