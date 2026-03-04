# Resource Cleanup Automation

This document describes the automated resource cleanup system for the Multimodal Librarian local development environment.

## Overview

The resource cleanup automation system provides automated management of local development resources including:

- Docker containers, images, volumes, and networks
- Application-generated files (logs, uploads, cache)
- Test artifacts and temporary files
- Python cache files and build artifacts
- Old backup files and log files

## Components

### 1. Manual Cleanup Script (`scripts/cleanup-local-resources.py`)

A comprehensive Python script for on-demand resource cleanup.

#### Features

- **Dry Run Mode**: Preview what would be cleaned without making changes
- **Selective Cleanup**: Clean specific resource types (containers, files, etc.)
- **Force Mode**: Skip confirmation prompts for automated use
- **Resource Reporting**: Generate detailed resource usage reports
- **Configurable Retention**: Customizable retention periods for logs and backups

#### Usage

```bash
# Basic cleanup (interactive)
python scripts/cleanup-local-resources.py

# Dry run to see what would be cleaned
python scripts/cleanup-local-resources.py --dry-run

# Force cleanup without prompts
python scripts/cleanup-local-resources.py --force

# Clean only Docker containers
python scripts/cleanup-local-resources.py --containers-only

# Clean only application files
python scripts/cleanup-local-resources.py --files-only

# Include database volumes (DESTRUCTIVE)
python scripts/cleanup-local-resources.py --include-data

# Generate resource usage report
python scripts/cleanup-local-resources.py --report-only
```

#### Makefile Targets

```bash
# Basic cleanup
make cleanup-local

# Dry run
make cleanup-local-dry-run

# Force cleanup
make cleanup-local-force

# Emergency cleanup
make cleanup-emergency

# Generate report
make cleanup-report
```

### 2. Scheduled Cleanup Service (`scripts/scheduled-cleanup.py`)

A background service that runs automated cleanup tasks on a schedule.

#### Features

- **Configurable Schedules**: Daily, weekly, and monthly cleanup tasks
- **Disk Usage Monitoring**: Automatic emergency cleanup when disk usage is high
- **Status Reporting**: Regular resource usage reports
- **Alert System**: Notifications when cleanup fails or disk usage is high
- **Graceful Error Handling**: Continues operation even if individual tasks fail

#### Configuration

The service is configured via `config/cleanup-config.json`:

```json
{
  "daily_cleanup": {
    "enabled": true,
    "time": "02:00",
    "tasks": ["logs", "temp_files", "test_artifacts"]
  },
  "weekly_cleanup": {
    "enabled": true,
    "day": "sunday",
    "time": "03:00",
    "tasks": ["docker_images", "old_backups", "cache_files"]
  },
  "thresholds": {
    "log_retention_days": 7,
    "backup_retention_days": 30,
    "max_disk_usage_gb": 10
  }
}
```

#### Usage

```bash
# Start as daemon
python scripts/scheduled-cleanup.py --daemon

# Test mode (run once and exit)
python scripts/scheduled-cleanup.py --test

# Interactive mode
python scripts/scheduled-cleanup.py
```

#### Makefile Targets

```bash
# Start scheduled cleanup service
make cleanup-scheduled-start

# Test scheduled cleanup
make cleanup-scheduled-test

# View configuration
make cleanup-scheduled-config
```

### 3. System Service Installation

#### Systemd Service (Linux)

Install as a systemd service for automatic startup:

```bash
# Install and start service
./scripts/install-cleanup-service.sh install

# Check service status
./scripts/install-cleanup-service.sh status

# View service logs
./scripts/install-cleanup-service.sh logs

# Uninstall service
./scripts/install-cleanup-service.sh uninstall
```

#### Cron-based Setup (macOS/Unix)

For systems without systemd, use cron-based scheduling:

```bash
# Install cron jobs
./scripts/setup-cron-cleanup.sh install

# Check status
./scripts/setup-cron-cleanup.sh status

# View logs
./scripts/setup-cron-cleanup.sh logs

# Uninstall
./scripts/setup-cron-cleanup.sh uninstall
```

## Cleanup Categories

### 1. Docker Resources

- **Containers**: Stops and removes development containers
- **Images**: Removes dangling and unused images
- **Volumes**: Removes unused volumes (with confirmation)
- **Networks**: Removes unused networks

### 2. Application Files

- **Uploads**: Temporary file uploads (`uploads/`)
- **Logs**: Application log files (`logs/`)
- **Cache**: Application cache files (`cache/`)
- **Test Uploads**: Test file uploads (`test_uploads/`)

### 3. Development Artifacts

- **Python Cache**: `__pycache__` directories and `.pyc` files
- **Test Cache**: `.pytest_cache` directories
- **Coverage Reports**: `htmlcov/` and `.coverage` files
- **Build Artifacts**: `build/`, `dist/`, `.egg-info/` directories

### 4. Log Files

- **Application Logs**: Configurable retention period (default: 7 days)
- **System Logs**: Cleanup service logs
- **Monitoring Logs**: Performance and health check logs

### 5. Backup Files

- **Database Backups**: Configurable retention period (default: 30 days)
- **Configuration Backups**: Old configuration snapshots
- **Log Backups**: Archived log files

## Safety Features

### 1. Confirmation Prompts

Interactive mode asks for confirmation before destructive operations:

```
Remove 3 volumes? This will delete all database data! (y/N):
```

### 2. Dry Run Mode

Preview mode shows what would be cleaned without making changes:

```
[DRY RUN] Would execute: docker volume rm volume1 volume2 volume3
[DRY RUN] Would remove directory: /path/to/uploads
```

### 3. Preserve Patterns

Important files are automatically preserved:

- Configuration files (`.env*`, `docker-compose*.yml`)
- Source code and documentation
- Requirements and project files
- Active database files

