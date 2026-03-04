# Local Development Setup Guide

## Overview

This guide provides comprehensive instructions for setting up the Multimodal Librarian application for local development using Docker Compose. The local setup replaces AWS-native databases (Neptune, OpenSearch, RDS) with local alternatives (Neo4j, Milvus, PostgreSQL) while maintaining full functionality.

## Prerequisites

### System Requirements

- **Operating System**: macOS, Linux, or Windows with WSL2
- **Memory**: Minimum 8GB RAM (16GB recommended)
- **Storage**: 20GB free disk space
- **CPU**: Multi-core processor (4+ cores recommended)

### Required Software

1. **Docker Desktop** (v4.0+)
   ```bash
   # macOS (Homebrew)
   brew install --cask docker
   
   # Linux (Ubuntu/Debian)
   curl -fsSL https://get.docker.com -o get-docker.sh
   sudo sh get-docker.sh
   
   # Windows: Download from https://docker.com/products/docker-desktop
   ```

2. **Docker Compose** (v2.0+)
   ```bash
   # Usually included with Docker Desktop
   # Verify installation
   docker compose version
   ```

3. **Git** (for cloning repository)
   ```bash
   # macOS
   brew install git
   
   # Linux
   sudo apt-get install git
   ```

4. **Make** (for build automation)
   ```bash
   # macOS (included with Xcode Command Line Tools)
   xcode-select --install
   
   # Linux
   sudo apt-get install build-essential
   ```

## Quick Start (5-Minute Setup)

### 1. Clone and Navigate to Repository

```bash
git clone <repository-url>
cd multimodal-librarian
```

### 2. Initial Setup

```bash
# Run the automated setup
make dev-setup

# This will:
# - Copy .env.local.example to .env.local
# - Pull all required Docker images
# - Create necessary directories
```

### 3. Start Local Environment

```bash
# Start all services
make dev-local

# This will:
# - Start PostgreSQL, Neo4j, Milvus, and dependencies
# - Wait for all services to be healthy
# - Start the application
# - Display access URLs
```

### 4. Verify Setup

```bash
# Check service health
make status-local

# View logs
make logs-local
```

### 5. Access Services

- **Application**: http://localhost:8000
- **Neo4j Browser**: http://localhost:7474 (neo4j/ml_password)
- **pgAdmin**: http://localhost:5050 (admin@multimodal-librarian.com/admin)
- **Attu (Milvus)**: http://localhost:3000

## Detailed Setup Instructions

### Environment Configuration

#### 1. Environment Variables

Copy and customize the local environment file:

```bash
cp .env.local.example .env.local
```

Edit `.env.local` with your preferences:

```bash
# Database Type Selection
ML_ENVIRONMENT=local

# PostgreSQL Configuration
ML_POSTGRES_HOST=postgres
ML_POSTGRES_PORT=5432
ML_POSTGRES_DB=multimodal_librarian
ML_POSTGRES_USER=ml_user
ML_POSTGRES_PASSWORD=ml_password

# Neo4j Configuration
ML_NEO4J_HOST=neo4j
ML_NEO4J_PORT=7687
ML_NEO4J_USER=neo4j
ML_NEO4J_PASSWORD=ml_password

# Milvus Configuration
ML_MILVUS_HOST=milvus
ML_MILVUS_PORT=19530

# Application Configuration
ML_LOG_LEVEL=INFO
ML_DEBUG=true
ML_RELOAD=true
```

#### 2. Docker Compose Configuration

The `docker-compose.local.yml` file defines all services:

```yaml
# Key services included:
# - multimodal-librarian (main application)
# - postgres (PostgreSQL 15)
# - neo4j (Neo4j Community Edition)
# - milvus (Milvus standalone)
# - etcd, minio (Milvus dependencies)
# - pgadmin, attu (Administration tools)
```

### Service-by-Service Setup

#### PostgreSQL Setup

1. **Automatic Initialization**
   ```bash
   # Database is automatically initialized with:
   # - User: ml_user
   # - Database: multimodal_librarian
   # - Password: ml_password (configurable)
   ```

2. **Manual Database Operations**
   ```bash
   # Connect to PostgreSQL
   docker compose -f docker-compose.local.yml exec postgres psql -U ml_user -d multimodal_librarian
   
   # Run migrations
   make db-migrate-local
   
   # Seed sample data
   make db-seed-local
   ```

3. **pgAdmin Access**
   - URL: http://localhost:5050
   - Email: admin@multimodal-librarian.com
   - Password: admin

#### Neo4j Setup

1. **Automatic Configuration**
   ```bash
   # Neo4j starts with:
   # - User: neo4j
   # - Password: ml_password
   # - Plugins: GDS, APOC
   ```

2. **Browser Access**
   - URL: http://localhost:7474
   - Username: neo4j
   - Password: ml_password

3. **Sample Queries**
   ```cypher
   // Check connection
   RETURN "Hello Neo4j!" as message
   
   // View sample data (after seeding)
   MATCH (n) RETURN n LIMIT 10
   ```

#### Milvus Setup

