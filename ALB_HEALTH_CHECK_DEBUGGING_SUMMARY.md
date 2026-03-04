# ALB Health Check Debugging Summary

## Date: 2026-01-17

## Problem Statement
The ALB (multimodal-lib-prod-alb-v2) cannot successfully health check the ECS tasks running the multimodal-lib-prod-service-alb, resulting in continuous "Target.Timeout" errors and task replacements.

## Investigation Findings

### 1. Application Status
- ✅ Application is running and responding
- ✅ Container health checks passing (localhost checks)
- ✅ Application listening on `0.0.0.0:8000`
- ✅ Task Definition: `multimodal-lib-prod-app:65`
- ✅ Memory: 8GB, CPU: 4 vCPU

### 2. Network Configuration
- **VPC**: `vpc-0b2186b38779e77f6`
- **ALB**: `multimodal-lib-prod-alb-v2`
- **ALB Security Group**: `sg-0135b368e20b7bd01` (multimodal-lib-prod-alb-sg)
- **ECS Security Group**: `sg-0c4dac025bda80435` (multimodal-lib-prod-ecs-tasks-sg)
- **Target Group**: `multimodal-lib-prod-tg-v2`

### 3. Security Group Analysis
✅ **ALB Security Group** (`sg-0135b368e20b7bd01`):
- Egress: All traffic allowed (0.0.0.0/0)

✅ **ECS Tasks Security Group** (`sg-0c4dac025bda80435`):
- Ingress: Port 8000 from ALB SG (`sg-0135b368e20b7bd01`)
- Egress: All traffic allowed

### 4. Network ACLs
✅ All subnets use the same NACL (`acl-00169acf1849846ce`):
- Allows ingress to port 8000
- Allows egress from port 8000

### 5. Route Tables
✅ All subnets use the same route table (`rtb-0f20f8bf26d9cb671`):
- `10.0.0.0/16` -> local
- `0.0.0.0/0` -> Internet Gateway (`igw-07ccfaa3229a312e1`)
- VPC Endpoint routes configured

### 6. Health Check Configuration

#### Container Health Check (ECS Task Definition)
```json
{
  "command": ["CMD-SHELL", "curl -f http://127.0.0.1:8000/api/health/simple || exit 1"],
  "interval": 30,
  "timeout": 15,
  "retries": 5,
  "startPeriod": 300
}
```

#### ALB Target Group Health Check
```json
{
  "HealthCheckPath": "/health/simple",
  "HealthCheckPort": "traffic-port",
  "HealthCheckProtocol": "HTTP",
  "HealthCheckIntervalSeconds": 30,
  "HealthCheckTimeoutSeconds": 10,
  "HealthyThresholdCount": 2,
  "UnhealthyThresholdCount": 3
}
```

### 7. Application Endpoints

The application has TWO health check endpoints:

1. **`/api/health/simple`** (Router-based, prefix="/api/health")
   - Defined in `src/multimodal_librarian/api/routers/health.py`
   - Returns detailed health status
   - Used by container health check

2. **`/health/simple`** (App-level, no prefix)
   - Defined in `src/multimodal_librarian/main.py` (line 2067-2071)
   - Simple endpoint: `{"status": "ok", "timestamp": time.time()}`
   - Should be used by ALB health check

### 8. Application Logs Analysis

**Container Health Checks** (Working):
```
2026-01-18T07:28:11.591000 INFO: 127.0.0.1:42834 - "GET /api/health/simple HTTP/1.1" 200 OK
```

**ALB Health Checks** (From earlier logs):
```
2026-01-18T06:57:42.618000 INFO: 10.0.2.206:10096 - "GET /health/simple HTTP/1.1" 200 OK
2026-01-18T06:57:42.669000 INFO: 10.0.3.220:20584 - "GET /health/simple HTTP/1.1" 200 OK
2026-01-18T06:57:42.768000 INFO: 10.0.1.211:35078 - "GET /health/simple HTTP/1.1" 200 OK
```

**Key Observation**: The application logs show successful 200 OK responses to ALB health checks from ALB IP addresses (`10.0.2.206`, `10.0.3.220`, `10.0.1.211`), but the ALB still reports "Target.Timeout".

## Root Cause Analysis

### The Paradox
- Application logs show: **200 OK responses to ALB IPs**
- ALB reports: **Target.Timeout**

This indicates one of the following:

1. **Response Path Issue**: The ALB can send requests to the target, but the responses are not reaching the ALB
2. **Timing Issue**: The responses are taking longer than the 10-second timeout
3. **ALB Internal Issue**: The ALB is not properly processing the responses

### Most Likely Cause: Response Timing
Looking at the application logs, the health check responses take 27-33ms, which is well within the 10-second timeout. However, there may be:
- Network latency between target and ALB
- ALB processing overhead
- Intermittent network issues

### Secondary Possibility: Asymmetric Routing
Even though security groups and NACLs appear correct, there could be:
- Ephemeral port blocking on return path
- ALB expecting responses from a different IP than the request was sent to
- Network interface issues on the ECS task

## Recommended Solutions

### Solution 1: Increase Health Check Timeout (IMMEDIATE)
```bash
aws elbv2 modify-target-group \
  --target-group-arn arn:aws:elasticloadbalancing:us-east-1:591222106065:targetgroup/multimodal-lib-prod-tg-v2/7b63a6337a5c7a34 \
  --health-check-timeout-seconds 20 \
  --health-check-interval-seconds 30 \
  --region us-east-1
```

### Solution 2: Simplify Health Check Endpoint
Ensure `/health/simple` returns immediately without any dependencies:
```python
@app.get("/health/simple")
async def simple_health_check():
    """Simple health check for load balancers."""
    return {"status": "ok", "timestamp": time.time()}
```

### Solution 3: Enable ALB Access Logs
Enable ALB access logs to see what the ALB is actually receiving:
```bash
aws elbv2 modify-load-balancer-attributes \
  --load-balancer-arn arn:aws:elasticloadbalancing:us-east-1:591222106065:loadbalancer/app/multimodal-lib-prod-alb-v2/5964a1d711ab8dfe \
  --attributes Key=access_logs.s3.enabled,Value=true Key=access_logs.s3.bucket,Value=<bucket-name> \
  --region us-east-1
```

### Solution 4: Check for Middleware Issues
Review the application middleware that might be slowing down responses:
- Session middleware
- Logging middleware
- Authentication middleware

### Solution 5: Use NLB Instead of ALB
If the issue persists, consider using a Network Load Balancer (NLB) which has simpler health check mechanics and lower latency.

## Next Steps

1. **Increase health check timeout** to 20 seconds
2. **Monitor target health** for 2-3 minutes
3. **Enable ALB access logs** for detailed debugging
4. **Review application middleware** for performance issues
5. **Consider NLB** if ALB issues persist

## Files Modified
- `scripts/fix-alb-health-check-path-mismatch.py` - Script to update health check path
- `scripts/diagnose-alb-network-connectivity.py` - Comprehensive network diagnosis script

## Status
🔴 **UNRESOLVED** - ALB health checks still timing out despite:
- Correct network configuration
- Successful application responses
- Proper security group rules
- Working NACLs and route tables

The issue appears to be related to response timing or ALB internal processing rather than network connectivity.
