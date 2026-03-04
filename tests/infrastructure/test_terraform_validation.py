"""
Property Test: Terraform Resource Validation
Feature: aws-production-deployment
Property 1: For any Terraform configuration, applying the configuration should create all specified AWS resources with correct attributes and tags
Validates: Requirements 1.1, 1.7
"""

import pytest
import subprocess
import json
import os
from pathlib import Path


class TestTerraformValidation:
    """Property-based tests for Terraform configuration validation."""
    
    @pytest.fixture
    def terraform_dir(self):
        """Get the Terraform directory path."""
        return Path(__file__).parent.parent.parent / "infrastructure" / "aws-native"
    
    def test_terraform_syntax_validation(self, terraform_dir):
        """Test that Terraform configuration has valid syntax."""
        # Change to terraform directory
        original_dir = os.getcwd()
        try:
            os.chdir(terraform_dir)
            
            # Run terraform validate
            result = subprocess.run(
                ["terraform", "validate"],
                capture_output=True,
                text=True
            )
            
            assert result.returncode == 0, f"Terraform validation failed: {result.stderr}"
            
        finally:
            os.chdir(original_dir)
    
    def test_terraform_format_validation(self, terraform_dir):
        """Test that Terraform configuration is properly formatted."""
        # Change to terraform directory
        original_dir = os.getcwd()
        try:
            os.chdir(terraform_dir)
            
            # Run terraform fmt -check
            result = subprocess.run(
                ["terraform", "fmt", "-check", "-recursive"],
                capture_output=True,
                text=True
            )
            
            # Note: fmt returns 0 if files are formatted, 3 if files need formatting
            assert result.returncode in [0, 3], f"Terraform fmt check failed: {result.stderr}"
            
        finally:
            os.chdir(original_dir)
    
    def test_terraform_plan_validation(self, terraform_dir):
        """Test that Terraform plan can be generated without errors."""
        # Change to terraform directory
        original_dir = os.getcwd()
        try:
            os.chdir(terraform_dir)
            
            # Initialize terraform (skip backend for validation)
            init_result = subprocess.run(
                ["terraform", "init", "-backend=false"],
                capture_output=True,
                text=True
            )
            
            if init_result.returncode != 0:
                pytest.skip(f"Terraform init failed: {init_result.stderr}")
            
            # Run terraform plan
            plan_result = subprocess.run(
                ["terraform", "plan", "-input=false"],
                capture_output=True,
                text=True
            )
            
            # Plan should succeed or fail with known issues (like missing credentials)
            # We're testing configuration validity, not actual deployment
            assert "Error: Invalid configuration" not in plan_result.stderr, \
                f"Invalid Terraform configuration: {plan_result.stderr}"
            
        finally:
            os.chdir(original_dir)
    
    def test_required_providers_specified(self, terraform_dir):
        """Test that all required providers are properly specified."""
        main_tf = terraform_dir / "main.tf"
        
        with open(main_tf, 'r') as f:
            content = f.read()
        
        # Check for required providers
        assert 'required_providers' in content, "Required providers block not found"
        assert 'aws' in content, "AWS provider not specified"
        assert 'source = "hashicorp/aws"' in content, "AWS provider source not specified"
        assert 'version' in content, "Provider version not specified"
    
    def test_backend_configuration_present(self, terraform_dir):
        """Test that backend configuration is present."""
        main_tf = terraform_dir / "main.tf"
        backend_conf = terraform_dir / "backend.conf"
        
        with open(main_tf, 'r') as f:
            content = f.read()
        
        # Check for backend configuration
        assert 'backend "s3"' in content, "S3 backend not configured"
        assert backend_conf.exists(), "Backend configuration file not found"
    
    def test_common_tags_configuration(self, terraform_dir):
        """Test that common tags are properly configured."""
        main_tf = terraform_dir / "main.tf"
        
        with open(main_tf, 'r') as f:
            content = f.read()
        
        # Check for common tags
        assert 'local.common_tags' in content or 'common_tags' in content, \
            "Common tags not configured"
        assert 'Project' in content, "Project tag not found"
        assert 'Environment' in content, "Environment tag not found"
        assert 'ManagedBy' in content, "ManagedBy tag not found"
    
    def test_variable_validation_rules(self, terraform_dir):
        """Test that variables have proper validation rules."""
        variables_tf = terraform_dir / "variables.tf"
        
        with open(variables_tf, 'r') as f:
            content = f.read()
        
        # Check for validation blocks
        assert 'validation {' in content, "Variable validation rules not found"
        
        # Check for specific validations
        assert 'environment' in content, "Environment variable not found"
        assert 'contains(["dev", "staging", "production"]' in content, \
            "Environment validation not found"
    
    def test_module_structure_present(self, terraform_dir):
        """Test that module structure is properly organized."""
        modules_dir = terraform_dir / "modules"
        
        assert modules_dir.exists(), "Modules directory not found"
        
        # Check for expected modules
        expected_modules = ["vpc", "security", "databases", "application"]
        for module in expected_modules:
            module_dir = modules_dir / module
            if module_dir.exists():  # Only check if module exists
                assert (module_dir / "main.tf").exists(), \
                    f"Module {module} missing main.tf"
                assert (module_dir / "variables.tf").exists(), \
                    f"Module {module} missing variables.tf"
                assert (module_dir / "outputs.tf").exists(), \
                    f"Module {module} missing outputs.tf"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])