#!/usr/bin/env python3
"""
Verify AWS Database Connectivity

This script checks:
1. RDS database status and accessibility
2. Application task environment variables
3. Application logs for database connection errors
4. Security group rules allowing database access
"""

import boto3
import json
import time
from datetime import datetime, timedelta

REGION = 'us-east-1'
CLUSTER_NAME = 'multimodal-lib-prod-cluster'
SERVICE_NAME = 'multimodal-lib-prod-service-alb'

# Initialize AWS clients
ecs = boto3.client('ecs', region_name=REGION)
ec2 = boto3.client('ec2', region_name=REGION)
rds = boto3.client('rds', region_name=REGION)
logs = boto3.client('logs', region_name=REGION)


def check_rds_database():
    """Check RDS database status"""
    print("\n" + "="*80)
    print("STEP 1: RDS DATABASE STATUS")
    print("="*80)
    
    try:
        # List all RDS instances
        response = rds.describe_db_instances()
        
        postgres_instances = [
            db for db in response['DBInstances']
            if 'postgres' in db['DBInstanceIdentifier'].lower() or
               'librarian' in db['DBInstanceIdentifier'].lower()
        ]
        
        if not postgres_instances:
            print("❌ No PostgreSQL RDS instances found for this application")
            return None
        
        for db in postgres_instances:
            print(f"\n📊 Database: {db['DBInstanceIdentifier']}")
            print(f"   Status: {db['DBInstanceStatus']}")
            print(f"   Engine: {db['Engine']} {db['EngineVersion']}")
            print(f"   Endpoint: {db['Endpoint']['Address']}:{db['Endpoint']['Port']}")
            print(f"   VPC: {db['DBSubnetGroup']['VpcId']}")
            print(f"   Publicly Accessible: {db['PubliclyAccessible']}")
            print(f"   Multi-AZ: {db['MultiAZ']}")
            
            # Check security groups
            print(f"\n   Security Groups:")
            for sg in db['VpcSecurityGroups']:
                print(f"      - {sg['VpcSecurityGroupId']} ({sg['Status']})")
            
            if db['DBInstanceStatus'] == 'available':
                print(f"\n   ✅ Database is AVAILABLE")
            else:
                print(f"\n   ⚠️  Database status: {db['DBInstanceStatus']}")
            
            return db
        
    except Exception as e:
        print(f"❌ Error checking RDS: {str(e)}")
        return None


def check_ecs_service():
    """Check ECS service and task status"""
    print("\n" + "="*80)
    print("STEP 2: ECS SERVICE STATUS")
    print("="*80)
    
    try:
        # Get service details
        response = ecs.describe_services(
            cluster=CLUSTER_NAME,
            services=[SERVICE_NAME]
        )
        
        if not response['services']:
            print(f"❌ Service {SERVICE_NAME} not found")
            return None
        
        service = response['services'][0]
        print(f"\n📊 Service: {service['serviceName']}")
        print(f"   Status: {service['status']}")
        print(f"   Desired Count: {service['desiredCount']}")
        print(f"   Running Count: {service['runningCount']}")
        print(f"   Pending Count: {service['pendingCount']}")
        
        # Get task definition
        task_def_arn = service['taskDefinition']
        task_def = ecs.describe_task_definition(taskDefinition=task_def_arn)
        
        print(f"\n   Task Definition: {task_def_arn.split('/')[-1]}")
        
        # Check for database environment variables
        print(f"\n   Database Environment Variables:")
        container_def = task_def['taskDefinition']['containerDefinitions'][0]
        
        db_env_vars = {}
        for env in container_def.get('environment', []):
            if any(key in env['name'] for key in ['DB_', 'POSTGRES_', 'DATABASE']):
                value = env['value']
                if 'PASSWORD' in env['name']:
                    value = '*' * len(value) if value else '(not set)'
                db_env_vars[env['name']] = value
                print(f"      {env['name']}: {value}")
        
        # Check for secrets
        print(f"\n   Database Secrets:")
        for secret in container_def.get('secrets', []):
            if any(key in secret['name'] for key in ['DB_', 'POSTGRES_', 'DATABASE']):
                print(f"      {secret['name']}: {secret['valueFrom']}")
        
        return service, task_def, db_env_vars
        
    except Exception as e:
        print(f"❌ Error checking ECS service: {str(e)}")
        return None


