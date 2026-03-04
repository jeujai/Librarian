#!/usr/bin/env python3
"""
Check Service Stability - Verify the application is actually running and stable

Before diagnosing ALB issues, we need to ensure the application itself is stable.
"""

import boto3
import json
import time
from datetime import datetime, timedelta

def main():
    ecs = boto3.client('ecs')
    ec2 = boto3.client('ec2')
    logs = boto3.client('logs')
    elbv2 = boto3.client('elbv2')
    
    print("=" * 80)
    print("Service Stability Check")
    print("=" * 80)
    
    cluster_name = 'multimodal-lib-prod-cluster'
    service_name = 'multimodal-lib-prod-service-alb'
    
    # Step 1: Check service status
    print("\n1. Checking ECS Service Status...")
    service_response = ecs.describe_services(
        cluster=cluster_name,
        services=[service_name]
    )
    
    if not service_response['services']:
        print(f"   ✗ Service {service_name} not found!")
        return
    
    service = service_response['services'][0]
    
    print(f"   Service: {service['serviceName']}")
    print(f"   Status: {service['status']}")
    print(f"   Desired Count: {service['desiredCount']}")
    print(f"   Running Count: {service['runningCount']}")
    print(f"   Pending Count: {service['pendingCount']}")
    
    if service['runningCount'] == 0:
        print(f"\n   ✗ NO RUNNING TASKS!")
        print(f"   The service has no running tasks. This is why ALB returns 504.")
        print(f"\n   Checking recent events...")
        
        for event in service['events'][:5]:
            print(f"     [{event['createdAt']}] {event['message']}")
        
        return
    
    if service['runningCount'] < service['desiredCount']:
        print(f"\n   ⚠️  WARNING: Running count ({service['runningCount']}) < Desired count ({service['desiredCount']})")
    else:
        print(f"   ✓ Service has correct number of running tasks")
    
    # Check deployments
    print(f"\n   Active Deployments: {len(service['deployments'])}")
    for deployment in service['deployments']:
        print(f"     Status: {deployment['status']}")
        print(f"     Running: {deployment['runningCount']}/{deployment['desiredCount']}")
        print(f"     Task Definition: {deployment['taskDefinition'].split('/')[-1]}")
        print(f"     Created: {deployment['createdAt']}")
        print(f"     Updated: {deployment['updatedAt']}")
        print()
    
    # Step 2: Check running tasks
    print("\n2. Checking Running Tasks...")
    tasks_response = ecs.list_tasks(
        cluster=cluster_name,
        serviceName=service_name,
        desiredStatus='RUNNING'
    )
    
    if not tasks_response['taskArns']:
        print(f"   ✗ NO RUNNING TASKS!")
        return
    
    task_details = ecs.describe_tasks(
        cluster=cluster_name,
        tasks=tasks_response['taskArns']
    )
    
    for task in task_details['tasks']:
        task_id = task['taskArn'].split('/')[-1]
        print(f"\n   Task: {task_id}")
        print(f"     Status: {task['lastStatus']}")
        print(f"     Health: {task.get('healthStatus', 'UNKNOWN')}")
        print(f"     Started: {task.get('startedAt', 'N/A')}")
        
        # Calculate uptime
        if 'startedAt' in task:
            uptime = datetime.now(task['startedAt'].tzinfo) - task['startedAt']
            uptime_seconds = uptime.total_seconds()
            print(f"     Uptime: {int(uptime_seconds)}s ({uptime_seconds/60:.1f} minutes)")
            
            if uptime_seconds < 120:
                print(f"     ⚠️  Task is still starting up (< 2 minutes)")
        
        # Get task IP and network details
        task_ip = None
        for attachment in task.get('attachments', []):
            if attachment['type'] == 'ElasticNetworkInterface':
                for detail in attachment['details']:
                    if detail['name'] == 'privateIPv4Address':
                        task_ip = detail['value']
                        print(f"     Private IP: {task_ip}")
                    elif detail['name'] == 'networkInterfaceId':
                        eni_id = detail['value']
                        print(f"     ENI: {eni_id}")
                        
                        # Get ENI details
                        eni_response = ec2.describe_network_interfaces(
                            NetworkInterfaceIds=[eni_id]
                        )
                        
                        if eni_response['NetworkInterfaces']:
                            eni = eni_response['NetworkInterfaces'][0]
                            sgs = [sg['GroupId'] for sg in eni['Groups']]
                            print(f"     Security Groups: {sgs}")
                            print(f"     Subnet: {eni['SubnetId']}")
        
        # Check container status
        print(f"\n     Containers:")
        for container in task.get('containers', []):
            print(f"       {container['name']}: {container['lastStatus']}")
            if 'healthStatus' in container:
                print(f"         Health: {container['healthStatus']}")
            if 'networkInterfaces' in container:
                for ni in container['networkInterfaces']:
                    print(f"         IP: {ni.get('privateIpv4Address', 'N/A')}")
    
    # Step 3: Check recent application logs
    print("\n3. Checking Recent Application Logs...")
    log_group = '/ecs/multimodal-lib-prod-app'
    
    try:
        # Get most recent log stream
        streams_response = logs.describe_log_streams(
            logGroupName=log_group,
            orderBy='LastEventTime',
            descending=True,
            limit=1
        )
        
        if streams_response['logStreams']:
            stream_name = streams_response['logStreams'][0]['logStreamName']
            last_event_time = streams_response['logStreams'][0].get('lastEventTimestamp', 0)
            last_event_dt = datetime.fromtimestamp(last_event_time / 1000)
            
            print(f"   Latest log stream: {stream_name}")
            print(f"   Last event: {last_event_dt}")
            
            # Check if logs are recent
            time_since_last_log = datetime.now() - last_event_dt
            if time_since_last_log.total_seconds() > 300:
                print(f"   ⚠️  WARNING: No logs in last {time_since_last_log.total_seconds()/60:.1f} minutes")
                print(f"   Application may have crashed or stopped logging")
            else:
                print(f"   ✓ Recent logs found ({time_since_last_log.total_seconds():.0f}s ago)")
            
            # Get recent log events
            events_response = logs.get_log_events(
                logGroupName=log_group,
                logStreamName=stream_name,
                limit=30,
                startFromHead=False
            )
            
            print(f"\n   Recent log entries (last 30):")
            
            # Look for key indicators
            has_uvicorn_running = False
            has_health_checks = False
            has_errors = False
            
            for event in events_response['events'][-30:]:
                timestamp = datetime.fromtimestamp(event['timestamp'] / 1000)
                message = event['message'].strip()
                
                # Check for key patterns
                if 'Uvicorn running on' in message:
                    has_uvicorn_running = True
                    print(f"     [{timestamp.strftime('%H:%M:%S')}] ✓ {message}")
                elif 'health' in message.lower():
                    has_health_checks = True
                    print(f"     [{timestamp.strftime('%H:%M:%S')}] ℹ {message}")
                elif 'error' in message.lower() or 'exception' in message.lower():
                    has_errors = True
                    print(f"     [{timestamp.strftime('%H:%M:%S')}] ✗ {message}")
                elif 'GET' in message or 'POST' in message:
                    print(f"     [{timestamp.strftime('%H:%M:%S')}]   {message}")
            
            print(f"\n   Log Analysis:")
            print(f"     Uvicorn running: {'✓' if has_uvicorn_running else '✗'}")
            print(f"     Health checks: {'✓' if has_health_checks else '✗'}")
            print(f"     Errors: {'✗ YES' if has_errors else '✓ None'}")
            
            if not has_uvicorn_running:
                print(f"\n   ⚠️  WARNING: No 'Uvicorn running' message found")
                print(f"   Application may not have started successfully")
            
            if not has_health_checks:
                print(f"\n   ⚠️  WARNING: No health check requests in logs")
                print(f"   ALB may not be able to reach the application")
    
    except Exception as e:
        print(f"   ✗ Could not retrieve logs: {e}")
    
    # Step 4: Check target group health
    print("\n4. Checking Target Group Health...")
    tg_name = 'multimodal-lib-prod-tg-v2'
    
    try:
        tg_response = elbv2.describe_target_groups(Names=[tg_name])
        tg_arn = tg_response['TargetGroups'][0]['TargetGroupArn']
        
        health_response = elbv2.describe_target_health(TargetGroupArn=tg_arn)
        
        print(f"   Target Group: {tg_name}")
        print(f"   Registered Targets: {len(health_response['TargetHealthDescriptions'])}")
        
        for target_health in health_response['TargetHealthDescriptions']:
            target = target_health['Target']
            health = target_health['TargetHealth']
            
            print(f"\n     Target: {target['Id']}:{target['Port']}")
            print(f"       State: {health['State']}")
            
            if health['State'] == 'healthy':
                print(f"       ✓ HEALTHY")
            else:
                print(f"       ✗ {health['State'].upper()}")
                if 'Reason' in health:
                    print(f"       Reason: {health['Reason']}")
                if 'Description' in health:
                    print(f"       Description: {health['Description']}")
    
    except Exception as e:
        print(f"   ✗ Could not check target health: {e}")
    
    # Step 5: Summary
    print("\n" + "=" * 80)
    print("STABILITY SUMMARY")
    print("=" * 80)
    
    print(f"\nService Status:")
    print(f"  Running Tasks: {service['runningCount']}/{service['desiredCount']}")
    print(f"  Service Status: {service['status']}")
    
    if service['runningCount'] == 0:
        print(f"\n✗ CRITICAL: No running tasks!")
        print(f"\nRecommendations:")
        print(f"  1. Check service events for deployment failures")
        print(f"  2. Check task stopped reason")
        print(f"  3. Review application logs for startup errors")
        print(f"  4. Verify task definition is correct")
    elif service['runningCount'] < service['desiredCount']:
        print(f"\n⚠️  WARNING: Service is not at desired capacity")
        print(f"\nRecommendations:")
        print(f"  1. Check why tasks are not starting")
        print(f"  2. Review recent service events")
        print(f"  3. Check resource availability")
    else:
        print(f"\n✓ Service appears stable")
        print(f"\nNext steps:")
        print(f"  1. Verify application is responding to requests")
        print(f"  2. Check ALB configuration")
        print(f"  3. Test connectivity from ALB to tasks")
    
    # Save results
    timestamp = int(time.time())
    filename = f'service-stability-check-{timestamp}.json'
    
    results = {
        'timestamp': datetime.now().isoformat(),
        'service': {
            'name': service['serviceName'],
            'status': service['status'],
            'desired_count': service['desiredCount'],
            'running_count': service['runningCount'],
            'pending_count': service['pendingCount']
        },
        'tasks': [
            {
                'task_id': t['taskArn'].split('/')[-1],
                'status': t['lastStatus'],
                'health': t.get('healthStatus', 'UNKNOWN'),
                'started_at': t.get('startedAt').isoformat() if 'startedAt' in t else None
            }
            for t in task_details['tasks']
        ] if 'task_details' in locals() else []
    }
    
    with open(filename, 'w') as f:
        json.dump(results, f, indent=2, default=str)
    
    print(f"\nResults saved to: {filename}")

if __name__ == '__main__':
    main()
