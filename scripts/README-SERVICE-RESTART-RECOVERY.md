# Service Restart and Recovery Scripts

This directory contains comprehensive service restart and recovery scripts for the local development environment. These scripts provide intelligent service management with dependency handling, health checking, and automated recovery procedures.

## Overview

The service restart and recovery system consists of four main components:

1. **`restart-service.py`** - Intelligent single service restart with dependency management
2. **`recover-services.py`** - Advanced service recovery with multiple strategies
3. **`service-monitor.py`** - Continuous service monitoring with automatic recovery
4. **`restart-all-services.sh`** - Comprehensive restart of all services

## Scripts Description

### 1. restart-service.py

Provides intelligent service restart capabilities with dependency management and health checking.

**Features:**
- Dependency-aware restart (restarts dependent services when needed)
- Health check validation after restart
- Force restart option for problematic services
- JSON output for automation
- Service status reporting

**Usage:**
```bash
# Restart a single service
python3 scripts/restart-service.py postgres

# Restart with dependent services
python3 scripts/restart-service.py postgres --cascade

# Force restart (continue even if some operations fail)
python3 scripts/restart-service.py milvus --force

# Restart all services
python3 scripts/restart-service.py all

# List available services
python3 scripts/restart-service.py --list-services

# Get JSON report
python3 scripts/restart-service.py neo4j --json
```

**Service Dependencies:**
- `multimodal-librarian` depends on: postgres, neo4j, milvus, redis
- `milvus` depends on: etcd, minio
- `attu` depends on: milvus
- `pgadmin` depends on: postgres

### 2. recover-services.py

Advanced service recovery with multiple strategies and automatic problem detection.

**Features:**
- Multiple recovery strategies (simple restart, dependency restart, container recreation, etc.)
- Automatic issue diagnosis from logs
- Known issue detection and resolution
- Emergency backup before destructive operations
- Comprehensive recovery reporting

**Recovery Strategies:**
1. **Simple Restart** - Basic service restart
2. **Dependency Restart** - Restart with dependencies
3. **Container Recreate** - Remove and recreate container
4. **Image Refresh** - Pull fresh image and recreate
5. **Volume Reset** - Reset service volumes (⚠️ Data loss)
6. **Network Reset** - Reset Docker networks
7. **Full Reset** - Complete environment reset (⚠️ All data loss)

**Usage:**
```bash
# Recover a service (tries all strategies)
python3 scripts/recover-services.py postgres

# Diagnose issues only (no recovery)
python3 scripts/recover-services.py postgres --diagnose-only

# Use specific recovery strategies
python3 scripts/recover-services.py milvus --strategies "simple_restart,container_recreate"

# Get JSON report
python3 scripts/recover-services.py neo4j --json
```

**Known Issues Detection:**
- Port conflicts
- Volume permission issues
- Network conflicts
- Image corruption
- Dependency failures

### 3. service-monitor.py

Continuous service monitoring with automatic restart and recovery capabilities.

**Features:**
- Real-time health monitoring
- Automatic restart of failed critical services
- Alert generation and tracking
- Configurable monitoring intervals
- Restart cooldown and attempt limits
- Comprehensive status reporting

**Usage:**
```bash
# Start monitoring all services
python3 scripts/service-monitor.py

# Monitor with custom interval
python3 scripts/service-monitor.py --interval 60

# Monitor specific services
python3 scripts/service-monitor.py --services postgres,neo4j,milvus

# Disable automatic restart
python3 scripts/service-monitor.py --no-auto-restart

# Get current status
python3 scripts/service-monitor.py --status --json
```

**Monitoring Configuration:**
- Check interval: 30 seconds (configurable)
- Health check timeout: 15 seconds
- Restart cooldown: 5 minutes
- Maximum restart attempts: 3
- Alert on 3 consecutive failures

### 4. restart-all-services.sh

Comprehensive restart of all services with proper dependency ordering and health verification.

**Features:**
- Dependency-aware service ordering
- Optional backup before restart
- Health check verification
- Verbose output option
- Force restart capability
- Final status reporting

**Usage:**
```bash
# Standard restart
./scripts/restart-all-services.sh

# Restart with backup
./scripts/restart-all-services.sh --backup

# Force restart with verbose output
./scripts/restart-all-services.sh --force --verbose

# Extended timeout
./scripts/restart-all-services.sh --timeout 600
```

**Service Start Order:**
1. etcd, minio (Milvus dependencies)
2. postgres, neo4j, redis (Core databases)
3. milvus (Vector database)
4. multimodal-librarian (Main application)
5. pgadmin, attu, redis-commander, log-viewer (Admin tools)

## Integration with Existing Scripts

These scripts integrate with existing health check and management scripts:

- **`wait-for-services.sh`** - Used for health verification
- **`health-check-all-services.py`** - Used for comprehensive health checks
- **`backup-all-databases.sh`** - Used for pre-restart backups

## Configuration

