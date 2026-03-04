# Performance Debugging Guide for Local Development

This guide covers the comprehensive performance debugging tools available for the local development environment, including monitoring, profiling, and optimization techniques.

## Overview

The performance debugging tools provide real-time monitoring, detailed profiling, and bottleneck identification for the local Docker-based development environment. These tools help developers optimize application performance and identify issues before they reach production.

## Available Tools

### 1. Performance Debugger (`PerformanceDebugger`)

The core performance debugging class that provides:
- Real-time system resource monitoring
- Database query performance analysis
- Docker container resource tracking
- Bottleneck identification
- Performance recommendations

### 2. Performance Debug API (`/debug/performance/*`)

REST API endpoints for performance monitoring:
- Start/stop monitoring
- Get performance summaries
- View metrics and query data
- Export performance data

### 3. Performance Debug CLI (`scripts/performance-debug-cli.py`)

Command-line interface for performance debugging:
- Interactive monitoring control
- Performance summaries and reports
- Data export and analysis
- Built-in benchmarking

### 4. Performance Profiler (`scripts/performance-profiler.py`)

Advanced profiling tool for detailed analysis:
- CPU profiling with cProfile
- Memory profiling with tracemalloc
- Database operation profiling
- Comprehensive profiling reports

## Quick Start

### Starting Performance Monitoring

```bash
# Start monitoring with 5-second intervals
python scripts/performance-debug-cli.py start --interval 5

# Check monitoring status
python scripts/performance-debug-cli.py status

# Get performance summary for last 10 minutes
python scripts/performance-debug-cli.py summary --minutes 10
```

### Using the API

```python
import requests

# Start monitoring
response = requests.post("http://localhost:8000/debug/performance/monitoring/start?interval_seconds=5")
print(response.json())

# Get performance summary
response = requests.get("http://localhost:8000/debug/performance/summary?last_minutes=10")
summary = response.json()
print(f"Bottlenecks found: {len(summary['bottlenecks'])}")
```

### Programmatic Usage

```python
from multimodal_librarian.development.performance_debugger import get_performance_debugger
from multimodal_librarian.config.local_config import LocalDatabaseConfig

# Get debugger instance
config = LocalDatabaseConfig()
debugger = get_performance_debugger(config)

# Start monitoring
await debugger.start_monitoring(interval_seconds=5)

# Measure specific operations
async with debugger.measure_operation("my_operation", {"context": "test"}):
    # Your code here
    await some_database_operation()

# Get performance summary
summary = debugger.get_performance_summary(last_minutes=10)
print(f"Database performance: {summary['database_performance']}")

# Stop monitoring
await debugger.stop_monitoring()
```

## Detailed Usage

### 1. Real-time Monitoring

Start continuous monitoring to collect performance metrics:

```bash
# Start monitoring with custom interval
python scripts/performance-debug-cli.py start --interval 3

# Monitor for a specific duration then stop
python scripts/performance-debug-cli.py start --interval 5
sleep 60
python scripts/performance-debug-cli.py stop
```

The monitoring system collects:
- System CPU and memory usage
- Docker container resource usage
- Database query performance
- Network and disk I/O metrics

### 2. Performance Analysis

#### View Performance Summary

```bash
# Get summary for last 15 minutes
python scripts/performance-debug-cli.py summary --minutes 15
```

The summary includes:
- Database performance statistics (avg, min, max query times)
- System resource usage (CPU, memory, disk, network)
- Docker container performance
- Identified bottlenecks
- Optimization recommendations

#### View Detailed Metrics

```bash
# Show all metrics
python scripts/performance-debug-cli.py metrics

# Filter metrics by name
python scripts/performance-debug-cli.py metrics --filter postgres

# Limit number of results
python scripts/performance-debug-cli.py metrics --limit 20
```

#### View Query Performance

```bash
# Show all database queries
python scripts/performance-debug-cli.py queries

# Filter by database type
python scripts/performance-debug-cli.py queries --database postgresql

# Show recent queries only
python scripts/performance-debug-cli.py queries --limit 10
```

