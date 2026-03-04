# Local Development Troubleshooting Guide

This guide covers common issues encountered when setting up and using the local development environment for the Multimodal Librarian application.

## Table of Contents

1. [Docker Compose Issues](#docker-compose-issues)
2. [Database Connection Problems](#database-connection-problems)
3. [Service Startup Issues](#service-startup-issues)
4. [Performance Problems](#performance-problems)
5. [Environment Configuration Issues](#environment-configuration-issues)
6. [Volume Mount Problems](#volume-mount-problems)
7. [Network Connectivity Issues](#network-connectivity-issues)
8. [Resource Exhaustion](#resource-exhaustion)
9. [Application-Specific Issues](#application-specific-issues)
10. [Development Workflow Issues](#development-workflow-issues)

---

## Docker Compose Issues

### Issue: Services fail to start with "port already in use" error

**Symptoms:**
```
ERROR: for postgres  Cannot start service postgres: driver failed programming external connectivity on endpoint
```

**Causes:**
- Another service is using the same port
- Previous containers weren't properly cleaned up

**Solutions:**
1. Check what's using the port:
   ```bash
   lsof -i :5432  # For PostgreSQL
   lsof -i :7474  # For Neo4j HTTP
   lsof -i :7687  # For Neo4j Bolt
   lsof -i :19530 # For Milvus
   ```

2. Stop conflicting services:
   ```bash
   # Stop local PostgreSQL
   brew services stop postgresql
   
   # Or kill specific processes
   sudo kill -9 <PID>
   ```

3. Clean up Docker containers:
   ```bash
   docker-compose -f docker-compose.local.yml down -v
   docker system prune -f
   ```

### Issue: "No space left on device" during container startup

**Symptoms:**
```
ERROR: Could not install packages due to an EnvironmentError: [Errno 28] No space left on device
```

**Solutions:**
1. Clean up Docker resources:
   ```bash
   docker system df  # Check disk usage
   docker system prune -a --volumes  # Clean everything
   ```

2. Remove unused images and containers:
   ```bash
   docker image prune -a
   docker container prune
   docker volume prune
   ```

3. Increase Docker Desktop disk allocation (macOS/Windows)

### Issue: Services start but health checks fail

**Symptoms:**
- Containers show as "unhealthy" in `docker-compose ps`
- Application can't connect to databases

**Solutions:**
1. Check service logs:
   ```bash
   docker-compose -f docker-compose.local.yml logs postgres
   docker-compose -f docker-compose.local.yml logs neo4j
   docker-compose -f docker-compose.local.yml logs milvus
   ```

2. Verify health check commands:
   ```bash
   # Test PostgreSQL manually
   docker-compose -f docker-compose.local.yml exec postgres pg_isready -U ml_user -d multimodal_librarian
   
   # Test Neo4j manually
   docker-compose -f docker-compose.local.yml exec neo4j cypher-shell -u neo4j -p ml_password "RETURN 1"
   ```

3. Increase health check timeouts in `docker-compose.local.yml`:
   ```yaml
   healthcheck:
     test: ["CMD-SHELL", "pg_isready -U ml_user -d multimodal_librarian"]
     interval: 30s  # Increase from 10s
     timeout: 10s   # Increase from 5s
     retries: 10    # Increase from 5
   ```

---

## Database Connection Problems

### Issue: PostgreSQL connection refused

**Symptoms:**
```
psycopg2.OperationalError: could not connect to server: Connection refused
```

**Solutions:**
1. Verify PostgreSQL is running:
   ```bash
   docker-compose -f docker-compose.local.yml ps postgres
   ```

2. Check PostgreSQL logs:
   ```bash
   docker-compose -f docker-compose.local.yml logs postgres
   ```

3. Test connection manually:
   ```bash
   docker-compose -f docker-compose.local.yml exec postgres psql -U ml_user -d multimodal_librarian -c "SELECT 1;"
   ```

4. Verify environment variables:
   ```bash
   # Check .env.local file
   cat .env.local | grep POSTGRES
   ```

### Issue: Neo4j authentication failed

**Symptoms:**
```
neo4j.exceptions.AuthError: The client is unauthorized due to authentication failure.
```

**Solutions:**
1. Reset Neo4j password:
   ```bash
   docker-compose -f docker-compose.local.yml exec neo4j neo4j-admin set-initial-password ml_password
   ```

2. Check Neo4j logs:
   ```bash
   docker-compose -f docker-compose.local.yml logs neo4j
   ```

3. Access Neo4j browser and reset manually:
   - Open http://localhost:7474
   - Login with neo4j/neo4j (default)
   - Change password to ml_password

### Issue: Milvus connection timeout

**Symptoms:**
```
MilvusException: <MilvusException: (code=2, message=Fail connecting to server on localhost:19530. Timeout)>
```

**Solutions:**
1. Check Milvus dependencies:
   ```bash
   docker-compose -f docker-compose.local.yml ps etcd minio
   ```

2. Restart Milvus stack:
   ```bash
   docker-compose -f docker-compose.local.yml restart etcd minio milvus
   ```

3. Verify Milvus health:
   ```bash
   curl -f http://localhost:9091/healthz
   ```

4. Check Milvus logs:
   ```bash
   docker-compose -f docker-compose.local.yml logs milvus
   ```

---

## Service Startup Issues

### Issue: Application fails to start with import errors

**Symptoms:**
```
ModuleNotFoundError: No module named 'multimodal_librarian'
```

**Solutions:**
1. Rebuild the application container:
   ```bash
   docker-compose -f docker-compose.local.yml build multimodal-librarian
   ```

2. Check Python path in container:
   ```bash
   docker-compose -f docker-compose.local.yml exec multimodal-librarian python -c "import sys; print(sys.path)"
   ```

3. Verify volume mounts:
   ```bash
   docker-compose -f docker-compose.local.yml exec multimodal-librarian ls -la /app
   ```

### Issue: Services start in wrong order

**Symptoms:**
- Application starts before databases are ready
- Connection errors during startup

**Solutions:**
1. Use wait script:
   ```bash
   # Run wait script manually
   ./scripts/wait-for-services.sh
   ```

2. Check depends_on configuration in docker-compose.local.yml

3. Add startup delays:
   ```yaml
   multimodal-librarian:
     depends_on:
       postgres:
         condition: service_healthy
       neo4j:
         condition: service_healthy
       milvus:
         condition: service_healthy
   ```

### Issue: Hot reload not working

**Symptoms:**
- Code changes don't trigger application restart
- Need to manually restart container

**Solutions:**
1. Check volume mounts:
   ```yaml
   volumes:
     - ./src:/app/src
     - ./tests:/app/tests
   ```

2. Verify file watching:
   ```bash
   docker-compose -f docker-compose.local.yml exec multimodal-librarian ls -la /app/src
   ```

3. Use development command:
   ```bash
   docker-compose -f docker-compose.local.yml exec multimodal-librarian uvicorn src.multimodal_librarian.main:app --reload --host 0.0.0.0
   ```

---

## Performance Problems

### Issue: Slow database queries

**Symptoms:**
- Long response times
- Timeouts during operations

**Solutions:**
1. Check database resource usage:
   ```bash
   docker stats
   ```

2. Optimize PostgreSQL configuration:
   ```sql
   -- Check current settings
   SHOW shared_buffers;
   SHOW effective_cache_size;
   
   -- Monitor slow queries
   SELECT query, mean_time, calls FROM pg_stat_statements ORDER BY mean_time DESC LIMIT 10;
   ```

3. Tune Neo4j memory settings:
   ```yaml
   neo4j:
     environment:
       - NEO4J_dbms_memory_heap_initial__size=1G
       - NEO4J_dbms_memory_heap_max__size=2G
       - NEO4J_dbms_memory_pagecache_size=1G
   ```

4. Optimize Milvus indexing:
   ```python
   # Use appropriate index type
   collection.create_index("embeddings", {"index_type": "IVF_FLAT", "metric_type": "L2", "params": {"nlist": 128}})
   ```

### Issue: High memory usage

**Symptoms:**
- System becomes unresponsive
- Docker containers killed by OOM

**Solutions:**
1. Monitor memory usage:
   ```bash
   docker stats --format "table {{.Container}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.MemPerc}}"
   ```

2. Reduce container memory limits:
   ```yaml
   services:
     postgres:
       deploy:
         resources:
           limits:
             memory: 512M
   ```

3. Optimize application memory:
   ```python
   # Use connection pooling
   DATABASE_URL = "postgresql://user:pass@localhost/db?pool_size=5&max_overflow=10"
   ```

### Issue: Slow container startup

**Symptoms:**
- Long wait times for services to become ready
- Timeouts during startup

**Solutions:**
1. Use multi-stage Docker builds:
   ```dockerfile
   FROM python:3.9-slim as builder
   # Install dependencies
   
   FROM python:3.9-slim as runtime
   # Copy only necessary files
   ```

2. Pre-pull images:
   ```bash
   docker-compose -f docker-compose.local.yml pull
   ```

3. Use local image registry:
   ```bash
   # Build and tag locally
   docker build -t local/multimodal-librarian .
   ```

---

## Environment Configuration Issues

### Issue: Environment variables not loaded

**Symptoms:**
- Application uses default values instead of configured ones
- Connection strings point to wrong hosts

**Solutions:**
1. Verify .env.local file exists:
   ```bash
   ls -la .env.local
   cat .env.local
   ```

2. Check environment variable loading:
   ```python
   import os
   print(os.environ.get('ML_POSTGRES_HOST'))
   ```

3. Ensure proper env_file configuration:
   ```yaml
   multimodal-librarian:
     env_file:
       - .env.local
   ```

### Issue: Configuration validation errors

**Symptoms:**
```
ValidationError: ML_POSTGRES_HOST field required
```

**Solutions:**
1. Copy example configuration:
   ```bash
   cp .env.local.example .env.local
   ```

2. Validate configuration:
   ```bash
   python scripts/validate-config.py
   ```

3. Check required variables:
   ```bash
   grep -E "^[A-Z_]+" .env.local.example
   ```

### Issue: Wrong database type selected

**Symptoms:**
- Application tries to connect to AWS services locally
- "local" services not found

**Solutions:**
1. Set database type explicitly:
   ```bash
   export ML_DATABASE_TYPE=local
   ```

2. Verify configuration factory:
   ```python
   from multimodal_librarian.config.config_factory import get_database_config
   config = get_database_config()
   print(config.database_type)
   ```

---

## Volume Mount Problems

### Issue: Permission denied errors

**Symptoms:**
```
PermissionError: [Errno 13] Permission denied: '/app/uploads/file.pdf'
```

**Solutions:**
1. Fix file permissions:
   ```bash
   sudo chown -R $(id -u):$(id -g) ./uploads
   chmod -R 755 ./uploads
   ```

2. Use proper user in Dockerfile:
   ```dockerfile
   RUN adduser --disabled-password --gecos '' appuser
   USER appuser
   ```

3. Set volume permissions:
   ```yaml
   volumes:
     - ./uploads:/app/uploads:rw
   ```

### Issue: Files not persisting between restarts

**Symptoms:**
- Data disappears when containers restart
- Database changes lost

**Solutions:**
1. Verify named volumes:
   ```yaml
   volumes:
     postgres_data:
     neo4j_data:
     milvus_data:
   ```

2. Check volume mounts:
   ```bash
   docker volume ls
   docker volume inspect local-development-conversion_postgres_data
   ```

3. Backup important data:
   ```bash
   ./scripts/backup-all-databases.sh
   ```

---

## Network Connectivity Issues

### Issue: Services can't communicate

**Symptoms:**
- Connection refused between containers
- DNS resolution failures

**Solutions:**
1. Check Docker network:
   ```bash
   docker network ls
   docker network inspect local-development-conversion_default
   ```

2. Test connectivity between containers:
   ```bash
   docker-compose -f docker-compose.local.yml exec multimodal-librarian ping postgres
   ```

3. Verify service names in configuration:
   ```yaml
   # Use service names, not localhost
   POSTGRES_HOST: postgres  # Not localhost
   NEO4J_HOST: neo4j       # Not localhost
   ```

### Issue: Port conflicts with host services

**Symptoms:**
- Can't access services from host
- Port binding errors

**Solutions:**
1. Change port mappings:
   ```yaml
   postgres:
     ports:
       - "5433:5432"  # Use different host port
   ```

2. Stop conflicting host services:
   ```bash
   sudo systemctl stop postgresql
   brew services stop postgresql
   ```

---

## Resource Exhaustion

### Issue: Disk space exhaustion

**Symptoms:**
- "No space left on device" errors
- Containers fail to start

**Solutions:**
1. Clean up Docker resources:
   ```bash
   docker system df
   docker system prune -a --volumes
   ```

2. Remove old logs:
   ```bash
   docker-compose -f docker-compose.local.yml exec postgres find /var/log -name "*.log" -mtime +7 -delete
   ```

3. Monitor disk usage:
   ```bash
   df -h
   du -sh ./data/*
   ```

### Issue: Memory exhaustion

**Symptoms:**
- System becomes unresponsive
- OOM killer terminates processes

**Solutions:**
1. Reduce memory limits:
   ```yaml
   deploy:
     resources:
       limits:
         memory: 1G
   ```

2. Monitor memory usage:
   ```bash
   free -h
   docker stats
   ```

3. Optimize queries and caching:
   ```python
   # Use pagination
   results = session.query(Model).limit(100).offset(page * 100)
   ```

### Issue: CPU exhaustion

**Symptoms:**
- High CPU usage
- Slow response times

**Solutions:**
1. Limit CPU usage:
   ```yaml
   deploy:
     resources:
       limits:
         cpus: '0.5'
   ```

2. Profile application:
   ```python
   import cProfile
   cProfile.run('your_function()')
   ```

---

## Application-Specific Issues

### Issue: Model loading failures

**Symptoms:**
```
OSError: [Errno 2] No such file or directory: 'model.bin'
```

**Solutions:**
1. Download models manually:
   ```bash
   python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"
   ```

2. Use model cache volume:
   ```yaml
   volumes:
     - model_cache:/root/.cache/huggingface
   ```

3. Set model path explicitly:
   ```python
   MODEL_PATH = os.environ.get('MODEL_PATH', '/app/models')
   ```

### Issue: Vector search not working

**Symptoms:**
- Empty search results
- Milvus collection errors

**Solutions:**
1. Check collection exists:
   ```python
   from pymilvus import connections, Collection
   connections.connect(host='localhost', port='19530')
   collection = Collection('documents')
   print(collection.num_entities)
   ```

2. Verify embeddings:
   ```python
   # Check embedding dimensions
   embeddings = model.encode(['test'])
   print(embeddings.shape)
   ```

3. Recreate collection:
   ```python
   collection.drop()
   # Recreate with correct schema
   ```

### Issue: Knowledge graph queries fail

**Symptoms:**
- Cypher syntax errors
- Empty graph results

**Solutions:**
1. Test queries in Neo4j browser:
   - Open http://localhost:7474
   - Run: `MATCH (n) RETURN count(n)`

2. Check node creation:
   ```cypher
   CREATE (d:Document {id: 'test', title: 'Test Document'})
   RETURN d
   ```

3. Verify relationships:
   ```cypher
   MATCH (d:Document)-[r]->(c:Concept)
   RETURN d, r, c LIMIT 10
   ```

---

## Development Workflow Issues

### Issue: Tests fail in local environment

**Symptoms:**
- Test database connection errors
- Fixture loading failures

**Solutions:**
1. Use test database:
   ```bash
   export ML_POSTGRES_DB=multimodal_librarian_test
   ```

2. Run tests with proper environment:
   ```bash
   ML_ENVIRONMENT=local pytest tests/
   ```

3. Reset test data:
   ```bash
   ./scripts/reset-test-databases.py
   ```

### Issue: Debugging not working

**Symptoms:**
- Breakpoints not hit
- Debug server not accessible

**Solutions:**
1. Enable debug mode:
   ```yaml
   multimodal-librarian:
     command: python -m debugpy --listen 0.0.0.0:5678 --wait-for-client -m uvicorn src.multimodal_librarian.main:app --reload --host 0.0.0.0
     ports:
       - "5678:5678"  # Debug port
   ```

2. Configure IDE debugger:
   - Host: localhost
   - Port: 5678
   - Path mappings: ./src -> /app/src

### Issue: Code changes not reflected

**Symptoms:**
- Old code still running
- Import errors after changes

**Solutions:**
1. Force rebuild:
   ```bash
   docker-compose -f docker-compose.local.yml build --no-cache multimodal-librarian
   ```

2. Clear Python cache:
   ```bash
   find . -name "*.pyc" -delete
   find . -name "__pycache__" -type d -exec rm -rf {} +
   ```

3. Restart with clean state:
   ```bash
   docker-compose -f docker-compose.local.yml down
   docker-compose -f docker-compose.local.yml up --build
   ```

---

## Quick Diagnostic Commands

### Health Check All Services
```bash
# Check all container status
docker-compose -f docker-compose.local.yml ps

# Check service health
./scripts/health-check-all-services.py

# Test database connections
python scripts/test-database-connectivity.py
```

### Resource Monitoring
```bash
# Monitor resource usage
docker stats

# Check disk usage
df -h
docker system df

# Monitor logs
docker-compose -f docker-compose.local.yml logs -f
```

### Network Diagnostics
```bash
# Test connectivity
docker-compose -f docker-compose.local.yml exec multimodal-librarian ping postgres

# Check port bindings
netstat -tulpn | grep -E "(5432|7474|7687|19530)"

# Inspect network
docker network inspect local-development-conversion_default
```

---

## Getting Help

### Log Collection
When reporting issues, collect these logs:
```bash
# Application logs
docker-compose -f docker-compose.local.yml logs multimodal-librarian > app.log

# Database logs
docker-compose -f docker-compose.local.yml logs postgres > postgres.log
docker-compose -f docker-compose.local.yml logs neo4j > neo4j.log
docker-compose -f docker-compose.local.yml logs milvus > milvus.log

# System information
docker version > system-info.txt
docker-compose version >> system-info.txt
uname -a >> system-info.txt
```

### Configuration Dump
```bash
# Export current configuration
env | grep ML_ > current-config.txt
docker-compose -f docker-compose.local.yml config > docker-config.yml
```

### Reset Everything
If all else fails, complete reset:
```bash
# Stop and remove everything
docker-compose -f docker-compose.local.yml down -v
docker system prune -a --volumes

# Remove configuration
rm .env.local

# Start fresh
cp .env.local.example .env.local
make dev-setup
make dev-local
```

---

## Prevention Tips

1. **Regular Maintenance**
   - Run `docker system prune` weekly
   - Monitor disk space regularly
   - Keep Docker Desktop updated

2. **Configuration Management**
   - Always use version control for .env files
   - Document any custom configurations
   - Test configuration changes in isolation

3. **Resource Management**
   - Set appropriate resource limits
   - Monitor memory and CPU usage
   - Use connection pooling

4. **Backup Strategy**
   - Regular database backups
   - Export important configurations
   - Document custom modifications

5. **Development Practices**
   - Use feature branches for experiments
   - Test changes in clean environment
   - Keep dependencies updated

This troubleshooting guide should help resolve most common issues encountered during local development. For additional help, consult the project documentation or reach out to the development team.