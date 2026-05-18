# ALB Connectivity Fix - Design Document

## Overview

**CRITICAL UPDATE (January 16, 2026):** This document has been updated to reflect a deeper infrastructure issue. The problem is not just ALB connectivity - it's a core networking issue preventing ANY load balancer from reaching ECS tasks. CloudFront is also completely misconfigured (pointing to S3 instead of a load balancer).

This document outlines the technical design for systematically diagnosing and resolving the underlying network connectivity issue.

**Status:** Design Phase - Updated for Deep Troubleshooting  
**Created:** January 15, 2026  
**Updated:** January 16, 2026  
**Approach:** Systematic network diagnosis and fix

## Architecture

### Current Architecture (Broken)

```
Internet
    ↓
CloudFront (E3NVIH7ET1R4G9) ❌ MISCONFIGURED
    ↓ (Pointing to S3, returning 404)
[No Load Balancer Connection]
    
Separately:
ALB (multimodal-lib-prod-alb) ❌ CANNOT REACH TASKS
    ↓ (Health checks timeout)
Target Group (multimodal-lib-prod-tg)
    ↓ (No connectivity)
    
NLB (multimodal-lib-prod-nlb) ❌ TIMING OUT
    ↓ (Not responding)
Target Group (multimodal-lib-prod-nlb-tg)
    ↓ (No connectivity)
    
ECS Task (10.0.1.x:8000) ✅ RUNNING & HEALTHY
```

**Problems:**
1. CloudFront not pointing to any load balancer (returning 404 from S3)
2. ALB cannot reach ECS tasks (health checks timeout)
3. NLB timing out (not responding)
4. Core networking issue preventing load balancer → ECS connectivity

### Target Architecture (Fixed)

```
Internet
    ↓
CloudFront (E3NVIH7ET1R4G9) ✅ FIXED
    ↓ (Updated to point to working load balancer)
Load Balancer (ALB or NLB) ✅ WORKING
    ↓ (Network issue resolved)
Target Group ✅ HEALTHY
    ↓ (Connectivity established)
ECS Task (IP:8000) ✅ HEALTHY
```

**Solution:** 
1. Diagnose and fix the core networking issue
2. Verify load balancer can reach ECS tasks
3. Update CloudFront to point to working load balancer

## Diagnostic Approach

### Phase 1: Verify Application Status

Before troubleshooting load balancers, confirm the application is actually running and accessible:

**Checks:**
1. ECS task status (RUNNING?)
2. Task IP address
3. Application listening on port 8000?
4. Health endpoints responding?
5. Application logs showing any errors?

**Tools:**
```bash
# Get task status
aws ecs describe-tasks --cluster <cluster> --tasks <task-arn>

# Get task IP
aws ecs describe-tasks ... | jq '.tasks[0].attachments[0].details[] | select(.name=="privateIPv4Address") | .value'

# Check application logs
aws logs tail /ecs/multimodal-lib-prod-app --since 10m
```

### Phase 2: Network Connectivity Diagnosis

Systematically check each layer of the network stack:

**Layer 1: Security Groups**
- ALB security group allows outbound to ECS?
- ECS security group allows inbound from ALB?
- Port 8000 explicitly allowed?

**Layer 2: Route Tables**
- ALB subnets can route to ECS subnets?
- All subnets in same VPC?
- Routes configured correctly?

**Layer 3: Network ACLs**
- NACLs allowing traffic between ALB and ECS?
- Both inbound and outbound rules?
- No explicit deny rules?

**Layer 4: VPC Flow Logs**
- Enable flow logs for task ENI
- Monitor during health check attempts
- Identify where packets are dropped

**Diagnostic Script:**
```python
def diagnose_network_connectivity():
    """Comprehensive network diagnostic"""
    
    # 1. Get ECS task details
    task_ip = get_task_ip()
    task_eni = get_task_eni()
    task_sg = get_task_security_group()
    
    # 2. Get ALB details
    alb_sg = get_alb_security_group()
    alb_subnets = get_alb_subnets()
    
    # 3. Check security groups
    sg_issues = check_security_groups(alb_sg, task_sg)
    
    # 4. Check route tables
    route_issues = check_route_tables(alb_subnets, task_ip)
    
    # 5. Check NACLs
    nacl_issues = check_network_acls(alb_subnets, task_ip)
    
    # 6. Enable and check VPC Flow Logs
    flow_log_issues = check_vpc_flow_logs(task_eni, port=8000)
    
    # 7. Generate report
    return {
        "task_ip": task_ip,
        "security_groups": sg_issues,
        "route_tables": route_issues,
        "nacls": nacl_issues,
        "flow_logs": flow_log_issues,
        "recommendation": generate_recommendation(sg_issues, route_issues, nacl_issues, flow_log_issues)
    }
```