1. **Service Dependencies**
   ```bash
   # Milvus requires:
   # - etcd (metadata storage)
   # - minio (object storage)
   # Both are automatically started
   ```

2. **Attu Administration**
   - URL: http://localhost:3000
   - Milvus Host: milvus:19530

3. **Collection Management**
   ```python
   # Collections are created automatically
   # Default collection: "documents" (384 dimensions)
   ```

### Development Workflow

#### Starting Development

```bash
# Full development environment
make dev-local

# Application only (assumes databases running)
make run

# With hot reload
make dev
```

#### Database Management

```bash
# Run migrations
make db-migrate-local

# Seed test data
make db-seed-local

# Reset databases
make db-reset-local

# Backup databases
make db-backup-local

# Restore from backup
make db-restore-local
```

#### Testing

```bash
# Run tests against local services
make test-local

# Run specific test suite
pytest tests/integration/test_local_setup.py

# Run with coverage
pytest --cov=multimodal_librarian tests/
```

#### Monitoring and Debugging

```bash
# View all service logs
make logs-local

# View specific service logs
docker compose -f docker-compose.local.yml logs -f postgres
docker compose -f docker-compose.local.yml logs -f neo4j
docker compose -f docker-compose.local.yml logs -f milvus

# Check service status
make status-local

# Monitor resource usage
make monitor-local
```

## Troubleshooting

### Common Issues

#### 1. Services Not Starting

**Problem**: Docker services fail to start

**Solutions**:
```bash
# Check Docker daemon
docker info

# Check available resources
docker system df

# Clean up resources
docker system prune -f

# Restart Docker Desktop
```

#### 2. Port Conflicts

**Problem**: Ports already in use

**Solutions**:
```bash
# Check port usage
lsof -i :5432  # PostgreSQL
lsof -i :7474  # Neo4j HTTP
lsof -i :7687  # Neo4j Bolt
lsof -i :19530 # Milvus

# Stop conflicting services or change ports in docker-compose.local.yml
```

#### 3. Database Connection Issues

**Problem**: Application can't connect to databases

**Solutions**:
```bash
# Check service health
docker compose -f docker-compose.local.yml ps

# Test database connections
scripts/health-check-postgresql.py
scripts/health-check-neo4j.py
scripts/health-check-milvus.py

# Restart specific service
docker compose -f docker-compose.local.yml restart postgres
```

#### 4. Memory Issues

**Problem**: System running out of memory

**Solutions**:
```bash
# Check memory usage
docker stats

# Reduce resource limits in docker-compose.local.yml
# Stop unnecessary services
docker compose -f docker-compose.local.yml stop pgadmin attu
```

#### 5. Data Persistence Issues

**Problem**: Data lost after container restart

**Solutions**:
```bash
# Check volume mounts
docker volume ls

# Verify volume configuration in docker-compose.local.yml
# Ensure volumes are properly defined and mounted
```

### Performance Optimization

#### 1. Database Tuning

**PostgreSQL**:
```bash
# Edit database/postgresql/postgresql.conf
shared_buffers = 256MB
effective_cache_size = 1GB
maintenance_work_mem = 64MB
```

**Neo4j**:
```bash
# Memory settings in docker-compose.local.yml
NEO4J_dbms_memory_heap_initial__size=512m
NEO4J_dbms_memory_heap_max__size=1G
NEO4J_dbms_memory_pagecache_size=512m
```

**Milvus**:
```bash
# Optimize for development workloads
# Reduce index building frequency
# Use smaller segment sizes
```

#### 2. Container Optimization

```bash
# Use multi-stage builds
# Optimize Docker layer caching
# Use .dockerignore effectively
```

#### 3. Development Workflow

```bash
# Use hot reload for faster development
# Implement incremental builds
# Cache dependencies effectively
```

### Health Checks and Monitoring

#### Service Health Endpoints

```bash
# Application health
curl http://localhost:8000/health/simple

# Database health
curl http://localhost:8000/health/databases

# Detailed health check
curl http://localhost:8000/health/detailed
```

#### Monitoring Commands

```bash
# Resource usage
make monitor-local

# Performance metrics
scripts/monitor-local-performance.py

# Database performance
scripts/monitor-database-performance.py
```

## Advanced Configuration

### Custom Database Configurations

#### PostgreSQL Custom Config

1. Edit `database/postgresql/postgresql.conf`
2. Restart PostgreSQL service
3. Verify changes with health checks

#### Neo4j Custom Config

1. Add environment variables to docker-compose.local.yml
2. Mount custom configuration files
3. Restart Neo4j service

#### Milvus Custom Config

1. Create custom milvus.yaml
2. Mount configuration in docker-compose.local.yml
3. Restart Milvus service

### Development vs Production Switching

#### Environment Switching

```bash
# Switch to local development
export ML_ENVIRONMENT=local
make dev-local

# Switch to AWS production
export ML_ENVIRONMENT=aws
make dev-aws
```

#### Configuration Management

```python
# Automatic environment detection
from multimodal_librarian.config import get_database_config

config = get_database_config()  # Automatically selects local or AWS
```

