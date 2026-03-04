# Application Recovery Runbook

## Overview

This runbook covers restoring the Multimodal Librarian application services after infrastructure and database recovery.

## Prerequisites

- Infrastructure must be recreated (see [Infrastructure Recreation](./infrastructure-recreation.md))
- Databases must be restored (see [Database Recovery](./database-recovery.md))
- ECS cluster and services must be running

## Recovery Steps

### 1. Verify Infrastructure Status

```bash
# Check ECS cluster status
aws ecs describe-clusters --clusters multimodal-librarian-learning

# Check ECS services
aws ecs list-services --cluster multimodal-librarian-learning

# Check load balancer status
aws elbv2 describe-load-balancers --names multimodal-librarian-learning-alb

# Check target group health
aws elbv2 describe-target-health --target-group-arn $(aws elbv2 describe-target-groups --names multimodal-librarian-learning-tg --query 'TargetGroups[0].TargetGroupArn' --output text)
```

### 2. Update Application Configuration

```bash
# Get current secrets
aws secretsmanager list-secrets --filters Key=name,Values=multimodal-librarian-learning

# Update database connection strings if needed
DB_ENDPOINT=$(aws rds describe-db-instances --db-instance-identifier multimodal-librarian-learning --query 'DBInstances[0].Endpoint.Address' --output text)

# Update Neo4j endpoint if needed
NEO4J_INSTANCE_IP=$(aws ec2 describe-instances --filters "Name=tag:Name,Values=*neo4j*" "Name=instance-state-name,Values=running" --query 'Reservations[0].Instances[0].PrivateIpAddress' --output text)

# Update Milvus endpoint (should be automatic via service discovery)
echo "Milvus endpoint: milvus.milvus.local:19530"
```

### 3. Deploy Application Services

```bash
# Check current task definition
aws ecs describe-task-definition --task-definition multimodal-librarian-learning-web

# Update ECS service to latest task definition
aws ecs update-service \
  --cluster multimodal-librarian-learning \
  --service multimodal-librarian-learning-web \
  --force-new-deployment

# Wait for deployment to complete
aws ecs wait services-stable \
  --cluster multimodal-librarian-learning \
  --services multimodal-librarian-learning-web
```

### 4. Verify Service Health

```bash
# Check service status
aws ecs describe-services \
  --cluster multimodal-librarian-learning \
  --services multimodal-librarian-learning-web \
  --query 'services[0].deployments[0].status'

# Check task health
aws ecs list-tasks --cluster multimodal-librarian-learning --service-name multimodal-librarian-learning-web

# Get task details
TASK_ARN=$(aws ecs list-tasks --cluster multimodal-librarian-learning --service-name multimodal-librarian-learning-web --query 'taskArns[0]' --output text)

aws ecs describe-tasks --cluster multimodal-librarian-learning --tasks $TASK_ARN
```

### 5. Test Application Endpoints

```bash
# Get load balancer DNS name
ALB_DNS=$(aws elbv2 describe-load-balancers --names multimodal-librarian-learning-alb --query 'LoadBalancers[0].DNSName' --output text)

# Test health endpoint
curl -f http://$ALB_DNS/health

# Test API endpoints
curl -f http://$ALB_DNS/api/v1/status

# Test WebSocket connection (basic)
curl -f -H "Upgrade: websocket" -H "Connection: Upgrade" http://$ALB_DNS/ws
```

### 6. Restore Application Data

#### 6.1 Vector Database Collections

```bash
# The application will need to recreate Milvus collections
# This is typically done through the application's initialization process

# Check if collections exist (requires application-level testing)
echo "Vector database collections will be recreated by the application"
```

#### 6.2 Knowledge Graph Data

```bash
# Neo4j data should be restored from backup
# Verify graph data exists
NEO4J_INSTANCE_ID=$(aws ec2 describe-instances --filters "Name=tag:Name,Values=*neo4j*" "Name=instance-state-name,Values=running" --query 'Reservations[0].Instances[0].InstanceId' --output text)

aws ssm send-command \
  --instance-ids $NEO4J_INSTANCE_ID \
  --document-name "AWS-RunShellScript" \
  --parameters 'commands=["echo \"MATCH (n) RETURN count(n) as total_nodes\" | /opt/neo4j/bin/cypher-shell -u neo4j -p $(aws secretsmanager get-secret-value --secret-id multimodal-librarian-learning-neo4j-secret --query SecretString --output text | jq -r .password)"]'
```

#### 6.3 File Storage

```bash
# Verify S3 bucket access
aws s3 ls s3://multimodal-librarian-learning-storage-$(aws sts get-caller-identity --query Account --output text)/

# Test file upload (if needed)
echo "test file" > test-upload.txt
aws s3 cp test-upload.txt s3://multimodal-librarian-learning-storage-$(aws sts get-caller-identity --query Account --output text)/test/
aws s3 rm s3://multimodal-librarian-learning-storage-$(aws sts get-caller-identity --query Account --output text)/test/test-upload.txt
rm test-upload.txt
```

