# Local Development Memory Monitoring

This document describes the memory monitoring functionality added to the Multimodal Librarian for local development environments.

## Overview

The memory monitoring system provides comprehensive tracking of memory usage for both the system and Docker containers during local development. It helps developers:

- Monitor system and container memory usage in real-time
- Detect potential memory leaks
- Get optimization recommendations
- Track memory usage trends over time
- Receive alerts when memory usage exceeds thresholds

## Components

### 1. Memory Monitoring Script

**Location**: `scripts/monitor-memory-usage.py`

A standalone script for monitoring memory usage with the following features:

- System memory monitoring (RAM, swap, cache, buffers)
- Docker container memory monitoring
- Memory leak detection
- Configurable alerts and thresholds
- Detailed reporting with optimization recommendations

**Usage**:
```bash
# Basic monitoring (30 minutes)
python scripts/monitor-memory-usage.py

# Quick check (10 minutes)
python scripts/monitor-memory-usage.py --duration 10 --interval 5

# Extended monitoring with leak detection
python scripts/monitor-memory-usage.py --duration 120 --interval 30 --leak-detection

# Monitor only system (no containers)
python scripts/monitor-memory-usage.py --no-containers

# Custom output file
python scripts/monitor-memory-usage.py --output my-memory-report.json
```

**Options**:
- `--interval SECONDS`: Monitoring interval (default: 10)
- `--duration MINUTES`: Total monitoring duration (default: 30)
- `--output FILE`: Output file for detailed report
- `--alert-threshold PCT`: Memory alert threshold (default: 85)
- `--no-containers`: Skip container monitoring
- `--no-leak-detection`: Disable memory leak detection
- `--verbose`: Enable verbose logging

### 2. Application Memory Monitor

**Location**: `src/multimodal_librarian/monitoring/local_memory_monitor.py`

Integrated memory monitoring that runs within the application:

- Automatic startup in local development environments
- Background monitoring with configurable intervals
- Integration with application health checks
- Memory metrics collection and history tracking
- Container-specific monitoring for local services

### 3. API Endpoints

**Location**: `src/multimodal_librarian/api/routers/local_memory_monitoring.py`

REST API endpoints for memory monitoring:

- `GET /api/v1/memory/status` - Current memory status
- `POST /api/v1/memory/monitoring/start` - Start monitoring
- `POST /api/v1/memory/monitoring/stop` - Stop monitoring
- `GET /api/v1/memory/metrics/current` - Current metrics
- `GET /api/v1/memory/history` - Memory usage history
- `GET /api/v1/memory/analysis/trends` - Trend analysis
- `GET /api/v1/memory/containers` - Container memory info
- `GET /api/v1/memory/recommendations` - Optimization recommendations
- `GET /api/v1/memory/alerts` - Current memory alerts
- `GET /api/v1/memory/health` - Monitoring system health

### 4. Makefile Targets

**Location**: `Makefile`

Convenient targets for memory monitoring:

```bash
# Standard memory monitoring (30 minutes)
make monitor-memory

# Quick memory check (10 minutes)
make monitor-memory-quick

# Extended monitoring (2 hours)
make monitor-memory-extended

# Container-only monitoring
make monitor-memory-containers
```

## Configuration

### Environment Variables

The memory monitoring system respects the following environment variables:

- `ML_ENVIRONMENT`: Set to "local" to enable automatic memory monitoring
- `ML_DATABASE_TYPE`: Set to "local" for local development mode

### Docker Compose Integration

Memory monitoring automatically detects and monitors these local containers:

- `multimodal-librarian-multimodal-librarian-1` (main application)
- `multimodal-librarian-postgres-1` (PostgreSQL database)
- `multimodal-librarian-neo4j-1` (Neo4j graph database)
- `multimodal-librarian-milvus-1` (Milvus vector database)
- `multimodal-librarian-redis-1` (Redis cache)
- `multimodal-librarian-etcd-1` (etcd for Milvus)
- `multimodal-librarian-minio-1` (MinIO for Milvus)

### Service-Specific Thresholds

Different services have different memory alert thresholds:

- PostgreSQL: 80%
- Neo4j: 85%
- Milvus: 90%
- Redis: 75%
- Main application: 80%

## Features

### Memory Leak Detection

The system includes intelligent memory leak detection that:

- Tracks memory usage patterns over time
- Identifies sustained memory growth
- Categorizes leaks by severity (low, medium, high, critical)
- Provides detailed descriptions of detected issues

