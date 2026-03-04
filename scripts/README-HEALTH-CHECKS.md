# Service Health Check Scripts

This directory contains comprehensive health check scripts for all local development services in the Multimodal Librarian project.

## Overview

The health check system provides detailed monitoring and diagnostics for:
- **PostgreSQL** - Relational database for metadata and configuration
- **Neo4j** - Graph database for knowledge graph operations
- **Milvus** - Vector database for semantic search and embeddings
- **Redis** - Cache and session storage

## Scripts

### Individual Service Health Checks

Each service has a dedicated health check script with comprehensive diagnostics:

- `health-check-postgresql.py` - PostgreSQL health monitoring
- `health-check-neo4j.py` - Neo4j health monitoring  
- `health-check-milvus.py` - Milvus health monitoring
- `health-check-redis.py` - Redis health monitoring

### Orchestration Scripts

- `health-check-all-services.py` - Orchestrates all service health checks
- `health-check-service.sh` - Convenient wrapper script for all functionality
- `health-check.sh` - Basic connectivity health checks (existing)
- `check-all-database-health.py` - Comprehensive database health checker (existing)

## Usage

### Quick Start

```bash
# Check all services
./scripts/health-check-service.sh all

# Check specific service
./scripts/health-check-service.sh postgresql

# Detailed check with full diagnostics
./scripts/health-check-service.sh detailed

# Show Docker Compose status
./scripts/health-check-service.sh status

# Continuous monitoring
./scripts/health-check-service.sh monitor
```

### Individual Service Checks

```bash
# PostgreSQL health check
python3 scripts/health-check-postgresql.py

# Neo4j health check  
python3 scripts/health-check-neo4j.py

# Milvus health check
python3 scripts/health-check-milvus.py

# Redis health check
python3 scripts/health-check-redis.py
```

### Advanced Usage

```bash
# JSON output for automation
./scripts/health-check-service.sh all --json

# Parallel execution for faster checks
./scripts/health-check-service.sh all --parallel

# Quiet mode for scripts
./scripts/health-check-service.sh all --quiet

# Custom timeout
./scripts/health-check-service.sh all --timeout 120
```

## Health Check Categories

### PostgreSQL Checks
- **Connectivity** - Basic database connection
- **Database Size** - Storage usage monitoring
- **Connections** - Active connection monitoring
- **Extensions** - Required PostgreSQL extensions
- **Performance Stats** - Query performance metrics
- **Replication** - Replication lag (if applicable)
- **Locks** - Blocking lock detection

### Neo4j Checks
- **Connectivity** - Basic graph database connection
- **Version** - Neo4j version and edition
- **APOC Plugin** - APOC plugin availability and functionality
- **GDS Plugin** - Graph Data Science plugin status
- **Database Stats** - Node and relationship counts
- **Memory Usage** - Heap and memory configuration
- **Query Performance** - Query execution performance

### Milvus Checks
- **Connectivity** - Basic vector database connection
- **Server Info** - Milvus version and server type
- **Dependencies** - etcd and MinIO health status
- **Collection Ops** - Collection creation and management
- **Index Ops** - Index creation and optimization
- **Data Ops** - Data insertion and retrieval
- **Search Ops** - Vector similarity search
- **Performance** - Search performance metrics

### Redis Checks
- **Connectivity** - Basic cache connection
- **Server Info** - Redis version and configuration
- **Memory Usage** - Memory consumption monitoring
- **Client Connections** - Connected client monitoring
- **Keyspace Info** - Database and key statistics
- **Persistence Config** - AOF and RDB configuration
- **Performance Stats** - Operations and hit rate metrics
- **Basic Operations** - SET/GET/DELETE functionality

## Output Formats

### Human-Readable Output
```
============================================================
PostgreSQL Health Check Results
============================================================
Overall Status: ✅ OK
Duration: 2.34s
Timestamp: 2024-01-23T15:30:45.123456

Connection: localhost:5432/multimodal_librarian (user: ml_user)

Check Results:
  ✅ Connectivity: PostgreSQL connection successful (45.2ms)
  ✅ Database Size: Database size: 12MB (23.1ms)
  ✅ Connections: Connections: 5/100 (5.0%) (18.7ms)
  ✅ Extensions: All 6 required extensions installed (31.4ms)
  ⚠️  Performance: Avg query time: 15.2ms (89.3ms)
  ℹ️  Replication: Not a replica server (12.1ms)
  ✅ Locks: No waiting locks (8 total locks) (19.8ms)

Summary: 5 OK, 1 Warning, 0 Critical, 1 Info
```

