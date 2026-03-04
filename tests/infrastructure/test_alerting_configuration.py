#!/usr/bin/env python3
"""
Property Test: Alerting Configuration
Property 14: Alerting Configuration - For any critical system metric, appropriate CloudWatch alarms should be configured with SNS notifications
Validates: Requirements 5.3, 5.6
"""

import subprocess
import json
import os
from pathlib import Path

def test_alerting_configuration():
    """Test alerting configuration properties."""
    terraform_dir = Path("infrastructure/aws-native")
    
    print("Testing Alerting Configuration...")
    
    os.chdir(terraform_dir)
    
    # Test 1: SNS Topics Configuration
    print("1. Testing SNS topics configuration...")
    
    monitoring_main = Path("modules/monitoring/main.tf")
    with open(monitoring_main, 'r') as f:
        monitoring_content = f.read()
    
    # Test SNS topics for different alert levels
    assert 'aws_sns_topic" "critical_alerts' in monitoring_content, \
        "Critical alerts SNS topic should be configured"
    assert 'aws_sns_topic" "warning_alerts' in monitoring_content, \
        "Warning alerts SNS topic should be configured"
    assert 'aws_sns_topic" "info_alerts' in monitoring_content, \
        "Info alerts SNS topic should be configured"
    print("   ✓ SNS topics are configured")
    
    # Test 2: SNS Topic Encryption
    print("2. Testing SNS topic encryption...")
    
    # Test KMS encryption for SNS topics
    assert 'kms_master_key_id = var.kms_key_arn' in monitoring_content, \
        "SNS topics should be encrypted with KMS"
    print("   ✓ SNS topic encryption is configured")
    
    # Test 3: ECS Service Alarms
    print("3. Testing ECS service alarms...")
    
    # Test ECS CPU alarm
    assert 'aws_cloudwatch_metric_alarm" "ecs_cpu_high' in monitoring_content, \
        "ECS CPU high alarm should be configured"
    assert 'CPUUtilization' in monitoring_content, \
        "CPU utilization metric should be monitored"
    assert 'threshold           = "80"' in monitoring_content, \
        "CPU threshold should be configured"
    
    # Test ECS memory alarm
    assert 'aws_cloudwatch_metric_alarm" "ecs_memory_high' in monitoring_content, \
        "ECS memory high alarm should be configured"
    assert 'MemoryUtilization' in monitoring_content, \
        "Memory utilization metric should be monitored"
    assert 'threshold           = "85"' in monitoring_content, \
        "Memory threshold should be configured"
    print("   ✓ ECS service alarms are configured")
    
    # Test 4: Application Load Balancer Alarms
    print("4. Testing ALB alarms...")
    
    # Test ALB response time alarm
    assert 'aws_cloudwatch_metric_alarm" "alb_response_time' in monitoring_content, \
        "ALB response time alarm should be configured"
    assert 'TargetResponseTime' in monitoring_content, \
        "Target response time metric should be monitored"
    
    # Test ALB 5xx errors alarm
    assert 'aws_cloudwatch_metric_alarm" "alb_5xx_errors' in monitoring_content, \
        "ALB 5xx errors alarm should be configured"
    assert 'HTTPCode_Target_5XX_Count' in monitoring_content, \
        "5xx error count metric should be monitored"
    
    # Test ALB 4xx errors alarm
    assert 'aws_cloudwatch_metric_alarm" "alb_4xx_errors' in monitoring_content, \
        "ALB 4xx errors alarm should be configured"
    assert 'HTTPCode_Target_4XX_Count' in monitoring_content, \
        "4xx error count metric should be monitored"
    print("   ✓ ALB alarms are configured")
    
    # Test 5: Database Alarms
    print("5. Testing database alarms...")
    
    # Test Neptune alarms
    assert 'aws_cloudwatch_metric_alarm" "neptune_cpu_high' in monitoring_content, \
        "Neptune CPU high alarm should be configured"
    assert 'aws_cloudwatch_metric_alarm" "neptune_connections_high' in monitoring_content, \
        "Neptune connections high alarm should be configured"
    assert 'DatabaseConnections' in monitoring_content, \
        "Database connections metric should be monitored"
    
    # Test OpenSearch alarms
    assert 'aws_cloudwatch_metric_alarm" "opensearch_cpu_high' in monitoring_content, \
        "OpenSearch CPU high alarm should be configured"
    assert 'aws_cloudwatch_metric_alarm" "opensearch_storage_high' in monitoring_content, \
        "OpenSearch storage high alarm should be configured"
    assert 'StorageUtilization' in monitoring_content, \
        "Storage utilization metric should be monitored"
    print("   ✓ Database alarms are configured")
    
    # Test 6: Application Custom Metric Alarms
    print("6. Testing application custom metric alarms...")
    
    # Test application error alarm
    assert 'aws_cloudwatch_metric_alarm" "application_errors' in monitoring_content, \
        "Application errors alarm should be configured"
    assert 'ErrorCount' in monitoring_content, \
        "Error count metric should be monitored"
    
    # Test application response time alarm
    assert 'aws_cloudwatch_metric_alarm" "application_response_time' in monitoring_content, \
        "Application response time alarm should be configured"
    assert 'ResponseTime' in monitoring_content, \
        "Response time metric should be monitored"
    print("   ✓ Application custom metric alarms are configured")
    
    # Test 7: Alarm Actions Configuration
    print("7. Testing alarm actions configuration...")
    
    # Test alarm actions point to SNS topics
    assert 'alarm_actions       = [aws_sns_topic.critical_alerts.arn]' in monitoring_content, \
        "Critical alarms should send to critical alerts topic"
    assert 'alarm_actions       = [aws_sns_topic.warning_alerts.arn]' in monitoring_content, \
        "Warning alarms should send to warning alerts topic"
    assert 'ok_actions          = [aws_sns_topic.info_alerts.arn]' in monitoring_content, \
        "OK actions should send to info alerts topic"
    print("   ✓ Alarm actions are configured")
    
    # Test 8: Alarm Thresholds and Evaluation
    print("8. Testing alarm thresholds and evaluation...")
    
    # Test evaluation periods are configured
    assert 'evaluation_periods  = "2"' in monitoring_content, \
        "Evaluation periods should be configured"
    assert 'evaluation_periods  = "3"' in monitoring_content, \
        "Different evaluation periods should be used"
    
    # Test comparison operators
    assert 'comparison_operator = "GreaterThanThreshold"' in monitoring_content, \
        "Comparison operators should be configured"
    
    # Test statistics
    assert 'statistic           = "Average"' in monitoring_content, \
        "Statistics should be configured"
    assert 'statistic           = "Sum"' in monitoring_content, \
        "Different statistics should be used"
    print("   ✓ Alarm thresholds and evaluation are configured")
    
    print("\n🎉 Alerting Configuration tests passed!")
    print("✅ Property 14: Alerting Configuration validated")
    
    os.chdir("../..")

if __name__ == "__main__":
    test_alerting_configuration()