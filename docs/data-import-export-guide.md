# Data Import/Export Utilities Guide

This guide covers the comprehensive data import/export utilities for the Multimodal Librarian application, enabling data migration between local development and AWS production environments.

## Overview

The data import/export system provides:

- **Cross-environment compatibility**: Migrate data between local (Neo4j, Milvus, PostgreSQL) and AWS (Neptune, OpenSearch, RDS) environments
- **Multiple database support**: Handle PostgreSQL, Neo4j/Neptune, and Milvus/OpenSearch simultaneously
- **Data transformation**: Automatic format conversion and environment-specific adaptations
- **Integrity validation**: Comprehensive data validation before and after migration
- **Batch processing**: Efficient handling of large datasets with progress tracking
- **Error recovery**: Graceful handling of failures with detailed error reporting

## Available Utilities

### 1. Export Database Data (`export-database-data.py`)

Exports data from all database services in a standardized format.

```bash
# Export all databases
python scripts/export-database-data.py

# Export specific databases
python scripts/export-database-data.py --databases postgresql,neo4j

# Export with compression
python scripts/export-database-data.py --compress --format json

# Export from AWS environment
ML_ENVIRONMENT=aws python scripts/export-database-data.py

# Custom output directory
python scripts/export-database-data.py --output-dir ./exports/prod-backup
```

**Features:**
- Supports JSON, CSV, SQL, and Cypher formats
- Optional gzip compression
- Metadata generation with checksums
- Parallel export for performance
- Comprehensive error handling

### 2. Import Database Data (`import-database-data.py`)

Imports data into database services from export files.

```bash
# Import from export directory
python scripts/import-database-data.py ./exports/export_20231201_120000/

# Import specific databases
python scripts/import-database-data.py --databases postgresql,neo4j ./exports/

# Import with different modes
python scripts/import-database-data.py --mode append ./exports/
python scripts/import-database-data.py --mode skip_existing ./exports/

# Dry run (validate without importing)
python scripts/import-database-data.py --dry-run ./exports/

# Import to AWS environment
ML_ENVIRONMENT=aws python scripts/import-database-data.py ./exports/
```

**Import Modes:**
- `replace`: Replace existing data (default)
- `append`: Append to existing data
- `update`: Update existing records
- `skip_existing`: Skip records that already exist

### 3. Environment Migration (`migrate-data-between-environments.py`)

High-level migration between local and AWS environments.

```bash
# Migrate from local to AWS
python scripts/migrate-data-between-environments.py --from local --to aws

# Migrate specific databases
python scripts/migrate-data-between-environments.py --from aws --to local --databases postgresql,neo4j

# Dry run migration
python scripts/migrate-data-between-environments.py --from local --to aws --dry-run

# Migration with data transformation
python scripts/migrate-data-between-environments.py --from local --to aws --transform
```

**Features:**
- Automated export → transform → import pipeline
- Environment-specific data transformations
- Comprehensive validation at each step
- Rollback capabilities
- Progress tracking and reporting

### 4. Data Integrity Validation (`validate-data-integrity.py`)

Validates data integrity across all databases.

```bash
# Validate all databases
python scripts/validate-data-integrity.py

# Validate specific databases
python scripts/validate-data-integrity.py --databases postgresql,neo4j

# Deep validation with relationship checks
python scripts/validate-data-integrity.py --level deep

# Generate detailed report
python scripts/validate-data-integrity.py --report ./validation-report.json

# Validate AWS environment
ML_ENVIRONMENT=aws python scripts/validate-data-integrity.py
```

**Validation Levels:**
- `basic`: Connectivity and structure checks
- `standard`: Standard integrity checks (default)
- `deep`: Comprehensive validation including relationships

## Data Formats and Structure

### Export File Structure

