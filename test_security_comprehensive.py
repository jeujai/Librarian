#!/usr/bin/env python3
"""
Security Testing Script for System Integration and Stability

This script runs comprehensive security tests covering:
- Authentication mechanisms
- Data encryption validation  
- Access control verification

Validates Requirement 5.5: Security validation for production readiness
"""

import asyncio
import json
import sys
import os
import time
from datetime import datetime

# Add the project root to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '.'))

from tests.security.test_security_comprehensive import SecurityTestSuite
from src.multimodal_librarian.logging_config import configure_logging, get_logger

# Configure logging
configure_logging()
logger = get_logger(__name__)


def print_security_banner():
    """Print security test banner."""
    print("=" * 80)
    print("🔒 COMPREHENSIVE SECURITY TESTING SUITE")
    print("=" * 80)
    print("Testing Components:")
    print("  🔐 Authentication Mechanisms")
    print("  🔒 Data Encryption (at rest and in transit)")
    print("  🛡️  Access Control Systems")
    print("  🚨 Security Vulnerability Detection")
    print("=" * 80)


def print_security_summary(results):
    """Print security test summary."""
    summary = results["summary"]
    
    print("\n" + "=" * 80)
    print("🔒 SECURITY TEST RESULTS SUMMARY")
    print("=" * 80)
    
    # Overall status with appropriate emoji
    status_icons = {
        "SECURE": "✅",
        "MINOR_ISSUES": "⚠️",
        "SECURITY_CONCERNS": "🚨",
        "CRITICAL_VULNERABILITIES": "🚨"
    }
    
    status = summary["security_status"]
    icon = status_icons.get(status, "❓")
    
    print(f"Security Status: {icon} {status}")
    print(f"Overall Success Rate: {summary['overall_success_rate']:.1f}%")
    print(f"Tests Passed: {summary['passed_tests']}/{summary['total_tests']}")
    
    if summary['critical_failures'] > 0:
        print(f"🚨 Critical Failures: {summary['critical_failures']}")
    
    if summary['warnings'] > 0:
        print(f"⚠️  Warnings: {summary['warnings']}")
    
    print(f"⏱️  Duration: {summary['duration_seconds']:.2f} seconds")
    
    # Category breakdown
    print(f"\n📊 CATEGORY BREAKDOWN:")
    print("-" * 40)
    
    for category, results_data in results["category_results"].items():
        success_rate = results_data["success_rate"]
        passed = results_data["passed"]
        total = results_data["total"]
        
        if success_rate == 100:
            icon = "✅"
        elif success_rate >= 80:
            icon = "⚠️"
        else:
            icon = "❌"
        
        print(f"{icon} {category}: {passed}/{total} ({success_rate:.1f}%)")
    
    # Security recommendations
    if results["security_recommendations"]:
        print(f"\n🔍 SECURITY RECOMMENDATIONS:")
        print("-" * 40)
        for i, recommendation in enumerate(results["security_recommendations"], 1):
            print(f"{i}. {recommendation}")
    
    print("=" * 80)


def main():
    """Main security testing function."""
    print_security_banner()
    
    # Check if server URL is specified
    base_url = "http://localhost:8000"
    if len(sys.argv) > 1:
        base_url = sys.argv[1]
    
    print(f"🌐 Target System: {base_url}")
    print(f"🕐 Test Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    try:
        # Initialize security test suite
        logger.info("Initializing comprehensive security test suite...")
        security_tester = SecurityTestSuite(base_url)
        
        # Run all security tests
        logger.info("Running comprehensive security tests...")
        results = security_tester.run_all_security_tests()
        
        # Print summary
        print_security_summary(results)
        
        # Save detailed results
        timestamp = int(time.time())
        results_file = f"security-test-results-{timestamp}.json"
        
        with open(results_file, 'w') as f:
            json.dump(results, f, indent=2)
        
        print(f"\n📄 Detailed results saved to: {results_file}")
        
        # Determine exit status
        security_status = results["summary"]["security_status"]
        critical_failures = results["summary"]["critical_failures"]
        success_rate = results["summary"]["overall_success_rate"]
        
        if security_status == "SECURE" and critical_failures == 0:
            print("\n✅ SECURITY VALIDATION PASSED")
            print("   System meets security requirements for production deployment")
            return 0
        elif security_status == "MINOR_ISSUES" and critical_failures == 0:
            print("\n⚠️  SECURITY VALIDATION PASSED WITH WARNINGS")
            print("   System is acceptable for production but has minor security issues")
            return 0
        elif critical_failures > 0:
            print(f"\n🚨 SECURITY VALIDATION FAILED")
            print(f"   {critical_failures} critical security vulnerabilities found")
            print("   DO NOT DEPLOY TO PRODUCTION until issues are resolved")
            return 1
        else:
            print(f"\n❌ SECURITY VALIDATION FAILED")
            print(f"   Success rate: {success_rate:.1f}% (minimum 80% required)")
            print("   Review failed tests and implement security fixes")
            return 1
            
    except KeyboardInterrupt:
        print("\n\n⚠️  Security testing interrupted by user")
        return 130
    except Exception as e:
        logger.error(f"Security testing failed with error: {e}")
        print(f"\n❌ SECURITY TESTING ERROR: {e}")
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)