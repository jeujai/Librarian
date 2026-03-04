# Environment Variables Reference

This document provides a comprehensive reference for all environment variables used in the Multimodal Librarian local development conversion.

## Variable Naming Convention

All configuration variables use the `ML_` prefix to avoid conflicts with system variables:
- `ML_POSTGRES_HOST` - PostgreSQL host
- `ML_NEO4J_PORT` - Neo4j port
- `ML_ENABLE_VECTOR_SEARCH` - Enable vector search feature

## Environment Variables by Category

### Environment Control

| Variable | Type | Default | Description | Example |
|----------|------|---------|-------------|---------|
| `ML_ENVIRONMENT` | string | `"local"` | Environment name | `development`, `staging`, `production` |
| `ML_DATABASE_TYPE` | string | `"local"` | Database backend type | `local`, `aws` |
| `DATABASE_TYPE` | string | `"local"` | Alternative database type variable | `local`, `aws` |

### PostgreSQL Configuration

| Variable | Type | Default | Description | Example |
|----------|------|---------|-------------|---------|
| `ML_POSTGRES_HOST` | string | `"localhost"` | PostgreSQL host | `postgres`, `localhost`, `192.168.1.100` |
| `ML_POSTGRES_PORT` | int | `5432` | PostgreSQL port | `5432`, `5433` |
| `ML_POSTGRES_DB` | string | `"multimodal_librarian"` | Database name | `multimodal_librarian`, `ml_dev` |
| `ML_POSTGRES_USER` | string | `"ml_user"` | Username | `ml_user`, `postgres` |
| `ML_POSTGRES_PASSWORD` | string | `"ml_password"` | Password | `secure_password_123!` |
| `ML_POSTGRES_POOL_SIZE` | int | `10` | Connection pool size | `5`, `20` |
| `ML_POSTGRES_MAX_OVERFLOW` | int | `20` | Max overflow connections | `10`, `40` |
| `ML_POSTGRES_POOL_RECYCLE` | int | `3600` | Pool recycle time (seconds) | `1800`, `7200` |

**Alternative Variable Names** (for compatibility):
- `POSTGRES_HOST` → `ML_POSTGRES_HOST`
- `POSTGRES_PORT` → `ML_POSTGRES_PORT`
- `POSTGRES_DB` → `ML_POSTGRES_DB`
- `POSTGRES_USER` → `ML_POSTGRES_USER`
- `POSTGRES_PASSWORD` → `ML_POSTGRES_PASSWORD`

### Neo4j Configuration

| Variable | Type | Default | Description | Example |
|----------|------|---------|-------------|---------|
| `ML_NEO4J_HOST` | string | `"localhost"` | Neo4j host | `neo4j`, `localhost` |
| `ML_NEO4J_PORT` | int | `7687` | Neo4j Bolt port | `7687`, `7688` |
| `ML_NEO4J_HTTP_PORT` | int | `7474` | Neo4j HTTP port | `7474`, `7475` |
| `ML_NEO4J_USER` | string | `"neo4j"` | Username | `neo4j`, `admin` |
| `ML_NEO4J_PASSWORD` | string | `"ml_password"` | Password | `secure_neo4j_pass!` |
| `ML_NEO4J_POOL_SIZE` | int | `100` | Connection pool size | `50`, `200` |
| `ML_NEO4J_MAX_CONNECTION_LIFETIME` | int | `3600` | Max connection lifetime (seconds) | `1800`, `7200` |

**Alternative Variable Names**:
- `NEO4J_HOST` → `ML_NEO4J_HOST`
- `NEO4J_PORT` → `ML_NEO4J_PORT`
- `NEO4J_USER` → `ML_NEO4J_USER`
- `NEO4J_PASSWORD` → `ML_NEO4J_PASSWORD`
- `NEO4J_URI` → Constructed from host/port

### Milvus Configuration

