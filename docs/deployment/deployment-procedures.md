# Deployment and Rollback Procedures

This document outlines comprehensive deployment and rollback procedures for the Multimodal Librarian system.

## Deployment Overview

### Deployment Architecture
- **Environment**: AWS ECS with Fargate
- **Database**: PostgreSQL RDS, OpenSearch, Neptune, Redis
- **Storage**: S3 for document files
- **Load Balancer**: Application Load Balancer (ALB)
- **Monitoring**: CloudWatch, custom metrics
- **CI/CD**: GitHub Actions

### Deployment Environments
1. **Development**: Local development and testing
2. **Staging**: Pre-production testing and validation
3. **Production**: Live user environment

## Pre-Deployment Checklist

### Code Quality Verification
- [ ] All tests pass (unit, integration, end-to-end)
- [ ] Code review completed and approved
- [ ] Security scan completed with no critical issues
- [ ] Performance benchmarks meet requirements
- [ ] Documentation updated

### Infrastructure Readiness
- [ ] Database migrations tested and ready
- [ ] Environment variables configured
- [ ] Secrets properly stored in AWS Secrets Manager
- [ ] Resource limits and scaling policies configured
- [ ] Monitoring and alerting configured

### Backup and Recovery
- [ ] Database backup completed
- [ ] Configuration backup created
- [ ] Rollback plan documented and tested
- [ ] Recovery procedures validated

## Deployment Procedures

### 1. Staging Deployment

#### Automated Staging Deployment
```bash
#!/bin/bash
# deploy-staging.sh

set -e

echo "Starting staging deployment..."

# 1. Build and test
echo "Building application..."
docker build -t multimodal-librarian:staging .

echo "Running tests..."
python -m pytest tests/ -v

# 2. Database migrations
echo "Running database migrations..."
python -m alembic upgrade head

# 3. Deploy to staging ECS
echo "Deploying to staging..."
aws ecs update-service \
    --cluster multimodal-librarian-staging \
    --service multimodal-librarian-service \
    --task-definition multimodal-librarian-staging:latest \
    --force-new-deployment

# 4. Wait for deployment
echo "Waiting for deployment to complete..."
aws ecs wait services-stable \
    --cluster multimodal-librarian-staging \
    --services multimodal-librarian-service

# 5. Health check
echo "Running health checks..."
./scripts/health-check.sh staging

echo "Staging deployment completed successfully!"
```

#### Manual Staging Verification
```bash
#!/bin/bash
# verify-staging.sh

STAGING_URL="https://staging.multimodal-librarian.com"

echo "Verifying staging deployment..."

# Health check
curl -f "$STAGING_URL/health" || exit 1

# API endpoints
curl -f "$STAGING_URL/api/health" || exit 1

# Database connectivity
curl -f "$STAGING_URL/api/health/database" || exit 1

# AI service connectivity
curl -f "$STAGING_URL/api/health/ai" || exit 1

# Document processing
curl -f "$STAGING_URL/api/health/processing" || exit 1

echo "All staging health checks passed!"
```

### 2. Production Deployment

#### Blue-Green Deployment Strategy
```bash
#!/bin/bash
# deploy-production.sh

set -e

CLUSTER_NAME="multimodal-librarian-prod"
SERVICE_NAME="multimodal-librarian-service"
NEW_TASK_DEF="multimodal-librarian-prod:${BUILD_NUMBER}"

echo "Starting production deployment with blue-green strategy..."

# 1. Create new task definition
echo "Creating new task definition..."
aws ecs register-task-definition \
    --cli-input-json file://task-definition-prod.json

# 2. Update service with new task definition
echo "Updating service with new task definition..."
aws ecs update-service \
    --cluster $CLUSTER_NAME \
    --service $SERVICE_NAME \
    --task-definition $NEW_TASK_DEF

# 3. Wait for new tasks to be running
echo "Waiting for new tasks to start..."
aws ecs wait services-stable \
    --cluster $CLUSTER_NAME \
    --services $SERVICE_NAME

# 4. Health check new deployment
echo "Running health checks on new deployment..."
./scripts/health-check.sh production

# 5. Gradually shift traffic (if using ALB with target groups)
echo "Gradually shifting traffic to new deployment..."
./scripts/shift-traffic.sh

# 6. Monitor for issues
echo "Monitoring deployment for 10 minutes..."
./scripts/monitor-deployment.sh 600

echo "Production deployment completed successfully!"
```

