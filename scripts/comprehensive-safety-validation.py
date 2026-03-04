#!/usr/bin/env python3
"""
Comprehensive Safety Validation Script for Configuration Cleanup

This script validates that the system is working correctly before, during, 
and after configuration cleanup operations.
"""

import requests
import json
import time
import sys
from typing import Dict, List, Tuple, Any
from datetime import datetime

class SafetyValidator:
    def __init__(self, base_url: str = "http://multimodal-librarian-full-ml-249704554.us-east-1.elb.amazonaws.com"):
        self.base_url = base_url
        self.test_results = []
        self.baseline_results = None
        
    def log_test(self, test_name: str, status: str, details: Any = None):
        """Log test result with timestamp."""
        result = {
            "timestamp": datetime.now().isoformat(),
            "test_name": test_name,
            "status": status,
            "details": details
        }
        self.test_results.append(result)
        print(f"[{status}] {test_name}: {details}")
        
    def test_health_endpoint(self) -> bool:
        """Test the main health endpoint."""
        try:
            response = requests.get(f"{self.base_url}/health", timeout=10)
            if response.status_code == 200:
                data = response.json()
                if data.get("overall_status") == "healthy":
                    self.log_test("Health Endpoint", "PASS", "System reports healthy")
                    return True
                else:
                    self.log_test("Health Endpoint", "FAIL", f"Status: {data.get('overall_status')}")
                    return False
            else:
                self.log_test("Health Endpoint", "FAIL", f"HTTP {response.status_code}")
                return False
        except Exception as e:
            self.log_test("Health Endpoint", "FAIL", str(e))
            return False
    
    def test_database_connectivity(self) -> bool:
        """Test database connectivity."""
        try:
            response = requests.get(f"{self.base_url}/test/database", timeout=15)
            if response.status_code == 200:
                data = response.json()
                if data.get("status") == "success" and data.get("connection_test") == "passed":
                    self.log_test("Database Connectivity", "PASS", f"Connected to {data.get('host')}")
                    return True
                else:
                    self.log_test("Database Connectivity", "FAIL", data.get("error", "Unknown error"))
                    return False
            else:
                self.log_test("Database Connectivity", "FAIL", f"HTTP {response.status_code}")
                return False
        except Exception as e:
            self.log_test("Database Connectivity", "FAIL", str(e))
            return False
    
    def test_redis_connectivity(self) -> bool:
        """Test Redis connectivity."""
        try:
            response = requests.get(f"{self.base_url}/test/redis", timeout=15)
            if response.status_code == 200:
                data = response.json()
                if data.get("status") == "success":
                    self.log_test("Redis Connectivity", "PASS", f"Connected to {data.get('host')}")
                    return True
                else:
                    self.log_test("Redis Connectivity", "FAIL", data.get("error", "Unknown error"))
                    return False
            else:
                self.log_test("Redis Connectivity", "FAIL", f"HTTP {response.status_code}")
                return False
        except Exception as e:
            self.log_test("Redis Connectivity", "FAIL", str(e))
            return False
    
    def test_api_documentation(self) -> bool:
        """Test API documentation endpoint."""
        try:
            response = requests.get(f"{self.base_url}/docs", timeout=10)
            if response.status_code == 200:
                self.log_test("API Documentation", "PASS", "Docs accessible")
                return True
            else:
                self.log_test("API Documentation", "FAIL", f"HTTP {response.status_code}")
                return False
        except Exception as e:
            self.log_test("API Documentation", "FAIL", str(e))
            return False
    
    def test_chat_interface(self) -> bool:
        """Test chat interface endpoint."""
        try:
            response = requests.get(f"{self.base_url}/chat", timeout=10)
            if response.status_code == 200:
                self.log_test("Chat Interface", "PASS", "Chat interface accessible")
                return True
            else:
                self.log_test("Chat Interface", "FAIL", f"HTTP {response.status_code}")
                return False
        except Exception as e:
            self.log_test("Chat Interface", "FAIL", str(e))
            return False
    
    def test_features_endpoint(self) -> bool:
        """Test features endpoint and validate expected features."""
        try:
            response = requests.get(f"{self.base_url}/features", timeout=10)
            if response.status_code == 200:
                data = response.json()
                features = data.get("features", {})
                
                # Check expected features
                expected_features = {
                    "chat": True,
                    "functional_chat": True,
                    "conversation_context": True,
                    "monitoring": True
                }
                
                all_good = True
                for feature, expected_value in expected_features.items():
                    if features.get(feature) != expected_value:
                        self.log_test("Features Endpoint", "FAIL", 
                                    f"Feature {feature} expected {expected_value}, got {features.get(feature)}")
                        all_good = False
                
                if all_good:
                    self.log_test("Features Endpoint", "PASS", f"All expected features present")
                    return True
                else:
                    return False
            else:
                self.log_test("Features Endpoint", "FAIL", f"HTTP {response.status_code}")
                return False
        except Exception as e:
            self.log_test("Features Endpoint", "FAIL", str(e))
            return False
    
    def test_response_times(self) -> bool:
        """Test response times for key endpoints."""
        endpoints = ["/health", "/features", "/docs"]
        all_good = True
        
        for endpoint in endpoints:
            try:
                start_time = time.time()
                response = requests.get(f"{self.base_url}{endpoint}", timeout=10)
                end_time = time.time()
                
                response_time = (end_time - start_time) * 1000  # Convert to milliseconds
                
                if response.status_code == 200 and response_time < 2000:  # Less than 2 seconds
                    self.log_test(f"Response Time {endpoint}", "PASS", f"{response_time:.2f}ms")
                else:
                    self.log_test(f"Response Time {endpoint}", "FAIL", 
                                f"{response_time:.2f}ms (HTTP {response.status_code})")
                    all_good = False
            except Exception as e:
                self.log_test(f"Response Time {endpoint}", "FAIL", str(e))
                all_good = False
        
        return all_good
    
    def run_comprehensive_validation(self) -> Tuple[bool, Dict]:
        """Run all validation tests."""
        print(f"\n🔍 Starting Comprehensive Safety Validation at {datetime.now()}")
        print(f"Target: {self.base_url}")
        print("=" * 60)
        
        tests = [
            ("Health Check", self.test_health_endpoint),
            ("Database Connectivity", self.test_database_connectivity),
            ("Redis Connectivity", self.test_redis_connectivity),
            ("API Documentation", self.test_api_documentation),
            ("Chat Interface", self.test_chat_interface),
            ("Features Validation", self.test_features_endpoint),
            ("Response Times", self.test_response_times),
        ]
        
        passed = 0
        total = len(tests)
        
        for test_name, test_func in tests:
            if test_func():
                passed += 1
        
        success_rate = (passed / total) * 100
        
        print("\n" + "=" * 60)
        print(f"📊 VALIDATION SUMMARY")
        print(f"Tests Passed: {passed}/{total} ({success_rate:.1f}%)")
        
        if passed == total:
            print("✅ ALL TESTS PASSED - System is healthy and ready")
            status = "PASS"
        else:
            print("❌ SOME TESTS FAILED - System may have issues")
            status = "FAIL"
        
        # Create summary report
        summary = {
            "timestamp": datetime.now().isoformat(),
            "total_tests": total,
            "passed_tests": passed,
            "success_rate": success_rate,
            "overall_status": status,
            "detailed_results": self.test_results
        }
        
        return status == "PASS", summary
    
    def save_baseline(self, filename: str = "baseline-validation-results.json"):
        """Save current results as baseline for comparison."""
        success, summary = self.run_comprehensive_validation()
        
        with open(filename, 'w') as f:
            json.dump(summary, f, indent=2)
        
        print(f"\n💾 Baseline saved to {filename}")
        return success
    
    def compare_to_baseline(self, baseline_file: str = "baseline-validation-results.json") -> bool:
        """Compare current results to baseline."""
        try:
            with open(baseline_file, 'r') as f:
                baseline = json.load(f)
        except FileNotFoundError:
            print(f"❌ Baseline file {baseline_file} not found")
            return False
        
        success, current = self.run_comprehensive_validation()
        
        print(f"\n🔄 COMPARISON TO BASELINE")
        print(f"Baseline Success Rate: {baseline['success_rate']:.1f}%")
        print(f"Current Success Rate:  {current['success_rate']:.1f}%")
        
        if current['success_rate'] >= baseline['success_rate']:
            print("✅ Current results meet or exceed baseline")
            return True
        else:
            print("❌ Current results are worse than baseline")
            return False

def main():
    """Main function to run validation."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Comprehensive Safety Validation")
    parser.add_argument("--baseline", action="store_true", help="Save current results as baseline")
    parser.add_argument("--compare", action="store_true", help="Compare to baseline")
    parser.add_argument("--url", default="http://multimodal-librarian-full-ml-249704554.us-east-1.elb.amazonaws.com", 
                       help="Base URL to test")
    
    args = parser.parse_args()
    
    validator = SafetyValidator(args.url)
    
    if args.baseline:
        success = validator.save_baseline()
        sys.exit(0 if success else 1)
    elif args.compare:
        success = validator.compare_to_baseline()
        sys.exit(0 if success else 1)
    else:
        success, summary = validator.run_comprehensive_validation()
        
        # Save results
        with open(f"validation-results-{int(time.time())}.json", 'w') as f:
            json.dump(summary, f, indent=2)
        
        sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()