def check_running_tasks():
    """Check running tasks and their network configuration"""
    print("\n" + "="*80)
    print("STEP 3: RUNNING TASKS")
    print("="*80)
    
    try:
        # List running tasks
        response = ecs.list_tasks(
            cluster=CLUSTER_NAME,
            serviceName=SERVICE_NAME,
            desiredStatus='RUNNING'
        )
        
        if not response['taskArns']:
            print("❌ No running tasks found")
            return None
        
        # Describe tasks
        tasks = ecs.describe_tasks(
            cluster=CLUSTER_NAME,
            tasks=response['taskArns']
        )
        
        for task in tasks['tasks']:
            task_id = task['taskArn'].split('/')[-1]
            print(f"\n📊 Task: {task_id}")
            print(f"   Status: {task['lastStatus']}")
            print(f"   Health: {task.get('healthStatus', 'UNKNOWN')}")
            print(f"   Started: {task.get('startedAt', 'N/A')}")
            
            # Network configuration
            if 'attachments' in task:
                for attachment in task['attachments']:
                    if attachment['type'] == 'ElasticNetworkInterface':
                        for detail in attachment['details']:
                            if detail['name'] == 'subnetId':
                                print(f"   Subnet: {detail['value']}")
                            elif detail['name'] == 'networkInterfaceId':
                                print(f"   ENI: {detail['value']}")
            
            # Check container status
            print(f"\n   Containers:")
            for container in task['containers']:
                print(f"      - {container['name']}: {container['lastStatus']}")
                if 'exitCode' in container:
                    print(f"        Exit Code: {container['exitCode']}")
                if 'reason' in container:
                    print(f"        Reason: {container['reason']}")
        
        return tasks['tasks']
        
    except Exception as e:
        print(f"❌ Error checking tasks: {str(e)}")
        return None


def check_application_logs():
    """Check application logs for database connection errors"""
    print("\n" + "="*80)
    print("STEP 4: APPLICATION LOGS (Last 10 minutes)")
    print("="*80)
    
    try:
        log_group = '/ecs/multimodal-lib-prod-app'
        
        # Get log streams
        response = logs.describe_log_streams(
            logGroupName=log_group,
            orderBy='LastEventTime',
            descending=True,
            limit=5
        )
        
        if not response['logStreams']:
            print(f"❌ No log streams found in {log_group}")
            return
        
        print(f"\n📊 Log Group: {log_group}")
        print(f"   Recent Streams: {len(response['logStreams'])}")
        
        # Search for database-related logs
        start_time = int((datetime.now() - timedelta(minutes=10)).timestamp() * 1000)
        
        keywords = [
            'database',
            'postgres',
            'connection',
            'psycopg2',
            'sqlalchemy',
            'DB_',
            'error',
            'failed',
            'timeout'
        ]
        
        print(f"\n   Searching for database-related logs...")
        
        for stream in response['logStreams'][:3]:  # Check last 3 streams
            stream_name = stream['logStreamName']
            
            try:
                events = logs.get_log_events(
                    logGroupName=log_group,
                    logStreamName=stream_name,
                    startTime=start_time,
                    limit=100
                )
                
                db_related_logs = []
                for event in events['events']:
                    message = event['message'].lower()
                    if any(keyword in message for keyword in keywords):
                        db_related_logs.append(event)
                
                if db_related_logs:
                    print(f"\n   Stream: {stream_name}")
                    print(f"   Found {len(db_related_logs)} database-related log entries:")
                    
                    for event in db_related_logs[-10:]:  # Show last 10
                        timestamp = datetime.fromtimestamp(event['timestamp'] / 1000)
                        message = event['message'][:200]  # Truncate long messages
                        print(f"\n      [{timestamp}]")
                        print(f"      {message}")
                        if len(event['message']) > 200:
                            print(f"      ... (truncated)")
                
            except Exception as e:
                print(f"   ⚠️  Could not read stream {stream_name}: {str(e)}")
        
    except Exception as e:
        print(f"❌ Error checking logs: {str(e)}")


