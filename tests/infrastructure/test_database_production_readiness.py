#!/usr/bin/env python3
"""
Property-Based Tests for Database Production Readiness
Feature: aws-production-deployment, Property 8: Database Production Readiness

This module tests that Neptune and OpenSearch databases are configured
for production workloads with proper multi-AZ, monitoring, and performance settings.
"""

import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, List, Any, Optional
import pytest
from hypothesis import given, strategies as st, settings, assume


class DatabaseProductionReadinessTest:
    """Test class for database production readiness validation."""
    
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
    
    def extract_neptune_config(self, plan_data: Dict) -> Optional[Dict]:
        """Extract Neptune cluster configuration from Terraform plan."""
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
            return None
        
        root_module = plan_data["planned_values"]["root_module"]
        neptune_clusters = find_resources_in_module(root_module, "aws_neptune_cluster")
        
        if not neptune_clusters:
            return None
        
        return neptune_clusters[0].get("values", {})
    
    def extract_opensearch_config(self, plan_data: Dict) -> Optional[Dict]:
        """Extract OpenSearch domain configuration from Terraform plan."""
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
            return None
        
        root_module = plan_data["planned_values"]["root_module"]
        opensearch_domains = find_resources_in_module(root_module, "aws_opensearch_domain")
        
        if not opensearch_domains:
            return None
        
        return opensearch_domains[0].get("values", {})
    
    def validate_neptune_production_readiness(self, neptune_config: Dict) -> List[str]:
        """Validate Neptune configuration for production readiness."""
        issues = []
        
        # Check backup retention
        backup_retention = neptune_config.get("backup_retention_period", 0)
        if backup_retention < 7:
            issues.append(f"Neptune backup retention period ({backup_retention}) should be at least 7 days for production")
        
        # Check encryption
        if not neptune_config.get("storage_encrypted", False):
            issues.append("Neptune storage encryption should be enabled for production")
        
        # Check IAM authentication
        if not neptune_config.get("iam_database_authentication_enabled", False):
            issues.append("Neptune IAM database authentication should be enabled for production")
        
        # Check audit logging
        log_exports = neptune_config.get("enable_cloudwatch_logs_exports", [])
        if "audit" not in log_exports:
            issues.append("Neptune audit logging should be enabled for production")
        
        # Check backup window is set
        backup_window = neptune_config.get("preferred_backup_window")
        if not backup_window:
            issues.append("Neptune preferred backup window should be configured for production")
        
        # Check maintenance window is set
        maintenance_window = neptune_config.get("preferred_maintenance_window")
        if not maintenance_window:
            issues.append("Neptune preferred maintenance window should be configured for production")
        
        return issues
    
    def validate_opensearch_production_readiness(self, opensearch_config: Dict) -> List[str]:
        """Validate OpenSearch configuration for production readiness."""
        issues = []
        
        # Check encryption at rest
        encrypt_at_rest = opensearch_config.get("encrypt_at_rest", [])
        if not encrypt_at_rest or not encrypt_at_rest[0].get("enabled", False):
            issues.append("OpenSearch encryption at rest should be enabled for production")
        
        # Check node-to-node encryption
        node_encryption = opensearch_config.get("node_to_node_encryption", [])
        if not node_encryption or not node_encryption[0].get("enabled", False):
            issues.append("OpenSearch node-to-node encryption should be enabled for production")
        
        # Check HTTPS enforcement
        domain_endpoint_options = opensearch_config.get("domain_endpoint_options", [])
        if not domain_endpoint_options or not domain_endpoint_options[0].get("enforce_https", False):
            issues.append("OpenSearch HTTPS enforcement should be enabled for production")
        
        # Check advanced security options
        advanced_security = opensearch_config.get("advanced_security_options", [])
        if not advanced_security or not advanced_security[0].get("enabled", False):
            issues.append("OpenSearch advanced security options should be enabled for production")
        
        # Check cluster configuration
        cluster_config = opensearch_config.get("cluster_config", [])
        if cluster_config:
            cluster = cluster_config[0]
            instance_count = cluster.get("instance_count", 1)
            
            # For production, should have multiple instances or dedicated master
            if instance_count < 2 and not cluster.get("dedicated_master_enabled", False):
                issues.append("OpenSearch should have multiple instances or dedicated master nodes for production")
        
        # Check EBS configuration
        ebs_options = opensearch_config.get("ebs_options", [])
        if ebs_options:
            ebs = ebs_options[0]
            if not ebs.get("ebs_enabled", False):
                issues.append("OpenSearch EBS storage should be enabled for production")
            
            volume_size = ebs.get("volume_size", 0)
            if volume_size < 20:
                issues.append(f"OpenSearch EBS volume size ({volume_size}GB) should be at least 20GB for production")
        
        # Check VPC configuration
        vpc_options = opensearch_config.get("vpc_options", [])
        if not vpc_options:
            issues.append("OpenSearch should be deployed in VPC for production")
        
        return issues


