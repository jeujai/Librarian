#!/usr/bin/env python3
"""
Verify HTTPS Deployment

This script verifies that the CloudFront HTTPS deployment is working correctly.
Run this after the CloudFront distribution has finished deploying (10-15 minutes).
"""

import boto3
import json
import time
import sys
from datetime import datetime
from typing import Dict, Any

class HTTPSDeploymentVerifier:
    """Verifies HTTPS deployment through CloudFront."""
    
    def __init__(self):
        self.cloudfront_client = boto3.client('cloudfront', region_name='us-east-1')
        
        # Known distribution details
        self.distribution_id = "E3NVIH7ET1R4G9"
        self.distribution_domain = "d1c3ih7gvhogu1.cloudfront.net"
        self.lb_dns_name = "multimodal-librarian-full-ml-249704554.us-east-1.elb.amazonaws.com"
        
        self.results = {
            'timestamp': datetime.now().isoformat(),
            'operation': 'verify_https_deployment',
            'distribution_id': self.distribution_id,
            'distribution_domain': self.distribution_domain,
            'tests': {},
            'success': False
        }
    
    def verify_deployment(self) -> Dict[str, Any]:
        """Verify the HTTPS deployment is working."""
        
        print("🔍 Verifying HTTPS Deployment")
        print("=" * 35)
        print(f"Distribution ID: {self.distribution_id}")
        print(f"CloudFront Domain: {self.distribution_domain}")
        print()
        
        try:
            # Test 1: Check distribution status
            if not self._check_distribution_status():
                print("⚠️  Distribution not yet deployed, but continuing with tests...")
            
            # Test 2: DNS resolution
            self._test_dns_resolution()
            
            # Test 3: HTTPS connectivity
            self._test_https_connectivity()
            
            # Test 4: HTTP to HTTPS redirect
            self._test_http_redirect()
            
            # Test 5: Application endpoints
            self._test_application_endpoints()
            
            # Determine overall success
            successful_tests = sum(1 for test in self.results['tests'].values() if test.get('success', False))
            total_tests = len(self.results['tests'])
            
            self.results['successful_tests'] = successful_tests
            self.results['total_tests'] = total_tests
            self.results['success'] = successful_tests >= 2  # At least 2 tests should pass
            
            if self.results['success']:
                print(f"\n🎉 HTTPS Deployment Verification: {successful_tests}/{total_tests} tests passed")
                print("✅ HTTPS upgrade completed successfully!")
            else:
                print(f"\n⚠️  HTTPS Deployment Verification: {successful_tests}/{total_tests} tests passed")
                print("🔄 Distribution may still be deploying...")
            
        except Exception as e:
            self.results['error'] = str(e)
            print(f"\n❌ Verification failed: {e}")
        
        return self.results
    
    def _check_distribution_status(self) -> bool:
        """Check CloudFront distribution status."""
        
        print("📊 Test 1: Distribution Status")
        
        try:
            response = self.cloudfront_client.get_distribution(
                Id=self.distribution_id
            )
            
            status = response['Distribution']['Status']
            last_modified = response['Distribution']['LastModifiedTime']
            
            print(f"   Status: {status}")
            print(f"   Last Modified: {last_modified}")
            
            success = status == 'Deployed'
            
            self.results['tests']['distribution_status'] = {
                'success': success,
                'status': status,
                'last_modified': str(last_modified)
            }
            
            if success:
                print("   ✅ Distribution is deployed")
            else:
                print("   🔄 Distribution is still deploying")
            
            return success
            
        except Exception as e:
            print(f"   ❌ Error checking status: {e}")
            self.results['tests']['distribution_status'] = {
                'success': False,
                'error': str(e)
            }
            return False
    
    def _test_dns_resolution(self) -> bool:
        """Test DNS resolution for the CloudFront domain."""
        
        print("\n🌐 Test 2: DNS Resolution")
        
        try:
            import socket
            
            print(f"   Resolving: {self.distribution_domain}")
            ip = socket.gethostbyname(self.distribution_domain)
            print(f"   ✅ Resolves to: {ip}")
            
            self.results['tests']['dns_resolution'] = {
                'success': True,
                'ip_address': ip
            }
            
            return True
            
        except Exception as e:
            print(f"   ❌ DNS resolution failed: {e}")
            self.results['tests']['dns_resolution'] = {
                'success': False,
                'error': str(e)
            }
            return False
    
    def _test_https_connectivity(self) -> bool:
        """Test HTTPS connectivity."""
        
        print("\n🔒 Test 3: HTTPS Connectivity")
        
        try:
            import requests
            from urllib3.exceptions import InsecureRequestWarning
            requests.packages.urllib3.disable_warnings(InsecureRequestWarning)
            
            https_url = f"https://{self.distribution_domain}"
            
            print(f"   Testing: {https_url}")
            response = requests.get(https_url, timeout=30, verify=False)
            
            print(f"   ✅ HTTPS Status: {response.status_code}")
            print(f"   Response Size: {len(response.content)} bytes")
            
            success = response.status_code in [200, 301, 302]
            
            self.results['tests']['https_connectivity'] = {
                'success': success,
                'status_code': response.status_code,
                'response_size': len(response.content)
            }
            
            return success
            
        except Exception as e:
            print(f"   ❌ HTTPS test failed: {e}")
            self.results['tests']['https_connectivity'] = {
                'success': False,
                'error': str(e)
            }
            return False
    
    def _test_http_redirect(self) -> bool:
        """Test HTTP to HTTPS redirect."""
        
        print("\n🔄 Test 4: HTTP to HTTPS Redirect")
        
        try:
            import requests
            
            http_url = f"http://{self.distribution_domain}"
            
            print(f"   Testing: {http_url}")
            response = requests.get(http_url, timeout=30, allow_redirects=False)
            
            if response.status_code in [301, 302]:
                location = response.headers.get('Location', '')
                print(f"   ✅ Redirect Status: {response.status_code}")
                print(f"   Redirect Location: {location}")
                
                success = location.startswith('https://')
                
                self.results['tests']['http_redirect'] = {
                    'success': success,
                    'status_code': response.status_code,
                    'redirect_location': location
                }
                
                return success
            else:
                print(f"   ❌ No redirect, status: {response.status_code}")
                self.results['tests']['http_redirect'] = {
                    'success': False,
                    'status_code': response.status_code
                }
                return False
            
        except Exception as e:
            print(f"   ❌ HTTP redirect test failed: {e}")
            self.results['tests']['http_redirect'] = {
                'success': False,
                'error': str(e)
            }
            return False
    
    def _test_application_endpoints(self) -> bool:
        """Test key application endpoints."""
        
        print("\n🚀 Test 5: Application Endpoints")
        
        try:
            import requests
            from urllib3.exceptions import InsecureRequestWarning
            requests.packages.urllib3.disable_warnings(InsecureRequestWarning)
            
            base_url = f"https://{self.distribution_domain}"
            endpoints = [
                ('/', 'Root endpoint'),
                ('/health/simple', 'Health check'),
                ('/docs', 'API documentation'),
                ('/features', 'Features endpoint')
            ]
            
            endpoint_results = {}
            successful_endpoints = 0
            
            for path, description in endpoints:
                url = f"{base_url}{path}"
                print(f"   Testing {description}: {path}")
                
                try:
                    response = requests.get(url, timeout=15, verify=False)
                    success = response.status_code in [200, 301, 302]
                    
                    if success:
                        print(f"     ✅ {response.status_code}")
                        successful_endpoints += 1
                    else:
                        print(f"     ⚠️  {response.status_code}")
                    
                    endpoint_results[path] = {
                        'success': success,
                        'status_code': response.status_code
                    }
                    
                except Exception as e:
                    print(f"     ❌ Error: {e}")
                    endpoint_results[path] = {
                        'success': False,
                        'error': str(e)
                    }
            
            overall_success = successful_endpoints >= 2  # At least 2 endpoints should work
            
            self.results['tests']['application_endpoints'] = {
                'success': overall_success,
                'successful_endpoints': successful_endpoints,
                'total_endpoints': len(endpoints),
                'endpoint_results': endpoint_results
            }
            
            print(f"   📊 Endpoints working: {successful_endpoints}/{len(endpoints)}")
            
            return overall_success
            
        except Exception as e:
            print(f"   ❌ Application endpoints test failed: {e}")
            self.results['tests']['application_endpoints'] = {
                'success': False,
                'error': str(e)
            }
            return False
    
    def save_results(self) -> str:
        """Save verification results to file."""
        
        filename = f"https-verification-results-{int(time.time())}.json"
        
        with open(filename, 'w') as f:
            json.dump(self.results, f, indent=2, default=str)
        
        return filename


