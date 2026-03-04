#!/usr/bin/env python3
"""
Fix the old database password issue by:
1. Generating a new secure password
2. Updating the RDS master password
3. Updating the Secrets Manager secret
4. Redeploying the ECS service
"""

import boto3
import json
import secrets
import string
import time
from datetime import datetime

REGION = 'us-east-1'
OLD_DB_INSTANCE = 'ml-librarian-postgres-prod'
SECRET_NAME = 'multimodal-librarian/learning/database'
CLUSTER_NAME = 'multimodal-lib-prod-cluster'
SERVICE_NAME = 'multimodal-lib-prod-service-alb'

rds = boto3.client('rds', region_name=REGION)
secretsmanager = boto3.client('secretsmanager', region_name=REGION)
ecs = boto3.client('ecs', region_name=REGION)

def generate_secure_password(length=32):
    """Generate a secure random password"""
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
    password = ''.join(secrets.choice(alphabet) for _ in range(length))
    return password

def update_rds_password(new_password):
    """Update the RDS master password"""
    print("\n" + "=" * 70)
    print("STEP 1: UPDATING RDS MASTER PASSWORD")
    print("=" * 70)
    
    print(f"\n🔐 Updating password for database: {OLD_DB_INSTANCE}")
    print("   This will take a few minutes...")
    
    try:
        response = rds.modify_db_instance(
            DBInstanceIdentifier=OLD_DB_INSTANCE,
            MasterUserPassword=new_password,
            ApplyImmediately=True
        )
        
        print(f"   ✓ Password update initiated")
        print(f"   Status: {response['DBInstance']['DBInstanceStatus']}")
        
        # Wait for the modification to complete
        print("\n⏳ Waiting for password update to complete...")
        waiter = rds.get_waiter('db_instance_available')
        waiter.wait(
            DBInstanceIdentifier=OLD_DB_INSTANCE,
            WaiterConfig={'Delay': 30, 'MaxAttempts': 20}
        )
        
        print("   ✅ Password updated successfully!")
        return True
        
    except Exception as e:
        print(f"   ❌ Failed to update password: {str(e)}")
        return False

def update_secrets_manager(new_password):
    """Update the Secrets Manager secret with new password"""
    print("\n" + "=" * 70)
    print("STEP 2: UPDATING SECRETS MANAGER")
    print("=" * 70)
    
    print(f"\n🔐 Updating secret: {SECRET_NAME}")
    
    # Create new secret value
    secret_value = {
        "username": "postgres",
        "password": new_password,
        "engine": "postgres",
        "host": "ml-librarian-postgres-prod.cq1iiac2gfkf.us-east-1.rds.amazonaws.com",
        "port": 5432,
        "dbname": "multimodal_librarian",
        "dbInstanceIdentifier": OLD_DB_INSTANCE
    }
    
    try:
        response = secretsmanager.update_secret(
            SecretId=SECRET_NAME,
            SecretString=json.dumps(secret_value)
        )
        
        print(f"   ✓ Secret updated successfully")
        print(f"   ARN: {response['ARN']}")
        print(f"   Version: {response['VersionId']}")
        return True
        
    except Exception as e:
        print(f"   ❌ Failed to update secret: {str(e)}")
        return False

def force_service_redeploy():
    """Force ECS service to redeploy with new secret"""
    print("\n" + "=" * 70)
    print("STEP 3: REDEPLOYING ECS SERVICE")
    print("=" * 70)
    
    print(f"\n🚀 Forcing service redeploy: {SERVICE_NAME}")
    
    try:
        response = ecs.update_service(
            cluster=CLUSTER_NAME,
            service=SERVICE_NAME,
            forceNewDeployment=True
        )
        
        print(f"   ✓ Redeploy initiated")
        print(f"   Deployment ID: {response['service']['deployments'][0]['id']}")
        
        # Wait a bit for new tasks to start
        print("\n⏳ Waiting for new tasks to start (30 seconds)...")
        time.sleep(30)
        
        print("   ✅ Service redeployment in progress")
        return True
        
    except Exception as e:
        print(f"   ❌ Failed to redeploy service: {str(e)}")
        return False

def verify_database_connection():
    """Verify the database connection works"""
    print("\n" + "=" * 70)
    print("STEP 4: VERIFICATION")
    print("=" * 70)
    
    print("\n🔍 Checking if new tasks can connect to database...")
    print("   (This may take a few minutes for tasks to start)")
    
    # Get the new task
    time.sleep(30)  # Wait for task to start
    
    tasks = ecs.list_tasks(
        cluster=CLUSTER_NAME,
        serviceName=SERVICE_NAME,
        desiredStatus='RUNNING'
    )
    
    if tasks['taskArns']:
        print(f"   ✓ Found {len(tasks['taskArns'])} running task(s)")
        print("   Check logs to verify database connection")
    else:
        print("   ⚠️  No running tasks found yet")

def main():
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    
    print("=" * 70)
    print("FIX OLD DATABASE PASSWORD")
    print("=" * 70)
    print("\nThis script will:")
    print("1. Generate a new secure password")
    print("2. Update the RDS master password")
    print("3. Update Secrets Manager with new password")
    print("4. Force ECS service redeploy")
    
    # Generate new password
    print("\n🔐 Generating new secure password...")
    new_password = generate_secure_password()
    print(f"   ✓ Generated password: {new_password[:5]}...{new_password[-5:]}")
    
    # Save password to file for backup
    backup_file = f'database-password-backup-{timestamp}.txt'
    with open(backup_file, 'w') as f:
        f.write(f"Database: {OLD_DB_INSTANCE}\n")
        f.write(f"Username: postgres\n")
        f.write(f"Password: {new_password}\n")
        f.write(f"Timestamp: {timestamp}\n")
    
    print(f"   ✓ Password backed up to: {backup_file}")
    
    # Confirm before proceeding
    print("\n⚠️  WARNING: This will change the database password!")
    print("   Press Ctrl+C to cancel, or Enter to continue...")
    try:
        input()
    except KeyboardInterrupt:
        print("\n\n❌ Cancelled by user")
        return 1
    
    # Update RDS password
    if not update_rds_password(new_password):
        print("\n❌ Failed to update RDS password")
        return 1
    
    # Update Secrets Manager
    if not update_secrets_manager(new_password):
        print("\n❌ Failed to update Secrets Manager")
        return 1
    
    # Redeploy service
    if not force_service_redeploy():
        print("\n❌ Failed to redeploy service")
        return 1
    
    # Verify
    verify_database_connection()
    
    print("\n" + "=" * 70)
    print("✅ DATABASE PASSWORD FIX COMPLETED")
    print("=" * 70)
    print(f"\n📊 Summary:")
    print(f"   • Database: {OLD_DB_INSTANCE}")
    print(f"   • Password: Updated (backed up to {backup_file})")
    print(f"   • Secret: {SECRET_NAME}")
    print(f"   • Service: Redeploying")
    print(f"\n🔗 Next steps:")
    print(f"   1. Wait 2-3 minutes for tasks to start")
    print(f"   2. Check logs: python3 scripts/get-container-logs.py")
    print(f"   3. Test health endpoint")
    print(f"   4. Verify ALB target health")
    
    return 0

if __name__ == '__main__':
    exit(main())
