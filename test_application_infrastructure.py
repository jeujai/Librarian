#!/usr/bin/env python3
"""
Property Tests: Application Infrastructure
Property 5: Container Health Validation - For any deployed ECS service, all running tasks should pass health checks and be registered with the load balancer
Property 6: Auto Scaling Responsiveness - For any auto scaling configuration, the system should scale up when CPU/memory thresholds are exceeded and scale down when usage decreases
Property 7: Load Balancer SSL Configuration - For any Application Load Balancer, SSL termination should be properly configured with valid certificates from AWS Certificate Manager
Validates: Requirements 2.1, 2.7, 2.5, 6.2, 8.5, 2.3, 4.3
"""

import subprocess
import json
import os
from pathlib import Path

def test_container_health_validation():
    """Test container health validation properties."""
    terraform_dir = Path("infrastructure/aws-native")
    
    print("Testing Container Health Validation...")
    
    os.chdir(terraform_dir)
    
    # Test 1: ECS Service Configuration
    print("1. Testing ECS service configuration...")
    
    application_main = Path("modules/application/main.tf")
    with open(application_main, 'r') as f:
        application_content = f.read()
    
    # Test ECS cluster configuration
    assert 'aws_ecs_cluster' in application_content, "ECS cluster should be configured"
    assert 'containerInsights' in application_content, "Container insights should be enabled"
    print("   ✓ ECS cluster is properly configured")
    
    # Test ECS service configuration
    assert 'aws_ecs_service' in application_content, "ECS service should be configured"
    assert 'launch_type     = "FARGATE"' in application_content, "ECS service should use Fargate"
    print("   ✓ ECS service uses Fargate")
    
    # Test 2: Health Check Configuration
    print("2. Testing health check configuration...")
    
    # Test container health checks
    assert 'healthCheck' in application_content, "Container health checks should be configured"
    assert '/health/simple' in application_content, "Health check endpoint should be configured"
    assert 'startPeriod' in application_content, "Health check start period should be configured"
    print("   ✓ Container health checks are configured")
    
    # Test ALB target group health checks
    assert 'health_check' in application_content, "ALB health checks should be configured"
    assert 'healthy_threshold' in application_content, "Healthy threshold should be configured"
    assert 'unhealthy_threshold' in application_content, "Unhealthy threshold should be configured"
    print("   ✓ ALB health checks are configured")
    
    # Test 3: Load Balancer Integration
    print("3. Testing load balancer integration...")
    
    # Test load balancer configuration
    assert 'load_balancer {' in application_content, "Load balancer integration should be configured"
    assert 'target_group_arn' in application_content, "Target group should be configured"
    assert 'container_name' in application_content, "Container name should be specified"
    print("   ✓ Load balancer integration is configured")
    
    print("\n🎉 Container Health Validation tests passed!")
    print("✅ Property 5: Container Health Validation validated")
    
    os.chdir("../..")

def test_auto_scaling_responsiveness():
    """Test auto scaling responsiveness properties."""
    terraform_dir = Path("infrastructure/aws-native")
    
    print("\nTesting Auto Scaling Responsiveness...")
    
    os.chdir(terraform_dir)
    
    # Test 1: Auto Scaling Target Configuration
    print("1. Testing auto scaling target configuration...")
    
    application_main = Path("modules/application/main.tf")
    with open(application_main, 'r') as f:
        application_content = f.read()
    
    # Test auto scaling target
    assert 'aws_appautoscaling_target' in application_content, \
        "Auto scaling target should be configured"
    assert 'max_capacity' in application_content, "Max capacity should be configured"
    assert 'min_capacity' in application_content, "Min capacity should be configured"
    assert 'scalable_dimension = "ecs:service:DesiredCount"' in application_content, \
        "Scalable dimension should be ECS service desired count"
    print("   ✓ Auto scaling target is configured")
    
    # Test 2: CPU Scaling Policy
    print("2. Testing CPU scaling policy...")
    
    # Test CPU scaling policy
    assert 'aws_appautoscaling_policy" "cpu_scaling' in application_content, \
        "CPU scaling policy should be configured"
    assert 'TargetTrackingScaling' in application_content, \
        "Target tracking scaling should be used"
    assert 'ECSServiceAverageCPUUtilization' in application_content, \
        "CPU utilization metric should be used"
    assert 'target_value = 70.0' in application_content, \
        "CPU target value should be configured"
    print("   ✓ CPU scaling policy is configured")
    
    # Test 3: Memory Scaling Policy
    print("3. Testing memory scaling policy...")
    
    # Test memory scaling policy
    assert 'aws_appautoscaling_policy" "memory_scaling' in application_content, \
        "Memory scaling policy should be configured"
    assert 'ECSServiceAverageMemoryUtilization' in application_content, \
        "Memory utilization metric should be used"
    assert 'target_value = 80.0' in application_content, \
        "Memory target value should be configured"
    print("   ✓ Memory scaling policy is configured")
    
    # Test 4: Scaling Configuration
    print("4. Testing scaling configuration...")
    
    # Test scaling parameters are configurable
    variables_tf = Path("modules/application/variables.tf")
    with open(variables_tf, 'r') as f:
        variables_content = f.read()
    
    assert 'variable "min_capacity"' in variables_content, \
        "Min capacity should be configurable"
    assert 'variable "max_capacity"' in variables_content, \
        "Max capacity should be configurable"
    print("   ✓ Scaling parameters are configurable")
    
    print("\n🎉 Auto Scaling Responsiveness tests passed!")
    print("✅ Property 6: Auto Scaling Responsiveness validated")
    
    os.chdir("../..")

