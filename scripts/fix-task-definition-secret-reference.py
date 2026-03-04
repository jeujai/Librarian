#!/usr/bin/env python3
"""
Fix ALB to Task Security Group Communication

The ALB and ECS tasks are in the same security group (sg-0135b368e20b7bd01),
but the security group doesn't have a rule allowing traffic from itself.
This causes the ALB to be unable to reach the tasks on port 8000.

Solution: Add an ingress rule allowing the security group to communicate with itself on port 8000.
"""

import boto3
import json
from datetime import datetime

def main():
    ec2 = boto3.client('ec2', region_name='us-east-1')
    
    security_group_id = 'sg-0135b368e20b7bd01'
    
    print("=" * 80)
    print("FIX ALB TO TASK SECURITY GROUP COMMUNICATION")
    print("=" * 80)
    print()
    
    print("🔍 Problem:")
    print("   ALB and ECS tasks use the same security group")
    print("   Security group allows 0.0.0.0/0 on port 8000")
    print("   BUT: Security group doesn't allow traffic from itself")
    print("   Result: ALB cannot reach tasks, causing 504 Gateway Timeout")
    print()
    
    print("🔧 Solution:")
    print(f"   Add ingress rule to {security_group_id}")
    print("   Allow traffic from itself on port 8000")
    print()
    
    try:
        # Add ingress rule allowing the security group to communicate with itself
        response = ec2.authorize_security_group_ingress(
            GroupId=security_group_id,
            IpPermissions=[
                {
                    'IpProtocol': 'tcp',
                    'FromPort': 8000,
                    'ToPort': 8000,
                    'UserIdGroupPairs': [
                        {
                            'GroupId': security_group_id,
                            'Description': 'Allow ALB to communicate with ECS tasks'
                        }
                    ]
                }
            ]
        )
        
        print("✅ Security group rule added successfully!")
        print()
        print("Rule details:")
        print(f"   Protocol: TCP")
        print(f"   Port: 8000")
        print(f"   Source: {security_group_id} (self)")
        print()
        
    except ec2.exceptions.ClientError as e:
        if 'InvalidPermission.Duplicate' in str(e):
            print("ℹ️  Rule already exists - no action needed")
            print()
        else:
            print(f"❌ Error adding security group rule: {e}")
            raise
    
    # Verify the rule was added
    print("🔍 Verifying security group rules...")
    sg_response = ec2.describe_security_groups(GroupIds=[security_group_id])
    sg = sg_response['SecurityGroups'][0]
    
    print()
    print("Current ingress rules:")
    for rule in sg['IpPermissions']:
        from_port = rule.get('FromPort', 'N/A')
        to_port = rule.get('ToPort', 'N/A')
        protocol = rule.get('IpProtocol', 'N/A')
        
        if rule.get('UserIdGroupPairs'):
            for pair in rule['UserIdGroupPairs']:
                source = pair.get('GroupId', 'N/A')
                desc = pair.get('Description', '')
                print(f"   {protocol} {from_port}-{to_port} from {source} ({desc})")
        
        if rule.get('IpRanges'):
            for ip_range in rule['IpRanges']:
                source = ip_range.get('CidrIp', 'N/A')
                desc = ip_range.get('Description', '')
                print(f"   {protocol} {from_port}-{to_port} from {source} ({desc})")
    
    print()
    print("=" * 80)
    print("✅ SECURITY GROUP FIX COMPLETE")
    print("=" * 80)
    print()
    print("What happens next:")
    print("1. ALB can now communicate with ECS tasks on port 8000")
    print("2. Health checks should start passing immediately")
    print("3. Application should be accessible via ALB")
    print()
    print("Test the fix:")
    print("  curl http://multimodal-lib-prod-alb-v2-1090291461.us-east-1.elb.amazonaws.com/health/simple")
    print()
    print("Expected result:")
    print("  HTTP 200 OK with health status response")
    print()
    
    # Save results
    results = {
        'timestamp': datetime.now().isoformat(),
        'issue': 'alb_to_task_security_group_communication',
        'root_cause': 'Security group does not allow traffic from itself',
        'security_group_id': security_group_id,
        'rule_added': {
            'protocol': 'tcp',
            'port': 8000,
            'source': security_group_id
        },
        'alb_dns': 'multimodal-lib-prod-alb-v2-1090291461.us-east-1.elb.amazonaws.com'
    }
    
    filename = f"alb-security-group-fix-{int(datetime.now().timestamp())}.json"
    with open(filename, 'w') as f:
        json.dump(results, f, indent=2)
    
    print(f"Results saved to: {filename}")
    print()

if __name__ == '__main__':
    main()
