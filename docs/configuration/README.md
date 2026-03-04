# Configuration Documentation

This directory contains comprehensive documentation for configuring the Multimodal Librarian local development conversion.

## Documentation Overview

### 📋 [Configuration Options](configuration-options.md)
Complete reference for all configuration options available in both local and AWS environments. Includes detailed descriptions, default values, validation rules, and usage examples.

**What you'll find:**
- Complete configuration class documentation
- Database configuration (PostgreSQL, Neo4j, Milvus, Redis)
- Application settings (API, security, storage)
- Feature flags and dependencies
- AWS-specific configuration
- Performance and monitoring settings

### ⚡ [Quick Reference](quick-reference.md)
Essential configuration options for getting started quickly. Perfect for developers who need to set up the environment fast.

**What you'll find:**
- Essential environment variables
- Common configuration patterns
- Quick setup commands
- Troubleshooting checklist
- Performance tuning tips

### ✅ [Validation Guide](validation-guide.md)
Comprehensive guide for validating configuration and troubleshooting issues. Learn how to ensure your configuration is correct and services are properly connected.

**What you'll find:**
- Configuration validation methods
- Connectivity testing
- Common validation errors and solutions
- Environment detection troubleshooting
- Automated validation setup

### 🔧 [Environment Variables](environment-variables.md)
Complete reference for all environment variables, including naming conventions, formats, and precedence rules.

**What you'll find:**
- All environment variables by category
- Variable naming conventions
- Boolean and type formats
- Precedence rules
- Common patterns and examples

## Quick Start

### 1. Basic Setup
```bash
# Copy the environment template
cp .env.local.example .env.local

# Edit with your settings
vim .env.local

# Start services
make dev-local
```

### 2. Essential Configuration
```bash
# Environment
ML_ENVIRONMENT=local
ML_DATABASE_TYPE=local

# API Keys (Required for AI functionality)
OPENAI_API_KEY=your-openai-api-key-here

# Database hosts (for Docker)
ML_POSTGRES_HOST=postgres
ML_NEO4J_HOST=neo4j
ML_MILVUS_HOST=milvus
ML_REDIS_HOST=redis
```

### 3. Validate Configuration
```python
from multimodal_librarian.config.config_factory import get_database_config

config = get_database_config()
validation = config.validate_configuration()
print(f"Valid: {validation['valid']}")
```

## Configuration Architecture

### Configuration Classes

```
ConfigurationFactory
├── LocalDatabaseConfig (local development)
│   ├── PostgreSQL configuration
│   ├── Neo4j configuration
│   ├── Milvus configuration
│   └── Redis configuration
└── AWSNativeConfig (production)
    ├── RDS PostgreSQL configuration
    ├── Neptune configuration
    ├── OpenSearch configuration
    └── AWS services configuration
```

### Environment Detection

The system automatically detects the environment based on:
- Environment variables (`ML_DATABASE_TYPE`, `ML_ENVIRONMENT`)
- AWS-specific indicators (region, service endpoints)
- Local development indicators (Docker files, localhost)
- Runtime environment (ECS, Lambda)

### Configuration Flow

```
1. Environment Detection
   ↓
2. Configuration Class Selection
   ↓
3. Environment Variable Loading
   ↓
4. Configuration Validation
   ↓
5. Service Connectivity Testing
   ↓
6. Application Startup
```

## Common Use Cases

### Local Development
- **Goal**: Fast development with Docker services
- **Configuration**: `ML_DATABASE_TYPE=local`
- **Services**: PostgreSQL, Neo4j, Milvus, Redis in Docker
- **Documentation**: [Quick Reference](quick-reference.md)

### Production Deployment
- **Goal**: Scalable AWS deployment
- **Configuration**: `ML_DATABASE_TYPE=aws`
- **Services**: RDS, Neptune, OpenSearch, ElastiCache
- **Documentation**: [Configuration Options](configuration-options.md)

### Testing Environment
- **Goal**: Isolated testing with minimal resources
- **Configuration**: Test-specific overrides
- **Services**: Lightweight local services
- **Documentation**: [Validation Guide](validation-guide.md)

