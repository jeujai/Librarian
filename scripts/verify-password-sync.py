#!/usr/bin/env python3
"""
Verify if RDS password and Secrets Manager are in sync
"""

import boto3
import json

REGION = 'us-east-1'
DB_IDENTIFIER = 'ml-librarian-postgres-prod'

# Secret ARNs from task definition
SECRET_ARNS = [
    'arn:aws:secretsmanager:us-east-1:591222106065:secret:multimodal-librarian/full-ml/database-OxpSTB',
    'arn:aws:secretsmanager:us-east-1:591222106065:secret:multimodal-librarian/learning/database-TSnLsl'
]

secrets = boto3.client('secretsmanager', region_name=REGION)
rds = boto3.client('rds', region_name=REGION)

print("="*80)
print("PASSWORD SYNCHRONIZATION VERIFICATION")
print("="*80)

# Check RDS database
print("\n1. RDS DATABASE INFO")
print("-"*80)
try:
    db = rds.describe_db_instances(DBInstanceIdentifier=DB_IDENTIFIER)
    db_instance = db['DBInstances'][0]
    print(f"Database: {DB_IDENTIFIER}")
    print(f"Status: {db_instance['DBInstanceStatus']}")
    print(f"Master Username: {db_instance['MasterUsername']}")
    print(f"Endpoint: {db_instance['Endpoint']['Address']}")
    
    # Check when password was last modified
    print(f"\nInstance Created: {db_instance.get('InstanceCreateTime', 'N/A')}")
    
except Exception as e:
    print(f"❌ Error: {e}")

# Check Secrets Manager
print("\n2. SECRETS MANAGER SECRETS")
print("-"*80)

for secret_arn in SECRET_ARNS:
    secret_name = secret_arn.split(':')[-1]
    print(f"\nSecret: {secret_name}")
    
    try:
        # Get secret metadata
        metadata = secrets.describe_secret(SecretId=secret_arn)
        print(f"  Last Changed: {metadata.get('LastChangedDate', 'N/A')}")
        print(f"  Last Accessed: {metadata.get('LastAccessedDate', 'N/A')}")
        
        # Get secret value
        secret_value = secrets.get_secret_value(SecretId=secret_arn)
        
        if 'SecretString' in secret_value:
            secret_data = json.loads(secret_value['SecretString'])
            
            # Show what keys are in the secret
            print(f"  Keys in secret: {list(secret_data.keys())}")
            
            # Check if password exists
            if 'password' in secret_data:
                password = secret_data['password']
                print(f"  Password length: {len(password)} characters")
                print(f"  Password preview: {password[:3]}...{password[-3:]}")
            else:
                print(f"  ⚠️  No 'password' key found!")
                
        else:
            print(f"  ⚠️  Secret is binary, not string")
            
    except Exception as e:
        print(f"  ❌ Error: {e}")

# Check CloudTrail for recent password changes
print("\n3. RECENT PASSWORD CHANGE EVENTS")
print("-"*80)

cloudtrail = boto3.client('cloudtrail', region_name=REGION)

try:
    from datetime import datetime, timedelta
    
    # Look for ModifyDBInstance events in last 24 hours
    response = cloudtrail.lookup_events(
        LookupAttributes=[
            {
                'AttributeKey': 'ResourceName',
                'AttributeValue': DB_IDENTIFIER
            }
        ],
        StartTime=datetime.now() - timedelta(hours=24),
        MaxResults=50
    )
    
    password_changes = []
    for event in response['Events']:
        if event['EventName'] == 'ModifyDBInstance':
            password_changes.append(event)
    
    if password_changes:
        print(f"\nFound {len(password_changes)} ModifyDBInstance event(s):")
        for event in password_changes:
            print(f"  Time: {event['EventTime']}")
            print(f"  User: {event.get('Username', 'N/A')}")
    else:
        print("\n⚠️  No ModifyDBInstance events found in last 24 hours")
        
    # Look for PutSecretValue events
    response = cloudtrail.lookup_events(
        LookupAttributes=[
            {
                'AttributeKey': 'EventName',
                'AttributeValue': 'PutSecretValue'
            }
        ],
        StartTime=datetime.now() - timedelta(hours=24),
        MaxResults=50
    )
    
    if response['Events']:
        print(f"\nFound {len(response['Events'])} PutSecretValue event(s):")
        for event in response['Events']:
            print(f"  Time: {event['EventTime']}")
            print(f"  User: {event.get('Username', 'N/A')}")
            # Try to get resource name
            if 'Resources' in event:
                for resource in event['Resources']:
                    if 'ResourceName' in resource:
                        print(f"  Secret: {resource['ResourceName']}")
    else:
        print("\n⚠️  No PutSecretValue events found in last 24 hours")
        
except Exception as e:
    print(f"❌ Error checking CloudTrail: {e}")

print("\n" + "="*80)
print("CONCLUSION")
print("="*80)
print("\nBased on the timestamps above:")
print("- If RDS password was changed, ModifyDBInstance event should exist")
print("- If Secrets Manager was updated, PutSecretValue event should exist")
print("- If both timestamps are recent and close together, they are in sync")
print("- If timestamps are old or missing, the password reset may not have happened")