### Phase 3: Fix Implementation

Based on diagnostic findings, implement the appropriate fix:

**Scenario A: Security Group Issue**
```bash
# Add rule to ALB SG for outbound to ECS
aws ec2 authorize-security-group-egress \
  --group-id <alb-sg> \
  --protocol tcp \
  --port 8000 \
  --source-group <ecs-sg>

# Add rule to ECS SG for inbound from ALB
aws ec2 authorize-security-group-ingress \
  --group-id <ecs-sg> \
  --protocol tcp \
  --port 8000 \
  --source-group <alb-sg>
```

**Scenario B: Route Table Issue**
```bash
# Add route if missing
aws ec2 create-route \
  --route-table-id <rt-id> \
  --destination-cidr-block <destination> \
  --gateway-id <target>
```

**Scenario C: NACL Issue**
```bash
# Add NACL rule to allow traffic
aws ec2 create-network-acl-entry \
  --network-acl-id <nacl-id> \
  --rule-number 100 \
  --protocol tcp \
  --port-range From=8000,To=8000 \
  --cidr-block <source-cidr> \
  --egress/--ingress
```

**Scenario D: AWS Service Issue**
```bash
# If no configuration issue found, recreate load balancer
# This was the original plan and may still be needed
```

### Phase 4: CloudFront Reconfiguration

Once load balancer connectivity is working:

**Steps:**
1. Identify working load balancer (ALB or NLB)
2. Get load balancer DNS name
3. Update CloudFront origin
4. Invalidate cache
5. Test HTTPS URL

**CloudFront Update:**
```python
def update_cloudfront_origin(distribution_id, new_origin_dns):
    """Update CloudFront to point to working load balancer"""
    
    # 1. Get current config
    config = get_distribution_config(distribution_id)
    
    # 2. Update origin domain
    config['Origins']['Items'][0]['DomainName'] = new_origin_dns
    config['Origins']['Items'][0]['CustomOriginConfig'] = {
        'HTTPPort': 80,
        'HTTPSPort': 443,
        'OriginProtocolPolicy': 'http-only'  # ALB handles HTTP, CloudFront handles HTTPS
    }
    
    # 3. Apply update
    update_distribution(distribution_id, config)
    
    # 4. Invalidate cache
    create_invalidation(distribution_id, paths=['/*'])
    
    # 5. Wait for deployment
    wait_for_deployment(distribution_id)
```

## Component Design

### 1. Diagnostic Script

**Name:** `scripts/diagnose-infrastructure-networking.py`

**Purpose:** Comprehensive network diagnostic to identify the specific issue

**Features:**
- Check ECS task status and get IP
- Verify application is listening on port 8000
- Analyze security group rules
- Check route table configuration
- Verify NACL rules
- Enable and analyze VPC Flow Logs
- Test direct connectivity if possible
- Generate detailed report with recommendations

**Output:**
```json
{
  "timestamp": "2026-01-16T...",
  "task_status": {
    "status": "RUNNING",
    "ip": "10.0.1.x",
    "port": 8000,
    "health": "HEALTHY"
  },
  "security_groups": {
    "alb_sg": "sg-xxx",
    "ecs_sg": "sg-yyy",
    "issues": [],
    "status": "OK"
  },
  "route_tables": {
    "alb_subnets": ["subnet-a", "subnet-b"],
    "ecs_subnet": "subnet-c",
    "issues": [],
    "status": "OK"
  },
  "nacls": {
    "issues": [],
    "status": "OK"
  },
  "vpc_flow_logs": {
    "enabled": true,
    "packets_seen": 0,
    "status": "NO_TRAFFIC"
  },
  "recommendation": "Security group issue detected: ECS SG missing inbound rule from ALB SG on port 8000"
}
```

### 2. Network Fix Script

**Name:** `scripts/fix-network-connectivity.py`

