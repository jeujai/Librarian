# PostgreSQL 15 Configuration for Multimodal Librarian

This directory contains the PostgreSQL 15 configuration and management scripts for the Multimodal Librarian local development environment.

## Overview

The PostgreSQL setup includes:
- Comprehensive initialization scripts
- Performance-tuned configuration
- Health monitoring and maintenance functions
- Backup and restore capabilities
- Management utilities

## Directory Structure

```
database/postgresql/
├── README.md                    # This file
├── postgresql.conf              # Main PostgreSQL configuration
├── health_check.sql            # Health check queries
├── manage.sh                   # Database management script
├── backup.sh                   # Backup script
├── restore.sh                  # Restore script
└── init/                       # Initialization scripts
    ├── 01_extensions.sql       # PostgreSQL extensions
    ├── 02_users_and_permissions.sql  # User setup
    ├── 03_performance_tuning.sql     # Performance functions
    ├── 04_monitoring_setup.sql       # Monitoring views
    └── 05_maintenance_functions.sql  # Maintenance utilities
```

## Quick Start

### 1. Start PostgreSQL with Docker Compose

```bash
# Start all services including PostgreSQL
docker-compose -f docker-compose.local.yml up -d postgres

# Or start all services
make dev-local
```

### 2. Check Database Status

```bash
# Check if PostgreSQL is running and accessible
./database/postgresql/manage.sh status

# Run comprehensive health check
./database/postgresql/manage.sh health
```

### 3. Access Database

```bash
# Open PostgreSQL shell
./database/postgresql/manage.sh shell

# Or use psql directly
psql -h localhost -p 5432 -U ml_user -d multimodal_librarian
```

## Configuration Features

### Performance Optimization

The PostgreSQL configuration is optimized for local development:

- **Memory Settings**: 256MB shared_buffers, 1GB effective_cache_size
- **Connection Limits**: 100 max connections
- **WAL Configuration**: Optimized for development workloads
- **Autovacuum**: Enabled with appropriate thresholds
- **Statistics**: pg_stat_statements enabled for query analysis

### Extensions

The following PostgreSQL extensions are automatically installed:

- `uuid-ossp`: UUID generation functions
- `pg_trgm`: Trigram matching for full-text search
- `btree_gin`: GIN indexes for btree-equivalent operators
- `pg_stat_statements`: Query statistics collection
- `pgcrypto`: Cryptographic functions
- `citext`: Case-insensitive text type

### Monitoring

Built-in monitoring includes:

- **Health Checks**: Comprehensive database health monitoring
- **Performance Views**: Active connections, query statistics, table sizes
- **Maintenance Functions**: Automated cleanup and optimization

## Management Scripts

### Database Management (`manage.sh`)

```bash
# Show database status
./database/postgresql/manage.sh status

# Run health check
./database/postgresql/manage.sh health

# Run maintenance tasks
./database/postgresql/manage.sh maintenance

# Show table sizes
./database/postgresql/manage.sh tables

# Show active connections
./database/postgresql/manage.sh connections

# Analyze all tables
./database/postgresql/manage.sh analyze

# Vacuum all tables
./database/postgresql/manage.sh vacuum

# Reset database (DANGEROUS!)
./database/postgresql/manage.sh reset

# Open PostgreSQL shell
./database/postgresql/manage.sh shell
```

### Backup Management (`backup.sh`)

```bash
# Create full backup
./database/postgresql/backup.sh full

# Create schema-only backup
./database/postgresql/backup.sh schema

# Create data-only backup
./database/postgresql/backup.sh data

# Create compressed backup
./database/postgresql/backup.sh compressed

# Create all types of backups
./database/postgresql/backup.sh all

# Clean up old backups
./database/postgresql/backup.sh cleanup

# Show backup statistics
./database/postgresql/backup.sh stats
```

### Restore Management (`restore.sh`)

```bash
# List available backups
./database/postgresql/restore.sh list

# Restore from latest backup
./database/postgresql/restore.sh latest

# Restore schema from latest schema backup
./database/postgresql/restore.sh latest-schema

# Restore from specific file
./database/postgresql/restore.sh file /path/to/backup.sql
```

## Database Schema

The database includes the following main components:

### Core Tables

- `users`: User accounts and authentication
- `user_sessions`: Session management
- `documents`: Uploaded documents and files
- `conversation_threads`: Chat conversations
- `messages`: Individual chat messages
- `knowledge_chunks`: Processed document chunks for vector search

### Configuration Tables

- `domain_configurations`: Chunking framework configurations
- `performance_metrics`: System performance tracking
- `user_feedback`: User interaction feedback

### Audit and Export

- `audit.audit_log`: Security and compliance audit trail
- `export_history`: Document export tracking

### Monitoring Schemas

