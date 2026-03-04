# System Troubleshooting Guide

## Overview

This guide provides comprehensive troubleshooting procedures for the Multimodal Librarian system. It covers common issues, diagnostic procedures, and resolution steps for various system components.

## Quick Diagnostic Checklist

### 1. System Health Check
```bash
# Check overall system health
curl http://localhost:8000/health/detailed

# Check individual components
curl http://localhost:8000/health/simple
curl http://localhost:8000/api/monitoring/metrics
```

### 2. Service Status Check
```bash
# Check if main application is running
ps aux | grep uvicorn

# Check database connectivity
psql -h localhost -U username -d database_name -c "SELECT 1;"

# Check Redis connectivity
redis-cli ping

# Check vector store connectivity (if using Milvus)
curl http://localhost:19121/health
```

### 3. Log Analysis
```bash
# Check application logs
tail -f /var/log/multimodal-librarian/app.log

# Check error logs
grep -i error /var/log/multimodal-librarian/app.log | tail -20

# Check performance logs
grep -i "slow\|timeout\|performance" /var/log/multimodal-librarian/app.log
```

## Common Issues and Solutions

### 1. Application Startup Issues

#### Issue: Application fails to start
**Symptoms:**
- Server doesn't respond on port 8000
- Import errors in logs
- Configuration errors

**Diagnostic Steps:**
```bash
# Check if port is in use
netstat -tulpn | grep :8000

# Check application logs
tail -f logs/app.log

# Test configuration
python -c "from src.multimodal_librarian.config import get_settings; print(get_settings())"
```

**Common Causes and Solutions:**

1. **Port Already in Use**
   ```bash
   # Find process using port 8000
   lsof -i :8000
   
   # Kill the process
   kill -9 <PID>
   
   # Or use different port
   uvicorn src.multimodal_librarian.main:app --port 8001
   ```

2. **Missing Dependencies**
   ```bash
   # Install missing dependencies
   pip install -r requirements.txt
   
   # Check for import errors
   python -c "import src.multimodal_librarian.main"
   ```

3. **Configuration Issues**
   ```bash
   # Check environment variables
   env | grep -E "(DATABASE|REDIS|MILVUS|AWS)"
   
   # Validate configuration
   python -m src.multimodal_librarian.config.validate
   ```

#### Issue: Circular Import Errors
**Symptoms:**
- ImportError during startup
- "cannot import name" errors
- Module loading failures

**Resolution:**
```bash
# Check for circular imports
python -c "
import sys
sys.path.insert(0, 'src')
from multimodal_librarian.components.vector_store.search_service import EnhancedSemanticSearchService
print('Search service loaded successfully')
"

# If circular import detected, check search_types.py
python -c "
from multimodal_librarian.models.search_types import SearchResult
print('Search types loaded successfully')
"
```

**Fix Applied:**
The system now uses `search_types.py` to avoid circular imports between search components.

### 2. Database Connection Issues

#### Issue: Database connection failures
**Symptoms:**
- "connection refused" errors
- Timeout errors
- Authentication failures

**Diagnostic Steps:**
```bash
# Test database connectivity
pg_isready -h localhost -p 5432

# Test authentication
psql -h localhost -U username -d database_name -c "SELECT version();"

# Check connection pool status
curl http://localhost:8000/health/detailed | jq '.components.database'
```

**Solutions:**

1. **Database Not Running**
   ```bash
   # Start PostgreSQL
   sudo systemctl start postgresql
   
   # Check status
   sudo systemctl status postgresql
   ```

2. **Connection Pool Exhausted**
   ```bash
   # Check active connections
   psql -c "SELECT count(*) FROM pg_stat_activity;"
   
   # Restart application to reset pool
   sudo systemctl restart multimodal-librarian
   ```

3. **Authentication Issues**
   ```bash
   # Check credentials in environment
   echo $DATABASE_URL
   
   # Test with correct credentials
   psql $DATABASE_URL -c "SELECT 1;"
   ```

### 3. Search Service Issues