```
exports/
└── export_20231201_120000/
    ├── export_summary.json          # Export session summary
    ├── postgresql_export_*.json.gz  # PostgreSQL data
    ├── postgresql_metadata.json     # PostgreSQL metadata
    ├── neo4j_export_*.json.gz      # Neo4j data
    ├── neo4j_metadata.json         # Neo4j metadata
    ├── milvus_export_*.json.gz     # Milvus data
    └── milvus_metadata.json        # Milvus metadata
```

### PostgreSQL Export Format

```json
{
  "users": {
    "schema": {
      "columns": [
        {"column_name": "id", "data_type": "uuid", "is_nullable": "NO"},
        {"column_name": "email", "data_type": "character varying", "is_nullable": "NO"},
        {"column_name": "name", "data_type": "character varying", "is_nullable": "YES"}
      ]
    },
    "data": [
      {"id": "123e4567-e89b-12d3-a456-426614174000", "email": "user@example.com", "name": "John Doe"},
      // ... more records
    ],
    "record_count": 1000
  },
  "documents": {
    // ... similar structure
  }
}
```

### Neo4j Export Format

```json
{
  "nodes": {
    "User": {
      "data": [
        {
          "id": "123",
          "labels": ["User", "Person"],
          "properties": {"name": "John Doe", "email": "john@example.com"}
        }
      ],
      "record_count": 500
    },
    "Document": {
      // ... similar structure
    }
  },
  "relationships": {
    "OWNS": {
      "data": [
        {
          "id": "456",
          "type": "OWNS",
          "start_node_id": "123",
          "end_node_id": "789",
          "properties": {"created_at": "2023-01-01T00:00:00Z"}
        }
      ],
      "record_count": 200
    }
  },
  "schema": {
    "labels": ["User", "Document", "Concept"],
    "relationship_types": ["OWNS", "CONTAINS", "RELATED_TO"]
  }
}
```

### Milvus Export Format

```json
{
  "collections": {
    "document_chunks": {
      "stats": {
        "name": "document_chunks",
        "vector_count": 10000,
        "dimension": 384,
        "metric_type": "L2",
        "memory_usage": 15728640,
        "disk_usage": 52428800
      },
      "record_count": 10000
    }
  },
  "schema": {
    "collection_names": ["document_chunks", "user_embeddings"]
  }
}
```

## Environment Configuration

### Local Development Environment

```bash
# .env.local
ML_ENVIRONMENT=local
ML_DATABASE_TYPE=local

# PostgreSQL
ML_POSTGRES_HOST=localhost
ML_POSTGRES_PORT=5432
ML_POSTGRES_DB=multimodal_librarian
ML_POSTGRES_USER=ml_user
ML_POSTGRES_PASSWORD=ml_password

# Neo4j
ML_NEO4J_HOST=localhost
ML_NEO4J_PORT=7687
ML_NEO4J_USER=neo4j
ML_NEO4J_PASSWORD=ml_password

# Milvus
ML_MILVUS_HOST=localhost
ML_MILVUS_PORT=19530
```

### AWS Production Environment

```bash
# .env.aws
ML_ENVIRONMENT=aws
ML_DATABASE_TYPE=aws

# RDS PostgreSQL
ML_RDS_ENDPOINT=mydb.cluster-xyz.us-east-1.rds.amazonaws.com
ML_RDS_SECRET_NAME=multimodal-librarian/rds
ML_RDS_DATABASE=multimodal_librarian

# Neptune
ML_NEPTUNE_ENDPOINT=mydb.cluster-xyz.neptune.us-east-1.amazonaws.com
ML_NEPTUNE_SECRET_NAME=multimodal-librarian/neptune

# OpenSearch
ML_OPENSEARCH_ENDPOINT=https://search-mydb-xyz.us-east-1.es.amazonaws.com
ML_OPENSEARCH_SECRET_NAME=multimodal-librarian/opensearch
```

## Common Workflows

### 1. Local Development Setup

```bash
# Start local services
make dev-local

# Wait for services to be ready
make wait-for-databases

# Seed with sample data
python scripts/seed-all-sample-data.py

# Validate setup
python scripts/validate-data-integrity.py
```

### 2. Production Data Backup

