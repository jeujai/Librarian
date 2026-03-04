# Docker Resource Limits Configuration

## Overview

This document describes the Docker resource limits configuration for the Multimodal Librarian local development environment. Resource limits prevent any single container from consuming excessive system resources and ensure stable performance across different development machines.

## Resource Allocation Strategy

### Total System Requirements
- **Minimum**: 8GB RAM, 4 CPU cores, 50GB disk space
- **Recommended**: 16GB RAM, 8 CPU cores, 100GB disk space
- **Optimal**: 32GB RAM, 16 CPU cores, 200GB disk space

### Resource Distribution

| Service | CPU Limit | CPU Reserve | Memory Limit | Memory Reserve | Priority |
|---------|-----------|-------------|--------------|----------------|----------|
| multimodal-librarian | 2.0 | 0.5 | 2GB | 512MB | High |
| postgres | 1.0 | 0.25 | 1GB | 256MB | High |
| neo4j | 1.5 | 0.5 | 1.5GB | 512MB | High |
| milvus | 1.5 | 0.5 | 2GB | 512MB | High |
| redis | 0.5 | 0.1 | 512MB | 128MB | Medium |
| etcd | 0.5 | 0.1 | 512MB | 128MB | Medium |
| minio | 0.5 | 0.1 | 512MB | 128MB | Medium |
| pgadmin | 0.5 | 0.1 | 512MB | 128MB | Low |
| attu | 0.25 | 0.1 | 256MB | 64MB | Low |
| redis-commander | 0.25 | 0.1 | 256MB | 64MB | Low |
| log-viewer | 0.25 | 0.1 | 256MB | 64MB | Low |

**Total Allocation**: 8.0 CPU cores, 8.5GB RAM

## Resource Limit Types

### CPU Limits
- **Limits**: Maximum CPU cores a container can use
- **Reservations**: Guaranteed CPU allocation
- **Shares**: Relative CPU priority when resources are contended

### Memory Limits
- **Limits**: Maximum memory a container can use (hard limit)
- **Reservations**: Guaranteed memory allocation
- **Swap**: Swap usage limits (disabled for performance)

### Disk I/O Limits
- **Read/Write IOPS**: Input/output operations per second
- **Read/Write BPS**: Bytes per second throughput
- **Device Weight**: Relative I/O priority

### Network Limits
- **Bandwidth**: Network throughput limits
- **Packet Rate**: Packets per second limits

## Environment-Specific Configurations

### Development (8GB RAM)
```yaml
deploy:
  resources:
    limits:
      cpus: '1.0'
      memory: 1GB
    reservations:
      cpus: '0.25'
      memory: 256MB
```

### Development (16GB RAM)
```yaml
deploy:
  resources:
    limits:
      cpus: '2.0'
      memory: 2GB
    reservations:
      cpus: '0.5'
      memory: 512MB
```

### Development (32GB RAM)
```yaml
deploy:
  resources:
    limits:
      cpus: '4.0'
      memory: 4GB
    reservations:
      cpus: '1.0'
      memory: 1GB
```

## Monitoring and Alerting

### Resource Usage Thresholds
- **CPU Warning**: 70% of limit
- **CPU Critical**: 85% of limit
- **Memory Warning**: 80% of limit
- **Memory Critical**: 90% of limit
- **Disk Warning**: 85% of available space
- **Disk Critical**: 95% of available space

### Monitoring Tools
- Built-in Docker stats
- Resource usage monitoring script
- Container health checks
- System resource monitoring

## Optimization Guidelines

### CPU Optimization
1. **I/O Bound Services**: Lower CPU limits (Redis, MinIO)
2. **Compute Bound Services**: Higher CPU limits (Neo4j, Milvus)
3. **Application Services**: Balanced CPU allocation

### Memory Optimization
1. **Database Services**: Higher memory for caching
2. **Cache Services**: Moderate memory with efficient eviction
3. **Admin Tools**: Minimal memory allocation

### Disk I/O Optimization
1. **Database Services**: Higher I/O priority
2. **Log Services**: Lower I/O priority
3. **Temporary Services**: Minimal I/O allocation

## Troubleshooting

### Common Issues

#### Out of Memory (OOM) Kills
- **Symptoms**: Container restarts, memory limit exceeded
- **Solutions**: Increase memory limits, optimize application memory usage
- **Prevention**: Monitor memory usage trends

#### CPU Throttling
- **Symptoms**: Slow response times, high CPU wait times
- **Solutions**: Increase CPU limits, optimize CPU-intensive operations
- **Prevention**: Monitor CPU usage patterns

#### Disk Space Issues
- **Symptoms**: Container startup failures, write errors
- **Solutions**: Clean up logs, increase disk space, optimize storage
- **Prevention**: Regular disk cleanup, monitoring

### Resource Monitoring Commands

```bash
# Monitor all containers
docker stats

# Monitor specific container
docker stats multimodal-librarian-postgres-1

# Check resource limits
docker inspect <container_name> | jq '.HostConfig.Memory'

# System resource usage
python scripts/monitor-resource-usage.py --duration 5

# Container resource usage
docker system df
docker system prune
```

## Configuration Files

### Main Configuration
- `docker-compose.local.yml`: Primary resource configuration
- `.env.local`: Environment-specific overrides

### Monitoring Configuration
- `scripts/monitor-resource-usage.py`: Resource monitoring
- `scripts/optimize-resource-usage.py`: Resource optimization

### Validation Scripts
- `scripts/validate-resource-limits.py`: Validate configuration
- `scripts/test-resource-constraints.py`: Test resource limits

## Best Practices

1. **Start Conservative**: Begin with lower limits and increase as needed
2. **Monitor Continuously**: Use monitoring tools to track resource usage
3. **Test Under Load**: Validate limits under realistic workloads
4. **Document Changes**: Keep track of resource limit adjustments
5. **Environment Parity**: Maintain similar ratios across environments
6. **Regular Review**: Periodically review and optimize resource allocation

## Integration with Development Workflow

### Startup Sequence
1. Validate system resources
2. Apply resource limits
3. Start services in dependency order
4. Monitor resource usage
5. Alert on resource issues

### Development Commands
```bash
# Start with resource monitoring
make dev-with-monitoring

# Check resource usage
make resource-check

# Optimize resource usage
make resource-optimize

# Validate resource limits
make resource-validate
```