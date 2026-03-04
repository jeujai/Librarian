# Disaster Recovery Validation Checklist

## Overview

This checklist ensures that all systems are fully operational after disaster recovery procedures.

## Pre-Validation Setup

- [ ] All infrastructure components are deployed
- [ ] All databases are restored and accessible
- [ ] All application services are running
- [ ] Load balancer is healthy and routing traffic

## Infrastructure Validation

### AWS Resources

- [ ] **VPC and Networking**
  - [ ] VPC exists with correct CIDR blocks
  - [ ] Public and private subnets are created
  - [ ] Internet Gateway and NAT Gateway are operational
  - [ ] Route tables are configured correctly
  - [ ] Security groups have appropriate rules

- [ ] **Compute Resources**
  - [ ] ECS cluster is running
  - [ ] ECS services are stable with desired task count
  - [ ] EC2 instances (Neo4j) are running and healthy
  - [ ] Load balancer is operational with healthy targets

- [ ] **Storage and Databases**
  - [ ] RDS PostgreSQL instance is available
  - [ ] ElastiCache Redis cluster is available
  - [ ] S3 buckets exist with correct permissions
  - [ ] EFS file system is mounted and accessible

### Validation Commands

```bash
# VPC validation
aws ec2 describe-vpcs --filters "Name=tag:Project,Values=multimodal-librarian"

# ECS validation
aws ecs describe-clusters --clusters multimodal-librarian-learning
aws ecs describe-services --cluster multimodal-librarian-learning --services multimodal-librarian-learning-web

# RDS validation
aws rds describe-db-instances --db-instance-identifier multimodal-librarian-learning

# Load balancer validation
aws elbv2 describe-load-balancers --names multimodal-librarian-learning-alb
aws elbv2 describe-target-health --target-group-arn <target-group-arn>
```

## Database Validation

### PostgreSQL Database

- [ ] **Connection and Authentication**
  - [ ] Database is accessible from application
  - [ ] Credentials from Secrets Manager work
  - [ ] SSL connections are working

- [ ] **Data Integrity**
  - [ ] All expected tables exist
  - [ ] Table row counts match expectations
  - [ ] Critical data is present and accessible
  - [ ] Indexes are rebuilt and functional

- [ ] **Performance**
  - [ ] Query response times are acceptable
  - [ ] Connection pooling is working
  - [ ] No blocking queries or locks

### Validation Queries

```sql
-- Check database connectivity
SELECT version();

-- Verify table existence and row counts
SELECT 
  schemaname,
  tablename,
  n_tup_ins as inserts,
  n_tup_upd as updates,
  n_tup_del as deletes
FROM pg_stat_user_tables
WHERE schemaname = 'public'
ORDER BY tablename;

-- Check for any corrupted indexes
SELECT schemaname, tablename, indexname, idx_scan, idx_tup_read, idx_tup_fetch
FROM pg_stat_user_indexes
WHERE schemaname = 'public'
ORDER BY tablename, indexname;
```

### Neo4j Knowledge Graph

- [ ] **Service Status**
  - [ ] Neo4j service is running
  - [ ] Web interface is accessible (if enabled)
  - [ ] Bolt protocol connections work

- [ ] **Data Integrity**
  - [ ] Node counts match expectations
  - [ ] Relationship counts are correct
  - [ ] Critical graph patterns exist
  - [ ] APOC procedures are available

### Validation Queries

```cypher
// Check node and relationship counts
MATCH (n) RETURN labels(n) as node_types, count(n) as count ORDER BY count DESC;
MATCH ()-[r]->() RETURN type(r) as relationship_types, count(r) as count ORDER BY count DESC;

// Verify APOC procedures
CALL apoc.help("apoc");

// Test graph traversal performance
MATCH (n)-[r*1..3]-(m) RETURN count(*) as connected_components LIMIT 1000;
```

### Milvus Vector Database

- [ ] **Service Status**
  - [ ] Milvus service is running
  - [ ] etcd and MinIO dependencies are healthy
  - [ ] Collections are accessible

