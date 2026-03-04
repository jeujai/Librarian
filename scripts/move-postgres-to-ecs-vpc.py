#!/usr/bin/env python3
"""
Move PostgreSQL RDS Instance to ECS Service VPC

This script migrates the PostgreSQL database from the MultimodalLibrarianFullML VPC
to the ml-librarian-prod-vpc where the ECS service runs.

Source DB: multimodallibrarianfullml-databasepostgresdatabase-ccjxkhsancro
Source VPC: vpc-0bc85162dcdbcc986
Target VPC: vpc-0b2186b38779e77f6

Process:
1. Create snapshot of current database
2. Get target VPC subnet group
3. Restore snapshot to new instance in target VPC
4. Update application connection strings
5. Verify connectivity
6. Delete old database (manual step)
"""

import boto3
import time
import json
from datetime import datetime

# Configuration
SOURCE_DB_INSTANCE = "multimodallibrarianfullml-databasepostgresdatabase-ccjxkhsancro"
TARGET_VPC_ID = "vpc-0b2186b38779e77f6"
NEW_DB_INSTANCE = "ml-librarian-postgres-prod"
SNAPSHOT_ID = f"postgres-migration-{int(time.time())}"

# AWS clients
rds = boto3.client('rds')
ec2 = boto3.client('ec2')

def create_snapshot():
    """Create a snapshot of the source database."""
    print(f"\n=== Step 1: Creating snapshot of {SOURCE_DB_INSTANCE} ===")
    
    try:
        response = rds.create_db_snapshot(
            DBSnapshotIdentifier=SNAPSHOT_ID,
            DBInstanceIdentifier=SOURCE_DB_INSTANCE,
            Tags=[
                {'Key': 'Purpose', 'Value': 'VPC Migration'},
                {'Key': 'SourceVPC', 'Value': 'vpc-0bc85162dcdbcc986'},
                {'Key': 'TargetVPC', 'Value': TARGET_VPC_ID},
                {'Key': 'CreatedAt', 'Value': datetime.utcnow().isoformat()}
            ]
        )
        
        print(f"✓ Snapshot creation initiated: {SNAPSHOT_ID}")
        print(f"  Status: {response['DBSnapshot']['Status']}")
        
        # Wait for snapshot to complete
        print("\n  Waiting for snapshot to complete (this may take 10-30 minutes)...")
        waiter = rds.get_waiter('db_snapshot_completed')
        waiter.wait(
            DBSnapshotIdentifier=SNAPSHOT_ID,
            WaiterConfig={'Delay': 30, 'MaxAttempts': 60}
        )
        
        print("✓ Snapshot completed successfully")
        return SNAPSHOT_ID
        
    except Exception as e:
        print(f"✗ Error creating snapshot: {e}")
        raise

def get_target_subnet_group():
    """Get or create DB subnet group in target VPC."""
    print(f"\n=== Step 2: Setting up subnet group in target VPC ===")
    
    subnet_group_name = "ml-librarian-prod-db-subnet-group"
    
    try:
        # Check if subnet group exists
        response = rds.describe_db_subnet_groups(
            DBSubnetGroupName=subnet_group_name
        )
        print(f"✓ Subnet group already exists: {subnet_group_name}")
        return subnet_group_name
        
    except rds.exceptions.DBSubnetGroupNotFoundFault:
        # Create new subnet group
        print(f"  Creating new subnet group: {subnet_group_name}")
        
        # Get private subnets in target VPC
        subnets_response = ec2.describe_subnets(
            Filters=[
                {'Name': 'vpc-id', 'Values': [TARGET_VPC_ID]},
                {'Name': 'tag:Name', 'Values': ['*private*', '*Private*']}
            ]
        )
        
        subnet_ids = [subnet['SubnetId'] for subnet in subnets_response['Subnets']]
        
        if len(subnet_ids) < 2:
            # Get all subnets if not enough private ones
            subnets_response = ec2.describe_subnets(
                Filters=[{'Name': 'vpc-id', 'Values': [TARGET_VPC_ID]}]
            )
            subnet_ids = [subnet['SubnetId'] for subnet in subnets_response['Subnets']]
        
        print(f"  Found {len(subnet_ids)} subnets: {subnet_ids}")
        
        response = rds.create_db_subnet_group(
            DBSubnetGroupName=subnet_group_name,
            DBSubnetGroupDescription='Subnet group for ML Librarian PostgreSQL in prod VPC',
            SubnetIds=subnet_ids,
            Tags=[
                {'Key': 'Name', 'Value': subnet_group_name},
                {'Key': 'VPC', 'Value': TARGET_VPC_ID}
            ]
        )
        
        print(f"✓ Subnet group created: {subnet_group_name}")
        return subnet_group_name

