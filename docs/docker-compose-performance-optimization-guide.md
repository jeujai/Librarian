# Docker Compose Performance Optimization Guide

## Overview

This guide covers Docker Compose-specific performance optimizations for the local development environment. These optimizations focus on container orchestration, resource management, and service coordination to achieve optimal performance within the 8GB memory limit and 2-minute startup time requirements.

## Container Resource Optimization

### Memory Management

#### Service Memory Allocation Strategy

```yaml
# docker-compose.local.yml - Optimized resource allocation
version: '3.8'

services:
  # Application container - Primary service
  multimodal-librarian:
    deploy:
      resources:
        limits:
          memory: 2G        # Maximum memory for application
          cpus: '2.0'       # Maximum CPU cores
        reservations:
          memory: 1G        # Guaranteed memory
          cpus: '1.0'       # Guaranteed CPU
    environment:
      # Memory-optimized JVM settings for any Java components
      - JAVA_OPTS=-Xms512m -Xmx1g -XX:+UseG1GC -XX:MaxGCPauseMillis=200
      # Python memory optimization
      - PYTHONMALLOC=malloc
      - MALLOC_ARENA_MAX=2

  # PostgreSQL - Relational database
  postgres:
    deploy:
      resources:
        limits:
          memory: 1G
          cpus: '1.0'
        reservations:
          memory: 512M
          cpus: '0.5'
    # Optimized PostgreSQL configuration
    command: >
      postgres
      -c shared_buffers=256MB
      -c work_mem=8MB
      -c maintenance_work_mem=128MB
      -c effective_cache_size=768MB
      -c max_connections=100
      -c random_page_cost=2.0
      -c checkpoint_completion_target=0.9

  # Neo4j - Graph database
  neo4j:
    deploy:
      resources:
        limits:
          memory: 1.5G
          cpus: '1.5'
        reservations:
          memory: 1G
          cpus: '0.5'
    environment:
      # Heap memory configuration
      - NEO4J_server_memory_heap_initial__size=512m
      - NEO4J_server_memory_heap_max__size=1G
      # Page cache for graph data
      - NEO4J_server_memory_pagecache_size=384m
      # Off-heap memory limit
      - NEO4J_server_memory_off__heap_max__size=128m

  # Milvus - Vector database
  milvus:
    deploy:
      resources:
        limits:
          memory: 2G
          cpus: '2.0'
        reservations:
          memory: 1G
          cpus: '0.5'
    environment:
      # Milvus memory optimization
      - MILVUS_QUERY_NODE_GRACEFUL_TIME=10
      - MILVUS_QUERY_NODE_STATS_TASK_DELAY_EXECUTE=10
      - MILVUS_ROOTCOORD_MIN_SEGMENT_SIZE_TO_ENABLE_INDEX=1024

  # Milvus dependencies - Lightweight configuration
  etcd:
    deploy:
      resources:
        limits:
          memory: 256M
          cpus: '0.5'
        reservations:
          memory: 128M
          cpus: '0.25'

  minio:
    deploy:
      resources:
        limits:
          memory: 512M
          cpus: '0.5'
        reservations:
          memory: 256M
          cpus: '0.25'

  # Admin tools - Development only
  pgadmin:
    deploy:
      resources:
        limits:
          memory: 512M
          cpus: '0.5'
        reservations:
          memory: 256M
          cpus: '0.25'
    profiles: ["admin"]  # Optional profile

  attu:
    deploy:
      resources:
        limits:
          memory: 256M
          cpus: '0.5'
        reservations:
          memory: 128M
          cpus: '0.25'
    profiles: ["admin"]  # Optional profile
```

### CPU Optimization

#### CPU Affinity and Scheduling