# Property-based test strategies
@st.composite
def production_database_config(draw):
    """Generate production-ready database configurations."""
    return {
        "aws_region": draw(st.sampled_from(["us-east-1", "us-west-2", "eu-west-1"])),
        "environment": "production",
        "project_name": draw(st.text(min_size=3, max_size=20, alphabet=st.characters(whitelist_categories=("Ll", "Nd"), whitelist_characters="-"))),
        "vpc_cidr": draw(st.sampled_from(["10.0.0.0/16", "172.16.0.0/16"])),
        "az_count": draw(st.integers(min_value=2, max_value=3)),
        
        # Neptune production settings
        "neptune_cluster_identifier": "prod-neptune-cluster",
        "neptune_instance_count": draw(st.integers(min_value=1, max_value=3)),
        "neptune_instance_class": draw(st.sampled_from(["db.t3.medium", "db.r5.large", "db.r5.xlarge"])),
        "neptune_backup_retention_period": draw(st.integers(min_value=7, max_value=35)),
        "neptune_backup_window": "07:00-09:00",
        "neptune_maintenance_window": "sun:09:00-sun:10:00",
        "neptune_performance_insights_enabled": draw(st.booleans()),
        "neptune_monitoring_interval": draw(st.sampled_from([0, 60])),
        
        # OpenSearch production settings
        "opensearch_domain_name": "prod-opensearch-domain",
        "opensearch_instance_type": draw(st.sampled_from(["t3.small.search", "m6g.large.search", "r6g.large.search"])),
        "opensearch_instance_count": draw(st.integers(min_value=1, max_value=6)),
        "opensearch_dedicated_master_enabled": draw(st.booleans()),
        "opensearch_master_instance_count": draw(st.integers(min_value=0, max_value=3)),
        "opensearch_zone_awareness_enabled": draw(st.booleans()),
        "opensearch_availability_zone_count": draw(st.integers(min_value=2, max_value=3)),
        "opensearch_volume_size": draw(st.integers(min_value=20, max_value=100)),
        "opensearch_encrypt_at_rest": True,
        "opensearch_node_to_node_encryption": True,
        "opensearch_enforce_https": True,
        "opensearch_advanced_security_enabled": True,
        
        "skip_final_snapshot": True,
        "log_retention_days": draw(st.integers(min_value=7, max_value=90)),
    }