#### View Resource Usage

```bash
# Show system resource snapshots
python scripts/performance-debug-cli.py resources

# Show recent snapshots only
python scripts/performance-debug-cli.py resources --limit 5
```

### 3. Advanced Profiling

Use the performance profiler for detailed analysis:

```bash
# Run comprehensive profiling
python scripts/performance-profiler.py
```

The profiler provides:
- CPU profiling with function-level analysis
- Memory profiling with allocation tracking
- Database operation profiling
- Combined comprehensive analysis

#### Custom Profiling

```python
from scripts.performance_profiler import PerformanceProfiler

profiler = PerformanceProfiler()

# CPU profiling
with profiler.cpu_profile("my_cpu_operation"):
    # CPU-intensive code
    result = complex_calculation()

# Memory profiling
with profiler.memory_profile("my_memory_operation"):
    # Memory-intensive code
    large_data = create_large_dataset()

# Database profiling
async with profiler.database_profile("my_db_operation"):
    # Database operations
    await database_queries()

# Comprehensive profiling
async with profiler.comprehensive_profile("my_full_operation"):
    # All types of operations
    await full_application_workflow()

# View results
profiler.print_profile_summary()
profiler.export_profiles("/tmp/my_profile.json")
```

### 4. Benchmarking

Run built-in benchmarks to test system performance:

```bash
# Run performance benchmark
python scripts/performance-debug-cli.py benchmark
```

The benchmark tests:
- Database connection and query performance
- System resource utilization
- Container performance
- Overall system responsiveness

### 5. Data Export and Analysis

Export performance data for external analysis:

```bash
# Export all data to JSON
python scripts/performance-debug-cli.py export --filepath /tmp/perf-data.json

# Export with custom format (future: CSV, XML)
python scripts/performance-debug-cli.py export --filepath /tmp/perf-data.json --format json
```

The exported data includes:
- All collected metrics
- Query performance data
- Resource usage snapshots
- Performance summary

## Performance Optimization Tips

### Database Performance

1. **Monitor Query Times**: Watch for queries taking >100ms
2. **Check Connection Pooling**: Ensure efficient connection reuse
3. **Analyze Slow Queries**: Use query profiling to identify bottlenecks
4. **Database Configuration**: Optimize database settings for development

```bash
# Monitor database-specific performance
python scripts/performance-debug-cli.py queries --database postgresql
python scripts/performance-debug-cli.py queries --database neo4j
python scripts/performance-debug-cli.py queries --database milvus
```

### System Resource Optimization

1. **CPU Usage**: Monitor for sustained high CPU usage
2. **Memory Usage**: Watch for memory leaks and high usage
3. **Docker Containers**: Optimize container resource limits
4. **Disk I/O**: Monitor for excessive disk operations

```bash
# Monitor system resources
python scripts/performance-debug-cli.py resources --limit 20
```

### Container Performance

1. **Resource Limits**: Set appropriate CPU and memory limits
2. **Health Checks**: Optimize health check frequency
3. **Startup Time**: Monitor container startup performance
4. **Network Usage**: Watch for excessive network traffic

## Troubleshooting Common Issues

### High CPU Usage

```bash
# Check CPU usage patterns
python scripts/performance-debug-cli.py summary --minutes 5

# Look for CPU-intensive operations
python scripts/performance-debug-cli.py metrics --filter cpu
```

**Solutions**:
- Reduce Docker container CPU limits
- Optimize CPU-intensive algorithms
- Use async operations where possible
- Consider caching for repeated calculations

### High Memory Usage

```bash
# Check memory usage trends
python scripts/performance-debug-cli.py resources --limit 10

# Look for memory-intensive operations
python scripts/performance-debug-cli.py metrics --filter memory
```

**Solutions**:
- Increase available memory
- Optimize memory usage in containers
- Implement proper garbage collection
- Use memory-efficient data structures