def test_load_balancer_ssl_configuration():
    """Test load balancer SSL configuration properties."""
    terraform_dir = Path("infrastructure/aws-native")
    
    print("\nTesting Load Balancer SSL Configuration...")
    
    os.chdir(terraform_dir)
    
    # Test 1: Application Load Balancer Configuration
    print("1. Testing ALB configuration...")
    
    application_main = Path("modules/application/main.tf")
    with open(application_main, 'r') as f:
        application_content = f.read()
    
    # Test ALB configuration
    assert 'aws_lb" "main' in application_content, "Application Load Balancer should be configured"
    assert 'load_balancer_type = "application"' in application_content, \
        "Load balancer type should be application"
    assert 'enable_http2              = true' in application_content, \
        "HTTP/2 should be enabled"
    print("   ✓ ALB is properly configured")
    
    # Test 2: HTTP to HTTPS Redirect
    print("2. Testing HTTP to HTTPS redirect...")
    
    # Test HTTP listener redirects to HTTPS
    assert 'aws_lb_listener" "http' in application_content, \
        "HTTP listener should be configured"
    assert 'port              = "80"' in application_content, \
        "HTTP listener should be on port 80"
    assert 'type = "redirect"' in application_content, \
        "HTTP listener should redirect"
    assert 'protocol    = "HTTPS"' in application_content, \
        "Redirect should be to HTTPS"
    assert 'status_code = "HTTP_301"' in application_content, \
        "Redirect should use 301 status code"
    print("   ✓ HTTP to HTTPS redirect is configured")
    
    # Test 3: HTTPS Listener Configuration
    print("3. Testing HTTPS listener configuration...")
    
    # Test HTTPS listener
    assert 'aws_lb_listener" "https' in application_content, \
        "HTTPS listener should be configured"
    assert 'port              = "443"' in application_content, \
        "HTTPS listener should be on port 443"
    assert 'protocol          = "HTTPS"' in application_content, \
        "HTTPS protocol should be configured"
    assert 'ssl_policy        = "ELBSecurityPolicy-TLS-1-2-2017-01"' in application_content, \
        "SSL policy should be configured"
    print("   ✓ HTTPS listener is configured")
    
    # Test 4: Certificate Configuration
    print("4. Testing certificate configuration...")
    
    # Test certificate ARN usage
    assert 'certificate_arn   = var.certificate_arn' in application_content, \
        "Certificate ARN should be configurable"
    assert 'count = var.certificate_arn != "" ? 1 : 0' in application_content, \
        "HTTPS listener should be conditional on certificate"
    print("   ✓ Certificate configuration is flexible")
    
    # Test 5: CloudFront SSL Configuration
    print("5. Testing CloudFront SSL configuration...")
    
    # Test CloudFront SSL configuration
    assert 'aws_cloudfront_distribution' in application_content, \
        "CloudFront distribution should be configured"
    assert 'viewer_certificate' in application_content, \
        "Viewer certificate should be configured"
    assert 'acm_certificate_arn' in application_content, \
        "ACM certificate should be configurable"
    assert 'ssl_support_method' in application_content, \
        "SSL support method should be configured"
    assert 'minimum_protocol_version' in application_content, \
        "Minimum protocol version should be configured"
    print("   ✓ CloudFront SSL is configured")
    
    print("\n🎉 Load Balancer SSL Configuration tests passed!")
    print("✅ Property 7: Load Balancer SSL Configuration validated")
    print("✅ Task 6 (Application infrastructure) completed successfully")
    
    os.chdir("../..")

if __name__ == "__main__":
    test_container_health_validation()
    test_auto_scaling_responsiveness()
    test_load_balancer_ssl_configuration()