```yaml
# CPU optimization for multi-core systems
services:
  postgres:
    cpuset: "0,1"        # Bind to specific CPU cores
    cpu_shares: 1024     # CPU priority (default: 1024)
    
  neo4j:
    cpuset: "2,3"        # Different cores for Neo4j
    cpu_shares: 1536     # Higher priority for graph operations
    
  milvus:
    cpuset: "0-3"        # Can use all cores for vector operations
    cpu_shares: 2048     # Highest priority for ML workloads
```

#### CPU Governor Optimization

```bash
# Host system CPU optimization script
#!/bin/bash
# scripts/optimize-cpu-performance.sh

# Set CPU governor to performance for consistent performance
echo "Setting CPU governor to performance..."
for cpu in /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor; do
    if [ -w "$cpu" ]; then
        echo performance | sudo tee "$cpu" > /dev/null
    fi
done

# Disable CPU frequency scaling
echo "Disabling CPU frequency scaling..."
for policy in /sys/devices/system/cpu/cpufreq/policy*/scaling_governor; do
    if [ -w "$policy" ]; then
        echo performance | sudo tee "$policy" > /dev/null
    fi
done

echo "CPU optimization completed!"
```

## Startup Performance Optimization

### Service Dependency Optimization

#### Parallel Startup Strategy

```yaml
# Optimized service dependencies for parallel startup
services:
  # Infrastructure services (can start in parallel)
  etcd:
    # No dependencies - starts immediately
    
  minio:
    # No dependencies - starts immediately
    
  postgres:
    # No dependencies - starts immediately
    
  # Database services (depend on infrastructure)
  neo4j:
    # Independent of other databases
    
  milvus:
    depends_on:
      etcd:
        condition: service_healthy
      minio:
        condition: service_healthy
    
  # Application (depends on all databases)
  multimodal-librarian:
    depends_on:
      postgres:
        condition: service_healthy
      neo4j:
        condition: service_healthy
      milvus:
        condition: service_healthy
```

#### Optimized Health Checks

```yaml
# Fast and reliable health checks
services:
  postgres:
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ml_user -d multimodal_librarian"]
      interval: 5s          # Check every 5 seconds
      timeout: 3s           # 3 second timeout
      retries: 5            # 5 retries before failure
      start_period: 10s     # Wait 10s before first check

  neo4j:
    healthcheck:
      test: ["CMD-SHELL", "cypher-shell -u neo4j -p ml_password 'RETURN 1' || exit 1"]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 30s     # Neo4j takes longer to start

  milvus:
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:9091/healthz"]
      interval: 15s
      timeout: 10s
      retries: 3
      start_period: 45s     # Milvus takes longest to start

  etcd:
    healthcheck:
      test: ["CMD", "etcdctl", "endpoint", "health"]
      interval: 10s
      timeout: 5s
      retries: 3
      start_period: 10s

  minio:
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:9000/minio/health/live"]
      interval: 10s
      timeout: 5s
      retries: 3
      start_period: 15s
```

### Image Optimization

#### Multi-stage Dockerfile for Faster Builds

```dockerfile
# Dockerfile.optimized - Multi-stage build for development
FROM python:3.11-slim as base

# Install system dependencies once
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Create application user
RUN useradd --create-home --shell /bin/bash app

WORKDIR /app

# Install Python dependencies (cached layer)
FROM base as dependencies
COPY requirements.txt requirements-dev.txt ./
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt -r requirements-dev.txt

# Development stage
FROM dependencies as development
USER app
COPY --chown=app:app . .

# Set environment variables for development
ENV PYTHONPATH=/app/src
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONHASHSEED=random

# Expose port
EXPOSE 8000

# Development command with hot reload
CMD ["uvicorn", "multimodal_librarian.main:app", "--reload", "--host", "0.0.0.0", "--port", "8000", "--reload-dir", "src"]
```

#### Image Layer Caching Strategy

```yaml
# docker-compose.local.yml - Build optimization
services:
  multimodal-librarian:
    build:
      context: .
      dockerfile: Dockerfile.optimized
      target: development
      cache_from:
        - multimodal-librarian:latest
        - python:3.11-slim
      args:
        BUILDKIT_INLINE_CACHE: 1
```

