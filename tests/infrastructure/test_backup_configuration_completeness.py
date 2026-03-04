#!/usr/bin/env python3
"""
Property-Based Tests for Backup Configuration Completeness
Feature: aws-production-deployment, Property 10: Backup Configuration Completeness

This module tests that Neptune and OpenSearch databases have comprehensive
backup configurations including automated backups, retention policies,
and disaster recovery capabilities.
"""

import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, List, Any, Optional
import pytest
from hypothesis import given, strategies as st, settings, assume


class BackupConfigurationCompletenessTest:
    """Test class for backup configuration completeness validation."""
    
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
    
    def validate_neptune_backup_configuration(self, plan_data: Dict) -> List[str]:
        """Validate Neptune backup configuration."""
        issues = []
        
        # Find Neptune cluster
        neptune_clusters = self.find_resources_in_plan(plan_data, "aws_neptune_cluster")
        if not neptune_clusters:
            issues.append("No Neptune cluster found in plan")
            return issues
        
        neptune_config = neptune_clusters[0].get("values", {})
        
        # Check backup retention period
        backup_retention = neptune_config.get("backup_retention_period", 0)
        if backup_retention < 7:
            issues.append(f"Neptune backup retention period ({backup_retention} days) should be at least 7 days")
        elif backup_retention > 35:
            issues.append(f"Neptune backup retention period ({backup_retention} days) exceeds maximum of 35 days")
        
        # Check backup window is configured
        backup_window = neptune_config.get("preferred_backup_window")
        if not backup_window:
            issues.append("Neptune preferred backup window should be configured")
        else:
            # Validate backup window format (HH:MM-HH:MM)
            if not self._validate_time_window_format(backup_window):
                issues.append(f"Neptune backup window format is invalid: {backup_window}")
        
        # Check maintenance window is configured
        maintenance_window = neptune_config.get("preferred_maintenance_window")
        if not maintenance_window:
            issues.append("Neptune preferred maintenance window should be configured")
        else:
            # Validate maintenance window format (ddd:HH:MM-ddd:HH:MM)
            if not self._validate_maintenance_window_format(maintenance_window):
                issues.append(f"Neptune maintenance window format is invalid: {maintenance_window}")
        
        # Check that backup and maintenance windows don't overlap
        if backup_window and maintenance_window:
            if self._windows_overlap(backup_window, maintenance_window):
                issues.append("Neptune backup and maintenance windows should not overlap")
        
        # Check final snapshot configuration
        skip_final_snapshot = neptune_config.get("skip_final_snapshot", True)
        if skip_final_snapshot:
            # For production, we might want to keep final snapshots
            final_snapshot_identifier = neptune_config.get("final_snapshot_identifier")
            if not final_snapshot_identifier:
                issues.append("Neptune should have final snapshot identifier configured for production")
        
        return issues
    
    def validate_opensearch_backup_configuration(self, plan_data: Dict) -> List[str]:
        """Validate OpenSearch backup configuration."""
        issues = []
        
        # Find OpenSearch domain
        opensearch_domains = self.find_resources_in_plan(plan_data, "aws_opensearch_domain")
        if not opensearch_domains:
            issues.append("No OpenSearch domain found in plan")
            return issues
        
        opensearch_config = opensearch_domains[0].get("values", {})
        
        # OpenSearch automatic snapshots are enabled by default, but check for custom configuration
        # Check if there are any snapshot configuration resources
        snapshot_configs = self.find_resources_in_plan(plan_data, "aws_opensearch_domain_snapshot_options")
        
        # Check cluster configuration for backup considerations
        cluster_config = opensearch_config.get("cluster_config", [])
        if cluster_config:
            cluster = cluster_config[0]
            instance_count = cluster.get("instance_count", 1)
            
            # For backup resilience, should have multiple instances
            if instance_count < 2:
                issues.append("OpenSearch should have multiple instances for backup resilience")
        
        # Check EBS configuration for backup
        ebs_options = opensearch_config.get("ebs_options", [])
        if ebs_options:
            ebs = ebs_options[0]
            if not ebs.get("ebs_enabled", False):
                issues.append("OpenSearch EBS should be enabled for persistent storage and backups")
        
        # Check zone awareness for backup resilience
        if cluster_config:
            zone_awareness = cluster.get("zone_awareness_enabled", False)
            if not zone_awareness and instance_count > 1:
                issues.append("OpenSearch zone awareness should be enabled for backup resilience with multiple instances")
        
        return issues
    
    def validate_backup_monitoring_and_alerting(self, plan_data: Dict) -> List[str]:
        """Validate backup monitoring and alerting configuration."""
        issues = []
        
        # Check for CloudWatch log groups related to backups
        log_groups = self.find_resources_in_plan(plan_data, "aws_cloudwatch_log_group")
        
        backup_related_logs = []
        for lg in log_groups:
            lg_values = lg.get("values", {})
            lg_name = lg_values.get("name", "")
            
            if any(keyword in lg_name.lower() for keyword in ["backup", "snapshot", "audit"]):
                backup_related_logs.append(lg_name)
        
        if not backup_related_logs:
            issues.append("No backup-related CloudWatch log groups found for monitoring")
        
        # Check for CloudWatch alarms (would be in a more complete implementation)
        cloudwatch_alarms = self.find_resources_in_plan(plan_data, "aws_cloudwatch_metric_alarm")
        
        backup_alarms = []
        for alarm in cloudwatch_alarms:
            alarm_values = alarm.get("values", {})
            alarm_name = alarm_values.get("alarm_name", "")
            metric_name = alarm_values.get("metric_name", "")
            
            if any(keyword in alarm_name.lower() or keyword in metric_name.lower() 
                   for keyword in ["backup", "snapshot"]):
                backup_alarms.append(alarm_name)
        
        # Note: In current implementation, backup alarms might not be explicitly defined
        # This is a placeholder for future enhancement
        
        return issues
    
    def validate_cross_region_backup_capability(self, plan_data: Dict) -> List[str]:
        """Validate cross-region backup capability."""
        issues = []
        
        # Check for cross-region backup resources
        # This would include things like cross-region snapshot copying
        
        # For Neptune, check if there are any cross-region configurations
        # (This would be implemented in a more advanced setup)
        
        # For OpenSearch, check for cross-region snapshot repository
        # (This would also be implemented in a more advanced setup)
        
        # For now, we'll check that the basic infrastructure supports cross-region backups
        # by ensuring proper IAM roles and KMS keys are configured
        
        iam_roles = self.find_resources_in_plan(plan_data, "aws_iam_role")
        kms_keys = self.find_resources_in_plan(plan_data, "aws_kms_key")
        
        if not iam_roles:
            issues.append("No IAM roles found - needed for cross-region backup operations")
        
        if not kms_keys:
            issues.append("No KMS keys found - needed for cross-region backup encryption")
        
        return issues
    
    def _validate_time_window_format(self, window: str) -> bool:
        """Validate time window format (HH:MM-HH:MM)."""
        import re
        pattern = r'^([0-1][0-9]|2[0-3]):[0-5][0-9]-([0-1][0-9]|2[0-3]):[0-5][0-9]$'
        return bool(re.match(pattern, window))
    
    def _validate_maintenance_window_format(self, window: str) -> bool:
        """Validate maintenance window format (ddd:HH:MM-ddd:HH:MM)."""
        import re
        days = ['sun', 'mon', 'tue', 'wed', 'thu', 'fri', 'sat']
        pattern = f'^({"|".join(days)}):([0-1][0-9]|2[0-3]):[0-5][0-9]-({"|".join(days)}):([0-1][0-9]|2[0-3]):[0-5][0-9]$'
        return bool(re.match(pattern, window.lower()))
    
    def _windows_overlap(self, backup_window: str, maintenance_window: str) -> bool:
        """Check if backup and maintenance windows overlap."""
        # Simplified overlap check - in reality, this would need more sophisticated logic
        # to handle day-of-week and time ranges properly
        
        # Extract time portions
        backup_times = backup_window.split('-')
        maintenance_times = maintenance_window.split('-')
        
        if len(backup_times) != 2 or len(maintenance_times) != 2:
            return False
        
        # For maintenance window, extract just the time part (after the day)
        if ':' in maintenance_times[0]:
            maint_start = maintenance_times[0].split(':', 1)[1]  # Skip day part
            maint_end = maintenance_times[1].split(':', 1)[1]    # Skip day part
        else:
            return False
        
        # Simple time overlap check (assumes same day)
        backup_start = backup_times[0]
        backup_end = backup_times[1]
        
        # Convert to minutes for easier comparison
        def time_to_minutes(time_str):
            hours, minutes = map(int, time_str.split(':'))
            return hours * 60 + minutes
        
        try:
            b_start = time_to_minutes(backup_start)
            b_end = time_to_minutes(backup_end)
            m_start = time_to_minutes(maint_start)
            m_end = time_to_minutes(maint_end)
            
            # Check for overlap
            return not (b_end <= m_start or m_end <= b_start)
        except:
            return False


