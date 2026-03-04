# Developer Onboarding Guide - Local Development Environment

## Welcome to Multimodal Librarian Local Development

This guide will help you set up and start developing with the Multimodal Librarian application using the local development environment. The local setup replaces AWS-native databases with Docker-based alternatives to reduce development costs while maintaining full functionality.

## Prerequisites

Before starting, ensure you have the following installed:

- **Docker Desktop** (4.20+) with Docker Compose
- **Python 3.9+** 
- **Git**
- **Make** (for build automation)
- **8GB+ RAM** available for containers
- **20GB+ free disk space**

### System Requirements

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| RAM | 8GB | 16GB |
| CPU | 4 cores | 8 cores |
| Disk Space | 20GB | 50GB |
| Docker Memory | 6GB | 8GB |

## Quick Start (10-Minute Setup)

### 1. Clone and Setup

```bash
# Clone the repository
git clone <repository-url>
cd multimodal-librarian

# Set up local environment
make dev-setup
```

### 2. Configure Environment

```bash
# Copy and customize local environment variables
cp .env.local.example .env.local

# Edit .env.local with your preferences (optional)
# Default values work out of the box
```

### 3. Start Local Development

```bash
# Start all services (first run takes 2-3 minutes)
make dev-local

# Wait for services to be ready
# The command will show you when everything is running
```

### 4. Verify Setup

```bash
# Check service health
make status-local

# View logs if needed
make logs-local
```

### 5. Access Your Environment

Once setup is complete, you'll have access to:

- **Application**: http://localhost:8000
- **Neo4j Browser**: http://localhost:7474 (neo4j/ml_password)
- **pgAdmin**: http://localhost:5050 (admin@multimodal-librarian.com/admin)
- **Attu (Milvus)**: http://localhost:3000
- **API Documentation**: http://localhost:8000/docs

## Architecture Overview

The local development environment replaces AWS services with Docker containers:

```
AWS Production          →    Local Development
├── AWS Neptune         →    Neo4j (Docker)
├── AWS OpenSearch      →    Milvus (Docker)  
├── AWS RDS PostgreSQL  →    PostgreSQL (Docker)
└── AWS S3              →    Local file storage
```

### Service Stack

| Service | Port | Purpose | Admin Interface |
|---------|------|---------|-----------------|
| Application | 8000 | Main FastAPI app | http://localhost:8000 |
| PostgreSQL | 5432 | Metadata & config | pgAdmin (port 5050) |
| Neo4j | 7687/7474 | Knowledge graph | Neo4j Browser (port 7474) |
| Milvus | 19530 | Vector search | Attu (port 3000) |
| etcd | 2379 | Milvus dependency | - |
| MinIO | 9000/9001 | Milvus storage | MinIO Console (port 9001) |

## Development Workflow

### Daily Development

```bash
# Start your development session
make dev-local

# Run tests against local services
make test-local

# View application logs
make logs-local

# Stop services when done
make dev-teardown
```

### Database Management

```bash
# Seed databases with sample data
make db-seed-local

# Run database migrations
make db-migrate-local

# Reset all databases (clean slate)
make db-reset-local

# Backup databases
make db-backup-local
```

### Environment Switching

The application supports seamless switching between local and AWS environments:

```bash
# Local development (default)
export ML_ENVIRONMENT=local
make dev-local

# AWS development (requires AWS credentials)
export ML_ENVIRONMENT=aws
make dev-aws
```

## Configuration Guide

### Environment Variables

Key environment variables in `.env.local`:

```bash
# Environment Selection
ML_ENVIRONMENT=local

# Database Connections (defaults work for Docker setup)
ML_POSTGRES_HOST=localhost
ML_POSTGRES_PORT=5432
ML_POSTGRES_DB=multimodal_librarian
ML_POSTGRES_USER=ml_user
ML_POSTGRES_PASSWORD=ml_password

ML_NEO4J_HOST=localhost
ML_NEO4J_PORT=7687
ML_NEO4J_USER=neo4j
ML_NEO4J_PASSWORD=ml_password

ML_MILVUS_HOST=localhost
ML_MILVUS_PORT=19530

# Application Settings
ML_DEBUG=true
ML_LOG_LEVEL=DEBUG
ML_HOT_RELOAD=true
```

### Docker Resource Limits

Adjust Docker Desktop settings if you encounter performance issues:

1. Open Docker Desktop → Settings → Resources
2. Set Memory to at least 6GB (8GB recommended)
3. Set CPU to at least 4 cores
4. Apply & Restart

## Development Features

### Hot Reload

The local setup supports hot reload for rapid development:

- Python code changes are automatically detected
- No need to restart containers for code changes
- Database schema changes require migration runs

### Sample Data

The environment comes with pre-seeded sample data:

- **Users**: Developer and test user accounts
- **Documents**: Sample PDFs for testing
- **Knowledge Graph**: Sample concepts and relationships
- **Vectors**: Pre-computed embeddings for search testing
- **Conversations**: Sample chat history

### Testing Framework

```bash
# Run all tests
make test-local

# Run specific test categories
pytest tests/integration/ -v
pytest tests/components/ -v
pytest tests/api/ -v

# Run tests with coverage
make test-cov
```

## Troubleshooting

