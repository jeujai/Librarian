# Rollback Procedures and Emergency Response

This document provides detailed rollback procedures and emergency response protocols for the Multimodal Librarian system.

## Rollback Strategy Overview

### Rollback Types
1. **Application Rollback**: Revert to previous application version
2. **Database Rollback**: Revert database schema and data changes
3. **Configuration Rollback**: Revert environment and configuration changes
4. **Infrastructure Rollback**: Revert infrastructure changes
5. **Emergency Rollback**: Immediate system restoration

### Rollback Decision Matrix

| Issue Type | Severity | Rollback Type | Timeline | Approval Required |
|------------|----------|---------------|----------|-------------------|
| Application Bug | Low | Application | 30 minutes | Team Lead |
| Performance Degradation | Medium | Application | 15 minutes | Team Lead |
| Data Corruption | High | Database + Application | 10 minutes | Engineering Manager |
| Security Breach | Critical | Emergency | 5 minutes | On-call Engineer |
| System Outage | Critical | Emergency | 2 minutes | On-call Engineer |

## Application Rollback Procedures

### 1. ECS Service Rollback

#### Automated Rollback Script
```bash
#!/bin/bash
# rollback-application.sh

set -e

CLUSTER_NAME="${1:-multimodal-librarian-prod}"
SERVICE_NAME="${2:-multimodal-librarian-service}"
TARGET_REVISION="${3:-previous}"

echo "Starting application rollback for $SERVICE_NAME in $CLUSTER_NAME"

# Get current task definition
CURRENT_TASK_DEF=$(aws ecs describe-services \
    --cluster $CLUSTER_NAME \
    --services $SERVICE_NAME \
    --query 'services[0].taskDefinition' \
    --output text)

echo "Current task definition: $CURRENT_TASK_DEF"

# Get previous task definition
if [ "$TARGET_REVISION" = "previous" ]; then
    TASK_DEF_FAMILY=$(echo $CURRENT_TASK_DEF | cut -d':' -f1)
    CURRENT_REVISION=$(echo $CURRENT_TASK_DEF | cut -d':' -f2)
    PREVIOUS_REVISION=$((CURRENT_REVISION - 1))
    TARGET_TASK_DEF="$TASK_DEF_FAMILY:$PREVIOUS_REVISION"
else
    TARGET_TASK_DEF="$TARGET_REVISION"
fi

echo "Rolling back to: $TARGET_TASK_DEF"

# Verify target task definition exists
aws ecs describe-task-definition \
    --task-definition $TARGET_TASK_DEF \
    --query 'taskDefinition.taskDefinitionArn' \
    --output text > /dev/null

if [ $? -ne 0 ]; then
    echo "ERROR: Target task definition $TARGET_TASK_DEF not found"
    exit 1
fi

# Create rollback backup of current state
echo "Creating rollback backup..."
aws ecs describe-task-definition \
    --task-definition $CURRENT_TASK_DEF \
    --query 'taskDefinition' > "rollback-backup-$(date +%Y%m%d-%H%M%S).json"

# Update service to previous task definition
echo "Updating service to previous task definition..."
aws ecs update-service \
    --cluster $CLUSTER_NAME \
    --service $SERVICE_NAME \
    --task-definition $TARGET_TASK_DEF \
    --force-new-deployment

# Wait for rollback to complete
echo "Waiting for rollback to complete..."
aws ecs wait services-stable \
    --cluster $CLUSTER_NAME \
    --services $SERVICE_NAME \
    --max-attempts 20 \
    --delay 30

# Verify rollback
echo "Verifying rollback..."
UPDATED_TASK_DEF=$(aws ecs describe-services \
    --cluster $CLUSTER_NAME \
    --services $SERVICE_NAME \
    --query 'services[0].taskDefinition' \
    --output text)

if [ "$UPDATED_TASK_DEF" = "$TARGET_TASK_DEF" ]; then
    echo "✅ Application rollback completed successfully"
    echo "Service is now running: $UPDATED_TASK_DEF"
else
    echo "❌ Rollback verification failed"
    echo "Expected: $TARGET_TASK_DEF"
    echo "Actual: $UPDATED_TASK_DEF"
    exit 1
fi

# Run health checks
echo "Running post-rollback health checks..."
./scripts/health-check.sh production

echo "Application rollback completed successfully!"
```

