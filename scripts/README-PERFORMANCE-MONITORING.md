# Performance Monitoring Scripts

This directory contains comprehensive performance monitoring scripts for the local development environment. These scripts help monitor system resources, database performance, and overall application health.

## Overview

The performance monitoring system provides:

- **Real-time monitoring** of system and container resources
- **Database performance tracking** for PostgreSQL, Neo4j, and Milvus
- **Interactive dashboard** with live metrics and charts
- **Automated alerting** for performance issues
- **Comprehensive reporting** with recommendations
- **Bottleneck detection** and analysis

## Scripts

### Core Monitoring Scripts

#### `monitor-local-development.py`
**Main orchestrator script** that coordinates all monitoring activities.

```bash
# Start comprehensive monitoring (60 minutes)
python scripts/monitor-local-development.py start

# Quick health check
python scripts/monitor-local-development.py check

# Launch interactive dashboard
python scripts/monitor-local-development.py dashboard

# Run performance benchmarks
python scripts/monitor-local-development.py benchmark

# Generate summary report
python scripts/monitor-local-development.py report
```

**Options:**
- `--config FILE`: Configuration file (default: monitoring_config.json)
- `--interval SECONDS`: Monitoring interval (default: 30)
- `--duration MINUTES`: Monitoring duration (default: 60)
- `--services SERVICE`: Services to monitor (comma-separated)
- `--alerts`: Enable alert notifications
- `--verbose`: Enable verbose logging

#### `monitor-local-performance.py`
**System-wide performance monitoring** including containers and services.

```bash
# Monitor all services for 1 hour
python scripts/monitor-local-performance.py --duration 60 --interval 30

# Monitor specific services
python scripts/monitor-local-performance.py --services postgres,neo4j --duration 30

# Quick monitoring with verbose output
python scripts/monitor-local-performance.py --duration 10 --interval 5 --verbose
```

**Features:**
- System CPU, memory, disk, and network monitoring
- Docker container resource usage
- Service-specific metrics (PostgreSQL connections, Neo4j memory, etc.)
- Performance bottleneck detection
- Automated recommendations

#### `monitor-database-performance.py`
**Database-specific performance monitoring** with detailed metrics.

```bash
# Monitor all databases
python scripts/monitor-database-performance.py --database all --duration 30

# Monitor PostgreSQL only
python scripts/monitor-database-performance.py --database postgres --interval 5

# Monitor with custom thresholds
python scripts/monitor-database-performance.py --threshold-cpu 70 --threshold-memory 800
```

**Database Metrics:**
- **PostgreSQL**: Query performance, connection pools, cache hit ratios, slow queries
- **Neo4j**: Cypher queries, memory usage, transaction stats, heap utilization
- **Milvus**: Vector operations, collection stats, index performance

#### `monitor-resource-usage.py`
**System and container resource monitoring** with real-time alerts.

```bash
# Monitor resources for 15 minutes
python scripts/monitor-resource-usage.py --duration 15 --interval 5

# Monitor with custom alert thresholds
python scripts/monitor-resource-usage.py --alert-cpu 80 --alert-memory 85 --alert-disk 90

# Monitor system only (no containers)
python scripts/monitor-resource-usage.py --no-containers --duration 10
```

**Resource Metrics:**
- System CPU, memory, disk usage
- Container resource consumption
- Network I/O statistics
- Load averages and process counts
- Bottleneck detection

#### `performance-dashboard.py`
**Interactive real-time dashboard** with ASCII charts and live metrics.

```bash
# Launch dashboard with default settings
python scripts/performance-dashboard.py

# Compact dashboard with faster refresh
python scripts/performance-dashboard.py --refresh 1 --compact

# Dashboard without charts
python scripts/performance-dashboard.py --no-charts --services postgres,neo4j
```

**Dashboard Features:**
- Real-time system and container metrics
- ASCII charts for CPU and memory usage
- Database connection and performance stats
- Color-coded alerts and warnings
- Service status indicators

## Makefile Integration

The monitoring scripts are integrated into the Makefile for easy access:

### Quick Commands

```bash
# Start comprehensive monitoring
make monitor-performance

# Quick 5-minute check
make monitor-performance-quick

# Extended 2-hour monitoring
make monitor-performance-extended

# Launch interactive dashboard
make monitor-dashboard

# Run health check
make monitor-health-check
```

### Database Monitoring

```bash
# Monitor all databases
make monitor-database

# Monitor specific databases
make monitor-database-postgres
make monitor-database-neo4j
make monitor-database-milvus
```

### Resource Monitoring

```bash
# Monitor system resources
make monitor-resources

# Detailed resource monitoring with alerts
make monitor-resources-detailed

# Overall system performance
make monitor-system
```

### Reporting and Maintenance

```bash
# Generate performance report
make monitor-report

# Check for alerts
make monitor-alerts

# View monitoring configuration
make monitor-config

# Clean up monitoring files
make monitor-clean

# Show monitoring system status
make monitor-status
```