def check_security_groups(db_instance, tasks):
    """Check security group rules between ECS tasks and RDS"""
    print("\n" + "="*80)
    print("STEP 5: SECURITY GROUP CONNECTIVITY")
    print("="*80)
    
    if not db_instance or not tasks:
        print("⚠️  Skipping - missing database or task information")
        return
    
    try:
        # Get RDS security groups
        db_sg_ids = [sg['VpcSecurityGroupId'] for sg in db_instance['VpcSecurityGroups']]
        print(f"\n📊 RDS Security Groups: {', '.join(db_sg_ids)}")
        
        # Get task security groups (from ENI)
        task_sg_ids = set()
        for task in tasks:
            if 'attachments' in task:
                for attachment in task['attachments']:
                    if attachment['type'] == 'ElasticNetworkInterface':
                        for detail in attachment['details']:
                            if detail['name'] == 'networkInterfaceId':
                                eni_id = detail['value']
                                eni = ec2.describe_network_interfaces(
                                    NetworkInterfaceIds=[eni_id]
                                )
                                for group in eni['NetworkInterfaces'][0]['Groups']:
                                    task_sg_ids.add(group['GroupId'])
        
        print(f"\n📊 Task Security Groups: {', '.join(task_sg_ids)}")
        
        # Check RDS security group rules
        print(f"\n   Checking RDS security group ingress rules...")
        for sg_id in db_sg_ids:
            sg = ec2.describe_security_groups(GroupIds=[sg_id])
            
            print(f"\n   Security Group: {sg_id}")
            print(f"   Ingress Rules:")
            
            allows_tasks = False
            for rule in sg['SecurityGroups'][0]['IpPermissions']:
                if rule.get('FromPort') == 5432:
                    print(f"      Port 5432:")
                    
                    # Check if it allows task security groups
                    for source in rule.get('UserIdGroupPairs', []):
                        source_sg = source['GroupId']
                        print(f"         Allows: {source_sg}")
                        if source_sg in task_sg_ids:
                            allows_tasks = True
                            print(f"            ✅ This is a task security group!")
                    
                    # Check CIDR blocks
                    for cidr in rule.get('IpRanges', []):
                        print(f"         Allows: {cidr['CidrIp']}")
            
            if allows_tasks:
                print(f"\n   ✅ RDS allows connections from ECS tasks")
            else:
                print(f"\n   ⚠️  RDS may not allow connections from ECS tasks")
                print(f"      Task SGs: {', '.join(task_sg_ids)}")
        
    except Exception as e:
        print(f"❌ Error checking security groups: {str(e)}")


def main():
    print("="*80)
    print("AWS DATABASE CONNECTIVITY VERIFICATION")
    print("="*80)
    print("\nThis script will check:")
    print("1. RDS database status and configuration")
    print("2. ECS service and task configuration")
    print("3. Running tasks and their network setup")
    print("4. Application logs for database errors")
    print("5. Security group rules for connectivity")
    
    # Run checks
    db_instance = check_rds_database()
    service_info = check_ecs_service()
    tasks = check_running_tasks()
    check_application_logs()
    
    if db_instance and tasks:
        check_security_groups(db_instance, tasks)
    
    # Summary
    print("\n" + "="*80)
    print("SUMMARY")
    print("="*80)
    
    if db_instance and db_instance['DBInstanceStatus'] == 'available':
        print("✅ Database is available")
    else:
        print("❌ Database issue detected")
    
    if service_info and service_info[0]['runningCount'] > 0:
        print("✅ Application is running")
    else:
        print("❌ Application not running")
    
    if tasks:
        healthy_tasks = sum(1 for t in tasks if t.get('healthStatus') == 'HEALTHY')
        print(f"✅ {healthy_tasks}/{len(tasks)} tasks are healthy")
    
    print("\n💡 Next Steps:")
    print("   1. Review the logs above for any database connection errors")
    print("   2. Verify security group rules allow ECS → RDS connectivity")
    print("   3. Check that database credentials are correctly configured")
    print("   4. Test connectivity: python scripts/test-application-database-connectivity.py")
    
    return 0


if __name__ == '__main__':
    exit(main())
