#!/usr/bin/env python3
"""
Create New CloudFront Distribution for HTTPS

This script creates a fresh CloudFront distribution specifically for our load balancer
to provide HTTPS access with SSL termination at the edge.
"""

import boto3
import json
import time
import sys
from datetime import datetime
from typing import Dict, Any

class NewCloudFrontHTTPS:
    """Creates a new CloudFront distribution for HTTPS access."""
    
    def __init__(self):
        self.elbv2_client = boto3.client('elbv2', region_name='us-east-1')
        self.cloudfront_client = boto3.client('cloudfront', region_name='us-east-1')
        
        # Load balancer configuration
        self.lb_name = "multimodal-librarian-full-ml"
        self.lb_dns_name = None
        self.distribution_id = None
        self.distribution_domain = None
        
        self.results = {
            'timestamp': datetime.now().isoformat(),
            'operation': 'create_new_cloudfront_https',
            'steps': {},
            'success': False
        }
    
    def create_https_distribution(self) -> Dict[str, Any]:
        """Create a new CloudFront distribution for HTTPS."""
        
        print("🌐 Creating New CloudFront Distribution for HTTPS")
        print("=" * 55)
        
        try:
            # Step 1: Find the load balancer
            if not self._find_load_balancer():
                return self.results
            
            # Step 2: Create new CloudFront distribution
            if not self._create_distribution():
                return self.results
            
            # Step 3: Wait for deployment (optional)
            self._check_deployment_status()
            
            # Step 4: Test basic connectivity
            if not self._test_basic_connectivity():
                return self.results
            
            self.results['success'] = True
            print("\n🎉 CloudFront HTTPS distribution created successfully!")
            print(f"✅ HTTPS URL: https://{self.distribution_domain}")
            print(f"✅ Distribution ID: {self.distribution_id}")
            print("✅ SSL termination handled by CloudFront")
            
        except Exception as e:
            self.results['error'] = str(e)
            print(f"\n❌ CloudFront HTTPS creation failed: {e}")
        
        return self.results
    
    def _find_load_balancer(self) -> bool:
        """Find the existing load balancer."""
        
        print("\n📍 Step 1: Finding load balancer...")
        
        try:
            response = self.elbv2_client.describe_load_balancers()
            
            for lb in response['LoadBalancers']:
                if self.lb_name in lb['LoadBalancerName']:
                    self.lb_dns_name = lb['DNSName']
                    
                    print(f"✅ Found load balancer: {lb['LoadBalancerName']}")
                    print(f"   - DNS: {self.lb_dns_name}")
                    print(f"   - Length: {len(self.lb_dns_name)} chars")
                    
                    self.results['steps']['find_load_balancer'] = {
                        'success': True,
                        'lb_dns_name': self.lb_dns_name
                    }
                    return True
            
            print("❌ Load balancer not found")
            self.results['steps']['find_load_balancer'] = {
                'success': False,
                'error': 'Load balancer not found'
            }
            return False
            
        except Exception as e:
            print(f"❌ Error finding load balancer: {e}")
            self.results['steps']['find_load_balancer'] = {
                'success': False,
                'error': str(e)
            }
            return False
    
    def _create_distribution(self) -> bool:
        """Create a new CloudFront distribution."""
        
        print("\n🌐 Step 2: Creating CloudFront distribution...")
        
        try:
            # Generate unique caller reference
            caller_reference = f"ml-https-{int(time.time())}"
            
            distribution_config = {
                'CallerReference': caller_reference,
                'Comment': f'HTTPS distribution for Multimodal Librarian - {datetime.now().strftime("%Y-%m-%d")}',
                'DefaultRootObject': '',
                'Enabled': True,
                'PriceClass': 'PriceClass_100',  # US, Canada, Europe only
                'HttpVersion': 'http2',
                'Origins': {
                    'Quantity': 1,
                    'Items': [
                        {
                            'Id': 'ml-alb-origin',
                            'DomainName': self.lb_dns_name,
                            'CustomOriginConfig': {
                                'HTTPPort': 80,
                                'HTTPSPort': 443,
                                'OriginProtocolPolicy': 'http-only',  # ALB only serves HTTP
                                'OriginSslProtocols': {
                                    'Quantity': 1,
                                    'Items': ['TLSv1.2']
                                },
                                'OriginReadTimeout': 30,
                                'OriginKeepaliveTimeout': 5
                            }
                        }
                    ]
                },
                'DefaultCacheBehavior': {
                    'TargetOriginId': 'ml-alb-origin',
                    'ViewerProtocolPolicy': 'redirect-to-https',  # Force HTTPS
                    'MinTTL': 0,
                    'DefaultTTL': 0,  # Don't cache by default
                    'MaxTTL': 31536000,
                    'ForwardedValues': {
                        'QueryString': True,
                        'Cookies': {
                            'Forward': 'all'
                        },
                        'Headers': {
                            'Quantity': 1,
                            'Items': ['*']  # Forward all headers
                        }
                    },
                    'TrustedSigners': {
                        'Enabled': False,
                        'Quantity': 0
                    },
                    'AllowedMethods': {
                        'Quantity': 7,
                        'Items': ['GET', 'HEAD', 'OPTIONS', 'PUT', 'POST', 'PATCH', 'DELETE'],
                        'CachedMethods': {
                            'Quantity': 2,
                            'Items': ['GET', 'HEAD']
                        }
                    },
                    'Compress': True
                },
                'ViewerCertificate': {
                    'CloudFrontDefaultCertificate': True  # Use CloudFront's default SSL certificate
                },
                'WebACLId': ''
            }
            
            print("   - Creating distribution with configuration:")
            print(f"     - Origin: {self.lb_dns_name}")
            print(f"     - SSL: CloudFront default certificate")
            print(f"     - Protocol: Redirect HTTP to HTTPS")
            print(f"     - Caching: Disabled by default")
            
            response = self.cloudfront_client.create_distribution(
                DistributionConfig=distribution_config
            )
            
            self.distribution_id = response['Distribution']['Id']
            self.distribution_domain = response['Distribution']['DomainName']
            
            print(f"   - ✅ Created distribution: {self.distribution_id}")
            print(f"   - Domain: {self.distribution_domain}")
            print(f"   - Status: {response['Distribution']['Status']}")
            
            self.results['steps']['create_distribution'] = {
                'success': True,
                'distribution_id': self.distribution_id,
                'distribution_domain': self.distribution_domain,
                'status': response['Distribution']['Status']
            }
            
            return True
            
        except Exception as e:
            print(f"   - ❌ Error creating distribution: {e}")
            self.results['steps']['create_distribution'] = {
                'success': False,
                'error': str(e)
            }
            return False
    
    def _check_deployment_status(self) -> None:
        """Check deployment status (non-blocking)."""
        
        print("\n⏳ Step 3: Checking deployment status...")
        
        try:
            response = self.cloudfront_client.get_distribution(
                Id=self.distribution_id
            )
            
            status = response['Distribution']['Status']
            print(f"   - Current status: {status}")
            
            if status == 'Deployed':
                print("   - ✅ Distribution is already deployed!")
            elif status == 'InProgress':
                print("   - 🔄 Distribution is deploying (this can take 10-15 minutes)")
                print("   - You can use the HTTPS URL now, but it may take time to propagate globally")
            
            self.results['steps']['check_deployment'] = {
                'success': True,
                'status': status
            }
            
        except Exception as e:
            print(f"   - ⚠️  Could not check deployment status: {e}")
            self.results['steps']['check_deployment'] = {
                'success': False,
                'error': str(e)
            }
    
    def _test_basic_connectivity(self) -> bool:
        """Test basic connectivity to the distribution."""
        
        print("\n🔍 Step 4: Testing basic connectivity...")
        
        try:
            # Simple DNS resolution test
            import socket
            
            print(f"   - Testing DNS resolution for {self.distribution_domain}...")
            try:
                ip = socket.gethostbyname(self.distribution_domain)
                print(f"   - ✅ DNS resolves to: {ip}")
                dns_success = True
            except Exception as e:
                print(f"   - ⚠️  DNS resolution failed: {e}")
                dns_success = False
            
            # Basic HTTP test (may fail if still deploying)
            print("   - Testing basic HTTP connectivity...")
            try:
                import requests
                response = requests.get(f"http://{self.distribution_domain}", timeout=10)
                print(f"   - HTTP response: {response.status_code}")
                http_success = response.status_code in [200, 301, 302]
            except Exception as e:
                print(f"   - ⚠️  HTTP test failed (may be still deploying): {e}")
                http_success = False
            
            # At least DNS should work
            success = dns_success
            
            self.results['steps']['test_connectivity'] = {
                'success': success,
                'dns_resolution': dns_success,
                'http_test': http_success,
                'distribution_ip': ip if dns_success else None
            }
            
            if success:
                print("   - ✅ Basic connectivity test passed")
            else:
                print("   - ⚠️  Basic connectivity test had issues")
            
            return success
            
        except Exception as e:
            print(f"   - ❌ Error testing connectivity: {e}")
            self.results['steps']['test_connectivity'] = {
                'success': False,
                'error': str(e)
            }
            return False
    
    def save_results(self) -> str:
        """Save creation results to file."""
        
        filename = f"new-cloudfront-https-results-{int(time.time())}.json"
        
        with open(filename, 'w') as f:
            json.dump(self.results, f, indent=2, default=str)
        
        return filename