### Common Issues

#### Services Won't Start

```bash
# Check Docker is running
docker --version
docker-compose --version

# Check available resources
docker system df
docker system prune  # Clean up if needed

# Restart Docker Desktop and try again
make dev-teardown
make dev-local
```

#### Port Conflicts

If you get port conflict errors:

```bash
# Check what's using the ports
lsof -i :8000  # Application
lsof -i :5432  # PostgreSQL
lsof -i :7474  # Neo4j

# Stop conflicting services or change ports in docker-compose.local.yml
```

#### Database Connection Issues

```bash
# Check database health
make health-local

# View database logs
docker-compose -f docker-compose.local.yml logs postgres
docker-compose -f docker-compose.local.yml logs neo4j
docker-compose -f docker-compose.local.yml logs milvus

# Reset databases if corrupted
make db-reset-local
```

#### Performance Issues

```bash
# Check resource usage
docker stats

# Optimize Docker settings
# Increase memory allocation in Docker Desktop

# Clean up unused resources
docker system prune -a
```

### Getting Help

1. **Check logs**: `make logs-local`
2. **Health status**: `make status-local`
3. **Service restart**: `make restart-service SERVICE=postgres`
4. **Full reset**: `make dev-teardown && make dev-local`

## Advanced Usage

### Custom Configuration

Create custom configurations for different scenarios:

```bash
# Create custom environment file
cp .env.local .env.local.custom

# Use custom configuration
ENV_FILE=.env.local.custom make dev-local
```

### Performance Monitoring

Monitor your local development environment:

```bash
# Resource usage dashboard
make monitor-local

# Database performance
make db-monitor-local

# Application metrics
curl http://localhost:8000/health/detailed
```

### Debugging

#### Database Debugging

```bash
# PostgreSQL debugging
docker-compose -f docker-compose.local.yml exec postgres psql -U ml_user -d multimodal_librarian

# Neo4j debugging
docker-compose -f docker-compose.local.yml exec neo4j cypher-shell -u neo4j -p ml_password

# Milvus debugging
python scripts/debug-milvus-connection.py
```

#### Application Debugging

```bash
# Enable debug mode
export ML_DEBUG=true
export ML_LOG_LEVEL=DEBUG

# Attach debugger (VS Code)
# Use the provided launch.json configuration

# View detailed logs
tail -f logs/application.log
```

## Best Practices

### Development Workflow

1. **Start Fresh Daily**: Use `make dev-local` to ensure clean state
2. **Test Early**: Run `make test-local` before committing changes
3. **Monitor Resources**: Keep an eye on Docker resource usage
4. **Clean Up**: Use `make dev-teardown` when switching contexts

### Code Organization

1. **Environment Switching**: Always use the database factory pattern
2. **Configuration**: Use environment variables, not hardcoded values
3. **Testing**: Write tests that work with both local and AWS setups
4. **Dependencies**: Use the dependency injection system properly

### Performance Tips

1. **Selective Services**: Only run services you need for your current task
2. **Resource Limits**: Set appropriate Docker resource limits
3. **Data Volume**: Use sample data, not full production datasets
4. **Cleanup**: Regularly clean up Docker images and volumes

## Migration from AWS Development

If you're migrating from AWS-based development:

### 1. Backup Current Work

```bash
# Export any important data from AWS
# (Follow your team's data export procedures)
```

### 2. Update Development Scripts

```bash
# Update any custom scripts to use ML_ENVIRONMENT=local
# Replace direct AWS client usage with factory pattern
```

### 3. Test Environment Switching

```bash
# Verify you can switch between environments
export ML_ENVIRONMENT=local
make test-local

export ML_ENVIRONMENT=aws  
make test-aws  # (if you still have AWS access)
```

## Team Collaboration

### Shared Development

- **Environment Files**: Don't commit `.env.local` with secrets
- **Docker Images**: Use consistent image versions across team
- **Sample Data**: Share sample data scripts, not actual data
- **Documentation**: Update this guide as you discover new patterns

### Code Reviews

- **Environment Compatibility**: Ensure code works in both local and AWS
- **Resource Usage**: Review Docker resource requirements
- **Testing**: Verify tests pass in local environment
- **Documentation**: Update guides for any new setup steps

## Next Steps

Now that you have your local development environment running:

1. **Explore the Application**: Visit http://localhost:8000 and try the features
2. **Review the Code**: Familiarize yourself with the codebase structure
3. **Run Tests**: Execute `make test-local` to understand the test suite
4. **Make Changes**: Start with small changes to understand the workflow
5. **Read Documentation**: Check `docs/` for detailed component guides

## Additional Resources

- **Architecture Guide**: `docs/architecture/system-architecture.md`
- **API Documentation**: http://localhost:8000/docs (when running)
- **Database Schemas**: `database/*/README.md`
- **Troubleshooting**: `docs/local-development-troubleshooting-guide.md`
- **Performance Tuning**: `docs/local-development-performance-tuning-guide.md`

## Support

If you encounter issues not covered in this guide:

1. Check the troubleshooting section above
2. Review existing documentation in `docs/`
3. Ask your team members
4. Create an issue with detailed error messages and steps to reproduce

Welcome to the team! Happy coding! 🚀