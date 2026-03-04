#!/usr/bin/env python3
"""
Test script to verify CLI functionality for production deployment validation.
"""

import subprocess
import sys
import json
import tempfile
import os
from pathlib import Path

def test_cli_help():
    """Test that CLI help works."""
    print("Testing CLI help...")
    result = subprocess.run([
        sys.executable, '-m', 'multimodal_librarian.validation.cli', '--help'
    ], capture_output=True, text=True, cwd='src')
    
    if result.returncode == 0:
        print("✅ CLI help works")
        return True
    else:
        print(f"❌ CLI help failed: {result.stderr}")
        return False

def test_cli_config_validation():
    """Test CLI with configuration file."""
    print("Testing CLI with configuration file...")
    
    # Create a temporary config file
    config = {
        "task_definition_arn": "arn:aws:ecs:us-east-1:123456789012:task-definition/test:1",
        "iam_role_arn": "arn:aws:iam::123456789012:role/test-role",
        "load_balancer_arn": "arn:aws:elasticloadbalancing:us-east-1:123456789012:loadbalancer/app/test-lb/123",
        "target_environment": "test",
        "region": "us-east-1"
    }
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(config, f)
        config_file = f.name
    
    try:
        # Test with dry-run (this will fail validation but should not crash)
        result = subprocess.run([
            sys.executable, '-m', 'multimodal_librarian.validation.cli',
            '--config', config_file,
            '--output-format', 'json'
        ], capture_output=True, text=True, cwd='src')
        
        # We expect this to fail (exit code 1) because we're using fake ARNs
        # But it should not crash (exit code != 2)
        if result.returncode in [0, 1]:
            print("✅ CLI config validation works (expected failure with fake ARNs)")
            return True
        else:
            print(f"❌ CLI config validation crashed: {result.stderr}")
            return False
            
    finally:
        os.unlink(config_file)

def test_cli_argument_validation():
    """Test CLI argument validation."""
    print("Testing CLI argument validation...")
    
    # Test missing required arguments
    result = subprocess.run([
        sys.executable, '-m', 'multimodal_librarian.validation.cli'
    ], capture_output=True, text=True, cwd='src')
    
    # Should fail with exit code 2 (argument error)
    if result.returncode == 2 and "required" in result.stderr.lower():
        print("✅ CLI argument validation works")
        return True
    else:
        print(f"❌ CLI argument validation failed: {result.stderr}")
        return False

def test_cli_output_formats():
    """Test different output formats."""
    print("Testing CLI output formats...")
    
    config = {
        "task_definition_arn": "arn:aws:ecs:us-east-1:123456789012:task-definition/test:1",
        "iam_role_arn": "arn:aws:iam::123456789012:role/test-role", 
        "load_balancer_arn": "arn:aws:elasticloadbalancing:us-east-1:123456789012:loadbalancer/app/test-lb/123",
        "target_environment": "test"
    }
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(config, f)
        config_file = f.name
    
    try:
        # Test JSON output
        result = subprocess.run([
            sys.executable, '-m', 'multimodal_librarian.validation.cli',
            '--config', config_file,
            '--output-format', 'json'
        ], capture_output=True, text=True, cwd='src')
        
        if result.returncode in [0, 1]:  # May fail validation but should produce output
            try:
                # Try to parse JSON output
                json.loads(result.stdout)
                print("✅ JSON output format works")
                return True
            except json.JSONDecodeError:
                print(f"❌ JSON output format invalid: {result.stdout[:200]}")
                return False
        else:
            print(f"❌ CLI output format test crashed: {result.stderr}")
            return False
            
    finally:
        os.unlink(config_file)

def main():
    """Run all CLI tests."""
    print("🧪 Testing Production Deployment Validation CLI")
    print("=" * 50)
    
    tests = [
        test_cli_help,
        test_cli_argument_validation,
        test_cli_config_validation,
        test_cli_output_formats
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        try:
            if test():
                passed += 1
            print()
        except Exception as e:
            print(f"❌ Test {test.__name__} crashed: {e}")
            print()
    
    print("=" * 50)
    print(f"Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All CLI tests passed!")
        return 0
    else:
        print("⚠️  Some CLI tests failed")
        return 1

if __name__ == '__main__':
    sys.exit(main())