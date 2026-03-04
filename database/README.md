# Database Health Checks

This directory contains comprehensive health check implementations for all database services used in the local development environment.

## Overview

The local development environment uses the following database services:
- **PostgreSQL 15** - Relational database for metadata and configuration
- **Neo4j 5.15** - Graph database for knowledge graph operations
- **Milvus 2.3.4** - Vector database for semantic search and embeddings
- **Redis 7** - Cache and session storage
- **etcd 3.5.5** - Metadata storage for Milvus
- **MinIO** - Object storage for Milvus

## Health Check Components

### 1. Docker Compose Health Checks

Each service in `docker-compose.local.yml` has comprehensive health checks:

```yaml
# PostgreSQL - Advanced SQL-based health check
healthcheck:
  test: ["CMD-SHELL", "pg_isready -U ml_user -d multimodal_librarian && psql -U ml_user -d multimodal_librarian -f /etc/postgresql/health_check.sql -t -A -F'|' | head -1 | grep -q 'OK\\|INFO'"]
  interval: 30s
  timeout: 15s
  retries: 5
  start_period: 60s

# Neo4j - Connectivity + plugin verification
healthcheck:
  test: ["CMD-SHELL", "cypher-shell -u neo4j -p ml_password 'RETURN 1 as status' && cypher-shell -u neo4j -p ml_password 'CALL apoc.version() YIELD version RETURN version LIMIT 1' && cypher-shell -u neo4j -p ml_password 'CALL gds.version() YIELD version RETURN version LIMIT 1'"]
  interval: 30s
  timeout: 20s
  retries: 5
  start_period: 90s

# Milvus - HTTP health + API health
healthcheck:
  test: ["CMD-SHELL", "curl -f http://localhost:9091/healthz && curl -f http://localhost:9091/api/v1/health"]
  interval: 30s
  timeout: 20s
  retries: 3
  start_period: 90s
```

### 2. Service-Specific Health Check Scripts

#### PostgreSQL (`database/postgresql/`)
- `health_check.sql` - Comprehensive SQL health check script
- `manage.sh` - Management script with health check functionality
- `validate_setup.py` - Setup validation script

#### Neo4j (`database/neo4j/`)
- `health_check.cypher` - Comprehensive Cypher health check script
- `manage.sh` - Management script with health check functionality
- `wait-for-neo4j.sh` - Service readiness script
- `validate_setup.py` - Setup validation script

#### Milvus (`database/milvus/`)
- `health_check.py` - Comprehensive Python health check script
- `manage.sh` - Management script with health check functionality
- `wait-for-milvus.sh` - Service readiness script
- `validate_setup.py` - Setup validation script

### 3. Comprehensive Health Check Scripts

#### `scripts/check-all-database-health.py`
Comprehensive health checker for all database services:

```bash
# Check all services
python scripts/check-all-database-health.py

# Check specific services
python scripts/check-all-database-health.py --services postgresql,neo4j

# JSON output
python scripts/check-all-database-health.py --json

# Quiet mode (summary only)
python scripts/check-all-database-health.py --quiet
```

Features:
- Async concurrent health checks
- Detailed performance metrics
- Graceful degradation when Python clients unavailable
- Comprehensive error reporting
- JSON and human-readable output formats

#### `scripts/wait-for-all-databases.sh`
Service readiness orchestration script:

```bash
# Wait for all services with defaults
./scripts/wait-for-all-databases.sh

# Custom timeout and interval
./scripts/wait-for-all-databases.sh --timeout 600 --interval 10

# Custom compose file
./scripts/wait-for-all-databases.sh --file docker-compose.prod.yml
```

Features:
- Dependency-aware startup ordering
- Docker health check integration
- Comprehensive error reporting
- Troubleshooting guidance

## Health Check Categories

### 1. Connectivity Tests
- Basic network connectivity
- Authentication verification
- Protocol-specific handshakes

### 2. Functional Tests
- Basic CRUD operations
- Query execution
- Index operations (where applicable)

### 3. Performance Tests
- Query response times
- Resource utilization
- Connection pooling

### 4. Configuration Tests
- Required extensions/plugins
- Memory settings
- Security configuration

### 5. Data Integrity Tests
- Schema validation
- Constraint verification
- Index consistency

## Makefile Integration

The health check system is integrated into the Makefile:

```bash
# Comprehensive health check
make health

# Service-specific checks
make health-postgres
make health-neo4j
make health-milvus
make health-redis

# Output formats
make health-json
make health-quiet

# Service management
make db-status
make wait-for-databases
```

## Health Check Status Codes

### Status Levels
- **OK** - Service is healthy and performing normally
- **INFO** - Informational status (version, statistics, etc.)
- **WARNING** - Service is functional but has minor issues
- **CRITICAL** - Service is not functional or has major issues

