# Docker Deployment Guide

This guide covers how to deploy the Multimodal Librarian using Docker containers with support for chat interface, ML APIs, and WebSocket connections.

## Quick Start

### Prerequisites

- Docker Engine 20.10+
- Docker Compose 2.0+
- At least 8GB RAM available for containers
- 20GB free disk space

### Development Setup

1. **Clone and setup environment:**
   ```bash
   git clone <repository-url>
   cd multimodal-librarian
   make quickstart
   ```

2. **Edit environment variables:**
   ```bash
   # Edit .env file with your API keys
   nano .env
   ```

3. **Start services:**
   ```bash
   make dev
   ```

4. **Access the application:**
   - Web Interface: http://localhost:8000
   - API Documentation: http://localhost:8000/docs
   - PostgreSQL: localhost:5432

**Note:** This application now uses AWS-native databases (Neptune for graph operations and OpenSearch for vector search). Legacy Neo4j and Milvus support has been removed. For local development, configure AWS credentials to access your Neptune and OpenSearch instances.

## Architecture Overview

The Docker setup includes the following services:

### Core Application Services

- **app**: Main FastAPI application with chat interface and ML APIs
- **postgres**: PostgreSQL database for metadata and configuration

### AWS-Native Database Services (External)

- **Neptune**: AWS-managed graph database for knowledge graph operations (configured via environment variables)
- **OpenSearch**: AWS-managed vector database for embeddings and semantic search (configured via environment variables)

### Supporting Services

- **redis**: Caching and session management (optional)
- **nginx**: Reverse proxy for production (optional)

## Environment Configuration

### Required Environment Variables

```bash
# API Keys (required for full functionality)
OPENAI_API_KEY=your-openai-api-key
GOOGLE_API_KEY=your-google-api-key
GEMINI_API_KEY=your-gemini-api-key

# Security (change in production)
SECRET_KEY=your-super-secret-key
ENCRYPTION_KEY=your-base64-encoded-encryption-key

# Database passwords (change in production)
POSTGRES_PASSWORD=your-postgres-password

# AWS-Native Database Configuration
NEPTUNE_ENDPOINT=your-neptune-cluster-endpoint.region.neptune.amazonaws.com
NEPTUNE_PORT=8182
OPENSEARCH_ENDPOINT=your-opensearch-domain-endpoint.region.es.amazonaws.com
OPENSEARCH_PORT=443
```

### Optional Configuration

```bash
# Application settings
DEBUG=false
LOG_LEVEL=INFO
REQUIRE_AUTH=false

# Performance settings
API_WORKERS=4
RATE_LIMIT_PER_MINUTE=60
WEBSOCKET_TIMEOUT=3600

# File processing
MAX_FILE_SIZE=10737418240  # 10GB - effectively unlimited
CHUNK_SIZE=512
CHUNK_OVERLAP=50
```

## Deployment Modes

### Development Mode

Best for local development with hot reload and debugging:

```bash
# Start development environment
make dev

# View logs
make logs

# Open shell in app container
make shell

# Stop services
make down
```

Features:
- Hot reload enabled
- Source code mounted as volume
- Debug mode enabled
- All ports exposed
- Development dependencies included

### Production Mode

Optimized for production deployment:

```bash
# Build production images
make prod-build

# Deploy to production
make prod-deploy

# Monitor services
make monitor
```

Features:
- Multi-stage build for smaller images
- Non-root user for security
- Resource limits configured
- SSL/TLS support with nginx
- Health checks enabled
- Audit logging enabled

### Testing Mode

Isolated environment for running tests:

```bash
# Run tests in containers
make test-docker
```

Features:
- Separate test databases
- Test data isolation
- Automated test execution
- Clean environment for each run

## Service Configuration

### Model Server Service

The model server is a dedicated container that handles ML model inference:

- **Embedding Generation**: Generates text embeddings using sentence-transformers (all-MiniLM-L6-v2)
- **NLP Processing**: Provides tokenization, NER, and POS tagging using spaCy (en_core_web_sm)
- **Health Endpoints**: Provides readiness and liveness probes for container orchestration

