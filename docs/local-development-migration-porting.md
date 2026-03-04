# Migration Porting for Local Development

This document describes the migration porting system that adapts existing AWS-focused database migrations to work with the local PostgreSQL development environment.

## Overview

The migration porting system ensures that all existing database migrations designed for AWS production environments can be seamlessly used in local development with PostgreSQL, Neo4j, and Milvus.

## Architecture

### Components

1. **LocalMigrationManager** - Core migration porting logic
2. **SQL Porting Scripts** - Database-specific migration adaptations
3. **Migration Compatibility Layer** - Bridges between old and new schemas
4. **CLI Tools** - Command-line interface for migration management

### Migration Flow

```
Existing AWS Migrations → Porting Analysis → Local Adaptation → Verification
```

## Migration Porting Process

### 1. Automatic Detection

The system automatically detects existing migrations in:
- `src/multimodal_librarian/database/migrations/`
- Individual migration files (`.py` format)
- SQL migration scripts (`.sql` format)

### 2. Schema Adaptation

Each migration is analyzed and adapted for local environment:

#### Authentication Tables
- `users` - User accounts and authentication
- `api_keys` - API key management
- `audit_logs` - Security audit logging
- `privacy_requests` - GDPR compliance
- `security_incidents` - Security event tracking

#### Application Tables
- `documents` - Document upload and management
- `document_chunks` - Processed document content
- `chat_messages` - Conversation history
- `knowledge_chunks` - Vector database metadata

#### ML Training Tables
- `knowledge_sources` - Unified content sources
- `content_profiles` - Document analysis results
- `bridge_chunks` - Gap-filling content
- `training_sessions` - ML training metadata

### 3. Compatibility Layer

Creates compatibility views and functions:
- `documents_compat` - Bridges old/new document schemas
- `chat_messages_compat` - Maintains chat message compatibility
- Migration tracking functions
- Data migration utilities

## Usage

### Command Line Interface

```bash
# Port all existing migrations
make db-port-migrations

# Check porting status
make db-migration-status

# Verify porting results
make db-migration-verify

# Reset migration state (development only)
make db-migration-reset
```

### Python API

```python
from src.multimodal_librarian.database.local_migration_manager import (
    LocalMigrationManager,
    port_migrations_to_local,
    get_local_migration_status
)

# Port migrations programmatically
success = await port_migrations_to_local()

# Get detailed status
status = await get_local_migration_status()
print(f"Porting complete: {status['porting_complete']}")
print(f"Applied migrations: {len(status['migration_history'])}")
```

### Direct Script Usage

```bash
# Port migrations with verbose output
python scripts/port-migrations-to-local.py port --verbose

# Get detailed status
python scripts/port-migrations-to-local.py status

# Verify porting
python scripts/port-migrations-to-local.py verify

# Reset migration state
python scripts/port-migrations-to-local.py reset --force
```

## Migration Tracking

### Migration History

The system tracks all applied migrations in `public.migration_history`:

```sql
SELECT migration_name, applied_at, success 
FROM public.migration_history 
ORDER BY applied_at DESC;
```

### Status Functions

Built-in PostgreSQL functions for migration management:

```sql
-- Check if migration was applied
SELECT is_migration_applied('migration_name');

-- Record migration application
SELECT record_migration('migration_name', 'checksum', true);
```

## Troubleshooting

### Common Issues

#### 1. Migration Already Applied

```
Error: Migration already applied
```

**Solution**: Use `--force` flag to re-run porting:
```bash
python scripts/port-migrations-to-local.py port --force
```

#### 2. Database Connection Issues

```
Error: Could not connect to database
```

**Solutions**:
- Ensure PostgreSQL is running: `make status-local`
- Check database credentials in `.env.local`
- Verify network connectivity: `make health-postgres`

#### 3. Missing Tables After Porting

```
Error: Required table missing after porting
```

**Solutions**:
- Check migration logs for errors
- Verify database permissions
- Run verification: `make db-migration-verify`

#### 4. SQL Parsing Errors

```
Error: Failed to parse SQL statement
```

**Solutions**:
- Check for syntax errors in migration files
- Ensure proper statement termination (semicolons)
- Review function and DO block formatting

### Debugging

#### Enable Verbose Logging

```bash
python scripts/port-migrations-to-local.py port --verbose
```

#### Check Migration Status

```bash
# Get comprehensive status
make db-migration-status

# Check specific table counts
python scripts/check-all-database-health.py --services postgresql
```

#### Manual Verification

```sql
-- Check schema exists
SELECT schema_name FROM information_schema.schemata 
WHERE schema_name = 'multimodal_librarian';

-- List all tables
SELECT table_name FROM information_schema.tables 
WHERE table_schema = 'multimodal_librarian';

-- Check migration history
SELECT * FROM public.migration_history 
WHERE success = false;
```

## Development Workflow

### Initial Setup

1. Start local development environment:
   ```bash
   make dev-local
   ```

