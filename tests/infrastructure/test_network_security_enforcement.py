#!/usr/bin/env python3
"""
Property-Based Tests for Network Security Enforcement
Feature: aws-production-deployment, Property 12: Network Security Enforcement

This module tests that network security is properly enforced through security groups,
NACLs, VPC configuration, and proper network segmentation.
"""

import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, List, Any, Optional
import pytest
from hypothesis import given, strategies as st, settings, assume


class NetworkSecurityEnforcementTest:
    """Test class for network security enforcement validation."""
    
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
    
    def validate_vpc_network_segmentation(self, plan_data: Dict) -> List[str]:
        """Validate VPC network segmentation."""
        issues = []
        
        # Find VPC
        vpcs = self.find_resources_in_plan(plan_data, "aws_vpc")
        
        if not vpcs:
            issues.append("No VPC found - network infrastructure missing")
            return issues
        
        for vpc in vpcs:
            vpc_values = vpc.get("values", {})
            
            # Check VPC CIDR
            cidr_block = vpc_values.get("cidr_block")
            if not cidr_block:
                issues.append("VPC should have CIDR block configured")
                continue
            
            # Validate CIDR is private
            if not (cidr_block.startswith("10.") or 
                   cidr_block.startswith("172.16.") or 
                   cidr_block.startswith("192.168.")):
                issues.append("VPC CIDR should use private IP address space (RFC 1918)")
            
            # Check DNS settings
            enable_dns_hostnames = vpc_values.get("enable_dns_hostnames", False)
            enable_dns_support = vpc_values.get("enable_dns_support", False)
            
            if not enable_dns_hostnames:
                issues.append("VPC should enable DNS hostnames for proper service discovery")
            
            if not enable_dns_support:
                issues.append("VPC should enable DNS support for name resolution")
        
        # Check subnets
        subnets = self.find_resources_in_plan(plan_data, "aws_subnet")
        
        if not subnets:
            issues.append("No subnets found - network segmentation missing")
            return issues
        
        # Categorize subnets
        public_subnets = []
        private_subnets = []
        database_subnets = []
        
        for subnet in subnets:
            subnet_values = subnet.get("values", {})
            
            # Check availability zone
            availability_zone = subnet_values.get("availability_zone")
            if not availability_zone:
                issues.append("Subnet should specify availability zone for high availability")
            
            # Check CIDR block
            cidr_block = subnet_values.get("cidr_block")
            if not cidr_block:
                issues.append("Subnet should have CIDR block configured")
            
            # Categorize based on map_public_ip_on_launch
            map_public_ip = subnet_values.get("map_public_ip_on_launch", False)
            
            # Use tags or naming to determine subnet type (simplified)
            subnet_name = str(subnet_values.get("tags", {}))
            
            if map_public_ip or "public" in subnet_name.lower():
                public_subnets.append(subnet)
            elif "database" in subnet_name.lower() or "db" in subnet_name.lower():
                database_subnets.append(subnet)
            else:
                private_subnets.append(subnet)
        
        # Validate subnet distribution
        if len(public_subnets) < 2:
            issues.append("Should have at least 2 public subnets for high availability")
        
        if len(private_subnets) < 2:
            issues.append("Should have at least 2 private subnets for application tier")
        
        if len(database_subnets) < 2:
            issues.append("Should have at least 2 database subnets for database tier")
        
        return issues
    
    def validate_security_group_rules(self, plan_data: Dict) -> List[str]:
        """Validate security group rules and isolation."""
        issues = []
        
        # Find security groups
        security_groups = self.find_resources_in_plan(plan_data, "aws_security_group")
        
        if not security_groups:
            issues.append("No security groups found - network access control missing")
            return issues
        
        # Expected security groups
        expected_sg_types = {
            "alb": False,
            "ecs": False,
            "neptune": False,
            "opensearch": False
        }
        
        for sg in security_groups:
            sg_values = sg.get("values", {})
            sg_name = sg_values.get("name", "").lower()
            
            # Categorize security groups
            for sg_type in expected_sg_types:
                if sg_type in sg_name:
                    expected_sg_types[sg_type] = True
                    break
            
            # Check ingress rules
            ingress_rules = sg_values.get("ingress", [])
            
            for rule in ingress_rules:
                from_port = rule.get("from_port")
                to_port = rule.get("to_port")
                protocol = rule.get("protocol")
                cidr_blocks = rule.get("cidr_blocks", [])
                security_groups = rule.get("security_groups", [])
                
                # Check for overly permissive rules
                if "0.0.0.0/0" in cidr_blocks:
                    # Only ALB should allow 0.0.0.0/0 for HTTP/HTTPS
                    if "alb" not in sg_name:
                        issues.append(f"Security group {sg_name} should not allow 0.0.0.0/0 access")
                    elif from_port not in [80, 443]:
                        issues.append(f"Security group {sg_name} should only allow 0.0.0.0/0 for HTTP/HTTPS")
                
                # Check for unnecessary port ranges
                if from_port != to_port and protocol != "-1":
                    port_range = to_port - from_port
                    if port_range > 100:
                        issues.append(f"Security group {sg_name} has overly broad port range ({from_port}-{to_port})")
            
            # Check egress rules
            egress_rules = sg_values.get("egress", [])
            
            # Check for overly permissive egress
            for rule in egress_rules:
                cidr_blocks = rule.get("cidr_blocks", [])
                protocol = rule.get("protocol")
                
                if "0.0.0.0/0" in cidr_blocks and protocol == "-1":
                    # This is common but should be noted for database security groups
                    if "database" in sg_name or "neptune" in sg_name or "opensearch" in sg_name:
                        issues.append(f"Database security group {sg_name} should have restricted egress rules")
        
        # Check for missing security groups
        for sg_type, found in expected_sg_types.items():
            if not found:
                issues.append(f"Missing {sg_type} security group")
        
        # Find security group rules (newer format)
        sg_ingress_rules = self.find_resources_in_plan(plan_data, "aws_vpc_security_group_ingress_rule")
        sg_egress_rules = self.find_resources_in_plan(plan_data, "aws_vpc_security_group_egress_rule")
        
        # Validate explicit security group rules
        for rule in sg_ingress_rules:
            rule_values = rule.get("values", {})
            
            cidr_ipv4 = rule_values.get("cidr_ipv4")
            from_port = rule_values.get("from_port")
            to_port = rule_values.get("to_port")
            
            # Check for appropriate port restrictions
            if cidr_ipv4 == "0.0.0.0/0":
                if from_port not in [80, 443]:
                    issues.append(f"Ingress rule allowing 0.0.0.0/0 should only be for HTTP (80) or HTTPS (443), got port {from_port}")
        
        return issues
    
    def validate_network_acl_enforcement(self, plan_data: Dict) -> List[str]:
        """Validate Network ACL enforcement."""
        issues = []
        
        # Find Network ACLs
        network_acls = self.find_resources_in_plan(plan_data, "aws_network_acl")
        
        if not network_acls:
            issues.append("No custom Network ACLs found - additional network security layer missing")
            return issues
        
        nacl_types = {
            "private": False,
            "database": False
        }
        
        for nacl in network_acls:
            nacl_values = nacl.get("values", {})
            
            # Determine NACL type (simplified check)
            nacl_name = str(nacl_values)
            
            if "private" in nacl_name.lower():
                nacl_types["private"] = True
            elif "database" in nacl_name.lower():
                nacl_types["database"] = True
            
            # Check subnet associations
            subnet_ids = nacl_values.get("subnet_ids", [])
            if not subnet_ids:
                issues.append("Network ACL should be associated with subnets")
            
            # Check ingress rules
            ingress_rules = nacl_values.get("ingress", [])
            if not ingress_rules:
                issues.append("Network ACL should have ingress rules configured")
            else:
                for rule in ingress_rules:
                    rule_no = rule.get("rule_no")
                    action = rule.get("action")
                    
                    if rule_no is None:
                        issues.append("Network ACL ingress rule should have rule number")
                    
                    if action not in ["allow", "deny"]:
                        issues.append("Network ACL ingress rule should specify allow or deny action")
            
            # Check egress rules
            egress_rules = nacl_values.get("egress", [])
            if not egress_rules:
                issues.append("Network ACL should have egress rules configured")
            else:
                for rule in egress_rules:
                    rule_no = rule.get("rule_no")
                    action = rule.get("action")
                    
                    if rule_no is None:
                        issues.append("Network ACL egress rule should have rule number")
                    
                    if action not in ["allow", "deny"]:
                        issues.append("Network ACL egress rule should specify allow or deny action")
        
        # Check for missing NACL types
        for nacl_type, found in nacl_types.items():
            if not found:
                issues.append(f"Missing {nacl_type} Network ACL for additional security")
        
        return issues
    
    def validate_internet_gateway_configuration(self, plan_data: Dict) -> List[str]:
        """Validate Internet Gateway and NAT Gateway configuration."""
        issues = []
        
        # Find Internet Gateway
        internet_gateways = self.find_resources_in_plan(plan_data, "aws_internet_gateway")
        
        if not internet_gateways:
            issues.append("No Internet Gateway found - public internet access missing")
        else:
            for igw in internet_gateways:
                igw_values = igw.get("values", {})
                vpc_id = igw_values.get("vpc_id")
                
                if not vpc_id:
                    issues.append("Internet Gateway should be attached to VPC")
        
        # Find NAT Gateways
        nat_gateways = self.find_resources_in_plan(plan_data, "aws_nat_gateway")
        
        if not nat_gateways:
            issues.append("No NAT Gateways found - private subnet internet access missing")
        else:
            # Check NAT Gateway configuration
            for nat in nat_gateways:
                nat_values = nat.get("values", {})
                
                allocation_id = nat_values.get("allocation_id")
                subnet_id = nat_values.get("subnet_id")
                
                if not allocation_id:
                    issues.append("NAT Gateway should have Elastic IP allocation")
                
                if not subnet_id:
                    issues.append("NAT Gateway should be deployed in public subnet")
        
        # Find Elastic IPs for NAT Gateways
        eips = self.find_resources_in_plan(plan_data, "aws_eip")
        
        nat_eips = [eip for eip in eips 
                   if eip.get("values", {}).get("domain") == "vpc"]
        
        if len(nat_eips) < len(nat_gateways):
            issues.append("Each NAT Gateway should have dedicated Elastic IP")
        
        return issues
    
    def validate_route_table_configuration(self, plan_data: Dict) -> List[str]:
        """Validate route table configuration for proper traffic flow."""
        issues = []
        
        # Find route tables
        route_tables = self.find_resources_in_plan(plan_data, "aws_route_table")
        
        if not route_tables:
            issues.append("No custom route tables found - traffic routing may not be properly configured")
            return issues
        
        route_table_types = {
            "public": False,
            "private": False
        }
        
        for rt in route_tables:
            rt_values = rt.get("values", {})
            
            # Check routes
            routes = rt_values.get("route", [])
            
            # Determine route table type based on routes
            has_igw_route = False
            has_nat_route = False
            
            for route in routes:
                cidr_block = route.get("cidr_block")
                gateway_id = route.get("gateway_id", "")
                nat_gateway_id = route.get("nat_gateway_id")
                
                if cidr_block == "0.0.0.0/0":
                    if "igw-" in gateway_id:
                        has_igw_route = True
                        route_table_types["public"] = True
                    elif nat_gateway_id:
                        has_nat_route = True
                        route_table_types["private"] = True
            
            # Validate route configuration
            if not routes:
                issues.append("Route table should have routes configured")
        
        # Check for missing route table types
        for rt_type, found in route_table_types.items():
            if not found:
                issues.append(f"Missing {rt_type} route table for proper traffic routing")
        
        # Find route table associations
        rt_associations = self.find_resources_in_plan(plan_data, "aws_route_table_association")
        
        if not rt_associations:
            issues.append("Route tables should be associated with subnets")
        
        return issues
    
    def validate_vpc_endpoints_security(self, plan_data: Dict) -> List[str]:
        """Validate VPC endpoints for secure AWS service access."""
        issues = []
        
        # Find VPC endpoints
        vpc_endpoints = self.find_resources_in_plan(plan_data, "aws_vpc_endpoint")
        
        # While VPC endpoints are not strictly required, they improve security
        # by keeping traffic within AWS network
        
        if vpc_endpoints:
            for endpoint in vpc_endpoints:
                endpoint_values = endpoint.get("values", {})
                
                # Check endpoint type
                vpc_endpoint_type = endpoint_values.get("vpc_endpoint_type")
                if vpc_endpoint_type not in ["Gateway", "Interface"]:
                    issues.append("VPC endpoint should specify type (Gateway or Interface)")
                
                # Check security groups for Interface endpoints
                if vpc_endpoint_type == "Interface":
                    security_group_ids = endpoint_values.get("security_group_ids", [])
                    if not security_group_ids:
                        issues.append("Interface VPC endpoint should have security groups configured")
                
                # Check subnet IDs for Interface endpoints
                if vpc_endpoint_type == "Interface":
                    subnet_ids = endpoint_values.get("subnet_ids", [])
                    if not subnet_ids:
                        issues.append("Interface VPC endpoint should be deployed in subnets")
        
        return issues
    
    def validate_network_security_completeness(self, plan_data: Dict) -> Dict[str, Any]:
        """Validate overall network security completeness."""
        completeness_score = {
            "vpc_segmentation": 0,
            "security_groups": 0,
            "network_acls": 0,
            "internet_access": 0,
            "route_configuration": 0,
            "vpc_flow_logs": 0
        }
        
        # Check VPC segmentation
        vpcs = self.find_resources_in_plan(plan_data, "aws_vpc")
        subnets = self.find_resources_in_plan(plan_data, "aws_subnet")
        if vpcs and len(subnets) >= 6:  # Expect public, private, database subnets
            completeness_score["vpc_segmentation"] = 1
        
        # Check security groups
        security_groups = self.find_resources_in_plan(plan_data, "aws_security_group")
        if len(security_groups) >= 4:  # Expect ALB, ECS, Neptune, OpenSearch SGs
            completeness_score["security_groups"] = 1
        
        # Check Network ACLs
        network_acls = self.find_resources_in_plan(plan_data, "aws_network_acl")
        if len(network_acls) >= 2:  # Expect private and database NACLs
            completeness_score["network_acls"] = 1
        
        # Check internet access
        internet_gateways = self.find_resources_in_plan(plan_data, "aws_internet_gateway")
        nat_gateways = self.find_resources_in_plan(plan_data, "aws_nat_gateway")
        if internet_gateways and nat_gateways:
            completeness_score["internet_access"] = 1
        
        # Check route configuration
        route_tables = self.find_resources_in_plan(plan_data, "aws_route_table")
        rt_associations = self.find_resources_in_plan(plan_data, "aws_route_table_association")
        if route_tables and rt_associations:
            completeness_score["route_configuration"] = 1
        
        # Check VPC Flow Logs
        flow_logs = self.find_resources_in_plan(plan_data, "aws_flow_log")
        if flow_logs:
            completeness_score["vpc_flow_logs"] = 1
        
        total_score = sum(completeness_score.values())
        max_score = len(completeness_score)
        percentage = (total_score / max_score) * 100
        
        return {
            "score": percentage,
            "details": completeness_score,
            "recommendations": self._get_network_security_recommendations(completeness_score)
        }
    
    def _get_network_security_recommendations(self, score_details: Dict[str, int]) -> List[str]:
        """Get recommendations for improving network security."""
        recommendations = []
        
        if score_details["vpc_segmentation"] == 0:
            recommendations.append("Implement proper VPC segmentation with public, private, and database subnets")
        
        if score_details["security_groups"] == 0:
            recommendations.append("Configure security groups for each tier with least-privilege access")
        
        if score_details["network_acls"] == 0:
            recommendations.append("Implement Network ACLs for additional network security layer")
        
        if score_details["internet_access"] == 0:
            recommendations.append("Configure Internet Gateway and NAT Gateways for proper internet access")
        
        if score_details["route_configuration"] == 0:
            recommendations.append("Configure route tables and associations for proper traffic routing")
        
        if score_details["vpc_flow_logs"] == 0:
            recommendations.append("Enable VPC Flow Logs for network traffic monitoring")
        
        return recommendations


