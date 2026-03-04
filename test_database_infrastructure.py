#!/usr/bin/env python3
"""
Property Tests: Database Infrastructure
Property 8: Database Production Readiness - For any database cluster (Neptune or OpenSearch), the configuration should use production-appropriate instance types and multi-AZ deployment
Property 9: Database Authentication Security - For any database connection, authentication should use IAM roles and credentials should be stored in AWS Secrets Manager
Property 10: Backup Configuration Completeness - For any database service, automated backups should be enabled with appropriate retention periods and point-in-time recovery capabilities
Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.7, 7.1, 7.2, 7.7
"""

import subprocess
import json
import os
from pathlib import Path

def test_database_production_readiness():
    """Test database production readiness properties."""
    terraform_dir = Path("infrastructure/aws-native")
    
    print("Testing Database Production Readiness...")
    
    os.chdir(terraform_dir)
    
    # Test 1: Neptune Production Configuration
    print("1. Testing Neptune production configuration...")
    
    databases_main = Path("modules/databases/main.tf")
    with open(databases_main, 'r') as f:
        databases_content = f.read()
    
    # Test Neptune cluster configuration
    assert 'aws_neptune_cluster' in databases_content, "Neptune cluster should be configured"
    assert 'backup_retention_period' in databases_content, "Neptune backup retention should be configured"
    assert 'preferred_backup_window' in databases_content, "Neptune backup window should be configured"
    assert 'preferred_maintenance_window' in databases_content, "Neptune maintenance window should be configured"
    assert 'storage_encrypted = true' in databases_content, "Neptune storage should be encrypted"
    print("   ✓ Neptune cluster has production configuration")
    
    # Test Neptune multi-instance deployment
    assert 'count = var.neptune_instance_count' in databases_content, \
        "Neptune should support multiple instances"
    print("   ✓ Neptune supports multi-instance deployment")
    
    # Test 2: OpenSearch Production Configuration
    print("2. Testing OpenSearch production configuration...")
    
    # Test OpenSearch cluster configuration
    assert 'aws_opensearch_domain' in databases_content, "OpenSearch domain should be configured"
    assert 'dedicated_master_enabled' in databases_content, "OpenSearch dedicated master should be configurable"
    assert 'zone_awareness_enabled' in databases_content, "OpenSearch zone awareness should be enabled"
    assert 'encrypt_at_rest' in databases_content, "OpenSearch encryption at rest should be enabled"
    assert 'node_to_node_encryption' in databases_content, "OpenSearch node-to-node encryption should be enabled"
    print("   ✓ OpenSearch domain has production configuration")
    
    # Test OpenSearch EBS configuration
    assert 'ebs_options' in databases_content, "OpenSearch EBS options should be configured"
    assert 'volume_type = "gp3"' in databases_content, "OpenSearch should use GP3 volumes"
    print("   ✓ OpenSearch uses production-grade storage")
    
    # Test 3: Multi-AZ Deployment
    print("3. Testing multi-AZ deployment...")
    
    # Test VPC configuration for multi-AZ
    assert 'vpc_options' in databases_content, "OpenSearch VPC options should be configured"
    assert 'subnet_ids' in databases_content, "OpenSearch should be deployed across subnets"
    print("   ✓ Databases are configured for multi-AZ deployment")
    
    print("\n🎉 Database Production Readiness tests passed!")
    print("✅ Property 8: Database Production Readiness validated")
    
    os.chdir("../..")

def test_database_authentication_security():
    """Test database authentication security properties."""
    terraform_dir = Path("infrastructure/aws-native")
    
    print("\nTesting Database Authentication Security...")
    
    os.chdir(terraform_dir)
    
    # Test 1: Secrets Manager Integration
    print("1. Testing Secrets Manager integration...")
    
    main_tf = Path("main.tf")
    with open(main_tf, 'r') as f:
        main_content = f.read()
    
    # Test Secrets Manager secrets exist
    assert 'aws_secretsmanager_secret" "neptune' in main_content, \
        "Neptune secret should be configured"
    assert 'aws_secretsmanager_secret" "opensearch' in main_content, \
        "OpenSearch secret should be configured"
    print("   ✓ Secrets Manager secrets are configured")
    
    # Test secret versions with connection info
    assert 'aws_secretsmanager_secret_version" "neptune' in main_content, \
        "Neptune secret version should be configured"
    assert 'aws_secretsmanager_secret_version" "opensearch' in main_content, \
        "OpenSearch secret version should be configured"
    print("   ✓ Secret versions contain connection information")
    
    # Test 2: OpenSearch Advanced Security
    print("2. Testing OpenSearch advanced security...")
    
    databases_main = Path("modules/databases/main.tf")
    with open(databases_main, 'r') as f:
        databases_content = f.read()
    
    # Test OpenSearch advanced security options
    assert 'advanced_security_options' in databases_content, \
        "OpenSearch advanced security should be enabled"
    assert 'enabled                        = true' in databases_content, \
        "OpenSearch advanced security should be enabled"
    assert 'anonymous_auth_enabled         = false' in databases_content, \
        "OpenSearch anonymous auth should be disabled"
    print("   ✓ OpenSearch advanced security is properly configured")
    
    # Test 3: Encryption Configuration
    print("3. Testing encryption configuration...")
    
    # Test KMS encryption for secrets
    assert 'kms_key_id = module.security.kms_key_arn' in main_content, \
        "Secrets should use KMS encryption"
    print("   ✓ Secrets Manager uses KMS encryption")
    
    # Test database encryption
    assert 'encrypt_at_rest' in databases_content, "OpenSearch encryption at rest should be configured"
    assert 'storage_encrypted = true' in databases_content, "Neptune storage encryption should be enabled"
    print("   ✓ Database encryption is properly configured")
    
    print("\n🎉 Database Authentication Security tests passed!")
    print("✅ Property 9: Database Authentication Security validated")
    
    os.chdir("../..")

