#!/usr/bin/env python3
"""
Get HTTPS Endpoint

Retrieves the HTTPS endpoint URL for the application.
"""

import boto3
import json

def get_https_endpoint():
    """Get the HTTPS endpoint for the application."""
    
    print("🔍 Finding HTTPS Endpoint")
    print("=" * 60)
    
    elbv2 = boto3.client('elbv2', region_name='us-east-1')
    
    try:
        # List all load balancers
        response = elbv2.describe_load_balancers()
        
        print(f"\n📋 Found {len(response['LoadBalancers'])} load balancer(s):\n")
        
        https_endpoints = []
        
        for lb in response['LoadBalancers']:
            lb_name = lb['LoadBalancerName']
            lb_dns = lb['DNSName']
            lb_scheme = lb['Scheme']
            lb_type = lb['Type']
            
            print(f"Load Balancer: {lb_name}")
            print(f"  Type: {lb_type}")
            print(f"  Scheme: {lb_scheme}")
            print(f"  DNS: {lb_dns}")
            
            # Get listeners
            listeners_response = elbv2.describe_listeners(
                LoadBalancerArn=lb['LoadBalancerArn']
            )
            
            has_https = False
            has_http = False
            
            for listener in listeners_response['Listeners']:
                protocol = listener['Protocol']
                port = listener['Port']
                print(f"  Listener: {protocol}:{port}")
                
                if protocol == 'HTTPS':
                    has_https = True
                    https_url = f"https://{lb_dns}"
                    https_endpoints.append({
                        'name': lb_name,
                        'url': https_url,
                        'type': lb_type,
                        'scheme': lb_scheme
                    })
                elif protocol == 'HTTP':
                    has_http = True
            
            if has_https:
                print(f"  ✅ HTTPS Endpoint: https://{lb_dns}")
            elif has_http:
                print(f"  ⚠️  HTTP Only: http://{lb_dns}")
            
            print()
        
        # Summary
        if https_endpoints:
            print("\n🎉 HTTPS Endpoints Available:")
            print("=" * 60)
            for endpoint in https_endpoints:
                print(f"\n{endpoint['name']}:")
                print(f"  URL: {endpoint['url']}")
                print(f"  Type: {endpoint['type']}")
                print(f"  Scheme: {endpoint['scheme']}")
        else:
            print("\n⚠️  No HTTPS endpoints found")
            print("The application may only be accessible via HTTP")
        
        return https_endpoints
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return []

if __name__ == "__main__":
    get_https_endpoint()
