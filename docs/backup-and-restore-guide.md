# Database Backup and Restore Guide

This guide covers the comprehensive backup and restore system for the Multimodal Librarian local development environment.

## Overview

The backup and restore system supports all local database services:
- **PostgreSQL**: Relational database for metadata and configuration
- **Neo4j**: Graph database for knowledge graph operations
- **Milvus**: Vector database for semantic search and embeddings
- **Redis**: Cache and session storage

## Quick Start

### Creating Backups

```bash
# Backup all databases
./scripts/backup-all-databases.sh

# Backup specific database
./database/postgresql/backup.sh
./scripts/backup-neo4j.sh
./scripts/backup-milvus.py all
```

### Restoring from Backups

```bash
# Restore all databases from latest backups
./scripts/restore-all-databases.sh latest

# Restore specific database
./database/postgresql/restore.sh latest
./scripts/restore-neo4j.sh latest
./scripts/restore-milvus.py system --latest
./scripts/restore-redis.sh latest
```

## Backup System

### Backup All Databases

The main backup script coordinates backups across all database services:

```bash
./scripts/backup-all-databases.sh [full|schema|data|compressed|cleanup|stats|verify|help]
```

**Options:**
- `full` - Create full backups of all databases (default)
- `schema` - Create schema-only backups
- `data` - Create data-only backups
- `compressed` - Create compressed backups
- `cleanup` - Remove backups older than 7 days
- `stats` - Show backup statistics
- `verify` - Verify backup integrity

**Environment Variables:**
```bash
export BACKUP_DIR="./backups"              # Root backup directory
export PARALLEL_BACKUPS="true"             # Run backups in parallel
export BACKUP_TYPE="full"                  # Default backup type
```

### Individual Database Backups

#### PostgreSQL Backup

```bash
./database/postgresql/backup.sh [schema|data|compressed|full|all|cleanup|stats]
```

**Features:**
- Schema-only backups (`pg_dump --schema-only`)
- Data-only backups (`pg_dump --data-only`)
- Full SQL backups (`pg_dump`)
- Compressed binary backups (`pg_dump --format=custom`)

#### Neo4j Backup

```bash
./scripts/backup-neo4j.sh [cypher|json|graphml|schema|stats|admin|all|cleanup|verify|stats-only]
```

**Features:**
- Cypher export backups (using APOC)
- JSON export backups
- GraphML export backups
- Schema-only backups (constraints and indexes)
- Database statistics backups
- Admin backups (using neo4j-admin)

#### Milvus Backup

```bash
./scripts/backup-milvus.py [system|collection|all|cleanup|stats|list]
```

**Features:**
- System information backups
- Collection schema backups
- Collection data backups (with/without vectors)
- Per-collection backups

#### Redis Backup

Redis backups are handled within the main backup script using:
- RDB snapshots (`BGSAVE`)
- AOF file copies (if enabled)

## Restore System

### Restore All Databases

The main restore script coordinates restores across all database services:

```bash
./scripts/restore-all-databases.sh [latest|schema|file <path>|list|verify|help]
```

**Options:**
- `latest` - Restore from latest backups (default)
- `schema` - Restore schema-only from latest schema backups
- `file <path>` - Restore from specific backup file
- `list` - List available backups
- `verify` - Verify current database state

**Environment Variables:**
```bash
export BACKUP_DIR="./backups"              # Root backup directory
export PARALLEL_RESTORES="false"           # Run restores in parallel
export FORCE_RESTORE="false"               # Skip confirmation prompts
```

### Individual Database Restores

#### PostgreSQL Restore

```bash
./database/postgresql/restore.sh [list|latest|latest-schema|file <path>]
```

**Features:**
- Restore from latest full backup
- Restore schema from latest schema backup
- Restore from specific backup file
- Automatic database recreation

#### Neo4j Restore

```bash
./scripts/restore-neo4j.sh [list|latest|latest-json|schema|file <path>|admin|verify]
```

