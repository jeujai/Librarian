#!/usr/bin/env python3
"""
Property-Based Tests for Auto Scaling Responsiveness
Feature: aws-production-deployment, Property 6: Auto Scaling Responsiveness

This module tests that auto scaling policies are configured to respond appropriately
to load changes with proper thresholds, cooldowns, and scaling behaviors.
"""

import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, List, Any, Optional
import pytest
from hypothesis import given, strategies as st, settings, assume


class AutoScalingResponsivenessTest:
    """Test class for auto scaling responsiveness validation."""
    
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
    
    def validate_auto_scaling_targets(self, plan_data: Dict) -> List[str]:
        """Validate auto scaling target configuration."""
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
            
            # Validate capacity ranges
            if min_capacity < 1:
                issues.append("Auto scaling minimum capacity should be at least 1 for availability")
            
            if max_capacity <= min_capacity:
                issues.append("Auto scaling maximum capacity should be greater than minimum capacity")
            
            if max_capacity < 2:
                issues.append("Auto scaling maximum capacity should be at least 2 for high availability")
            
            # Check scaling range is reasonable
            scaling_range = max_capacity - min_capacity
            if scaling_range < 1:
                issues.append("Auto scaling should allow at least 1 additional instance for scaling")
            
            if scaling_range > 50:
                issues.append(f"Auto scaling range ({scaling_range}) is very large, consider smaller increments")
            
            # Validate resource ID format
            resource_id = target_values.get("resource_id", "")
            if not resource_id.startswith("service/"):
                issues.append("Auto scaling resource ID should reference an ECS service")
            
            # Validate scalable dimension
            scalable_dimension = target_values.get("scalable_dimension")
            if scalable_dimension != "ecs:service:DesiredCount":
                issues.append(f"Auto scaling should target ECS service desired count, got: {scalable_dimension}")
            
            # Validate service namespace
            service_namespace = target_values.get("service_namespace")
            if service_namespace != "ecs":
                issues.append(f"Auto scaling should use ECS service namespace, got: {service_namespace}")
        
        return issues
    
    def validate_auto_scaling_policies(self, plan_data: Dict) -> List[str]:
        """Validate auto scaling policy configuration."""
        issues = []
        
        # Find auto scaling policies
        scaling_policies = self.find_resources_in_plan(plan_data, "aws_appautoscaling_policy")
        if not scaling_policies:
            issues.append("No auto scaling policies found in plan")
            return issues
        
        cpu_policy_found = False
        memory_policy_found = False
        policy_names = []
        
        for policy in scaling_policies:
            policy_values = policy.get("values", {})
            policy_name = policy_values.get("name", "")
            policy_names.append(policy_name)
            
            # Check policy type
            policy_type = policy_values.get("policy_type")
            if policy_type != "TargetTrackingScaling":
                issues.append(f"Auto scaling policy should use TargetTrackingScaling for responsiveness, got: {policy_type}")
            
            # Validate target tracking configuration
            target_tracking_config = policy_values.get("target_tracking_scaling_policy_configuration", [])
            if not target_tracking_config:
                issues.append("Auto scaling policy should have target tracking configuration")
                continue
            
            tt_config = target_tracking_config[0]
            
            # Check predefined metric specification
            predefined_metric = tt_config.get("predefined_metric_specification", [])
            if not predefined_metric:
                issues.append("Auto scaling policy should use predefined metrics for reliability")
                continue
            
            metric_spec = predefined_metric[0]
            metric_type = metric_spec.get("predefined_metric_type")
            
            # Track which metrics are being monitored
            if metric_type == "ECSServiceAverageCPUUtilization":
                cpu_policy_found = True
            elif metric_type == "ECSServiceAverageMemoryUtilization":
                memory_policy_found = True
            else:
                issues.append(f"Auto scaling policy should use CPU or Memory utilization metrics, got: {metric_type}")
            
            # Validate target value
            target_value = tt_config.get("target_value", 0)
            if target_value <= 0:
                issues.append("Auto scaling target value should be greater than 0")
            elif target_value < 30:
                issues.append(f"Auto scaling target value ({target_value}%) is too low, may cause excessive scaling")
            elif target_value > 90:
                issues.append(f"Auto scaling target value ({target_value}%) is too high, may not scale in time")
            
            # Validate cooldown periods
            scale_in_cooldown = tt_config.get("scale_in_cooldown", 0)
            scale_out_cooldown = tt_config.get("scale_out_cooldown", 0)
            
            if scale_in_cooldown < 300:
                issues.append(f"Scale-in cooldown ({scale_in_cooldown}s) should be at least 300s to prevent flapping")
            elif scale_in_cooldown > 900:
                issues.append(f"Scale-in cooldown ({scale_in_cooldown}s) is too long, may delay cost optimization")
            
            if scale_out_cooldown < 300:
                issues.append(f"Scale-out cooldown ({scale_out_cooldown}s) should be at least 300s to prevent flapping")
            elif scale_out_cooldown > 600:
                issues.append(f"Scale-out cooldown ({scale_out_cooldown}s) is too long, may delay response to load")
            
            # Check that scale-out is faster than scale-in for responsiveness
            if scale_out_cooldown > scale_in_cooldown:
                issues.append("Scale-out cooldown should be <= scale-in cooldown for better responsiveness")
        
        # Ensure both CPU and memory policies exist for comprehensive scaling
        if not cpu_policy_found:
            issues.append("Auto scaling should include CPU utilization policy for performance responsiveness")
        
        if not memory_policy_found:
            issues.append("Auto scaling should include memory utilization policy for resource management")
        
        # Check for policy naming consistency
        if len(policy_names) > 1:
            for name in policy_names:
                if not any(keyword in name.lower() for keyword in ["cpu", "memory"]):
                    issues.append(f"Auto scaling policy name '{name}' should indicate metric type (cpu/memory)")
        
        return issues
    
    def validate_scaling_responsiveness_metrics(self, plan_data: Dict) -> List[str]:
        """Validate that scaling metrics are appropriate for responsiveness."""
        issues = []
        
        # Find CloudWatch alarms (if any are configured for additional monitoring)
        cloudwatch_alarms = self.find_resources_in_plan(plan_data, "aws_cloudwatch_metric_alarm")
        
        # Check if there are any custom scaling alarms
        scaling_alarms = []
        for alarm in cloudwatch_alarms:
            alarm_values = alarm.get("values", {})
            alarm_name = alarm_values.get("alarm_name", "")
            metric_name = alarm_values.get("metric_name", "")
            
            if any(keyword in alarm_name.lower() or keyword in metric_name.lower() 
                   for keyword in ["cpu", "memory", "scaling", "utilization"]):
                scaling_alarms.append(alarm_values)
        
        # If custom alarms exist, validate their configuration
        for alarm in scaling_alarms:
            evaluation_periods = alarm.get("evaluation_periods", 0)
            if evaluation_periods < 2:
                issues.append("CloudWatch alarms should evaluate at least 2 periods to avoid false positives")
            elif evaluation_periods > 5:
                issues.append("CloudWatch alarms should not evaluate too many periods to maintain responsiveness")
            
            period = alarm.get("period", 0)
            if period < 60:
                issues.append("CloudWatch alarm period should be at least 60 seconds for stable metrics")
            elif period > 300:
                issues.append("CloudWatch alarm period should not exceed 300 seconds for responsiveness")
            
            # Check threshold values
            threshold = alarm.get("threshold", 0)
            comparison_operator = alarm.get("comparison_operator", "")
            
            if "cpu" in alarm.get("metric_name", "").lower():
                if "GreaterThanThreshold" in comparison_operator and threshold > 90:
                    issues.append(f"CPU alarm threshold ({threshold}%) is too high for responsive scaling")
                elif "LessThanThreshold" in comparison_operator and threshold < 20:
                    issues.append(f"CPU alarm threshold ({threshold}%) is too low, may cause excessive scale-in")
        
        return issues
    
    def validate_load_balancer_scaling_integration(self, plan_data: Dict) -> List[str]:
        """Validate that load balancer configuration supports auto scaling."""
        issues = []
        
        # Find target groups
        target_groups = self.find_resources_in_plan(plan_data, "aws_lb_target_group")
        
        for tg in target_groups:
            tg_values = tg.get("values", {})
            
            # Check deregistration delay for scaling responsiveness
            deregistration_delay = tg_values.get("deregistration_delay", 300)
            if deregistration_delay > 60:
                issues.append(f"Target group deregistration delay ({deregistration_delay}s) should be <= 60s for faster scaling")
            
            # Check health check configuration for scaling
            health_check = tg_values.get("health_check", [])
            if health_check:
                hc_config = health_check[0]
                
                interval = hc_config.get("interval", 0)
                timeout = hc_config.get("timeout", 0)
                healthy_threshold = hc_config.get("healthy_threshold", 0)
                
                # Calculate time to mark instance healthy
                time_to_healthy = interval * healthy_threshold + timeout
                if time_to_healthy > 120:
                    issues.append(f"Health check configuration takes too long ({time_to_healthy}s) to mark instances healthy")
                
                # Check that health check is frequent enough for scaling
                if interval > 30:
                    issues.append(f"Health check interval ({interval}s) should be <= 30s for responsive scaling")
        
        # Find load balancers
        load_balancers = self.find_resources_in_plan(plan_data, "aws_lb")
        
        for lb in load_balancers:
            lb_values = lb.get("values", {})
            
            # Check cross-zone load balancing for even distribution during scaling
            cross_zone_lb = lb_values.get("enable_cross_zone_load_balancing", False)
            if not cross_zone_lb:
                issues.append("Load balancer should enable cross-zone load balancing for even traffic distribution during scaling")
        
        return issues
    
    def calculate_scaling_responsiveness_score(self, plan_data: Dict) -> Dict[str, Any]:
        """Calculate a responsiveness score based on configuration."""
        score_factors = {
            "target_tracking_policies": 0,
            "appropriate_thresholds": 0,
            "fast_cooldowns": 0,
            "multi_metric_scaling": 0,
            "fast_health_checks": 0
        }
        
        # Check auto scaling policies
        scaling_policies = self.find_resources_in_plan(plan_data, "aws_appautoscaling_policy")
        cpu_policy = False
        memory_policy = False
        
        for policy in scaling_policies:
            policy_values = policy.get("values", {})
            
            if policy_values.get("policy_type") == "TargetTrackingScaling":
                score_factors["target_tracking_policies"] += 1
            
            tt_config = policy_values.get("target_tracking_scaling_policy_configuration", [])
            if tt_config:
                config = tt_config[0]
                target_value = config.get("target_value", 0)
                
                # Check for appropriate thresholds (50-80% range)
                if 50 <= target_value <= 80:
                    score_factors["appropriate_thresholds"] += 1
                
                # Check for fast cooldowns (300-600s range)
                scale_out_cooldown = config.get("scale_out_cooldown", 0)
                if 300 <= scale_out_cooldown <= 600:
                    score_factors["fast_cooldowns"] += 1
                
                # Check metric types
                predefined_metric = config.get("predefined_metric_specification", [])
                if predefined_metric:
                    metric_type = predefined_metric[0].get("predefined_metric_type")
                    if metric_type == "ECSServiceAverageCPUUtilization":
                        cpu_policy = True
                    elif metric_type == "ECSServiceAverageMemoryUtilization":
                        memory_policy = True
        
        # Multi-metric scaling bonus
        if cpu_policy and memory_policy:
            score_factors["multi_metric_scaling"] = 1
        
        # Check health check responsiveness
        target_groups = self.find_resources_in_plan(plan_data, "aws_lb_target_group")
        for tg in target_groups:
            tg_values = tg.get("values", {})
            health_check = tg_values.get("health_check", [])
            
            if health_check:
                hc_config = health_check[0]
                interval = hc_config.get("interval", 0)
                healthy_threshold = hc_config.get("healthy_threshold", 0)
                
                # Fast health checks (< 60s to healthy)
                if interval * healthy_threshold < 60:
                    score_factors["fast_health_checks"] = 1
        
        # Calculate overall score (0-100)
        max_score = len(score_factors)
        actual_score = sum(score_factors.values())
        responsiveness_score = (actual_score / max_score) * 100
        
        return {
            "score": responsiveness_score,
            "factors": score_factors,
            "recommendations": self._get_responsiveness_recommendations(score_factors)
        }
    
    def _get_responsiveness_recommendations(self, score_factors: Dict[str, int]) -> List[str]:
        """Get recommendations for improving scaling responsiveness."""
        recommendations = []
        
        if score_factors["target_tracking_policies"] == 0:
            recommendations.append("Implement target tracking scaling policies for automatic responsiveness")
        
        if score_factors["appropriate_thresholds"] == 0:
            recommendations.append("Set target values between 50-80% for optimal scaling responsiveness")
        
        if score_factors["fast_cooldowns"] == 0:
            recommendations.append("Configure scale-out cooldowns between 300-600s for responsive scaling")
        
        if score_factors["multi_metric_scaling"] == 0:
            recommendations.append("Implement both CPU and memory scaling policies for comprehensive responsiveness")
        
        if score_factors["fast_health_checks"] == 0:
            recommendations.append("Configure health checks to mark instances healthy within 60 seconds")
        
        return recommendations