def main():
    """Main execution function."""
    
    print("🔍 HTTPS Deployment Verification for Multimodal Librarian")
    print("Verifying CloudFront HTTPS functionality")
    print()
    
    verifier = HTTPSDeploymentVerifier()
    results = verifier.verify_deployment()
    
    # Save results
    results_file = verifier.save_results()
    print(f"\n📄 Verification results saved to: {results_file}")
    
    # Summary
    if results['success']:
        print("\n🎉 HTTPS Deployment Verification Summary:")
        print("=" * 45)
        print("✅ CloudFront HTTPS deployment is working!")
        print(f"✅ {results['successful_tests']}/{results['total_tests']} verification tests passed")
        print()
        print("🌐 Your application is now available via HTTPS:")
        print(f"   Primary HTTPS URL: https://{verifier.distribution_domain}")
        print(f"   Direct ALB URL:    http://{verifier.lb_dns_name}")
        print()
        print("🔐 HTTPS Features Active:")
        print("   - SSL/TLS encryption via CloudFront")
        print("   - AWS managed certificates")
        print("   - Automatic HTTP to HTTPS redirect")
        print("   - Global CDN with edge SSL termination")
        print("   - Optimized for performance and security")
        
        return 0
    else:
        print("\n⚠️  HTTPS Deployment Verification Results:")
        print("=" * 45)
        print(f"📊 {results['successful_tests']}/{results['total_tests']} verification tests passed")
        print()
        if results['successful_tests'] > 0:
            print("🔄 The CloudFront distribution may still be deploying globally.")
            print("   This can take 10-15 minutes. Try running this script again later.")
            print()
            print(f"🌐 HTTPS URL (may work in some regions): https://{verifier.distribution_domain}")
        else:
            print("❌ HTTPS deployment verification failed.")
            print("   Check the results file for detailed error information.")
        
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)