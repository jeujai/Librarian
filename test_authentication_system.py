#!/usr/bin/env python3
"""
Test script for the authentication system implementation.

This script tests user registration, login, token validation, and API access
to ensure the authentication system is working correctly.
"""

import asyncio
import json
import sys
import os
from datetime import datetime
import requests
import time

# Add the project root to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '.'))

from src.multimodal_librarian.logging_config import get_logger

logger = get_logger(__name__)


class AuthenticationTester:
    """Test suite for authentication system."""
    
    def __init__(self, base_url: str = "http://localhost:8000"):
        """Initialize authentication tester."""
        self.base_url = base_url
        self.session = requests.Session()
        self.test_results = []
        
        # Test user credentials
        self.test_users = [
            {
                "username": "testuser1",
                "email": "testuser1@example.com",
                "password": "testpass123",
                "role": "user"
            },
            {
                "username": "testadmin",
                "email": "testadmin@example.com", 
                "password": "adminpass123",
                "role": "admin"
            }
        ]
        
        self.tokens = {}
    
    def log_test_result(self, test_name: str, success: bool, message: str, details: dict = None):
        """Log test result."""
        result = {
            "test": test_name,
            "success": success,
            "message": message,
            "timestamp": datetime.utcnow().isoformat(),
            "details": details or {}
        }
        
        self.test_results.append(result)
        
        status = "✅ PASS" if success else "❌ FAIL"
        logger.info(f"{status} {test_name}: {message}")
        
        if details:
            logger.debug(f"Details: {json.dumps(details, indent=2)}")
    
    def test_server_health(self) -> bool:
        """Test if server is running and healthy."""
        try:
            response = self.session.get(f"{self.base_url}/health", timeout=10)
            
            if response.status_code == 200:
                health_data = response.json()
                self.log_test_result(
                    "Server Health Check",
                    True,
                    f"Server is healthy (status: {health_data.get('overall_status', 'unknown')})",
                    {"health_data": health_data}
                )
                return True
            else:
                self.log_test_result(
                    "Server Health Check",
                    False,
                    f"Server returned status {response.status_code}",
                    {"status_code": response.status_code, "response": response.text}
                )
                return False
                
        except Exception as e:
            self.log_test_result(
                "Server Health Check",
                False,
                f"Failed to connect to server: {e}",
                {"error": str(e)}
            )
            return False
    
    def test_features_endpoint(self) -> bool:
        """Test features endpoint to check authentication availability."""
        try:
            response = self.session.get(f"{self.base_url}/features", timeout=10)
            
            if response.status_code == 200:
                features = response.json()
                auth_enabled = features.get("features", {}).get("auth", False)
                
                self.log_test_result(
                    "Features Check",
                    True,
                    f"Features endpoint accessible (auth enabled: {auth_enabled})",
                    {"features": features.get("features", {})}
                )
                return auth_enabled
            else:
                self.log_test_result(
                    "Features Check",
                    False,
                    f"Features endpoint returned status {response.status_code}",
                    {"status_code": response.status_code}
                )
                return False
                
        except Exception as e:
            self.log_test_result(
                "Features Check",
                False,
                f"Failed to check features: {e}",
                {"error": str(e)}
            )
            return False
    
    def test_user_registration(self) -> bool:
        """Test user registration functionality."""
        success_count = 0
        
        for user in self.test_users:
            try:
                response = self.session.post(
                    f"{self.base_url}/auth/register",
                    json=user,
                    timeout=10
                )
                
                if response.status_code == 200:
                    registration_data = response.json()
                    self.log_test_result(
                        f"User Registration ({user['username']})",
                        True,
                        f"User {user['username']} registered successfully",
                        {"user_id": registration_data.get("user_id")}
                    )
                    success_count += 1
                    
                elif response.status_code == 400:
                    # User might already exist
                    error_data = response.json()
                    if "already exists" in error_data.get("detail", ""):
                        self.log_test_result(
                            f"User Registration ({user['username']})",
                            True,
                            f"User {user['username']} already exists (expected)",
                            {"message": "User already registered"}
                        )
                        success_count += 1
                    else:
                        self.log_test_result(
                            f"User Registration ({user['username']})",
                            False,
                            f"Registration failed: {error_data.get('detail')}",
                            {"error_data": error_data}
                        )
                else:
                    self.log_test_result(
                        f"User Registration ({user['username']})",
                        False,
                        f"Registration returned status {response.status_code}",
                        {"status_code": response.status_code, "response": response.text}
                    )
                    
            except Exception as e:
                self.log_test_result(
                    f"User Registration ({user['username']})",
                    False,
                    f"Registration failed with error: {e}",
                    {"error": str(e)}
                )
        
        return success_count == len(self.test_users)
    
    def test_user_login(self) -> bool:
        """Test user login functionality."""
        success_count = 0
        
        # First try default admin user
        admin_login = {
            "username": "admin",
            "password": "admin123"
        }
        
        try:
            response = self.session.post(
                f"{self.base_url}/auth/login",
                json=admin_login,
                timeout=10
            )
            
            if response.status_code == 200:
                login_data = response.json()
                self.tokens["admin"] = login_data["access_token"]
                
                self.log_test_result(
                    "Admin Login",
                    True,
                    "Default admin login successful",
                    {
                        "user_id": login_data.get("user_id"),
                        "role": login_data.get("role"),
                        "permissions": login_data.get("permissions", [])
                    }
                )
                success_count += 1
            else:
                self.log_test_result(
                    "Admin Login",
                    False,
                    f"Admin login failed with status {response.status_code}",
                    {"status_code": response.status_code, "response": response.text}
                )
                
        except Exception as e:
            self.log_test_result(
                "Admin Login",
                False,
                f"Admin login failed with error: {e}",
                {"error": str(e)}
            )
        
        # Test registered users
        for user in self.test_users:
            try:
                login_data = {
                    "username": user["username"],
                    "password": user["password"]
                }
                
                response = self.session.post(
                    f"{self.base_url}/auth/login",
                    json=login_data,
                    timeout=10
                )
                
                if response.status_code == 200:
                    response_data = response.json()
                    self.tokens[user["username"]] = response_data["access_token"]
                    
                    self.log_test_result(
                        f"User Login ({user['username']})",
                        True,
                        f"Login successful for {user['username']}",
                        {
                            "user_id": response_data.get("user_id"),
                            "role": response_data.get("role"),
                            "expires_in": response_data.get("expires_in")
                        }
                    )
                    success_count += 1
                else:
                    self.log_test_result(
                        f"User Login ({user['username']})",
                        False,
                        f"Login failed with status {response.status_code}",
                        {"status_code": response.status_code, "response": response.text}
                    )
                    
            except Exception as e:
                self.log_test_result(
                    f"User Login ({user['username']})",
                    False,
                    f"Login failed with error: {e}",
                    {"error": str(e)}
                )
        
        return success_count > 0
    
    def test_token_validation(self) -> bool:
        """Test JWT token validation."""
        success_count = 0
        
        for username, token in self.tokens.items():
            try:
                headers = {"Authorization": f"Bearer {token}"}
                response = self.session.post(
                    f"{self.base_url}/auth/validate",
                    headers=headers,
                    timeout=10
                )
                
                if response.status_code == 200:
                    validation_data = response.json()
                    
                    if validation_data.get("valid"):
                        self.log_test_result(
                            f"Token Validation ({username})",
                            True,
                            f"Token valid for {username}",
                            {
                                "user_id": validation_data.get("user_id"),
                                "role": validation_data.get("role"),
                                "expires_at": validation_data.get("expires_at")
                            }
                        )
                        success_count += 1
                    else:
                        self.log_test_result(
                            f"Token Validation ({username})",
                            False,
                            f"Token invalid for {username}",
                            {"validation_data": validation_data}
                        )
                else:
                    self.log_test_result(
                        f"Token Validation ({username})",
                        False,
                        f"Validation failed with status {response.status_code}",
                        {"status_code": response.status_code}
                    )
                    
            except Exception as e:
                self.log_test_result(
                    f"Token Validation ({username})",
                    False,
                    f"Validation failed with error: {e}",
                    {"error": str(e)}
                )
        
        return success_count > 0
    
    def test_protected_endpoints(self) -> bool:
        """Test access to protected endpoints."""
        success_count = 0
        
        # Test accessing user info endpoint
        for username, token in self.tokens.items():
            try:
                headers = {"Authorization": f"Bearer {token}"}
                response = self.session.get(
                    f"{self.base_url}/auth/me",
                    headers=headers,
                    timeout=10
                )
                
                if response.status_code == 200:
                    user_data = response.json()
                    self.log_test_result(
                        f"Protected Endpoint Access ({username})",
                        True,
                        f"Successfully accessed /auth/me for {username}",
                        {
                            "user_id": user_data.get("user_id"),
                            "role": user_data.get("role")
                        }
                    )
                    success_count += 1
                else:
                    self.log_test_result(
                        f"Protected Endpoint Access ({username})",
                        False,
                        f"Failed to access protected endpoint: {response.status_code}",
                        {"status_code": response.status_code}
                    )
                    
            except Exception as e:
                self.log_test_result(
                    f"Protected Endpoint Access ({username})",
                    False,
                    f"Protected endpoint access failed: {e}",
                    {"error": str(e)}
                )
        
        return success_count > 0
    
    def test_unauthorized_access(self) -> bool:
        """Test that endpoints properly reject unauthorized access."""
        try:
            # Try to access protected endpoint without token
            response = self.session.get(f"{self.base_url}/auth/me", timeout=10)
            
            if response.status_code == 401:
                self.log_test_result(
                    "Unauthorized Access Test",
                    True,
                    "Protected endpoint properly rejected unauthorized access",
                    {"status_code": response.status_code}
                )
                return True
            else:
                self.log_test_result(
                    "Unauthorized Access Test",
                    False,
                    f"Protected endpoint should return 401, got {response.status_code}",
                    {"status_code": response.status_code}
                )
                return False
                
        except Exception as e:
            self.log_test_result(
                "Unauthorized Access Test",
                False,
                f"Unauthorized access test failed: {e}",
                {"error": str(e)}
            )
            return False
    
    def run_all_tests(self) -> dict:
        """Run all authentication tests."""
        logger.info("=== Authentication System Test Suite ===")
        start_time = time.time()
        
        # Test sequence
        tests = [
            ("Server Health", self.test_server_health),
            ("Features Check", self.test_features_endpoint),
            ("User Registration", self.test_user_registration),
            ("User Login", self.test_user_login),
            ("Token Validation", self.test_token_validation),
            ("Protected Endpoints", self.test_protected_endpoints),
            ("Unauthorized Access", self.test_unauthorized_access)
        ]
        
        passed_tests = 0
        total_tests = len(tests)
        
        for test_name, test_func in tests:
            logger.info(f"\n--- Running {test_name} ---")
            try:
                success = test_func()
                if success:
                    passed_tests += 1
            except Exception as e:
                logger.error(f"Test {test_name} failed with exception: {e}")
                self.log_test_result(
                    test_name,
                    False,
                    f"Test failed with exception: {e}",
                    {"error": str(e)}
                )
        
        # Calculate results
        end_time = time.time()
        duration = end_time - start_time
        success_rate = (passed_tests / total_tests) * 100
        
        # Summary
        logger.info(f"\n=== Test Results Summary ===")
        logger.info(f"Tests Passed: {passed_tests}/{total_tests}")
        logger.info(f"Success Rate: {success_rate:.1f}%")
        logger.info(f"Duration: {duration:.2f} seconds")
        
        # Detailed results
        results = {
            "summary": {
                "total_tests": total_tests,
                "passed_tests": passed_tests,
                "failed_tests": total_tests - passed_tests,
                "success_rate": success_rate,
                "duration_seconds": duration,
                "timestamp": datetime.utcnow().isoformat()
            },
            "test_results": self.test_results,
            "tokens_obtained": list(self.tokens.keys()),
            "recommendations": []
        }
        
        # Add recommendations
        if success_rate < 100:
            results["recommendations"].append("Some tests failed - check logs for details")
        
        if not self.tokens:
            results["recommendations"].append("No authentication tokens obtained - check login functionality")
        
        if success_rate >= 80:
            results["recommendations"].append("Authentication system is mostly functional")
        
        return results


async def main():
    """Main test function."""
    # Check if server is specified
    base_url = "http://localhost:8000"
    if len(sys.argv) > 1:
        base_url = sys.argv[1]
    
    logger.info(f"Testing authentication system at: {base_url}")
    
    # Run tests
    tester = AuthenticationTester(base_url)
    results = tester.run_all_tests()
    
    # Save results
    results_file = f"authentication-test-results-{int(time.time())}.json"
    with open(results_file, 'w') as f:
        json.dump(results, f, indent=2)
    
    logger.info(f"Test results saved to: {results_file}")
    
    # Exit with appropriate code
    success_rate = results["summary"]["success_rate"]
    if success_rate >= 80:
        logger.info("✅ Authentication system tests PASSED")
        return True
    else:
        logger.error("❌ Authentication system tests FAILED")
        return False


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)