#### Blue-Green Rollback
```bash
#!/bin/bash
# rollback-blue-green.sh

set -e

LOAD_BALANCER_ARN="${1}"
TARGET_GROUP_BLUE="${2}"
TARGET_GROUP_GREEN="${3}"
CURRENT_ACTIVE="${4:-green}"

echo "Starting blue-green rollback..."

if [ "$CURRENT_ACTIVE" = "green" ]; then
    ROLLBACK_TARGET="$TARGET_GROUP_BLUE"
    echo "Rolling back from GREEN to BLUE"
else
    ROLLBACK_TARGET="$TARGET_GROUP_GREEN"
    echo "Rolling back from BLUE to GREEN"
fi

# Update load balancer to point to rollback target
aws elbv2 modify-listener \
    --listener-arn $(aws elbv2 describe-listeners \
        --load-balancer-arn $LOAD_BALANCER_ARN \
        --query 'Listeners[0].ListenerArn' \
        --output text) \
    --default-actions Type=forward,TargetGroupArn=$ROLLBACK_TARGET

echo "Traffic switched to rollback target: $ROLLBACK_TARGET"

# Wait for health checks
echo "Waiting for health checks to pass..."
sleep 60

# Verify rollback
./scripts/health-check.sh production

echo "Blue-green rollback completed successfully!"
```

### 2. Container Image Rollback

#### Docker Image Rollback
```python
# scripts/rollback-container-image.py

import boto3
import json
import logging
from datetime import datetime

class ContainerRollback:
    def __init__(self, cluster_name: str, service_name: str):
        self.ecs_client = boto3.client('ecs')
        self.ecr_client = boto3.client('ecr')
        self.cluster_name = cluster_name
        self.service_name = service_name
        
    def get_current_image(self):
        """Get currently deployed container image."""
        response = self.ecs_client.describe_services(
            cluster=self.cluster_name,
            services=[self.service_name]
        )
        
        task_def_arn = response['services'][0]['taskDefinition']
        
        task_def = self.ecs_client.describe_task_definition(
            taskDefinition=task_def_arn
        )
        
        container_def = task_def['taskDefinition']['containerDefinitions'][0]
        return container_def['image']
    
    def get_previous_images(self, limit: int = 10):
        """Get list of previous container images."""
        response = self.ecr_client.describe_images(
            repositoryName='multimodal-librarian',
            maxResults=limit,
            imageDetails=[
                {
                    'imageDigest': 'string',
                    'imageTags': ['string'],
                    'registryId': 'string',
                    'repositoryName': 'string',
                    'imagePushedAt': datetime(2015, 1, 1),
                    'imageSizeInBytes': 123
                }
            ]
        )
        
        # Sort by push date, most recent first
        images = sorted(
            response['imageDetails'],
            key=lambda x: x['imagePushedAt'],
            reverse=True
        )
        
        return images
    
    def rollback_to_image(self, target_image: str):
        """Rollback to specific container image."""
        logging.info(f"Rolling back to image: {target_image}")
        
        # Get current task definition
        current_service = self.ecs_client.describe_services(
            cluster=self.cluster_name,
            services=[self.service_name]
        )
        
        current_task_def_arn = current_service['services'][0]['taskDefinition']
        
        # Get task definition details
        task_def_response = self.ecs_client.describe_task_definition(
            taskDefinition=current_task_def_arn
        )
        
        task_def = task_def_response['taskDefinition']
        
        # Update container image
        for container in task_def['containerDefinitions']:
            if container['name'] == 'multimodal-librarian':
                container['image'] = target_image
        
        # Remove read-only fields
        for field in ['taskDefinitionArn', 'revision', 'status', 'requiresAttributes', 
                     'placementConstraints', 'compatibilities', 'registeredAt', 'registeredBy']:
            task_def.pop(field, None)
        
        # Register new task definition
        new_task_def = self.ecs_client.register_task_definition(**task_def)
        new_task_def_arn = new_task_def['taskDefinition']['taskDefinitionArn']
        
        # Update service
        self.ecs_client.update_service(
            cluster=self.cluster_name,
            service=self.service_name,
            taskDefinition=new_task_def_arn,
            forceNewDeployment=True
        )
        
        # Wait for deployment
        waiter = self.ecs_client.get_waiter('services_stable')
        waiter.wait(
            cluster=self.cluster_name,
            services=[self.service_name],
            WaiterConfig={
                'Delay': 30,
                'MaxAttempts': 20
            }
        )
        
        logging.info(f"Rollback to {target_image} completed successfully")
        return new_task_def_arn

# Usage example
if __name__ == "__main__":
    rollback = ContainerRollback(
        cluster_name="multimodal-librarian-prod",
        service_name="multimodal-librarian-service"
    )
    
    # Get previous images
    previous_images = rollback.get_previous_images()
    
    # Rollback to previous image (second in list, first is current)
    if len(previous_images) > 1:
        target_image = f"123456789012.dkr.ecr.us-east-1.amazonaws.com/multimodal-librarian:{previous_images[1]['imageTags'][0]}"
        rollback.rollback_to_image(target_image)
```

