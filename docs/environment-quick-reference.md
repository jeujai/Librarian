# Environment Setup Quick Reference

## Quick Start Commands

### Local Development Setup
```bash
# 1. Create environment file
cp .env.local.example .env.local

# 2. Edit API keys in .env.local
# OPENAI_API_KEY=your-key-here

# 3. Start services
make dev-local

# 4. Verify setup
python scripts/switch-environment.py status
```

### Environment Switching
```bash
# Switch to local development
python scripts/switch-environment.py switch local

# Switch to AWS production
python scripts/switch-environment.py switch aws

# Check current environment
python scripts/switch-environment.py status

# List all environments
python scripts/switch-environment.py list
```

### Validation and Troubleshooting
```bash
# Validate current environment
python scripts/switch-environment.py validate local

# Check configuration via API
curl http://localhost:8000/config/validation

# View environment info
curl http://localhost:8000/config/environment

# Test database connectivity
curl http://localhost:8000/test/database
```

## Environment Variables Cheat Sheet

### Core Environment Selection
```bash
ML_ENVIRONMENT=local          # or 'aws'
DATABASE_TYPE=local           # or 'aws'
DEBUG=true                    # or 'false'
LOG_LEVEL=DEBUG              # or 'INFO', 'WARNING', 'ERROR'
```

### Local Development
```bash
# Database Services (Docker Compose)
POSTGRES_HOST=postgres
NEO4J_HOST=neo4j
MILVUS_HOST=milvus
REDIS_HOST=redis

# API Keys (required for AI features)
OPENAI_API_KEY=your-openai-key
GOOGLE_API_KEY=your-google-key
GEMINI_API_KEY=your-gemini-key
```

### AWS Production
```bash
# AWS Services
NEPTUNE_ENDPOINT=your-neptune-endpoint
OPENSEARCH_ENDPOINT=your-opensearch-endpoint
POSTGRES_HOST=your-rds-endpoint
AWS_REGION=us-east-1

# AWS Credentials (if not using IAM roles)
AWS_ACCESS_KEY_ID=your-access-key
AWS_SECRET_ACCESS_KEY=your-secret-key
```

## Service Ports (Local Development)

| Service | Port | Admin Interface |
|---------|------|-----------------|
| Application | 8000 | - |
| PostgreSQL | 5432 | pgAdmin: 5050 |
| Neo4j | 7687 | Browser: 7474 |
| Milvus | 19530 | Attu: 3000 |
| Redis | 6379 | - |

## Common Commands

### Docker Compose
```bash
# Start all services
docker-compose -f docker-compose.local.yml up -d

# View logs
docker-compose -f docker-compose.local.yml logs -f

# Stop services
docker-compose -f docker-compose.local.yml down

# Restart a service
docker-compose -f docker-compose.local.yml restart postgres
```

### Makefile Targets
```bash
make dev-local        # Start local development
make dev-teardown     # Stop and clean up
make test-local       # Run tests against local services
make db-seed-local    # Seed databases with sample data
make logs-local       # View service logs
```

### Health Checks
```bash
# Simple health check
curl http://localhost:8000/health/simple

# Detailed health check
curl http://localhost:8000/health

# Configuration validation
curl http://localhost:8000/config/validation

# Environment information
curl http://localhost:8000/config/environment
```

## Troubleshooting Quick Fixes

### Configuration Issues
```bash
# Reset to local environment
export ML_ENVIRONMENT=local
export DATABASE_TYPE=local

# Validate configuration
python scripts/switch-environment.py validate local

# Create fresh environment file
python scripts/switch-environment.py create-env local
```

### Service Issues
```bash
# Check Docker services
docker-compose -f docker-compose.local.yml ps

# Restart all services
docker-compose -f docker-compose.local.yml restart

# View service logs
docker-compose -f docker-compose.local.yml logs postgres
docker-compose -f docker-compose.local.yml logs neo4j
```

### API Issues
```bash
# Check if API is running
curl http://localhost:8000/health/simple

# View application logs
docker-compose -f docker-compose.local.yml logs multimodal-librarian

# Restart application
docker-compose -f docker-compose.local.yml restart multimodal-librarian
```

## File Locations

### Configuration Files
- `.env.local.example` - Local environment template
- `.env.local` - Your local configuration (create from template)
- `.env` - Fallback configuration
- `docker-compose.local.yml` - Local services definition

### Scripts
- `scripts/switch-environment.py` - Environment switching utility
- `scripts/wait-for-services.sh` - Service readiness checker

### Documentation
- `docs/environment-setup-guide.md` - Complete setup guide
- `docs/environment-quick-reference.md` - This quick reference
- `README.md` - Project overview and setup

## API Endpoints

### Configuration
- `GET /config/validation` - Validate current configuration
- `GET /config/environment` - Get environment information
- `GET /config/environment/list` - List available environments
- `GET /config/environment/switch/{env_type}` - Switch environment
- `GET /config/environment/validate/{env_type}` - Validate environment

### Health Checks
- `GET /health/simple` - Simple health check
- `GET /health` - Detailed health check
- `GET /test/database` - Test database connectivity
- `GET /test/config` - Test configuration system

### Application
- `GET /` - API information
- `GET /docs` - API documentation (Swagger UI)
- `GET /chat` - Chat interface
- `GET /documents` - Document management interface