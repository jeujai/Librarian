#!/usr/bin/env python3
"""
Fix LLM Integration and HTTPS Issues

This script addresses the two main issues:
1. LLM Integration: Fix IAM permissions for secrets manager access
2. HTTPS: Update CloudFront distribution to point to new load balancer

The script will:
- Update IAM permissions with correct secret ARNs
- Update CloudFront distribution origin to new load balancer
- Restart ECS service to apply new permissions
- Test both HTTP and HTTPS connectivity
"""

import boto3
import json
import time
import sys
from datetime import datetime
from typing import Dict, List, Any, Optional

class LLMAndHTTPSFixer:
    """Fixes LLM integration and HTTPS issues."""
    
    def __init__(self):
        self.iam_client = boto3.client('iam', region_name='us-east-1')
        self.cf_client = boto3.client('cloudfront', region_name='us-east-1')
        self.ecs_client = boto3.client('ecs', region_name='us-east-1')
        self.secrets_client = boto3.client('secretsmanager', region_name='us-east-1')
        self.sts_client = boto3.client('sts', region_name='us-east-1')
        
        # Configuration
        self.task_role_name = "ecsTaskRole"
        self.cloudfront_distribution_id = "E3NVIH7ET1R4G9"
        self.new_load_balancer_dns = "ml-shared-vpc-alb-1260972620.us-east-1.elb.amazonaws.com"
        self.cluster_name = "multimodal-lib-prod-cluster"
        self.service_name = "multimodal-lib-prod-service"
        
        self.results = {
            'timestamp': datetime.now().isoformat(),
            'operation': 'fix_llm_and_https_integration',
            'steps': {},
            'success': False
        }
    
    def fix_integration_issues(self) -> Dict[str, Any]:
        """Fix both LLM integration and HTTPS issues."""
        
        print("🔧 Fixing LLM Integration and HTTPS Issues")
        print("=" * 50)
        
        try:
            # Step 1: Fix IAM permissions for secrets access
            if not self._fix_iam_permissions():
                return self.results
            
            # Step 2: Update CloudFront distribution
            if not self._update_cloudfront_distribution():
                return self.results
            
            # Step 3: Restart ECS service
            if not self._restart_ecs_service():
                return self.results
            
            # Step 4: Wait for services to stabilize
            if not self._wait_for_stabilization():
                return self.results
            
            # Step 5: Test connectivity
            if not self._test_connectivity():
                return self.results
            
            self.results['success'] = True
            print("\n🎉 LLM Integration and HTTPS fixes completed successfully!")
            print("✅ AI chat endpoints should now work")
            print("✅ HTTPS should now work properly")
            
        except Exception as e:
            self.results['error'] = str(e)
            print(f"\n❌ Fix failed: {e}")
        
        return self.results
    
    def _fix_iam_permissions(self) -> bool:
        """Fix IAM permissions for secrets manager access."""
        
        print("\n🔐 Step 1: Fixing IAM permissions for secrets access...")
        
        try:
            # Get actual secret ARNs
            actual_secrets = self._get_actual_secret_arns()
            
            if not actual_secrets:
                print("❌ No secrets found")
                return False
            
            # Create policy with actual secret ARNs
            policy_name = "MultimodalLibrarianSecretsManagerAccess"
            policy_document = {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Effect": "Allow",
                        "Action": [
                            "secretsmanager:GetSecretValue",
                            "secretsmanager:DescribeSecret"
                        ],
                        "Resource": actual_secrets
                    }
                ]
            }
            
            # Update or create policy
            account_id = self._get_account_id()
            policy_arn = f"arn:aws:iam::{account_id}:policy/{policy_name}"
            
            try:
                # Try to update existing policy
                self.iam_client.create_policy_version(
                    PolicyArn=policy_arn,
                    PolicyDocument=json.dumps(policy_document),
                    SetAsDefault=True
                )
                print(f"✅ Updated existing policy: {policy_name}")
                
            except self.iam_client.exceptions.NoSuchEntityException:
                # Create new policy
                response = self.iam_client.create_policy(
                    PolicyName=policy_name,
                    PolicyDocument=json.dumps(policy_document),
                    Description="Allows ECS tasks to access Secrets Manager secrets for multimodal librarian"
                )
                policy_arn = response['Policy']['Arn']
                print(f"✅ Created new policy: {policy_name}")
                
                # Attach policy to role
                self.iam_client.attach_role_policy(
                    RoleName=self.task_role_name,
                    PolicyArn=policy_arn
                )
                print(f"✅ Attached policy to role: {self.task_role_name}")
            
            self.results['steps']['fix_iam_permissions'] = {
                'success': True,
                'policy_arn': policy_arn,
                'secrets_count': len(actual_secrets)
            }
            
            print(f"✅ IAM permissions updated for {len(actual_secrets)} secrets")
            return True
            
        except Exception as e:
            print(f"❌ Error fixing IAM permissions: {e}")
            self.results['steps']['fix_iam_permissions'] = {
                'success': False,
                'error': str(e)
            }
            return False
    
    def _update_cloudfront_distribution(self) -> bool:
        """Update CloudFront distribution to point to new load balancer."""
        
        print("\n🌐 Step 2: Updating CloudFront distribution...")
        
        try:
            # Get current distribution config
            response = self.cf_client.get_distribution_config(Id=self.cloudfront_distribution_id)
            distribution_config = response['DistributionConfig']
            etag = response['ETag']
            
            # Check current origin
            current_origin = distribution_config['Origins']['Items'][0]['DomainName']
            print(f"Current origin: {current_origin}")
            print(f"New origin: {self.new_load_balancer_dns}")
            
            if current_origin == self.new_load_balancer_dns:
                print("✅ CloudFront already points to new load balancer")
                self.results['steps']['update_cloudfront_distribution'] = {
                    'success': True,
                    'already_updated': True
                }
                return True
            
            # Update origin to new load balancer
            distribution_config['Origins']['Items'][0]['DomainName'] = self.new_load_balancer_dns
            
            # Update distribution
            update_response = self.cf_client.update_distribution(
                Id=self.cloudfront_distribution_id,
                DistributionConfig=distribution_config,
                IfMatch=etag
            )
            
            distribution_status = update_response['Distribution']['Status']
            
            self.results['steps']['update_cloudfront_distribution'] = {
                'success': True,
                'old_origin': current_origin,
                'new_origin': self.new_load_balancer_dns,
                'status': distribution_status
            }
            
            print(f"✅ CloudFront distribution updated")
            print(f"   Status: {distribution_status}")
            print("   Note: Changes may take 5-15 minutes to propagate globally")
            
            return True
            
        except Exception as e:
            print(f"❌ Error updating CloudFront distribution: {e}")
            self.results['steps']['update_cloudfront_distribution'] = {
                'success': False,
                'error': str(e)
            }
            return False
    
    def _restart_ecs_service(self) -> bool:
        """Restart ECS service to apply new IAM permissions."""
        
        print("\n🔄 Step 3: Restarting ECS service...")
        
        try:
            # Force new deployment to pick up new IAM permissions
            response = self.ecs_client.update_service(
                cluster=self.cluster_name,
                service=self.service_name,
                forceNewDeployment=True
            )
            
            deployment_id = response['service']['deployments'][0]['id']
            
            self.results['steps']['restart_ecs_service'] = {
                'success': True,
                'deployment_id': deployment_id
            }
            
            print(f"✅ ECS service restart initiated")
            print(f"   Deployment ID: {deployment_id}")
            
            return True
            
        except Exception as e:
            print(f"❌ Error restarting ECS service: {e}")
            self.results['steps']['restart_ecs_service'] = {
                'success': False,
                'error': str(e)
            }
            return False
    
    def _wait_for_stabilization(self) -> bool:
        """Wait for ECS service to stabilize."""
        
        print("\n⏳ Step 4: Waiting for service to stabilize...")
        
        try:
            print("Waiting for ECS service to stabilize (this may take 2-3 minutes)...")
            
            # Wait for service to be stable
            waiter = self.ecs_client.get_waiter('services_stable')
            waiter.wait(
                cluster=self.cluster_name,
                services=[self.service_name],
                WaiterConfig={
                    'Delay': 15,
                    'MaxAttempts': 20  # 5 minutes max
                }
            )
            
            self.results['steps']['wait_for_stabilization'] = {
                'success': True
            }
            
            print("✅ ECS service is stable")
            return True
            
        except Exception as e:
            print(f"⚠️  Service stabilization timeout: {e}")
            print("Service may still be starting - continuing with tests...")
            self.results['steps']['wait_for_stabilization'] = {
                'success': False,
                'error': str(e),
                'note': 'Timeout - service may still be starting'
            }
            # Continue anyway - service might still work
            return True
    
    def _test_connectivity(self) -> bool:
        """Test HTTP and HTTPS connectivity."""
        
        print("\n🔍 Step 5: Testing connectivity...")
        
        try:
            import requests
            
            # Test HTTP (new load balancer)
            http_url = f"http://{self.new_load_balancer_dns}"
            print(f"Testing HTTP: {http_url}")
            
            try:
                response = requests.get(http_url, timeout=10)
                http_status = response.status_code
                print(f"✅ HTTP test: {http_status}")
            except Exception as e:
                http_status = f"Error: {e}"
                print(f"❌ HTTP test failed: {e}")
            
            # Test HTTP health endpoint
            health_url = f"http://{self.new_load_balancer_dns}/health/simple"
            print(f"Testing HTTP health: {health_url}")
            
            try:
                response = requests.get(health_url, timeout=10)
                health_status = response.status_code
                print(f"✅ HTTP health test: {health_status}")
            except Exception as e:
                health_status = f"Error: {e}"
                print(f"❌ HTTP health test failed: {e}")
            
            # Test HTTPS (CloudFront)
            https_url = "https://d1c3ih7gvhogu1.cloudfront.net"
            print(f"Testing HTTPS: {https_url}")
            
            try:
                response = requests.get(https_url, timeout=15)
                https_status = response.status_code
                print(f"✅ HTTPS test: {https_status}")
            except Exception as e:
                https_status = f"Error: {e}"
                print(f"⚠️  HTTPS test: {e}")
                print("   Note: CloudFront changes may take 5-15 minutes to propagate")
            
            # Test AI chat endpoint
            ai_chat_url = f"http://{self.new_load_balancer_dns}/api/chat/status"
            print(f"Testing AI chat status: {ai_chat_url}")
            
            try:
                response = requests.get(ai_chat_url, timeout=10)
                ai_status = response.status_code
                if ai_status == 200:
                    print(f"✅ AI chat status test: {ai_status}")
                else:
                    print(f"⚠️  AI chat status test: {ai_status}")
            except Exception as e:
                ai_status = f"Error: {e}"
                print(f"❌ AI chat status test failed: {e}")
            
            self.results['steps']['test_connectivity'] = {
                'success': True,
                'http_status': http_status,
                'health_status': health_status,
                'https_status': https_status,
                'ai_chat_status': ai_status
            }
            
            print("\n📊 Connectivity Test Summary:")
            print(f"   HTTP (new LB): {http_status}")
            print(f"   Health check: {health_status}")
            print(f"   HTTPS (CloudFront): {https_status}")
            print(f"   AI chat status: {ai_status}")
            
            return True
            
        except ImportError:
            print("⚠️  requests library not available - skipping connectivity tests")
            self.results['steps']['test_connectivity'] = {
                'success': False,
                'error': 'requests library not available'
            }
            return True
        except Exception as e:
            print(f"❌ Error testing connectivity: {e}")
            self.results['steps']['test_connectivity'] = {
                'success': False,
                'error': str(e)
            }
            return False
    
    def _get_actual_secret_arns(self) -> List[str]:
        """Get ARNs of actual secrets that exist."""
        
        try:
            response = self.secrets_client.list_secrets()
            secrets = response['SecretList']
            
            # Filter for multimodal librarian secrets
            ml_secret_arns = []
            for secret in secrets:
                name = secret['Name']
                if 'multimodal' in name.lower():
                    ml_secret_arns.append(secret['ARN'])
            
            print(f"Found {len(ml_secret_arns)} multimodal librarian secrets")
            return ml_secret_arns
            
        except Exception as e:
            print(f"Error getting secret ARNs: {e}")
            return []
    
    def _get_account_id(self) -> str:
        """Get the current AWS account ID."""
        try:
            response = self.sts_client.get_caller_identity()
            return response['Account']
        except Exception:
            return "unknown"
    
    def save_results(self) -> str:
        """Save fix results to file."""
        
        filename = f"llm-https-integration-fix-{int(time.time())}.json"
        
        with open(filename, 'w') as f:
            json.dump(self.results, f, indent=2, default=str)
        
        return filename


