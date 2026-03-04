#!/usr/bin/env python3
"""
Diagnose ALB to ECS network path issues.

This script investigates why the ALB cannot reach ECS tasks on port 8000
by checking:
1. Network ACLs (NACLs)
2. Route tables
3. ALB ENI placement
4. ECS task ENI details
5. VPC Flow Logs status
"""

import boto3
import json
import time
from datetime import datetime

def main():
    ec2 = boto3.client('ec2')
    ecs = boto3.client('ecs')
    elbv2 = boto3.client('elbv2')
    logs = boto3.client('logs')
    
    print("=" * 80)
    print("ALB to ECS Network Path Diagnosis")
    print("=" * 80)
    
    results = {
        'timestamp': datetime.now().isoformat(),
        'issues_found': [],
        'recommendations': []
    }
    
    # Step 1: Get ALB and ECS task information
    print("\n1. Gathering ALB and ECS task information...")
    
    # Get ALB details
    alb_response = elbv2.describe_load_balancers(
        Names=['multimodal-lib-prod-alb-v2']
    )
    alb = alb_response['LoadBalancers'][0]
    alb_subnets = alb['AvailabilityZones']
    vpc_id = alb['VpcId']
    
    print(f"   ALB: {alb['LoadBalancerName']}")
    print(f"   VPC: {vpc_id}")
    print(f"   ALB Subnets:")
    for az in alb_subnets:
        print(f"     - {az['SubnetId']} ({az['ZoneName']})")
    
    # Get ECS task details
    cluster_name = 'multimodal-lib-prod-cluster'
    service_name = 'multimodal-lib-prod-service-alb'
    
    tasks_response = ecs.list_tasks(
        cluster=cluster_name,
        serviceName=service_name,
        desiredStatus='RUNNING'
    )
    
    if not tasks_response['taskArns']:
        print("   ✗ No running tasks found!")
        return
    
    task_arn = tasks_response['taskArns'][0]
    task_details = ecs.describe_tasks(
        cluster=cluster_name,
        tasks=[task_arn]
    )
    
    task = task_details['tasks'][0]
    task_eni_id = None
    task_private_ip = None
    task_subnet_id = None
    
    for attachment in task['attachments']:
        if attachment['type'] == 'ElasticNetworkInterface':
            for detail in attachment['details']:
                if detail['name'] == 'networkInterfaceId':
                    task_eni_id = detail['value']
                elif detail['name'] == 'privateIPv4Address':
                    task_private_ip = detail['value']
                elif detail['name'] == 'subnetId':
                    task_subnet_id = detail['value']
    
    print(f"\n   ECS Task:")
    print(f"     - Task ARN: {task_arn.split('/')[-1]}")
    print(f"     - Private IP: {task_private_ip}")
    print(f"     - Subnet: {task_subnet_id}")
    print(f"     - ENI: {task_eni_id}")
    
    results['alb_vpc'] = vpc_id
    results['alb_subnets'] = [az['SubnetId'] for az in alb_subnets]
    results['task_ip'] = task_private_ip
    results['task_subnet'] = task_subnet_id
    results['task_eni'] = task_eni_id
    
    # Step 2: Check Network ACLs for task subnet
    print("\n2. Checking Network ACLs for ECS task subnet...")
    
    nacl_response = ec2.describe_network_acls(
        Filters=[
            {'Name': 'association.subnet-id', 'Values': [task_subnet_id]}
        ]
    )
    
    if nacl_response['NetworkAcls']:
        nacl = nacl_response['NetworkAcls'][0]
        nacl_id = nacl['NetworkAclId']
        print(f"   Network ACL: {nacl_id}")
        
        # Check ingress rules
        print("\n   Ingress Rules:")
        ingress_allows_8000 = False
        for entry in sorted(nacl['Entries'], key=lambda x: x['RuleNumber']):
            if not entry['Egress']:  # Ingress rule
                rule_action = entry['RuleAction']
                rule_num = entry['RuleNumber']
                protocol = entry.get('Protocol', '-1')
                cidr = entry.get('CidrBlock', entry.get('Ipv6CidrBlock', 'N/A'))
                
                port_range = "All"
                if 'PortRange' in entry:
                    from_port = entry['PortRange'].get('From', 'N/A')
                    to_port = entry['PortRange'].get('To', 'N/A')
                    port_range = f"{from_port}-{to_port}"
                    
                    # Check if port 8000 is allowed
                    if rule_action == 'allow' and from_port <= 8000 <= to_port:
                        ingress_allows_8000 = True
                
                print(f"     Rule {rule_num}: {rule_action.upper()} - Protocol {protocol}, Ports {port_range}, CIDR {cidr}")
        
        # Check egress rules
        print("\n   Egress Rules:")
        egress_allows_all = False
        for entry in sorted(nacl['Entries'], key=lambda x: x['RuleNumber']):
            if entry['Egress']:  # Egress rule
                rule_action = entry['RuleAction']
                rule_num = entry['RuleNumber']
                protocol = entry.get('Protocol', '-1')
                cidr = entry.get('CidrBlock', entry.get('Ipv6CidrBlock', 'N/A'))
                
                port_range = "All"
                if 'PortRange' in entry:
                    from_port = entry['PortRange'].get('From', 'N/A')
                    to_port = entry['PortRange'].get('To', 'N/A')
                    port_range = f"{from_port}-{to_port}"
                else:
                    if rule_action == 'allow' and protocol == '-1':
                        egress_allows_all = True
                
                print(f"     Rule {rule_num}: {rule_action.upper()} - Protocol {protocol}, Ports {port_range}, CIDR {cidr}")
        
        results['nacl_id'] = nacl_id
        results['nacl_allows_ingress_8000'] = ingress_allows_8000
        results['nacl_allows_egress'] = egress_allows_all
        
        if not ingress_allows_8000:
            issue = "Network ACL may be blocking ingress traffic on port 8000"
            print(f"\n   ⚠️  {issue}")
            results['issues_found'].append(issue)
            results['recommendations'].append("Review and update Network ACL ingress rules to allow port 8000")
    
    # Step 3: Check Network ACLs for ALB subnets
    print("\n3. Checking Network ACLs for ALB subnets...")
    
    for alb_subnet_id in results['alb_subnets']:
        nacl_response = ec2.describe_network_acls(
            Filters=[
                {'Name': 'association.subnet-id', 'Values': [alb_subnet_id]}
            ]
        )
        
        if nacl_response['NetworkAcls']:
            nacl = nacl_response['NetworkAcls'][0]
            nacl_id = nacl['NetworkAclId']
            print(f"\n   Subnet {alb_subnet_id}: NACL {nacl_id}")
            
            # Check if egress allows port 8000
            egress_allows_8000 = False
            for entry in nacl['Entries']:
                if entry['Egress'] and entry['RuleAction'] == 'allow':
                    if 'PortRange' in entry:
                        from_port = entry['PortRange'].get('From', 0)
                        to_port = entry['PortRange'].get('To', 65535)
                        if from_port <= 8000 <= to_port:
                            egress_allows_8000 = True
                    elif entry.get('Protocol') == '-1':  # All protocols
                        egress_allows_8000 = True
            
            if not egress_allows_8000:
                issue = f"ALB subnet {alb_subnet_id} NACL may be blocking egress to port 8000"
                print(f"     ⚠️  {issue}")
                results['issues_found'].append(issue)
    
    # Step 4: Check route tables
    print("\n4. Checking route tables...")
    
    # Task subnet route table
    rt_response = ec2.describe_route_tables(
        Filters=[
            {'Name': 'association.subnet-id', 'Values': [task_subnet_id]}
        ]
    )
    
    if rt_response['RouteTables']:
        rt = rt_response['RouteTables'][0]
        rt_id = rt['RouteTableId']
        print(f"\n   Task Subnet Route Table: {rt_id}")
        print("   Routes:")
        for route in rt['Routes']:
            dest = route.get('DestinationCidrBlock', route.get('DestinationIpv6CidrBlock', 'N/A'))
            target = route.get('GatewayId', route.get('NatGatewayId', route.get('NetworkInterfaceId', route.get('VpcPeeringConnectionId', 'local'))))
            state = route.get('State', 'active')
            print(f"     - {dest} -> {target} ({state})")
        
        results['task_route_table'] = rt_id
    
    # ALB subnet route tables
    for alb_subnet_id in results['alb_subnets']:
        rt_response = ec2.describe_route_tables(
            Filters=[
                {'Name': 'association.subnet-id', 'Values': [alb_subnet_id]}
            ]
        )
        
        if rt_response['RouteTables']:
            rt = rt_response['RouteTables'][0]
            rt_id = rt['RouteTableId']
            print(f"\n   ALB Subnet {alb_subnet_id} Route Table: {rt_id}")
            print("   Routes:")
            for route in rt['Routes']:
                dest = route.get('DestinationCidrBlock', route.get('DestinationIpv6CidrBlock', 'N/A'))
                target = route.get('GatewayId', route.get('NatGatewayId', route.get('NetworkInterfaceId', route.get('VpcPeeringConnectionId', 'local'))))
                state = route.get('State', 'active')
                print(f"     - {dest} -> {target} ({state})")
    
    # Step 5: Check ALB ENIs
    print("\n5. Checking ALB network interfaces...")
    
    alb_eni_response = ec2.describe_network_interfaces(
        Filters=[
            {'Name': 'description', 'Values': [f'ELB {alb["LoadBalancerArn"].split("/")[-2]}/{alb["LoadBalancerArn"].split("/")[-1]}']},
            {'Name': 'vpc-id', 'Values': [vpc_id]}
        ]
    )
    
    print(f"   Found {len(alb_eni_response['NetworkInterfaces'])} ALB ENIs")
    for eni in alb_eni_response['NetworkInterfaces']:
        eni_id = eni['NetworkInterfaceId']
        eni_ip = eni['PrivateIpAddress']
        eni_subnet = eni['SubnetId']
        eni_sg = [sg['GroupId'] for sg in eni['Groups']]
        print(f"     - ENI {eni_id}: {eni_ip} in {eni_subnet}, SGs: {eni_sg}")
    
    # Step 6: Check ECS task ENI details
    print("\n6. Checking ECS task network interface details...")
    
    if task_eni_id:
        task_eni_response = ec2.describe_network_interfaces(
            NetworkInterfaceIds=[task_eni_id]
        )
        
        if task_eni_response['NetworkInterfaces']:
            eni = task_eni_response['NetworkInterfaces'][0]
            print(f"   ENI: {eni['NetworkInterfaceId']}")
            print(f"   Private IP: {eni['PrivateIpAddress']}")
            print(f"   Subnet: {eni['SubnetId']}")
            print(f"   Security Groups: {[sg['GroupId'] for sg in eni['Groups']]}")
            print(f"   Status: {eni['Status']}")
            
            # Check if ENI has a public IP
            if 'Association' in eni:
                print(f"   Public IP: {eni['Association'].get('PublicIp', 'None')}")
            else:
                print(f"   Public IP: None")
    
    # Step 7: Check VPC Flow Logs status
    print("\n7. Checking VPC Flow Logs status...")
    
    flow_logs_response = ec2.describe_flow_logs(
        Filters=[
            {'Name': 'resource-id', 'Values': [vpc_id]}
        ]
    )
    
    if flow_logs_response['FlowLogs']:
        print(f"   ✓ VPC Flow Logs are enabled")
        for flow_log in flow_logs_response['FlowLogs']:
            print(f"     - Flow Log: {flow_log['FlowLogId']}")
            print(f"       Status: {flow_log['FlowLogStatus']}")
            print(f"       Destination: {flow_log.get('LogDestination', 'CloudWatch Logs')}")
            
            # Check if we can access the logs
            if flow_log.get('LogGroupName'):
                log_group = flow_log['LogGroupName']
                print(f"       Log Group: {log_group}")
                
                try:
                    # Try to get recent log streams
                    streams_response = logs.describe_log_streams(
                        logGroupName=log_group,
                        orderBy='LastEventTime',
                        descending=True,
                        limit=5
                    )
                    print(f"       Recent log streams: {len(streams_response['logStreams'])}")
                except Exception as e:
                    print(f"       ⚠️  Cannot access log streams: {e}")
        
        results['flow_logs_enabled'] = True
    else:
        print(f"   ⚠️  VPC Flow Logs are NOT enabled")
        results['flow_logs_enabled'] = False
        results['recommendations'].append("Enable VPC Flow Logs to diagnose packet drops")
    
    # Step 8: Test connectivity from ALB subnet to task IP
    print("\n8. Analyzing connectivity path...")
    
    # Check if ALB and task are in same subnet
    if task_subnet_id in results['alb_subnets']:
        print(f"   ✓ ALB and ECS task are in the SAME subnet ({task_subnet_id})")
        print(f"     This should allow direct communication")
        results['same_subnet'] = True
    else:
        print(f"   ℹ️  ALB and ECS task are in DIFFERENT subnets")
        print(f"     ALB subnets: {results['alb_subnets']}")
        print(f"     Task subnet: {task_subnet_id}")
        print(f"     Traffic will route through VPC")
        results['same_subnet'] = False
    
    # Summary
    print("\n" + "=" * 80)
    print("DIAGNOSIS SUMMARY")
    print("=" * 80)
    
    if results['issues_found']:
        print("\n⚠️  Issues Found:")
        for i, issue in enumerate(results['issues_found'], 1):
            print(f"   {i}. {issue}")
    else:
        print("\n✓ No obvious network configuration issues found")
        print("\nPossible causes:")
        print("  1. Health check timing - application may be slow to respond")
        print("  2. Application not fully initialized when health check runs")
        print("  3. Transient network issues")
        print("  4. ALB target group deregistration delay")
    
    if results['recommendations']:
        print("\n📋 Recommendations:")
        for i, rec in enumerate(results['recommendations'], 1):
            print(f"   {i}. {rec}")
    
    print("\n🔍 Next Steps:")
    if not results.get('flow_logs_enabled'):
        print("   1. Enable VPC Flow Logs to see packet flow")
    print("   2. Increase ALB health check timeout to 15 seconds")
    print("   3. Increase health check interval to 60 seconds")
    print("   4. Add deregistration delay of 60 seconds")
    print("   5. Check application logs during health check failures")
    
    # Save results
    timestamp = int(time.time())
    filename = f'alb-network-path-diagnosis-{timestamp}.json'
    with open(filename, 'w') as f:
        json.dump(results, f, indent=2, default=str)
    
    print(f"\n📄 Results saved to: {filename}")

if __name__ == '__main__':
    main()
