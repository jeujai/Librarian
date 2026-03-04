# PostgreSQL Initialization Scripts

This directory contains the PostgreSQL initialization scripts for the Multimodal Librarian local development environment. These scripts are executed automatically when the PostgreSQL container starts for the first time.

## Execution Order

The scripts are executed in alphabetical order by PostgreSQL's `docker-entrypoint-initdb.d` mechanism:

1. **01_extensions.sql** - Install required PostgreSQL extensions
2. **02_users_and_permissions.sql** - Create database users and set permissions
3. **03_performance_tuning.sql** - Configure performance settings and functions
4. **04_monitoring_setup.sql** - Set up monitoring views and functions
5. **05_maintenance_functions.sql** - Create maintenance and utility functions
6. **06_application_schema.sql** - Create main application database schema
7. **07_migration_compatibility.sql** - Set up migration compatibility layer

## Script Details

### 01_extensions.sql
Installs essential PostgreSQL extensions:
- `uuid-ossp` - UUID generation functions
- `pg_trgm` - Trigram matching for full-text search
- `btree_gin` - GIN indexes for btree-equivalent operators
- `pg_stat_statements` - Query statistics collection
- `pgcrypto` - Cryptographic functions
- `citext` - Case-insensitive text type

### 02_users_and_permissions.sql
Creates database users with appropriate permissions:
- `ml_app_user` - Main application user with full access
- `ml_readonly` - Read-only user for reporting and monitoring
- `ml_backup` - Backup user with necessary permissions

### 03_performance_tuning.sql
Sets up performance optimization:
- Performance monitoring functions
- Table analysis utilities
- Vacuum and maintenance functions
- Configuration logging

### 04_monitoring_setup.sql
Creates monitoring infrastructure:
- `monitoring` schema with views and functions
- Connection monitoring views
- Database statistics views
- Table and index usage views
- Health check functions

### 05_maintenance_functions.sql
Provides maintenance utilities:
- `maintenance` schema with utility functions
- Session cleanup functions
- Export cleanup functions
- Audit log cleanup functions
- Routine maintenance procedures

### 06_application_schema.sql
Creates the main application database schema:
- `multimodal_librarian` schema for application tables
- `audit` schema for audit logging
- Core application tables (users, documents, conversations, etc.)
- Indexes for performance
- Triggers for automatic timestamp updates
- Default admin user creation

### 07_migration_compatibility.sql
Ensures compatibility with existing migrations:
- Migration tracking tables
- Compatibility functions for existing code
- Data migration utilities
- Bridge views between old and new schemas

## Database Schema Overview

### Core Tables

#### multimodal_librarian.users
User accounts and authentication data with security features like failed login tracking and account locking.

#### multimodal_librarian.documents
Uploaded documents and files with processing status tracking and metadata storage.

#### multimodal_librarian.conversation_threads
Chat conversation threads with archiving and metadata support.

#### multimodal_librarian.messages
Individual messages within conversations with multimedia content support.

#### multimodal_librarian.knowledge_chunks
Processed document chunks for vector search with deduplication and metadata.

#### multimodal_librarian.domain_configurations
Chunking framework configurations with versioning and performance tracking.

### Audit and Compliance

#### audit.audit_log
Comprehensive audit logging for all system operations with security event tracking.

### Monitoring and Maintenance

#### monitoring schema
Views and functions for database monitoring, performance tracking, and health checks.

#### maintenance schema
Utility functions for database maintenance, cleanup operations, and routine tasks.

## Environment Variables

The initialization scripts use these environment variables:

- `POSTGRES_DB` - Database name (default: multimodal_librarian)
- `POSTGRES_USER` - Database user (default: ml_user)
- `POSTGRES_PASSWORD` - Database password (default: ml_password)

## Security Considerations

### Development Security
- Default passwords are used for local development
- SSL is disabled for simplicity
- Authentication is simplified for development ease

### Production Recommendations
When moving to production:
1. Change all default passwords
2. Enable SSL/TLS encryption
3. Configure proper authentication methods
4. Set up connection pooling
5. Enable comprehensive audit logging
6. Configure backup encryption

## Validation

After initialization, you can validate the setup using:

```bash
# Run the validation script
python database/postgresql/validate_setup.py

# Or use the management script
./database/postgresql/manage.sh health
```

## Troubleshooting

### Common Issues

1. **Permission Denied Errors**
   - Check that the script files have proper permissions
   - Ensure Docker has access to the script directory

2. **Extension Installation Failures**
   - Verify PostgreSQL version compatibility
   - Check that the PostgreSQL image includes required extensions

3. **Schema Creation Errors**
   - Review the logs for specific error messages
   - Check for conflicting table or schema names

4. **User Creation Failures**
   - Verify that user names don't conflict with existing users
   - Check password complexity requirements

### Debugging

To debug initialization issues:

```bash
# Check PostgreSQL logs
docker-compose -f docker-compose.local.yml logs postgres

# Connect to the database and check status
docker-compose -f docker-compose.local.yml exec postgres psql -U ml_user -d multimodal_librarian

# Run health check manually
docker-compose -f docker-compose.local.yml exec postgres psql -U ml_user -d multimodal_librarian -f /etc/postgresql/health_check.sql
```

## Migration from Existing Setup

If you have an existing database setup, you can migrate data using the compatibility layer:

```sql
-- Connect to the database
\c multimodal_librarian

-- Run data migration
SELECT * FROM migrate_data_to_new_schema();

-- Check migration status
SELECT * FROM public.migration_history ORDER BY applied_at DESC;
```

## Backup and Restore

The initialization scripts create a foundation that supports:

- Automated backups using the backup scripts
- Point-in-time recovery
- Schema-only backups for development
- Data migration between environments

See the main PostgreSQL README for detailed backup and restore procedures.

## Performance Optimization

The initialization scripts include performance optimizations for local development:

- Appropriate memory settings for development machines
- Optimized indexes for common queries
- Query statistics collection for performance monitoring
- Maintenance functions for keeping the database healthy

## Integration with Application

The database schema is designed to integrate seamlessly with the Multimodal Librarian application:

- Database factory pattern for environment switching
- Connection pooling support
- Health check integration
- Migration compatibility for existing code

## Support

For issues with the initialization scripts:

1. Check the PostgreSQL logs for specific error messages
2. Verify environment variables are set correctly
3. Ensure all required files are present and readable
4. Run the validation script to identify specific issues
5. Consult the main PostgreSQL documentation for advanced troubleshooting