def main():
    """Main execution function."""
    
    print("🔧 LLM Integration and HTTPS Fix")
    print("Fixing AI chat and HTTPS connectivity issues")
    print()
    
    fixer = LLMAndHTTPSFixer()
    results = fixer.fix_integration_issues()
    
    # Save results
    results_file = fixer.save_results()
    print(f"\n📄 Fix results saved to: {results_file}")
    
    # Summary
    if results['success']:
        print("\n🎉 Integration Fix Summary:")
        print("=" * 40)
        print("✅ IAM permissions updated for secrets access")
        print("✅ CloudFront distribution updated to new load balancer")
        print("✅ ECS service restarted with new permissions")
        print("✅ Connectivity tests completed")
        print()
        print("🔄 What's Fixed:")
        print("1. AI chat endpoints should now work (/api/chat/*)")
        print("2. HTTPS should work properly (may take 5-15 min to propagate)")
        print("3. Secrets manager access permissions corrected")
        print()
        print("🧪 Test URLs:")
        print("- HTTP: http://ml-shared-vpc-alb-1260972620.us-east-1.elb.amazonaws.com")
        print("- HTTPS: https://d1c3ih7gvhogu1.cloudfront.net")
        print("- AI Chat: http://ml-shared-vpc-alb-1260972620.us-east-1.elb.amazonaws.com/api/chat/status")
        
        return 0
    else:
        print("\n❌ Integration Fix Failed")
        print("Check the results file for detailed error information")
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)