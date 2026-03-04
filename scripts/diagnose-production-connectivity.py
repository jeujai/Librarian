#!/usr/bin/env python3
"""
Diagnose production connectivity issues.
"""

import boto3
import json
import sys
from datetime import datetime

def diagnose_production_connectivity():
    """Diagnose production connectivity issues."""
    
    try:
        # Initialize clients
        ecs_client = boto3.client('ecs', region_name='us-east-1')
        elb_client = boto3.client('elbv2', region_name='us-east-1')
        ec2_client = boto3.client('ec2', region_name='us-east-1')
        
        diagnosis = {
            'timestamp': datetime.now().isoformat(),
            'load_balancer_status': {},
            'target_group_health': {},
            'ecs_service_status': {},
            'security_groups': {},
            'recommendations': []
        }
        
        print("🔍 Diagnosing Production Connectivity Issues")
        print("=" * 50)
        
        # 1. Check Load Balancer Status
        print("\n1. Load Balancer Status:")
        print("-" * 30)
        
        lb_response = elb_client.describe_load_balancers()
        multimodal_lb = None
        
        for lb in lb_response['LoadBalancers']:
            if 'multimodal' in lb['LoadBalancerName'].lower():
                multimodal_lb = lb
                break
        
        if multimodal_lb:
            lb_name = multimodal_lb['LoadBalancerName']
            lb_state = multimodal_lb['State']['Code']
            lb_dns = multimodal_lb['DNSName']
            
            diagnosis['load_balancer_status'] = {
                'name': lb_name,
                'state': lb_state,
                'dns_name': lb_dns,
                'scheme': multimodal_lb['Scheme'],
                'type': multimodal_lb['Type']
            }
            
            print(f"✅ Load Balancer Found: {lb_name}")
            print(f"   - State: {lb_state}")
            print(f"   - DNS: {lb_dns}")
            print(f"   - Scheme: {multimodal_lb['Scheme']}")
            
            if lb_state != 'active':
                diagnosis['recommendations'].append(f"Load balancer is {lb_state}, not active")
        else:
            print("❌ No multimodal load balancer found")
            diagnosis['recommendations'].append("No multimodal load balancer found")
            return diagnosis
        
        # 2. Check Target Group Health
        print("\n2. Target Group Health:")
        print("-" * 25)
        
        # Get target groups for the load balancer
        tg_response = elb_client.describe_target_groups(
            LoadBalancerArn=multimodal_lb['LoadBalancerArn']
        )
        
        for tg in tg_response['TargetGroups']:
            tg_name = tg['TargetGroupName']
            tg_arn = tg['TargetGroupArn']
            
            print(f"📋 Target Group: {tg_name}")
            
            # Get target health
            health_response = elb_client.describe_target_health(
                TargetGroupArn=tg_arn
            )
            
            healthy_targets = 0
            total_targets = len(health_response['TargetHealthDescriptions'])
            
            for target_health in health_response['TargetHealthDescriptions']:
                target_id = target_health['Target']['Id']
                health_state = target_health['TargetHealth']['State']
                
                print(f"   - Target {target_id}: {health_state}")
                
                if health_state == 'healthy':
                    healthy_targets += 1
                elif health_state in ['unhealthy', 'draining']:
                    reason = target_health['TargetHealth'].get('Reason', 'Unknown')
                    description = target_health['TargetHealth'].get('Description', '')
                    print(f"     Reason: {reason}")
                    print(f"     Description: {description}")
            
            diagnosis['target_group_health'][tg_name] = {
                'healthy_targets': healthy_targets,
                'total_targets': total_targets,
                'health_details': health_response['TargetHealthDescriptions']
            }
            
            print(f"   - Health: {healthy_targets}/{total_targets} healthy")
            
            if healthy_targets == 0:
                diagnosis['recommendations'].append(f"No healthy targets in {tg_name}")
        
        # 3. Check ECS Service Status
        print("\n3. ECS Service Status:")
        print("-" * 22)
        
        # List clusters
        clusters_response = ecs_client.list_clusters()
        
        for cluster_arn in clusters_response['clusterArns']:
            cluster_name = cluster_arn.split('/')[-1]
            
            if 'multimodal' in cluster_name.lower() or 'prod' in cluster_name.lower():
                print(f"📦 Cluster: {cluster_name}")
                
                # List services in cluster
                services_response = ecs_client.list_services(cluster=cluster_arn)
                
                for service_arn in services_response['serviceArns']:
                    service_name = service_arn.split('/')[-1]
                    
                    if 'multimodal' in service_name.lower() or 'prod' in service_name.lower():
                        # Get service details
                        service_details = ecs_client.describe_services(
                            cluster=cluster_arn,
                            services=[service_arn]
                        )
                        
                        service = service_details['services'][0]
                        
                        print(f"   🚀 Service: {service_name}")
                        print(f"      - Status: {service['status']}")
                        print(f"      - Running: {service['runningCount']}")
                        print(f"      - Desired: {service['desiredCount']}")
                        print(f"      - Pending: {service['pendingCount']}")
                        
                        diagnosis['ecs_service_status'][service_name] = {
                            'status': service['status'],
                            'running_count': service['runningCount'],
                            'desired_count': service['desiredCount'],
                            'pending_count': service['pendingCount']
                        }
                        
                        if service['runningCount'] == 0:
                            diagnosis['recommendations'].append(f"Service {service_name} has no running tasks")
                        
                        # Check recent events
                        events = service.get('events', [])[:3]  # Last 3 events
                        if events:
                            print(f"      Recent events:")
                            for event in events:
                                print(f"        - {event['message'][:80]}...")
        
        # 4. Check Security Groups
        print("\n4. Security Group Analysis:")
        print("-" * 30)
        
        # Get security groups for the load balancer
        if multimodal_lb:
            sg_ids = multimodal_lb.get('SecurityGroups', [])
            
            if sg_ids:
                sg_response = ec2_client.describe_security_groups(GroupIds=sg_ids)
                
                for sg in sg_response['SecurityGroups']:
                    sg_name = sg['GroupName']
                    sg_id = sg['GroupId']
                    
                    print(f"🔒 Security Group: {sg_name} ({sg_id})")
                    
                    # Check inbound rules
                    inbound_rules = sg['IpPermissions']
                    https_allowed = False
                    http_allowed = False
                    
                    for rule in inbound_rules:
                        from_port = rule.get('FromPort')
                        to_port = rule.get('ToPort')
                        protocol = rule.get('IpProtocol')
                        
                        if from_port == 443 and to_port == 443:
                            https_allowed = True
                        if from_port == 80 and to_port == 80:
                            http_allowed = True
                        
                        print(f"   - {protocol}:{from_port}-{to_port}")
                    
                    diagnosis['security_groups'][sg_name] = {
                        'group_id': sg_id,
                        'https_allowed': https_allowed,
                        'http_allowed': http_allowed,
                        'rules_count': len(inbound_rules)
                    }
                    
                    if not https_allowed and not http_allowed:
                        diagnosis['recommendations'].append(f"Security group {sg_name} may not allow web traffic")
        
        # 5. Summary and Recommendations
        print("\n5. Summary and Recommendations:")
        print("-" * 35)
        
        if diagnosis['recommendations']:
            print("🚨 Issues Found:")
            for i, rec in enumerate(diagnosis['recommendations'], 1):
                print(f"   {i}. {rec}")
        else:
            print("✅ No obvious issues found")
        
        return diagnosis
        
    except Exception as e:
        print(f"❌ Error during diagnosis: {e}")
        return {'error': str(e)}

if __name__ == "__main__":
    result = diagnose_production_connectivity()
    
    # Save diagnosis to file
    diagnosis_file = f"production-connectivity-diagnosis-{int(datetime.now().timestamp())}.json"
    with open(diagnosis_file, 'w') as f:
        json.dump(result, f, indent=2, default=str)
    
    print(f"\n📄 Diagnosis saved to: {diagnosis_file}")
    
    if result.get('recommendations'):
        sys.exit(1)
    else:
        sys.exit(0)