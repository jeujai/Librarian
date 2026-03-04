#!/usr/bin/env python3
"""
Switch ECS Service from NLB to ALB with HTTPS Support

This script:
1. Gets the existing ALB (multimodal-lib-prod-alb)
2. Creates/updates target group for the ALB
3. Adds HTTPS listener with SSL certificate
4. Updates ECS service to use the ALB
5. Configures HTTP to HTTPS redirect
"""

import boto3
import json
import time
import sys
from datetime import datetime

class ALBSwitcher:
    def __init__(self):
        self.ecs_client = boto3.client('ecs', region_name='us-east-1')
        self.elbv2_client = boto3.client('elbv2', region_name='us-east-1')
        self.ec2_client = boto3.client('ec2', region_name='us-east-1')
        self.acm_client = boto3.client('acm', region_name='us-east-1')
        
        self.results = {
            'timestamp': datetime.now().isoformat(),
            'operation': 'switch_to_alb_with_https',
            'steps': {},
            'success': False
        }
        
    def switch_to_alb(self, domain_name=None):
        """Main execution function"""
        
        print("🔄 Switching from NLB to ALB with HTTPS Support")
        print("=" * 60)
        print()
        
        try:
            # Step 1: Get the existing ALB
            if not self._get_alb():
                return self.results
            
            # Step 2: Get VPC and subnets from ALB
            if not self._get_vpc_info():
                return self.results
            
            # Step 3: Create target group for ALB
            if not self._create_target_group():
                return self.results
            
            # Step 4: Get or create SSL certificate (if domain provided)
            if domain_name:
                if not self._setup_ssl_certificate(domain_name):
                    print("⚠️  Continuing without HTTPS...")
                    self.https_enabled = False
                else:
                    self.https_enabled = True
            else:
                print("⚠️  No domain provided - will configure HTTP only")
                print("   You can add HTTPS later with a domain name")
                self.https_enabled = False
            
            # Step 5: Configure ALB listeners
            if not self._configure_listeners():
                return self.results
            
            # Step 6: Update ECS service
            if not self._update_ecs_service():
                return self.results
            
            # Step 7: Wait for service stability
            if not self._wait_for_service_stable():
                return self.results
            
            self.results['success'] = True
            print("\n✅ Successfully switched to ALB!")
            
        except Exception as e:
            self.results['error'] = str(e)
            print(f"\n❌ Error: {e}")
        
        return self.results
    
    def _get_alb(self):
        """Get the existing ALB"""
        print("📍 Step 1: Finding existing ALB...")
        
        try:
            response = self.elbv2_client.describe_load_balancers()
            
            for lb in response['LoadBalancers']:
                if lb['LoadBalancerName'] == 'multimodal-lib-prod-alb':
                    self.alb_arn = lb['LoadBalancerArn']
                    self.alb_dns = lb['DNSName']
                    self.vpc_id = lb['VpcId']
                    self.alb_subnets = [az['SubnetId'] for az in lb['AvailabilityZones']]
                    self.security_groups = lb.get('SecurityGroups', [])
                    
                    print(f"✅ Found ALB: {lb['LoadBalancerName']}")
                    print(f"   DNS: {self.alb_dns}")
                    print(f"   VPC: {self.vpc_id}")
                    
                    self.results['steps']['get_alb'] = {
                        'success': True,
                        'alb_arn': self.alb_arn,
                        'alb_dns': self.alb_dns
                    }
                    return True
            
            print("❌ ALB 'multimodal-lib-prod-alb' not found")
            return False
            
        except Exception as e:
            print(f"❌ Error: {e}")
            self.results['steps']['get_alb'] = {'success': False, 'error': str(e)}
            return False
    
    def _get_vpc_info(self):
        """Get VPC and subnet information"""
        print("\n📍 Step 2: Getting VPC information...")
        
        try:
            # Get subnet details
            subnets_response = self.ec2_client.describe_subnets(SubnetIds=self.alb_subnets)
            
            print(f"✅ VPC ID: {self.vpc_id}")
            print(f"   Subnets: {len(self.alb_subnets)}")
            
            self.results['steps']['get_vpc_info'] = {
                'success': True,
                'vpc_id': self.vpc_id,
                'subnets': self.alb_subnets
            }
            return True
            
        except Exception as e:
            print(f"❌ Error: {e}")
            self.results['steps']['get_vpc_info'] = {'success': False, 'error': str(e)}
            return False
    
    def _create_target_group(self):
        """Create a new target group for the ALB"""
        print("\n📍 Step 3: Creating target group...")
        
        try:
            # Check if target group already exists
            try:
                tg_response = self.elbv2_client.describe_target_groups(
                    Names=['multimodal-lib-prod-alb-tg']
                )
                if tg_response['TargetGroups']:
                    self.target_group_arn = tg_response['TargetGroups'][0]['TargetGroupArn']
                    print(f"✅ Using existing target group")
                    print(f"   ARN: {self.target_group_arn}")
                    
                    self.results['steps']['create_target_group'] = {
                        'success': True,
                        'target_group_arn': self.target_group_arn,
                        'existing': True
                    }
                    return True
            except:
                pass
            
            # Create new target group
            response = self.elbv2_client.create_target_group(
                Name='multimodal-lib-prod-alb-tg',
                Protocol='HTTP',
                Port=8000,
                VpcId=self.vpc_id,
                HealthCheckProtocol='HTTP',
                HealthCheckPath='/health',
                HealthCheckIntervalSeconds=30,
                HealthCheckTimeoutSeconds=5,
                HealthyThresholdCount=2,
                UnhealthyThresholdCount=3,
                TargetType='ip',
                Tags=[
                    {'Key': 'Name', 'Value': 'multimodal-lib-prod-alb-tg'},
                    {'Key': 'Environment', 'Value': 'production'}
                ]
            )
            
            self.target_group_arn = response['TargetGroups'][0]['TargetGroupArn']
            
            print(f"✅ Created target group")
            print(f"   ARN: {self.target_group_arn}")
            
            self.results['steps']['create_target_group'] = {
                'success': True,
                'target_group_arn': self.target_group_arn,
                'existing': False
            }
            return True
            
        except Exception as e:
            print(f"❌ Error: {e}")
            self.results['steps']['create_target_group'] = {'success': False, 'error': str(e)}
            return False
    
    def _setup_ssl_certificate(self, domain_name):
        """Get or create SSL certificate"""
        print(f"\n📍 Step 4: Setting up SSL certificate for {domain_name}...")
        
        try:
            # Check for existing certificate
            response = self.acm_client.list_certificates(
                CertificateStatuses=['ISSUED']
            )
            
            for cert in response['CertificateSummaryList']:
                if cert['DomainName'] == domain_name:
                    self.certificate_arn = cert['CertificateArn']
                    print(f"✅ Found existing certificate")
                    print(f"   ARN: {self.certificate_arn}")
                    
                    self.results['steps']['setup_ssl'] = {
                        'success': True,
                        'certificate_arn': self.certificate_arn,
                        'existing': True
                    }
                    return True
            
            # No existing certificate - need to create one
            print(f"⚠️  No existing certificate found for {domain_name}")
            print("   You'll need to:")
            print("   1. Request a certificate in AWS Certificate Manager")
            print("   2. Validate it via DNS")
            print("   3. Run this script again")
            
            self.results['steps']['setup_ssl'] = {
                'success': False,
                'reason': 'No certificate found - manual setup required'
            }
            return False
            
        except Exception as e:
            print(f"❌ Error: {e}")
            self.results['steps']['setup_ssl'] = {'success': False, 'error': str(e)}
            return False
    
    def _configure_listeners(self):
        """Configure ALB listeners"""
        print("\n📍 Step 5: Configuring ALB listeners...")
        
        try:
            # Get existing listeners
            listeners = self.elbv2_client.describe_listeners(
                LoadBalancerArn=self.alb_arn
            )
            
            # Configure HTTPS listener if we have a certificate
            if self.https_enabled:
                https_exists = False
                for listener in listeners['Listeners']:
                    if listener['Protocol'] == 'HTTPS':
                        https_exists = True
                        # Update existing HTTPS listener
                        self.elbv2_client.modify_listener(
                            ListenerArn=listener['ListenerArn'],
                            DefaultActions=[{
                                'Type': 'forward',
                                'TargetGroupArn': self.target_group_arn
                            }]
                        )
                        print("✅ Updated existing HTTPS listener")
                        break
                
                if not https_exists:
                    # Create HTTPS listener
                    self.elbv2_client.create_listener(
                        LoadBalancerArn=self.alb_arn,
                        Protocol='HTTPS',
                        Port=443,
                        Certificates=[{'CertificateArn': self.certificate_arn}],
                        DefaultActions=[{
                            'Type': 'forward',
                            'TargetGroupArn': self.target_group_arn
                        }]
                    )
                    print("✅ Created HTTPS listener (port 443)")
                
                # Configure HTTP listener to redirect to HTTPS
                http_listener_arn = None
                for listener in listeners['Listeners']:
                    if listener['Protocol'] == 'HTTP' and listener['Port'] == 80:
                        http_listener_arn = listener['ListenerArn']
                        break
                
                if http_listener_arn:
                    self.elbv2_client.modify_listener(
                        ListenerArn=http_listener_arn,
                        DefaultActions=[{
                            'Type': 'redirect',
                            'RedirectConfig': {
                                'Protocol': 'HTTPS',
                                'Port': '443',
                                'StatusCode': 'HTTP_301'
                            }
                        }]
                    )
                    print("✅ Configured HTTP → HTTPS redirect")
            else:
                # HTTP only - update existing HTTP listener
                http_listener_arn = None
                for listener in listeners['Listeners']:
                    if listener['Protocol'] == 'HTTP' and listener['Port'] == 80:
                        http_listener_arn = listener['ListenerArn']
                        break
                
                if http_listener_arn:
                    self.elbv2_client.modify_listener(
                        ListenerArn=http_listener_arn,
                        DefaultActions=[{
                            'Type': 'forward',
                            'TargetGroupArn': self.target_group_arn
                        }]
                    )
                    print("✅ Updated HTTP listener (port 80)")
                else:
                    # Create HTTP listener
                    self.elbv2_client.create_listener(
                        LoadBalancerArn=self.alb_arn,
                        Protocol='HTTP',
                        Port=80,
                        DefaultActions=[{
                            'Type': 'forward',
                            'TargetGroupArn': self.target_group_arn
                        }]
                    )
                    print("✅ Created HTTP listener (port 80)")
            
            # Ensure security group allows HTTPS if enabled
            if self.https_enabled and self.security_groups:
                self._update_security_group_for_https()
            
            self.results['steps']['configure_listeners'] = {
                'success': True,
                'https_enabled': self.https_enabled
            }
            return True
            
        except Exception as e:
            print(f"❌ Error: {e}")
            self.results['steps']['configure_listeners'] = {'success': False, 'error': str(e)}
            return False
    
    def _update_security_group_for_https(self):
        """Ensure security group allows HTTPS traffic"""
        try:
            for sg_id in self.security_groups:
                sg = self.ec2_client.describe_security_groups(GroupIds=[sg_id])
                
                # Check if HTTPS rule exists
                https_exists = False
                for rule in sg['SecurityGroups'][0]['IpPermissions']:
                    if rule.get('FromPort') == 443:
                        https_exists = True
                        break
                
                if not https_exists:
                    self.ec2_client.authorize_security_group_ingress(
                        GroupId=sg_id,
                        IpPermissions=[{
                            'IpProtocol': 'tcp',
                            'FromPort': 443,
                            'ToPort': 443,
                            'IpRanges': [{'CidrIp': '0.0.0.0/0'}]
                        }]
                    )
                    print(f"   Added HTTPS rule to security group {sg_id}")
        except Exception as e:
            if 'Duplicate' not in str(e):
                print(f"   Warning: Could not update security group: {e}")
    
    def _update_ecs_service(self):
        """Update ECS service to use the ALB"""
        print("\n📍 Step 6: Updating ECS service...")
        
        try:
            response = self.ecs_client.update_service(
                cluster='multimodal-lib-prod-cluster',
                service='multimodal-lib-prod-service',
                loadBalancers=[{
                    'targetGroupArn': self.target_group_arn,
                    'containerName': 'multimodal-lib-prod-app',
                    'containerPort': 8000
                }],
                healthCheckGracePeriodSeconds=60
            )
            
            print("✅ Updated ECS service to use ALB")
            print("   Waiting for service to stabilize...")
            
            self.results['steps']['update_ecs_service'] = {
                'success': True,
                'target_group_arn': self.target_group_arn
            }
            return True
            
        except Exception as e:
            print(f"❌ Error: {e}")
            self.results['steps']['update_ecs_service'] = {'success': False, 'error': str(e)}
            return False
    
    def _wait_for_service_stable(self):
        """Wait for ECS service to become stable"""
        print("\n📍 Step 7: Waiting for service stability...")
        
        try:
            waiter = self.ecs_client.get_waiter('services_stable')
            waiter.wait(
                cluster='multimodal-lib-prod-cluster',
                services=['multimodal-lib-prod-service'],
                WaiterConfig={'Delay': 15, 'MaxAttempts': 40}
            )
            
            print("✅ Service is stable")
            
            self.results['steps']['wait_for_stable'] = {'success': True}
            return True
            
        except Exception as e:
            print(f"⚠️  Service may still be stabilizing: {e}")
            print("   Check the ECS console for status")
            self.results['steps']['wait_for_stable'] = {
                'success': False,
                'warning': 'Timeout waiting for stability'
            }
            return True  # Continue anyway
    
    def save_results(self):
        """Save results to file"""
        filename = f"alb-switch-{int(time.time())}.json"
        with open(filename, 'w') as f:
            json.dump(self.results, f, indent=2, default=str)
        return filename


