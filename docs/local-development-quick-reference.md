# Local Development Quick Reference

## Essential Commands

### Setup and Startup
```bash
make dev-setup          # Initial setup (run once)
make dev-local          # Start all services
make dev-teardown       # Stop and cleanup
make status-local       # Check service status
```

### Development
```bash
make run                # Run application only
make dev                # Run with hot reload
make test-local         # Run tests
make logs-local         # View all logs
```

### Database Management
```bash
make db-migrate-local   # Run migrations
make db-seed-local      # Seed test data
make db-reset-local     # Reset databases
make db-backup-local    # Backup databases
```

## Service URLs

| Service | URL | Credentials |
|---------|-----|-------------|
| Application | http://localhost:8000 | - |
| Neo4j Browser | http://localhost:7474 | neo4j/ml_password |
| pgAdmin | http://localhost:5050 | admin@multimodal-librarian.com/admin |
| Attu (Milvus) | http://localhost:3000 | - |

## Health Check Endpoints

```bash
# Application health
curl http://localhost:8000/health/simple

# Database health
curl http://localhost:8000/health/databases

# Detailed health
curl http://localhost:8000/health/detailed
```

## Environment Variables

```bash
# Core configuration
ML_ENVIRONMENT=local
ML_DEBUG=true
ML_LOG_LEVEL=INFO

# Database connections
ML_POSTGRES_HOST=postgres
ML_NEO4J_HOST=neo4j
ML_MILVUS_HOST=milvus
```

## Troubleshooting Commands

```bash
# Check Docker status
docker info
docker compose -f docker-compose.local.yml ps

# Service logs
docker compose -f docker-compose.local.yml logs -f [service]

# Resource monitoring
docker stats
make monitor-local

# Health checks
scripts/health-check-postgresql.py
scripts/health-check-neo4j.py
scripts/health-check-milvus.py
```

## Common File Locations

```
.env.local                          # Environment configuration
docker-compose.local.yml            # Service definitions
src/multimodal_librarian/           # Application code
tests/                              # Test suite
database/                           # Database initialization
scripts/                            # Utility scripts
docs/                              # Documentation
```

## Port Reference

| Service | Port | Protocol |
|---------|------|----------|
| Application | 8000 | HTTP |
| PostgreSQL | 5432 | TCP |
| Neo4j HTTP | 7474 | HTTP |
| Neo4j Bolt | 7687 | TCP |
| Milvus | 19530 | TCP |
| pgAdmin | 5050 | HTTP |
| Attu | 3000 | HTTP |