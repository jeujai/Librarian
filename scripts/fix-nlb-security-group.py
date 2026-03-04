#!/usr/bin/env python3
"""
Fix NLB Security Group Configuration
=====================================

This script adds the missing security group rule to allow traffic on port 8000,
which is required for the NLB to reach the ECS task.

The issue: Security group only allows ports 80 and 443, but the application
runs on port 8000.

Usage:
    python scripts/fix-nlb-security-group.py
"""

import boto3
import json
from datetime import datetime

# Configuration
SECURITY_GROUP_ID = "sg-0135b368e20b7bd01"
VPC_CIDR = "10.0.0.0/16"
APPLICATION_PORT = 8000

# Initialize AWS client
ec2_client = boto3.client('ec2', region_name='us-east-1')


def add_port_8000_rule():
    """Add security group rule to allow traffic on port 8000."""
    print("\n" + "="*80)
    print("FIXING SECURITY GROUP CONFIGURATION")
    print("="*80)
    print(f"Security Group: {SECURITY_GROUP_ID}")
    print(f"Adding rule: TCP port {APPLICATION_PORT} from {VPC_CIDR}")
    
    try:
        # Add inbound rule for port 8000
        response = ec2_client.authorize_security_group_ingress(
            GroupId=SECURITY_GROUP_ID,
            IpPermissions=[
                {
                    'IpProtocol': 'tcp',
                    'FromPort': APPLICATION_PORT,
                    'ToPort': APPLICATION_PORT,
                    'IpRanges': [
                        {
                            'CidrIp': VPC_CIDR,
                            'Description': 'Allow NLB to reach application on port 8000'
                        }
                    ]
                }
            ]
        )
        
        print(f"\n✅ Security Group Rule Added Successfully!")
        print(f"   Protocol: TCP")
        print(f"   Port: {APPLICATION_PORT}")
        print(f"   Source: {VPC_CIDR}")
        print(f"   Description: Allow NLB to reach application on port 8000")
        
        return True
        
    except ec2_client.exceptions.ClientError as e:
        if 'InvalidPermission.Duplicate' in str(e):
            print(f"\n✅ Rule already exists (no action needed)")
            return True
        else:
            print(f"\n❌ Error adding security group rule: {str(e)}")
            raise
    except Exception as e:
        print(f"\n❌ Error: {str(e)}")
        raise


def verify_security_group():
    """Verify the security group configuration."""
    print("\n" + "="*80)
    print("VERIFYING SECURITY GROUP CONFIGURATION")
    print("="*80)
    
    try:
        response = ec2_client.describe_security_groups(
            GroupIds=[SECURITY_GROUP_ID]
        )
        
        sg = response['SecurityGroups'][0]
        
        print(f"\nSecurity Group: {sg['GroupName']} ({sg['GroupId']})")
        print(f"VPC: {sg['VpcId']}")
        print(f"\nInbound Rules:")
        
        port_8000_found = False
        
        for rule in sg['IpPermissions']:
            protocol = rule['IpProtocol']
            from_port = rule.get('FromPort', 'N/A')
            to_port = rule.get('ToPort', 'N/A')
            
            if rule.get('IpRanges'):
                for ip_range in rule['IpRanges']:
                    cidr = ip_range['CidrIp']
                    desc = ip_range.get('Description', 'N/A')
                    print(f"  - {protocol} {from_port}-{to_port} from {cidr} ({desc})")
                    
                    if from_port == APPLICATION_PORT:
                        port_8000_found = True
        
        if port_8000_found:
            print(f"\n✅ Port {APPLICATION_PORT} rule is configured correctly")
            return True
        else:
            print(f"\n⚠️  Port {APPLICATION_PORT} rule not found")
            return False
            
    except Exception as e:
        print(f"\n❌ Error verifying security group: {str(e)}")
        raise


def main():
    """Main execution function."""
    print("\n" + "="*80)
    print("NLB SECURITY GROUP FIX")
    print("="*80)
    print(f"Timestamp: {datetime.now().isoformat()}")
    
    results = {
        'timestamp': datetime.now().isoformat(),
        'security_group_id': SECURITY_GROUP_ID,
        'port': APPLICATION_PORT,
        'vpc_cidr': VPC_CIDR,
        'success': False
    }
    
    try:
        # Add the rule
        add_ok = add_port_8000_rule()
        results['rule_added'] = add_ok
        
        # Verify configuration
        verify_ok = verify_security_group()
        results['verified'] = verify_ok
        
        results['success'] = add_ok and verify_ok
        
        # Save results
        import time
        timestamp = int(time.time())
        filename = f"nlb-security-group-fix-{timestamp}.json"
        with open(filename, 'w') as f:
            json.dump(results, f, indent=2, default=str)
        print(f"\n💾 Results saved to: {filename}")
        
        # Final summary
        print("\n" + "="*80)
        print("FINAL SUMMARY")
        print("="*80)
        
        if results['success']:
            print("✅ Security Group Fix SUCCESSFUL!")
            print(f"\n📋 Next Steps:")
            print(f"   1. Wait 1-2 minutes for health checks to pass")
            print(f"   2. Verify target health status")
            print(f"   3. Test NLB connectivity")
            print(f"   4. Update CloudFront origin if successful")
        else:
            print("⚠️  Security Group Fix completed with warnings")
        
        print(f"\n🔍 Monitor target health:")
        print(f"   aws elbv2 describe-target-health \\")
        print(f"     --target-group-arn arn:aws:elasticloadbalancing:us-east-1:591222106065:targetgroup/multimodal-lib-prod-nlb-tg/e3896922f939759a")
        
    except Exception as e:
        print(f"\n❌ FATAL ERROR: {str(e)}")
        results['error'] = str(e)
        
        import time
        timestamp = int(time.time())
        filename = f"nlb-security-group-fix-error-{timestamp}.json"
        with open(filename, 'w') as f:
            json.dump(results, f, indent=2, default=str)
        print(f"\n💾 Error results saved to: {filename}")
        
        raise


if __name__ == '__main__':
    main()
