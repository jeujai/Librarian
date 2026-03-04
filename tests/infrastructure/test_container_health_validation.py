#!/usr/bin/env python3
"""
Property-Based Tests for Container Health Validation
Feature: aws-production-deployment, Property 5: Container Health Validation

This module tests that ECS containers are configured with proper health checks,
monitoring, logging, and resource allocation for production workloads.
"""

import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, List, Any, Optional
import pytest
from hypothesis import given, strategies as st, settings, assume


class ContainerHealthValidationTest:
    """Test class for container health validation."""
    
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
    
    def validate_ecs_task_definition_health(self, plan_data: Dict) -> List[str]:
        """Validate ECS task definition health configuration."""
        issues = []
        
        # Find ECS task definitions
        task_definitions = self.find_resources_in_plan(plan_data, "aws_ecs_task_definition")
        if not task_definitions:
            issues.append("No ECS task definitions found in plan")
            return issues
        
        for task_def in task_definitions:
            task_values = task_def.get("values", {})
            
            # Check CPU and memory allocation
            cpu = task_values.get("cpu")
            memory = task_values.get("memory")
            
            if not cpu:
                issues.append("ECS task definition should specify CPU allocation")
            else:
                try:
                    cpu_int = int(cpu)
                    if cpu_int < 256:
                        issues.append(f"ECS task CPU allocation ({cpu_int}) should be at least 256 for production")
                except ValueError:
                    issues.append(f"ECS task CPU allocation should be a valid integer, got: {cpu}")
            
            if not memory:
                issues.append("ECS task definition should specify memory allocation")
            else:
                try:
                    memory_int = int(memory)
                    if memory_int < 512:
                        issues.append(f"ECS task memory allocation ({memory_int}MB) should be at least 512MB for production")
                except ValueError:
                    issues.append(f"ECS task memory allocation should be a valid integer, got: {memory}")
            
            # Check network mode
            network_mode = task_values.get("network_mode")
            if network_mode != "awsvpc":
                issues.append(f"ECS task should use 'awsvpc' network mode for security, got: {network_mode}")
            
            # Check requires compatibilities
            requires_compatibilities = task_values.get("requires_compatibilities", [])
            if "FARGATE" not in requires_compatibilities:
                issues.append("ECS task should be compatible with Fargate for serverless deployment")
            
            # Check execution and task roles
            execution_role_arn = task_values.get("execution_role_arn")
            task_role_arn = task_values.get("task_role_arn")
            
            if not execution_role_arn:
                issues.append("ECS task should have execution role for container management")
            
            if not task_role_arn:
                issues.append("ECS task should have task role for application permissions")
            
            # Parse container definitions
            container_definitions_str = task_values.get("container_definitions")
            if container_definitions_str:
                try:
                    container_definitions = json.loads(container_definitions_str)
                    for container in container_definitions:
                        # Check health check configuration
                        health_check = container.get("healthCheck")
                        if not health_check:
                            issues.append(f"Container '{container.get('name', 'unknown')}' should have health check configured")
                        else:
                            # Validate health check parameters
                            command = health_check.get("command", [])
                            if not command:
                                issues.append(f"Container '{container.get('name', 'unknown')}' health check should have command")
                            
                            interval = health_check.get("interval", 0)
                            if interval < 30:
                                issues.append(f"Container '{container.get('name', 'unknown')}' health check interval should be at least 30 seconds")
                            
                            timeout = health_check.get("timeout", 0)
                            if timeout < 5:
                                issues.append(f"Container '{container.get('name', 'unknown')}' health check timeout should be at least 5 seconds")
                            
                            retries = health_check.get("retries", 0)
                            if retries < 3:
                                issues.append(f"Container '{container.get('name', 'unknown')}' health check should have at least 3 retries")
                        
                        # Check logging configuration
                        log_config = container.get("logConfiguration")
                        if not log_config:
                            issues.append(f"Container '{container.get('name', 'unknown')}' should have logging configured")
                        else:
                            log_driver = log_config.get("logDriver")
                            if log_driver != "awslogs":
                                issues.append(f"Container '{container.get('name', 'unknown')}' should use 'awslogs' driver for CloudWatch integration")
                        
                        # Check port mappings
                        port_mappings = container.get("portMappings", [])
                        if not port_mappings:
                            issues.append(f"Container '{container.get('name', 'unknown')}' should have port mappings configured")
                        
                        # Check essential flag
                        essential = container.get("essential", False)
                        if not essential:
                            issues.append(f"Container '{container.get('name', 'unknown')}' should be marked as essential")
                
                except json.JSONDecodeError:
                    issues.append("ECS task definition container definitions should be valid JSON")
        
        return issues
    
    def validate_ecs_service_health(self, plan_data: Dict) -> List[str]:
        """Validate ECS service health and deployment configuration."""
        issues = []
        
        # Find ECS services
        ecs_services = self.find_resources_in_plan(plan_data, "aws_ecs_service")
        if not ecs_services:
            issues.append("No ECS services found in plan")
            return issues
        
        for service in ecs_services:
            service_values = service.get("values", {})
            
            # Check desired count
            desired_count = service_values.get("desired_count", 0)
            if desired_count < 1:
                issues.append("ECS service should have at least 1 desired task for availability")
            
            # Check launch type
            launch_type = service_values.get("launch_type")
            if launch_type != "FARGATE":
                issues.append(f"ECS service should use Fargate launch type for serverless deployment, got: {launch_type}")
            
            # Check network configuration
            network_config = service_values.get("network_configuration", [])
            if not network_config:
                issues.append("ECS service should have network configuration")
            else:
                net_config = network_config[0]
                security_groups = net_config.get("security_groups", [])
                subnets = net_config.get("subnets", [])
                assign_public_ip = net_config.get("assign_public_ip", True)
                
                if not security_groups:
                    issues.append("ECS service should have security groups configured")
                
                if not subnets:
                    issues.append("ECS service should have subnets configured")
                
                if assign_public_ip:
                    issues.append("ECS service should not assign public IP for security (should be in private subnets)")
            
            # Check load balancer configuration
            load_balancer = service_values.get("load_balancer", [])
            if not load_balancer:
                issues.append("ECS service should have load balancer configuration for high availability")
            else:
                lb_config = load_balancer[0]
                target_group_arn = lb_config.get("target_group_arn")
                container_name = lb_config.get("container_name")
                container_port = lb_config.get("container_port")
                
                if not target_group_arn:
                    issues.append("ECS service load balancer should specify target group ARN")
                
                if not container_name:
                    issues.append("ECS service load balancer should specify container name")
                
                if not container_port:
                    issues.append("ECS service load balancer should specify container port")
            
            # Check deployment configuration
            deployment_config = service_values.get("deployment_configuration", [])
            if deployment_config:
                deploy_config = deployment_config[0]
                max_percent = deploy_config.get("maximum_percent", 100)
                min_healthy_percent = deploy_config.get("minimum_healthy_percent", 0)
                
                if max_percent < 150:
                    issues.append("ECS service maximum percent should be at least 150% for rolling deployments")
                
                if min_healthy_percent < 50:
                    issues.append("ECS service minimum healthy percent should be at least 50% for availability")
                
                # Check deployment circuit breaker
                circuit_breaker = deploy_config.get("deployment_circuit_breaker", [])
                if circuit_breaker:
                    cb_config = circuit_breaker[0]
                    enable = cb_config.get("enable", False)
                    rollback = cb_config.get("rollback", False)
                    
                    if not enable:
                        issues.append("ECS service should enable deployment circuit breaker for failure detection")
                    
                    if not rollback:
                        issues.append("ECS service should enable automatic rollback on deployment failure")
            
            # Check execute command capability
            enable_execute_command = service_values.get("enable_execute_command", False)
            if not enable_execute_command:
                issues.append("ECS service should enable execute command for debugging and maintenance")
        
        return issues
    
    def validate_load_balancer_health(self, plan_data: Dict) -> List[str]:
        """Validate Application Load Balancer health configuration."""
        issues = []
        
        # Find ALB target groups
        target_groups = self.find_resources_in_plan(plan_data, "aws_lb_target_group")
        if not target_groups:
            issues.append("No ALB target groups found in plan")
            return issues
        
        for tg in target_groups:
            tg_values = tg.get("values", {})
            
            # Check target type
            target_type = tg_values.get("target_type")
            if target_type != "ip":
                issues.append(f"Target group should use 'ip' target type for Fargate compatibility, got: {target_type}")
            
            # Check health check configuration
            health_check = tg_values.get("health_check", [])
            if not health_check:
                issues.append("Target group should have health check configuration")
            else:
                hc_config = health_check[0]
                
                enabled = hc_config.get("enabled", False)
                if not enabled:
                    issues.append("Target group health check should be enabled")
                
                healthy_threshold = hc_config.get("healthy_threshold", 0)
                if healthy_threshold < 2:
                    issues.append("Target group healthy threshold should be at least 2")
                
                unhealthy_threshold = hc_config.get("unhealthy_threshold", 0)
                if unhealthy_threshold < 2:
                    issues.append("Target group unhealthy threshold should be at least 2")
                
                timeout = hc_config.get("timeout", 0)
                if timeout < 5:
                    issues.append("Target group health check timeout should be at least 5 seconds")
                
                interval = hc_config.get("interval", 0)
                if interval < 30:
                    issues.append("Target group health check interval should be at least 30 seconds")
                
                path = hc_config.get("path")
                if not path:
                    issues.append("Target group health check should specify a path")
                
                matcher = hc_config.get("matcher")
                if not matcher:
                    issues.append("Target group health check should specify success codes")
            
            # Check deregistration delay
            deregistration_delay = tg_values.get("deregistration_delay", 300)
            if deregistration_delay > 60:
                issues.append(f"Target group deregistration delay ({deregistration_delay}s) should be <= 60s for faster deployments")
        
        return issues
    
    def validate_auto_scaling_configuration(self, plan_data: Dict) -> List[str]:
        """Validate auto scaling configuration for containers."""
        issues = []
        
        # Find auto scaling targets
        scaling_targets = self.find_resources_in_plan(plan_data, "aws_appautoscaling_target")
        if not scaling_targets:
            issues.append("No auto scaling targets found in plan")
            return issues
        
        for target in scaling_targets:
            target_values = target.get("values", {})
            
            min_capacity = target_values.get("min_capacity", 0)
            max_capacity = target_values.get("max_capacity", 0)
            
            if min_capacity < 1:
                issues.append("Auto scaling minimum capacity should be at least 1")
            
            if max_capacity <= min_capacity:
                issues.append("Auto scaling maximum capacity should be greater than minimum capacity")
            
            if max_capacity < 2:
                issues.append("Auto scaling maximum capacity should be at least 2 for high availability")
            
            scalable_dimension = target_values.get("scalable_dimension")
            if scalable_dimension != "ecs:service:DesiredCount":
                issues.append(f"Auto scaling should target ECS service desired count, got: {scalable_dimension}")
        
        # Find auto scaling policies
        scaling_policies = self.find_resources_in_plan(plan_data, "aws_appautoscaling_policy")
        if not scaling_policies:
            issues.append("No auto scaling policies found in plan")
            return issues
        
        cpu_policy_found = False
        memory_policy_found = False
        
        for policy in scaling_policies:
            policy_values = policy.get("values", {})
            
            policy_type = policy_values.get("policy_type")
            if policy_type != "TargetTrackingScaling":
                issues.append(f"Auto scaling policy should use target tracking scaling, got: {policy_type}")
            
            # Check target tracking configuration
            target_tracking_config = policy_values.get("target_tracking_scaling_policy_configuration", [])
            if target_tracking_config:
                tt_config = target_tracking_config[0]
                
                predefined_metric = tt_config.get("predefined_metric_specification", [])
                if predefined_metric:
                    metric_type = predefined_metric[0].get("predefined_metric_type")
                    if metric_type == "ECSServiceAverageCPUUtilization":
                        cpu_policy_found = True
                    elif metric_type == "ECSServiceAverageMemoryUtilization":
                        memory_policy_found = True
                
                target_value = tt_config.get("target_value", 0)
                if target_value <= 0 or target_value > 90:
                    issues.append(f"Auto scaling target value should be between 1-90%, got: {target_value}")
                
                scale_in_cooldown = tt_config.get("scale_in_cooldown", 0)
                scale_out_cooldown = tt_config.get("scale_out_cooldown", 0)
                
                if scale_in_cooldown < 300:
                    issues.append("Auto scaling scale-in cooldown should be at least 300 seconds")
                
                if scale_out_cooldown < 300:
                    issues.append("Auto scaling scale-out cooldown should be at least 300 seconds")
        
        if not cpu_policy_found:
            issues.append("Auto scaling should include CPU utilization policy")
        
        if not memory_policy_found:
            issues.append("Auto scaling should include memory utilization policy")
        
        return issues


