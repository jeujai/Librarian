#!/usr/bin/env python3
"""
Basic Security Validation Utilities for AWS Learning Deployment

This module provides utility functions for basic security validation
in the Multimodal Librarian AWS learning deployment. It includes
common security checks, validation helpers, and security testing utilities.
"""

import os
import re
import ssl
import socket
import hashlib
import secrets
from typing import Dict, List, Optional, Tuple, Any
from urllib.parse import urlparse
import subprocess
import json
from datetime import datetime, timedelta

from multimodal_librarian.logging_config import get_logger


class SecurityValidationError(Exception):
    """Custom exception for security validation errors."""
    pass


class BasicSecurityValidator:
    """Basic security validation utilities for learning deployment."""
    
    def __init__(self):
        self.logger = get_logger("basic_security_validator")
    
    def validate_url_security(self, url: str) -> Dict[str, Any]:
        """Validate URL security characteristics."""
        self.logger.info(f"Validating URL security for: {url}")
        
        validation_result = {
            "url": url,
            "is_https": False,
            "has_valid_certificate": False,
            "certificate_info": {},
            "security_headers": {},
            "issues": [],
            "recommendations": []
        }
        
        try:
            parsed_url = urlparse(url)
            
            # Check HTTPS
            if parsed_url.scheme == 'https':
                validation_result["is_https"] = True
                
                # Validate SSL certificate
                hostname = parsed_url.hostname
                port = parsed_url.port or 443
                
                try:
                    context = ssl.create_default_context()
                    with socket.create_connection((hostname, port), timeout=10) as sock:
                        with context.wrap_socket(sock, server_hostname=hostname) as ssock:
                            cert = ssock.getpeercert()
                            validation_result["has_valid_certificate"] = True
                            validation_result["certificate_info"] = {
                                "subject": dict(x[0] for x in cert.get('subject', [])),
                                "issuer": dict(x[0] for x in cert.get('issuer', [])),
                                "version": cert.get('version'),
                                "serial_number": cert.get('serialNumber'),
                                "not_before": cert.get('notBefore'),
                                "not_after": cert.get('notAfter')
                            }
                            
                            # Check certificate expiry
                            not_after = datetime.strptime(cert['notAfter'], '%b %d %H:%M:%S %Y %Z')
                            days_until_expiry = (not_after - datetime.now()).days
                            
                            if days_until_expiry < 30:
                                validation_result["issues"].append(f"Certificate expires in {days_until_expiry} days")
                                validation_result["recommendations"].append("Renew SSL certificate")
                
                except Exception as e:
                    validation_result["issues"].append(f"SSL certificate validation failed: {str(e)}")
                    validation_result["recommendations"].append("Check SSL certificate configuration")
            else:
                validation_result["issues"].append("URL does not use HTTPS")
                validation_result["recommendations"].append("Enable HTTPS encryption")
        
        except Exception as e:
            validation_result["issues"].append(f"URL validation failed: {str(e)}")
            validation_result["recommendations"].append("Review URL configuration")
        
        return validation_result
    
    def validate_password_strength(self, password: str) -> Dict[str, Any]:
        """Validate password strength according to basic security standards."""
        validation_result = {
            "password_length": len(password),
            "has_uppercase": bool(re.search(r'[A-Z]', password)),
            "has_lowercase": bool(re.search(r'[a-z]', password)),
            "has_digits": bool(re.search(r'\d', password)),
            "has_special_chars": bool(re.search(r'[!@#$%^&*(),.?":{}|<>]', password)),
            "is_strong": False,
            "strength_score": 0,
            "issues": [],
            "recommendations": []
        }
        
        # Calculate strength score
        score = 0
        
        # Length scoring
        if validation_result["password_length"] >= 12:
            score += 25
        elif validation_result["password_length"] >= 8:
            score += 15
        else:
            validation_result["issues"].append("Password is too short")
            validation_result["recommendations"].append("Use at least 8 characters (12+ recommended)")
        
        # Character variety scoring
        if validation_result["has_uppercase"]:
            score += 20
        else:
            validation_result["issues"].append("Password lacks uppercase letters")
            validation_result["recommendations"].append("Include uppercase letters")
        
        if validation_result["has_lowercase"]:
            score += 20
        else:
            validation_result["issues"].append("Password lacks lowercase letters")
            validation_result["recommendations"].append("Include lowercase letters")
        
        if validation_result["has_digits"]:
            score += 20
        else:
            validation_result["issues"].append("Password lacks numbers")
            validation_result["recommendations"].append("Include numbers")
        
        if validation_result["has_special_chars"]:
            score += 15
        else:
            validation_result["issues"].append("Password lacks special characters")
            validation_result["recommendations"].append("Include special characters (!@#$%^&*)")
        
        validation_result["strength_score"] = score
        validation_result["is_strong"] = score >= 80
        
        return validation_result
    
    def validate_input_sanitization(self, input_value: str, input_type: str = "general") -> Dict[str, Any]:
        """Validate input for common security issues."""
        validation_result = {
            "input_value": input_value[:100] + "..." if len(input_value) > 100 else input_value,
            "input_type": input_type,
            "length": len(input_value),
            "potential_issues": [],
            "risk_level": "low",
            "is_safe": True,
            "sanitized_value": input_value,
            "recommendations": []
        }
        
        # SQL Injection patterns
        sql_patterns = [
            r"(\b(SELECT|INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|EXEC|UNION)\b)",
            r"(--|#|/\*|\*/)",
            r"(\b(OR|AND)\s+\d+\s*=\s*\d+)",
            r"('|\"|`)",
            r"(\bxp_cmdshell\b|\bsp_executesql\b)"
        ]
        
        for pattern in sql_patterns:
            if re.search(pattern, input_value, re.IGNORECASE):
                validation_result["potential_issues"].append("Potential SQL injection pattern detected")
                validation_result["risk_level"] = "high"
                validation_result["is_safe"] = False
                break
        
        # XSS patterns
        xss_patterns = [
            r"<script[^>]*>.*?</script>",
            r"javascript:",
            r"on\w+\s*=",
            r"<iframe[^>]*>",
            r"<object[^>]*>",
            r"<embed[^>]*>"
        ]
        
        for pattern in xss_patterns:
            if re.search(pattern, input_value, re.IGNORECASE):
                validation_result["potential_issues"].append("Potential XSS pattern detected")
                if validation_result["risk_level"] != "high":
                    validation_result["risk_level"] = "medium"
                validation_result["is_safe"] = False
        
        # Path traversal patterns
        path_patterns = [
            r"\.\./",
            r"\.\.\\",
            r"/etc/passwd",
            r"\\windows\\system32"
        ]
        
        for pattern in path_patterns:
            if re.search(pattern, input_value, re.IGNORECASE):
                validation_result["potential_issues"].append("Potential path traversal pattern detected")
                if validation_result["risk_level"] == "low":
                    validation_result["risk_level"] = "medium"
                validation_result["is_safe"] = False
        
        # Command injection patterns
        command_patterns = [
            r"[;&|`$()]",
            r"\b(cat|ls|pwd|whoami|id|uname)\b",
            r"(>|<|>>|<<)"
        ]
        
        for pattern in command_patterns:
            if re.search(pattern, input_value):
                validation_result["potential_issues"].append("Potential command injection pattern detected")
                if validation_result["risk_level"] == "low":
                    validation_result["risk_level"] = "medium"
                validation_result["is_safe"] = False
        
        # Generate recommendations
        if not validation_result["is_safe"]:
            validation_result["recommendations"].extend([
                "Implement input validation and sanitization",
                "Use parameterized queries for database operations",
                "Encode output to prevent XSS",
                "Validate file paths to prevent traversal attacks"
            ])
        
        # Basic sanitization (for demonstration)
        sanitized = input_value
        sanitized = re.sub(r'<script[^>]*>.*?</script>', '', sanitized, flags=re.IGNORECASE)
        sanitized = re.sub(r'[<>"\']', '', sanitized)
        validation_result["sanitized_value"] = sanitized
        
        return validation_result
    
    def validate_file_upload_security(self, filename: str, file_content: bytes = None) -> Dict[str, Any]:
        """Validate file upload security."""
        validation_result = {
            "filename": filename,
            "file_extension": "",
            "is_safe_extension": False,
            "file_size": len(file_content) if file_content else 0,
            "content_type_matches": True,
            "potential_issues": [],
            "risk_level": "low",
            "is_safe": True,
            "recommendations": []
        }
        
        # Extract file extension
        if '.' in filename:
            validation_result["file_extension"] = filename.split('.')[-1].lower()
        
        # Safe file extensions for learning environment
        safe_extensions = {
            'pdf', 'txt', 'doc', 'docx', 'rtf', 'odt',
            'jpg', 'jpeg', 'png', 'gif', 'bmp', 'webp',
            'mp3', 'wav', 'ogg', 'mp4', 'avi', 'mov', 'webm',
            'csv', 'json', 'xml', 'yaml', 'yml'
        }
        
        # Dangerous file extensions
        dangerous_extensions = {
            'exe', 'bat', 'cmd', 'com', 'pif', 'scr', 'vbs', 'js',
            'jar', 'php', 'asp', 'aspx', 'jsp', 'py', 'rb', 'pl',
            'sh', 'bash', 'ps1', 'sql'
        }
        
        file_ext = validation_result["file_extension"]
        
        if file_ext in safe_extensions:
            validation_result["is_safe_extension"] = True
        elif file_ext in dangerous_extensions:
            validation_result["potential_issues"].append(f"Dangerous file extension: {file_ext}")
            validation_result["risk_level"] = "high"
            validation_result["is_safe"] = False
        elif file_ext:
            validation_result["potential_issues"].append(f"Unknown file extension: {file_ext}")
            validation_result["risk_level"] = "medium"
        
        # Check filename for suspicious patterns
        suspicious_patterns = [
            r'\.\.',  # Path traversal
            r'[<>:"|?*]',  # Invalid filename characters
            r'^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])$',  # Windows reserved names
        ]
        
        for pattern in suspicious_patterns:
            if re.search(pattern, filename, re.IGNORECASE):
                validation_result["potential_issues"].append("Suspicious filename pattern detected")
                validation_result["risk_level"] = "medium"
                validation_result["is_safe"] = False
        
        # File size validation (10MB limit for learning)
        max_size = 10 * 1024 * 1024  # 10MB
        if validation_result["file_size"] > max_size:
            validation_result["potential_issues"].append(f"File too large: {validation_result['file_size']} bytes")
            validation_result["risk_level"] = "medium"
        
        # Generate recommendations
        if not validation_result["is_safe"]:
            validation_result["recommendations"].extend([
                "Restrict file uploads to safe extensions only",
                "Validate file content matches extension",
                "Scan uploaded files for malware",
                "Store uploaded files outside web root",
                "Implement file size limits"
            ])
        
        return validation_result
    
    def generate_secure_token(self, length: int = 32) -> str:
        """Generate a cryptographically secure random token."""
        return secrets.token_urlsafe(length)
    
    def hash_password(self, password: str, salt: str = None) -> Tuple[str, str]:
        """Hash password with salt using secure algorithm."""
        if salt is None:
            salt = secrets.token_hex(16)
        
        # Use PBKDF2 with SHA-256
        password_hash = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 100000)
        return password_hash.hex(), salt
    
    def verify_password(self, password: str, password_hash: str, salt: str) -> bool:
        """Verify password against hash."""
        computed_hash, _ = self.hash_password(password, salt)
        return secrets.compare_digest(computed_hash, password_hash)
    
    def validate_jwt_token_format(self, token: str) -> Dict[str, Any]:
        """Validate JWT token format (basic validation)."""
        validation_result = {
            "token_format": "invalid",
            "has_three_parts": False,
            "header_valid": False,
            "payload_valid": False,
            "signature_present": False,
            "issues": [],
            "recommendations": []
        }
        
        try:
            # JWT should have three parts separated by dots
            parts = token.split('.')
            
            if len(parts) == 3:
                validation_result["has_three_parts"] = True
                validation_result["signature_present"] = bool(parts[2])
                
                # Basic base64 validation for header and payload
                import base64
                
                try:
                    # Add padding if needed
                    header_padded = parts[0] + '=' * (4 - len(parts[0]) % 4)
                    base64.urlsafe_b64decode(header_padded)
                    validation_result["header_valid"] = True
                except Exception:
                    validation_result["issues"].append("Invalid JWT header encoding")
                
                try:
                    payload_padded = parts[1] + '=' * (4 - len(parts[1]) % 4)
                    base64.urlsafe_b64decode(payload_padded)
                    validation_result["payload_valid"] = True
                except Exception:
                    validation_result["issues"].append("Invalid JWT payload encoding")
                
                if validation_result["header_valid"] and validation_result["payload_valid"]:
                    validation_result["token_format"] = "valid"
            else:
                validation_result["issues"].append(f"JWT should have 3 parts, found {len(parts)}")
        
        except Exception as e:
            validation_result["issues"].append(f"JWT validation error: {str(e)}")
        
        if validation_result["token_format"] != "valid":
            validation_result["recommendations"].extend([
                "Ensure JWT token has proper format (header.payload.signature)",
                "Verify JWT token is properly base64 encoded",
                "Check JWT token generation process"
            ])
        
        return validation_result
    
    def check_common_vulnerabilities(self, target_url: str) -> Dict[str, Any]:
        """Check for common web application vulnerabilities."""
        self.logger.info(f"Checking common vulnerabilities for: {target_url}")
        
        vulnerability_check = {
            "target_url": target_url,
            "checks_performed": [],
            "vulnerabilities_found": [],
            "risk_level": "low",
            "recommendations": []
        }
        
        # Check for common security headers
        try:
            import requests
            response = requests.get(target_url, timeout=10)
            
            security_headers = {
                'X-Content-Type-Options': 'nosniff',
                'X-Frame-Options': 'DENY',
                'X-XSS-Protection': '1; mode=block',
                'Strict-Transport-Security': 'max-age=31536000',
                'Content-Security-Policy': 'default-src'
            }
            
            missing_headers = []
            for header, expected in security_headers.items():
                if header not in response.headers:
                    missing_headers.append(header)
            
            vulnerability_check["checks_performed"].append("Security headers check")
            
            if missing_headers:
                vulnerability_check["vulnerabilities_found"].append(
                    f"Missing security headers: {', '.join(missing_headers)}"
                )
                vulnerability_check["risk_level"] = "medium"
                vulnerability_check["recommendations"].append("Implement missing security headers")
        
        except Exception as e:
            vulnerability_check["checks_performed"].append(f"Security headers check failed: {str(e)}")
        
        return vulnerability_check