- [ ] **Data Integrity**
  - [ ] Expected collections exist
  - [ ] Vector counts match expectations
  - [ ] Search functionality works
  - [ ] Index performance is acceptable

### Redis Cache

- [ ] **Service Status**
  - [ ] Redis cluster is available
  - [ ] Memory usage is within limits
  - [ ] No connection errors

- [ ] **Functionality**
  - [ ] Cache read/write operations work
  - [ ] TTL settings are correct
  - [ ] Cache hit rates are reasonable

## Application Validation

### Core Functionality

- [ ] **Web Interface**
  - [ ] Homepage loads correctly
  - [ ] Chat interface is functional
  - [ ] File upload works
  - [ ] Search functionality operates

- [ ] **API Endpoints**
  - [ ] Health check endpoint responds
  - [ ] Authentication endpoints work
  - [ ] Core API endpoints return expected responses
  - [ ] WebSocket connections establish successfully

- [ ] **ML and AI Features**
  - [ ] Document processing works
  - [ ] Vector search returns results
  - [ ] Knowledge graph queries execute
  - [ ] ML training APIs respond

### API Testing Commands

```bash
# Get load balancer DNS
ALB_DNS=$(aws elbv2 describe-load-balancers --names multimodal-librarian-learning-alb --query 'LoadBalancers[0].DNSName' --output text)

# Test health endpoint
curl -f http://$ALB_DNS/health

# Test API status
curl -f http://$ALB_DNS/api/v1/status

# Test chat endpoint
curl -X POST http://$ALB_DNS/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "test message"}'

# Test search endpoint
curl -f "http://$ALB_DNS/api/v1/search?q=test"
```

## Security Validation

### Access Controls

- [ ] **Network Security**
  - [ ] Security groups restrict access appropriately
  - [ ] VPC Flow Logs are enabled
  - [ ] No unnecessary ports are open

- [ ] **Authentication and Authorization**
  - [ ] API authentication works
  - [ ] User permissions are correct
  - [ ] Admin access is restricted

- [ ] **Data Protection**
  - [ ] Data at rest encryption is enabled
  - [ ] Data in transit encryption works
  - [ ] Secrets are properly managed

### Security Testing Commands

```bash
# Check security groups
aws ec2 describe-security-groups --filters "Name=group-name,Values=*multimodal-librarian*"

# Verify VPC Flow Logs
aws ec2 describe-flow-logs

# Check encryption settings
aws rds describe-db-instances --db-instance-identifier multimodal-librarian-learning --query 'DBInstances[0].StorageEncrypted'

# Verify secrets
aws secretsmanager list-secrets --filters Key=name,Values=multimodal-librarian-learning
```

## Monitoring and Alerting Validation

### CloudWatch Metrics

- [ ] **Application Metrics**
  - [ ] ECS service metrics are reporting
  - [ ] Load balancer metrics show traffic
  - [ ] Database metrics are available
  - [ ] Custom application metrics work

- [ ] **Alarms and Notifications**
  - [ ] Critical alarms are configured
  - [ ] Alarm thresholds are appropriate
  - [ ] Notification channels work
  - [ ] Escalation procedures are clear

### Monitoring Commands

```bash
# Check CloudWatch alarms
aws cloudwatch describe-alarms --alarm-name-prefix multimodal-librarian-learning

# Verify metrics are being published
aws cloudwatch list-metrics --namespace AWS/ECS --dimensions Name=ServiceName,Value=multimodal-librarian-learning-web

# Test SNS notifications (if configured)
aws sns list-subscriptions-by-topic --topic-arn <backup-notification-topic-arn>
```

## Backup and Recovery Validation

### Backup Systems

- [ ] **Automated Backups**
  - [ ] RDS automated backups are enabled
  - [ ] Backup Lambda function is operational
  - [ ] Backup schedules are configured
  - [ ] Backup retention policies are set

- [ ] **Backup Testing**
  - [ ] Recent backups exist and are accessible
  - [ ] Backup integrity checks pass
  - [ ] Restore procedures are documented
  - [ ] Recovery time objectives are met