### Exit Codes
- `0` - All services healthy
- `1` - Some services have warnings
- `2` - Some services are critical/failed

## Troubleshooting

### Common Issues

#### PostgreSQL
```bash
# Check if service is running
docker-compose -f docker-compose.local.yml ps postgres

# View logs
docker-compose -f docker-compose.local.yml logs postgres

# Manual health check
./database/postgresql/manage.sh health

# Connection test
pg_isready -h localhost -p 5432 -U ml_user -d multimodal_librarian
```

#### Neo4j
```bash
# Check service status
docker-compose -f docker-compose.local.yml ps neo4j

# View logs
docker-compose -f docker-compose.local.yml logs neo4j

# Manual health check
./database/neo4j/manage.sh health

# Connection test
cypher-shell -a bolt://localhost:7687 -u neo4j -p ml_password "RETURN 1"
```

#### Milvus
```bash
# Check service status
docker-compose -f docker-compose.local.yml ps milvus etcd minio

# View logs
docker-compose -f docker-compose.local.yml logs milvus

# Manual health check
./database/milvus/manage.sh health

# HTTP health check
curl -f http://localhost:9091/healthz
```

#### Redis
```bash
# Check service status
docker-compose -f docker-compose.local.yml ps redis

# Connection test
redis-cli -h localhost -p 6379 ping
```

### Performance Issues

#### Memory Usage
```bash
# Check container memory usage
docker stats --no-stream

# PostgreSQL memory settings
docker-compose -f docker-compose.local.yml exec postgres psql -U ml_user -d multimodal_librarian -c "SHOW shared_buffers; SHOW effective_cache_size;"

# Neo4j memory settings
docker-compose -f docker-compose.local.yml exec neo4j cypher-shell -u neo4j -p ml_password "CALL dbms.queryJvm('java.lang:type=Memory') YIELD attributes RETURN attributes.HeapMemoryUsage"
```

#### Disk Space
```bash
# Check disk usage
df -h

# Database sizes
docker-compose -f docker-compose.local.yml exec postgres psql -U ml_user -d multimodal_librarian -c "SELECT pg_size_pretty(pg_database_size(current_database()))"
```

### Network Issues
```bash
# Check port availability
netstat -tlnp | grep -E ':(5432|7474|7687|19530|6379|2379|9000)'

# Test connectivity
telnet localhost 5432
telnet localhost 7687
telnet localhost 19530
telnet localhost 6379
```

## Development Workflow

### Starting Development Environment
```bash
# Start all services
make dev-local

# Wait for services to be ready
make wait-for-databases

# Check health
make health
```

### Daily Health Monitoring
```bash
# Quick status check
make db-status

# Comprehensive health check
make health

# Service-specific checks
make health-postgres
make health-neo4j
```

### Debugging Issues
```bash
# View service logs
make logs

# Check specific service
docker-compose -f docker-compose.local.yml logs [service_name]

# Run individual health checks
./database/postgresql/manage.sh health
./database/neo4j/manage.sh health
./database/milvus/manage.sh health
```

## Configuration

### Environment Variables
Health checks respect the following environment variables:

```bash
# PostgreSQL
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_USER=ml_user
POSTGRES_PASSWORD=ml_password
POSTGRES_DB=multimodal_librarian

# Neo4j
NEO4J_HOST=localhost
NEO4J_PORT=7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=ml_password

# Milvus
MILVUS_HOST=localhost
MILVUS_PORT=19530
MILVUS_HTTP_PORT=9091

# Redis
REDIS_HOST=localhost
REDIS_PORT=6379

# Health check timing
MAX_WAIT_TIME=300
CHECK_INTERVAL=5
```

### Customization
Health check scripts can be customized by:
1. Modifying service-specific health check files
2. Adjusting Docker health check parameters
3. Setting environment variables
4. Creating custom health check scripts

## Best Practices

### Development
1. Always run `make wait-for-databases` before starting development
2. Use `make health` to verify system state
3. Monitor logs during development: `make logs`
4. Use service-specific health checks for debugging

### Production
1. Implement monitoring based on health check scripts
2. Set up alerting for critical health check failures
3. Use health checks in deployment pipelines
4. Regular health check scheduling

### Maintenance
1. Review health check logs regularly
2. Update health check thresholds based on usage patterns
3. Add new health checks for custom functionality
4. Keep health check scripts updated with service versions

## Integration with CI/CD

Health checks can be integrated into CI/CD pipelines:

```yaml
# Example GitHub Actions step
- name: Wait for databases
  run: ./scripts/wait-for-all-databases.sh --timeout 300

- name: Run health checks
  run: python scripts/check-all-database-health.py --json > health-report.json

- name: Upload health report
  uses: actions/upload-artifact@v2
  with:
    name: health-report
    path: health-report.json
```

This comprehensive health check system ensures reliable database operations in the local development environment and provides the foundation for production monitoring and alerting.