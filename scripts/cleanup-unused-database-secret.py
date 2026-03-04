#!/usr/bin/env python3
"""
Clean up unused database secret

The full-ml/database secret points to a database we're not using.
We're using ml-librarian-postgres-prod with the learning/database secret.
"""

import boto3
import json

REGION = 'us-east-1'

# Secret to DELETE (points to unused database)
UNUSED_SECRET_ARN = 'arn:aws:secretsmanager:us-east-1:591222106065:secret:multimodal-librarian/full-ml/database-OxpSTB'

# Secret to KEEP (points to ml-librarian-postgres-prod)
ACTIVE_SECRET_ARN = 'arn:aws:secretsmanager:us-east-1:591222106065:secret:multimodal-librarian/learning/database-TSnLsl'

secrets = boto3.client('secretsmanager', region_name=REGION)

print("="*80)
print("DATABASE SECRET CLEANUP")
print("="*80)

# Show what we're keeping
print("\n✅ KEEPING (Active Production Database):")
print("-"*80)
try:
    secret_value = secrets.get_secret_value(SecretId=ACTIVE_SECRET_ARN)
    secret_data = json.loads(secret_value['SecretString'])
    print(f"Secret: multimodal-librarian/learning/database")
    print(f"  Database: {secret_data['dbInstanceIdentifier']}")
    print(f"  Host: {secret_data['host']}")
    print(f"  This is the database currently in use by ECS tasks")
except Exception as e:
    print(f"❌ Error: {e}")

# Show what we're deleting
print("\n❌ DELETING (Unused Database):")
print("-"*80)
try:
    secret_value = secrets.get_secret_value(SecretId=UNUSED_SECRET_ARN)
    secret_data = json.loads(secret_value['SecretString'])
    print(f"Secret: multimodal-librarian/full-ml/database")
    print(f"  Database: {secret_data['dbInstanceIdentifier']}")
    print(f"  Host: {secret_data['host']}")
    print(f"  This database is NOT being used by any ECS tasks")
except Exception as e:
    print(f"❌ Error: {e}")

# Confirm deletion
print("\n" + "="*80)
response = input("Delete the unused full-ml/database secret? (yes/no): ")

if response.lower() != 'yes':
    print("❌ Cancelled")
    exit(1)

# Delete the secret
print("\n🗑️  Deleting secret...")
try:
    # Delete with recovery window (can be restored within 30 days)
    response = secrets.delete_secret(
        SecretId=UNUSED_SECRET_ARN,
        RecoveryWindowInDays=30
    )
    
    print(f"✅ Secret deleted successfully")
    print(f"   Deletion Date: {response['DeletionDate']}")
    print(f"   ARN: {response['ARN']}")
    print(f"\n💡 The secret can be restored within 30 days if needed")
    
except Exception as e:
    print(f"❌ Error deleting secret: {e}")
    exit(1)

print("\n" + "="*80)
print("CLEANUP COMPLETE")
print("="*80)
print("\n✅ Unused database secret has been deleted")
print("✅ Active production database secret remains intact")
print("\nCurrent configuration:")
print(f"  Database: ml-librarian-postgres-prod")
print(f"  Secret: multimodal-librarian/learning/database")
print(f"  Status: Active and in use by ECS tasks")

