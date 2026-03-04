"""
SSL Configuration Validator for Production Deployment Checklist.

This validator ensures that load balancers have proper HTTPS/SSL configuration
including SSL listeners, valid certificates, HTTPS redirects, and security headers.
Validates Requirements 3.1, 3.2, 3.3.
"""

import json
import logging
import ssl
import socket
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Tuple
from urllib.parse import urlparse
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from botocore.exceptions import ClientError

from .base_validator import BaseValidator, ValidationError, ValidationUtilities
from .models import ValidationResult, DeploymentConfig


class SSLConfigValidator(BaseValidator):
    """Validates SSL/HTTPS configuration for load balancers and certificates."""
    
    def __init__(self, region: str = "us-east-1"):
        """Initialize SSL configuration validator."""
        super().__init__(region)
        
        # Required security headers for production
        self.required_security_headers = {
            'Strict-Transport-Security': 'HSTS header for HTTPS enforcement',
            'X-Content-Type-Options': 'Prevents MIME type sniffing',
            'X-Frame-Options': 'Prevents clickjacking attacks',
            'X-XSS-Protection': 'XSS protection (legacy browsers)',
            'Content-Security-Policy': 'CSP for content security'
        }
        
        # Recommended security header values
        self.recommended_header_values = {
            'Strict-Transport-Security': 'max-age=31536000; includeSubDomains',
            'X-Content-Type-Options': 'nosniff',
            'X-Frame-Options': 'DENY',
            'X-XSS-Protection': '1; mode=block'
        }
        
        # Configure requests session with retries
        self.session = requests.Session()
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
    
    def validate(self, deployment_config: DeploymentConfig) -> ValidationResult:
        """
        Validate SSL configuration for the deployment.
        
        Args:
            deployment_config: Configuration containing load balancer ARN and SSL certificate ARN
            
        Returns:
            ValidationResult with validation status and details
        """
        check_name = "SSL Configuration Validation"
        
        try:
            # Validate load balancer ARN format
            if not self._validate_load_balancer_arn(deployment_config.load_balancer_arn):
                return self.create_failure_result(
                    check_name=check_name,
                    message=f"Invalid load balancer ARN format: {deployment_config.load_balancer_arn}",
                    remediation_steps=[
                        "Verify the load balancer ARN is correctly formatted",
                        "Ensure the load balancer exists in your AWS account",
                        "Check that the ARN matches the pattern: arn:aws:elasticloadbalancing:REGION:ACCOUNT:loadbalancer/app/NAME/ID"
                    ],
                    fix_scripts=["scripts/add-https-ssl-support.py"]
                )
            
            # Get load balancer details and listeners
            lb_details, listeners = self._get_load_balancer_configuration(
                deployment_config.load_balancer_arn
            )
            
            if not lb_details:
                return self.create_failure_result(
                    check_name=check_name,
                    message=f"Could not retrieve load balancer details for {deployment_config.load_balancer_arn}",
                    remediation_steps=[
                        "Verify the load balancer exists and is accessible",
                        "Check IAM permissions for elasticloadbalancing:DescribeLoadBalancers",
                        "Ensure the load balancer ARN is correct"
                    ],
                    fix_scripts=["scripts/add-https-ssl-support.py"]
                )
            
            # Validate SSL listener configuration
            ssl_validation = self._validate_ssl_listeners(listeners, deployment_config.ssl_certificate_arn)
            
            if not ssl_validation['has_ssl_listener']:
                return self._create_ssl_listener_failure_result(check_name, ssl_validation)
            
            # Validate certificate if specified
            if deployment_config.ssl_certificate_arn:
                cert_validation = self._validate_ssl_certificate(deployment_config.ssl_certificate_arn)
                if not cert_validation['is_valid']:
                    return self._create_certificate_failure_result(check_name, cert_validation)
            
            # Test HTTPS redirect functionality
            redirect_validation = self._test_https_redirect(lb_details)
            
            # Validate security headers (if load balancer is accessible)
            headers_validation = self._validate_security_headers(lb_details)
            
            # Compile overall results
            validation_details = {
                'load_balancer_arn': deployment_config.load_balancer_arn,
                'load_balancer_details': lb_details,
                'ssl_listener_validation': ssl_validation,
                'certificate_validation': cert_validation if deployment_config.ssl_certificate_arn else None,
                'https_redirect_validation': redirect_validation,
                'security_headers_validation': headers_validation
            }
            
            # Check if all validations passed
            all_passed = (
                ssl_validation['has_ssl_listener'] and
                ssl_validation['certificate_configured'] and
                (not deployment_config.ssl_certificate_arn or cert_validation['is_valid']) and
                redirect_validation.get('redirect_working', True) and  # Optional check
                headers_validation.get('has_security_headers', True)   # Optional check
            )
            
            if all_passed:
                return self.create_success_result(
                    check_name=check_name,
                    message="SSL configuration is properly configured with valid certificates and security settings",
                    details=validation_details
                )
            else:
                return self._create_partial_failure_result(check_name, validation_details)
            
        except Exception as e:
            self.logger.error(f"Error validating SSL configuration: {str(e)}")
            return self.create_error_result(check_name, e)
    
    def _validate_load_balancer_arn(self, lb_arn: str) -> bool:
        """Validate load balancer ARN format and existence."""
        try:
            # Check ARN format
            if not ValidationUtilities.validate_arn_format(lb_arn, 'elasticloadbalancing'):
                return False
            
            # Extract load balancer name from ARN
            arn_components = ValidationUtilities.extract_arn_components(lb_arn)
            
            # Verify load balancer exists
            elbv2_client = self.get_aws_client('elbv2')
            
            success, result, error = self.safe_aws_call(
                "describe load balancers",
                elbv2_client.describe_load_balancers,
                LoadBalancerArns=[lb_arn]
            )
            
            return success and len(result.get('LoadBalancers', [])) > 0
            
        except Exception as e:
            self.logger.error(f"Error validating load balancer ARN: {e}")
            return False
    
    def _get_load_balancer_configuration(self, lb_arn: str) -> Tuple[Optional[Dict], List[Dict]]:
        """
        Get load balancer details and listeners.
        
        Args:
            lb_arn: Load balancer ARN
            
        Returns:
            Tuple of (load_balancer_details, listeners)
        """
        try:
            elbv2_client = self.get_aws_client('elbv2')
            
            # Get load balancer details
            success, lb_result, error = self.safe_aws_call(
                "describe load balancers",
                elbv2_client.describe_load_balancers,
                LoadBalancerArns=[lb_arn]
            )
            
            if not success or not lb_result.get('LoadBalancers'):
                self.logger.error(f"Failed to get load balancer details: {error}")
                return None, []
            
            lb_details = lb_result['LoadBalancers'][0]
            
            # Get listeners
            success, listeners_result, error = self.safe_aws_call(
                "describe listeners",
                elbv2_client.describe_listeners,
                LoadBalancerArn=lb_arn
            )
            
            if not success:
                self.logger.error(f"Failed to get listeners: {error}")
                return lb_details, []
            
            listeners = listeners_result.get('Listeners', [])
            
            return lb_details, listeners
            
        except Exception as e:
            self.logger.error(f"Error getting load balancer configuration: {e}")
            return None, []
    
    def _validate_ssl_listeners(self, listeners: List[Dict], certificate_arn: Optional[str]) -> Dict[str, Any]:
        """
        Validate SSL listener configuration.
        
        Args:
            listeners: List of load balancer listeners
            certificate_arn: Expected SSL certificate ARN
            
        Returns:
            Dictionary with validation results
        """
        validation = {
            'has_ssl_listener': False,
            'has_http_listener': False,
            'certificate_configured': False,
            'https_listeners': [],
            'http_listeners': [],
            'certificate_arns': [],
            'redirect_configured': False
        }
        
        try:
            for listener in listeners:
                protocol = listener.get('Protocol', '').upper()
                port = listener.get('Port')
                
                if protocol == 'HTTPS':
                    validation['has_ssl_listener'] = True
                    validation['https_listeners'].append({
                        'port': port,
                        'protocol': protocol,
                        'listener_arn': listener.get('ListenerArn')
                    })
                    
                    # Check for certificates
                    certificates = listener.get('Certificates', [])
                    for cert in certificates:
                        cert_arn = cert.get('CertificateArn')
                        if cert_arn:
                            validation['certificate_arns'].append(cert_arn)
                            validation['certificate_configured'] = True
                
                elif protocol == 'HTTP':
                    validation['has_http_listener'] = True
                    validation['http_listeners'].append({
                        'port': port,
                        'protocol': protocol,
                        'listener_arn': listener.get('ListenerArn')
                    })
                    
                    # Check if HTTP listener has redirect actions
                    default_actions = listener.get('DefaultActions', [])
                    for action in default_actions:
                        if action.get('Type') == 'redirect':
                            redirect_config = action.get('RedirectConfig', {})
                            if redirect_config.get('Protocol') == 'HTTPS':
                                validation['redirect_configured'] = True
            
            # Validate certificate ARN matches if provided
            if certificate_arn and validation['certificate_arns']:
                validation['certificate_matches'] = certificate_arn in validation['certificate_arns']
            else:
                validation['certificate_matches'] = True  # No specific certificate required
            
        except Exception as e:
            self.logger.error(f"Error validating SSL listeners: {e}")
            validation['error'] = str(e)
        
        return validation
    
    def _validate_ssl_certificate(self, certificate_arn: str) -> Dict[str, Any]:
        """
        Validate SSL certificate validity and expiration.
        
        Args:
            certificate_arn: SSL certificate ARN
            
        Returns:
            Dictionary with certificate validation results
        """
        validation = {
            'certificate_arn': certificate_arn,
            'is_valid': False,
            'is_expired': False,
            'expires_soon': False,
            'expiration_date': None,
            'days_until_expiration': None,
            'domain_names': [],
            'status': None
        }
        
        try:
            acm_client = self.get_aws_client('acm')
            
            # Get certificate details
            success, result, error = self.safe_aws_call(
                "describe certificate",
                acm_client.describe_certificate,
                CertificateArn=certificate_arn
            )
            
            if not success:
                validation['error'] = error
                return validation
            
            cert_details = result['Certificate']
            validation['status'] = cert_details.get('Status')
            validation['domain_names'] = cert_details.get('DomainValidationOptions', [])
            
            # Check expiration
            not_after = cert_details.get('NotAfter')
            if not_after:
                validation['expiration_date'] = not_after.isoformat()
                
                # Calculate days until expiration
                now = datetime.now(timezone.utc)
                days_until_expiration = (not_after - now).days
                validation['days_until_expiration'] = days_until_expiration
                
                # Check if expired or expires soon
                validation['is_expired'] = days_until_expiration < 0
                validation['expires_soon'] = 0 <= days_until_expiration <= 30
            
            # Certificate is valid if it's issued and not expired
            validation['is_valid'] = (
                validation['status'] == 'ISSUED' and
                not validation['is_expired']
            )
            
        except Exception as e:
            self.logger.error(f"Error validating SSL certificate: {e}")
            validation['error'] = str(e)
        
        return validation
    
    def _test_https_redirect(self, lb_details: Dict[str, Any]) -> Dict[str, Any]:
        """
        Test HTTPS redirect functionality.
        
        Args:
            lb_details: Load balancer details
            
        Returns:
            Dictionary with redirect test results
        """
        validation = {
            'redirect_working': False,
            'test_attempted': False,
            'dns_name': None,
            'http_status': None,
            'redirect_location': None,
            'error': None
        }
        
        try:
            dns_name = lb_details.get('DNSName')
            if not dns_name:
                validation['error'] = "No DNS name found for load balancer"
                return validation
            
            validation['dns_name'] = dns_name
            validation['test_attempted'] = True
            
            # Test HTTP to HTTPS redirect
            http_url = f"http://{dns_name}"
            
            try:
                response = self.session.get(
                    http_url,
                    allow_redirects=False,
                    timeout=10
                )
                
                validation['http_status'] = response.status_code
                
                # Check for redirect status codes
                if response.status_code in [301, 302, 307, 308]:
                    location = response.headers.get('Location', '')
                    validation['redirect_location'] = location
                    
                    # Check if redirect is to HTTPS
                    if location.startswith('https://'):
                        validation['redirect_working'] = True
                
            except requests.exceptions.RequestException as e:
                validation['error'] = f"HTTP request failed: {str(e)}"
            
        except Exception as e:
            self.logger.error(f"Error testing HTTPS redirect: {e}")
            validation['error'] = str(e)
        
        return validation
    
    def _validate_security_headers(self, lb_details: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate security headers in HTTP responses.
        
        Args:
            lb_details: Load balancer details
            
        Returns:
            Dictionary with security headers validation results
        """
        validation = {
            'has_security_headers': False,
            'test_attempted': False,
            'dns_name': None,
            'headers_found': {},
            'missing_headers': [],
            'header_recommendations': {},
            'error': None
        }
        
        try:
            dns_name = lb_details.get('DNSName')
            if not dns_name:
                validation['error'] = "No DNS name found for load balancer"
                return validation
            
            validation['dns_name'] = dns_name
            validation['test_attempted'] = True
            
            # Test HTTPS endpoint for security headers
            https_url = f"https://{dns_name}"
            
            try:
                response = self.session.get(
                    https_url,
                    timeout=10,
                    verify=False  # Skip SSL verification for testing
                )
                
                # Check for security headers
                response_headers = response.headers
                
                for header_name, description in self.required_security_headers.items():
                    header_value = response_headers.get(header_name)
                    
                    if header_value:
                        validation['headers_found'][header_name] = {
                            'value': header_value,
                            'description': description
                        }
                        
                        # Check if value matches recommendation
                        recommended = self.recommended_header_values.get(header_name)
                        if recommended and header_value != recommended:
                            validation['header_recommendations'][header_name] = recommended
                    else:
                        validation['missing_headers'].append({
                            'name': header_name,
                            'description': description,
                            'recommended_value': self.recommended_header_values.get(header_name, 'See security documentation')
                        })
                
                # Consider headers valid if at least some critical ones are present
                critical_headers = ['Strict-Transport-Security', 'X-Content-Type-Options']
                has_critical = any(header in validation['headers_found'] for header in critical_headers)
                validation['has_security_headers'] = has_critical
                
            except requests.exceptions.RequestException as e:
                validation['error'] = f"HTTPS request failed: {str(e)}"
            
        except Exception as e:
            self.logger.error(f"Error validating security headers: {e}")
            validation['error'] = str(e)
        
        return validation
    
    def _create_ssl_listener_failure_result(self, check_name: str, 
                                          ssl_validation: Dict[str, Any]) -> ValidationResult:
        """Create failure result for missing SSL listener."""
        remediation_steps = [
            "Add an HTTPS listener to your load balancer",
            "Configure SSL certificate for the HTTPS listener",
            "Ensure the listener is on port 443 (standard HTTPS port)",
        ]
        
        if not ssl_validation['has_ssl_listener']:
            remediation_steps.extend([
                "Use AWS CLI to add HTTPS listener:",
                "aws elbv2 create-listener --load-balancer-arn <LB_ARN> --protocol HTTPS --port 443 --certificates CertificateArn=<CERT_ARN>",
            ])
        
        if ssl_validation['has_http_listener'] and not ssl_validation['redirect_configured']:
            remediation_steps.extend([
                "Configure HTTP to HTTPS redirect on existing HTTP listener",
                "Use the provided script to set up SSL configuration automatically"
            ])
        
        return self.create_failure_result(
            check_name=check_name,
            message="Load balancer does not have proper SSL/HTTPS configuration",
            remediation_steps=remediation_steps,
            fix_scripts=["scripts/add-https-ssl-support.py"],
            details=ssl_validation
        )
    
    def _create_certificate_failure_result(self, check_name: str,
                                         cert_validation: Dict[str, Any]) -> ValidationResult:
        """Create failure result for certificate issues."""
        remediation_steps = [
            f"SSL certificate {cert_validation['certificate_arn']} has issues:",
        ]
        
        if cert_validation['is_expired']:
            remediation_steps.extend([
                "Certificate has expired - renew immediately",
                "Request new certificate through AWS Certificate Manager",
                "Update load balancer listener with new certificate ARN"
            ])
        elif cert_validation['expires_soon']:
            days = cert_validation.get('days_until_expiration', 0)
            remediation_steps.extend([
                f"Certificate expires in {days} days - renew soon",
                "Set up automatic certificate renewal if using ACM"
            ])
        elif cert_validation['status'] != 'ISSUED':
            remediation_steps.extend([
                f"Certificate status is '{cert_validation['status']}' instead of 'ISSUED'",
                "Complete domain validation for the certificate",
                "Ensure certificate is properly issued before deployment"
            ])
        
        return self.create_failure_result(
            check_name=check_name,
            message=f"SSL certificate validation failed: {cert_validation.get('error', 'Certificate issues detected')}",
            remediation_steps=remediation_steps,
            fix_scripts=["scripts/add-https-ssl-support.py"],
            details=cert_validation
        )
    
    def _create_partial_failure_result(self, check_name: str,
                                     validation_details: Dict[str, Any]) -> ValidationResult:
        """Create result for partial SSL configuration issues."""
        issues = []
        remediation_steps = []
        
        ssl_val = validation_details.get('ssl_listener_validation', {})
        cert_val = validation_details.get('certificate_validation', {})
        redirect_val = validation_details.get('https_redirect_validation', {})
        headers_val = validation_details.get('security_headers_validation', {})
        
        if not ssl_val.get('has_ssl_listener'):
            issues.append("Missing HTTPS listener")
            remediation_steps.append("Add HTTPS listener to load balancer")
        
        if not ssl_val.get('certificate_configured'):
            issues.append("No SSL certificate configured")
            remediation_steps.append("Configure SSL certificate on HTTPS listener")
        
        if cert_val and not cert_val.get('is_valid'):
            issues.append("Invalid SSL certificate")
            remediation_steps.append("Fix SSL certificate issues")
        
        if redirect_val and not redirect_val.get('redirect_working'):
            issues.append("HTTP to HTTPS redirect not working")
            remediation_steps.append("Configure HTTP to HTTPS redirect")
        
        if headers_val and not headers_val.get('has_security_headers'):
            missing_headers = headers_val.get('missing_headers', [])
            if missing_headers:
                issues.append(f"Missing security headers: {', '.join([h['name'] for h in missing_headers])}")
                remediation_steps.append("Configure security headers in application or load balancer")
        
        remediation_steps.append("Use the provided SSL setup script to fix configuration issues")
        
        return self.create_failure_result(
            check_name=check_name,
            message=f"SSL configuration has issues: {'; '.join(issues)}",
            remediation_steps=remediation_steps,
            fix_scripts=["scripts/add-https-ssl-support.py"],
            details=validation_details
        )
    
    def validate_load_balancer_ssl(self, lb_arn: str) -> ValidationResult:
        """
        Public method to validate SSL configuration for a specific load balancer.
        
        Args:
            lb_arn: Load balancer ARN to validate
            
        Returns:
            ValidationResult with validation status
        """
        deployment_config = DeploymentConfig(
            task_definition_arn="arn:aws:ecs:us-east-1:123456789012:task-definition/test:1",
            iam_role_arn="arn:aws:iam::123456789012:role/test-role",
            load_balancer_arn=lb_arn,
            target_environment="validation"
        )
        
        return self.validate(deployment_config)
    
    def check_certificate_validity(self, certificate_arn: str) -> bool:
        """
        Check if SSL certificate is valid and not expired.
        
        Args:
            certificate_arn: SSL certificate ARN
            
        Returns:
            True if certificate is valid, False otherwise
        """
        try:
            cert_validation = self._validate_ssl_certificate(certificate_arn)
            return cert_validation.get('is_valid', False)
        except Exception as e:
            self.logger.error(f"Error checking certificate validity: {e}")
            return False
    
    def validate_security_headers(self, endpoint_url: str) -> ValidationResult:
        """
        Validate security headers for a specific endpoint.
        
        Args:
            endpoint_url: URL to test for security headers
            
        Returns:
            ValidationResult with header validation status
        """
        check_name = "Security Headers Validation"
        
        try:
            parsed_url = urlparse(endpoint_url)
            lb_details = {'DNSName': parsed_url.netloc}
            
            headers_validation = self._validate_security_headers(lb_details)
            
            if headers_validation.get('has_security_headers'):
                return self.create_success_result(
                    check_name=check_name,
                    message="Security headers are properly configured",
                    details=headers_validation
                )
            else:
                missing_headers = headers_validation.get('missing_headers', [])
                remediation_steps = [
                    "Configure the following security headers:",
                ]
                
                for header in missing_headers:
                    remediation_steps.append(f"  - {header['name']}: {header['recommended_value']}")
                
                return self.create_failure_result(
                    check_name=check_name,
                    message=f"Missing security headers: {', '.join([h['name'] for h in missing_headers])}",
                    remediation_steps=remediation_steps,
                    details=headers_validation
                )
        
        except Exception as e:
            return self.create_error_result(check_name, e)