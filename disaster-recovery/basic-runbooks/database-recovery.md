# Database Recovery Runbook

## Overview

This runbook covers restoring all databases (PostgreSQL, Neo4j, Milvus) from backups.

## Prerequisites

- Infrastructure must be recreated first (see [Infrastructure Recreation](./infrastructure-recreation.md))
- Access to backup S3 bucket
- AWS CLI configured with appropriate permissions

## Recovery Steps

### 1. PostgreSQL Database Recovery

#### Option A: Restore from RDS Snapshot (Recommended)

```bash
# List available snapshots
aws rds describe-db-snapshots \
  --db-instance-identifier multimodal-librarian-learning \
  --snapshot-type manual \
  --query 'DBSnapshots[*].[DBSnapshotIdentifier,SnapshotCreateTime]' \
  --output table

# Restore from latest snapshot
LATEST_SNAPSHOT=$(aws rds describe-db-snapshots \
  --db-instance-identifier multimodal-librarian-learning \
  --snapshot-type manual \
  --query 'DBSnapshots | sort_by(@, &SnapshotCreateTime) | [-1].DBSnapshotIdentifier' \
  --output text)

echo "Restoring from snapshot: $LATEST_SNAPSHOT"

# Delete existing instance (if it exists and is empty)
aws rds delete-db-instance \
  --db-instance-identifier multimodal-librarian-learning \
  --skip-final-snapshot

# Wait for deletion to complete
aws rds wait db-instance-deleted \
  --db-instance-identifier multimodal-librarian-learning

# Restore from snapshot
aws rds restore-db-instance-from-db-snapshot \
  --db-instance-identifier multimodal-librarian-learning \
  --db-snapshot-identifier $LATEST_SNAPSHOT \
  --db-instance-class db.t3.micro \
  --publicly-accessible false

# Wait for restoration to complete
aws rds wait db-instance-available \
  --db-instance-identifier multimodal-librarian-learning
```

#### Option B: Manual Database Restore (if snapshots unavailable)

```bash
# Get database endpoint
DB_ENDPOINT=$(aws rds describe-db-instances \
  --db-instance-identifier multimodal-librarian-learning \
  --query 'DBInstances[0].Endpoint.Address' \
  --output text)

# Get database credentials from Secrets Manager
DB_SECRET=$(aws secretsmanager get-secret-value \
  --secret-id multimodal-librarian-learning-db-secret \
  --query 'SecretString' \
  --output text)

DB_USERNAME=$(echo $DB_SECRET | jq -r '.username')
DB_PASSWORD=$(echo $DB_SECRET | jq -r '.password')

# Download latest database backup from S3 (if available)
aws s3 cp s3://multimodal-librarian-learning-backups/database/ . --recursive

# Restore database schema
psql -h $DB_ENDPOINT -U $DB_USERNAME -d multimodal_librarian -f schema_backup.sql

# Restore data
psql -h $DB_ENDPOINT -U $DB_USERNAME -d multimodal_librarian -f data_backup.sql
```

### 2. Neo4j Database Recovery

```bash
# Get Neo4j instance ID
NEO4J_INSTANCE_ID=$(aws ec2 describe-instances \
  --filters "Name=tag:Name,Values=*neo4j*" "Name=instance-state-name,Values=running" \
  --query 'Reservations[0].Instances[0].InstanceId' \
  --output text)

# List available Neo4j backups
aws s3 ls s3://multimodal-librarian-learning-backups/neo4j-backups/

# Get latest backup
LATEST_NEO4J_BACKUP=$(aws s3 ls s3://multimodal-librarian-learning-backups/neo4j-backups/ \
  --query 'sort_by(Contents, &LastModified)[-1].Key' \
  --output text)

echo "Restoring Neo4j from backup: $LATEST_NEO4J_BACKUP"

# Create restore script
cat > restore_neo4j.sh << 'EOF'
#!/bin/bash
set -e

BACKUP_FILE="$1"
BACKUP_DIR="/tmp/neo4j-restore"

# Stop Neo4j service
sudo systemctl stop neo4j

# Create restore directory
mkdir -p $BACKUP_DIR

# Download backup from S3
aws s3 cp s3://multimodal-librarian-learning-backups/neo4j-backups/$BACKUP_FILE $BACKUP_DIR/

# Clear existing data
sudo rm -rf /var/lib/neo4j/data/*

# Extract backup
sudo tar -xzf $BACKUP_DIR/$BACKUP_FILE -C /var/lib/neo4j/

# Fix permissions
sudo chown -R neo4j:neo4j /var/lib/neo4j/data

# Start Neo4j service
sudo systemctl start neo4j

# Wait for Neo4j to start
sleep 30

# Test connection
echo "RETURN 1" | /opt/neo4j/bin/cypher-shell -u neo4j -p $(aws secretsmanager get-secret-value --secret-id multimodal-librarian-learning-neo4j-secret --query 'SecretString' --output text | jq -r '.password')

echo "Neo4j restore completed successfully"
EOF

# Execute restore on Neo4j instance
aws ssm send-command \
  --instance-ids $NEO4J_INSTANCE_ID \
  --document-name "AWS-RunShellScript" \
  --parameters "commands=[\"$(cat restore_neo4j.sh)\"]" \
  --comment "Neo4j database restore"
```

