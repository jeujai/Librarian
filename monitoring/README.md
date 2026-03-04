# Monitoring and Dashboards for Local Development

This directory contains monitoring configuration and dashboards for the Multimodal Librarian local development environment.

## Overview

The monitoring setup provides:
- **Service Health Monitoring:** Real-time status of all services
- **Resource Usage Tracking:** CPU, memory, and disk usage
- **Application Metrics:** API performance, database operations, search metrics
- **Log Aggregation:** Centralized log viewing and analysis
- **Simple Dashboards:** Web-based monitoring interfaces

## Quick Start

### Start Monitoring Services

```bash
# Start with monitoring profile
docker-compose -f docker-compose.local.yml --profile monitoring up -d

# Or start specific monitoring services
docker-compose -f docker-compose.local.yml up -d log-viewer
```

### Access Monitoring Interfaces

- **Log Viewer (Dozzle):** http://localhost:8080
- **Simple Dashboard:** http://localhost:8000/monitoring (when app is running)
- **Redis Commander:** http://localhost:8081 (with admin-tools profile)
- **pgAdmin:** http://localhost:5050 (with admin-tools profile)
- **Neo4j Browser:** http://localhost:7474
- **Attu (Milvus):** http://localhost:3000 (with admin-tools profile)
- **MinIO Console:** http://localhost:9001

## Monitoring Components

### 1. Service Health Monitoring

**Health Check Script:**
```bash
# Check all services
scripts/health-check.sh

# Check specific service
scripts/health-check.sh postgres
```

**Health Check Endpoints:**
- Application: http://localhost:8000/health/simple
- Application (detailed): http://localhost:8000/health/detailed
- Milvus: http://localhost:9091/healthz
- MinIO: http://localhost:9000/minio/health/live

### 2. Resource Monitoring

**Docker Stats:**
```bash
# Real-time resource usage
docker stats

# Specific containers
docker stats $(docker-compose -f docker-compose.local.yml ps -q)
```

**System Resource Script:**
```bash
scripts/monitor-resources.sh
```

### 3. Log Monitoring

**Real-time Log Viewing:**
```bash
# All services
docker-compose -f docker-compose.local.yml logs -f

# Specific service
docker-compose -f docker-compose.local.yml logs -f multimodal-librarian

# With Dozzle web interface
# http://localhost:8080
```

**Log Analysis:**
```bash
# Analyze recent logs
scripts/logs-analyze.sh

# Analyze specific time range
scripts/logs-analyze.sh 30m
```

## Dashboard Configuration

### Simple Web Dashboard

The application includes a built-in monitoring dashboard accessible at:
http://localhost:8000/monitoring

**Features:**
- Service status indicators
- Resource usage graphs
- Recent error summary
- API endpoint statistics
- Database connection status

### Custom Monitoring Scripts

**System Overview:**
```bash
#!/bin/bash
# monitoring/system-overview.sh

echo "=== Multimodal Librarian System Overview ==="
echo "Generated: $(date)"
echo ""

# Service status
echo "Service Status:"
docker-compose -f docker-compose.local.yml ps

echo ""

# Resource usage
echo "Resource Usage:"
docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.NetIO}}\t{{.BlockIO}}"

echo ""

# Disk usage
echo "Disk Usage:"
df -h . | tail -1
du -sh data/ logs/ uploads/ 2>/dev/null || echo "Data directories not found"

echo ""

# Recent errors
echo "Recent Errors (last hour):"
docker-compose -f docker-compose.local.yml logs --since=1h | grep -i error | wc -l
```

## Environment Variables

Configure monitoring in your `.env.local` file:

```bash
# Monitoring Configuration
ENABLE_MONITORING=true
MONITORING_PORT=8080
MONITORING_INTERVAL=30

# Health Check Configuration
HEALTH_CHECK_INTERVAL=30
HEALTH_CHECK_TIMEOUT=10
HEALTH_CHECK_RETRIES=3

# Metrics Collection
ENABLE_METRICS_COLLECTION=true
METRICS_COLLECTION_INTERVAL=60
METRICS_RETENTION_DAYS=7

# Alerting (for future use)
ENABLE_ALERTING=false
ALERT_EMAIL=admin@localhost
ALERT_WEBHOOK_URL=
```

## Monitoring Profiles

### Development Profile (Default)
- Basic health checks
- Log viewing via Docker commands
- Manual monitoring scripts

### Enhanced Monitoring Profile
```bash
# Start with enhanced monitoring
docker-compose -f docker-compose.local.yml --profile monitoring --profile admin-tools up -d
```

Includes:
- Dozzle log viewer
- All admin interfaces
- Resource monitoring
- Automated health checks

## Custom Metrics Collection

### Application Metrics

The application can expose metrics at `/metrics` endpoint:

```python
# Example metrics in the application
from prometheus_client import Counter, Histogram, Gauge

# Request counters
api_requests_total = Counter('api_requests_total', 'Total API requests', ['method', 'endpoint'])
api_request_duration = Histogram('api_request_duration_seconds', 'API request duration')

# Database metrics
db_connections_active = Gauge('db_connections_active', 'Active database connections')
db_query_duration = Histogram('db_query_duration_seconds', 'Database query duration')

# Search metrics
search_requests_total = Counter('search_requests_total', 'Total search requests')
search_results_count = Histogram('search_results_count', 'Number of search results')
```

### Database Metrics