def validate_environment_security() -> Dict[str, Any]:
    """Validate security configuration of the current environment."""
    validator = BasicSecurityValidator()
    logger = get_logger("environment_security_validator")
    
    logger.info("Validating environment security configuration")
    
    validation_result = {
        "timestamp": datetime.now().isoformat(),
        "environment_checks": [],
        "overall_status": "unknown",
        "critical_issues": [],
        "recommendations": []
    }
    
    # Check environment variables for sensitive data
    env_check = {
        "check_name": "Environment Variables Security",
        "status": "pass",
        "issues": [],
        "recommendations": []
    }
    
    sensitive_patterns = [
        r'password', r'secret', r'key', r'token', r'credential'
    ]
    
    for env_var, env_value in os.environ.items():
        for pattern in sensitive_patterns:
            if re.search(pattern, env_var, re.IGNORECASE):
                if env_value and len(env_value) > 10:  # Likely contains actual secret
                    env_check["issues"].append(f"Potential secret in environment variable: {env_var}")
                    env_check["status"] = "warning"
    
    if env_check["issues"]:
        env_check["recommendations"].append("Move secrets to AWS Secrets Manager")
        env_check["recommendations"].append("Use IAM roles instead of hardcoded credentials")
    
    validation_result["environment_checks"].append(env_check)
    
    # Check file permissions (basic)
    file_check = {
        "check_name": "File Permissions Security",
        "status": "pass",
        "issues": [],
        "recommendations": []
    }
    
    # Check for world-writable files in current directory
    try:
        for root, dirs, files in os.walk('.'):
            for file in files:
                file_path = os.path.join(root, file)
                try:
                    file_stat = os.stat(file_path)
                    if file_stat.st_mode & 0o002:  # World writable
                        file_check["issues"].append(f"World-writable file: {file_path}")
                        file_check["status"] = "warning"
                except (OSError, PermissionError):
                    pass  # Skip files we can't access
    except Exception as e:
        file_check["issues"].append(f"File permission check failed: {str(e)}")
    
    if file_check["issues"]:
        file_check["recommendations"].append("Fix file permissions to prevent unauthorized access")
    
    validation_result["environment_checks"].append(file_check)
    
    # Determine overall status
    critical_count = sum(1 for check in validation_result["environment_checks"] if check["status"] == "fail")
    warning_count = sum(1 for check in validation_result["environment_checks"] if check["status"] == "warning")
    
    if critical_count > 0:
        validation_result["overall_status"] = "critical"
    elif warning_count > 0:
        validation_result["overall_status"] = "warning"
    else:
        validation_result["overall_status"] = "pass"
    
    # Collect all recommendations
    all_recommendations = []
    for check in validation_result["environment_checks"]:
        all_recommendations.extend(check["recommendations"])
    
    validation_result["recommendations"] = list(set(all_recommendations))
    
    return validation_result


if __name__ == "__main__":
    # Example usage
    validator = BasicSecurityValidator()
    
    # Test URL validation
    print("Testing URL validation:")
    url_result = validator.validate_url_security("https://example.com")
    print(f"HTTPS: {url_result['is_https']}")
    print(f"Issues: {url_result['issues']}")
    print()
    
    # Test password validation
    print("Testing password validation:")
    password_result = validator.validate_password_strength("TestPassword123!")
    print(f"Strong: {password_result['is_strong']}")
    print(f"Score: {password_result['strength_score']}")
    print()
    
    # Test input validation
    print("Testing input validation:")
    input_result = validator.validate_input_sanitization("SELECT * FROM users WHERE id = 1")
    print(f"Safe: {input_result['is_safe']}")
    print(f"Risk Level: {input_result['risk_level']}")
    print(f"Issues: {input_result['potential_issues']}")
    print()
    
    # Test environment validation
    print("Testing environment validation:")
    env_result = validate_environment_security()
    print(f"Overall Status: {env_result['overall_status']}")
    print(f"Recommendations: {env_result['recommendations']}")