# Property-based test strategies
@st.composite
def network_security_config(draw):
    """Generate network security configuration test scenarios."""
    config = {
        "aws_region": draw(st.sampled_from(["us-east-1", "us-west-2", "eu-west-1"])),
        "environment": draw(st.sampled_from(["staging", "production"])),
        "project_name": draw(st.text(min_size=3, max_size=20, alphabet=st.characters(whitelist_categories=("Ll", "Nd"), whitelist_characters="-"))),
        "vpc_cidr": draw(st.sampled_from(["10.0.0.0/16", "172.16.0.0/16", "192.168.0.0/16"])),
        "az_count": draw(st.integers(min_value=2, max_value=3)),
        
        # Network configuration
        "enable_nat_gateway": draw(st.booleans()),
        "single_nat_gateway": draw(st.booleans()),
        "enable_flow_logs": draw(st.booleans()),
        
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


class TestNetworkSecurityEnforcement:
    """Property-based tests for network security enforcement."""
    
    def setup_method(self):
        """Set up test environment."""
        self.network_test = NetworkSecurityEnforcementTest()
    
    @given(config=network_security_config())
    @settings(max_examples=3, deadline=120000)  # 2 minute timeout
    def test_vpc_network_segmentation(self, config):
        """
        Property test: For any network configuration,
        VPC should be properly segmented with appropriate subnets.
        
        **Feature: aws-production-deployment, Property 12: Network Security Enforcement**
        **Validates: Requirements 4.2, 1.5**
        """
        # Skip if Terraform not available
        if not subprocess.run(["which", "terraform"], capture_output=True).returncode == 0:
            pytest.skip("Terraform not available")
        
        plan_data = self.network_test.get_terraform_plan_json(config)
        assume(plan_data is not None)
        
        # Validate VPC network segmentation
        issues = self.network_test.validate_vpc_network_segmentation(plan_data)
        
        assert len(issues) == 0, f"VPC network segmentation issues: {'; '.join(issues)}"
    
    @given(config=network_security_config())
    @settings(max_examples=3, deadline=120000)
    def test_security_group_rules(self, config):
        """
        Property test: For any network configuration,
        security group rules should enforce proper access control.
        
        **Feature: aws-production-deployment, Property 12: Network Security Enforcement**
        **Validates: Requirements 4.2, 1.5**
        """
        # Skip if Terraform not available
        if not subprocess.run(["which", "terraform"], capture_output=True).returncode == 0:
            pytest.skip("Terraform not available")
        
        plan_data = self.network_test.get_terraform_plan_json(config)
        assume(plan_data is not None)
        
        # Validate security group rules
        issues = self.network_test.validate_security_group_rules(plan_data)
        
        assert len(issues) == 0, f"Security group rules issues: {'; '.join(issues)}"
    
    @given(config=network_security_config())
    @settings(max_examples=3, deadline=120000)
    def test_network_acl_enforcement(self, config):
        """
        Property test: For any network configuration,
        Network ACLs should provide additional security layer.
        
        **Feature: aws-production-deployment, Property 12: Network Security Enforcement**
        **Validates: Requirements 4.2, 1.5**
        """
        # Skip if Terraform not available
        if not subprocess.run(["which", "terraform"], capture_output=True).returncode == 0:
            pytest.skip("Terraform not available")
        
        plan_data = self.network_test.get_terraform_plan_json(config)
        assume(plan_data is not None)
        
        # Validate Network ACL enforcement
        issues = self.network_test.validate_network_acl_enforcement(plan_data)
        
        assert len(issues) == 0, f"Network ACL enforcement issues: {'; '.join(issues)}"
    
    def test_comprehensive_network_security(self):
        """
        Test that comprehensive network security achieves good completeness score.
        
        **Feature: aws-production-deployment, Property 12: Network Security Enforcement**
        **Validates: Requirements 4.2, 1.5**
        """
        # Skip if Terraform not available
        if not subprocess.run(["which", "terraform"], capture_output=True).returncode == 0:
            pytest.skip("Terraform not available")
        
        config = {
            "aws_region": "us-east-1",
            "environment": "production",
            "project_name": "test-project",
            "vpc_cidr": "10.0.0.0/16",
            "az_count": 2,
            "enable_nat_gateway": True,
            "single_nat_gateway": False,
            "enable_flow_logs": True,
            "log_retention_days": 30,
            "neptune_cluster_identifier": "test-neptune",
            "opensearch_domain_name": "test-opensearch",
            "skip_final_snapshot": True,
        }
        
        plan_data = self.network_test.get_terraform_plan_json(config)
        assert plan_data is not None, "Should be able to generate Terraform plan"
        
        # Calculate network security completeness
        completeness = self.network_test.validate_network_security_completeness(plan_data)
        
        assert completeness["score"] >= 80, f"Network security completeness ({completeness['score']}%) should be at least 80%"
        
        # Check specific requirements
        assert completeness["details"]["vpc_segmentation"] == 1, "Should have VPC segmentation configured"
        assert completeness["details"]["security_groups"] == 1, "Should have security groups configured"
        assert completeness["details"]["internet_access"] == 1, "Should have internet access configured"
    
    def test_internet_gateway_configuration(self):
        """
        Test that Internet Gateway and NAT Gateway are properly configured.
        
        **Feature: aws-production-deployment, Property 12: Network Security Enforcement**
        **Validates: Requirements 4.2, 1.5**
        """
        # Skip if Terraform not available
        if not subprocess.run(["which", "terraform"], capture_output=True).returncode == 0:
            pytest.skip("Terraform not available")
        
        config = {
            "aws_region": "us-east-1",
            "environment": "production",
            "project_name": "test-project",
            "vpc_cidr": "10.0.0.0/16",
            "enable_nat_gateway": True,
            "neptune_cluster_identifier": "test-neptune",
            "opensearch_domain_name": "test-opensearch",
            "skip_final_snapshot": True,
        }
        
        plan_data = self.network_test.get_terraform_plan_json(config)
        assert plan_data is not None, "Should be able to generate Terraform plan"
        
        # Validate Internet Gateway configuration
        issues = self.network_test.validate_internet_gateway_configuration(plan_data)
        
        assert len(issues) == 0, f"Internet Gateway configuration issues: {'; '.join(issues)}"
        
        # Check that gateways exist
        internet_gateways = self.network_test.find_resources_in_plan(plan_data, "aws_internet_gateway")
        nat_gateways = self.network_test.find_resources_in_plan(plan_data, "aws_nat_gateway")
        
        assert len(internet_gateways) >= 1, "Should have Internet Gateway"
        assert len(nat_gateways) >= 1, "Should have NAT Gateway"


if __name__ == "__main__":
    # Run basic validation tests
    test_instance = TestNetworkSecurityEnforcement()
    test_instance.setup_method()
    
    print("Running network security enforcement tests...")
    
    try:
        test_instance.test_comprehensive_network_security()
        print("✅ Comprehensive network security test passed")
    except Exception as e:
        print(f"❌ Comprehensive network security test failed: {e}")
    
    try:
        test_instance.test_internet_gateway_configuration()
        print("✅ Internet Gateway configuration test passed")
    except Exception as e:
        print(f"❌ Internet Gateway configuration test failed: {e}")
    
    print("\nTo run property-based tests with Hypothesis:")
    print("pytest tests/infrastructure/test_network_security_enforcement.py -v")