#### Issue: Search operations failing
**Symptoms:**
- Search returns empty results
- Timeout errors
- Fallback service activation

**Diagnostic Steps:**
```bash
# Test search endpoint
curl -X POST http://localhost:8000/api/search \
  -H "Content-Type: application/json" \
  -d '{"query": "test", "limit": 5}'

# Check search service health
curl http://localhost:8000/health/detailed | jq '.components.search_service'

# Check vector store connectivity
curl http://localhost:8000/health/detailed | jq '.components.vector_store'
```

**Solutions:**

1. **Vector Store Connection Issues**
   ```bash
   # Check Milvus/OpenSearch status
   curl http://localhost:19121/health  # Milvus
   curl http://localhost:9200/_cluster/health  # OpenSearch
   
   # Restart vector store service
   sudo systemctl restart milvus-standalone
   ```

2. **Search Service Fallback Active**
   ```bash
   # Check fallback status
   curl http://localhost:8000/api/monitoring/metrics | jq '.search.fallback_rate'
   
   # Reset search service
   curl -X POST http://localhost:8000/api/search/reset
   ```

3. **No Documents Indexed**
   ```bash
   # Check document count
   curl http://localhost:8000/api/documents/ | jq '.total_count'
   
   # Check processing status
   curl http://localhost:8000/api/analytics/documents | jq '.document_stats'
   ```

#### Issue: Search performance degradation
**Symptoms:**
- Slow search responses (>1 second)
- High CPU usage
- Memory issues

**Diagnostic Steps:**
```bash
# Check search performance metrics
curl http://localhost:8000/api/monitoring/metrics | jq '.search'

# Monitor resource usage
top -p $(pgrep -f multimodal-librarian)

# Check cache performance
curl http://localhost:8000/api/monitoring/metrics | jq '.cache'
```

**Solutions:**

1. **Cache Issues**
   ```bash
   # Clear search cache
   curl -X DELETE http://localhost:8000/api/cache/search
   
   # Check Redis connectivity
   redis-cli ping
   
   # Monitor cache hit rate
   redis-cli info stats | grep hit_rate
   ```

2. **Vector Store Performance**
   ```bash
   # Check vector store metrics
   curl http://localhost:19121/metrics  # Milvus
   
   # Optimize vector store
   curl -X POST http://localhost:8000/api/vector-store/optimize
   ```

### 4. Document Processing Issues

#### Issue: Document upload failures
**Symptoms:**
- Upload timeouts
- Processing stuck
- File validation errors

**Diagnostic Steps:**
```bash
# Check upload endpoint
curl -X POST http://localhost:8000/api/documents/upload \
  -F "file=@test.pdf" \
  -F "title=Test Document"

# Check processing queue
curl http://localhost:8000/api/documents/ | jq '.documents[] | select(.processing_status != "completed")'

# Check storage connectivity
aws s3 ls s3://your-bucket-name/documents/
```

**Solutions:**

1. **File Size Issues**
   ```bash
   # Check file size limits
   curl http://localhost:8000/api/documents/limits
   
   # Increase limits in configuration
   export MAX_FILE_SIZE_MB=200
   ```

2. **Processing Queue Stuck**
   ```bash
   # Check Celery workers (if using)
   celery -A src.multimodal_librarian.services.celery_service inspect active
   
   # Restart processing service
   sudo systemctl restart celery-worker
   ```

3. **S3 Connectivity Issues**
   ```bash
   # Test AWS credentials
   aws sts get-caller-identity
   
   # Test S3 access
   aws s3 ls s3://your-bucket-name/
   ```

### 5. Memory and Performance Issues

#### Issue: High memory usage
**Symptoms:**
- Application using >2GB memory
- Out of memory errors
- Slow response times

**Diagnostic Steps:**
```bash
# Check memory usage
free -h
ps aux --sort=-%mem | head -10

# Check application memory
curl http://localhost:8000/api/monitoring/metrics | jq '.resources.memory_usage_mb'

# Profile memory usage
python -m memory_profiler src/multimodal_librarian/main.py
```

