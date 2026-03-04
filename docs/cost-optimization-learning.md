# Cost Optimization Guide - AWS Learning Deployment

This guide provides strategies and best practices for optimizing costs in your AWS learning deployment while maintaining functionality and learning value. The goal is to stay within budget while maximizing educational benefit.

## 🎯 Cost Optimization Objectives

### Budget Targets
- **Development Environment**: $50/month
- **Staging Environment**: $150/month
- **Total Learning Budget**: $200/month
- **Alert Threshold**: 80% of monthly budget

### Key Principles
- **Right-size resources** for learning workloads
- **Use Free Tier** services where possible
- **Implement lifecycle policies** for data retention
- **Monitor and alert** on cost thresholds
- **Automate shutdown** of non-production resources

## 💰 Current Cost Breakdown

### Development Environment (~$50/month)
```
Service                 Monthly Cost    Optimization Strategy
ECS Fargate            $15-25          Right-size tasks, use Spot pricing
RDS t3.micro           $15-20          Use Free Tier, single AZ
NAT Gateway            $15-20          Single gateway, consider alternatives
S3 Storage             $2-5            Lifecycle policies, compression
CloudWatch             $3-8            Optimize log retention
Application Load Balancer $16-20       Consider Network Load Balancer
Data Transfer          $1-3            Minimize cross-AZ traffic
```

### Staging Environment (~$150/month)
```
Service                 Monthly Cost    Optimization Strategy
ECS Fargate            $30-50          Scheduled scaling, Spot instances
RDS t3.small           $25-35          Right-size, optimize queries
NAT Gateway            $45             Single gateway for cost savings
S3 Storage             $5-10           Aggressive lifecycle policies
CloudWatch             $10-15          Optimize metrics and logs
Application Load Balancer $20          Required for blue-green deployment
Data Transfer          $5-10           Optimize data flow patterns
```

## 🔧 Cost Optimization Strategies

### 1. Compute Optimization

#### ECS Fargate Right-Sizing
```bash
# Check current task resource usage
aws cloudwatch get-metric-statistics \
  --namespace AWS/ECS \
  --metric-name CPUUtilization \
  --dimensions Name=ServiceName,Value=multimodal-librarian-dev-service \
  --start-time $(date -u -d '7 days ago' +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 3600 \
  --statistics Average,Maximum

# If average CPU < 30%, consider reducing CPU allocation
# If average Memory < 50%, consider reducing memory allocation
```

**Optimization Actions:**
- **Reduce CPU/Memory** if utilization is consistently low
- **Use Spot pricing** for non-critical workloads
- **Implement scheduled scaling** for predictable workloads

#### Auto-Shutdown for Development
```bash
# Create Lambda function to stop ECS services after hours
# Schedule: Stop at 10 PM, Start at 8 AM on weekdays

# Stop ECS service
aws ecs update-service \
  --cluster multimodal-librarian-dev-cluster \
  --service multimodal-librarian-dev-service \
  --desired-count 0

# Start ECS service
aws ecs update-service \
  --cluster multimodal-librarian-dev-cluster \
  --service multimodal-librarian-dev-service \
  --desired-count 1
```

### 2. Database Optimization

#### RDS Cost Optimization
```bash
# Check database utilization
aws cloudwatch get-metric-statistics \
  --namespace AWS/RDS \
  --metric-name CPUUtilization \
  --dimensions Name=DBInstanceIdentifier,Value=dev-database \
  --start-time $(date -u -d '7 days ago' +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 3600 \
  --statistics Average,Maximum

# Check connection count
aws cloudwatch get-metric-statistics \
  --namespace AWS/RDS \
  --metric-name DatabaseConnections \
  --dimensions Name=DBInstanceIdentifier,Value=dev-database \
  --start-time $(date -u -d '7 days ago' +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 3600 \
  --statistics Average,Maximum
```

**Optimization Actions:**
- **Use Free Tier** t3.micro for development
- **Single AZ deployment** to avoid Multi-AZ costs
- **Optimize backup retention** (7 days for learning)
- **Consider Aurora Serverless** for variable workloads

#### Database Query Optimization
```sql
-- Identify slow queries
SELECT query, mean_time, calls, total_time
FROM pg_stat_statements
ORDER BY mean_time DESC
LIMIT 10;

-- Check index usage
SELECT schemaname, tablename, attname, n_distinct, correlation
FROM pg_stats
WHERE schemaname = 'public'
ORDER BY n_distinct DESC;
```

### 3. Storage Optimization