**Purpose:** Implement the fix based on diagnostic findings

**Features:**
- Accept diagnostic report as input
- Implement appropriate fix (SG, route, NACL)
- Verify fix with VPC Flow Logs
- Test connectivity after fix
- Rollback if fix doesn't work

### 3. CloudFront Update Script

**Name:** `scripts/update-cloudfront-to-working-lb.py`

**Purpose:** Update CloudFront to point to working load balancer

**Features:**
- Backup current CloudFront config
- Update origin to working load balancer
- Invalidate cache
- Wait for deployment
- Test HTTPS URL
- Rollback capability

### 4. Original ALB Recreation (Fallback)

If diagnostic doesn't find a configuration issue, fall back to original plan:

**Name:** `multimodal-lib-prod-alb-v2`

**Configuration:**
```python
{
    "name": "multimodal-lib-prod-alb-v2",
    "scheme": "internet-facing",
    "type": "application",
    "ip_address_type": "ipv4",
    "subnets": [
        "subnet-0c352188f5398a718",  # us-east-1a
        "subnet-02f4d9ecb751beb27",  # us-east-1b
        "subnet-02fe694f061238d5a"   # us-east-1c
    ],
    "security_groups": [
        "sg-0135b368e20b7bd01"  # Existing ALB security group
    ],
    "tags": [
        {"Key": "Name", "Value": "multimodal-lib-prod-alb-v2"},
        {"Key": "Environment", "Value": "production"},
        {"Key": "Application", "Value": "multimodal-librarian"},
        {"Key": "Version", "Value": "v2"},
        {"Key": "CreatedDate", "Value": "2026-01-15"}
    ]
}
```

**Security Group:** Reuse existing `sg-0135b368e20b7bd01`
- Inbound: HTTP (80), HTTPS (443) from 0.0.0.0/0
- Outbound: All traffic

### 2. New Target Group

**Name:** `multimodal-lib-prod-tg-v2`

**Configuration:**
```python
{
    "name": "multimodal-lib-prod-tg-v2",
    "protocol": "HTTP",
    "port": 8000,
    "vpc_id": "vpc-0b2186b38779e77f6",
    "target_type": "ip",
    "health_check": {
        "enabled": True,
        "protocol": "HTTP",
        "path": "/api/health/simple",
        "port": "traffic-port",
        "interval_seconds": 30,
        "timeout_seconds": 29,
        "healthy_threshold_count": 2,
        "unhealthy_threshold_count": 2,
        "matcher": {
            "http_code": "200"
        }
    },
    "deregistration_delay": 30,
    "tags": [
        {"Key": "Name", "Value": "multimodal-lib-prod-tg-v2"},
        {"Key": "Environment", "Value": "production"},
        {"Key": "Application", "Value": "multimodal-librarian"}
    ]
}
```

**Health Check Rationale:**
- Path: `/api/health/simple` - Verified to exist and return 200
- Interval: 30s - Standard interval
- Timeout: 29s - Maximum for 30s interval (leaves 1s buffer)
- Thresholds: 2/2 - Balanced between responsiveness and stability

### 3. ALB Listener

**Configuration:**
```python
{
    "protocol": "HTTP",
    "port": 80,
    "default_actions": [
        {
            "type": "forward",
            "target_group_arn": "<new-target-group-arn>"
        }
    ]
}
```

**Note:** HTTP only initially. HTTPS can be added after verifying basic connectivity.

### 4. ECS Service Update

**Update Strategy:**
```python
{
    "cluster": "multimodal-lib-prod-cluster",
    "service": "multimodal-lib-prod-service",
    "load_balancers": [
        {
            "target_group_arn": "<new-target-group-arn>",
            "container_name": "multimodal-lib-prod-app",
            "container_port": 8000
        }
    ],
    "health_check_grace_period_seconds": 300,
    "force_new_deployment": True
}
```

**Grace Period:** 300 seconds (5 minutes) to allow for:
- Container startup
- Model loading (if any)
- Health endpoint availability

### 5. CloudFront Origin Update

**Current Origin:**
```
multimodal-lib-prod-alb-1415728107.us-east-1.elb.amazonaws.com
```

**New Origin:**
```
multimodal-lib-prod-alb-v2-<id>.us-east-1.elb.amazonaws.com
```

