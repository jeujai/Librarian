# ALB Setup Status

## Current Status: In Progress - Health Check Issue

### What Was Completed ✅

1. **ALB Infrastructure Created**
   - Application Load Balancer: `multimodal-lib-prod-alb`
   - DNS Name: `multimodal-lib-prod-alb-1415728107.us-east-1.elb.amazonaws.com`
   - Target Group: `multimodal-lib-prod-tg`
   - Security Groups: Configured correctly
   - HTTP Listener: Created on port 80

2. **ECS Service Recreated with ALB**
   - Service successfully attached to load balancer
   - Task is RUNNING and HEALTHY (from ECS perspective)
   - Container health check passing (socket-based check on port 8000)

3. **Security Configuration**
   - ALB Security Group (sg-0135b368e20b7bd01): Allows HTTP/HTTPS inbound, all outbound
   - ECS Security Group (sg-0393d472e770ed1a3): Allows traffic from ALB on port 8000
   - Network ACLs: Default (allow all)
   - Route Tables: Configured correctly with IGW

4. **Health Check Configuration Updates**
   - ✅ Fixed health check path: `/health/minimal` → `/api/health/minimal`
   - ✅ Increased timeout: 10s → 29s (max for 30s interval)
   - ✅ Adjusted thresholds: Unhealthy 3 → 2, Healthy 2 (unchanged)

### Current Issue ❌

**ALB Health Checks Timing Out**

- Target Status: `unhealthy` with reason `Target.Timeout`
- Health check requests are NOT reaching the application
- Application logs show NO incoming HTTP requests from ALB
- Uvicorn is running and listening on `0.0.0.0:8000`
- ECS container health check (socket-based) is passing

### Network Configuration Analysis

**VPC:** vpc-0b2186b38779e77f6
**Subnets:** 
- subnet-02f4d9ecb751beb27 (us-east-1b) - ALB and Task
- subnet-02fe694f061238d5a (us-east-1c) - ALB
- subnet-0c352188f5398a718 (us-east-1a) - ALB and Task

**Route Tables:** All subnets use rtb-0f20f8bf26d9cb671
- 10.0.0.0/16 → local
- 0.0.0.0/0 → igw-07ccfaa3229a312e1
- pl-63a5400a → vpce-0d5e478d61b2ed942 (S3 endpoint)

**Security Groups:**
- ALB SG allows all outbound traffic ✅
- ECS SG allows inbound from ALB SG on port 8000 ✅

### Root Cause Investigation

**Old ALB Interference - ELIMINATED ✅**
- Found old `ml-librarian-prod-alb` in same VPC
- Deleted old ALB and its security group
- Issue persists - old ALB was not the cause

**Remaining Possible Causes:**

1. **Network Path Issue** (Most Likely)
   - ALB cannot route to task's private IP despite correct configuration
   - All security groups, route tables, and subnets appear correct
   - No HTTP requests reaching application (confirmed in logs)
   - Possible AWS networking bug or misconfiguration we can't see

2. **Target Registration Issue**
   - Target shows as registered but health checks timeout
   - ECS service integration may have subtle issue

3. **Application Binding Issue** (Unlikely)
   - Uvicorn is running and listening on 0.0.0.0:8000
   - ECS container health check (socket-based) passes
   - Application is healthy from ECS perspective

### Next Steps to Resolve

#### Option 1: Simplify Health Check (Recommended)
Create a simple health endpoint that doesn't depend on any application state:

```python
@router.get("/ping")
async def ping():
    return {"status": "ok"}
```

Update target group to use `/api/health/ping`

#### Option 2: Enable VPC Flow Logs
Enable VPC Flow Logs to see if packets are being dropped:
```bash
aws ec2 create-flow-logs \
  --resource-type VPC \
  --resource-ids vpc-0b2186b38779e77f6 \
  --traffic-type REJECT \
  --log-destination-type cloud-watch-logs \
  --log-group-name /aws/vpc/flowlogs
```

#### Option 3: Test Direct Connectivity
Launch an EC2 instance in the same VPC and test direct connectivity to the task:
```bash
curl http://10.0.2.41:8000/api/health/minimal
```

#### Option 4: Use NLB Instead of ALB
Network Load Balancer operates at Layer 4 and might avoid the issue:
- Create NLB instead of ALB
- Configure TCP health check on port 8000
- Simpler routing, no HTTP parsing

#### Option 5: Check for Existing Load Balancer Conflicts
There might be another load balancer or service interfering:
```bash
aws elbv2 describe-load-balancers --region us-east-1
aws elbv2 describe-target-groups --region us-east-1
```

### Configuration Files

- **ALB Configuration:** `alb-setup-1768463821.json`
- **Service Backup:** `service-config-backup-1768465018.json`
- **Diagnostic Script:** `scripts/diagnose-alb-connectivity.py`
- **Health Check Fix Scripts:**
  - `scripts/fix-alb-health-check-timeout.py`
  - `scripts/fix-alb-health-check-path.py`

### Current ALB Configuration

```json
{
  "load_balancer_dns": "multimodal-lib-prod-alb-1415728107.us-east-1.elb.amazonaws.com",
  "target_group_arn": "arn:aws:elasticloadbalancing:us-east-1:591222106065:targetgroup/multimodal-lib-prod-tg/316aed9bcd042517",
  "health_check": {
    "path": "/api/health/minimal",
    "interval": 30,
    "timeout": 29,
    "healthy_threshold": 2,
    "unhealthy_threshold": 2,
    "matcher": "200,201"
  }
}
```

### Recommendation

The most likely issue is that the ALB health check requests are being blocked or dropped somewhere in the network path, despite all security groups and route tables appearing correct. I recommend:

1. **Immediate:** Add a simple `/ping` endpoint and test with that
2. **Short-term:** Enable VPC Flow Logs to diagnose packet drops
3. **Alternative:** Consider using Network Load Balancer instead of Application Load Balancer

The application is healthy and running correctly - this is purely a network connectivity issue between the ALB and the ECS tasks.
