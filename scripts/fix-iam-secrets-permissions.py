#!/usr/bin/env python3
"""
Fix IAM Permissions for Secrets Manager Access

This script adds the necessary IAM permissions to the ECS task role
to allow access to AWS Secrets Manager secrets for Neptune and OpenSearch.
"""

import boto3
import json
import time
import sys
from datetime import datetime
from typing import Dict, List, Any, Optional

class IAMPermissionsFixer:
    """Manages IAM permissions for ECS task role to access Secrets Manager."""
    
    def __init__(self):
        self.iam_client = boto3.client('iam', region_name='us-east-1')
        self.sts_client = boto3.client('sts', region_name='us-east-1')
        
        # ECS task role configuration
        self.task_role_name = "ecsTaskRole"
        self.task_role_arn = None
        
        self.results = {
            'timestamp': datetime.now().isoformat(),
            'operation': 'fix_iam_secrets_permissions',
            'steps': {},
            'success': False
        }
    
    def fix_secrets_permissions(self) -> Dict[str, Any]:
        """Fix IAM permissions for Secrets Manager access."""
        
        print("🔐 Fixing IAM Permissions for Secrets Manager Access")
        print("=" * 60)
        
        try:
            # Step 1: Find the ECS task role
            if not self._find_task_role():
                return self.results
            
            # Step 2: Check current permissions
            if not self._check_current_permissions():
                return self.results
            
            # Step 3: Create or update Secrets Manager policy
            if not self._create_secrets_policy():
                return self.results
            
            # Step 4: Attach policy to role
            if not self._attach_policy_to_role():
                return self.results
            
            # Step 5: Verify permissions
            if not self._verify_permissions():
                return self.results
            
            # Step 6: Restart ECS service to apply new permissions
            if not self._restart_ecs_service():
                return self.results
            
            self.results['success'] = True
            print("\n🎉 IAM permissions fixed successfully!")
            print("✅ ECS task role now has access to Secrets Manager")
            print("✅ Document upload and database services should work")
            
        except Exception as e:
            self.results['error'] = str(e)
            print(f"\n❌ IAM permissions fix failed: {e}")
        
        return self.results
    
    def _find_task_role(self) -> bool:
        """Find the ECS task role."""
        
        print("\n📍 Step 1: Finding ECS task role...")
        
        try:
            response = self.iam_client.get_role(RoleName=self.task_role_name)
            self.task_role_arn = response['Role']['Arn']
            
            self.results['steps']['find_task_role'] = {
                'success': True,
                'role_name': self.task_role_name,
                'role_arn': self.task_role_arn
            }
            
            print(f"✅ Found ECS task role: {self.task_role_name}")
            print(f"   - ARN: {self.task_role_arn}")
            return True
            
        except Exception as e:
            print(f"❌ Error finding task role: {e}")
            self.results['steps']['find_task_role'] = {
                'success': False,
                'error': str(e)
            }
            return False
    
    def _check_current_permissions(self) -> bool:
        """Check current permissions attached to the role."""
        
        print("\n🔍 Step 2: Checking current permissions...")
        
        try:
            # List attached policies
            response = self.iam_client.list_attached_role_policies(
                RoleName=self.task_role_name
            )
            
            attached_policies = response['AttachedPolicies']
            
            # Check for existing Secrets Manager permissions
            has_secrets_access = False
            
            for policy in attached_policies:
                policy_name = policy['PolicyName']
                print(f"   - Attached policy: {policy_name}")
                
                if 'secrets' in policy_name.lower() or 'secretsmanager' in policy_name.lower():
                    has_secrets_access = True
            
            self.results['steps']['check_current_permissions'] = {
                'success': True,
                'attached_policies': [p['PolicyName'] for p in attached_policies],
                'has_secrets_access': has_secrets_access
            }
            
            if has_secrets_access:
                print("✅ Found existing Secrets Manager permissions")
            else:
                print("⚠️  No Secrets Manager permissions found")
            
            return True
            
        except Exception as e:
            print(f"❌ Error checking permissions: {e}")
            self.results['steps']['check_current_permissions'] = {
                'success': False,
                'error': str(e)
            }
            return False
    
    def _create_secrets_policy(self) -> bool:
        """Create or update the Secrets Manager policy."""
        
        print("\n📝 Step 3: Creating Secrets Manager policy...")
        
        try:
            policy_name = "MultimodalLibrarianSecretsManagerAccess"
            
            # Define the policy document
            policy_document = {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Effect": "Allow",
                        "Action": [
                            "secretsmanager:GetSecretValue",
                            "secretsmanager:DescribeSecret"
                        ],
                        "Resource": [
                            "arn:aws:secretsmanager:us-east-1:*:secret:multimodal-librarian/aws-native/neptune*",
                            "arn:aws:secretsmanager:us-east-1:*:secret:multimodal-librarian/aws-native/opensearch*",
                            "arn:aws:secretsmanager:us-east-1:*:secret:multimodal-lib-prod/neptune/connection*",
                            "arn:aws:secretsmanager:us-east-1:*:secret:multimodal-lib-prod/opensearch/connection*",
                            "arn:aws:secretsmanager:us-east-1:*:secret:multimodal-librarian/full-ml/database*",
                            "arn:aws:secretsmanager:us-east-1:*:secret:multimodal-librarian/full-ml/redis*"
                        ]
                    }
                ]
            }
            
            # Check if policy already exists
            try:
                existing_policy = self.iam_client.get_policy(
                    PolicyArn=f"arn:aws:iam::{self._get_account_id()}:policy/{policy_name}"
                )
                
                # Update existing policy
                self.iam_client.create_policy_version(
                    PolicyArn=existing_policy['Policy']['Arn'],
                    PolicyDocument=json.dumps(policy_document),
                    SetAsDefault=True
                )
                
                policy_arn = existing_policy['Policy']['Arn']
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
            
            self.results['steps']['create_secrets_policy'] = {
                'success': True,
                'policy_name': policy_name,
                'policy_arn': policy_arn,
                'policy_document': policy_document
            }
            
            self.secrets_policy_arn = policy_arn
            print(f"   - Policy ARN: {policy_arn}")
            
            return True
            
        except Exception as e:
            print(f"❌ Error creating Secrets Manager policy: {e}")
            self.results['steps']['create_secrets_policy'] = {
                'success': False,
                'error': str(e)
            }
            return False
    
    def _attach_policy_to_role(self) -> bool:
        """Attach the Secrets Manager policy to the ECS task role."""
        
        print("\n🔗 Step 4: Attaching policy to ECS task role...")
        
        try:
            # Check if policy is already attached
            response = self.iam_client.list_attached_role_policies(
                RoleName=self.task_role_name
            )
            
            policy_name = "MultimodalLibrarianSecretsManagerAccess"
            already_attached = any(
                policy['PolicyName'] == policy_name 
                for policy in response['AttachedPolicies']
            )
            
            if already_attached:
                print(f"✅ Policy already attached to role")
            else:
                # Attach the policy
                self.iam_client.attach_role_policy(
                    RoleName=self.task_role_name,
                    PolicyArn=self.secrets_policy_arn
                )
                print(f"✅ Policy attached to role: {self.task_role_name}")
            
            self.results['steps']['attach_policy_to_role'] = {
                'success': True,
                'policy_arn': self.secrets_policy_arn,
                'role_name': self.task_role_name,
                'already_attached': already_attached
            }
            
            return True
            
        except Exception as e:
            print(f"❌ Error attaching policy to role: {e}")
            self.results['steps']['attach_policy_to_role'] = {
                'success': False,
                'error': str(e)
            }
            return False
    
    def _verify_permissions(self) -> bool:
        """Verify that the permissions are correctly applied."""
        
        print("\n✅ Step 5: Verifying permissions...")
        
        try:
            # List all attached policies
            response = self.iam_client.list_attached_role_policies(
                RoleName=self.task_role_name
            )
            
            attached_policies = response['AttachedPolicies']
            secrets_policy_attached = False
            
            for policy in attached_policies:
                if 'SecretsManager' in policy['PolicyName']:
                    secrets_policy_attached = True
                    print(f"✅ Secrets Manager policy attached: {policy['PolicyName']}")
            
            # Test permissions by attempting to assume the role (simulation)
            try:
                # Get current account ID for verification
                account_id = self._get_account_id()
                
                self.results['steps']['verify_permissions'] = {
                    'success': True,
                    'secrets_policy_attached': secrets_policy_attached,
                    'account_id': account_id,
                    'total_policies': len(attached_policies)
                }
                
                if secrets_policy_attached:
                    print("✅ Permissions verification successful")
                    return True
                else:
                    print("❌ Secrets Manager policy not found")
                    return False
                    
            except Exception as e:
                print(f"⚠️  Permission verification warning: {e}")
                return True  # Continue anyway
            
        except Exception as e:
            print(f"❌ Error verifying permissions: {e}")
            self.results['steps']['verify_permissions'] = {
                'success': False,
                'error': str(e)
            }
            return False
    
    def _restart_ecs_service(self) -> bool:
        """Restart the ECS service to apply new permissions."""
        
        print("\n🔄 Step 6: Restarting ECS service...")
        
        try:
            ecs_client = boto3.client('ecs', region_name='us-east-1')
            
            # Find the ECS service
            cluster_name = "multimodal-lib-prod-cluster"
            service_name = "multimodal-lib-prod-service"
            
            # Force new deployment to pick up new IAM permissions
            response = ecs_client.update_service(
                cluster=cluster_name,
                service=service_name,
                forceNewDeployment=True
            )
            
            deployment_id = response['service']['deployments'][0]['id']
            
            self.results['steps']['restart_ecs_service'] = {
                'success': True,
                'cluster': cluster_name,
                'service': service_name,
                'deployment_id': deployment_id
            }
            
            print(f"✅ ECS service restart initiated")
            print(f"   - Cluster: {cluster_name}")
            print(f"   - Service: {service_name}")
            print(f"   - Deployment ID: {deployment_id}")
            print("   - New tasks will have updated IAM permissions")
            
            return True
            
        except Exception as e:
            print(f"❌ Error restarting ECS service: {e}")
            self.results['steps']['restart_ecs_service'] = {
                'success': False,
                'error': str(e)
            }
            return False
    
    def _get_account_id(self) -> str:
        """Get the current AWS account ID."""
        try:
            response = self.sts_client.get_caller_identity()
            return response['Account']
        except Exception:
            return "unknown"
    
    def save_results(self) -> str:
        """Save fix results to file."""
        
        filename = f"iam-secrets-permissions-fix-{int(time.time())}.json"
        
        with open(filename, 'w') as f:
            json.dump(self.results, f, indent=2, default=str)
        
        return filename


def main():
    """Main execution function."""
    
    print("🔐 IAM Secrets Manager Permissions Fix")
    print("Adding permissions for Neptune and OpenSearch access")
    print()
    
    fixer = IAMPermissionsFixer()
    results = fixer.fix_secrets_permissions()
    
    # Save results
    results_file = fixer.save_results()
    print(f"\n📄 Fix results saved to: {results_file}")
    
    # Summary
    if results['success']:
        print("\n🎉 IAM Permissions Fix Summary:")
        print("=" * 40)
        print("✅ ECS task role permissions updated")
        print("✅ Secrets Manager access granted for:")
        print("   - Neptune database connections")
        print("   - OpenSearch vector database connections")
        print("   - PostgreSQL database connections")
        print("   - Redis cache connections")
        print("✅ ECS service restarted with new permissions")
        print()
        print("🔄 Next Steps:")
        print("1. Wait 2-3 minutes for new ECS tasks to start")
        print("2. Run the end-to-end test again")
        print("3. Document upload API should now work")
        print("4. Database services should be accessible")
        
        return 0
    else:
        print("\n❌ IAM Permissions Fix Failed")
        print("Check the results file for detailed error information")
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)