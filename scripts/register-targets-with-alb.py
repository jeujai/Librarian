#!/usr/bin/env python3
"""
Register ECS Tasks with ALB Target Group
Fixes the issue where targets are only registered with NLB
"""

import boto3
import json
import sys
from datetime import datetime

def save_results(data, filename_prefix):
    """Save results to JSON file"""
    timestamp = int(datetime.now().timestamp())
    filename = f"{filename_prefix}-{timestamp}.json"
    with open(filename, 'w') as f:
        json.dump(data, f, indent=2, default=str)
    return filename

def print_section(title):
    """Print a formatted section header"""
    print("\n" + "="*80)
    print(title)
    print("="*80)

def main():
    ecs = boto3.client('ecs', region_name='us-east-1')
    elbv2 = boto3.client('elbv2', region_name='us-east-1')
    
    results = {
        'timestamp': datetime.now().isoformat(),
        'operation': 'Register ECS Tasks with ALB Target Group'
    }
    
    print_section("REGISTER TARGETS WITH ALB")
    print(f"Timestamp: {results['timestamp']}")
    
    # 1. Get ALB Target Group ARN
    print_section("1. GET ALB TARGET GROUP")
    try:
        alb_response = elbv2.describe_load_balancers(
            Names=['multimodal-lib-prod-alb-v2']
        )
        alb = alb_response['LoadBalancers'][0]
        
        tg_response = elbv2.describe_target_groups(
            LoadBalancerArn=alb['LoadBalancerArn']
        )
        
        if not tg_response['TargetGroups']:
            print("❌ No target group found for ALB")
            results['error'] = 'No target group found'
            return results
        
        alb_tg = tg_response['TargetGroups'][0]
        alb_tg_arn = alb_tg['TargetGroupArn']
        
        results['alb_target_group'] = {
            'arn': alb_tg_arn,
            'name': alb_tg['TargetGroupName'],
            'port': alb_tg['Port'],
            'protocol': alb_tg['Protocol'],
            'target_type': alb_tg['TargetType']
        }
        
        print(f"Target Group: {alb_tg['TargetGroupName']}")
        print(f"ARN: {alb_tg_arn}")
        print(f"Port: {alb_tg['Port']}")
        print(f"Protocol: {alb_tg['Protocol']}")
        print(f"Target Type: {alb_tg['TargetType']}")
        
    except Exception as e:
        print(f"❌ Error getting ALB target group: {e}")
        results['error'] = str(e)
        return results
    
    # 2. Get Running ECS Tasks
    print_section("2. GET RUNNING ECS TASKS")
    try:
        tasks_response = ecs.list_tasks(
            cluster='multimodal-lib-prod-cluster',
            serviceName='multimodal-lib-prod-service',
            desiredStatus='RUNNING'
        )
        
        if not tasks_response['taskArns']:
            print("❌ No running tasks found")
            results['error'] = 'No running tasks'
            return results
        
        task_details = ecs.describe_tasks(
            cluster='multimodal-lib-prod-cluster',
            tasks=tasks_response['taskArns']
        )
        
        results['tasks'] = []
        targets_to_register = []
        
        for task in task_details['tasks']:
            task_id = task['taskArn'].split('/')[-1]
            
            # Get private IP from ENI
            private_ip = None
            for attachment in task.get('attachments', []):
                if attachment['type'] == 'ElasticNetworkInterface':
                    for detail in attachment['details']:
                        if detail['name'] == 'privateIPv4Address':
                            private_ip = detail['value']
                            break
            
            if private_ip:
                task_info = {
                    'task_id': task_id,
                    'private_ip': private_ip,
                    'status': task['lastStatus'],
                    'health': task.get('healthStatus', 'UNKNOWN')
                }
                results['tasks'].append(task_info)
                
                # Prepare target for registration
                # ALB target type is 'ip', so we register by IP
                targets_to_register.append({
                    'Id': private_ip,
                    'Port': 8000  # Application port
                })
                
                print(f"Task: {task_id}")
                print(f"  IP: {private_ip}")
                print(f"  Status: {task['lastStatus']}")
                print(f"  Health: {task.get('healthStatus', 'UNKNOWN')}")
        
        results['targets_to_register'] = targets_to_register
        print(f"\n✅ Found {len(targets_to_register)} targets to register")
        
    except Exception as e:
        print(f"❌ Error getting ECS tasks: {e}")
        results['error'] = str(e)
        return results
    
    # 3. Check Current ALB Targets
    print_section("3. CHECK CURRENT ALB TARGETS")
    try:
        current_health = elbv2.describe_target_health(
            TargetGroupArn=alb_tg_arn
        )
        
        current_targets = []
        for target in current_health['TargetHealthDescriptions']:
            current_targets.append({
                'id': target['Target']['Id'],
                'port': target['Target']['Port'],
                'state': target['TargetHealth']['State']
            })
            print(f"Current Target: {target['Target']['Id']}:{target['Target']['Port']}")
            print(f"  State: {target['TargetHealth']['State']}")
        
        results['current_targets'] = current_targets
        
        if not current_targets:
            print("\n⚠️  No targets currently registered with ALB")
        
    except Exception as e:
        print(f"❌ Error checking current targets: {e}")
        results['current_targets'] = {'error': str(e)}
    
    # 4. Register Targets with ALB
    print_section("4. REGISTER TARGETS WITH ALB")
    try:
        if not targets_to_register:
            print("⚠️  No targets to register")
            results['registration'] = 'No targets to register'
            return results
        
        print(f"Registering {len(targets_to_register)} targets...")
        for target in targets_to_register:
            print(f"  - {target['Id']}:{target['Port']}")
        
        response = elbv2.register_targets(
            TargetGroupArn=alb_tg_arn,
            Targets=targets_to_register
        )
        
        results['registration'] = {
            'status': 'success',
            'targets_registered': len(targets_to_register),
            'response': response
        }
        
        print(f"\n✅ Successfully registered {len(targets_to_register)} targets")
        
    except Exception as e:
        print(f"❌ Error registering targets: {e}")
        results['registration'] = {'error': str(e)}
        return results
    
    # 5. Verify Registration
    print_section("5. VERIFY REGISTRATION")
    try:
        import time
        print("Waiting 5 seconds for registration to propagate...")
        time.sleep(5)
        
        health_response = elbv2.describe_target_health(
            TargetGroupArn=alb_tg_arn
        )
        
        results['verification'] = []
        print("\nTarget Health Status:")
        for target in health_response['TargetHealthDescriptions']:
            target_info = {
                'id': target['Target']['Id'],
                'port': target['Target']['Port'],
                'state': target['TargetHealth']['State']
            }
            
            if 'Reason' in target['TargetHealth']:
                target_info['reason'] = target['TargetHealth']['Reason']
            if 'Description' in target['TargetHealth']:
                target_info['description'] = target['TargetHealth']['Description']
            
            results['verification'].append(target_info)
            
            print(f"  {target['Target']['Id']}:{target['Target']['Port']}")
            print(f"    State: {target['TargetHealth']['State']}")
            if 'Reason' in target['TargetHealth']:
                print(f"    Reason: {target['TargetHealth']['Reason']}")
            if 'Description' in target['TargetHealth']:
                print(f"    Description: {target['TargetHealth']['Description']}")
        
        # Check if any targets are healthy
        healthy_count = sum(1 for t in results['verification'] if t['state'] == 'healthy')
        if healthy_count > 0:
            print(f"\n✅ {healthy_count} target(s) are healthy")
        else:
            print("\n⚠️  No targets are healthy yet (may take 30-60 seconds)")
        
    except Exception as e:
        print(f"❌ Error verifying registration: {e}")
        results['verification'] = {'error': str(e)}
    
    # Save results
    filename = save_results(results, 'alb-target-registration')
    
    print_section("SUMMARY")
    print(f"✅ Target registration completed")
    print(f"📄 Results saved to: {filename}")
    print(f"\n📋 Next Steps:")
    print(f"   1. Wait 30-60 seconds for health checks to pass")
    print(f"   2. Test ALB connectivity:")
    print(f"      curl http://{alb['DNSName']}/health")
    print(f"   3. Monitor target health:")
    print(f"      aws elbv2 describe-target-health --target-group-arn {alb_tg_arn}")
    
    return results

if __name__ == '__main__':
    try:
        results = main()
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