#### Database Migration Procedure
```python
# scripts/run-production-migration.py

import asyncio
import asyncpg
import logging
from alembic import command
from alembic.config import Config

async def run_production_migration():
    """Run database migration with safety checks."""
    
    # 1. Create database backup
    logging.info("Creating database backup...")
    backup_result = await create_database_backup()
    if not backup_result:
        raise Exception("Database backup failed")
    
    # 2. Test migration on backup
    logging.info("Testing migration on backup database...")
    test_result = await test_migration_on_backup()
    if not test_result:
        raise Exception("Migration test failed")
    
    # 3. Run migration with monitoring
    logging.info("Running production migration...")
    alembic_cfg = Config("alembic.ini")
    
    try:
        command.upgrade(alembic_cfg, "head")
        logging.info("Migration completed successfully")
    except Exception as e:
        logging.error(f"Migration failed: {e}")
        # Automatic rollback
        await rollback_migration()
        raise
    
    # 4. Verify migration
    logging.info("Verifying migration...")
    verification_result = await verify_migration()
    if not verification_result:
        await rollback_migration()
        raise Exception("Migration verification failed")
    
    logging.info("Production migration completed successfully")

async def create_database_backup():
    """Create full database backup before migration."""
    # Implementation for database backup
    pass

async def test_migration_on_backup():
    """Test migration on backup database."""
    # Implementation for migration testing
    pass

async def verify_migration():
    """Verify migration completed correctly."""
    # Implementation for migration verification
    pass

async def rollback_migration():
    """Rollback migration if issues occur."""
    # Implementation for migration rollback
    pass
```

### 3. Monitoring During Deployment

#### Real-time Monitoring Script
```python
# scripts/monitor-deployment.py

import asyncio
import aiohttp
import logging
from datetime import datetime, timedelta

class DeploymentMonitor:
    def __init__(self, environment: str):
        self.environment = environment
        self.base_url = self.get_base_url(environment)
        self.metrics = {
            "response_times": [],
            "error_rates": [],
            "health_checks": [],
            "resource_usage": []
        }
    
    async def monitor_deployment(self, duration_minutes: int):
        """Monitor deployment for specified duration."""
        end_time = datetime.now() + timedelta(minutes=duration_minutes)
        
        while datetime.now() < end_time:
            try:
                # Health checks
                health_status = await self.check_health()
                self.metrics["health_checks"].append(health_status)
                
                # Response time checks
                response_time = await self.check_response_time()
                self.metrics["response_times"].append(response_time)
                
                # Error rate monitoring
                error_rate = await self.check_error_rate()
                self.metrics["error_rates"].append(error_rate)
                
                # Resource usage
                resource_usage = await self.check_resource_usage()
                self.metrics["resource_usage"].append(resource_usage)
                
                # Alert on issues
                await self.check_for_alerts()
                
                await asyncio.sleep(30)  # Check every 30 seconds
                
            except Exception as e:
                logging.error(f"Monitoring error: {e}")
                await self.send_alert(f"Monitoring error: {e}")
    
    async def check_health(self):
        """Check application health endpoints."""
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(f"{self.base_url}/health") as response:
                    return {
                        "timestamp": datetime.now(),
                        "status_code": response.status,
                        "healthy": response.status == 200
                    }
            except Exception as e:
                return {
                    "timestamp": datetime.now(),
                    "status_code": 0,
                    "healthy": False,
                    "error": str(e)
                }
    
    async def check_response_time(self):
        """Check API response times."""
        start_time = datetime.now()
        
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(f"{self.base_url}/api/health") as response:
                    response_time = (datetime.now() - start_time).total_seconds()
                    return {
                        "timestamp": datetime.now(),
                        "response_time": response_time,
                        "status_code": response.status
                    }
            except Exception as e:
                return {
                    "timestamp": datetime.now(),
                    "response_time": None,
                    "error": str(e)
                }
    
    async def check_for_alerts(self):
        """Check if any alerts should be triggered."""
        # Check recent health checks
        recent_health = self.metrics["health_checks"][-5:]
        unhealthy_count = sum(1 for h in recent_health if not h.get("healthy", False))
        
        if unhealthy_count >= 3:
            await self.send_alert("Multiple health check failures detected")
        
        # Check response times
        recent_times = [r["response_time"] for r in self.metrics["response_times"][-10:] 
                      if r["response_time"] is not None]
        if recent_times and sum(recent_times) / len(recent_times) > 5.0:
            await self.send_alert("High response times detected")
        
        # Check error rates
        recent_errors = self.metrics["error_rates"][-5:]
        if recent_errors and sum(recent_errors) / len(recent_errors) > 0.05:
            await self.send_alert("High error rate detected")
    
    async def send_alert(self, message: str):
        """Send alert notification."""
        logging.error(f"DEPLOYMENT ALERT: {message}")
        # Implementation for sending alerts (Slack, email, etc.)
```

