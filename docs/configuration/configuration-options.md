# Configuration Options Documentation

This document provides comprehensive documentation for all configuration options available in the Multimodal Librarian local development conversion.

## Overview

The Multimodal Librarian supports two main configuration environments:
- **Local Development**: Uses Docker containers for PostgreSQL, Neo4j, and Milvus
- **AWS Production**: Uses AWS-managed services (RDS, Neptune, OpenSearch)

Configuration is managed through environment variables with the `ML_` prefix and can be set via `.env.local` files.

## Quick Start

1. **Copy the example environment file**:
   ```bash
   cp .env.local.example .env.local
   ```

2. **Edit `.env.local`** with your specific settings

3. **Start the application**:
   ```bash
   make dev-local
   ```

The configuration system will automatically detect your environment and load the appropriate settings.

## Configuration Classes

### LocalDatabaseConfig

The `LocalDatabaseConfig` class manages configuration for local development with Docker containers.

**Location**: `src/multimodal_librarian/config/local_config.py`

**Key Features**:
- Comprehensive validation with detailed error messages
- Automatic environment detection and configuration
- Connection string generation for all database types
- Health check and connectivity validation
- Docker environment integration
- Hot reload support for development
- Connection pool optimization
- Retry logic and error handling

**Usage Example**:
```python
from multimodal_librarian.config.local_config import LocalDatabaseConfig

# Create configuration with defaults
config = LocalDatabaseConfig()

# Create test configuration (bypasses validation)
test_config = LocalDatabaseConfig.create_test_config(
    postgres_port=5433,
    enable_knowledge_graph=False
)

# Validate configuration
validation = config.validate_configuration()
if not validation["valid"]:
    print("Configuration issues:", validation["issues"])

# Test connectivity
connectivity = config.validate_connectivity(timeout=5)
print("Service status:", connectivity["overall_status"])
```

### AWSNativeConfig

The `AWSNativeConfig` class manages configuration for AWS production deployment.

**Location**: `src/multimodal_librarian/config/aws_native_config.py`

### ConfigurationFactory

The `ConfigurationFactory` automatically detects the environment and creates the appropriate configuration.

**Location**: `src/multimodal_librarian/config/config_factory.py`

**Usage Example**:
```python
from multimodal_librarian.config.config_factory import get_database_config

# Auto-detect environment
config = get_database_config("auto")

# Force specific environment
local_config = get_database_config("local")
aws_config = get_database_config("aws")

# Get environment information
from multimodal_librarian.config.config_factory import detect_environment
env_info = detect_environment()
print(f"Detected: {env_info.detected_type} (confidence: {env_info.confidence:.2f})")
```

## Environment Configuration

### Environment Identification

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `ML_ENVIRONMENT` | string | `"local"` | Environment name (local, development, production) |
| `ML_DATABASE_TYPE` | string | `"local"` | Database backend type (`"local"` or `"aws"`) |
| `DATABASE_TYPE` | string | `"local"` | Alternative database type variable |

### Environment Detection

The configuration factory automatically detects the environment based on:
- Environment variables (`ML_ENVIRONMENT`, `ML_DATABASE_TYPE`)
- AWS-specific variables (`AWS_REGION`, `NEPTUNE_CLUSTER_ENDPOINT`)
- Local development indicators (Docker Compose files, localhost hostnames)
- Runtime environment (ECS, Lambda)

## Database Configuration

### PostgreSQL Configuration (Local)

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `ML_POSTGRES_HOST` | string | `"localhost"` | PostgreSQL host |
| `ML_POSTGRES_PORT` | int | `5432` | PostgreSQL port |
| `ML_POSTGRES_DB` | string | `"multimodal_librarian"` | Database name |
| `ML_POSTGRES_USER` | string | `"ml_user"` | Username |
| `ML_POSTGRES_PASSWORD` | string | `"ml_password"` | Password |
| `ML_POSTGRES_POOL_SIZE` | int | `10` | Connection pool size |
| `ML_POSTGRES_MAX_OVERFLOW` | int | `20` | Max overflow connections |
| `ML_POSTGRES_POOL_RECYCLE` | int | `3600` | Pool recycle time (seconds) |