# Property-based test strategies
@st.composite
def auto_scaling_config(draw):
    """Generate auto scaling configuration test scenarios."""
    min_capacity = draw(st.integers(min_value=1, max_value=5))
    max_capacity = draw(st.integers(min_value=min_capacity + 1, max_value=20))
    
    return {
        "aws_region": draw(st.sampled_from(["us-east-1", "us-west-2", "eu-west-1"])),
        "environment": draw(st.sampled_from(["staging", "production"])),
        "project_name": draw(st.text(min_size=3, max_size=20, alphabet=st.characters(whitelist_categories=("Ll", "Nd"), whitelist_characters="-"))),
        "vpc_cidr": draw(st.sampled_from(["10.0.0.0/16", "172.16.0.0/16"])),
        "az_count": draw(st.integers(min_value=2, max_value=3)),
        
        # Auto scaling configuration
        "ecs_min_capacity": min_capacity,
        "ecs_max_capacity": max_capacity,
        "ecs_desired_count": draw(st.integers(min_value=min_capacity, max_value=max_capacity)),
        
        # Scaling thresholds
        "cpu_target_value": draw(st.floats(min_value=40.0, max_value=85.0)),
        "memory_target_value": draw(st.floats(min_value=50.0, max_value=90.0)),
        
        # Cooldown periods
        "scale_up_cooldown": draw(st.integers(min_value=300, max_value=600)),
        "scale_down_cooldown": draw(st.integers(min_value=300, max_value=900)),
        
        # Application configuration
        "app_port": draw(st.integers(min_value=3000, max_value=9000)),
        "health_check_path": "/health/simple",
        
        # Database configuration (required)
        "neptune_cluster_identifier": "test-neptune",
        "opensearch_domain_name": "test-opensearch",
        "skip_final_snapshot": True,
        "log_retention_days": draw(st.integers(min_value=7, max_value=30)),
    }


