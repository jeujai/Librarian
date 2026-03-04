# Daily Health Checks - AWS Learning Deployment

Perform these health checks daily to ensure system reliability and catch issues early. This checklist takes 10-15 minutes and should be completed each morning.

## 🎯 Objectives

- **Verify system availability** and basic functionality
- **Identify performance issues** before they impact users
- **Monitor resource utilization** trends
- **Check security alerts** and unusual activity
- **Ensure cost tracking** is on target

## ✅ Daily Health Check Checklist

### 1. System Availability (2 minutes)

#### Application Health Check
```bash
# Get ALB DNS name
ALB_DNS=$(aws cloudformation describe-stacks \
  --stack-name MultimodalLibrarianDevStack \
  --query 'Stacks[0].Outputs[?OutputKey==`DevALBDNS`].OutputValue' \
  --output text)

# Test health endpoint
curl -f http://$ALB_DNS/health

# Expected response: {"status": "healthy", "timestamp": "..."}
```

#### ECS Service Status
```bash
# Check ECS service health
aws ecs describe-services \
  --cluster multimodal-librarian-dev-cluster \
  --services multimodal-librarian-dev-service \
  --query 'services[0].{Status:status,Running:runningCount,Desired:desiredCount}'
```

**Expected Output:**
```json
{
    "Status": "ACTIVE",
    "Running": 1,
    "Desired": 1
}
```

#### Database Connectivity
```bash
# Check RDS instance status
aws rds describe-db-instances \
  --query 'DBInstances[?DBName==`multimodal_librarian_dev`].{Status:DBInstanceStatus,Engine:Engine}' \
  --output table
```

**Expected Status:** `available`

### 2. Performance Metrics (3 minutes)

#### Application Response Time
```bash
# Test API response time
time curl -s http://$ALB_DNS/api/health > /dev/null

# Should complete in < 2 seconds
```

#### ECS Task Performance
```bash
# Check CPU and memory utilization (last hour)
aws cloudwatch get-metric-statistics \
  --namespace AWS/ECS \
  --metric-name CPUUtilization \
  --dimensions Name=ServiceName,Value=multimodal-librarian-dev-service Name=ClusterName,Value=multimodal-librarian-dev-cluster \
  --start-time $(date -u -d '1 hour ago' +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 3600 \
  --statistics Average \
  --output table
```

**Healthy Range:** CPU < 70%, Memory < 80%

#### Database Performance
```bash
# Check database connections
aws cloudwatch get-metric-statistics \
  --namespace AWS/RDS \
  --metric-name DatabaseConnections \
  --dimensions Name=DBInstanceIdentifier,Value=dev-database \
  --start-time $(date -u -d '1 hour ago' +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 3600 \
  --statistics Average \
  --output table
```

**Healthy Range:** < 20 connections for t3.micro

### 3. Error Rate Monitoring (2 minutes)

#### Application Logs
```bash
# Check for errors in the last hour
aws logs filter-log-events \
  --log-group-name /aws/ecs/multimodal-librarian-dev \
  --start-time $(date -d '1 hour ago' +%s)000 \
  --filter-pattern "ERROR" \
  --query 'events[*].{Time:timestamp,Message:message}' \
  --output table
```

**Healthy State:** No critical errors, < 5 warning messages

#### ALB Error Rates
```bash
# Check ALB 4xx and 5xx errors
aws cloudwatch get-metric-statistics \
  --namespace AWS/ApplicationELB \
  --metric-name HTTPCode_Target_4XX_Count \
  --dimensions Name=LoadBalancer,Value=app/multimodal-librarian-dev-alb \
  --start-time $(date -u -d '1 hour ago' +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 3600 \
  --statistics Sum \
  --output table
```

**Healthy Range:** < 1% error rate

### 4. Security Status (3 minutes)

#### Failed Login Attempts
```bash
# Check CloudTrail for failed authentication
aws logs filter-log-events \
  --log-group-name CloudTrail/multimodal-librarian \
  --start-time $(date -d '24 hours ago' +%s)000 \
  --filter-pattern "{ $.errorCode = \"SigninFailure\" }" \
  --query 'events[*].{Time:timestamp,Source:sourceIPAddress}' \
  --output table
```

**Healthy State:** No unusual failed login patterns

#### Security Group Changes
```bash
# Check for recent security group modifications
aws ec2 describe-security-groups \
  --filters "Name=group-name,Values=*Dev*" \
  --query 'SecurityGroups[*].{GroupId:GroupId,GroupName:GroupName,Description:Description}' \
  --output table
```

**Action Required:** Investigate any unexpected changes

#### Secrets Manager Access
```bash
# Verify secrets are accessible
aws secretsmanager describe-secret \
  --secret-id dev/database/credentials \
  --query '{Name:Name,LastChanged:LastChangedDate}' \
  --output table
```