## Volume and Storage Optimization

### Persistent Volume Configuration

```yaml
# Optimized volume configuration
volumes:
  # Database volumes with performance options
  postgres_data:
    driver: local
    driver_opts:
      type: none
      o: bind
      device: ./data/postgres

  neo4j_data:
    driver: local
    driver_opts:
      type: none
      o: bind
      device: ./data/neo4j

  neo4j_logs:
    driver: local
    driver_opts:
      type: none
      o: bind
      device: ./logs/neo4j

  milvus_data:
    driver: local
    driver_opts:
      type: none
      o: bind
      device: ./data/milvus

  etcd_data:
    driver: local
    driver_opts:
      type: none
      o: bind
      device: ./data/etcd

  minio_data:
    driver: local
    driver_opts:
      type: none
      o: bind
      device: ./data/minio

services:
  postgres:
    volumes:
      - postgres_data:/var/lib/postgresql/data:rw,Z
      - ./database/postgresql/init:/docker-entrypoint-initdb.d:ro
      - ./database/postgresql/postgresql.conf:/etc/postgresql/postgresql.conf:ro
    # Use tmpfs for temporary files
    tmpfs:
      - /tmp:noexec,nosuid,size=100m
      - /var/run/postgresql:noexec,nosuid,size=100m

  neo4j:
    volumes:
      - neo4j_data:/data:rw,Z
      - neo4j_logs:/logs:rw,Z
      - ./database/neo4j/neo4j.conf:/conf/neo4j.conf:ro
    # Tmpfs for temporary operations
    tmpfs:
      - /tmp:noexec,nosuid,size=200m
```

### Development Volume Mounts

```yaml
# Development-specific volume mounts for hot reload
services:
  multimodal-librarian:
    volumes:
      # Source code for hot reload
      - ./src:/app/src:ro,cached
      - ./tests:/app/tests:ro,cached
      
      # Configuration files
      - ./.env.local:/app/.env:ro
      
      # Upload directory (persistent)
      - ./uploads:/app/uploads:rw,delegated
      
      # Logs directory (persistent)
      - ./logs:/app/logs:rw,delegated
      
      # Cache directory (temporary)
      - cache_volume:/app/.cache:rw,delegated

volumes:
  cache_volume:
    driver: local
    driver_opts:
      type: tmpfs
      device: tmpfs
      o: size=1g,uid=1000,gid=1000
```

## Network Optimization

### Custom Network Configuration

```yaml
# Optimized network configuration
networks:
  ml_network:
    driver: bridge
    driver_opts:
      com.docker.network.bridge.name: ml_bridge
      com.docker.network.driver.mtu: 1500
    ipam:
      driver: default
      config:
        - subnet: 172.20.0.0/16
          gateway: 172.20.0.1

services:
  postgres:
    networks:
      ml_network:
        ipv4_address: 172.20.0.10
        
  neo4j:
    networks:
      ml_network:
        ipv4_address: 172.20.0.11
        
  milvus:
    networks:
      ml_network:
        ipv4_address: 172.20.0.12
        
  multimodal-librarian:
    networks:
      ml_network:
        ipv4_address: 172.20.0.20
```

### DNS and Service Discovery Optimization

```yaml
# DNS optimization for faster service discovery
services:
  multimodal-librarian:
    environment:
      # Use IP addresses for faster connection
      - POSTGRES_HOST=172.20.0.10
      - NEO4J_HOST=172.20.0.11
      - MILVUS_HOST=172.20.0.12
      # Or use optimized DNS
      - POSTGRES_HOST=postgres.ml_network
      - NEO4J_HOST=neo4j.ml_network
      - MILVUS_HOST=milvus.ml_network
    dns:
      - 8.8.8.8
      - 8.8.4.4
    dns_search:
      - ml_network
```

