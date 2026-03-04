# Hot Reload Development Guide

This guide explains how to use the enhanced hot reload functionality for local development of the Multimodal Librarian application.

## Overview

The hot reload system provides automatic server restart when files change, making development faster and more efficient. It includes intelligent file watching, graceful restarts, and real-time feedback.

## Features

### 🔥 Enhanced Hot Reload
- **Automatic restart** on Python file changes
- **Configuration monitoring** for `.env.local` and `pyproject.toml` changes
- **Intelligent exclusions** for cache and temporary files
- **Real-time feedback** on file changes
- **Graceful restart** with minimal downtime

### 📁 File Watching
- **Python files** (`.py`) - Core application code
- **Configuration files** (`.yaml`, `.yml`, `.json`, `.toml`) - Settings and config
- **Environment files** (`.env.local`) - Environment variables
- **Exclusions** - Automatically excludes cache files, logs, and temporary files

### 🚀 Development Optimizations
- **Fast startup** with progressive loading
- **Persistent volumes** for data retention
- **Cache optimization** for faster rebuilds
- **Resource monitoring** and management

## Quick Start

### 1. Setup Development Environment

```bash
# Start hot reload development environment
make dev-hot-reload
```

This command will:
- Create all necessary directories
- Copy `.env.local.example` to `.env.local` (if not exists)
- Start all database services
- Start the application with hot reload enabled
- Wait for all services to be ready

### 2. Access the Application

Once started, you can access:
- **Application**: http://localhost:8000
- **API Documentation**: http://localhost:8000/docs
- **Neo4j Browser**: http://localhost:7474 (neo4j/ml_password)
- **pgAdmin**: http://localhost:5050 (admin@multimodal-librarian.local/admin)
- **Milvus Admin**: http://localhost:3000
- **Redis Commander**: http://localhost:8081

### 3. Start Developing

Edit any Python file in the `src/` directory and watch the server automatically restart:

```bash
# Edit a file
echo "# Hot reload test" >> src/multimodal_librarian/main.py

# Watch the logs to see the restart
make logs-hot-reload
```

## Available Commands

### Development Commands

```bash
# Start hot reload development
make dev-hot-reload

# View application logs
make logs-hot-reload

# Restart just the application
make restart-app

# Open shell in app container
make shell-hot-reload

# Watch file changes (debugging)
make watch-files

# Stop all services
make down
```

### Service Management

```bash
# Check service status
make status-local

# Check service health
make health-local

# Wait for services to be ready
make wait-for-services

# Restart all services
make restart-local
```

### Database Management

```bash
# Run database migrations
make db-migrate-local

# Seed databases with test data
make db-seed-local

# Reset databases (WARNING: deletes all data)
make db-reset-local

# Backup local databases
make backup-local
```

## Configuration

### Environment Variables

The hot reload system is configured through environment variables in `.env.local`:

```bash
# Hot reload configuration
ENABLE_HOT_RELOAD=true
WATCHDOG_ENABLED=true
RELOAD_DIRS=/app/src
RELOAD_INCLUDES=*.py,*.yaml,*.yml,*.json,*.toml
RELOAD_EXCLUDES=__pycache__,*.pyc,*.pyo,*.pyd,.git
UVICORN_RELOAD=true
UVICORN_RELOAD_DELAY=1
UVICORN_USE_COLORS=true
UVICORN_ACCESS_LOG=true

# File watching settings
WATCH_POLL_INTERVAL=1.0
WATCH_RECURSIVE=true
DEBOUNCE_DELAY=1.0
```

### Docker Compose Configuration

The `docker-compose.local.yml` file includes volume mounts for hot reload:

```yaml
volumes:
  # Source code mounts for hot reload
  - ./src:/app/src:rw
  - ./pyproject.toml:/app/pyproject.toml:ro
  - ./.env.local:/app/.env.local:ro
  
  # Application data directories
  - ./uploads:/app/uploads:rw
  - ./media:/app/media:rw
  - ./exports:/app/exports:rw
  - ./logs:/app/logs:rw
```

## File Watching Details

### Monitored Files

The hot reload system monitors these file types:
- **Python files** (`.py`) - Application code
- **YAML files** (`.yaml`, `.yml`) - Configuration files
- **JSON files** (`.json`) - Configuration and data files
- **TOML files** (`.toml`) - Project configuration
- **Environment files** (`.env.local`) - Environment variables

### Excluded Files

These files and directories are automatically excluded:
- **Cache directories** (`__pycache__`, `.pytest_cache`, `.mypy_cache`)
- **Compiled Python** (`.pyc`, `.pyo`, `.pyd`)
- **Version control** (`.git`)
- **Log files** (`.log`)
- **Temporary files** (`.tmp`, `.DS_Store`, `Thumbs.db`)