**Update Configuration:**
```python
{
    "distribution_id": "E3NVIH7ET1R4G9",
    "origin_id": "multimodal-lib-alb",
    "domain_name": "<new-alb-dns>",
    "origin_protocol_policy": "http-only",  # Initially
    "origin_ssl_protocols": ["TLSv1.2"],
    "http_port": 80,
    "https_port": 443
}
```

**Name:** `multimodal-lib-prod-alb-v2` (if recreation needed)

This is the fallback if diagnostic shows no configuration issue.

## Implementation Phases

### Phase 1: Comprehensive Network Diagnostic (60 minutes)

**Steps:**
1. Run comprehensive diagnostic script
2. Check ECS task status and get IP address
3. Verify application is listening on port 8000
4. Analyze security group rules (ALB SG → ECS SG)
5. Check route tables for ALB subnets → ECS subnet
6. Verify NACL rules aren't blocking traffic
7. Enable VPC Flow Logs for task ENI
8. Monitor flow logs during health check attempts
9. Identify specific issue (SG, route, NACL, or AWS service)
10. Generate detailed diagnostic report

**Validation:**
- Task status: RUNNING
- Application listening: Port 8000
- Security groups: Rules analyzed
- Route tables: Configuration checked
- NACLs: Rules verified
- VPC Flow Logs: Enabled and monitored
- Issue identified: Specific problem found

**Rollback:** None (read-only diagnostic)

**Output:** Diagnostic report with specific recommendation

### Phase 2: Implement Network Fix (30 minutes)

**Steps:**
1. Review diagnostic report
2. Implement appropriate fix based on findings:
   - **If Security Group Issue:** Add missing rules
   - **If Route Table Issue:** Add missing routes
   - **If NACL Issue:** Update NACL rules
   - **If AWS Service Issue:** Recreate load balancer (fallback to original plan)
3. Verify fix is applied correctly
4. Monitor VPC Flow Logs for traffic
5. Check target health status
6. Test load balancer connectivity

**Validation:**
- Fix applied successfully
- VPC Flow Logs show packets reaching task
- Target health: "healthy"
- Load balancer returns 200 OK
- Application logs show incoming requests

**Rollback:** Revert configuration changes if fix doesn't work

### Phase 3: Verify Load Balancer Connectivity (15 minutes)

**Steps:**
1. Test load balancer DNS directly: `curl http://<lb-dns>/api/health/simple`
2. Verify VPC Flow Logs show traffic reaching task
3. Check application logs for incoming requests
4. Confirm target group health status: "healthy"
5. Monitor stability for 10 minutes
6. Run load test to verify sustained connectivity

**Validation:**
- Load balancer returns 200 OK
- VPC Flow Logs show ACCEPT entries
- Application logs show requests from load balancer
- Target health: "healthy" for 10+ minutes
- No timeout errors
- Load test passes

**Rollback:** None needed (connectivity verified)

### Phase 4: Update CloudFront Origin (15 minutes)

**Steps:**
1. Backup current CloudFront configuration
2. Update origin to working load balancer DNS
3. Set origin protocol policy to HTTP (CloudFront handles HTTPS)
4. Invalidate CloudFront cache: `/*`
5. Wait for distribution deployment (5-10 minutes)
6. Test HTTPS URL: `https://d3a2xw711pvw5j.cloudfront.net/`
7. Verify application loads correctly

**Validation:**
- CloudFront config backed up
- Origin updated to working load balancer
- Distribution status: "Deployed"
- HTTPS URL returns 200 OK
- Application loads correctly
- No 502 or 404 errors

**Rollback:** Restore CloudFront config from backup

### Phase 5: Cleanup and Documentation (15 minutes)

**Steps:**
1. Verify system is stable for 30+ minutes
2. Delete any unused load balancers (if applicable)
3. Disable VPC Flow Logs (to reduce costs)
4. Update documentation with fix details
5. Document root cause and resolution
6. Create runbook for future reference

**Validation:**
- System stable for 30+ minutes
- Unused resources deleted
- VPC Flow Logs disabled
- Documentation updated
- Root cause documented

**Rollback:** N/A (cleanup phase)

## Monitoring and Validation

### Real-Time Monitoring