## Logging and Monitoring Optimization

### Optimized Logging Configuration

```yaml
# Logging optimization to reduce I/O overhead
services:
  postgres:
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
        compress: "true"

  neo4j:
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
        compress: "true"

  milvus:
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
        compress: "true"

  multimodal-librarian:
    logging:
      driver: "json-file"
      options:
        max-size: "50m"
        max-file: "5"
        compress: "true"
```

### Performance Monitoring Integration

```yaml
# Optional monitoring services (use profile to enable)
services:
  # Lightweight monitoring
  cadvisor:
    image: gcr.io/cadvisor/cadvisor:latest
    container_name: cadvisor
    ports:
      - "8080:8080"
    volumes:
      - /:/rootfs:ro
      - /var/run:/var/run:rw
      - /sys:/sys:ro
      - /var/lib/docker/:/var/lib/docker:ro
    deploy:
      resources:
        limits:
          memory: 128M
          cpus: '0.5'
    profiles: ["monitoring"]

  # Resource usage monitoring
  node-exporter:
    image: prom/node-exporter:latest
    container_name: node-exporter
    ports:
      - "9100:9100"
    volumes:
      - /proc:/host/proc:ro
      - /sys:/host/sys:ro
      - /:/rootfs:ro
    command:
      - '--path.procfs=/host/proc'
      - '--path.sysfs=/host/sys'
      - '--collector.filesystem.ignored-mount-points=^/(sys|proc|dev|host|etc)($$|/)'
    deploy:
      resources:
        limits:
          memory: 64M
          cpus: '0.25'
    profiles: ["monitoring"]
```

## Environment-Specific Optimizations

### Development Profile Configuration

```yaml
# docker-compose.override.yml - Development overrides
version: '3.8'

services:
  multimodal-librarian:
    environment:
      - DEBUG=true
      - LOG_LEVEL=DEBUG
      - RELOAD=true
    volumes:
      # Additional development volumes
      - ./docs:/app/docs:ro,cached
      - ./scripts:/app/scripts:ro,cached
    ports:
      - "8000:8000"
      - "5678:5678"  # Debug port

  # Enable admin tools by default in development
  pgadmin:
    profiles: []  # Remove profile to enable by default

  attu:
    profiles: []  # Remove profile to enable by default
```

### Production-like Profile

```yaml
# docker-compose.prod-like.yml - Production-like testing
version: '3.8'

services:
  multimodal-librarian:
    environment:
      - DEBUG=false
      - LOG_LEVEL=INFO
      - RELOAD=false
    deploy:
      resources:
        limits:
          memory: 1.5G  # Reduced for production-like testing
          cpus: '1.5'

  # Disable admin tools in production-like mode
  pgadmin:
    profiles: ["never"]

  attu:
    profiles: ["never"]
```

## Performance Testing and Validation

### Docker Compose Performance Testing

```bash
#!/bin/bash
# scripts/test-docker-compose-performance.sh

echo "Testing Docker Compose performance..."

# Measure startup time
echo "Measuring startup time..."
start_time=$(date +%s)

# Start services
docker-compose -f docker-compose.local.yml up -d

# Wait for all services to be healthy
echo "Waiting for services to be healthy..."
docker-compose -f docker-compose.local.yml ps --services | while read service; do
    echo "Waiting for $service..."
    while [ "$(docker-compose -f docker-compose.local.yml ps -q $service | xargs docker inspect -f '{{.State.Health.Status}}')" != "healthy" ]; do
        sleep 1
    done
    echo "$service is healthy"
done

end_time=$(date +%s)
startup_time=$((end_time - start_time))

echo "Startup time: ${startup_time} seconds"

# Test resource usage
echo "Checking resource usage..."
docker stats --no-stream --format "table {{.Container}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.MemPerc}}"

# Test service connectivity
echo "Testing service connectivity..."
docker-compose -f docker-compose.local.yml exec -T postgres pg_isready -U ml_user -d multimodal_librarian
docker-compose -f docker-compose.local.yml exec -T neo4j cypher-shell -u neo4j -p ml_password "RETURN 1"
curl -f http://localhost:19530/healthz

echo "Performance test completed!"
```

