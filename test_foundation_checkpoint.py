#!/usr/bin/env python3
"""
Checkpoint Test: Foundation Infrastructure Validation
Validates completion of Tasks 1-3: Terraform foundation, VPC/networking, and security/encryption
"""

import subprocess
import os
from pathlib import Path

def test_foundation_checkpoint():
    """Comprehensive test of foundation infrastructure."""
    terraform_dir = Path("infrastructure/aws-native")
    
    print("🔍 CHECKPOINT: Testing Foundation Infrastructure (Tasks 1-3)")
    print("=" * 60)
    
    os.chdir(terraform_dir)
    
    # Test 1: Terraform Configuration Validation
    print("\n1. TERRAFORM FOUNDATION VALIDATION")
    print("-" * 40)
    
    # Terraform validate
    result = subprocess.run(["terraform", "validate"], capture_output=True, text=True)
    assert result.returncode == 0, f"Terraform validation failed: {result.stderr}"
    print("   ✅ Terraform configuration is valid")
    
    # Check required files
    required_files = ["main.tf", "variables.tf", "backend.conf", "terraform.tfvars.example"]
    for file in required_files:
        assert Path(file).exists(), f"Required file {file} not found"
    print("   ✅ All required configuration files exist")
    
    # Check module structure
    modules = ["vpc", "security"]
    for module in modules:
        module_path = Path(f"modules/{module}")
        assert module_path.exists(), f"Module {module} not found"
        assert (module_path / "main.tf").exists(), f"Module {module} main.tf not found"
        assert (module_path / "variables.tf").exists(), f"Module {module} variables.tf not found"
        assert (module_path / "outputs.tf").exists(), f"Module {module} outputs.tf not found"
    print("   ✅ Module structure is complete")
    
    # Test 2: VPC and Networking Validation
    print("\n2. VPC AND NETWORKING VALIDATION")
    print("-" * 40)
    
    vpc_main = Path("modules/vpc/main.tf")
    with open(vpc_main, 'r') as f:
        vpc_content = f.read()
    
    # Test VPC components
    vpc_components = [
        "aws_vpc",
        "aws_internet_gateway", 
        "aws_subnet.*public",
        "aws_subnet.*private",
        "aws_nat_gateway",
        "aws_route_table",
        "aws_network_acl",
        "aws_flow_log"
    ]
    
    for component in vpc_components:
        if ".*" in component:
            # Handle regex patterns
            base_component = component.split(".*")[0]
            pattern = component.split(".*")[1]
            assert base_component in vpc_content and pattern in vpc_content, \
                f"VPC component {component} not found"
        else:
            assert component in vpc_content, \
                f"VPC component {component} not found"
    print("   ✅ All VPC components are configured")
    
    # Test network security
    assert 'map_public_ip_on_launch = true' not in vpc_content.split('resource "aws_subnet" "private"')[1].split('resource')[0], \
        "Private subnets should not auto-assign public IPs"
    print("   ✅ Network security isolation is properly configured")
    
    # Test 3: Security and Encryption Validation
    print("\n3. SECURITY AND ENCRYPTION VALIDATION")
    print("-" * 40)
    
    security_main = Path("modules/security/main.tf")
    with open(security_main, 'r') as f:
        security_content = f.read()
    
    main_tf = Path("main.tf")
    with open(main_tf, 'r') as f:
        main_content = f.read()
    
    # Test security groups
    security_groups = ["alb", "ecs", "neptune", "opensearch", "elasticache"]
    for sg in security_groups:
        assert f'aws_security_group" "{sg}' in security_content, \
            f"Security group {sg} not found"
    print("   ✅ All security groups are configured")
    
    # Test KMS encryption
    assert 'aws_kms_key' in security_content, "KMS key not found"
    assert 'enable_key_rotation' in security_content, "KMS key rotation not configured"
    print("   ✅ KMS encryption is properly configured")
    
    # Test IAM roles
    iam_roles = ["ecs_task_execution", "ecs_task"]
    for role in iam_roles:
        assert f'aws_iam_role" "{role}' in security_content, \
            f"IAM role {role} not found"
    print("   ✅ IAM roles are properly configured")
    
    # Test Secrets Manager
    assert 'aws_secretsmanager_secret' in main_content, "Secrets Manager not configured"
    assert 'kms_key_id = module.security.kms_key_arn' in main_content, \
        "Secrets Manager KMS encryption not configured"
    print("   ✅ Secrets Manager with KMS encryption is configured")
    
    # Test CloudTrail (if enabled)
    if 'aws_cloudtrail' in main_content:
        assert 'aws_s3_bucket_server_side_encryption_configuration' in main_content, \
            "CloudTrail S3 bucket encryption not configured"
        print("   ✅ CloudTrail with encryption is configured")
    
    # Test 4: Configuration Completeness
    print("\n4. CONFIGURATION COMPLETENESS VALIDATION")
    print("-" * 40)
    
    # Test variables are comprehensive
    variables_tf = Path("variables.tf")
    with open(variables_tf, 'r') as f:
        variables_content = f.read()
    
    required_variables = [
        "aws_region",
        "environment", 
        "project_name",
        "vpc_cidr",
        "availability_zones",
        "public_subnet_cidrs",
        "private_subnet_cidrs",
        "enable_cloudtrail",
        "kms_key_rotation"
    ]
    
    for var in required_variables:
        assert f'variable "{var}"' in variables_content, \
            f"Required variable {var} not found"
    print("   ✅ All required variables are defined")
    
    # Test variable validation rules
    assert 'validation {' in variables_content, "Variable validation rules not found"
    print("   ✅ Variable validation rules are configured")
    
    # Test 5: Module Integration
    print("\n5. MODULE INTEGRATION VALIDATION")
    print("-" * 40)
    
    # Test modules are properly called in main.tf
    assert 'module "vpc"' in main_content, "VPC module not called"
    assert 'module "security"' in main_content, "Security module not called"
    print("   ✅ All modules are properly integrated")
    
    # Test module dependencies
    assert 'vpc_id              = module.vpc.vpc_id' in main_content, \
        "Security module VPC dependency not configured"
    print("   ✅ Module dependencies are properly configured")
    
    # Test common tags
    assert 'local.common_tags' in main_content, "Common tags not configured"
    print("   ✅ Common tagging strategy is implemented")
    
    print("\n" + "=" * 60)
    print("🎉 CHECKPOINT PASSED: Foundation Infrastructure Complete!")
    print("✅ Task 1: Terraform infrastructure foundation - COMPLETED")
    print("✅ Task 2: VPC and networking infrastructure - COMPLETED") 
    print("✅ Task 3: Security and encryption infrastructure - COMPLETED")
    print("✅ Task 4: Foundation infrastructure checkpoint - PASSED")
    print("\n🚀 Ready to proceed with database infrastructure (Task 5)")
    print("=" * 60)
    
    os.chdir("../..")

if __name__ == "__main__":
    test_foundation_checkpoint()