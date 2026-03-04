# Networking and Service Discovery for Local Development

This document describes the networking and service discovery setup for the Multimodal Librarian local development environment.

## Overview

The local development environment uses Docker Compose with a custom bridge network to provide:

- **Service Discovery**: Automatic discovery and health monitoring of all services
- **Network Isolation**: Dedicated network for development services
- **Health Monitoring**: Comprehensive health checks and monitoring
- **Troubleshooting**: Network diagnostics and connectivity testing

## Network Configuration

### Custom Bridge Network

The development environment uses a custom Docker bridge network:

- **Name**: `multimodal-librarian-local`
- **Subnet**: `172.21.0.0/16`
- **Gateway**: `172.21.0.1`
- **Driver**: `bridge`

### Network Features

- **Service Discovery**: Containers can communicate using service names
- **DNS Resolution**: Automatic DNS resolution for container names
- **Port Mapping**: Host ports mapped to container ports for external access
- **Health Checks**: Built-in health checks for all services

## Service Discovery

### Automatic Service Discovery

The service discovery system automatically:

1. **Discovers Services**: Finds all containers in the network
2. **Health Monitoring**: Continuously monitors service health
3. **Dependency Tracking**: Manages service dependencies and startup order
4. **Status Reporting**: Provides real-time status updates

### Service Discovery Tools

#### 1. Service Discovery Script

```bash
# Basic service discovery
python3 scripts/service-discovery.py

# Wait for all services to be ready
python3 scripts/service-discovery.py --wait --timeout 300

# Check specific services
python3 scripts/service-discovery.py --services postgres,neo4j,redis

# Export service information
python3 scripts/service-discovery.py --export json --output services.json
```

#### 2. Health Monitor

```bash
# Continuous health monitoring
python3 scripts/health-monitor.py

# One-time health check
python3 scripts/health-monitor.py --one-shot

# Custom check interval
python3 scripts/health-monitor.py --interval 60

# Export health report
python3 scripts/health-monitor.py --export health-report.json
```

#### 3. Network Configuration

```bash
# Show network information
python3 scripts/network-config.py info

# List all networks
python3 scripts/network-config.py list

# Create development network
python3 scripts/network-config.py create

# Remove development network
python3 scripts/network-config.py remove

# Diagnose connectivity
python3 scripts/network-config.py diagnose
```

#### 4. Network Troubleshooting

```bash
# Full network diagnosis
python3 scripts/network-troubleshoot.py

# Export diagnosis report
python3 scripts/network-troubleshoot.py --export diagnosis.json

# Verbose output
python3 scripts/network-troubleshoot.py --verbose
```

## Service Configuration

### Core Services

| Service | Container | Ports | Health Check | Dependencies |
|---------|-----------|-------|--------------|--------------|
| Application | multimodal-librarian | 8000 | HTTP /health/simple | postgres, neo4j, milvus, redis |
| PostgreSQL | postgres | 5432 | pg_isready | - |
| Neo4j | neo4j | 7474, 7687 | cypher-shell | - |
| Redis | redis | 6379 | redis-cli ping | - |
| Milvus | milvus | 19530, 9091 | HTTP /healthz | etcd, minio |
| etcd | etcd | 2379 | HTTP /health | - |
| MinIO | minio | 9000, 9001 | HTTP /minio/health/live | - |

### Admin Tools (Optional)

| Service | Container | Ports | Profile | Dependencies |
|---------|-----------|-------|---------|--------------|
| pgAdmin | pgadmin | 5050 | admin-tools | postgres |
| Attu | attu | 3000 | admin-tools | milvus |
| Redis Commander | redis-commander | 8081 | admin-tools | redis |

### Monitoring Tools (Optional)

| Service | Container | Ports | Profile | Dependencies |
|---------|-----------|-------|---------|--------------|
| Dozzle | log-viewer | 8080 | monitoring | - |

## Health Checks

### Health Check Types

1. **HTTP Health Checks**: For services with HTTP endpoints
   - Application: `GET /health/simple`
   - Milvus: `GET /healthz`
   - etcd: `GET /health`
   - MinIO: `GET /minio/health/live`

2. **Command Health Checks**: For database services
   - PostgreSQL: `pg_isready -U ml_user -d multimodal_librarian`
   - Neo4j: `cypher-shell -u neo4j -p ml_password 'RETURN 1'`
   - Redis: `redis-cli ping`

### Health Check Configuration

```yaml
health_checks:
  global_timeout: 300  # seconds
  check_interval: 30   # seconds
  max_retries: 5
  parallel_checks: true
  
  alerts:
    consecutive_failures: 3
    failure_rate_window: 300  # 5 minutes
    max_failure_rate: 0.5     # 50%
```

