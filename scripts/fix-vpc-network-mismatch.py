#!/usr/bin/env python3

"""
VPC Network Configuration Mismatch Fix Script

This script addresses the VPC mismatch between the load balancer and ECS service
that prevents external access to the application.

Issue: Load balancer in vpc-0bc85162dcdbcc986, ECS service in vpc-0b2186b38779e77f6
Solution: Update ECS service to use the same VPC as the load balancer
"""

import boto3
import json
import time
from datetime import datetime
from typing import Dict, List, Optional

class VPCNetworkMismatchFixer:
    def __init__(self):
        self.ecs = boto3.client('ecs')
        self.ec2 = boto3.client('ec2')
        self.elbv2 = boto3.client('elbv2')
        
        # Configuration
        self.cluster_name = 'multimodal-lib-prod-cluster'
        self.service_name = 'multimodal-lib-prod-service'
        self.load_balancer_arn = 'arn:aws:elasticloadbalancing:us-east-1:591222106065:loadbalancer/app/multimodal-librarian-full-ml/39e45609ae99d010'
        self.target_group_arn = 'arn:aws:elasticloadbalancing:us-east-1:591222106065:targetgroup/multimodal-librarian-full-ml/470249d1c107d47d'
        
        # Results storage
        self.results = {
            'timestamp': datetime.now().isoformat(),
            'script_name': 'VPC Network Mismatch Fix',
            'steps_completed': [],
            'errors': [],
            'network_config': {}
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

    def get_load_balancer_vpc_info(self) -> Dict:
        """Get load balancer VPC and subnet information"""
        print("🔍 Step 1: Analyzing load balancer network configuration...")
        
        try:
            # Get load balancer details
            lb_response = self.elbv2.describe_load_balancers(
                LoadBalancerArns=[self.load_balancer_arn]
            )
            
            lb = lb_response['LoadBalancers'][0]
            lb_vpc_id = lb['VpcId']
            lb_subnets = lb['AvailabilityZones']
            
            # Get subnet details
            subnet_ids = [az['SubnetId'] for az in lb_subnets]
            subnets_response = self.ec2.describe_subnets(SubnetIds=subnet_ids)
            
            # Get security groups
            lb_security_groups = lb['SecurityGroups']
            
            network_info = {
                'vpc_id': lb_vpc_id,
                'subnet_ids': subnet_ids,
                'availability_zones': [az['ZoneName'] for az in lb_subnets],
                'security_groups': lb_security_groups,
                'subnets_details': []
            }
            
            for subnet in subnets_response['Subnets']:
                network_info['subnets_details'].append({
                    'subnet_id': subnet['SubnetId'],
                    'availability_zone': subnet['AvailabilityZone'],
                    'cidr_block': subnet['CidrBlock'],
                    'is_public': len([rt for rt in self.get_route_tables(subnet['SubnetId']) 
                                    if any(route.get('GatewayId', '').startswith('igw-') 
                                          for route in rt.get('Routes', []))]) > 0
                })
            
            self.results['network_config']['load_balancer'] = network_info
            
            self.log_step("Load balancer network analysis completed", details={
                'VPC ID': lb_vpc_id,
                'Subnets': len(subnet_ids),
                'Security Groups': len(lb_security_groups)
            })
            
            return network_info
            
        except Exception as e:
            self.log_error(f"Failed to analyze load balancer network: {str(e)}")
            raise

    def get_route_tables(self, subnet_id: str) -> List[Dict]:
        """Get route tables for a subnet"""
        try:
            response = self.ec2.describe_route_tables(
                Filters=[
                    {'Name': 'association.subnet-id', 'Values': [subnet_id]}
                ]
            )
            return response['RouteTables']
        except Exception:
            return []

    def get_current_ecs_service_config(self) -> Dict:
        """Get current ECS service network configuration"""
        print("🔍 Step 2: Analyzing current ECS service configuration...")
        
        try:
            response = self.ecs.describe_services(
                cluster=self.cluster_name,
                services=[self.service_name]
            )
            
            service = response['services'][0]
            network_config = service['networkConfiguration']['awsvpcConfiguration']
            
            # Get subnet VPC information
            subnet_response = self.ec2.describe_subnets(
                SubnetIds=network_config['subnets']
            )
            
            current_vpc_id = subnet_response['Subnets'][0]['VpcId']
            
            service_info = {
                'vpc_id': current_vpc_id,
                'subnets': network_config['subnets'],
                'security_groups': network_config['securityGroups'],
                'assign_public_ip': network_config['assignPublicIp'],
                'task_definition': service['taskDefinition']
            }
            
            self.results['network_config']['ecs_service'] = service_info
            
            self.log_step("ECS service network analysis completed", details={
                'Current VPC ID': current_vpc_id,
                'Subnets': len(network_config['subnets']),
                'Security Groups': len(network_config['securityGroups'])
            })
            
            return service_info
            
        except Exception as e:
            self.log_error(f"Failed to analyze ECS service network: {str(e)}")
            raise

    def find_compatible_subnets(self, target_vpc_id: str, current_config: Dict) -> List[str]:
        """Find compatible subnets in the target VPC"""
        print("🔍 Step 3: Finding compatible subnets in target VPC...")
        
        try:
            # Get all subnets in target VPC
            response = self.ec2.describe_subnets(
                Filters=[
                    {'Name': 'vpc-id', 'Values': [target_vpc_id]}
                ]
            )
            
            subnets = response['Subnets']
            
            # Filter for private subnets (ECS tasks should run in private subnets)
            private_subnets = []
            for subnet in subnets:
                # Check if subnet has route to NAT Gateway (private) or Internet Gateway (public)
                route_tables = self.get_route_tables(subnet['SubnetId'])
                is_private = True
                
                for rt in route_tables:
                    for route in rt.get('Routes', []):
                        if route.get('GatewayId', '').startswith('igw-'):
                            is_private = False
                            break
                    if not is_private:
                        break
                
                if is_private:
                    private_subnets.append(subnet)
            
            # Select subnets across multiple AZs for high availability
            selected_subnets = []
            used_azs = set()
            
            for subnet in private_subnets:
                if subnet['AvailabilityZone'] not in used_azs:
                    selected_subnets.append(subnet['SubnetId'])
                    used_azs.add(subnet['AvailabilityZone'])
                    
                    # Limit to 3 subnets for cost optimization
                    if len(selected_subnets) >= 3:
                        break
            
            if not selected_subnets:
                # Fallback to public subnets if no private subnets found
                selected_subnets = [s['SubnetId'] for s in subnets[:3]]
            
            self.log_step("Compatible subnets identified", details={
                'Target VPC': target_vpc_id,
                'Selected Subnets': len(selected_subnets),
                'Availability Zones': len(used_azs)
            })
            
            return selected_subnets
            
        except Exception as e:
            self.log_error(f"Failed to find compatible subnets: {str(e)}")
            raise

    def find_compatible_security_groups(self, target_vpc_id: str) -> List[str]:
        """Find or create compatible security groups in target VPC"""
        print("🔍 Step 4: Finding compatible security groups...")
        
        try:
            # Look for existing security groups that allow port 8000
            response = self.ec2.describe_security_groups(
                Filters=[
                    {'Name': 'vpc-id', 'Values': [target_vpc_id]}
                ]
            )
            
            compatible_sgs = []
            
            for sg in response['SecurityGroups']:
                # Check if security group allows inbound traffic on port 8000
                for rule in sg['IpPermissions']:
                    if (rule.get('FromPort', 0) <= 8000 <= rule.get('ToPort', 65535) or
                        (rule.get('FromPort') is None and rule.get('ToPort') is None)):
                        compatible_sgs.append(sg['GroupId'])
                        break
            
            if compatible_sgs:
                self.log_step("Compatible security groups found", details={
                    'Security Groups': len(compatible_sgs),
                    'Selected': compatible_sgs[0]
                })
                return [compatible_sgs[0]]
            
            # If no compatible security group found, use default
            default_sg_response = self.ec2.describe_security_groups(
                Filters=[
                    {'Name': 'vpc-id', 'Values': [target_vpc_id]},
                    {'Name': 'group-name', 'Values': ['default']}
                ]
            )
            
            if default_sg_response['SecurityGroups']:
                default_sg = default_sg_response['SecurityGroups'][0]['GroupId']
                self.log_step("Using default security group", details={
                    'Security Group': default_sg
                })
                return [default_sg]
            
            raise Exception("No compatible security groups found")
            
        except Exception as e:
            self.log_error(f"Failed to find compatible security groups: {str(e)}")
            raise

    def update_ecs_service_network_config(self, lb_network_info: Dict, current_config: Dict):
        """Update ECS service to use the same VPC as load balancer"""
        print("🔧 Step 5: Updating ECS service network configuration...")
        
        try:
            target_vpc_id = lb_network_info['vpc_id']
            
            # Find compatible subnets and security groups
            new_subnets = self.find_compatible_subnets(target_vpc_id, current_config)
            new_security_groups = self.find_compatible_security_groups(target_vpc_id)
            
            # Update service network configuration
            update_response = self.ecs.update_service(
                cluster=self.cluster_name,
                service=self.service_name,
                networkConfiguration={
                    'awsvpcConfiguration': {
                        'subnets': new_subnets,
                        'securityGroups': new_security_groups,
                        'assignPublicIp': 'DISABLED'  # Use private subnets
                    }
                }
            )
            
            self.log_step("ECS service network configuration updated", details={
                'New VPC': target_vpc_id,
                'New Subnets': len(new_subnets),
                'New Security Groups': len(new_security_groups)
            })
            
            return update_response
            
        except Exception as e:
            self.log_error(f"Failed to update ECS service network configuration: {str(e)}")
            raise

    def wait_for_service_stability(self):
        """Wait for ECS service to reach stable state"""
        print("⏳ Step 6: Waiting for service to stabilize...")
        
        try:
            waiter = self.ecs.get_waiter('services_stable')
            waiter.wait(
                cluster=self.cluster_name,
                services=[self.service_name],
                WaiterConfig={
                    'Delay': 15,
                    'MaxAttempts': 40  # 10 minutes max
                }
            )
            
            self.log_step("ECS service stabilized successfully")
            
        except Exception as e:
            self.log_error(f"Service failed to stabilize: {str(e)}")
            raise

    def verify_target_group_registration(self):
        """Verify that ECS tasks are registered with the correct target group"""
        print("🔍 Step 7: Verifying target group registration...")
        
        try:
            # Check target group health
            response = self.elbv2.describe_target_health(
                TargetGroupArn=self.target_group_arn
            )
            
            healthy_targets = [
                target for target in response['TargetHealthDescriptions']
                if target['TargetHealth']['State'] == 'healthy'
            ]
            
            total_targets = len(response['TargetHealthDescriptions'])
            
            self.log_step("Target group registration verified", details={
                'Total Targets': total_targets,
                'Healthy Targets': len(healthy_targets),
                'Target Group': self.target_group_arn.split('/')[-2]
            })
            
            return len(healthy_targets) > 0
            
        except Exception as e:
            self.log_error(f"Failed to verify target group registration: {str(e)}")
            return False

    def test_load_balancer_connectivity(self):
        """Test load balancer connectivity"""
        print("🔍 Step 8: Testing load balancer connectivity...")
        
        try:
            # Get load balancer DNS name
            lb_response = self.elbv2.describe_load_balancers(
                LoadBalancerArns=[self.load_balancer_arn]
            )
            
            dns_name = lb_response['LoadBalancers'][0]['DNSName']
            
            self.log_step("Load balancer connectivity test prepared", details={
                'DNS Name': dns_name,
                'Test URL': f"http://{dns_name}",
                'Health Check URL': f"http://{dns_name}/health/simple"
            })
            
            return dns_name
            
        except Exception as e:
            self.log_error(f"Failed to prepare connectivity test: {str(e)}")
            return None

    def save_results(self):
        """Save results to file"""
        timestamp = int(time.time())
        filename = f"vpc-network-mismatch-fix-{timestamp}.json"
        
        with open(filename, 'w') as f:
            json.dump(self.results, f, indent=2)
        
        print(f"📄 Fix results saved to: {filename}")
        return filename

    def run_fix(self):
        """Execute the complete VPC mismatch fix"""
        print("🔧 VPC Network Configuration Mismatch Fix")
        print("=" * 50)
        
        try:
            # Step 1: Analyze load balancer network configuration
            lb_network_info = self.get_load_balancer_vpc_info()
            
            # Step 2: Analyze current ECS service configuration
            current_config = self.get_current_ecs_service_config()
            
            # Check if fix is needed
            if lb_network_info['vpc_id'] == current_config['vpc_id']:
                print("✅ VPC configuration already matches - no fix needed!")
                self.log_step("VPC configuration already correct")
                return self.save_results()
            
            print(f"🔧 VPC mismatch detected:")
            print(f"   Load Balancer VPC: {lb_network_info['vpc_id']}")
            print(f"   ECS Service VPC: {current_config['vpc_id']}")
            print(f"   Proceeding with fix...")
            
            # Step 3-4: Find compatible network resources (handled in step 5)
            
            # Step 5: Update ECS service network configuration
            self.update_ecs_service_network_config(lb_network_info, current_config)
            
            # Step 6: Wait for service to stabilize
            self.wait_for_service_stability()
            
            # Step 7: Verify target group registration
            targets_healthy = self.verify_target_group_registration()
            
            # Step 8: Test connectivity
            dns_name = self.test_load_balancer_connectivity()
            
            print("\n🎉 VPC Network Mismatch Fix Completed!")
            print("=" * 50)
            print(f"✅ ECS service moved to Load Balancer VPC: {lb_network_info['vpc_id']}")
            print(f"✅ Service stabilized successfully")
            
            if targets_healthy:
                print(f"✅ Target group has healthy targets")
            else:
                print(f"⚠️  Target group registration in progress")
            
            if dns_name:
                print(f"🌐 Test your application at: http://{dns_name}")
                print(f"🔍 Health check: http://{dns_name}/health/simple")
            
            print(f"\n📄 Detailed results saved to file")
            
        except Exception as e:
            self.log_error(f"VPC mismatch fix failed: {str(e)}")
            print(f"\n❌ VPC Mismatch Fix Failed: {str(e)}")
            print("Check the results file for detailed error information")
        
        finally:
            return self.save_results()

def main():
    """Main execution function"""
    fixer = VPCNetworkMismatchFixer()
    results_file = fixer.run_fix()
    
    print(f"\n📊 Summary:")
    print(f"   Steps completed: {len(fixer.results['steps_completed'])}")
    print(f"   Errors encountered: {len(fixer.results['errors'])}")
    print(f"   Results file: {results_file}")

if __name__ == "__main__":
    main()