```bash
# Export production data
ML_ENVIRONMENT=aws python scripts/export-database-data.py \
  --output-dir ./backups/prod-$(date +%Y%m%d) \
  --compress

# Validate export
python scripts/validate-data-integrity.py \
  --report ./backups/prod-$(date +%Y%m%d)/validation-report.json
```

### 3. Local Development with Production Data

```bash
# Export from production
ML_ENVIRONMENT=aws python scripts/export-database-data.py \
  --output-dir ./temp-export

# Import to local
ML_ENVIRONMENT=local python scripts/import-database-data.py \
  --mode replace ./temp-export

# Validate import
ML_ENVIRONMENT=local python scripts/validate-data-integrity.py
```

### 4. Staging Environment Sync

```bash
# Migrate from production to staging
python scripts/migrate-data-between-environments.py \
  --from aws --to local \
  --transform \
  --databases postgresql,neo4j
```

### 5. Data Migration Testing

```bash
# Dry run migration
python scripts/migrate-data-between-environments.py \
  --from local --to aws \
  --dry-run \
  --keep-temp

# Review migration plan
cat /tmp/ml_migration_*/migration_plan.json

# Execute actual migration
python scripts/migrate-data-between-environments.py \
  --from local --to aws
```

## Performance Considerations

### Large Dataset Handling

For large datasets (>1GB), consider:

```bash
# Use compression
python scripts/export-database-data.py --compress

# Increase batch size for imports
python scripts/import-database-data.py --batch-size 5000 ./exports/

# Export specific databases separately
python scripts/export-database-data.py --databases postgresql
python scripts/export-database-data.py --databases neo4j
python scripts/export-database-data.py --databases milvus
```

### Memory Optimization

```bash
# Monitor memory usage during operations
docker stats --no-stream

# Adjust Docker memory limits if needed
docker-compose -f docker-compose.local.yml up -d --scale postgres=1 --memory=2g
```

### Network Optimization

For AWS operations:
- Use EC2 instances in the same region as your databases
- Consider using AWS DataSync for very large transfers
- Enable compression for network transfers

## Error Handling and Troubleshooting

### Common Issues

#### 1. Connection Errors

```bash
# Check service status
docker-compose -f docker-compose.local.yml ps

# Test database connections
python scripts/validate-data-integrity.py --level basic

# Check network connectivity
telnet localhost 5432  # PostgreSQL
telnet localhost 7687  # Neo4j
telnet localhost 19530 # Milvus
```

#### 2. Permission Errors

```bash
# Check file permissions
ls -la ./exports/

# Fix permissions
chmod -R 755 ./exports/
chown -R $USER:$USER ./exports/
```

#### 3. Data Format Issues

```bash
# Validate export files
python -c "import json, gzip; print(json.load(gzip.open('export.json.gz'))['summary'])"

# Check file integrity
gzip -t export_file.json.gz
```

#### 4. Memory Issues

```bash
# Check available memory
free -h

# Monitor process memory usage
ps aux --sort=-%mem | head

# Reduce batch size
python scripts/import-database-data.py --batch-size 100 ./exports/
```

### Debugging Tips

#### Enable Verbose Logging

```bash
python scripts/export-database-data.py --verbose
python scripts/import-database-data.py --verbose
python scripts/validate-data-integrity.py --verbose
```

#### Check Temporary Files

```bash
# Keep temporary files for debugging
python scripts/migrate-data-between-environments.py --keep-temp

# Examine migration artifacts
ls -la /tmp/ml_migration_*/
cat /tmp/ml_migration_*/migration_result.json
```

#### Validate Each Step

```bash
# Export with validation
python scripts/export-database-data.py
python scripts/validate-data-integrity.py --report export-validation.json

# Import with dry run first
python scripts/import-database-data.py --dry-run ./exports/
python scripts/import-database-data.py ./exports/

# Post-import validation
python scripts/validate-data-integrity.py --report import-validation.json
```

## Security Considerations

### Sensitive Data Handling