## Configuration

### Configuration File (`monitoring_config.json`)

```json
{
  "interval": 30,
  "duration": 60,
  "services": ["postgres", "neo4j", "milvus", "etcd", "minio"],
  "alerts_enabled": true,
  "output_dir": "monitoring_reports",
  "thresholds": {
    "cpu_warning": 70.0,
    "cpu_critical": 85.0,
    "memory_warning": 80.0,
    "memory_critical": 90.0,
    "disk_warning": 85.0,
    "disk_critical": 95.0
  }
}
```

### Environment Variables

The monitoring scripts respect these environment variables:

- `ML_ENVIRONMENT`: Set to "local" for local development monitoring
- `ML_DATABASE_TYPE`: Database type (local/aws)
- `ML_POSTGRES_HOST`: PostgreSQL host (default: localhost)
- `ML_NEO4J_HOST`: Neo4j host (default: localhost)
- `ML_MILVUS_HOST`: Milvus host (default: localhost)

## Output and Reports

### Report Structure

Monitoring generates several types of reports:

1. **Performance Reports** (`performance_YYYYMMDD_HHMMSS.json`)
   - System and container metrics
   - Service performance statistics
   - Resource usage trends

2. **Database Reports** (`database_YYYYMMDD_HHMMSS.json`)
   - Query performance metrics
   - Connection statistics
   - Database-specific health data

3. **Resource Reports** (`resources_YYYYMMDD_HHMMSS.json`)
   - System resource usage
   - Container resource consumption
   - Bottleneck analysis

4. **Summary Reports** (`summary_YYYYMMDD_HHMMSS.json`)
   - Consolidated metrics from all monitoring
   - Performance recommendations
   - Alert summaries

### Report Location

All reports are saved to the `monitoring_reports/` directory by default. This can be configured in the monitoring configuration file.

## Alerts and Thresholds

### Alert Types

- **CPU Alerts**: Triggered when CPU usage exceeds thresholds
- **Memory Alerts**: Triggered when memory usage is high
- **Disk Alerts**: Triggered when disk space is low
- **Database Alerts**: Connection issues, slow queries, high resource usage
- **Service Alerts**: Container failures, service unavailability

### Threshold Configuration

Thresholds can be configured globally in `monitoring_config.json` or per-script:

```bash
# Custom CPU threshold
python scripts/monitor-resource-usage.py --alert-cpu 75

# Custom memory threshold for databases
python scripts/monitor-database-performance.py --threshold-memory 1200
```

## Troubleshooting

### Common Issues

1. **Docker Not Available**
   ```
   Error: Docker not available
   Solution: Ensure Docker is running and accessible
   ```

2. **Database Connection Errors**
   ```
   Error: Database connection failed
   Solution: Ensure local services are running (make dev-local)
   ```

3. **Permission Errors**
   ```
   Error: Permission denied
   Solution: Make scripts executable (chmod +x scripts/monitor-*.py)
   ```

4. **Missing Dependencies**
   ```
   Error: Module not found
   Solution: Install required packages (pip install docker psutil asyncpg neo4j pymilvus)
   ```

### Debug Mode

Enable verbose logging for troubleshooting:

```bash
python scripts/monitor-local-development.py start --verbose
```

### Log Files

Monitoring logs are written to:
- `performance_dashboard.log`: Dashboard and monitoring logs
- `monitoring_reports/`: All generated reports

## Performance Optimization

### Monitoring Overhead

The monitoring scripts are designed to have minimal impact:

- **CPU Usage**: < 2% additional CPU usage
- **Memory Usage**: < 50MB additional memory
- **Disk I/O**: Minimal, only during report generation
- **Network**: No additional network traffic

### Optimization Tips

1. **Adjust Intervals**: Increase monitoring intervals for lower overhead
2. **Selective Monitoring**: Monitor only necessary services
3. **Batch Reporting**: Generate reports less frequently
4. **Resource Limits**: Set appropriate alert thresholds

## Integration with CI/CD

The monitoring scripts can be integrated into CI/CD pipelines:

```bash
# Pre-deployment health check
make monitor-health-check

# Performance regression testing
make monitor-benchmark

# Post-deployment monitoring
make monitor-performance-quick
```

## Best Practices

1. **Regular Monitoring**: Run performance checks regularly during development
2. **Baseline Establishment**: Create performance baselines for comparison
3. **Alert Tuning**: Adjust alert thresholds based on your environment
4. **Report Analysis**: Review monitoring reports for optimization opportunities
5. **Proactive Monitoring**: Use continuous monitoring during intensive development

## Support

For issues or questions about performance monitoring:

1. Check the troubleshooting section above
2. Review the monitoring logs
3. Ensure all dependencies are installed
4. Verify local services are running properly

## Future Enhancements

Planned improvements to the monitoring system:

- Web-based dashboard interface
- Historical performance trending
- Machine learning-based anomaly detection
- Integration with external monitoring systems
- Custom metric collection and alerting
- Performance regression detection