def main():
    print("🔄 Switch to ALB with HTTPS Support")
    print()
    
    domain_name = None
    if len(sys.argv) > 1:
        domain_name = sys.argv[1]
        print(f"Domain: {domain_name}")
    else:
        print("No domain provided - will configure HTTP only")
        print("Usage: python switch-to-alb-with-https.py [domain-name]")
    
    print()
    
    switcher = ALBSwitcher()
    results = switcher.switch_to_alb(domain_name)
    
    # Save results
    results_file = switcher.save_results()
    print(f"\n📄 Results saved to: {results_file}")
    
    # Summary
    if results['success']:
        print("\n✅ Switch Complete!")
        print("=" * 60)
        print(f"Your application is now using the ALB")
        
        if switcher.https_enabled:
            print(f"\n🔒 HTTPS Endpoint:")
            print(f"   https://{switcher.alb_dns}")
            print(f"\n   HTTP traffic will redirect to HTTPS")
        else:
            print(f"\n🌐 HTTP Endpoint:")
            print(f"   http://{switcher.alb_dns}")
            print(f"\n   To add HTTPS later, run:")
            print(f"   python {sys.argv[0]} your-domain.com")
        
        print(f"\n💡 Next Steps:")
        print(f"   1. Test the endpoint above")
        print(f"   2. Update your DNS to point to the ALB")
        if not switcher.https_enabled:
            print(f"   3. Set up SSL certificate for HTTPS")
        print(f"   4. Delete the unused NLB to save costs")
        
        return 0
    else:
        print("\n❌ Switch Failed")
        print("Check the results file for details")
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