# Property-based test strategies
@st.composite
def container_health_config(draw):
    """Generate container health configuration test scenarios."""
    return {
        "aws_region": draw(st.sampled_from(["us-east-1", "us-west-2", "eu-west-1"])),
        "environment": draw(st.sampled_from(["staging", "production"])),
        "project_name": draw(st.text(min_size=3, max_size=20, alphabet=st.characters(whitelist_categories=("Ll", "Nd"), whitelist_characters="-"))),
        "vpc_cidr": draw(st.sampled_from(["10.0.0.0/16", "172.16.0.0/16"])),
        "az_count": draw(st.integers(min_value=2, max_value=3)),
        
        # ECS configuration
        "ecs_cpu": draw(st.sampled_from([256, 512, 1024, 2048, 4096])),
        "ecs_memory": draw(st.integers(min_value=512, max_value=8192)),
        "ecs_desired_count": draw(st.integers(min_value=1, max_value=5)),
        "ecs_min_capacity": draw(st.integers(min_value=1, max_value=3)),
        "ecs_max_capacity": draw(st.integers(min_value=2, max_value=10)),
        
        # Application configuration
        "app_port": draw(st.integers(min_value=3000, max_value=9000)),
        "health_check_path": draw(st.sampled_from(["/health", "/health/simple", "/api/health"])),
        
        # Auto scaling configuration
        "cpu_target_value": draw(st.floats(min_value=50.0, max_value=80.0)),
        "memory_target_value": draw(st.floats(min_value=60.0, max_value=85.0)),
        "scale_up_cooldown": draw(st.integers(min_value=300, max_value=600)),
        "scale_down_cooldown": draw(st.integers(min_value=300, max_value=600)),
        
        # Database configuration (required)
        "neptune_cluster_identifier": "test-neptune",
        "opensearch_domain_name": "test-opensearch",
        "skip_final_snapshot": True,
        "log_retention_days": draw(st.integers(min_value=7, max_value=30)),
        "enable_container_insights": True,
    }


