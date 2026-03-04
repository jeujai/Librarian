#!/usr/bin/env python3
"""
Comprehensive Load Balancer Connectivity Diagnosis
Investigates why both ALB and NLB cannot connect to the application
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
    ec2 = boto3.client('ec2', region_name='us-east-1')
    ecs = boto3.client('ecs', region_name='us-east-1')
    elbv2 = boto3.client('elbv2', region_name='us-east-1')
    
    results = {
        'timestamp': datetime.now().isoformat(),
        'investigation': 'Load Balancer Connectivity Root Cause Analysis'
    }
    
    print_section("LOAD BALANCER CONNECTIVITY ROOT CAUSE ANALYSIS")
    print(f"Timestamp: {results['timestamp']}")
    
    # 1. Get ECS Task Details
    print_section("1. ECS TASK ANALYSIS")
    try:
        tasks_response = ecs.list_tasks(
            cluster='multimodal-lib-prod-cluster',
            serviceName='multimodal-lib-prod-service'
        )
        
        if not tasks_response['taskArns']:
            print("❌ No running tasks found!")
            results['tasks'] = {'error': 'No running tasks'}
            return results
        
        task_details = ecs.describe_tasks(
            cluster='multimodal-lib-prod-cluster',
            tasks=tasks_response['taskArns']
        )
        
        task = task_details['tasks'][0]
        results['task'] = {
            'taskArn': task['taskArn'],
            'lastStatus': task['lastStatus'],
            'healthStatus': task.get('healthStatus', 'UNKNOWN'),
            'containers': []
        }
        
        print(f"Task ARN: {task['taskArn']}")
        print(f"Status: {task['lastStatus']}")
        print(f"Health: {task.get('healthStatus', 'UNKNOWN')}")
        
        # Get ENI details
        for attachment in task.get('attachments', []):
            if attachment['type'] == 'ElasticNetworkInterface':
                for detail in attachment['details']:
                    if detail['name'] == 'networkInterfaceId':
                        eni_id = detail['value']
                        results['task']['eni_id'] = eni_id
                        print(f"ENI ID: {eni_id}")
                    elif detail['name'] == 'privateIPv4Address':
                        private_ip = detail['value']
                        results['task']['private_ip'] = private_ip
                        print(f"Private IP: {private_ip}")
        
        # Container details
        for container in task['containers']:
            container_info = {
                'name': container['name'],
                'lastStatus': container['lastStatus'],
                'healthStatus': container.get('healthStatus', 'UNKNOWN')
            }
            results['task']['containers'].append(container_info)
            print(f"\nContainer: {container['name']}")
            print(f"  Status: {container['lastStatus']}")
            print(f"  Health: {container.get('healthStatus', 'UNKNOWN')}")
            
            if 'networkBindings' in container:
                for binding in container['networkBindings']:
                    print(f"  Port Binding: {binding.get('containerPort')} -> {binding.get('hostPort')}")
        
    except Exception as e:
        print(f"❌ Error getting task details: {e}")
        results['tasks'] = {'error': str(e)}
        return results
    
    # 2. Check ENI Security Groups and Network Configuration
    print_section("2. ENI NETWORK CONFIGURATION")
    try:
        eni_id = results['task']['eni_id']
        eni_response = ec2.describe_network_interfaces(
            NetworkInterfaceIds=[eni_id]
        )
        
        eni = eni_response['NetworkInterfaces'][0]
        results['eni'] = {
            'id': eni['NetworkInterfaceId'],
            'subnet_id': eni['SubnetId'],
            'vpc_id': eni['VpcId'],
            'private_ip': eni['PrivateIpAddress'],
            'security_groups': [sg['GroupId'] for sg in eni['Groups']],
            'status': eni['Status']
        }
        
        print(f"ENI ID: {eni['NetworkInterfaceId']}")
        print(f"Status: {eni['Status']}")
        print(f"VPC: {eni['VpcId']}")
        print(f"Subnet: {eni['SubnetId']}")
        print(f"Private IP: {eni['PrivateIpAddress']}")
        print(f"Security Groups: {', '.join([sg['GroupId'] for sg in eni['Groups']])}")
        
        # Check if ENI has a public IP
        if 'Association' in eni:
            public_ip = eni['Association'].get('PublicIp')
            results['eni']['public_ip'] = public_ip
            print(f"Public IP: {public_ip}")
        else:
            print("⚠️  No public IP associated")
            results['eni']['public_ip'] = None
        
    except Exception as e:
        print(f"❌ Error getting ENI details: {e}")
        results['eni'] = {'error': str(e)}
    
    # 3. Analyze Security Groups
    print_section("3. SECURITY GROUP ANALYSIS")
    try:
        sg_ids = results['eni']['security_groups']
        sg_response = ec2.describe_security_groups(GroupIds=sg_ids)
        
        results['security_groups'] = []
        for sg in sg_response['SecurityGroups']:
            sg_info = {
                'id': sg['GroupId'],
                'name': sg['GroupName'],
                'inbound_rules': [],
                'outbound_rules': []
            }
            
            print(f"\nSecurity Group: {sg['GroupName']} ({sg['GroupId']})")
            print("Inbound Rules:")
            for rule in sg['IpPermissions']:
                rule_str = f"  {rule.get('IpProtocol', 'all')} "
                if 'FromPort' in rule:
                    rule_str += f"{rule['FromPort']}-{rule['ToPort']} "
                
                sources = []
                for ip_range in rule.get('IpRanges', []):
                    sources.append(ip_range['CidrIp'])
                for sg_ref in rule.get('UserIdGroupPairs', []):
                    sources.append(f"sg:{sg_ref['GroupId']}")
                
                rule_str += f"from {', '.join(sources) if sources else 'any'}"
                print(rule_str)
                sg_info['inbound_rules'].append(rule_str)
            
            print("Outbound Rules:")
            for rule in sg['IpPermissionsEgress']:
                rule_str = f"  {rule.get('IpProtocol', 'all')} "
                if 'FromPort' in rule:
                    rule_str += f"{rule['FromPort']}-{rule['ToPort']} "
                
                destinations = []
                for ip_range in rule.get('IpRanges', []):
                    destinations.append(ip_range['CidrIp'])
                
                rule_str += f"to {', '.join(destinations) if destinations else 'any'}"
                print(rule_str)
                sg_info['outbound_rules'].append(rule_str)
            
            results['security_groups'].append(sg_info)
        
    except Exception as e:
        print(f"❌ Error analyzing security groups: {e}")
        results['security_groups'] = {'error': str(e)}
    
    # 4. Check Subnet Configuration
    print_section("4. SUBNET CONFIGURATION")
    try:
        subnet_id = results['eni']['subnet_id']
        subnet_response = ec2.describe_subnets(SubnetIds=[subnet_id])
        subnet = subnet_response['Subnets'][0]
        
        results['subnet'] = {
            'id': subnet['SubnetId'],
            'cidr': subnet['CidrBlock'],
            'availability_zone': subnet['AvailabilityZone'],
            'available_ips': subnet['AvailableIpAddressCount'],
            'map_public_ip': subnet.get('MapPublicIpOnLaunch', False)
        }
        
        print(f"Subnet ID: {subnet['SubnetId']}")
        print(f"CIDR: {subnet['CidrBlock']}")
        print(f"AZ: {subnet['AvailabilityZone']}")
        print(f"Available IPs: {subnet['AvailableIpAddressCount']}")
        print(f"Auto-assign Public IP: {subnet.get('MapPublicIpOnLaunch', False)}")
        
        # Check route table
        route_tables = ec2.describe_route_tables(
            Filters=[
                {'Name': 'association.subnet-id', 'Values': [subnet_id]}
            ]
        )
        
        if route_tables['RouteTables']:
            rt = route_tables['RouteTables'][0]
            results['subnet']['route_table_id'] = rt['RouteTableId']
            print(f"\nRoute Table: {rt['RouteTableId']}")
            print("Routes:")
            for route in rt['Routes']:
                dest = route.get('DestinationCidrBlock', route.get('DestinationPrefixListId', 'unknown'))
                target = route.get('GatewayId', route.get('NatGatewayId', route.get('NetworkInterfaceId', 'local')))
                print(f"  {dest} -> {target}")
        
    except Exception as e:
        print(f"❌ Error checking subnet: {e}")
        results['subnet'] = {'error': str(e)}
    
    # 5. Check Load Balancer Configurations
    print_section("5. LOAD BALANCER CONFIGURATIONS")
    
    # ALB
    print("\n--- ALB Configuration ---")
    try:
        alb_response = elbv2.describe_load_balancers(
            Names=['multimodal-lib-prod-alb-v2']
        )
        alb = alb_response['LoadBalancers'][0]
        
        results['alb'] = {
            'arn': alb['LoadBalancerArn'],
            'dns_name': alb['DNSName'],
            'scheme': alb['Scheme'],
            'vpc_id': alb['VpcId'],
            'subnets': alb['AvailabilityZones'],
            'security_groups': alb.get('SecurityGroups', [])
        }
        
        print(f"ALB DNS: {alb['DNSName']}")
        print(f"Scheme: {alb['Scheme']}")
        print(f"VPC: {alb['VpcId']}")
        print(f"Security Groups: {', '.join(alb.get('SecurityGroups', []))}")
        print("Subnets:")
        for az in alb['AvailabilityZones']:
            print(f"  {az['ZoneName']}: {az['SubnetId']}")
        
        # Get target group health
        tg_response = elbv2.describe_target_groups(
            LoadBalancerArn=alb['LoadBalancerArn']
        )
        if tg_response['TargetGroups']:
            tg = tg_response['TargetGroups'][0]
            health_response = elbv2.describe_target_health(
                TargetGroupArn=tg['TargetGroupArn']
            )
            
            results['alb']['target_group'] = {
                'arn': tg['TargetGroupArn'],
                'health_check_path': tg['HealthCheckPath'],
                'health_check_port': tg['HealthCheckPort'],
                'targets': []
            }
            
            print(f"\nTarget Group: {tg['TargetGroupName']}")
            print(f"Health Check: {tg['HealthCheckPath']} on port {tg['HealthCheckPort']}")
            print("Target Health:")
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
                
                results['alb']['target_group']['targets'].append(target_info)
                print(f"  {target['Target']['Id']}:{target['Target']['Port']} - {target['TargetHealth']['State']}")
                if 'Reason' in target['TargetHealth']:
                    print(f"    Reason: {target['TargetHealth']['Reason']}")
                if 'Description' in target['TargetHealth']:
                    print(f"    Description: {target['TargetHealth']['Description']}")
        
    except Exception as e:
        print(f"❌ Error checking ALB: {e}")
        results['alb'] = {'error': str(e)}
    
    # NLB
    print("\n--- NLB Configuration ---")
    try:
        nlb_response = elbv2.describe_load_balancers(
            Names=['multimodal-lib-prod-nlb']
        )
        nlb = nlb_response['LoadBalancers'][0]
        
        results['nlb'] = {
            'arn': nlb['LoadBalancerArn'],
            'dns_name': nlb['DNSName'],
            'scheme': nlb['Scheme'],
            'vpc_id': nlb['VpcId'],
            'subnets': nlb['AvailabilityZones']
        }
        
        print(f"NLB DNS: {nlb['DNSName']}")
        print(f"Scheme: {nlb['Scheme']}")
        print(f"VPC: {nlb['VpcId']}")
        print("Subnets:")
        for az in nlb['AvailabilityZones']:
            print(f"  {az['ZoneName']}: {az['SubnetId']}")
        
        # Get target group health
        tg_response = elbv2.describe_target_groups(
            LoadBalancerArn=nlb['LoadBalancerArn']
        )
        if tg_response['TargetGroups']:
            tg = tg_response['TargetGroups'][0]
            health_response = elbv2.describe_target_health(
                TargetGroupArn=tg['TargetGroupArn']
            )
            
            results['nlb']['target_group'] = {
                'arn': tg['TargetGroupArn'],
                'health_check_path': tg.get('HealthCheckPath', 'TCP'),
                'health_check_port': tg['HealthCheckPort'],
                'targets': []
            }
            
            print(f"\nTarget Group: {tg['TargetGroupName']}")
            print(f"Health Check: {tg.get('HealthCheckPath', 'TCP')} on port {tg['HealthCheckPort']}")
            print("Target Health:")
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
                
                results['nlb']['target_group']['targets'].append(target_info)
                print(f"  {target['Target']['Id']}:{target['Target']['Port']} - {target['TargetHealth']['State']}")
                if 'Reason' in target['TargetHealth']:
                    print(f"    Reason: {target['TargetHealth']['Reason']}")
                if 'Description' in target['TargetHealth']:
                    print(f"    Description: {target['TargetHealth']['Description']}")
        
    except Exception as e:
        print(f"❌ Error checking NLB: {e}")
        results['nlb'] = {'error': str(e)}
    
    # 6. Root Cause Analysis
    print_section("6. ROOT CAUSE ANALYSIS")
    
    issues = []
    
    # Check if task is in private subnet without NAT
    if not results['eni'].get('public_ip'):
        issues.append({
            'severity': 'HIGH',
            'issue': 'Task has no public IP',
            'impact': 'Cannot reach internet for health checks or external services',
            'recommendation': 'Ensure subnet has NAT Gateway or use public subnet with auto-assign public IP'
        })
    
    # Check if load balancers are in different VPC
    task_vpc = results['eni']['vpc_id']
    if results.get('alb', {}).get('vpc_id') != task_vpc:
        issues.append({
            'severity': 'CRITICAL',
            'issue': f"ALB VPC ({results['alb']['vpc_id']}) != Task VPC ({task_vpc})",
            'impact': 'ALB cannot route traffic to tasks',
            'recommendation': 'Move ALB to same VPC as tasks or use VPC peering'
        })
    
    if results.get('nlb', {}).get('vpc_id') != task_vpc:
        issues.append({
            'severity': 'CRITICAL',
            'issue': f"NLB VPC ({results['nlb']['vpc_id']}) != Task VPC ({task_vpc})",
            'impact': 'NLB cannot route traffic to tasks',
            'recommendation': 'Move NLB to same VPC as tasks'
        })
    
    # Check security group rules
    task_ip = results['eni']['private_ip']
    has_port_8000_rule = False
    for sg in results.get('security_groups', []):
        for rule in sg.get('inbound_rules', []):
            if '8000' in rule:
                has_port_8000_rule = True
                break
    
    if not has_port_8000_rule:
        issues.append({
            'severity': 'HIGH',
            'issue': 'No inbound rule for port 8000 in task security group',
            'impact': 'Load balancers cannot reach application',
            'recommendation': 'Add inbound rule allowing port 8000 from load balancer security groups'
        })
    
    results['root_cause_analysis'] = {
        'issues_found': len(issues),
        'issues': issues
    }
    
    if issues:
        print(f"\n🔍 Found {len(issues)} potential issues:\n")
        for i, issue in enumerate(issues, 1):
            print(f"{i}. [{issue['severity']}] {issue['issue']}")
            print(f"   Impact: {issue['impact']}")
            print(f"   Recommendation: {issue['recommendation']}\n")
    else:
        print("✅ No obvious configuration issues found")
        print("⚠️  Issue may be application-level (app not listening on port 8000)")
    
    # Save results
    filename = save_results(results, 'lb-connectivity-diagnosis')
    print_section("RESULTS SAVED")
    print(f"📄 Full diagnosis saved to: {filename}")
    
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
