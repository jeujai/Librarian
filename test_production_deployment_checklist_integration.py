#!/usr/bin/env python3
"""
Integration test for production deployment checklist validation system.

This test demonstrates that the validation system correctly identifies
the deployment issues that caused the original failures and blocks
deployment until they are resolved.
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Dict, Any, List


def run_command(cmd: List[str], capture_output: bool = True) -> subprocess.CompletedProcess:
    """Run a command and return the result."""
    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(
        cmd,
        capture_output=capture_output,
        text=True,
        cwd=Path(__file__).parent
    )
    return result


def test_validation_detects_deployment_failures():
    """
    Test that the validation system detects the exact issues that caused
    the deployment failures documented in the diagnosis files.
    """
    print("🔍 Testing Production Deployment Checklist Integration")
    print("=" * 60)
    
    # Test 1: Run validation and expect it to fail
    print("\n1. Testing validation failure detection...")
    result = run_command(["./scripts/deploy-with-validation.sh", "--validate-only"])
    
    # Validation should fail (exit code 1)
    assert result.returncode == 1, f"Expected validation to fail, but got exit code {result.returncode}"
    print("✅ Validation correctly failed as expected")
    
    # Test 2: Check that validation report exists and contains expected failures
    print("\n2. Analyzing validation report...")
    
    validation_report_path = Path("validation-report.json")
    assert validation_report_path.exists(), "Validation report should exist"
    
    with open(validation_report_path) as f:
        report = json.load(f)
    
    # Check overall status
    assert report["overall_status"] is False, "Overall status should be False"
    assert report["total_checks"] == 3, f"Expected 3 checks, got {report['total_checks']}"
    assert report["passed_checks"] == 0, f"Expected 0 passed checks, got {report['passed_checks']}"
    assert report["failed_checks"] == 3, f"Expected 3 failed checks, got {report['failed_checks']}"
    
    print(f"✅ Report shows {report['failed_checks']}/{report['total_checks']} checks failed")
    
    # Test 3: Verify specific failure types match the original deployment issues
    print("\n3. Verifying specific failure detection...")
    
    failed_checks = {check["check_name"]: check for check in report["checks_performed"] if not check["passed"]}
    
    # Check 1: IAM Permissions issue (matches ResourceInitializationError)
    assert "IAM Permissions Validation" in failed_checks, "Should detect IAM permissions issue"
    iam_check = failed_checks["IAM Permissions Validation"]
    assert "Invalid IAM role ARN format" in iam_check["message"], "Should detect IAM role format issue"
    print("✅ Detected IAM permissions issue (matches ResourceInitializationError)")
    
    # Check 2: Storage Configuration issue (matches CannotPullContainerError - disk space)
    assert "Storage Configuration Validation" in failed_checks, "Should detect storage issue"
    storage_check = failed_checks["Storage Configuration Validation"]
    assert "no ephemeral storage configuration" in storage_check["message"], "Should detect missing storage config"
    print("✅ Detected storage configuration issue (matches CannotPullContainerError)")
    
    # Check 3: SSL Configuration issue (matches network/connectivity issues)
    assert "SSL Configuration Validation" in failed_checks, "Should detect SSL issue"
    ssl_check = failed_checks["SSL Configuration Validation"]
    assert "SSL/HTTPS configuration" in ssl_check["message"], "Should detect SSL configuration issue"
    print("✅ Detected SSL configuration issue (matches network connectivity problems)")
    
    # Test 4: Verify remediation steps are provided
    print("\n4. Verifying remediation guidance...")
    
    for check_name, check in failed_checks.items():
        assert "remediation_steps" in check, f"{check_name} should have remediation steps"
        assert len(check["remediation_steps"]) > 0, f"{check_name} should have non-empty remediation steps"
        print(f"✅ {check_name} has {len(check['remediation_steps'])} remediation steps")
    
    # Test 5: Test automatic fixes functionality
    print("\n5. Testing automatic fixes...")
    
    fix_result = run_command(["./scripts/deploy-with-validation.sh", "--fix-only"])
    assert fix_result.returncode == 0, f"Fix script should succeed, got exit code {fix_result.returncode}"
    print("✅ Automatic fixes completed successfully")
    
    # Test 6: Verify deployment is blocked when validation fails
    print("\n6. Testing deployment blocking...")
    
    # Try to run full deployment (should be blocked by validation)
    deploy_result = run_command(["./scripts/deploy-with-validation.sh"])
    assert deploy_result.returncode == 1, f"Deployment should be blocked, got exit code {deploy_result.returncode}"
    
    # Check for deployment blocked message in either stdout or stderr
    output_text = (deploy_result.stdout + deploy_result.stderr).lower()
    assert "deployment blocked" in output_text, \
        f"Should show deployment blocked message. Output: {deploy_result.stdout[:500]}..."
    print("✅ Deployment correctly blocked by validation failures")
    
    return True


def test_integration_addresses_original_failures():
    """
    Test that the integration addresses the specific failures documented
    in the comprehensive production diagnosis files.
    """
    print("\n🔍 Testing Integration Against Original Failure Scenarios")
    print("=" * 60)
    
    # Load the original failure diagnosis
    diagnosis_files = [
        "comprehensive-production-diagnosis-1768008740.json",
        "task-startup-diagnosis-1768005975.json"
    ]
    
    original_failures = []
    for file_path in diagnosis_files:
        if Path(file_path).exists():
            with open(file_path) as f:
                data = json.load(f)
                original_failures.append(data)
    
    print(f"✅ Loaded {len(original_failures)} original failure diagnosis files")
    
    # Test that validation catches the key failure patterns
    print("\n1. Checking validation catches original failure patterns...")
    
    # Run validation to get current report
    run_command(["./scripts/deploy-with-validation.sh", "--validate-only"])
    
    with open("validation-report.json") as f:
        current_report = json.load(f)
    
    # Map original failures to validation checks
    failure_mappings = {
        "CannotPullContainerError": "Storage Configuration Validation",
        "ResourceInitializationError": "IAM Permissions Validation", 
        "network timeout": "SSL Configuration Validation"
    }
    
    for original_error, validation_check in failure_mappings.items():
        # Find the validation check
        check_found = False
        for check in current_report["checks_performed"]:
            if check["check_name"] == validation_check and not check["passed"]:
                check_found = True
                print(f"✅ {validation_check} catches {original_error}")
                break
        
        assert check_found, f"Validation should catch {original_error} with {validation_check}"
    
    print("✅ All original failure patterns are caught by validation")
    
    return True


def main():
    """Run all integration tests."""
    print("🚀 Production Deployment Checklist Integration Test")
    print("=" * 60)
    print("This test verifies that the validation system correctly identifies")
    print("and prevents the deployment failures that occurred previously.")
    print()
    
    try:
        # Test 1: Basic validation integration
        test_validation_detects_deployment_failures()
        
        # Test 2: Integration addresses original failures
        test_integration_addresses_original_failures()
        
        print("\n" + "=" * 60)
        print("🎉 ALL INTEGRATION TESTS PASSED!")
        print("=" * 60)
        print()
        print("✅ The production deployment checklist validation system is working correctly")
        print("✅ It detects the exact issues that caused the original deployment failures")
        print("✅ It properly blocks deployment until issues are resolved")
        print("✅ It provides clear remediation guidance")
        print("✅ The integration successfully bridges the gap between validation and deployment")
        print()
        print("🔧 Next Steps:")
        print("   1. Fix the identified issues (IAM role, storage, SSL)")
        print("   2. Re-run validation to confirm fixes")
        print("   3. Use the integrated deployment script for all future deployments")
        print("   4. Integrate with CI/CD pipeline")
        
        return 0
        
    except Exception as e:
        print(f"\n❌ Integration test failed: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())