## Database Rollback Procedures

### 1. Schema Rollback with Alembic

#### Database Rollback Script
```python
# scripts/rollback-database.py

import asyncio
import asyncpg
import logging
import subprocess
import os
from datetime import datetime
from alembic import command
from alembic.config import Config

class DatabaseRollback:
    def __init__(self, database_url: str, alembic_config_path: str = "alembic.ini"):
        self.database_url = database_url
        self.alembic_config = Config(alembic_config_path)
        self.backup_dir = "database_backups"
        
    async def create_pre_rollback_backup(self):
        """Create backup before rollback."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_file = f"{self.backup_dir}/pre_rollback_backup_{timestamp}.sql"
        
        os.makedirs(self.backup_dir, exist_ok=True)
        
        # Create database dump
        cmd = [
            "pg_dump",
            self.database_url,
            "-f", backup_file,
            "--verbose",
            "--no-owner",
            "--no-privileges"
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            raise Exception(f"Backup failed: {result.stderr}")
        
        logging.info(f"Pre-rollback backup created: {backup_file}")
        return backup_file
    
    async def get_current_revision(self):
        """Get current database revision."""
        conn = await asyncpg.connect(self.database_url)
        try:
            result = await conn.fetchval(
                "SELECT version_num FROM alembic_version ORDER BY version_num DESC LIMIT 1"
            )
            return result
        finally:
            await conn.close()
    
    async def get_migration_history(self, limit: int = 10):
        """Get recent migration history."""
        conn = await asyncpg.connect(self.database_url)
        try:
            # This would need to be adapted based on your migration tracking
            result = await conn.fetch(
                """
                SELECT version_num, applied_at 
                FROM migration_history 
                ORDER BY applied_at DESC 
                LIMIT $1
                """,
                limit
            )
            return result
        except Exception:
            # Fallback if migration_history table doesn't exist
            return []
        finally:
            await conn.close()
    
    async def rollback_to_revision(self, target_revision: str):
        """Rollback database to specific revision."""
        logging.info(f"Starting database rollback to revision: {target_revision}")
        
        # Create pre-rollback backup
        backup_file = await self.create_pre_rollback_backup()
        
        try:
            # Stop application connections
            await self.stop_application_connections()
            
            # Perform rollback
            command.downgrade(self.alembic_config, target_revision)
            
            # Verify rollback
            current_revision = await self.get_current_revision()
            if current_revision != target_revision:
                raise Exception(f"Rollback verification failed. Expected: {target_revision}, Got: {current_revision}")
            
            logging.info(f"Database rollback completed successfully to revision: {target_revision}")
            
        except Exception as e:
            logging.error(f"Database rollback failed: {e}")
            # Attempt to restore from backup
            await self.restore_from_backup(backup_file)
            raise
        
        finally:
            # Resume application connections
            await self.resume_application_connections()
    
    async def rollback_one_revision(self):
        """Rollback database by one revision."""
        command.downgrade(self.alembic_config, "-1")
        logging.info("Database rolled back by one revision")
    
    async def stop_application_connections(self):
        """Stop application connections to database."""
        # Implementation depends on your connection pooling setup
        logging.info("Stopping application database connections...")
        
        # Example: Update ECS service to 0 desired count
        import boto3
        ecs = boto3.client('ecs')
        
        ecs.update_service(
            cluster='multimodal-librarian-prod',
            service='multimodal-librarian-service',
            desiredCount=0
        )
        
        # Wait for tasks to stop
        waiter = ecs.get_waiter('services_stable')
        waiter.wait(
            cluster='multimodal-librarian-prod',
            services=['multimodal-librarian-service']
        )
    
    async def resume_application_connections(self):
        """Resume application connections to database."""
        logging.info("Resuming application database connections...")
        
        import boto3
        ecs = boto3.client('ecs')
        
        ecs.update_service(
            cluster='multimodal-librarian-prod',
            service='multimodal-librarian-service',
            desiredCount=2  # Or your normal desired count
        )
    
    async def restore_from_backup(self, backup_file: str):
        """Restore database from backup file."""
        logging.info(f"Restoring database from backup: {backup_file}")
        
        # Drop and recreate database (be very careful with this!)
        cmd = [
            "psql",
            self.database_url,
            "-c", "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise Exception(f"Schema drop/create failed: {result.stderr}")
        
        # Restore from backup
        cmd = [
            "psql",
            self.database_url,
            "-f", backup_file
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise Exception(f"Backup restore failed: {result.stderr}")
        
        logging.info("Database restored from backup successfully")

# Usage example
async def main():
    rollback = DatabaseRollback(
        database_url="postgresql://user:pass@host:5432/dbname"
    )
    
    # Rollback to specific revision
    await rollback.rollback_to_revision("abc123def456")
    
    # Or rollback one revision
    # await rollback.rollback_one_revision()

if __name__ == "__main__":
    asyncio.run(main())
```