## Rollback Procedures

### Automatic Rollback Triggers
- Health check failures for >5 minutes
- Error rate >5% for >3 minutes
- Response time >10 seconds for >2 minutes
- Database connection failures
- Critical service unavailability

### Manual Rollback Process

#### 1. Immediate Rollback
```bash
#!/bin/bash
# rollback-immediate.sh

set -e

CLUSTER_NAME="multimodal-librarian-prod"
SERVICE_NAME="multimodal-librarian-service"
PREVIOUS_TASK_DEF="multimodal-librarian-prod:${PREVIOUS_BUILD_NUMBER}"

echo "Starting immediate rollback..."

# 1. Revert to previous task definition
echo "Reverting to previous task definition: $PREVIOUS_TASK_DEF"
aws ecs update-service \
    --cluster $CLUSTER_NAME \
    --service $SERVICE_NAME \
    --task-definition $PREVIOUS_TASK_DEF \
    --force-new-deployment

# 2. Wait for rollback to complete
echo "Waiting for rollback to complete..."
aws ecs wait services-stable \
    --cluster $CLUSTER_NAME \
    --services $SERVICE_NAME

# 3. Verify rollback
echo "Verifying rollback..."
./scripts/health-check.sh production

echo "Immediate rollback completed successfully!"
```

#### 2. Database Rollback
```python
# scripts/rollback-database.py

import asyncio
import logging
from alembic import command
from alembic.config import Config

async def rollback_database(target_revision: str = None):
    """Rollback database to previous state."""
    
    logging.info("Starting database rollback...")
    
    # 1. Stop application traffic to database
    await stop_application_traffic()
    
    # 2. Create current state backup
    backup_result = await create_rollback_backup()
    if not backup_result:
        raise Exception("Rollback backup failed")
    
    # 3. Perform rollback
    alembic_cfg = Config("alembic.ini")
    
    try:
        if target_revision:
            command.downgrade(alembic_cfg, target_revision)
        else:
            command.downgrade(alembic_cfg, "-1")  # Rollback one revision
        
        logging.info("Database rollback completed")
    except Exception as e:
        logging.error(f"Database rollback failed: {e}")
        # Restore from backup
        await restore_from_backup()
        raise
    
    # 4. Verify rollback
    verification_result = await verify_rollback()
    if not verification_result:
        await restore_from_backup()
        raise Exception("Rollback verification failed")
    
    # 5. Resume application traffic
    await resume_application_traffic()
    
    logging.info("Database rollback completed successfully")

async def stop_application_traffic():
    """Stop application traffic to database."""
    # Implementation to gracefully stop traffic
    pass

async def resume_application_traffic():
    """Resume application traffic to database."""
    # Implementation to resume traffic
    pass
```