### Neo4j Configuration (Local)

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `ML_NEO4J_HOST` | string | `"localhost"` | Neo4j host |
| `ML_NEO4J_PORT` | int | `7687` | Neo4j Bolt port |
| `ML_NEO4J_HTTP_PORT` | int | `7474` | Neo4j HTTP port |
| `ML_NEO4J_USER` | string | `"neo4j"` | Username |
| `ML_NEO4J_PASSWORD` | string | `"ml_password"` | Password |
| `ML_NEO4J_POOL_SIZE` | int | `100` | Connection pool size |
| `ML_NEO4J_MAX_CONNECTION_LIFETIME` | int | `3600` | Max connection lifetime (seconds) |

### Milvus Configuration (Local)

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `ML_MILVUS_HOST` | string | `"localhost"` | Milvus host |
| `ML_MILVUS_PORT` | int | `19530` | Milvus port |
| `ML_MILVUS_USER` | string | `""` | Username (optional) |
| `ML_MILVUS_PASSWORD` | string | `""` | Password (optional) |
| `ML_MILVUS_DEFAULT_COLLECTION` | string | `"documents"` | Default collection name |
| `ML_MILVUS_INDEX_TYPE` | string | `"IVF_FLAT"` | Index type |
| `ML_MILVUS_METRIC_TYPE` | string | `"L2"` | Distance metric |
| `ML_MILVUS_NLIST` | int | `1024` | Index parameter nlist |

### Connection Pool Optimization

Advanced connection pool settings for performance tuning:

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `ML_ENABLE_POOL_OPTIMIZATION` | bool | `true` | Enable automatic connection pool optimization |
| `ML_POOL_OPTIMIZATION_STRATEGY` | string | `"balanced"` | Pool optimization strategy |
| `ML_POOL_MONITORING_INTERVAL` | int | `30` | Pool monitoring interval (seconds) |
| `ML_POOL_OPTIMIZATION_INTERVAL` | int | `300` | Pool optimization interval (seconds) |
| `ML_ENABLE_AUTO_POOL_OPTIMIZATION` | bool | `false` | Enable automatic pool optimization |
| `ML_POOL_TARGET_UTILIZATION` | float | `0.7` | Target pool utilization (0.0-1.0) |
| `ML_POOL_CONNECTION_TIMEOUT_THRESHOLD` | float | `5.0` | Connection timeout threshold for warnings |
| `ML_POOL_STALE_CONNECTION_THRESHOLD` | int | `3600` | Stale connection threshold (seconds) |

**Valid Optimization Strategies**: `conservative`, `balanced`, `aggressive`, `custom`

### Advanced Pool Settings

Database-specific advanced pool configuration:

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `ML_POSTGRES_POOL_PRE_PING` | bool | `true` | Enable PostgreSQL pool pre-ping |
| `ML_POSTGRES_POOL_RESET_ON_RETURN` | string | `"commit"` | PostgreSQL pool reset behavior |
| `ML_NEO4J_CONNECTION_ACQUISITION_TIMEOUT` | int | `60` | Neo4j connection acquisition timeout |
| `ML_NEO4J_MAX_TRANSACTION_RETRY_TIME` | int | `30` | Neo4j max transaction retry time |
| `ML_MILVUS_CONNECTION_POOL_SIZE` | int | `10` | Milvus connection pool size |
| `ML_MILVUS_CONNECTION_TIMEOUT` | int | `60` | Milvus connection timeout |

**Valid PostgreSQL Reset Behaviors**: `commit`, `rollback`, `None`

### Pool Health Monitoring

Connection pool health monitoring settings:

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `ML_ENABLE_POOL_HEALTH_MONITORING` | bool | `true` | Enable pool health monitoring |
| `ML_POOL_HEALTH_CHECK_INTERVAL` | int | `60` | Pool health check interval (seconds) |
| `ML_POOL_LEAK_DETECTION` | bool | `true` | Enable connection leak detection |
| `ML_POOL_PERFORMANCE_TRACKING` | bool | `true` | Enable pool performance tracking |

