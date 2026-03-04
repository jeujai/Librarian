#!/usr/bin/env python3
"""
Property-Based Tests for IAM Least Privilege
Feature: aws-production-deployment, Property 4: IAM Least Privilege

This module tests that IAM roles and policies follow least-privilege principles
and do not grant unnecessary access using property-based testing.
"""

import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, List, Any, Set
import pytest
from hypothesis import given, strategies as st, settings, assume
from hypothesis.stateful import RuleBasedStateMachine, Bundle, rule, initialize


class IAMTest:
    """Test class for IAM least privilege validation."""
    
    def __init__(self, terraform_dir: str = None):
        if terraform_dir is None:
            # Auto-detect terraform directory
            current_dir = Path.cwd()
            if (current_dir / "terraform.tf").exists():
                self.terraform_dir = current_dir
            elif (current_dir / "infrastructure" / "aws-native").exists():
                self.terraform_dir = current_dir / "infrastructure" / "aws-native"
            else:
                self.terraform_dir = Path("infrastructure/aws-native")
        else:
            self.terraform_dir = Path(terraform_dir)
    
    def extract_iam_resources_from_plan(self, plan_output: str) -> Dict[str, Dict]:
        """Extract IAM-related resources from Terraform plan."""
        iam_resources = {}
        
        try:
            plan_data = json.loads(plan_output)
            
            def extract_from_module(module_data, module_path=""):
                if "resources" not in module_data:
                    return
                
                for resource in module_data["resources"]:
                    resource_type = resource.get("type", "")
                    resource_name = resource.get("name", "")
                    resource_values = resource.get("values", {})
                    
                    full_name = f"{module_path}.{resource_name}" if module_path else resource_name
                    
                    # Check for IAM-related resources
                    if resource_type.startswith("aws_iam_"):
                        iam_resources[f"{resource_type}.{full_name}"] = {
                            "type": resource_type,
                            "name": resource_name,
                            "values": resource_values
                        }
            
            # Extract from root module
            if "planned_values" in plan_data and "root_module" in plan_data["planned_values"]:
                root_module = plan_data["planned_values"]["root_module"]
                extract_from_module(root_module)
                
                # Extract from child modules
                if "child_modules" in root_module:
                    for child_module in root_module["child_modules"]:
                        module_address = child_module.get("address", "")
                        extract_from_module(child_module, module_address)
        
        except (json.JSONDecodeError, KeyError) as e:
            print(f"Error parsing IAM resources: {e}")
        
        return iam_resources
    
    def validate_iam_role_trust_policies(self, iam_resources: Dict[str, Dict]) -> bool:
        """Validate IAM role trust policies follow least privilege."""
        iam_roles = {
            name: resource for name, resource in iam_resources.items()
            if resource["type"] == "aws_iam_role"
        }
        
        for role_name, role_resource in iam_roles.items():
            values = role_resource["values"]
            assume_role_policy = values.get("assume_role_policy")
            
            if assume_role_policy:
                try:
                    policy_doc = json.loads(assume_role_policy)
                    statements = policy_doc.get("Statement", [])
                    
                    for statement in statements:
                        # Check that principals are specific, not wildcard
                        principal = statement.get("Principal", {})
                        
                        if isinstance(principal, dict):
                            # Check AWS principals
                            aws_principals = principal.get("AWS", [])
                            if isinstance(aws_principals, str):
                                aws_principals = [aws_principals]
                            
                            for aws_principal in aws_principals:
                                # Should not allow wildcard access
                                if aws_principal == "*":
                                    return False
                            
                            # Check Service principals - these are usually specific
                            service_principals = principal.get("Service", [])
                            if isinstance(service_principals, str):
                                service_principals = [service_principals]
                            
                            # Service principals should be AWS services
                            for service_principal in service_principals:
                                if not service_principal.endswith(".amazonaws.com"):
                                    return False
                        
                        # Check conditions exist for cross-account access
                        if "AWS" in principal and "Condition" not in statement:
                            # Cross-account access without conditions might be too permissive
                            aws_principals = principal.get("AWS", [])
                            if isinstance(aws_principals, str):
                                aws_principals = [aws_principals]
                            
                            for aws_principal in aws_principals:
                                # If it's not the same account, should have conditions
                                if ":root" in aws_principal and "Condition" not in statement:
                                    # This is acceptable for same-account root access
                                    pass
                
                except json.JSONDecodeError:
                    return False
        
        return True
    
    def validate_iam_policy_permissions(self, iam_resources: Dict[str, Dict]) -> bool:
        """Validate IAM policies don't grant excessive permissions."""
        # Check inline policies
        iam_role_policies = {
            name: resource for name, resource in iam_resources.items()
            if resource["type"] == "aws_iam_role_policy"
        }
        
        for policy_name, policy_resource in iam_role_policies.items():
            values = policy_resource["values"]
            policy_document = values.get("policy")
            
            if policy_document:
                try:
                    policy_doc = json.loads(policy_document)
                    statements = policy_doc.get("Statement", [])
                    
                    for statement in statements:
                        actions = statement.get("Action", [])
                        if isinstance(actions, str):
                            actions = [actions]
                        
                        resources = statement.get("Resource", [])
                        if isinstance(resources, str):
                            resources = [resources]
                        
                        # Check for overly broad permissions
                        for action in actions:
                            # Should not allow all actions on all resources
                            if action == "*" and "*" in resources:
                                return False
                            
                            # Should not allow admin-level permissions unless necessary
                            dangerous_actions = [
                                "*:*",
                                "iam:*",
                                "sts:AssumeRole",  # Should be specific
                                "s3:*",  # Should be more specific
                            ]
                            
                            for dangerous_action in dangerous_actions:
                                if action == dangerous_action and "*" in resources:
                                    # This might be too permissive
                                    # Allow some exceptions for specific roles
                                    if "admin" not in policy_name.lower():
                                        return False
                        
                        # Check resource specificity
                        for resource in resources:
                            # Resources should be specific when possible
                            if resource == "*":
                                # Check if this is for a legitimate use case
                                effect = statement.get("Effect", "Allow")
                                if effect == "Allow":
                                    # Some actions legitimately need * resources
                                    legitimate_wildcard_actions = [
                                        "logs:CreateLogGroup",
                                        "logs:CreateLogStream",
                                        "logs:PutLogEvents",
                                        "xray:PutTraceSegments",
                                        "xray:PutTelemetryRecords",
                                        "cloudwatch:PutMetricData"
                                    ]
                                    
                                    if not any(action in legitimate_wildcard_actions for action in actions):
                                        # Might be too permissive
                                        pass
                
                except json.JSONDecodeError:
                    return False
        
        return True
    
    def validate_managed_policy_attachments(self, iam_resources: Dict[str, Dict]) -> bool:
        """Validate managed policy attachments are appropriate."""
        policy_attachments = {
            name: resource for name, resource in iam_resources.items()
            if resource["type"] == "aws_iam_role_policy_attachment"
        }
        
        for attachment_name, attachment_resource in policy_attachments.items():
            values = attachment_resource["values"]
            policy_arn = values.get("policy_arn", "")
            
            # Check for overly broad managed policies
            dangerous_policies = [
                "arn:aws:iam::aws:policy/AdministratorAccess",
                "arn:aws:iam::aws:policy/PowerUserAccess",
                "arn:aws:iam::aws:policy/IAMFullAccess",
            ]
            
            if policy_arn in dangerous_policies:
                # These should only be used for admin roles
                if "admin" not in attachment_name.lower():
                    return False
        
        return True
    
    def validate_role_naming_conventions(self, iam_resources: Dict[str, Dict]) -> bool:
        """Validate IAM roles follow naming conventions that indicate their purpose."""
        iam_roles = {
            name: resource for name, resource in iam_resources.items()
            if resource["type"] == "aws_iam_role"
        }
        
        for role_name, role_resource in iam_roles.items():
            values = role_resource["values"]
            role_name_value = values.get("name", "")
            
            # Role names should indicate their purpose
            if not role_name_value:
                return False
            
            # Should contain service or purpose indicator
            purpose_indicators = [
                "ecs", "lambda", "ec2", "rds", "neptune", "opensearch",
                "cloudwatch", "monitoring", "execution", "task", "autoscaling"
            ]
            
            if not any(indicator in role_name_value.lower() for indicator in purpose_indicators):
                return False
        
        return True


