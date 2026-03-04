# ALB Health Check Connectivity Analysis

## Problem Statement
The application is running and responding to localhost health checks, but the ALB can't reach it on port 8000, resulting in "Target.Timeout" errors.

## Current Status (as of 2026-01-18 01:03 UTC)

### Application Status
- ✅ Application is running on `http://0.0.0.0:8000`
- ✅ Uvicorn started successfully
- ✅ Container health checks passing (localhost)
- ✅ Task Definition: `multimodal-lib-prod-app:58`
- ✅ Memory: 8GB, CPU: 4 vCPU

### Network Configuration
- **ECS Task IP**: `10.0.1.12`
- **ECS Task Subnet**: `subnet-0c352188f5398a718` (us-east-1a, 10.0.1.0/24)
- **ECS Security Group**: `sg-0c4dac025bda80435` (multimodal-lib-prod-ecs-tasks-sg)
- **ALB**: `multimodal-lib-prod-alb-v2`
- **ALB Security Group**: `sg-0135b368e20b7bd01` (multimodal-lib-prod-alb-sg)
- **ALB Subnets**: 
  - `subnet-0c352188f5398a718` (us-east-1a)
  - `subnet-02f4d9ecb751beb27` (us-east-1b)
  - `subnet-02fe694f061238d5a` (us-east-1c)
- **Target Group**: `multimodal-lib-prod-tg-v2`
- **Health Check Path**: `/health/simple`

### Security Group Rules

#### ECS Tasks Security Group (sg-0c4dac025bda80435)
**Ingress:**
- Port 8000 TCP from ALB SG (sg-0135b368e20b7bd01) ✅

**Egress:**
- All traffic to 0.0.0.0/0 ✅

#### ALB Security Group (sg-0135b368e20b7bd01)
**Ingress:**
- Port 80 TCP from 0.0.0.0/0
- Port 443 TCP from 0.0.0.0/0
- Port 8000 TCP from itself and 0.0.0.0/0

**Egress:**
- All traffic to 0.0.0.0/0 ✅

### Health Check Observations
From application logs:
```
2026-01-18T01:01:06 INFO:     127.0.0.1:36844 - "GET /health/simple HTTP/1.1" 200 OK
```

**Key Finding**: Health checks are coming from `127.0.0.1` (localhost), NOT from the ALB IP addresses. This means:
1. The ECS container health check is working (checks localhost)
2. The ALB health check is NOT reaching the application (timing out)

### Target Health Status
```json
{
  "ip": "10.0.1.12",
  "state": "unhealthy",
  "reason": "Target.Timeout",
  "description": "Request timed out"
}
```

## Root Cause Analysis

The ALB cannot establish a TCP connection to the ECS task on port 8000. Possible causes:

### 1. ✅ Application Not Listening (RULED OUT)
- Application is confirmed listening on `0.0.0.0:8000`
- Logs show: `INFO:     Uvicorn running on http://0.0.0.0:8000`

### 2. ✅ Security Group Misconfiguration (FIXED)
- Created dedicated ECS security group
- Configured to allow traffic from ALB security group
- Applied to ECS service

### 3. ⚠️ Network Routing Issue (INVESTIGATING)
- ALB and ECS task are in the same VPC (vpc-0b2186b38779e77f6)
- ALB is in multiple subnets including the same subnet as the ECS task
- Need to verify route tables and NACLs

### 4. ⚠️ ALB Target Registration Issue (POSSIBLE)
- Target is registered but showing as unhealthy
- Health check timeout is 10 seconds
- Health check interval is 30 seconds
- Application startup takes ~60 seconds

### 5. ⚠️ Port Mapping Issue (UNLIKELY)
- Port mapping is correct: 8000:8000
- Network mode is awsvpc (correct for Fargate)

## Actions Taken

1. ✅ Created dedicated security group for ECS tasks (`sg-0c4dac025bda80435`)
2. ✅ Configured security group to allow port 8000 from ALB SG
3. ✅ Updated ECS service to use new security group
4. ✅ Triggered new deployment
5. ✅ Verified new task is running with correct security group

## Next Steps

### Immediate Actions
1. **Verify Network ACLs**: Check if NACLs are blocking traffic between ALB and ECS
2. **Check Route Tables**: Verify routing is correct for the subnets
3. **Test Direct Connectivity**: Use AWS Systems Manager Session Manager to test connectivity from within the VPC
4. **Review ALB Logs**: Enable ALB access logs to see what's happening at the load balancer level

### Alternative Solutions
1. **Use NLB Instead**: Network Load Balancer might have better compatibility
2. **Adjust Health Check Settings**: Increase timeout and start period
3. **Add ALB IP Ranges**: Explicitly allow ALB IP ranges in security group (though this shouldn't be necessary)
4. **Check VPC Flow Logs**: Enable and analyze VPC flow logs to see where packets are being dropped

## Diagnostic Commands

```bash
# Check target health
aws elbv2 describe-target-health \
  --target-group-arn $(aws elbv2 describe-target-groups \
    --names multimodal-lib-prod-tg-v2 \
    --query 'TargetGroups[0].TargetGroupArn' \
    --output text)

# Check ECS task network interface
aws ec2 describe-network-interfaces \
  --network-interface-ids eni-0f2c024b5e3b645ad

# Check application logs
aws logs tail /ecs/multimodal-lib-prod-app --since 5m --follow

# Check security group rules
aws ec2 describe-security-groups \
  --group-ids sg-0c4dac025bda80435 sg-0135b368e20b7bd01
```

## Timeline
- **00:42 UTC**: Initial investigation started
- **00:53 UTC**: Created dedicated ECS security group
- **00:54 UTC**: Updated ECS service with new security group
- **00:58 UTC**: New task started with correct security group
- **01:01 UTC**: Task fully running, still showing Target.Timeout
- **01:03 UTC**: Confirmed ALB health checks not reaching application

## Conclusion
Despite correct security group configuration, the ALB still cannot reach the ECS task. The issue appears to be at the network layer (routing, NACLs, or ALB configuration) rather than security groups or application configuration.