| Variable | Type | Default | Description | Example |
|----------|------|---------|-------------|---------|
| `ML_MILVUS_HOST` | string | `"localhost"` | Milvus host | `milvus`, `localhost` |
| `ML_MILVUS_PORT` | int | `19530` | Milvus port | `19530`, `19531` |
| `ML_MILVUS_USER` | string | `""` | Username (optional) | `milvus_user` |
| `ML_MILVUS_PASSWORD` | string | `""` | Password (optional) | `milvus_pass` |
| `ML_MILVUS_DEFAULT_COLLECTION` | string | `"documents"` | Default collection name | `documents`, `knowledge_chunks` |
| `ML_MILVUS_INDEX_TYPE` | string | `"IVF_FLAT"` | Index type | `IVF_FLAT`, `HNSW` |
| `ML_MILVUS_METRIC_TYPE` | string | `"L2"` | Distance metric | `L2`, `IP`, `COSINE` |
| `ML_MILVUS_NLIST` | int | `1024` | Index parameter nlist | `512`, `2048` |

**Alternative Variable Names**:
- `MILVUS_HOST` → `ML_MILVUS_HOST`
- `MILVUS_PORT` → `ML_MILVUS_PORT`

### Redis Configuration

| Variable | Type | Default | Description | Example |
|----------|------|---------|-------------|---------|
| `ML_REDIS_HOST` | string | `"localhost"` | Redis host | `redis`, `localhost` |
| `ML_REDIS_PORT` | int | `6379` | Redis port | `6379`, `6380` |
| `ML_REDIS_DB` | int | `0` | Redis database number | `0`, `1` |
| `ML_REDIS_PASSWORD` | string | `""` | Password (optional) | `redis_password` |
| `ML_REDIS_MAX_CONNECTIONS` | int | `10` | Max connections | `5`, `20` |
| `ML_CACHE_TTL` | int | `3600` | Cache TTL in seconds | `1800`, `7200` |

**Alternative Variable Names**:
- `REDIS_HOST` → `ML_REDIS_HOST`
- `REDIS_PORT` → `ML_REDIS_PORT`
- `REDIS_PASSWORD` → `ML_REDIS_PASSWORD`

### Application Configuration

| Variable | Type | Default | Description | Example |
|----------|------|---------|-------------|---------|
| `ML_API_HOST` | string | `"0.0.0.0"` | API host | `0.0.0.0`, `127.0.0.1` |
| `ML_API_PORT` | int | `8000` | API port | `8000`, `8080` |
| `ML_API_WORKERS` | int | `1` (local) / `4` (AWS) | Number of API workers | `1`, `4`, `8` |
| `ML_DEBUG` | bool | `true` (local) / `false` (AWS) | Enable debug mode | `true`, `false` |
| `ML_LOG_LEVEL` | string | `"INFO"` | Logging level | `DEBUG`, `INFO`, `WARNING`, `ERROR` |

**Alternative Variable Names**:
- `API_HOST` → `ML_API_HOST`
- `API_PORT` → `ML_API_PORT`
- `DEBUG` → `ML_DEBUG`
- `LOG_LEVEL` → `ML_LOG_LEVEL`

### Security Configuration

| Variable | Type | Default | Description | Example |
|----------|------|---------|-------------|---------|
| `ML_SECRET_KEY` | string | `"local-dev-secret-key-change-in-production"` | Application secret key | `your-32-char-secret-key-here` |
| `ML_REQUIRE_AUTH` | bool | `false` (local) / `true` (AWS) | Require authentication | `true`, `false` |
| `ML_ENABLE_REGISTRATION` | bool | `true` (local) / `false` (AWS) | Enable user registration | `true`, `false` |
| `ML_SESSION_TIMEOUT` | int | `86400` | Session timeout in seconds | `3600`, `86400` |
| `ML_RATE_LIMIT_PER_MINUTE` | int | `100` (local) / `1000` (AWS) | Rate limit per minute | `60`, `1000` |

