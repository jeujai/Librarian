#!/usr/bin/env python3
"""
Create new target group for ALB connectivity fix.

This script creates a new target group with optimized health check configuration
to resolve the ALB connectivity issue.
"""

import boto3
import json
import sys
from datetime import datetime
from typing import Dict, Any

def create_target_group() -> Dict[str, Any]:
    """
    Create new target group with optimized configuration.
    
    Returns:
        Dict containing creation results and target group details
    """
    client = boto3.client('elbv2', region_name='us-east-1')
    
    # Target group configuration from design document
    config = {
        'name': 'multimodal-lib-prod-tg-v2',
        'protocol': 'HTTP',
        'port': 8000,
        'vpc_id': 'vpc-0b2186b38779e77f6',
        'target_type': 'ip',
        'health_check': {
            'enabled': True,
            'protocol': 'HTTP',
            'path': '/api/health/simple',
            'interval_seconds': 30,
            'timeout_seconds': 29,
            'healthy_threshold_count': 2,
            'unhealthy_threshold_count': 2,
            'matcher': {'http_code': '200'}
        }
    }
    
    print("=" * 80)
    print("Creating New Target Group: multimodal-lib-prod-tg-v2")
    print("=" * 80)
    print(f"\nConfiguration:")
    print(f"  Name: {config['name']}")
    print(f"  Protocol: {config['protocol']}")
    print(f"  Port: {config['port']}")
    print(f"  VPC ID: {config['vpc_id']}")
    print(f"  Target Type: {config['target_type']}")
    print(f"\nHealth Check Configuration:")
    print(f"  Path: {config['health_check']['path']}")
    print(f"  Interval: {config['health_check']['interval_seconds']}s")
    print(f"  Timeout: {config['health_check']['timeout_seconds']}s")
    print(f"  Healthy Threshold: {config['health_check']['healthy_threshold_count']}")
    print(f"  Unhealthy Threshold: {config['health_check']['unhealthy_threshold_count']}")
    print(f"  Matcher: {config['health_check']['matcher']['http_code']}")
    print()
    
    try:
        # Create target group
        print("Creating target group...")
        response = client.create_target_group(
            Name=config['name'],
            Protocol=config['protocol'],
            Port=config['port'],
            VpcId=config['vpc_id'],
            TargetType=config['target_type'],
            HealthCheckEnabled=config['health_check']['enabled'],
            HealthCheckProtocol=config['health_check']['protocol'],
            HealthCheckPath=config['health_check']['path'],
            HealthCheckIntervalSeconds=config['health_check']['interval_seconds'],
            HealthCheckTimeoutSeconds=config['health_check']['timeout_seconds'],
            HealthyThresholdCount=config['health_check']['healthy_threshold_count'],
            UnhealthyThresholdCount=config['health_check']['unhealthy_threshold_count'],
            Matcher={'HttpCode': config['health_check']['matcher']['http_code']},
            Tags=[
                {'Key': 'Name', 'Value': config['name']},
                {'Key': 'Environment', 'Value': 'production'},
                {'Key': 'Application', 'Value': 'multimodal-librarian'},
                {'Key': 'Version', 'Value': 'v2'},
                {'Key': 'CreatedDate', 'Value': datetime.now().strftime('%Y-%m-%d')},
                {'Key': 'Purpose', 'Value': 'ALB-connectivity-fix'}
            ]
        )
        
        target_group = response['TargetGroups'][0]
        target_group_arn = target_group['TargetGroupArn']
        
        print(f"✅ Target group created successfully!")
        print(f"\nTarget Group Details:")
        print(f"  ARN: {target_group_arn}")
        print(f"  Name: {target_group['TargetGroupName']}")
        print(f"  Protocol: {target_group['Protocol']}")
        print(f"  Port: {target_group['Port']}")
        print(f"  VPC ID: {target_group['VpcId']}")
        print(f"  Target Type: {target_group['TargetType']}")
        
        # Verify health check configuration
        print("\n" + "=" * 80)
        print("Verifying Health Check Configuration")
        print("=" * 80)
        
        describe_response = client.describe_target_groups(
            TargetGroupArns=[target_group_arn]
        )
        
        verified_tg = describe_response['TargetGroups'][0]
        
        print(f"\nHealth Check Settings:")
        print(f"  Enabled: {verified_tg.get('HealthCheckEnabled', 'N/A')}")
        print(f"  Protocol: {verified_tg.get('HealthCheckProtocol', 'N/A')}")
        print(f"  Path: {verified_tg.get('HealthCheckPath', 'N/A')}")
        print(f"  Port: {verified_tg.get('HealthCheckPort', 'N/A')}")
        print(f"  Interval: {verified_tg.get('HealthCheckIntervalSeconds', 'N/A')}s")
        print(f"  Timeout: {verified_tg.get('HealthCheckTimeoutSeconds', 'N/A')}s")
        print(f"  Healthy Threshold: {verified_tg.get('HealthyThresholdCount', 'N/A')}")
        print(f"  Unhealthy Threshold: {verified_tg.get('UnhealthyThresholdCount', 'N/A')}")
        print(f"  Matcher: {verified_tg.get('Matcher', {}).get('HttpCode', 'N/A')}")
        
        # Prepare results
        results = {
            'success': True,
            'timestamp': datetime.now().isoformat(),
            'target_group': {
                'arn': target_group_arn,
                'name': target_group['TargetGroupName'],
                'protocol': target_group['Protocol'],
                'port': target_group['Port'],
                'vpc_id': target_group['VpcId'],
                'target_type': target_group['TargetType']
            },
            'health_check': {
                'enabled': verified_tg.get('HealthCheckEnabled'),
                'protocol': verified_tg.get('HealthCheckProtocol'),
                'path': verified_tg.get('HealthCheckPath'),
                'port': verified_tg.get('HealthCheckPort'),
                'interval_seconds': verified_tg.get('HealthCheckIntervalSeconds'),
                'timeout_seconds': verified_tg.get('HealthCheckTimeoutSeconds'),
                'healthy_threshold': verified_tg.get('HealthyThresholdCount'),
                'unhealthy_threshold': verified_tg.get('UnhealthyThresholdCount'),
                'matcher': verified_tg.get('Matcher', {}).get('HttpCode')
            },
            'configuration_used': config
        }
        
        # Save results to file
        timestamp = int(datetime.now().timestamp())
        output_file = f'target-group-creation-{timestamp}.json'
        with open(output_file, 'w') as f:
            json.dump(results, f, indent=2)
        
        print(f"\n✅ Results saved to: {output_file}")
        
        print("\n" + "=" * 80)
        print("Next Steps")
        print("=" * 80)
        print(f"\n1. Use this Target Group ARN in the next task:")
        print(f"   {target_group_arn}")
        print(f"\n2. Create the Application Load Balancer")
        print(f"3. Update ECS service to use this target group")
        print()
        
        return results
        
    except client.exceptions.DuplicateTargetGroupNameException:
        print(f"❌ Error: Target group '{config['name']}' already exists!")
        print(f"\nTo use the existing target group, run:")
        print(f"  aws elbv2 describe-target-groups --names {config['name']}")
        print(f"\nTo delete the existing target group first, run:")
        print(f"  aws elbv2 delete-target-group --target-group-arn <arn>")
        
        # Try to get existing target group info
        try:
            existing = client.describe_target_groups(Names=[config['name']])
            if existing['TargetGroups']:
                tg = existing['TargetGroups'][0]
                print(f"\nExisting Target Group ARN: {tg['TargetGroupArn']}")
        except Exception:
            pass
        
        return {
            'success': False,
            'error': 'DuplicateTargetGroupName',
            'message': f"Target group '{config['name']}' already exists"
        }
        
    except Exception as e:
        print(f"❌ Error creating target group: {str(e)}")
        return {
            'success': False,
            'error': type(e).__name__,
            'message': str(e)
        }

def main():
    """Main execution function."""
    print("\n" + "=" * 80)
    print("ALB Connectivity Fix - Task 1: Create New Target Group")
    print("=" * 80)
    print()
    
    results = create_target_group()
    
    if results['success']:
        print("\n✅ Task completed successfully!")
        sys.exit(0)
    else:
        print("\n❌ Task failed!")
        sys.exit(1)

if __name__ == '__main__':
    main()