def get_security_group():
    """Get or create security group for database in target VPC."""
    print(f"\n=== Step 3: Setting up security group ===")
    
    sg_name = "ml-librarian-postgres-sg"
    
    try:
        # Check if security group exists
        response = ec2.describe_security_groups(
            Filters=[
                {'Name': 'group-name', 'Values': [sg_name]},
                {'Name': 'vpc-id', 'Values': [TARGET_VPC_ID]}
            ]
        )
        
        if response['SecurityGroups']:
            sg_id = response['SecurityGroups'][0]['GroupId']
            print(f"✓ Security group already exists: {sg_id}")
            return sg_id
            
    except Exception:
        pass
    
    # Create new security group
    print(f"  Creating new security group: {sg_name}")
    
    response = ec2.create_security_group(
        GroupName=sg_name,
        Description='Security group for ML Librarian PostgreSQL database',
        VpcId=TARGET_VPC_ID,
        TagSpecifications=[{
            'ResourceType': 'security-group',
            'Tags': [
                {'Key': 'Name', 'Value': sg_name},
                {'Key': 'Purpose', 'Value': 'PostgreSQL Database'}
            ]
        }]
    )
    
    sg_id = response['GroupId']
    
    # Add ingress rule for PostgreSQL from VPC CIDR
    ec2.authorize_security_group_ingress(
        GroupId=sg_id,
        IpPermissions=[{
            'IpProtocol': 'tcp',
            'FromPort': 5432,
            'ToPort': 5432,
            'IpRanges': [{'CidrIp': '10.0.0.0/16', 'Description': 'PostgreSQL from VPC'}]
        }]
    )
    
    print(f"✓ Security group created: {sg_id}")
    return sg_id

def restore_snapshot_to_new_vpc(snapshot_id, subnet_group_name, security_group_id):
    """Restore snapshot to new database instance in target VPC."""
    print(f"\n=== Step 4: Restoring database to target VPC ===")
    
    # Get source DB details
    source_db = rds.describe_db_instances(
        DBInstanceIdentifier=SOURCE_DB_INSTANCE
    )['DBInstances'][0]
    
    print(f"  Source DB class: {source_db['DBInstanceClass']}")
    print(f"  Source engine: {source_db['Engine']} {source_db['EngineVersion']}")
    print(f"  Source storage: {source_db['AllocatedStorage']} GB")
    
    try:
        response = rds.restore_db_instance_from_db_snapshot(
            DBInstanceIdentifier=NEW_DB_INSTANCE,
            DBSnapshotIdentifier=snapshot_id,
            DBInstanceClass=source_db['DBInstanceClass'],
            DBSubnetGroupName=subnet_group_name,
            VpcSecurityGroupIds=[security_group_id],
            PubliclyAccessible=False,
            MultiAZ=source_db.get('MultiAZ', False),
            StorageType=source_db.get('StorageType', 'gp2'),
            CopyTagsToSnapshot=True,
            Tags=[
                {'Key': 'Name', 'Value': NEW_DB_INSTANCE},
                {'Key': 'Environment', 'Value': 'production'},
                {'Key': 'VPC', 'Value': TARGET_VPC_ID},
                {'Key': 'MigratedFrom', 'Value': SOURCE_DB_INSTANCE}
            ]
        )
        
        print(f"✓ Database restore initiated: {NEW_DB_INSTANCE}")
        print(f"  Status: {response['DBInstance']['DBInstanceStatus']}")
        
        # Wait for database to be available
        print("\n  Waiting for database to become available (this may take 10-20 minutes)...")
        waiter = rds.get_waiter('db_instance_available')
        waiter.wait(
            DBInstanceIdentifier=NEW_DB_INSTANCE,
            WaiterConfig={'Delay': 30, 'MaxAttempts': 40}
        )
        
        # Get new endpoint
        new_db = rds.describe_db_instances(
            DBInstanceIdentifier=NEW_DB_INSTANCE
        )['DBInstances'][0]
        
        endpoint = new_db['Endpoint']['Address']
        port = new_db['Endpoint']['Port']
        
        print(f"\n✓ Database is now available!")
        print(f"  Endpoint: {endpoint}")
        print(f"  Port: {port}")
        print(f"  VPC: {new_db['DBSubnetGroup']['VpcId']}")
        
        return endpoint, port
        
    except Exception as e:
        print(f"✗ Error restoring database: {e}")
        raise

