#!/usr/bin/env python3
"""
Property Test for Cost Monitoring Implementation
Tests Property 17: Cost Monitoring Implementation
**Validates: Requirements 6.6, 1.7**
"""

import pytest
import json
import os
import subprocess
from pathlib import Path


class TestCostMonitoringImplementation:
    """Test cost monitoring implementation"""
    
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
    
    def test_budget_configuration_comprehensive(self):
        """Test comprehensive budget configuration"""
        main_tf_path = self.cost_optimization_module / "main.tf"
        with open(main_tf_path, 'r') as f:
            content = f.read()
        
        # Test for all budget types
        assert 'resource "aws_budgets_budget" "monthly_cost_budget"' in content, "Monthly budget should be configured"
        assert 'resource "aws_budgets_budget" "ecs_cost_budget"' in content, "ECS budget should be configured"
        assert 'resource "aws_budgets_budget" "database_cost_budget"' in content, "Database budget should be configured"
        
        # Test budget configuration details
        assert 'budget_type  = "COST"' in content, "Budget type should be COST"
        assert 'limit_unit   = "USD"' in content, "Budget limit unit should be USD"
        assert 'time_unit    = "MONTHLY"' in content, "Budget time unit should be MONTHLY"
        
        # Test cost filters for proper resource targeting
        assert 'cost_filter {' in content, "Cost filters should be configured"
        assert 'name   = "Service"' in content, "Service-based cost filtering should exist"
        assert 'name   = "TagKey"' in content, "Tag-based cost filtering should exist"
        assert 'Amazon Elastic Container Service' in content, "ECS service filtering should exist"
        assert 'Amazon Neptune' in content, "Neptune service filtering should exist"
        assert 'Amazon OpenSearch Service' in content, "OpenSearch service filtering should exist"
    
    def test_budget_notifications_configured(self):
        """Test that budget notifications are properly configured"""
        main_tf_path = self.cost_optimization_module / "main.tf"
        with open(main_tf_path, 'r') as f:
            content = f.read()
        
        # Test notification configuration
        assert 'notification {' in content, "Budget notifications should be configured"
        assert 'comparison_operator        = "GREATER_THAN"' in content, "Comparison operator should be GREATER_THAN"
        assert 'threshold_type           = "PERCENTAGE"' in content, "Threshold type should be PERCENTAGE"
        assert 'notification_type        = "ACTUAL"' in content, "Actual notification type should exist"
        assert 'notification_type          = "FORECASTED"' in content, "Forecasted notification type should exist"
        assert 'subscriber_email_addresses' in content, "Email subscribers should be configured"
        
        # Test threshold values
        assert 'threshold                 = 80' in content or 'threshold = 80' in content, "80% threshold should be configured"
        assert 'threshold                 = 100' in content or 'threshold = 100' in content, "100% threshold should be configured"
    
    def test_cost_monitoring_dashboard_exists(self):
        """Test that cost monitoring dashboard exists"""
        main_tf_path = self.cost_optimization_module / "main.tf"
        with open(main_tf_path, 'r') as f:
            content = f.read()
        
        # Test dashboard resource
        assert 'resource "aws_cloudwatch_dashboard" "cost_monitoring"' in content, "Cost monitoring dashboard should exist"
        assert 'dashboard_name = "${var.name_prefix}-cost-monitoring"' in content, "Dashboard name should be configured"
        
        # Test dashboard widgets
        assert 'widgets = [' in content, "Dashboard widgets should be configured"
        assert 'EstimatedCharges' in content, "Estimated charges metric should be monitored"
        assert 'CPUUtilization' in content, "CPU utilization should be monitored"
        assert 'MemoryUtilization' in content, "Memory utilization should be monitored"
        
        # Test dashboard properties
        assert '"timeSeries"' in content, "Time series view should be configured"
        assert '"Maximum"' in content, "Maximum statistic should be used for billing"
    
    def test_cost_alerts_configured(self):
        """Test that cost alerts are properly configured"""
        main_tf_path = self.cost_optimization_module / "main.tf"
        with open(main_tf_path, 'r') as f:
            content = f.read()
        
        # Test high cost utilization alarm
        assert 'resource "aws_cloudwatch_metric_alarm" "high_cost_utilization"' in content, "High cost alarm should exist"
        assert 'metric_name         = "EstimatedCharges"' in content, "Estimated charges metric should be used"
        assert 'namespace           = "AWS/Billing"' in content, "Billing namespace should be used"
        assert 'comparison_operator = "GreaterThanThreshold"' in content, "Greater than comparison should be used"
        
        # Test cost anomaly alarm
        assert 'cost_anomaly_alarm' in content, "Cost anomaly alarm should exist"
        
        # Test alarm actions
        assert 'alarm_actions' in content, "Alarm actions should be configured"
        assert 'var.sns_topic_arn' in content, "SNS topic should be used for notifications"
    
    def test_cost_optimization_variables_comprehensive(self):
        """Test comprehensive cost optimization variables"""
        variables_tf_path = self.terraform_dir / "variables.tf"
        with open(variables_tf_path, 'r') as f:
            content = f.read()
        
        # Test budget limit variables
        assert 'variable "monthly_budget_limit"' in content, "Monthly budget limit variable should exist"
        assert 'variable "ecs_budget_limit"' in content, "ECS budget limit variable should exist"
        assert 'variable "database_budget_limit"' in content, "Database budget limit variable should exist"
        
        # Test notification variables
        assert 'variable "budget_alert_emails"' in content, "Budget alert emails variable should exist"
        assert 'variable "cost_anomaly_threshold"' in content, "Cost anomaly threshold variable should exist"
        
        # Test feature toggle variables
        assert 'variable "enable_cost_optimization"' in content, "Enable cost optimization variable should exist"
        
        # Test validation rules
        assert 'validation {' in content, "Variable validation should exist"
        assert 'error_message' in content, "Error messages should be provided"
    
    def test_cost_optimization_outputs_comprehensive(self):
        """Test comprehensive cost optimization outputs"""
        outputs_tf_path = self.terraform_dir / "outputs.tf"
        with open(outputs_tf_path, 'r') as f:
            content = f.read()
        
        # Test main cost optimization output
        assert 'output "cost_optimization"' in content, "Cost optimization output should exist"
        
        # Test budget outputs
        assert 'monthly_budget_name' in content, "Monthly budget name should be in outputs"
        assert 'ecs_budget_name' in content, "ECS budget name should be in outputs"
        assert 'database_budget_name' in content, "Database budget name should be in outputs"
        
        # Test monitoring outputs
        assert 'dashboard_name' in content, "Dashboard name should be in outputs"
        assert 'dashboard_url' in content, "Dashboard URL should be in outputs"
        assert 'high_cost_alarm' in content, "High cost alarm should be in outputs"
        
        # Test summary output
        assert 'summary' in content, "Cost optimization summary should be in outputs"
    
    def test_terraform_tfvars_cost_configuration(self):
        """Test terraform.tfvars cost configuration"""
        tfvars_path = self.terraform_dir / "terraform.tfvars"
        with open(tfvars_path, 'r') as f:
            content = f.read()
        
        # Test budget configuration
        assert 'monthly_budget_limit' in content, "Monthly budget limit should be in tfvars"
        assert 'ecs_budget_limit' in content, "ECS budget limit should be in tfvars"
        assert 'database_budget_limit' in content, "Database budget limit should be in tfvars"
        assert 'budget_alert_emails' in content, "Budget alert emails should be in tfvars"
        assert 'cost_anomaly_threshold' in content, "Cost anomaly threshold should be in tfvars"
        
        # Test feature enablement
        assert 'enable_cost_optimization = true' in content, "Cost optimization should be enabled"
    
    def test_resource_tagging_for_cost_allocation(self):
        """Test resource tagging for cost allocation"""
        # Test main.tf for common tags
        main_tf_path = self.terraform_dir / "main.tf"
        with open(main_tf_path, 'r') as f:
            main_content = f.read()
        
        assert 'tags = local.common_tags' in main_content, "Common tags should be applied to cost optimization module"
        assert 'local.common_tags' in main_content, "Common tags should be defined"
        
        # Test variables for cost center
        variables_tf_path = self.terraform_dir / "variables.tf"
        with open(variables_tf_path, 'r') as f:
            var_content = f.read()
        
        assert 'cost_center' in var_content, "Cost center variable should exist for tagging"
        
        # Test cost optimization module uses tags
        cost_main_tf = self.cost_optimization_module / "main.tf"
        with open(cost_main_tf, 'r') as f:
            cost_content = f.read()
        
        assert 'tags = var.tags' in cost_content, "Cost optimization resources should use tags"
    
    def test_cost_optimization_module_integration(self):
        """Test cost optimization module integration with main infrastructure"""
        main_tf_path = self.terraform_dir / "main.tf"
        with open(main_tf_path, 'r') as f:
            content = f.read()
        
        # Test module call
        assert 'module "cost_optimization"' in content, "Cost optimization module should be called"
        assert 'source = "./modules/cost_optimization"' in content, "Module source should be correct"
        
        # Test module configuration
        assert 'monthly_budget_limit        = var.monthly_budget_limit' in content, "Monthly budget limit should be passed"
        assert 'budget_notification_emails = var.budget_alert_emails' in content, "Budget emails should be passed"
        assert 'ecs_cluster_name = module.application.ecs_cluster_name' in content, "ECS cluster name should be passed"
        assert 'ecs_service_name = module.application.ecs_service_name' in content, "ECS service name should be passed"
        
        # Test SNS integration
        assert 'sns_topic_arn = var.notification_email != "" ? aws_sns_topic.notifications[0].arn : ""' in content, "SNS topic should be integrated"
    
    def test_property_cost_monitoring_implementation(self):
        """
        Property 17: Cost Monitoring Implementation
        For any deployed environment, cost tracking should be enabled with 
        budget alerts and resource tagging for cost allocation
        **Validates: Requirements 6.6, 1.7**
        """
        # Test comprehensive budget monitoring
        main_tf_path = self.cost_optimization_module / "main.tf"
        with open(main_tf_path, 'r') as f:
            content = f.read()
        
        # Verify budget tracking is enabled
        assert 'aws_budgets_budget' in content, "Budget tracking should be enabled"
        assert 'monthly_cost_budget' in content, "Monthly cost budget should exist"
        assert 'ecs_cost_budget' in content, "ECS cost budget should exist"
        assert 'database_cost_budget' in content, "Database cost budget should exist"
        
        # Verify budget alerts are configured
        assert 'notification {' in content, "Budget alerts should be configured"
        assert 'subscriber_email_addresses' in content, "Email alerts should be configured"
        assert 'threshold                 = 80' in content or 'threshold = 80' in content, "80% alert threshold should exist"
        assert 'threshold                 = 100' in content or 'threshold = 100' in content, "100% alert threshold should exist"
        
        # Verify cost monitoring dashboard
        assert 'aws_cloudwatch_dashboard' in content, "Cost monitoring dashboard should exist"
        assert 'EstimatedCharges' in content, "Cost tracking metrics should be monitored"
        
        # Verify resource tagging for cost allocation
        main_tf_path = self.terraform_dir / "main.tf"
        with open(main_tf_path, 'r') as f:
            main_content = f.read()
        
        assert 'tags = local.common_tags' in main_content, "Resource tagging should be implemented"
        
        # Verify cost anomaly detection
        assert 'cost_anomaly_alarm' in content, "Cost anomaly detection should be implemented"
        
        print("✅ Property 17: Cost Monitoring Implementation - PASSED")
        print("   - Budget tracking enabled for all service categories")
        print("   - Budget alerts configured with email notifications")
        print("   - Cost monitoring dashboard implemented")
        print("   - Resource tagging for cost allocation")
        print("   - Cost anomaly detection and alerting")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])