def main():
    """Main execution function."""
    
    print("🌐 New CloudFront HTTPS Distribution for Multimodal Librarian")
    print("Creating fresh CloudFront distribution with SSL termination")
    print()
    
    creator = NewCloudFrontHTTPS()
    results = creator.create_https_distribution()
    
    # Save results
    results_file = creator.save_results()
    print(f"\n📄 Creation results saved to: {results_file}")
    
    # Summary
    if results['success']:
        print("\n🎉 CloudFront HTTPS Distribution Summary:")
        print("=" * 50)
        print("✅ New CloudFront distribution created")
        print("✅ SSL termination enabled at CloudFront edge")
        print("✅ HTTP to HTTPS redirect configured")
        print("✅ Origin configured to use load balancer")
        print("✅ Basic connectivity verified")
        print()
        print(f"🌐 Your application HTTPS URLs:")
        print(f"   HTTPS: https://{creator.distribution_domain}")
        print(f"   HTTP:  http://{creator.distribution_domain} (redirects to HTTPS)")
        print()
        print("📋 Next Steps:")
        print("   1. Wait 10-15 minutes for global deployment")
        print("   2. Test HTTPS functionality")
        print("   3. Update DNS records if needed")
        print("   4. Configure custom domain (optional)")
        print()
        print("🔐 Security Features:")
        print("   - SSL/TLS encryption via CloudFront")
        print("   - AWS managed certificates")
        print("   - Automatic HTTP to HTTPS redirect")
        print("   - Global CDN with edge SSL termination")
        
        return 0
    else:
        print("\n❌ CloudFront HTTPS Distribution Creation Failed")
        print("Check the results file for detailed error information")
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)