### 3. Configuration Rollback
```bash
#!/bin/bash
# rollback-configuration.sh

set -e

echo "Starting configuration rollback..."

# 1. Restore environment variables
echo "Restoring environment variables..."
aws secretsmanager put-secret-value \
    --secret-id multimodal-librarian/config \
    --secret-string file://config-backup.json

# 2. Restore task definition
echo "Restoring task definition..."
aws ecs register-task-definition \
    --cli-input-json file://task-definition-backup.json

# 3. Update service
echo "Updating service with restored configuration..."
aws ecs update-service \
    --cluster multimodal-librarian-prod \
    --service multimodal-librarian-service \
    --task-definition multimodal-librarian-prod:backup \
    --force-new-deployment

echo "Configuration rollback completed!"
```

## Post-Deployment Procedures

### 1. Deployment Verification
```python
# scripts/post-deployment-verification.py

import asyncio
import aiohttp
import logging

class PostDeploymentVerifier:
    def __init__(self, environment: str):
        self.environment = environment
        self.base_url = self.get_base_url(environment)
    
    async def run_verification_suite(self):
        """Run comprehensive post-deployment verification."""
        
        results = {
            "health_checks": await self.verify_health_endpoints(),
            "api_functionality": await self.verify_api_endpoints(),
            "database_connectivity": await self.verify_database(),
            "ai_services": await self.verify_ai_services(),
            "document_processing": await self.verify_document_processing(),
            "performance": await self.verify_performance(),
            "security": await self.verify_security()
        }
        
        # Generate verification report
        await self.generate_verification_report(results)
        
        # Check if all verifications passed
        all_passed = all(result["passed"] for result in results.values())
        
        if not all_passed:
            await self.send_verification_alert(results)
            raise Exception("Post-deployment verification failed")
        
        logging.info("All post-deployment verifications passed")
        return results
    
    async def verify_health_endpoints(self):
        """Verify all health check endpoints."""
        endpoints = [
            "/health",
            "/api/health",
            "/api/health/database",
            "/api/health/ai",
            "/api/health/processing"
        ]
        
        results = []
        for endpoint in endpoints:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(f"{self.base_url}{endpoint}") as response:
                        results.append({
                            "endpoint": endpoint,
                            "status": response.status,
                            "passed": response.status == 200
                        })
            except Exception as e:
                results.append({
                    "endpoint": endpoint,
                    "error": str(e),
                    "passed": False
                })
        
        return {
            "passed": all(r["passed"] for r in results),
            "details": results
        }
    
    async def verify_api_endpoints(self):
        """Verify critical API endpoints."""
        # Implementation for API endpoint verification
        pass
    
    async def verify_performance(self):
        """Verify performance meets requirements."""
        # Implementation for performance verification
        pass
```

### 2. Monitoring Setup
```python
# scripts/setup-post-deployment-monitoring.py

import boto3
import json

def setup_cloudwatch_alarms():
    """Set up CloudWatch alarms for new deployment."""
    
    cloudwatch = boto3.client('cloudwatch')
    
    # CPU utilization alarm
    cloudwatch.put_metric_alarm(
        AlarmName='MultimodalLibrarian-HighCPU',
        ComparisonOperator='GreaterThanThreshold',
        EvaluationPeriods=2,
        MetricName='CPUUtilization',
        Namespace='AWS/ECS',
        Period=300,
        Statistic='Average',
        Threshold=80.0,
        ActionsEnabled=True,
        AlarmActions=[
            'arn:aws:sns:us-east-1:123456789012:multimodal-librarian-alerts'
        ],
        AlarmDescription='Alert when CPU exceeds 80%',
        Dimensions=[
            {
                'Name': 'ServiceName',
                'Value': 'multimodal-librarian-service'
            },
            {
                'Name': 'ClusterName',
                'Value': 'multimodal-librarian-prod'
            }
        ]
    )
    
    # Memory utilization alarm
    cloudwatch.put_metric_alarm(
        AlarmName='MultimodalLibrarian-HighMemory',
        ComparisonOperator='GreaterThanThreshold',
        EvaluationPeriods=2,
        MetricName='MemoryUtilization',
        Namespace='AWS/ECS',
        Period=300,
        Statistic='Average',
        Threshold=85.0,
        ActionsEnabled=True,
        AlarmActions=[
            'arn:aws:sns:us-east-1:123456789012:multimodal-librarian-alerts'
        ],
        AlarmDescription='Alert when memory exceeds 85%'
    )
    
    # Error rate alarm
    cloudwatch.put_metric_alarm(
        AlarmName='MultimodalLibrarian-HighErrorRate',
        ComparisonOperator='GreaterThanThreshold',
        EvaluationPeriods=2,
        MetricName='4XXError',
        Namespace='AWS/ApplicationELB',
        Period=300,
        Statistic='Sum',
        Threshold=10.0,
        ActionsEnabled=True,
        AlarmActions=[
            'arn:aws:sns:us-east-1:123456789012:multimodal-librarian-alerts'
        ],
        AlarmDescription='Alert when error rate is high'
    )
```