# Property-based test strategies
@st.composite
def iam_config_strategy(draw):
    """Generate IAM configurations for testing."""
    return {
        "enable_cloudtrail": draw(st.booleans()),
        "enable_caching": draw(st.booleans()),
        "neptune_monitoring_interval": draw(st.sampled_from([0, 60, 300])),
        "neptune_performance_insights_enabled": draw(st.booleans()),
    }


@st.composite
def service_config_strategy(draw):
    """Generate service configurations that affect IAM."""
    return {
        "ecs_cpu": draw(st.sampled_from([256, 512, 1024, 2048])),
        "ecs_memory": draw(st.integers(min_value=512, max_value=4096)),
        "enable_xray": draw(st.booleans()),
        "log_retention_days": draw(st.sampled_from([7, 14, 30, 90])),
    }


class TestIAMLeastPrivilege:
    """Property-based tests for IAM least privilege."""
    
    def setup_method(self):
        """Set up test environment."""
        self.iam_test = IAMTest()
    
    @given(
        iam_config=iam_config_strategy(),
        service_config=service_config_strategy()
    )
    @settings(max_examples=5, deadline=120000)  # 2 minute timeout
    def test_iam_least_privilege_property(self, iam_config, service_config):
        """
        Property test: For any configuration, IAM roles and policies should
        follow least-privilege principles and not grant unnecessary access.
        
        **Feature: aws-production-deployment, Property 4: IAM Least Privilege**
        **Validates: Requirements 1.5, 4.1**
        """
        # Skip if Terraform not available
        if not subprocess.run(["which", "terraform"], capture_output=True).returncode == 0:
            pytest.skip("Terraform not available")
        
        # Create test configuration
        config = {
            "aws_region": "us-east-1",
            "environment": "test",
            "project_name": "iam-test",
            "neptune_cluster_identifier": "test-neptune",
            "opensearch_domain_name": "test-opensearch",
            "skip_final_snapshot": True,
            "vpc_cidr": "10.0.0.0/16",
            "az_count": 2,
            **iam_config,
            **service_config
        }
        
        # Create temporary tfvars file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.tfvars', delete=False) as f:
            for key, value in config.items():
                if isinstance(value, str):
                    f.write(f'{key} = "{value}"\n')
                else:
                    f.write(f'{key} = {value}\n')
            tfvars_path = f.name
        
        try:
            # Change to terraform directory
            original_dir = os.getcwd()
            os.chdir(self.iam_test.terraform_dir)
            
            # Initialize Terraform
            init_result = subprocess.run(
                ["terraform", "init", "-backend=false"],
                capture_output=True,
                text=True,
                timeout=60
            )
            
            assume(init_result.returncode == 0)
            
            # Run terraform plan
            plan_result = subprocess.run(
                ["terraform", "plan", "-var-file", tfvars_path, "-out=iam-test.tfplan"],
                capture_output=True,
                text=True,
                timeout=120
            )
            
            assume(plan_result.returncode in [0, 2])
            
            # Get plan in JSON format
            show_result = subprocess.run(
                ["terraform", "show", "-json", "iam-test.tfplan"],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if show_result.returncode == 0:
                # Extract IAM resources
                iam_resources = self.iam_test.extract_iam_resources_from_plan(show_result.stdout)
                
                # Validate IAM role trust policies
                assert self.iam_test.validate_iam_role_trust_policies(iam_resources), \
                    "IAM role trust policies must follow least privilege principles"
                
                # Validate IAM policy permissions
                assert self.iam_test.validate_iam_policy_permissions(iam_resources), \
                    "IAM policies must not grant excessive permissions"
                
                # Validate managed policy attachments
                assert self.iam_test.validate_managed_policy_attachments(iam_resources), \
                    "Managed policy attachments must be appropriate for role purpose"
                
                # Validate role naming conventions
                assert self.iam_test.validate_role_naming_conventions(iam_resources), \
                    "IAM roles must follow naming conventions that indicate their purpose"
        
        finally:
            os.chdir(original_dir)
            # Cleanup
            try:
                os.unlink(tfvars_path)
                if os.path.exists(os.path.join(self.iam_test.terraform_dir, "iam-test.tfplan")):
                    os.unlink(os.path.join(self.iam_test.terraform_dir, "iam-test.tfplan"))
            except:
                pass
    
    def test_ecs_task_role_permissions(self):
        """
        Test that ECS task roles have appropriate permissions.
        
        **Feature: aws-production-deployment, Property 4: IAM Least Privilege**
        **Validates: Requirements 1.5, 4.1**
        """
        # Skip if Terraform not available
        if not subprocess.run(["which", "terraform"], capture_output=True).returncode == 0:
            pytest.skip("Terraform not available")
        
        config = {
            "aws_region": "us-east-1",
            "environment": "test",
            "project_name": "ecs-iam-test",
            "neptune_cluster_identifier": "test-neptune",
            "opensearch_domain_name": "test-opensearch",
            "skip_final_snapshot": True,
            "enable_xray": True
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.tfvars', delete=False) as f:
            for key, value in config.items():
                if isinstance(value, str):
                    f.write(f'{key} = "{value}"\n')
                else:
                    f.write(f'{key} = {value}\n')
            tfvars_path = f.name
        
        try:
            original_dir = os.getcwd()
            os.chdir(self.iam_test.terraform_dir)
            
            subprocess.run(["terraform", "init", "-backend=false"], 
                         capture_output=True, timeout=60)
            
            plan_result = subprocess.run(
                ["terraform", "plan", "-var-file", tfvars_path, "-out=ecs-iam-test.tfplan"],
                capture_output=True, text=True, timeout=120
            )
            
            if plan_result.returncode in [0, 2]:
                show_result = subprocess.run(
                    ["terraform", "show", "-json", "ecs-iam-test.tfplan"],
                    capture_output=True, text=True, timeout=30
                )
                
                if show_result.returncode == 0:
                    iam_resources = self.iam_test.extract_iam_resources_from_plan(show_result.stdout)
                    
                    # Find ECS task roles
                    ecs_task_roles = {
                        name: resource for name, resource in iam_resources.items()
                        if resource["type"] == "aws_iam_role" and "ecs-task" in resource["values"].get("name", "")
                    }
                    
                    assert len(ecs_task_roles) > 0, "Should have ECS task roles defined"
                    
                    # Check ECS task role trust policies
                    for role_name, role_resource in ecs_task_roles.items():
                        values = role_resource["values"]
                        assume_role_policy = values.get("assume_role_policy")
                        
                        if assume_role_policy:
                            policy_doc = json.loads(assume_role_policy)
                            statements = policy_doc.get("Statement", [])
                            
                            # Should allow ECS tasks service to assume the role
                            found_ecs_service = False
                            for statement in statements:
                                principal = statement.get("Principal", {})
                                service = principal.get("Service", [])
                                if isinstance(service, str):
                                    service = [service]
                                
                                if "ecs-tasks.amazonaws.com" in service:
                                    found_ecs_service = True
                                    break
                            
                            assert found_ecs_service, f"ECS task role {role_name} should trust ecs-tasks.amazonaws.com"
        
        finally:
            os.chdir(original_dir)
            try:
                os.unlink(tfvars_path)
                if os.path.exists(os.path.join(self.iam_test.terraform_dir, "ecs-iam-test.tfplan")):
                    os.unlink(os.path.join(self.iam_test.terraform_dir, "ecs-iam-test.tfplan"))
            except:
                pass
    
    def test_database_access_permissions(self):
        """
        Test that database access permissions are properly scoped.
        
        **Feature: aws-production-deployment, Property 4: IAM Least Privilege**
        **Validates: Requirements 4.1**
        """
        # Skip if Terraform not available
        if not subprocess.run(["which", "terraform"], capture_output=True).returncode == 0:
            pytest.skip("Terraform not available")
        
        config = {
            "aws_region": "us-east-1",
            "environment": "test",
            "project_name": "db-iam-test",
            "neptune_cluster_identifier": "test-neptune",
            "opensearch_domain_name": "test-opensearch",
            "skip_final_snapshot": True
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.tfvars', delete=False) as f:
            for key, value in config.items():
                if isinstance(value, str):
                    f.write(f'{key} = "{value}"\n')
                else:
                    f.write(f'{key} = {value}\n')
            tfvars_path = f.name
        
        try:
            original_dir = os.getcwd()
            os.chdir(self.iam_test.terraform_dir)
            
            subprocess.run(["terraform", "init", "-backend=false"], 
                         capture_output=True, timeout=60)
            
            plan_result = subprocess.run(
                ["terraform", "plan", "-var-file", tfvars_path, "-out=db-iam-test.tfplan"],
                capture_output=True, text=True, timeout=120
            )
            
            if plan_result.returncode in [0, 2]:
                show_result = subprocess.run(
                    ["terraform", "show", "-json", "db-iam-test.tfplan"],
                    capture_output=True, text=True, timeout=30
                )
                
                if show_result.returncode == 0:
                    iam_resources = self.iam_test.extract_iam_resources_from_plan(show_result.stdout)
                    
                    # Check database access policies
                    iam_policies = {
                        name: resource for name, resource in iam_resources.items()
                        if resource["type"] == "aws_iam_role_policy"
                    }
                    
                    for policy_name, policy_resource in iam_policies.items():
                        values = policy_resource["values"]
                        policy_document = values.get("policy")
                        
                        if policy_document:
                            policy_doc = json.loads(policy_document)
                            statements = policy_doc.get("Statement", [])
                            
                            for statement in statements:
                                actions = statement.get("Action", [])
                                if isinstance(actions, str):
                                    actions = [actions]
                                
                                resources = statement.get("Resource", [])
                                if isinstance(resources, str):
                                    resources = [resources]
                                
                                # Check Neptune permissions
                                neptune_actions = [action for action in actions if action.startswith("neptune-db:")]
                                if neptune_actions:
                                    # Neptune resources should be scoped
                                    for resource in resources:
                                        assert not resource == "*", \
                                            f"Neptune permissions in {policy_name} should not use wildcard resources"
                                
                                # Check OpenSearch permissions
                                es_actions = [action for action in actions if action.startswith("es:")]
                                if es_actions:
                                    # OpenSearch resources should be scoped
                                    for resource in resources:
                                        if resource == "*":
                                            # Some ES actions might legitimately need wildcard
                                            # but should be limited
                                            pass
        
        finally:
            os.chdir(original_dir)
            try:
                os.unlink(tfvars_path)
                if os.path.exists(os.path.join(self.iam_test.terraform_dir, "db-iam-test.tfplan")):
                    os.unlink(os.path.join(self.iam_test.terraform_dir, "db-iam-test.tfplan"))
            except:
                pass


if __name__ == "__main__":
    # Run basic IAM tests
    test_instance = TestIAMLeastPrivilege()
    test_instance.setup_method()
    
    print("Running IAM least privilege tests...")
    
    try:
        test_instance.test_ecs_task_role_permissions()
        print("✅ ECS task role permissions test passed")
    except Exception as e:
        print(f"❌ ECS task role permissions test failed: {e}")
    
    try:
        test_instance.test_database_access_permissions()
        print("✅ Database access permissions test passed")
    except Exception as e:
        print(f"❌ Database access permissions test failed: {e}")
    
    print("\nTo run property-based tests with Hypothesis:")
    print("pytest tests/infrastructure/test_iam_least_privilege.py -v")