### 3. Milvus Database Recovery

```bash
# Get ECS cluster and service information
CLUSTER_NAME="multimodal-librarian-learning"

# Stop Milvus service
aws ecs update-service \
  --cluster $CLUSTER_NAME \
  --service milvus-learning \
  --desired-count 0

# Wait for service to stop
aws ecs wait services-stable \
  --cluster $CLUSTER_NAME \
  --services milvus-learning

# Get EFS file system ID
EFS_ID=$(aws efs describe-file-systems \
  --query 'FileSystems[?Tags[?Key==`Project` && Value==`multimodal-librarian`]].FileSystemId' \
  --output text)

# Create EC2 instance for EFS access (temporary)
# This is a simplified approach - in production, use EFS utils on existing instances

# List available Milvus backups
aws s3 ls s3://multimodal-librarian-learning-backups/milvus-backups/

# For Milvus, we'll rely on EFS snapshots or manual collection recreation
# Restart Milvus service
aws ecs update-service \
  --cluster $CLUSTER_NAME \
  --service milvus-learning \
  --desired-count 1

# Wait for service to start
aws ecs wait services-stable \
  --cluster $CLUSTER_NAME \
  --services milvus-learning

echo "Milvus service restarted. Collections will need to be recreated from application data."
```

### 4. Redis Cache Recovery

```bash
# Redis is used as a cache, so no data recovery is needed
# Verify Redis cluster is running
aws elasticache describe-cache-clusters \
  --cache-cluster-id multimodal-librarian-learning-redis \
  --show-cache-node-info

echo "Redis cluster is running. Cache will be rebuilt automatically."
```

## Verification Steps

### 1. PostgreSQL Verification

```bash
# Test database connection
psql -h $DB_ENDPOINT -U $DB_USERNAME -d multimodal_librarian -c "SELECT version();"

# Check table counts
psql -h $DB_ENDPOINT -U $DB_USERNAME -d multimodal_librarian -c "
SELECT schemaname, tablename, n_tup_ins as inserts, n_tup_upd as updates, n_tup_del as deletes
FROM pg_stat_user_tables
ORDER BY schemaname, tablename;"

# Verify critical tables exist
psql -h $DB_ENDPOINT -U $DB_USERNAME -d multimodal_librarian -c "
SELECT table_name FROM information_schema.tables 
WHERE table_schema = 'public' 
ORDER BY table_name;"
```

### 2. Neo4j Verification

```bash
# Test Neo4j connection via SSM
aws ssm send-command \
  --instance-ids $NEO4J_INSTANCE_ID \
  --document-name "AWS-RunShellScript" \
  --parameters 'commands=["echo \"MATCH (n) RETURN count(n) as node_count\" | /opt/neo4j/bin/cypher-shell -u neo4j -p $(aws secretsmanager get-secret-value --secret-id multimodal-librarian-learning-neo4j-secret --query SecretString --output text | jq -r .password)"]'
```

### 3. Milvus Verification

```bash
# Check Milvus service status
aws ecs describe-services \
  --cluster $CLUSTER_NAME \
  --services milvus-learning \
  --query 'services[0].status'

# Test Milvus connection (requires application-level testing)
echo "Milvus verification requires application-level testing"
```

## Recovery Time Estimates

- **PostgreSQL restore from snapshot**: 10-20 minutes
- **Neo4j restore**: 15-30 minutes (depending on data size)
- **Milvus restart**: 5-10 minutes
- **Total database recovery**: 30-60 minutes

## Troubleshooting

### Common Issues

1. **RDS Snapshot Not Found**
   - Check if automated backups are enabled
   - Look for manual snapshots
   - Consider point-in-time recovery if available

2. **Neo4j Backup Corruption**
   - Try previous backup
   - Check backup integrity
   - Consider partial data recovery

3. **EFS Mount Issues**
   - Verify security group rules
   - Check EFS mount targets
   - Ensure proper IAM permissions

4. **Service Dependencies**
   - Start services in correct order: etcd → MinIO → Milvus
   - Allow time for each service to fully start
   - Check service logs for errors

### Validation Queries

```sql
-- PostgreSQL health check
SELECT 
  schemaname,
  tablename,
  n_tup_ins + n_tup_upd + n_tup_del as total_operations
FROM pg_stat_user_tables 
WHERE schemaname = 'public'
ORDER BY total_operations DESC;
```

```cypher
// Neo4j health check
MATCH (n) 
RETURN labels(n) as node_types, count(n) as count 
ORDER BY count DESC;
```

## Next Steps

After database recovery:
1. Proceed to [Application Recovery](./application-recovery.md)
2. Run [Recovery Testing](./recovery-testing.md)
3. Complete [Validation Checklist](./validation-checklist.md)

## Data Loss Assessment

Document any data loss discovered during recovery:
- Time range of lost data
- Affected tables/collections
- Business impact
- Recovery options for lost data