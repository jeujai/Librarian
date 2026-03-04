#!/usr/bin/env python3

"""
Move Load Balancer to Shared VPC Script

This script moves the load balancer to the same VPC as the ECS service
where the shared NAT Gateway provides internet access.
"""

import boto3
import json
import time
from datetime import datetime
from typing import Dict, List, Optional

class LoadBalancerMover:
    def __init__(self):
        self.elbv2 = boto3.client('elbv2')
        self.ec2 = boto3.client('ec2')
        self.route53 = boto3.client('route53')
        
        # Configuration
        self.current_lb_arn = 'arn:aws:elasticloadbalancing:us-east-1:591222106065:loadbalancer/app/multimodal-librarian-full-ml/39e45609ae99d010'
        self.current_tg_arn = 'arn:aws:elasticloadbalancing:us-east-1:591222106065:targetgroup/multimodal-librarian-full-ml/470249d1c107d47d'
        self.target_vpc_id = 'vpc-014ac5b9fc828c78f'  # Shared NAT Gateway VPC
        
        # Results storage
        self.results = {
            'timestamp': datetime.now().isoformat(),
            'script_name': 'Load Balancer VPC Move',
            'steps_completed': [],
            'errors': [],
            'resources_created': []
        }

    def log_step(self, step: str, status: str = 'completed', details: Dict = None):
        """Log a step completion"""
        step_info = {
            'step': step,
            'status': status,
            'timestamp': datetime.now().isoformat()
        }
        if details:
            step_info['details'] = details
        
        self.results['steps_completed'].append(step_info)
        print(f"✅ {step}")
        if details:
            for key, value in details.items():
                print(f"   - {key}: {value}")

    def log_error(self, error: str, details: Dict = None):
        """Log an error"""
        error_info = {
            'error': error,
            'timestamp': datetime.now().isoformat()
        }
        if details:
            error_info['details'] = details
            
        self.results['errors'].append(error_info)
        print(f"❌ {error}")

    def get_current_lb_configuration(self) -> Dict:
        """Get current load balancer configuration"""
        print("🔍 Step 1: Analyzing current load balancer configuration...")
        
        try:
            # Get load balancer details
            lb_response = self.elbv2.describe_load_balancers(
                LoadBalancerArns=[self.current_lb_arn]
            )
            lb = lb_response['LoadBalancers'][0]
            
            # Get listeners
            listeners_response = self.elbv2.describe_listeners(
                LoadBalancerArn=self.current_lb_arn
            )
            
            # Get target group details
            tg_response = self.elbv2.describe_target_groups(
                TargetGroupArns=[self.current_tg_arn]
            )
            tg = tg_response['TargetGroups'][0]
            
            config = {
                'load_balancer': {
                    'name': lb['LoadBalancerName'],
                    'vpc_id': lb['VpcId'],
                    'scheme': lb['Scheme'],
                    'type': lb['Type'],
                    'security_groups': lb['SecurityGroups'],
                    'subnets': [az['SubnetId'] for az in lb['AvailabilityZones']],
                    'dns_name': lb['DNSName']
                },
                'listeners': listeners_response['Listeners'],
                'target_group': {
                    'name': tg['TargetGroupName'],
                    'vpc_id': tg['VpcId'],
                    'port': tg['Port'],
                    'protocol': tg['Protocol'],
                    'health_check': {
                        'path': tg['HealthCheckPath'],
                        'port': tg['HealthCheckPort'],
                        'protocol': tg['HealthCheckProtocol']
                    }
                }
            }
            
            self.log_step("Load balancer configuration analyzed", details={
                'Current VPC': lb['VpcId'],
                'Target VPC': self.target_vpc_id,
                'Listeners': len(listeners_response['Listeners']),
                'DNS Name': lb['DNSName']
            })
            
            return config
            
        except Exception as e:
            self.log_error(f"Failed to analyze load balancer configuration: {str(e)}")
            raise

    def get_target_vpc_public_subnets(self) -> List[str]:
        """Get public subnets in the target VPC for the load balancer"""
        print("🔍 Step 2: Finding public subnets in target VPC...")
        
        try:
            # Get all subnets in target VPC
            response = self.ec2.describe_subnets(
                Filters=[
                    {'Name': 'vpc-id', 'Values': [self.target_vpc_id]}
                ]
            )
            
            subnets = response['Subnets']
            
            # Find public subnets (those that map public IPs)
            public_subnets = [s for s in subnets if s['MapPublicIpOnLaunch']]
            
            if not public_subnets:
                # Fallback: check route tables for internet gateway routes
                public_subnets = []
                for subnet in subnets:
                    route_response = self.ec2.describe_route_tables(
                        Filters=[
                            {'Name': 'association.subnet-id', 'Values': [subnet['SubnetId']]}
                        ]
                    )
                    
                    # Check main route table if no explicit association
                    if not route_response['RouteTables']:
                        route_response = self.ec2.describe_route_tables(
                            Filters=[
                                {'Name': 'vpc-id', 'Values': [self.target_vpc_id]},
                                {'Name': 'association.main', 'Values': ['true']}
                            ]
                        )
                    
                    # Check for internet gateway routes
                    for rt in route_response['RouteTables']:
                        for route in rt['Routes']:
                            if route.get('GatewayId', '').startswith('igw-'):
                                public_subnets.append(subnet)
                                break
            
            # Select subnets across multiple AZs
            selected_subnets = []
            used_azs = set()
            
            for subnet in public_subnets:
                if subnet['AvailabilityZone'] not in used_azs:
                    selected_subnets.append(subnet['SubnetId'])
                    used_azs.add(subnet['AvailabilityZone'])
                    
                    if len(selected_subnets) >= 2:  # ALB needs at least 2 AZs
                        break
            
            if len(selected_subnets) < 2:
                raise Exception("Need at least 2 public subnets in different AZs for ALB")
            
            self.log_step("Public subnets identified in target VPC", details={
                'VPC': self.target_vpc_id,
                'Total Subnets': len(subnets),
                'Public Subnets': len(public_subnets),
                'Selected': len(selected_subnets)
            })
            
            return selected_subnets
            
        except Exception as e:
            self.log_error(f"Failed to find public subnets: {str(e)}")
            raise

    def create_security_group(self) -> str:
        """Create security group for the new load balancer"""
        print("🔧 Step 3: Creating security group for new load balancer...")
        
        try:
            sg_name = 'multimodal-librarian-alb-shared-vpc'
            
            # Check if security group already exists
            try:
                existing_sg_response = self.ec2.describe_security_groups(
                    Filters=[
                        {'Name': 'group-name', 'Values': [sg_name]},
                        {'Name': 'vpc-id', 'Values': [self.target_vpc_id]}
                    ]
                )
                
                if existing_sg_response['SecurityGroups']:
                    sg_id = existing_sg_response['SecurityGroups'][0]['GroupId']
                    self.log_step("Using existing security group", details={
                        'Security Group ID': sg_id,
                        'VPC': self.target_vpc_id,
                        'Status': 'Reusing existing security group'
                    })
                    return sg_id
            except Exception:
                pass
            
            # Create security group
            sg_response = self.ec2.create_security_group(
                GroupName=sg_name,
                Description='Security group for Multimodal Librarian ALB in shared VPC',
                VpcId=self.target_vpc_id
            )
            
            sg_id = sg_response['GroupId']
            
            # Add inbound rules for HTTP and HTTPS
            self.ec2.authorize_security_group_ingress(
                GroupId=sg_id,
                IpPermissions=[
                    {
                        'IpProtocol': 'tcp',
                        'FromPort': 80,
                        'ToPort': 80,
                        'IpRanges': [{'CidrIp': '0.0.0.0/0', 'Description': 'HTTP from anywhere'}]
                    },
                    {
                        'IpProtocol': 'tcp',
                        'FromPort': 443,
                        'ToPort': 443,
                        'IpRanges': [{'CidrIp': '0.0.0.0/0', 'Description': 'HTTPS from anywhere'}]
                    }
                ]
            )
            
            self.results['resources_created'].append({
                'type': 'security_group',
                'id': sg_id,
                'name': sg_name
            })
            
            self.log_step("Security group created", details={
                'Security Group ID': sg_id,
                'VPC': self.target_vpc_id,
                'Rules': 'HTTP (80) and HTTPS (443) from anywhere'
            })
            
            return sg_id
            
        except Exception as e:
            self.log_error(f"Failed to create security group: {str(e)}")
            raise

    def create_target_group(self, config: Dict) -> str:
        """Create new target group in target VPC"""
        print("🔧 Step 4: Creating target group in target VPC...")
        
        try:
            tg_config = config['target_group']
            
            response = self.elbv2.create_target_group(
                Name='ml-shared-vpc-tg',
                Protocol=tg_config['protocol'],
                Port=tg_config['port'],
                VpcId=self.target_vpc_id,
                TargetType='ip',  # Required for ECS awsvpc network mode
                HealthCheckPath=tg_config['health_check']['path'],
                HealthCheckPort=str(tg_config['health_check']['port']),
                HealthCheckProtocol=tg_config['health_check']['protocol'],
                HealthCheckIntervalSeconds=30,
                HealthCheckTimeoutSeconds=5,
                HealthyThresholdCount=2,
                UnhealthyThresholdCount=2,
                Tags=[
                    {'Key': 'Name', 'Value': 'ml-shared-vpc-tg'},
                    {'Key': 'Environment', 'Value': 'production'}
                ]
            )
            
            tg_arn = response['TargetGroups'][0]['TargetGroupArn']
            
            self.results['resources_created'].append({
                'type': 'target_group',
                'arn': tg_arn,
                'name': 'ml-shared-vpc-tg'
            })
            
            self.log_step("Target group created", details={
                'Target Group ARN': tg_arn,
                'VPC': self.target_vpc_id,
                'Port': tg_config['port'],
                'Health Check Path': tg_config['health_check']['path']
            })
            
            return tg_arn
            
        except Exception as e:
            self.log_error(f"Failed to create target group: {str(e)}")
            raise

    def create_load_balancer(self, config: Dict, subnets: List[str], security_group: str) -> str:
        """Create new load balancer in target VPC"""
        print("🔧 Step 5: Creating load balancer in target VPC...")
        
        try:
            lb_config = config['load_balancer']
            
            response = self.elbv2.create_load_balancer(
                Name='ml-shared-vpc-alb',
                Subnets=subnets,
                SecurityGroups=[security_group],
                Scheme=lb_config['scheme'],
                Type=lb_config['type'],
                Tags=[
                    {'Key': 'Name', 'Value': 'ml-shared-vpc-alb'},
                    {'Key': 'Environment', 'Value': 'production'}
                ]
            )
            
            lb_arn = response['LoadBalancers'][0]['LoadBalancerArn']
            dns_name = response['LoadBalancers'][0]['DNSName']
            
            self.results['resources_created'].append({
                'type': 'load_balancer',
                'arn': lb_arn,
                'name': 'ml-shared-vpc-alb',
                'dns_name': dns_name
            })
            
            self.log_step("Load balancer created", details={
                'Load Balancer ARN': lb_arn,
                'DNS Name': dns_name,
                'VPC': self.target_vpc_id,
                'Subnets': len(subnets)
            })
            
            return lb_arn, dns_name
            
        except Exception as e:
            self.log_error(f"Failed to create load balancer: {str(e)}")
            raise

    def create_listeners(self, config: Dict, lb_arn: str, tg_arn: str):
        """Create listeners for the new load balancer"""
        print("🔧 Step 6: Creating listeners...")
        
        try:
            listeners_created = []
            
            for listener in config['listeners']:
                # Create HTTP listener (port 80)
                if listener['Port'] == 80:
                    response = self.elbv2.create_listener(
                        LoadBalancerArn=lb_arn,
                        Protocol='HTTP',
                        Port=80,
                        DefaultActions=[
                            {
                                'Type': 'forward',
                                'TargetGroupArn': tg_arn
                            }
                        ]
                    )
                    listeners_created.append(response['Listeners'][0]['ListenerArn'])
                
                # For HTTPS listeners, we'd need SSL certificates
                # Skip for now and focus on HTTP connectivity
            
            self.log_step("Listeners created", details={
                'Listeners': len(listeners_created),
                'Protocols': 'HTTP'
            })
            
            return listeners_created
            
        except Exception as e:
            self.log_error(f"Failed to create listeners: {str(e)}")
            raise

    def update_ecs_service_target_group(self, new_tg_arn: str):
        """Update ECS service to use the new target group"""
        print("🔧 Step 7: Updating ECS service to use new target group...")
        
        try:
            ecs = boto3.client('ecs')
            
            # Get current service configuration
            response = ecs.describe_services(
                cluster='multimodal-lib-prod-cluster',
                services=['multimodal-lib-prod-service']
            )
            
            service = response['services'][0]
            current_lb_config = service['loadBalancers'][0]
            
            # Update service with new target group
            ecs.update_service(
                cluster='multimodal-lib-prod-cluster',
                service='multimodal-lib-prod-service',
                loadBalancers=[
                    {
                        'targetGroupArn': new_tg_arn,
                        'containerName': current_lb_config['containerName'],
                        'containerPort': current_lb_config['containerPort']
                    }
                ]
            )
            
            self.log_step("ECS service updated with new target group", details={
                'Target Group ARN': new_tg_arn,
                'Container': current_lb_config['containerName'],
                'Port': current_lb_config['containerPort']
            })
            
        except Exception as e:
            self.log_error(f"Failed to update ECS service: {str(e)}")
            raise

    def save_results(self):
        """Save results to file"""
        timestamp = int(time.time())
        filename = f"load-balancer-move-{timestamp}.json"
        
        with open(filename, 'w') as f:
            json.dump(self.results, f, indent=2)
        
        print(f"📄 Results saved to: {filename}")
        return filename

    def run_move(self):
        """Execute the load balancer move"""
        print("🔧 Move Load Balancer to Shared VPC")
        print("=" * 50)
        print("This will create a new load balancer in the shared NAT Gateway VPC")
        print()
        
        try:
            # Step 1: Get current configuration
            config = self.get_current_lb_configuration()
            
            # Check if already in target VPC
            if config['load_balancer']['vpc_id'] == self.target_vpc_id:
                print("✅ Load balancer is already in the target VPC!")
                return self.save_results()
            
            # Step 2: Get public subnets in target VPC
            subnets = self.get_target_vpc_public_subnets()
            
            # Step 3: Create security group
            security_group = self.create_security_group()
            
            # Step 4: Create target group
            new_tg_arn = self.create_target_group(config)
            
            # Step 5: Create load balancer
            new_lb_arn, new_dns_name = self.create_load_balancer(config, subnets, security_group)
            
            # Step 6: Create listeners
            self.create_listeners(config, new_lb_arn, new_tg_arn)
            
            # Step 7: Update ECS service
            self.update_ecs_service_target_group(new_tg_arn)
            
            print("\n🎉 Load Balancer Move Completed!")
            print("=" * 50)
            print(f"✅ New load balancer created in VPC: {self.target_vpc_id}")
            print(f"✅ New DNS name: {new_dns_name}")
            print(f"✅ ECS service updated to use new target group")
            print(f"\n🌐 Test your application at: http://{new_dns_name}")
            print(f"\n💡 Next Steps:")
            print(f"   1. Test the new load balancer connectivity")
            print(f"   2. Update DNS records to point to new load balancer")
            print(f"   3. Delete the old load balancer after verification")
            
        except Exception as e:
            self.log_error(f"Load balancer move failed: {str(e)}")
            print(f"\n❌ Load Balancer Move Failed: {str(e)}")
            print("Check the results file for detailed error information")
        
        finally:
            return self.save_results()

def main():
    """Main execution function"""
    mover = LoadBalancerMover()
    results_file = mover.run_move()
    
    print(f"\n📊 Summary:")
    print(f"   Steps completed: {len(mover.results['steps_completed'])}")
    print(f"   Errors encountered: {len(mover.results['errors'])}")
    print(f"   Resources created: {len(mover.results['resources_created'])}")
    print(f"   Results file: {results_file}")

if __name__ == "__main__":
    main()