## Makefile Integration

### Network Commands

```bash
# Show network information
make network-info

# Diagnose network issues
make network-diagnose

# Create development network
make network-create

# Remove development network
make network-remove
```

### Service Discovery Commands

```bash
# Run service discovery
make service-discovery

# Start health monitoring
make service-monitor

# Wait for services
make wait-for-services

# Check service health
make health
```

### Development Workflow

```bash
# Start local development (includes service discovery)
make dev-local

# Monitor services
make monitor

# View logs
make logs

# Stop services
make down
```

## Troubleshooting

### Common Issues

#### 1. Network Not Found

**Symptoms**: Services cannot communicate, network errors

**Solution**:
```bash
# Check if network exists
make network-info

# Create network if missing
make network-create

# Restart services
make down && make dev-local
```

#### 2. Service Communication Failures

**Symptoms**: Services cannot reach each other

**Solution**:
```bash
# Diagnose network connectivity
make network-diagnose

# Check service health
make health

# Restart problematic services
docker-compose -f docker-compose.local.yml restart <service-name>
```

#### 3. Port Conflicts

**Symptoms**: Cannot bind to port, port already in use

**Solution**:
```bash
# Check what's using the port
lsof -i :8000

# Stop conflicting services
# Update port mappings in docker-compose.local.yml if needed
```

#### 4. DNS Resolution Issues

**Symptoms**: Cannot resolve service names

**Solution**:
```bash
# Check DNS resolution
python3 scripts/network-troubleshoot.py

# Restart Docker daemon if needed
sudo systemctl restart docker  # Linux
# or restart Docker Desktop
```

### Diagnostic Commands

```bash
# Full network diagnosis
python3 scripts/network-troubleshoot.py --export diagnosis.json

# Check specific service
docker-compose -f docker-compose.local.yml exec <service> <command>

# View network details
docker network inspect multimodal-librarian-local

# Check container connectivity
docker-compose -f docker-compose.local.yml exec multimodal-librarian ping postgres
```

## Configuration Files

### Service Discovery Configuration

Location: `config/service-discovery.yaml`

Contains:
- Service definitions and health checks
- Network configuration
- Alert thresholds
- Troubleshooting settings

### Docker Compose Network Configuration

Location: `docker-compose.local.yml`

```yaml
networks:
  ml-local-network:
    name: multimodal-librarian-local
    driver: bridge
    ipam:
      driver: default
      config:
        - subnet: 172.21.0.0/16
          gateway: 172.21.0.1
    driver_opts:
      com.docker.network.bridge.name: ml-local-br0
      com.docker.network.bridge.enable_icc: "true"
      com.docker.network.bridge.enable_ip_masquerade: "true"
      com.docker.network.driver.mtu: 1500
    labels:
      - "multimodal-librarian.network.type=local-development"
      - "multimodal-librarian.network.environment=local"
```

## Requirements

### Python Dependencies

Install development tools requirements:

```bash
pip install -r requirements-dev-tools.txt
```

Required packages:
- `docker>=6.1.0` - Docker API client
- `aiohttp>=3.8.0` - Async HTTP client
- `PyYAML>=6.0` - YAML configuration parsing

### System Requirements

- Docker and Docker Compose
- Python 3.8+
- Network tools (ping, netcat, nslookup)

## Best Practices

### Service Startup

1. **Use Dependency Order**: Services start in dependency order
2. **Wait for Health**: Always wait for services to be healthy
3. **Monitor Startup**: Use health monitoring during startup

### Network Management

1. **Use Service Names**: Always use service names for inter-service communication
2. **Check Health**: Regularly check service health
3. **Monitor Network**: Use network monitoring for issues

### Troubleshooting

1. **Start with Basics**: Check network existence and service status
2. **Use Diagnostics**: Run comprehensive diagnostics for complex issues
3. **Check Logs**: Always check service logs for errors

## Security Considerations

### Development Only

- Default credentials are for development only
- Network is isolated but not secured for production
- Admin tools should not be exposed in production

### Network Isolation

- Services communicate within isolated Docker network
- Host ports are mapped only for necessary services
- Admin tools are on separate profiles

## Performance Considerations

### Resource Limits

- Services have appropriate resource limits
- Network MTU optimized for local development
- Health check intervals balanced for responsiveness

### Monitoring Overhead

- Health checks are lightweight
- Monitoring can be disabled if not needed
- Export capabilities for analysis

This networking and service discovery setup provides a robust foundation for local development with comprehensive monitoring and troubleshooting capabilities.