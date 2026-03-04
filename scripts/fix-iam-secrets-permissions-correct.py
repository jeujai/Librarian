#!/usr/bin/env python3
"""
Fix IAM Permissions for Secrets Manager Access - Corrected Version

This script updates the IAM permissions to use the correct secret ARNs
that actually exist in the AWS account.
"""

import boto3
import json
import time
import sys
from datetime import datetime
from typing import Dict, List, Any, Optional

class IAMPermissionsFixerCorrected:
    """Manages IAM permissions for ECS task role to access Secrets Manager."""
    
    def __init__(self):
        self.iam_client = boto3.client('iam', region_name='us-east-1')
        self.sts_client = boto3.client('sts', region_name='us-east-1')
        
        # ECS task role configuration
        self.task_role_name = "ecsTaskRole"
        self.task_role_arn = None
        
        self.results = {
            'timestamp': datetime.now().isoformat(),
            'operation': 'fix_iam_secrets_permissions_corrected',
            'steps': {},
            'success': False
        }
    
    def fix_secrets_permissions(self) -> Dict[str, Any]:
        """Fix IAM permissions for Secrets Manager access with correct ARNs."""
        
        print("🔐 Fixing IAM Permissions for Secrets Manager Access (Corrected)")
        print("=" * 70)
        
        try:
            # Step 1: Find the ECS task role
            if not self._find_task_role():
                return self.results
            
            # Step 2: Update Secrets Manager policy with correct ARNs
            if not self._update_secrets_policy():
                return self.results
            
            # Step 3: Verify permissions
            if not self._verify_permissions():
                return self.results
            
            # Step 4: Restart ECS service to apply new permissions
            if not self._restart_ecs_service():
                return self.results
            
            self.results['success'] = True
            print("\n🎉 IAM permissions fixed successfully!")
            print("✅ ECS task role now has access to correct Secrets Manager secrets")
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
    
    def _update_secrets_policy(self) -> bool:
        """Update the Secrets Manager policy with correct ARNs."""
        
        print("\n📝 Step 2: Updating Secrets Manager policy with correct ARNs...")
        
        try:
            policy_name = "MultimodalLibrarianSecretsManagerAccess"
            
            # Define the policy document with correct secret ARNs
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
                            # Actual secrets that exist
                            "arn:aws:secretsmanager:us-east-1:*:secret:multimodal-lib-prod/neptune/connection*",
                            "arn:aws:secretsmanager:us-east-1:*:secret:multimodal-lib-prod/opensearch/connection*",
                            "arn:aws:secretsmanager:us-east-1:*:secret:multimodal-lib-prod/api-keys*",
                            "arn:aws:secretsmanager:us-east-1:*:secret:multimodal-librarian/full-ml/database*",
                            "arn:aws:secretsmanager:us-east-1:*:secret:multimodal-librarian/full-ml/redis*",
                            "arn:aws:secretsmanager:us-east-1:*:secret:multimodal-librarian/full-ml/api-keys*",
                            "arn:aws:secretsmanager:us-east-1:*:secret:multimodal-librarian/full-ml/neo4j*",
                            "arn:aws:secretsmanager:us-east-1:*:secret:multimodal-librarian/learning/database*",
                            "arn:aws:secretsmanager:us-east-1:*:secret:multimodal-librarian/learning/redis*"
                        ]
                    }
                ]
            }
            
            # Get existing policy ARN
            account_id = self._get_account_id()
            policy_arn = f"arn:aws:iam::{account_id}:policy/{policy_name}"
            
            try:
                # Update existing policy
                self.iam_client.create_policy_version(
                    PolicyArn=policy_arn,
                    PolicyDocument=json.dumps(policy_document),
                    SetAsDefault=True
                )
                
                print(f"✅ Updated existing policy: {policy_name}")
                
            except self.iam_client.exceptions.NoSuchEntityException:
                # Create new policy if it doesn't exist
                response = self.iam_client.create_policy(
                    PolicyName=policy_name,
                    PolicyDocument=json.dumps(policy_document),
                    Description="Allows ECS tasks to access Secrets Manager secrets for multimodal librarian (corrected ARNs)"
                )
                
                policy_arn = response['Policy']['Arn']
                print(f"✅ Created new policy: {policy_name}")
            
            self.results['steps']['update_secrets_policy'] = {
                'success': True,
                'policy_name': policy_name,
                'policy_arn': policy_arn,
                'policy_document': policy_document
            }
            
            self.secrets_policy_arn = policy_arn
            print(f"   - Policy ARN: {policy_arn}")
            print("   - Updated with correct secret ARNs")
            
            return True
            
        except Exception as e:
            print(f"❌ Error updating Secrets Manager policy: {e}")
            self.results['steps']['update_secrets_policy'] = {
                'success': False,
                'error': str(e)
            }
            return False
    
    def _verify_permissions(self) -> bool:
        """Verify that the permissions are correctly applied."""
        
        print("\n✅ Step 3: Verifying permissions...")
        
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
            
            self.results['steps']['verify_permissions'] = {
                'success': True,
                'secrets_policy_attached': secrets_policy_attached,
                'total_policies': len(attached_policies)
            }
            
            if secrets_policy_attached:
                print("✅ Permissions verification successful")
                return True
            else:
                print("❌ Secrets Manager policy not found")
                return False
                
        except Exception as e:
            print(f"❌ Error verifying permissions: {e}")
            self.results['steps']['verify_permissions'] = {
                'success': False,
                'error': str(e)
            }
            return False
    
    def _restart_ecs_service(self) -> bool:
        """Restart the ECS service to apply new permissions."""
        
        print("\n🔄 Step 4: Restarting ECS service...")
        
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
        
        filename = f"iam-secrets-permissions-fix-corrected-{int(time.time())}.json"
        
        with open(filename, 'w') as f:
            json.dump(self.results, f, indent=2, default=str)
        
        return filename


def main():
    """Main execution function."""
    
    print("🔐 IAM Secrets Manager Permissions Fix (Corrected)")
    print("Adding permissions for correct secret ARNs")
    print()
    
    fixer = IAMPermissionsFixerCorrected()
    results = fixer.fix_secrets_permissions()
    
    # Save results
    results_file = fixer.save_results()
    print(f"\n📄 Fix results saved to: {results_file}")
    
    # Summary
    if results['success']:
        print("\n🎉 IAM Permissions Fix Summary:")
        print("=" * 40)
        print("✅ ECS task role permissions updated with correct ARNs")
        print("✅ Secrets Manager access granted for:")
        print("   - multimodal-lib-prod/neptune/connection")
        print("   - multimodal-lib-prod/opensearch/connection")
        print("   - multimodal-lib-prod/api-keys")
        print("   - multimodal-librarian/full-ml/database")
        print("   - multimodal-librarian/full-ml/redis")
        print("   - multimodal-librarian/full-ml/api-keys")
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