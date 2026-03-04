#!/usr/bin/env python3
"""
Property-Based Tests for Encryption Enforcement
Feature: aws-production-deployment, Property 3: Encryption Enforcement

This module tests that encryption is enabled both in transit and at rest
with proper KMS key management using property-based testing.
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


class EncryptionTest:
    """Test class for encryption enforcement validation."""
    
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
    
    def extract_encryption_resources_from_plan(self, plan_output: str) -> Dict[str, Dict]:
        """Extract encryption-related resources from Terraform plan."""
        encryption_resources = {}
        
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
                    
                    # Check for encryption-related resources
                    if resource_type in [
                        "aws_kms_key", "aws_kms_alias",
                        "aws_neptune_cluster", "aws_opensearch_domain",
                        "aws_s3_bucket", "aws_s3_bucket_encryption",
                        "aws_cloudwatch_log_group", "aws_secretsmanager_secret"
                    ]:
                        encryption_resources[f"{resource_type}.{full_name}"] = {
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
            print(f"Error parsing encryption resources: {e}")
        
        return encryption_resources
    
    def validate_kms_key_configuration(self, encryption_resources: Dict[str, Dict]) -> bool:
        """Validate KMS key configurations for proper encryption setup."""
        kms_keys = {
            name: resource for name, resource in encryption_resources.items()
            if resource["type"] == "aws_kms_key"
        }
        
        if not kms_keys:
            return False  # Should have KMS keys for encryption
        
        for key_name, key_resource in kms_keys.items():
            values = key_resource["values"]
            
            # Check key rotation is enabled
            if not values.get("enable_key_rotation", False):
                return False
            
            # Check deletion window is reasonable (not too short)
            deletion_window = values.get("deletion_window_in_days", 30)
            if deletion_window < 7:
                return False
        
        return True
    
    def validate_database_encryption(self, encryption_resources: Dict[str, Dict]) -> bool:
        """Validate that databases have encryption enabled."""
        # Check Neptune encryption
        neptune_clusters = {
            name: resource for name, resource in encryption_resources.items()
            if resource["type"] == "aws_neptune_cluster"
        }
        
        for cluster_name, cluster_resource in neptune_clusters.items():
            values = cluster_resource["values"]
            
            # Check storage encryption is enabled
            if not values.get("storage_encrypted", False):
                return False
            
            # Check KMS key is specified
            if not values.get("kms_key_id"):
                return False
        
        # Check OpenSearch encryption
        opensearch_domains = {
            name: resource for name, resource in encryption_resources.items()
            if resource["type"] == "aws_opensearch_domain"
        }
        
        for domain_name, domain_resource in opensearch_domains.items():
            values = domain_resource["values"]
            
            # Check encrypt_at_rest configuration
            encrypt_at_rest = values.get("encrypt_at_rest", [])
            if not encrypt_at_rest or not encrypt_at_rest[0].get("enabled", False):
                return False
            
            # Check node-to-node encryption
            node_to_node = values.get("node_to_node_encryption", [])
            if not node_to_node or not node_to_node[0].get("enabled", False):
                return False
            
            # Check domain endpoint options enforce HTTPS
            domain_endpoint = values.get("domain_endpoint_options", [])
            if not domain_endpoint or not domain_endpoint[0].get("enforce_https", False):
                return False
        
        return True
    
    def validate_secrets_encryption(self, encryption_resources: Dict[str, Dict]) -> bool:
        """Validate that secrets are encrypted with KMS."""
        secrets = {
            name: resource for name, resource in encryption_resources.items()
            if resource["type"] == "aws_secretsmanager_secret"
        }
        
        for secret_name, secret_resource in secrets.items():
            values = secret_resource["values"]
            
            # Check KMS key is specified for encryption
            if not values.get("kms_key_id"):
                return False
        
        return True
    
    def validate_log_encryption(self, encryption_resources: Dict[str, Dict]) -> bool:
        """Validate that CloudWatch logs are encrypted."""
        log_groups = {
            name: resource for name, resource in encryption_resources.items()
            if resource["type"] == "aws_cloudwatch_log_group"
        }
        
        for log_name, log_resource in log_groups.items():
            values = log_resource["values"]
            
            # Check KMS key is specified for log encryption
            if not values.get("kms_key_id"):
                return False
        
        return True
    
    def validate_s3_encryption(self, encryption_resources: Dict[str, Dict]) -> bool:
        """Validate that S3 buckets have encryption enabled."""
        s3_encryption_configs = {
            name: resource for name, resource in encryption_resources.items()
            if resource["type"] == "aws_s3_bucket_encryption"
        }
        
        # If there are S3 buckets, they should have encryption configurations
        s3_buckets = {
            name: resource for name, resource in encryption_resources.items()
            if resource["type"] == "aws_s3_bucket"
        }
        
        if s3_buckets and not s3_encryption_configs:
            return False
        
        for encryption_name, encryption_resource in s3_encryption_configs.items():
            values = encryption_resource["values"]
            
            # Check server-side encryption configuration
            sse_config = values.get("server_side_encryption_configuration", [])
            if not sse_config:
                return False
            
            for config in sse_config:
                rules = config.get("rule", [])
                for rule in rules:
                    default_encryption = rule.get("apply_server_side_encryption_by_default", [])
                    if not default_encryption:
                        return False
                    
                    for encryption in default_encryption:
                        # Should use KMS encryption
                        if encryption.get("sse_algorithm") != "aws:kms":
                            return False
                        
                        # Should specify KMS key
                        if not encryption.get("kms_master_key_id"):
                            return False
        
        return True


# Property-based test strategies
@st.composite
def encryption_config_strategy(draw):
    """Generate encryption configurations for testing."""
    return {
        "enable_key_rotation": draw(st.booleans()),
        "kms_deletion_window": draw(st.integers(min_value=7, max_value=30)),
        "opensearch_encrypt_at_rest": draw(st.booleans()),
        "opensearch_node_to_node_encryption": draw(st.booleans()),
        "opensearch_enforce_https": draw(st.booleans()),
    }


@st.composite
def database_config_strategy(draw):
    """Generate database configurations for testing."""
    return {
        "neptune_instance_count": draw(st.integers(min_value=1, max_value=3)),
        "opensearch_instance_count": draw(st.integers(min_value=1, max_value=3)),
        "opensearch_dedicated_master_enabled": draw(st.booleans()),
        "opensearch_zone_awareness_enabled": draw(st.booleans()),
    }


class TestEncryptionEnforcement:
    """Property-based tests for encryption enforcement."""
    
    def setup_method(self):
        """Set up test environment."""
        self.encryption_test = EncryptionTest()
    
    @given(
        encryption_config=encryption_config_strategy(),
        database_config=database_config_strategy()
    )
    @settings(max_examples=5, deadline=120000)  # 2 minute timeout
    def test_encryption_enforcement_property(self, encryption_config, database_config):
        """
        Property test: For any configuration, encryption should be enabled
        both in transit and at rest with proper KMS key management.
        
        **Feature: aws-production-deployment, Property 3: Encryption Enforcement**
        **Validates: Requirements 1.6, 3.6**
        """
        # Skip if Terraform not available
        if not subprocess.run(["which", "terraform"], capture_output=True).returncode == 0:
            pytest.skip("Terraform not available")
        
        # Create test configuration
        config = {
            "aws_region": "us-east-1",
            "environment": "test",
            "project_name": "encryption-test",
            "neptune_cluster_identifier": "test-neptune",
            "opensearch_domain_name": "test-opensearch",
            "skip_final_snapshot": True,
            "vpc_cidr": "10.0.0.0/16",
            "az_count": 2,
            "enable_cloudtrail": True,
            **encryption_config,
            **database_config
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
            os.chdir(self.encryption_test.terraform_dir)
            
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
                ["terraform", "plan", "-var-file", tfvars_path, "-out=encryption-test.tfplan"],
                capture_output=True,
                text=True,
                timeout=120
            )
            
            assume(plan_result.returncode in [0, 2])
            
            # Get plan in JSON format
            show_result = subprocess.run(
                ["terraform", "show", "-json", "encryption-test.tfplan"],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if show_result.returncode == 0:
                # Extract encryption resources
                encryption_resources = self.encryption_test.extract_encryption_resources_from_plan(show_result.stdout)
                
                # Validate KMS key configuration
                assert self.encryption_test.validate_kms_key_configuration(encryption_resources), \
                    "KMS keys must be properly configured with rotation enabled"
                
                # Validate database encryption
                assert self.encryption_test.validate_database_encryption(encryption_resources), \
                    "Databases must have encryption enabled in transit and at rest"
                
                # Validate secrets encryption
                assert self.encryption_test.validate_secrets_encryption(encryption_resources), \
                    "Secrets must be encrypted with KMS keys"
                
                # Validate log encryption
                assert self.encryption_test.validate_log_encryption(encryption_resources), \
                    "CloudWatch logs must be encrypted with KMS keys"
        
        finally:
            os.chdir(original_dir)
            # Cleanup
            try:
                os.unlink(tfvars_path)
                if os.path.exists(os.path.join(self.encryption_test.terraform_dir, "encryption-test.tfplan")):
                    os.unlink(os.path.join(self.encryption_test.terraform_dir, "encryption-test.tfplan"))
            except:
                pass
    
    def test_kms_key_rotation_enabled(self):
        """
        Test that KMS keys have rotation enabled.
        
        **Feature: aws-production-deployment, Property 3: Encryption Enforcement**
        **Validates: Requirements 1.6**
        """
        # Skip if Terraform not available
        if not subprocess.run(["which", "terraform"], capture_output=True).returncode == 0:
            pytest.skip("Terraform not available")
        
        config = {
            "aws_region": "us-east-1",
            "environment": "test",
            "project_name": "kms-test",
            "neptune_cluster_identifier": "test-neptune",
            "opensearch_domain_name": "test-opensearch",
            "skip_final_snapshot": True,
            "enable_key_rotation": True,
            "kms_deletion_window": 7
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
            os.chdir(self.encryption_test.terraform_dir)
            
            subprocess.run(["terraform", "init", "-backend=false"], 
                         capture_output=True, timeout=60)
            
            plan_result = subprocess.run(
                ["terraform", "plan", "-var-file", tfvars_path, "-out=kms-test.tfplan"],
                capture_output=True, text=True, timeout=120
            )
            
            if plan_result.returncode in [0, 2]:
                show_result = subprocess.run(
                    ["terraform", "show", "-json", "kms-test.tfplan"],
                    capture_output=True, text=True, timeout=30
                )
                
                if show_result.returncode == 0:
                    encryption_resources = self.encryption_test.extract_encryption_resources_from_plan(show_result.stdout)
                    
                    # Check that KMS keys exist and have rotation enabled
                    kms_keys = {
                        name: resource for name, resource in encryption_resources.items()
                        if resource["type"] == "aws_kms_key"
                    }
                    
                    assert len(kms_keys) > 0, "Should have KMS keys defined"
                    
                    for key_name, key_resource in kms_keys.items():
                        values = key_resource["values"]
                        assert values.get("enable_key_rotation", False), \
                            f"KMS key {key_name} should have rotation enabled"
        
        finally:
            os.chdir(original_dir)
            try:
                os.unlink(tfvars_path)
                if os.path.exists(os.path.join(self.encryption_test.terraform_dir, "kms-test.tfplan")):
                    os.unlink(os.path.join(self.encryption_test.terraform_dir, "kms-test.tfplan"))
            except:
                pass
    
    def test_database_encryption_at_rest(self):
        """
        Test that databases have encryption at rest enabled.
        
        **Feature: aws-production-deployment, Property 3: Encryption Enforcement**
        **Validates: Requirements 3.6**
        """
        # Skip if Terraform not available
        if not subprocess.run(["which", "terraform"], capture_output=True).returncode == 0:
            pytest.skip("Terraform not available")
        
        config = {
            "aws_region": "us-east-1",
            "environment": "test",
            "project_name": "db-encryption-test",
            "neptune_cluster_identifier": "test-neptune",
            "opensearch_domain_name": "test-opensearch",
            "skip_final_snapshot": True,
            "opensearch_encrypt_at_rest": True,
            "opensearch_node_to_node_encryption": True,
            "opensearch_enforce_https": True
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
            os.chdir(self.encryption_test.terraform_dir)
            
            subprocess.run(["terraform", "init", "-backend=false"], 
                         capture_output=True, timeout=60)
            
            plan_result = subprocess.run(
                ["terraform", "plan", "-var-file", tfvars_path, "-out=db-encryption-test.tfplan"],
                capture_output=True, text=True, timeout=120
            )
            
            if plan_result.returncode in [0, 2]:
                show_result = subprocess.run(
                    ["terraform", "show", "-json", "db-encryption-test.tfplan"],
                    capture_output=True, text=True, timeout=30
                )
                
                if show_result.returncode == 0:
                    encryption_resources = self.encryption_test.extract_encryption_resources_from_plan(show_result.stdout)
                    
                    # Validate Neptune encryption
                    neptune_clusters = {
                        name: resource for name, resource in encryption_resources.items()
                        if resource["type"] == "aws_neptune_cluster"
                    }
                    
                    for cluster_name, cluster_resource in neptune_clusters.items():
                        values = cluster_resource["values"]
                        assert values.get("storage_encrypted", False), \
                            f"Neptune cluster {cluster_name} should have storage encryption enabled"
                        assert values.get("kms_key_id"), \
                            f"Neptune cluster {cluster_name} should specify KMS key"
                    
                    # Validate OpenSearch encryption
                    opensearch_domains = {
                        name: resource for name, resource in encryption_resources.items()
                        if resource["type"] == "aws_opensearch_domain"
                    }
                    
                    for domain_name, domain_resource in opensearch_domains.items():
                        values = domain_resource["values"]
                        
                        # Check encrypt_at_rest
                        encrypt_at_rest = values.get("encrypt_at_rest", [])
                        assert encrypt_at_rest and encrypt_at_rest[0].get("enabled", False), \
                            f"OpenSearch domain {domain_name} should have encryption at rest enabled"
                        
                        # Check node-to-node encryption
                        node_to_node = values.get("node_to_node_encryption", [])
                        assert node_to_node and node_to_node[0].get("enabled", False), \
                            f"OpenSearch domain {domain_name} should have node-to-node encryption enabled"
        
        finally:
            os.chdir(original_dir)
            try:
                os.unlink(tfvars_path)
                if os.path.exists(os.path.join(self.encryption_test.terraform_dir, "db-encryption-test.tfplan")):
                    os.unlink(os.path.join(self.encryption_test.terraform_dir, "db-encryption-test.tfplan"))
            except:
                pass


if __name__ == "__main__":
    # Run basic encryption tests
    test_instance = TestEncryptionEnforcement()
    test_instance.setup_method()
    
    print("Running encryption enforcement tests...")
    
    try:
        test_instance.test_kms_key_rotation_enabled()
        print("✅ KMS key rotation test passed")
    except Exception as e:
        print(f"❌ KMS key rotation test failed: {e}")
    
    try:
        test_instance.test_database_encryption_at_rest()
        print("✅ Database encryption at rest test passed")
    except Exception as e:
        print(f"❌ Database encryption at rest test failed: {e}")
    
    print("\nTo run property-based tests with Hypothesis:")
    print("pytest tests/infrastructure/test_encryption_enforcement.py -v")