# Environment Setup Guide

This guide explains how to set up and switch between different environments in the Multimodal Librarian system.

## Overview

The Multimodal Librarian supports two main environments:

- **Local Development**: Uses Docker Compose with local database services (PostgreSQL, Neo4j, Milvus, Redis)
- **AWS Production**: Uses AWS-managed services (RDS PostgreSQL, Neptune, OpenSearch, ElastiCache)

## Environment Configuration

### Environment Variables

The system uses environment variables to determine which environment to use:

- `ML_ENVIRONMENT`: Primary environment selector (`local` or `aws`)
- `DATABASE_TYPE`: Database backend type (`local` or `aws`)
- `ML_DATABASE_TYPE`: Legacy compatibility (`local` or `aws`)

### Configuration Files

Environment variables can be loaded from:

1. `.env.local` (highest priority, for local development)
2. `.env` (fallback, for general configuration)
3. System environment variables (lowest priority)

## Local Development Environment

### Prerequisites

- Docker and Docker Compose installed
- At least 8GB RAM available
- 20GB free disk space

### Setup Steps

1. **Create Local Environment File**
   ```bash
   # Using the environment switcher script
   python scripts/switch-environment.py create-env local --output .env.local
   
   # Or copy from template
   cp .env.local.example .env.local
   ```

2. **Edit Configuration**
   Edit `.env.local` and customize the following key settings:
   ```bash
   # Environment Configuration
   ML_ENVIRONMENT=local
   DATABASE_TYPE=local
   
   # API Keys (required for AI functionality)
   OPENAI_API_KEY=your-openai-api-key-here
   GOOGLE_API_KEY=your-google-api-key-here
   GEMINI_API_KEY=your-gemini-api-key-here
   
   # Database Configuration (Docker Compose services)
   POSTGRES_HOST=postgres
   NEO4J_HOST=neo4j
   MILVUS_HOST=milvus
   REDIS_HOST=redis
   ```

3. **Start Local Services**
   ```bash
   # Start all services with Docker Compose
   make dev-local
   
   # Or manually
   docker-compose -f docker-compose.local.yml up -d
   ```

4. **Verify Setup**
   ```bash
   # Check environment status
   python scripts/switch-environment.py status
   
   # Validate configuration
   curl http://localhost:8000/config/validation
   ```

### Local Services

The local environment includes:

| Service | Port | Admin Interface | Purpose |
|---------|------|-----------------|---------|
| PostgreSQL | 5432 | pgAdmin (5050) | Metadata and configuration |
| Neo4j | 7687/7474 | Neo4j Browser (7474) | Knowledge graph |
| Milvus | 19530 | Attu (3000) | Vector search |
| Redis | 6379 | Redis Commander | Caching |
| Application | 8000 | - | Main API |

### Development Workflow

```bash
# Start development environment
make dev-local

# View logs
make logs-local

# Run tests against local services
make test-local

# Seed with sample data
make db-seed-local

# Stop and clean up
make dev-teardown
```

## AWS Production Environment

### Prerequisites

- AWS CLI configured with appropriate credentials
- Access to AWS services (RDS, Neptune, OpenSearch, ElastiCache)
- Production environment variables configured

### Setup Steps

1. **Create AWS Environment File**
   ```bash
   python scripts/switch-environment.py create-env aws --output .env.aws
   ```

2. **Configure AWS Settings**
   Edit `.env.aws` with your AWS configuration:
   ```bash
   # Environment Configuration
   ML_ENVIRONMENT=aws
   DATABASE_TYPE=aws
   
   # AWS Configuration
   AWS_REGION=us-east-1
   AWS_ACCESS_KEY_ID=your-access-key-id
   AWS_SECRET_ACCESS_KEY=your-secret-access-key
   
   # AWS Services
   NEPTUNE_ENDPOINT=your-neptune-cluster.region.neptune.amazonaws.com
   OPENSEARCH_ENDPOINT=your-opensearch-domain.region.es.amazonaws.com
   POSTGRES_HOST=your-rds-instance.region.rds.amazonaws.com
   ```

3. **Deploy to AWS**
   ```bash
   # Switch to AWS environment
   python scripts/switch-environment.py switch aws
   
   # Deploy using Terraform
   cd infrastructure/aws-native
   terraform init
   terraform plan
   terraform apply
   ```

## Environment Switching

### Using the Command Line Tool

The `scripts/switch-environment.py` tool provides comprehensive environment management:

```bash
# Show current environment status
python scripts/switch-environment.py status

# List all available environments
python scripts/switch-environment.py list

# Switch to local development
python scripts/switch-environment.py switch local

# Switch to AWS production (with validation)
python scripts/switch-environment.py switch aws

# Force switch (skip validation)
python scripts/switch-environment.py switch aws --force

# Validate an environment without switching
python scripts/switch-environment.py validate local

# Create environment file templates
python scripts/switch-environment.py create-env local
python scripts/switch-environment.py create-env aws --output .env.production
```

### Using the API

Environment switching is also available via REST API:

```bash
# Get current environment info
curl http://localhost:8000/config/environment

# List available environments
curl http://localhost:8000/config/environment/list

# Validate an environment
curl http://localhost:8000/config/environment/validate/local

# Switch environments
curl -X GET "http://localhost:8000/config/environment/switch/local"

# Create environment file
curl -X POST "http://localhost:8000/config/environment/create-file/local"
```

