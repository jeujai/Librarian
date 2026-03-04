# Local Development Debugging Utilities

This directory contains comprehensive debugging tools for the local development environment. These tools help diagnose issues with Docker services, database connections, network connectivity, and application performance.

## Available Tools

### 1. Local Debug CLI (`local-debug-cli.py`)
**Main debugging command-line interface**

Provides a unified interface for common debugging tasks:

```bash
# Check overall system status
python scripts/debug/local-debug-cli.py status

# Check Docker services
python scripts/debug/local-debug-cli.py services

# Check database connections
python scripts/debug/local-debug-cli.py databases

# Check application health
python scripts/debug/local-debug-cli.py health

# Collect service logs
python scripts/debug/local-debug-cli.py logs --service postgres --lines 200

# Monitor system resources
python scripts/debug/local-debug-cli.py monitor --duration 120

# Diagnose network connectivity
python scripts/debug/local-debug-cli.py network

# Generate comprehensive debug report
python scripts/debug/local-debug-cli.py report

# Restart a service
python scripts/debug/local-debug-cli.py restart postgres

# Clean up Docker resources
python scripts/debug/local-debug-cli.py cleanup
```

### 2. Database Debug Tool (`database-debug-tool.py`)
**Specialized database diagnostics**

Provides detailed diagnostics for PostgreSQL, Neo4j, and Milvus:

```bash
# Run comprehensive database diagnostics
python scripts/debug/database-debug-tool.py diagnostics

# Test database performance over time
python scripts/debug/database-debug-tool.py performance --duration 60

# Test specific databases
python scripts/debug/database-debug-tool.py postgresql
python scripts/debug/database-debug-tool.py neo4j
python scripts/debug/database-debug-tool.py milvus
```

**Features:**
- Connection testing with detailed error reporting
- Performance metrics collection
- Database-specific health checks
- Query performance analysis
- Server version and configuration info

### 3. Container Inspector (`container-inspector.py`)
**Docker container analysis**

Advanced container inspection and resource monitoring:

```bash
# Inspect all containers
python scripts/debug/container-inspector.py inspect

# Inspect specific container
python scripts/debug/container-inspector.py inspect --container postgres

# Monitor container resources
python scripts/debug/container-inspector.py monitor postgres --duration 300

# Get container logs
python scripts/debug/container-inspector.py logs postgres --lines 500

# Follow logs in real-time
python scripts/debug/container-inspector.py logs postgres --follow

# Restart container
python scripts/debug/container-inspector.py restart postgres

# Execute command in container
python scripts/debug/container-inspector.py exec postgres "pg_isready -U ml_user"
```

**Features:**
- Detailed container inspection (status, health, resources)
- Real-time resource monitoring (CPU, memory, network)
- Log collection and analysis
- Container lifecycle management
- Command execution inside containers

### 4. Log Analyzer (`log-analyzer.py`)
**Advanced log analysis**

Analyzes logs from all services to identify patterns and issues:

```bash
# Analyze all service logs
python scripts/debug/log-analyzer.py analyze

# Analyze specific service
python scripts/debug/log-analyzer.py analyze --service postgres --lines 2000

# Search for specific patterns
python scripts/debug/log-analyzer.py search "ERROR"
python scripts/debug/log-analyzer.py search "connection.*failed" --services postgres neo4j

# Generate log summary
python scripts/debug/log-analyzer.py summary --hours 2
```

**Features:**
- Pattern-based error detection
- Performance metrics extraction
- Cross-service error correlation
- Timeline analysis of critical events
- Automated health assessment

### 5. Network Diagnostics (`network-diagnostics.py`)
**Network connectivity troubleshooting**

Comprehensive network diagnostics for service connectivity:

```bash
# Check all service ports
python scripts/debug/network-diagnostics.py ports

# Check health endpoints
python scripts/debug/network-diagnostics.py health

# Check Docker networks
python scripts/debug/network-diagnostics.py networks

# Test inter-service connectivity
python scripts/debug/network-diagnostics.py connectivity

# Test DNS resolution
python scripts/debug/network-diagnostics.py dns

# Run network trace
python scripts/debug/network-diagnostics.py trace localhost 5432

# Generate comprehensive network report
python scripts/debug/network-diagnostics.py report
```

