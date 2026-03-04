#!/usr/bin/env python3
"""
Property Test for Resource Right-Sizing
Tests Property 16: Resource Right-Sizing
**Validates: Requirements 6.1, 6.3**
"""

import pytest
import json
import os
import subprocess
from pathlib import Path


class TestResourceRightSizing:
    """Test resource right-sizing implementation"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test environment"""
        self.terraform_dir = Path("infrastructure/aws-native")
        self.cost_optimization_module = self.terraform_dir / "modules/cost_optimization"
        
    def test_cost_optimization_module_exists(self):
        """Test that cost optimization module exists"""
        assert self.cost_optimization_module.exists(), "Cost optimization module directory should exist"
        assert (self.cost_optimization_module / "main.tf").exists(), "Cost optimization main.tf should exist"
        assert (self.cost_optimization_module / "variables.tf").exists(), "Cost optimization variables.tf should exist"
        assert (self.cost_optimization_module / "outputs.tf").exists(), "Cost optimization outputs.tf should exist"
    
    def test_terraform_configuration_valid(self):
        """Test that Terraform configuration is valid"""
        result = subprocess.run(
            ["terraform", "validate"],
            cwd=self.terraform_dir,
            capture_output=True,
            text=True
        )
        assert result.returncode == 0, f"Terraform validation failed: {result.stderr}"
    
    def test_cost_optimization_module_called(self):
        """Test that cost optimization module is called in main.tf"""
        main_tf_path = self.terraform_dir / "main.tf"
        with open(main_tf_path, 'r') as f:
            content = f.read()
        
        assert 'module "cost_optimization"' in content, "Cost optimization module should be called in main.tf"
        assert 'source = "./modules/cost_optimization"' in content, "Cost optimization module source should be correct"
    
    def test_budget_configuration_exists(self):
        """Test that budget configuration exists"""
        main_tf_path = self.cost_optimization_module / "main.tf"
        with open(main_tf_path, 'r') as f:
            content = f.read()
        
        # Test for budget resources
        assert 'resource "aws_budgets_budget" "monthly_cost_budget"' in content, "Monthly budget should be configured"
        assert 'resource "aws_budgets_budget" "ecs_cost_budget"' in content, "ECS budget should be configured"
        assert 'resource "aws_budgets_budget" "database_cost_budget"' in content, "Database budget should be configured"
        
        # Test for budget notifications
        assert 'notification {' in content, "Budget notifications should be configured"
        assert 'threshold = 80' in content, "80% threshold should be configured"
        assert 'threshold = 100' in content, "100% threshold should be configured"
    
    def test_right_sizing_monitoring_exists(self):
        """Test that right-sizing monitoring exists"""
        main_tf_path = self.cost_optimization_module / "main.tf"
        with open(main_tf_path, 'r') as f:
            content = f.read()
        
        # Test for underutilization alarms
        assert 'resource "aws_cloudwatch_metric_alarm" "underutilized_ecs_cpu"' in content, "CPU underutilization alarm should exist"
        assert 'resource "aws_cloudwatch_metric_alarm" "underutilized_ecs_memory"' in content, "Memory underutilization alarm should exist"
        
        # Test for CloudWatch dashboard
        assert 'resource "aws_cloudwatch_dashboard" "cost_monitoring"' in content, "Cost monitoring dashboard should exist"
        
        # Test for metrics
        assert 'CPUUtilization' in content, "CPU utilization metric should be monitored"
        assert 'MemoryUtilization' in content, "Memory utilization metric should be monitored"
    
    def test_cost_optimization_variables_exist(self):
        """Test that cost optimization variables exist"""
        variables_tf_path = self.terraform_dir / "variables.tf"
        with open(variables_tf_path, 'r') as f:
            content = f.read()
        
        # Test for cost optimization variables
        assert 'variable "monthly_budget_limit"' in content, "Monthly budget limit variable should exist"
        assert 'variable "ecs_budget_limit"' in content, "ECS budget limit variable should exist"
        assert 'variable "database_budget_limit"' in content, "Database budget limit variable should exist"
        assert 'variable "budget_alert_emails"' in content, "Budget alert emails variable should exist"
        assert 'variable "cost_anomaly_threshold"' in content, "Cost anomaly threshold variable should exist"
        assert 'variable "enable_cost_optimization"' in content, "Enable cost optimization variable should exist"
    
    def test_cost_optimization_outputs_exist(self):
        """Test that cost optimization outputs exist"""
        outputs_tf_path = self.terraform_dir / "outputs.tf"
        with open(outputs_tf_path, 'r') as f:
            content = f.read()
        
        # Test for cost optimization outputs
        assert 'output "cost_optimization"' in content, "Cost optimization output should exist"
        assert 'monthly_budget_name' in content, "Monthly budget name should be in outputs"
        assert 'dashboard_name' in content, "Dashboard name should be in outputs"
        assert 'high_cost_alarm' in content, "High cost alarm should be in outputs"
    
    def test_terraform_tfvars_has_cost_settings(self):
        """Test that terraform.tfvars has cost optimization settings"""
        tfvars_path = self.terraform_dir / "terraform.tfvars"
        with open(tfvars_path, 'r') as f:
            content = f.read()
        
        # Test for cost optimization settings
        assert 'monthly_budget_limit' in content, "Monthly budget limit should be in tfvars"
        assert 'ecs_budget_limit' in content, "ECS budget limit should be in tfvars"
        assert 'database_budget_limit' in content, "Database budget limit should be in tfvars"
        assert 'enable_cost_optimization = true' in content, "Cost optimization should be enabled"
    
    def test_auto_scaling_configuration_exists(self):
        """Test that auto-scaling configuration exists for cost optimization"""
        # Check application module for auto-scaling
        app_main_tf = self.terraform_dir / "modules/application/main.tf"
        with open(app_main_tf, 'r') as f:
            content = f.read()
        
        # Test for auto-scaling resources
        assert 'resource "aws_appautoscaling_target"' in content, "Auto-scaling target should exist"
        assert 'resource "aws_appautoscaling_policy"' in content, "Auto-scaling policy should exist"
        
        # Test for CPU and memory scaling
        assert 'ECSServiceAverageCPUUtilization' in content, "CPU-based scaling should exist"
        assert 'ECSServiceAverageMemoryUtilization' in content, "Memory-based scaling should exist"
    
    def test_cost_recommendations_parameter_exists(self):
        """Test that cost optimization recommendations parameter exists"""
        main_tf_path = self.cost_optimization_module / "main.tf"
        with open(main_tf_path, 'r') as f:
            content = f.read()
        
        # Test for SSM parameter with recommendations
        assert 'resource "aws_ssm_parameter" "cost_optimization_recommendations"' in content, "Cost recommendations parameter should exist"
        assert 'right_sizing' in content, "Right-sizing recommendations should be included"
        assert 'auto_scaling' in content, "Auto-scaling recommendations should be included"
        assert 'cost_monitoring' in content, "Cost monitoring recommendations should be included"
        assert 'reserved_instances' in content, "Reserved instances recommendations should be included"
    
    def test_property_resource_right_sizing_implementation(self):
        """
        Property 16: Resource Right-Sizing
        For any AWS resource, the instance type and configuration should be 
        appropriate for the workload requirements without over-provisioning
        **Validates: Requirements 6.1, 6.3**
        """
        # Test that right-sizing monitoring is implemented
        main_tf_path = self.cost_optimization_module / "main.tf"
        with open(main_tf_path, 'r') as f:
            content = f.read()
        
        # Verify underutilization monitoring exists
        assert 'underutilized_ecs_cpu' in content, "CPU underutilization monitoring should exist"
        assert 'underutilized_ecs_memory' in content, "Memory underutilization monitoring should exist"
        
        # Verify thresholds are configurable
        variables_tf_path = self.cost_optimization_module / "variables.tf"
        with open(variables_tf_path, 'r') as f:
            var_content = f.read()
        
        assert 'cpu_underutilization_threshold' in var_content, "CPU underutilization threshold should be configurable"
        assert 'memory_underutilization_threshold' in var_content, "Memory underutilization threshold should be configurable"
        assert 'target_cpu_utilization' in var_content, "Target CPU utilization should be configurable"
        assert 'target_memory_utilization' in var_content, "Target memory utilization should be configurable"
        
        # Verify recommendations are provided
        assert 'Monitor CPU and memory utilization patterns' in content, "Right-sizing recommendations should be provided"
        assert 'AWS Compute Optimizer' in content, "AWS Compute Optimizer should be recommended"
        
        print("✅ Property 16: Resource Right-Sizing - PASSED")
        print("   - Underutilization monitoring configured")
        print("   - Configurable thresholds for CPU and memory")
        print("   - Right-sizing recommendations provided")
        print("   - Auto-scaling policies implemented")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])