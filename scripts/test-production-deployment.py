#!/usr/bin/env python3
"""
Production Deployment Test Runner

This script runs the production deployment test suite to validate
deployment procedures, startup sequences, and configuration management.

Usage:
    python scripts/test-production-deployment.py [--verbose] [--save-results]
"""

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

# Add the project root to the Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from tests.deployment.test_production_deployment import ProductionDeploymentTester


def main():
    """Main function to run production deployment tests."""
    
    parser = argparse.ArgumentParser(description='Run production deployment tests')
    parser.add_argument('--verbose', '-v', action='store_true', 
                       help='Enable verbose output')
    parser.add_argument('--save-results', '-s', action='store_true',
                       help='Save detailed results to JSON file')
    parser.add_argument('--timeout', '-t', type=int, default=300,
                       help='Timeout in seconds for deployment tests (default: 300)')
    
    args = parser.parse_args()
    
    print("🚀 Production Deployment Test Runner")
    print("=" * 60)
    print("Testing deployment procedures, startup sequences, and configuration management")
    print()
    
    # Configure deployment tester
    config = {
        "environment": "production",
        "timeout_seconds": args.timeout,
        "health_check_retries": 10,
        "health_check_interval": 30,
        "required_services": [
            "main_application",
            "database",
            "vector_store", 
            "cache_service",
            "monitoring"
        ],
        "configuration_files": [
            "docker-compose.prod.yml",
            "nginx.conf",
            ".env",
            "infrastructure/aws-native/main.tf"
        ],
        "deployment_steps": [
            "pre_deployment_validation",
            "configuration_validation", 
            "infrastructure_preparation",
            "application_deployment",
            "service_startup",
            "health_verification",
            "post_deployment_validation"
        ]
    }
    
    # Run comprehensive deployment tests
    tester = ProductionDeploymentTester(config)
    
    try:
        test_results = asyncio.run(tester.run_comprehensive_deployment_test())
        
        # Generate and display comprehensive report
        report = tester.generate_deployment_report()
        print("\n" + report)
        
        # Save results if requested
        if args.save_results:
            results_file = f"production-deployment-test-results-{int(time.time())}.json"
            with open(results_file, 'w') as f:
                json.dump(test_results, f, indent=2, default=str)
            print(f"\n📄 Detailed results saved to: {results_file}")
        
        # Determine exit code based on deployment readiness
        deployment_ready = test_results.get('deployment_ready', {}).get('ready_for_deployment', False)
        overall_success = test_results.get('overall_success', False)
        
        if deployment_ready and overall_success:
            print("\n🎉 System is ready for production deployment!")
            return 0
        elif overall_success:
            print("\n⚠️  System has minor issues but may be deployable - check report")
            return 0
        else:
            print("\n❌ System is not ready for production deployment - address critical issues")
            return 1
            
    except KeyboardInterrupt:
        print("\n⚠️  Test interrupted by user")
        return 130
    except Exception as e:
        print(f"\n❌ Test execution failed: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)