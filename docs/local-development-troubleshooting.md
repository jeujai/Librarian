# Local Development Troubleshooting Guide

## Quick Diagnostics

### Health Check Commands
```bash
# Overall system health
make health-local

# Individual service health
scripts/health-check-postgresql.py
scripts/health-check-neo4j.py
scripts/health-check-milvus.py

# Application health
curl http://localhost:8000/health/simple
```

### Common Issues and Solutions

#### 1. Docker Services Won't Start

**Symptoms**: Services fail to start or immediately exit

**Diagnosis**:
```bash
docker compose -f docker-compose.local.yml ps
docker compose -f docker-compose.local.yml logs
```

**Solutions**:
- Check Docker daemon is running
- Verify sufficient disk space (20GB+)
- Ensure ports are available
- Restart Docker Desktop

#### 2. Database Connection Failures

**Symptoms**: Application can't connect to databases

**Diagnosis**:
```bash
# Test connections directly
docker compose -f docker-compose.local.yml exec postgres pg_isready
docker compose -f docker-compose.local.yml exec neo4j cypher-shell -u neo4j -p ml_password "RETURN 1"
```

**Solutions**:
- Wait for services to fully initialize
- Check environment variables in .env.local
- Verify network connectivity between containers

#### 3. Memory/Performance Issues

**Symptoms**: Slow performance or out-of-memory errors

**Diagnosis**:
```bash
docker stats
make monitor-local
```

**Solutions**:
- Increase Docker memory allocation
- Reduce resource limits in docker-compose.local.yml
- Close unnecessary applications

#### 4. Port Conflicts

**Symptoms**: "Port already in use" errors

**Diagnosis**:
```bash
lsof -i :5432  # PostgreSQL
lsof -i :7474  # Neo4j
lsof -i :8000  # Application
```

**Solutions**:
- Stop conflicting services
- Change ports in docker-compose.local.yml
- Use different port mappings

## Advanced Troubleshooting

### Debug Mode Setup
```bash
# Enable debug logging
export ML_DEBUG=true
export ML_LOG_LEVEL=DEBUG

# Start with verbose output
docker compose -f docker-compose.local.yml up --verbose
```

### Container Inspection
```bash
# Enter container for debugging
docker compose -f docker-compose.local.yml exec multimodal-librarian bash
docker compose -f docker-compose.local.yml exec postgres bash

# Check container logs
docker compose -f docker-compose.local.yml logs -f [service-name]
```

### Network Debugging
```bash
# Test network connectivity
docker compose -f docker-compose.local.yml exec multimodal-librarian ping postgres
docker compose -f docker-compose.local.yml exec multimodal-librarian nslookup neo4j

# Check network configuration
docker network ls
docker network inspect multimodal-librarian_default
```