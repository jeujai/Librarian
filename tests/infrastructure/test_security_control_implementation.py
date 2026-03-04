#!/usr/bin/env python3
"""
Property-Based Tests for Security Control Implementation
Feature: aws-production-deployment, Property 11: Security Control Implementation

This module tests that comprehensive security controls are implemented including
WAF, GuardDuty, Security Hub, AWS Config, and network security controls.
"""

import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, List, Any, Optional
import pytest
from hypothesis import given, strategies as st, settings, assume


class SecurityControlImplementationTest:
    """Test class for security control implementation validation."""
    
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
    
    def validate_waf_configuration(self, plan_data: Dict) -> List[str]:
        """Validate WAF configuration."""
        issues = []
        
        # Find WAF Web ACLs
        web_acls = self.find_resources_in_plan(plan_data, "aws_wafv2_web_acl")
        
        if not web_acls:
            issues.append("No WAF Web ACL found - web application firewall missing")
            return issues
        
        for web_acl in web_acls:
            web_acl_values = web_acl.get("values", {})
            
            # Check scope
            scope = web_acl_values.get("scope")
            if scope != "REGIONAL":
                issues.append(f"WAF Web ACL scope should be REGIONAL for ALB, got: {scope}")
            
            # Check default action
            default_action = web_acl_values.get("default_action", [])
            if not default_action:
                issues.append("WAF Web ACL should have default action configured")
            else:
                action = default_action[0]
                if "allow" not in action:
                    issues.append("WAF Web ACL default action should allow traffic (with rules for blocking)")
            
            # Check rules
            rules = web_acl_values.get("rule", [])
            if not rules:
                issues.append("WAF Web ACL should have security rules configured")
                continue
            
            # Expected rule types
            expected_rules = {
                "rate_limit": False,
                "common_rules": False,
                "known_bad_inputs": False,
                "sqli_rules": False,
                "ip_reputation": False
            }
            
            for rule in rules:
                rule_name = rule.get("name", "").lower()
                
                # Check rate limiting
                if "rate" in rule_name:
                    expected_rules["rate_limit"] = True
                    
                    # Validate rate limiting configuration
                    statement = rule.get("statement", [])
                    if statement:
                        rate_statement = statement[0].get("rate_based_statement", [])
                        if rate_statement:
                            limit = rate_statement[0].get("limit")
                            if not limit or limit < 100:
                                issues.append("WAF rate limit should be at least 100 requests per 5 minutes")
                            elif limit > 20000:
                                issues.append("WAF rate limit seems too high, may not be effective")
                
                # Check managed rule groups
                if "common" in rule_name:
                    expected_rules["common_rules"] = True
                elif "badinputs" in rule_name or "knownbad" in rule_name:
                    expected_rules["known_bad_inputs"] = True
                elif "sqli" in rule_name:
                    expected_rules["sqli_rules"] = True
                elif "reputation" in rule_name:
                    expected_rules["ip_reputation"] = True
                
                # Check visibility configuration
                visibility_config = rule.get("visibility_config", [])
                if not visibility_config:
                    issues.append(f"WAF rule {rule_name} should have visibility configuration")
                else:
                    vis_config = visibility_config[0]
                    if not vis_config.get("cloudwatch_metrics_enabled", False):
                        issues.append(f"WAF rule {rule_name} should enable CloudWatch metrics")
            
            # Check for missing rule types
            for rule_type, found in expected_rules.items():
                if not found:
                    issues.append(f"WAF should include {rule_type.replace('_', ' ')} rules")
        
        # Check WAF association with ALB
        waf_associations = self.find_resources_in_plan(plan_data, "aws_wafv2_web_acl_association")
        if not waf_associations:
            issues.append("WAF Web ACL should be associated with Application Load Balancer")
        
        # Check WAF logging
        waf_logging = self.find_resources_in_plan(plan_data, "aws_wafv2_web_acl_logging_configuration")
        if not waf_logging:
            issues.append("WAF should have logging configuration for security monitoring")
        
        return issues
    
    def validate_threat_detection_services(self, plan_data: Dict, config: Dict[str, Any]) -> List[str]:
        """Validate threat detection services configuration."""
        issues = []
        
        # Check GuardDuty
        if config.get("enable_guardduty", True):
            guardduty_detectors = self.find_resources_in_plan(plan_data, "aws_guardduty_detector")
            
            if not guardduty_detectors:
                issues.append("GuardDuty detector should be enabled for threat detection")
            else:
                for detector in guardduty_detectors:
                    detector_values = detector.get("values", {})
                    
                    if not detector_values.get("enable", False):
                        issues.append("GuardDuty detector should be enabled")
                    
                    # Check data sources
                    datasources = detector_values.get("datasources", [])
                    if datasources:
                        ds = datasources[0]
                        
                        # Check S3 logs
                        s3_logs = ds.get("s3_logs", [])
                        if s3_logs and not s3_logs[0].get("enable", False):
                            issues.append("GuardDuty should enable S3 logs monitoring")
                        
                        # Check malware protection
                        malware_protection = ds.get("malware_protection", [])
                        if malware_protection:
                            scan_config = malware_protection[0].get("scan_ec2_instance_with_findings", [])
                            if scan_config:
                                ebs_volumes = scan_config[0].get("ebs_volumes", [])
                                if ebs_volumes and not ebs_volumes[0].get("enable", False):
                                    issues.append("GuardDuty should enable EBS volume malware scanning")
        
        # Check Security Hub
        if config.get("enable_security_hub", True):
            security_hub_accounts = self.find_resources_in_plan(plan_data, "aws_securityhub_account")
            
            if not security_hub_accounts:
                issues.append("Security Hub should be enabled for centralized security findings")
        
        # Check Inspector
        if config.get("enable_inspector", True):
            inspector_enablers = self.find_resources_in_plan(plan_data, "aws_inspector2_enabler")
            
            if not inspector_enablers:
                issues.append("Inspector should be enabled for vulnerability assessment")
            else:
                for enabler in inspector_enablers:
                    enabler_values = enabler.get("values", {})
                    resource_types = enabler_values.get("resource_types", [])
                    
                    if "ECR" not in resource_types:
                        issues.append("Inspector should scan ECR repositories for vulnerabilities")
                    
                    if "EC2" not in resource_types:
                        issues.append("Inspector should scan EC2 instances for vulnerabilities")
        
        return issues
    
    def validate_compliance_monitoring(self, plan_data: Dict, config: Dict[str, Any]) -> List[str]:
        """Validate compliance monitoring configuration."""
        issues = []
        
        if not config.get("enable_config", True):
            return issues
        
        # Check AWS Config
        config_recorders = self.find_resources_in_plan(plan_data, "aws_config_configuration_recorder")
        
        if not config_recorders:
            issues.append("AWS Config should be enabled for compliance monitoring")
            return issues
        
        for recorder in config_recorders:
            recorder_values = recorder.get("values", {})
            
            # Check recording group
            recording_group = recorder_values.get("recording_group", [])
            if recording_group:
                group = recording_group[0]
                
                if not group.get("all_supported", False):
                    issues.append("AWS Config should record all supported resources")
                
                if not group.get("include_global_resource_types", False):
                    issues.append("AWS Config should include global resource types")
        
        # Check Config delivery channel
        delivery_channels = self.find_resources_in_plan(plan_data, "aws_config_delivery_channel")
        
        if not delivery_channels:
            issues.append("AWS Config should have delivery channel configured")
        else:
            for channel in delivery_channels:
                channel_values = channel.get("values", {})
                
                if not channel_values.get("s3_bucket_name"):
                    issues.append("AWS Config delivery channel should specify S3 bucket")
                
                # Check snapshot delivery
                snapshot_props = channel_values.get("snapshot_delivery_properties", [])
                if snapshot_props:
                    delivery_freq = snapshot_props[0].get("delivery_frequency")
                    if delivery_freq not in ["Daily", "TwentyFour_Hours"]:
                        issues.append("AWS Config should deliver snapshots at least daily")
        
        return issues
    
    def validate_network_security_controls(self, plan_data: Dict) -> List[str]:
        """Validate network security controls."""
        issues = []
        
        # Check Network ACLs
        network_acls = self.find_resources_in_plan(plan_data, "aws_network_acl")
        
        if not network_acls:
            issues.append("Network ACLs should be configured for additional network security")
            return issues
        
        private_nacl_found = False
        database_nacl_found = False
        
        for nacl in network_acls:
            nacl_values = nacl.get("values", {})
            
            # Check subnet associations
            subnet_ids = nacl_values.get("subnet_ids", [])
            if not subnet_ids:
                issues.append("Network ACL should be associated with subnets")
                continue
            
            # Determine NACL type based on name or subnets
            # This is a simplified check - in practice you'd check subnet types
            if len(subnet_ids) > 0:
                if "private" in str(nacl_values):
                    private_nacl_found = True
                elif "database" in str(nacl_values):
                    database_nacl_found = True
            
            # Check ingress rules
            ingress_rules = nacl_values.get("ingress", [])
            if not ingress_rules:
                issues.append("Network ACL should have ingress rules configured")
            
            # Check egress rules
            egress_rules = nacl_values.get("egress", [])
            if not egress_rules:
                issues.append("Network ACL should have egress rules configured")
        
        if not private_nacl_found:
            issues.append("Should have Network ACL for private subnets")
        
        if not database_nacl_found:
            issues.append("Should have Network ACL for database subnets")
        
        # Check VPC Flow Logs
        flow_logs = self.find_resources_in_plan(plan_data, "aws_flow_log")
        
        if not flow_logs:
            issues.append("VPC Flow Logs should be enabled for network monitoring")
        else:
            for flow_log in flow_logs:
                flow_log_values = flow_log.get("values", {})
                
                traffic_type = flow_log_values.get("traffic_type")
                if traffic_type != "ALL":
                    issues.append("VPC Flow Logs should capture ALL traffic types")
                
                log_destination = flow_log_values.get("log_destination")
                if not log_destination:
                    issues.append("VPC Flow Logs should specify log destination")
        
        return issues
    
    def validate_security_monitoring_alarms(self, plan_data: Dict) -> List[str]:
        """Validate security monitoring alarms."""
        issues = []
        
        # Find CloudWatch alarms
        alarms = self.find_resources_in_plan(plan_data, "aws_cloudwatch_metric_alarm")
        
        security_alarms = {
            "waf_blocked": False,
            "guardduty_findings": False
        }
        
        for alarm in alarms:
            alarm_values = alarm.get("values", {})
            alarm_name = alarm_values.get("alarm_name", "").lower()
            
            # Check for security-related alarms
            if "waf" in alarm_name and "blocked" in alarm_name:
                security_alarms["waf_blocked"] = True
                
                # Validate WAF alarm configuration
                namespace = alarm_values.get("namespace")
                if namespace != "AWS/WAFV2":
                    issues.append("WAF alarm should use AWS/WAFV2 namespace")
                
                metric_name = alarm_values.get("metric_name")
                if metric_name != "BlockedRequests":
                    issues.append("WAF alarm should monitor BlockedRequests metric")
            
            elif "guardduty" in alarm_name:
                security_alarms["guardduty_findings"] = True
                
                # Validate GuardDuty alarm configuration
                namespace = alarm_values.get("namespace")
                if namespace != "AWS/GuardDuty":
                    issues.append("GuardDuty alarm should use AWS/GuardDuty namespace")
        
        # Check for missing security alarms
        for alarm_type, found in security_alarms.items():
            if not found:
                issues.append(f"Missing {alarm_type.replace('_', ' ')} security alarm")
        
        return issues
    
    def validate_security_control_completeness(self, plan_data: Dict, config: Dict[str, Any]) -> Dict[str, Any]:
        """Validate overall security control completeness."""
        completeness_score = {
            "waf_protection": 0,
            "threat_detection": 0,
            "compliance_monitoring": 0,
            "network_security": 0,
            "security_monitoring": 0,
            "vulnerability_assessment": 0
        }
        
        # Check WAF protection
        web_acls = self.find_resources_in_plan(plan_data, "aws_wafv2_web_acl")
        waf_associations = self.find_resources_in_plan(plan_data, "aws_wafv2_web_acl_association")
        if web_acls and waf_associations:
            completeness_score["waf_protection"] = 1
        
        # Check threat detection
        guardduty_detectors = self.find_resources_in_plan(plan_data, "aws_guardduty_detector")
        security_hub_accounts = self.find_resources_in_plan(plan_data, "aws_securityhub_account")
        if (guardduty_detectors or not config.get("enable_guardduty", True)) and \
           (security_hub_accounts or not config.get("enable_security_hub", True)):
            completeness_score["threat_detection"] = 1
        
        # Check compliance monitoring
        config_recorders = self.find_resources_in_plan(plan_data, "aws_config_configuration_recorder")
        if config_recorders or not config.get("enable_config", True):
            completeness_score["compliance_monitoring"] = 1
        
        # Check network security
        network_acls = self.find_resources_in_plan(plan_data, "aws_network_acl")
        flow_logs = self.find_resources_in_plan(plan_data, "aws_flow_log")
        if len(network_acls) >= 2 and flow_logs:  # Expect private and database NACLs
            completeness_score["network_security"] = 1
        
        # Check security monitoring
        alarms = self.find_resources_in_plan(plan_data, "aws_cloudwatch_metric_alarm")
        security_alarm_count = 0
        for alarm in alarms:
            alarm_name = alarm.get("values", {}).get("alarm_name", "").lower()
            if any(keyword in alarm_name for keyword in ["waf", "guardduty", "security"]):
                security_alarm_count += 1
        
        if security_alarm_count >= 2:
            completeness_score["security_monitoring"] = 1
        
        # Check vulnerability assessment
        inspector_enablers = self.find_resources_in_plan(plan_data, "aws_inspector2_enabler")
        if inspector_enablers or not config.get("enable_inspector", True):
            completeness_score["vulnerability_assessment"] = 1
        
        total_score = sum(completeness_score.values())
        max_score = len(completeness_score)
        percentage = (total_score / max_score) * 100
        
        return {
            "score": percentage,
            "details": completeness_score,
            "recommendations": self._get_security_recommendations(completeness_score)
        }
    
    def _get_security_recommendations(self, score_details: Dict[str, int]) -> List[str]:
        """Get recommendations for improving security controls."""
        recommendations = []
        
        if score_details["waf_protection"] == 0:
            recommendations.append("Implement WAF with managed rule sets for web application protection")
        
        if score_details["threat_detection"] == 0:
            recommendations.append("Enable GuardDuty and Security Hub for threat detection")
        
        if score_details["compliance_monitoring"] == 0:
            recommendations.append("Configure AWS Config for compliance monitoring")
        
        if score_details["network_security"] == 0:
            recommendations.append("Implement Network ACLs and VPC Flow Logs for network security")
        
        if score_details["security_monitoring"] == 0:
            recommendations.append("Create security monitoring alarms for proactive threat response")
        
        if score_details["vulnerability_assessment"] == 0:
            recommendations.append("Enable Inspector for vulnerability assessment of containers and instances")
        
        return recommendations