**Solutions:**

1. **Memory Leaks**
   ```bash
   # Enable memory optimization
   curl -X POST http://localhost:8000/api/memory-optimization/enable
   
   # Force garbage collection
   curl -X POST http://localhost:8000/api/memory-optimization/gc
   
   # Check for leaks
   curl http://localhost:8000/api/memory-optimization/profile
   ```

2. **Cache Size Issues**
   ```bash
   # Reduce cache size
   curl -X PUT http://localhost:8000/api/cache/config \
     -H "Content-Type: application/json" \
     -d '{"max_size_mb": 256}'
   
   # Clear caches
   curl -X DELETE http://localhost:8000/api/cache/all
   ```

#### Issue: High CPU usage
**Symptoms:**
- CPU usage >80%
- Slow response times
- Request timeouts

**Solutions:**

1. **Optimize Search Operations**
   ```bash
   # Enable search optimization
   curl -X POST http://localhost:8000/api/search/optimize
   
   # Reduce concurrent operations
   curl -X PUT http://localhost:8000/api/config/concurrency \
     -d '{"max_workers": 4}'
   ```

2. **Database Query Optimization**
   ```bash
   # Check slow queries
   psql -c "SELECT query, mean_time FROM pg_stat_statements ORDER BY mean_time DESC LIMIT 10;"
   
   # Optimize database
   curl -X POST http://localhost:8000/api/database/optimize
   ```

### 6. Authentication and Authorization Issues

#### Issue: Authentication failures
**Symptoms:**
- 401 Unauthorized errors
- Token validation failures
- Login issues

**Diagnostic Steps:**
```bash
# Test authentication endpoint
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "test", "password": "test"}'

# Validate JWT token
curl -X GET http://localhost:8000/api/auth/validate \
  -H "Authorization: Bearer <token>"
```

**Solutions:**

1. **JWT Token Issues**
   ```bash
   # Check token expiration
   python -c "
   import jwt
   token = 'your_token_here'
   decoded = jwt.decode(token, options={'verify_signature': False})
   print(decoded)
   "
   
   # Refresh token
   curl -X POST http://localhost:8000/api/auth/refresh \
     -H "Content-Type: application/json" \
     -d '{"refresh_token": "refresh_token_here"}'
   ```

2. **Database Authentication Issues**
   ```bash
   # Check user exists
   psql -c "SELECT * FROM users WHERE username = 'test_user';"
   
   # Reset password
   curl -X POST http://localhost:8000/api/auth/reset-password \
     -d '{"username": "test_user"}'
   ```

### 7. WebSocket Connection Issues

#### Issue: Chat WebSocket failures
**Symptoms:**
- WebSocket connection refused
- Chat messages not delivered
- Connection drops

**Diagnostic Steps:**
```bash
# Test WebSocket endpoint
wscat -c ws://localhost:8000/ws/chat/test_user

# Check WebSocket connections
netstat -an | grep :8000 | grep ESTABLISHED

# Check application logs for WebSocket errors
grep -i websocket /var/log/multimodal-librarian/app.log
```

**Solutions:**

1. **Connection Issues**
   ```bash
   # Check if WebSocket is enabled
   curl http://localhost:8000/health/detailed | jq '.components.websocket'
   
   # Restart application
   sudo systemctl restart multimodal-librarian
   ```

2. **Message Delivery Issues**
   ```bash
   # Check connection manager
   curl http://localhost:8000/api/chat/connections
   
   # Clear connection cache
   curl -X DELETE http://localhost:8000/api/chat/connections/clear
   ```

## Performance Optimization

### 1. Search Performance
```bash
# Enable search result caching
curl -X POST http://localhost:8000/api/search/cache/enable

# Optimize vector operations
curl -X POST http://localhost:8000/api/vector-store/optimize

# Monitor search performance
watch -n 5 'curl -s http://localhost:8000/api/monitoring/metrics | jq ".search.avg_latency_ms"'
```

