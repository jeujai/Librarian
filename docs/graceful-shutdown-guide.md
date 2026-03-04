# Graceful Shutdown Guide

This guide explains the graceful shutdown procedures implemented for the Multimodal Librarian local development environment.

## Overview

The graceful shutdown system ensures that all services and resources are properly cleaned up when stopping the local development environment. This prevents data corruption, connection leaks, and other issues that can occur with abrupt shutdowns.

## Features

- **Coordinated Shutdown**: Services are stopped in the correct dependency order
- **Configurable Timeouts**: Each service has appropriate shutdown timeouts
- **Resource Cleanup**: Automatic cleanup of containers, networks, and temporary resources
- **Status Monitoring**: Real-time monitoring of shutdown progress
- **Force Mode**: Fallback to forced shutdown if graceful shutdown fails
- **Selective Shutdown**: Ability to shutdown specific services only

## Quick Start

### Basic Graceful Shutdown

```bash
# Standard graceful shutdown
make dev-shutdown

# Or use the script directly
python scripts/graceful-shutdown.py
```

### Quick Shutdown

```bash
# Quick shutdown with 30-second timeout
make dev-shutdown-quick

# Or specify custom timeout
python scripts/graceful-shutdown.py --timeout 30
```

### Force Shutdown

```bash
# Force shutdown if graceful shutdown fails
make dev-shutdown-force

# Or use the script with force flag
python scripts/graceful-shutdown.py --force
```

## Available Commands

### Makefile Targets

| Command | Description |
|---------|-------------|
| `make dev-shutdown` | Standard graceful shutdown |
| `make dev-shutdown-force` | Forced shutdown if graceful fails |
| `make dev-shutdown-quick` | Quick shutdown (30s timeout) |
| `make dev-shutdown-services` | Interactive service selection |
| `make dev-shutdown-dry-run` | Show what would be done |
| `make dev-shutdown-status` | Check shutdown status |

### Script Options

```bash
python scripts/graceful-shutdown.py [OPTIONS]

Options:
  --timeout SECONDS    Maximum time to wait for graceful shutdown (default: 60)
  --force             Force shutdown if graceful shutdown fails
  --services SERVICE  Shutdown specific services only (comma-separated)
  --skip-cleanup      Skip resource cleanup validation
  --verbose           Enable verbose logging
  --dry-run           Show what would be done without executing
```

## Shutdown Process

The graceful shutdown process follows these phases:

### Phase 1: Pre-shutdown Validation
- Check Docker Compose availability
- Verify docker-compose.local.yml exists
- Identify running services
- Validate environment

### Phase 2: Application Shutdown Signal
- Send SIGTERM to the application container
- Wait for application to acknowledge shutdown
- Allow time for in-flight requests to complete

### Phase 3: Service Shutdown
Services are stopped in dependency order:

1. **multimodal-librarian** (30s timeout) - Main application
2. **attu, pgadmin, redis-commander, log-viewer** (5-10s) - Admin tools
3. **milvus** (20s timeout) - Vector database
4. **neo4j** (25s timeout) - Graph database
5. **postgres** (20s timeout) - Relational database
6. **redis** (10s timeout) - Cache
7. **minio** (15s timeout) - Milvus dependency
8. **etcd** (10s timeout) - Milvus dependency

### Phase 4: Resource Cleanup
- Remove stopped containers
- Clean up unused networks
- Validate port release
- Optional: Clean up unused images

### Phase 5: Validation
- Verify all services are stopped
- Check that ports are released
- Validate cleanup completion

## Docker Compose Configuration

Each service in `docker-compose.local.yml` is configured with:

```yaml
services:
  service-name:
    # Graceful shutdown configuration
    stop_signal: SIGTERM      # Send SIGTERM for graceful shutdown
    stop_grace_period: 30s    # Wait up to 30s before SIGKILL
    init: true               # Use init process for proper signal handling
```

### Service-Specific Timeouts

| Service | Grace Period | Reason |
|---------|--------------|--------|
| multimodal-librarian | 30s | Allow request completion and cleanup |
| postgres | 20s | Database checkpoint and connection cleanup |
| neo4j | 25s | Graph database transaction completion |
| milvus | 20s | Vector index flushing |
| redis | 10s | Memory persistence |
| minio | 15s | Object storage cleanup |
| etcd | 10s | Cluster state synchronization |

## Application-Level Shutdown

The application implements comprehensive shutdown handling:

