# Configuration Quick Reference

This document provides a quick reference for the most commonly used configuration options in the Multimodal Librarian local development conversion.

## Essential Environment Variables

### Environment Control
```bash
ML_ENVIRONMENT=local                    # Environment name
ML_DATABASE_TYPE=local                  # Database backend (local/aws)
DEBUG=true                             # Enable debug mode
LOG_LEVEL=INFO                         # Logging level
```

### Database Connections
```bash
# PostgreSQL
ML_POSTGRES_HOST=postgres              # Container name or localhost
ML_POSTGRES_PORT=5432                  # Default PostgreSQL port
ML_POSTGRES_DB=multimodal_librarian    # Database name
ML_POSTGRES_USER=ml_user               # Username
ML_POSTGRES_PASSWORD=ml_password       # Password

# Neo4j
ML_NEO4J_HOST=neo4j                    # Container name or localhost
ML_NEO4J_PORT=7687                     # Bolt protocol port
ML_NEO4J_USER=neo4j                    # Username
ML_NEO4J_PASSWORD=ml_password          # Password

# Milvus
ML_MILVUS_HOST=milvus                  # Container name or localhost
ML_MILVUS_PORT=19530                   # Default Milvus port

# Redis
ML_REDIS_HOST=redis                    # Container name or localhost
ML_REDIS_PORT=6379                     # Default Redis port
```

### API Configuration
```bash
ML_API_HOST=0.0.0.0                    # Listen on all interfaces
ML_API_PORT=8000                       # API port
ML_API_WORKERS=1                       # Number of workers (local dev)
```

### Feature Flags (Most Important)
```bash
ML_ENABLE_VECTOR_SEARCH=true           # Enable Milvus vector search
ML_ENABLE_GRAPH_DB=true                # Enable Neo4j graph database
ML_ENABLE_AI_CHAT=true                 # Enable AI chat functionality
ML_ENABLE_DOCUMENT_UPLOAD=true         # Enable document upload
```

## Common Configuration Patterns

### Minimal Local Development
```bash
# .env.local
ML_ENVIRONMENT=local
ML_DATABASE_TYPE=local
DEBUG=true
ML_POSTGRES_HOST=postgres
ML_NEO4J_HOST=neo4j
ML_MILVUS_HOST=milvus
ML_REDIS_HOST=redis
```

### Performance Optimized
```bash
# Larger connection pools for better performance
ML_POSTGRES_POOL_SIZE=20
ML_NEO4J_POOL_SIZE=100
ML_REDIS_MAX_CONNECTIONS=20
ML_API_WORKERS=4

# Enable optimizations
ML_ENABLE_POOL_OPTIMIZATION=true
ML_QUERY_CACHING=true
```

### Resource Constrained
```bash
# Smaller pools for limited resources
ML_POSTGRES_POOL_SIZE=5
ML_NEO4J_POOL_SIZE=20
ML_REDIS_MAX_CONNECTIONS=5
ML_API_WORKERS=1

# Disable optional features
ML_ENABLE_ANALYTICS=false
ML_ENABLE_EXPORT_FUNCTIONALITY=false
```

### Development with Hot Reload
```bash
# Hot reload settings
ML_ENABLE_HOT_RELOAD=true
ML_WATCHDOG_ENABLED=true
ML_RELOAD_DIRS=/app/src/multimodal_librarian
ML_RELOAD_DELAY=0.5

# Development optimizations
DEBUG=true
LOG_LEVEL=DEBUG
ML_ENABLE_QUERY_LOGGING=true
```

## Quick Setup Commands

### Initial Setup
```bash
# Copy example environment file
cp .env.local.example .env.local

# Edit configuration
nano .env.local

# Start services
make dev-local
```

### Service Management
```bash
# Start all services
docker-compose -f docker-compose.local.yml up -d

# Check service status
docker-compose -f docker-compose.local.yml ps

# View logs
docker-compose -f docker-compose.local.yml logs -f

# Stop services
docker-compose -f docker-compose.local.yml down
```

### Health Checks
```bash
# Check application health
curl http://localhost:8000/health/simple

# Check database health
curl http://localhost:8000/health/databases

# Check all services
make status-local
```

## Configuration Validation

### Python Validation
```python
from multimodal_librarian.config.local_config import LocalDatabaseConfig

# Create and validate configuration
config = LocalDatabaseConfig()
validation = config.validate_configuration()

if not validation["valid"]:
    print("Issues found:")
    for issue in validation["issues"]:
        print(f"  - {issue}")

# Test connectivity
connectivity = config.validate_connectivity()
print(f"Overall status: {connectivity['overall_status']}")
```