### 2. Database Performance
```bash
# Analyze database performance
psql -c "SELECT * FROM pg_stat_statements ORDER BY total_time DESC LIMIT 10;"

# Optimize database
curl -X POST http://localhost:8000/api/database/optimize

# Update statistics
psql -c "ANALYZE;"
```

### 3. Memory Optimization
```bash
# Enable memory optimization
curl -X POST http://localhost:8000/api/memory-optimization/enable

# Monitor memory usage
watch -n 10 'curl -s http://localhost:8000/api/monitoring/metrics | jq ".resources.memory_usage_mb"'

# Force garbage collection
curl -X POST http://localhost:8000/api/memory-optimization/gc
```

## Monitoring and Alerting

### 1. Set Up Monitoring
```bash
# Enable comprehensive monitoring
curl -X POST http://localhost:8000/api/monitoring/enable

# Configure alerts
curl -X POST http://localhost:8000/api/monitoring/alerts \
  -H "Content-Type: application/json" \
  -d '{
    "response_time_threshold_ms": 1000,
    "error_rate_threshold": 0.05,
    "memory_threshold_mb": 2048
  }'
```

### 2. Health Check Automation
```bash
# Create health check script
cat > health_check.sh << 'EOF'
#!/bin/bash
HEALTH_URL="http://localhost:8000/health/detailed"
RESPONSE=$(curl -s $HEALTH_URL)
STATUS=$(echo $RESPONSE | jq -r '.status')

if [ "$STATUS" != "healthy" ]; then
    echo "ALERT: System unhealthy - $RESPONSE"
    # Send notification (email, Slack, etc.)
    exit 1
fi

echo "System healthy"
EOF

chmod +x health_check.sh

# Add to crontab for regular checks
echo "*/5 * * * * /path/to/health_check.sh" | crontab -
```

### 3. Log Monitoring
```bash
# Monitor error logs
tail -f /var/log/multimodal-librarian/app.log | grep -i error

# Set up log rotation
cat > /etc/logrotate.d/multimodal-librarian << 'EOF'
/var/log/multimodal-librarian/*.log {
    daily
    rotate 30
    compress
    delaycompress
    missingok
    notifempty
    create 644 app app
    postrotate
        systemctl reload multimodal-librarian
    endscript
}
EOF
```

## Emergency Procedures

### 1. System Recovery
```bash
# Emergency restart
sudo systemctl restart multimodal-librarian

# Reset all caches
curl -X DELETE http://localhost:8000/api/cache/all

# Reset search service
curl -X POST http://localhost:8000/api/search/reset

# Clear processing queue
curl -X DELETE http://localhost:8000/api/documents/processing-queue/clear
```

### 2. Database Recovery
```bash
# Check database integrity
psql -c "SELECT pg_database_size(current_database());"

# Vacuum and analyze
psql -c "VACUUM ANALYZE;"

# Reindex if needed
psql -c "REINDEX DATABASE multimodal_librarian;"
```

### 3. Rollback Procedures
```bash
# Rollback to previous version
git checkout <previous_commit>
docker build -t multimodal-librarian:rollback .
docker stop multimodal-librarian
docker run -d --name multimodal-librarian multimodal-librarian:rollback

# Restore database backup
pg_restore -d multimodal_librarian backup_file.sql
```

## Contact and Escalation

### Internal Team
- **Development Team**: dev-team@company.com
- **Operations Team**: ops-team@company.com
- **On-call Engineer**: +1-555-0123

### External Support
- **AWS Support**: AWS Console → Support
- **Database Support**: PostgreSQL Community
- **Vector Store Support**: Milvus/OpenSearch Documentation

### Escalation Matrix
1. **Level 1**: Application restart, cache clearing
2. **Level 2**: Database optimization, service reconfiguration
3. **Level 3**: Infrastructure changes, code deployment
4. **Level 4**: Architecture changes, external support

---

*This troubleshooting guide is maintained as part of the system documentation. Report issues or improvements to the development team. Last updated: January 2026*