- `monitoring`: Database monitoring views and functions
- `maintenance`: Database maintenance utilities

## Health Monitoring

### Automated Health Checks

The PostgreSQL container includes automated health checks that verify:

- Database connectivity
- Query response time
- Active connection count
- Extension availability
- Basic functionality

### Manual Health Checks

```sql
-- Run comprehensive health check
\i /etc/postgresql/health_check.sql

-- Check monitoring functions
SELECT * FROM monitoring.health_check();

-- View database statistics
SELECT * FROM monitoring.database_stats;

-- Check table sizes
SELECT * FROM monitoring.get_table_sizes();
```

## Maintenance

### Automated Maintenance

The system includes automated maintenance functions:

```sql
-- Run routine maintenance
SELECT * FROM maintenance.routine_maintenance();

-- Clean up expired sessions
SELECT maintenance.cleanup_expired_sessions();

-- Clean up expired exports
SELECT maintenance.cleanup_expired_exports();

-- Update table statistics
SELECT maintenance.update_statistics();
```

### Manual Maintenance

```bash
# Run all maintenance tasks
./database/postgresql/manage.sh maintenance

# Analyze tables for better query planning
./database/postgresql/manage.sh analyze

# Vacuum tables to reclaim space
./database/postgresql/manage.sh vacuum
```

## Backup Strategy

### Automated Backups

Backups can be automated using cron jobs:

```bash
# Add to crontab for daily backups at 2 AM
0 2 * * * /path/to/database/postgresql/backup.sh compressed

# Weekly full backup on Sundays at 3 AM
0 3 * * 0 /path/to/database/postgresql/backup.sh all

# Monthly cleanup of old backups
0 4 1 * * /path/to/database/postgresql/backup.sh cleanup
```

### Backup Types

1. **Full Backup**: Complete database dump (schema + data)
2. **Schema Backup**: Database structure only
3. **Data Backup**: Data only (no schema)
4. **Compressed Backup**: Binary format with compression

## Troubleshooting

### Common Issues

1. **Connection Refused**
   ```bash
   # Check if PostgreSQL is running
   docker-compose -f docker-compose.local.yml ps postgres
   
   # Check logs
   docker-compose -f docker-compose.local.yml logs postgres
   ```

2. **Performance Issues**
   ```bash
   # Check active connections
   ./database/postgresql/manage.sh connections
   
   # Run maintenance
   ./database/postgresql/manage.sh maintenance
   ```

3. **Disk Space Issues**
   ```bash
   # Check table sizes
   ./database/postgresql/manage.sh tables
   
   # Vacuum to reclaim space
   ./database/postgresql/manage.sh vacuum
   ```

### Log Analysis

```bash
# View PostgreSQL logs
docker-compose -f docker-compose.local.yml logs -f postgres

# Check for slow queries (>1 second)
# These are logged automatically with current configuration
```

## Security Considerations

### Development Security

- Default passwords are used for local development
- SSL is disabled for simplicity
- Authentication is simplified for development

### Production Considerations

When moving to production:

1. Change all default passwords
2. Enable SSL/TLS encryption
3. Configure proper authentication methods
4. Set up connection pooling
5. Enable audit logging
6. Configure backup encryption

## Performance Tuning

### Current Settings

The configuration is optimized for development with:

- 256MB shared_buffers (suitable for 8GB+ systems)
- 1GB effective_cache_size
- Autovacuum enabled
- Query statistics collection enabled

### Monitoring Performance

```sql
-- View slow queries
SELECT * FROM pg_stat_statements 
WHERE mean_time > 1000 
ORDER BY mean_time DESC;

-- Check index usage
SELECT * FROM monitoring.index_usage 
WHERE idx_scan = 0;

-- Monitor table statistics
SELECT * FROM monitoring.table_stats;
```

## Integration with Application

The PostgreSQL setup integrates with the Multimodal Librarian application through:

1. **Database Factory**: Automatic client selection based on environment
2. **Connection Pooling**: Managed through application configuration
3. **Migration System**: Alembic-based database migrations
4. **Health Checks**: Application-level health monitoring

## Environment Variables

Key environment variables for PostgreSQL configuration:

```bash
# Connection settings
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=multimodal_librarian
POSTGRES_USER=ml_user
POSTGRES_PASSWORD=ml_password

# Backup settings
BACKUP_DIR=./backups/postgresql
```

## Support and Maintenance

For issues or questions:

1. Check the health status: `./database/postgresql/manage.sh health`
2. Review logs: `docker-compose logs postgres`
3. Run maintenance: `./database/postgresql/manage.sh maintenance`
4. Consult PostgreSQL documentation for advanced configuration

## Version Information

- **PostgreSQL Version**: 15-alpine
- **Configuration Version**: 1.0
- **Last Updated**: 2024
- **Compatibility**: Multimodal Librarian v1.0+