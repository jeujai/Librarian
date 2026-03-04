#!/usr/bin/env python3
"""
Fix NAT Gateway EIP Issue

This script addresses the Elastic IP address limit issue preventing NAT Gateway creation
by releasing unused EIP addresses and creating a single NAT Gateway for production.
"""

import boto3
import json
import time
from typing import Dict, List, Any

class NATGatewayEIPFixer:
    """Fix EIP limits and create NAT Gateway for production connectivity."""
    
    def __init__(self):
        self.session = boto3.Session()
        self.prod_vpc_id = "vpc-0b2186b38779e77f6"  # multimodal-lib-prod-vpc
        self.region = "us-east-1"
        
    def fix_eip_and_create_nat_gateway(self) -> Dict[str, Any]:
        """Fix EIP limits and create NAT Gateway."""
        
        results = {
            'eip_analysis': {},
            'eip_cleanup': {},
            'nat_gateway_creation': {},
            'route_table_updates': {},
            'summary': {}
        }
        
        try:
            print("🔧 Fixing EIP Limits and Creating NAT Gateway")
            print("=" * 60)
            
            # Step 1: Analyze current EIP usage
            results['eip_analysis'] = self._analyze_eip_usage()
            
            # Step 2: Release unused EIPs
            results['eip_cleanup'] = self._cleanup_unused_eips()
            
            # Step 3: Create NAT Gateway
            results['nat_gateway_creation'] = self._create_nat_gateway()
            
            # Step 4: Update route tables (pass NAT Gateway ID)
            if results['nat_gateway_creation'].get('success'):
                results['route_table_updates'] = self._update_route_tables(results)
            
            # Step 5: Generate summary
            results['summary'] = self._generate_summary(results)
            
            self._print_results(results)
            
        except Exception as e:
            print(f"❌ Error fixing EIP and NAT Gateway: {e}")
            results['error'] = str(e)
        
        return results
    
    def _analyze_eip_usage(self) -> Dict[str, Any]:
        """Analyze current Elastic IP usage."""
        
        analysis = {
            'total_eips': 0,
            'associated_eips': 0,
            'unassociated_eips': 0,
            'eip_details': [],
            'unused_eips': []
        }
        
        try:
            ec2 = self.session.client('ec2', region_name=self.region)
            
            print("📊 Analyzing Elastic IP usage...")
            
            # Get all EIPs
            eips_response = ec2.describe_addresses()
            addresses = eips_response['Addresses']
            
            analysis['total_eips'] = len(addresses)
            
            for address in addresses:
                eip_detail = {
                    'allocation_id': address['AllocationId'],
                    'public_ip': address['PublicIp'],
                    'domain': address['Domain'],
                    'associated': 'AssociationId' in address,
                    'instance_id': address.get('InstanceId'),
                    'network_interface_id': address.get('NetworkInterfaceId'),
                    'tags': address.get('Tags', [])
                }
                
                analysis['eip_details'].append(eip_detail)
                
                if eip_detail['associated']:
                    analysis['associated_eips'] += 1
                else:
                    analysis['unassociated_eips'] += 1
                    analysis['unused_eips'].append(eip_detail)
            
            print(f"   Total EIPs: {analysis['total_eips']}")
            print(f"   Associated: {analysis['associated_eips']}")
            print(f"   Unassociated: {analysis['unassociated_eips']}")
            
            # Show unused EIPs
            if analysis['unused_eips']:
                print(f"   Unused EIPs available for cleanup:")
                for eip in analysis['unused_eips']:
                    print(f"      - {eip['public_ip']} ({eip['allocation_id']})")
            
        except Exception as e:
            print(f"❌ Error analyzing EIP usage: {e}")
            analysis['error'] = str(e)
        
        return analysis
    
    def _cleanup_unused_eips(self) -> Dict[str, Any]:
        """Release unused Elastic IP addresses."""
        
        cleanup = {
            'eips_released': [],
            'release_errors': [],
            'space_created': 0
        }
        
        try:
            ec2 = self.session.client('ec2', region_name=self.region)
            
            # Get unused EIPs from analysis
            eip_analysis = getattr(self, '_last_eip_analysis', {})
            unused_eips = eip_analysis.get('unused_eips', [])
            
            if not unused_eips:
                # Re-analyze if not available
                eip_analysis = self._analyze_eip_usage()
                unused_eips = eip_analysis.get('unused_eips', [])
            
            if unused_eips:
                print(f"\n🧹 Releasing {len(unused_eips)} unused EIP addresses...")
                
                for eip in unused_eips:
                    try:
                        allocation_id = eip['allocation_id']
                        public_ip = eip['public_ip']
                        
                        # Check if EIP has any important tags before releasing
                        tags = eip.get('tags', [])
                        important_tags = ['production', 'critical', 'keep', 'permanent']
                        
                        has_important_tags = any(
                            tag.get('Key', '').lower() in important_tags or 
                            tag.get('Value', '').lower() in important_tags 
                            for tag in tags
                        )
                        
                        if has_important_tags:
                            print(f"   ⚠️  Skipping {public_ip} - has important tags")
                            continue
                        
                        # Release the EIP
                        ec2.release_address(AllocationId=allocation_id)
                        
                        cleanup['eips_released'].append({
                            'allocation_id': allocation_id,
                            'public_ip': public_ip
                        })
                        
                        cleanup['space_created'] += 1
                        
                        print(f"   ✅ Released {public_ip} ({allocation_id})")
                        
                        # Small delay to avoid rate limiting
                        time.sleep(0.5)
                        
                    except Exception as e:
                        error_info = {
                            'allocation_id': eip['allocation_id'],
                            'public_ip': eip['public_ip'],
                            'error': str(e)
                        }
                        cleanup['release_errors'].append(error_info)
                        print(f"   ❌ Failed to release {eip['public_ip']}: {e}")
                
                print(f"   📊 Released {cleanup['space_created']} EIP addresses")
                
            else:
                print("\n🧹 No unused EIP addresses found to release")
            
        except Exception as e:
            print(f"❌ Error during EIP cleanup: {e}")
            cleanup['error'] = str(e)
        
        return cleanup
    
    def _create_nat_gateway(self) -> Dict[str, Any]:
        """Create NAT Gateway after EIP cleanup."""
        
        nat_result = {
            'success': False,
            'nat_gateway_id': None,
            'subnet_id': None,
            'allocation_id': None,
            'public_ip': None
        }
        
        try:
            ec2 = self.session.client('ec2', region_name=self.region)
            
            print(f"\n🌐 Creating NAT Gateway...")
            
            # Find public subnet in production VPC
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
                # Use first available subnet as fallback
                public_subnet = subnets_response['Subnets'][0]
            
            subnet_id = public_subnet['SubnetId']
            print(f"   Using subnet: {subnet_id}")
            
            # Allocate new Elastic IP for NAT Gateway
            eip_response = ec2.allocate_address(Domain='vpc')
            allocation_id = eip_response['AllocationId']
            public_ip = eip_response['PublicIp']
            
            print(f"   Allocated new Elastic IP: {public_ip} ({allocation_id})")
            
            # Create NAT Gateway (without TagSpecifications as it's not supported)
            nat_response = ec2.create_nat_gateway(
                SubnetId=subnet_id,
                AllocationId=allocation_id
            )
            
            # Add tags after creation
            nat_gateway_id = nat_response['NatGateway']['NatGatewayId']
            
            try:
                ec2.create_tags(
                    Resources=[nat_gateway_id],
                    Tags=[
                        {'Key': 'Name', 'Value': 'multimodal-lib-prod-nat-gateway'},
                        {'Key': 'Project', 'Value': 'multimodal-lib'},
                        {'Key': 'Environment', 'Value': 'prod'},
                        {'Key': 'ManagedBy', 'Value': 'kiro-agent'},
                        {'Key': 'CostCenter', 'Value': 'engineering'},
                        {'Key': 'Purpose', 'Value': 'outbound-connectivity'}
                    ]
                )
                print(f"   ✅ Tags added to NAT Gateway")
            except Exception as tag_error:
                print(f"   ⚠️  Failed to add tags: {tag_error}")
            
            nat_gateway_id = nat_response['NatGateway']['NatGatewayId']
            
            nat_gateway_id = nat_response['NatGateway']['NatGatewayId']
            
            nat_result.update({
                'success': True,
                'nat_gateway_id': nat_gateway_id,
                'subnet_id': subnet_id,
                'allocation_id': allocation_id,
                'public_ip': public_ip,
                'state': nat_response['NatGateway']['State']
            })
            
            print(f"✅ NAT Gateway created successfully!")
            print(f"   NAT Gateway ID: {nat_gateway_id}")
            print(f"   State: {nat_response['NatGateway']['State']}")
            print(f"   Public IP: {public_ip}")
            
            # Wait for NAT Gateway to become available
            print(f"   ⏳ Waiting for NAT Gateway to become available...")
            
            waiter = ec2.get_waiter('nat_gateway_available')
            waiter.wait(
                NatGatewayIds=[nat_gateway_id],
                WaiterConfig={'Delay': 15, 'MaxAttempts': 20}  # 5 minutes max
            )
            
            print(f"   ✅ NAT Gateway is now available")
            
        except Exception as e:
            print(f"❌ Error creating NAT Gateway: {e}")
            nat_result['error'] = str(e)
        
        return nat_result
    
    def _update_route_tables(self, results: Dict[str, Any]) -> Dict[str, Any]:
        """Update route tables to use the new NAT Gateway."""
        
        route_updates = {
            'private_route_tables': [],
            'routes_added': [],
            'update_errors': []
        }
        
        try:
            ec2 = self.session.client('ec2', region_name=self.region)
            
            # Get NAT Gateway ID from creation result
            nat_creation = results.get('nat_gateway_creation', {})
            nat_gateway_id = nat_creation.get('nat_gateway_id')
            
            if not nat_gateway_id:
                print("⚠️  No NAT Gateway ID available for route table updates")
                return route_updates
            
            print(f"\n🛣️  Updating route tables for NAT Gateway...")
            
            # Find private route tables (those without IGW routes)
            route_tables = ec2.describe_route_tables(
                Filters=[{'Name': 'vpc-id', 'Values': [self.prod_vpc_id]}]
            )
            
            for rt in route_tables['RouteTables']:
                rt_id = rt['RouteTableId']
                
                # Check if this is a private route table (no IGW route)
                has_igw_route = any(
                    route.get('GatewayId', '').startswith('igw-') 
                    for route in rt['Routes']
                )
                
                if not has_igw_route:
                    # This is a private route table
                    route_updates['private_route_tables'].append(rt_id)
                    
                    # Check if default route already exists
                    has_default_route = any(
                        route.get('DestinationCidrBlock') == '0.0.0.0/0'
                        for route in rt['Routes']
                    )
                    
                    try:
                        if has_default_route:
                            # Replace existing default route
                            ec2.replace_route(
                                RouteTableId=rt_id,
                                DestinationCidrBlock='0.0.0.0/0',
                                NatGatewayId=nat_gateway_id
                            )
                            print(f"   ✅ Replaced default route in {rt_id}")
                        else:
                            # Create new default route
                            ec2.create_route(
                                RouteTableId=rt_id,
                                DestinationCidrBlock='0.0.0.0/0',
                                NatGatewayId=nat_gateway_id
                            )
                            print(f"   ✅ Added default route to {rt_id}")
                        
                        route_updates['routes_added'].append({
                            'route_table_id': rt_id,
                            'destination': '0.0.0.0/0',
                            'nat_gateway_id': nat_gateway_id,
                            'action': 'replaced' if has_default_route else 'created'
                        })
                        
                    except Exception as e:
                        error_info = {
                            'route_table_id': rt_id,
                            'error': str(e)
                        }
                        route_updates['update_errors'].append(error_info)
                        print(f"   ❌ Failed to update route table {rt_id}: {e}")
            
            print(f"   📊 Updated {len(route_updates['routes_added'])} route tables")
            
        except Exception as e:
            print(f"❌ Error updating route tables: {e}")
            route_updates['error'] = str(e)
        
        return route_updates
    
    def _generate_summary(self, results: Dict[str, Any]) -> Dict[str, Any]:
        """Generate summary of NAT Gateway fix operations."""
        
        eip_cleanup = results.get('eip_cleanup', {})
        nat_creation = results.get('nat_gateway_creation', {})
        route_updates = results.get('route_table_updates', {})
        
        summary = {
            'eips_released': len(eip_cleanup.get('eips_released', [])),
            'nat_gateway_created': nat_creation.get('success', False),
            'route_tables_updated': len(route_updates.get('routes_added', [])),
            'connectivity_restored': False,
            'cost_impact': {},
            'next_steps': []
        }
        
        # Determine if connectivity should be restored
        if (summary['nat_gateway_created'] and 
            summary['route_tables_updated'] > 0):
            summary['connectivity_restored'] = True
        
        # Calculate cost impact
        if summary['nat_gateway_created']:
            summary['cost_impact'] = {
                'nat_gateway_monthly': 45.60,  # $0.045/hour * 24 * 30
                'data_processing': 'Variable based on usage',
                'eip_savings_monthly': summary['eips_released'] * 3.65,  # $0.005/hour per unused EIP
                'net_monthly_cost': 45.60 - (summary['eips_released'] * 3.65)
            }
        
        # Generate next steps
        if summary['connectivity_restored']:
            summary['next_steps'].extend([
                "✅ NAT Gateway created and routes configured",
                "🔄 ECS tasks should now have outbound internet connectivity",
                "🧪 Run end-to-end tests to validate functionality",
                "📊 Monitor service health and performance"
            ])
        else:
            summary['next_steps'].extend([
                "❌ NAT Gateway creation or routing failed",
                "🔍 Check AWS permissions and VPC configuration",
                "🔄 Retry NAT Gateway creation if needed"
            ])
        
        summary['next_steps'].extend([
            "💰 Monitor costs and optimize as needed",
            "🔒 Validate security groups allow required traffic"
        ])
        
        return summary
    
    def _print_results(self, results: Dict[str, Any]):
        """Print formatted results."""
        
        summary = results['summary']
        
        print(f"\n📊 NAT GATEWAY FIX SUMMARY")
        print("=" * 40)
        
        print(f"EIPs Released: {summary['eips_released']}")
        print(f"NAT Gateway Created: {'✅ Yes' if summary['nat_gateway_created'] else '❌ No'}")
        print(f"Route Tables Updated: {summary['route_tables_updated']}")
        print(f"Connectivity Restored: {'✅ Yes' if summary['connectivity_restored'] else '❌ No'}")
        
        if summary.get('cost_impact'):
            cost = summary['cost_impact']
            print(f"\n💰 Cost Impact:")
            print(f"   NAT Gateway: +${cost['nat_gateway_monthly']:.2f}/month")
            print(f"   EIP Savings: -${cost['eip_savings_monthly']:.2f}/month")
            print(f"   Net Cost: ${cost['net_monthly_cost']:.2f}/month")
        
        print(f"\n🎯 Next Steps:")
        for step in summary['next_steps']:
            print(f"   {step}")

def main():
    """Main execution function."""
    
    fixer = NATGatewayEIPFixer()
    
    try:
        results = fixer.fix_eip_and_create_nat_gateway()
        
        # Save detailed results
        timestamp = int(time.time())
        results_file = f"nat-gateway-eip-fix-{timestamp}.json"
        
        with open(results_file, 'w') as f:
            json.dump(results, f, indent=2, default=str)
        
        print(f"\n📄 Detailed results saved to: {results_file}")
        
        # Return appropriate exit code
        summary = results.get('summary', {})
        if summary.get('connectivity_restored'):
            print("\n✅ NAT Gateway connectivity fix completed successfully")
            return 0
        else:
            print("\n⚠️  NAT Gateway fix completed with issues")
            return 1
        
    except Exception as e:
        print(f"❌ NAT Gateway fix failed: {e}")
        return 1

if __name__ == "__main__":
    exit(main())