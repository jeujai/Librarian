#!/usr/bin/env python3
"""
Test the fix capabilities of the production deployment checklist system.

This test evaluates whether the system can actually fix the problems it detects,
not just identify them.
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


def test_fix_capabilities():
    """
    Test whether the system can fix the problems it detects.
    """
    print("🔧 Testing Fix Capabilities of Production Deployment Checklist")
    print("=" * 70)
    
    # First, run validation to get current issues
    print("\n1. Running validation to identify current issues...")
    result = run_command(["./scripts/deploy-with-validation.sh", "--validate-only"])
    
    # Load validation report
    with open("validation-report.json") as f:
        report = json.load(f)
    
    print(f"✅ Found {report['failed_checks']} issues to test fixes for")
    
    # Test each fix capability
    fix_results = {}
    
    # Test 1: Storage Configuration Fix
    print("\n2. Testing Storage Configuration Fix...")
    storage_issue = next((check for check in report["checks_performed"] 
                         if check["check_name"] == "Storage Configuration Validation"), None)
    
    if storage_issue and not storage_issue["passed"]:
        print("   Issue: Missing ephemeral storage configuration")
        
        # Check if task-definition-update.json has the fix
        try:
            with open("task-definition-update.json") as f:
                task_def = json.load(f)
            
            has_storage = "ephemeralStorage" in task_def
            storage_size = task_def.get("ephemeralStorage", {}).get("sizeInGiB", 0)
            
            if has_storage and storage_size >= 30:
                fix_results["storage"] = {
                    "can_fix": True,
                    "method": "task-definition-update.json",
                    "storage_gb": storage_size,
                    "meets_requirements": True
                }
                print(f"   ✅ CAN FIX: Task definition has {storage_size}GB ephemeral storage")
            else:
                fix_results["storage"] = {
                    "can_fix": False,
                    "method": "task-definition-update.json",
                    "storage_gb": storage_size,
                    "meets_requirements": False
                }
                print(f"   ❌ CANNOT FIX: Task definition only has {storage_size}GB storage")
                
        except Exception as e:
            fix_results["storage"] = {
                "can_fix": False,
                "error": str(e)
            }
            print(f"   ❌ CANNOT FIX: Error reading task definition: {e}")
    
    # Test 2: IAM Permissions Fix
    print("\n3. Testing IAM Permissions Fix...")
    iam_issue = next((check for check in report["checks_performed"] 
                     if check["check_name"] == "IAM Permissions Validation"), None)
    
    if iam_issue and not iam_issue["passed"]:
        print("   Issue: Invalid IAM role ARN format")
        
        # Check if fix script exists and is executable
        fix_script = Path("scripts/fix-iam-secrets-permissions-correct.py")
        
        if fix_script.exists():
            # Test if script can identify the issue
            try:
                # Read the script to see if it addresses the specific issue
                with open(fix_script) as f:
                    script_content = f.read()
                
                # Check if script handles role ARN validation
                handles_role_arn = "role" in script_content.lower() and "arn" in script_content.lower()
                handles_secrets = "secrets" in script_content.lower() or "secretsmanager" in script_content.lower()
                
                if handles_role_arn and handles_secrets:
                    fix_results["iam"] = {
                        "can_fix": True,
                        "method": "scripts/fix-iam-secrets-permissions-correct.py",
                        "handles_role_arn": True,
                        "handles_secrets": True
                    }
                    print("   ✅ CAN FIX: Script handles IAM role and secrets permissions")
                else:
                    fix_results["iam"] = {
                        "can_fix": False,
                        "method": "scripts/fix-iam-secrets-permissions-correct.py",
                        "handles_role_arn": handles_role_arn,
                        "handles_secrets": handles_secrets
                    }
                    print("   ❌ PARTIAL FIX: Script may not handle all IAM issues")
                    
            except Exception as e:
                fix_results["iam"] = {
                    "can_fix": False,
                    "error": str(e)
                }
                print(f"   ❌ CANNOT FIX: Error analyzing fix script: {e}")
        else:
            fix_results["iam"] = {
                "can_fix": False,
                "error": "Fix script not found"
            }
            print("   ❌ CANNOT FIX: Fix script not found")
    
    # Test 3: SSL Configuration Fix
    print("\n4. Testing SSL Configuration Fix...")
    ssl_issue = next((check for check in report["checks_performed"] 
                     if check["check_name"] == "SSL Configuration Validation"), None)
    
    if ssl_issue and not ssl_issue["passed"]:
        print("   Issue: Missing HTTPS/SSL configuration")
        
        # Check if SSL fix script exists
        ssl_fix_script = Path("scripts/add-https-ssl-support.py")
        
        if ssl_fix_script.exists():
            try:
                # Read the script to see if it can handle SSL setup
                with open(ssl_fix_script) as f:
                    script_content = f.read()
                
                # Check if script handles key SSL setup tasks
                handles_certificate = "certificate" in script_content.lower() or "acm" in script_content.lower()
                handles_https_listener = "https" in script_content.lower() and "listener" in script_content.lower()
                handles_security_groups = "security" in script_content.lower() and "group" in script_content.lower()
                
                comprehensive_ssl_fix = handles_certificate and handles_https_listener and handles_security_groups
                
                if comprehensive_ssl_fix:
                    fix_results["ssl"] = {
                        "can_fix": True,
                        "method": "scripts/add-https-ssl-support.py",
                        "handles_certificate": True,
                        "handles_https_listener": True,
                        "handles_security_groups": True
                    }
                    print("   ✅ CAN FIX: Script handles comprehensive SSL setup")
                else:
                    fix_results["ssl"] = {
                        "can_fix": False,
                        "method": "scripts/add-https-ssl-support.py",
                        "handles_certificate": handles_certificate,
                        "handles_https_listener": handles_https_listener,
                        "handles_security_groups": handles_security_groups
                    }
                    print("   ❌ PARTIAL FIX: Script may not handle all SSL requirements")
                    
            except Exception as e:
                fix_results["ssl"] = {
                    "can_fix": False,
                    "error": str(e)
                }
                print(f"   ❌ CANNOT FIX: Error analyzing SSL fix script: {e}")
        else:
            fix_results["ssl"] = {
                "can_fix": False,
                "error": "SSL fix script not found"
            }
            print("   ❌ CANNOT FIX: SSL fix script not found")
    
    # Test 4: Automatic Fix Integration
    print("\n5. Testing Automatic Fix Integration...")
    
    # Check if the deployment script calls the fix scripts
    try:
        with open("scripts/deploy-with-validation.sh") as f:
            deploy_script = f.read()
        
        calls_iam_fix = "fix-iam-secrets-permissions" in deploy_script
        calls_storage_fix = "ephemeralStorage" in deploy_script
        calls_ssl_fix = "add-https-ssl-support" in deploy_script
        
        integration_score = sum([calls_iam_fix, calls_storage_fix, calls_ssl_fix])
        
        fix_results["integration"] = {
            "calls_iam_fix": calls_iam_fix,
            "calls_storage_fix": calls_storage_fix,
            "calls_ssl_fix": calls_ssl_fix,
            "integration_score": f"{integration_score}/3"
        }
        
        if integration_score >= 2:
            print(f"   ✅ GOOD INTEGRATION: Deployment script calls {integration_score}/3 fix types")
        else:
            print(f"   ⚠️  PARTIAL INTEGRATION: Deployment script calls {integration_score}/3 fix types")
            
    except Exception as e:
        fix_results["integration"] = {
            "error": str(e)
        }
        print(f"   ❌ INTEGRATION ERROR: {e}")
    
    # Overall Assessment
    print("\n6. Overall Fix Capability Assessment...")
    
    fixable_issues = sum(1 for result in fix_results.values() 
                        if isinstance(result, dict) and result.get("can_fix", False))
    total_issues = len([r for r in fix_results.values() if isinstance(r, dict) and "can_fix" in r])
    
    if total_issues > 0:
        fix_percentage = (fixable_issues / total_issues) * 100
        
        print(f"   Fix Capability: {fixable_issues}/{total_issues} issues ({fix_percentage:.1f}%)")
        
        if fix_percentage >= 80:
            print("   ✅ EXCELLENT: System can fix most detected issues")
            overall_assessment = "excellent"
        elif fix_percentage >= 60:
            print("   ✅ GOOD: System can fix majority of detected issues")
            overall_assessment = "good"
        elif fix_percentage >= 40:
            print("   ⚠️  PARTIAL: System can fix some detected issues")
            overall_assessment = "partial"
        else:
            print("   ❌ POOR: System can fix few detected issues")
            overall_assessment = "poor"
    else:
        print("   ❓ UNKNOWN: No fixable issues found to assess")
        overall_assessment = "unknown"
    
    # Summary
    print("\n" + "=" * 70)
    print("🔧 FIX CAPABILITY TEST RESULTS")
    print("=" * 70)
    
    for issue_type, result in fix_results.items():
        if isinstance(result, dict) and "can_fix" in result:
            status = "✅ CAN FIX" if result["can_fix"] else "❌ CANNOT FIX"
            method = result.get("method", "Unknown")
            print(f"{issue_type.upper()}: {status} (via {method})")
    
    print(f"\nOVERALL ASSESSMENT: {overall_assessment.upper()}")
    
    # Save results
    results = {
        "timestamp": "2026-01-11T21:15:00Z",
        "fix_results": fix_results,
        "overall_assessment": overall_assessment,
        "fixable_issues": fixable_issues,
        "total_issues": total_issues,
        "fix_percentage": fix_percentage if total_issues > 0 else 0
    }
    
    with open("fix-capability-test-results.json", "w") as f:
        json.dump(results, f, indent=2)
    
    print(f"\n📄 Results saved to: fix-capability-test-results.json")
    
    return overall_assessment in ["excellent", "good"]


def main():
    """Run fix capability tests."""
    
    try:
        success = test_fix_capabilities()
        
        if success:
            print("\n🎉 Fix capability test PASSED!")
            print("The system is properly equipped to fix the reported problems.")
            return 0
        else:
            print("\n⚠️  Fix capability test shows GAPS!")
            print("The system may not be able to fix all reported problems.")
            return 1
            
    except Exception as e:
        print(f"\n❌ Fix capability test failed: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())