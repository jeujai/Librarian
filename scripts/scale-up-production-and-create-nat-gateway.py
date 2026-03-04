#!/usr/bin/env python3
"""
Scale Up Production Service and Create NAT Gateway

This script:
1. Scales up the multimodal-lib-prod-service to 1 instance
2. Creates a single NAT Gateway in one of the production VPC subnets
3. Monitors the service startup and health
"""

import boto3
import json
import time
from typing import Dict, List, Any
from datetime import datetime

class ProductionScaleUpManager:
    """Manage scaling up production service and NAT Gateway creation."""
    
    def __init__(self):
        self.session = boto3.Session()
        self.cluster_name = "multimodal-lib-prod-cluster"
        self.service_name = "multimodal-lib-prod-service"
        self.prod_vpc_id = "vpc-0b2186b38779e77f6"  # multimodal-lib-prod-vpc
        
    def scale_up_and_create_nat_gateway(self) -> Dict[str, Any]:
        """Scale up production service and create NAT Gateway."""
        
        results = {
            'service_scaling': {},
            'nat_gateway_creation': {},
            'monitoring': {},
            'summary': {}
        }
        
        try:
            print("🚀 Scaling Up Production Service and Creating NAT Gateway")
            print("=" * 70)
            
            # Step 1: Scale up the production service
            results['service_scaling'] = self._scale_up_service()
            
            # Step 2: Create NAT Gateway
            results['nat_gateway_creation'] = self._create_nat_gateway()
            
            # Step 3: Monitor service startup
            results['monitoring'] = self._monitor_service_startup()
            
            # Step 4: Generate summary
            results['summary'] = self._generate_summary(results)
            
            self._print_results(results)
            
        except Exception as e:
            print(f"❌ Error during scale-up: {e}")
            results['error'] = str(e)
        
        return results
    
    def _scale_up_service(self) -> Dict[str, Any]:
        """Scale up the production service to 1 instance."""
        
        scaling_result = {
            'success': False,
            'previous_desired_count': 0,
            'new_desired_count': 1,
            'response': {}
        }
        
        try:
            ecs = self.session.client('ecs', region_name='us-east-1')
            
            print("📈 Scaling up production service...")
            
            # Get current service status
            service_response = ecs.describe_services(
                cluster=self.cluster_name,
                services=[self.service_name]
            )
            
            if service_response['services']:
                service = service_response['services'][0]
                scaling_result['previous_desired_count'] = service['desiredCount']
                
                print(f"   Current desired count: {service['desiredCount']}")
                print(f"   Current running count: {service['runningCount']}")
            
            # Scale up to 1 instance
            update_response = ecs.update_service(
                cluster=self.cluster_name,
                service=self.service_name,
                desiredCount=1
            )
            
            scaling_result['response'] = {
                'service_name': update_response['service']['serviceName'],
                'desired_count': update_response['service']['desiredCount'],
                'running_count': update_response['service']['runningCount'],
                'pending_count': update_response['service']['pendingCount'],
                'status': update_response['service']['status']
            }
            
            scaling_result['success'] = True
            
            print(f"✅ Service scaled up successfully!")
            print(f"   New desired count: {update_response['service']['desiredCount']}")
            print(f"   Status: {update_response['service']['status']}")
            
        except Exception as e:
            print(f"❌ Error scaling up service: {e}")
            scaling_result['error'] = str(e)
        
        return scaling_result
    
    def _create_nat_gateway(self) -> Dict[str, Any]:
        """Create a single NAT Gateway in the production VPC."""
        
        nat_result = {
            'success': False,
            'nat_gateway_id': None,
            'subnet_id': None,
            'allocation_id': None
        }
        
        try:
            ec2 = self.session.client('ec2', region_name='us-east-1')
            
            print("\n🌐 Creating NAT Gateway...")
            
            # Find public subnets in the production VPC
            subnets_response = ec2.describe_subnets(
                Filters=[
                    {'Name': 'vpc-id', 'Values': [self.prod_vpc_id]},
                    {'Name': 'tag:Name', 'Values': ['*public*']}
                ]
            )
            
            if not subnets_response['Subnets']:
                # Try finding subnets by route table (public subnets have IGW routes)
                subnets_response = ec2.describe_subnets(
                    Filters=[{'Name': 'vpc-id', 'Values': [self.prod_vpc_id]}]
                )
                
                # Find public subnet by checking route tables
                public_subnet = None
                for subnet in subnets_response['Subnets']:
                    # Check if subnet has route to internet gateway
                    route_tables = ec2.describe_route_tables(
                        Filters=[
                            {'Name': 'association.subnet-id', 'Values': [subnet['SubnetId']]}
                        ]
                    )
                    
                    for rt in route_tables['RouteTables']:
                        for route in rt['Routes']:
                            if route.get('GatewayId', '').startswith('igw-'):
                                public_subnet = subnet
                                break
                        if public_subnet:
                            break
                    if public_subnet:
                        break
                
                if not public_subnet:
                    # Use first available subnet
                    public_subnet = subnets_response['Subnets'][0]
            else:
                public_subnet = subnets_response['Subnets'][0]
            
            subnet_id = public_subnet['SubnetId']
            print(f"   Using subnet: {subnet_id}")
            
            # Allocate Elastic IP for NAT Gateway
            eip_response = ec2.allocate_address(Domain='vpc')
            allocation_id = eip_response['AllocationId']
            
            print(f"   Allocated Elastic IP: {eip_response['PublicIp']} ({allocation_id})")
            
            # Create NAT Gateway
            nat_response = ec2.create_nat_gateway(
                SubnetId=subnet_id,
                AllocationId=allocation_id,
                TagSpecifications=[
                    {
                        'ResourceType': 'nat-gateway',
                        'Tags': [
                            {'Key': 'Name', 'Value': 'multimodal-lib-prod-nat-gateway'},
                            {'Key': 'Project', 'Value': 'multimodal-lib'},
                            {'Key': 'Environment', 'Value': 'prod'},
                            {'Key': 'ManagedBy', 'Value': 'kiro-agent'},
                            {'Key': 'CostCenter', 'Value': 'engineering'}
                        ]
                    }
                ]
            )
            
            nat_gateway_id = nat_response['NatGateway']['NatGatewayId']
            
            nat_result.update({
                'success': True,
                'nat_gateway_id': nat_gateway_id,
                'subnet_id': subnet_id,
                'allocation_id': allocation_id,
                'public_ip': eip_response['PublicIp'],
                'state': nat_response['NatGateway']['State']
            })
            
            print(f"✅ NAT Gateway created successfully!")
            print(f"   NAT Gateway ID: {nat_gateway_id}")
            print(f"   State: {nat_response['NatGateway']['State']}")
            print(f"   Public IP: {eip_response['PublicIp']}")
            
        except Exception as e:
            print(f"❌ Error creating NAT Gateway: {e}")
            nat_result['error'] = str(e)
        
        return nat_result
    
    def _monitor_service_startup(self) -> Dict[str, Any]:
        """Monitor the service startup process."""
        
        monitoring_result = {
            'startup_successful': False,
            'monitoring_duration': 0,
            'final_status': {},
            'events': []
        }
        
        try:
            ecs = self.session.client('ecs', region_name='us-east-1')
            
            print(f"\n👀 Monitoring service startup (up to 5 minutes)...")
            
            start_time = time.time()
            max_wait_time = 300  # 5 minutes
            
            while time.time() - start_time < max_wait_time:
                # Check service status
                service_response = ecs.describe_services(
                    cluster=self.cluster_name,
                    services=[self.service_name]
                )
                
                if service_response['services']:
                    service = service_response['services'][0]
                    
                    running_count = service['runningCount']
                    desired_count = service['desiredCount']
                    pending_count = service['pendingCount']
                    
                    print(f"   Status: {running_count}/{desired_count} running, {pending_count} pending")
                    
                    # Check recent events
                    recent_events = service.get('events', [])[:3]
                    for event in recent_events:
                        event_time = event['createdAt']
                        if (datetime.now(event_time.tzinfo) - event_time).total_seconds() < 60:
                            print(f"   Event: {event['message']}")
                            monitoring_result['events'].append({
                                'time': event_time.isoformat(),
                                'message': event['message']
                            })
                    
                    # Check if service is running
                    if running_count >= desired_count and desired_count > 0:
                        monitoring_result['startup_successful'] = True
                        monitoring_result['final_status'] = {
                            'running_count': running_count,
                            'desired_count': desired_count,
                            'pending_count': pending_count,
                            'status': service['status']
                        }
                        print(f"✅ Service startup successful!")
                        break
                
                time.sleep(30)  # Wait 30 seconds before next check
            
            monitoring_result['monitoring_duration'] = time.time() - start_time
            
            if not monitoring_result['startup_successful']:
                print(f"⚠️  Service startup still in progress after {monitoring_result['monitoring_duration']:.1f} seconds")
                
                # Get final status
                service_response = ecs.describe_services(
                    cluster=self.cluster_name,
                    services=[self.service_name]
                )
                
                if service_response['services']:
                    service = service_response['services'][0]
                    monitoring_result['final_status'] = {
                        'running_count': service['runningCount'],
                        'desired_count': service['desiredCount'],
                        'pending_count': service['pendingCount'],
                        'status': service['status']
                    }
            
        except Exception as e:
            print(f"❌ Error monitoring service: {e}")
            monitoring_result['error'] = str(e)
        
        return monitoring_result
    
    def _generate_summary(self, results: Dict[str, Any]) -> Dict[str, Any]:
        """Generate summary of operations."""
        
        summary = {
            'service_scaling_success': results['service_scaling'].get('success', False),
            'nat_gateway_creation_success': results['nat_gateway_creation'].get('success', False),
            'service_startup_success': results['monitoring'].get('startup_successful', False),
            'cost_impact': {},
            'next_steps': []
        }
        
        # Calculate cost impact
        if results['nat_gateway_creation'].get('success'):
            summary['cost_impact'] = {
                'nat_gateway_monthly': 45.60,  # $0.045/hour * 24 * 30
                'data_processing': 'Variable based on usage',
                'elastic_ip': 0,  # Free when attached to running resource
                'total_estimated_monthly': 45.60
            }
        
        # Generate next steps
        if summary['service_scaling_success']:
            summary['next_steps'].append("✅ Service scaled up successfully")
        else:
            summary['next_steps'].append("❌ Service scaling failed - investigate issues")
        
        if summary['nat_gateway_creation_success']:
            summary['next_steps'].append("✅ NAT Gateway created for outbound connectivity")
        else:
            summary['next_steps'].append("❌ NAT Gateway creation failed - check permissions")
        
        if summary['service_startup_success']:
            summary['next_steps'].append("✅ Service is running - ready for end-to-end testing")
        else:
            summary['next_steps'].append("⚠️  Service startup in progress - monitor CloudWatch logs")
        
        summary['next_steps'].extend([
            "🔍 Run end-to-end tests to validate functionality",
            "📊 Monitor service health and performance",
            "💰 Track costs and optimize as needed"
        ])
        
        return summary
    
    def _print_results(self, results: Dict[str, Any]):
        """Print formatted results."""
        
        summary = results['summary']
        
        print(f"\n📊 OPERATION SUMMARY")
        print("=" * 40)
        
        print(f"Service Scaling: {'✅ Success' if summary['service_scaling_success'] else '❌ Failed'}")
        print(f"NAT Gateway: {'✅ Created' if summary['nat_gateway_creation_success'] else '❌ Failed'}")
        print(f"Service Startup: {'✅ Running' if summary['service_startup_success'] else '⚠️  In Progress'}")
        
        if summary.get('cost_impact'):
            cost = summary['cost_impact']
            print(f"\n💰 Cost Impact:")
            print(f"   NAT Gateway: ${cost['nat_gateway_monthly']:.2f}/month")
            print(f"   Data Processing: {cost['data_processing']}")
            print(f"   Total Estimated: ${cost['total_estimated_monthly']:.2f}/month")
        
        print(f"\n🎯 Next Steps:")
        for step in summary['next_steps']:
            print(f"   {step}")

def main():
    """Main execution function."""
    
    manager = ProductionScaleUpManager()
    
    try:
        results = manager.scale_up_and_create_nat_gateway()
        
        # Save detailed results
        timestamp = int(time.time())
        results_file = f"production-scale-up-{timestamp}.json"
        
        with open(results_file, 'w') as f:
            json.dump(results, f, indent=2, default=str)
        
        print(f"\n📄 Detailed results saved to: {results_file}")
        
        # Return appropriate exit code
        summary = results.get('summary', {})
        if summary.get('service_scaling_success') and summary.get('nat_gateway_creation_success'):
            print("\n✅ Production scale-up completed successfully")
            return 0
        else:
            print("\n⚠️  Production scale-up completed with issues")
            return 1
        
    except Exception as e:
        print(f"❌ Production scale-up failed: {e}")
        return 1

if __name__ == "__main__":
    exit(main())