Configuration:
```bash
# Model Server URL (default: http://model-server:8001)
MODEL_SERVER_URL=http://model-server:8001

# Request timeout in seconds (default: 30)
MODEL_SERVER_TIMEOUT=30

# Enable/disable model server (default: true)
# When disabled, the app falls back to local model loading
MODEL_SERVER_ENABLED=true
```

The model server pre-downloads models at build time for faster startup. It exposes:
- `POST /embeddings` - Generate embeddings for text
- `POST /nlp/process` - Process text with NLP tasks
- `GET /health` - Health check with model status
- `GET /health/ready` - Readiness probe
- `GET /health/live` - Liveness probe

### Application Service

The main application container includes:

- **FastAPI** web framework with WebSocket support
- **Chat interface** with multimedia support
- **ML training APIs** for reinforcement learning
- **Export functionality** for multiple formats
- **Security features** including encryption and audit logging

### Database Services

#### PostgreSQL
- Stores application metadata, user data, and configuration
- Includes health checks and backup support
- Configured with UTF-8 encoding and optimized settings

#### Neptune (AWS-Native)
- AWS-managed graph database for knowledge graph operations
- Stores concept relationships and entity connections
- Accessed via Gremlin or SPARQL queries
- Configured through environment variables (endpoint and port)

#### OpenSearch (AWS-Native)
- AWS-managed vector database for semantic search
- Stores embeddings for similarity search
- Provides full-text search capabilities
- Configured through environment variables (endpoint and port)

## Networking

All services communicate through a custom Docker network (`app-network`) with the following configuration:

- **Subnet**: 172.20.0.0/16
- **Internal communication**: Service names as hostnames
- **External access**: Only necessary ports exposed to host

### Port Mapping

| Service | Internal Port | External Port | Purpose |
|---------|---------------|---------------|---------|
| app | 8000 | 8000 | Main application |
| postgres | 5432 | 5432 | Database access |
| nginx | 80/443 | 80/443 | Reverse proxy |

**Note:** Neptune and OpenSearch are AWS-managed services accessed via their respective endpoints. No local ports are exposed for these services.

## Volume Management

### Persistent Volumes

- **postgres_data**: PostgreSQL database files
- **redis_data**: Redis cache data

**Note:** Neptune and OpenSearch data is managed by AWS and does not require local volumes.

### Bind Mounts

Development mode includes bind mounts for:
- **./uploads**: User uploaded files
- **./media**: Generated media files
- **./exports**: Exported documents
- **./logs**: Application logs
- **./audit_logs**: Security audit logs
- **./src**: Source code (development only)

## Health Checks

All services include health checks:

```bash
# Check overall system health
make health

# Monitor service status
make monitor

# View detailed health information
curl http://localhost:8000/health
```

### Health Check Endpoints

- **Application**: `/health` (detailed) and `/health/simple` (basic)
- **PostgreSQL**: `pg_isready` command
- **Neptune**: Gremlin query execution (via application)
- **OpenSearch**: HTTP health endpoint (via application)

## Backup and Recovery

### Database Backup

```bash
# Backup all databases
make backup

# Manual PostgreSQL backup
docker-compose exec postgres pg_dump -U postgres multimodal_librarian > backup.sql
```

**Note:** Neptune and OpenSearch backups are managed through AWS automated backup services. Configure backup retention policies in your AWS console.

### Volume Backup

```bash
# Backup Docker volumes
docker run --rm -v multimodal-librarian_postgres_data:/data \
  -v $(pwd)/backups:/backup alpine \
  tar czf /backup/postgres_data.tar.gz -C /data .
```

## Monitoring and Logging

### Log Management

```bash
# View all service logs
make logs

# View specific service logs
docker-compose logs -f app

# View log files
tail -f logs/app.log
tail -f audit_logs/audit.log
```

### Resource Monitoring

```bash
# Monitor resource usage
make monitor

# Detailed container stats
docker stats

# Service status
docker-compose ps
```

## Security Considerations

### Production Security

1. **Change default passwords** in `.env` file
2. **Generate secure keys** for encryption and JWT
3. **Enable authentication** with `REQUIRE_AUTH=true`
4. **Configure SSL/TLS** certificates for nginx
5. **Set up firewall rules** to restrict access
6. **Enable audit logging** for compliance
7. **Regular security updates** for base images

### Network Security