#### S3 Lifecycle Policies
```json
{
  "Rules": [
    {
      "ID": "DevEnvironmentLifecycle",
      "Status": "Enabled",
      "Filter": {"Prefix": "dev/"},
      "Transitions": [
        {
          "Days": 7,
          "StorageClass": "STANDARD_IA"
        },
        {
          "Days": 30,
          "StorageClass": "GLACIER"
        }
      ],
      "Expiration": {
        "Days": 90
      }
    },
    {
      "ID": "TempFilesCleanup",
      "Status": "Enabled",
      "Filter": {"Prefix": "temp/"},
      "Expiration": {
        "Days": 1
      }
    },
    {
      "ID": "LogsRetention",
      "Status": "Enabled",
      "Filter": {"Prefix": "logs/"},
      "Expiration": {
        "Days": 30
      }
    }
  ]
}
```

#### S3 Cost Analysis
```bash
# Check S3 storage usage by storage class
aws s3api list-objects-v2 \
  --bucket multimodal-librarian-dev-storage \
  --query 'Contents[*].{Key:Key,Size:Size,StorageClass:StorageClass}' \
  --output table

# Calculate total storage costs
aws ce get-cost-and-usage \
  --time-period Start=$(date -d '1 month ago' +%Y-%m-%d),End=$(date +%Y-%m-%d) \
  --granularity MONTHLY \
  --metrics BlendedCost \
  --group-by Type=DIMENSION,Key=SERVICE \
  --filter file://s3-filter.json
```

### 4. Network Optimization

#### NAT Gateway Alternatives
```bash
# Consider NAT instances for lower cost (learning environments only)
# Or use VPC endpoints for AWS services to avoid NAT gateway costs

# Create VPC endpoint for S3
aws ec2 create-vpc-endpoint \
  --vpc-id vpc-xxxxxxxxx \
  --service-name com.amazonaws.us-east-1.s3 \
  --route-table-ids rtb-xxxxxxxxx
```

#### Data Transfer Optimization
- **Minimize cross-AZ traffic** by keeping related services in same AZ
- **Use CloudFront** for static content delivery
- **Compress data** before transfer
- **Cache frequently accessed data**

### 5. Monitoring Cost Optimization

#### CloudWatch Log Retention
```bash
# Set appropriate log retention periods
aws logs put-retention-policy \
  --log-group-name /aws/ecs/multimodal-librarian-dev \
  --retention-in-days 7

# For staging environment
aws logs put-retention-policy \
  --log-group-name /aws/ecs/multimodal-librarian-staging \
  --retention-in-days 14
```

#### Custom Metrics Optimization
```bash
# Review custom metrics usage
aws cloudwatch list-metrics \
  --namespace "MultimodalLibrarian/Custom" \
  --query 'Metrics[*].{MetricName:MetricName,Dimensions:Dimensions}'

# Remove unused metrics to reduce costs
```

## 📊 Cost Monitoring and Alerting

### Daily Cost Tracking
```bash
#!/bin/bash
# Daily cost check script

# Get yesterday's costs
YESTERDAY_COST=$(aws ce get-cost-and-usage \
  --time-period Start=$(date -d '2 days ago' +%Y-%m-%d),End=$(date -d '1 day ago' +%Y-%m-%d) \
  --granularity DAILY \
  --metrics BlendedCost \
  --query 'ResultsByTime[0].Total.BlendedCost.Amount' \
  --output text)

echo "Yesterday's cost: \$${YESTERDAY_COST}"

# Check if over daily budget ($2 for dev)
if (( $(echo "$YESTERDAY_COST > 2.0" | bc -l) )); then
    echo "⚠️  Daily cost exceeded budget!"
    # Send alert or notification
fi
```

### Budget Alerts Setup
```bash
# Create budget with alerts
aws budgets create-budget \
  --account-id $(aws sts get-caller-identity --query Account --output text) \
  --budget '{
    "BudgetName": "MultimodalLibrarianLearning",
    "BudgetLimit": {
      "Amount": "200",
      "Unit": "USD"
    },
    "TimeUnit": "MONTHLY",
    "BudgetType": "COST"
  }' \
  --notifications-with-subscribers '[
    {
      "Notification": {
        "NotificationType": "ACTUAL",
        "ComparisonOperator": "GREATER_THAN",
        "Threshold": 80
      },
      "Subscribers": [
        {
          "SubscriptionType": "EMAIL",
          "Address": "your-email@example.com"
        }
      ]
    }
  ]'
```

### Cost Allocation Tags
```bash
# Apply consistent cost allocation tags
aws resourcegroupstaggingapi tag-resources \
  --resource-arn-list arn:aws:ecs:us-east-1:123456789012:service/multimodal-librarian-dev-cluster/multimodal-librarian-dev-service \
  --tags Environment=development,Project=multimodal-librarian,CostCenter=learning,Owner=team
```

## 🎯 Cost Optimization Automation

