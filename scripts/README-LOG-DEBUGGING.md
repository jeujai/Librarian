# Log Viewing and Debugging Utilities

This document describes the comprehensive log viewing and debugging utilities available for the Multimodal Librarian local development environment.

## Overview

The local development environment includes several utilities for monitoring, debugging, and analyzing logs and service health:

- **Interactive Log Viewer** - Real-time log viewing with filtering and search
- **Service Debugger** - Comprehensive service health and connectivity analysis
- **Network Debugger** - Network connectivity and DNS resolution testing
- **Log Analysis** - Automated log analysis for errors and patterns
- **Log Cleanup** - Automated log rotation, compression, and cleanup

## Quick Start

### View Logs Interactively

```bash
# Start interactive log viewer
make logs-viewer

# Or directly
python3 scripts/logs-viewer.py
```

### Debug a Service

```bash
# Debug specific service
make debug-service SERVICE=postgres

# Or directly
python3 scripts/debug-service.py postgres
```

### Debug Network Issues

```bash
# Run network diagnostic
make debug-network

# Or directly
python3 scripts/debug-network.py
```

### Analyze Logs

```bash
# Analyze logs for errors and patterns
make logs-analyze

# Or directly
./scripts/logs-analyze.sh
```

## Detailed Usage

### 1. Interactive Log Viewer (`logs-viewer.py`)

A terminal-based interactive log viewer with real-time filtering and search capabilities.

**Features:**
- Real-time log streaming from all services
- Interactive filtering by service and log level
- Search functionality with highlighting
- Scroll through log history
- Color-coded log levels
- Service status indicators

**Usage:**
```bash
# Basic usage
python3 scripts/logs-viewer.py

# Specific services only
python3 scripts/logs-viewer.py --services multimodal-librarian postgres

# Custom compose file
python3 scripts/logs-viewer.py --compose-file docker-compose.prod.yml

# Show logs since specific time
python3 scripts/logs-viewer.py --since "2024-01-15T10:00:00"
```

**Interactive Controls:**
- `↑/↓` - Scroll up/down one line
- `PgUp/PgDn` - Scroll up/down one page
- `f` - Toggle filter mode
- `/` - Search logs
- `c` - Clear log buffer
- `h` - Show help
- `q` - Quit

**Filter Mode:**
- `s` - Toggle service filters
- `l` - Toggle log level filters
- `q` - Exit filter mode

### 2. Service Debugger (`debug-service.py`)

Comprehensive debugging tool for individual services with health checks, resource monitoring, and configuration analysis.

**Features:**
- Service status and uptime monitoring
- CPU and memory usage tracking
- Network connectivity testing
- Port accessibility checks
- Recent error analysis
- Configuration validation
- Automated recommendations

**Usage:**
```bash
# Debug specific service
python3 scripts/debug-service.py postgres

# Save report to file
python3 scripts/debug-service.py postgres --output debug-postgres.json

# Quiet mode (recommendations only)
python3 scripts/debug-service.py postgres --quiet

# Custom compose file
python3 scripts/debug-service.py postgres --compose-file docker-compose.prod.yml
```

**Available Services:**
- `multimodal-librarian` - Main application
- `postgres` - PostgreSQL database
- `neo4j` - Neo4j graph database
- `milvus` - Milvus vector database
- `redis` - Redis cache
- `etcd` - etcd key-value store
- `minio` - MinIO object storage

**Sample Output:**
```
================================================================================
DEBUG REPORT: POSTGRES
================================================================================
Generated: 2024-01-15 14:30:45

📊 STATUS
   Status: running
   Uptime: 2h 15m
   CPU Usage: 2.3%
   Memory Usage: 156.2MB / 512.0MB (30.5%)

🌐 NETWORK STATUS
   Container Network: ✅
   External Access: ✅
   DNS Resolution: ✅

🔌 PORT STATUS
   Port 5432: ✅ Accessible

🚨 RECENT ERRORS
   No recent errors found

⚙️  CONFIGURATION
   Config Files:
     database/postgresql/postgresql.conf: ✅
   Exposed Ports: 5432
   Volume Mounts: 3 configured

💡 RECOMMENDATIONS
   Service appears healthy - no issues detected
```

### 3. Network Debugger (`debug-network.py`)

Comprehensive network connectivity and DNS resolution testing for the entire development environment.

**Features:**
- Docker network status validation
- Container-to-container connectivity testing
- Port accessibility from host
- DNS resolution testing (internal and external)
- Service health checks via HTTP endpoints
- Dependency connectivity validation
- Automated network troubleshooting recommendations

