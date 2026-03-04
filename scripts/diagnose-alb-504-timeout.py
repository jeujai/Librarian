#!/usr/bin/env python3
"""
Diagnose ALB 504 Gateway Timeout Issue

The target is showing as healthy, but the ALB returns 504 Gateway Timeout.
This script investigates ALB configuration, listener rules, and timeout settings.
"""

import boto3
import json
import time
from datetime import datetime

def main():
    elbv2 = boto3.client('elbv2')
    ec2 = boto3.client('ec2')
    ecs = boto3.client('ecs')
    logs = boto3.client('logs')
    
    print("=" * 80)
    print("ALB 504 Gateway Timeout Diagnosis")
    print("=" * 80)
    
    alb_name = 'multimodal-lib-prod-alb-v2'
    tg_name = 'multimodal-lib-prod-tg-v2'
    cluster_name = 'multimodal-lib-prod-cluster'
    service_name = 'multimodal-lib-prod-service-alb'
    
    results = {
        'timestamp': datetime.now().isoformat(),
        'alb_name': alb_name,
        'target_group_name': tg_name,
        'findings': []
    }
    
    # Step 1: Get ALB details
    print("\n1. Checking ALB Configuration...")
    alb_response = elbv2.describe_load_balancers(Names=[alb_name])
    alb = alb_response['LoadBalancers'][0]
    
    print(f"   ALB: {alb['LoadBalancerName']}")
    print(f"   DNS: {alb['DNSName']}")
    print(f"   State: {alb['State']['Code']}")
    print(f"   Scheme: {alb['Scheme']}")
    print(f"   VPC: {alb['VpcId']}")
    print(f"   Subnets: {alb['AvailabilityZones']}")
    
    results['alb'] = {
        'dns_name': alb['DNSName'],
        'state': alb['State']['Code'],
        'scheme': alb['Scheme'],
        'vpc_id': alb['VpcId'],
        'subnets': [az['SubnetId'] for az in alb['AvailabilityZones']]
    }
    
    # Step 2: Check ALB attributes (including timeout settings)
    print("\n2. Checking ALB Attributes (Timeout Settings)...")
    alb_arn = alb['LoadBalancerArn']
    
    attrs_response = elbv2.describe_load_balancer_attributes(
        LoadBalancerArn=alb_arn
    )
    
    print("   ALB Attributes:")
    timeout_attrs = {}
    for attr in attrs_response['Attributes']:
        if 'timeout' in attr['Key'].lower() or 'idle' in attr['Key'].lower():
            print(f"     {attr['Key']}: {attr['Value']}")
            timeout_attrs[attr['Key']] = attr['Value']
    
    results['alb_attributes'] = timeout_attrs
    
    # Check idle timeout specifically
    idle_timeout = int(timeout_attrs.get('idle_timeout.timeout_seconds', '60'))
    if idle_timeout < 60:
        results['findings'].append({
            'severity': 'high',
            'issue': 'ALB idle timeout too low',
            'detail': f'Idle timeout is {idle_timeout}s, should be at least 60s for slow-starting applications',
            'recommendation': 'Increase idle timeout to 120s or more'
        })
        print(f"   ⚠️  WARNING: Idle timeout is {idle_timeout}s (may be too low)")
    else:
        print(f"   ✓ Idle timeout is {idle_timeout}s (acceptable)")
    
    # Step 3: Check listeners and rules
    print("\n3. Checking ALB Listeners and Rules...")
    listeners_response = elbv2.describe_listeners(LoadBalancerArn=alb_arn)
    
    print(f"   Found {len(listeners_response['Listeners'])} listener(s)")
    
    for listener in listeners_response['Listeners']:
        protocol = listener['Protocol']
        port = listener['Port']
        print(f"\n   Listener: {protocol}:{port}")
        print(f"     ARN: {listener['ListenerArn']}")
        
        # Check default actions
        print(f"     Default Actions:")
        for action in listener['DefaultActions']:
            print(f"       Type: {action['Type']}")
            if action['Type'] == 'forward':
                if 'TargetGroupArn' in action:
                    tg_arn = action['TargetGroupArn']
                    tg_name_from_arn = tg_arn.split(':')[-1].split('/')[-2]
                    print(f"       Target Group: {tg_name_from_arn}")
                    
                    if tg_name_from_arn != tg_name:
                        results['findings'].append({
                            'severity': 'critical',
                            'issue': 'Listener forwarding to wrong target group',
                            'detail': f'Listener forwards to {tg_name_from_arn}, expected {tg_name}',
                            'recommendation': 'Update listener to forward to correct target group'
                        })
                        print(f"       ✗ WRONG TARGET GROUP! Expected {tg_name}")
                    else:
                        print(f"       ✓ Forwarding to correct target group")
        
        # Check for rules
        rules_response = elbv2.describe_rules(ListenerArn=listener['ListenerArn'])
        print(f"     Rules: {len(rules_response['Rules'])}")
        
        for rule in rules_response['Rules']:
            if rule['IsDefault']:
                continue
            print(f"       Rule Priority: {rule.get('Priority', 'default')}")
            print(f"       Conditions: {rule.get('Conditions', [])}")
            print(f"       Actions: {[a['Type'] for a in rule.get('Actions', [])]}")
    
    results['listeners'] = [
        {
            'protocol': l['Protocol'],
            'port': l['Port'],
            'default_action_type': l['DefaultActions'][0]['Type'] if l['DefaultActions'] else None
        }
        for l in listeners_response['Listeners']
    ]
    
    # Step 4: Check target group configuration
    print("\n4. Checking Target Group Configuration...")
    tg_response = elbv2.describe_target_groups(Names=[tg_name])
    tg = tg_response['TargetGroups'][0]
    tg_arn = tg['TargetGroupArn']
    
    print(f"   Target Group: {tg['TargetGroupName']}")
    print(f"   Protocol: {tg['Protocol']}")
    print(f"   Port: {tg['Port']}")
    print(f"   Target Type: {tg['TargetType']}")
    print(f"   VPC: {tg['VpcId']}")
    
    # Health check settings
    print(f"\n   Health Check Settings:")
    print(f"     Protocol: {tg['HealthCheckProtocol']}")
    print(f"     Port: {tg.get('HealthCheckPort', 'traffic-port')}")
    print(f"     Path: {tg.get('HealthCheckPath', '/')}")
    print(f"     Interval: {tg['HealthCheckIntervalSeconds']}s")
    print(f"     Timeout: {tg['HealthCheckTimeoutSeconds']}s")
    print(f"     Healthy Threshold: {tg['HealthyThresholdCount']}")
    print(f"     Unhealthy Threshold: {tg['UnhealthyThresholdCount']}")
    
    results['target_group'] = {
        'protocol': tg['Protocol'],
        'port': tg['Port'],
        'target_type': tg['TargetType'],
        'health_check': {
            'protocol': tg['HealthCheckProtocol'],
            'port': tg.get('HealthCheckPort', 'traffic-port'),
            'path': tg.get('HealthCheckPath', '/'),
            'interval': tg['HealthCheckIntervalSeconds'],
            'timeout': tg['HealthCheckTimeoutSeconds'],
            'healthy_threshold': tg['HealthyThresholdCount'],
            'unhealthy_threshold': tg['UnhealthyThresholdCount']
        }
    }
    
    # Check target group attributes
    print("\n   Target Group Attributes:")
    tg_attrs_response = elbv2.describe_target_group_attributes(
        TargetGroupArn=tg_arn
    )
    
    for attr in tg_attrs_response['Attributes']:
        if 'timeout' in attr['Key'].lower() or 'deregistration' in attr['Key'].lower():
            print(f"     {attr['Key']}: {attr['Value']}")
    
    # Step 5: Check target health
    print("\n5. Checking Target Health...")
    health_response = elbv2.describe_target_health(TargetGroupArn=tg_arn)
    
    print(f"   Registered Targets: {len(health_response['TargetHealthDescriptions'])}")
    
    for target_health in health_response['TargetHealthDescriptions']:
        target = target_health['Target']
        health = target_health['TargetHealth']
        
        print(f"\n   Target: {target['Id']}:{target['Port']}")
        print(f"     State: {health['State']}")
        if 'Reason' in health:
            print(f"     Reason: {health['Reason']}")
        if 'Description' in health:
            print(f"     Description: {health['Description']}")
        
        if health['State'] == 'healthy':
            print(f"     ✓ Target is HEALTHY")
        else:
            print(f"     ✗ Target is {health['State'].upper()}")
            results['findings'].append({
                'severity': 'high',
                'issue': f'Target {target["Id"]} is {health["State"]}',
                'detail': health.get('Description', 'No description'),
                'recommendation': 'Investigate why target is not healthy'
            })
    
    results['target_health'] = [
        {
            'target_id': th['Target']['Id'],
            'port': th['Target']['Port'],
            'state': th['TargetHealth']['State'],
            'reason': th['TargetHealth'].get('Reason'),
            'description': th['TargetHealth'].get('Description')
        }
        for th in health_response['TargetHealthDescriptions']
    ]
    
    # Step 6: Check ECS task details
    print("\n6. Checking ECS Task Details...")
    tasks_response = ecs.list_tasks(
        cluster=cluster_name,
        serviceName=service_name,
        desiredStatus='RUNNING'
    )
    
    if tasks_response['taskArns']:
        task_details = ecs.describe_tasks(
            cluster=cluster_name,
            tasks=tasks_response['taskArns']
        )
        
        for task in task_details['tasks']:
            task_id = task['taskArn'].split('/')[-1]
            print(f"\n   Task: {task_id}")
            print(f"     Status: {task['lastStatus']}")
            print(f"     Health: {task.get('healthStatus', 'UNKNOWN')}")
            
            # Get task IP
            for attachment in task.get('attachments', []):
                if attachment['type'] == 'ElasticNetworkInterface':
                    for detail in attachment['details']:
                        if detail['name'] == 'privateIPv4Address':
                            task_ip = detail['value']
                            print(f"     Private IP: {task_ip}")
                            
                            # Check if this IP matches registered targets
                            target_ips = [th['Target']['Id'] for th in health_response['TargetHealthDescriptions']]
                            if task_ip in target_ips:
                                print(f"     ✓ Task IP matches registered target")
                            else:
                                print(f"     ✗ Task IP NOT in target group!")
                                results['findings'].append({
                                    'severity': 'critical',
                                    'issue': 'Task IP not registered in target group',
                                    'detail': f'Task IP {task_ip} not found in target group',
                                    'recommendation': 'Check ECS service target group configuration'
                                })
    
    # Step 7: Test ALB endpoint
    print("\n7. Testing ALB Endpoint...")
    alb_dns = alb['DNSName']
    
    print(f"   Testing: http://{alb_dns}/health/simple")
    print(f"   (This will likely timeout if the issue persists)")
    
    # We can't actually test from here, but we can provide the command
    print(f"\n   To test manually, run:")
    print(f"   curl -v -m 10 http://{alb_dns}/health/simple")
    
    # Step 8: Check recent application logs
    print("\n8. Checking Recent Application Logs...")
    log_group = '/ecs/multimodal-lib-prod-app'
    
    try:
        # Get recent log streams
        streams_response = logs.describe_log_streams(
            logGroupName=log_group,
            orderBy='LastEventTime',
            descending=True,
            limit=1
        )
        
        if streams_response['logStreams']:
            stream_name = streams_response['logStreams'][0]['logStreamName']
            print(f"   Latest log stream: {stream_name}")
            
            # Get recent log events
            events_response = logs.get_log_events(
                logGroupName=log_group,
                logStreamName=stream_name,
                limit=20,
                startFromHead=False
            )
            
            print(f"\n   Recent log entries:")
            for event in events_response['events'][-10:]:
                timestamp = datetime.fromtimestamp(event['timestamp'] / 1000)
                message = event['message'].strip()
                print(f"     [{timestamp.strftime('%H:%M:%S')}] {message}")
                
                # Look for health check requests
                if 'health' in message.lower():
                    print(f"       ^ Health check detected")
    
    except Exception as e:
        print(f"   Could not retrieve logs: {e}")
    
    # Step 9: Summary and recommendations
    print("\n" + "=" * 80)
    print("DIAGNOSIS SUMMARY")
    print("=" * 80)
    
    if not results['findings']:
        print("\n✓ No configuration issues found")
        print("\nPossible causes of 504 Gateway Timeout:")
        print("1. Application is slow to respond (>60s)")
        print("2. Application is not actually listening on port 8000")
        print("3. Network path issue between ALB and target")
        print("4. ALB idle timeout too low for slow application startup")
        print("\nRecommendations:")
        print("- Increase ALB idle timeout to 120s")
        print("- Check application logs for incoming requests")
        print("- Verify application is responding within timeout period")
        print("- Test direct connectivity to task IP from within VPC")
    else:
        print(f"\n✗ Found {len(results['findings'])} issue(s):")
        for i, finding in enumerate(results['findings'], 1):
            print(f"\n{i}. [{finding['severity'].upper()}] {finding['issue']}")
            print(f"   Detail: {finding['detail']}")
            print(f"   Recommendation: {finding['recommendation']}")
    
    # Save results
    timestamp = int(time.time())
    filename = f'alb-504-diagnosis-{timestamp}.json'
    with open(filename, 'w') as f:
        json.dump(results, f, indent=2, default=str)
    
    print(f"\nResults saved to: {filename}")

if __name__ == '__main__':
    main()
