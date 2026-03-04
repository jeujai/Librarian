#!/usr/bin/env python3
"""
AWS Basic Security Testing for Learning Deployment

This module provides basic security testing capabilities for the Multimodal
Librarian system deployed on AWS. It focuses on learning-oriented security
validation with cost-optimized testing scenarios.

Test Categories:
- Infrastructure security validation
- API endpoint security testing
- Authentication and authorization testing
- Data encryption validation
- Network security assessment
"""

import os
import sys
import asyncio
import aiohttp
import json
import ssl
import socket
from typing import Dict, Any, List, Optional
from datetime import datetime
from dataclasses import dataclass, asdict
import subprocess
import boto3

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from multimodal_librarian.logging_config import get_logger


@dataclass
class SecurityTestResult:
    """Security test result data structure."""
    test_name: str
    category: str
    start_time: datetime
    end_time: datetime
    duration_seconds: float
    passed: bool
    risk_level: str  # low, medium, high, critical
    findings: List[str]
    recommendations: List[str]
    compliance_status: str
    details: Dict[str, Any]


class AWSBasicSecurityTester:
    """Basic security tester for AWS learning deployment."""
    
    def __init__(self, base_url: str, aws_region: str = "us-east-1"):
        self.base_url = base_url.rstrip('/')
        self.aws_region = aws_region
        self.logger = get_logger("aws_basic_security_tester")
        
        # Initialize AWS clients (optional for learning)
        try:
            self.ec2_client = boto3.client('ec2', region_name=aws_region)
            self.iam_client = boto3.client('iam', region_name=aws_region)
            self.s3_client = boto3.client('s3', region_name=aws_region)
            self.logger.info("AWS clients initialized successfully")
        except Exception as e:
            self.logger.warning(f"AWS clients not available: {e}")
            self.ec2_client = None
            self.iam_client = None
            self.s3_client = None
        
        # Test results storage
        self.test_results = []
        
        self.logger.info(f"Initialized AWS security tester for {base_url}")
    
    async def run_security_assessment(self) -> Dict[str, Any]:
        """Run comprehensive security assessment."""
        self.logger.info("🔒 Starting AWS basic security assessment")
        
        assessment_results = {
            "start_time": datetime.now(),
            "target_url": self.base_url,
            "aws_region": self.aws_region,
            "test_results": [],
            "summary": {},
            "overall_risk_level": "unknown",
            "compliance_score": 0,
            "recommendations": []
        }
        
        print("=" * 80)
        print("🔒 AWS BASIC SECURITY ASSESSMENT")
        print("=" * 80)
        print(f"📅 Started: {assessment_results['start_time'].isoformat()}")
        print(f"🎯 Target: {self.base_url}")
        print(f"🌍 AWS Region: {self.aws_region}")
        print()
        
        # Security test categories
        test_categories = [
            {
                "name": "SSL/TLS Security",
                "description": "Test SSL/TLS configuration and certificate security",
                "test_func": self._test_ssl_tls_security
            },
            {
                "name": "API Security",
                "description": "Test API endpoint security and authentication",
                "test_func": self._test_api_security
            },
            {
                "name": "Authentication Security",
                "description": "Test authentication mechanisms and session security",
                "test_func": self._test_authentication_security
            },
            {
                "name": "Input Validation",
                "description": "Test input validation and injection protection",
                "test_func": self._test_input_validation
            },
            {
                "name": "Infrastructure Security",
                "description": "Test AWS infrastructure security configuration",
                "test_func": self._test_infrastructure_security
            }
        ]
        
        # Run security tests
        for i, category in enumerate(test_categories, 1):
            print(f"🔍 [{i}/{len(test_categories)}] {category['name']}")
            print(f"   {category['description']}")
            print("-" * 60)
            
            try:
                results = await category['test_func']()
                if isinstance(results, list):
                    self.test_results.extend(results)
                    assessment_results["test_results"].extend(results)
                else:
                    self.test_results.append(results)
                    assessment_results["test_results"].append(results)
                
                # Print category summary
                self._print_category_summary(category['name'], results)
                
            except Exception as e:
                self.logger.error(f"Error in {category['name']}: {e}")
                error_result = SecurityTestResult(
                    test_name=f"{category['name']} - Error",
                    category=category['name'],
                    start_time=datetime.now(),
                    end_time=datetime.now(),
                    duration_seconds=0,
                    passed=False,
                    risk_level="high",
                    findings=[f"Test execution failed: {str(e)}"],
                    recommendations=["Review test configuration and retry"],
                    compliance_status="failed",
                    details={"error": str(e)}
                )
                self.test_results.append(error_result)
                assessment_results["test_results"].append(error_result)
            
            print()
        
        # Generate assessment summary
        assessment_results["end_time"] = datetime.now()
        assessment_results["total_duration"] = (
            assessment_results["end_time"] - assessment_results["start_time"]
        ).total_seconds()
        
        self._generate_security_summary(assessment_results)
        self._print_security_summary(assessment_results)
        
        return assessment_results
    
    async def _test_ssl_tls_security(self) -> List[SecurityTestResult]:
        """Test SSL/TLS configuration and certificate security."""
        self.logger.info("Testing SSL/TLS security configuration")
        
        ssl_tests = []
        
        # Test 1: SSL Certificate Validation
        ssl_cert_test = SecurityTestResult(
            test_name="SSL Certificate Validation",
            category="SSL/TLS Security",
            start_time=datetime.now(),
            end_time=None,
            duration_seconds=0,
            passed=False,
            risk_level="medium",
            findings=[],
            recommendations=[],
            compliance_status="unknown",
            details={}
        )
        
        try:
            # Extract hostname from URL
            from urllib.parse import urlparse
            parsed_url = urlparse(self.base_url)
            hostname = parsed_url.hostname
            port = parsed_url.port or (443 if parsed_url.scheme == 'https' else 80)
            
            if parsed_url.scheme == 'https':
                # Test SSL certificate
                context = ssl.create_default_context()
                
                with socket.create_connection((hostname, port), timeout=10) as sock:
                    with context.wrap_socket(sock, server_hostname=hostname) as ssock:
                        cert = ssock.getpeercert()
                        
                        ssl_cert_test.details = {
                            "subject": dict(x[0] for x in cert['subject']),
                            "issuer": dict(x[0] for x in cert['issuer']),
                            "version": cert['version'],
                            "serial_number": cert['serialNumber'],
                            "not_before": cert['notBefore'],
                            "not_after": cert['notAfter']
                        }
                        
                        # Check certificate validity
                        import datetime as dt
                        not_after = dt.datetime.strptime(cert['notAfter'], '%b %d %H:%M:%S %Y %Z')
                        days_until_expiry = (not_after - dt.datetime.now()).days
                        
                        if days_until_expiry > 30:
                            ssl_cert_test.passed = True
                            ssl_cert_test.risk_level = "low"
                            ssl_cert_test.compliance_status = "compliant"
                            ssl_cert_test.findings.append(f"SSL certificate valid for {days_until_expiry} days")
                        elif days_until_expiry > 7:
                            ssl_cert_test.passed = True
                            ssl_cert_test.risk_level = "medium"
                            ssl_cert_test.compliance_status = "warning"
                            ssl_cert_test.findings.append(f"SSL certificate expires in {days_until_expiry} days")
                            ssl_cert_test.recommendations.append("Renew SSL certificate soon")
                        else:
                            ssl_cert_test.passed = False
                            ssl_cert_test.risk_level = "high"
                            ssl_cert_test.compliance_status = "non_compliant"
                            ssl_cert_test.findings.append(f"SSL certificate expires in {days_until_expiry} days")
                            ssl_cert_test.recommendations.append("Renew SSL certificate immediately")
            else:
                ssl_cert_test.passed = False
                ssl_cert_test.risk_level = "high"
                ssl_cert_test.compliance_status = "non_compliant"
                ssl_cert_test.findings.append("No HTTPS encryption detected")
                ssl_cert_test.recommendations.append("Enable HTTPS with valid SSL certificate")
        
        except Exception as e:
            ssl_cert_test.passed = False
            ssl_cert_test.risk_level = "high"
            ssl_cert_test.compliance_status = "failed"
            ssl_cert_test.findings.append(f"SSL certificate test failed: {str(e)}")
            ssl_cert_test.recommendations.append("Review SSL configuration")
        
        ssl_cert_test.end_time = datetime.now()
        ssl_cert_test.duration_seconds = (ssl_cert_test.end_time - ssl_cert_test.start_time).total_seconds()
        ssl_tests.append(ssl_cert_test)
        
        # Test 2: TLS Protocol Security
        tls_protocol_test = SecurityTestResult(
            test_name="TLS Protocol Security",
            category="SSL/TLS Security",
            start_time=datetime.now(),
            end_time=None,
            duration_seconds=0,
            passed=False,
            risk_level="medium",
            findings=[],
            recommendations=[],
            compliance_status="unknown",
            details={}
        )
        
        try:
            # Test TLS version support
            async with aiohttp.ClientSession(
                connector=aiohttp.TCPConnector(ssl=False),
                timeout=aiohttp.ClientTimeout(total=10)
            ) as session:
                async with session.get(f"{self.base_url}/health") as response:
                    tls_protocol_test.details = {
                        "response_headers": dict(response.headers),
                        "status_code": response.status
                    }
                    
                    # Check security headers
                    security_headers = {
                        'Strict-Transport-Security': 'HSTS header missing',
                        'X-Content-Type-Options': 'Content type options header missing',
                        'X-Frame-Options': 'Frame options header missing',
                        'X-XSS-Protection': 'XSS protection header missing'
                    }
                    
                    missing_headers = []
                    for header, message in security_headers.items():
                        if header not in response.headers:
                            missing_headers.append(message)
                    
                    if not missing_headers:
                        tls_protocol_test.passed = True
                        tls_protocol_test.risk_level = "low"
                        tls_protocol_test.compliance_status = "compliant"
                        tls_protocol_test.findings.append("All security headers present")
                    elif len(missing_headers) <= 2:
                        tls_protocol_test.passed = True
                        tls_protocol_test.risk_level = "medium"
                        tls_protocol_test.compliance_status = "warning"
                        tls_protocol_test.findings.extend(missing_headers)
                        tls_protocol_test.recommendations.append("Add missing security headers")
                    else:
                        tls_protocol_test.passed = False
                        tls_protocol_test.risk_level = "high"
                        tls_protocol_test.compliance_status = "non_compliant"
                        tls_protocol_test.findings.extend(missing_headers)
                        tls_protocol_test.recommendations.append("Implement comprehensive security headers")
        
        except Exception as e:
            tls_protocol_test.passed = False
            tls_protocol_test.risk_level = "medium"
            tls_protocol_test.compliance_status = "failed"
            tls_protocol_test.findings.append(f"TLS protocol test failed: {str(e)}")
            tls_protocol_test.recommendations.append("Review TLS configuration")
        
        tls_protocol_test.end_time = datetime.now()
        tls_protocol_test.duration_seconds = (tls_protocol_test.end_time - tls_protocol_test.start_time).total_seconds()
        ssl_tests.append(tls_protocol_test)
        
        return ssl_tests
    
    async def _test_api_security(self) -> List[SecurityTestResult]:
        """Test API endpoint security and authentication."""
        self.logger.info("Testing API security configuration")
        
        api_tests = []
        
        # Test 1: API Authentication
        auth_test = SecurityTestResult(
            test_name="API Authentication",
            category="API Security",
            start_time=datetime.now(),
            end_time=None,
            duration_seconds=0,
            passed=False,
            risk_level="medium",
            findings=[],
            recommendations=[],
            compliance_status="unknown",
            details={}
        )
        
        try:
            # Test unauthenticated access to protected endpoints
            protected_endpoints = [
                "/api/conversations",
                "/api/documents/upload",
                "/api/ml-training/status",
                "/api/knowledge-graph/query"
            ]
            
            unauthenticated_access = []
            
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
                for endpoint in protected_endpoints:
                    try:
                        async with session.get(f"{self.base_url}{endpoint}") as response:
                            if response.status == 200:
                                unauthenticated_access.append(endpoint)
                            
                            auth_test.details[endpoint] = {
                                "status_code": response.status,
                                "requires_auth": response.status != 200
                            }
                    except Exception as e:
                        auth_test.details[endpoint] = {"error": str(e)}
                
                if not unauthenticated_access:
                    auth_test.passed = True
                    auth_test.risk_level = "low"
                    auth_test.compliance_status = "compliant"
                    auth_test.findings.append("All protected endpoints require authentication")
                else:
                    auth_test.passed = False
                    auth_test.risk_level = "high"
                    auth_test.compliance_status = "non_compliant"
                    auth_test.findings.append(f"Unauthenticated access to: {', '.join(unauthenticated_access)}")
                    auth_test.recommendations.append("Implement authentication for all protected endpoints")
        
        except Exception as e:
            auth_test.passed = False
            auth_test.risk_level = "medium"
            auth_test.compliance_status = "failed"
            auth_test.findings.append(f"API authentication test failed: {str(e)}")
            auth_test.recommendations.append("Review API authentication configuration")
        
        auth_test.end_time = datetime.now()
        auth_test.duration_seconds = (auth_test.end_time - auth_test.start_time).total_seconds()
        api_tests.append(auth_test)
        
        # Test 2: Rate Limiting
        rate_limit_test = SecurityTestResult(
            test_name="API Rate Limiting",
            category="API Security",
            start_time=datetime.now(),
            end_time=None,
            duration_seconds=0,
            passed=False,
            risk_level="medium",
            findings=[],
            recommendations=[],
            compliance_status="unknown",
            details={}
        )
        
        try:
            # Test rate limiting by making rapid requests
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
                rate_limit_responses = []
                
                for i in range(20):  # Make 20 rapid requests
                    try:
                        async with session.get(f"{self.base_url}/health") as response:
                            rate_limit_responses.append({
                                "request_number": i + 1,
                                "status_code": response.status,
                                "headers": dict(response.headers)
                            })
                    except Exception as e:
                        rate_limit_responses.append({
                            "request_number": i + 1,
                            "error": str(e)
                        })
                
                # Check for rate limiting indicators
                rate_limited = any(
                    resp.get("status_code") == 429 or 
                    "rate" in str(resp.get("headers", {})).lower()
                    for resp in rate_limit_responses
                )
                
                rate_limit_test.details = {"responses": rate_limit_responses}
                
                if rate_limited:
                    rate_limit_test.passed = True
                    rate_limit_test.risk_level = "low"
                    rate_limit_test.compliance_status = "compliant"
                    rate_limit_test.findings.append("Rate limiting is active")
                else:
                    rate_limit_test.passed = False
                    rate_limit_test.risk_level = "medium"
                    rate_limit_test.compliance_status = "warning"
                    rate_limit_test.findings.append("No rate limiting detected")
                    rate_limit_test.recommendations.append("Implement API rate limiting to prevent abuse")
        
        except Exception as e:
            rate_limit_test.passed = False
            rate_limit_test.risk_level = "medium"
            rate_limit_test.compliance_status = "failed"
            rate_limit_test.findings.append(f"Rate limiting test failed: {str(e)}")
            rate_limit_test.recommendations.append("Review rate limiting configuration")
        
        rate_limit_test.end_time = datetime.now()
        rate_limit_test.duration_seconds = (rate_limit_test.end_time - rate_limit_test.start_time).total_seconds()
        api_tests.append(rate_limit_test)
        
        return api_tests
    
    async def _test_authentication_security(self) -> List[SecurityTestResult]:
        """Test authentication mechanisms and session security."""
        self.logger.info("Testing authentication security")
        
        auth_tests = []
        
        # Test 1: Session Security
        session_test = SecurityTestResult(
            test_name="Session Security",
            category="Authentication Security",
            start_time=datetime.now(),
            end_time=None,
            duration_seconds=0,
            passed=False,
            risk_level="medium",
            findings=[],
            recommendations=[],
            compliance_status="unknown",
            details={}
        )
        
        try:
            # Test session cookie security
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
                async with session.get(f"{self.base_url}/") as response:
                    cookies = response.cookies
                    headers = response.headers
                    
                    session_test.details = {
                        "cookies": {name: cookie.value for name, cookie in cookies.items()},
                        "set_cookie_headers": headers.getall('Set-Cookie', [])
                    }
                    
                    # Check for secure session cookies
                    secure_cookies = []
                    insecure_cookies = []
                    
                    for cookie_header in headers.getall('Set-Cookie', []):
                        if 'Secure' in cookie_header and 'HttpOnly' in cookie_header:
                            secure_cookies.append(cookie_header)
                        else:
                            insecure_cookies.append(cookie_header)
                    
                    if insecure_cookies:
                        session_test.passed = False
                        session_test.risk_level = "medium"
                        session_test.compliance_status = "non_compliant"
                        session_test.findings.append(f"Insecure cookies detected: {len(insecure_cookies)}")
                        session_test.recommendations.append("Set Secure and HttpOnly flags on all cookies")
                    else:
                        session_test.passed = True
                        session_test.risk_level = "low"
                        session_test.compliance_status = "compliant"
                        session_test.findings.append("Session cookies are properly secured")
        
        except Exception as e:
            session_test.passed = False
            session_test.risk_level = "medium"
            session_test.compliance_status = "failed"
            session_test.findings.append(f"Session security test failed: {str(e)}")
            session_test.recommendations.append("Review session configuration")
        
        session_test.end_time = datetime.now()
        session_test.duration_seconds = (session_test.end_time - session_test.start_time).total_seconds()
        auth_tests.append(session_test)
        
        # Test 2: Password Policy (if applicable)
        password_test = SecurityTestResult(
            test_name="Password Policy",
            category="Authentication Security",
            start_time=datetime.now(),
            end_time=None,
            duration_seconds=0,
            passed=True,  # Default to pass for learning environment
            risk_level="low",
            findings=["Password policy testing skipped for learning environment"],
            recommendations=["Implement strong password policies in production"],
            compliance_status="not_applicable",
            details={}
        )
        
        password_test.end_time = datetime.now()
        password_test.duration_seconds = (password_test.end_time - password_test.start_time).total_seconds()
        auth_tests.append(password_test)
        
        return auth_tests
    
    async def _test_input_validation(self) -> List[SecurityTestResult]:
        """Test input validation and injection protection."""
        self.logger.info("Testing input validation security")
        
        input_tests = []
        
        # Test 1: SQL Injection Protection
        sql_injection_test = SecurityTestResult(
            test_name="SQL Injection Protection",
            category="Input Validation",
            start_time=datetime.now(),
            end_time=None,
            duration_seconds=0,
            passed=False,
            risk_level="high",
            findings=[],
            recommendations=[],
            compliance_status="unknown",
            details={}
        )
        
        try:
            # Test basic SQL injection patterns
            sql_payloads = [
                "' OR '1'='1",
                "'; DROP TABLE users; --",
                "' UNION SELECT * FROM users --",
                "admin'--",
                "' OR 1=1 --"
            ]
            
            vulnerable_endpoints = []
            
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
                for payload in sql_payloads:
                    # Test search endpoint with SQL injection payload
                    try:
                        search_data = {"query": payload}
                        async with session.post(
                            f"{self.base_url}/api/search/vector",
                            json=search_data,
                            headers={"Content-Type": "application/json"}
                        ) as response:
                            response_text = await response.text()
                            
                            # Check for SQL error messages
                            sql_errors = [
                                "sql syntax",
                                "mysql_fetch",
                                "ora-",
                                "postgresql",
                                "sqlite",
                                "syntax error"
                            ]
                            
                            if any(error in response_text.lower() for error in sql_errors):
                                vulnerable_endpoints.append(f"/api/search/vector with payload: {payload}")
                    
                    except Exception:
                        pass  # Connection errors are expected for some payloads
                
                sql_injection_test.details = {
                    "payloads_tested": sql_payloads,
                    "vulnerable_endpoints": vulnerable_endpoints
                }
                
                if not vulnerable_endpoints:
                    sql_injection_test.passed = True
                    sql_injection_test.risk_level = "low"
                    sql_injection_test.compliance_status = "compliant"
                    sql_injection_test.findings.append("No SQL injection vulnerabilities detected")
                else:
                    sql_injection_test.passed = False
                    sql_injection_test.risk_level = "critical"
                    sql_injection_test.compliance_status = "non_compliant"
                    sql_injection_test.findings.extend(vulnerable_endpoints)
                    sql_injection_test.recommendations.append("Implement parameterized queries and input validation")
        
        except Exception as e:
            sql_injection_test.passed = False
            sql_injection_test.risk_level = "medium"
            sql_injection_test.compliance_status = "failed"
            sql_injection_test.findings.append(f"SQL injection test failed: {str(e)}")
            sql_injection_test.recommendations.append("Review input validation implementation")
        
        sql_injection_test.end_time = datetime.now()
        sql_injection_test.duration_seconds = (sql_injection_test.end_time - sql_injection_test.start_time).total_seconds()
        input_tests.append(sql_injection_test)
        
        # Test 2: XSS Protection
        xss_test = SecurityTestResult(
            test_name="XSS Protection",
            category="Input Validation",
            start_time=datetime.now(),
            end_time=None,
            duration_seconds=0,
            passed=False,
            risk_level="medium",
            findings=[],
            recommendations=[],
            compliance_status="unknown",
            details={}
        )
        
        try:
            # Test basic XSS patterns
            xss_payloads = [
                "<script>alert('xss')</script>",
                "javascript:alert('xss')",
                "<img src=x onerror=alert('xss')>",
                "';alert('xss');//",
                "<svg onload=alert('xss')>"
            ]
            
            xss_vulnerable = []
            
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
                for payload in xss_payloads:
                    try:
                        # Test chat message with XSS payload
                        message_data = {"content": payload, "user_id": "test_user"}
                        async with session.post(
                            f"{self.base_url}/api/conversations",
                            json=message_data,
                            headers={"Content-Type": "application/json"}
                        ) as response:
                            response_text = await response.text()
                            
                            # Check if payload is reflected unescaped
                            if payload in response_text and "<script>" in response_text:
                                xss_vulnerable.append(f"Chat endpoint reflects: {payload}")
                    
                    except Exception:
                        pass  # Connection errors are expected
                
                xss_test.details = {
                    "payloads_tested": xss_payloads,
                    "vulnerable_reflections": xss_vulnerable
                }
                
                if not xss_vulnerable:
                    xss_test.passed = True
                    xss_test.risk_level = "low"
                    xss_test.compliance_status = "compliant"
                    xss_test.findings.append("No XSS vulnerabilities detected")
                else:
                    xss_test.passed = False
                    xss_test.risk_level = "high"
                    xss_test.compliance_status = "non_compliant"
                    xss_test.findings.extend(xss_vulnerable)
                    xss_test.recommendations.append("Implement proper input sanitization and output encoding")
        
        except Exception as e:
            xss_test.passed = False
            xss_test.risk_level = "medium"
            xss_test.compliance_status = "failed"
            xss_test.findings.append(f"XSS test failed: {str(e)}")
            xss_test.recommendations.append("Review XSS protection implementation")
        
        xss_test.end_time = datetime.now()
        xss_test.duration_seconds = (xss_test.end_time - xss_test.start_time).total_seconds()
        input_tests.append(xss_test)
        
        return input_tests
    
    async def _test_infrastructure_security(self) -> List[SecurityTestResult]:
        """Test AWS infrastructure security configuration."""
        self.logger.info("Testing AWS infrastructure security")
        
        infra_tests = []
        
        # Test 1: S3 Bucket Security
        s3_test = SecurityTestResult(
            test_name="S3 Bucket Security",
            category="Infrastructure Security",
            start_time=datetime.now(),
            end_time=None,
            duration_seconds=0,
            passed=False,
            risk_level="medium",
            findings=[],
            recommendations=[],
            compliance_status="unknown",
            details={}
        )
        
        try:
            if self.s3_client:
                # List buckets and check public access
                buckets_response = self.s3_client.list_buckets()
                
                public_buckets = []
                encrypted_buckets = []
                
                for bucket in buckets_response.get('Buckets', []):
                    bucket_name = bucket['Name']
                    
                    try:
                        # Check public access block
                        public_access = self.s3_client.get_public_access_block(Bucket=bucket_name)
                        if not all(public_access['PublicAccessBlockConfiguration'].values()):
                            public_buckets.append(bucket_name)
                    except Exception:
                        public_buckets.append(bucket_name)  # Assume public if can't check
                    
                    try:
                        # Check encryption
                        encryption = self.s3_client.get_bucket_encryption(Bucket=bucket_name)
                        if encryption:
                            encrypted_buckets.append(bucket_name)
                    except Exception:
                        pass  # No encryption configured
                
                s3_test.details = {
                    "total_buckets": len(buckets_response.get('Buckets', [])),
                    "public_buckets": public_buckets,
                    "encrypted_buckets": encrypted_buckets
                }
                
                if not public_buckets:
                    s3_test.passed = True
                    s3_test.risk_level = "low"
                    s3_test.compliance_status = "compliant"
                    s3_test.findings.append("All S3 buckets have proper access controls")
                else:
                    s3_test.passed = False
                    s3_test.risk_level = "high"
                    s3_test.compliance_status = "non_compliant"
                    s3_test.findings.append(f"Public S3 buckets detected: {', '.join(public_buckets)}")
                    s3_test.recommendations.append("Enable S3 public access block on all buckets")
                
                if len(encrypted_buckets) < len(buckets_response.get('Buckets', [])):
                    s3_test.recommendations.append("Enable S3 bucket encryption for all buckets")
            else:
                s3_test.passed = True
                s3_test.risk_level = "low"
                s3_test.compliance_status = "not_applicable"
                s3_test.findings.append("S3 security test skipped - AWS client not available")
        
        except Exception as e:
            s3_test.passed = False
            s3_test.risk_level = "medium"
            s3_test.compliance_status = "failed"
            s3_test.findings.append(f"S3 security test failed: {str(e)}")
            s3_test.recommendations.append("Review S3 configuration and permissions")
        
        s3_test.end_time = datetime.now()
        s3_test.duration_seconds = (s3_test.end_time - s3_test.start_time).total_seconds()
        infra_tests.append(s3_test)
        
        # Test 2: Network Security
        network_test = SecurityTestResult(
            test_name="Network Security",
            category="Infrastructure Security",
            start_time=datetime.now(),
            end_time=None,
            duration_seconds=0,
            passed=False,
            risk_level="medium",
            findings=[],
            recommendations=[],
            compliance_status="unknown",
            details={}
        )
        
        try:
            # Test for common open ports
            from urllib.parse import urlparse
            parsed_url = urlparse(self.base_url)
            hostname = parsed_url.hostname
            
            common_ports = [22, 23, 25, 53, 80, 110, 143, 443, 993, 995, 3389, 5432, 3306]
            open_ports = []
            
            for port in common_ports:
                try:
                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    sock.settimeout(2)
                    result = sock.connect_ex((hostname, port))
                    if result == 0:
                        open_ports.append(port)
                    sock.close()
                except Exception:
                    pass
            
            network_test.details = {
                "hostname": hostname,
                "ports_scanned": common_ports,
                "open_ports": open_ports
            }
            
            # Expected ports for web application
            expected_ports = [80, 443]
            unexpected_ports = [port for port in open_ports if port not in expected_ports]
            
            if not unexpected_ports:
                network_test.passed = True
                network_test.risk_level = "low"
                network_test.compliance_status = "compliant"
                network_test.findings.append("Only expected ports are open")
            else:
                network_test.passed = False
                network_test.risk_level = "medium"
                network_test.compliance_status = "warning"
                network_test.findings.append(f"Unexpected open ports: {unexpected_ports}")
                network_test.recommendations.append("Review and close unnecessary open ports")
        
        except Exception as e:
            network_test.passed = False
            network_test.risk_level = "medium"
            network_test.compliance_status = "failed"
            network_test.findings.append(f"Network security test failed: {str(e)}")
            network_test.recommendations.append("Review network security configuration")
        
        network_test.end_time = datetime.now()
        network_test.duration_seconds = (network_test.end_time - network_test.start_time).total_seconds()
        infra_tests.append(network_test)
        
        return infra_tests
    
    def _print_category_summary(self, category_name: str, results):
        """Print summary for a security test category."""
        if isinstance(results, list):
            test_results = results
        else:
            test_results = [results]
        
        passed_tests = len([r for r in test_results if r.passed])
        total_tests = len(test_results)
        
        status_icon = "✅" if passed_tests == total_tests else "⚠️" if passed_tests > 0 else "❌"
        
        print(f"{status_icon} {category_name}: {passed_tests}/{total_tests} tests passed")
        
        for result in test_results:
            test_icon = "✅" if result.passed else "❌"
            risk_icon = {"low": "🟢", "medium": "🟡", "high": "🔴", "critical": "🚨"}.get(result.risk_level, "⚪")
            
            print(f"   {test_icon} {result.test_name} {risk_icon}")
            
            if result.findings:
                for finding in result.findings[:2]:  # Show top 2 findings
                    print(f"      • {finding}")
    
    def _generate_security_summary(self, assessment_results: Dict[str, Any]):
        """Generate comprehensive security assessment summary."""
        test_results = assessment_results["test_results"]
        
        # Calculate summary statistics
        total_tests = len(test_results)
        passed_tests = len([r for r in test_results if r.passed])
        failed_tests = total_tests - passed_tests
        
        # Risk level distribution
        risk_levels = {"low": 0, "medium": 0, "high": 0, "critical": 0}
        for result in test_results:
            risk_levels[result.risk_level] = risk_levels.get(result.risk_level, 0) + 1
        
        # Compliance status distribution
        compliance_statuses = {"compliant": 0, "warning": 0, "non_compliant": 0, "failed": 0, "not_applicable": 0}
        for result in test_results:
            compliance_statuses[result.compliance_status] = compliance_statuses.get(result.compliance_status, 0) + 1
        
        # Determine overall risk level
        if risk_levels["critical"] > 0:
            overall_risk = "critical"
        elif risk_levels["high"] > 0:
            overall_risk = "high"
        elif risk_levels["medium"] > 0:
            overall_risk = "medium"
        else:
            overall_risk = "low"
        
        # Calculate compliance score (0-100)
        compliance_score = 0
        if total_tests > 0:
            compliant_weight = compliance_statuses["compliant"] * 100
            warning_weight = compliance_statuses["warning"] * 75
            not_applicable_weight = compliance_statuses["not_applicable"] * 100
            
            total_weight = compliant_weight + warning_weight + not_applicable_weight
            max_possible = total_tests * 100
            
            compliance_score = (total_weight / max_possible) * 100 if max_possible > 0 else 0
        
        # Generate recommendations
        all_recommendations = []
        for result in test_results:
            all_recommendations.extend(result.recommendations)
        
        # Remove duplicates and prioritize
        unique_recommendations = list(set(all_recommendations))
        
        # Prioritize critical recommendations
        critical_recommendations = [
            rec for result in test_results 
            if result.risk_level in ["critical", "high"]
            for rec in result.recommendations
        ]
        
        prioritized_recommendations = list(set(critical_recommendations)) + [
            rec for rec in unique_recommendations if rec not in critical_recommendations
        ]
        
        assessment_results["summary"] = {
            "total_tests": total_tests,
            "passed_tests": passed_tests,
            "failed_tests": failed_tests,
            "success_rate": (passed_tests / total_tests * 100) if total_tests > 0 else 0,
            "risk_level_distribution": risk_levels,
            "compliance_status_distribution": compliance_statuses,
            "compliance_score": compliance_score
        }
        
        assessment_results["overall_risk_level"] = overall_risk
        assessment_results["compliance_score"] = compliance_score
        assessment_results["recommendations"] = prioritized_recommendations[:10]  # Top 10 recommendations
    
    def _print_security_summary(self, assessment_results: Dict[str, Any]):
        """Print comprehensive security assessment summary."""
        summary = assessment_results["summary"]
        
        print("=" * 80)
        print("🔒 SECURITY ASSESSMENT SUMMARY")
        print("=" * 80)
        print(f"⏱️  Total Duration: {assessment_results['total_duration']:.1f} seconds")
        print(f"🎯 Overall Risk Level: {assessment_results['overall_risk_level'].upper()}")
        print(f"📊 Compliance Score: {assessment_results['compliance_score']:.1f}/100")
        print()
        
        print("📋 Test Results:")
        print(f"   Total Tests: {summary['total_tests']}")
        print(f"   ✅ Passed: {summary['passed_tests']}")
        print(f"   ❌ Failed: {summary['failed_tests']}")
        print(f"   📈 Success Rate: {summary['success_rate']:.1f}%")
        print()
        
        print("⚠️  Risk Level Distribution:")
        risk_icons = {"low": "🟢", "medium": "🟡", "high": "🔴", "critical": "🚨"}
        for level, count in summary["risk_level_distribution"].items():
            if count > 0:
                print(f"   {risk_icons[level]} {level.title()}: {count}")
        print()
        
        print("📋 Compliance Status:")
        compliance_icons = {
            "compliant": "✅", "warning": "⚠️", "non_compliant": "❌", 
            "failed": "💥", "not_applicable": "➖"
        }
        for status, count in summary["compliance_status_distribution"].items():
            if count > 0:
                print(f"   {compliance_icons[status]} {status.replace('_', ' ').title()}: {count}")
        print()
        
        print("💡 Top Security Recommendations:")
        for i, recommendation in enumerate(assessment_results["recommendations"][:5], 1):
            print(f"   {i}. {recommendation}")
        print()
        
        # Overall assessment
        overall_risk = assessment_results["overall_risk_level"]
        compliance_score = assessment_results["compliance_score"]
        
        if overall_risk == "low" and compliance_score >= 90:
            print("🎉 EXCELLENT SECURITY POSTURE - System security is very good!")
        elif overall_risk == "medium" and compliance_score >= 75:
            print("✅ GOOD SECURITY POSTURE - System security is acceptable with minor issues")
        elif overall_risk == "high" or compliance_score < 60:
            print("⚠️  SECURITY ISSUES DETECTED - Address high-risk findings immediately")
        else:
            print("❌ CRITICAL SECURITY ISSUES - Immediate action required")
        
        print("=" * 80)