### Backup Validation Commands

```bash
# Check RDS backups
aws rds describe-db-snapshots --db-instance-identifier multimodal-librarian-learning

# Verify backup Lambda function
aws lambda get-function --function-name multimodal-librarian-learning-backup

# Check backup S3 bucket
aws s3 ls s3://multimodal-librarian-learning-backups/

# Test backup function
aws lambda invoke --function-name multimodal-librarian-learning-backup --payload '{"backup_type":"test"}' response.json
```

## Performance Validation

### Response Times

- [ ] **Application Performance**
  - [ ] Page load times are acceptable (< 3 seconds)
  - [ ] API response times are reasonable (< 1 second)
  - [ ] Database queries perform well (< 500ms)
  - [ ] Search operations complete quickly (< 2 seconds)

- [ ] **Resource Utilization**
  - [ ] CPU usage is within normal ranges (< 70%)
  - [ ] Memory usage is stable (< 80%)
  - [ ] Disk I/O is not saturated
  - [ ] Network bandwidth is sufficient

### Performance Testing Commands

```bash
# Test response times
time curl -f http://$ALB_DNS/health

# Check ECS task resource usage
aws ecs describe-tasks --cluster multimodal-librarian-learning --tasks <task-arn>

# Monitor CloudWatch metrics
aws cloudwatch get-metric-statistics \
  --namespace AWS/ECS \
  --metric-name CPUUtilization \
  --dimensions Name=ServiceName,Value=multimodal-librarian-learning-web \
  --start-time $(date -u -d '1 hour ago' +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 300 \
  --statistics Average
```

## Integration Testing

### End-to-End Tests

- [ ] **User Workflows**
  - [ ] Complete user registration/login flow
  - [ ] Document upload and processing
  - [ ] Chat conversation with AI
  - [ ] Search and retrieval operations
  - [ ] Export functionality

- [ ] **System Integration**
  - [ ] All microservices communicate properly
  - [ ] External API integrations work
  - [ ] Data flows between components
  - [ ] Error handling works correctly

### Integration Test Commands

```bash
# Run automated integration tests
cd /path/to/project
python -m pytest tests/integration/ -v

# Run AWS-specific tests
python tests/aws/test_aws_basic_integration.py

# Run performance tests
python tests/performance/basic_load_test.py
```

## Final Validation

### System Health Summary

- [ ] All infrastructure components: ✅ Healthy
- [ ] All databases: ✅ Operational
- [ ] All applications: ✅ Running
- [ ] All security controls: ✅ Active
- [ ] All monitoring: ✅ Functional
- [ ] All backups: ✅ Working

### Sign-off

- [ ] **Technical Validation**
  - [ ] Infrastructure team approval
  - [ ] Database team approval
  - [ ] Security team approval
  - [ ] Application team approval

- [ ] **Business Validation**
  - [ ] Key functionality verified
  - [ ] Performance meets requirements
  - [ ] User acceptance testing passed
  - [ ] Stakeholder approval received

### Documentation Updates

- [ ] Recovery procedures updated
- [ ] Lessons learned documented
- [ ] Contact information verified
- [ ] Runbooks updated with any changes

## Recovery Metrics

Document the following metrics for future reference:

- **Recovery Time Actual**: _____ hours
- **Recovery Point Objective Met**: Yes/No
- **Data Loss**: _____ (describe any data loss)
- **Issues Encountered**: _____ (list major issues)
- **Total Cost**: $_____ (AWS costs during recovery)

## Post-Recovery Actions

- [ ] Schedule post-incident review meeting
- [ ] Update disaster recovery plan based on lessons learned
- [ ] Conduct team retrospective
- [ ] Update monitoring and alerting based on gaps identified
- [ ] Plan next disaster recovery test

---

**Validation Completed By**: _____________________  
**Date**: _____________________  
**Time**: _____________________  
**Overall Status**: ✅ PASS / ❌ FAIL