**Usage:**
```bash
# Full network diagnostic
python3 scripts/debug-network.py

# Save report to file
python3 scripts/debug-network.py --output network-diagnostic.json

# Quiet mode (recommendations only)
python3 scripts/debug-network.py --quiet

# Focus on specific service
python3 scripts/debug-network.py --service postgres
```

**Sample Output:**
```
================================================================================
NETWORK DIAGNOSTIC REPORT
================================================================================
Generated: 2024-01-15T14:30:45.123456

🐳 DOCKER NETWORK STATUS
   Network Exists: ✅
   Network Name: multimodal-librarian-local_ml-local-network
   Driver: bridge
   Subnet: 172.21.0.0/16
   Connected Containers: 7

🔗 CONTAINER CONNECTIVITY
   multimodal-librarian: ✅ (IP: 172.21.0.2)
   postgres: ✅ (IP: 172.21.0.3)
   neo4j: ✅ (IP: 172.21.0.4)
   milvus: ✅ (IP: 172.21.0.5)

🔌 PORT ACCESSIBILITY (from host)
   multimodal-librarian: ✅ [8000]
   postgres: ✅ [5432]
   neo4j: ✅ [7474, 7687]
   milvus: ✅ [19530, 9091]

🏥 SERVICE HEALTH
   multimodal-librarian: ✅ healthy
     HTTP /api/health/simple: ✅ (200, 0.045s)
   postgres: ✅ healthy
   neo4j: ✅ healthy
     HTTP /db/manage/server/core/available: ✅ (200, 0.123s)

🌐 DNS RESOLUTION
   External DNS:
     google.com: ✅
     github.com: ✅
     docker.io: ✅

💡 RECOMMENDATIONS
   Network appears healthy - no issues detected
```

### 4. Log Analysis (`logs-analyze.sh`)

Automated log analysis script that examines logs from all services and provides insights about errors, performance, and system health.

**Features:**
- Log level distribution analysis
- Error pattern detection and reporting
- API endpoint usage statistics
- Performance metrics extraction
- Database error analysis
- System health assessment
- Automated recommendations

**Usage:**
```bash
# Analyze logs from last hour (default)
./scripts/logs-analyze.sh

# Analyze logs from specific time range
./scripts/logs-analyze.sh 30m    # Last 30 minutes
./scripts/logs-analyze.sh 2h     # Last 2 hours
./scripts/logs-analyze.sh 1d     # Last day

# Show help
./scripts/logs-analyze.sh --help
```

**Sample Output:**
```
=============================================================================
MULTIMODAL LIBRARIAN - LOG ANALYSIS REPORT
=============================================================================
Time Range: 1h
Generated: Mon Jan 15 14:30:45 PST 2024

=============================================================================
APPLICATION LOG ANALYSIS
=============================================================================

Log Level Distribution:
----------------------
DEBUG:       245
INFO:        156
WARNING:       3
ERROR:         0
CRITICAL:      0

✅ No errors found in the specified time range

API Endpoint Activity:
---------------------
    45  /api/chat
    23  /api/documents
    12  /api/health/simple
     8  /api/search
     3  /docs

Performance Metrics:
-------------------
Slow operations (>1000ms): 2

Slowest Operations:
  2340 ms
  1567 ms

=============================================================================
DATABASE LOG ANALYSIS
=============================================================================

PostgreSQL errors:          0
Connection events:          12

Neo4j errors:               0
Query events:               8

Milvus errors:              0
Search events:              5

=============================================================================
SUMMARY AND RECOMMENDATIONS
=============================================================================

✅ System appears healthy - no errors found in the last 1h

Recommendations:
----------------
• Monitor logs in real-time: docker-compose -f docker-compose.local.yml logs -f
• View logs in browser: http://localhost:8080 (start with --profile monitoring)
```

### 5. Log Cleanup (`logs-cleanup.sh`)

Comprehensive log management utility for cleanup, rotation, compression, and archival.

**Features:**
- Automated log cleanup based on age
- Log compression to save disk space
- Log archival for long-term storage
- Log rotation for large files
- Disk usage monitoring
- Configurable retention policies

**Usage:**
```bash
# Basic cleanup (default: 30 days retention)
./scripts/logs-cleanup.sh

# Custom retention period
./scripts/logs-cleanup.sh --retention-days 14

# Compress old logs
./scripts/logs-cleanup.sh compress

# Archive very old logs
./scripts/logs-cleanup.sh archive

# Rotate large log files
./scripts/logs-cleanup.sh rotate

# Show log directory status
./scripts/logs-cleanup.sh status

# Dry run (preview without changes)
./scripts/logs-cleanup.sh --dry-run cleanup

# Verbose output
./scripts/logs-cleanup.sh --verbose cleanup
```