# Property-based test strategies
@st.composite
def security_control_config(draw):
    """Generate security control configuration test scenarios."""
    config = {
        "aws_region": draw(st.sampled_from(["us-east-1", "us-west-2", "eu-west-1"])),
        "environment": draw(st.sampled_from(["staging", "production"])),
        "project_name": draw(st.text(min_size=3, max_size=20, alphabet=st.characters(whitelist_categories=("Ll", "Nd"), whitelist_characters="-"))),
        "vpc_cidr": draw(st.sampled_from(["10.0.0.0/16", "172.16.0.0/16"])),
        "az_count": draw(st.integers(min_value=2, max_value=3)),
        
        # Security configuration
        "enable_security_hub": draw(st.booleans()),
        "enable_guardduty": draw(st.booleans()),
        "enable_inspector": draw(st.booleans()),
        "enable_config": draw(st.booleans()),
        "waf_rate_limit": draw(st.integers(min_value=100, max_value=10000)),
        
        # Application configuration
        "app_port": draw(st.integers(min_value=3000, max_value=9000)),
        "health_check_path": "/health/simple",
        "log_retention_days": draw(st.integers(min_value=7, max_value=90)),
        
        # Database configuration (required)
        "neptune_cluster_identifier": "test-neptune",
        "opensearch_domain_name": "test-opensearch",
        "skip_final_snapshot": True,
        
        # Alert configuration
        "alert_email": draw(st.sampled_from(["", "test@example.com"])),
    }
    
    return config


