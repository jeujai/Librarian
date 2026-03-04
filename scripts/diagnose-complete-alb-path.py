#!/usr/bin/env python3
"""
Comprehensive ALB to ECS Task Network Path Diagnostic

This script traces the complete path from ALB to ECS tasks to identify
where health check packets are being dropped.
"""

import boto3
import json
from datetime import datetime

def diagnose_complete_path():
    """Diagnose the complete network path from ALB to ECS tasks"""
    
    elbv2 = boto3.client('elbv2')
    ecs = boto3.client('ecs')
    ec2 = boto3.client('ec2')
    
    results = {
        'timestamp': datetime.now().isoformat(),
        'checks': {}
    }
    
    print("=" * 80)
    print("COMPREHENSIVE ALB TO ECS NETWORK PATH DIAGNOSTIC")
    print("=" * 80)
    
    # 1. Find the ALB
    print("\n1. LOCATING APPLICATION LOAD BALANCER...")
    lbs = elbv2.describe_load_balancers()['LoadBalancers']
    alb = None
    for lb in lbs:
        if 'multimodal-lib-prod' in lb['LoadBalancerName']:
            alb = lb
            break
    
    if not alb:
        print("❌ No ALB found with 'multimodal-lib-prod' in name")
        return results
    
    print(f"✅ Found ALB: {alb['LoadBalancerName']}")
    print(f"   ARN: {alb['LoadBalancerArn']}")
    print(f"   DNS: {alb['DNSName']}")
    print(f"   Subnets: {alb['AvailabilityZones']}")
    print(f"   Security Groups: {alb['SecurityGroups']}")
    
    results['checks']['alb'] = {
        'name': alb['LoadBalancerName'],
        'arn': alb['LoadBalancerArn'],
        'subnets': [az['SubnetId'] for az in alb['AvailabilityZones']],
        'security_groups': alb['SecurityGroups']
    }
    
    # 2. Check Target Groups
    print("\n2. CHECKING TARGET GROUPS...")
    tgs = elbv2.describe_target_groups(LoadBalancerArn=alb['LoadBalancerArn'])
    
    if not tgs['TargetGroups']:
        print("❌ No target groups attached to ALB")
        results['checks']['target_groups'] = {'error': 'No target groups found'}
        return results
    
    for tg in tgs['TargetGroups']:
        print(f"\n   Target Group: {tg['TargetGroupName']}")
        print(f"   Protocol: {tg['Protocol']}:{tg['Port']}")
        print(f"   Health Check: {tg['HealthCheckProtocol']} {tg['HealthCheckPath']}")
        print(f"   Health Check Interval: {tg['HealthCheckIntervalSeconds']}s")
        print(f"   Health Check Timeout: {tg['HealthCheckTimeoutSeconds']}s")
        print(f"   Healthy Threshold: {tg['HealthyThresholdCount']}")
        print(f"   Unhealthy Threshold: {tg['UnhealthyThresholdCount']}")
        
        # Check target health
        health = elbv2.describe_target_health(TargetGroupArn=tg['TargetGroupArn'])
        print(f"\n   Registered Targets: {len(health['TargetHealthDescriptions'])}")
        
        for target in health['TargetHealthDescriptions']:
            print(f"      Target: {target['Target']['Id']}:{target['Target']['Port']}")
            print(f"      State: {target['TargetHealth']['State']}")
            if 'Reason' in target['TargetHealth']:
                print(f"      Reason: {target['TargetHealth']['Reason']}")
            if 'Description' in target['TargetHealth']:
                print(f"      Description: {target['TargetHealth']['Description']}")
        
        results['checks']['target_group'] = {
            'name': tg['TargetGroupName'],
            'protocol': f"{tg['Protocol']}:{tg['Port']}",
            'health_check': {
                'protocol': tg['HealthCheckProtocol'],
                'path': tg['HealthCheckPath'],
                'interval': tg['HealthCheckIntervalSeconds'],
                'timeout': tg['HealthCheckTimeoutSeconds']
            },
            'targets': [
                {
                    'id': t['Target']['Id'],
                    'port': t['Target']['Port'],
                    'state': t['TargetHealth']['State'],
                    'reason': t['TargetHealth'].get('Reason', 'N/A')
                }
                for t in health['TargetHealthDescriptions']
            ]
        }
    
    # 3. Check ECS Service
    print("\n3. CHECKING ECS SERVICE...")
    clusters = ecs.list_clusters()['clusterArns']
    
    service_found = False
    for cluster_arn in clusters:
        cluster_name = cluster_arn.split('/')[-1]
        if 'prod' not in cluster_name.lower():
            continue
            
        services = ecs.list_services(cluster=cluster_arn)['serviceArns']
        for service_arn in services:
            service_name = service_arn.split('/')[-1]
            if 'multimodal' in service_name.lower() or 'librarian' in service_name.lower():
                service_found = True
                print(f"\n   Found Service: {service_name}")
                print(f"   Cluster: {cluster_name}")
                
                # Get service details
                service_details = ecs.describe_services(
                    cluster=cluster_arn,
                    services=[service_arn]
                )['services'][0]
                
                print(f"   Desired Count: {service_details['desiredCount']}")
                print(f"   Running Count: {service_details['runningCount']}")
                print(f"   Network Mode: {service_details.get('networkConfiguration', {})}")
                
                # Check load balancers
                if 'loadBalancers' in service_details:
                    print(f"\n   Load Balancers Configured:")
                    for lb in service_details['loadBalancers']:
                        print(f"      Target Group: {lb.get('targetGroupArn', 'N/A')}")
                        print(f"      Container: {lb.get('containerName', 'N/A')}:{lb.get('containerPort', 'N/A')}")
                else:
                    print("   ❌ NO LOAD BALANCERS CONFIGURED ON SERVICE!")
                
                # Get task details
                tasks = ecs.list_tasks(cluster=cluster_arn, serviceName=service_name)['taskArns']
                print(f"\n   Running Tasks: {len(tasks)}")
                
                if tasks:
                    task_details = ecs.describe_tasks(cluster=cluster_arn, tasks=tasks)['tasks']
                    for task in task_details:
                        print(f"\n      Task: {task['taskArn'].split('/')[-1]}")
                        print(f"      Status: {task['lastStatus']}")
                        print(f"      Health: {task.get('healthStatus', 'UNKNOWN')}")
                        
                        # Network interfaces
                        for attachment in task.get('attachments', []):
                            if attachment['type'] == 'ElasticNetworkInterface':
                                for detail in attachment['details']:
                                    if detail['name'] == 'networkInterfaceId':
                                        eni_id = detail['value']
                                        print(f"      ENI: {eni_id}")
                                        
                                        # Get ENI details
                                        enis = ec2.describe_network_interfaces(
                                            NetworkInterfaceIds=[eni_id]
                                        )['NetworkInterfaces']
                                        
                                        if enis:
                                            eni = enis[0]
                                            print(f"         Private IP: {eni.get('PrivateIpAddress', 'N/A')}")
                                            print(f"         Subnet: {eni.get('SubnetId', 'N/A')}")
                                            print(f"         VPC: {eni.get('VpcId', 'N/A')}")
                                            print(f"         Security Groups: {[sg['GroupId'] for sg in eni.get('Groups', [])]}")
                
                results['checks']['ecs_service'] = {
                    'cluster': cluster_name,
                    'service': service_name,
                    'desired_count': service_details['desiredCount'],
                    'running_count': service_details['runningCount'],
                    'load_balancers_configured': len(service_details.get('loadBalancers', [])) > 0,
                    'task_count': len(tasks)
                }
                
                break
        
        if service_found:
            break
    
    if not service_found:
        print("❌ No ECS service found")
        results['checks']['ecs_service'] = {'error': 'Service not found'}
    
    # 4. Check Security Group Rules
    print("\n4. ANALYZING SECURITY GROUP CHAIN...")
    
    # ALB security groups
    alb_sgs = alb['SecurityGroups']
    print(f"\n   ALB Security Groups: {alb_sgs}")
    
    for sg_id in alb_sgs:
        sg = ec2.describe_security_groups(GroupIds=[sg_id])['SecurityGroups'][0]
        print(f"\n   Security Group: {sg['GroupName']} ({sg_id})")
        print(f"   Egress Rules:")
        for rule in sg['IpPermissionsEgress']:
            print(f"      {rule}")
    
    # 5. Check Subnet Route Tables
    print("\n5. CHECKING SUBNET ROUTING...")
    
    alb_subnet_ids = [az['SubnetId'] for az in alb['AvailabilityZones']]
    
    for subnet_id in alb_subnet_ids:
        subnet = ec2.describe_subnets(SubnetIds=[subnet_id])['Subnets'][0]
        print(f"\n   Subnet: {subnet_id}")
        print(f"   CIDR: {subnet['CidrBlock']}")
        print(f"   AZ: {subnet['AvailabilityZone']}")
        
        # Get route table
        route_tables = ec2.describe_route_tables(
            Filters=[{'Name': 'association.subnet-id', 'Values': [subnet_id]}]
        )['RouteTables']
        
        if route_tables:
            rt = route_tables[0]
            print(f"   Route Table: {rt['RouteTableId']}")
            print(f"   Routes:")
            for route in rt['Routes']:
                dest = route.get('DestinationCidrBlock', route.get('DestinationPrefixListId', 'N/A'))
                target = route.get('GatewayId', route.get('NatGatewayId', route.get('NetworkInterfaceId', 'local')))
                print(f"      {dest} -> {target}")
    
    # Save results
    output_file = f"alb-complete-diagnosis-{int(datetime.now().timestamp())}.json"
    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2, default=str)
    
    print(f"\n{'=' * 80}")
    print(f"Diagnostic results saved to: {output_file}")
    print(f"{'=' * 80}")
    
    # Summary
    print("\n" + "=" * 80)
    print("DIAGNOSTIC SUMMARY")
    print("=" * 80)
    
    issues = []
    
    if 'target_group' in results['checks']:
        unhealthy = [t for t in results['checks']['target_group']['targets'] if t['state'] != 'healthy']
        if unhealthy:
            issues.append(f"❌ {len(unhealthy)} unhealthy targets")
    
    if 'ecs_service' in results['checks']:
        if not results['checks']['ecs_service'].get('load_balancers_configured', False):
            issues.append("❌ ECS service not configured with load balancer")
        
        if results['checks']['ecs_service'].get('running_count', 0) == 0:
            issues.append("❌ No running ECS tasks")
    
    if issues:
        print("\nISSUES FOUND:")
        for issue in issues:
            print(f"  {issue}")
    else:
        print("\n✅ All checks passed - issue may be at application level")
    
    return results

if __name__ == '__main__':
    diagnose_complete_path()