class TestContainerHealthValidation:
    """Property-based tests for container health validation."""
    
    def setup_method(self):
        """Set up test environment."""
        self.health_test = ContainerHealthValidationTest()
    
    @given(config=container_health_config())
    @settings(max_examples=3, deadline=120000)  # 2 minute timeout
    def test_ecs_task_definition_health_configuration(self, config):
        """
        Property test: For any container configuration,
        ECS task definitions should have proper health checks and resource allocation.
        
        **Feature: aws-production-deployment, Property 5: Container Health Validation**
        **Validates: Requirements 2.1, 2.7**
        """
        # Skip if Terraform not available
        if not subprocess.run(["which", "terraform"], capture_output=True).returncode == 0:
            pytest.skip("Terraform not available")
        
        plan_data = self.health_test.get_terraform_plan_json(config)
        assume(plan_data is not None)
        
        # Validate ECS task definition health
        issues = self.health_test.validate_ecs_task_definition_health(plan_data)
        
        assert len(issues) == 0, f"ECS task definition health issues: {'; '.join(issues)}"
    
    @given(config=container_health_config())
    @settings(max_examples=3, deadline=120000)
    def test_ecs_service_health_configuration(self, config):
        """
        Property test: For any container configuration,
        ECS services should have proper deployment and health settings.
        
        **Feature: aws-production-deployment, Property 5: Container Health Validation**
        **Validates: Requirements 2.1, 2.7**
        """
        # Skip if Terraform not available
        if not subprocess.run(["which", "terraform"], capture_output=True).returncode == 0:
            pytest.skip("Terraform not available")
        
        plan_data = self.health_test.get_terraform_plan_json(config)
        assume(plan_data is not None)
        
        # Validate ECS service health
        issues = self.health_test.validate_ecs_service_health(plan_data)
        
        assert len(issues) == 0, f"ECS service health issues: {'; '.join(issues)}"
    
    @given(config=container_health_config())
    @settings(max_examples=3, deadline=120000)
    def test_load_balancer_health_configuration(self, config):
        """
        Property test: For any container configuration,
        load balancers should have proper health check settings.
        
        **Feature: aws-production-deployment, Property 5: Container Health Validation**
        **Validates: Requirements 2.1, 2.7**
        """
        # Skip if Terraform not available
        if not subprocess.run(["which", "terraform"], capture_output=True).returncode == 0:
            pytest.skip("Terraform not available")
        
        plan_data = self.health_test.get_terraform_plan_json(config)
        assume(plan_data is not None)
        
        # Validate load balancer health
        issues = self.health_test.validate_load_balancer_health(plan_data)
        
        assert len(issues) == 0, f"Load balancer health issues: {'; '.join(issues)}"
    
    def test_container_resource_allocation(self):
        """
        Test that containers have appropriate resource allocation for production.
        
        **Feature: aws-production-deployment, Property 5: Container Health Validation**
        **Validates: Requirements 2.1, 2.7**
        """
        # Skip if Terraform not available
        if not subprocess.run(["which", "terraform"], capture_output=True).returncode == 0:
            pytest.skip("Terraform not available")
        
        config = {
            "aws_region": "us-east-1",
            "environment": "production",
            "project_name": "test-project",
            "ecs_cpu": 1024,
            "ecs_memory": 2048,
            "ecs_desired_count": 2,
            "app_port": 8000,
            "health_check_path": "/health/simple",
            "neptune_cluster_identifier": "test-neptune",
            "opensearch_domain_name": "test-opensearch",
            "skip_final_snapshot": True,
        }
        
        plan_data = self.health_test.get_terraform_plan_json(config)
        assert plan_data is not None, "Should be able to generate Terraform plan"
        
        # Check ECS task definitions
        task_definitions = self.health_test.find_resources_in_plan(plan_data, "aws_ecs_task_definition")
        assert len(task_definitions) > 0, "Should have ECS task definitions"
        
        task_def = task_definitions[0]["values"]
        assert int(task_def.get("cpu", 0)) >= 256, "Task should have adequate CPU allocation"
        assert int(task_def.get("memory", 0)) >= 512, "Task should have adequate memory allocation"
        assert task_def.get("network_mode") == "awsvpc", "Task should use awsvpc network mode"
        assert "FARGATE" in task_def.get("requires_compatibilities", []), "Task should support Fargate"
    
    def test_auto_scaling_configuration(self):
        """
        Test that auto scaling is properly configured for container health.
        
        **Feature: aws-production-deployment, Property 5: Container Health Validation**
        **Validates: Requirements 2.1, 2.7**
        """
        # Skip if Terraform not available
        if not subprocess.run(["which", "terraform"], capture_output=True).returncode == 0:
            pytest.skip("Terraform not available")
        
        config = {
            "aws_region": "us-east-1",
            "environment": "production",
            "project_name": "test-project",
            "ecs_min_capacity": 2,
            "ecs_max_capacity": 10,
            "cpu_target_value": 70.0,
            "memory_target_value": 80.0,
            "neptune_cluster_identifier": "test-neptune",
            "opensearch_domain_name": "test-opensearch",
            "skip_final_snapshot": True,
        }
        
        plan_data = self.health_test.get_terraform_plan_json(config)
        assert plan_data is not None, "Should be able to generate Terraform plan"
        
        # Validate auto scaling configuration
        issues = self.health_test.validate_auto_scaling_configuration(plan_data)
        assert len(issues) == 0, f"Auto scaling configuration issues: {'; '.join(issues)}"


if __name__ == "__main__":
    # Run basic validation tests
    test_instance = TestContainerHealthValidation()
    test_instance.setup_method()
    
    print("Running container health validation tests...")
    
    try:
        test_instance.test_container_resource_allocation()
        print("✅ Container resource allocation test passed")
    except Exception as e:
        print(f"❌ Container resource allocation test failed: {e}")
    
    try:
        test_instance.test_auto_scaling_configuration()
        print("✅ Auto scaling configuration test passed")
    except Exception as e:
        print(f"❌ Auto scaling configuration test failed: {e}")
    
    print("\nTo run property-based tests with Hypothesis:")
    print("pytest tests/infrastructure/test_container_health_validation.py -v")