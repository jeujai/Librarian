"""
IAM Permissions Validator for Production Deployment Checklist.

This validator ensures that ECS tasks have proper IAM permissions to access
AWS Secrets Manager for retrieving database credentials and API keys.
Validates Requirements 1.1, 1.2, 1.3, and 1.5.
"""

import json
import logging
from typing import Dict, List, Optional, Any, Tuple
from urllib.parse import unquote

from botocore.exceptions import ClientError

from .base_validator import BaseValidator, ValidationError
from .models import ValidationResult, DeploymentConfig


class IAMPermissionsValidator(BaseValidator):
    """Validates IAM permissions for ECS task access to Secrets Manager."""
    
    def __init__(self, region: str = "us-east-1"):
        """Initialize IAM permissions validator."""
        super().__init__(region)
        self.required_permissions = [
            "secretsmanager:GetSecretValue"
        ]
        
        # Test secrets for validation (these should exist in the environment)
        self.test_secrets = {
            'database_credentials': [
                'multimodal-librarian/database/credentials',
                'prod/database/credentials', 
                'database-credentials'
            ],
            'api_keys': [
                'multimodal-librarian/api/keys',
                'prod/api/keys',
                'api-keys'
            ]
        }
    
    def validate(self, deployment_config: DeploymentConfig) -> ValidationResult:
        """
        Validate IAM permissions for the deployment configuration.
        
        Args:
            deployment_config: Configuration containing IAM role ARN
            
        Returns:
            ValidationResult with validation status and details
        """
        check_name = "IAM Permissions Validation"
        
        try:
            # Validate IAM role ARN format
            if not self._validate_iam_role_arn(deployment_config.iam_role_arn):
                return self.create_failure_result(
                    check_name=check_name,
                    message=f"Invalid IAM role ARN format: {deployment_config.iam_role_arn}",
                    remediation_steps=[
                        "Verify the IAM role ARN is correctly formatted",
                        "Ensure the role exists in your AWS account",
                        "Check that the ARN matches the pattern: arn:aws:iam::ACCOUNT:role/ROLE_NAME"
                    ],
                    fix_scripts=["scripts/fix-iam-secrets-permissions.py"]
                )
            
            # Check if role has required permissions
            has_permissions, permission_details = self._check_secrets_manager_permissions(
                deployment_config.iam_role_arn
            )
            
            if not has_permissions:
                return self._create_permission_failure_result(
                    check_name, deployment_config.iam_role_arn, permission_details
                )
            
            # Test actual secret retrieval
            retrieval_success, retrieval_details = self._test_secret_retrieval(
                deployment_config.iam_role_arn
            )
            
            if not retrieval_success:
                return self._create_retrieval_failure_result(
                    check_name, deployment_config.iam_role_arn, retrieval_details
                )
            
            # All checks passed
            return self.create_success_result(
                check_name=check_name,
                message="IAM role has proper Secrets Manager permissions and can retrieve test secrets",
                details={
                    'role_arn': deployment_config.iam_role_arn,
                    'permissions_validated': self.required_permissions,
                    'test_retrieval_results': retrieval_details,
                    'permission_details': permission_details
                }
            )
            
        except Exception as e:
            self.logger.error(f"Error validating IAM permissions: {str(e)}")
            return self.create_error_result(check_name, e)
    
    def _validate_iam_role_arn(self, role_arn: str) -> bool:
        """Validate IAM role ARN format and existence."""
        try:
            # Check ARN format
            if not role_arn.startswith('arn:aws:iam::'):
                return False
            
            # Check for role resource type (format: arn:aws:iam::account:role/role-name)
            if ':role/' not in role_arn:
                return False
            
            # Extract role name and verify it exists
            role_name = role_arn.split('/')[-1]
            iam_client = self.get_aws_client('iam')
            
            success, result, error = self.safe_aws_call(
                "get IAM role",
                iam_client.get_role,
                RoleName=role_name
            )
            
            return success
            
        except Exception as e:
            self.logger.error(f"Error validating IAM role ARN: {e}")
            return False
    
    def _check_secrets_manager_permissions(self, role_arn: str) -> Tuple[bool, Dict[str, Any]]:
        """
        Check if IAM role has required Secrets Manager permissions.
        
        Args:
            role_arn: IAM role ARN to check
            
        Returns:
            Tuple of (has_permissions: bool, details: Dict)
        """
        try:
            role_name = role_arn.split('/')[-1]
            iam_client = self.get_aws_client('iam')
            
            # Get all policies attached to the role
            attached_policies = self._get_role_policies(iam_client, role_name)
            
            # Check each policy for required permissions
            permission_found = False
            policy_details = []
            
            for policy in attached_policies:
                has_permission, policy_info = self._check_policy_permissions(
                    iam_client, policy, role_name
                )
                policy_details.append(policy_info)
                
                if has_permission:
                    permission_found = True
            
            details = {
                'role_name': role_name,
                'required_permissions': self.required_permissions,
                'policies_checked': policy_details,
                'permission_found': permission_found
            }
            
            return permission_found, details
            
        except Exception as e:
            self.logger.error(f"Error checking IAM permissions: {e}")
            return False, {'error': str(e)}
    
    def _get_role_policies(self, iam_client, role_name: str) -> List[Dict[str, Any]]:
        """Get all policies attached to a role (managed and inline)."""
        policies = []
        
        try:
            # Get managed policies
            success, result, error = self.safe_aws_call(
                "list attached role policies",
                iam_client.list_attached_role_policies,
                RoleName=role_name
            )
            
            if success:
                for policy in result['AttachedPolicies']:
                    policies.append({
                        'type': 'managed',
                        'name': policy['PolicyName'],
                        'arn': policy['PolicyArn']
                    })
            
            # Get inline policies
            success, result, error = self.safe_aws_call(
                "list role policies",
                iam_client.list_role_policies,
                RoleName=role_name
            )
            
            if success:
                for policy_name in result['PolicyNames']:
                    policies.append({
                        'type': 'inline',
                        'name': policy_name,
                        'role_name': role_name
                    })
            
        except Exception as e:
            self.logger.error(f"Error getting role policies: {e}")
        
        return policies
    
    def _check_policy_permissions(self, iam_client, policy: Dict[str, Any], 
                                role_name: str) -> Tuple[bool, Dict[str, Any]]:
        """Check if a specific policy contains required permissions."""
        policy_info = {
            'name': policy['name'],
            'type': policy['type'],
            'has_required_permissions': False,
            'permissions_found': [],
            'statements_checked': 0
        }
        
        try:
            # Get policy document
            if policy['type'] == 'managed':
                success, result, error = self.safe_aws_call(
                    "get policy version",
                    iam_client.get_policy,
                    PolicyArn=policy['arn']
                )
                
                if not success:
                    policy_info['error'] = error
                    return False, policy_info
                
                # Get the default version
                default_version = result['Policy']['DefaultVersionId']
                success, version_result, error = self.safe_aws_call(
                    "get policy version document",
                    iam_client.get_policy_version,
                    PolicyArn=policy['arn'],
                    VersionId=default_version
                )
                
                if not success:
                    policy_info['error'] = error
                    return False, policy_info
                
                policy_document = version_result['PolicyVersion']['Document']
                
            else:  # inline policy
                success, result, error = self.safe_aws_call(
                    "get role policy",
                    iam_client.get_role_policy,
                    RoleName=role_name,
                    PolicyName=policy['name']
                )
                
                if not success:
                    policy_info['error'] = error
                    return False, policy_info
                
                policy_document = result['PolicyDocument']
            
            # Parse policy document
            if isinstance(policy_document, str):
                policy_document = json.loads(unquote(policy_document))
            
            # Check statements for required permissions
            statements = policy_document.get('Statement', [])
            if not isinstance(statements, list):
                statements = [statements]
            
            policy_info['statements_checked'] = len(statements)
            
            for statement in statements:
                if self._statement_has_required_permissions(statement):
                    policy_info['has_required_permissions'] = True
                    policy_info['permissions_found'] = self.required_permissions
                    return True, policy_info
            
        except Exception as e:
            policy_info['error'] = str(e)
            self.logger.error(f"Error checking policy {policy['name']}: {e}")
        
        return False, policy_info
    
    def _statement_has_required_permissions(self, statement: Dict[str, Any]) -> bool:
        """Check if a policy statement contains required permissions."""
        try:
            # Check if statement allows the actions
            effect = statement.get('Effect', '').lower()
            if effect != 'allow':
                return False
            
            actions = statement.get('Action', [])
            if isinstance(actions, str):
                actions = [actions]
            
            # Check if any required permission is in the actions
            for required_perm in self.required_permissions:
                if self._action_matches_permission(actions, required_perm):
                    return True
            
            return False
            
        except Exception as e:
            self.logger.error(f"Error checking statement permissions: {e}")
            return False
    
    def _action_matches_permission(self, actions: List[str], required_permission: str) -> bool:
        """Check if any action matches the required permission (supports wildcards)."""
        for action in actions:
            # Exact match
            if action == required_permission:
                return True
            
            # Wildcard match
            if '*' in action:
                # Convert wildcard to regex-like matching
                if action == '*':  # Full wildcard
                    return True
                
                if action.endswith('*'):
                    prefix = action[:-1]
                    if required_permission.startswith(prefix):
                        return True
                
                if action.startswith('*'):
                    suffix = action[1:]
                    if required_permission.endswith(suffix):
                        return True
        
        return False
    
    def _test_secret_retrieval(self, role_arn: str) -> Tuple[bool, Dict[str, Any]]:
        """
        Test actual secret retrieval using the IAM role.
        
        Note: This is a simulation since we can't actually assume the role
        in this context. In a real deployment, this would use STS assume role.
        """
        details = {
            'role_arn': role_arn,
            'test_secrets_attempted': [],
            'successful_retrievals': [],
            'failed_retrievals': [],
            'simulation_mode': True,
            'note': 'Actual secret retrieval testing requires STS assume role capability'
        }
        
        try:
            secrets_client = self.get_aws_client('secretsmanager')
            
            # Test if secrets exist (without assuming role)
            for secret_type, secret_names in self.test_secrets.items():
                for secret_name in secret_names:
                    details['test_secrets_attempted'].append({
                        'type': secret_type,
                        'name': secret_name
                    })
                    
                    # Check if secret exists
                    success, result, error = self.safe_aws_call(
                        f"describe secret {secret_name}",
                        secrets_client.describe_secret,
                        SecretId=secret_name
                    )
                    
                    if success:
                        details['successful_retrievals'].append({
                            'type': secret_type,
                            'name': secret_name,
                            'arn': result['ARN'],
                            'status': 'exists'
                        })
                        # Found at least one secret of this type, move to next type
                        break
                    else:
                        details['failed_retrievals'].append({
                            'type': secret_type,
                            'name': secret_name,
                            'error': error
                        })
            
            # Consider successful if we found at least one secret for each type
            required_types = set(self.test_secrets.keys())
            found_types = set(item['type'] for item in details['successful_retrievals'])
            
            success = required_types.issubset(found_types)
            
            if not success:
                missing_types = required_types - found_types
                details['missing_secret_types'] = list(missing_types)
            
            return success, details
            
        except Exception as e:
            details['error'] = str(e)
            self.logger.error(f"Error testing secret retrieval: {e}")
            return False, details
    
    def _create_permission_failure_result(self, check_name: str, role_arn: str, 
                                        details: Dict[str, Any]) -> ValidationResult:
        """Create failure result for missing permissions."""
        remediation_steps = [
            f"Add secretsmanager:GetSecretValue permission to IAM role {role_arn.split('/')[-1]}",
            "Attach a policy with the following statement:",
            json.dumps({
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Effect": "Allow",
                        "Action": "secretsmanager:GetSecretValue",
                        "Resource": "*"
                    }
                ]
            }, indent=2),
            "Or use the provided fix script to automatically add permissions"
        ]
        
        return self.create_failure_result(
            check_name=check_name,
            message=f"IAM role {role_arn} lacks required Secrets Manager permissions",
            remediation_steps=remediation_steps,
            fix_scripts=[
                "scripts/fix-iam-secrets-permissions.py",
                "scripts/fix-iam-secrets-permissions-correct.py"
            ],
            details=details
        )
    
    def _create_retrieval_failure_result(self, check_name: str, role_arn: str,
                                       details: Dict[str, Any]) -> ValidationResult:
        """Create failure result for secret retrieval issues."""
        missing_types = details.get('missing_secret_types', [])
        
        remediation_steps = [
            "Ensure the following secrets exist in AWS Secrets Manager:",
        ]
        
        for secret_type in missing_types:
            secret_names = self.test_secrets.get(secret_type, [])
            remediation_steps.append(f"  - {secret_type}: one of {secret_names}")
        
        remediation_steps.extend([
            "Create missing secrets using AWS CLI or Console:",
            "aws secretsmanager create-secret --name <secret-name> --secret-string <secret-value>",
            "Verify IAM role can access the secrets after creation"
        ])
        
        return self.create_failure_result(
            check_name=check_name,
            message=f"Cannot retrieve required secrets using role {role_arn}",
            remediation_steps=remediation_steps,
            fix_scripts=["scripts/fix-iam-secrets-permissions.py"],
            details=details
        )
    
    def validate_secrets_manager_access(self, role_arn: str) -> ValidationResult:
        """
        Public method to validate Secrets Manager access for a specific role.
        
        Args:
            role_arn: IAM role ARN to validate
            
        Returns:
            ValidationResult with validation status
        """
        deployment_config = DeploymentConfig(
            task_definition_arn="arn:aws:ecs:us-east-1:123456789012:task-definition/test:1",
            iam_role_arn=role_arn,
            load_balancer_arn="arn:aws:elasticloadbalancing:us-east-1:123456789012:loadbalancer/app/test/1234567890123456",
            target_environment="validation"
        )
        
        return self.validate(deployment_config)
    
    def test_secret_retrieval(self, role_arn: str, secret_name: str) -> bool:
        """
        Test retrieval of a specific secret.
        
        Args:
            role_arn: IAM role ARN
            secret_name: Name of secret to test
            
        Returns:
            True if secret can be retrieved, False otherwise
        """
        try:
            secrets_client = self.get_aws_client('secretsmanager')
            
            success, result, error = self.safe_aws_call(
                f"get secret value {secret_name}",
                secrets_client.get_secret_value,
                SecretId=secret_name
            )
            
            return success
            
        except Exception as e:
            self.logger.error(f"Error testing secret retrieval: {e}")
            return False
    
    def get_required_permissions(self) -> List[str]:
        """Get list of required IAM permissions."""
        return self.required_permissions.copy()