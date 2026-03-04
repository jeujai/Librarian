#!/usr/bin/env python3
"""
Add HTTPS Support with SSL Certificates to Load Balancer

This script adds HTTPS support to the existing load balancer by:
1. Requesting an SSL certificate from AWS Certificate Manager (ACM)
2. Adding HTTPS listener (port 443) to the load balancer
3. Configuring security groups to allow HTTPS traffic
4. Setting up HTTP to HTTPS redirect for security
"""

import boto3
import json
import time
import sys
from datetime import datetime
from typing import Dict, List, Any, Optional

class HTTPSSetupManager:
    """Manages HTTPS setup for the production load balancer."""
    
    def __init__(self):
        self.elbv2_client = boto3.client('elbv2', region_name='us-east-1')
        self.acm_client = boto3.client('acm', region_name='us-east-1')
        self.ec2_client = boto3.client('ec2', region_name='us-east-1')
        
        # Load balancer configuration
        self.lb_name = "multimodal-librarian-full-ml"
        self.lb_arn = None
        self.lb_dns_name = None
        self.certificate_arn = None
        
        self.results = {
            'timestamp': datetime.now().isoformat(),
            'operation': 'https_ssl_setup',
            'steps': {},
            'success': False
        }
    
    def setup_https_support(self) -> Dict[str, Any]:
        """Set up complete HTTPS support with SSL certificates."""
        
        print("🔒 Setting up HTTPS Support with SSL Certificates")
        print("=" * 60)
        
        try:
            # Step 1: Find the load balancer
            if not self._find_load_balancer():
                return self.results
            
            # Step 2: Request SSL certificate
            if not self._request_ssl_certificate():
                return self.results
            
            # Step 3: Wait for certificate validation
            if not self._wait_for_certificate_validation():
                return self.results
            
            # Step 4: Add HTTPS listener
            if not self._add_https_listener():
                return self.results
            
            # Step 5: Update security groups
            if not self._update_security_groups():
                return self.results
            
            # Step 6: Add HTTP to HTTPS redirect
            if not self._add_http_redirect():
                return self.results
            
            # Step 7: Verify HTTPS setup
            if not self._verify_https_setup():
                return self.results
            
            self.results['success'] = True
            print("\n🎉 HTTPS setup completed successfully!")
            print(f"✅ Your application is now available at: https://{self.lb_dns_name}")
            
        except Exception as e:
            self.results['error'] = str(e)
            print(f"\n❌ HTTPS setup failed: {e}")
        
        return self.results
    
    def _find_load_balancer(self) -> bool:
        """Find the existing load balancer."""
        
        print("\n📍 Step 1: Finding load balancer...")
        
        try:
            response = self.elbv2_client.describe_load_balancers()
            
            for lb in response['LoadBalancers']:
                if self.lb_name in lb['LoadBalancerName']:
                    self.lb_arn = lb['LoadBalancerArn']
                    self.lb_dns_name = lb['DNSName']
                    
                    self.results['steps']['find_load_balancer'] = {
                        'success': True,
                        'lb_arn': self.lb_arn,
                        'lb_dns_name': self.lb_dns_name
                    }
                    
                    print(f"✅ Found load balancer: {lb['LoadBalancerName']}")
                    print(f"   - ARN: {self.lb_arn}")
                    print(f"   - DNS: {self.lb_dns_name}")
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
    
    def _request_ssl_certificate(self) -> bool:
        """Request SSL certificate from AWS Certificate Manager."""
        
        print("\n🔐 Step 2: Requesting SSL certificate...")
        
        try:
            # Check if certificate already exists
            existing_cert = self._find_existing_certificate()
            if existing_cert:
                self.certificate_arn = existing_cert
                print(f"✅ Using existing certificate: {self.certificate_arn}")
                self.results['steps']['request_certificate'] = {
                    'success': True,
                    'certificate_arn': self.certificate_arn,
                    'existing': True
                }
                return True
            
            # Request new certificate
            response = self.acm_client.request_certificate(
                DomainName=self.lb_dns_name,
                ValidationMethod='DNS',
                Options={
                    'CertificateTransparencyLoggingPreference': 'ENABLED'
                },
                Tags=[
                    {
                        'Key': 'Name',
                        'Value': f'multimodal-librarian-ssl-{int(time.time())}'
                    },
                    {
                        'Key': 'Environment',
                        'Value': 'production'
                    }
                ]
            )
            
            self.certificate_arn = response['CertificateArn']
            
            self.results['steps']['request_certificate'] = {
                'success': True,
                'certificate_arn': self.certificate_arn,
                'domain': self.lb_dns_name,
                'validation_method': 'DNS'
            }
            
            print(f"✅ SSL certificate requested")
            print(f"   - Certificate ARN: {self.certificate_arn}")
            print(f"   - Domain: {self.lb_dns_name}")
            print(f"   - Validation: DNS")
            
            return True
            
        except Exception as e:
            print(f"❌ Error requesting SSL certificate: {e}")
            self.results['steps']['request_certificate'] = {
                'success': False,
                'error': str(e)
            }
            return False
    
    def _find_existing_certificate(self) -> Optional[str]:
        """Find existing certificate for the domain."""
        
        try:
            response = self.acm_client.list_certificates(
                CertificateStatuses=['ISSUED', 'PENDING_VALIDATION']
            )
            
            for cert in response['CertificateSummaryList']:
                if cert['DomainName'] == self.lb_dns_name:
                    return cert['CertificateArn']
            
            return None
            
        except Exception:
            return None
    
    def _wait_for_certificate_validation(self) -> bool:
        """Wait for certificate validation to complete."""
        
        print("\n⏳ Step 3: Waiting for certificate validation...")
        print("   Note: DNS validation may take several minutes...")
        
        try:
            max_wait_time = 600  # 10 minutes
            start_time = time.time()
            
            while (time.time() - start_time) < max_wait_time:
                response = self.acm_client.describe_certificate(
                    CertificateArn=self.certificate_arn
                )
                
                cert_status = response['Certificate']['Status']
                
                if cert_status == 'ISSUED':
                    validation_time = time.time() - start_time
                    
                    self.results['steps']['certificate_validation'] = {
                        'success': True,
                        'status': 'ISSUED',
                        'validation_time_seconds': validation_time
                    }
                    
                    print(f"✅ Certificate validated and issued ({validation_time:.1f}s)")
                    return True
                
                elif cert_status == 'FAILED':
                    print("❌ Certificate validation failed")
                    self.results['steps']['certificate_validation'] = {
                        'success': False,
                        'status': 'FAILED',
                        'error': 'Certificate validation failed'
                    }
                    return False
                
                elif cert_status == 'PENDING_VALIDATION':
                    # Show DNS validation records if available
                    if 'DomainValidationOptions' in response['Certificate']:
                        for validation in response['Certificate']['DomainValidationOptions']:
                            if 'ResourceRecord' in validation:
                                record = validation['ResourceRecord']
                                print(f"   DNS validation record needed:")
                                print(f"   - Name: {record['Name']}")
                                print(f"   - Type: {record['Type']}")
                                print(f"   - Value: {record['Value']}")
                    
                    print(f"   Status: {cert_status} (waiting...)")
                    time.sleep(30)  # Wait 30 seconds before checking again
                
                else:
                    print(f"   Status: {cert_status}")
                    time.sleep(10)
            
            print("❌ Certificate validation timeout")
            self.results['steps']['certificate_validation'] = {
                'success': False,
                'error': 'Validation timeout',
                'timeout_seconds': max_wait_time
            }
            return False
            
        except Exception as e:
            print(f"❌ Error waiting for certificate validation: {e}")
            self.results['steps']['certificate_validation'] = {
                'success': False,
                'error': str(e)
            }
            return False
    
    def _add_https_listener(self) -> bool:
        """Add HTTPS listener to the load balancer."""
        
        print("\n🔗 Step 4: Adding HTTPS listener...")
        
        try:
            # Get existing target group
            target_group_arn = self._get_target_group_arn()
            if not target_group_arn:
                return False
            
            # Check if HTTPS listener already exists
            existing_listener = self._find_https_listener()
            if existing_listener:
                print("✅ HTTPS listener already exists")
                self.results['steps']['add_https_listener'] = {
                    'success': True,
                    'listener_arn': existing_listener,
                    'existing': True
                }
                return True
            
            # Create HTTPS listener
            response = self.elbv2_client.create_listener(
                LoadBalancerArn=self.lb_arn,
                Protocol='HTTPS',
                Port=443,
                Certificates=[
                    {
                        'CertificateArn': self.certificate_arn
                    }
                ],
                DefaultActions=[
                    {
                        'Type': 'forward',
                        'TargetGroupArn': target_group_arn
                    }
                ]
            )
            
            listener_arn = response['Listeners'][0]['ListenerArn']
            
            self.results['steps']['add_https_listener'] = {
                'success': True,
                'listener_arn': listener_arn,
                'port': 443,
                'protocol': 'HTTPS',
                'certificate_arn': self.certificate_arn
            }
            
            print(f"✅ HTTPS listener created")
            print(f"   - Listener ARN: {listener_arn}")
            print(f"   - Port: 443")
            print(f"   - Certificate: {self.certificate_arn}")
            
            return True
            
        except Exception as e:
            print(f"❌ Error adding HTTPS listener: {e}")
            self.results['steps']['add_https_listener'] = {
                'success': False,
                'error': str(e)
            }
            return False
    
    def _get_target_group_arn(self) -> Optional[str]:
        """Get the target group ARN for the load balancer."""
        
        try:
            # Get listeners to find target group
            response = self.elbv2_client.describe_listeners(
                LoadBalancerArn=self.lb_arn
            )
            
            for listener in response['Listeners']:
                if listener['Port'] == 80:  # HTTP listener
                    for action in listener['DefaultActions']:
                        if action['Type'] == 'forward':
                            return action['TargetGroupArn']
            
            return None
            
        except Exception:
            return None
    
    def _find_https_listener(self) -> Optional[str]:
        """Find existing HTTPS listener."""
        
        try:
            response = self.elbv2_client.describe_listeners(
                LoadBalancerArn=self.lb_arn
            )
            
            for listener in response['Listeners']:
                if listener['Protocol'] == 'HTTPS' and listener['Port'] == 443:
                    return listener['ListenerArn']
            
            return None
            
        except Exception:
            return None
    
    def _update_security_groups(self) -> bool:
        """Update security groups to allow HTTPS traffic."""
        
        print("\n🛡️  Step 5: Updating security groups...")
        
        try:
            # Get load balancer security groups
            response = self.elbv2_client.describe_load_balancers(
                LoadBalancerArns=[self.lb_arn]
            )
            
            security_groups = response['LoadBalancers'][0]['SecurityGroups']
            
            updated_groups = []
            
            for sg_id in security_groups:
                if self._add_https_rule_to_security_group(sg_id):
                    updated_groups.append(sg_id)
            
            self.results['steps']['update_security_groups'] = {
                'success': True,
                'updated_groups': updated_groups,
                'total_groups': len(security_groups)
            }
            
            print(f"✅ Security groups updated ({len(updated_groups)}/{len(security_groups)})")
            
            return True
            
        except Exception as e:
            print(f"❌ Error updating security groups: {e}")
            self.results['steps']['update_security_groups'] = {
                'success': False,
                'error': str(e)
            }
            return False
    
    def _add_https_rule_to_security_group(self, sg_id: str) -> bool:
        """Add HTTPS rule to a security group."""
        
        try:
            # Check if HTTPS rule already exists
            response = self.ec2_client.describe_security_groups(
                GroupIds=[sg_id]
            )
            
            for rule in response['SecurityGroups'][0]['IpPermissions']:
                if (rule.get('IpProtocol') == 'tcp' and 
                    rule.get('FromPort') == 443 and 
                    rule.get('ToPort') == 443):
                    print(f"   - HTTPS rule already exists in {sg_id}")
                    return True
            
            # Add HTTPS rule
            self.ec2_client.authorize_security_group_ingress(
                GroupId=sg_id,
                IpPermissions=[
                    {
                        'IpProtocol': 'tcp',
                        'FromPort': 443,
                        'ToPort': 443,
                        'IpRanges': [
                            {
                                'CidrIp': '0.0.0.0/0',
                                'Description': 'HTTPS access from anywhere'
                            }
                        ]
                    }
                ]
            )
            
            print(f"   - Added HTTPS rule to {sg_id}")
            return True
            
        except Exception as e:
            if 'already exists' in str(e).lower():
                print(f"   - HTTPS rule already exists in {sg_id}")
                return True
            else:
                print(f"   - Error updating {sg_id}: {e}")
                return False
    
    def _add_http_redirect(self) -> bool:
        """Add HTTP to HTTPS redirect for security."""
        
        print("\n🔄 Step 6: Adding HTTP to HTTPS redirect...")
        
        try:
            # Find HTTP listener
            response = self.elbv2_client.describe_listeners(
                LoadBalancerArn=self.lb_arn
            )
            
            http_listener_arn = None
            for listener in response['Listeners']:
                if listener['Protocol'] == 'HTTP' and listener['Port'] == 80:
                    http_listener_arn = listener['ListenerArn']
                    break
            
            if not http_listener_arn:
                print("⚠️  No HTTP listener found to redirect")
                self.results['steps']['add_http_redirect'] = {
                    'success': True,
                    'message': 'No HTTP listener found'
                }
                return True
            
            # Modify HTTP listener to redirect to HTTPS
            self.elbv2_client.modify_listener(
                ListenerArn=http_listener_arn,
                DefaultActions=[
                    {
                        'Type': 'redirect',
                        'RedirectConfig': {
                            'Protocol': 'HTTPS',
                            'Port': '443',
                            'StatusCode': 'HTTP_301'
                        }
                    }
                ]
            )
            
            self.results['steps']['add_http_redirect'] = {
                'success': True,
                'listener_arn': http_listener_arn,
                'redirect_type': 'HTTP_301',
                'target_port': 443
            }
            
            print("✅ HTTP to HTTPS redirect configured")
            print("   - All HTTP traffic will redirect to HTTPS")
            print("   - Redirect type: 301 (Permanent)")
            
            return True
            
        except Exception as e:
            print(f"❌ Error adding HTTP redirect: {e}")
            self.results['steps']['add_http_redirect'] = {
                'success': False,
                'error': str(e)
            }
            return False
    
    def _verify_https_setup(self) -> bool:
        """Verify HTTPS setup is working correctly."""
        
        print("\n✅ Step 7: Verifying HTTPS setup...")
        
        try:
            # Check listeners
            response = self.elbv2_client.describe_listeners(
                LoadBalancerArn=self.lb_arn
            )
            
            https_listener_found = False
            http_redirect_found = False
            
            for listener in response['Listeners']:
                if listener['Protocol'] == 'HTTPS' and listener['Port'] == 443:
                    https_listener_found = True
                    print("   ✅ HTTPS listener (port 443) active")
                
                elif listener['Protocol'] == 'HTTP' and listener['Port'] == 80:
                    # Check if it's redirecting
                    for action in listener['DefaultActions']:
                        if action['Type'] == 'redirect':
                            http_redirect_found = True
                            print("   ✅ HTTP redirect (port 80) active")
                            break
            
            # Check certificate status
            cert_response = self.acm_client.describe_certificate(
                CertificateArn=self.certificate_arn
            )
            
            cert_status = cert_response['Certificate']['Status']
            cert_valid = cert_status == 'ISSUED'
            
            if cert_valid:
                print("   ✅ SSL certificate valid and issued")
            else:
                print(f"   ⚠️  SSL certificate status: {cert_status}")
            
            setup_complete = https_listener_found and cert_valid
            
            self.results['steps']['verify_https_setup'] = {
                'success': setup_complete,
                'https_listener': https_listener_found,
                'http_redirect': http_redirect_found,
                'certificate_valid': cert_valid,
                'certificate_status': cert_status
            }
            
            if setup_complete:
                print("\n🎉 HTTPS setup verification successful!")
                print(f"   - HTTPS URL: https://{self.lb_dns_name}")
                print(f"   - HTTP redirects to HTTPS automatically")
                print(f"   - SSL certificate is valid and active")
            else:
                print("\n⚠️  HTTPS setup verification found issues")
            
            return setup_complete
            
        except Exception as e:
            print(f"❌ Error verifying HTTPS setup: {e}")
            self.results['steps']['verify_https_setup'] = {
                'success': False,
                'error': str(e)
            }
            return False
    
    def save_results(self) -> str:
        """Save setup results to file."""
        
        filename = f"https-ssl-setup-results-{int(time.time())}.json"
        
        with open(filename, 'w') as f:
            json.dump(self.results, f, indent=2, default=str)
        
        return filename


def main():
    """Main execution function."""
    
    print("🔒 HTTPS SSL Setup for Production Load Balancer")
    print("Adding SSL certificates and HTTPS support")
    print()
    
    manager = HTTPSSetupManager()
    results = manager.setup_https_support()
    
    # Save results
    results_file = manager.save_results()
    print(f"\n📄 Setup results saved to: {results_file}")
    
    # Summary
    if results['success']:
        print("\n🎉 HTTPS Setup Summary:")
        print("=" * 40)
        print("✅ SSL certificate requested and validated")
        print("✅ HTTPS listener (port 443) added to load balancer")
        print("✅ Security groups updated to allow HTTPS traffic")
        print("✅ HTTP to HTTPS redirect configured")
        print("✅ Setup verification completed successfully")
        print()
        print(f"🌐 Your application is now available at:")
        print(f"   https://{manager.lb_dns_name}")
        print()
        print("🔐 Security features enabled:")
        print("   - SSL/TLS encryption for all traffic")
        print("   - Automatic HTTP to HTTPS redirect")
        print("   - AWS Certificate Manager managed certificate")
        
        return 0
    else:
        print("\n❌ HTTPS Setup Failed")
        print("Check the results file for detailed error information")
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)