2. Port existing migrations:
   ```bash
   make db-port-migrations
   ```

3. Verify porting success:
   ```bash
   make db-migration-verify
   ```

### Adding New Migrations

1. Create migration in `src/multimodal_librarian/database/migrations/`
2. Test with local environment
3. Add porting logic if needed
4. Update compatibility layer

### Testing Migration Changes

1. Reset migration state:
   ```bash
   make db-migration-reset
   ```

2. Re-run porting:
   ```bash
   make db-port-migrations
   ```

3. Verify results:
   ```bash
   make db-migration-verify
   ```

## Best Practices

### Migration Design

1. **Environment Agnostic**: Write migrations that work in both local and AWS environments
2. **Idempotent Operations**: Use `IF NOT EXISTS` and similar constructs
3. **Proper Error Handling**: Include rollback procedures
4. **Documentation**: Comment complex migration logic

### Local Development

1. **Regular Porting**: Re-run porting after pulling new migrations
2. **Status Monitoring**: Check migration status regularly
3. **Clean State**: Reset migrations when switching branches
4. **Backup Data**: Backup local data before major migrations

### Testing

1. **Unit Tests**: Test migration logic in isolation
2. **Integration Tests**: Test full porting process
3. **Verification Tests**: Ensure data integrity after porting
4. **Performance Tests**: Monitor migration performance

## Configuration

### Environment Variables

```bash
# Database connection
ML_POSTGRES_HOST=localhost
ML_POSTGRES_PORT=5432
ML_POSTGRES_DB=multimodal_librarian
ML_POSTGRES_USER=ml_user
ML_POSTGRES_PASSWORD=ml_password

# Migration settings
ML_MIGRATION_TIMEOUT=300
ML_MIGRATION_RETRY_COUNT=3
ML_MIGRATION_BATCH_SIZE=100
```

### Docker Compose Configuration

The migration porting system integrates with the local Docker Compose setup:

```yaml
services:
  postgres:
    volumes:
      - ./database/postgresql/init:/docker-entrypoint-initdb.d
    environment:
      - POSTGRES_DB=multimodal_librarian
      - POSTGRES_USER=ml_user
      - POSTGRES_PASSWORD=ml_password
```

## Security Considerations

### Data Protection

1. **No Production Data**: Never use production data in local development
2. **Secure Credentials**: Use strong passwords for local databases
3. **Network Isolation**: Keep local services isolated from production

### Migration Safety

1. **Backup Before Migration**: Always backup before running migrations
2. **Test Migrations**: Test all migrations in development first
3. **Rollback Procedures**: Ensure rollback procedures are available
4. **Access Control**: Limit migration execution to authorized users

## Performance Optimization

### Migration Speed

1. **Batch Processing**: Process migrations in batches
2. **Parallel Execution**: Run independent migrations in parallel
3. **Index Management**: Drop/recreate indexes for large data migrations
4. **Connection Pooling**: Use connection pooling for better performance

### Resource Usage

1. **Memory Management**: Monitor memory usage during migrations
2. **Disk Space**: Ensure sufficient disk space for migrations
3. **CPU Usage**: Monitor CPU usage and adjust batch sizes
4. **Network Bandwidth**: Consider network impact for large migrations

## Monitoring and Alerting

### Migration Monitoring

1. **Progress Tracking**: Monitor migration progress
2. **Error Detection**: Detect and alert on migration errors
3. **Performance Metrics**: Track migration performance
4. **Resource Usage**: Monitor resource consumption

### Health Checks

```bash
# Check migration health
make db-migration-status

# Verify database health
make health-postgres

# Check overall system health
make health-local
```

## Future Enhancements

### Planned Features

1. **Automatic Migration Detection**: Auto-detect new migrations
2. **Migration Rollback**: Automated rollback procedures
3. **Performance Optimization**: Improved migration performance
4. **Enhanced Monitoring**: Better monitoring and alerting

### Roadmap

- **Phase 1**: Basic migration porting (✅ Complete)
- **Phase 2**: Enhanced compatibility layer
- **Phase 3**: Automated migration management
- **Phase 4**: Advanced monitoring and optimization

## Support

### Getting Help

1. **Documentation**: Check this documentation first
2. **Troubleshooting**: Follow troubleshooting guide
3. **Logs**: Check migration logs for errors
4. **Community**: Ask questions in development channels

### Reporting Issues

When reporting migration issues, include:

1. **Error Messages**: Full error messages and stack traces
2. **Migration Status**: Output of `make db-migration-status`
3. **Environment Info**: Local environment configuration
4. **Steps to Reproduce**: Clear steps to reproduce the issue
5. **Expected Behavior**: What you expected to happen

## References

- [Local Development Setup](local-development-setup.md)
- [Database Configuration](database-configuration.md)
- [Docker Compose Guide](docker-compose-guide.md)
- [Troubleshooting Guide](troubleshooting-guide.md)