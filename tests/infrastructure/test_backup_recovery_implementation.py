#!/usr/bin/env python3
"""
Property Test: Backup and Recovery Implementation
Tests comprehensive backup and recovery infrastructure for Task 11.

This test validates:
- Requirements 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7
- Property 18: Backup and Recovery Implementation
"""

import json
import os
import sys
import unittest
import subprocess
from pathlib import Path

# Add the project root to the Python path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

class TestBackupRecoveryImplementation(unittest.TestCase):
    """Test backup and recovery infrastructure implementation."""
    
    @classmethod
    def setUpClass(cls):
        """Set up test fixtures."""
        cls.terraform_dir = project_root / "infrastructure" / "aws-native"
        cls.main_tf = cls.terraform_dir / "main.tf"
        cls.variables_tf = cls.terraform_dir / "variables.tf"
        cls.outputs_tf = cls.terraform_dir / "outputs.tf"
        cls.backup_module_dir = cls.terraform_dir / "modules" / "backup"
        
        # Read Terraform files
        cls.main_tf_content = cls.main_tf.read_text() if cls.main_tf.exists() else ""
        cls.variables_tf_content = cls.variables_tf.read_text() if cls.variables_tf.exists() else ""
        cls.outputs_tf_content = cls.outputs_tf.read_text() if cls.outputs_tf.exists() else ""
        
        # Read backup module files
        cls.backup_main_tf = cls.backup_module_dir / "main.tf"
        cls.backup_variables_tf = cls.backup_module_dir / "variables.tf"
        cls.backup_outputs_tf = cls.backup_module_dir / "outputs.tf"
        
        cls.backup_main_content = cls.backup_main_tf.read_text() if cls.backup_main_tf.exists() else ""
        cls.backup_variables_content = cls.backup_variables_tf.read_text() if cls.backup_variables_tf.exists() else ""
        cls.backup_outputs_content = cls.backup_outputs_tf.read_text() if cls.backup_outputs_tf.exists() else ""
        
        # Get terraform plan for backup module
        cls.backup_plan = cls._get_backup_plan()
    
    @classmethod
    def _get_backup_plan(cls):
        """Get terraform plan for backup module to validate resources."""
        try:
            original_dir = os.getcwd()
            os.chdir(cls.terraform_dir)
            
            # Run terraform plan for backup module
            result = subprocess.run(
                ["terraform", "plan", "-target=module.backup", "-out=/tmp/backup_plan"],
                capture_output=True,
                text=True
            )
            
            if result.returncode == 0:
                # Get plan in JSON format
                show_result = subprocess.run(
                    ["terraform", "show", "-json", "/tmp/backup_plan"],
                    capture_output=True,
                    text=True
                )
                if show_result.returncode == 0:
                    return json.loads(show_result.stdout)
            
            return {}
        except Exception as e:
            print(f"Warning: Could not get backup plan: {e}")
            return {}
        finally:
            os.chdir(original_dir)
    
    def test_backup_module_integration(self):
        """Test backup module is properly integrated in main.tf."""
        # Check backup module is called in main.tf
        self.assertIn("module \"backup\"", self.main_tf_content)
        self.assertIn("source = \"./modules/backup\"", self.main_tf_content)
        
        # Check backup module has cross-region provider
        self.assertIn("aws.backup_region = aws.backup_region", self.main_tf_content)
        
        print("✅ Backup module integration validated")
    
    def test_neptune_backup_configuration(self):
        """Test Neptune automated backup configuration (Requirement 7.1)."""
        # Check Neptune cluster has backup configuration in databases module call
        self.assertIn("backup_retention_period", self.main_tf_content)
        self.assertIn("neptune_backup_window", self.main_tf_content)
        
        # Check backup retention variable exists
        self.assertIn("neptune_backup_retention", self.variables_tf_content)
        self.assertIn("neptune_backup_window", self.variables_tf_content)
        
        # Check point-in-time recovery is mentioned in outputs
        self.assertIn("point_in_time_recovery", self.outputs_tf_content)
        
        print("✅ Neptune backup configuration validated")
    
    def test_opensearch_backup_configuration(self):
        """Test OpenSearch snapshot configuration (Requirement 7.2)."""
        # Check S3 bucket for OpenSearch snapshots in backup module
        self.assertIn("opensearch_snapshots", self.backup_main_content)
        self.assertIn("aws_s3_bucket", self.backup_main_content)
        
        # Check IAM role for backup Lambda
        self.assertIn("backup_lambda", self.backup_main_content)
        self.assertIn("lambda.amazonaws.com", self.backup_main_content)
        
        # Check lifecycle configuration for snapshots
        self.assertIn("lifecycle_configuration", self.backup_main_content)
        self.assertIn("STANDARD_IA", self.backup_main_content)
        self.assertIn("GLACIER", self.backup_main_content)
        self.assertIn("DEEP_ARCHIVE", self.backup_main_content)
        
        print("✅ OpenSearch backup configuration validated")
    
    def test_cross_region_backup_replication(self):
        """Test cross-region backup replication (Requirement 7.5)."""
        # Check cross-region backup variables
        self.assertIn("enable_cross_region_backup", self.variables_tf_content)
        self.assertIn("backup_region", self.variables_tf_content)
        
        # Check backup region provider in main.tf
        self.assertIn('alias  = "backup_region"', self.main_tf_content)
        
        # Check S3 replication configuration in backup module
        self.assertIn("backup_replication", self.backup_main_content)
        self.assertIn("replication_configuration", self.backup_main_content)
        
        # Check replication IAM role
        self.assertIn("s3-replication-role", self.backup_main_content)
        self.assertIn("s3.amazonaws.com", self.backup_main_content)
        
        print("✅ Cross-region backup replication validated")
    
    def test_backup_management_automation(self):
        """Test automated backup management (Requirement 7.3)."""
        # Check backup manager Lambda function in backup module
        self.assertIn("backup_manager", self.backup_main_content)
        self.assertIn("aws_lambda_function", self.backup_main_content)
        
        # Check backup schedule
        self.assertIn("backup_schedule", self.backup_main_content)
        self.assertIn("cron(0 3 * * ? *)", self.backup_main_content)  # Daily at 3 AM
        
        # Check Lambda permissions and IAM role
        self.assertIn("backup-lambda-role", self.backup_main_content)
        self.assertIn("lambda.amazonaws.com", self.backup_main_content)
        
        # Check Lambda has necessary permissions
        self.assertIn("neptune:DescribeDBClusters", self.backup_main_content)
        self.assertIn("es:ESHttpPost", self.backup_main_content)
        self.assertIn("s3:ListBucket", self.backup_main_content)
        
        print("✅ Backup management automation validated")
    
    def test_backup_monitoring_and_alerting(self):
        """Test backup monitoring and alerting (Requirement 7.6)."""
        # Check backup monitoring alarms in backup module
        self.assertIn("backup_failures", self.backup_main_content)
        self.assertIn("backup_success", self.backup_main_content)
        self.assertIn("BackupErrors", self.backup_main_content)
        self.assertIn("BackupSuccess", self.backup_main_content)
        
        # Check backup monitoring dashboard
        self.assertIn("backup_monitoring", self.backup_main_content)
        self.assertIn("aws_cloudwatch_dashboard", self.backup_main_content)
        
        # Check SNS topic integration in main.tf
        self.assertIn("sns_topic_arn", self.main_tf_content)
        
        # Check CloudWatch metrics namespace
        self.assertIn("Custom/Backup", self.backup_main_content)
        
        print("✅ Backup monitoring and alerting validated")
    
    def test_disaster_recovery_procedures(self):
        """Test disaster recovery documentation (Requirement 7.4)."""
        # Check disaster recovery procedures parameter in backup module
        self.assertIn("disaster_recovery_procedures", self.backup_main_content)
        self.assertIn("aws_ssm_parameter", self.backup_main_content)
        
        # Check recovery procedures content
        self.assertIn("neptune_recovery", self.backup_main_content)
        self.assertIn("opensearch_recovery", self.backup_main_content)
        self.assertIn("application_recovery", self.backup_main_content)
        self.assertIn("cross_region_recovery", self.backup_main_content)
        
        # Check RTO and RPO targets
        self.assertIn("4 hours", self.backup_main_content)
        self.assertIn("1 hour", self.backup_main_content)
        
        # Check testing procedures
        self.assertIn("testing_procedures", self.backup_main_content)
        self.assertIn("monthly_dr_test", self.backup_main_content)
        
        print("✅ Disaster recovery procedures validated")
    
    def test_backup_storage_security(self):
        """Test backup storage security and encryption."""
        # Check S3 bucket encryption in backup module
        self.assertIn("server_side_encryption_configuration", self.backup_main_content)
        self.assertIn("aws:kms", self.backup_main_content)
        
        # Check S3 bucket public access block
        self.assertIn("public_access_block", self.backup_main_content)
        self.assertIn("block_public_acls", self.backup_main_content)
        
        # Check S3 bucket versioning
        self.assertIn("versioning_configuration", self.backup_main_content)
        self.assertIn("Enabled", self.backup_main_content)
        
        # Check force_destroy is false for backup buckets
        self.assertIn("force_destroy = false", self.backup_main_content)
        
        print("✅ Backup storage security validated")
    
    def test_point_in_time_recovery_capabilities(self):
        """Test point-in-time recovery capabilities (Requirement 7.7)."""
        # Check Neptune PITR configuration in main.tf
        self.assertIn("backup_retention_period", self.main_tf_content)
        
        # Check recovery procedures mention PITR in backup module
        self.assertIn("point-in-time recovery", self.backup_main_content)
        self.assertIn("restore-db-cluster-to-point-in-time", self.backup_main_content)
        
        # Check backup retention variables
        self.assertIn("backup_retention_days", self.variables_tf_content)
        
        # Check outputs mention PITR capabilities
        self.assertIn("point_in_time_recovery", self.outputs_tf_content)
        
        print("✅ Point-in-time recovery capabilities validated")
    
    def test_backup_retention_policies(self):
        """Test backup retention policies and lifecycle management."""
        # Check backup retention variables with validation
        self.assertIn("backup_retention_days", self.variables_tf_content)
        self.assertIn("validation", self.variables_tf_content)
        
        # Check S3 lifecycle policies in backup module
        self.assertIn("lifecycle_configuration", self.backup_main_content)
        self.assertIn("transition", self.backup_main_content)
        self.assertIn("expiration", self.backup_main_content)
        
        # Check different storage classes
        self.assertIn("STANDARD_IA", self.backup_main_content)
        self.assertIn("GLACIER", self.backup_main_content)
        self.assertIn("DEEP_ARCHIVE", self.backup_main_content)
        
        print("✅ Backup retention policies validated")
    
    def test_backup_outputs_completeness(self):
        """Test backup and recovery outputs are comprehensive."""
        # Check backup outputs section exists
        self.assertIn("backup_and_recovery", self.outputs_tf_content)
        
        # Check Neptune backup outputs
        self.assertIn("neptune_backup", self.outputs_tf_content)
        self.assertIn("backup_retention_period", self.outputs_tf_content)
        
        # Check OpenSearch backup outputs
        self.assertIn("opensearch_backup", self.outputs_tf_content)
        self.assertIn("snapshot_bucket", self.outputs_tf_content)
        
        # Check disaster recovery outputs
        self.assertIn("disaster_recovery", self.outputs_tf_content)
        self.assertIn("rto_target", self.outputs_tf_content)
        self.assertIn("rpo_target", self.outputs_tf_content)
        
        # Check backup management outputs
        self.assertIn("backup_management", self.outputs_tf_content)
        self.assertIn("lambda_function_name", self.outputs_tf_content)
        
        print("✅ Backup outputs completeness validated")
    
    def test_backup_variables_validation(self):
        """Test backup variables have proper validation rules."""
        # Check backup retention validation
        self.assertIn("backup_retention_days >= 1", self.variables_tf_content)
        self.assertIn("backup_retention_days <= 365", self.variables_tf_content)
        
        # Check backup region validation
        self.assertIn("backup_region", self.variables_tf_content)
        self.assertIn("regex", self.variables_tf_content)
        
        # Check snapshot hour validation
        self.assertIn("opensearch_snapshot_hour", self.variables_tf_content)
        self.assertIn("opensearch_snapshot_hour >= 0", self.variables_tf_content)
        self.assertIn("opensearch_snapshot_hour <= 23", self.variables_tf_content)
        
        print("✅ Backup variables validation validated")

def main():
    """Run the backup and recovery implementation tests."""
    print("🧪 Testing Backup and Recovery Implementation")
    print("=" * 50)
    
    # Create test suite
    suite = unittest.TestLoader().loadTestsFromTestCase(TestBackupRecoveryImplementation)
    
    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    # Print summary
    print("\n" + "=" * 50)
    if result.wasSuccessful():
        print("✅ All backup and recovery implementation tests passed!")
        print(f"📊 Tests run: {result.testsRun}")
        print("🎯 Requirements validated: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7")
        print("🏗️  Property 18: Backup and Recovery Implementation - VALIDATED")
        return 0
    else:
        print("❌ Some backup and recovery implementation tests failed!")
        print(f"📊 Tests run: {result.testsRun}")
        print(f"❌ Failures: {len(result.failures)}")
        print(f"💥 Errors: {len(result.errors)}")
        return 1

if __name__ == "__main__":
    exit(main())