class TestSecurityControlImplementation:
    """Property-based tests for security control implementation."""
    
    def setup_method(self):
        """Set up test environment."""
        self.security_test = SecurityControlImplementationTest()
    
    @given(config=security_control_config())
    @settings(max_examples=3, deadline=120000)  # 2 minute timeout
    def test_waf_configuration(self, config):
        """
        Property test: For any security configuration,
        WAF should be properly configured with security rules.
        
        **Feature: aws-production-deployment, Property 11: Security Control Implementation**
        **Validates: Requirements 4.5, 4.6, 4.7**
        """
        # Skip if Terraform not available
        if not subprocess.run(["which", "terraform"], capture_output=True).returncode == 0:
            pytest.skip("Terraform not available")
        
        plan_data = self.security_test.get_terraform_plan_json(config)
        assume(plan_data is not None)
        
        # Validate WAF configuration
        issues = self.security_test.validate_waf_configuration(plan_data)
        
        assert len(issues) == 0, f"WAF configuration issues: {'; '.join(issues)}"
    
    @given(config=security_control_config())
    @settings(max_examples=3, deadline=120000)
    def test_threat_detection_services(self, config):
        """
        Property test: For any security configuration,
        threat detection services should be properly configured.
        
        **Feature: aws-production-deployment, Property 11: Security Control Implementation**
        **Validates: Requirements 4.5, 4.6, 4.7**
        """
        # Skip if Terraform not available
        if not subprocess.run(["which", "terraform"], capture_output=True).returncode == 0:
            pytest.skip("Terraform not available")
        
        plan_data = self.security_test.get_terraform_plan_json(config)
        assume(plan_data is not None)
        
        # Validate threat detection services
        issues = self.security_test.validate_threat_detection_services(plan_data, config)
        
        assert len(issues) == 0, f"Threat detection services issues: {'; '.join(issues)}"
    
    @given(config=security_control_config())
    @settings(max_examples=3, deadline=120000)
    def test_network_security_controls(self, config):
        """
        Property test: For any security configuration,
        network security controls should be properly implemented.
        
        **Feature: aws-production-deployment, Property 11: Security Control Implementation**
        **Validates: Requirements 4.5, 4.6, 4.7**
        """
        # Skip if Terraform not available
        if not subprocess.run(["which", "terraform"], capture_output=True).returncode == 0:
            pytest.skip("Terraform not available")
        
        plan_data = self.security_test.get_terraform_plan_json(config)
        assume(plan_data is not None)
        
        # Validate network security controls
        issues = self.security_test.validate_network_security_controls(plan_data)
        
        assert len(issues) == 0, f"Network security controls issues: {'; '.join(issues)}"
    
    def test_comprehensive_security_controls(self):
        """
        Test that comprehensive security controls achieve good completeness score.
        
        **Feature: aws-production-deployment, Property 11: Security Control Implementation**
        **Validates: Requirements 4.5, 4.6, 4.7**
        """
        # Skip if Terraform not available
        if not subprocess.run(["which", "terraform"], capture_output=True).returncode == 0:
            pytest.skip("Terraform not available")
        
        config = {
            "aws_region": "us-east-1",
            "environment": "production",
            "project_name": "test-project",
            "enable_security_hub": True,
            "enable_guardduty": True,
            "enable_inspector": True,
            "enable_config": True,
            "waf_rate_limit": 2000,
            "log_retention_days": 30,
            "neptune_cluster_identifier": "test-neptune",
            "opensearch_domain_name": "test-opensearch",
            "skip_final_snapshot": True,
            "alert_email": "test@example.com",
        }
        
        plan_data = self.security_test.get_terraform_plan_json(config)
        assert plan_data is not None, "Should be able to generate Terraform plan"
        
        # Calculate security control completeness
        completeness = self.security_test.validate_security_control_completeness(plan_data, config)
        
        assert completeness["score"] >= 80, f"Security control completeness ({completeness['score']}%) should be at least 80%"
        
        # Check specific requirements
        assert completeness["details"]["waf_protection"] == 1, "Should have WAF protection configured"
        assert completeness["details"]["threat_detection"] == 1, "Should have threat detection configured"
        assert completeness["details"]["network_security"] == 1, "Should have network security configured"
    
    def test_security_monitoring_alarms(self):
        """
        Test that security monitoring alarms are properly configured.
        
        **Feature: aws-production-deployment, Property 11: Security Control Implementation**
        **Validates: Requirements 4.5, 4.6, 4.7**
        """
        # Skip if Terraform not available
        if not subprocess.run(["which", "terraform"], capture_output=True).returncode == 0:
            pytest.skip("Terraform not available")
        
        config = {
            "aws_region": "us-east-1",
            "environment": "production",
            "project_name": "test-project",
            "enable_guardduty": True,
            "neptune_cluster_identifier": "test-neptune",
            "opensearch_domain_name": "test-opensearch",
            "skip_final_snapshot": True,
        }
        
        plan_data = self.security_test.get_terraform_plan_json(config)
        assert plan_data is not None, "Should be able to generate Terraform plan"
        
        # Validate security monitoring alarms
        issues = self.security_test.validate_security_monitoring_alarms(plan_data)
        
        assert len(issues) == 0, f"Security monitoring alarms issues: {'; '.join(issues)}"
        
        # Check that security alarms exist
        alarms = self.security_test.find_resources_in_plan(plan_data, "aws_cloudwatch_metric_alarm")
        security_alarms = [alarm for alarm in alarms 
                          if any(keyword in alarm.get("values", {}).get("alarm_name", "").lower() 
                                for keyword in ["waf", "guardduty", "security"])]
        
        assert len(security_alarms) >= 1, "Should have at least one security monitoring alarm"


if __name__ == "__main__":
    # Run basic validation tests
    test_instance = TestSecurityControlImplementation()
    test_instance.setup_method()
    
    print("Running security control implementation tests...")
    
    try:
        test_instance.test_comprehensive_security_controls()
        print("✅ Comprehensive security controls test passed")
    except Exception as e:
        print(f"❌ Comprehensive security controls test failed: {e}")
    
    try:
        test_instance.test_security_monitoring_alarms()
        print("✅ Security monitoring alarms test passed")
    except Exception as e:
        print(f"❌ Security monitoring alarms test failed: {e}")
    
    print("\nTo run property-based tests with Hypothesis:")
    print("pytest tests/infrastructure/test_security_control_implementation.py -v")