### 2. Data Rollback Procedures

#### Point-in-Time Recovery
```bash
#!/bin/bash
# point-in-time-recovery.sh

set -e

DB_INSTANCE_IDENTIFIER="multimodal-librarian-prod"
TARGET_TIME="${1}"  # Format: 2024-01-15T10:30:00Z
NEW_DB_IDENTIFIER="multimodal-librarian-recovery-$(date +%Y%m%d-%H%M%S)"

echo "Starting point-in-time recovery to: $TARGET_TIME"

# Create new DB instance from point-in-time
aws rds restore-db-instance-to-point-in-time \
    --source-db-instance-identifier $DB_INSTANCE_IDENTIFIER \
    --target-db-instance-identifier $NEW_DB_IDENTIFIER \
    --restore-time $TARGET_TIME \
    --db-instance-class db.t3.medium \
    --no-multi-az \
    --publicly-accessible

echo "Waiting for recovery instance to be available..."
aws rds wait db-instance-available \
    --db-instance-identifiers $NEW_DB_IDENTIFIER

# Get new endpoint
NEW_ENDPOINT=$(aws rds describe-db-instances \
    --db-instance-identifier $NEW_DB_IDENTIFIER \
    --query 'DBInstances[0].Endpoint.Address' \
    --output text)

echo "Recovery instance available at: $NEW_ENDPOINT"

# Update application configuration to use recovery instance
# This would typically involve updating secrets manager or environment variables

echo "Point-in-time recovery completed. New endpoint: $NEW_ENDPOINT"
echo "Remember to update application configuration and test thoroughly before switching traffic."
```

## Configuration Rollback

### 1. Environment Variables Rollback
```python
# scripts/rollback-configuration.py

import boto3
import json
import logging
from datetime import datetime

class ConfigurationRollback:
    def __init__(self):
        self.secrets_client = boto3.client('secretsmanager')
        self.ecs_client = boto3.client('ecs')
        
    def backup_current_config(self, secret_name: str):
        """Backup current configuration."""
        try:
            response = self.secrets_client.get_secret_value(SecretId=secret_name)
            current_config = response['SecretString']
            
            # Store backup with timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_secret_name = f"{secret_name}-backup-{timestamp}"
            
            self.secrets_client.create_secret(
                Name=backup_secret_name,
                SecretString=current_config,
                Description=f"Backup of {secret_name} created at {timestamp}"
            )
            
            logging.info(f"Configuration backed up to: {backup_secret_name}")
            return backup_secret_name
            
        except Exception as e:
            logging.error(f"Failed to backup configuration: {e}")
            raise
    
    def rollback_configuration(self, secret_name: str, backup_secret_name: str):
        """Rollback configuration from backup."""
        try:
            # Get backup configuration
            response = self.secrets_client.get_secret_value(SecretId=backup_secret_name)
            backup_config = response['SecretString']
            
            # Update current secret with backup
            self.secrets_client.update_secret(
                SecretId=secret_name,
                SecretString=backup_config
            )
            
            logging.info(f"Configuration rolled back from: {backup_secret_name}")
            
            # Force ECS service to restart with new configuration
            self.restart_ecs_service()
            
        except Exception as e:
            logging.error(f"Failed to rollback configuration: {e}")
            raise
    
    def restart_ecs_service(self):
        """Restart ECS service to pick up new configuration."""
        self.ecs_client.update_service(
            cluster='multimodal-librarian-prod',
            service='multimodal-librarian-service',
            forceNewDeployment=True
        )
        
        # Wait for service to stabilize
        waiter = self.ecs_client.get_waiter('services_stable')
        waiter.wait(
            cluster='multimodal-librarian-prod',
            services=['multimodal-librarian-service']
        )
        
        logging.info("ECS service restarted with rolled back configuration")

# Usage
config_rollback = ConfigurationRollback()

# Backup current config
backup_name = config_rollback.backup_current_config('multimodal-librarian/config')

# Rollback to previous backup
config_rollback.rollback_configuration('multimodal-librarian/config', 'multimodal-librarian/config-backup-20240115_103000')
```

