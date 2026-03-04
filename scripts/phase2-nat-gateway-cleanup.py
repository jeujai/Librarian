#!/usr/bin/env python3
"""
Phase 2: NAT Gateway Cleanup - Highest cost savings.

This script deletes NAT Gateways which are the highest cost items.
Each NAT Gateway costs ~$45/month, so deleting 4-5 saves ~$180-225/month.

WARNING: This action is not easily reversible. NAT Gateways would need to be recreated.
"""

import boto3
import sys
import time

def cleanup_nat_gateways():
    """Delete NAT Gateways for maximum cost savings."""
    
    print("🌐 Phase 2: NAT Gateway Cleanup (High Cost Savings)")
    print("=" * 55)
    print("WARNING: This deletes NAT Gateways - not easily reversible")
    print("Estimated savings: ~$225/month")
    print()
    
    # Initialize AWS client
    session = boto3.Session()
    ec2 = session.client('ec2', region_name='us-east-1')
    
    # NAT Gateways found in scan
    nat_gateways_to_delete = [
        "nat-0922d45658199821b",  # multimodal-lib-prod-nat-gateway-3
        "nat-08dd08fa1b4ab6083",  # multimodal-lib-prod-nat-gateway-1  
        "nat-0ba6c7fb864e0b7b7",  # multimodal-lib-prod-nat-gateway-2
        "nat-0de7c20c01213cedb",  # MultimodalLibrarianFullML NAT Gateway
        # Note: Skipping nat-0e52e9a066891174e (CollaborativeEditor - different project)
    ]
    
    actions_completed = []
    
    print("🔍 Checking NAT Gateway status...")
    
    for nat_gw_id in nat_gateways_to_delete:
        try:
            # Check current status
            response = ec2.describe_nat_gateways(NatGatewayIds=[nat_gw_id])
            
            if response['NatGateways']:
                nat_gw = response['NatGateways'][0]
                state = nat_gw.get('State')
                vpc_id = nat_gw.get('VpcId')
                
                # Get tags for identification
                tags = {tag['Key']: tag['Value'] for tag in nat_gw.get('Tags', [])}
                name = tags.get('Name', 'Unknown')
                
                print(f"\n🌐 NAT Gateway: {nat_gw_id}")
                print(f"   Name: {name}")
                print(f"   State: {state}")
                print(f"   VPC: {vpc_id}")
                print(f"   Monthly cost: ~$45")
                
                if state == 'available':
                    print(f"   ⚠️  Ready for deletion")
                    
                    # Confirm deletion
                    print(f"   🗑️  Deleting NAT Gateway...")
                    
                    try:
                        ec2.delete_nat_gateway(NatGatewayId=nat_gw_id)
                        print(f"   ✅ Deletion initiated for {nat_gw_id}")
                        print(f"   💰 Will save ~$45/month")
                        actions_completed.append(f"Deleted NAT Gateway: {nat_gw_id} ({name})")
                        
                    except Exception as delete_error:
                        print(f"   ❌ Deletion failed: {delete_error}")
                        
                elif state in ['deleting', 'deleted']:
                    print(f"   ✅ Already being deleted or deleted")
                else:
                    print(f"   ℹ️  State: {state} - skipping")
            else:
                print(f"   ℹ️  NAT Gateway {nat_gw_id} not found (may already be deleted)")
                
        except Exception as e:
            print(f"   ❌ Error checking {nat_gw_id}: {e}")
    
    # Summary
    print(f"\n📊 Phase 2 Complete!")
    print(f"NAT Gateways processed: {len(actions_completed)}")
    
    for action in actions_completed:
        print(f"   ✅ {action}")
    
    if actions_completed:
        estimated_savings = len(actions_completed) * 45
        print(f"\n💰 Estimated monthly savings: ~${estimated_savings}")
        print(f"💰 Estimated annual savings: ~${estimated_savings * 12}")
        print(f"⏰ Deletion takes a few minutes to complete")
        print(f"🔄 NAT Gateways can be recreated if needed (but will incur costs again)")
    else:
        print(f"\n✅ No NAT Gateways needed deletion")
    
    return len(actions_completed)


def main():
    """Main execution with safety confirmation."""
    
    print("🧹 Multimodal Librarian - Phase 2 NAT Gateway Cleanup")
    print()
    
    # Safety confirmation
    print("⚠️  WARNING: This will delete NAT Gateways")
    print("   • Each NAT Gateway costs ~$45/month")
    print("   • Deletion is not easily reversible")
    print("   • NAT Gateways provide outbound internet access for private subnets")
    print("   • Only proceed if you're sure they're not needed")
    print()
    
    response = input("Do you want to proceed with NAT Gateway deletion? (type 'DELETE' to confirm): ")
    
    if response != 'DELETE':
        print("❌ Aborted - NAT Gateways not deleted")
        print("💡 You can run this script again when ready")
        return 0
    
    try:
        actions_count = cleanup_nat_gateways()
        
        if actions_count > 0:
            print(f"\n🎉 Successfully initiated deletion of {actions_count} NAT Gateways!")
            print(f"💰 This will save ~${actions_count * 45}/month")
            print(f"⏰ Check AWS console in a few minutes to confirm deletion")
        
        return 0
        
    except Exception as e:
        print(f"❌ Error during NAT Gateway cleanup: {e}")
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)