**Features:**
- Restore from Cypher export backups
- Restore from JSON export backups
- Restore from GraphML export backups
- Schema-only restore
- Admin backup restore (requires service restart)

#### Milvus Restore

```bash
./scripts/restore-milvus.py [list|system|collection|file|verify]
```

**Features:**
- System restore (recreate all collections)
- Individual collection restore
- Restore from specific backup files
- Schema and data restoration

#### Redis Restore

```bash
./scripts/restore-redis.sh [list|latest|latest-aof|file <path>|verify]
```

**Features:**
- RDB backup restoration
- AOF backup restoration
- Redis commands file restoration
- Automatic safety backup creation

## Backup Directory Structure

```
backups/
├── postgresql/
│   ├── full_multimodal_librarian_20240115_143022.sql
│   ├── schema_multimodal_librarian_20240115_143022.sql
│   └── compressed_multimodal_librarian_20240115_143022.dump
├── neo4j/
│   ├── cypher_export_20240115_143022.cypher
│   ├── json_export_20240115_143022.json
│   ├── schema_20240115_143022.cypher
│   └── admin_backup_20240115_143022/
├── milvus/
│   ├── system_info_20240115_143022.json
│   └── documents/
│       ├── schema_documents_20240115_143022.json
│       ├── data_documents_20240115_143022.json
│       └── vectors_documents_20240115_143022.json
├── redis/
│   ├── redis_dump_20240115_143022.rdb
│   └── safety/
│       └── safety_backup_20240115_143022.rdb
└── system/
    └── backup_metadata_20240115_143022.json
```

## Configuration

### Database Connection Settings

All scripts use environment variables for database connections:

```bash
# PostgreSQL
export POSTGRES_HOST="localhost"
export POSTGRES_PORT="5432"
export POSTGRES_DB="multimodal_librarian"
export POSTGRES_USER="ml_user"
export POSTGRES_PASSWORD="ml_password"

# Neo4j
export NEO4J_HOST="localhost"
export NEO4J_PORT="7687"
export NEO4J_USER="neo4j"
export NEO4J_PASSWORD="ml_password"

# Milvus
export MILVUS_HOST="localhost"
export MILVUS_PORT="19530"
export MILVUS_HTTP_PORT="9091"

# Redis
export REDIS_HOST="localhost"
export REDIS_PORT="6379"
```

### Backup Configuration

```bash
# Backup settings
export BACKUP_DIR="./backups"              # Root backup directory
export PARALLEL_BACKUPS="true"             # Run backups in parallel
export PARALLEL_RESTORES="false"           # Run restores sequentially by default
export FORCE_RESTORE="false"               # Require confirmation for restores
```

## Best Practices

### Backup Strategy

1. **Regular Backups**: Run daily full backups
2. **Schema Backups**: Create schema backups before major changes
3. **Verification**: Regularly verify backup integrity
4. **Cleanup**: Remove old backups to save space

```bash
# Daily backup cron job example
0 2 * * * cd /path/to/multimodal-librarian && ./scripts/backup-all-databases.sh full
0 3 * * 0 cd /path/to/multimodal-librarian && ./scripts/backup-all-databases.sh cleanup
```

### Restore Strategy

1. **Safety First**: Always create safety backups before restore
2. **Verification**: Verify restored data after restore
3. **Testing**: Test restore procedures regularly
4. **Documentation**: Document restore procedures for your team

### Performance Optimization

1. **Parallel Operations**: Use parallel backups for faster execution
2. **Compression**: Use compressed backups to save space
3. **Incremental**: Consider incremental backups for large datasets
4. **Storage**: Use fast storage for backup directories

## Troubleshooting

### Common Issues

#### Connection Errors
```bash
# Check service status
docker-compose -f docker-compose.local.yml ps

# Check service logs
docker-compose -f docker-compose.local.yml logs postgres
docker-compose -f docker-compose.local.yml logs neo4j
docker-compose -f docker-compose.local.yml logs milvus
docker-compose -f docker-compose.local.yml logs redis
```