### Resource Usage Monitoring

```python
# scripts/monitor-docker-performance.py
import docker
import time
import json
from datetime import datetime

class DockerPerformanceMonitor:
    def __init__(self):
        self.client = docker.from_env()
        self.containers = {}
    
    def collect_stats(self):
        """Collect performance statistics for all containers."""
        stats = {}
        
        for container in self.client.containers.list():
            if 'local-development-conversion' in container.name:
                container_stats = container.stats(stream=False)
                
                # Calculate CPU percentage
                cpu_delta = container_stats['cpu_stats']['cpu_usage']['total_usage'] - \
                           container_stats['precpu_stats']['cpu_usage']['total_usage']
                system_delta = container_stats['cpu_stats']['system_cpu_usage'] - \
                              container_stats['precpu_stats']['system_cpu_usage']
                
                cpu_percent = 0.0
                if system_delta > 0:
                    cpu_percent = (cpu_delta / system_delta) * 100.0
                
                # Calculate memory usage
                memory_usage = container_stats['memory_stats']['usage']
                memory_limit = container_stats['memory_stats']['limit']
                memory_percent = (memory_usage / memory_limit) * 100.0
                
                stats[container.name] = {
                    'cpu_percent': cpu_percent,
                    'memory_usage_mb': memory_usage / 1024 / 1024,
                    'memory_percent': memory_percent,
                    'memory_limit_mb': memory_limit / 1024 / 1024,
                    'timestamp': datetime.now().isoformat()
                }
        
        return stats
    
    def monitor_performance(self, duration_minutes=5, interval_seconds=10):
        """Monitor performance for specified duration."""
        end_time = time.time() + (duration_minutes * 60)
        performance_data = []
        
        while time.time() < end_time:
            stats = self.collect_stats()
            performance_data.append(stats)
            
            # Print current stats
            print(f"\n--- {datetime.now().strftime('%H:%M:%S')} ---")
            for container, data in stats.items():
                print(f"{container}: CPU: {data['cpu_percent']:.1f}%, "
                      f"Memory: {data['memory_usage_mb']:.1f}MB "
                      f"({data['memory_percent']:.1f}%)")
            
            time.sleep(interval_seconds)
        
        return performance_data
    
    def generate_report(self, performance_data):
        """Generate performance report."""
        report = {
            'summary': {},
            'recommendations': [],
            'data': performance_data
        }
        
        # Calculate averages
        for container in performance_data[0].keys():
            cpu_values = [data[container]['cpu_percent'] for data in performance_data]
            memory_values = [data[container]['memory_usage_mb'] for data in performance_data]
            
            report['summary'][container] = {
                'avg_cpu_percent': sum(cpu_values) / len(cpu_values),
                'max_cpu_percent': max(cpu_values),
                'avg_memory_mb': sum(memory_values) / len(memory_values),
                'max_memory_mb': max(memory_values)
            }
            
            # Generate recommendations
            if report['summary'][container]['avg_cpu_percent'] > 70:
                report['recommendations'].append(
                    f"{container}: High CPU usage ({report['summary'][container]['avg_cpu_percent']:.1f}%). "
                    "Consider optimizing application or increasing CPU limits."
                )
            
            if report['summary'][container]['max_memory_mb'] > 1500:
                report['recommendations'].append(
                    f"{container}: High memory usage ({report['summary'][container]['max_memory_mb']:.1f}MB). "
                    "Consider optimizing memory usage or increasing memory limits."
                )
        
        return report

if __name__ == "__main__":
    monitor = DockerPerformanceMonitor()
    print("Starting Docker Compose performance monitoring...")
    
    # Monitor for 5 minutes
    data = monitor.monitor_performance(duration_minutes=5, interval_seconds=10)
    
    # Generate and save report
    report = monitor.generate_report(data)
    
    with open('docker_performance_report.json', 'w') as f:
        json.dump(report, f, indent=2)
    
    print("\nPerformance monitoring completed!")
    print("Report saved to docker_performance_report.json")
    
    # Print summary
    print("\n--- SUMMARY ---")
    for container, stats in report['summary'].items():
        print(f"{container}:")
        print(f"  Average CPU: {stats['avg_cpu_percent']:.1f}%")
        print(f"  Average Memory: {stats['avg_memory_mb']:.1f}MB")
    
    if report['recommendations']:
        print("\n--- RECOMMENDATIONS ---")
        for rec in report['recommendations']:
            print(f"• {rec}")
```