## Emergency Rollback Procedures

### 1. Emergency Rollback Script
```bash
#!/bin/bash
# emergency-rollback.sh

set -e

echo "🚨 EMERGENCY ROLLBACK INITIATED 🚨"
echo "Timestamp: $(date)"

# Log emergency rollback
echo "Emergency rollback initiated at $(date)" >> /var/log/emergency-rollback.log

# 1. Immediate application rollback to last known good version
echo "Step 1: Rolling back application to emergency stable version..."
aws ecs update-service \
    --cluster multimodal-librarian-prod \
    --service multimodal-librarian-service \
    --task-definition multimodal-librarian-prod:emergency-stable \
    --force-new-deployment

# 2. Stop all background processing
echo "Step 2: Stopping background processing..."
redis-cli -h production-redis.cluster.amazonaws.com FLUSHALL

# 3. Put system in maintenance mode
echo "Step 3: Enabling maintenance mode..."
aws secretsmanager update-secret \
    --secret-id multimodal-librarian/config \
    --secret-string '{"MAINTENANCE_MODE": "true", "MAINTENANCE_MESSAGE": "System under emergency maintenance"}'

# 4. Send emergency notifications
echo "Step 4: Sending emergency notifications..."
./scripts/send-emergency-notification.sh "Emergency rollback initiated - system in maintenance mode"

# 5. Wait for rollback to complete
echo "Step 5: Waiting for rollback to complete..."
aws ecs wait services-stable \
    --cluster multimodal-librarian-prod \
    --services multimodal-librarian-service \
    --max-attempts 10 \
    --delay 30

# 6. Basic health check
echo "Step 6: Running basic health check..."
if curl -f -s http://internal-load-balancer/health > /dev/null; then
    echo "✅ Basic health check passed"
else
    echo "❌ Basic health check failed - manual intervention required"
    exit 1
fi

echo "🚨 EMERGENCY ROLLBACK COMPLETED 🚨"
echo "System is in maintenance mode. Manual verification required before resuming normal operations."
```

### 2. Disaster Recovery Rollback
```bash
#!/bin/bash
# disaster-recovery-rollback.sh

set -e

echo "🔥 DISASTER RECOVERY ROLLBACK INITIATED 🔥"

# 1. Restore from latest backup
echo "Restoring from latest backup..."
./scripts/restore-from-backup.sh latest

# 2. Recreate infrastructure from known good state
echo "Recreating infrastructure..."
cd infrastructure/
terraform workspace select disaster-recovery
terraform apply -var-file="disaster-recovery.tfvars" -auto-approve

# 3. Deploy emergency version
echo "Deploying emergency version..."
./scripts/deploy-emergency-version.sh

# 4. Verify disaster recovery
echo "Verifying disaster recovery..."
./scripts/verify-disaster-recovery.sh

# 5. Send disaster recovery notifications
echo "Sending disaster recovery notifications..."
./scripts/send-disaster-notification.sh "Disaster recovery rollback completed"

echo "🔥 DISASTER RECOVERY ROLLBACK COMPLETED 🔥"
```

## Rollback Verification

