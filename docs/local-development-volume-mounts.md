# Local Development Volume Mounts

This document explains the volume mount configuration for local development with Docker Compose.

## Overview

The local development environment uses extensive volume mounts to provide:
- Hot reload for source code changes
- Persistent data storage across container restarts
- Development tool integration
- Efficient caching for faster rebuilds

## Volume Mount Categories

### 1. Source Code Mounts (Hot Reload)

These mounts enable real-time code changes without container rebuilds:

```yaml
# Source code for hot reload
- ./src:/app/src:rw
# Configuration files
- ./pyproject.toml:/app/pyproject.toml:ro
- ./.env.local:/app/.env.local:ro
```

**Benefits:**
- Instant code changes without rebuilding containers
- Faster development iteration
- Real-time debugging capabilities

### 2. Application Data Directories

Persistent storage for application data:

```yaml
# Main data directories
- ./uploads:/app/uploads:rw
- ./media:/app/media:rw
- ./exports:/app/exports:rw
- ./logs:/app/logs:rw
- ./audit_logs:/app/audit_logs:rw

# Test data directories
- ./test_uploads:/app/test_uploads:rw
- ./test_media:/app/test_media:rw
- ./test_exports:/app/test_exports:rw
- ./test_data:/app/test_data:rw
```

**Benefits:**
- Data persists across container restarts
- Easy access to uploaded files and generated content
- Separate test data isolation

### 3. Development Tools and Configuration

Read-only mounts for development resources:

```yaml
# Development requirements
- ./requirements-dev.txt:/app/requirements-dev.txt:ro
- ./requirements-dev-tools.txt:/app/requirements-dev-tools.txt:ro

# Documentation and examples
- ./docs:/app/docs:ro
- ./examples:/app/examples:ro

# Development scripts
- ./scripts:/app/scripts:ro
```

**Benefits:**
- Access to documentation within containers
- Development scripts available for debugging
- Consistent development environment

### 4. Cache and Temporary Directories

Named volumes for performance optimization:

```yaml
# ML model cache (persistent)
- ml_model_cache:/app/.cache
# Python package cache
- python_cache:/root/.cache/pip
# Pytest cache
- pytest_cache:/app/.pytest_cache
```

**Benefits:**
- Faster container startup (cached models)
- Reduced download times for dependencies
- Improved test execution speed

### 5. Development Workspace

Optional workspace for experimentation:

```yaml
# Jupyter notebooks and workspace
- ./notebooks:/app/notebooks:rw
# IDE settings (read-only)
- ./.vscode:/app/.vscode:ro
```

**Benefits:**
- Jupyter notebook integration
- IDE configuration sharing
- Experimental workspace

## Database Volume Mounts

Each database service has dedicated volume mounts:

### PostgreSQL
```yaml
- postgres_data:/var/lib/postgresql/data
- postgres_config:/etc/postgresql
- ./database/postgresql/init/:/docker-entrypoint-initdb.d/:ro
- ./backups/postgresql:/backups:rw
```

### Neo4j
```yaml
- neo4j_data:/data
- neo4j_logs:/logs
- neo4j_import:/var/lib/neo4j/import
- neo4j_plugins:/plugins
- ./backups/neo4j:/backups:rw
```

### Milvus
```yaml
- milvus_data:/var/lib/milvus
```

### Redis
```yaml
- redis_data:/data
```

## Volume Types

### Bind Mounts
Used for source code and configuration files that need to be edited on the host:
```yaml
- ./src:/app/src:rw  # Read-write bind mount
- ./docs:/app/docs:ro  # Read-only bind mount
```

### Named Volumes
Used for data that should persist but doesn't need host access:
```yaml
volumes:
  ml_model_cache:
    driver: local
    driver_opts:
      type: none
      o: bind
      device: ./cache/models
```

## Directory Structure

The volume mounts expect this directory structure:

