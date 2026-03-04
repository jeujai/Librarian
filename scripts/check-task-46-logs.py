#!/usr/bin/env python3
"""
Check Task Definition 46 Logs

Checks CloudWatch logs for task definition 46 to verify
secret retrieval is working correctly.
"""

import boto3
from datetime import datetime, timedelta

def check_task_logs():
    """Check CloudWatch logs for task 46."""
    
    print("📋 Checking Task Definition 46 Logs")
    print("=" * 60)
    
    ecs = boto3.client('ecs', region_name='us-east-1')
    logs = boto3.client('logs', region_name='us-east-1')
    
    cluster_name = "multimodal-lib-prod-cluster"
    service_name = "multimodal-lib-prod-service"
    
    try:
        # Get running tasks
        tasks_response = ecs.list_tasks(
            cluster=cluster_name,
            serviceName=service_name,
            desiredStatus='RUNNING'
        )
        
        if not tasks_response['taskArns']:
            print("❌ No running tasks found")
            return
        
        # Get task details
        tasks_detail = ecs.describe_tasks(
            cluster=cluster_name,
            tasks=tasks_response['taskArns']
        )
        
        # Find task with definition 46
        task_46 = None
        for task in tasks_detail['tasks']:
            if ':46' in task['taskDefinitionArn']:
                task_46 = task
                break
        
        if not task_46:
            print("⚠️  No task with definition 46 found yet")
            print("\nAll tasks:")
            for task in tasks_detail['tasks']:
                task_id = task['taskArn'].split('/')[-1]
                task_def = task['taskDefinitionArn'].split('/')[-1]
                status = task['lastStatus']
                print(f"  - {task_id[:8]}... ({task_def}) - {status}")
            return
        
        task_id = task_46['taskArn'].split('/')[-1]
        print(f"✅ Found task with definition 46: {task_id}")
        print(f"   Status: {task_46['lastStatus']}")
        print(f"   Health: {task_46.get('healthStatus', 'UNKNOWN')}")
        print()
        
        # Get container info
        container = task_46['containers'][0]
        print(f"Container Status: {container.get('lastStatus', 'UNKNOWN')}")
        
        if 'reason' in container:
            print(f"Container Reason: {container['reason']}")
        
        print()
        
        # Check CloudWatch logs
        log_group = "/ecs/multimodal-lib-prod-app"
        log_stream_prefix = f"ecs/multimodal-lib-prod-app/{task_id}"
        
        print(f"📋 Checking CloudWatch logs...")
        print(f"   Log Group: {log_group}")
        print(f"   Stream Prefix: {log_stream_prefix}")
        print()
        
        # List log streams
        try:
            streams_response = logs.describe_log_streams(
                logGroupName=log_group,
                logStreamNamePrefix=log_stream_prefix,
                descending=True,
                limit=5
            )
            
            if not streams_response['logStreams']:
                print("⚠️  No log streams found yet (task may still be starting)")
                return
            
            # Get latest log stream
            log_stream = streams_response['logStreams'][0]['logStreamName']
            print(f"✅ Found log stream: {log_stream}")
            print()
            
            # Get recent log events
            start_time = int((datetime.now() - timedelta(minutes=10)).timestamp() * 1000)
            
            events_response = logs.get_log_events(
                logGroupName=log_group,
                logStreamName=log_stream,
                startTime=start_time,
                limit=100
            )
            
            if not events_response['events']:
                print("⚠️  No log events found yet")
                return
            
            print("📝 Recent Log Events:")
            print("-" * 60)
            
            # Look for secret-related messages
            secret_errors = []
            secret_success = []
            
            for event in events_response['events']:
                message = event['message']
                timestamp = datetime.fromtimestamp(event['timestamp'] / 1000)
                
                # Check for secret-related messages
                if 'secret' in message.lower() or 'asm' in message.lower():
                    if 'error' in message.lower() or 'fail' in message.lower():
                        secret_errors.append((timestamp, message))
                    else:
                        secret_success.append((timestamp, message))
                
                # Print all recent messages
                print(f"[{timestamp.strftime('%H:%M:%S')}] {message.strip()}")
            
            print("-" * 60)
            print()
            
            # Summary
            if secret_errors:
                print("❌ Secret Retrieval Errors Found:")
                for ts, msg in secret_errors:
                    print(f"   [{ts.strftime('%H:%M:%S')}] {msg.strip()}")
            elif secret_success:
                print("✅ Secret Retrieval Messages:")
                for ts, msg in secret_success:
                    print(f"   [{ts.strftime('%H:%M:%S')}] {msg.strip()}")
            else:
                print("ℹ️  No secret-related messages found in logs")
            
        except logs.exceptions.ResourceNotFoundException:
            print(f"⚠️  Log group not found: {log_group}")
        except Exception as e:
            print(f"❌ Error reading logs: {e}")
        
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    check_task_logs()