### 1. Post-Rollback Verification Script
```python
# scripts/verify-rollback.py

import asyncio
import aiohttp
import logging
import json
from datetime import datetime

class RollbackVerifier:
    def __init__(self, environment: str = "production"):
        self.environment = environment
        self.base_url = self.get_base_url(environment)
        
    async def verify_rollback(self):
        """Comprehensive rollback verification."""
        verification_results = {
            "timestamp": datetime.now().isoformat(),
            "environment": self.environment,
            "tests": {}
        }
        
        # Health checks
        verification_results["tests"]["health"] = await self.verify_health()
        
        # API functionality
        verification_results["tests"]["api"] = await self.verify_api_functionality()
        
        # Database connectivity
        verification_results["tests"]["database"] = await self.verify_database()
        
        # Performance checks
        verification_results["tests"]["performance"] = await self.verify_performance()
        
        # Data integrity
        verification_results["tests"]["data_integrity"] = await self.verify_data_integrity()
        
        # Generate report
        overall_success = all(
            test_result.get("passed", False) 
            for test_result in verification_results["tests"].values()
        )
        
        verification_results["overall_success"] = overall_success
        
        # Save verification report
        with open(f"rollback-verification-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json", "w") as f:
            json.dump(verification_results, f, indent=2)
        
        if overall_success:
            logging.info("✅ Rollback verification passed")
        else:
            logging.error("❌ Rollback verification failed")
            await self.send_verification_failure_alert(verification_results)
        
        return verification_results
    
    async def verify_health(self):
        """Verify system health endpoints."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.base_url}/health") as response:
                    if response.status == 200:
                        health_data = await response.json()
                        return {
                            "passed": True,
                            "status_code": response.status,
                            "response_data": health_data
                        }
                    else:
                        return {
                            "passed": False,
                            "status_code": response.status,
                            "error": "Health check returned non-200 status"
                        }
        except Exception as e:
            return {
                "passed": False,
                "error": str(e)
            }
    
    async def verify_api_functionality(self):
        """Verify critical API endpoints."""
        endpoints_to_test = [
            "/api/health",
            "/api/health/database",
            "/api/health/ai",
            "/api/documents",
            "/api/chat/health"
        ]
        
        results = []
        
        async with aiohttp.ClientSession() as session:
            for endpoint in endpoints_to_test:
                try:
                    async with session.get(f"{self.base_url}{endpoint}") as response:
                        results.append({
                            "endpoint": endpoint,
                            "status_code": response.status,
                            "passed": response.status == 200
                        })
                except Exception as e:
                    results.append({
                        "endpoint": endpoint,
                        "error": str(e),
                        "passed": False
                    })
        
        overall_passed = all(result["passed"] for result in results)
        
        return {
            "passed": overall_passed,
            "endpoint_results": results
        }
    
    async def verify_performance(self):
        """Verify system performance meets requirements."""
        # Implementation for performance verification
        # This would test response times, throughput, etc.
        pass
    
    async def send_verification_failure_alert(self, results):
        """Send alert when verification fails."""
        # Implementation for sending alerts
        pass

# Usage
async def main():
    verifier = RollbackVerifier("production")
    results = await verifier.verify_rollback()
    
    if results["overall_success"]:
        print("Rollback verification successful!")
    else:
        print("Rollback verification failed!")
        exit(1)

if __name__ == "__main__":
    asyncio.run(main())
```

## Communication and Documentation

### Rollback Communication Template
```
Subject: [URGENT] Production Rollback Completed - Multimodal Librarian

Team,

A production rollback has been completed for the Multimodal Librarian system.

ROLLBACK DETAILS:
- Initiated: [TIMESTAMP]
- Completed: [TIMESTAMP]
- Duration: [DURATION]
- Rollback Type: [Application/Database/Configuration/Emergency]
- Target Version: [VERSION/REVISION]

REASON FOR ROLLBACK:
[Detailed explanation of the issue that triggered the rollback]

IMPACT:
- User Impact: [Description of user-facing impact]
- Downtime: [Duration of any downtime]
- Data Loss: [Any data loss or corruption]

VERIFICATION STATUS:
- Health Checks: [✅/❌] [Details]
- API Functionality: [✅/❌] [Details]
- Database Integrity: [✅/❌] [Details]
- Performance: [✅/❌] [Details]

NEXT STEPS:
1. [Immediate actions required]
2. [Investigation tasks]
3. [Prevention measures]
4. [Timeline for resolution]

MONITORING:
- Dashboard: [Link to monitoring dashboard]
- Alerts: [Status of alerting systems]

For questions or concerns, contact:
- On-call Engineer: [Contact info]
- Engineering Manager: [Contact info]
- Incident Commander: [Contact info]

Post-mortem meeting scheduled for: [Date/Time]
```

This comprehensive rollback procedure ensures quick, safe recovery from deployment issues while maintaining system integrity and minimizing user impact.