### CI/CD Pipeline
- **Goal**: Automated testing and deployment
- **Configuration**: Environment-specific configs
- **Services**: Containerized or cloud services
- **Documentation**: [Environment Variables](environment-variables.md)

## Configuration Best Practices

### Security
- ✅ Use strong, unique passwords
- ✅ Generate secure secret keys (32+ characters)
- ✅ Enable authentication in production
- ✅ Use SSL/TLS for all connections
- ❌ Never commit `.env.local` files
- ❌ Don't use default passwords

### Performance
- ✅ Right-size connection pools
- ✅ Enable caching where appropriate
- ✅ Monitor resource usage
- ✅ Use appropriate timeout values
- ❌ Don't over-provision for local dev
- ❌ Avoid excessive logging in production

### Development
- ✅ Use hot reload for faster iteration
- ✅ Enable debug mode for development
- ✅ Validate configuration early
- ✅ Test environment switching
- ❌ Don't use production settings locally
- ❌ Don't ignore validation warnings

### Deployment
- ✅ Validate before deployment
- ✅ Use environment-specific configs
- ✅ Test connectivity after deployment
- ✅ Monitor health continuously
- ❌ Don't deploy without validation
- ❌ Don't mix environment configurations

## Troubleshooting Quick Links

### Common Issues
- **Services won't start**: [Quick Reference - Troubleshooting](quick-reference.md#troubleshooting)
- **Configuration errors**: [Validation Guide - Common Errors](validation-guide.md#common-validation-errors)
- **Environment detection**: [Validation Guide - Environment Issues](validation-guide.md#environment-detection-issues)
- **Connection failures**: [Configuration Options - Connectivity](configuration-options.md#connection-and-performance-settings)

### Validation Commands
```bash
# Validate configuration
make validate-config

# Test connectivity
make validate-connectivity

# Check Docker environment
make validate-docker

# Run all validations
make validate-all
```

### Health Checks
```bash
# Application health
curl http://localhost:8000/health/simple

# Database health
curl http://localhost:8000/health/databases

# Service status
docker-compose -f docker-compose.local.yml ps
```

## Configuration Files

### Primary Files
- `src/multimodal_librarian/config/local_config.py` - Local configuration class
- `src/multimodal_librarian/config/aws_native_config.py` - AWS configuration class
- `src/multimodal_librarian/config/config_factory.py` - Configuration factory
- `.env.local.example` - Environment template
- `.env.local` - Your local environment (create from template)

### Docker Files
- `docker-compose.local.yml` - Local services definition
- `Dockerfile` - Application container
- `Makefile` - Development commands

### Documentation Files
- `docs/configuration/configuration-options.md` - Complete reference
- `docs/configuration/quick-reference.md` - Quick start guide
- `docs/configuration/validation-guide.md` - Validation and troubleshooting
- `docs/configuration/environment-variables.md` - Environment variables reference

## Getting Help

### Documentation
1. Start with [Quick Reference](quick-reference.md) for immediate needs
2. Check [Configuration Options](configuration-options.md) for complete details
3. Use [Validation Guide](validation-guide.md) for troubleshooting
4. Reference [Environment Variables](environment-variables.md) for specific variables

### Validation Tools
```python
# Configuration validation
from multimodal_librarian.config.config_factory import get_database_config
config = get_database_config()
validation = config.validate_configuration()

# Environment detection
from multimodal_librarian.config.config_factory import detect_environment
env_info = detect_environment()

# Comprehensive validation
from multimodal_librarian.config.config_factory import ConfigurationFactory
factory = ConfigurationFactory()
results = factory.validate_environment_setup()
```

### Support Resources
- Configuration source code with inline documentation
- Example configuration files (`.env.local.example`)
- Validation error messages with specific guidance
- Health check endpoints for runtime validation

This documentation provides everything you need to configure the Multimodal Librarian for local development. Start with the [Quick Reference](quick-reference.md) if you're new to the system, or dive into the [Configuration Options](configuration-options.md) for comprehensive details.