**Commands:**
- `cleanup` - Remove logs older than retention period (default)
- `compress` - Compress logs older than compress period
- `archive` - Archive logs older than archive period to tar.gz
- `rotate` - Rotate logs larger than maximum size
- `status` - Show log directory status and statistics
- `purge` - Remove ALL logs (dangerous!)

**Configuration:**
```bash
# Environment variables
export LOG_RETENTION_DAYS=30      # Keep logs for 30 days
export LOG_COMPRESS_DAYS=7        # Compress logs older than 7 days
export LOG_ARCHIVE_DAYS=90        # Archive logs older than 90 days
export MAX_LOG_SIZE=100M          # Rotate logs larger than 100MB
```

## Makefile Integration

All utilities are integrated into the Makefile for easy access:

### Log Viewing Commands
```bash
make logs                 # Basic log viewing
make logs-local          # Local development logs
make logs-viewer         # Interactive log viewer
make logs-analyze        # Analyze logs for patterns
make logs-status         # Show log directory status
make logs-cleanup        # Clean up old logs
```

### Debugging Commands
```bash
make debug-service SERVICE=postgres    # Debug specific service
make debug-network                     # Debug network connectivity
make health                           # Check service health
make monitor                          # Show resource usage
```

### Service Management
```bash
make dev-local           # Start local development environment
make down               # Stop all services
make db-status          # Show database status
make network-info       # Show network information
```

## Web-Based Log Viewing

In addition to command-line tools, you can use Dozzle for web-based log viewing:

```bash
# Start with monitoring profile
docker-compose -f docker-compose.local.yml --profile monitoring up -d

# Access web interface
open http://localhost:8080
```

**Dozzle Features:**
- Real-time log streaming
- Multi-container log viewing
- Search and filtering
- Log downloading
- Container statistics

## Troubleshooting

### Common Issues

**1. Interactive log viewer not working:**
```bash
# Install required dependencies
pip install docker

# Check curses support
python3 -c "import curses; print('Curses available')"
```

**2. Service debugger missing dependencies:**
```bash
# Install required packages
pip install docker requests psutil
```

**3. Network debugger fails:**
```bash
# Install required packages
pip install docker requests

# Check Docker daemon
docker info
```

**4. Permission issues with log files:**
```bash
# Fix log directory permissions
sudo chown -R $USER:$USER logs/
chmod -R 755 logs/
```

### Debug Script Issues

**1. Script not executable:**
```bash
chmod +x scripts/logs-viewer.py
chmod +x scripts/debug-service.py
chmod +x scripts/debug-network.py
chmod +x scripts/logs-analyze.sh
chmod +x scripts/logs-cleanup.sh
```

**2. Python import errors:**
```bash
# Install development requirements
pip install -r requirements-dev.txt

# Or install specific packages
pip install docker requests psutil
```

**3. Docker connection issues:**
```bash
# Check Docker daemon
docker info

# Check Docker socket permissions
ls -la /var/run/docker.sock

# Add user to docker group (Linux)
sudo usermod -aG docker $USER
```

## Best Practices

### Log Management
1. **Regular Cleanup**: Run log cleanup weekly to prevent disk space issues
2. **Monitor Disk Usage**: Check log directory size regularly
3. **Retention Policy**: Adjust retention periods based on your needs
4. **Compression**: Enable log compression for older logs to save space

### Debugging Workflow
1. **Start with Health Checks**: Use `make health` for quick overview
2. **Service-Specific Issues**: Use `make debug-service SERVICE=name` for detailed analysis
3. **Network Issues**: Use `make debug-network` for connectivity problems
4. **Log Analysis**: Use `make logs-analyze` to identify patterns and errors

### Performance Monitoring
1. **Regular Monitoring**: Use `make monitor` to check resource usage
2. **Log Analysis**: Run log analysis daily to catch performance issues
3. **Service Health**: Monitor service health continuously in production
4. **Network Diagnostics**: Run network diagnostics when connectivity issues arise

## Integration with Development Workflow

### Daily Development
```bash
# Start development environment
make dev-local

# Check service health
make health

# View logs interactively
make logs-viewer

# Debug issues as they arise
make debug-service SERVICE=problematic-service
```

### Troubleshooting Workflow
```bash
# 1. Quick health check
make health

# 2. Analyze recent logs
make logs-analyze

# 3. Debug specific service
make debug-service SERVICE=failing-service

# 4. Check network connectivity
make debug-network

# 5. Clean up logs if needed
make logs-cleanup
```

### Maintenance Tasks
```bash
# Weekly log cleanup
make logs-cleanup

# Monthly log status check
make logs-status

# Quarterly log archival
./scripts/logs-cleanup.sh archive
```

This comprehensive suite of log viewing and debugging utilities provides everything needed to monitor, debug, and maintain the local development environment effectively.