### Redis Configuration (Local)

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `ML_REDIS_HOST` | string | `"localhost"` | Redis host |
| `ML_REDIS_PORT` | int | `6379` | Redis port |
| `ML_REDIS_DB` | int | `0` | Redis database number |
| `ML_REDIS_PASSWORD` | string | `""` | Password (optional) |
| `ML_REDIS_MAX_CONNECTIONS` | int | `10` | Max connections |
| `ML_CACHE_TTL` | int | `3600` | Cache TTL in seconds |

### AWS Database Configuration (Production)

#### AWS General

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `AWS_DEFAULT_REGION` | string | `"us-east-1"` | AWS region |
| `AWS_PROFILE` | string | `None` | AWS profile name |

#### Neptune (Graph Database)

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `NEPTUNE_CLUSTER_ENDPOINT` | string | `None` | Neptune cluster endpoint |
| `NEPTUNE_PORT` | int | `8182` | Neptune port |
| `NEPTUNE_SECRET_NAME` | string | `"multimodal-librarian/aws-native/neptune"` | Credentials secret name |
| `NEPTUNE_IAM_AUTH` | bool | `true` | Use IAM authentication |
| `NEPTUNE_SSL` | bool | `true` | Use SSL connections |

#### OpenSearch (Vector Database)

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `OPENSEARCH_DOMAIN_ENDPOINT` | string | `None` | OpenSearch domain endpoint |
| `OPENSEARCH_PORT` | int | `443` | OpenSearch port |
| `OPENSEARCH_SECRET_NAME` | string | `"multimodal-librarian/aws-native/opensearch"` | Credentials secret name |
| `OPENSEARCH_USE_SSL` | bool | `true` | Use SSL |
| `OPENSEARCH_VERIFY_CERTS` | bool | `true` | Verify SSL certificates |
| `OPENSEARCH_INDEX_PREFIX` | string | `"ml"` | Index prefix |

#### RDS PostgreSQL

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `RDS_ENDPOINT` | string | `None` | RDS PostgreSQL endpoint |
| `RDS_PORT` | int | `5432` | RDS port |
| `RDS_DATABASE` | string | `"multimodal_librarian"` | Database name |
| `RDS_SECRET_NAME` | string | `"multimodal-librarian/aws-native/rds"` | Credentials secret name |
| `RDS_SSL_MODE` | string | `"require"` | SSL mode |
| `RDS_POOL_SIZE` | int | `20` | Connection pool size |
| `RDS_MAX_OVERFLOW` | int | `40` | Max overflow connections |

## Application Configuration

### API Server

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `ML_API_HOST` | string | `"0.0.0.0"` | API host |
| `ML_API_PORT` | int | `8000` | API port |
| `ML_API_WORKERS` | int | `1` (local) / `4` (AWS) | Number of API workers |
| `ML_DEBUG` | bool | `true` (local) / `false` (AWS) | Enable debug mode |
| `ML_LOG_LEVEL` | string | `"INFO"` | Logging level |