```
project-root/
├── src/                    # Source code (hot reload)
├── uploads/               # File uploads
├── media/                 # Media files
├── exports/               # Generated exports
├── logs/                  # Application logs
├── audit_logs/            # Audit logs
├── test_uploads/          # Test file uploads
├── test_media/            # Test media files
├── test_exports/          # Test exports
├── test_data/             # Test data
├── notebooks/             # Jupyter notebooks
├── docs/                  # Documentation
├── examples/              # Code examples
├── scripts/               # Utility scripts
├── data/                  # Database data
│   ├── postgres/
│   ├── neo4j/
│   ├── milvus/
│   ├── etcd/
│   ├── minio/
│   ├── redis/
│   └── pgadmin/
├── cache/                 # Cache directories
│   ├── models/
│   ├── pip/
│   └── pytest/
└── backups/               # Database backups
    ├── postgresql/
    └── neo4j/
```

## Setup

Run the setup script to create all necessary directories:

```bash
./scripts/setup-development-directories.sh
```

Or use the Makefile target:

```bash
make dev-local-setup
```

## Performance Considerations

### Hot Reload Performance
- Source code mounts use `:rw` for read-write access
- Configuration files use `:ro` for read-only access
- File watching is optimized for Python files only

### Cache Optimization
- ML models are cached in persistent volumes
- Python packages are cached to speed up rebuilds
- Test cache improves pytest performance

### Resource Usage
- Volume mounts have minimal performance impact
- Named volumes are stored on the host filesystem
- Database volumes use bind mounts for easy backup access

## Troubleshooting

### Permission Issues
If you encounter permission issues:

```bash
# Fix directory permissions
sudo chown -R $USER:$USER data/ cache/ backups/
chmod -R 755 data/ cache/ backups/
```

### Hot Reload Not Working
1. Check that source files are mounted correctly:
   ```bash
   docker-compose -f docker-compose.local.yml exec multimodal-librarian ls -la /app/src
   ```

2. Verify the development target is being used:
   ```bash
   docker-compose -f docker-compose.local.yml exec multimodal-librarian env | grep DEBUG
   ```

### Volume Mount Failures
1. Ensure directories exist:
   ```bash
   ./scripts/setup-development-directories.sh
   ```

2. Check Docker daemon permissions:
   ```bash
   docker info | grep -i "storage driver"
   ```

### Database Connection Issues
1. Check database volumes are mounted:
   ```bash
   docker-compose -f docker-compose.local.yml exec postgres ls -la /var/lib/postgresql/data
   ```

2. Verify initialization scripts:
   ```bash
   docker-compose -f docker-compose.local.yml exec postgres ls -la /docker-entrypoint-initdb.d/
   ```

## Best Practices

### Development Workflow
1. Always run `make dev-local-setup` before first use
2. Use `make logs-local` to monitor service logs
3. Use `make health-local` to check service status
4. Use `make backup-local` regularly for data safety

### File Organization
1. Keep test data separate from production data
2. Use meaningful names for uploaded files
3. Regularly clean up temporary files
4. Document any custom scripts or configurations

### Performance Optimization
1. Use `.dockerignore` to exclude unnecessary files
2. Keep source code changes small and focused
3. Use development profiles for optional services
4. Monitor resource usage with `make monitor`

## Security Considerations

### File Permissions
- Application data directories are writable by the container user
- Configuration files are read-only to prevent accidental changes
- Database directories have restricted permissions

### Sensitive Data
- Never mount sensitive files like private keys
- Use environment variables for secrets
- Keep `.env.local` out of version control

### Network Security
- Services communicate through Docker networks
- Database ports are exposed only for development
- Admin tools are available only with specific profiles

## Integration with IDE

### VS Code
The `.vscode` directory is mounted read-only for configuration sharing:
- Debugger configurations
- Extension settings
- Workspace preferences

### Jupyter Notebooks
The `notebooks/` directory provides a workspace for:
- Data exploration
- Algorithm prototyping
- Interactive debugging

### Development Scripts
The `scripts/` directory is mounted for:
- Database management utilities
- Health check scripts
- Development automation tools