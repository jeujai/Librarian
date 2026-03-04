# Local Development Configuration Guide

## Environment Configuration

### Environment Variables

The local development environment uses environment variables for configuration. Copy and customize the template:

```bash
cp .env.local.example .env.local
```

### Core Configuration Options

#### Database Selection
```bash
# Choose environment type
ML_ENVIRONMENT=local          # Use local databases
# ML_ENVIRONMENT=aws          # Use AWS databases (production)
```

#### PostgreSQL Configuration
```bash
ML_POSTGRES_HOST=postgres     # Docker service name
ML_POSTGRES_PORT=5432         # Standard PostgreSQL port
ML_POSTGRES_DB=multimodal_librarian
ML_POSTGRES_USER=ml_user
ML_POSTGRES_PASSWORD=ml_password
```

#### Neo4j Configuration
```bash
ML_NEO4J_HOST=neo4j          # Docker service name
ML_NEO4J_PORT=7687           # Bolt protocol port
ML_NEO4J_USER=neo4j
ML_NEO4J_PASSWORD=ml_password
```

#### Milvus Configuration
```bash
ML_MILVUS_HOST=milvus        # Docker service name
ML_MILVUS_PORT=19530         # Standard Milvus port
```

#### Application Configuration
```bash
ML_LOG_LEVEL=INFO            # DEBUG, INFO, WARNING, ERROR
ML_DEBUG=true                # Enable debug mode
ML_RELOAD=true               # Enable hot reload
```

## Docker Compose Configuration

### Service Customization

Edit `docker-compose.local.yml` to customize services:

#### PostgreSQL Customization
```yaml
postgres:
  environment:
    POSTGRES_SHARED_BUFFERS: 256MB
    POSTGRES_EFFECTIVE_CACHE_SIZE: 1GB
  volumes:
    - ./database/postgresql/custom.conf:/etc/postgresql/postgresql.conf
```

#### Neo4j Customization
```yaml
neo4j:
  environment:
    NEO4J_dbms_memory_heap_initial__size: 512m
    NEO4J_dbms_memory_heap_max__size: 1G
    NEO4J_PLUGINS: '["gds", "apoc", "graph-data-science"]'
```

#### Resource Limits
```yaml
services:
  postgres:
    deploy:
      resources:
        limits:
          memory: 1G
          cpus: '1.0'
```

### Port Mapping

Change default ports if needed:
```yaml
services:
  postgres:
    ports:
      - "15432:5432"  # Use port 15432 instead of 5432
  neo4j:
    ports:
      - "17474:7474"  # Use port 17474 for HTTP
      - "17687:7687"  # Use port 17687 for Bolt
```

## Configuration Validation

### Startup Validation
The application validates configuration on startup:
- Database connection strings
- Required environment variables
- Service availability

### Manual Validation
```bash
# Test configuration
python -c "from multimodal_librarian.config import get_database_config; print(get_database_config())"

# Validate environment
scripts/validate-local-env-config.py
```