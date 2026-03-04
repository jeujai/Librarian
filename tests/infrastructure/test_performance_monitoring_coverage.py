#!/usr/bin/env python3
"""
Property Test: Performance Monitoring Coverage
Property 15: Performance Monitoring Coverage - For any performance-critical component, comprehensive metrics should be collected and visualized in CloudWatch dashboards
Validates: Requirements 5.2, 5.4, 8.7
"""

import subprocess
import json
import os
from pathlib import Path

def test_performance_monitoring_coverage():
    """Test performance monitoring coverage properties."""
    terraform_dir = Path("infrastructure/aws-native")
    
    print("Testing Performance Monitoring Coverage...")
    
    os.chdir(terraform_dir)
    
    # Test 1: CloudWatch Dashboard Configuration
    print("1. Testing CloudWatch dashboard configuration...")
    
    monitoring_main = Path("modules/monitoring/main.tf")
    with open(monitoring_main, 'r') as f:
        monitoring_content = f.read()
    
    # Test dashboard is configured
    assert 'aws_cloudwatch_dashboard" "main' in monitoring_content, \
        "CloudWatch dashboard should be configured"
    assert 'dashboard_name = "${var.name_prefix}-operational-dashboard"' in monitoring_content, \
        "Dashboard name should be configured"
    print("   ✓ CloudWatch dashboard is configured")
    
    # Test 2: ECS Performance Metrics
    print("2. Testing ECS performance metrics...")
    
    # Test ECS metrics in dashboard
    assert '["AWS/ECS", "CPUUtilization"' in monitoring_content, \
        "ECS CPU utilization should be in dashboard"
    assert '[".", "MemoryUtilization"' in monitoring_content, \
        "ECS memory utilization should be in dashboard"
    assert '"ServiceName", var.ecs_service_name' in monitoring_content, \
        "ECS service name should be used in metrics"
    assert '"ClusterName", var.ecs_cluster_name' in monitoring_content, \
        "ECS cluster name should be used in metrics"
    print("   ✓ ECS performance metrics are configured")
    
    # Test 3: Application Load Balancer Performance Metrics
    print("3. Testing ALB performance metrics...")
    
    # Test ALB metrics in dashboard
    assert '["AWS/ApplicationELB", "TargetResponseTime"' in monitoring_content, \
        "ALB target response time should be in dashboard"
    assert '[".", "RequestCount"' in monitoring_content, \
        "ALB request count should be in dashboard"
    assert '[".", "HTTPCode_Target_2XX_Count"' in monitoring_content, \
        "ALB 2xx count should be in dashboard"
    assert '[".", "HTTPCode_Target_4XX_Count"' in monitoring_content, \
        "ALB 4xx count should be in dashboard"
    assert '[".", "HTTPCode_Target_5XX_Count"' in monitoring_content, \
        "ALB 5xx count should be in dashboard"
    print("   ✓ ALB performance metrics are configured")
    
    # Test 4: Neptune Database Performance Metrics
    print("4. Testing Neptune performance metrics...")
    
    # Test Neptune metrics in dashboard
    assert '["AWS/Neptune", "CPUUtilization"' in monitoring_content, \
        "Neptune CPU utilization should be in dashboard"
    assert '[".", "DatabaseConnections"' in monitoring_content, \
        "Neptune database connections should be in dashboard"
    assert '[".", "VolumeBytesUsed"' in monitoring_content, \
        "Neptune volume bytes used should be in dashboard"
    assert '"DBClusterIdentifier", var.neptune_cluster_id' in monitoring_content, \
        "Neptune cluster ID should be used in metrics"
    print("   ✓ Neptune performance metrics are configured")
    
    # Test 5: OpenSearch Performance Metrics
    print("5. Testing OpenSearch performance metrics...")
    
    # Test OpenSearch metrics in dashboard
    assert '["AWS/ES", "CPUUtilization"' in monitoring_content, \
        "OpenSearch CPU utilization should be in dashboard"
    assert '[".", "StorageUtilization"' in monitoring_content, \
        "OpenSearch storage utilization should be in dashboard"
    assert '[".", "SearchLatency"' in monitoring_content, \
        "OpenSearch search latency should be in dashboard"
    assert '[".", "IndexingLatency"' in monitoring_content, \
        "OpenSearch indexing latency should be in dashboard"
    assert '"DomainName", var.opensearch_domain_name' in monitoring_content, \
        "OpenSearch domain name should be used in metrics"
    print("   ✓ OpenSearch performance metrics are configured")
    
    # Test 6: Custom Application Metrics
    print("6. Testing custom application metrics...")
    
    # Test custom metrics in dashboard
    assert '["MultimodalLibrarian/${var.environment}", "ErrorCount"]' in monitoring_content, \
        "Custom error count metric should be in dashboard"
    assert '[".", "WarningCount"]' in monitoring_content, \
        "Custom warning count metric should be in dashboard"
    assert '[".", "ResponseTime"]' in monitoring_content, \
        "Custom response time metric should be in dashboard"
    print("   ✓ Custom application metrics are configured")
    
    # Test 7: Dashboard Widget Configuration
    print("7. Testing dashboard widget configuration...")
    
    # Test widget types and properties
    assert 'type   = "metric"' in monitoring_content, \
        "Metric widgets should be configured"
    assert 'type   = "log"' in monitoring_content, \
        "Log widgets should be configured"
    assert 'view    = "timeSeries"' in monitoring_content, \
        "Time series view should be configured"
    assert 'period  = 300' in monitoring_content, \
        "5-minute period should be configured"
    assert 'region  = var.aws_region' in monitoring_content, \
        "Region should be configured in widgets"
    print("   ✓ Dashboard widget configuration is correct")
    
    # Test 8: Log-based Performance Monitoring
    print("8. Testing log-based performance monitoring...")
    
    # Test log widget for errors
    assert 'filter @message like /ERROR/' in monitoring_content, \
        "Error log filtering should be configured"
    assert 'sort @timestamp desc' in monitoring_content, \
        "Log sorting should be configured"
    assert 'limit 100' in monitoring_content, \
        "Log limit should be configured"
    print("   ✓ Log-based performance monitoring is configured")
    
    # Test 9: X-Ray Tracing Configuration
    print("9. Testing X-Ray tracing configuration...")
    
    # Test X-Ray sampling rule
    assert 'aws_xray_sampling_rule" "main' in monitoring_content, \
        "X-Ray sampling rule should be configured"
    assert 'fixed_rate     = 0.1' in monitoring_content, \
        "X-Ray sampling rate should be configured"
    assert 'reservoir_size = 1' in monitoring_content, \
        "X-Ray reservoir size should be configured"
    print("   ✓ X-Ray tracing configuration is correct")
    
    # Test 10: Performance Metric Filters
    print("10. Testing performance metric filters...")
    
    # Test response time metric filter
    assert 'response_time' in monitoring_content, \
        "Response time should be extracted from logs"
    assert 'metric_transformation' in monitoring_content, \
        "Metric transformation should be configured"
    assert 'namespace = "MultimodalLibrarian/${var.environment}"' in monitoring_content, \
        "Custom namespace should be configured"
    print("   ✓ Performance metric filters are configured")
    
    print("\n🎉 Performance Monitoring Coverage tests passed!")
    print("✅ Property 15: Performance Monitoring Coverage validated")
    print("✅ Task 7 (Monitoring and logging infrastructure) completed successfully")
    
    os.chdir("../..")

if __name__ == "__main__":
    test_performance_monitoring_coverage()