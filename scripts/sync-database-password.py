#!/usr/bin/env python3
"""
Sync RDS database password with Secrets Manager

The secret was updated but the RDS password was not changed to match.
This script will update the RDS password to match what's in Secrets Manager.
"""

import boto3
import json

REGION = 'us-east-1'
DB_IDENTIFIER = 'ml-librarian-postgres-prod'
SECRET_ARN = 'arn:aws:secretsmanager:us-east-1:591222106065:secret:multimodal-librarian/learning/database-TSnLsl'

secrets = boto3.client('secretsmanager', region_name=REGION)
rds = boto3.client('rds', region_name=REGION)

print("="*80)
print("SYNC RDS PASSWORD WITH SECRETS MANAGER")
print("="*80)

# Get password from Secrets Manager
print("\n1. Getting password from Secrets Manager...")
try:
    secret_value = secrets.get_secret_value(SecretId=SECRET_ARN)
    secret_data = json.loads(secret_value['SecretString'])
    password = secret_data['password']
    
    print(f"✅ Retrieved password from secret")
    print(f"   Secret: multimodal-librarian/learning/database")
    print(f"   Password length: {len(password)} characters")
    print(f"   Password preview: {password[:3]}...{password[-3:]}")
    
except Exception as e:
    print(f"❌ Error: {e}")
    exit(1)

# Check RDS database
print("\n2. Checking RDS database...")
try:
    db = rds.describe_db_instances(DBInstanceIdentifier=DB_IDENTIFIER)
    db_instance = db['DBInstances'][0]
    
    print(f"✅ Database found")
    print(f"   Database: {DB_IDENTIFIER}")
    print(f"   Status: {db_instance['DBInstanceStatus']}")
    print(f"   Endpoint: {db_instance['Endpoint']['Address']}")
    
except Exception as e:
    print(f"❌ Error: {e}")
    exit(1)

# Confirm update
print("\n" + "="*80)
print("⚠️  WARNING: This will change the RDS master password")
print("="*80)
print(f"\nDatabase: {DB_IDENTIFIER}")
print(f"New password will match: multimodal-librarian/learning/database secret")
print(f"\nThis will:")
print(f"  1. Update the RDS master password")
print(f"  2. Cause a brief connection interruption")
print(f"  3. Allow the application to connect successfully")

response = input("\nProceed with password update? (yes/no): ")

if response.lower() != 'yes':
    print("❌ Cancelled")
    exit(1)

# Update RDS password
print("\n3. Updating RDS master password...")
try:
    response = rds.modify_db_instance(
        DBInstanceIdentifier=DB_IDENTIFIER,
        MasterUserPassword=password,
        ApplyImmediately=True
    )
    
    print(f"✅ Password update initiated")
    print(f"   Database: {DB_IDENTIFIER}")
    print(f"   Status: {response['DBInstance']['DBInstanceStatus']}")
    print(f"   Apply Immediately: True")
    
    print(f"\n💡 The password change will take effect immediately")
    print(f"   There may be a brief connection interruption")
    
except Exception as e:
    print(f"❌ Error updating password: {e}")
    exit(1)

# Force ECS service to restart tasks
print("\n4. Restarting ECS tasks to pick up new password...")
ecs = boto3.client('ecs', region_name=REGION)

try:
    response = ecs.update_service(
        cluster='multimodal-lib-prod-cluster',
        service='multimodal-lib-prod-service-alb',
        forceNewDeployment=True
    )
    
    print(f"✅ ECS service deployment initiated")
    print(f"   Service: multimodal-lib-prod-service-alb")
    print(f"   New tasks will use the updated password")
    
except Exception as e:
    print(f"⚠️  Warning: Could not restart ECS service: {e}")
    print(f"   You may need to manually restart the service")

print("\n" + "="*80)
print("PASSWORD SYNC COMPLETE")
print("="*80)
print("\n✅ RDS password updated to match Secrets Manager")
print("✅ ECS service redeployment initiated")
print("\nNext steps:")
print("  1. Wait 2-3 minutes for tasks to restart")
print("  2. Check logs: python3 scripts/verify-aws-database-connectivity.py")
print("  3. Verify no more password authentication errors")