### Programmatic Switching

You can also switch environments programmatically:

```python
from multimodal_librarian.config.environment_switcher import (
    switch_to_local,
    switch_to_aws,
    get_current_environment_info,
    validate_current_environment
)

# Switch to local development
result = switch_to_local()
if result["success"]:
    print("Switched to local environment")

# Get current environment info
env_info = get_current_environment_info()
print(f"Current environment: {env_info['name']}")

# Validate current environment
validation = validate_current_environment()
if validation["valid"]:
    print("Environment is valid")
```

## Configuration Validation

### Automatic Validation

The system automatically validates configuration on startup:

- **Required variables**: Must be present for the environment to function
- **Optional variables**: Generate warnings if missing but don't prevent startup
- **Environment-specific checks**: Validate service availability and connectivity

### Manual Validation

You can manually validate configuration:

```bash
# Validate current environment
curl http://localhost:8000/config/validation

# Validate specific environment
python scripts/switch-environment.py validate local
python scripts/switch-environment.py validate aws
```

### Validation Results

Validation returns:

- **Errors**: Critical issues that prevent the environment from working
- **Warnings**: Non-critical issues that may affect functionality
- **Missing variables**: Lists of required/optional variables not configured
- **Environment info**: Current configuration status

## Troubleshooting

### Common Issues

1. **Configuration validation fails**
   ```bash
   # Check what's missing
   python scripts/switch-environment.py validate local
   
   # View detailed configuration
   curl http://localhost:8000/config/validation
   ```

2. **Local services not starting**
   ```bash
   # Check Docker Compose status
   docker-compose -f docker-compose.local.yml ps
   
   # View service logs
   docker-compose -f docker-compose.local.yml logs
   
   # Restart services
   docker-compose -f docker-compose.local.yml restart
   ```

3. **AWS services not accessible**
   ```bash
   # Check AWS credentials
   aws sts get-caller-identity
   
   # Test service connectivity
   curl http://localhost:8000/test/database
   
   # Validate AWS configuration
   curl http://localhost:8000/config/aws-native
   ```

4. **Environment switch fails**
   ```bash
   # Force switch (skip validation)
   python scripts/switch-environment.py switch local --force
   
   # Check environment variables
   env | grep ML_ENVIRONMENT
   env | grep DATABASE_TYPE
   ```

### Debug Mode

Enable debug mode for detailed logging:

```bash
# In .env.local or .env
DEBUG=true
LOG_LEVEL=DEBUG

# Or set environment variable
export DEBUG=true
export LOG_LEVEL=DEBUG
```

### Health Checks

Monitor system health:

```bash
# Basic health check
curl http://localhost:8000/health/simple

# Detailed health check
curl http://localhost:8000/health

# Database connectivity
curl http://localhost:8000/test/database

# Configuration status
curl http://localhost:8000/config/validation
```

## Best Practices

### Development

1. **Use local environment for development**
   - Faster iteration cycles
   - No AWS costs
   - Full control over services

2. **Keep environment files secure**
   - Never commit `.env.local` or `.env` to version control
   - Use different API keys for development and production
   - Rotate secrets regularly

3. **Validate before switching**
   - Always validate environment configuration
   - Check service availability
   - Test connectivity after switching

### Production

1. **Use AWS environment for production**
   - Managed services for reliability
   - Automatic scaling and backups
   - Production-grade security

2. **Secure configuration**
   - Use AWS Secrets Manager for sensitive data
   - Enable strict configuration validation
   - Monitor configuration changes

3. **Deployment safety**
   - Test in staging environment first
   - Use infrastructure as code (Terraform)
   - Implement proper rollback procedures

## Configuration Reference

### Required Variables by Environment

#### Local Development
- `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`
- `NEO4J_HOST`, `NEO4J_PORT`, `NEO4J_USER`, `NEO4J_PASSWORD`
- `MILVUS_HOST`, `MILVUS_PORT`
- `REDIS_HOST`, `REDIS_PORT`

#### AWS Production
- `NEPTUNE_ENDPOINT`, `OPENSEARCH_ENDPOINT`
- `AWS_REGION`, `POSTGRES_HOST`, `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`

### Optional Variables (All Environments)
- `OPENAI_API_KEY`, `GOOGLE_API_KEY`, `GEMINI_API_KEY`, `ANTHROPIC_API_KEY`
- `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` (if not using IAM roles)

### Feature Flags
- `ENABLE_DOCUMENT_UPLOAD=true`
- `ENABLE_KNOWLEDGE_GRAPH=true`
- `ENABLE_VECTOR_SEARCH=true`
- `ENABLE_AI_CHAT=true`
- `ENABLE_ANALYTICS=true`

### Development Settings
- `DEBUG=true` (local), `false` (production)
- `LOG_LEVEL=DEBUG` (local), `INFO` (production)
- `ENABLE_API_DOCS=true` (local), `false` (production)
- `ENABLE_HOT_RELOAD=true` (local), `false` (production)

For a complete list of configuration options, see the `.env.local.example` file.