#### Permission Errors
```bash
# Fix script permissions
chmod +x scripts/*.sh
chmod +x scripts/*.py
chmod +x database/postgresql/*.sh
```

#### Disk Space Issues
```bash
# Check backup directory size
du -sh backups/

# Clean up old backups
./scripts/backup-all-databases.sh cleanup
```

#### Backup Corruption
```bash
# Verify backup integrity
./scripts/backup-all-databases.sh verify

# Check specific backup files
./database/postgresql/restore.sh list
./scripts/restore-neo4j.sh list
./scripts/restore-milvus.py list
./scripts/restore-redis.sh list
```

### Recovery Procedures

#### Complete System Recovery

1. **Stop all services**:
   ```bash
   docker-compose -f docker-compose.local.yml down
   ```

2. **Clear data volumes** (if needed):
   ```bash
   docker-compose -f docker-compose.local.yml down -v
   ```

3. **Start services**:
   ```bash
   docker-compose -f docker-compose.local.yml up -d
   ```

4. **Wait for services to be ready**:
   ```bash
   ./scripts/wait-for-services.sh
   ```

5. **Restore all databases**:
   ```bash
   ./scripts/restore-all-databases.sh latest
   ```

#### Partial Recovery

For individual database recovery, use the specific restore scripts:

```bash
# PostgreSQL only
./database/postgresql/restore.sh latest

# Neo4j only
./scripts/restore-neo4j.sh latest

# Milvus only
./scripts/restore-milvus.py system --latest

# Redis only
./scripts/restore-redis.sh latest
```

## Monitoring and Alerting

### Backup Monitoring

```bash
# Check backup status
./scripts/backup-all-databases.sh stats

# Verify backup integrity
./scripts/backup-all-databases.sh verify
```

### Automated Monitoring

Create monitoring scripts to check:
- Backup completion status
- Backup file sizes and timestamps
- Available disk space
- Service health before/after operations

### Alerting

Set up alerts for:
- Backup failures
- Disk space issues
- Service unavailability
- Backup verification failures

## Integration with Development Workflow

### Pre-deployment Backups

```bash
# Create backup before deployment
./scripts/backup-all-databases.sh full

# Deploy changes
make deploy-local

# Verify deployment
./scripts/restore-all-databases.sh verify
```

### Testing with Backups

```bash
# Create test data backup
./scripts/backup-all-databases.sh full

# Run tests that modify data
make test-local

# Restore clean state
./scripts/restore-all-databases.sh latest
```

### Development Environment Reset

```bash
# Quick reset to clean state
./scripts/restore-all-databases.sh schema  # Schema only
# or
./scripts/restore-all-databases.sh latest  # Full restore
```

## Security Considerations

### Backup Security

1. **Access Control**: Restrict access to backup directories
2. **Encryption**: Consider encrypting sensitive backups
3. **Network Security**: Secure backup transfer if using remote storage
4. **Audit Logging**: Log backup and restore operations

### Credential Management

1. **Environment Variables**: Use environment variables for credentials
2. **Secret Management**: Consider using secret management tools
3. **Rotation**: Regularly rotate database passwords
4. **Least Privilege**: Use minimal required permissions

## Advanced Usage

### Custom Backup Scripts

Create custom backup scripts for specific use cases:

```bash
#!/bin/bash
# Custom backup for specific collections
./scripts/backup-milvus.py collection --collection documents --type vectors
./scripts/backup-neo4j.sh schema
./database/postgresql/backup.sh data
```

### Backup Validation

```bash
#!/bin/bash
# Validate backup completeness
./scripts/backup-all-databases.sh verify
if [ $? -eq 0 ]; then
    echo "Backups are valid"
else
    echo "Backup validation failed"
    exit 1
fi
```

### Automated Recovery Testing

```bash
#!/bin/bash
# Test restore procedures
./scripts/backup-all-databases.sh full
./scripts/restore-all-databases.sh latest
./scripts/restore-all-databases.sh verify
```

This comprehensive backup and restore system ensures data safety and enables reliable development workflows for the Multimodal Librarian local development environment.