- Services communicate through internal Docker network
- Only necessary ports exposed to host
- nginx reverse proxy for SSL termination
- Rate limiting configured for API endpoints

### Data Security

- Encryption at rest for sensitive data
- Encrypted communication between services
- Secure key management with environment variables
- Audit trail for all data access

## Troubleshooting

### Common Issues

1. **Services won't start**:
   ```bash
   # Check logs for errors
   make logs
   
   # Verify environment variables
   cat .env
   
   # Check disk space
   df -h
   ```

2. **Database connection errors**:
   ```bash
   # Check database health
   make health
   
   # Restart database services
   docker-compose restart postgres
   
   # For Neptune/OpenSearch issues, verify AWS credentials and endpoints
   # Check AWS service health in AWS Console
   ```

3. **Memory issues**:
   ```bash
   # Check memory usage
   docker stats
   
   # Increase Docker memory limit
   # Reduce number of workers in production
   ```

4. **WebSocket connection issues**:
   ```bash
   # Check nginx configuration
   # Verify WebSocket headers in proxy settings
   # Check firewall rules for WebSocket traffic
   ```

5. **Model Server Issues**:
   ```bash
   # Check model server health
   curl http://localhost:8001/health
   
   # Check model server logs
   docker compose logs model-server
   
   # Restart model server
   docker compose restart model-server
   
   # If model server is unavailable, the app will fall back to local model loading
   # To disable model server entirely:
   MODEL_SERVER_ENABLED=false
   ```

6. **App Container Health Check Timeouts**:
   
   If the app container shows as "unhealthy" and external requests timeout while
   internal health checks work, this is typically caused by blocking operations
   during module import. Common causes:
   
   - **SentenceTransformer loading at import time**: ML models should be loaded
     lazily (on first use) rather than at module import time
   - **Synchronous database connections**: Database connections should be async
     or run in thread pools
   - **Blocking I/O in middleware**: Middleware should be non-blocking
   
   To diagnose:
   ```bash
   # Check if requests reach the app
   docker compose logs app --tail=50
   
   # Test from inside the container
   docker compose exec app curl http://localhost:8000/health/simple
   
   # Check for stuck processes
   docker compose exec app ps aux
   ```
   
   The fix is to ensure all ML model loading uses lazy initialization:
   ```python
   # BAD - blocks event loop during import
   from sentence_transformers import SentenceTransformer
   model = SentenceTransformer('all-MiniLM-L6-v2')
   
   # GOOD - lazy loading on first use
   _model = None
   @property
   def model(self):
       if self._model is None:
           from sentence_transformers import SentenceTransformer
           self._model = SentenceTransformer('all-MiniLM-L6-v2')
       return self._model
   ```

### Performance Tuning

1. **Increase memory limits** for database services
2. **Adjust worker processes** based on CPU cores
3. **Configure connection pooling** for databases
4. **Enable caching** with Redis
5. **Optimize Docker images** with multi-stage builds

## Scaling

### Horizontal Scaling

```bash
# Scale application instances
docker-compose up -d --scale app=3

# Use nginx load balancer
# Configure database connection pooling
```

### Vertical Scaling

```bash
# Increase resource limits in docker-compose.prod.yml
deploy:
  resources:
    limits:
      cpus: '4.0'
      memory: 8G
```

## Development Workflow

### Local Development

1. **Start development environment**:
   ```bash
   make dev
   ```

2. **Make code changes** (hot reload enabled)

3. **Run tests**:
   ```bash
   make test-docker
   ```

4. **Check code quality**:
   ```bash
   make quality
   ```

5. **Commit changes** and push to repository

### CI/CD Integration

The Docker setup supports CI/CD pipelines:

```yaml
# Example GitHub Actions workflow
- name: Build and test
  run: |
    make test-docker
    make prod-build
```

## Support

For issues and questions:

1. Check the logs: `make logs`
2. Verify configuration: `cat .env`
3. Check service health: `make health`
4. Review this documentation
5. Open an issue in the repository

## Additional Resources

- [Docker Documentation](https://docs.docker.com/)
- [Docker Compose Documentation](https://docs.docker.com/compose/)
- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [Milvus Documentation](https://milvus.io/docs)
- [Neo4j Documentation](https://neo4j.com/docs/)