**PostgreSQL Metrics:**
```sql
-- Active connections
SELECT count(*) FROM pg_stat_activity WHERE state = 'active';

-- Database size
SELECT pg_size_pretty(pg_database_size('multimodal_librarian'));

-- Slow queries
SELECT query, mean_time, calls FROM pg_stat_statements ORDER BY mean_time DESC LIMIT 10;
```

**Neo4j Metrics:**
```cypher
// Database statistics
CALL dbms.queryJmx("org.neo4j:instance=kernel#0,name=Store file sizes")
YIELD attributes
RETURN attributes;

// Active queries
CALL dbms.listQueries()
YIELD query, elapsedTimeMillis
WHERE elapsedTimeMillis > 1000
RETURN query, elapsedTimeMillis;
```

**Milvus Metrics:**
```python
from pymilvus import utility

# Collection statistics
stats = utility.get_query_segment_info("knowledge_chunks")
print(f"Segments: {len(stats)}")

# Index information
collection = Collection("knowledge_chunks")
print(f"Entities: {collection.num_entities}")
```

## Alerting and Notifications

### Simple Alert Script

```bash
#!/bin/bash
# monitoring/check-alerts.sh

# Check for high error rate
error_count=$(docker-compose -f docker-compose.local.yml logs --since=5m | grep -i error | wc -l)

if [ "$error_count" -gt 10 ]; then
    echo "ALERT: High error rate detected ($error_count errors in last 5 minutes)"
    # Send notification (email, webhook, etc.)
fi

# Check for service failures
failed_services=$(docker-compose -f docker-compose.local.yml ps | grep -c "Exit\|Restarting")

if [ "$failed_services" -gt 0 ]; then
    echo "ALERT: $failed_services services are not running properly"
fi

# Check disk space
disk_usage=$(df . | tail -1 | awk '{print $5}' | sed 's/%//')

if [ "$disk_usage" -gt 90 ]; then
    echo "ALERT: Disk usage is at ${disk_usage}%"
fi
```

### Webhook Notifications

```bash
# Send alert to webhook
send_alert() {
    local message="$1"
    local webhook_url="$ALERT_WEBHOOK_URL"
    
    if [ -n "$webhook_url" ]; then
        curl -X POST "$webhook_url" \
             -H "Content-Type: application/json" \
             -d "{\"text\": \"$message\"}"
    fi
}
```

## Performance Monitoring

### Application Performance

**API Response Times:**
```bash
# Monitor API response times
curl -w "@monitoring/curl-format.txt" -s -o /dev/null http://localhost:8000/health/simple
```

**curl-format.txt:**
```
     time_namelookup:  %{time_namelookup}\n
        time_connect:  %{time_connect}\n
     time_appconnect:  %{time_appconnect}\n
    time_pretransfer:  %{time_pretransfer}\n
       time_redirect:  %{time_redirect}\n
  time_starttransfer:  %{time_starttransfer}\n
                     ----------\n
          time_total:  %{time_total}\n
```

### Database Performance

**PostgreSQL Performance:**
```bash
# Monitor PostgreSQL performance
docker-compose -f docker-compose.local.yml exec postgres psql -U ml_user -d multimodal_librarian -c "
SELECT 
    schemaname,
    tablename,
    n_tup_ins as inserts,
    n_tup_upd as updates,
    n_tup_del as deletes,
    n_tup_hot_upd as hot_updates
FROM pg_stat_user_tables 
ORDER BY n_tup_ins + n_tup_upd + n_tup_del DESC;
"
```

## Troubleshooting

### Common Monitoring Issues

**Dozzle not accessible:**
```bash
# Check if monitoring profile is started
docker-compose -f docker-compose.local.yml --profile monitoring ps

# Check Dozzle logs
docker-compose -f docker-compose.local.yml logs log-viewer
```

**High resource usage:**
```bash
# Identify resource-heavy containers
docker stats --no-stream | sort -k3 -hr

# Check for memory leaks
docker-compose -f docker-compose.local.yml logs | grep -i "memory\|oom"
```

**Service health check failures:**
```bash
# Check individual service health
scripts/health-check.sh --verbose

# Check service logs for errors
docker-compose -f docker-compose.local.yml logs [service-name]
```

## Best Practices

### Monitoring Strategy

1. **Start Simple:** Use basic Docker commands and scripts
2. **Add Gradually:** Introduce more sophisticated monitoring as needed
3. **Focus on Key Metrics:** Monitor what matters for development
4. **Automate Checks:** Use scripts for routine monitoring tasks
5. **Document Issues:** Keep track of common problems and solutions

### Resource Management

1. **Set Resource Limits:** Use Docker resource constraints
2. **Monitor Trends:** Track resource usage over time
3. **Clean Up Regularly:** Remove old logs and unused data
4. **Optimize Queries:** Monitor and optimize slow database queries

### Development Workflow

1. **Check Health First:** Always verify system health before development
2. **Monitor During Development:** Keep an eye on resource usage
3. **Review Logs Regularly:** Check for errors and warnings
4. **Performance Test:** Validate performance after changes

## Integration with CI/CD

### Health Check in CI

```yaml
# .github/workflows/test.yml
- name: Health Check
  run: |
    docker-compose -f docker-compose.local.yml up -d
    sleep 30
    scripts/health-check.sh --ci
```

### Performance Regression Detection

```bash
# Compare performance metrics
scripts/performance-baseline.sh > baseline.json
# ... make changes ...
scripts/performance-test.sh > current.json
scripts/compare-performance.sh baseline.json current.json
```

This monitoring setup provides a solid foundation for local development while remaining lightweight and easy to use.