### Debouncing

The system includes debouncing to prevent multiple restarts for rapid file changes:
- **Debounce delay**: 1 second (configurable)
- **Intelligent grouping** of related changes
- **Graceful restart** with proper cleanup

## Troubleshooting

### Common Issues

#### 1. Hot Reload Not Working

**Symptoms**: Files change but server doesn't restart

**Solutions**:
```bash
# Check if hot reload is enabled
grep ENABLE_HOT_RELOAD .env.local

# Check container logs
make logs-hot-reload

# Restart the application container
make restart-app
```

#### 2. Services Not Starting

**Symptoms**: Services fail to start or become unhealthy

**Solutions**:
```bash
# Check service status
make status-local

# Check service health
make health-local

# View all service logs
docker-compose -f docker-compose.local.yml logs

# Reset and restart
make down
make dev-hot-reload
```

#### 3. File Changes Not Detected

**Symptoms**: File changes don't trigger restart

**Solutions**:
```bash
# Check file permissions
ls -la src/

# Check if files are properly mounted
make shell-hot-reload
ls -la /app/src/

# Watch file changes manually
make watch-files
```

#### 4. Slow Restart Times

**Symptoms**: Server takes too long to restart

**Solutions**:
```bash
# Check resource usage
make monitor

# Optimize Docker resources
# Edit docker-compose.local.yml resource limits

# Clear caches
docker system prune -f
```

### Debug Mode

Enable verbose logging for debugging:

```bash
# Set debug environment variables
export DEBUG=true
export LOG_LEVEL=DEBUG

# Start with verbose output
make dev-hot-reload
```

### Manual Hot Reload

If automatic hot reload isn't working, you can manually restart:

```bash
# Restart just the application
make restart-app

# Or restart all services
make restart-local
```

## Advanced Configuration

### Custom File Patterns

You can customize which files trigger hot reload by editing `.env.local`:

```bash
# Add custom file extensions
RELOAD_INCLUDES=*.py,*.yaml,*.yml,*.json,*.toml,*.sql,*.md

# Add custom exclusions
RELOAD_EXCLUDES=__pycache__,*.pyc,*.pyo,*.pyd,.git,*.log,test_*
```

### Performance Tuning

Optimize hot reload performance:

```bash
# Reduce debounce delay for faster restarts
DEBOUNCE_DELAY=0.5

# Increase poll interval to reduce CPU usage
WATCH_POLL_INTERVAL=2.0

# Disable access logs for better performance
UVICORN_ACCESS_LOG=false
```

### Development Profiles

Use Docker Compose profiles to control which services start:

```bash
# Start with admin tools
docker-compose -f docker-compose.local.yml --profile admin-tools up -d

# Start with monitoring
docker-compose -f docker-compose.local.yml --profile monitoring up -d

# Start with all features
docker-compose -f docker-compose.local.yml --profile admin-tools --profile monitoring up -d
```

## Best Practices

### 1. File Organization

- Keep source code in `src/` directory
- Use meaningful file and directory names
- Organize code into logical modules
- Avoid deeply nested directory structures

### 2. Configuration Management

- Use `.env.local` for local development settings
- Never commit `.env.local` to version control
- Document all environment variables
- Use sensible defaults for development

### 3. Development Workflow

- Start with `make dev-hot-reload`
- Use `make logs-hot-reload` to monitor changes
- Test changes immediately after editing
- Use `make health-local` to verify service status

### 4. Performance Optimization

- Use volume mounts for source code
- Enable caching for dependencies
- Monitor resource usage with `make monitor`
- Clean up unused Docker resources regularly

### 5. Debugging

- Enable debug logging when needed
- Use `make shell-hot-reload` for container debugging
- Monitor file changes with `make watch-files`
- Check service health regularly

## Integration with IDEs

### VS Code

Add these settings to `.vscode/settings.json`:

```json
{
  "python.defaultInterpreterPath": "./venv/bin/python",
  "python.terminal.activateEnvironment": true,
  "files.watcherExclude": {
    "**/data/**": true,
    "**/cache/**": true,
    "**/logs/**": true,
    "**/__pycache__/**": true
  }
}
```

### PyCharm

Configure PyCharm for hot reload development:
1. Set Python interpreter to project virtual environment
2. Configure file watchers to exclude cache directories
3. Enable automatic upload for remote development
4. Configure Docker integration for container debugging

## Conclusion

The hot reload system provides a powerful development experience with automatic restarts, intelligent file watching, and comprehensive tooling. Use the provided commands and configuration options to customize the system for your development workflow.

For more information, see:
- [Local Development Setup](local-development-setup.md)
- [Docker Compose Configuration](docker-compose-local.yml)
- [Environment Variables](.env.local.example)
- [Makefile Targets](../Makefile)