**Valid Log Levels**: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`

### Security Configuration

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `ML_SECRET_KEY` | string | `"local-dev-secret-key-change-in-production"` | Application secret key |
| `ML_REQUIRE_AUTH` | bool | `false` (local) / `true` (AWS) | Require authentication |
| `ML_ENABLE_REGISTRATION` | bool | `true` (local) / `false` (AWS) | Enable user registration |
| `ML_SESSION_TIMEOUT` | int | `86400` | Session timeout in seconds |
| `ML_RATE_LIMIT_PER_MINUTE` | int | `100` (local) / `1000` (AWS) | Rate limit per minute |

### File Storage Configuration

#### Local Storage

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `ML_UPLOAD_DIR` | string | `"/app/uploads"` | Upload directory |
| `ML_MEDIA_DIR` | string | `"/app/media"` | Media directory |
| `ML_EXPORT_DIR` | string | `"/app/exports"` | Export directory |
| `ML_BACKUP_DIR` | string | `"/app/backups"` | Backup directory |
| `ML_LOG_DIR` | string | `"/app/logs"` | Log directory |
| `ML_MAX_FILE_SIZE` | int | `10737418240` | Max file size in bytes (10GB - effectively unlimited) |
| `ML_MAX_FILES_PER_UPLOAD` | int | `10` | Max files per upload |

#### AWS S3 Storage

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `S3_BUCKET` | string | `None` | S3 bucket for file storage |
| `S3_REGION` | string | `None` | S3 bucket region |
| `S3_PREFIX` | string | `"multimodal-librarian"` | S3 key prefix |
| `S3_UPLOAD_PREFIX` | string | `"uploads"` | S3 upload prefix |
| `S3_MEDIA_PREFIX` | string | `"media"` | S3 media prefix |
| `S3_EXPORT_PREFIX` | string | `"exports"` | S3 export prefix |
| `S3_BACKUP_PREFIX` | string | `"backups"` | S3 backup prefix |

## Feature Flags

Feature flags control which functionality is enabled in the application.

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `ML_ENABLE_RELATIONAL_DB` | bool | `true` | Enable PostgreSQL/RDS |
| `ML_ENABLE_VECTOR_SEARCH` | bool | `true` | Enable Milvus/OpenSearch vector search |
| `ML_ENABLE_GRAPH_DB` | bool | `true` | Enable Neo4j/Neptune graph database |
| `ML_ENABLE_REDIS_CACHE` | bool | `true` | Enable Redis caching |
| `ML_ENABLE_DOCUMENT_UPLOAD` | bool | `true` | Enable document upload functionality |
| `ML_ENABLE_KNOWLEDGE_GRAPH` | bool | `true` | Enable knowledge graph features |
| `ML_ENABLE_AI_CHAT` | bool | `true` | Enable AI chat functionality |
| `ML_ENABLE_EXPORT_FUNCTIONALITY` | bool | `true` | Enable export features |
| `ML_ENABLE_ANALYTICS` | bool | `true` | Enable analytics |
| `ML_ENABLE_USER_MANAGEMENT` | bool | `false` (local) / `true` (AWS) | Enable user management |

### Feature Dependencies

Some features have dependencies on others:
- **Knowledge Graph**: Requires `ENABLE_GRAPH_DB=true`
- **AI Chat**: Requires at least one of `ENABLE_VECTOR_SEARCH` or `ENABLE_RELATIONAL_DB`
- **Export Functionality**: Requires `ENABLE_RELATIONAL_DB=true`
- **Analytics**: Requires `ENABLE_RELATIONAL_DB=true`

## Connection and Performance Settings

### Connection Settings

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `ML_CONNECTION_TIMEOUT` | int | `60` | Database connection timeout (seconds) |
| `ML_QUERY_TIMEOUT` | int | `30` | Database query timeout (seconds) |
| `ML_MAX_RETRIES` | int | `3` | Maximum connection retry attempts |

### Performance Settings

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `ML_CONNECTION_POOLING` | bool | `true` | Enable connection pooling |
| `ML_QUERY_CACHING` | bool | `true` | Enable query result caching |
| `ML_ENABLE_QUERY_LOGGING` | bool | `false` | Enable SQL/Cypher query logging |

### Embedding Configuration

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `ML_EMBEDDING_DIMENSION` | int | `384` | Vector embedding dimension |
| `ML_EMBEDDING_MODEL` | string | `"sentence-transformers/all-MiniLM-L6-v2"` | Embedding model name |

**Common Model Dimensions**:
- `all-MiniLM-L6-v2`: 384 dimensions
- `all-mpnet-base-v2`: 768 dimensions
- `all-distilroberta-v1`: 768 dimensions
- `paraphrase-MiniLM-L6-v2`: 384 dimensions

## Development Configuration

### Hot Reload Configuration

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `ML_ENABLE_HOT_RELOAD` | bool | `true` | Enable hot reload for development |
| `ML_WATCHDOG_ENABLED` | bool | `true` | Enable file watching |
| `ML_RELOAD_DIRS` | string | `"/app/src"` | Directories to watch for changes |
| `ML_RELOAD_DELAY` | float | `1.0` | Reload delay in seconds |

### Docker Configuration

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `ML_DOCKER_NETWORK` | string | `"multimodal-librarian_default"` | Docker network name |
| `ML_DOCKER_COMPOSE_FILE` | string | `"docker-compose.local.yml"` | Docker compose file |

## AWS-Specific Configuration

### CloudWatch Configuration

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `CLOUDWATCH_LOG_GROUP` | string | `"/aws/ecs/multimodal-librarian"` | CloudWatch log group |
| `CLOUDWATCH_LOG_STREAM_PREFIX` | string | `"app"` | Log stream prefix |
| `ENABLE_CLOUDWATCH_METRICS` | bool | `true` | Enable CloudWatch metrics |
| `ENABLE_XRAY_TRACING` | bool | `true` | Enable AWS X-Ray tracing |

### Auto Scaling Configuration

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `ENABLE_AUTO_SCALING` | bool | `true` | Enable ECS auto scaling |
| `MIN_CAPACITY` | int | `1` | Minimum ECS task count |
| `MAX_CAPACITY` | int | `10` | Maximum ECS task count |
| `TARGET_CPU_UTILIZATION` | int | `70` | Target CPU utilization for scaling |
| `TARGET_MEMORY_UTILIZATION` | int | `80` | Target memory utilization for scaling |

### Backup Configuration

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `ENABLE_AUTOMATED_BACKUPS` | bool | `true` | Enable automated backups |
| `BACKUP_RETENTION_DAYS` | int | `30` | Backup retention period in days |
| `BACKUP_SCHEDULE` | string | `"0 2 * * *"` | Backup schedule (cron format) |

### Cost Optimization

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `ENABLE_COST_OPTIMIZATION` | bool | `true` | Enable cost optimization features |
| `USE_SPOT_INSTANCES` | bool | `false` | Use EC2 spot instances for ECS |
| `ENABLE_RESOURCE_TAGGING` | bool | `true` | Enable resource tagging for cost tracking |

## External API Configuration

### AI/LLM Services

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `OPENAI_API_KEY` | string | `None` | OpenAI API key |
| `OPENAI_MODEL` | string | `"gpt-3.5-turbo"` | OpenAI model name |
| `OPENAI_MAX_TOKENS` | int | `2048` | Max tokens per request |
| `OPENAI_TEMPERATURE` | float | `0.7` | Response temperature |
| `GOOGLE_API_KEY` | string | `None` | Google API key |
| `GEMINI_API_KEY` | string | `None` | Gemini API key |
| `ANTHROPIC_API_KEY` | string | `None` | Anthropic API key |

## Configuration Validation

### Validation Rules

The configuration system includes comprehensive validation:

1. **Port Validation**: All ports must be between 1 and 65535
2. **Timeout Validation**: Timeouts must be positive values
3. **Pool Size Validation**: Pool sizes must be positive
4. **Embedding Dimension**: Must be positive integer
5. **Log Level**: Must be valid logging level
6. **Metric Type**: Must be valid Milvus metric type
7. **Index Type**: Must be valid Milvus index type

### Port Conflict Detection

The system automatically detects port conflicts between services and reports them during validation.

### Feature Dependency Validation

The system validates that required dependencies are enabled for each feature.

### Resource Constraint Validation

The system warns about potentially excessive resource usage:
- Total connection pool size > 500
- File size limits > 1GB
- Very high timeout values

## Environment File Templates

### .env.local.example

A comprehensive template file is provided at `.env.local.example` with all available configuration options and their descriptions.

### Creating Custom Templates

You can generate a custom environment template:

```python
from multimodal_librarian.config.local_config import LocalDatabaseConfig