**Alternative Variable Names**:
- `SECRET_KEY` → `ML_SECRET_KEY`
- `REQUIRE_AUTH` → `ML_REQUIRE_AUTH`

### File Storage Configuration

| Variable | Type | Default | Description | Example |
|----------|------|---------|-------------|---------|
| `ML_UPLOAD_DIR` | string | `"/app/uploads"` | Upload directory | `/app/uploads`, `/data/uploads` |
| `ML_MEDIA_DIR` | string | `"/app/media"` | Media directory | `/app/media`, `/data/media` |
| `ML_EXPORT_DIR` | string | `"/app/exports"` | Export directory | `/app/exports`, `/data/exports` |
| `ML_BACKUP_DIR` | string | `"/app/backups"` | Backup directory | `/app/backups`, `/data/backups` |
| `ML_LOG_DIR` | string | `"/app/logs"` | Log directory | `/app/logs`, `/var/log/ml` |
| `ML_MAX_FILE_SIZE` | int | `104857600` | Max file size in bytes (100MB) | `52428800` (50MB), `209715200` (200MB) |
| `ML_MAX_FILES_PER_UPLOAD` | int | `10` | Max files per upload | `5`, `20` |

**Alternative Variable Names**:
- `UPLOAD_DIR` → `ML_UPLOAD_DIR`
- `MEDIA_DIR` → `ML_MEDIA_DIR`
- `MAX_FILE_SIZE` → `ML_MAX_FILE_SIZE`

### Feature Flags

| Variable | Type | Default | Description | Example |
|----------|------|---------|-------------|---------|
| `ML_ENABLE_RELATIONAL_DB` | bool | `true` | Enable PostgreSQL | `true`, `false` |
| `ML_ENABLE_VECTOR_SEARCH` | bool | `true` | Enable Milvus vector search | `true`, `false` |
| `ML_ENABLE_GRAPH_DB` | bool | `true` | Enable Neo4j graph database | `true`, `false` |
| `ML_ENABLE_REDIS_CACHE` | bool | `true` | Enable Redis caching | `true`, `false` |
| `ML_ENABLE_DOCUMENT_UPLOAD` | bool | `true` | Enable document upload functionality | `true`, `false` |
| `ML_ENABLE_KNOWLEDGE_GRAPH` | bool | `true` | Enable knowledge graph features | `true`, `false` |
| `ML_ENABLE_AI_CHAT` | bool | `true` | Enable AI chat functionality | `true`, `false` |
| `ML_ENABLE_EXPORT_FUNCTIONALITY` | bool | `true` | Enable export features | `true`, `false` |
| `ML_ENABLE_ANALYTICS` | bool | `true` | Enable analytics | `true`, `false` |
| `ML_ENABLE_USER_MANAGEMENT` | bool | `false` (local) / `true` (AWS) | Enable user management | `true`, `false` |

### Connection Settings

| Variable | Type | Default | Description | Example |
|----------|------|---------|-------------|---------|
| `ML_CONNECTION_TIMEOUT` | int | `60` | Database connection timeout (seconds) | `30`, `120` |
| `ML_QUERY_TIMEOUT` | int | `30` | Database query timeout (seconds) | `15`, `60` |
| `ML_MAX_RETRIES` | int | `3` | Maximum connection retry attempts | `2`, `5` |

### Performance Settings

| Variable | Type | Default | Description | Example |
|----------|------|---------|-------------|---------|
| `ML_CONNECTION_POOLING` | bool | `true` | Enable connection pooling | `true`, `false` |
| `ML_QUERY_CACHING` | bool | `true` | Enable query result caching | `true`, `false` |
| `ML_ENABLE_QUERY_LOGGING` | bool | `false` | Enable SQL/Cypher query logging | `true`, `false` |

### Embedding Configuration

| Variable | Type | Default | Description | Example |
|----------|------|---------|-------------|---------|
| `ML_EMBEDDING_DIMENSION` | int | `384` | Vector embedding dimension | `384`, `768`, `1536` |
| `ML_EMBEDDING_MODEL` | string | `"sentence-transformers/all-MiniLM-L6-v2"` | Embedding model name | `all-mpnet-base-v2` |