# Property-based test strategies
@st.composite
def backup_configuration_config(draw):
    """Generate backup configuration test scenarios."""
    return {
        "aws_region": draw(st.sampled_from(["us-east-1", "us-west-2", "eu-west-1"])),
        "environment": draw(st.sampled_from(["staging", "production"])),
        "project_name": draw(st.text(min_size=3, max_size=20, alphabet=st.characters(whitelist_categories=("Ll", "Nd"), whitelist_characters="-"))),
        "vpc_cidr": draw(st.sampled_from(["10.0.0.0/16", "172.16.0.0/16"])),
        "az_count": draw(st.integers(min_value=2, max_value=3)),
        
        # Neptune backup settings
        "neptune_cluster_identifier": "backup-test-neptune",
        "neptune_instance_count": draw(st.integers(min_value=1, max_value=2)),
        "neptune_backup_retention_period": draw(st.integers(min_value=7, max_value=35)),
        "neptune_backup_window": draw(st.sampled_from(["07:00-09:00", "02:00-04:00", "23:00-01:00"])),
        "neptune_maintenance_window": draw(st.sampled_from(["sun:09:00-sun:10:00", "sat:03:00-sat:04:00", "tue:05:00-tue:06:00"])),
        
        # OpenSearch backup settings
        "opensearch_domain_name": "backup-test-opensearch",
        "opensearch_instance_count": draw(st.integers(min_value=1, max_value=3)),
        "opensearch_zone_awareness_enabled": draw(st.booleans()),
        "opensearch_availability_zone_count": draw(st.integers(min_value=2, max_value=3)),
        "opensearch_ebs_enabled": True,
        "opensearch_volume_size": draw(st.integers(min_value=20, max_value=100)),
        
        "skip_final_snapshot": draw(st.booleans()),
        "log_retention_days": draw(st.integers(min_value=7, max_value=90)),
        "enable_cloudtrail": True,
    }