### Command Line Validation
```bash
# Validate configuration
python -c "
from multimodal_librarian.config.local_config import LocalDatabaseConfig
config = LocalDatabaseConfig()
result = config.validate_configuration()
print('Valid:', result['valid'])
if result['issues']: print('Issues:', result['issues'])
"

# Test connectivity
python -c "
from multimodal_librarian.config.local_config import LocalDatabaseConfig
config = LocalDatabaseConfig()
result = config.validate_connectivity(timeout=5)
print('Status:', result['overall_status'])
"
```

## Troubleshooting

### Common Issues and Solutions

#### Port Conflicts
```bash
# Check what's using a port
lsof -i :5432
netstat -tulpn | grep :5432

# Change ports in .env.local
ML_POSTGRES_PORT=5433
ML_NEO4J_PORT=7688
```

#### Service Not Reachable
```bash
# Check Docker services
docker-compose -f docker-compose.local.yml ps

# Check service logs
docker-compose -f docker-compose.local.yml logs postgres
docker-compose -f docker-compose.local.yml logs neo4j
docker-compose -f docker-compose.local.yml logs milvus

# Restart services
docker-compose -f docker-compose.local.yml restart
```

#### Configuration Errors
```bash
# Check environment variables
env | grep ML_

# Validate Docker Compose file
docker-compose -f docker-compose.local.yml config

# Reset to defaults
cp .env.local.example .env.local
```

#### Performance Issues
```bash
# Check resource usage
docker stats

# Reduce pool sizes
ML_POSTGRES_POOL_SIZE=5
ML_NEO4J_POOL_SIZE=20

# Disable features
ML_ENABLE_ANALYTICS=false
ML_ENABLE_QUERY_LOGGING=false
```

## Environment File Templates

### Basic Template (.env.local)
```bash
# Environment
ML_ENVIRONMENT=local
ML_DATABASE_TYPE=local
DEBUG=true

# Database hosts (use container names)
ML_POSTGRES_HOST=postgres
ML_NEO4J_HOST=neo4j
ML_MILVUS_HOST=milvus
ML_REDIS_HOST=redis

# Passwords (change these!)
ML_POSTGRES_PASSWORD=your_secure_password
ML_NEO4J_PASSWORD=your_secure_password

# API Keys (required for AI features)
OPENAI_API_KEY=your_openai_key_here
```

### Production-like Template
```bash
# Environment
ML_ENVIRONMENT=local
ML_DATABASE_TYPE=local
DEBUG=false
LOG_LEVEL=WARNING

# Security
ML_REQUIRE_AUTH=true
ML_ENABLE_REGISTRATION=false
ML_SECRET_KEY=your-32-character-secret-key-here

# Performance
ML_POSTGRES_POOL_SIZE=20
ML_NEO4J_POOL_SIZE=100
ML_API_WORKERS=4
```

## Configuration Hierarchy

Configuration values are loaded in this order (later values override earlier ones):

1. **Default values** in `LocalDatabaseConfig`
2. **Environment file** (`.env.local`)
3. **System environment variables**
4. **Docker Compose environment** section
5. **Runtime overrides**

## Validation Rules Summary

- **Ports**: Must be 1-65535, no conflicts between services
- **Timeouts**: Must be positive, connection ≥ query timeout
- **Pool sizes**: Must be positive, total <500 recommended for local dev
- **Passwords**: Minimum 8 characters, avoid defaults
- **File paths**: Should be absolute paths
- **Log levels**: DEBUG, INFO, WARNING, ERROR, CRITICAL
- **Feature dependencies**: Some features require others to be enabled

## Performance Tuning Quick Tips

### For Development Speed
```bash
ML_POSTGRES_POOL_SIZE=5          # Small pools
ML_NEO4J_POOL_SIZE=20            # Reduce memory usage
ML_ENABLE_HOT_RELOAD=true        # Fast development
ML_RELOAD_DELAY=0.5              # Quick reloads
```

### For Testing Performance
```bash
ML_POSTGRES_POOL_SIZE=20         # Larger pools
ML_NEO4J_POOL_SIZE=100           # Handle more connections
ML_QUERY_CACHING=true            # Cache results
ML_ENABLE_POOL_OPTIMIZATION=true # Auto-optimize
```

### For Resource Constraints
```bash
ML_API_WORKERS=1                 # Single worker
ML_POSTGRES_POOL_SIZE=3          # Minimal pools
ML_NEO4J_POOL_SIZE=10            # Reduce memory
ML_ENABLE_ANALYTICS=false        # Disable optional features
```

This quick reference covers the most commonly used configuration options. For complete documentation, see [Configuration Options](configuration-options.md) and [Environment Variables](environment-variables.md).