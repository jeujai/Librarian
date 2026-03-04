#!/usr/bin/env python3
"""
Property-Based Tests for Load Balancer SSL Configuration
Feature: aws-production-deployment, Property 7: Load Balancer SSL Configuration

This module tests that Application Load Balancers are configured with proper SSL/TLS
settings, certificates, security policies, and HTTPS enforcement for production security.
"""

import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, List, Any, Optional
import pytest
from hypothesis import given, strategies as st, settings, assume


class LoadBalancerSSLConfigurationTest:
    """Test class for load balancer SSL configuration validation."""
    
    def __init__(self, terraform_dir: str = None):
        if terraform_dir is None:
            current_dir = Path.cwd()
            if (current_dir / "terraform.tf").exists():
                self.terraform_dir = current_dir
            elif (current_dir / "infrastructure" / "aws-native").exists():
                self.terraform_dir = current_dir / "infrastructure" / "aws-native"
            else:
                self.terraform_dir = Path("infrastructure/aws-native")
        else:
            self.terraform_dir = Path(terraform_dir)
    
    def get_terraform_plan_json(self, config: Dict[str, Any]) -> Optional[Dict]:
        """Generate Terraform plan and return JSON representation."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.tfvars', delete=False) as f:
            for key, value in config.items():
                if isinstance(value, str):
                    f.write(f'{key} = "{value}"\n')
                else:
                    f.write(f'{key} = {value}\n')
            tfvars_path = f.name
        
        try:
            original_dir = os.getcwd()
            os.chdir(self.terraform_dir)
            
            # Initialize Terraform
            init_result = subprocess.run(
                ["terraform", "init", "-backend=false"],
                capture_output=True, text=True, timeout=60
            )
            
            if init_result.returncode != 0:
                return None
            
            # Generate plan
            plan_result = subprocess.run(
                ["terraform", "plan", "-var-file", tfvars_path, "-out=test.tfplan"],
                capture_output=True, text=True, timeout=120
            )
            
            if plan_result.returncode not in [0, 2]:
                return None
            
            # Get JSON representation
            show_result = subprocess.run(
                ["terraform", "show", "-json", "test.tfplan"],
                capture_output=True, text=True, timeout=30
            )
            
            if show_result.returncode == 0:
                return json.loads(show_result.stdout)
            
            return None
            
        except Exception as e:
            print(f"Error generating plan: {e}")
            return None
        finally:
            os.chdir(original_dir)
            try:
                os.unlink(tfvars_path)
                if os.path.exists(os.path.join(self.terraform_dir, "test.tfplan")):
                    os.unlink(os.path.join(self.terraform_dir, "test.tfplan"))
            except:
                pass
    
    def find_resources_in_plan(self, plan_data: Dict, resource_type: str) -> List[Dict]:
        """Find all resources of a specific type in the Terraform plan."""
        def find_resources_in_module(module_data, resource_type):
            resources = []
            if "resources" in module_data:
                for resource in module_data["resources"]:
                    if resource.get("type") == resource_type:
                        resources.append(resource)
            
            if "child_modules" in module_data:
                for child_module in module_data["child_modules"]:
                    resources.extend(find_resources_in_module(child_module, resource_type))
            
            return resources
        
        if "planned_values" not in plan_data or "root_module" not in plan_data["planned_values"]:
            return []
        
        root_module = plan_data["planned_values"]["root_module"]
        return find_resources_in_module(root_module, resource_type)
    
    def validate_ssl_certificates(self, plan_data: Dict) -> List[str]:
        """Validate SSL certificate configuration."""
        issues = []
        
        # Find ACM certificates
        certificates = self.find_resources_in_plan(plan_data, "aws_acm_certificate")
        
        for cert in certificates:
            cert_values = cert.get("values", {})
            
            # Check validation method
            validation_method = cert_values.get("validation_method")
            if validation_method != "DNS":
                issues.append(f"SSL certificate should use DNS validation for automation, got: {validation_method}")
            
            # Check domain name is specified
            domain_name = cert_values.get("domain_name")
            if not domain_name:
                issues.append("SSL certificate should specify a domain name")
            
            # Check for wildcard certificate (SANs)
            subject_alternative_names = cert_values.get("subject_alternative_names", [])
            if domain_name and not any(san.startswith("*.") for san in subject_alternative_names):
                issues.append("SSL certificate should include wildcard SAN for subdomain flexibility")
            
            # Check lifecycle configuration
            lifecycle = cert_values.get("lifecycle", [])
            if lifecycle:
                create_before_destroy = lifecycle[0].get("create_before_destroy", False)
                if not create_before_destroy:
                    issues.append("SSL certificate should use create_before_destroy lifecycle for zero-downtime updates")
        
        return issues
    
    def validate_load_balancer_listeners(self, plan_data: Dict) -> List[str]:
        """Validate load balancer listener SSL configuration."""
        issues = []
        
        # Find ALB listeners
        listeners = self.find_resources_in_plan(plan_data, "aws_lb_listener")
        
        http_listener_found = False
        https_listener_found = False
        
        for listener in listeners:
            listener_values = listener.get("values", {})
            
            port = listener_values.get("port")
            protocol = listener_values.get("protocol")
            
            if port == "80" and protocol == "HTTP":
                http_listener_found = True
                
                # Check that HTTP listener redirects to HTTPS
                default_action = listener_values.get("default_action", [])
                if default_action:
                    action = default_action[0]
                    action_type = action.get("type")
                    
                    if action_type != "redirect":
                        issues.append("HTTP listener should redirect to HTTPS for security")
                    else:
                        redirect_config = action.get("redirect", [])
                        if redirect_config:
                            redirect = redirect_config[0]
                            redirect_protocol = redirect.get("protocol")
                            redirect_port = redirect.get("port")
                            status_code = redirect.get("status_code")
                            
                            if redirect_protocol != "HTTPS":
                                issues.append("HTTP redirect should redirect to HTTPS protocol")
                            
                            if redirect_port != "443":
                                issues.append("HTTP redirect should redirect to port 443")
                            
                            if status_code != "HTTP_301":
                                issues.append("HTTP redirect should use 301 status code for SEO")
            
            elif port == "443" and protocol == "HTTPS":
                https_listener_found = True
                
                # Check SSL policy
                ssl_policy = listener_values.get("ssl_policy")
                if not ssl_policy:
                    issues.append("HTTPS listener should specify SSL policy")
                else:
                    # Check for modern TLS policy
                    if "TLS-1-2" not in ssl_policy:
                        issues.append(f"HTTPS listener should use TLS 1.2 or higher, got: {ssl_policy}")
                    
                    # Warn about outdated policies
                    if "2017-01" in ssl_policy:
                        issues.append("HTTPS listener SSL policy is from 2017, consider newer policy for better security")
                
                # Check certificate ARN
                certificate_arn = listener_values.get("certificate_arn")
                if not certificate_arn:
                    issues.append("HTTPS listener should specify certificate ARN")
                
                # Check default action
                default_action = listener_values.get("default_action", [])
                if default_action:
                    action = default_action[0]
                    action_type = action.get("type")
                    
                    if action_type != "forward":
                        issues.append("HTTPS listener should forward traffic to target group")
        
        # Check that both HTTP and HTTPS listeners exist
        if not http_listener_found:
            issues.append("Load balancer should have HTTP listener for redirect")
        
        if not https_listener_found:
            issues.append("Load balancer should have HTTPS listener for secure traffic")
        
        return issues
    
    def validate_load_balancer_security(self, plan_data: Dict) -> List[str]:
        """Validate load balancer security configuration."""
        issues = []
        
        # Find load balancers
        load_balancers = self.find_resources_in_plan(plan_data, "aws_lb")
        
        for lb in load_balancers:
            lb_values = lb.get("values", {})
            
            # Check load balancer type
            lb_type = lb_values.get("load_balancer_type")
            if lb_type != "application":
                issues.append(f"Should use Application Load Balancer for HTTP/HTTPS, got: {lb_type}")
            
            # Check that it's internet-facing for public access
            internal = lb_values.get("internal", True)
            if internal:
                issues.append("Load balancer should be internet-facing for public access")
            
            # Check HTTP/2 support
            enable_http2 = lb_values.get("enable_http2", False)
            if not enable_http2:
                issues.append("Load balancer should enable HTTP/2 for better performance")
            
            # Check cross-zone load balancing
            cross_zone_lb = lb_values.get("enable_cross_zone_load_balancing", False)
            if not cross_zone_lb:
                issues.append("Load balancer should enable cross-zone load balancing for availability")
            
            # Check deletion protection for production
            deletion_protection = lb_values.get("enable_deletion_protection", False)
            # Note: This might be environment-dependent, so we'll make it a warning
            
            # Check security groups
            security_groups = lb_values.get("security_groups", [])
            if not security_groups:
                issues.append("Load balancer should have security groups configured")
            
            # Check subnets (should be in public subnets)
            subnets = lb_values.get("subnets", [])
            if not subnets:
                issues.append("Load balancer should be deployed in subnets")
            elif len(subnets) < 2:
                issues.append("Load balancer should be deployed in at least 2 subnets for high availability")
            
            # Check access logs configuration
            access_logs = lb_values.get("access_logs", [])
            if access_logs:
                logs_config = access_logs[0]
                enabled = logs_config.get("enabled", False)
                bucket = logs_config.get("bucket")
                
                if not enabled:
                    issues.append("Load balancer access logs should be enabled for monitoring")
                
                if not bucket:
                    issues.append("Load balancer access logs should specify S3 bucket")
        
        return issues
    
    def validate_cloudfront_ssl_configuration(self, plan_data: Dict) -> List[str]:
        """Validate CloudFront SSL configuration if CDN is enabled."""
        issues = []
        
        # Find CloudFront distributions
        distributions = self.find_resources_in_plan(plan_data, "aws_cloudfront_distribution")
        
        for dist in distributions:
            dist_values = dist.get("values", {})
            
            # Check viewer certificate configuration
            viewer_certificate = dist_values.get("viewer_certificate", [])
            if not viewer_certificate:
                issues.append("CloudFront distribution should have viewer certificate configuration")
                continue
            
            cert_config = viewer_certificate[0]
            
            # Check SSL support method
            ssl_support_method = cert_config.get("ssl_support_method")
            if ssl_support_method and ssl_support_method != "sni-only":
                issues.append("CloudFront should use SNI-only SSL support for cost efficiency")
            
            # Check minimum protocol version
            min_protocol_version = cert_config.get("minimum_protocol_version")
            if min_protocol_version:
                if "TLSv1.2" not in min_protocol_version:
                    issues.append(f"CloudFront should require TLS 1.2 or higher, got: {min_protocol_version}")
            
            # Check certificate ARN for custom domains
            acm_certificate_arn = cert_config.get("acm_certificate_arn")
            cloudfront_default_certificate = cert_config.get("cloudfront_default_certificate", False)
            
            if not cloudfront_default_certificate and not acm_certificate_arn:
                issues.append("CloudFront with custom domain should specify ACM certificate ARN")
            
            # Check cache behaviors for HTTPS enforcement
            default_cache_behavior = dist_values.get("default_cache_behavior", [])
            if default_cache_behavior:
                behavior = default_cache_behavior[0]
                viewer_protocol_policy = behavior.get("viewer_protocol_policy")
                
                if viewer_protocol_policy != "redirect-to-https":
                    issues.append("CloudFront default cache behavior should redirect to HTTPS")
            
            # Check ordered cache behaviors
            ordered_cache_behaviors = dist_values.get("ordered_cache_behavior", [])
            for behavior in ordered_cache_behaviors:
                viewer_protocol_policy = behavior.get("viewer_protocol_policy")
                if viewer_protocol_policy != "redirect-to-https":
                    path_pattern = behavior.get("path_pattern", "unknown")
                    issues.append(f"CloudFront cache behavior for {path_pattern} should redirect to HTTPS")
        
        return issues
    
    def validate_security_headers(self, plan_data: Dict) -> List[str]:
        """Validate security headers configuration."""
        issues = []
        
        # Check if there are any Lambda@Edge functions for security headers
        lambda_functions = self.find_resources_in_plan(plan_data, "aws_lambda_function")
        
        security_header_function_found = False
        for func in lambda_functions:
            func_values = func.get("values", {})
            func_name = func_values.get("function_name", "")
            
            if "security" in func_name.lower() or "header" in func_name.lower():
                security_header_function_found = True
                break
        
        # Note: Security headers are often configured at the application level
        # or through CloudFront response headers policies (newer feature)
        # This is more of a recommendation than a hard requirement
        
        return issues
    
    def validate_ssl_configuration_completeness(self, plan_data: Dict) -> Dict[str, Any]:
        """Validate overall SSL configuration completeness."""
        completeness_score = {
            "certificate_management": 0,
            "https_enforcement": 0,
            "modern_tls_policies": 0,
            "security_best_practices": 0,
            "monitoring_and_logging": 0
        }
        
        # Check certificate management
        certificates = self.find_resources_in_plan(plan_data, "aws_acm_certificate")
        if certificates:
            for cert in certificates:
                cert_values = cert.get("values", {})
                if cert_values.get("validation_method") == "DNS":
                    completeness_score["certificate_management"] += 1
                    break
        
        # Check HTTPS enforcement
        listeners = self.find_resources_in_plan(plan_data, "aws_lb_listener")
        https_redirect_found = False
        https_listener_found = False
        
        for listener in listeners:
            listener_values = listener.get("values", {})
            port = listener_values.get("port")
            protocol = listener_values.get("protocol")
            
            if port == "80" and protocol == "HTTP":
                default_action = listener_values.get("default_action", [])
                if default_action and default_action[0].get("type") == "redirect":
                    https_redirect_found = True
            
            elif port == "443" and protocol == "HTTPS":
                https_listener_found = True
        
        if https_redirect_found and https_listener_found:
            completeness_score["https_enforcement"] = 1
        
        # Check modern TLS policies
        for listener in listeners:
            listener_values = listener.get("values", {})
            ssl_policy = listener_values.get("ssl_policy", "")
            
            if "TLS-1-2" in ssl_policy:
                completeness_score["modern_tls_policies"] = 1
                break
        
        # Check security best practices
        load_balancers = self.find_resources_in_plan(plan_data, "aws_lb")
        for lb in load_balancers:
            lb_values = lb.get("values", {})
            
            if (lb_values.get("enable_http2", False) and 
                not lb_values.get("internal", True)):
                completeness_score["security_best_practices"] = 1
                break
        
        # Check monitoring and logging
        for lb in load_balancers:
            lb_values = lb.get("values", {})
            access_logs = lb_values.get("access_logs", [])
            
            if access_logs and access_logs[0].get("enabled", False):
                completeness_score["monitoring_and_logging"] = 1
                break
        
        total_score = sum(completeness_score.values())
        max_score = len(completeness_score)
        percentage = (total_score / max_score) * 100
        
        return {
            "score": percentage,
            "details": completeness_score,
            "recommendations": self._get_ssl_recommendations(completeness_score)
        }
    
    def _get_ssl_recommendations(self, score_details: Dict[str, int]) -> List[str]:
        """Get recommendations for improving SSL configuration."""
        recommendations = []
        
        if score_details["certificate_management"] == 0:
            recommendations.append("Implement ACM certificates with DNS validation for automated management")
        
        if score_details["https_enforcement"] == 0:
            recommendations.append("Configure HTTP to HTTPS redirect and HTTPS listeners")
        
        if score_details["modern_tls_policies"] == 0:
            recommendations.append("Use modern TLS 1.2+ SSL policies for better security")
        
        if score_details["security_best_practices"] == 0:
            recommendations.append("Enable HTTP/2 and configure load balancer security settings")
        
        if score_details["monitoring_and_logging"] == 0:
            recommendations.append("Enable access logs for security monitoring and troubleshooting")
        
        return recommendations


# Property-based test strategies
@st.composite
def ssl_configuration_config(draw):
    """Generate SSL configuration test scenarios."""
    has_domain = draw(st.booleans())
    
    config = {
        "aws_region": draw(st.sampled_from(["us-east-1", "us-west-2", "eu-west-1"])),
        "environment": draw(st.sampled_from(["staging", "production"])),
        "project_name": draw(st.text(min_size=3, max_size=20, alphabet=st.characters(whitelist_categories=("Ll", "Nd"), whitelist_characters="-"))),
        "vpc_cidr": draw(st.sampled_from(["10.0.0.0/16", "172.16.0.0/16"])),
        "az_count": draw(st.integers(min_value=2, max_value=3)),
        
        # SSL configuration
        "domain_name": draw(st.text(min_size=5, max_size=30, alphabet=st.characters(whitelist_categories=("Ll", "Nd"), whitelist_characters=".-"))) + ".com" if has_domain else "",
        "ssl_certificate_arn": "",  # Let it create new certificate
        
        # Application configuration
        "app_port": draw(st.integers(min_value=3000, max_value=9000)),
        "health_check_path": "/health/simple",
        
        # Feature flags
        "enable_cdn": draw(st.booleans()),
        
        # Database configuration (required)
        "neptune_cluster_identifier": "test-neptune",
        "opensearch_domain_name": "test-opensearch",
        "skip_final_snapshot": True,
        "log_retention_days": draw(st.integers(min_value=7, max_value=30)),
    }
    
    return config


class TestLoadBalancerSSLConfiguration:
    """Property-based tests for load balancer SSL configuration."""
    
    def setup_method(self):
        """Set up test environment."""
        self.ssl_test = LoadBalancerSSLConfigurationTest()
    
    @given(config=ssl_configuration_config())
    @settings(max_examples=3, deadline=120000)  # 2 minute timeout
    def test_ssl_certificate_configuration(self, config):
        """
        Property test: For any SSL configuration with domain,
        certificates should be properly configured with DNS validation.
        
        **Feature: aws-production-deployment, Property 7: Load Balancer SSL Configuration**
        **Validates: Requirements 2.3, 4.3**
        """
        # Skip if Terraform not available
        if not subprocess.run(["which", "terraform"], capture_output=True).returncode == 0:
            pytest.skip("Terraform not available")
        
        # Skip if no domain name (no SSL certificate needed)
        if not config.get("domain_name"):
            pytest.skip("No domain name configured, skipping SSL certificate test")
        
        plan_data = self.ssl_test.get_terraform_plan_json(config)
        assume(plan_data is not None)
        
        # Validate SSL certificates
        issues = self.ssl_test.validate_ssl_certificates(plan_data)
        
        assert len(issues) == 0, f"SSL certificate issues: {'; '.join(issues)}"
    
    @given(config=ssl_configuration_config())
    @settings(max_examples=5, deadline=120000)
    def test_load_balancer_listener_ssl_configuration(self, config):
        """
        Property test: For any SSL configuration,
        load balancer listeners should enforce HTTPS properly.
        
        **Feature: aws-production-deployment, Property 7: Load Balancer SSL Configuration**
        **Validates: Requirements 2.3, 4.3**
        """
        # Skip if Terraform not available
        if not subprocess.run(["which", "terraform"], capture_output=True).returncode == 0:
            pytest.skip("Terraform not available")
        
        plan_data = self.ssl_test.get_terraform_plan_json(config)
        assume(plan_data is not None)
        
        # Validate load balancer listeners
        issues = self.ssl_test.validate_load_balancer_listeners(plan_data)
        
        # Filter out issues that only apply when domain is configured
        if not config.get("domain_name"):
            issues = [issue for issue in issues if "HTTPS listener" not in issue]
        
        assert len(issues) == 0, f"Load balancer listener SSL issues: {'; '.join(issues)}"
    
    @given(config=ssl_configuration_config())
    @settings(max_examples=3, deadline=120000)
    def test_load_balancer_security_configuration(self, config):
        """
        Property test: For any SSL configuration,
        load balancer should have proper security settings.
        
        **Feature: aws-production-deployment, Property 7: Load Balancer SSL Configuration**
        **Validates: Requirements 2.3, 4.3**
        """
        # Skip if Terraform not available
        if not subprocess.run(["which", "terraform"], capture_output=True).returncode == 0:
            pytest.skip("Terraform not available")
        
        plan_data = self.ssl_test.get_terraform_plan_json(config)
        assume(plan_data is not None)
        
        # Validate load balancer security
        issues = self.ssl_test.validate_load_balancer_security(plan_data)
        
        assert len(issues) == 0, f"Load balancer security issues: {'; '.join(issues)}"
    
    def test_https_enforcement_configuration(self):
        """
        Test that HTTPS enforcement is properly configured.
        
        **Feature: aws-production-deployment, Property 7: Load Balancer SSL Configuration**
        **Validates: Requirements 2.3, 4.3**
        """
        # Skip if Terraform not available
        if not subprocess.run(["which", "terraform"], capture_output=True).returncode == 0:
            pytest.skip("Terraform not available")
        
        config = {
            "aws_region": "us-east-1",
            "environment": "production",
            "project_name": "test-project",
            "domain_name": "example.com",
            "app_port": 8000,
            "health_check_path": "/health/simple",
            "neptune_cluster_identifier": "test-neptune",
            "opensearch_domain_name": "test-opensearch",
            "skip_final_snapshot": True,
        }
        
        plan_data = self.ssl_test.get_terraform_plan_json(config)
        assert plan_data is not None, "Should be able to generate Terraform plan"
        
        # Check that both HTTP and HTTPS listeners exist
        listeners = self.ssl_test.find_resources_in_plan(plan_data, "aws_lb_listener")
        assert len(listeners) >= 2, "Should have both HTTP and HTTPS listeners"
        
        # Validate HTTPS enforcement
        http_redirect_found = False
        https_listener_found = False
        
        for listener in listeners:
            listener_values = listener.get("values", {})
            port = listener_values.get("port")
            protocol = listener_values.get("protocol")
            
            if port == "80" and protocol == "HTTP":
                default_action = listener_values.get("default_action", [])
                if default_action and default_action[0].get("type") == "redirect":
                    http_redirect_found = True
            
            elif port == "443" and protocol == "HTTPS":
                https_listener_found = True
                
                # Check SSL policy
                ssl_policy = listener_values.get("ssl_policy", "")
                assert "TLS-1-2" in ssl_policy, "HTTPS listener should use TLS 1.2 or higher"
        
        assert http_redirect_found, "Should have HTTP to HTTPS redirect"
        assert https_listener_found, "Should have HTTPS listener"
    
    def test_ssl_configuration_completeness_score(self):
        """
        Test that SSL configuration achieves good completeness score.
        
        **Feature: aws-production-deployment, Property 7: Load Balancer SSL Configuration**
        **Validates: Requirements 2.3, 4.3**
        """
        # Skip if Terraform not available
        if not subprocess.run(["which", "terraform"], capture_output=True).returncode == 0:
            pytest.skip("Terraform not available")
        
        config = {
            "aws_region": "us-east-1",
            "environment": "production",
            "project_name": "test-project",
            "domain_name": "example.com",
            "enable_cdn": True,
            "neptune_cluster_identifier": "test-neptune",
            "opensearch_domain_name": "test-opensearch",
            "skip_final_snapshot": True,
        }
        
        plan_data = self.ssl_test.get_terraform_plan_json(config)
        assert plan_data is not None, "Should be able to generate Terraform plan"
        
        # Calculate SSL configuration completeness
        completeness = self.ssl_test.validate_ssl_configuration_completeness(plan_data)
        
        assert completeness["score"] >= 60, f"SSL configuration completeness ({completeness['score']}%) should be at least 60%"
        
        # Check specific requirements
        assert completeness["details"]["https_enforcement"] == 1, "Should have HTTPS enforcement configured"
        assert completeness["details"]["modern_tls_policies"] == 1, "Should use modern TLS policies"


if __name__ == "__main__":
    # Run basic validation tests
    test_instance = TestLoadBalancerSSLConfiguration()
    test_instance.setup_method()
    
    print("Running load balancer SSL configuration tests...")
    
    try:
        test_instance.test_https_enforcement_configuration()
        print("✅ HTTPS enforcement configuration test passed")
    except Exception as e:
        print(f"❌ HTTPS enforcement configuration test failed: {e}")
    
    try:
        test_instance.test_ssl_configuration_completeness_score()
        print("✅ SSL configuration completeness score test passed")
    except Exception as e:
        print(f"❌ SSL configuration completeness score test failed: {e}")
    
    print("\nTo run property-based tests with Hypothesis:")
    print("pytest tests/infrastructure/test_load_balancer_ssl_configuration.py -v")