**During Implementation:**
```bash
# Terminal 1: Watch target health
watch -n 5 'aws elbv2 describe-target-health \
  --target-group-arn <new-tg-arn> \
  --query "TargetHealthDescriptions[*].[Target.Id,TargetHealth.State,TargetHealth.Reason]" \
  --output table'

# Terminal 2: Watch VPC Flow Logs
aws logs tail /aws/vpc/flowlogs/multimodal-lib-prod \
  --follow \
  --filter-pattern "[version, account, eni, source, destination=10.0.*, ...]"

# Terminal 3: Watch application logs
aws logs tail /ecs/multimodal-lib-prod-app \
  --follow \
  --filter-pattern "GET /api/health"

# Terminal 4: Watch ECS service events
watch -n 10 'aws ecs describe-services \
  --cluster multimodal-lib-prod-cluster \
  --services multimodal-lib-prod-service \
  --query "services[0].events[:5]" \
  --output table'
```

### Success Criteria

**Phase 1 Success:**
- ✅ ALB created and active
- ✅ Target group created
- ✅ Listener configured
- ✅ DNS name available

**Phase 2 Success:**
- ✅ ECS service updated
- ✅ New task running
- ✅ Task registered with target group
- ✅ Target health: "healthy"

**Phase 3 Success:**
- ✅ ALB DNS returns 200 OK
- ✅ Application logs show requests
- ✅ VPC Flow Logs show packets
- ✅ No timeout errors

**Phase 4 Success:**
- ✅ CloudFront deployed
- ✅ HTTPS URL returns 200 OK
- ✅ Application loads
- ✅ No 502 errors

**Phase 5 Success:**
- ✅ Old resources deleted
- ✅ Documentation updated
- ✅ System stable

### Failure Detection

**Automated Checks:**
```python
def validate_alb_connectivity():
    checks = {
        "alb_active": check_alb_status(),
        "target_healthy": check_target_health(),
        "vpc_flow_logs": check_vpc_flow_logs(),
        "app_logs": check_application_logs(),
        "http_response": check_http_response(),
        "cloudfront_response": check_cloudfront_response()
    }
    return all(checks.values()), checks
```

**Alert Conditions:**
- Target health: "unhealthy" for > 2 minutes
- VPC Flow Logs: Zero packets for > 5 minutes
- Application logs: No requests for > 5 minutes
- HTTP response: Non-200 status code
- CloudFront: 502 errors

## Rollback Strategy

### Rollback Triggers
- Phase 2 fails: New task doesn't register or stay healthy
- Phase 3 fails: No connectivity after 15 minutes
- Phase 4 fails: CloudFront returns errors
- Any phase: Critical error or unexpected behavior

### Rollback Procedures

**From Phase 2 (ECS Service Update):**
```bash
# Revert to old target group (if it was working)
aws ecs update-service \
  --cluster multimodal-lib-prod-cluster \
  --service multimodal-lib-prod-service \
  --load-balancers targetGroupArn=<old-tg-arn>,containerName=multimodal-lib-prod-app,containerPort=8000 \
  --force-new-deployment
```

**From Phase 4 (CloudFront Update):**
```bash
# Revert CloudFront origin
aws cloudfront update-distribution \
  --id E3NVIH7ET1R4G9 \
  --distribution-config <old-config>
```

**Complete Rollback:**
1. Revert CloudFront origin (if updated)
2. Revert ECS service to old target group (if updated)
3. Delete new ALB and target group
4. Document failure and try alternative approach (NLB)

### Rollback Time
- Phase 2 rollback: ~5 minutes
- Phase 4 rollback: ~10 minutes (CloudFront propagation)
- Complete rollback: ~15 minutes

## Alternative Design: Network Load Balancer

**If ALB recreation fails, switch to NLB:**

### NLB Configuration
```python
{
    "name": "multimodal-lib-prod-nlb",
    "scheme": "internet-facing",
    "type": "network",
    "ip_address_type": "ipv4",
    "subnets": [
        "subnet-0c352188f5398a718",
        "subnet-02f4d9ecb751beb27",
        "subnet-02fe694f061238d5a"
    ]
}
```

### NLB Target Group
```python
{
    "name": "multimodal-lib-prod-nlb-tg",
    "protocol": "TCP",
    "port": 8000,
    "vpc_id": "vpc-0b2186b38779e77f6",
    "target_type": "ip",
    "health_check": {
        "enabled": True,
        "protocol": "TCP",
        "port": "traffic-port",
        "interval_seconds": 30,
        "healthy_threshold_count": 2,
        "unhealthy_threshold_count": 2
    }
}
```

