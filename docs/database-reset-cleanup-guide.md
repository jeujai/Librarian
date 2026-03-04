# Database Reset and Cleanup Guide

This guide covers the comprehensive database reset and cleanup functionality for the Multimodal Librarian application. These tools provide safe and efficient ways to manage database state during development and maintenance.

## Overview

The database reset and cleanup system provides:

- **Full database reset** - Complete reset of all databases
- **Selective reset** - Reset specific databases or tables
- **Data cleanup** - Remove old or unnecessary data without full reset
- **Backup integration** - Automatic backup creation before destructive operations
- **Environment awareness** - Works with both local and AWS environments
- **Safety features** - Confirmation prompts, dry run mode, and rollback capabilities

## Available Scripts

### 1. Unified Management Script

**`scripts/database-management.sh`** - Main entry point for all database operations

```bash
# Quick development reset
./scripts/database-management.sh dev-reset

# Full reset with backup
./scripts/database-management.sh reset-all --backup

# Check database health
./scripts/database-management.sh health

# Clean old data
./scripts/database-management.sh cleanup-age 30

# Show all available commands
./scripts/database-management.sh help
```

### 2. Reset Scripts

#### Full Database Reset
**`scripts/reset-all-databases.py`** - Reset all databases

```bash
# Reset all databases with confirmation
python scripts/reset-all-databases.py --all

# Reset specific databases
python scripts/reset-all-databases.py --databases postgresql,neo4j

# Force reset without confirmation (dangerous!)
python scripts/reset-all-databases.py --all --force

# Dry run to see what would be reset
python scripts/reset-all-databases.py --all --dry-run

# Reset with automatic backup
python scripts/reset-all-databases.py --all --backup
```

#### PostgreSQL-Specific Reset
**`scripts/reset-postgresql.py`** - Advanced PostgreSQL reset options

```bash
# Full PostgreSQL reset
python scripts/reset-postgresql.py --full

# Reset only data, keep schema
python scripts/reset-postgresql.py --data-only

# Reset specific tables
python scripts/reset-postgresql.py --tables users,sessions

# Reset with migrations
python scripts/reset-postgresql.py --full --migrate
```

#### Shell Wrapper
**`scripts/reset-all-databases.sh`** - Shell wrapper for easier usage

```bash
# Reset all databases
./scripts/reset-all-databases.sh all

# Reset with backup
./scripts/reset-all-databases.sh all --backup

# Reset specific database
./scripts/reset-all-databases.sh postgresql
```

### 3. Cleanup Scripts

#### Data Cleanup
**`scripts/cleanup-database-data.py`** - Selective data cleanup

```bash
# Clean data older than 30 days
python scripts/cleanup-database-data.py --age 30

# Clean when database exceeds size limit
python scripts/cleanup-database-data.py --max-size 1GB

# Clean specific data types
python scripts/cleanup-database-data.py --age 7 --types temp,cache,logs

# Clean specific databases
python scripts/cleanup-database-data.py --age 30 --databases postgresql,redis

# Dry run to see what would be cleaned
python scripts/cleanup-database-data.py --age 30 --dry-run
```

### 4. Validation Script

**`scripts/validate-reset-cleanup.py`** - Test reset and cleanup functionality

```bash
# Validate all functionality
python scripts/validate-reset-cleanup.py

# Skip specific tests
python scripts/validate-reset-cleanup.py --skip-reset --skip-cleanup

# Validate in specific environment
python scripts/validate-reset-cleanup.py --environment local
```

## Usage Examples

### Development Workflows

#### Quick Development Reset
```bash
# Reset all databases and seed with sample data
./scripts/database-management.sh dev-reset
```

#### Safe Production-like Reset
```bash
# Create backup, reset, and restore if needed
./scripts/database-management.sh backup
./scripts/database-management.sh reset-all --force
# If something goes wrong:
./scripts/database-management.sh restore
```

#### Selective Database Reset
```bash
# Reset only PostgreSQL with backup
python scripts/reset-postgresql.py --full --backup --migrate
```

### Maintenance Workflows

#### Regular Cleanup
```bash
# Clean data older than 30 days
./scripts/database-management.sh cleanup-age 30

# Clean temporary data daily
./scripts/database-management.sh cleanup-temp
```

#### Size Management
```bash
# Clean when databases exceed 1GB
./scripts/database-management.sh cleanup-size 1GB
```

#### Performance Optimization
```bash
# Optimize database performance
./scripts/database-management.sh optimize
```

### Testing and Validation

#### Pre-deployment Testing
```bash
# Validate reset functionality works
python scripts/validate-reset-cleanup.py

# Test specific environment
python scripts/validate-reset-cleanup.py --environment local
```

#### Health Monitoring
```bash
# Check database health
./scripts/database-management.sh health

# Get detailed status
./scripts/database-management.sh status
```

## Configuration

### Environment Variables

The scripts use these environment variables for database connections:

```bash
# Environment selection
export ML_ENVIRONMENT=local          # or 'aws'
export DATABASE_TYPE=local           # or 'aws'

# PostgreSQL
export POSTGRES_HOST=localhost
export POSTGRES_PORT=5432
export POSTGRES_DB=multimodal_librarian
export POSTGRES_USER=ml_user
export POSTGRES_PASSWORD=ml_password

# Neo4j
export NEO4J_HOST=localhost
export NEO4J_PORT=7687
export NEO4J_USER=neo4j
export NEO4J_PASSWORD=ml_password

# Milvus
export MILVUS_HOST=localhost
export MILVUS_PORT=19530

# Redis
export REDIS_HOST=localhost
export REDIS_PORT=6379

# Backup settings
export BACKUP_DIR=./backups
```

