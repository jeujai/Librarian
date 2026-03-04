#!/usr/bin/env python3
"""
Quick test of Terraform foundation without pytest dependencies
"""

import subprocess
import os
from pathlib import Path

def test_terraform_foundation():
    """Test the Terraform foundation setup."""
    terraform_dir = Path("infrastructure/aws-native")
    
    print("Testing Terraform foundation...")
    
    # Test 1: Terraform validate
    print("1. Testing terraform validate...")
    os.chdir(terraform_dir)
    result = subprocess.run(["terraform", "validate"], capture_output=True, text=True)
    assert result.returncode == 0, f"Terraform validation failed: {result.stderr}"
    print("   ✓ Terraform validation passed")
    
    # Test 2: Check required files exist
    print("2. Testing required files...")
    required_files = ["main.tf", "variables.tf", "backend.conf"]
    for file in required_files:
        assert Path(file).exists(), f"Required file {file} not found"
    print("   ✓ Required files exist")
    
    # Test 3: Check module structure
    print("3. Testing module structure...")
    modules_dir = Path("modules")
    assert modules_dir.exists(), "Modules directory not found"
    
    vpc_module = modules_dir / "vpc"
    assert vpc_module.exists(), "VPC module not found"
    assert (vpc_module / "main.tf").exists(), "VPC module main.tf not found"
    assert (vpc_module / "variables.tf").exists(), "VPC module variables.tf not found"
    assert (vpc_module / "outputs.tf").exists(), "VPC module outputs.tf not found"
    print("   ✓ Module structure is correct")
    
    # Test 4: Check configuration content
    print("4. Testing configuration content...")
    with open("main.tf", 'r') as f:
        main_content = f.read()
    
    assert 'required_providers' in main_content, "Required providers not found"
    assert 'aws' in main_content, "AWS provider not found"
    assert 'backend "s3"' in main_content, "S3 backend not found"
    assert 'module "vpc"' in main_content, "VPC module not found"
    print("   ✓ Configuration content is correct")
    
    print("\n🎉 All Terraform foundation tests passed!")
    print("✅ Task 1 (Terraform infrastructure foundation) completed successfully")
    
    os.chdir("../..")

if __name__ == "__main__":
    test_terraform_foundation()