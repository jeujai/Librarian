#!/usr/bin/env python3
"""
Diagnose ECS task networking issues preventing load balancer registration.
"""

import boto3
import json
import sys
from datetime import datetime

def diagnose_ecs_task_networking():
    """Diagnose ECS task networking issues."""
    
    try:
        # Initialize clients
        ecs_client = boto3.client('ecs', region_name='us-east-1')
        ec2_client = boto3.client('ec2', region_name='us-east-1')
        elb_client = boto3.client('elbv2', region_name='us-east-1')
        
        diagnosis = {
            'timestamp': datetime.now().isoformat(),
            'task_analysis': {},
            'network_configuration': {},
            'subnet_analysis': {},
            'security_group_analysis': {},
            'recommendations': []
        }
        
        print("🔍 Diagnosing ECS Task Networking Issues")
        print("=" * 50)
        
        cluster_name = 'multimodal-lib-prod-cluster'
        service_name = 'multimodal-lib-prod-service'
        
        # 1. Get running tasks
        print("\n1. Analyzing Running Tasks:")
        print("-" * 30)
        
        tasks_response = ecs_client.list_tasks(
            cluster=cluster_name,
            serviceName=service_name
        )
        
        if not tasks_response['taskArns']:
            print("❌ No running tasks found")
            diagnosis['recommendations'].append("No running tasks found - service may be failing to start")
            return diagnosis
        
        # Get task details
        task_details = ecs_client.describe_tasks(
            cluster=cluster_name,
            tasks=tasks_response['taskArns']
        )
        
        for task in task_details['tasks']:
            task_arn = task['taskArn']
            task_id = task_arn.split('/')[-1]
            
            print(f"📋 Task: {task_id}")
            print(f"   - Status: {task['lastStatus']}")
            print(f"   - Health: {task.get('healthStatus', 'UNKNOWN')}")
            print(f"   - CPU/Memory: {task.get('cpu', 'N/A')}/{task.get('memory', 'N/A')}")
            
            # Get network configuration
            attachments = task.get('attachments', [])
            for attachment in attachments:
                if attachment['type'] == 'ElasticNetworkInterface':
                    for detail in attachment['details']:
                        if detail['name'] == 'networkInterfaceId':
                            eni_id = detail['value']
                            print(f"   - ENI: {eni_id}")
                            
                            # Get ENI details
                            eni_response = ec2_client.describe_network_interfaces(
                                NetworkInterfaceIds=[eni_id]
                            )
                            
                            if eni_response['NetworkInterfaces']:
                                eni = eni_response['NetworkInterfaces'][0]
                                private_ip = eni.get('PrivateIpAddress')
                                subnet_id = eni.get('SubnetId')
                                vpc_id = eni.get('VpcId')
                                
                                print(f"   - Private IP: {private_ip}")
                                print(f"   - Subnet: {subnet_id}")
                                print(f"   - VPC: {vpc_id}")
                                
                                diagnosis['task_analysis'][task_id] = {
                                    'status': task['lastStatus'],
                                    'health': task.get('healthStatus', 'UNKNOWN'),
                                    'eni_id': eni_id,
                                    'private_ip': private_ip,
                                    'subnet_id': subnet_id,
                                    'vpc_id': vpc_id
                                }
                                
                                # Check if IP is in correct subnet for target group
                                print(f"   - Checking subnet compatibility...")
                                
                                # Get subnet details
                                subnet_response = ec2_client.describe_subnets(
                                    SubnetIds=[subnet_id]
                                )
                                
                                if subnet_response['Subnets']:
                                    subnet = subnet_response['Subnets'][0]
                                    subnet_cidr = subnet['CidrBlock']
                                    az = subnet['AvailabilityZone']
                                    
                                    print(f"     - Subnet CIDR: {subnet_cidr}")
                                    print(f"     - AZ: {az}")
                                    
                                    diagnosis['subnet_analysis'][subnet_id] = {
                                        'cidr_block': subnet_cidr,
                                        'availability_zone': az,
                                        'vpc_id': vpc_id
                                    }
            
            # Check container status
            containers = task.get('containers', [])
            for container in containers:
                container_name = container['name']
                container_status = container['lastStatus']
                
                print(f"   - Container {container_name}: {container_status}")
                
                if container_status != 'RUNNING':
                    reason = container.get('reason', 'Unknown')
                    print(f"     Reason: {reason}")
                    diagnosis['recommendations'].append(f"Container {container_name} not running: {reason}")
                
                # Check network bindings
                network_bindings = container.get('networkBindings', [])
                for binding in network_bindings:
                    host_port = binding.get('hostPort')
                    container_port = binding.get('containerPort')
                    protocol = binding.get('protocol')
                    
                    print(f"     - Port binding: {host_port}:{container_port} ({protocol})")
        
        # 2. Check service network configuration
        print("\n2. Service Network Configuration:")
        print("-" * 35)
        
        service_details = ecs_client.describe_services(
            cluster=cluster_name,
            services=[service_name]
        )
        
        if service_details['services']:
            service = service_details['services'][0]
            network_config = service.get('networkConfiguration', {})
            
            if network_config:
                awsvpc_config = network_config.get('awsvpcConfiguration', {})
                subnets = awsvpc_config.get('subnets', [])
                security_groups = awsvpc_config.get('securityGroups', [])
                assign_public_ip = awsvpc_config.get('assignPublicIp', 'DISABLED')
                
                print(f"✅ Network Configuration Found:")
                print(f"   - Subnets: {len(subnets)}")
                for subnet in subnets:
                    print(f"     - {subnet}")
                print(f"   - Security Groups: {len(security_groups)}")
                for sg in security_groups:
                    print(f"     - {sg}")
                print(f"   - Public IP: {assign_public_ip}")
                
                diagnosis['network_configuration'] = {
                    'subnets': subnets,
                    'security_groups': security_groups,
                    'assign_public_ip': assign_public_ip
                }
                
                # Check if subnets are compatible with load balancer
                print("\n3. Load Balancer Subnet Compatibility:")
                print("-" * 40)
                
                # Get load balancer subnets
                lb_response = elb_client.describe_load_balancers()
                multimodal_lb = None
                
                for lb in lb_response['LoadBalancers']:
                    if 'multimodal' in lb['LoadBalancerName'].lower():
                        multimodal_lb = lb
                        break
                
                if multimodal_lb:
                    lb_subnets = multimodal_lb.get('AvailabilityZones', [])
                    lb_subnet_ids = [az['SubnetId'] for az in lb_subnets]
                    
                    print(f"Load Balancer Subnets: {len(lb_subnet_ids)}")
                    for subnet_id in lb_subnet_ids:
                        print(f"   - {subnet_id}")
                    
                    # Check overlap
                    common_subnets = set(subnets) & set(lb_subnet_ids)
                    
                    print(f"\nSubnet Overlap Analysis:")
                    print(f"   - Service subnets: {len(subnets)}")
                    print(f"   - LB subnets: {len(lb_subnet_ids)}")
                    print(f"   - Common subnets: {len(common_subnets)}")
                    
                    if not common_subnets:
                        diagnosis['recommendations'].append("Service and load balancer have no common subnets")
                        print("   ❌ No common subnets - this may cause registration issues")
                    else:
                        print(f"   ✅ Common subnets: {list(common_subnets)}")
                
                # 4. Check security group rules
                print("\n4. Security Group Analysis:")
                print("-" * 30)
                
                if security_groups:
                    sg_response = ec2_client.describe_security_groups(
                        GroupIds=security_groups
                    )
                    
                    for sg in sg_response['SecurityGroups']:
                        sg_name = sg['GroupName']
                        sg_id = sg['GroupId']
                        
                        print(f"🔒 Security Group: {sg_name} ({sg_id})")
                        
                        # Check inbound rules for port 8000
                        inbound_rules = sg['IpPermissions']
                        port_8000_allowed = False
                        
                        for rule in inbound_rules:
                            from_port = rule.get('FromPort')
                            to_port = rule.get('ToPort')
                            protocol = rule.get('IpProtocol')
                            
                            if from_port <= 8000 <= to_port:
                                port_8000_allowed = True
                                print(f"   ✅ Port 8000 allowed: {protocol}:{from_port}-{to_port}")
                            else:
                                print(f"   - Rule: {protocol}:{from_port}-{to_port}")
                        
                        diagnosis['security_group_analysis'][sg_id] = {
                            'name': sg_name,
                            'port_8000_allowed': port_8000_allowed,
                            'rules_count': len(inbound_rules)
                        }
                        
                        if not port_8000_allowed:
                            diagnosis['recommendations'].append(f"Security group {sg_name} may not allow port 8000")
        
        # 5. Summary and Recommendations
        print("\n5. Summary and Recommendations:")
        print("-" * 35)
        
        if diagnosis['recommendations']:
            print("🚨 Issues Found:")
            for i, rec in enumerate(diagnosis['recommendations'], 1):
                print(f"   {i}. {rec}")
        else:
            print("✅ No obvious networking issues found")
        
        return diagnosis
        
    except Exception as e:
        print(f"❌ Error during diagnosis: {e}")
        return {'error': str(e)}

if __name__ == "__main__":
    result = diagnose_ecs_task_networking()
    
    # Save diagnosis to file
    diagnosis_file = f"ecs-task-networking-diagnosis-{int(datetime.now().timestamp())}.json"
    with open(diagnosis_file, 'w') as f:
        json.dump(result, f, indent=2, default=str)
    
    print(f"\n📄 Diagnosis saved to: {diagnosis_file}")
    
    if result.get('recommendations'):
        sys.exit(1)
    else:
        sys.exit(0)