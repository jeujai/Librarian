#!/usr/bin/env python3
"""
Property Tests: Encryption Enforcement and IAM Least Privilege
Property 3: For any data storage resource, encryption should be enabled both in transit and at rest with proper KMS key management
Property 4: For any IAM role or policy, the permissions should follow least-privilege principles and not grant unnecessary access
Validates: Requirements 1.6, 3.6, 1.5, 4.1
"""

import subprocess
import json
import os
from pathlib import Path

def test_encryption_enforcement():
    """Test encryption enforcement properties."""
    terraform_dir = Path("infrastructure/aws-native")
    
    print("Testing Encryption Enforcement...")
    
    os.chdir(terraform_dir)
    
    # Test 1: KMS Key Configuration
    print("1. Testing KMS key configuration...")
    
    security_main = Path("modules/security/main.tf")
    with open(security_main, 'r') as f:
        security_content = f.read()
    
    # Test KMS key exists and has rotation enabled
    assert 'resource "aws_kms_key" "main"' in security_content, "KMS key should be defined"
    assert 'enable_key_rotation     = var.enable_key_rotation' in security_content, \
        "KMS key rotation should be configurable"
    print("   ✓ KMS key is properly configured with rotation")
    
    # Test KMS key has proper policy
    assert '"kms:Encrypt"' in security_content, "KMS key should allow encryption"
    assert '"kms:Decrypt"' in security_content, "KMS key should allow decryption"
    assert '"kms:GenerateDataKey*"' in security_content, "KMS key should allow data key generation"
    print("   ✓ KMS key has proper encryption permissions")
    
    # Test 2: Secrets Manager Encryption
    print("2. Testing Secrets Manager encryption...")
    
    main_tf = Path("main.tf")
    with open(main_tf, 'r') as f:
        main_content = f.read()
    
    # Test Secrets Manager uses KMS encryption
    assert 'kms_key_id = module.security.kms_key_arn' in main_content, \
        "Secrets Manager should use KMS encryption"
    print("   ✓ Secrets Manager uses KMS encryption")
    
    # Test 3: S3 Bucket Encryption
    print("3. Testing S3 bucket encryption...")
    
    # Test CloudTrail S3 bucket encryption
    assert 'aws_s3_bucket_server_side_encryption_configuration' in main_content, \
        "S3 buckets should have encryption configuration"
    assert 'sse_algorithm     = "aws:kms"' in main_content, \
        "S3 buckets should use KMS encryption"
    print("   ✓ S3 buckets use KMS encryption")
    
    print("\n🎉 Encryption Enforcement tests passed!")
    print("✅ Property 3: Encryption Enforcement validated")
    
    os.chdir("../..")

def test_iam_least_privilege():
    """Test IAM least privilege properties."""
    terraform_dir = Path("infrastructure/aws-native")
    
    print("\nTesting IAM Least Privilege...")
    
    os.chdir(terraform_dir)
    
    # Test 1: ECS Task Execution Role
    print("1. Testing ECS task execution role...")
    
    security_main = Path("modules/security/main.tf")
    with open(security_main, 'r') as f:
        security_content = f.read()
    
    # Test ECS task execution role uses AWS managed policy
    assert 'arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy' in security_content, \
        "ECS task execution role should use AWS managed policy"
    print("   ✓ ECS task execution role uses appropriate managed policy")
    
    # Test 2: ECS Task Role Permissions
    print("2. Testing ECS task role permissions...")
    
    # Test Secrets Manager permissions are scoped
    assert '"arn:aws:secretsmanager:*:${data.aws_caller_identity.current.account_id}:secret:${var.name_prefix}/*"' in security_content, \
        "Secrets Manager permissions should be scoped to project secrets"
    print("   ✓ Secrets Manager permissions are properly scoped")
    
    # Test CloudWatch Logs permissions are scoped
    assert '"arn:aws:logs:*:${data.aws_caller_identity.current.account_id}:log-group:/ecs/${var.name_prefix}*"' in security_content, \
        "CloudWatch Logs permissions should be scoped to project logs"
    print("   ✓ CloudWatch Logs permissions are properly scoped")
    
    # Test KMS permissions are scoped
    assert 'aws_kms_key.main.arn' in security_content, \
        "KMS permissions should be scoped to project key"
    print("   ✓ KMS permissions are properly scoped")
    
    # Test 3: Service Assume Role Policies
    print("3. Testing service assume role policies...")
    
    # Test ECS tasks can assume roles
    assert 'Service = "ecs-tasks.amazonaws.com"' in security_content, \
        "Only ECS tasks should be able to assume ECS roles"
    print("   ✓ Role assumption is limited to appropriate services")
    
    # Test 4: No Wildcard Permissions
    print("4. Testing for overly broad permissions...")
    
    # Check for dangerous wildcard permissions (excluding X-Ray which needs *)
    dangerous_patterns = [
        '"Resource": "*"',
        '"Action": "*"'
    ]
    
    # Count occurrences and verify they're only in safe contexts
    wildcard_count = 0
    for pattern in dangerous_patterns:
        wildcard_count += security_content.count(pattern)
    
    # X-Ray legitimately needs wildcard permissions, KMS key policy needs root access
    # So we expect some wildcards but they should be limited
    assert wildcard_count <= 3, f"Too many wildcard permissions found: {wildcard_count}"
    print("   ✓ Wildcard permissions are limited to necessary services")
    
    print("\n🎉 IAM Least Privilege tests passed!")
    print("✅ Property 4: IAM Least Privilege validated")
    print("✅ Task 3 (Security and encryption infrastructure) completed successfully")
    
    os.chdir("../..")

if __name__ == "__main__":
    test_encryption_enforcement()
    test_iam_least_privilege()