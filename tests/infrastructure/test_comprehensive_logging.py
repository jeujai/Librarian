#!/usr/bin/env python3
"""
Property Test: Comprehensive Logging
Property 13: Comprehensive Logging - For any application component, all logs should be centrally collected in CloudWatch with proper retention and encryption
Validates: Requirements 5.1, 5.7
"""

import subprocess
import json
import os
from pathlib import Path

def test_comprehensive_logging():
    """Test comprehensive logging properties."""
    terraform_dir = Path("infrastructure/aws-native")
    
    print("Testing Comprehensive Logging...")
    
    os.chdir(terraform_dir)
    
    # Test 1: CloudWatch Log Groups Configuration
    print("1. Testing CloudWatch log groups configuration...")
    
    monitoring_main = Path("modules/monitoring/main.tf")
    with open(monitoring_main, 'r') as f:
        monitoring_content = f.read()
    
    # Test log groups are configured
    assert 'aws_cloudwatch_log_group" "application' in monitoring_content, \
        "Application log group should be configured"
    assert 'aws_cloudwatch_log_group" "api_gateway' in monitoring_content, \
        "API Gateway log group should be configured"
    assert 'aws_cloudwatch_log_group" "lambda' in monitoring_content, \
        "Lambda log group should be configured"
    print("   ✓ CloudWatch log groups are configured")
    
    # Test 2: Log Retention Configuration
    print("2. Testing log retention configuration...")
    
    # Test retention is configurable
    assert 'retention_in_days = var.log_retention_days' in monitoring_content, \
        "Log retention should be configurable"
    print("   ✓ Log retention is configurable")
    
    # Test 3: Log Encryption Configuration
    print("3. Testing log encryption configuration...")
    
    # Test KMS encryption for logs
    assert 'kms_key_id        = var.kms_key_arn' in monitoring_content, \
        "Log encryption should be configured with KMS"
    print("   ✓ Log encryption is configured")
    
    # Test 4: Application Log Groups in Application Module
    print("4. Testing application log groups...")
    
    application_main = Path("modules/application/main.tf")
    with open(application_main, 'r') as f:
        application_content = f.read()
    
    # Test ECS log groups
    assert 'aws_cloudwatch_log_group" "ecs_tasks' in application_content, \
        "ECS tasks log group should be configured"
    assert 'aws_cloudwatch_log_group" "ecs_exec' in application_content, \
        "ECS exec log group should be configured"
    assert 'aws_cloudwatch_log_group" "elasticache_slow' in application_content, \
        "ElastiCache slow log group should be configured"
    print("   ✓ Application log groups are configured")
    
    # Test 5: Log Configuration in ECS Task Definition
    print("5. Testing ECS task log configuration...")
    
    # Test log configuration in container definition
    assert 'logConfiguration' in application_content, \
        "Log configuration should be in container definition"
    assert 'logDriver = "awslogs"' in application_content, \
        "AWS logs driver should be configured"
    assert 'awslogs-group' in application_content, \
        "Log group should be specified"
    assert 'awslogs-region' in application_content, \
        "Log region should be specified"
    print("   ✓ ECS task log configuration is correct")
    
    # Test 6: Log Metric Filters
    print("6. Testing log metric filters...")
    
    # Test error count metric filter
    assert 'aws_cloudwatch_log_metric_filter" "error_count' in monitoring_content, \
        "Error count metric filter should be configured"
    assert 'level=\\"ERROR\\"' in monitoring_content, \
        "Error level pattern should be configured"
    
    # Test warning count metric filter
    assert 'aws_cloudwatch_log_metric_filter" "warning_count' in monitoring_content, \
        "Warning count metric filter should be configured"
    assert 'level=\\"WARNING\\"' in monitoring_content, \
        "Warning level pattern should be configured"
    
    # Test response time metric filter
    assert 'aws_cloudwatch_log_metric_filter" "response_time' in monitoring_content, \
        "Response time metric filter should be configured"
    print("   ✓ Log metric filters are configured")
    
    # Test 7: CloudWatch Insights Queries
    print("7. Testing CloudWatch Insights queries...")
    
    # Test error analysis query
    assert 'aws_cloudwatch_query_definition" "error_analysis' in monitoring_content, \
        "Error analysis query should be configured"
    assert 'filter @message like /ERROR/' in monitoring_content, \
        "Error filter should be in query"
    
    # Test performance analysis query
    assert 'aws_cloudwatch_query_definition" "performance_analysis' in monitoring_content, \
        "Performance analysis query should be configured"
    assert 'response_time' in monitoring_content, \
        "Response time should be in performance query"
    
    # Test database connection analysis query
    assert 'aws_cloudwatch_query_definition" "database_connection_analysis' in monitoring_content, \
        "Database connection analysis query should be configured"
    print("   ✓ CloudWatch Insights queries are configured")
    
    print("\n🎉 Comprehensive Logging tests passed!")
    print("✅ Property 13: Comprehensive Logging validated")
    
    os.chdir("../..")

if __name__ == "__main__":
    test_comprehensive_logging()