### 4. Backup Before Delete

Critical files are backed up before deletion:

- Database backups
- Important log files
- Configuration snapshots

## Monitoring and Alerting

### 1. Resource Usage Reports

Regular reports include:

- Docker resource usage (containers, images, volumes)
- Disk usage by category
- Cleanup operation results
- Performance metrics

### 2. Disk Usage Monitoring

Automatic monitoring with configurable thresholds:

- **Warning Level**: 8GB project disk usage
- **Emergency Level**: 10GB project disk usage
- **Actions**: Automatic emergency cleanup, alerts

### 3. Alert System

Configurable notifications for:

- Cleanup operation failures
- High disk usage warnings
- Service health issues
- Configuration problems

## Configuration Options

### Cleanup Thresholds

```json
{
  "thresholds": {
    "log_retention_days": 7,
    "backup_retention_days": 30,
    "temp_file_retention_hours": 24,
    "max_disk_usage_gb": 10,
    "emergency_cleanup_threshold_gb": 15
  }
}
```

### Cleanup Rules

```json
{
  "cleanup_rules": {
    "preserve_patterns": [
      "*.env*",
      "docker-compose*.yml",
      "requirements*.txt"
    ],
    "aggressive_cleanup_patterns": [
      "**/__pycache__/**",
      "**/*.pyc",
      "**/.pytest_cache/**"
    ]
  }
}
```

### Notification Settings

```json
{
  "notifications": {
    "enabled": true,
    "methods": {
      "file": {
        "enabled": true,
        "path": "logs/cleanup-alerts.log"
      },
      "email": {
        "enabled": false,
        "smtp_server": "localhost",
        "to_addresses": ["admin@localhost"]
      }
    }
  }
}
```

## Troubleshooting

### Common Issues

#### 1. Permission Errors

```bash
# Fix file permissions
sudo chown -R $USER:$USER /path/to/project
chmod -R u+w /path/to/project
```

#### 2. Docker Permission Issues

```bash
# Add user to docker group
sudo usermod -aG docker $USER
# Logout and login again
```

#### 3. Service Won't Start

```bash
# Check service logs
sudo journalctl -u multimodal-librarian-cleanup -f

# Check Python dependencies
python3 -c "import schedule; print('OK')"
```

#### 4. High Disk Usage Persists

```bash
# Manual emergency cleanup
make cleanup-emergency

# Check for large files
du -h . | sort -hr | head -20

# Check Docker system usage
docker system df
```

### Log Files

- **Cleanup Logs**: `logs/cleanup.log`
- **Service Logs**: `logs/scheduled-cleanup.log`
- **Alert Logs**: `logs/cleanup-alerts.log`
- **System Logs**: `journalctl -u multimodal-librarian-cleanup`

### Debug Mode

Enable debug logging:

```bash
# Set environment variable
export ML_CLEANUP_DEBUG=1

# Run with verbose output
python scripts/cleanup-local-resources.py --dry-run
```

## Best Practices

### 1. Regular Monitoring

- Check cleanup logs weekly
- Monitor disk usage trends
- Review resource usage reports

### 2. Configuration Management

- Keep cleanup configuration in version control
- Test configuration changes in development
- Document custom retention policies

### 3. Backup Strategy

- Ensure important data is backed up before cleanup
- Test backup restoration procedures
- Monitor backup file sizes and retention

### 4. Performance Optimization

- Schedule intensive cleanup during off-hours
- Use incremental cleanup for large datasets
- Monitor cleanup operation performance

## Integration with Development Workflow

### 1. Pre-commit Hooks

Add cleanup checks to pre-commit hooks:

```bash
# .pre-commit-config.yaml
- repo: local
  hooks:
    - id: cleanup-check
      name: Check resource usage
      entry: python scripts/cleanup-local-resources.py --report-only
      language: system
      pass_filenames: false
```

### 2. CI/CD Integration

Include cleanup in CI/CD pipelines:

```yaml
# .github/workflows/cleanup.yml
- name: Cleanup resources
  run: |
    python scripts/cleanup-local-resources.py --force --files-only
```

### 3. Development Scripts

Integrate with development scripts:

```bash
# In Makefile
dev-clean: cleanup-local-force dev-local
	@echo "Started clean development environment"
```

## Security Considerations

### 1. File Permissions

- Cleanup scripts run with user permissions
- No sudo required for normal operations
- Sensitive files are preserved by default

### 2. Data Protection

- Database volumes require explicit confirmation
- Important files are backed up before deletion
- Dry run mode for testing changes

### 3. Service Security

- Systemd service runs with restricted permissions
- No network access required
- Logs contain no sensitive information

## Performance Impact

### 1. Resource Usage

- Minimal CPU usage during normal operation
- I/O intensive during cleanup operations
- Memory usage scales with project size

### 2. Optimization

- Cleanup operations run during off-hours
- Incremental cleanup reduces impact
- Configurable operation timeouts

### 3. Monitoring

- Track cleanup operation duration
- Monitor system resource usage
- Alert on performance degradation

## Future Enhancements

### Planned Features

1. **Web Dashboard**: Browser-based monitoring and control
2. **Advanced Scheduling**: More flexible scheduling options
3. **Cloud Integration**: Backup to cloud storage
4. **Machine Learning**: Predictive cleanup based on usage patterns
5. **Multi-Project Support**: Manage multiple development environments

### Contributing

To contribute to the cleanup automation system:

1. Follow the existing code style and patterns
2. Add comprehensive tests for new features
3. Update documentation for any changes
4. Test with different operating systems and configurations

## Support

For issues with the resource cleanup automation:

1. Check the troubleshooting section above
2. Review log files for error messages
3. Test with dry run mode first
4. Create an issue with detailed information about your environment