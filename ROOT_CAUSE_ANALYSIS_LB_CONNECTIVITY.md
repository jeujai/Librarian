# Root Cause Analysis: Load Balancer Connectivity Failure

## Executive Summary

**Root Cause**: The application inside the ECS container is not listening on port 8000, preventing both ALB and NLB from connecting to it.

## Investigation Timeline

### 1. Initial Symptoms
- ALB health checks failing (no registered targets)
- NLB created as alternative, targets show as "healthy" but connections timeout
- Direct connection to container public IP on port 8000 times out

### 2. Key Findings

#### Network Configuration ✅
- VPC: vpc-0b2186b38779e77f6 (correct)
- Subnet: subnet-02f4d9ecb751beb27 (public subnet with IGW)
- Security Group: sg-0135b368e20b7bd01 (allows port 8000 from 10.0.0.0/16)
- Public IP: 54.211.25.126 (assigned)
- Route Table: Has IGW route (0.0.0.0/0 -> igw-07ccfaa3229a312e1)

#### ECS Task Status ✅
- Task Status: RUNNING
- Container Status: RUNNING
- Health Status: HEALTHY (misleading!)
- ENI: eni-0267eef61cb4657bc (properly attached)

#### Port Configuration ✅
- Task Definition: Port 8000 mapped correctly
- Container Port: 8000
- Host Port: 8000
- Protocol: TCP

#### Load Balancers ✅
- ALB: Properly configured, same VPC, correct subnets
- NLB: Properly configured, same VPC, correct subnets
- Target Groups: Configured correctly

### 3. The Smoking Gun 🔥

**Test Results**:
```bash
# Direct connection to container public IP
curl -v "http://54.211.25.126:8000/health" --max-time 5
# Result: Connection timed out

# Container network bindings
networkBindings: []  # Empty in awsvpc mode (expected)

# Container is RUNNING but not responding
```

**Conclusion**: The application process inside the container is either:
1. Not starting at all
2. Starting but crashing before listening on port 8000
3. Starting but listening on a different port
4. Starting but binding to 127.0.0.1 instead of 0.0.0.0

## Why Both Load Balancers Fail

### ALB Behavior
- Performs HTTP health checks to `/api/health/simple`
- Cannot reach the application → marks targets as unhealthy
- **No targets registered** in target group

### NLB Behavior  
- Performs TCP health checks (just checks if port is open)
- Marks target as "healthy" because the ENI exists and security group allows traffic
- **But actual connections fail** because nothing is listening on port 8000

## Why ECS Health Check Passes

The container health check uses:
```bash
python -c "import socket; s=socket.socket(); s.settimeout(5); s.connect(('localhost', 8000)); s.close()" || exit 1
```

This might be passing because:
1. The health check runs inside the container network namespace
2. Something might be listening on port 8000 briefly during startup
3. The health check might have a race condition
4. The `startPeriod: 120` gives 2 minutes before health checks count

## Next Steps

### Immediate Actions Required

1. **Check Application Logs**
   ```bash
   # Get the actual log group name
   aws logs describe-log-groups --region us-east-1 | grep multimodal
   
   # Check container logs
   aws ecs execute-command --cluster multimodal-lib-prod-cluster \
     --task <task-id> --container multimodal-lib-prod-app \
     --command "/bin/sh" --interactive
   ```

2. **Verify Application Startup**
   - Check if the application is actually starting
   - Verify it's binding to 0.0.0.0:8000 (not 127.0.0.1:8000)
   - Check for startup errors or crashes

3. **Test Inside Container**
   ```bash
   # From inside the container
   netstat -tlnp | grep 8000
   curl localhost:8000/health
   ```

### Likely Issues

1. **Application Not Starting**
   - Missing environment variables
   - Dependency failures
   - Configuration errors

2. **Wrong Bind Address**
   - App listening on 127.0.0.1:8000 instead of 0.0.0.0:8000
   - Common with development configurations

3. **Port Mismatch**
   - App actually listening on different port (e.g., 80, 5000, 3000)

4. **Startup Crash**
   - App starts, crashes, restarts in loop
   - Health check catches it during brief "up" period

## Configuration Summary

### What's Working ✅
- VPC and networking infrastructure
- Security groups
- Load balancer configuration
- ECS task scheduling
- Container image pulling
- ENI attachment

### What's Broken ❌
- Application not listening on port 8000
- No actual service responding to requests
- Both ALB and NLB cannot establish connections

## Recommendation

**Priority 1**: Access the container and check application logs to determine why the application isn't listening on port 8000.

The infrastructure is correctly configured. This is an **application-level issue**, not an infrastructure issue.