### CI/CD Integration

#### GitHub Actions

```yaml
# .github/workflows/local-testing.yml
name: Local Development Tests
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Start local services
        run: make dev-setup && make dev-local
      - name: Run tests
        run: make test-local
```

#### Local Testing Pipeline

```bash
# Full testing pipeline
make dev-setup
make dev-local
make test-local
make dev-teardown
```

## Migration from AWS

### Gradual Migration Strategy

1. **Phase 1**: Set up local environment alongside AWS
2. **Phase 2**: Test feature parity between environments
3. **Phase 3**: Switch development to local environment
4. **Phase 4**: Maintain AWS for production deployment

### Data Migration (Optional)

```bash
# Export data from AWS (if needed)
scripts/export-aws-data.py

# Import data to local environment
scripts/import-local-data.py

# Validate data integrity
scripts/validate-data-migration.py
```

## Maintenance and Updates

### Regular Maintenance

```bash
# Update Docker images
docker compose -f docker-compose.local.yml pull

# Clean up unused resources
docker system prune -f

# Update application dependencies
pip install -r requirements.txt
```

### Database Maintenance

```bash
# PostgreSQL maintenance
scripts/maintain-postgresql.py

# Neo4j maintenance
scripts/maintain-neo4j.py

# Milvus maintenance
scripts/maintain-milvus.py
```

### Backup Strategy

```bash
# Automated daily backups
scripts/setup-backup-cron.sh

# Manual backup
make backup-local

# Restore from backup
make restore-local
```

## Getting Help

### Documentation Resources

- [Configuration Guide](docs/configuration/README.md)
- [Troubleshooting Guide](docs/troubleshooting/local-development.md)
- [Performance Optimization](docs/performance/local-optimization.md)
- [API Documentation](docs/api/README.md)

### Support Channels

1. **GitHub Issues**: Report bugs and feature requests
2. **Documentation**: Check existing guides and tutorials
3. **Community**: Join development discussions

### Debugging Resources

```bash
# Debug scripts
scripts/debug/local-debug-cli.py
scripts/debug/database-debug-tool.py
scripts/debug/container-inspector.py

# Log analysis
scripts/debug/log-analyzer.py
scripts/debug/network-diagnostics.py
```

## Appendix

### Complete Command Reference

```bash
# Setup Commands
make dev-setup          # Initial setup
make dev-local          # Start local environment
make dev-teardown       # Stop and cleanup

# Development Commands
make run                # Run application only
make dev                # Run with hot reload
make test-local         # Run tests

# Database Commands
make db-migrate-local   # Run migrations
make db-seed-local      # Seed test data
make db-reset-local     # Reset databases
make db-backup-local    # Backup databases
make db-restore-local   # Restore databases

# Monitoring Commands
make status-local       # Check service status
make logs-local         # View all logs
make monitor-local      # Monitor resources
make health-local       # Check health

# Cleanup Commands
make clean-local        # Clean temporary files
make clean-docker       # Clean Docker resources
```

### Environment Variables Reference

| Variable | Default | Description |
|----------|---------|-------------|
| `ML_ENVIRONMENT` | `local` | Environment type (local/aws) |
| `ML_POSTGRES_HOST` | `postgres` | PostgreSQL hostname |
| `ML_POSTGRES_PORT` | `5432` | PostgreSQL port |
| `ML_POSTGRES_DB` | `multimodal_librarian` | Database name |
| `ML_POSTGRES_USER` | `ml_user` | Database user |
| `ML_POSTGRES_PASSWORD` | `ml_password` | Database password |
| `ML_NEO4J_HOST` | `neo4j` | Neo4j hostname |
| `ML_NEO4J_PORT` | `7687` | Neo4j Bolt port |
| `ML_NEO4J_USER` | `neo4j` | Neo4j username |
| `ML_NEO4J_PASSWORD` | `ml_password` | Neo4j password |
| `ML_MILVUS_HOST` | `milvus` | Milvus hostname |
| `ML_MILVUS_PORT` | `19530` | Milvus port |
| `ML_LOG_LEVEL` | `INFO` | Application log level |
| `ML_DEBUG` | `false` | Enable debug mode |
| `ML_RELOAD` | `false` | Enable hot reload |

### Service Ports Reference

| Service | Port | Protocol | Description |
|---------|------|----------|-------------|
| Application | 8000 | HTTP | Main application |
| PostgreSQL | 5432 | TCP | Database connection |
| Neo4j HTTP | 7474 | HTTP | Browser interface |
| Neo4j Bolt | 7687 | TCP | Database connection |
| Milvus | 19530 | TCP | Vector database |
| pgAdmin | 5050 | HTTP | PostgreSQL admin |
| Attu | 3000 | HTTP | Milvus admin |
| etcd | 2379 | TCP | Milvus metadata |
| MinIO | 9000 | HTTP | Milvus object storage |
| MinIO Console | 9001 | HTTP | MinIO admin |

This comprehensive setup guide provides everything needed to get started with local development of the Multimodal Librarian application. Follow the quick start for immediate setup, or use the detailed instructions for customized configurations.