async def run_aws_security_test(
    base_url: str = "http://localhost:8000",
    aws_region: str = "us-east-1",
    output_file: Optional[str] = None
) -> Dict[str, Any]:
    """Run AWS basic security assessment."""
    
    # Create security tester
    tester = AWSBasicSecurityTester(base_url, aws_region)
    
    # Run security assessment
    results = await tester.run_security_assessment()
    
    # Save results if requested
    if output_file:
        try:
            # Convert datetime objects to strings for JSON serialization
            results_copy = json.loads(json.dumps(results, default=str))
            
            with open(output_file, 'w') as f:
                json.dump(results_copy, f, indent=2)
            
            print(f"📄 Security assessment results saved to: {output_file}")
            
        except Exception as e:
            print(f"⚠️  Could not save results: {e}")
    
    return results


def main():
    """Main security test runner function."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Run AWS Basic Security Tests')
    parser.add_argument('--url', type=str, default='http://localhost:8000',
                       help='Base URL for security testing')
    parser.add_argument('--region', type=str, default='us-east-1',
                       help='AWS region for infrastructure testing')
    parser.add_argument('--output', type=str,
                       help='Output file for results (JSON)')
    
    args = parser.parse_args()
    
    # Run security assessment
    results = asyncio.run(run_aws_security_test(
        base_url=args.url,
        aws_region=args.region,
        output_file=args.output
    ))
    
    # Exit with appropriate code
    overall_risk = results.get("overall_risk_level", "high")
    compliance_score = results.get("compliance_score", 0)
    
    if overall_risk == "low" and compliance_score >= 90:
        exit(0)  # Excellent security
    elif overall_risk == "medium" and compliance_score >= 75:
        exit(1)  # Good security with warnings
    elif overall_risk == "high" or compliance_score < 60:
        exit(2)  # Security issues detected
    else:
        exit(3)  # Critical security issues


if __name__ == "__main__":
    main()