config = LocalDatabaseConfig()
config.create_env_file_template(".env.custom")
```

## Configuration Factory

### Automatic Environment Detection

The `ConfigurationFactory` automatically detects the environment based on:

1. **Explicit Variables**: `ML_ENVIRONMENT`, `ML_DATABASE_TYPE`
2. **AWS Indicators**: AWS region, Neptune/OpenSearch endpoints
3. **Local Indicators**: Docker Compose files, localhost hostnames
4. **Runtime Environment**: ECS task metadata, Lambda environment

### Usage Examples

```python
from multimodal_librarian.config.config_factory import get_database_config

# Auto-detect environment
config = get_database_config("auto")

# Force specific environment
local_config = get_database_config("local")
aws_config = get_database_config("aws")
```

### Environment Detection Confidence

The factory provides confidence scores for environment detection:
- **High Confidence (>0.8)**: Clear indicators present
- **Medium Confidence (0.5-0.8)**: Some indicators present
- **Low Confidence (<0.5)**: Ambiguous or missing indicators

## Configuration Methods

### LocalDatabaseConfig Methods

The `LocalDatabaseConfig` class provides numerous methods for accessing configuration in different formats:

#### Connection String Generation

```python
# PostgreSQL connection strings
postgres_async_url = config.get_postgres_connection_string(async_driver=True)
postgres_sync_url = config.get_postgres_connection_string(async_driver=False)
postgres_with_pool = config.get_postgres_connection_string(
    async_driver=False, 
    include_pool_params=True
)