1. **Environment Variables**: Store credentials in environment variables, not in code
2. **Temporary Files**: Ensure temporary files are cleaned up and not accessible to other users
3. **Network Security**: Use encrypted connections (SSL/TLS) for database connections
4. **Access Control**: Limit file permissions on export/import directories

### Data Sanitization

```bash
# Remove sensitive data before export (if needed)
python scripts/export-database-data.py --sanitize

# Validate no sensitive data in exports
grep -r "password\|secret\|key" ./exports/ || echo "No sensitive data found"
```

### Audit Trail

All operations create audit logs:

```bash
# Check operation logs
tail -f logs/data-operations.log

# Review export/import history
ls -la ./exports/*/export_summary.json
```

## Integration with CI/CD

### GitHub Actions Example

```yaml
name: Data Migration Test
on:
  pull_request:
    paths:
      - 'scripts/export-database-data.py'
      - 'scripts/import-database-data.py'

jobs:
  test-migration:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      
      - name: Setup Local Environment
        run: |
          make dev-local
          make wait-for-databases
          
      - name: Seed Test Data
        run: python scripts/seed-all-sample-data.py --quick
        
      - name: Test Export
        run: python scripts/export-database-data.py --output-dir ./test-export
        
      - name: Test Import
        run: python scripts/import-database-data.py --dry-run ./test-export
        
      - name: Validate Data Integrity
        run: python scripts/validate-data-integrity.py --report validation-report.json
        
      - name: Upload Validation Report
        uses: actions/upload-artifact@v2
        with:
          name: validation-report
          path: validation-report.json
```

### Makefile Integration

```makefile
# Data management targets
.PHONY: export-data import-data validate-data migrate-data

export-data:
	python scripts/export-database-data.py --output-dir ./exports/$(shell date +%Y%m%d_%H%M%S)

import-data:
	@read -p "Enter import directory: " dir; \
	python scripts/import-database-data.py $$dir

validate-data:
	python scripts/validate-data-integrity.py --report ./validation-report-$(shell date +%Y%m%d_%H%M%S).json

migrate-local-to-aws:
	python scripts/migrate-data-between-environments.py --from local --to aws

migrate-aws-to-local:
	python scripts/migrate-data-between-environments.py --from aws --to local

# Backup and restore
backup-prod:
	ML_ENVIRONMENT=aws $(MAKE) export-data

restore-from-backup:
	@read -p "Enter backup directory: " dir; \
	ML_ENVIRONMENT=local python scripts/import-database-data.py --mode replace $$dir
```

## Best Practices

### 1. Regular Backups

```bash
# Daily production backup
0 2 * * * ML_ENVIRONMENT=aws /path/to/scripts/export-database-data.py --output-dir /backups/daily/$(date +\%Y\%m\%d)

# Weekly full backup with validation
0 3 * * 0 ML_ENVIRONMENT=aws /path/to/scripts/export-database-data.py --output-dir /backups/weekly/$(date +\%Y\%m\%d) && \
          python /path/to/scripts/validate-data-integrity.py --report /backups/weekly/$(date +\%Y\%m\%d)/validation.json
```

### 2. Testing Migrations

Always test migrations in a staging environment:

```bash
# 1. Export from production
ML_ENVIRONMENT=aws python scripts/export-database-data.py --output-dir ./staging-migration

# 2. Import to staging
ML_ENVIRONMENT=staging python scripts/import-database-data.py ./staging-migration

# 3. Validate staging environment
ML_ENVIRONMENT=staging python scripts/validate-data-integrity.py --level deep

# 4. Run application tests against staging
make test-staging
```

### 3. Monitoring and Alerting

Set up monitoring for:
- Export/import operation success/failure
- Data integrity validation results
- Storage space for backups
- Migration performance metrics

### 4. Documentation

Maintain documentation for:
- Migration procedures for each environment
- Data transformation rules
- Recovery procedures
- Contact information for database administrators

This comprehensive guide provides everything needed to effectively use the data import/export utilities for the Multimodal Librarian application.