class TestDatabaseProductionReadiness:
    """Property-based tests for database production readiness."""
    
    def setup_method(self):
        """Set up test environment."""
        self.db_test = DatabaseProductionReadinessTest()
    
    @given(config=production_database_config())
    @settings(max_examples=5, deadline=120000)  # 2 minute timeout
    def test_neptune_production_configuration(self, config):
        """
        Property test: For any production database configuration,
        Neptune should be configured with production-ready settings.
        
        **Feature: aws-production-deployment, Property 8: Database Production Readiness**
        **Validates: Requirements 3.1, 3.2**
        """
        # Skip if Terraform not available
        if not subprocess.run(["which", "terraform"], capture_output=True).returncode == 0:
            pytest.skip("Terraform not available")
        
        plan_data = self.db_test.get_terraform_plan_json(config)
        assume(plan_data is not None)
        
        neptune_config = self.db_test.extract_neptune_config(plan_data)
        assume(neptune_config is not None)
        
        # Validate Neptune production readiness
        issues = self.db_test.validate_neptune_production_readiness(neptune_config)
        
        assert len(issues) == 0, f"Neptune production readiness issues: {'; '.join(issues)}"
    
    @given(config=production_database_config())
    @settings(max_examples=5, deadline=120000)
    def test_opensearch_production_configuration(self, config):
        """
        Property test: For any production database configuration,
        OpenSearch should be configured with production-ready settings.
        
        **Feature: aws-production-deployment, Property 8: Database Production Readiness**
        **Validates: Requirements 3.1, 3.2**
        """
        # Skip if Terraform not available
        if not subprocess.run(["which", "terraform"], capture_output=True).returncode == 0:
            pytest.skip("Terraform not available")
        
        plan_data = self.db_test.get_terraform_plan_json(config)
        assume(plan_data is not None)
        
        opensearch_config = self.db_test.extract_opensearch_config(plan_data)
        assume(opensearch_config is not None)
        
        # Validate OpenSearch production readiness
        issues = self.db_test.validate_opensearch_production_readiness(opensearch_config)
        
        assert len(issues) == 0, f"OpenSearch production readiness issues: {'; '.join(issues)}"
    
    def test_database_multi_az_deployment(self):
        """
        Test that databases are configured for multi-AZ deployment.
        
        **Feature: aws-production-deployment, Property 8: Database Production Readiness**
        **Validates: Requirements 3.1, 3.2**
        """
        # Skip if Terraform not available
        if not subprocess.run(["which", "terraform"], capture_output=True).returncode == 0:
            pytest.skip("Terraform not available")
        
        config = {
            "aws_region": "us-east-1",
            "environment": "production",
            "project_name": "test-project",
            "az_count": 3,
            "neptune_cluster_identifier": "test-neptune",
            "opensearch_domain_name": "test-opensearch",
            "opensearch_zone_awareness_enabled": True,
            "opensearch_availability_zone_count": 2,
            "skip_final_snapshot": True,
        }
        
        plan_data = self.db_test.get_terraform_plan_json(config)
        assert plan_data is not None, "Should be able to generate Terraform plan"
        
        # Check that database subnets span multiple AZs
        def find_subnet_groups(module_data):
            subnet_groups = []
            if "resources" in module_data:
                for resource in module_data["resources"]:
                    if resource.get("type") == "aws_neptune_subnet_group":
                        subnet_groups.append(resource)
            
            if "child_modules" in module_data:
                for child_module in module_data["child_modules"]:
                    subnet_groups.extend(find_subnet_groups(child_module))
            
            return subnet_groups
        
        root_module = plan_data["planned_values"]["root_module"]
        subnet_groups = find_subnet_groups(root_module)
        
        assert len(subnet_groups) > 0, "Should have Neptune subnet group"
        
        # Verify subnet group spans multiple subnets (multi-AZ)
        subnet_group = subnet_groups[0]["values"]
        subnet_ids = subnet_group.get("subnet_ids", [])
        assert len(subnet_ids) >= 2, "Neptune subnet group should span at least 2 AZs for production"
    
    def test_database_monitoring_enabled(self):
        """
        Test that database monitoring and logging are properly configured.
        
        **Feature: aws-production-deployment, Property 8: Database Production Readiness**
        **Validates: Requirements 3.1, 3.2**
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
            "skip_final_snapshot": True,
        }
        
        plan_data = self.db_test.get_terraform_plan_json(config)
        assert plan_data is not None, "Should be able to generate Terraform plan"
        
        # Check CloudWatch log groups exist
        def find_log_groups(module_data):
            log_groups = []
            if "resources" in module_data:
                for resource in module_data["resources"]:
                    if resource.get("type") == "aws_cloudwatch_log_group":
                        log_groups.append(resource)
            
            if "child_modules" in module_data:
                for child_module in module_data["child_modules"]:
                    log_groups.extend(find_log_groups(child_module))
            
            return log_groups
        
        root_module = plan_data["planned_values"]["root_module"]
        log_groups = find_log_groups(root_module)
        
        # Should have log groups for both Neptune and OpenSearch
        log_group_names = [lg["values"]["name"] for lg in log_groups]
        
        # Check for Neptune audit logs
        neptune_audit_logs = [name for name in log_group_names if "neptune" in name and "audit" in name]
        assert len(neptune_audit_logs) > 0, "Should have Neptune audit log group"
        
        # Check for OpenSearch logs
        opensearch_logs = [name for name in log_group_names if "opensearch" in name]
        assert len(opensearch_logs) > 0, "Should have OpenSearch log groups"


if __name__ == "__main__":
    # Run basic validation tests
    test_instance = TestDatabaseProductionReadiness()
    test_instance.setup_method()
    
    print("Running database production readiness tests...")
    
    try:
        test_instance.test_database_multi_az_deployment()
        print("✅ Database multi-AZ deployment test passed")
    except Exception as e:
        print(f"❌ Database multi-AZ deployment test failed: {e}")
    
    try:
        test_instance.test_database_monitoring_enabled()
        print("✅ Database monitoring test passed")
    except Exception as e:
        print(f"❌ Database monitoring test failed: {e}")
    
    print("\nTo run property-based tests with Hypothesis:")
    print("pytest tests/infrastructure/test_database_production_readiness.py -v")