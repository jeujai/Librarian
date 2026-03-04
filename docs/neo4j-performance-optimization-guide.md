# Neo4j Performance Optimization Guide

## Overview

This guide documents the Neo4j performance optimizations implemented for local development as part of the local-development-conversion spec. The optimizations are designed to meet the following requirements:

- **Memory usage**: < 8GB total for all services (Neo4j target: ~1.5GB)
- **Query performance**: Within 20% of AWS Neptune performance
- **Startup time**: < 2 minutes for the entire stack
- **CPU usage**: Reasonable on development machines

## Memory Optimization

### Heap Memory Configuration

```yaml
# Docker Compose Environment Variables
- NEO4J_server_memory_heap_initial__size=512m
- NEO4J_server_memory_heap_max__size=1G
```

**Rationale**: 
- Initial heap of 512MB provides fast startup
- Maximum heap of 1GB limits memory usage while providing sufficient space for development workloads
- Allows JVM to scale memory usage based on actual needs

### Page Cache Optimization

```yaml
- NEO4J_server_memory_pagecache_size=512m
```

**Rationale**:
- 512MB page cache provides good performance for development datasets
- Balances memory usage with query performance
- Sufficient for typical development knowledge graphs (< 100K nodes)

### Off-Heap Memory

```yaml
- NEO4J_server_memory_off__heap_max__size=256m
```

**Rationale**:
- Limits off-heap memory usage for predictable memory consumption
- Prevents memory leaks in development environment
- Provides buffer for transaction state and query processing

## Query Performance Optimization

### Query Cache Configuration

```properties
# neo4j.conf
dbms.query_cache_size=1000
cypher.query_plan_cache_size=1000
```

**Benefits**:
- Caches frequently used queries for faster execution
- Reduces query planning overhead for repeated queries
- Improves response times for development testing

### Cypher Runtime Optimization

```properties
cypher.default_language_version=5
cypher.runtime=parallel
cypher.planner=cost
```

**Benefits**:
- Uses latest Cypher version with performance improvements
- Enables parallel query execution for better performance
- Uses cost-based optimizer for efficient query plans

### Connection Pool Tuning

```yaml
- NEO4J_server_bolt_thread__pool__min__size=5
- NEO4J_server_bolt_thread__pool__max__size=400
- NEO4J_server_bolt_connection__keep__alive=true
```

**Benefits**:
- Maintains minimum connections for immediate availability
- Allows scaling up to handle concurrent development requests
- Keeps connections alive to reduce connection overhead

## Transaction Optimization

### Transaction Log Configuration

```yaml
- NEO4J_db_tx__log_rotation_retention__policy=1G size
- NEO4J_db_tx__log_rotation_size=100M
```

**Benefits**:
- Limits transaction log size for development
- Prevents excessive disk usage
- Maintains sufficient history for recovery

### Checkpoint Optimization

```properties
db.checkpoint.interval.time=5m
db.checkpoint.interval.tx=10000
```

**Benefits**:
- More frequent checkpoints reduce recovery time
- Balances performance with data safety
- Optimized for development workload patterns

## Development-Specific Optimizations

### Disabled Features for Performance

```yaml
- NEO4J_dbms_usage__report_enabled=false
- NEO4J_dbms_logs_query_enabled=false
- NEO4J_metrics_csv_enabled=false
- NEO4J_metrics_graphite_enabled=false
```

**Benefits**:
- Reduces CPU overhead from telemetry collection
- Eliminates network calls for usage reporting
- Focuses resources on core database operations

### Timeout Configuration

```yaml
- NEO4J_dbms_transaction_timeout=60s
- NEO4J_dbms_lock_acquisition_timeout=60s
```

**Benefits**:
- Prevents long-running queries from blocking development
- Provides reasonable timeout for complex operations
- Allows debugging of performance issues

## Plugin Optimization

### APOC Configuration

```yaml
- NEO4J_apoc_export_file_enabled=true
- NEO4J_apoc_import_file_enabled=true
- NEO4J_dbms_security_allow__csv__import__from__file__urls=true
```

**Benefits**:
- Enables data import/export for development
- Allows CSV processing for test data
- Provides utility functions for development workflows

### GDS (Graph Data Science) Configuration

```yaml
- NEO4J_PLUGINS=["graph-data-science", "apoc"]
- NEO4J_dbms_security_procedures_unrestricted=gds.*,apoc.*
```

**Benefits**:
- Provides graph algorithms for development
- Enables advanced analytics capabilities
- Maintains compatibility with production features

## Performance Monitoring

### JMX Metrics

```properties
metrics.enabled=true
metrics.jmx.enabled=true
metrics.csv.enabled=false
```

