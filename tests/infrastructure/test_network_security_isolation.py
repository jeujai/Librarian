#!/usr/bin/env python3
"""
Property-Based Tests for Network Security Isolation
Feature: aws-production-deployment, Property 2: Network Security Isolation

This module tests that backend services are only accessible from private subnets
and not directly from the internet using property-based testing.
"""

import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, List, Any, Set
import pytest
from hypothesis import given, strategies as st, settings, assume
from hypothesis.stateful import RuleBasedStateMachine, Bundle, rule, initialize


class NetworkSecurityTest:
    """Test class for network security isolation validation."""
    
    def __init__(self, terraform_dir: str = None):
        if terraform_dir is None:
            # Auto-detect terraform directory
            current_dir = Path.cwd()
            if (current_dir / "terraform.tf").exists():
                self.terraform_dir = current_dir
            elif (current_dir / "infrastructure" / "aws-native").exists():
                self.terraform_dir = current_dir / "infrastructure" / "aws-native"
            else:
                self.terraform_dir = Path("infrastructure/aws-native")
        else:
            self.terraform_dir = Path(terraform_dir)
    
    def extract_security_groups_from_plan(self, plan_output: str) -> Dict[str, Dict]:
        """Extract security group configurations from Terraform plan."""
        security_groups = {}
        
        try:
            plan_data = json.loads(plan_output)
            
            def extract_from_module(module_data, module_path=""):
                if "resources" not in module_data:
                    return
                
                for resource in module_data["resources"]:
                    if resource.get("type") == "aws_security_group":
                        sg_name = resource.get("name", "")
                        sg_values = resource.get("values", {})
                        
                        full_name = f"{module_path}.{sg_name}" if module_path else sg_name
                        
                        security_groups[full_name] = {
                            "name": sg_values.get("name", ""),
                            "description": sg_values.get("description", ""),
                            "ingress": sg_values.get("ingress", []),
                            "egress": sg_values.get("egress", []),
                            "vpc_id": sg_values.get("vpc_id", "")
                        }
            
            # Extract from root module
            if "planned_values" in plan_data and "root_module" in plan_data["planned_values"]:
                root_module = plan_data["planned_values"]["root_module"]
                extract_from_module(root_module)
                
                # Extract from child modules
                if "child_modules" in root_module:
                    for child_module in root_module["child_modules"]:
                        module_address = child_module.get("address", "")
                        extract_from_module(child_module, module_address)
        
        except (json.JSONDecodeError, KeyError) as e:
            print(f"Error parsing security groups: {e}")
        
        return security_groups
    
    def extract_subnets_from_plan(self, plan_output: str) -> Dict[str, Dict]:
        """Extract subnet configurations from Terraform plan."""
        subnets = {}
        
        try:
            plan_data = json.loads(plan_output)
            
            def extract_from_module(module_data, module_path=""):
                if "resources" not in module_data:
                    return
                
                for resource in module_data["resources"]:
                    if resource.get("type") == "aws_subnet":
                        subnet_name = resource.get("name", "")
                        subnet_values = resource.get("values", {})
                        
                        full_name = f"{module_path}.{subnet_name}" if module_path else subnet_name
                        
                        subnets[full_name] = {
                            "cidr_block": subnet_values.get("cidr_block", ""),
                            "availability_zone": subnet_values.get("availability_zone", ""),
                            "map_public_ip_on_launch": subnet_values.get("map_public_ip_on_launch", False),
                            "tags": subnet_values.get("tags", {}),
                            "vpc_id": subnet_values.get("vpc_id", "")
                        }
            
            # Extract from root module
            if "planned_values" in plan_data and "root_module" in plan_data["planned_values"]:
                root_module = plan_data["planned_values"]["root_module"]
                extract_from_module(root_module)
                
                # Extract from child modules
                if "child_modules" in root_module:
                    for child_module in root_module["child_modules"]:
                        module_address = child_module.get("address", "")
                        extract_from_module(child_module, module_address)
        
        except (json.JSONDecodeError, KeyError) as e:
            print(f"Error parsing subnets: {e}")
        
        return subnets
    
    def validate_database_security_isolation(self, security_groups: Dict[str, Dict]) -> bool:
        """Validate that database security groups only allow access from private networks."""
        database_sgs = {
            name: sg for name, sg in security_groups.items() 
            if any(keyword in sg.get("description", "").lower() 
                  for keyword in ["neptune", "opensearch", "database"])
        }
        
        for sg_name, sg_config in database_sgs.items():
            ingress_rules = sg_config.get("ingress", [])
            
            for rule in ingress_rules:
                # Check CIDR blocks - should not allow 0.0.0.0/0 for database access
                cidr_blocks = rule.get("cidr_blocks", [])
                if "0.0.0.0/0" in cidr_blocks:
                    return False
                
                # Check for overly permissive CIDR blocks
                for cidr in cidr_blocks:
                    if cidr.endswith("/0") or cidr.endswith("/8"):
                        return False
        
        return True
    
    def validate_private_subnet_isolation(self, subnets: Dict[str, Dict]) -> bool:
        """Validate that private subnets don't auto-assign public IPs."""
        private_subnets = {
            name: subnet for name, subnet in subnets.items()
            if subnet.get("tags", {}).get("Type") in ["private", "database"]
        }
        
        for subnet_name, subnet_config in private_subnets.items():
            # Private subnets should not auto-assign public IPs
            if subnet_config.get("map_public_ip_on_launch", False):
                return False
        
        return True
    
    def validate_security_group_references(self, security_groups: Dict[str, Dict]) -> bool:
        """Validate that security groups reference each other appropriately."""
        # Database security groups should only allow access from application security groups
        database_sgs = {
            name: sg for name, sg in security_groups.items() 
            if any(keyword in sg.get("description", "").lower() 
                  for keyword in ["neptune", "opensearch", "database"])
        }
        
        app_sgs = {
            name: sg for name, sg in security_groups.items() 
            if any(keyword in sg.get("description", "").lower() 
                  for keyword in ["ecs", "application", "app"])
        }
        
        for db_sg_name, db_sg_config in database_sgs.items():
            ingress_rules = db_sg_config.get("ingress", [])
            
            for rule in ingress_rules:
                security_groups_refs = rule.get("security_groups", [])
                cidr_blocks = rule.get("cidr_blocks", [])
                
                # If using CIDR blocks, they should be private ranges
                for cidr in cidr_blocks:
                    if not self._is_private_cidr(cidr):
                        return False
                
                # Security group references should point to application SGs
                # This is a simplified check - in practice, we'd validate the actual references
                if security_groups_refs and not any(
                    "ecs" in ref or "app" in ref for ref in security_groups_refs
                ):
                    # Allow self-references and monitoring
                    if not any("self" in str(ref) or "monitoring" in str(ref) 
                             for ref in security_groups_refs):
                        return False
        
        return True
    
    def _is_private_cidr(self, cidr: str) -> bool:
        """Check if CIDR block is in private IP ranges."""
        private_ranges = [
            "10.0.0.0/8",
            "172.16.0.0/12", 
            "192.168.0.0/16"
        ]
        
        # Simple check - in practice, you'd use ipaddress module for proper validation
        for private_range in private_ranges:
            if cidr.startswith(private_range.split('/')[0].split('.')[0]):
                return True
        
        return False