def update_secrets_manager(endpoint, port):
    """Update Secrets Manager with new database endpoint."""
    print(f"\n=== Step 5: Updating Secrets Manager ===")
    
    secrets = boto3.client('secretsmanager')
    
    # List secrets to find database credentials
    response = secrets.list_secrets()
    
    db_secrets = [s for s in response['SecretList'] 
                  if 'postgres' in s['Name'].lower() or 'database' in s['Name'].lower()]
    
    if not db_secrets:
        print("  No database secrets found to update")
        print(f"  You'll need to manually update POSTGRES_HOST to: {endpoint}")
        return
    
    print(f"  Found {len(db_secrets)} database secret(s):")
    for secret in db_secrets:
        print(f"    - {secret['Name']}")
    
    print(f"\n  New database endpoint: {endpoint}:{port}")
    print(f"  Please update your secrets manually or confirm to proceed")

def print_summary(endpoint, port):
    """Print migration summary and next steps."""
    print("\n" + "="*70)
    print("MIGRATION SUMMARY")
    print("="*70)
    
    print(f"\n✓ PostgreSQL database successfully migrated to ECS VPC!")
    print(f"\nNew Database Details:")
    print(f"  Instance ID: {NEW_DB_INSTANCE}")
    print(f"  Endpoint: {endpoint}")
    print(f"  Port: {port}")
    print(f"  VPC: {TARGET_VPC_ID}")
    
    print(f"\nNext Steps:")
    print(f"  1. Update application environment variables:")
    print(f"     POSTGRES_HOST={endpoint}")
    print(f"     POSTGRES_PORT={port}")
    
    print(f"\n  2. Test database connectivity from ECS tasks")
    
    print(f"\n  3. Update ECS task definition and redeploy")
    
    print(f"\n  4. Verify application works correctly")
    
    print(f"\n  5. Once verified, delete old database:")
    print(f"     aws rds delete-db-instance \\")
    print(f"       --db-instance-identifier {SOURCE_DB_INSTANCE} \\")
    print(f"       --skip-final-snapshot")
    
    print(f"\n  6. Delete old VPC peering connection:")
    print(f"     aws ec2 delete-vpc-peering-connection \\")
    print(f"       --vpc-peering-connection-id pcx-0a014455d9e2e2685")
    
    print("\n" + "="*70)

def main():
    """Main migration workflow."""
    print("="*70)
    print("PostgreSQL Database VPC Migration")
    print("="*70)
    print(f"\nThis will migrate PostgreSQL from:")
    print(f"  Source: {SOURCE_DB_INSTANCE}")
    print(f"  Source VPC: vpc-0bc85162dcdbcc986")
    print(f"\nTo:")
    print(f"  Target: {NEW_DB_INSTANCE}")
    print(f"  Target VPC: {TARGET_VPC_ID} (ECS Service VPC)")
    
    response = input("\nProceed with migration? (yes/no): ")
    if response.lower() != 'yes':
        print("Migration cancelled")
        return
    
    try:
        # Step 1: Create snapshot
        snapshot_id = create_snapshot()
        
        # Step 2: Get/create subnet group
        subnet_group_name = get_target_subnet_group()
        
        # Step 3: Get/create security group
        security_group_id = get_security_group()
        
        # Step 4: Restore to new VPC
        endpoint, port = restore_snapshot_to_new_vpc(
            snapshot_id, 
            subnet_group_name, 
            security_group_id
        )
        
        # Step 5: Update secrets (informational)
        update_secrets_manager(endpoint, port)
        
        # Print summary
        print_summary(endpoint, port)
        
        # Save migration details
        migration_details = {
            'timestamp': datetime.utcnow().isoformat(),
            'source_instance': SOURCE_DB_INSTANCE,
            'new_instance': NEW_DB_INSTANCE,
            'snapshot_id': snapshot_id,
            'new_endpoint': endpoint,
            'new_port': port,
            'target_vpc': TARGET_VPC_ID,
            'subnet_group': subnet_group_name,
            'security_group': security_group_id
        }
        
        filename = f"postgres-migration-{int(time.time())}.json"
        with open(filename, 'w') as f:
            json.dump(migration_details, f, indent=2)
        
        print(f"\nMigration details saved to: {filename}")
        
    except Exception as e:
        print(f"\n✗ Migration failed: {e}")
        print("\nPlease review the error and try again")
        return 1
    
    return 0

if __name__ == "__main__":
    exit(main())