**Features:**
- Port connectivity testing
- HTTP health endpoint validation
- Docker network inspection
- Inter-service connectivity testing
- DNS resolution diagnostics
- Network trace and ping tests

## Legacy Debug Tools

### Debug Server (`debug-server.py`)
Starts the application with remote debugging enabled:

```bash
python scripts/debug/debug-server.py
# Debugger listens on port 5678
```

### Memory Profiler (`memory-profiler.py`)
Monitors memory usage during development:

```bash
python scripts/debug/memory-profiler.py --duration 300 --interval 10
```

### Performance Profiler (`profile-server.py`)
Runs the application with performance profiling:

```bash
python scripts/debug/profile-server.py
```

### Request Tracer (`request-tracer.py`)
Traces HTTP requests for debugging:

```bash
python scripts/debug/request-tracer.py
```

## Output and Reports

All debugging tools save their output to the `debug_output/` directory:

```
debug_output/
├── containers/          # Container inspection reports
├── database/           # Database diagnostics
├── logs/              # Log analysis results
├── network/           # Network diagnostics
└── profiles/          # Performance profiles
```

## Common Debugging Workflows

### 1. Service Not Starting
```bash
# Check overall status
python scripts/debug/local-debug-cli.py status

# Inspect the problematic container
python scripts/debug/container-inspector.py inspect --container <service>

# Check logs for errors
python scripts/debug/container-inspector.py logs <service> --lines 200

# Check network connectivity
python scripts/debug/network-diagnostics.py ports
```

### 2. Database Connection Issues
```bash
# Test database connections
python scripts/debug/database-debug-tool.py diagnostics

# Check network connectivity to databases
python scripts/debug/network-diagnostics.py connectivity

# Analyze logs for connection errors
python scripts/debug/log-analyzer.py search "connection.*failed"
```

### 3. Performance Issues
```bash
# Monitor system resources
python scripts/debug/local-debug-cli.py monitor --duration 300

# Monitor specific container
python scripts/debug/container-inspector.py monitor <service> --duration 300

# Test database performance
python scripts/debug/database-debug-tool.py performance --duration 120

# Analyze logs for performance issues
python scripts/debug/log-analyzer.py search "slow|timeout|performance"
```

### 4. Network Connectivity Problems
```bash
# Generate comprehensive network report
python scripts/debug/network-diagnostics.py report

# Check specific connectivity
python scripts/debug/network-diagnostics.py trace <host> <port>

# Check Docker networks
python scripts/debug/network-diagnostics.py networks
```

### 5. Application Health Issues
```bash
# Check application health endpoints
python scripts/debug/network-diagnostics.py health

# Generate comprehensive debug report
python scripts/debug/local-debug-cli.py report

# Analyze recent logs
python scripts/debug/log-analyzer.py summary --hours 1
```

## Dependencies

The debugging tools require the following Python packages:

```bash
pip install docker psutil requests pyyaml psycopg2-binary neo4j pymilvus
```

## Integration with Development Workflow

These tools integrate with the local development workflow:

1. **Makefile Integration**: Add debug targets to your Makefile
2. **CI/CD Integration**: Use in automated testing and validation
3. **Monitoring Integration**: Set up automated health checks
4. **Documentation**: Reference in troubleshooting guides

## Best Practices

1. **Regular Health Checks**: Run `local-debug-cli.py status` regularly
2. **Log Analysis**: Use log analyzer to identify patterns before they become issues
3. **Performance Monitoring**: Monitor resources during development and testing
4. **Network Validation**: Verify network connectivity after configuration changes
5. **Report Generation**: Generate comprehensive reports for complex issues

## Troubleshooting the Debug Tools

If the debug tools themselves have issues:

1. **Check Dependencies**: Ensure all required packages are installed
2. **Docker Access**: Verify Docker daemon is running and accessible
3. **Permissions**: Check file permissions for output directories
4. **Network Access**: Ensure tools can access Docker networks and services
5. **Resource Limits**: Check if system has sufficient resources

## Contributing

When adding new debugging capabilities:

1. Follow the existing code structure and patterns
2. Add comprehensive error handling and logging
3. Include usage examples in docstrings
4. Update this README with new functionality
5. Add integration tests where appropriate