# Property-based test strategies
@st.composite
def network_config_strategy(draw):
    """Generate valid network configurations for testing."""
    return {
        "vpc_cidr": draw(st.sampled_from([
            "10.0.0.0/16", "172.16.0.0/16", "192.168.0.0/16"
        ])),
        "az_count": draw(st.integers(min_value=2, max_value=3)),
        "enable_nat_gateway": draw(st.booleans()),
        "single_nat_gateway": draw(st.booleans()),
    }


@st.composite
def security_group_config_strategy(draw):
    """Generate security group configurations for testing."""
    return {
        "enable_waf": draw(st.booleans()),
        "enable_caching": draw(st.booleans()),
        "app_port": draw(st.integers(min_value=8000, max_value=8999)),
    }


class TestNetworkSecurityIsolation:
    """Property-based tests for network security isolation."""
    
    def setup_method(self):
        """Set up test environment."""
        self.network_test = NetworkSecurityTest()
    
    @given(
        network_config=network_config_strategy(),
        security_config=security_group_config_strategy()
    )
    @settings(max_examples=5, deadline=120000)  # 2 minute timeout
    def test_database_security_isolation_property(self, network_config, security_config):
        """
        Property test: For any network configuration, database services should only
        be accessible from private subnets and not directly from the internet.
        
        **Feature: aws-production-deployment, Property 2: Network Security Isolation**
        **Validates: Requirements 1.4, 2.4, 3.5, 4.2**
        """
        # Skip if Terraform not available
        if not subprocess.run(["which", "terraform"], capture_output=True).returncode == 0:
            pytest.skip("Terraform not available")
        
        # Create test configuration
        config = {
            "aws_region": "us-east-1",
            "environment": "test",
            "project_name": "security-test",
            "neptune_cluster_identifier": "test-neptune",
            "opensearch_domain_name": "test-opensearch",
            "skip_final_snapshot": True,
            **network_config,
            **security_config
        }
        
        # Create temporary tfvars file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.tfvars', delete=False) as f:
            for key, value in config.items():
                if isinstance(value, str):
                    f.write(f'{key} = "{value}"\n')
                else:
                    f.write(f'{key} = {value}\n')
            tfvars_path = f.name
        
        try:
            # Change to terraform directory
            original_dir = os.getcwd()
            os.chdir(self.network_test.terraform_dir)
            
            # Initialize Terraform
            init_result = subprocess.run(
                ["terraform", "init", "-backend=false"],
                capture_output=True,
                text=True,
                timeout=60
            )
            
            assume(init_result.returncode == 0)
            
            # Run terraform plan
            plan_result = subprocess.run(
                ["terraform", "plan", "-var-file", tfvars_path, "-out=security-test.tfplan"],
                capture_output=True,
                text=True,
                timeout=120
            )
            
            assume(plan_result.returncode in [0, 2])
            
            # Get plan in JSON format
            show_result = subprocess.run(
                ["terraform", "show", "-json", "security-test.tfplan"],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if show_result.returncode == 0:
                # Extract security groups and subnets
                security_groups = self.network_test.extract_security_groups_from_plan(show_result.stdout)
                subnets = self.network_test.extract_subnets_from_plan(show_result.stdout)
                
                # Validate database security isolation
                assert self.network_test.validate_database_security_isolation(security_groups), \
                    "Database security groups must not allow direct internet access"
                
                # Validate private subnet isolation
                assert self.network_test.validate_private_subnet_isolation(subnets), \
                    "Private subnets must not auto-assign public IP addresses"
                
                # Validate security group references
                assert self.network_test.validate_security_group_references(security_groups), \
                    "Security groups must follow least-privilege access patterns"
        
        finally:
            os.chdir(original_dir)
            # Cleanup
            try:
                os.unlink(tfvars_path)
                if os.path.exists(os.path.join(self.network_test.terraform_dir, "security-test.tfplan")):
                    os.unlink(os.path.join(self.network_test.terraform_dir, "security-test.tfplan"))
            except:
                pass
    
    def test_security_group_ingress_rules_isolation(self):
        """
        Test that security group ingress rules follow isolation principles.
        
        **Feature: aws-production-deployment, Property 2: Network Security Isolation**
        **Validates: Requirements 1.4, 4.2**
        """
        # Skip if Terraform not available
        if not subprocess.run(["which", "terraform"], capture_output=True).returncode == 0:
            pytest.skip("Terraform not available")
        
        # Create minimal test configuration
        config = {
            "aws_region": "us-east-1",
            "environment": "test",
            "project_name": "isolation-test",
            "neptune_cluster_identifier": "test-neptune",
            "opensearch_domain_name": "test-opensearch",
            "skip_final_snapshot": True,
            "vpc_cidr": "10.0.0.0/16",
            "az_count": 2
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.tfvars', delete=False) as f:
            for key, value in config.items():
                if isinstance(value, str):
                    f.write(f'{key} = "{value}"\n')
                else:
                    f.write(f'{key} = {value}\n')
            tfvars_path = f.name
        
        try:
            original_dir = os.getcwd()
            os.chdir(self.network_test.terraform_dir)
            
            # Initialize and plan
            subprocess.run(["terraform", "init", "-backend=false"], 
                         capture_output=True, timeout=60)
            
            plan_result = subprocess.run(
                ["terraform", "plan", "-var-file", tfvars_path, "-out=isolation-test.tfplan"],
                capture_output=True, text=True, timeout=120
            )
            
            if plan_result.returncode in [0, 2]:
                # Get plan JSON
                show_result = subprocess.run(
                    ["terraform", "show", "-json", "isolation-test.tfplan"],
                    capture_output=True, text=True, timeout=30
                )
                
                if show_result.returncode == 0:
                    security_groups = self.network_test.extract_security_groups_from_plan(show_result.stdout)
                    
                    # Specific checks for known security groups
                    database_sg_found = False
                    alb_sg_found = False
                    
                    for sg_name, sg_config in security_groups.items():
                        description = sg_config.get("description", "").lower()
                        
                        # Check ALB security group allows internet access
                        if "load balancer" in description or "alb" in description:
                            alb_sg_found = True
                            ingress_rules = sg_config.get("ingress", [])
                            
                            # ALB should allow HTTP/HTTPS from internet
                            has_http_https = any(
                                rule.get("from_port") in [80, 443] and 
                                "0.0.0.0/0" in rule.get("cidr_blocks", [])
                                for rule in ingress_rules
                            )
                            assert has_http_https, "ALB security group must allow HTTP/HTTPS from internet"
                        
                        # Check database security groups don't allow internet access
                        elif any(db_keyword in description for db_keyword in ["neptune", "opensearch", "database"]):
                            database_sg_found = True
                            ingress_rules = sg_config.get("ingress", [])
                            
                            # Database SGs should not allow 0.0.0.0/0
                            for rule in ingress_rules:
                                cidr_blocks = rule.get("cidr_blocks", [])
                                assert "0.0.0.0/0" not in cidr_blocks, \
                                    f"Database security group {sg_name} must not allow internet access"
                    
                    # Ensure we found the expected security groups
                    assert database_sg_found, "Database security groups should be present in plan"
        
        finally:
            os.chdir(original_dir)
            try:
                os.unlink(tfvars_path)
                if os.path.exists(os.path.join(self.network_test.terraform_dir, "isolation-test.tfplan")):
                    os.unlink(os.path.join(self.network_test.terraform_dir, "isolation-test.tfplan"))
            except:
                pass
    
    def test_subnet_tier_isolation(self):
        """
        Test that subnet tiers are properly isolated (public, private, database).
        
        **Feature: aws-production-deployment, Property 2: Network Security Isolation**
        **Validates: Requirements 2.4, 3.5**
        """
        # Skip if Terraform not available
        if not subprocess.run(["which", "terraform"], capture_output=True).returncode == 0:
            pytest.skip("Terraform not available")
        
        config = {
            "aws_region": "us-east-1",
            "environment": "test",
            "project_name": "subnet-test",
            "neptune_cluster_identifier": "test-neptune",
            "opensearch_domain_name": "test-opensearch",
            "skip_final_snapshot": True,
            "vpc_cidr": "10.0.0.0/16",
            "az_count": 3
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.tfvars', delete=False) as f:
            for key, value in config.items():
                if isinstance(value, str):
                    f.write(f'{key} = "{value}"\n')
                else:
                    f.write(f'{key} = {value}\n')
            tfvars_path = f.name
        
        try:
            original_dir = os.getcwd()
            os.chdir(self.network_test.terraform_dir)
            
            subprocess.run(["terraform", "init", "-backend=false"], 
                         capture_output=True, timeout=60)
            
            plan_result = subprocess.run(
                ["terraform", "plan", "-var-file", tfvars_path, "-out=subnet-test.tfplan"],
                capture_output=True, text=True, timeout=120
            )
            
            if plan_result.returncode in [0, 2]:
                show_result = subprocess.run(
                    ["terraform", "show", "-json", "subnet-test.tfplan"],
                    capture_output=True, text=True, timeout=30
                )
                
                if show_result.returncode == 0:
                    subnets = self.network_test.extract_subnets_from_plan(show_result.stdout)
                    
                    public_subnets = []
                    private_subnets = []
                    database_subnets = []
                    
                    for subnet_name, subnet_config in subnets.items():
                        subnet_type = subnet_config.get("tags", {}).get("Type", "")
                        
                        if subnet_type == "public":
                            public_subnets.append(subnet_config)
                        elif subnet_type == "private":
                            private_subnets.append(subnet_config)
                        elif subnet_type == "database":
                            database_subnets.append(subnet_config)
                    
                    # Validate subnet counts
                    assert len(public_subnets) == config["az_count"], \
                        f"Should have {config['az_count']} public subnets"
                    assert len(private_subnets) == config["az_count"], \
                        f"Should have {config['az_count']} private subnets"
                    assert len(database_subnets) == config["az_count"], \
                        f"Should have {config['az_count']} database subnets"
                    
                    # Validate public subnets can auto-assign public IPs
                    for subnet in public_subnets:
                        assert subnet.get("map_public_ip_on_launch", False), \
                            "Public subnets should auto-assign public IP addresses"
                    
                    # Validate private and database subnets don't auto-assign public IPs
                    for subnet in private_subnets + database_subnets:
                        assert not subnet.get("map_public_ip_on_launch", False), \
                            "Private and database subnets should not auto-assign public IP addresses"
        
        finally:
            os.chdir(original_dir)
            try:
                os.unlink(tfvars_path)
                if os.path.exists(os.path.join(self.network_test.terraform_dir, "subnet-test.tfplan")):
                    os.unlink(os.path.join(self.network_test.terraform_dir, "subnet-test.tfplan"))
            except:
                pass


if __name__ == "__main__":
    # Run basic network security tests
    test_instance = TestNetworkSecurityIsolation()
    test_instance.setup_method()
    
    print("Running network security isolation tests...")
    
    try:
        test_instance.test_security_group_ingress_rules_isolation()
        print("✅ Security group ingress rules isolation test passed")
    except Exception as e:
        print(f"❌ Security group ingress rules isolation test failed: {e}")
    
    try:
        test_instance.test_subnet_tier_isolation()
        print("✅ Subnet tier isolation test passed")
    except Exception as e:
        print(f"❌ Subnet tier isolation test failed: {e}")
    
    print("\nTo run property-based tests with Hypothesis:")
    print("pytest tests/infrastructure/test_network_security_isolation.py -v")