### Service Configurations

Each service has specific configuration in the scripts:

```python
service_configs = {
    "postgres": {
        "critical": True,
        "health_check": check_postgres_health,
        "restart_priority": 1,
        "dependencies": []
    },
    "multimodal-librarian": {
        "critical": True,
        "health_check": check_app_health,
        "restart_priority": 3,
        "dependencies": ["postgres", "neo4j", "milvus", "redis"]
    }
}
```

### Health Check Methods

Each service has specific health check methods:

- **PostgreSQL**: `pg_isready` command
- **Neo4j**: Cypher shell connection test
- **Redis**: `redis-cli ping` command
- **Milvus**: HTTP health endpoint check
- **Application**: HTTP health endpoint check

## Error Handling and Recovery

### Automatic Recovery

The monitoring system automatically attempts recovery when:
- Service fails 3 consecutive health checks
- Service is marked as critical
- Restart cooldown period has passed
- Maximum restart attempts not exceeded

### Manual Recovery

For manual recovery, use the recovery script with different strategies:

```bash
# Try all recovery strategies
python3 scripts/recover-services.py <service>

# Try specific strategies only
python3 scripts/recover-services.py <service> --strategies "simple_restart,container_recreate"
```

### Emergency Procedures

For severe issues:

1. **Full Environment Reset**:
   ```bash
   python3 scripts/recover-services.py multimodal-librarian --strategies "full_reset"
   ```

2. **Manual Cleanup**:
   ```bash
   docker-compose -f docker-compose.local.yml down -v
   docker system prune -f --volumes
   ./scripts/restart-all-services.sh
   ```

## Logging and Monitoring

### Log Locations

- Service logs: `docker-compose -f docker-compose.local.yml logs <service>`
- Application logs: `./logs/` directory
- Monitoring logs: Console output with timestamps

### Status Monitoring

Check service status:
```bash
# Quick status
python3 scripts/restart-service.py --list-services

# Detailed health check
python3 scripts/health-check-all-services.py

# Monitor status
python3 scripts/service-monitor.py --status
```

## Troubleshooting

### Common Issues

1. **Port Conflicts**
   - Symptom: "port is already allocated"
   - Solution: Kill processes using the ports or change port mappings

2. **Volume Permission Issues**
   - Symptom: "permission denied"
   - Solution: Fix volume permissions or recreate volumes

3. **Network Conflicts**
   - Symptom: "network with name already exists"
   - Solution: Recreate Docker networks

4. **Image Corruption**
   - Symptom: "no such file or directory"
   - Solution: Pull fresh images

### Debug Steps

1. **Check service logs**:
   ```bash
   docker-compose -f docker-compose.local.yml logs <service>
   ```

2. **Diagnose issues**:
   ```bash
   python3 scripts/recover-services.py <service> --diagnose-only
   ```

3. **Check Docker status**:
   ```bash
   docker-compose -f docker-compose.local.yml ps
   ```

4. **Verify network connectivity**:
   ```bash
   docker network ls
   docker network inspect multimodal-librarian-local
   ```

## Best Practices

### Development Workflow

1. **Start monitoring** when beginning development:
   ```bash
   python3 scripts/service-monitor.py &
   ```

2. **Use cascade restart** when changing dependencies:
   ```bash
   python3 scripts/restart-service.py postgres --cascade
   ```

3. **Create backups** before major changes:
   ```bash
   ./scripts/restart-all-services.sh --backup
   ```

### Production Considerations

- These scripts are designed for local development only
- Do not use volume reset or full reset in production
- Always create backups before destructive operations
- Monitor restart attempts to avoid infinite loops

## Integration with Make Targets

Add these targets to your Makefile:

```makefile
# Service management targets
restart-service:
	python3 scripts/restart-service.py $(SERVICE)

restart-all:
	./scripts/restart-all-services.sh

recover-service:
	python3 scripts/recover-services.py $(SERVICE)

monitor-services:
	python3 scripts/service-monitor.py

service-status:
	python3 scripts/restart-service.py --list-services
```

Usage:
```bash
make restart-service SERVICE=postgres
make restart-all
make recover-service SERVICE=milvus
make monitor-services
make service-status
```

## Future Enhancements

Potential improvements for the restart and recovery system:

1. **External Alerting** - Email, Slack, or webhook notifications
2. **Metrics Collection** - Prometheus/Grafana integration
3. **Advanced Scheduling** - Cron-based maintenance windows
4. **Configuration Management** - External configuration files
5. **Performance Monitoring** - Resource usage tracking
6. **Automated Testing** - Post-restart validation tests

## Support

For issues with the restart and recovery scripts:

1. Check the troubleshooting section above
2. Review service logs for specific error messages
3. Use the diagnosis feature: `--diagnose-only`
4. Try different recovery strategies
5. Consider manual intervention for complex issues

The scripts provide comprehensive logging and error reporting to help identify and resolve issues quickly.