#!/usr/bin/env python3
"""
Test connectivity from multimodal-lib-prod-service-alb to Postgres database.
This script checks network connectivity, security groups, and database accessibility.
"""

import boto3
import json
import sys
from datetime import datetime

def get_timestamp():
    return datetime.now().strftime("%Y%m%d_%H%M%S")

def test_alb_postgres_connectivity():
    """Test connectivity between ALB and Postgres"""
    
    print("=" * 80)
    print("ALB to Postgres Connectivity Test")
    print("=" * 80)
    
    ec2 = boto3.client('ec2', region_name='us-east-1')
    elbv2 = boto3.client('elbv2', region_name='us-east-1')
    rds = boto3.client('rds', region_name='us-east-1')
    ecs = boto3.client('ecs', region_name='us-east-1')
    
    results = {
        'timestamp': get_timestamp(),
        'alb_info': {},
        'postgres_info': {},
        'ecs_tasks': {},
        'connectivity_checks': {},
        'issues': [],
        'recommendations': []
    }
    
    # 1. Find the ALB
    print("\n1. Finding multimodal-lib-prod ALB...")
    try:
        albs = elbv2.describe_load_balancers()
        target_alb = None
        
        # Look for the v2 ALB first, then fall back to regular ALB
        for alb in albs['LoadBalancers']:
            if alb['LoadBalancerName'] in ['multimodal-lib-prod-alb-v2', 'multimodal-lib-prod-alb']:
                target_alb = alb
                if 'v2' in alb['LoadBalancerName']:
                    break  # Prefer v2
        
        if not target_alb:
            print("❌ ALB not found!")
            results['issues'].append("ALB 'multimodal-lib-prod-alb' not found")
            return results
        
        print(f"✓ Found ALB: {target_alb['LoadBalancerName']}")
        print(f"  DNS: {target_alb['DNSName']}")
        print(f"  VPC: {target_alb['VpcId']}")
        print(f"  Subnets: {', '.join([az['SubnetId'] for az in target_alb['AvailabilityZones']])}")
        print(f"  Security Groups: {', '.join(target_alb['SecurityGroups'])}")
        
        results['alb_info'] = {
            'name': target_alb['LoadBalancerName'],
            'arn': target_alb['LoadBalancerArn'],
            'dns': target_alb['DNSName'],
            'vpc_id': target_alb['VpcId'],
            'subnets': [az['SubnetId'] for az in target_alb['AvailabilityZones']],
            'security_groups': target_alb['SecurityGroups']
        }
        
    except Exception as e:
        print(f"❌ Error finding ALB: {e}")
        results['issues'].append(f"Error finding ALB: {str(e)}")
        return results
    
    # 2. Find Postgres RDS instance
    print("\n2. Finding Postgres RDS instance...")
    try:
        db_instances = rds.describe_db_instances()
        postgres_db = None
        
        for db in db_instances['DBInstances']:
            if db['Engine'] == 'postgres':
                postgres_db = db
                break
        
        if not postgres_db:
            print("❌ Postgres RDS instance not found!")
            results['issues'].append("No Postgres RDS instance found")
            return results
        
        print(f"✓ Found Postgres: {postgres_db['DBInstanceIdentifier']}")
        print(f"  Endpoint: {postgres_db['Endpoint']['Address']}:{postgres_db['Endpoint']['Port']}")
        print(f"  VPC: {postgres_db['DBSubnetGroup']['VpcId']}")
        print(f"  Security Groups: {', '.join([sg['VpcSecurityGroupId'] for sg in postgres_db['VpcSecurityGroups']])}")
        print(f"  Status: {postgres_db['DBInstanceStatus']}")
        
        results['postgres_info'] = {
            'identifier': postgres_db['DBInstanceIdentifier'],
            'endpoint': postgres_db['Endpoint']['Address'],
            'port': postgres_db['Endpoint']['Port'],
            'vpc_id': postgres_db['DBSubnetGroup']['VpcId'],
            'security_groups': [sg['VpcSecurityGroupId'] for sg in postgres_db['VpcSecurityGroups']],
            'status': postgres_db['DBInstanceStatus'],
            'subnets': [subnet['SubnetIdentifier'] for subnet in postgres_db['DBSubnetGroup']['Subnets']]
        }
        
    except Exception as e:
        print(f"❌ Error finding Postgres: {e}")
        results['issues'].append(f"Error finding Postgres: {str(e)}")
        return results
    
    # 3. Check VPC match
    print("\n3. Checking VPC configuration...")
    alb_vpc = results['alb_info']['vpc_id']
    db_vpc = results['postgres_info']['vpc_id']
    
    if alb_vpc == db_vpc:
        print(f"✓ ALB and Postgres are in the same VPC: {alb_vpc}")
        results['connectivity_checks']['vpc_match'] = True
    else:
        print(f"❌ VPC MISMATCH!")
        print(f"  ALB VPC: {alb_vpc}")
        print(f"  Postgres VPC: {db_vpc}")
        results['connectivity_checks']['vpc_match'] = False
        results['issues'].append(f"VPC mismatch: ALB in {alb_vpc}, Postgres in {db_vpc}")
        results['recommendations'].append("Set up VPC peering or move resources to same VPC")
    
    # 4. Check ECS tasks behind ALB
    print("\n4. Checking ECS tasks behind ALB...")
    try:
        # Get target groups for ALB
        target_groups = elbv2.describe_target_groups(
            LoadBalancerArn=target_alb['LoadBalancerArn']
        )
        
        if target_groups['TargetGroups']:
            tg = target_groups['TargetGroups'][0]
            print(f"✓ Found target group: {tg['TargetGroupName']}")
            
            # Get target health
            health = elbv2.describe_target_health(
                TargetGroupArn=tg['TargetGroupArn']
            )
            
            print(f"  Registered targets: {len(health['TargetHealthDescriptions'])}")
            
            task_info = []
            for target in health['TargetHealthDescriptions']:
                target_id = target['Target']['Id']
                health_state = target['TargetHealth']['State']
                print(f"    Target {target_id}: {health_state}")
                
                # Try to get task details
                try:
                    # Extract task ID from target ID (format: arn:aws:ecs:region:account:task/cluster/task-id)
                    if 'task' in target_id:
                        task_arn = target_id
                        cluster_name = 'multimodal-lib-prod-cluster'
                        
                        task_details = ecs.describe_tasks(
                            cluster=cluster_name,
                            tasks=[task_arn]
                        )
                        
                        if task_details['tasks']:
                            task = task_details['tasks'][0]
                            task_info.append({
                                'task_arn': task_arn,
                                'health': health_state,
                                'vpc_id': task.get('attachments', [{}])[0].get('details', [{}])[0].get('value') if task.get('attachments') else None
                            })
                except Exception as e:
                    print(f"      Could not get task details: {e}")
            
            results['ecs_tasks'] = {
                'target_group': tg['TargetGroupName'],
                'target_count': len(health['TargetHealthDescriptions']),
                'tasks': task_info
            }
        else:
            print("❌ No target groups found for ALB")
            results['issues'].append("No target groups configured for ALB")
            
    except Exception as e:
        print(f"❌ Error checking ECS tasks: {e}")
        results['issues'].append(f"Error checking ECS tasks: {str(e)}")
    
    # 5. Check security group rules
    print("\n5. Checking security group rules...")
    try:
        # Check ALB security groups
        alb_sgs = results['alb_info']['security_groups']
        db_sgs = results['postgres_info']['security_groups']
        
        print(f"\n  ALB Security Groups: {', '.join(alb_sgs)}")
        for sg_id in alb_sgs:
            sg = ec2.describe_security_groups(GroupIds=[sg_id])['SecurityGroups'][0]
            print(f"    {sg_id} ({sg['GroupName']}):")
            print(f"      Egress rules: {len(sg['IpPermissionsEgress'])}")
            for rule in sg['IpPermissionsEgress']:
                if rule.get('IpProtocol') == '-1':
                    print(f"        ✓ All traffic allowed")
                elif rule.get('FromPort') == 5432:
                    print(f"        ✓ Port 5432 (Postgres) allowed")
        
        print(f"\n  Postgres Security Groups: {', '.join(db_sgs)}")
        postgres_allows_alb = False
        for sg_id in db_sgs:
            sg = ec2.describe_security_groups(GroupIds=[sg_id])['SecurityGroups'][0]
            print(f"    {sg_id} ({sg['GroupName']}):")
            print(f"      Ingress rules: {len(sg['IpPermissions'])}")
            for rule in sg['IpPermissions']:
                if rule.get('FromPort') == 5432 or rule.get('IpProtocol') == '-1':
                    print(f"        Port: {rule.get('FromPort', 'all')}")
                    # Check if ALB security groups are allowed
                    for sg_pair in rule.get('UserIdGroupPairs', []):
                        if sg_pair['GroupId'] in alb_sgs:
                            print(f"          ✓ Allows ALB security group {sg_pair['GroupId']}")
                            postgres_allows_alb = True
        
        results['connectivity_checks']['security_groups_configured'] = postgres_allows_alb
        
        if not postgres_allows_alb:
            print("\n  ❌ Postgres security group does not allow traffic from ALB security groups!")
            results['issues'].append("Postgres security group does not allow ALB security groups")
            results['recommendations'].append(
                f"Add inbound rule to Postgres security group allowing port 5432 from ALB security groups: {', '.join(alb_sgs)}"
            )
        else:
            print("\n  ✓ Security groups properly configured")
            
    except Exception as e:
        print(f"❌ Error checking security groups: {e}")
        results['issues'].append(f"Error checking security groups: {str(e)}")
    
    # 6. Summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    
    if results['issues']:
        print("\n❌ Issues Found:")
        for i, issue in enumerate(results['issues'], 1):
            print(f"  {i}. {issue}")
    
    if results['recommendations']:
        print("\n💡 Recommendations:")
        for i, rec in enumerate(results['recommendations'], 1):
            print(f"  {i}. {rec}")
    
    if not results['issues']:
        print("\n✓ All connectivity checks passed!")
        print("  The ALB should be able to connect to Postgres.")
    
    # Save results
    output_file = f"alb-postgres-connectivity-test-{get_timestamp()}.json"
    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2, default=str)
    
    print(f"\n📄 Results saved to: {output_file}")
    
    return results

if __name__ == '__main__':
    try:
        results = test_alb_postgres_connectivity()
        
        # Exit with error code if issues found
        if results.get('issues'):
            sys.exit(1)
        else:
            sys.exit(0)
            
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
