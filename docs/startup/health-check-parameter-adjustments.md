# Health Check Parameter Adjustments

## Overview

This document outlines the adjustments made to ECS health check timeout and retry parameters to optimize for AI-heavy applications with ML model loading requirements.

## Changes Made

### 1. Start Period Adjustment
- **Before**: 60 seconds
- **After**: 300 seconds (5 minutes)
- **Rationale**: AI applications require significant time to load ML models. The 5-minute start period allows the application to complete its multi-phase startup process before health checks begin failing.

### 2. Timeout Adjustment
- **Before**: 10 seconds
- **After**: 15 seconds
- **Rationale**: Increased timeout to accommodate potential delays in health endpoint responses during model loading phases, while still meeting the requirement to respond within reasonable time limits.

### 3. Retry Count Adjustment
- **Before**: 3 retries
- **After**: 5 retries
- **Rationale**: Increased retries to provide more resilience during startup phases when the application may be temporarily unresponsive due to resource-intensive operations.

### 4. Unhealthy Threshold Adjustment (ALB Target Group)
- **Before**: 3 consecutive failures
- **After**: 5 consecutive failures
- **Rationale**: More tolerance for temporary failures during startup and model loading phases.

## Configuration Files Updated

### 1. Terraform Configuration
File: `infrastructure/aws-native/modules/application/main.tf`

**ECS Task Definition Health Check:**
```hcl
healthCheck = {
  command     = ["CMD-SHELL", "curl -f http://localhost:${var.container_port}/api/health/minimal || exit 1"]
  interval    = 30
  timeout     = 15
  retries     = 5
  startPeriod = 300
}
```

**ALB Target Group Health Check:**
```hcl
health_check {
  enabled             = true
  healthy_threshold   = 2
  interval            = 30
  matcher             = "200"
  path                = "/api/health/minimal"
  port                = "traffic-port"
  protocol            = "HTTP"
  timeout             = 15
  unhealthy_threshold = 5
}
```

### 2. Task Definition JSON
File: `task-definition-update.json`

```json
"healthCheck": {
    "command": [
        "CMD-SHELL",
        "curl -f http://localhost:8000/api/health/minimal || exit 1"
    ],
    "interval": 30,
    "timeout": 15,
    "retries": 5,
    "startPeriod": 300
}
```

## Expected Benefits

1. **Reduced Startup Failures**: The 5-minute start period prevents premature health check failures during model loading.

2. **Improved Reliability**: Increased retries and timeout values provide better tolerance for temporary delays.

3. **Better User Experience**: Applications can complete their startup process without being terminated by health check failures.

4. **Compliance with Requirements**: Meets the requirement for health check start periods of at least 300 seconds for AI applications.

## Monitoring Recommendations

1. **CloudWatch Metrics**: Monitor ECS service health check metrics to ensure the new parameters are effective.

2. **Application Logs**: Review startup logs to verify that the 5-minute window is sufficient for model loading.

3. **Response Times**: Monitor health endpoint response times to ensure they stay well below the 15-second timeout.

## Rollback Plan

If issues arise with the new parameters, the previous values can be restored:
- startPeriod: 60 seconds
- timeout: 10 seconds  
- retries: 3
- unhealthy_threshold: 3

## Related Requirements

- **REQ-1**: Health Check Optimization - Allows sufficient time for AI-heavy application initialization
- **REQ-6**: Configuration Management - Uses health check start periods of at least 300 seconds for AI applications
- **REQ-5**: Health Endpoint Implementation - Health checks respond within reasonable timeout limits