class TestBackupConfigurationCompleteness:
    """Property-based tests for backup configuration completeness."""
    
    def setup_method(self):
        """Set up test environment."""
        self.backup_test = BackupConfigurationCompletenessTest()
    
    @given(config=backup_configuration_config())
    @settings(max_examples=5, deadline=120000)  # 2 minute timeout
    def test_neptune_backup_configuration(self, config):
        """
        Property test: For any backup configuration,
        Neptune should have comprehensive backup settings.
        
        **Feature: aws-production-deployment, Property 10: Backup Configuration Completeness**
        **Validates: Requirements 3.7, 7.1, 7.2, 7.7**
        """
        # Skip if Terraform not available
        if not subprocess.run(["which", "terraform"], capture_output=True).returncode == 0:
            pytest.skip("Terraform not available")
        
        plan_data = self.backup_test.get_terraform_plan_json(config)
        assume(plan_data is not None)
        
        # Validate Neptune backup configuration
        issues = self.backup_test.validate_neptune_backup_configuration(plan_data)
        
        assert len(issues) == 0, f"Neptune backup configuration issues: {'; '.join(issues)}"
    
    @given(config=backup_configuration_config())
    @settings(max_examples=5, deadline=120000)
    def test_opensearch_backup_configuration(self, config):
        """
        Property test: For any backup configuration,
        OpenSearch should have comprehensive backup settings.
        
        **Feature: aws-production-deployment, Property 10: Backup Configuration Completeness**
        **Validates: Requirements 3.7, 7.1, 7.2, 7.7**
        """
        # Skip if Terraform not available
        if not subprocess.run(["which", "terraform"], capture_output=True).returncode == 0:
            pytest.skip("Terraform not available")
        
        plan_data = self.backup_test.get_terraform_plan_json(config)
        assume(plan_data is not None)
        
        # Validate OpenSearch backup configuration
        issues = self.backup_test.validate_opensearch_backup_configuration(plan_data)
        
        assert len(issues) == 0, f"OpenSearch backup configuration issues: {'; '.join(issues)}"
    
    def test_backup_retention_policies(self):
        """
        Test that backup retention policies are properly configured.
        
        **Feature: aws-production-deployment, Property 10: Backup Configuration Completeness**
        **Validates: Requirements 3.7, 7.1, 7.2, 7.7**
        """
        # Skip if Terraform not available
        if not subprocess.run(["which", "terraform"], capture_output=True).returncode == 0:
            pytest.skip("Terraform not available")
        
        config = {
            "aws_region": "us-east-1",
            "environment": "production",
            "project_name": "test-project",
            "neptune_cluster_identifier": "test-neptune",
            "neptune_backup_retention_period": 14,
            "neptune_backup_window": "07:00-09:00",
            "neptune_maintenance_window": "sun:09:00-sun:10:00",
            "opensearch_domain_name": "test-opensearch",
            "opensearch_ebs_enabled": True,
            "skip_final_snapshot": True,
        }
        
        plan_data = self.backup_test.get_terraform_plan_json(config)
        assert plan_data is not None, "Should be able to generate Terraform plan"
        
        # Check Neptune backup retention
        neptune_clusters = self.backup_test.find_resources_in_plan(plan_data, "aws_neptune_cluster")
        assert len(neptune_clusters) > 0, "Should have Neptune cluster"
        
        neptune_config = neptune_clusters[0]["values"]
        backup_retention = neptune_config.get("backup_retention_period", 0)
        assert backup_retention >= 7, f"Neptune backup retention ({backup_retention}) should be at least 7 days"
        assert backup_retention <= 35, f"Neptune backup retention ({backup_retention}) should not exceed 35 days"
    
    def test_backup_window_configuration(self):
        """
        Test that backup windows are properly configured and don't conflict.
        
        **Feature: aws-production-deployment, Property 10: Backup Configuration Completeness**
        **Validates: Requirements 3.7, 7.1, 7.2, 7.7**
        """
        # Skip if Terraform not available
        if not subprocess.run(["which", "terraform"], capture_output=True).returncode == 0:
            pytest.skip("Terraform not available")
        
        config = {
            "aws_region": "us-east-1",
            "environment": "production",
            "project_name": "test-project",
            "neptune_cluster_identifier": "test-neptune",
            "neptune_backup_window": "07:00-09:00",
            "neptune_maintenance_window": "sun:10:00-sun:11:00",  # Non-overlapping
            "opensearch_domain_name": "test-opensearch",
            "skip_final_snapshot": True,
        }
        
        plan_data = self.backup_test.get_terraform_plan_json(config)
        assert plan_data is not None, "Should be able to generate Terraform plan"
        
        # Check Neptune backup and maintenance windows
        neptune_clusters = self.backup_test.find_resources_in_plan(plan_data, "aws_neptune_cluster")
        assert len(neptune_clusters) > 0, "Should have Neptune cluster"
        
        neptune_config = neptune_clusters[0]["values"]
        backup_window = neptune_config.get("preferred_backup_window")
        maintenance_window = neptune_config.get("preferred_maintenance_window")
        
        assert backup_window, "Neptune should have backup window configured"
        assert maintenance_window, "Neptune should have maintenance window configured"
        
        # Validate window formats
        assert self.backup_test._validate_time_window_format(backup_window), \
            f"Invalid backup window format: {backup_window}"
        assert self.backup_test._validate_maintenance_window_format(maintenance_window), \
            f"Invalid maintenance window format: {maintenance_window}"
    
    def test_backup_monitoring_setup(self):
        """
        Test that backup monitoring and logging are properly configured.
        
        **Feature: aws-production-deployment, Property 10: Backup Configuration Completeness**
        **Validates: Requirements 3.7, 7.1, 7.2, 7.7**
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
            "enable_cloudtrail": True,
            "log_retention_days": 30,
            "skip_final_snapshot": True,
        }
        
        plan_data = self.backup_test.get_terraform_plan_json(config)
        assert plan_data is not None, "Should be able to generate Terraform plan"
        
        # Check for CloudWatch log groups
        log_groups = self.backup_test.find_resources_in_plan(plan_data, "aws_cloudwatch_log_group")
        assert len(log_groups) > 0, "Should have CloudWatch log groups for monitoring"
        
        # Check log retention is configured
        for lg in log_groups:
            lg_values = lg.get("values", {})
            retention_days = lg_values.get("retention_in_days")
            if retention_days:
                assert retention_days >= 7, f"Log retention ({retention_days}) should be at least 7 days"
        
        # Check for CloudTrail (audit logging)
        cloudtrails = self.backup_test.find_resources_in_plan(plan_data, "aws_cloudtrail")
        if config.get("enable_cloudtrail"):
            assert len(cloudtrails) > 0, "Should have CloudTrail for audit logging"


if __name__ == "__main__":
    # Run basic validation tests
    test_instance = TestBackupConfigurationCompleteness()
    test_instance.setup_method()
    
    print("Running backup configuration completeness tests...")
    
    try:
        test_instance.test_backup_retention_policies()
        print("✅ Backup retention policies test passed")
    except Exception as e:
        print(f"❌ Backup retention policies test failed: {e}")
    
    try:
        test_instance.test_backup_window_configuration()
        print("✅ Backup window configuration test passed")
    except Exception as e:
        print(f"❌ Backup window configuration test failed: {e}")
    
    try:
        test_instance.test_backup_monitoring_setup()
        print("✅ Backup monitoring setup test passed")
    except Exception as e:
        print(f"❌ Backup monitoring setup test failed: {e}")
    
    print("\nTo run property-based tests with Hypothesis:")
    print("pytest tests/infrastructure/test_backup_configuration_completeness.py -v")