### JSON Output
```json
{
  "service": "postgresql",
  "status": "OK",
  "message": "PostgreSQL health check completed (OK)",
  "timestamp": "2024-01-23T15:30:45.123456",
  "duration_seconds": 2.34,
  "connection_info": {
    "host": "localhost",
    "port": 5432,
    "database": "multimodal_librarian",
    "user": "ml_user"
  },
  "checks": {
    "connectivity": {
      "status": "OK",
      "message": "PostgreSQL connection successful",
      "duration_ms": 45.2,
      "details": {
        "version": "15.5",
        "database": "multimodal_librarian",
        "user": "ml_user",
        "server_time": "2024-01-23T15:30:45.123456"
      }
    }
  },
  "summary": {
    "total_checks": 7,
    "ok": 5,
    "warning": 1,
    "critical": 0,
    "info": 1
  }
}
```

## Exit Codes

- `0` - All checks passed (OK status)
- `1` - Some checks have warnings (WARNING status)
- `2` - Critical issues detected (CRITICAL status)

## Environment Variables

All health check scripts support environment variable configuration:

### PostgreSQL
- `POSTGRES_HOST` - Database host (default: localhost)
- `POSTGRES_PORT` - Database port (default: 5432)
- `POSTGRES_DB` - Database name (default: multimodal_librarian)
- `POSTGRES_USER` - Database user (default: ml_user)
- `POSTGRES_PASSWORD` - Database password (default: ml_password)

### Neo4j
- `NEO4J_URI` - Neo4j URI (default: bolt://localhost:7687)
- `NEO4J_USER` - Neo4j user (default: neo4j)
- `NEO4J_PASSWORD` - Neo4j password (default: ml_password)

### Milvus
- `MILVUS_HOST` - Milvus host (default: localhost)
- `MILVUS_PORT` - Milvus port (default: 19530)

### Redis
- `REDIS_HOST` - Redis host (default: localhost)
- `REDIS_PORT` - Redis port (default: 6379)
- `REDIS_DB` - Redis database number (default: 0)

## Dependencies

### Required Python Packages
- `psycopg2` - PostgreSQL connectivity (optional, falls back to basic checks)
- `neo4j` - Neo4j connectivity (optional, falls back to basic checks)
- `pymilvus` - Milvus connectivity (optional, falls back to basic checks)
- `redis` - Redis connectivity (optional, falls back to basic checks)

### System Dependencies
- `curl` - For HTTP health endpoint checks
- `docker-compose` or `docker compose` - For service status checks
- `pg_isready` - For basic PostgreSQL connectivity (optional)
- `cypher-shell` - For basic Neo4j connectivity (optional)
- `redis-cli` - For basic Redis connectivity (optional)

## Integration with Development Workflow

### Makefile Integration
Add these targets to your Makefile:

```makefile
# Health check targets
.PHONY: health health-quick health-detailed health-monitor

health:
	@./scripts/health-check-service.sh all

health-quick:
	@./scripts/health-check-service.sh quick

health-detailed:
	@./scripts/health-check-service.sh detailed

health-monitor:
	@./scripts/health-check-service.sh monitor

health-postgresql:
	@./scripts/health-check-service.sh postgresql

health-neo4j:
	@./scripts/health-check-service.sh neo4j

health-milvus:
	@./scripts/health-check-service.sh milvus

health-redis:
	@./scripts/health-check-service.sh redis
```

### CI/CD Integration
```yaml
# Example GitHub Actions workflow step
- name: Health Check Services
  run: |
    ./scripts/health-check-service.sh all --json > health-results.json
    ./scripts/health-check-service.sh all --quiet
```

### Docker Compose Integration
Add health check commands to your docker-compose.local.yml:

```yaml
services:
  multimodal-librarian:
    healthcheck:
      test: ["CMD", "python3", "/app/scripts/health-check-postgresql.py", "--quiet"]
      interval: 30s
      timeout: 10s
      retries: 3
```

## Troubleshooting

### Common Issues

1. **Connection Refused**
   - Ensure services are running: `./scripts/health-check-service.sh status`
   - Check Docker Compose: `docker-compose -f docker-compose.local.yml ps`

2. **Permission Denied**
   - Make scripts executable: `chmod +x scripts/health-check-*.py scripts/health-check-service.sh`

3. **Module Not Found**
   - Install required packages: `pip install psycopg2 neo4j pymilvus redis`
   - Scripts will fall back to basic checks if packages are missing

4. **Timeout Errors**
   - Increase timeout: `--timeout 120`
   - Check service logs: `docker-compose -f docker-compose.local.yml logs [service]`

### Debug Mode
Enable verbose output for debugging:

```bash
# Individual service debug
python3 scripts/health-check-postgresql.py --json | jq .

# All services debug
./scripts/health-check-service.sh detailed --json | jq .
```

## Contributing

When adding new health checks:

1. Follow the existing pattern for status codes: OK, WARNING, CRITICAL, INFO
2. Include duration measurements for all checks
3. Provide both human-readable and JSON output formats
4. Add comprehensive error handling and fallback mechanisms
5. Update this README with new functionality

## Related Files

- `scripts/wait-for-services.sh` - Service readiness checker
- `scripts/health-check.sh` - Basic connectivity health checks
- `scripts/check-all-database-health.py` - Comprehensive database health checker
- `docker-compose.local.yml` - Local development service definitions
- `.env.local.example` - Environment variable template