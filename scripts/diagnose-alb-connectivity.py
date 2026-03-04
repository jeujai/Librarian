#!/usr/bin/env python3
"""
Diagnose ALB connectivity issues
"""
import boto3
import json
from datetime import datetime

def log(message):
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}")

def main():
    ecs = boto3.client('ecs', region_name='us-east-1')
    ec2 = boto3.client('ec2', region_name='us-east-1')
    elbv2 = boto3.client('elbv2', region_name='us-east-1')
    
    cluster = 'multimodal-lib-prod-cluster'
    service = 'multimodal-lib-prod-service'
    
    log("=" * 80)
    log("ALB Connectivity Diagnosis")
    log("=" * 80)
    
    # Get service details
    log("\n1. Service Configuration:")
    service_resp = ecs.describe_services(cluster=cluster, services=[service])
    service_data = service_resp['services'][0]
    
    load_balancers = service_data.get('loadBalancers', [])
    if not load_balancers:
        log("ERROR: No load balancers configured!")
        return
    
    target_group_arn = load_balancers[0]['targetGroupArn']
    log(f"   Target Group: {target_group_arn}")
    
    # Get target group details
    log("\n2. Target Group Configuration:")
    tg_resp = elbv2.describe_target_groups(TargetGroupArns=[target_group_arn])
    tg = tg_resp['TargetGroups'][0]
    
    log(f"   Health Check Path: {tg['HealthCheckPath']}")
    log(f"   Health Check Interval: {tg['HealthCheckIntervalSeconds']}s")
    log(f"   Health Check Timeout: {tg['HealthCheckTimeoutSeconds']}s")
    log(f"   Healthy Threshold: {tg['HealthyThresholdCount']}")
    log(f"   Unhealthy Threshold: {tg['UnhealthyThresholdCount']}")
    log(f"   VPC: {tg['VpcId']}")
    
    # Get load balancer details
    lb_arn = tg['LoadBalancerArns'][0]
    lb_resp = elbv2.describe_load_balancers(LoadBalancerArns=[lb_arn])
    lb = lb_resp['LoadBalancers'][0]
    
    log("\n3. Load Balancer Configuration:")
    log(f"   Name: {lb['LoadBalancerName']}")
    log(f"   DNS: {lb['DNSName']}")
    log(f"   Scheme: {lb['Scheme']}")
    log(f"   VPC: {lb['VpcId']}")
    log(f"   Subnets: {[az['SubnetId'] for az in lb['AvailabilityZones']]}")
    
    lb_sg_ids = lb['SecurityGroups']
    log(f"   Security Groups: {lb_sg_ids}")
    
    # Get task details
    log("\n4. Running Tasks:")
    tasks_resp = ecs.list_tasks(cluster=cluster, serviceName=service, desiredStatus='RUNNING')
    task_arns = tasks_resp['taskArns']
    
    if not task_arns:
        log("   No running tasks!")
        return
    
    tasks_detail = ecs.describe_tasks(cluster=cluster, tasks=task_arns)
    
    for task in tasks_detail['tasks']:
        task_id = task['taskArn'].split('/')[-1]
        log(f"\n   Task: {task_id}")
        log(f"   Status: {task['lastStatus']} / Health: {task.get('healthStatus', 'N/A')}")
        
        # Get network interface
        for attachment in task['attachments']:
            if attachment['type'] == 'ElasticNetworkInterface':
                for detail in attachment['details']:
                    if detail['name'] == 'networkInterfaceId':
                        eni_id = detail['value']
                        log(f"   ENI: {eni_id}")
                        
                        # Get ENI details
                        eni_resp = ec2.describe_network_interfaces(NetworkInterfaceIds=[eni_id])
                        eni = eni_resp['NetworkInterfaces'][0]
                        
                        log(f"   Private IP: {eni['PrivateIpAddress']}")
                        log(f"   Subnet: {eni['SubnetId']}")
                        log(f"   Security Groups: {[sg['GroupId'] for sg in eni['Groups']]}")
                        
                        task_sg_ids = [sg['GroupId'] for sg in eni['Groups']]
    
    # Check security group rules
    log("\n5. Security Group Analysis:")
    
    log("\n   ALB Security Groups:")
    for sg_id in lb_sg_ids:
        sg_resp = ec2.describe_security_groups(GroupIds=[sg_id])
        sg = sg_resp['SecurityGroups'][0]
        log(f"\n   {sg_id} ({sg['GroupName']}):")
        log(f"   Outbound Rules:")
        for rule in sg['IpPermissionsEgress']:
            log(f"      {rule}")
    
    log("\n   Task Security Groups:")
    for sg_id in task_sg_ids:
        sg_resp = ec2.describe_security_groups(GroupIds=[sg_id])
        sg = sg_resp['SecurityGroups'][0]
        log(f"\n   {sg_id} ({sg['GroupName']}):")
        log(f"   Inbound Rules (Port 8000):")
        for rule in sg['IpPermissions']:
            if rule.get('FromPort') == 8000:
                log(f"      {rule}")
    
    # Check target health
    log("\n6. Target Health:")
    health_resp = elbv2.describe_target_health(TargetGroupArn=target_group_arn)
    for target in health_resp['TargetHealthDescriptions']:
        log(f"\n   Target: {target['Target']['Id']}:{target['Target']['Port']}")
        log(f"   State: {target['TargetHealth']['State']}")
        log(f"   Reason: {target['TargetHealth'].get('Reason', 'N/A')}")
        log(f"   Description: {target['TargetHealth'].get('Description', 'N/A')}")
    
    # Check route tables
    log("\n7. Route Table Analysis:")
    for az in lb['AvailabilityZones']:
        subnet_id = az['SubnetId']
        log(f"\n   Subnet: {subnet_id}")
        
        # Get route table
        rt_resp = ec2.describe_route_tables(
            Filters=[{'Name': 'association.subnet-id', 'Values': [subnet_id]}]
        )
        
        if rt_resp['RouteTables']:
            rt = rt_resp['RouteTables'][0]
            log(f"   Route Table: {rt['RouteTableId']}")
            log(f"   Routes:")
            for route in rt['Routes']:
                dest = route.get('DestinationCidrBlock', route.get('DestinationPrefixListId', 'N/A'))
                target = route.get('GatewayId', route.get('NatGatewayId', route.get('NetworkInterfaceId', 'local')))
                log(f"      {dest} -> {target}")
    
    log("\n" + "=" * 80)
    log("Diagnosis Complete")
    log("=" * 80)

if __name__ == '__main__':
    main()
