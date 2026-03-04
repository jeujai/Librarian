#!/usr/bin/env python3
"""
Security Configuration Testing

Tests security configuration settings and infrastructure security.
"""

import os
import json
import sys
from pathlib import Path
from typing import Dict, List, Any

# Add the project root to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

from src.multimodal_librarian.logging_config import get_logger

logger = get_logger(__name__)


class SecurityConfigurationTester:
    """Test security configuration settings."""
    
    def __init__(self):
        """Initialize security configuration tester."""
        self.test_results = []
        self.project_root = Path(__file__).parent.parent.parent
    
    def log_test_result(self, test_name: str, success: bool, message: str, 
                       details: Dict[str, Any] = None, severity: str = "INFO"):
        """Log security configuration test result."""
        result = {
            "test": test_name,
            "success": success,
            "message": message,
            "severity": severity,
            "details": details or {}
        }
        
        self.test_results.append(result)
        
        status = "✅ PASS" if success else "❌ FAIL"
        severity_icon = {"INFO": "ℹ️", "WARNING": "⚠️", "CRITICAL": "🚨"}.get(severity, "ℹ️")
        
        logger.info(f"{status} {severity_icon} {test_name}: {message}")
    
    def test_environment_variables(self) -> bool:
        """Test security-related environment variables."""
        try:
            required_env_vars = [
                "SECRET_KEY",
                "DATABASE_URL"
            ]
            
            optional_env_vars = [
                "ENCRYPTION_KEY",
                "JWT_SECRET_KEY",
                "ADMIN_PASSWORD"
            ]
            
            all_passed = True
            
            # Check required environment variables
            for var in required_env_vars:
                value = os.getenv(var)
                if not value:
                    self.log_test_result(
                        f"Environment Variable ({var})",
                        False,
                        f"Required environment variable {var} is not set",
                        {"variable": var},
                        "CRITICAL"
                    )
                    all_passed = False
                elif len(value) < 16:
                    self.log_test_result(
                        f"Environment Variable ({var})",
                        False,
                        f"Environment variable {var} is too short (minimum 16 characters)",
                        {"variable": var, "length": len(value)},
                        "WARNING"
                    )
                else:
                    self.log_test_result(
                        f"Environment Variable ({var})",
                        True,
                        f"Environment variable {var} is properly configured",
                        {"variable": var, "length": len(value)}
                    )
            
            # Check optional environment variables
            for var in optional_env_vars:
                value = os.getenv(var)
                if value:
                    self.log_test_result(
                        f"Optional Environment Variable ({var})",
                        True,
                        f"Optional environment variable {var} is configured",
                        {"variable": var, "length": len(value)}
                    )
            
            return all_passed
            
        except Exception as e:
            self.log_test_result(
                "Environment Variables",
                False,
                f"Environment variable test failed: {e}",
                {"error": str(e)},
                "CRITICAL"
            )
            return False
    
    def test_file_permissions(self) -> bool:
        """Test file permissions for security-sensitive files."""
        try:
            sensitive_files = [
                ".env",
                "config/aws-config-basic.py",
                "infrastructure/aws-native/terraform.tfvars"
            ]
            
            all_passed = True
            
            for file_path in sensitive_files:
                full_path = self.project_root / file_path
                
                if not full_path.exists():
                    self.log_test_result(
                        f"File Permissions ({file_path})",
                        True,
                        f"Sensitive file {file_path} does not exist (acceptable)",
                        {"file_path": str(full_path)}
                    )
                    continue
                
                # Check file permissions (Unix-like systems)
                try:
                    import stat
                    file_stat = full_path.stat()
                    file_mode = stat.filemode(file_stat.st_mode)
                    
                    # Check if file is readable by others
                    if file_stat.st_mode & stat.S_IROTH:
                        self.log_test_result(
                            f"File Permissions ({file_path})",
                            False,
                            f"Sensitive file {file_path} is readable by others",
                            {"file_path": str(full_path), "permissions": file_mode},
                            "WARNING"
                        )
                    else:
                        self.log_test_result(
                            f"File Permissions ({file_path})",
                            True,
                            f"Sensitive file {file_path} has appropriate permissions",
                            {"file_path": str(full_path), "permissions": file_mode}
                        )
                        
                except Exception as e:
                    self.log_test_result(
                        f"File Permissions ({file_path})",
                        False,
                        f"Could not check permissions for {file_path}: {e}",
                        {"file_path": str(full_path), "error": str(e)},
                        "WARNING"
                    )
            
            return all_passed
            
        except Exception as e:
            self.log_test_result(
                "File Permissions",
                False,
                f"File permissions test failed: {e}",
                {"error": str(e)},
                "CRITICAL"
            )
            return False
    
    def test_configuration_security(self) -> bool:
        """Test security configuration in application settings."""
        try:
            # Test configuration files
            config_files = [
                "src/multimodal_librarian/config/__init__.py",
                "config/aws-config-basic.py"
            ]
            
            all_passed = True
            security_patterns = [
                "SECRET_KEY",
                "password",
                "token",
                "api_key",
                "encryption"
            ]
            
            for config_file in config_files:
                config_path = self.project_root / config_file
                
                if not config_path.exists():
                    continue
                
                try:
                    with open(config_path, 'r') as f:
                        content = f.read().lower()
                    
                    # Check for hardcoded secrets
                    hardcoded_secrets = []
                    for pattern in security_patterns:
                        if f'{pattern} = "' in content or f"{pattern} = '" in content:
                            # Check if it's actually a hardcoded value
                            lines = content.split('\n')
                            for line in lines:
                                if pattern in line and ('= "' in line or "= '" in line):
                                    if not ('os.getenv' in line or 'environ' in line):
                                        hardcoded_secrets.append(pattern)
                    
                    if hardcoded_secrets:
                        self.log_test_result(
                            f"Configuration Security ({config_file})",
                            False,
                            f"Hardcoded secrets found in {config_file}: {hardcoded_secrets}",
                            {"file": config_file, "secrets": hardcoded_secrets},
                            "CRITICAL"
                        )
                        all_passed = False
                    else:
                        self.log_test_result(
                            f"Configuration Security ({config_file})",
                            True,
                            f"No hardcoded secrets found in {config_file}",
                            {"file": config_file}
                        )
                        
                except Exception as e:
                    self.log_test_result(
                        f"Configuration Security ({config_file})",
                        False,
                        f"Could not analyze {config_file}: {e}",
                        {"file": config_file, "error": str(e)},
                        "WARNING"
                    )
            
            return all_passed
            
        except Exception as e:
            self.log_test_result(
                "Configuration Security",
                False,
                f"Configuration security test failed: {e}",
                {"error": str(e)},
                "CRITICAL"
            )
            return False
    
    def run_all_tests(self) -> Dict[str, Any]:
        """Run all security configuration tests."""
        logger.info("=== Security Configuration Test Suite ===")
        
        tests = [
            ("Environment Variables", self.test_environment_variables),
            ("File Permissions", self.test_file_permissions),
            ("Configuration Security", self.test_configuration_security)
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
        
        success_rate = (passed_tests / total_tests) * 100
        
        results = {
            "summary": {
                "total_tests": total_tests,
                "passed_tests": passed_tests,
                "success_rate": success_rate
            },
            "test_results": self.test_results
        }
        
        return results


if __name__ == "__main__":
    tester = SecurityConfigurationTester()
    results = tester.run_all_tests()
    
    print(f"\nConfiguration Security Tests: {results['summary']['passed_tests']}/{results['summary']['total_tests']}")
    print(f"Success Rate: {results['summary']['success_rate']:.1f}%")