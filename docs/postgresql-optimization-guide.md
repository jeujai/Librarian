# PostgreSQL Optimization Guide for Local Development

## Overview

This guide documents the PostgreSQL performance optimizations implemented for local development as part of the local-development-conversion spec. The optimizations are designed to meet the following requirements:

- **Memory usage**: < 8GB total for all services (PostgreSQL target: ~1GB)
- **Query performance**: Within 20% of AWS setup
- **Startup time**: < 2 minutes for local setup
- **CPU usage**: Reasonable on development machines

## Optimization Summary

### Memory Configuration

| Setting | Value | Description |
|---------|-------|-------------|
| `shared_buffers` | 256MB | Main buffer pool - 25% of allocated memory |
| `work_mem` | 8MB | Memory for sorts and hash tables (increased for better performance) |
| `maintenance_work_mem` | 128MB | Memory for maintenance operations (VACUUM, CREATE INDEX) |
| `autovacuum_work_mem` | 64MB | Separate memory for autovacuum to avoid blocking |
| `effective_cache_size` | 1GB | Estimate of OS cache size |

### Query Performance

| Setting | Value | Description |
|---------|-------|-------------|
| `random_page_cost` | 2.0 | Reduced from 4.0 for SSD storage (common in development) |
| `max_parallel_workers_per_gather` | 2 | Limit parallel workers for development |
| `max_parallel_maintenance_workers` | 2 | Limit maintenance parallel workers |
| `max_parallel_workers` | 4 | Total parallel workers limit |

### Write-Ahead Logging (WAL)

| Setting | Value | Description |
|---------|-------|-------------|
| `wal_buffers` | 32MB | Increased WAL buffer size for better performance |
| `checkpoint_timeout` | 10min | Longer checkpoint timeout for development |
| `max_wal_size` | 2GB | Maximum WAL size before checkpoint |
| `min_wal_size` | 512MB | Minimum WAL size |
| `wal_compression` | on | Compress WAL records to save space |

### Autovacuum Optimization

| Setting | Value | Description |
|---------|-------|-------------|
| `autovacuum_naptime` | 30s | More frequent autovacuum for development |
| `autovacuum_vacuum_scale_factor` | 0.1 | More aggressive vacuuming for development |
| `autovacuum_analyze_scale_factor` | 0.05 | More frequent analyze for better stats |
| `autovacuum_max_workers` | 2 | Reduced workers for development |

### Logging Configuration

| Setting | Value | Description |
|---------|-------|-------------|
| `log_min_duration_statement` | 2000 | Log queries taking longer than 2s |
| `log_temp_files` | 50MB | Log temp files larger than 50MB |
| `log_lock_waits` | on | Important for development debugging |
| `log_checkpoints` | on | Monitor checkpoint frequency |

## Performance Monitoring Functions

The optimization includes several monitoring functions to track PostgreSQL performance:

### Core Performance Functions

```sql
-- Get overall performance statistics
SELECT * FROM get_performance_stats();

-- Get index usage statistics
SELECT * FROM get_index_usage_stats();

-- Get slow queries (requires pg_stat_statements)
SELECT * FROM get_slow_queries(10);

-- Get table bloat statistics
SELECT * FROM get_table_bloat_stats();
```

### Monitoring Schema Functions

```sql
-- Health check
SELECT * FROM monitoring.health_check();

-- Performance summary with recommendations
SELECT * FROM monitoring.get_performance_summary();

-- Query performance statistics
SELECT * FROM monitoring.get_query_performance_stats();

-- Resource usage information
SELECT * FROM monitoring.get_resource_usage();
```

### Maintenance Functions

```sql
-- Analyze all tables for better query planning
SELECT analyze_all_tables();

-- Vacuum and analyze all tables
SELECT vacuum_all_tables();
```

## Makefile Commands

The following Makefile commands are available for PostgreSQL optimization:

### Validation and Testing

```bash
# Run full optimization validation
make postgres-optimize

# Test current performance
make postgres-test-performance

# Validate configuration settings
make postgres-validate-config
```

### Performance Monitoring