### Automated Resource Cleanup
```python
#!/usr/bin/env python3
"""
Automated resource cleanup script for cost optimization
"""

import boto3
import datetime
from dateutil import tz

def cleanup_old_snapshots():
    """Remove RDS snapshots older than 30 days"""
    rds = boto3.client('rds')
    
    # Get manual snapshots
    snapshots = rds.describe_db_snapshots(
        SnapshotType='manual',
        MaxRecords=100
    )
    
    cutoff_date = datetime.datetime.now(tz.tzutc()) - datetime.timedelta(days=30)
    
    for snapshot in snapshots['DBSnapshots']:
        if snapshot['SnapshotCreateTime'] < cutoff_date:
            print(f"Deleting old snapshot: {snapshot['DBSnapshotIdentifier']}")
            rds.delete_db_snapshot(
                DBSnapshotIdentifier=snapshot['DBSnapshotIdentifier']
            )

def cleanup_old_log_groups():
    """Remove old CloudWatch log groups"""
    logs = boto3.client('logs')
    
    # List log groups
    log_groups = logs.describe_log_groups()
    
    for log_group in log_groups['logGroups']:
        # Check if log group hasn't been used in 30 days
        if 'lastEventTime' in log_group:
            last_event = datetime.datetime.fromtimestamp(
                log_group['lastEventTime'] / 1000, tz.tzutc()
            )
            cutoff_date = datetime.datetime.now(tz.tzutc()) - datetime.timedelta(days=30)
            
            if last_event < cutoff_date and 'temp' in log_group['logGroupName']:
                print(f"Deleting old log group: {log_group['logGroupName']}")
                logs.delete_log_group(logGroupName=log_group['logGroupName'])

if __name__ == "__main__":
    cleanup_old_snapshots()
    cleanup_old_log_groups()
```

### Scheduled Scaling
```yaml
# CloudWatch Events rule for scheduled scaling
ScheduledScalingRule:
  Type: AWS::Events::Rule
  Properties:
    Description: "Scale down development environment after hours"
    ScheduleExpression: "cron(0 22 * * MON-FRI)"  # 10 PM weekdays
    State: ENABLED
    Targets:
      - Arn: !GetAtt ScalingLambda.Arn
        Id: "ScaleDownTarget"
        Input: '{"action": "scale_down", "environment": "development"}'
```

## 📈 Cost Optimization Metrics

### Key Performance Indicators
- **Cost per Environment**: Track monthly costs for dev/staging
- **Cost per User**: Calculate cost efficiency
- **Resource Utilization**: Monitor CPU/memory usage
- **Storage Efficiency**: Track storage usage and lifecycle transitions

### Monthly Cost Review Template
```markdown
# Monthly Cost Review - [Month/Year]

## Summary
- Total Spend: $XXX (Budget: $200)
- Variance: +/-X% from last month
- Largest Cost Centers: [Service 1, Service 2, Service 3]

## Environment Breakdown
- Development: $XX (Target: $50)
- Staging: $XX (Target: $150)

## Optimization Actions Taken
- [ ] Right-sized ECS tasks
- [ ] Implemented lifecycle policies
- [ ] Cleaned up unused resources
- [ ] Optimized log retention

## Next Month's Focus
- [ ] [Specific optimization target]
- [ ] [Resource to investigate]
- [ ] [Process improvement]
```

## 🎓 Learning Opportunities

### Cost Optimization Experiments
1. **Compare instance types** - Test different RDS instance sizes
2. **Evaluate storage classes** - Measure S3 storage class transitions
3. **Test scaling strategies** - Compare manual vs. automatic scaling
4. **Analyze data transfer** - Understand cross-AZ vs. same-AZ costs

### Best Practices to Learn
- **Tagging strategy** for cost allocation
- **Reserved instances** for predictable workloads
- **Spot instances** for fault-tolerant applications
- **Serverless architectures** for variable workloads

## 🚨 Cost Alerts and Thresholds

### Alert Levels
- **Green**: < 60% of monthly budget
- **Yellow**: 60-80% of monthly budget
- **Orange**: 80-95% of monthly budget
- **Red**: > 95% of monthly budget

### Automated Actions
- **80% threshold**: Send email alert
- **90% threshold**: Scale down non-critical resources
- **95% threshold**: Stop development environment
- **100% threshold**: Emergency shutdown procedures

## 📞 Cost Escalation Procedures

### When to Escalate
- **Unexpected cost spike** (>50% increase)
- **Budget overrun** (>110% of monthly budget)
- **Resource optimization** not achieving targets
- **Service pricing changes** affecting budget

### Escalation Contacts
1. **Technical Lead**: For resource optimization decisions
2. **Finance Team**: For budget adjustments
3. **AWS Support**: For billing questions
4. **Management**: For budget approval requests

---

**Remember**: Cost optimization is an ongoing process. Regular monitoring, analysis, and adjustment are key to maintaining an efficient and cost-effective AWS deployment while maximizing learning value.