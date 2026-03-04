#!/usr/bin/env python3
"""
AWS Integration Test Runner

This script runs all AWS integration tests in sequence and provides
a comprehensive report of the results.

Test Suites:
- Basic AWS Integration Tests
- S3 Operations Tests
- Database Connectivity Tests
- WebSocket Tests
- ML Training Tests
"""

import os
import sys
import subprocess
import json
from datetime import datetime
from typing import Dict, Any, List

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from multimodal_librarian.logging_config import get_logger


class AWSIntegrationTestRunner:
    """Comprehensive AWS integration test runner."""
    
    def __init__(self):
        self.logger = get_logger("aws_integration_test_runner")
        
        # Test configuration
        self.test_modules = [
            {
                "name": "AWS Basic Integration",
                "module": "test_aws_basic_integration.py",
                "description": "Core infrastructure and API endpoint tests"
            },
            {
                "name": "S3 Operations",
                "module": "test_s3_basic_operations.py",
                "description": "File storage and presigned URL tests"
            },
            {
                "name": "Database Connectivity",
                "module": "test_database_basic_connectivity.py",
                "description": "PostgreSQL and Redis connectivity tests"
            },
            {
                "name": "WebSocket Functionality",
                "module": "test_websocket_basic.py",
                "description": "WebSocket connections through load balancer"
            },
            {
                "name": "ML Training APIs",
                "module": "test_ml_training_basic.py",
                "description": "ML training and chunking framework tests"
            }
        ]
        
        # Results tracking
        self.results = {
            "start_time": None,
            "end_time": None,
            "total_duration": 0,
            "test_results": [],
            "summary": {
                "total_suites": len(self.test_modules),
                "passed_suites": 0,
                "failed_suites": 0,
                "skipped_suites": 0,
                "total_tests": 0,
                "passed_tests": 0,
                "failed_tests": 0,
                "skipped_tests": 0
            }
        }
    
    def run_all_tests(self, stop_on_failure: bool = False, verbose: bool = True) -> Dict[str, Any]:
        """Run all AWS integration test suites."""
        self.logger.info("🚀 Starting AWS Integration Test Suite")
        self.results["start_time"] = datetime.now()
        
        print("=" * 80)
        print("🚀 AWS INTEGRATION TEST SUITE")
        print("=" * 80)
        print(f"📅 Started: {self.results['start_time'].isoformat()}")
        print(f"🧪 Test Suites: {len(self.test_modules)}")
        print()
        
        # Run each test module
        for i, test_module in enumerate(self.test_modules, 1):
            print(f"📋 [{i}/{len(self.test_modules)}] {test_module['name']}")
            print(f"   {test_module['description']}")
            print("-" * 60)
            
            result = self._run_test_module(test_module, verbose)
            self.results["test_results"].append(result)
            
            # Update summary
            if result["status"] == "passed":
                self.results["summary"]["passed_suites"] += 1
            elif result["status"] == "failed":
                self.results["summary"]["failed_suites"] += 1
            else:
                self.results["summary"]["skipped_suites"] += 1
            
            # Update test counts
            self.results["summary"]["total_tests"] += result.get("total_tests", 0)
            self.results["summary"]["passed_tests"] += result.get("passed_tests", 0)
            self.results["summary"]["failed_tests"] += result.get("failed_tests", 0)
            self.results["summary"]["skipped_tests"] += result.get("skipped_tests", 0)
            
            print()
            
            # Stop on failure if requested
            if stop_on_failure and result["status"] == "failed":
                print("❌ Stopping on first failure as requested")
                break
        
        # Calculate final results
        self.results["end_time"] = datetime.now()
        self.results["total_duration"] = (
            self.results["end_time"] - self.results["start_time"]
        ).total_seconds()
        
        # Print final summary
        self._print_final_summary()
        
        return self.results
    
    def _run_test_module(self, test_module: Dict[str, str], verbose: bool = True) -> Dict[str, Any]:
        """Run a single test module."""
        module_path = os.path.join(os.path.dirname(__file__), test_module["module"])
        
        if not os.path.exists(module_path):
            return {
                "name": test_module["name"],
                "module": test_module["module"],
                "status": "skipped",
                "reason": "Module file not found",
                "duration": 0,
                "output": "",
                "error": f"File not found: {module_path}"
            }
        
        # Run pytest on the module
        cmd = [
            sys.executable, "-m", "pytest",
            module_path,
            "-v" if verbose else "-q",
            "--tb=short",
            "--color=yes",
            "--json-report",
            "--json-report-file=/tmp/pytest_report.json"
        ]
        
        start_time = datetime.now()
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300  # 5 minute timeout per module
            )
            
            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()
            
            # Parse test results
            test_counts = self._parse_pytest_output(result.stdout)
            
            # Determine status
            if result.returncode == 0:
                status = "passed"
                print(f"✅ PASSED ({duration:.1f}s)")
            elif result.returncode == 5:  # No tests collected
                status = "skipped"
                print(f"⚠️  SKIPPED - No tests collected ({duration:.1f}s)")
            else:
                status = "failed"
                print(f"❌ FAILED ({duration:.1f}s)")
            
            # Show output if verbose or if failed
            if verbose or status == "failed":
                if result.stdout:
                    print("📄 Output:")
                    print(result.stdout)
                if result.stderr:
                    print("⚠️  Errors:")
                    print(result.stderr)
            
            return {
                "name": test_module["name"],
                "module": test_module["module"],
                "status": status,
                "duration": duration,
                "return_code": result.returncode,
                "output": result.stdout,
                "error": result.stderr,
                **test_counts
            }
            
        except subprocess.TimeoutExpired:
            duration = 300  # Timeout duration
            print(f"⏰ TIMEOUT ({duration}s)")
            
            return {
                "name": test_module["name"],
                "module": test_module["module"],
                "status": "failed",
                "reason": "Timeout",
                "duration": duration,
                "output": "",
                "error": "Test execution timed out after 5 minutes"
            }
            
        except Exception as e:
            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()
            print(f"💥 ERROR ({duration:.1f}s): {e}")
            
            return {
                "name": test_module["name"],
                "module": test_module["module"],
                "status": "failed",
                "reason": "Execution error",
                "duration": duration,
                "output": "",
                "error": str(e)
            }
    
    def _parse_pytest_output(self, output: str) -> Dict[str, int]:
        """Parse pytest output to extract test counts."""
        counts = {
            "total_tests": 0,
            "passed_tests": 0,
            "failed_tests": 0,
            "skipped_tests": 0
        }
        
        try:
            # Look for pytest summary line
            lines = output.split('\n')
            for line in lines:
                if 'passed' in line or 'failed' in line or 'skipped' in line:
                    # Parse lines like "5 passed, 2 skipped in 1.23s"
                    parts = line.split()
                    for i, part in enumerate(parts):
                        if part.isdigit():
                            count = int(part)
                            if i + 1 < len(parts):
                                result_type = parts[i + 1]
                                if 'passed' in result_type:
                                    counts["passed_tests"] = count
                                elif 'failed' in result_type:
                                    counts["failed_tests"] = count
                                elif 'skipped' in result_type:
                                    counts["skipped_tests"] = count
            
            # Calculate total
            counts["total_tests"] = (
                counts["passed_tests"] + 
                counts["failed_tests"] + 
                counts["skipped_tests"]
            )
            
        except Exception as e:
            self.logger.warning(f"Could not parse pytest output: {e}")
        
        return counts
    
    def _print_final_summary(self):
        """Print final test summary."""
        summary = self.results["summary"]
        
        print("=" * 80)
        print("📊 FINAL TEST SUMMARY")
        print("=" * 80)
        print(f"⏱️  Total Duration: {self.results['total_duration']:.1f} seconds")
        print()
        
        print("📋 Test Suites:")
        print(f"   Total: {summary['total_suites']}")
        print(f"   ✅ Passed: {summary['passed_suites']}")
        print(f"   ❌ Failed: {summary['failed_suites']}")
        print(f"   ⚠️  Skipped: {summary['skipped_suites']}")
        print()
        
        print("🧪 Individual Tests:")
        print(f"   Total: {summary['total_tests']}")
        print(f"   ✅ Passed: {summary['passed_tests']}")
        print(f"   ❌ Failed: {summary['failed_tests']}")
        print(f"   ⚠️  Skipped: {summary['skipped_tests']}")
        print()
        
        # Success rate
        if summary['total_suites'] > 0:
            suite_success_rate = (summary['passed_suites'] / summary['total_suites']) * 100
            print(f"📈 Suite Success Rate: {suite_success_rate:.1f}%")
        
        if summary['total_tests'] > 0:
            test_success_rate = (summary['passed_tests'] / summary['total_tests']) * 100
            print(f"📈 Test Success Rate: {test_success_rate:.1f}%")
        
        print()
        
        # Individual suite results
        print("📋 Suite Details:")
        for result in self.results["test_results"]:
            status_icon = "✅" if result["status"] == "passed" else "❌" if result["status"] == "failed" else "⚠️ "
            print(f"   {status_icon} {result['name']}: {result['status'].upper()} ({result['duration']:.1f}s)")
        
        print()
        
        # Overall result
        if summary['failed_suites'] == 0:
            print("🎉 ALL TEST SUITES PASSED!")
        elif summary['passed_suites'] > 0:
            print("⚠️  SOME TEST SUITES FAILED - Check individual results above")
        else:
            print("❌ ALL TEST SUITES FAILED - System may have critical issues")
        
        print("=" * 80)
    
    def save_results(self, output_file: str = "aws_integration_test_results.json"):
        """Save test results to JSON file."""
        try:
            # Convert datetime objects to strings for JSON serialization
            results_copy = self.results.copy()
            if results_copy["start_time"]:
                results_copy["start_time"] = results_copy["start_time"].isoformat()
            if results_copy["end_time"]:
                results_copy["end_time"] = results_copy["end_time"].isoformat()
            
            with open(output_file, 'w') as f:
                json.dump(results_copy, f, indent=2, default=str)
            
            print(f"📄 Results saved to: {output_file}")
            
        except Exception as e:
            self.logger.error(f"Could not save results: {e}")


def main():
    """Main test runner function."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Run AWS Integration Tests')
    parser.add_argument('--stop-on-failure', action='store_true',
                       help='Stop running tests after first failure')
    parser.add_argument('--quiet', action='store_true',
                       help='Reduce output verbosity')
    parser.add_argument('--output-file', type=str,
                       default='aws_integration_test_results.json',
                       help='Output file for test results')
    
    args = parser.parse_args()
    
    # Set environment variables
    os.environ.setdefault("TESTING", "true")
    os.environ.setdefault("LOG_LEVEL", "INFO")
    
    # Run tests
    runner = AWSIntegrationTestRunner()
    results = runner.run_all_tests(
        stop_on_failure=args.stop_on_failure,
        verbose=not args.quiet
    )
    
    # Save results
    runner.save_results(args.output_file)
    
    # Exit with appropriate code
    if results["summary"]["failed_suites"] == 0:
        exit(0)  # Success
    else:
        exit(1)  # Some failures


if __name__ == "__main__":
    main()