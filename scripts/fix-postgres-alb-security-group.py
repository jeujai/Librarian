#!/usr/bin/env python3
"""
Fix Postgres security group to allow traffic from ALB.
This adds an inbound rule to the Postgres security group allowing port 5432 from the ALB security group.
"""

import boto3
import json
import sys
from datetime import datetime

def get_timestamp():
    return datetime.now().strftime("%Y%m%d_%H%M%S")

def fix_postgres_alb_security_group():
    """Add security group rule to allow ALB to connect to Postgres"""
    
    print("=" * 80)
    print("Fix Postgres Security Group for ALB Connectivity")
    print("=" * 80)
    
    ec2 = boto3.client('ec2', region_name='us-east-1')
    
    # From the connectivity test results
    postgres_sg = 'sg-06444720c970a9054'  # ml-librarian-postgres-sg
    alb_sg = 'sg-0135b368e20b7bd01'  # multimodal-lib-prod-alb-sg
    postgres_port = 5432
    
    results = {
        'timestamp': get_timestamp(),
        'postgres_sg': postgres_sg,
        'alb_sg': alb_sg,
        'port': postgres_port,
        'success': False,
        'error': None
    }
    
    print(f"\nPostgres Security Group: {postgres_sg}")
    print(f"ALB Security Group: {alb_sg}")
    print(f"Port: {postgres_port}")
    
    # Check current rules
    print("\n1. Checking current Postgres security group rules...")
    try:
        sg_info = ec2.describe_security_groups(GroupIds=[postgres_sg])['SecurityGroups'][0]
        print(f"   Security Group: {sg_info['GroupName']}")
        print(f"   Current ingress rules: {len(sg_info['IpPermissions'])}")
        
        # Check if rule already exists
        rule_exists = False
        for rule in sg_info['IpPermissions']:
            if rule.get('FromPort') == postgres_port:
                for sg_pair in rule.get('UserIdGroupPairs', []):
                    if sg_pair['GroupId'] == alb_sg:
                        rule_exists = True
                        print(f"   ✓ Rule already exists allowing {alb_sg} on port {postgres_port}")
                        break
        
        if rule_exists:
            print("\n✓ Security group rule already configured correctly!")
            results['success'] = True
            results['already_configured'] = True
            return results
            
    except Exception as e:
        print(f"   ❌ Error checking security group: {e}")
        results['error'] = str(e)
        return results
    
    # Add the rule
    print("\n2. Adding security group rule...")
    try:
        response = ec2.authorize_security_group_ingress(
            GroupId=postgres_sg,
            IpPermissions=[
                {
                    'IpProtocol': 'tcp',
                    'FromPort': postgres_port,
                    'ToPort': postgres_port,
                    'UserIdGroupPairs': [
                        {
                            'GroupId': alb_sg,
                            'Description': 'Allow ALB to connect to Postgres'
                        }
                    ]
                }
            ]
        )
        
        print(f"   ✓ Successfully added security group rule!")
        print(f"   Response: {response['ResponseMetadata']['HTTPStatusCode']}")
        
        results['success'] = True
        results['response'] = response
        
    except Exception as e:
        if 'InvalidPermission.Duplicate' in str(e):
            print(f"   ✓ Rule already exists (duplicate)")
            results['success'] = True
            results['already_configured'] = True
        else:
            print(f"   ❌ Error adding security group rule: {e}")
            results['error'] = str(e)
            return results
    
    # Verify the rule was added
    print("\n3. Verifying security group rule...")
    try:
        sg_info = ec2.describe_security_groups(GroupIds=[postgres_sg])['SecurityGroups'][0]
        
        rule_found = False
        for rule in sg_info['IpPermissions']:
            if rule.get('FromPort') == postgres_port:
                for sg_pair in rule.get('UserIdGroupPairs', []):
                    if sg_pair['GroupId'] == alb_sg:
                        rule_found = True
                        print(f"   ✓ Verified: Rule exists allowing {alb_sg} on port {postgres_port}")
                        break
        
        if not rule_found:
            print(f"   ❌ Rule not found after adding!")
            results['success'] = False
            results['error'] = "Rule not found after adding"
        
    except Exception as e:
        print(f"   ❌ Error verifying security group: {e}")
        results['error'] = str(e)
    
    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    
    if results['success']:
        print("\n✓ SUCCESS!")
        print("  Postgres security group now allows traffic from ALB.")
        print("  ECS tasks behind the ALB should now be able to connect to Postgres.")
        print("\nNext steps:")
        print("  1. Wait a few minutes for the security group change to propagate")
        print("  2. Check ECS task health in the target group")
        print("  3. Review application logs for database connectivity")
    else:
        print("\n❌ FAILED!")
        if results.get('error'):
            print(f"  Error: {results['error']}")
    
    # Save results
    output_file = f"postgres-alb-sg-fix-{get_timestamp()}.json"
    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2, default=str)
    
    print(f"\n📄 Results saved to: {output_file}")
    
    return results

if __name__ == '__main__':
    try:
        results = fix_postgres_alb_security_group()
        
        if results.get('success'):
            sys.exit(0)
        else:
            sys.exit(1)
            
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