## Emergency Procedures

### 1. Emergency Rollback
```bash
#!/bin/bash
# emergency-rollback.sh

set -e

echo "EMERGENCY ROLLBACK INITIATED"

# Immediate service rollback
aws ecs update-service \
    --cluster multimodal-librarian-prod \
    --service multimodal-librarian-service \
    --task-definition multimodal-librarian-prod:emergency-stable \
    --force-new-deployment

# Stop all processing queues
redis-cli -h production-redis.cluster.amazonaws.com FLUSHALL

# Send emergency notifications
./scripts/send-emergency-notification.sh "Emergency rollback initiated"

echo "Emergency rollback completed"
```

### 2. Disaster Recovery
```bash
#!/bin/bash
# disaster-recovery.sh

set -e

echo "DISASTER RECOVERY INITIATED"

# 1. Restore from latest backup
./scripts/restore-from-backup.sh latest

# 2. Recreate infrastructure if needed
terraform apply -var-file="disaster-recovery.tfvars"

# 3. Deploy last known good version
./scripts/deploy-emergency-version.sh

# 4. Verify recovery
./scripts/verify-disaster-recovery.sh

echo "Disaster recovery completed"
```

## Documentation and Communication

### Deployment Checklist Template
```markdown
# Deployment Checklist - [Date] - [Version]

## Pre-Deployment
- [ ] Code review completed
- [ ] Tests passing
- [ ] Security scan clean
- [ ] Database migration tested
- [ ] Backup created
- [ ] Rollback plan ready

## Deployment
- [ ] Staging deployment successful
- [ ] Production deployment initiated
- [ ] Health checks passing
- [ ] Performance metrics normal
- [ ] Error rates acceptable

## Post-Deployment
- [ ] Verification suite passed
- [ ] Monitoring configured
- [ ] Documentation updated
- [ ] Team notified
- [ ] Stakeholders informed

## Issues Encountered
- [ ] None / [List any issues]

## Rollback Required
- [ ] No / Yes - [Reason and actions taken]
```

### Communication Templates

#### Deployment Notification
```
Subject: [PROD] Multimodal Librarian Deployment - v[VERSION]

Team,

Production deployment of Multimodal Librarian v[VERSION] has been completed successfully.

Deployment Details:
- Start Time: [TIME]
- End Time: [TIME]
- Duration: [DURATION]
- Downtime: [DOWNTIME/None]

Changes Included:
- [List major changes]

Verification Status:
- Health Checks: ✅ Passed
- Performance: ✅ Normal
- Error Rates: ✅ Acceptable

Monitoring:
- Dashboard: [LINK]
- Alerts: Configured and active

Next Steps:
- Continue monitoring for 24 hours
- User feedback collection active
- Next deployment scheduled for [DATE]

Contact [NAME] for any issues or questions.
```

This comprehensive deployment and rollback procedure ensures safe, reliable deployments with quick recovery capabilities when issues arise.