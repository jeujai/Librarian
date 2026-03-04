#!/usr/bin/env python3
"""
Get the production load balancer URL for testing.
"""

import boto3
import json
import sys

def get_production_url():
    """Get the production load balancer URL."""
    
    try:
        # Initialize ELB client
        elb_client = boto3.client('elbv2', region_name='us-east-1')
        
        # Get load balancers
        response = elb_client.describe_load_balancers()
        
        # Find the multimodal librarian load balancer
        for lb in response['LoadBalancers']:
            lb_name = lb.get('LoadBalancerName', '')
            if 'multimodal' in lb_name.lower() or 'lib' in lb_name.lower():
                dns_name = lb['DNSName']
                scheme = lb['Scheme']
                state = lb['State']['Code']
                
                print(f"Found Load Balancer: {lb_name}")
                print(f"DNS Name: {dns_name}")
                print(f"Scheme: {scheme}")
                print(f"State: {state}")
                
                # Construct URL
                protocol = 'https' if scheme == 'internet-facing' else 'http'
                url = f"{protocol}://{dns_name}"
                
                print(f"Production URL: {url}")
                
                return {
                    'url': url,
                    'dns_name': dns_name,
                    'load_balancer_name': lb_name,
                    'scheme': scheme,
                    'state': state
                }
        
        print("No multimodal librarian load balancer found")
        return None
        
    except Exception as e:
        print(f"Error getting production URL: {e}")
        return None

if __name__ == "__main__":
    result = get_production_url()
    if result:
        sys.exit(0)
    else:
        sys.exit(1)