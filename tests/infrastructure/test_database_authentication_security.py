#!/usr/bin/env python3
"""
Property-Based Tests for Database Authentication Security
Feature: aws-production-deployment, Property 9: Database Authentication Security

This module tests that Neptune and OpenSearch databases are configured
with secure authentication mechanisms including IAM authentication,
VPC security groups, and proper access controls.
"""

import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, List, Any, Optional
import pytest
from hypothesis import given, strategies as st, settings, assume


class DatabaseAuthenticationSecurityTest:
    """Test class for database authentication security validation."""
    
    def __init__(self, terraform_dir: str = None):
        if terraform_dir is None:
            current_dir = Path.cwd()
            if (current_dir / "terraform.tf").exists():
                self.terraform_dir = current_dir
            elif (current_dir / "infrastructure" / "aws-native").exists():
                self.terraform_dir = current_dir / "infrastructure" / "aws-native"
            else:
                self.terraform_dir = Path("infrastructure/aws-native")
        else:
            self.terraform_dir = Path(terraform_dir)
    
    def get_terraform_plan_json(self, config: Dict[str, Any]) -> Optional[Dict]:
        """Generate Terraform plan and return JSON representation."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.tfvars', delete=False) as f:
            for key, value in config.items():
                if isinstance(value, str):
                    f.write(f'{key} = "{value}"\n')
                else:
                    f.write(f'{key} = {value}\n')
            tfvars_path = f.name
        
        try:
            original_dir = os.getcwd()
            os.chdir(self.terraform_dir)
            
            # Initialize Terraform
            init_result = subprocess.run(
                ["terraform", "init", "-backend=false"],
                capture_output=True, text=True, timeout=60
            )
            
            if init_result.returncode != 0:
                return None
            
            # Generate plan
            plan_result = subprocess.run(
                ["terraform", "plan", "-var-file", tfvars_path, "-out=test.tfplan"],
                capture_output=True, text=True, timeout=120
            )
            
            if plan_result.returncode not in [0, 2]:
                return None
            
            # Get JSON representation
            show_result = subprocess.run(
                ["terraform", "show", "-json", "test.tfplan"],
                capture_output=True, text=True, timeout=30
            )
            
            if show_result.returncode == 0:
                return json.loads(show_result.stdout)
            
            return None
            
        except Exception as e:
            print(f"Error generating plan: {e}")
            return None
        finally:
            os.chdir(original_dir)
            try:
                os.unlink(tfvars_path)
                if os.path.exists(os.path.join(self.terraform_dir, "test.tfplan")):
                    os.unlink(os.path.join(self.terraform_dir, "test.tfplan"))
            except:
                pass
    
    def find_resources_in_plan(self, plan_data: Dict, resource_type: str) -> List[Dict]:
        """Find all resources of a specific type in the Terraform plan."""
        def find_resources_in_module(module_data, resource_type):
            resources = []
            if "resources" in module_data:
                for resource in module_data["resources"]:
                    if resource.get("type") == resource_type:
                        resources.append(resource)
            
            if "child_modules" in module_data:
                for child_module in module_data["child_modules"]:
                    resources.extend(find_resources_in_module(child_module, resource_type))
            
            return resources
        
        if "planned_values" not in plan_data or "root_module" not in plan_data["planned_values"]:
            return []
        
        root_module = plan_data["planned_values"]["root_module"]
        return find_resources_in_module(root_module, resource_type)
    
    def validate_neptune_authentication_security(self, plan_data: Dict) -> List[str]:
        """Validate Neptune authentication and security configuration."""
        issues = []
        
        # Find Neptune cluster
        neptune_clusters = self.find_resources_in_plan(plan_data, "aws_neptune_cluster")
        if not neptune_clusters:
            issues.append("No Neptune cluster found in plan")
            return issues
        
        neptune_config = neptune_clusters[0].get("values", {})
        
        # Check IAM database authentication
        if not neptune_config.get("iam_database_authentication_enabled", False):
            issues.append("Neptune IAM database authentication should be enabled for security")
        
        # Check storage encryption
        if not neptune_config.get("storage_encrypted", False):
            issues.append("Neptune storage encryption should be enabled for security")
        
        # Check KMS key is specified
        kms_key_id = neptune_config.get("kms_key_id")
        if not kms_key_id:
            issues.append("Neptune should use customer-managed KMS key for encryption")
        
        # Check VPC security groups
        vpc_security_group_ids = neptune_config.get("vpc_security_group_ids", [])
        if not vpc_security_group_ids:
            issues.append("Neptune should be associated with VPC security groups")
        
        # Check subnet group (VPC deployment)
        db_subnet_group_name = neptune_config.get("db_subnet_group_name")
        if not db_subnet_group_name:
            issues.append("Neptune should be deployed in VPC with subnet group")
        
        return issues
    
    def validate_opensearch_authentication_security(self, plan_data: Dict) -> List[str]:
        """Validate OpenSearch authentication and security configuration."""
        issues = []
        
        # Find OpenSearch domain
        opensearch_domains = self.find_resources_in_plan(plan_data, "aws_opensearch_domain")
        if not opensearch_domains:
            issues.append("No OpenSearch domain found in plan")
            return issues
        
        opensearch_config = opensearch_domains[0].get("values", {})
        
        # Check advanced security options
        advanced_security = opensearch_config.get("advanced_security_options", [])
        if not advanced_security:
            issues.append("OpenSearch advanced security options should be configured")
        else:
            security_config = advanced_security[0]
            if not security_config.get("enabled", False):
                issues.append("OpenSearch advanced security options should be enabled")
            
            # Check that anonymous auth is disabled
            if security_config.get("anonymous_auth_enabled", True):
                issues.append("OpenSearch anonymous authentication should be disabled")
            
            # Check that internal user database is disabled (using IAM)
            if security_config.get("internal_user_database_enabled", True):
                issues.append("OpenSearch internal user database should be disabled in favor of IAM")
            
            # Check master user options
            master_user_options = security_config.get("master_user_options", [])
            if not master_user_options:
                issues.append("OpenSearch master user options should be configured")
            else:
                master_user = master_user_options[0]
                if not master_user.get("master_user_arn"):
                    issues.append("OpenSearch master user ARN should be specified for IAM authentication")
        
        # Check encryption at rest
        encrypt_at_rest = opensearch_config.get("encrypt_at_rest", [])
        if not encrypt_at_rest:
            issues.append("OpenSearch encryption at rest should be configured")
        else:
            encryption_config = encrypt_at_rest[0]
            if not encryption_config.get("enabled", False):
                issues.append("OpenSearch encryption at rest should be enabled")
            
            # Check KMS key
            kms_key_id = encryption_config.get("kms_key_id")
            if not kms_key_id:
                issues.append("OpenSearch should use customer-managed KMS key for encryption")
        
        # Check node-to-node encryption
        node_encryption = opensearch_config.get("node_to_node_encryption", [])
        if not node_encryption:
            issues.append("OpenSearch node-to-node encryption should be configured")
        else:
            if not node_encryption[0].get("enabled", False):
                issues.append("OpenSearch node-to-node encryption should be enabled")
        
        # Check domain endpoint options (HTTPS)
        domain_endpoint_options = opensearch_config.get("domain_endpoint_options", [])
        if not domain_endpoint_options:
            issues.append("OpenSearch domain endpoint options should be configured")
        else:
            endpoint_config = domain_endpoint_options[0]
            if not endpoint_config.get("enforce_https", False):
                issues.append("OpenSearch HTTPS enforcement should be enabled")
            
            # Check TLS policy
            tls_policy = endpoint_config.get("tls_security_policy", "")
            if not tls_policy or "1.2" not in tls_policy:
                issues.append("OpenSearch should enforce TLS 1.2 or higher")
        
        # Check VPC configuration
        vpc_options = opensearch_config.get("vpc_options", [])
        if not vpc_options:
            issues.append("OpenSearch should be deployed in VPC for network security")
        else:
            vpc_config = vpc_options[0]
            security_group_ids = vpc_config.get("security_group_ids", [])
            if not security_group_ids:
                issues.append("OpenSearch should be associated with VPC security groups")
            
            subnet_ids = vpc_config.get("subnet_ids", [])
            if not subnet_ids:
                issues.append("OpenSearch should be deployed in VPC subnets")
        
        return issues
    
    def validate_security_groups(self, plan_data: Dict) -> List[str]:
        """Validate security group configurations for databases."""
        issues = []
        
        # Find security groups
        security_groups = self.find_resources_in_plan(plan_data, "aws_security_group")
        
        # Look for database-related security groups
        db_security_groups = []
        for sg in security_groups:
            sg_values = sg.get("values", {})
            sg_name = sg_values.get("name", "")
            sg_description = sg_values.get("description", "")
            
            if any(keyword in sg_name.lower() or keyword in sg_description.lower() 
                   for keyword in ["neptune", "opensearch", "database", "db"]):
                db_security_groups.append(sg_values)
        
        if not db_security_groups:
            issues.append("No database security groups found")
            return issues
        
        for sg in db_security_groups:
            # Check ingress rules
            ingress_rules = sg.get("ingress", [])
            for rule in ingress_rules:
                # Check for overly permissive rules
                cidr_blocks = rule.get("cidr_blocks", [])
                if "0.0.0.0/0" in cidr_blocks:
                    issues.append(f"Security group {sg.get('name')} has overly permissive ingress rule allowing 0.0.0.0/0")
                
                # Check for IPv6 equivalent
                ipv6_cidr_blocks = rule.get("ipv6_cidr_blocks", [])
                if "::/0" in ipv6_cidr_blocks:
                    issues.append(f"Security group {sg.get('name')} has overly permissive IPv6 ingress rule")
        
        return issues
    
    def validate_iam_roles_and_policies(self, plan_data: Dict) -> List[str]:
        """Validate IAM roles and policies for database access."""
        issues = []
        
        # Find IAM roles
        iam_roles = self.find_resources_in_plan(plan_data, "aws_iam_role")
        
        # Look for database-related IAM roles
        db_roles = []
        for role in iam_roles:
            role_values = role.get("values", {})
            role_name = role_values.get("name", "")
            
            if any(keyword in role_name.lower() 
                   for keyword in ["neptune", "opensearch", "database", "db"]):
                db_roles.append(role_values)
        
        if not db_roles:
            issues.append("No database-related IAM roles found")
            return issues
        
        for role in db_roles:
            # Check assume role policy
            assume_role_policy = role.get("assume_role_policy")
            if not assume_role_policy:
                issues.append(f"IAM role {role.get('name')} should have assume role policy")
                continue
            
            try:
                policy_doc = json.loads(assume_role_policy)
                statements = policy_doc.get("Statement", [])
                
                for statement in statements:
                    # Check for overly permissive principals
                    principal = statement.get("Principal", {})
                    if principal == "*" or (isinstance(principal, dict) and principal.get("AWS") == "*"):
                        issues.append(f"IAM role {role.get('name')} has overly permissive assume role policy")
            
            except json.JSONDecodeError:
                issues.append(f"IAM role {role.get('name')} has invalid assume role policy JSON")
        
        return issues


# Property-based test strategies
@st.composite
def secure_database_config(draw):
    """Generate secure database configurations."""
    return {
        "aws_region": draw(st.sampled_from(["us-east-1", "us-west-2", "eu-west-1"])),
        "environment": draw(st.sampled_from(["staging", "production"])),
        "project_name": draw(st.text(min_size=3, max_size=20, alphabet=st.characters(whitelist_categories=("Ll", "Nd"), whitelist_characters="-"))),
        "vpc_cidr": draw(st.sampled_from(["10.0.0.0/16", "172.16.0.0/16"])),
        "az_count": draw(st.integers(min_value=2, max_value=3)),
        
        # Neptune security settings
        "neptune_cluster_identifier": "secure-neptune-cluster",
        "neptune_instance_count": draw(st.integers(min_value=1, max_value=2)),
        "neptune_instance_class": draw(st.sampled_from(["db.t3.medium", "db.r5.large"])),
        
        # OpenSearch security settings
        "opensearch_domain_name": "secure-opensearch-domain",
        "opensearch_instance_type": draw(st.sampled_from(["t3.small.search", "m6g.large.search"])),
        "opensearch_instance_count": draw(st.integers(min_value=1, max_value=3)),
        "opensearch_encrypt_at_rest": True,
        "opensearch_node_to_node_encryption": True,
        "opensearch_enforce_https": True,
        "opensearch_advanced_security_enabled": True,
        "opensearch_tls_security_policy": "Policy-Min-TLS-1-2-2019-07",
        
        "skip_final_snapshot": True,
        "log_retention_days": draw(st.integers(min_value=7, max_value=30)),
    }


class TestDatabaseAuthenticationSecurity:
    """Property-based tests for database authentication security."""
    
    def setup_method(self):
        """Set up test environment."""
        self.auth_test = DatabaseAuthenticationSecurityTest()
    
    @given(config=secure_database_config())
    @settings(max_examples=3, deadline=120000)  # 2 minute timeout
    def test_neptune_authentication_security(self, config):
        """
        Property test: For any secure database configuration,
        Neptune should have proper authentication and security controls.
        
        **Feature: aws-production-deployment, Property 9: Database Authentication Security**
        **Validates: Requirements 3.3, 3.4**
        """
        # Skip if Terraform not available
        if not subprocess.run(["which", "terraform"], capture_output=True).returncode == 0:
            pytest.skip("Terraform not available")
        
        plan_data = self.auth_test.get_terraform_plan_json(config)
        assume(plan_data is not None)
        
        # Validate Neptune authentication security
        issues = self.auth_test.validate_neptune_authentication_security(plan_data)
        
        assert len(issues) == 0, f"Neptune authentication security issues: {'; '.join(issues)}"
    
    @given(config=secure_database_config())
    @settings(max_examples=3, deadline=120000)
    def test_opensearch_authentication_security(self, config):
        """
        Property test: For any secure database configuration,
        OpenSearch should have proper authentication and security controls.
        
        **Feature: aws-production-deployment, Property 9: Database Authentication Security**
        **Validates: Requirements 3.3, 3.4**
        """
        # Skip if Terraform not available
        if not subprocess.run(["which", "terraform"], capture_output=True).returncode == 0:
            pytest.skip("Terraform not available")
        
        plan_data = self.auth_test.get_terraform_plan_json(config)
        assume(plan_data is not None)
        
        # Validate OpenSearch authentication security
        issues = self.auth_test.validate_opensearch_authentication_security(plan_data)
        
        assert len(issues) == 0, f"OpenSearch authentication security issues: {'; '.join(issues)}"
    
    @given(config=secure_database_config())
    @settings(max_examples=3, deadline=120000)
    def test_database_security_groups(self, config):
        """
        Property test: For any secure database configuration,
        security groups should follow least-privilege principles.
        
        **Feature: aws-production-deployment, Property 9: Database Authentication Security**
        **Validates: Requirements 3.3, 3.4**
        """
        # Skip if Terraform not available
        if not subprocess.run(["which", "terraform"], capture_output=True).returncode == 0:
            pytest.skip("Terraform not available")
        
        plan_data = self.auth_test.get_terraform_plan_json(config)
        assume(plan_data is not None)
        
        # Validate security groups
        issues = self.auth_test.validate_security_groups(plan_data)
        
        assert len(issues) == 0, f"Database security group issues: {'; '.join(issues)}"
    
    def test_database_vpc_isolation(self):
        """
        Test that databases are properly isolated within VPC.
        
        **Feature: aws-production-deployment, Property 9: Database Authentication Security**
        **Validates: Requirements 3.3, 3.4**
        """
        # Skip if Terraform not available
        if not subprocess.run(["which", "terraform"], capture_output=True).returncode == 0:
            pytest.skip("Terraform not available")
        
        config = {
            "aws_region": "us-east-1",
            "environment": "production",
            "project_name": "test-project",
            "az_count": 2,
            "neptune_cluster_identifier": "test-neptune",
            "opensearch_domain_name": "test-opensearch",
            "opensearch_advanced_security_enabled": True,
            "skip_final_snapshot": True,
        }
        
        plan_data = self.auth_test.get_terraform_plan_json(config)
        assert plan_data is not None, "Should be able to generate Terraform plan"
        
        # Check Neptune VPC configuration
        neptune_clusters = self.auth_test.find_resources_in_plan(plan_data, "aws_neptune_cluster")
        assert len(neptune_clusters) > 0, "Should have Neptune cluster"
        
        neptune_config = neptune_clusters[0]["values"]
        assert neptune_config.get("db_subnet_group_name"), "Neptune should be in VPC subnet group"
        assert neptune_config.get("vpc_security_group_ids"), "Neptune should have VPC security groups"
        
        # Check OpenSearch VPC configuration
        opensearch_domains = self.auth_test.find_resources_in_plan(plan_data, "aws_opensearch_domain")
        assert len(opensearch_domains) > 0, "Should have OpenSearch domain"
        
        opensearch_config = opensearch_domains[0]["values"]
        vpc_options = opensearch_config.get("vpc_options", [])
        assert len(vpc_options) > 0, "OpenSearch should have VPC options"
        
        vpc_config = vpc_options[0]
        assert vpc_config.get("subnet_ids"), "OpenSearch should be in VPC subnets"
        assert vpc_config.get("security_group_ids"), "OpenSearch should have VPC security groups"
    
    def test_database_encryption_keys(self):
        """
        Test that databases use customer-managed KMS keys for encryption.
        
        **Feature: aws-production-deployment, Property 9: Database Authentication Security**
        **Validates: Requirements 3.3, 3.4**
        """
        # Skip if Terraform not available
        if not subprocess.run(["which", "terraform"], capture_output=True).returncode == 0:
            pytest.skip("Terraform not available")
        
        config = {
            "aws_region": "us-east-1",
            "environment": "production",
            "project_name": "test-project",
            "neptune_cluster_identifier": "test-neptune",
            "opensearch_domain_name": "test-opensearch",
            "opensearch_encrypt_at_rest": True,
            "skip_final_snapshot": True,
        }
        
        plan_data = self.auth_test.get_terraform_plan_json(config)
        assert plan_data is not None, "Should be able to generate Terraform plan"
        
        # Check KMS keys exist
        kms_keys = self.auth_test.find_resources_in_plan(plan_data, "aws_kms_key")
        assert len(kms_keys) > 0, "Should have KMS keys for database encryption"
        
        # Check Neptune uses KMS key
        neptune_clusters = self.auth_test.find_resources_in_plan(plan_data, "aws_neptune_cluster")
        if neptune_clusters:
            neptune_config = neptune_clusters[0]["values"]
            assert neptune_config.get("storage_encrypted"), "Neptune should be encrypted"
            assert neptune_config.get("kms_key_id"), "Neptune should use customer-managed KMS key"
        
        # Check OpenSearch uses KMS key
        opensearch_domains = self.auth_test.find_resources_in_plan(plan_data, "aws_opensearch_domain")
        if opensearch_domains:
            opensearch_config = opensearch_domains[0]["values"]
            encrypt_at_rest = opensearch_config.get("encrypt_at_rest", [])
            if encrypt_at_rest:
                encryption_config = encrypt_at_rest[0]
                assert encryption_config.get("enabled"), "OpenSearch should be encrypted at rest"
                assert encryption_config.get("kms_key_id"), "OpenSearch should use customer-managed KMS key"


if __name__ == "__main__":
    # Run basic validation tests
    test_instance = TestDatabaseAuthenticationSecurity()
    test_instance.setup_method()
    
    print("Running database authentication security tests...")
    
    try:
        test_instance.test_database_vpc_isolation()
        print("✅ Database VPC isolation test passed")
    except Exception as e:
        print(f"❌ Database VPC isolation test failed: {e}")
    
    try:
        test_instance.test_database_encryption_keys()
        print("✅ Database encryption keys test passed")
    except Exception as e:
        print(f"❌ Database encryption keys test failed: {e}")
    
    print("\nTo run property-based tests with Hypothesis:")
    print("pytest tests/infrastructure/test_database_authentication_security.py -v")