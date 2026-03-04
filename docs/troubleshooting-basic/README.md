# Troubleshooting Guide - AWS Learning Deployment

This guide provides systematic approaches to diagnosing and resolving common issues in the Multimodal Librarian AWS deployment. Use these procedures to quickly identify and fix problems.

## 🎯 Troubleshooting Philosophy

### Systematic Approach
1. **Identify symptoms** - What is the user experiencing?
2. **Gather information** - Collect logs, metrics, and system state
3. **Form hypothesis** - What might be causing the issue?
4. **Test hypothesis** - Verify your theory with targeted investigation
5. **Implement fix** - Apply the solution
6. **Verify resolution** - Confirm the issue is resolved
7. **Document** - Record the issue and solution for future reference

### Information Gathering
- **Start with monitoring** - Check dashboards and alerts first
- **Review recent changes** - What changed before the issue started?
- **Check dependencies** - Are all required services running?
- **Examine logs** - Look for error messages and patterns
- **Test components** - Isolate the problem area

## 🚨 Common Issues and Solutions

### Application Issues
- **[Application Won't Start](application-startup-issues.md)** - ECS task failures and startup problems
- **[Slow Response Times](performance-issues.md)** - Performance degradation troubleshooting
- **[Database Connection Errors](database-connectivity.md)** - Database access problems
- **[File Upload Failures](storage-issues.md)** - S3 and file handling issues
- **[Authentication Problems](authentication-issues.md)** - Login and access issues

### Infrastructure Issues
- **[ECS Service Problems](ecs-troubleshooting.md)** - Container orchestration issues
- **[Load Balancer Issues](alb-troubleshooting.md)** - Traffic routing problems
- **[Network Connectivity](network-troubleshooting.md)** - VPC and security group issues
- **[DNS Resolution](dns-troubleshooting.md)** - Domain name resolution problems

### Deployment Issues
- **[CDK Deployment Failures](cdk-troubleshooting.md)** - Infrastructure deployment problems
- **[Application Deployment Issues](deployment-troubleshooting.md)** - Application update failures
- **[Configuration Problems](configuration-troubleshooting.md)** - Environment and config issues
- **[Permission Errors](iam-troubleshooting.md)** - IAM and access permission problems

### Monitoring and Logging
- **[CloudWatch Issues](cloudwatch-troubleshooting.md)** - Monitoring and alerting problems
- **[Log Analysis](log-analysis.md)** - How to effectively analyze logs
- **[Metric Interpretation](metric-interpretation.md)** - Understanding CloudWatch metrics

## 🔍 Diagnostic Tools and Commands

### Quick Health Check
```bash
#!/bin/bash
# Quick system health check script

echo "=== System Health Check ==="
echo "Date: $(date)"
echo

# Check ECS service
echo "ECS Service Status:"
aws ecs describe-services \
  --cluster multimodal-librarian-dev-cluster \
  --services multimodal-librarian-dev-service \
  --query 'services[0].{Status:status,Running:runningCount,Desired:desiredCount}'

# Check database
echo -e "\nDatabase Status:"
aws rds describe-db-instances \
  --query 'DBInstances[?DBName==`multimodal_librarian_dev`].{Status:DBInstanceStatus,Endpoint:Endpoint.Address}' \
  --output table

# Check application health
echo -e "\nApplication Health:"
ALB_DNS=$(aws cloudformation describe-stacks \
  --stack-name MultimodalLibrarianDevStack \
  --query 'Stacks[0].Outputs[?OutputKey==`DevALBDNS`].OutputValue' \
  --output text)

if curl -f -s http://$ALB_DNS/health > /dev/null; then
    echo "✅ Application is responding"
else
    echo "❌ Application is not responding"
fi

# Check recent errors
echo -e "\nRecent Errors (last hour):"
aws logs filter-log-events \
  --log-group-name /aws/ecs/multimodal-librarian-dev \
  --start-time $(date -d '1 hour ago' +%s)000 \
  --filter-pattern "ERROR" \
  --query 'length(events)' \
  --output text | xargs -I {} echo "{} error events found"
```

### Log Analysis Commands
```bash
# View recent application logs
aws logs tail /aws/ecs/multimodal-librarian-dev --follow

# Search for specific errors
aws logs filter-log-events \
  --log-group-name /aws/ecs/multimodal-librarian-dev \
  --start-time $(date -d '1 hour ago' +%s)000 \
  --filter-pattern "ERROR"

# Check CloudFormation events
aws cloudformation describe-stack-events \
  --stack-name MultimodalLibrarianDevStack \
  --query 'StackEvents[?ResourceStatus!=`CREATE_COMPLETE` && ResourceStatus!=`UPDATE_COMPLETE`]'
```

### Performance Analysis
```bash
# Check CPU and memory usage
aws cloudwatch get-metric-statistics \
  --namespace AWS/ECS \
  --metric-name CPUUtilization \
  --dimensions Name=ServiceName,Value=multimodal-librarian-dev-service \
  --start-time $(date -u -d '1 hour ago' +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 300 \
  --statistics Average,Maximum

# Check database performance
aws cloudwatch get-metric-statistics \
  --namespace AWS/RDS \
  --metric-name CPUUtilization \
  --dimensions Name=DBInstanceIdentifier,Value=dev-database \
  --start-time $(date -u -d '1 hour ago' +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 300 \
  --statistics Average,Maximum
```

## 🔧 Troubleshooting Workflows

### Application Not Responding

#### Step 1: Check Load Balancer
```bash
# Get ALB status
aws elbv2 describe-load-balancers \
  --names multimodal-librarian-dev-alb \
  --query 'LoadBalancers[0].State'

# Check target group health
aws elbv2 describe-target-health \
  --target-group-arn $(aws elbv2 describe-target-groups \
    --names multimodal-librarian-dev-tg \
    --query 'TargetGroups[0].TargetGroupArn' \
    --output text)
```

#### Step 2: Check ECS Service
```bash
# Check service status
aws ecs describe-services \
  --cluster multimodal-librarian-dev-cluster \
  --services multimodal-librarian-dev-service

# Check task status
aws ecs list-tasks \
  --cluster multimodal-librarian-dev-cluster \
  --service-name multimodal-librarian-dev-service

# Get task details
TASK_ARN=$(aws ecs list-tasks \
  --cluster multimodal-librarian-dev-cluster \
  --service-name multimodal-librarian-dev-service \
  --query 'taskArns[0]' \
  --output text)

aws ecs describe-tasks \
  --cluster multimodal-librarian-dev-cluster \
  --tasks $TASK_ARN
```

#### Step 3: Check Application Logs
```bash
# View recent logs
aws logs tail /aws/ecs/multimodal-librarian-dev --since 1h

# Look for startup errors
aws logs filter-log-events \
  --log-group-name /aws/ecs/multimodal-librarian-dev \
  --start-time $(date -d '1 hour ago' +%s)000 \
  --filter-pattern "ERROR"
```

### Database Connection Issues

#### Step 1: Check Database Status
```bash
# Check RDS instance
aws rds describe-db-instances \
  --query 'DBInstances[?DBName==`multimodal_librarian_dev`]'

# Check database connectivity from application
aws ecs execute-command \
  --cluster multimodal-librarian-dev-cluster \
  --task $TASK_ARN \
  --container multimodal-librarian \
  --interactive \
  --command "pg_isready -h $DB_HOST -p 5432"
```

#### Step 2: Check Security Groups
```bash
# Check database security group
aws ec2 describe-security-groups \
  --filters "Name=group-name,Values=*database*" \
  --query 'SecurityGroups[*].{GroupId:GroupId,IpPermissions:IpPermissions}'

# Check application security group
aws ec2 describe-security-groups \
  --filters "Name=group-name,Values=*app*" \
  --query 'SecurityGroups[*].{GroupId:GroupId,GroupName:GroupName}'
```

#### Step 3: Test Connection
```bash
# Test database connection
python3 -c "
import psycopg2
import os
try:
    conn = psycopg2.connect(
        host=os.environ['DB_HOST'],
        database='multimodal_librarian_dev',
        user=os.environ['DB_USER'],
        password=os.environ['DB_PASSWORD']
    )
    print('✅ Database connection successful')
    conn.close()
except Exception as e:
    print(f'❌ Database connection failed: {e}')
"
```

### High CPU/Memory Usage

#### Step 1: Identify Resource Usage
```bash
# Check ECS task resource usage
aws cloudwatch get-metric-statistics \
  --namespace AWS/ECS \
  --metric-name CPUUtilization \
  --dimensions Name=ServiceName,Value=multimodal-librarian-dev-service \
  --start-time $(date -u -d '1 hour ago' +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 300 \
  --statistics Average,Maximum

# Check memory usage
aws cloudwatch get-metric-statistics \
  --namespace AWS/ECS \
  --metric-name MemoryUtilization \
  --dimensions Name=ServiceName,Value=multimodal-librarian-dev-service \
  --start-time $(date -u -d '1 hour ago' +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 300 \
  --statistics Average,Maximum
```

#### Step 2: Analyze Application Logs
```bash
# Look for performance-related errors
aws logs filter-log-events \
  --log-group-name /aws/ecs/multimodal-librarian-dev \
  --start-time $(date -d '1 hour ago' +%s)000 \
  --filter-pattern "timeout OR memory OR performance"
```

#### Step 3: Scale if Necessary
```bash
# Temporarily scale up
aws ecs update-service \
  --cluster multimodal-librarian-dev-cluster \
  --service multimodal-librarian-dev-service \
  --desired-count 2

# Or increase task resources (requires task definition update)
# This is more complex and should be done through CDK
```

## 📊 Monitoring and Alerting

### Key Metrics to Monitor
- **Application Response Time**: < 2 seconds
- **Error Rate**: < 1%
- **CPU Utilization**: < 70%
- **Memory Utilization**: < 80%
- **Database Connections**: < 20 for t3.micro
- **Disk Usage**: < 80%

### Setting Up Alerts
```bash
# Create high CPU alarm
aws cloudwatch put-metric-alarm \
  --alarm-name "HighCPU-Dev" \
  --alarm-description "High CPU utilization" \
  --metric-name CPUUtilization \
  --namespace AWS/ECS \
  --statistic Average \
  --period 300 \
  --threshold 80 \
  --comparison-operator GreaterThanThreshold \
  --evaluation-periods 2 \
  --dimensions Name=ServiceName,Value=multimodal-librarian-dev-service
```

## 🎓 Learning from Incidents

### Post-Incident Review
1. **Timeline**: When did the issue start and end?
2. **Root Cause**: What was the underlying cause?
3. **Impact**: How did it affect users and systems?
4. **Response**: How quickly was it detected and resolved?
5. **Prevention**: How can we prevent this in the future?

### Documentation Template
```markdown
# Incident Report: [Brief Description]

**Date**: [Date and Time]
**Duration**: [How long the incident lasted]
**Severity**: [Critical/High/Medium/Low]

## Summary
[Brief description of what happened]

## Timeline
- [Time]: Issue first detected
- [Time]: Investigation began
- [Time]: Root cause identified
- [Time]: Fix implemented
- [Time]: Issue resolved

## Root Cause
[Detailed explanation of what caused the issue]

## Resolution
[What was done to fix the issue]

## Lessons Learned
[What we learned and how to prevent similar issues]

## Action Items
- [ ] [Specific actions to prevent recurrence]
- [ ] [Process improvements]
- [ ] [Monitoring enhancements]
```

## 🔗 Quick Reference Links

### AWS Console Links
- **[ECS Console](https://console.aws.amazon.com/ecs/)**
- **[CloudWatch Console](https://console.aws.amazon.com/cloudwatch/)**
- **[RDS Console](https://console.aws.amazon.com/rds/)**
- **[S3 Console](https://console.aws.amazon.com/s3/)**
- **[CloudFormation Console](https://console.aws.amazon.com/cloudformation/)**

### Useful Commands Reference
```bash
# Quick service restart
aws ecs update-service --cluster [cluster] --service [service] --force-new-deployment

# View logs in real-time
aws logs tail [log-group] --follow

# Check stack status
aws cloudformation describe-stacks --stack-name [stack-name]

# List running tasks
aws ecs list-tasks --cluster [cluster] --service-name [service]

# Get task definition
aws ecs describe-task-definition --task-definition [task-def]
```

---

**Remember**: Effective troubleshooting requires patience, systematic thinking, and good documentation. Always start with the basics and work your way up to more complex scenarios. Document your findings to help others learn from your experience.