# Neo4j URIs
neo4j_bolt_uri = config.get_neo4j_uri(protocol="bolt")
neo4j_uri = config.get_neo4j_uri(protocol="neo4j")
neo4j_http_uri = config.get_neo4j_http_uri(secure=False)

# Milvus connection
milvus_uri = config.get_milvus_uri()
milvus_config = config.get_milvus_connection_config()

# Redis connection
redis_url = config.get_redis_connection_string(include_auth=True)
redis_config = config.get_redis_connection_config()
```

#### Configuration Dictionaries

```python
# Get database-specific configuration
postgres_config = config.get_relational_db_config()
neo4j_config = config.get_graph_db_config()
milvus_config = config.get_vector_db_config()
redis_config = config.get_redis_config()

# Get application configuration
app_config = config.get_application_config()
storage_config = config.get_storage_config()
dev_config = config.get_development_config()

# Get advanced configuration
pool_config = config.get_connection_pool_config()
retry_config = config.get_retry_config()
health_config = config.get_health_monitoring_config()
docker_config = config.get_docker_config()
```

#### Validation and Health Checks

```python
# Comprehensive configuration validation
validation = config.validate_configuration()
print(f"Valid: {validation['valid']}")
print(f"Issues: {validation['issues']}")
print(f"Warnings: {validation['warnings']}")

# Test connectivity to all services
connectivity = config.validate_connectivity(timeout=5)
print(f"Overall status: {connectivity['overall_status']}")
for service, result in connectivity['services'].items():
    print(f"{service}: {'✓' if result['connected'] else '✗'}")

# Validate Docker environment
docker_status = config.validate_docker_environment()
print(f"Docker available: {docker_status['docker_available']}")
print(f"Compose available: {docker_status['compose_available']}")

# Validate and attempt fixes
fix_results = config.validate_and_fix_configuration()
print(f"Fixes applied: {len(fix_results['fixes_applied'])}")
print(f"Recommendations: {fix_results['recommendations']}")
```

#### Environment Information

```python
# Get environment information
env_info = config.get_environment_info()
print(f"Backend: {env_info['backend_type']}")
print(f"Services: {env_info['services']}")

# Create environment template
config.create_env_file_template(".env.custom")
```

### Configuration Testing

#### Test Configuration Creation

```python
# Create test configuration with validation bypassed
test_config = LocalDatabaseConfig.create_test_config(
    postgres_port=5433,
    neo4j_port=7688,
    enable_knowledge_graph=False,
    enable_ai_chat=False
)

