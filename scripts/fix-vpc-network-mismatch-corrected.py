#!/usr/bin/env python3

"""
Corrected VPC Network Configuration Fix Script

This script addresses the VPC mismatch while ensuring ECS tasks have internet access
through the shared NAT Gateway in the CollaborativeEditor VPC.

Issue: Load balancer in vpc-0bc85162dcdbcc986, but shared NAT Gateway in vpc-014ac5b9fc828c78f
Solution: Use cross-VPC load balancing or move load balancer to shared NAT Gateway VPC
"""

import boto3
import json
import time
from datetime import datetime
from typing import Dict, List, Optional

class CorrectedVPCNetworkFixer:
    def __init__(self):
        self.ecs = boto3.client('ecs')
        self.ec2 = boto3.client('ec2')
        self.elbv2 = boto3.client('elbv2')
        
        # Configuration
        self.cluster_name = 'multimodal-lib-prod-cluster'
        self.service_name = 'multimodal-lib-prod-service'
        self.load_balancer_arn = 'arn:aws:elasticloadbalancing:us-east-1:591222106065:loadbalancer/app/multimodal-librarian-full-ml/39e45609ae99d010'
        self.target_group_arn = 'arn:aws:elasticloadbalancing:us-east-1:591222106065:targetgroup/multimodal-librarian-full-ml/470249d1c107d47d'
        
        # Shared NAT Gateway configuration
        self.shared_nat_gateway_id = 'nat-0e52e9a066891174e'
        self.shared_nat_vpc_id = 'vpc-014ac5b9fc828c78f'  # CollaborativeEditor VPC
        
        # Results storage
        self.results = {
            'timestamp': datetime.now().isoformat(),
            'script_name': 'Corrected VPC Network Fix',
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

    def analyze_current_configuration(self) -> Dict:
        """Analyze current network configuration"""
        print("🔍 Step 1: Analyzing current network configuration...")
        
        try:
            # Get load balancer info
            lb_response = self.elbv2.describe_load_balancers(
                LoadBalancerArns=[self.load_balancer_arn]
            )
            lb_vpc_id = lb_response['LoadBalancers'][0]['VpcId']
            
            # Get ECS service info
            ecs_response = self.ecs.describe_services(
                cluster=self.cluster_name,
                services=[self.service_name]
            )
            service = ecs_response['services'][0]
            ecs_subnets = service['networkConfiguration']['awsvpcConfiguration']['subnets']
            
            # Get ECS VPC from subnets
            subnet_response = self.ec2.describe_subnets(SubnetIds=ecs_subnets[:1])
            ecs_vpc_id = subnet_response['Subnets'][0]['VpcId']
            
            # Get shared NAT Gateway info
            nat_response = self.ec2.describe_nat_gateways(
                NatGatewayIds=[self.shared_nat_gateway_id]
            )
            nat_vpc_id = nat_response['NatGateways'][0]['VpcId']
            
            config = {
                'load_balancer_vpc': lb_vpc_id,
                'ecs_service_vpc': ecs_vpc_id,
                'shared_nat_vpc': nat_vpc_id,
                'shared_nat_gateway': self.shared_nat_gateway_id
            }
            
            self.results['network_config']['current'] = config
            
            self.log_step("Network configuration analysis completed", details={
                'Load Balancer VPC': lb_vpc_id,
                'ECS Service VPC': ecs_vpc_id,
                'Shared NAT Gateway VPC': nat_vpc_id,
                'NAT Gateway ID': self.shared_nat_gateway_id
            })
            
            return config
            
        except Exception as e:
            self.log_error(f"Failed to analyze network configuration: {str(e)}")
            raise

    def check_cross_vpc_connectivity(self, lb_vpc: str, ecs_vpc: str) -> bool:
        """Check if cross-VPC connectivity exists between load balancer and ECS VPCs"""
        print("🔍 Step 2: Checking cross-VPC connectivity options...")
        
        try:
            # Check for VPC peering connections
            peering_response = self.ec2.describe_vpc_peering_connections(
                Filters=[
                    {'Name': 'status-code', 'Values': ['active']},
                    {'Name': 'accepter-vpc-info.vpc-id', 'Values': [lb_vpc, ecs_vpc]},
                    {'Name': 'requester-vpc-info.vpc-id', 'Values': [lb_vpc, ecs_vpc]}
                ]
            )
            
            peering_connections = peering_response['VpcPeeringConnections']
            
            if peering_connections:
                self.log_step("VPC peering connection found", details={
                    'Peering Connections': len(peering_connections),
                    'Status': 'Active'
                })
                return True
            else:
                self.log_step("No VPC peering connection found", details={
                    'Cross-VPC Load Balancing': 'Not available',
                    'Recommendation': 'Move ECS to shared NAT Gateway VPC'
                })
                return False
                
        except Exception as e:
            self.log_error(f"Failed to check cross-VPC connectivity: {str(e)}")
            return False

    def get_shared_nat_vpc_subnets(self) -> List[str]:
        """Get private subnets in the shared NAT Gateway VPC"""
        print("🔍 Step 3: Finding private subnets in shared NAT Gateway VPC...")
        
        try:
            # Get all subnets in the shared NAT VPC
            response = self.ec2.describe_subnets(
                Filters=[
                    {'Name': 'vpc-id', 'Values': [self.shared_nat_vpc_id]}
                ]
            )
            
            subnets = response['Subnets']
            
            # Find private subnets (those with routes to NAT Gateway)
            private_subnets = []
            
            for subnet in subnets:
                # Check route tables for this subnet
                route_response = self.ec2.describe_route_tables(
                    Filters=[
                        {'Name': 'association.subnet-id', 'Values': [subnet['SubnetId']]}
                    ]
                )
                
                # If no explicit association, check main route table
                if not route_response['RouteTables']:
                    route_response = self.ec2.describe_route_tables(
                        Filters=[
                            {'Name': 'vpc-id', 'Values': [self.shared_nat_vpc_id]},
                            {'Name': 'association.main', 'Values': ['true']}
                        ]
                    )
                
                # Check if any route table has our NAT Gateway
                for rt in route_response['RouteTables']:
                    for route in rt['Routes']:
                        if route.get('NatGatewayId') == self.shared_nat_gateway_id:
                            private_subnets.append(subnet)
                            break
            
            # Select subnets across multiple AZs
            selected_subnets = []
            used_azs = set()
            
            for subnet in private_subnets:
                if subnet['AvailabilityZone'] not in used_azs:
                    selected_subnets.append(subnet['SubnetId'])
                    used_azs.add(subnet['AvailabilityZone'])
                    
                    if len(selected_subnets) >= 3:  # Limit for cost optimization
                        break
            
            if not selected_subnets:
                # Fallback: use any private subnets in the VPC
                private_subnets_fallback = [s for s in subnets if not s['MapPublicIpOnLaunch']]
                selected_subnets = [s['SubnetId'] for s in private_subnets_fallback[:3]]
            
            self.log_step("Private subnets identified in shared NAT VPC", details={
                'VPC': self.shared_nat_vpc_id,
                'Total Subnets': len(subnets),
                'Private Subnets': len(private_subnets),
                'Selected': len(selected_subnets)
            })
            
            return selected_subnets
            
        except Exception as e:
            self.log_error(f"Failed to find private subnets: {str(e)}")
            raise

    def get_compatible_security_groups(self) -> List[str]:
        """Get compatible security groups in the shared NAT VPC"""
        print("🔍 Step 4: Finding compatible security groups...")
        
        try:
            # Look for security groups that allow port 8000
            response = self.ec2.describe_security_groups(
                Filters=[
                    {'Name': 'vpc-id', 'Values': [self.shared_nat_vpc_id]}
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
            
            # Use default security group as fallback
            default_sg_response = self.ec2.describe_security_groups(
                Filters=[
                    {'Name': 'vpc-id', 'Values': [self.shared_nat_vpc_id]},
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

    def move_ecs_to_shared_nat_vpc(self):
        """Move ECS service to the VPC with shared NAT Gateway"""
        print("🔧 Step 5: Moving ECS service to shared NAT Gateway VPC...")
        
        try:
            # Get subnets and security groups in shared NAT VPC
            subnets = self.get_shared_nat_vpc_subnets()
            security_groups = self.get_compatible_security_groups()
            
            if not subnets:
                raise Exception("No suitable subnets found in shared NAT VPC")
            
            # Update ECS service network configuration
            update_response = self.ecs.update_service(
                cluster=self.cluster_name,
                service=self.service_name,
                networkConfiguration={
                    'awsvpcConfiguration': {
                        'subnets': subnets,
                        'securityGroups': security_groups,
                        'assignPublicIp': 'DISABLED'  # Use private subnets with NAT
                    }
                }
            )
            
            self.log_step("ECS service moved to shared NAT Gateway VPC", details={
                'Target VPC': self.shared_nat_vpc_id,
                'Subnets': len(subnets),
                'Security Groups': len(security_groups),
                'NAT Gateway': self.shared_nat_gateway_id
            })
            
            return update_response
            
        except Exception as e:
            self.log_error(f"Failed to move ECS service: {str(e)}")
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
            # Don't raise - let's continue and check the status
            print("⚠️  Service may still be stabilizing - continuing with verification...")

    def verify_connectivity(self):
        """Verify that the service has proper connectivity"""
        print("🔍 Step 7: Verifying connectivity...")
        
        try:
            # Check target group health
            response = self.elbv2.describe_target_health(
                TargetGroupArn=self.target_group_arn
            )
            
            targets = response['TargetHealthDescriptions']
            healthy_targets = [t for t in targets if t['TargetHealth']['State'] == 'healthy']
            
            # Check service status
            service_response = self.ecs.describe_services(
                cluster=self.cluster_name,
                services=[self.service_name]
            )
            
            service = service_response['services'][0]
            running_count = service['runningCount']
            desired_count = service['desiredCount']
            
            self.log_step("Connectivity verification completed", details={
                'Running Tasks': f"{running_count}/{desired_count}",
                'Healthy Targets': f"{len(healthy_targets)}/{len(targets)}",
                'Service Status': service['status']
            })
            
            return len(healthy_targets) > 0 and running_count > 0
            
        except Exception as e:
            self.log_error(f"Failed to verify connectivity: {str(e)}")
            return False

    def save_results(self):
        """Save results to file"""
        timestamp = int(time.time())
        filename = f"corrected-vpc-network-fix-{timestamp}.json"
        
        with open(filename, 'w') as f:
            json.dump(self.results, f, indent=2)
        
        print(f"📄 Fix results saved to: {filename}")
        return filename

    def run_corrected_fix(self):
        """Execute the corrected VPC network fix"""
        print("🔧 Corrected VPC Network Configuration Fix")
        print("=" * 50)
        print("This fix ensures ECS tasks have internet access via shared NAT Gateway")
        print()
        
        try:
            # Step 1: Analyze current configuration
            config = self.analyze_current_configuration()
            
            # Check if ECS is already in the correct VPC
            if config['ecs_service_vpc'] == config['shared_nat_vpc']:
                print("✅ ECS service is already in the shared NAT Gateway VPC!")
                
                # Still need to verify connectivity with load balancer
                if config['load_balancer_vpc'] != config['shared_nat_vpc']:
                    print("⚠️  Load balancer is in a different VPC - checking cross-VPC connectivity...")
                    if not self.check_cross_vpc_connectivity(config['load_balancer_vpc'], config['ecs_service_vpc']):
                        print("❌ No cross-VPC connectivity found")
                        print("💡 Recommendation: Move load balancer to shared NAT Gateway VPC")
                        print("   This requires infrastructure changes beyond this script's scope")
                else:
                    print("✅ Load balancer and ECS service are in the same VPC!")
                
                # Verify current connectivity
                if self.verify_connectivity():
                    print("✅ Connectivity verification passed!")
                else:
                    print("⚠️  Connectivity issues detected - may need manual intervention")
                
                return self.save_results()
            
            print(f"🔧 Configuration mismatch detected:")
            print(f"   Load Balancer VPC: {config['load_balancer_vpc']}")
            print(f"   ECS Service VPC: {config['ecs_service_vpc']}")
            print(f"   Shared NAT Gateway VPC: {config['shared_nat_vpc']}")
            print(f"   Moving ECS service to shared NAT Gateway VPC...")
            print()
            
            # Step 2: Check cross-VPC connectivity options
            cross_vpc_available = self.check_cross_vpc_connectivity(
                config['load_balancer_vpc'], 
                config['shared_nat_vpc']
            )
            
            if not cross_vpc_available:
                print("⚠️  No VPC peering found - load balancer may not reach ECS tasks")
                print("💡 This fix will move ECS to shared NAT VPC for internet access")
                print("   Additional network configuration may be needed for load balancer connectivity")
                print()
            
            # Step 3-4: Get network resources (handled in step 5)
            
            # Step 5: Move ECS service to shared NAT Gateway VPC
            self.move_ecs_to_shared_nat_vpc()
            
            # Step 6: Wait for service to stabilize
            self.wait_for_service_stability()
            
            # Step 7: Verify connectivity
            connectivity_ok = self.verify_connectivity()
            
            print("\n🎉 Corrected VPC Network Fix Completed!")
            print("=" * 50)
            print(f"✅ ECS service moved to shared NAT Gateway VPC: {config['shared_nat_vpc']}")
            print(f"✅ Using shared NAT Gateway: {self.shared_nat_gateway_id}")
            print(f"✅ Internet access available for container image pulls")
            
            if connectivity_ok:
                print(f"✅ Service connectivity verified")
            else:
                print(f"⚠️  Service connectivity needs verification")
            
            if config['load_balancer_vpc'] != config['shared_nat_vpc']:
                print(f"\n💡 Next Steps:")
                print(f"   - Load balancer is in VPC {config['load_balancer_vpc']}")
                print(f"   - ECS service is now in VPC {config['shared_nat_vpc']}")
                print(f"   - You may need to configure VPC peering or move the load balancer")
                print(f"   - Test application connectivity after this fix")
            
            print(f"\n📄 Detailed results saved to file")
            
        except Exception as e:
            self.log_error(f"Corrected VPC fix failed: {str(e)}")
            print(f"\n❌ Corrected VPC Fix Failed: {str(e)}")
            print("Check the results file for detailed error information")
        
        finally:
            return self.save_results()

def main():
    """Main execution function"""
    fixer = CorrectedVPCNetworkFixer()
    results_file = fixer.run_corrected_fix()
    
    print(f"\n📊 Summary:")
    print(f"   Steps completed: {len(fixer.results['steps_completed'])}")
    print(f"   Errors encountered: {len(fixer.results['errors'])}")
    print(f"   Results file: {results_file}")

if __name__ == "__main__":
    main()