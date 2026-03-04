# Local Development Setup

This guide explains how to set up the Multimodal Librarian for local development using Docker Compose with local database alternatives.

## Overview

The local development setup replaces AWS-native databases with local alternatives:
- **AWS Neptune** → **Neo4j Community Edition**
- **AWS OpenSearch** → **Milvus**
- **AWS RDS PostgreSQL** → **Local PostgreSQL**

## Prerequisites

- Docker and Docker Compose installed
- At least 8GB RAM available
- At least 20GB free disk space
- Network connectivity for Docker image downloads

## Quick Start

1. **Copy environment configuration:**
   ```bash
   cp .env.local.example .env.local
   ```

2. **Edit `.env.local`** and add your API keys:
   ```bash
   # Required for AI features
   OPENAI_API_KEY=your_openai_api_key_here
   GOOGLE_API_KEY=your_google_api_key_here
   GEMINI_API_KEY=your_gemini_api_key_here
   ```

3. **Start all services:**
   ```bash
   docker-compose -f docker-compose.local.yml up -d
   ```

4. **Wait for services to be ready:**
   ```bash
   ./scripts/wait-for-services.sh
   ```

5. **Access the application:**
   - Main application: http://localhost:8000
   - Neo4j Browser: http://localhost:7474 (neo4j/ml_password)
   - MinIO Console: http://localhost:9001 (minioadmin/minioadmin)

## Service Architecture

### Core Services
- **multimodal-librarian**: Main FastAPI application (port 8000)
- **postgres**: PostgreSQL 15 for metadata (port 5432)
- **neo4j**: Neo4j 5.15 for knowledge graph (ports 7474, 7687)
- **milvus**: Milvus 2.3.4 for vector search (port 19530)
- **redis**: Redis 7 for caching (port 6379)

### Supporting Services
- **etcd**: Metadata store for Milvus (port 2379)
- **minio**: Object storage for Milvus (ports 9000, 9001)

### Admin Tools (Optional)
Enable with `--profile admin-tools`:
```bash
docker-compose -f docker-compose.local.yml --profile admin-tools up -d
```

- **pgAdmin**: PostgreSQL administration (port 5050)
- **Attu**: Milvus administration (port 3000)
- **Redis Commander**: Redis administration (port 8081)

### Monitoring (Optional)
Enable with `--profile monitoring`:
```bash
docker-compose -f docker-compose.local.yml --profile monitoring up -d
```

- **Dozzle**: Docker log viewer (port 8080)

## Environment Configuration

The application uses environment-based configuration switching:

```python
# Automatically detected from ML_ENVIRONMENT=local
config = get_database_config()  # Returns LocalDatabaseConfig
```

### Key Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `ML_ENVIRONMENT` | `local` | Environment selection (local/aws) |
| `DATABASE_TYPE` | `local` | Database type selection |
| `ML_POSTGRES_HOST` | `localhost` | PostgreSQL host |
| `ML_NEO4J_HOST` | `localhost` | Neo4j host |
| `ML_MILVUS_HOST` | `localhost` | Milvus host |

## Development Workflow

### Starting Services
```bash
# Start all core services
docker-compose -f docker-compose.local.yml up -d

# Start with admin tools
docker-compose -f docker-compose.local.yml --profile admin-tools up -d

# Start with monitoring
docker-compose -f docker-compose.local.yml --profile monitoring up -d

# Start with all profiles
docker-compose -f docker-compose.local.yml --profile admin-tools --profile monitoring up -d
```

### Viewing Logs
```bash
# All services
docker-compose -f docker-compose.local.yml logs -f

# Specific service
docker-compose -f docker-compose.local.yml logs -f multimodal-librarian

# With Dozzle (if monitoring profile enabled)
# Visit http://localhost:8080
```

### Stopping Services
```bash
# Stop services (keep data)
docker-compose -f docker-compose.local.yml down

# Stop and remove volumes (delete all data)
docker-compose -f docker-compose.local.yml down -v
```

### Service Health Checks
```bash
# Check service status
docker-compose -f docker-compose.local.yml ps

# Wait for all services
./scripts/wait-for-services.sh

# Manual health checks
curl http://localhost:8000/health/simple  # Application
curl http://localhost:9091/healthz        # Milvus
```

## Database Access

### PostgreSQL
- **Host**: localhost:5432
- **Database**: multimodal_librarian
- **User**: ml_user
- **Password**: ml_password
- **Admin UI**: http://localhost:5050 (with admin-tools profile)

### Neo4j
- **Browser**: http://localhost:7474
- **Bolt**: bolt://localhost:7687
- **User**: neo4j
- **Password**: ml_password

### Milvus
- **gRPC**: localhost:19530
- **Admin UI**: http://localhost:3000 (with admin-tools profile)

### Redis
- **Host**: localhost:6379
- **Admin UI**: http://localhost:8081 (with admin-tools profile)

## Data Management

### Persistent Data
All data is stored in Docker volumes:
- `postgres_data`: PostgreSQL data
- `neo4j_data`: Neo4j graph data
- `milvus_data`: Milvus vector data
- `redis_data`: Redis cache data

### Backup Data
```bash
# Backup PostgreSQL
docker-compose -f docker-compose.local.yml exec postgres pg_dump -U ml_user multimodal_librarian > backup.sql

# Backup Neo4j (stop service first)
docker-compose -f docker-compose.local.yml stop neo4j
docker cp $(docker-compose -f docker-compose.local.yml ps -q neo4j):/data ./neo4j_backup
```

### Reset Data
```bash
# Remove all data and restart
docker-compose -f docker-compose.local.yml down -v
docker-compose -f docker-compose.local.yml up -d
```

## Performance Tuning

### Resource Limits
The configuration includes optimized settings for development:
- PostgreSQL: 256MB shared_buffers, 1GB effective_cache_size
- Neo4j: 1GB heap, 512MB page cache
- Milvus: Optimized for single-node deployment

### Memory Usage
Expected memory usage:
- PostgreSQL: ~200MB
- Neo4j: ~1.5GB
- Milvus: ~1GB
- Application: ~500MB
- Supporting services: ~300MB
- **Total**: ~3.5GB

## Troubleshooting

### Common Issues

1. **Services won't start**
   ```bash
   # Check Docker resources
   docker system df
   docker system prune  # Clean up if needed
   
   # Check logs
   docker-compose -f docker-compose.local.yml logs
   ```

2. **Out of memory**
   ```bash
   # Reduce Neo4j memory
   # Edit docker-compose.local.yml:
   # NEO4J_dbms_memory_heap_max__size=512m
   ```

3. **Port conflicts**
   ```bash
   # Check what's using ports
   lsof -i :8000  # Application
   lsof -i :5432  # PostgreSQL
   lsof -i :7474  # Neo4j HTTP
   lsof -i :7687  # Neo4j Bolt
   ```

4. **Database connection errors**
   ```bash
   # Wait for services
   ./scripts/wait-for-services.sh
   
   # Check service health
   docker-compose -f docker-compose.local.yml ps
   ```

### Getting Help

1. Check service logs: `docker-compose -f docker-compose.local.yml logs [service]`
2. Verify environment variables in `.env.local`
3. Ensure all required ports are available
4. Check Docker resources (memory, disk space)

## Switching Between Local and AWS

The application supports seamless switching between local and AWS environments:

```bash
# Use local databases
export ML_ENVIRONMENT=local
python -m src.multimodal_librarian.main

# Use AWS databases
export ML_ENVIRONMENT=aws
python -m src.multimodal_librarian.main
```

The database factory automatically selects the appropriate clients based on the environment configuration.