### Development Configuration

| Variable | Type | Default | Description | Example |
|----------|------|---------|-------------|---------|
| `ML_ENABLE_HOT_RELOAD` | bool | `true` | Enable hot reload for development | `true`, `false` |
| `ML_WATCHDOG_ENABLED` | bool | `true` | Enable file watching | `true`, `false` |
| `ML_RELOAD_DIRS` | string | `"/app/src"` | Directories to watch for changes | `/app/src,/app/config` |
| `ML_RELOAD_DELAY` | float | `1.0` | Reload delay in seconds | `0.5`, `2.0` |

### Docker Configuration

| Variable | Type | Default | Description | Example |
|----------|------|---------|-------------|---------|
| `ML_DOCKER_NETWORK` | string | `"multimodal-librarian_default"` | Docker network name | `ml_network` |
| `ML_DOCKER_COMPOSE_FILE` | string | `"docker-compose.local.yml"` | Docker compose file | `docker-compose.yml` |

### External API Configuration

| Variable | Type | Default | Description | Example |
|----------|------|---------|-------------|---------|
| `OPENAI_API_KEY` | string | `None` | OpenAI API key | `sk-...` |
| `OPENAI_MODEL` | string | `"gpt-3.5-turbo"` | OpenAI model name | `gpt-4`, `gpt-3.5-turbo` |
| `OPENAI_MAX_TOKENS` | int | `2048` | Max tokens per request | `1024`, `4096` |
| `OPENAI_TEMPERATURE` | float | `0.7` | Response temperature | `0.0`, `1.0` |
| `GOOGLE_API_KEY` | string | `None` | Google API key | `AIza...` |
| `GEMINI_API_KEY` | string | `None` | Gemini API key | `AIza...` |
| `ANTHROPIC_API_KEY` | string | `None` | Anthropic API key | `sk-ant-...` |

### AWS Configuration (Production)

| Variable | Type | Default | Description | Example |
|----------|------|---------|-------------|---------|
| `AWS_DEFAULT_REGION` | string | `"us-east-1"` | AWS region | `us-west-2`, `eu-west-1` |
| `AWS_PROFILE` | string | `None` | AWS profile name | `default`, `production` |
| `NEPTUNE_CLUSTER_ENDPOINT` | string | `None` | Neptune cluster endpoint | `cluster.cluster-xyz.us-east-1.neptune.amazonaws.com` |
| `OPENSEARCH_DOMAIN_ENDPOINT` | string | `None` | OpenSearch domain endpoint | `search-domain.us-east-1.es.amazonaws.com` |
| `RDS_ENDPOINT` | string | `None` | RDS PostgreSQL endpoint | `instance.xyz.us-east-1.rds.amazonaws.com` |

## Boolean Value Formats

Boolean environment variables accept multiple formats:

**True Values**: `true`, `True`, `TRUE`, `1`, `yes`, `Yes`, `YES`, `on`, `On`, `ON`
**False Values**: `false`, `False`, `FALSE`, `0`, `no`, `No`, `NO`, `off`, `Off`, `OFF`

Examples:
```bash
ML_DEBUG=true
ML_ENABLE_VECTOR_SEARCH=1
ML_REQUIRE_AUTH=yes
ML_CONNECTION_POOLING=on
```

## Environment File Formats

### .env.local Format

```bash
# Comments start with #
ML_ENVIRONMENT=local
ML_DATABASE_TYPE=local

# Strings don't need quotes (but can use them)
ML_POSTGRES_HOST=postgres
ML_SECRET_KEY="my-secret-key"

# Numbers
ML_POSTGRES_PORT=5432
ML_API_WORKERS=4

# Booleans
ML_DEBUG=true
ML_ENABLE_VECTOR_SEARCH=false

# Multi-line values (not recommended for most settings)
ML_RELOAD_DIRS="/app/src,/app/config"
```