### Slow Database Queries

```bash
# Identify slow queries
python scripts/performance-debug-cli.py queries --limit 50

# Check database-specific performance
python scripts/performance-debug-cli.py summary --minutes 10
```

**Solutions**:
- Add database indexes
- Optimize query structure
- Use connection pooling
- Consider query caching

### Container Issues

```bash
# Check container performance
python scripts/performance-debug-cli.py resources

# Monitor container-specific metrics
python scripts/performance-debug-cli.py summary
```

**Solutions**:
- Adjust container resource limits
- Optimize Docker image size
- Use multi-stage builds
- Implement proper health checks

## Integration with Development Workflow

### Continuous Monitoring

Add performance monitoring to your development workflow:

```bash
# Add to your development startup script
echo "python scripts/performance-debug-cli.py start --interval 10" >> scripts/dev-startup.sh

# Add to your development shutdown script
echo "python scripts/performance-debug-cli.py stop" >> scripts/dev-shutdown.sh
```

### Automated Performance Testing

Create automated performance tests:

```python
# tests/performance/test_local_performance.py
import pytest
from multimodal_librarian.development.performance_debugger import get_performance_debugger

@pytest.mark.asyncio
async def test_database_performance():
    debugger = get_performance_debugger()
    
    async with debugger.measure_operation("test_db_performance"):
        # Your database operations
        await database_operations()
    
    # Check performance metrics
    summary = debugger.get_performance_summary(1)
    assert len(summary['bottlenecks']) == 0, "Performance bottlenecks detected"
```

### Performance Alerts

Set up performance alerts in your development environment:

```python
# Monitor for performance issues
async def check_performance_alerts():
    debugger = get_performance_debugger()
    summary = debugger.get_performance_summary(5)
    
    for bottleneck in summary['bottlenecks']:
        if bottleneck['severity'] == 'high':
            print(f"⚠️ Performance Alert: {bottleneck['description']}")
```

## API Reference

### Performance Debugger Class

```python
class PerformanceDebugger:
    async def start_monitoring(interval_seconds: int) -> Dict[str, Any]
    async def stop_monitoring() -> Dict[str, Any]
    async def measure_operation(name: str, context: Dict = None)
    def get_performance_summary(last_minutes: int) -> Dict[str, Any]
    def export_metrics(filepath: str, format: str) -> Dict[str, Any]
    def clear_data() -> Dict[str, Any]
```

### REST API Endpoints

- `POST /debug/performance/monitoring/start` - Start monitoring
- `POST /debug/performance/monitoring/stop` - Stop monitoring
- `GET /debug/performance/summary` - Get performance summary
- `GET /debug/performance/metrics` - Get collected metrics
- `GET /debug/performance/queries` - Get query performance data
- `GET /debug/performance/resources` - Get resource usage data
- `POST /debug/performance/export` - Export performance data
- `POST /debug/performance/clear` - Clear collected data

### CLI Commands

- `start` - Start performance monitoring
- `stop` - Stop performance monitoring
- `summary` - Show performance summary
- `metrics` - Show collected metrics
- `queries` - Show query performance data
- `resources` - Show resource usage data
- `export` - Export performance data
- `clear` - Clear all data
- `status` - Show monitoring status
- `benchmark` - Run performance benchmark

## Best Practices

1. **Regular Monitoring**: Keep monitoring active during development
2. **Baseline Measurements**: Establish performance baselines
3. **Incremental Testing**: Test performance after each change
4. **Resource Limits**: Set appropriate Docker resource limits
5. **Data Cleanup**: Regularly clear old performance data
6. **Export Analysis**: Export data for trend analysis
7. **Automated Alerts**: Set up automated performance alerts
8. **Documentation**: Document performance optimizations

## Conclusion

The performance debugging tools provide comprehensive monitoring and analysis capabilities for the local development environment. Use these tools regularly to maintain optimal performance and identify issues early in the development process.

For additional help or questions, refer to the tool documentation or run commands with `--help` flag.