**Benefits**:
- Enables performance monitoring via JMX
- Provides memory and query metrics
- Lightweight monitoring suitable for development

### Health Checks

```yaml
healthcheck:
  test: ["CMD-SHELL", "cypher-shell -u neo4j -p ml_password 'RETURN 1 as status' && cypher-shell -u neo4j -p ml_password 'CALL apoc.version() YIELD version RETURN version LIMIT 1' && cypher-shell -u neo4j -p ml_password 'CALL gds.version() YIELD version RETURN version LIMIT 1'"]
  interval: 30s
  timeout: 20s
  retries: 5
  start_period: 90s
```

**Benefits**:
- Validates database connectivity
- Confirms plugin availability
- Provides startup time monitoring

## Performance Validation

### Automated Testing

The performance optimizations are validated through automated tests:

```bash
# Run Neo4j performance tests
pytest tests/performance/test_neo4j_performance_optimization.py -v

# Monitor performance in real-time
python scripts/monitor-neo4j-performance.py
```

### Performance Targets

| Metric | Target | Validation |
|--------|--------|------------|
| Memory Usage | < 1.5GB | Container stats monitoring |
| Node Creation | < 100ms | Performance tests |
| Simple Queries | < 50ms | Performance tests |
| Complex Queries | < 200ms | End-to-end tests |
| Page Cache Hit Ratio | > 80% | JMX metrics |
| Startup Time | < 90s | Health check timing |

## Troubleshooting

### High Memory Usage

If Neo4j exceeds memory limits:

1. Check heap usage: `docker exec neo4j cypher-shell -u neo4j -p ml_password "CALL dbms.queryJmx('java.lang:type=Memory') YIELD attributes RETURN attributes"`
2. Reduce heap size if necessary
3. Clear query cache: `CALL db.clearQueryCaches()`
4. Check for memory leaks in custom procedures

### Poor Query Performance

If queries are slow:

1. Check query plans: `EXPLAIN MATCH (n) RETURN n`
2. Create indexes: `CREATE INDEX FOR (n:Label) ON (n.property)`
3. Monitor page cache hit ratio
4. Consider query optimization

### Startup Issues

If Neo4j fails to start:

1. Check container logs: `docker logs local-development-conversion-neo4j-1`
2. Verify memory limits are not too restrictive
3. Check plugin compatibility
4. Validate configuration syntax

## Configuration Files

### Docker Compose Configuration

The main configuration is in `docker-compose.local.yml` under the `neo4j` service.

### Neo4j Configuration File

Additional settings are in `database/neo4j/neo4j.conf`, which is mounted into the container.

### Environment Variables

Development-specific settings can be overridden in `.env.local`:

```bash
# Neo4j configuration
NEO4J_HOST=neo4j
NEO4J_PORT=7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=ml_password
```

## Best Practices

### Development Workflow

1. **Start with clean data**: Use `MATCH (n) DETACH DELETE n` to clear test data
2. **Monitor memory usage**: Run performance monitoring regularly
3. **Use transactions**: Batch operations for better performance
4. **Create indexes**: Add indexes for frequently queried properties
5. **Profile queries**: Use `PROFILE` to understand query performance

### Data Management

1. **Limit test data size**: Keep development datasets small (< 100K nodes)
2. **Use realistic data**: Test with data similar to production
3. **Clean up regularly**: Remove test data to prevent memory bloat
4. **Backup important data**: Use Neo4j backup tools for valuable datasets

### Performance Testing

1. **Test regularly**: Run performance tests with each change
2. **Monitor trends**: Track performance over time
3. **Test concurrency**: Validate performance under load
4. **Profile bottlenecks**: Identify and optimize slow queries

## Integration with Application

### Database Client Configuration

The application uses the optimized Neo4j instance through the database factory:

```python
# src/multimodal_librarian/clients/neo4j_client.py
class Neo4jClient:
    def __init__(self, uri: str, user: str, password: str):
        self.driver = GraphDatabase.driver(
            uri, 
            auth=(user, password),
            # Connection pool optimization
            max_connection_lifetime=30 * 60,  # 30 minutes
            max_connection_pool_size=50,
            connection_acquisition_timeout=60,
        )
```

### Health Check Integration

The application includes Neo4j health checks:

```python
# Health check endpoint validates Neo4j performance
@router.get("/health/databases")
async def check_database_health():
    # Validates connection, memory usage, and query performance
    pass
```

## Conclusion

These optimizations provide a balanced configuration for Neo4j in local development:

- **Memory efficient**: Uses ~1.5GB total memory
- **Performance optimized**: Provides good query performance for development
- **Development friendly**: Includes debugging and monitoring capabilities
- **Production compatible**: Maintains compatibility with production features

The configuration can be further tuned based on specific development needs and hardware constraints.