### Signal Handling
```python
from multimodal_librarian.shutdown import get_shutdown_handler

# Setup signal handlers for SIGTERM and SIGINT
shutdown_handler = get_shutdown_handler()
shutdown_handler.setup_signal_handlers()
```

### Cleanup Registration
```python
from multimodal_librarian.shutdown import register_cleanup_function

# Register custom cleanup functions
def my_cleanup():
    # Custom cleanup logic
    pass

register_cleanup_function(my_cleanup)
```

### Background Task Management
```python
from multimodal_librarian.shutdown import register_background_task

# Register background tasks for proper cancellation
task = asyncio.create_task(my_background_task())
register_background_task(task)
```

## Database Connection Cleanup

The database factory provides graceful shutdown of all connections:

```python
from multimodal_librarian.clients.database_factory import graceful_shutdown

# Graceful shutdown of all database connections
await graceful_shutdown()
```

### Connection Cleanup Process
1. **Concurrent Shutdown**: All database clients are shutdown concurrently
2. **Multiple Methods**: Tries `disconnect()`, `close()`, `quit()`, `shutdown()` methods
3. **Error Handling**: Continues shutdown even if individual clients fail
4. **Timeout Protection**: 30-second timeout prevents hanging
5. **Resource Clearing**: Clears all client references

## Monitoring and Debugging

### Shutdown Status
```bash
# Check current shutdown status
make dev-shutdown-status

# Or use Python directly
python -c "from src.multimodal_librarian.shutdown import get_shutdown_status; import json; print(json.dumps(get_shutdown_status(), indent=2))"
```

### Verbose Logging
```bash
# Enable verbose logging for debugging
python scripts/graceful-shutdown.py --verbose
```

### Dry Run Mode
```bash
# See what would be done without executing
python scripts/graceful-shutdown.py --dry-run
```

## Troubleshooting

### Common Issues

#### Services Won't Stop Gracefully
```bash
# Use force mode to kill stubborn services
python scripts/graceful-shutdown.py --force
```

#### Timeout Errors
```bash
# Increase timeout for slow systems
python scripts/graceful-shutdown.py --timeout 120
```

#### Port Still in Use
```bash
# Check what's using the port
lsof -i :8000

# Kill process if needed
kill -9 $(lsof -t -i:8000)
```

#### Database Connection Issues
```bash
# Check database container logs
docker-compose -f docker-compose.local.yml logs postgres
docker-compose -f docker-compose.local.yml logs neo4j
docker-compose -f docker-compose.local.yml logs milvus
```

### Debug Mode

For detailed debugging, use verbose mode and check logs:

```bash
# Verbose shutdown with logging
python scripts/graceful-shutdown.py --verbose 2>&1 | tee shutdown.log

# Check Docker Compose logs
docker-compose -f docker-compose.local.yml logs --tail=100
```

## Best Practices

### Development Workflow
1. Always use graceful shutdown instead of `docker-compose down`
2. Use `make dev-shutdown` for standard shutdown
3. Use `--dry-run` to preview changes
4. Monitor shutdown status for long-running operations

### Service Development
1. Implement proper signal handling in custom services
2. Register cleanup functions for resources
3. Use appropriate timeouts for service complexity
4. Test shutdown behavior during development

### Debugging
1. Use verbose mode for troubleshooting
2. Check individual service logs for errors
3. Validate resource cleanup after shutdown
4. Test both graceful and force shutdown modes

## Integration with CI/CD

The graceful shutdown system integrates with testing and CI/CD:

```bash
# In test scripts
make dev-shutdown-quick  # Quick shutdown for tests

# In CI/CD pipelines
python scripts/graceful-shutdown.py --timeout 30 --force
```

## Performance Considerations

- **Parallel Shutdown**: Database connections are closed concurrently
- **Timeout Management**: Each service has optimized timeout values
- **Resource Cleanup**: Minimal cleanup to avoid delays
- **Force Mode**: Available as fallback for time-critical situations

## Security Considerations

- **Signal Handling**: Proper SIGTERM/SIGINT handling prevents data corruption
- **Resource Cleanup**: Ensures no sensitive data remains in memory
- **Connection Cleanup**: Prevents connection leaks and security issues
- **Container Cleanup**: Removes containers that might contain sensitive data

## Future Enhancements

Planned improvements to the graceful shutdown system:

1. **Health Check Integration**: Monitor service health during shutdown
2. **Rollback Capability**: Restart services if shutdown fails
3. **Metrics Collection**: Collect shutdown performance metrics
4. **Custom Hooks**: Allow custom pre/post shutdown hooks
5. **Notification System**: Send notifications on shutdown completion/failure