### Docker Compose Environment

```yaml
# docker-compose.local.yml
services:
  app:
    environment:
      - ML_ENVIRONMENT=local
      - ML_DATABASE_TYPE=local
      - ML_POSTGRES_HOST=postgres
      - ML_NEO4J_HOST=neo4j
      - ML_MILVUS_HOST=milvus
    env_file:
      - .env.local
```

### Shell Export Format

```bash
export ML_ENVIRONMENT=local
export ML_DATABASE_TYPE=local
export ML_POSTGRES_HOST=postgres
export ML_DEBUG=true
```

## Variable Precedence

Environment variables are loaded in the following order (later values override earlier ones):

1. **Default values** in configuration classes
2. **Environment file** (`.env.local`)
3. **System environment variables**
4. **Docker Compose environment** section
5. **Runtime overrides**

Example:
```bash
# .env.local
ML_POSTGRES_PORT=5432

# System environment (overrides .env.local)
export ML_POSTGRES_PORT=5433

# Docker Compose (overrides system environment)
environment:
  - ML_POSTGRES_PORT=5434
```

## Validation Rules

### Port Numbers
- Must be between 1 and 65535
- Cannot conflict with other services

### Timeouts
- Must be positive integers
- Connection timeout should be >= query timeout

### Pool Sizes
- Must be positive integers
- Total pool size should be reasonable (<500 for local dev)

### File Paths
- Should be absolute paths
- Directories must be writable

### Passwords
- Minimum 8 characters recommended
- Should not use default values in production

### Log Levels
- Must be one of: DEBUG, INFO, WARNING, ERROR, CRITICAL

### Embedding Dimensions
- Must be positive integer
- Should match chosen embedding model

## Common Patterns

### Local Development
```bash
ML_ENVIRONMENT=local
ML_DATABASE_TYPE=local
ML_DEBUG=true
ML_LOG_LEVEL=INFO
ML_POSTGRES_HOST=postgres
ML_NEO4J_HOST=neo4j
ML_MILVUS_HOST=milvus
ML_REDIS_HOST=redis
```

### Production-like Testing
```bash
ML_ENVIRONMENT=local
ML_DATABASE_TYPE=local
ML_DEBUG=false
ML_LOG_LEVEL=WARNING
ML_REQUIRE_AUTH=true
ML_ENABLE_REGISTRATION=false
```

### AWS Production
```bash
ML_ENVIRONMENT=production
ML_DATABASE_TYPE=aws
ML_DEBUG=false
ML_LOG_LEVEL=INFO
AWS_DEFAULT_REGION=us-east-1
NEPTUNE_CLUSTER_ENDPOINT=...
OPENSEARCH_DOMAIN_ENDPOINT=...
RDS_ENDPOINT=...
```

### Performance Tuning
```bash
# Conservative (low resource)
ML_POSTGRES_POOL_SIZE=5
ML_NEO4J_POOL_SIZE=20
ML_REDIS_MAX_CONNECTIONS=5
ML_API_WORKERS=1

# Aggressive (high performance)
ML_POSTGRES_POOL_SIZE=20
ML_NEO4J_POOL_SIZE=100
ML_REDIS_MAX_CONNECTIONS=20
ML_API_WORKERS=4
```

## Troubleshooting

### Variable Not Recognized
- Check spelling and case sensitivity
- Ensure `ML_` prefix is used
- Verify variable is defined in configuration class

### Value Not Applied
- Check variable precedence (system env overrides .env file)
- Restart application after changes
- Clear configuration cache if needed

### Type Conversion Errors
- Ensure boolean values use correct format
- Check integer values are valid numbers
- Verify string values don't have extra quotes

### Connection Issues
- Verify hostnames (localhost vs container names)
- Check port numbers and conflicts
- Ensure services are running and reachable

This reference provides comprehensive documentation for all environment variables. For usage examples and validation, see the configuration documentation and quick reference guide.