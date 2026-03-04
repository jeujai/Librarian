#!/usr/bin/env python3
"""
Diagnose database credentials and connectivity after switching to old database.
"""

import boto3
import json
from datetime import datetime, timedelta

REGION = 'us-east-1'
CLUSTER_NAME = 'multimodal-lib-prod-cluster'
SERVICE_NAME = 'multimodal-lib-prod-service-alb'

def check_task_environment():
    """Check the task's environment variables"""
    print("=" * 70)
    print("CHECKING TASK ENVIRONMENT VARIABLES")
    print("=" * 70)
    
    ecs = boto3.client('ecs', region_name=REGION)
    
    # Get running task
    tasks = ecs.list_tasks(
        cluster=CLUSTER_NAME,
        serviceName=SERVICE_NAME,
        desiredStatus='RUNNING'
    )
    
    if not tasks['taskArns']:
        print("❌ No running tasks found")
        return
    
    task_arn = tasks['taskArns'][0]
    print(f"\n📋 Task: {task_arn.split('/')[-1]}")
    
    # Get task definition
    task_details = ecs.describe_tasks(
        cluster=CLUSTER_NAME,
        tasks=[task_arn]
    )
    
    task_def_arn = task_details['tasks'][0]['taskDefinitionArn']
    print(f"📋 Task Definition: {task_def_arn.split('/')[-1]}")
    
    # Get task definition details
    task_def = ecs.describe_task_definition(taskDefinition=task_def_arn)
    container = task_def['taskDefinition']['containerDefinitions'][0]
    
    print("\n🔍 Database Environment Variables:")
    env_vars = {e['name']: e['value'] for e in container.get('environment', []) if 'DB_' in e['name']}
    for key, value in sorted(env_vars.items()):
        print(f"   {key}: {value}")
    
    print("\n🔐 Database Secrets:")
    secrets = [s for s in container.get('secrets', []) if 'DB_' in s['name']]
    for secret in secrets:
        print(f"   {secret['name']}: {secret['valueFrom']}")
    
    return task_arn

def check_task_logs(task_arn):
    """Check recent task logs for database connection attempts"""
    print("\n" + "=" * 70)
    print("CHECKING TASK LOGS")
    print("=" * 70)
    
    logs = boto3.client('logs', region_name=REGION)
    
    # Extract task ID
    task_id = task_arn.split('/')[-1]
    
    # Try to find log stream
    log_group = '/ecs/multimodal-lib-prod-app'
    
    try:
        streams = logs.describe_log_streams(
            logGroupName=log_group,
            logStreamNamePrefix=f'ecs/multimodal-lib-prod-app/{task_id}',
            orderBy='LastEventTime',
            descending=True,
            limit=5
        )
        
        if not streams['logStreams']:
            print(f"⚠️  No log streams found for task {task_id}")
            return
        
        stream_name = streams['logStreams'][0]['logStreamName']
        print(f"\n📝 Log Stream: {stream_name}")
        
        # Get recent logs
        end_time = datetime.now()
        start_time = end_time - timedelta(minutes=10)
        
        events = logs.get_log_events(
            logGroupName=log_group,
            logStreamName=stream_name,
            startTime=int(start_time.timestamp() * 1000),
            endTime=int(end_time.timestamp() * 1000),
            limit=100
        )
        
        print(f"\n📊 Recent Log Events (last 10 minutes):")
        print("-" * 70)
        
        db_related = []
        for event in events['events']:
            message = event['message']
            if any(keyword in message.lower() for keyword in ['database', 'db_', 'postgres', 'connection', 'error', 'failed']):
                db_related.append(message)
        
        if db_related:
            for msg in db_related[-20:]:  # Last 20 database-related messages
                print(msg.strip())
        else:
            print("ℹ️  No database-related log messages found")
            print("\nShowing last 10 log messages:")
            for event in events['events'][-10:]:
                print(event['message'].strip())
        
    except Exception as e:
        print(f"❌ Error reading logs: {str(e)}")

def check_security_groups():
    """Check security group configuration"""
    print("\n" + "=" * 70)
    print("CHECKING SECURITY GROUPS")
    print("=" * 70)
    
    ecs = boto3.client('ecs', region_name=REGION)
    ec2 = boto3.client('ec2', region_name=REGION)
    rds = boto3.client('rds', region_name=REGION)
    
    # Get ECS task security group
    service = ecs.describe_services(
        cluster=CLUSTER_NAME,
        services=[SERVICE_NAME]
    )
    
    ecs_sg = service['services'][0]['networkConfiguration']['awsvpcConfiguration']['securityGroups'][0]
    print(f"\n🔒 ECS Task Security Group: {ecs_sg}")
    
    # Get database security group
    db = rds.describe_db_instances(DBInstanceIdentifier='ml-librarian-postgres-prod')
    db_sgs = [sg['VpcSecurityGroupId'] for sg in db['DBInstances'][0]['VpcSecurityGroups']]
    print(f"🔒 Database Security Groups: {', '.join(db_sgs)}")
    
    # Check if ECS SG can reach database
    print("\n🔍 Checking database security group rules:")
    for db_sg in db_sgs:
        sg_details = ec2.describe_security_groups(GroupIds=[db_sg])
        ingress_rules = sg_details['SecurityGroups'][0]['IpPermissions']
        
        print(f"\n   Security Group: {db_sg}")
        for rule in ingress_rules:
            if rule.get('FromPort') == 5432:
                sources = []
                if rule.get('IpRanges'):
                    sources.extend([r['CidrIp'] for r in rule['IpRanges']])
                if rule.get('UserIdGroupPairs'):
                    sources.extend([r['GroupId'] for r in rule['UserIdGroupPairs']])
                
                print(f"   ✓ Port 5432 allowed from: {', '.join(sources)}")
                
                if ecs_sg in sources:
                    print(f"   ✅ ECS security group {ecs_sg} is allowed!")
                else:
                    print(f"   ⚠️  ECS security group {ecs_sg} is NOT in allowed list")

def main():
    try:
        task_arn = check_task_environment()
        if task_arn:
            check_task_logs(task_arn)
        check_security_groups()
        
        print("\n" + "=" * 70)
        print("DIAGNOSIS COMPLETE")
        print("=" * 70)
        
    except Exception as e:
        print(f"\n❌ Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0

if __name__ == '__main__':
    exit(main())