### 7. Initialize Application State

```bash
# Run database migrations (if needed)
# This depends on your application's migration strategy

# Initialize ML models (if needed)
# This may require downloading pre-trained models

# Warm up caches
# Redis cache will be rebuilt automatically as the application runs

echo "Application initialization may require manual steps depending on your specific setup"
```

## Verification Steps

### 1. Health Checks

```bash
# Application health
curl -f http://$ALB_DNS/health

# Database connectivity
curl -f http://$ALB_DNS/api/v1/db/health

# External API connectivity
curl -f http://$ALB_DNS/api/v1/external/health
```

### 2. Functional Tests

```bash
# Test chat interface
curl -X POST http://$ALB_DNS/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Hello, test message"}'

# Test file upload
curl -X POST http://$ALB_DNS/api/v1/upload \
  -F "file=@test-file.txt"

# Test search functionality
curl -X GET "http://$ALB_DNS/api/v1/search?q=test"
```

### 3. Performance Verification

```bash
# Check response times
time curl -f http://$ALB_DNS/health

# Check memory usage
aws ecs describe-tasks --cluster multimodal-librarian-learning --tasks $TASK_ARN --query 'tasks[0].containers[0].memory'

# Check CPU usage
aws cloudwatch get-metric-statistics \
  --namespace AWS/ECS \
  --metric-name CPUUtilization \
  --dimensions Name=ServiceName,Value=multimodal-librarian-learning-web Name=ClusterName,Value=multimodal-librarian-learning \
  --start-time $(date -u -d '1 hour ago' +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 300 \
  --statistics Average
```

## Troubleshooting

### Common Issues

1. **Service Won't Start**
   ```bash
   # Check service events
   aws ecs describe-services --cluster multimodal-librarian-learning --services multimodal-librarian-learning-web --query 'services[0].events'
   
   # Check task logs
   aws logs get-log-events --log-group-name /aws/ecs/multimodal-librarian-learning --log-stream-name ecs/web/$(date +%Y/%m/%d)
   ```

2. **Database Connection Issues**
   ```bash
   # Verify security groups
   aws ec2 describe-security-groups --filters "Name=group-name,Values=*database*"
   
   # Test database connectivity from ECS task
   aws ecs execute-command --cluster multimodal-librarian-learning --task $TASK_ARN --container web --interactive --command "/bin/bash"
   ```

3. **Load Balancer Issues**
   ```bash
   # Check target group health
   aws elbv2 describe-target-health --target-group-arn $(aws elbv2 describe-target-groups --names multimodal-librarian-learning-tg --query 'TargetGroups[0].TargetGroupArn' --output text)
   
   # Check load balancer logs (if enabled)
   aws s3 ls s3://multimodal-librarian-learning-alb-logs/
   ```

4. **Application Errors**
   ```bash
   # Check application logs
   aws logs filter-log-events --log-group-name /aws/ecs/multimodal-librarian-learning --filter-pattern "ERROR"
   
   # Check CloudWatch metrics
   aws cloudwatch get-metric-statistics --namespace AWS/ApplicationELB --metric-name HTTPCode_Target_5XX_Count
   ```

### Recovery Time Estimates

- **Service deployment**: 5-10 minutes
- **Application startup**: 2-5 minutes
- **Data initialization**: 10-30 minutes (depending on data size)
- **Total application recovery**: 17-45 minutes

## Post-Recovery Tasks

### 1. Update Monitoring

```bash
# Verify CloudWatch alarms
aws cloudwatch describe-alarms --alarm-name-prefix multimodal-librarian-learning

# Check dashboard
echo "Verify CloudWatch dashboard shows healthy metrics"
```

### 2. Update Documentation

```bash
# Document any configuration changes
# Update runbooks with lessons learned
# Record recovery time and issues encountered
```

### 3. Notify Stakeholders

```bash
# Send recovery completion notification
# Update status page (if applicable)
# Schedule post-incident review
```

## Integration Testing

After application recovery, run comprehensive tests:

```bash
# Run integration tests
cd /path/to/project
python -m pytest tests/integration/ -v

# Run specific AWS integration tests
python tests/aws/test_aws_basic_integration.py

# Test ML training functionality
python tests/aws/test_ml_training_basic.py
```

## Next Steps

After application recovery:
1. Complete [Validation Checklist](./validation-checklist.md)
2. Run [Recovery Testing](./recovery-testing.md)
3. Document lessons learned
4. Update disaster recovery procedures based on experience

## Performance Optimization

After recovery, consider:
- Warming up caches
- Pre-loading frequently accessed data
- Optimizing database queries
- Adjusting resource allocations based on observed performance