# Test configuration doesn't trigger validation errors
assert test_config.postgres_port == 5433
```

### Configuration Factory Methods

```python
from multimodal_librarian.config.config_factory import (
    get_database_config,
    detect_environment,
    get_environment_summary,
    clear_configuration_cache
)

# Get configuration with auto-detection
config = get_database_config("auto")

# Detect environment manually
env_info = detect_environment()
print(f"Detected: {env_info.detected_type}")
print(f"Confidence: {env_info.confidence:.2f}")
print(f"Indicators: {env_info.indicators}")

# Get comprehensive environment summary
summary = get_environment_summary()
print(f"Detection: {summary['detection']}")
print(f"Configuration: {summary.get('configuration', 'Not loaded')}")

# Clear cache (useful for testing)
clear_configuration_cache()
```

## Troubleshooting

### Common Configuration Issues

1. **Port Conflicts**: Multiple services using the same port
2. **Missing Dependencies**: Features enabled without required services
3. **Invalid Credentials**: Incorrect database passwords or API keys
4. **Network Issues**: Services not reachable on specified hosts/ports
5. **Resource Limits**: Excessive connection pool sizes

### Validation Errors

The configuration system provides detailed error messages for validation failures:

```python
try:
    config = LocalDatabaseConfig()
except ValueError as e:
    print(f"Configuration error: {e}")
```

### Environment Detection Issues

If environment detection fails or has low confidence:

1. Set `ML_DATABASE_TYPE` explicitly
2. Check for conflicting environment variables
3. Verify AWS credentials and endpoints
4. Ensure Docker services are running for local development

### Performance Tuning

#### Connection Pool Sizing

- **Local Development**: Keep pools small (10-20 connections)
- **Production**: Size based on expected load and database capacity
- **Total Pools**: Monitor total connection count across all services

#### Timeout Configuration

- **Connection Timeout**: Balance between reliability and responsiveness
- **Query Timeout**: Set based on expected query complexity
- **Session Timeout**: Balance between security and user experience

## Best Practices

### Security

1. **Change Default Passwords**: Never use default passwords in production
2. **Use Strong Secret Keys**: Generate cryptographically secure secret keys
3. **Enable Authentication**: Always require authentication in production
4. **Use SSL/TLS**: Enable SSL for all database connections in production
5. **Rotate Credentials**: Regularly rotate database and API credentials

### Performance

1. **Right-Size Pools**: Configure connection pools based on actual usage
2. **Enable Caching**: Use Redis caching for frequently accessed data
3. **Monitor Resources**: Track connection usage and query performance
4. **Optimize Embeddings**: Choose appropriate embedding dimensions for your use case

### Development

1. **Use Hot Reload**: Enable hot reload for faster development cycles
2. **Enable Debug Mode**: Use debug mode for detailed error information
3. **Separate Environments**: Use different configurations for dev/staging/prod
4. **Version Control**: Never commit `.env.local` files to version control

### Monitoring

1. **Enable Logging**: Configure appropriate log levels for each environment
2. **Health Checks**: Implement comprehensive health checks for all services
3. **Metrics Collection**: Enable metrics collection for performance monitoring
4. **Error Tracking**: Configure error tracking and alerting

## Migration Guide

### From Legacy Configuration

If migrating from legacy configuration:

1. **Update Environment Variables**: Use new `ML_` prefixed variables
2. **Enable Feature Flags**: Configure feature flags based on your needs
3. **Update Connection Strings**: Use new configuration methods
4. **Test Thoroughly**: Validate all functionality after migration

### Between Environments

When switching between local and AWS environments:

1. **Clear Configuration Cache**: Call `clear_configuration_cache()`
2. **Update Environment Variables**: Set appropriate environment type
3. **Validate Configuration**: Run validation checks after switching
4. **Test Connectivity**: Verify all services are reachable

This documentation provides comprehensive coverage of all configuration options available in the Multimodal Librarian local development conversion. For additional help, refer to the source code documentation and example configuration files.