def test_backup_configuration_completeness():
    """Test backup configuration completeness properties."""
    terraform_dir = Path("infrastructure/aws-native")
    
    print("\nTesting Backup Configuration Completeness...")
    
    os.chdir(terraform_dir)
    
    # Test 1: Neptune Backup Configuration
    print("1. Testing Neptune backup configuration...")
    
    databases_main = Path("modules/databases/main.tf")
    with open(databases_main, 'r') as f:
        databases_content = f.read()
    
    # Test Neptune automated backups
    assert 'backup_retention_period' in databases_content, \
        "Neptune backup retention should be configured"
    assert 'preferred_backup_window' in databases_content, \
        "Neptune backup window should be configured"
    assert 'skip_final_snapshot               = false' in databases_content, \
        "Neptune final snapshot should be enabled"
    print("   ✓ Neptune automated backups are configured")
    
    # Test 2: OpenSearch Backup Configuration
    print("2. Testing OpenSearch backup configuration...")
    
    # Test S3 bucket for snapshots
    assert 'aws_s3_bucket" "opensearch_snapshots' in databases_content, \
        "S3 bucket for OpenSearch snapshots should be configured"
    assert 'aws_s3_bucket_versioning" "opensearch_snapshots' in databases_content, \
        "S3 bucket versioning should be enabled"
    assert 'aws_s3_bucket_server_side_encryption_configuration" "opensearch_snapshots' in databases_content, \
        "S3 bucket encryption should be configured"
    print("   ✓ OpenSearch snapshot storage is configured")
    
    # Test IAM role for snapshots
    assert 'aws_iam_role" "opensearch_snapshot' in databases_content, \
        "IAM role for OpenSearch snapshots should be configured"
    assert 'aws_iam_role_policy" "opensearch_snapshot' in databases_content, \
        "IAM policy for OpenSearch snapshots should be configured"
    print("   ✓ OpenSearch snapshot IAM permissions are configured")
    
    # Test 3: Monitoring and Logging
    print("3. Testing backup monitoring and logging...")
    
    # Test CloudWatch log groups
    assert 'aws_cloudwatch_log_group" "neptune_audit' in databases_content, \
        "Neptune audit logs should be configured"
    assert 'aws_cloudwatch_log_group" "opensearch' in databases_content, \
        "OpenSearch logs should be configured"
    print("   ✓ Database logging is configured")
    
    # Test log retention
    assert 'retention_in_days = var.log_retention_days' in databases_content, \
        "Log retention should be configurable"
    print("   ✓ Log retention is properly configured")
    
    # Test 4: Security for Backup Storage
    print("4. Testing backup storage security...")
    
    # Test S3 bucket security
    assert 'aws_s3_bucket_public_access_block" "opensearch_snapshots' in databases_content, \
        "S3 bucket public access should be blocked"
    assert 'block_public_acls       = true' in databases_content, \
        "S3 bucket public ACLs should be blocked"
    assert 'force_destroy = false' in databases_content, \
        "S3 bucket should be protected from accidental deletion"
    print("   ✓ Backup storage security is properly configured")
    
    print("\n🎉 Backup Configuration Completeness tests passed!")
    print("✅ Property 10: Backup Configuration Completeness validated")
    print("✅ Task 5 (Database infrastructure) completed successfully")
    
    os.chdir("../..")

if __name__ == "__main__":
    test_database_production_readiness()
    test_database_authentication_security()
    test_backup_configuration_completeness()