### 5. Cost Monitoring (2 minutes)

#### Daily Cost Check
```bash
# Check yesterday's costs
aws ce get-cost-and-usage \
  --time-period Start=$(date -d '2 days ago' +%Y-%m-%d),End=$(date -d '1 day ago' +%Y-%m-%d) \
  --granularity DAILY \
  --metrics BlendedCost \
  --group-by Type=DIMENSION,Key=SERVICE \
  --output table
```

**Budget Alert:** Daily cost should be < $2 for dev environment

#### Month-to-Date Spending
```bash
# Check current month spending
aws ce get-cost-and-usage \
  --time-period Start=$(date +%Y-%m-01),End=$(date +%Y-%m-%d) \
  --granularity MONTHLY \
  --metrics BlendedCost \
  --output table
```

**Budget Target:** < $50 for development environment

### 6. Backup Status (1 minute)

#### RDS Backup Status
```bash
# Check latest automated backup
aws rds describe-db-instances \
  --query 'DBInstances[?DBName==`multimodal_librarian_dev`].{BackupRetention:BackupRetentionPeriod,LatestBackup:LatestRestorableTime}' \
  --output table
```

**Expected:** Backup within last 24 hours

#### S3 Backup Objects
```bash
# Check backup objects in S3
aws s3 ls s3://multimodal-librarian-dev-backup/ --recursive --human-readable
```

## 🚨 Alert Conditions

### Critical Issues (Immediate Action Required)
- **Application health check fails**
- **ECS service not running** (Running < Desired)
- **Database unavailable**
- **Error rate > 5%**
- **Daily cost > $5**

### Warning Conditions (Investigate within 1 hour)
- **Response time > 3 seconds**
- **CPU utilization > 80%**
- **Memory utilization > 85%**
- **Error rate > 1%**
- **Unusual security events**

### Info Conditions (Review during business hours)
- **Performance degradation trends**
- **Cost variance > 20%**
- **Minor configuration changes**
- **Backup completion notifications**

## 📊 Health Check Dashboard

### CloudWatch Dashboard URL
```bash
# Get dashboard URL
echo "https://console.aws.amazon.com/cloudwatch/home?region=us-east-1#dashboards:name=MultimodalLibrarian-Dev"
```

### Key Metrics to Monitor
- **Application Response Time**: Target < 2 seconds
- **ECS CPU Utilization**: Target < 70%
- **ECS Memory Utilization**: Target < 80%
- **RDS CPU Utilization**: Target < 60%
- **ALB Request Count**: Monitor for traffic patterns
- **Error Rate**: Target < 1%

## 🔧 Quick Fixes for Common Issues

### Application Not Responding
```bash
# Restart ECS service
aws ecs update-service \
  --cluster multimodal-librarian-dev-cluster \
  --service multimodal-librarian-dev-service \
  --force-new-deployment
```

### High CPU Usage
```bash
# Scale up ECS service temporarily
aws ecs update-service \
  --cluster multimodal-librarian-dev-cluster \
  --service multimodal-librarian-dev-service \
  --desired-count 2
```

### Database Connection Issues
```bash
# Check database security groups
aws ec2 describe-security-groups \
  --filters "Name=group-name,Values=*database*" \
  --query 'SecurityGroups[*].IpPermissions[*]'
```

## 📝 Health Check Log Template

```
Date: $(date)
Operator: [Your Name]

System Availability:
- Application Health: ✅/❌
- ECS Service: ✅/❌ (Running/Desired)
- Database: ✅/❌

Performance:
- Response Time: [X]s
- CPU Usage: [X]%
- Memory Usage: [X]%

Errors:
- Application Errors: [Count]
- ALB 4xx/5xx: [Count]

Security:
- Failed Logins: [Count]
- Security Changes: ✅/❌

Cost:
- Daily Cost: $[X]
- MTD Cost: $[X]

Backups:
- RDS Backup: ✅/❌
- S3 Backup: ✅/❌

Issues Found: [None/List issues]
Actions Taken: [None/List actions]
```

## 🎓 Learning Notes

### What to Look For
- **Trends over time** rather than single data points
- **Correlation between metrics** (e.g., high CPU and slow response)
- **Unusual patterns** in logs or metrics
- **Cost spikes** that don't correlate with usage

### Best Practices
- **Consistent timing** - perform checks at the same time daily
- **Document findings** - keep a log of issues and resolutions
- **Automate where possible** - create scripts for repetitive checks
- **Share knowledge** - discuss findings with team members

### Escalation Guidelines
- **Critical issues**: Escalate immediately
- **Trends**: Document and discuss in weekly reviews
- **Cost concerns**: Alert finance/management promptly
- **Security events**: Follow security incident procedures

---

**Remember:** These daily health checks are your first line of defense against system issues. Consistency is key - perform them every day to establish baselines and catch problems early.