**Advantages:**
- Simpler Layer 4 routing
- TCP health checks (no HTTP parsing)
- Often more reliable
- Lower latency

**Disadvantages:**
- No HTTP features (path-based routing, etc.)
- Different health check mechanism
- Requires architecture change

## Security Considerations

### Network Security
- Reuse existing security groups (already verified correct)
- No changes to security group rules needed
- VPC and subnet configuration unchanged

### Access Control
- ALB remains internet-facing (required for CloudFront)
- ECS tasks remain in private subnets
- No changes to IAM roles or policies

### Data Protection
- HTTP initially for testing
- HTTPS can be added after verification
- CloudFront provides SSL termination

## Cost Analysis

### Additional Costs (Temporary)
- **Duplicate ALB:** ~$16/month (during transition)
- **VPC Flow Logs:** ~$0.50/GB (for monitoring)

### Final Costs (After Cleanup)
- **No change:** Same infrastructure, just recreated
- **Monthly Cost:** ~$204-214/month (unchanged)

### Cost Optimization
- Delete old ALB immediately after verification
- Disable VPC Flow Logs after confirming connectivity
- No long-term cost increase

## Testing Strategy

### Unit Tests
- N/A (infrastructure change, not code)

### Integration Tests
```bash
# Test 1: ALB health check
curl -v http://<alb-dns>/api/health/simple

# Test 2: Application endpoint
curl -v http://<alb-dns>/

# Test 3: CloudFront HTTPS
curl -v https://d3a2xw711pvw5j.cloudfront.net/

# Test 4: Load test (optional)
ab -n 100 -c 10 http://<alb-dns>/api/health/simple
```

### Validation Tests
```python
def test_alb_connectivity():
    # Test ALB DNS resolves
    assert resolve_dns(alb_dns)
    
    # Test ALB returns 200
    response = requests.get(f"http://{alb_dns}/api/health/simple")
    assert response.status_code == 200
    
    # Test VPC Flow Logs show traffic
    logs = get_vpc_flow_logs(task_ip, port=8000)
    assert len(logs) > 0
    
    # Test application logs show requests
    app_logs = get_application_logs()
    assert "GET /api/health/simple" in app_logs
    
    # Test target health
    health = get_target_health(target_group_arn)
    assert health == "healthy"
```

## Documentation Updates

### Files to Update
1. `ALB_SETUP_STATUS.md` - Update with new ALB details
2. `ALB_CONNECTIVITY_DIAGNOSIS_COMPLETE.md` - Add resolution
3. `HTTPS_UPGRADE_SUCCESS_FINAL.md` - Update CloudFront origin
4. `README.md` - Update deployment instructions

### New Files to Create
1. `ALB_CONNECTIVITY_FIX_SUCCESS.md` - Implementation summary
2. `scripts/recreate-alb-and-fix-connectivity.py` - Implementation script
3. `scripts/verify-alb-connectivity.py` - Validation script

## Success Metrics

### Technical Metrics
- ALB health check success rate: 100%
- VPC Flow Log entries: > 0 packets/minute
- Application request logs: > 0 requests/minute
- Target health status: "healthy"
- HTTP response time: < 1 second
- CloudFront response time: < 3 seconds

### Business Metrics
- Application accessibility: 100%
- User satisfaction: Can access application
- Downtime: < 15 minutes during transition

## Timeline

**Total Estimated Time:** 90 minutes

- Phase 1: 30 minutes (Create ALB)
- Phase 2: 15 minutes (Update ECS)
- Phase 3: 15 minutes (Verify)
- Phase 4: 15 minutes (Update CloudFront)
- Phase 5: 15 minutes (Cleanup)

**Buffer:** +30 minutes for unexpected issues

**Total with Buffer:** 2 hours

## Approval and Sign-off

**Technical Lead:** Approved  
**User:** Awaiting implementation  
**Risk Assessment:** Low (can rollback at any phase)  
**Go/No-Go:** GO

---

**Document Status:** Ready for Implementation  
**Last Updated:** January 15, 2026  
**Next Step:** Create implementation tasks