class TestAutoScalingResponsiveness:
    """Property-based tests for auto scaling responsiveness."""
    
    def setup_method(self):
        """Set up test environment."""
        self.scaling_test = AutoScalingResponsivenessTest()
    
    @given(config=auto_scaling_config())
    @settings(max_examples=5, deadline=120000)  # 2 minute timeout
    def test_auto_scaling_target_configuration(self, config):
        """
        Property test: For any auto scaling configuration,
        scaling targets should have appropriate capacity ranges and settings.
        
        **Feature: aws-production-deployment, Property 6: Auto Scaling Responsiveness**
        **Validates: Requirements 2.5, 6.2, 8.5**
        """
        # Skip if Terraform not available
        if not subprocess.run(["which", "terraform"], capture_output=True).returncode == 0:
            pytest.skip("Terraform not available")
        
        plan_data = self.scaling_test.get_terraform_plan_json(config)
        assume(plan_data is not None)
        
        # Validate auto scaling targets
        issues = self.scaling_test.validate_auto_scaling_targets(plan_data)
        
        assert len(issues) == 0, f"Auto scaling target issues: {'; '.join(issues)}"
    
    @given(config=auto_scaling_config())
    @settings(max_examples=5, deadline=120000)
    def test_auto_scaling_policy_responsiveness(self, config):
        """
        Property test: For any auto scaling configuration,
        scaling policies should be configured for responsive scaling.
        
        **Feature: aws-production-deployment, Property 6: Auto Scaling Responsiveness**
        **Validates: Requirements 2.5, 6.2, 8.5**
        """
        # Skip if Terraform not available
        if not subprocess.run(["which", "terraform"], capture_output=True).returncode == 0:
            pytest.skip("Terraform not available")
        
        plan_data = self.scaling_test.get_terraform_plan_json(config)
        assume(plan_data is not None)
        
        # Validate auto scaling policies
        issues = self.scaling_test.validate_auto_scaling_policies(plan_data)
        
        assert len(issues) == 0, f"Auto scaling policy issues: {'; '.join(issues)}"
    
    @given(config=auto_scaling_config())
    @settings(max_examples=3, deadline=120000)
    def test_load_balancer_scaling_integration(self, config):
        """
        Property test: For any auto scaling configuration,
        load balancer should be configured to support responsive scaling.
        
        **Feature: aws-production-deployment, Property 6: Auto Scaling Responsiveness**
        **Validates: Requirements 2.5, 6.2, 8.5**
        """
        # Skip if Terraform not available
        if not subprocess.run(["which", "terraform"], capture_output=True).returncode == 0:
            pytest.skip("Terraform not available")
        
        plan_data = self.scaling_test.get_terraform_plan_json(config)
        assume(plan_data is not None)
        
        # Validate load balancer scaling integration
        issues = self.scaling_test.validate_load_balancer_scaling_integration(plan_data)
        
        assert len(issues) == 0, f"Load balancer scaling integration issues: {'; '.join(issues)}"
    
    def test_scaling_responsiveness_score(self):
        """
        Test that auto scaling configuration achieves good responsiveness score.
        
        **Feature: aws-production-deployment, Property 6: Auto Scaling Responsiveness**
        **Validates: Requirements 2.5, 6.2, 8.5**
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
            "scale_up_cooldown": 300,
            "scale_down_cooldown": 300,
            "neptune_cluster_identifier": "test-neptune",
            "opensearch_domain_name": "test-opensearch",
            "skip_final_snapshot": True,
        }
        
        plan_data = self.scaling_test.get_terraform_plan_json(config)
        assert plan_data is not None, "Should be able to generate Terraform plan"
        
        # Calculate responsiveness score
        score_result = self.scaling_test.calculate_scaling_responsiveness_score(plan_data)
        
        assert score_result["score"] >= 60, f"Scaling responsiveness score ({score_result['score']}) should be at least 60%"
        
        # Check that we have both CPU and memory policies
        assert score_result["factors"]["multi_metric_scaling"] == 1, "Should have both CPU and memory scaling policies"
    
    def test_scaling_threshold_optimization(self):
        """
        Test that scaling thresholds are optimized for responsiveness vs stability.
        
        **Feature: aws-production-deployment, Property 6: Auto Scaling Responsiveness**
        **Validates: Requirements 2.5, 6.2, 8.5**
        """
        # Skip if Terraform not available
        if not subprocess.run(["which", "terraform"], capture_output=True).returncode == 0:
            pytest.skip("Terraform not available")
        
        config = {
            "aws_region": "us-east-1",
            "environment": "production",
            "project_name": "test-project",
            "cpu_target_value": 70.0,  # Good balance
            "memory_target_value": 80.0,  # Good balance
            "scale_up_cooldown": 300,  # Responsive
            "scale_down_cooldown": 600,  # Stable
            "neptune_cluster_identifier": "test-neptune",
            "opensearch_domain_name": "test-opensearch",
            "skip_final_snapshot": True,
        }
        
        plan_data = self.scaling_test.get_terraform_plan_json(config)
        assert plan_data is not None, "Should be able to generate Terraform plan"
        
        # Find scaling policies and validate thresholds
        scaling_policies = self.scaling_test.find_resources_in_plan(plan_data, "aws_appautoscaling_policy")
        assert len(scaling_policies) >= 2, "Should have at least 2 scaling policies (CPU and memory)"
        
        for policy in scaling_policies:
            policy_values = policy.get("values", {})
            tt_config = policy_values.get("target_tracking_scaling_policy_configuration", [])
            
            if tt_config:
                config_data = tt_config[0]
                target_value = config_data.get("target_value", 0)
                
                # Validate threshold is in optimal range
                assert 50 <= target_value <= 85, f"Target value ({target_value}) should be between 50-85% for optimal responsiveness"
                
                # Validate cooldowns
                scale_out_cooldown = config_data.get("scale_out_cooldown", 0)
                scale_in_cooldown = config_data.get("scale_in_cooldown", 0)
                
                assert scale_out_cooldown >= 300, "Scale-out cooldown should be at least 300s"
                assert scale_in_cooldown >= 300, "Scale-in cooldown should be at least 300s"
                assert scale_out_cooldown <= scale_in_cooldown, "Scale-out should be faster than or equal to scale-in"


if __name__ == "__main__":
    # Run basic validation tests
    test_instance = TestAutoScalingResponsiveness()
    test_instance.setup_method()
    
    print("Running auto scaling responsiveness tests...")
    
    try:
        test_instance.test_scaling_responsiveness_score()
        print("✅ Scaling responsiveness score test passed")
    except Exception as e:
        print(f"❌ Scaling responsiveness score test failed: {e}")
    
    try:
        test_instance.test_scaling_threshold_optimization()
        print("✅ Scaling threshold optimization test passed")
    except Exception as e:
        print(f"❌ Scaling threshold optimization test failed: {e}")
    
    print("\nTo run property-based tests with Hypothesis:")
    print("pytest tests/infrastructure/test_auto_scaling_responsiveness.py -v")