### Configuration Files

The scripts automatically detect and use configuration from:

- `.env.local` - Local development configuration
- Application configuration classes in `src/multimodal_librarian/config/`

## Safety Features

### Confirmation Prompts

All destructive operations require confirmation unless `--force` is used:

```
⚠️  DATABASE RESET CONFIRMATION
====================================
WARNING: This operation will permanently delete all data!

Environment: local
Databases to reset: postgresql, neo4j, milvus, redis

This action cannot be undone!

Are you sure you want to continue? (yes/no):
```

### Dry Run Mode

Use `--dry-run` to see what would be done without making changes:

```bash
python scripts/reset-all-databases.py --all --dry-run
```

### Automatic Backups

Use `--backup` to create backups before destructive operations:

```bash
python scripts/reset-all-databases.py --all --backup
```

### Environment Detection

Scripts automatically detect the environment and use appropriate database clients:

- **Local environment**: Uses Neo4j, Milvus, PostgreSQL, Redis
- **AWS environment**: Uses Neptune, OpenSearch, RDS, ElastiCache

## Error Handling

### Common Issues and Solutions

#### Database Connection Errors
```bash
# Check if services are running
./scripts/database-management.sh health

# Start local services
docker-compose -f docker-compose.local.yml up -d
```

#### Permission Errors
```bash
# Make scripts executable
chmod +x scripts/*.sh

# Check database permissions
./scripts/database-management.sh show-config
```

#### Python Import Errors
```bash
# Install dependencies
pip install -r requirements.txt
pip install -r requirements-dev.txt

# Check Python path
export PYTHONPATH="${PYTHONPATH}:$(pwd)/src"
```

### Recovery Procedures

#### Restore from Backup
```bash
# List available backups
./scripts/database-management.sh list-backups

# Restore from latest backup
./scripts/database-management.sh restore

# Restore specific database
./scripts/database-management.sh restore-single postgresql
```

#### Emergency Recovery
```bash
# Stop all operations
docker-compose -f docker-compose.local.yml down

# Restore from backup
./scripts/database-management.sh restore --force

# Restart services
docker-compose -f docker-compose.local.yml up -d
```

## Advanced Usage

### Custom Reset Operations

#### Reset Specific Tables
```python
# Using the PostgreSQL reset script
python scripts/reset-postgresql.py --tables users,sessions,temp_data
```

#### Reset with Custom Backup Directory
```bash
python scripts/reset-all-databases.py --all --backup --backup-dir /custom/backup/path
```

### Custom Cleanup Operations

#### Age-based Cleanup
```python
# Clean data older than specific days
python scripts/cleanup-database-data.py --age 7 --types temp,cache
python scripts/cleanup-database-data.py --age 30 --types logs,sessions
python scripts/cleanup-database-data.py --age 90 --types analytics
```

#### Size-based Cleanup
```python
# Clean when databases exceed limits
python scripts/cleanup-database-data.py --max-size 500MB --databases redis
python scripts/cleanup-database-data.py --max-size 2GB --databases postgresql
```

### Integration with CI/CD

#### Pre-deployment Reset
```bash
#!/bin/bash
# In CI/CD pipeline

# Validate environment
./scripts/database-management.sh health

# Reset test databases
./scripts/database-management.sh reset-all --force --environment local

# Seed with test data
./scripts/database-management.sh seed

# Run tests
pytest tests/
```

#### Scheduled Cleanup
```bash
#!/bin/bash
# In cron job

# Daily cleanup of temporary data
./scripts/database-management.sh cleanup-temp

# Weekly cleanup of old data
./scripts/database-management.sh cleanup-age 30

# Monthly optimization
./scripts/database-management.sh optimize
```

## Monitoring and Logging

### Log Files

Scripts create detailed logs in:
- Console output with colored messages
- Python logging to stderr
- Operation results in JSON format (when applicable)

### Health Monitoring

```bash
# Comprehensive health check
./scripts/database-management.sh health

# Detailed status with statistics
./scripts/database-management.sh status

# Validate functionality
python scripts/validate-reset-cleanup.py
```

### Performance Monitoring

```bash
# Database optimization
./scripts/database-management.sh optimize

# Check database sizes
./scripts/database-management.sh status
```

## Best Practices

### Development

1. **Always use dry run first** for new operations
2. **Create backups** before major resets
3. **Use dev-reset** for quick development cycles
4. **Validate functionality** after changes

### Production

1. **Never use --force** in production
2. **Always create backups** before operations
3. **Test in staging** environment first
4. **Monitor operations** closely

### Maintenance

1. **Schedule regular cleanup** of old data
2. **Monitor database sizes** and performance
3. **Keep backups** for recovery
4. **Document custom procedures**

## Troubleshooting

### Debug Mode

Enable verbose logging for troubleshooting:

```bash
python scripts/reset-all-databases.py --all --verbose
./scripts/database-management.sh reset-all --verbose
```

### Common Solutions

#### Services Not Running
```bash
# Check Docker services
docker-compose -f docker-compose.local.yml ps

# Restart services
docker-compose -f docker-compose.local.yml restart
```

#### Configuration Issues
```bash
# Show current configuration
./scripts/database-management.sh show-config

# Validate environment
python scripts/validate-reset-cleanup.py --environment local
```

#### Permission Issues
```bash
# Fix script permissions
find scripts/ -name "*.sh" -exec chmod +x {} \;

# Check database permissions
./scripts/database-management.sh health
```

For additional help, see the individual script help:
```bash
python scripts/reset-all-databases.py --help
python scripts/cleanup-database-data.py --help
./scripts/database-management.sh help
```