### Optimization Recommendations

Based on memory usage patterns, the system provides recommendations such as:

- Increasing system RAM when usage is consistently high
- Reducing container memory limits when over-provisioned
- Increasing container memory limits when under-provisioned
- Optimizing applications when memory pressure is detected

### Alerting System

The monitoring system generates alerts for:

- High system memory usage (>85% by default)
- High container memory usage (service-specific thresholds)
- Critical memory usage (>95%)
- Swap memory usage
- Low available memory
- Detected memory leaks

### Trend Analysis

The system analyzes memory usage trends to identify:

- Increasing memory usage patterns
- Decreasing memory usage patterns
- Stable memory usage
- Memory usage volatility

## Integration with Application

### Automatic Startup

In local development environments, memory monitoring starts automatically when the application starts. This is handled in the `_background_initialization` function in `main.py`.

### Health Check Integration

Memory monitoring status is included in application health checks, providing visibility into:

- Whether monitoring is active
- Current memory usage levels
- Any active memory alerts
- System health status

### Graceful Shutdown

Memory monitoring is properly shut down when the application stops, ensuring clean resource cleanup.

## Output and Reporting

### JSON Reports

Detailed memory usage reports are saved in JSON format containing:

- Monitoring session information
- Summary statistics by source (system/containers)
- Detailed memory snapshots over time
- Detected memory leaks
- All generated alerts
- Optimization recommendations
- Memory efficiency analysis

### Console Output

Real-time console output includes:

- Current memory usage for system and containers
- Memory alerts as they occur
- Memory leak detection results
- Final summary with recommendations

### Example Report Structure

```json
{
  "monitoring_session": {
    "start_time": "2026-01-24T19:41:03.316",
    "end_time": "2026-01-24T19:42:03.340",
    "duration_minutes": 1.0,
    "interval_seconds": 10,
    "total_samples": 12
  },
  "summary": {
    "system": {
      "avg_memory_mb": 10470.6,
      "peak_memory_mb": 10586.6,
      "avg_memory_percent": 75.4,
      "peak_memory_percent": 75.8
    }
  },
  "detected_leaks": [],
  "all_alerts": ["Swap memory in use: 91.0%"],
  "recommendations": [
    "Frequent swap usage detected - consider increasing RAM or optimizing applications"
  ]
}
```

## Testing

### Unit Tests

**Location**: `tests/monitoring/test_local_memory_monitor.py`

Comprehensive unit tests covering:

- Monitor initialization
- Memory metrics collection
- Alert generation
- Trend analysis
- Global function behavior
- Integration scenarios

**Run tests**:
```bash
pytest tests/monitoring/test_local_memory_monitor.py -v
```

### Integration Tests

The test suite includes integration tests that work with real system resources (when available):

- Real memory collection
- Docker container monitoring
- Short monitoring loops

## Troubleshooting

### Common Issues

1. **Docker not available**: Memory monitoring will work for system monitoring only
2. **Permission issues**: Ensure the user has access to Docker socket
3. **High resource usage**: Adjust monitoring intervals for less frequent checks
4. **Missing dependencies**: Install required packages (`psutil`, `docker`)

### Debug Mode

Enable verbose logging for troubleshooting:

```bash
python scripts/monitor-memory-usage.py --verbose
```

### Health Check

Check the health of the memory monitoring system:

```bash
curl http://localhost:8000/api/v1/memory/health
```

## Performance Impact

The memory monitoring system is designed to have minimal performance impact:

- Lightweight memory sampling (typically <1% CPU)
- Configurable intervals to balance accuracy vs. performance
- Efficient data structures with bounded memory usage
- Background processing that doesn't block application operations

## Future Enhancements

Potential improvements for the memory monitoring system:

- Integration with external monitoring systems (Prometheus, Grafana)
- Historical data persistence beyond application restarts
- Advanced memory leak detection algorithms
- Automated memory optimization suggestions
- Integration with container orchestration platforms
- Real-time memory usage dashboards
- Email/Slack notifications for critical alerts

## Related Documentation

- [Local Development Setup](local-development-setup.md)
- [Docker Compose Configuration](../docker-compose.local.yml)
- [Application Health Monitoring](../src/multimodal_librarian/monitoring/)
- [API Documentation](../src/multimodal_librarian/api/routers/local_memory_monitoring.py)