## Makefile Integration

### Performance-Optimized Makefile Targets

```makefile
# Performance optimization targets
.PHONY: perf-up perf-down perf-restart perf-test perf-monitor

# Start with performance monitoring
perf-up:
	@echo "Starting optimized local development environment..."
	@./scripts/optimize-system-performance.sh
	docker-compose -f docker-compose.local.yml up -d
	@echo "Waiting for services to be ready..."
	@./scripts/wait-for-services-optimized.sh
	@echo "Running performance validation..."
	@./scripts/validate-performance.sh

# Stop and clean up
perf-down:
	@echo "Stopping local development environment..."
	docker-compose -f docker-compose.local.yml down
	@echo "Cleaning up performance optimizations..."
	@./scripts/cleanup-performance-optimizations.sh

# Restart with performance optimization
perf-restart: perf-down perf-up

# Test performance
perf-test:
	@echo "Running Docker Compose performance tests..."
	@./scripts/test-docker-compose-performance.sh

# Monitor performance
perf-monitor:
	@echo "Starting performance monitoring..."
	python scripts/monitor-docker-performance.py

# Optimize Docker settings
docker-optimize:
	@echo "Optimizing Docker settings..."
	@./scripts/optimize-docker-settings.sh
	@echo "Docker optimization completed. Restart Docker daemon to apply changes."

# Clean up Docker resources
docker-cleanup:
	@echo "Cleaning up Docker resources..."
	docker system prune -f
	docker volume prune -f
	docker network prune -f
	@echo "Docker cleanup completed."
```

## Best Practices

### Resource Management
1. **Set appropriate limits**: Use Docker resource constraints to prevent resource exhaustion
2. **Monitor resource usage**: Regularly check memory and CPU usage
3. **Optimize for development**: Balance performance with resource constraints
4. **Use profiles**: Enable/disable services based on development needs

### Startup Optimization
1. **Parallel startup**: Start independent services in parallel
2. **Optimized health checks**: Use fast, reliable health checks
3. **Image caching**: Leverage Docker layer caching for faster builds
4. **Dependency management**: Minimize service dependencies

### Performance Monitoring
1. **Regular monitoring**: Use performance monitoring tools
2. **Automated testing**: Include performance tests in development workflow
3. **Resource tracking**: Monitor trends over time
4. **Optimization validation**: Verify improvements after changes

### Development Workflow
1. **Hot reload optimization**: Use efficient file watching and volume mounts
2. **Test performance**: Regularly test startup and runtime performance
3. **Profile-based configuration**: Use different configurations for different scenarios
4. **Documentation**: Keep performance optimizations documented

## Conclusion

This Docker Compose performance optimization guide provides comprehensive strategies for optimizing container orchestration in the local development environment. By following these guidelines, you can achieve:

- **Efficient resource usage**: Stay within memory and CPU limits
- **Fast startup times**: Achieve < 2 minutes total startup time
- **Optimal performance**: Maintain good application performance
- **Development efficiency**: Optimize for developer productivity

Regular monitoring and incremental optimization will help maintain optimal performance as the application and infrastructure evolve.