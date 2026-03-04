#!/usr/bin/env python3
"""
Cleanup Remaining Elastic IPs
Handles the Elastic IPs that need allocation IDs for proper release
"""

import boto3
import json
from datetime import datetime
from botocore.exceptions import ClientError

def cleanup_elastic_ips_with_allocation_ids():
    """Release unattached Elastic IPs using allocation IDs"""
    print("🔧 CLEANING UP REMAINING ELASTIC IPS")
    print("=" * 50)
    
    ec2 = boto3.client('ec2', region_name='us-east-1')
    results = []
    
    try:
        # Get all Elastic IPs with their allocation IDs
        response = ec2.describe_addresses()
        
        target_ips = ['3.233.193.206', '52.202.142.217']
        
        for address in response['Addresses']:
            public_ip = address['PublicIp']
            
            if public_ip in target_ips:
                # Check if it's unattached
                if 'InstanceId' not in address and 'NetworkInterfaceId' not in address:
                    allocation_id = address.get('AllocationId')
                    
                    if allocation_id:
                        try:
                            print(f"Releasing Elastic IP: {public_ip} (allocation: {allocation_id})")
                            ec2.release_address(AllocationId=allocation_id)
                            results.append({
                                "ip": public_ip,
                                "allocation_id": allocation_id,
                                "status": "released",
                                "savings": 3.65
                            })
                        except ClientError as e:
                            results.append({
                                "ip": public_ip,
                                "allocation_id": allocation_id,
                                "status": "error",
                                "error": str(e)
                            })
                    else:
                        # Classic Elastic IP (EC2-Classic)
                        try:
                            print(f"Releasing Classic Elastic IP: {public_ip}")
                            ec2.release_address(PublicIp=public_ip)
                            results.append({
                                "ip": public_ip,
                                "type": "classic",
                                "status": "released",
                                "savings": 3.65
                            })
                        except ClientError as e:
                            results.append({
                                "ip": public_ip,
                                "type": "classic",
                                "status": "error",
                                "error": str(e)
                            })
                else:
                    attachment = address.get('InstanceId', address.get('NetworkInterfaceId', 'unknown'))
                    results.append({
                        "ip": public_ip,
                        "status": "attached",
                        "attachment": attachment
                    })
    
    except ClientError as e:
        print(f"Error listing Elastic IPs: {e}")
        return []
    
    # Calculate savings
    total_savings = sum(r.get('savings', 0) for r in results if r['status'] == 'released')
    
    print("\n" + "=" * 50)
    print("📊 ELASTIC IP CLEANUP RESULTS")
    print("=" * 50)
    
    for result in results:
        if result['status'] == 'released':
            print(f"✅ Released: {result['ip']} - ${result['savings']}/month savings")
        elif result['status'] == 'attached':
            print(f"⏭️  Skipped: {result['ip']} - attached to {result['attachment']}")
        elif result['status'] == 'error':
            print(f"❌ Error: {result['ip']} - {result.get('error', 'unknown error')}")
    
    print(f"\n💰 Total Monthly Savings: ${total_savings:.2f}")
    print(f"💰 Total Annual Savings: ${total_savings * 12:.2f}")
    
    # Save results
    timestamp = int(datetime.now().timestamp())
    filename = f"elastic-ip-cleanup-{timestamp}.json"
    
    with open(filename, 'w') as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "total_monthly_savings": total_savings,
            "total_annual_savings": total_savings * 12,
            "results": results
        }, f, indent=2)
    
    print(f"📄 Detailed Report: {filename}")
    
    return results

if __name__ == "__main__":
    cleanup_elastic_ips_with_allocation_ids()