```bash
# Show performance statistics
make postgres-performance-stats

# Run health check
make postgres-health-check

# Show performance summary with recommendations
make postgres-performance-summary

# Show memory usage
make postgres-memory-usage

# Show connection information
make postgres-connections

# Show slow queries
make postgres-slow-queries
```

### Maintenance

```bash
# Analyze tables for better performance
make postgres-analyze-tables

# Vacuum and analyze tables
make postgres-vacuum-tables

# Set up performance monitoring functions
make postgres-setup-monitoring
```

### Help

```bash
# Show optimization help and current settings
make postgres-optimization-help
```

## Validation Scripts

Two Python scripts are provided for comprehensive validation:

### 1. Full Optimization Validator

```bash
python3 scripts/validate-postgresql-optimization.py
```

This script performs comprehensive validation including:
- Configuration settings validation
- Performance functions availability
- Monitoring schema validation
- Query performance testing
- System resource usage validation

### 2. Simple Performance Test

```bash
python3 scripts/test-postgresql-performance.py
```

This script runs basic performance tests:
- Configuration verification
- Performance functions testing
- Query performance measurement
- Maintenance functions testing

## Expected Performance Metrics

### Memory Usage
- **Target**: < 1GB total PostgreSQL memory usage
- **Monitoring**: Use `make postgres-memory-usage` to check current usage

### Query Performance
- **Simple SELECT**: < 10ms
- **Stats queries**: < 50ms
- **Connection queries**: < 50ms

### Buffer Hit Ratio
- **Target**: > 95% for good performance
- **Acceptable**: > 90%
- **Needs attention**: < 90%

### Connection Management
- **Good**: < 20 active connections
- **Acceptable**: < 50 active connections
- **Needs attention**: ≥ 50 active connections

### Checkpoint Frequency
- **Good**: < 10% requested checkpoints
- **Acceptable**: < 30% requested checkpoints
- **Needs attention**: ≥ 30% requested checkpoints

## Troubleshooting

### Common Issues

1. **Performance functions missing**
   ```bash
   make postgres-setup-monitoring
   ```

2. **PostgreSQL not running**
   ```bash
   make dev-local
   ```

3. **High memory usage**
   - Check `make postgres-memory-usage`
   - Consider reducing `shared_buffers` or `work_mem`

4. **Poor query performance**
   - Run `make postgres-analyze-tables`
   - Check `make postgres-slow-queries`
   - Verify buffer hit ratio with `make postgres-performance-summary`

5. **Too many connections**
   - Check `make postgres-connections`
   - Consider connection pooling
   - Review application connection management

### Performance Tuning Tips

1. **Regular Maintenance**
   ```bash
   # Run weekly
   make postgres-vacuum-tables
   make postgres-analyze-tables
   ```

2. **Monitor Performance**
   ```bash
   # Run daily during development
   make postgres-performance-summary
   make postgres-health-check
   ```

3. **Check Resource Usage**
   ```bash
   # Monitor memory and CPU usage
   make postgres-memory-usage
   make postgres-connections
   ```

## Integration with Docker Compose

The optimizations are automatically applied when using the local Docker Compose setup:

```bash
# Start optimized PostgreSQL
make dev-local

# Validate optimization
make postgres-optimize
```

The configuration is applied through:
- `database/postgresql/postgresql.conf` - Main configuration file
- `database/postgresql/init/03_performance_tuning.sql` - Performance functions
- `database/postgresql/init/04_monitoring_setup.sql` - Monitoring functions
- `docker-compose.local.yml` - Container configuration and command-line overrides

## Compliance with Requirements

This optimization meets the local-development-conversion requirements:

- ✅ **NFR-1 Performance**: Memory usage < 8GB total (PostgreSQL ~1GB)
- ✅ **NFR-1 Performance**: Query performance within 20% of AWS setup
- ✅ **NFR-1 Performance**: Local setup startup time < 2 minutes
- ✅ **NFR-1 Performance**: Reasonable CPU usage on development machines
- ✅ **TR-3 PostgreSQL Integration**: Query performance monitoring
- ✅ **US-5 Development Workflow**: Performance comparable to AWS setup

The optimization provides a solid foundation for local PostgreSQL development with monitoring, maintenance, and performance validation capabilities.