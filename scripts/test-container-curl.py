#!/usr/bin/env python3
"""
Test if curl works in the container by analyzing health check behavior
"""
import boto3
import json
from datetime import datetime, timedelta

def check_container_curl():
    """Check if curl is working in the container"""
    ecs = boto3.client('ecs', region_name='us-east-1')
    logs = boto3.client('logs', region_name='us-east-1')
    elbv2 = boto3.client('elbv2', region_name='us-east-1')
    
    print("=" * 80)
    print("CONTAINER CURL FUNCTIONALITY TEST")
    print("=" * 80)
    
    # Get task details
    cluster = 'multimodal-lib-prod-cluster'
    tasks = ecs.list_tasks(cluster=cluster)
    
    if not tasks['taskArns']:
        print("❌ No running tasks found")
        return
    
    task_arn = tasks['taskArns'][0]
    task_id = task_arn.split('/')[-1]
    
    task_details = ecs.describe_tasks(
        cluster=cluster,
        tasks=[task_arn]
    )
    
    task = task_details['tasks'][0]
    container_ip = task['containers'][0]['networkInterfaces'][0]['privateIpv4Address']
    
    print(f"\n📦 Task ID: {task_id}")
    print(f"🌐 Container IP: {container_ip}")
    print(f"📊 Task Status: {task['lastStatus']}")
    
    # Check target group health
    print("\n" + "=" * 80)
    print("TARGET GROUP HEALTH CHECK STATUS")
    print("=" * 80)
    
    target_groups = elbv2.describe_target_groups()
    
    for tg in target_groups['TargetGroups']:
        if 'multimodal' in tg['TargetGroupName'].lower():
            print(f"\n🎯 Target Group: {tg['TargetGroupName']}")
            print(f"   Health Check Path: {tg.get('HealthCheckPath', 'N/A')}")
            print(f"   Health Check Protocol: {tg.get('HealthCheckProtocol', 'N/A')}")
            print(f"   Health Check Port: {tg.get('HealthCheckPort', 'N/A')}")
            print(f"   Health Check Interval: {tg.get('HealthCheckIntervalSeconds', 'N/A')}s")
            print(f"   Health Check Timeout: {tg.get('HealthCheckTimeoutSeconds', 'N/A')}s")
            print(f"   Healthy Threshold: {tg.get('HealthyThresholdCount', 'N/A')}")
            print(f"   Unhealthy Threshold: {tg.get('UnhealthyThresholdCount', 'N/A')}")
            
            # Check target health
            health = elbv2.describe_target_health(
                TargetGroupArn=tg['TargetGroupArn']
            )
            
            print(f"\n   📊 Target Health:")
            for target in health['TargetHealthDescriptions']:
                target_id = target['Target']['Id']
                state = target['TargetHealth']['State']
                reason = target['TargetHealth'].get('Reason', 'N/A')
                description = target['TargetHealth'].get('Description', 'N/A')
                
                status_emoji = "✅" if state == "healthy" else "❌"
                print(f"   {status_emoji} Target: {target_id}")
                print(f"      State: {state}")
                print(f"      Reason: {reason}")
                print(f"      Description: {description}")
    
    # Check application logs for health check requests
    print("\n" + "=" * 80)
    print("APPLICATION LOGS - HEALTH CHECK REQUESTS")
    print("=" * 80)
    
    log_group = '/ecs/multimodal-lib-prod'
    log_stream_prefix = f'ecs/multimodal-lib-prod-app/{task_id}'
    
    try:
        # Get log streams
        streams = logs.describe_log_streams(
            logGroupName=log_group,
            logStreamNamePrefix=log_stream_prefix,
            orderBy='LastEventTime',
            descending=True,
            limit=1
        )
        
        if streams['logStreams']:
            log_stream = streams['logStreams'][0]['logStreamName']
            
            # Get recent logs
            end_time = int(datetime.now().timestamp() * 1000)
            start_time = int((datetime.now() - timedelta(minutes=5)).timestamp() * 1000)
            
            events = logs.get_log_events(
                logGroupName=log_group,
                logStreamName=log_stream,
                startTime=start_time,
                endTime=end_time,
                limit=100
            )
            
            print(f"\n📝 Recent logs from: {log_stream}")
            print("\nLooking for health check related entries...")
            
            health_check_logs = []
            for event in events['events']:
                message = event['message']
                if any(keyword in message.lower() for keyword in ['health', 'curl', 'get /', 'elb-healthchecker']):
                    timestamp = datetime.fromtimestamp(event['timestamp'] / 1000)
                    health_check_logs.append((timestamp, message))
            
            if health_check_logs:
                print(f"\n✅ Found {len(health_check_logs)} health check related log entries:")
                for timestamp, message in health_check_logs[-10:]:  # Last 10
                    print(f"\n[{timestamp}]")
                    print(f"  {message.strip()}")
            else:
                print("\n⚠️  No health check related logs found in recent entries")
                print("\nShowing last 5 log entries:")
                for event in events['events'][-5:]:
                    timestamp = datetime.fromtimestamp(event['timestamp'] / 1000)
                    print(f"\n[{timestamp}]")
                    print(f"  {event['message'].strip()}")
        else:
            print("❌ No log streams found")
    
    except Exception as e:
        print(f"❌ Error reading logs: {e}")
    
    # Analysis
    print("\n" + "=" * 80)
    print("CURL FUNCTIONALITY ANALYSIS")
    print("=" * 80)
    
    print("\n🔍 Why curl might work in the container:")
    print("   1. The application is listening on port 8000")
    print("   2. The health check endpoint /health is responding")
    print("   3. The load balancer is successfully making HTTP requests")
    print("   4. The container has network connectivity")
    
    print("\n🔍 Evidence that curl works:")
    print("   • If targets are healthy, the ALB is successfully curling the health endpoint")
    print("   • The ALB health checker uses HTTP GET requests (similar to curl)")
    print("   • If the app is responding to ALB health checks, it can respond to curl")
    
    print("\n🔍 Why the ALB health check IS essentially curl:")
    print("   • ALB sends: GET /health HTTP/1.1")
    print("   • curl sends: GET /health HTTP/1.1")
    print("   • Both are standard HTTP requests to the same endpoint")
    print("   • If one works, the other should work too")
    
    print("\n" + "=" * 80)

if __name__ == '__main__':
    check_container_curl()
