# ALB Connectivity Fix - Implementation Tasks

## Overview

**CRITICAL UPDATE (January 16, 2026):** Tasks updated to reflect deep infrastructure troubleshooting approach. The issue is not just ALB - it's a core networking problem preventing ANY load balancer from reaching ECS tasks. CloudFront is also misconfigured.

Implementation tasks for diagnosing and resolving the underlying network connectivity issue.

**Status:** Ready to Start  
**Priority:** P0 - Critical  
**Estimated Time:** 3-4 hours  
**Approach:** Systematic diagnosis → Fix → Verify → Update CloudFront

---

## Task 1: Run Comprehensive Network Diagnostic

**Status:** ⏳ Not Started  
**Priority:** P0  
**Estimated Time:** 60 minutes  
**Dependencies:** None

### Objectives
- Create comprehensive diagnostic script
- Check ECS task status and application health
- Analyze security groups, route tables, and NACLs
- Enable and monitor VPC Flow Logs
- Identify the specific networking issue
- Generate detailed diagnostic report with recommendations

### Acceptance Criteria
- [ ] Diagnostic script created: `scripts/diagnose-infrastructure-networking.py`
- [ ] ECS task status verified (RUNNING?)
- [ ] Task IP address obtained
- [ ] Application listening on port 8000 verified
- [ ] Security group rules analyzed (ALB SG ↔ ECS SG)
- [ ] Route tables checked (ALB subnets → ECS subnet)
- [ ] NACL rules verified
- [ ] VPC Flow Logs enabled for task ENI
- [ ] Flow logs monitored during health check attempts
- [ ] Specific issue identified
- [ ] Diagnostic report generated with recommendation

### Implementation Steps

1. **Create Diagnostic Script**
   ```python
   # scripts/diagnose-infrastructure-networking.py
   
   import boto3
   import json
   from datetime import datetime, timedelta
   
   def diagnose_infrastructure():
       """Comprehensive network diagnostic"""
       
       # Initialize clients
       ecs = boto3.client('ecs')
       ec2 = boto3.client('ec2')
       elbv2 = boto3.client('elbv2')
       logs = boto3.client('logs')
       
       report = {
           "timestamp": datetime.now().isoformat(),
           "checks": {}
       }
       
       # 1. Check ECS Task Status
       report["checks"]["ecs_task"] = check_ecs_task_status(ecs)
       
       # 2. Check Application Health
       report["checks"]["application"] = check_application_health(logs)
       
       # 3. Check Security Groups
       report["checks"]["security_groups"] = check_security_groups(ec2)
       
       # 4. Check Route Tables
       report["checks"]["route_tables"] = check_route_tables(ec2)
       
       # 5. Check NACLs
       report["checks"]["nacls"] = check_network_acls(ec2)
       
       # 6. Check VPC Flow Logs
       report["checks"]["vpc_flow_logs"] = check_vpc_flow_logs(ec2, logs)
       
       # 7. Generate Recommendation
       report["recommendation"] = generate_recommendation(report["checks"])
       
       return report
   ```

2. **Check ECS Task Status**
   ```bash
   # Get running tasks
   aws ecs list-tasks \
     --cluster multimodal-lib-prod-cluster \
     --service-name multimodal-lib-prod-service \
     --desired-status RUNNING
   
   # Get task details
   aws ecs describe-tasks \
     --cluster multimodal-lib-prod-cluster \
     --tasks <task-arn> \
     --query 'tasks[0].{Status:lastStatus,Health:healthStatus,IP:attachments[0].details[?name==`privateIPv4Address`].value|[0]}'
   ```

3. **Check Application Logs**
   ```bash
   # Check if application is running
   aws logs tail /ecs/multimodal-lib-prod-app \
     --since 10m \
     --filter-pattern "Uvicorn running"
   
   # Check for errors
   aws logs tail /ecs/multimodal-lib-prod-app \
     --since 10m \
     --filter-pattern "ERROR"
   ```

4. **Analyze Security Groups**
   ```bash
   # Get ALB security group
   aws ec2 describe-security-groups \
     --group-ids sg-0135b368e20b7bd01 \
     --query 'SecurityGroups[0].{Ingress:IpPermissions,Egress:IpPermissionsEgress}'
   
   # Get ECS security group
   aws ec2 describe-security-groups \
     --group-ids sg-0393d472e770ed1a3 \
     --query 'SecurityGroups[0].{Ingress:IpPermissions,Egress:IpPermissionsEgress}'
   
   # Check if ECS SG allows inbound from ALB SG on port 8000
   # Check if ALB SG allows outbound to ECS SG on port 8000
   ```

5. **Check Route Tables**
   ```bash
   # Get ALB subnet route tables
   aws ec2 describe-route-tables \
     --filters "Name=association.subnet-id,Values=subnet-0c352188f5398a718" \
     --query 'RouteTables[0].Routes'
   
   # Get ECS subnet route table
   aws ec2 describe-route-tables \
     --filters "Name=association.subnet-id,Values=<ecs-subnet>" \
     --query 'RouteTables[0].Routes'
   
   # Verify routes allow ALB → ECS communication
   ```

6. **Check Network ACLs**
   ```bash
   # Get NACL for ALB subnets
   aws ec2 describe-network-acls \
     --filters "Name=association.subnet-id,Values=subnet-0c352188f5398a718" \
     --query 'NetworkAcls[0].Entries'
   
   # Get NACL for ECS subnet
   aws ec2 describe-network-acls \
     --filters "Name=association.subnet-id,Values=<ecs-subnet>" \
     --query 'NetworkAcls[0].Entries'
   
   # Check for deny rules blocking port 8000
   ```

7. **Enable and Monitor VPC Flow Logs**
   ```bash
   # Enable flow logs if not already enabled
   aws ec2 create-flow-logs \
     --resource-type VPC \
     --resource-ids vpc-0b2186b38779e77f6 \
     --traffic-type ALL \
     --log-destination-type cloud-watch-logs \
     --log-group-name /aws/vpc/flowlogs/multimodal-lib-prod
   
   # Monitor flow logs for task IP
   aws logs filter-log-events \
     --log-group-name /aws/vpc/flowlogs/multimodal-lib-prod \
     --filter-pattern "<task-ip> 8000" \
     --start-time $(date -u -d '5 minutes ago' +%s)000
   ```

8. **Generate Diagnostic Report**
   ```python
   def generate_recommendation(checks):
       """Generate recommendation based on diagnostic findings"""
       
       issues = []
       
       # Check for security group issues
       if not checks["security_groups"]["alb_to_ecs_allowed"]:
           issues.append({
               "type": "security_group",
               "severity": "high",
               "description": "ECS security group missing inbound rule from ALB SG on port 8000",
               "fix": "Add security group rule: aws ec2 authorize-security-group-ingress ..."
           })
       
       # Check for route table issues
       if checks["route_tables"]["issues"]:
           issues.append({
               "type": "route_table",
               "severity": "high",
               "description": "Route table missing route for ALB → ECS communication",
               "fix": "Add route: aws ec2 create-route ..."
           })
       
       # Check for NACL issues
       if checks["nacls"]["blocking_rules"]:
           issues.append({
               "type": "nacl",
               "severity": "high",
               "description": "NACL blocking traffic on port 8000",
               "fix": "Update NACL rule: aws ec2 create-network-acl-entry ..."
           })
       
       # Check for VPC Flow Log evidence
       if checks["vpc_flow_logs"]["packets_seen"] == 0:
           issues.append({
               "type": "no_traffic",
               "severity": "critical",
               "description": "VPC Flow Logs show zero packets reaching task",
               "fix": "Indicates load balancer not sending traffic - check target registration"
           })
       
       if not issues:
           return {
               "status": "no_config_issue_found",
               "recommendation": "No configuration issue found. Consider recreating load balancer (AWS service issue)."
           }
       
       return {
           "status": "issues_found",
           "issues": issues,
           "primary_issue": issues[0],
           "recommendation": f"Fix {issues[0]['type']}: {issues[0]['fix']}"
       }
   ```

### Validation Commands
```bash
# Run diagnostic script
python scripts/diagnose-infrastructure-networking.py > infrastructure-diagnosis-<timestamp>.json

# Review report
cat infrastructure-diagnosis-<timestamp>.json | jq '.'

# Check specific sections
cat infrastructure-diagnosis-<timestamp>.json | jq '.checks.security_groups'
cat infrastructure-diagnosis-<timestamp>.json | jq '.recommendation'
```

### Success Indicators
- ✅ Script runs without errors
- ✅ All checks complete
- ✅ Specific issue identified
- ✅ Clear recommendation provided

### Files to Create
- `scripts/diagnose-infrastructure-networking.py` - Comprehensive diagnostic script
- `infrastructure-diagnosis-<timestamp>.json` - Diagnostic report

---

## Task 2: Implement Network Fix

**Status:** ⏳ Not Started  
**Priority:** P0  
**Estimated Time:** 30 minutes  
**Dependencies:** Task 1 (Diagnostic complete)

### Objectives
- Review diagnostic report
- Implement the recommended fix
- Verify fix is applied correctly
- Monitor VPC Flow Logs for traffic
- Confirm target health improves

### Acceptance Criteria
- [ ] Diagnostic report reviewed
- [ ] Fix implemented based on recommendation
- [ ] Configuration changes verified
- [ ] VPC Flow Logs show packets reaching task
- [ ] Target health status: "healthy"
- [ ] Application logs show incoming requests

### Implementation Steps

**Scenario A: Security Group Issue**
```bash
# Add rule to ECS SG for inbound from ALB SG
aws ec2 authorize-security-group-ingress \
  --group-id sg-0393d472e770ed1a3 \
  --protocol tcp \
  --port 8000 \
  --source-group sg-0135b368e20b7bd01

# Verify rule added
aws ec2 describe-security-groups \
  --group-ids sg-0393d472e770ed1a3 \
  --query 'SecurityGroups[0].IpPermissions[?ToPort==`8000`]'
```

**Scenario B: Route Table Issue**
```bash
# Add missing route
aws ec2 create-route \
  --route-table-id <rt-id> \
  --destination-cidr-block <destination> \
  --gateway-id <target>

# Verify route added
aws ec2 describe-route-tables \
  --route-table-ids <rt-id> \
  --query 'RouteTables[0].Routes'
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
  --ingress

# Verify rule added
aws ec2 describe-network-acls \
  --network-acl-ids <nacl-id> \
  --query 'NetworkAcls[0].Entries'
```

**Scenario D: No Configuration Issue (Fallback)**
```bash
# If no config issue found, recreate load balancer
# This is the original plan - create new ALB
python scripts/create-new-alb-infrastructure.py
```

### Validation Commands
```bash
# Monitor VPC Flow Logs after fix
aws logs tail /aws/vpc/flowlogs/multimodal-lib-prod \
  --follow \
  --filter-pattern "<task-ip> 8000"

# Check target health
aws elbv2 describe-target-health \
  --target-group-arn <tg-arn>

# Check application logs
aws logs tail /ecs/multimodal-lib-prod-app \
  --follow \
  --filter-pattern "GET"
```

### Rollback Procedure
```bash
# Revert security group rule
aws ec2 revoke-security-group-ingress \
  --group-id <sg-id> \
  --protocol tcp \
  --port 8000 \
  --source-group <source-sg>

# Revert route
aws ec2 delete-route \
  --route-table-id <rt-id> \
  --destination-cidr-block <destination>

# Revert NACL rule
aws ec2 delete-network-acl-entry \
  --network-acl-id <nacl-id> \
  --rule-number 100 \
  --ingress
```

### Files to Create
- `scripts/fix-network-connectivity.py` - Automated fix script
- `network-fix-<timestamp>.json` - Fix results

---

## Task 3: Verify Load Balancer Connectivity

**Status:** ⏳ Not Started  
**Priority:** P0  
**Estimated Time:** 15 minutes  
**Dependencies:** Task 3 (Load balancer connectivity verified)

### Objectives
- Backup current CloudFront configuration
- Update CloudFront origin to working load balancer DNS
- Invalidate CloudFront cache
- Wait for distribution deployment
- Test HTTPS URL through CloudFront
- Verify application loads correctly

### Acceptance Criteria
- [ ] CloudFront config backed up
- [ ] Origin updated from S3 to working load balancer DNS
- [ ] Origin protocol policy set to HTTP
- [ ] Cache invalidation created
- [ ] Distribution status: "Deployed"
- [ ] HTTPS URL returns 200 OK (not 404 from S3)
- [ ] Application loads correctly through CloudFront
- [ ] No 502 or 404 errors

### Implementation Steps

1. **Backup Current CloudFront Config**
   ```bash
   # Get current distribution config
   aws cloudfront get-distribution-config \
     --id E3NVIH7ET1R4G9 \
     --output json > cloudfront-config-backup-<timestamp>.json
   
   # Save ETag for update
   ETAG=$(aws cloudfront get-distribution-config \
     --id E3NVIH7ET1R4G9 \
     --query 'ETag' \
     --output text)
   ```

2. **Get Working Load Balancer DNS**
   ```bash
   # Get ALB DNS (or NLB if using that)
   LB_DNS=$(aws elbv2 describe-load-balancers \
     --names multimodal-lib-prod-alb \
     --query 'LoadBalancers[0].DNSName' \
     --output text)
   
   echo "Load Balancer DNS: $LB_DNS"
   ```

3. **Update CloudFront Origin**
   ```python
   # Use script to update CloudFront
   python scripts/update-cloudfront-to-working-lb.py \
     --distribution-id E3NVIH7ET1R4G9 \
     --origin-dns $LB_DNS \
     --protocol http-only
   ```
   
   Or manually:
   ```bash
   # Edit the config JSON to update origin domain
   # Then apply update
   aws cloudfront update-distribution \
     --id E3NVIH7ET1R4G9 \
     --distribution-config file://cloudfront-config-updated.json \
     --if-match $ETAG
   ```

4. **Create Cache Invalidation**
   ```bash
   # Invalidate all cached content
   aws cloudfront create-invalidation \
     --distribution-id E3NVIH7ET1R4G9 \
     --paths "/*"
   ```

5. **Wait for Deployment**
   ```bash
   # Monitor deployment status
   watch -n 30 'aws cloudfront get-distribution \
     --id E3NVIH7ET1R4G9 \
     --query "Distribution.Status" \
     --output text'
   
   # Expected: "Deployed" (takes 5-10 minutes)
   ```

6. **Test HTTPS URL**
   ```bash
   # Test health check through CloudFront
   curl -v https://d3a2xw711pvw5j.cloudfront.net/api/health/simple
   
   # Expected: HTTP 200 OK (not 404 from S3)
   
   # Test main page
   curl -v https://d3a2xw711pvw5j.cloudfront.net/
   
   # Expected: HTTP 200 OK, HTML content
   ```

7. **Test in Browser**
   ```bash
   # Open in browser
   open https://d3a2xw711pvw5j.cloudfront.net/
   
   # Expected: Application loads correctly
   # Expected: No 502 or 404 errors
   ```

### Validation Commands
```bash
# Check distribution status
aws cloudfront get-distribution \
  --id E3NVIH7ET1R4G9 \
  --query 'Distribution.{Status:Status,Origin:DistributionConfig.Origins.Items[0].DomainName}'

# Check invalidation status
aws cloudfront list-invalidations \
  --distribution-id E3NVIH7ET1R4G9 \
  --query 'InvalidationList.Items[0].{Id:Id,Status:Status}'

# Test HTTPS endpoint
curl -I https://d3a2xw711pvw5j.cloudfront.net/

# Test with verbose output
curl -v https://d3a2xw711pvw5j.cloudfront.net/ 2>&1 | grep -E "(HTTP|Server|X-Cache)"
```

### Success Indicators
- ✅ CloudFront config backed up
- ✅ Origin updated to load balancer DNS
- ✅ Distribution deployed
- ✅ HTTPS returns 200 OK (not 404)
- ✅ Application loads in browser
- ✅ No 502 or 404 errors

### Rollback Procedure
```bash
# Restore original CloudFront config
aws cloudfront update-distribution \
  --id E3NVIH7ET1R4G9 \
  --distribution-config file://cloudfront-config-backup-<timestamp>.json \
  --if-match <new-etag>

# Create new invalidation
aws cloudfront create-invalidation \
  --distribution-id E3NVIH7ET1R4G9 \
  --paths "/*"
```

### Files to Create
- `scripts/update-cloudfront-to-working-lb.py` - CloudFront update script
- `cloudfront-config-backup-<timestamp>.json` - Backup of original config
- `cloudfront-update-<timestamp>.json` - Update results

---

## Task 5: Cleanup and Documentation
**Status:** ⏳ Not Started  
**Priority:** P1  
**Estimated Time:** 30 minutes  
**Dependencies:** Task 4 (CloudFront updated and working)

### Objectives
- Verify system is stable for 30+ minutes
- Delete any unused load balancers (if applicable)
- Disable VPC Flow Logs to reduce costs
- Update all documentation with fix details
- Document root cause and resolution
- Create runbook for future reference

### Acceptance Criteria
- [ ] System stable for 30+ minutes
- [ ] Unused load balancers deleted (if any)
- [ ] VPC Flow Logs disabled or retention reduced
- [ ] Documentation updated with fix details
- [ ] Root cause documented
- [ ] Resolution steps documented
- [ ] Runbook created for future reference

### Implementation Steps

1. **Verify System Stability**
   ```bash
   # Monitor for 30 minutes
   for i in {1..60}; do
     STATUS=$(curl -s -o /dev/null -w "%{http_code}" https://d3a2xw711pvw5j.cloudfront.net/api/health/simple)
     echo "$(date): $STATUS"
     if [ "$STATUS" != "200" ]; then
       echo "ERROR: Non-200 status detected!"
     fi
     sleep 30
   done
   
   # Expected: All 200 responses
   ```

2. **Delete Unused Load Balancers (if applicable)**
   ```bash
   # List all load balancers
   aws elbv2 describe-load-balancers \
     --query 'LoadBalancers[*].{Name:LoadBalancerName,Type:Type,State:State.Code}'
   
   # Delete unused ALB-v2 (if exists and not in use)
   aws elbv2 delete-load-balancer \
     --load-balancer-arn <unused-alb-arn>
   
   # Delete unused NLB (if exists and not in use)
   aws elbv2 delete-load-balancer \
     --load-balancer-arn <unused-nlb-arn>
   
   # Wait for deletion
   sleep 120
   
   # Delete unused target groups
   aws elbv2 delete-target-group \
     --target-group-arn <unused-tg-arn>
   ```

3. **Disable or Reduce VPC Flow Logs**
   ```bash
   # Option A: Delete flow logs (if no longer needed)
   aws ec2 delete-flow-logs \
     --flow-log-ids <flow-log-id>
   
   # Option B: Reduce retention (keep for troubleshooting)
   aws logs put-retention-policy \
     --log-group-name /aws/vpc/flowlogs/multimodal-lib-prod \
     --retention-in-days 1
   ```

4. **Update Documentation**
   
   Create/update these files:
   
   **ALB_CONNECTIVITY_FIX_SUCCESS.md:**
   ```markdown
   # ALB Connectivity Fix - Success Summary
   
   **Date:** January 16, 2026
   **Status:** ✅ RESOLVED
   
   ## Problem
   - CloudFront returning 404 from S3 (misconfigured)
   - ALB cannot reach ECS tasks (health checks timeout)
   - NLB timing out (not responding)
   
   ## Root Cause
   [Document the specific issue found: security group, route table, NACL, or AWS service issue]
   
   ## Solution
   [Document the fix that was implemented]
   
   ## Resolution Steps
   1. Ran comprehensive network diagnostic
   2. Identified issue: [specific issue]
   3. Implemented fix: [specific fix]
   4. Verified connectivity
   5. Updated CloudFront origin
   6. Tested HTTPS URL
   
   ## Final Configuration
   - Load Balancer: [ALB or NLB name]
   - Target Group: [TG name]
   - CloudFront Origin: [LB DNS]
   - Status: ✅ Working
   
   ## Lessons Learned
   [Document what was learned from this issue]
   ```
   
   **Update INFRASTRUCTURE_DIAGNOSIS_SUMMARY.md:**
   - Add resolution section
   - Document root cause
   - Mark as resolved
   
   **Update LOAD_BALANCER_ANALYSIS.md:**
   - Update with final configuration
   - Remove references to unused load balancers
   - Document cost savings

5. **Create Runbook**
   
   **docs/runbooks/load-balancer-connectivity-troubleshooting.md:**
   ```markdown
   # Load Balancer Connectivity Troubleshooting Runbook
   
   ## Symptoms
   - Load balancer health checks failing
   - 502 Bad Gateway errors
   - Target health: "unhealthy"
   
   ## Diagnostic Steps
   1. Check ECS task status
   2. Verify application is running
   3. Analyze security groups
   4. Check route tables
   5. Verify NACLs
   6. Enable VPC Flow Logs
   7. Monitor flow logs for traffic
   
   ## Common Issues
   1. Security group missing inbound rule
   2. Route table missing route
   3. NACL blocking traffic
   4. AWS service issue (requires recreation)
   
   ## Resolution Steps
   [Document the steps that worked]
   ```

6. **Verify Documentation**
   ```bash
   # Check all documentation files exist
   ls -la ALB_CONNECTIVITY_FIX_SUCCESS.md
   ls -la INFRASTRUCTURE_DIAGNOSIS_SUMMARY.md
   ls -la LOAD_BALANCER_ANALYSIS.md
   ls -la docs/runbooks/load-balancer-connectivity-troubleshooting.md
   ```

### Validation Commands
```bash
# Verify system is stable
curl -I https://d3a2xw711pvw5j.cloudfront.net/

# Verify unused resources deleted
aws elbv2 describe-load-balancers \
  --query 'LoadBalancers[*].LoadBalancerName'

# Verify VPC Flow Logs status
aws ec2 describe-flow-logs \
  --filter "Name=resource-id,Values=vpc-0b2186b38779e77f6"

# Verify documentation exists
ls -la *FIX_SUCCESS.md
```

### Files to Create/Update
- `ALB_CONNECTIVITY_FIX_SUCCESS.md` - Complete success summary
- `INFRASTRUCTURE_DIAGNOSIS_SUMMARY.md` - Update with resolution
- `LOAD_BALANCER_ANALYSIS.md` - Update with final config
- `docs/runbooks/load-balancer-connectivity-troubleshooting.md` - Troubleshooting runbook
- `.kiro/specs/alb-connectivity-fix/requirements.md` - Mark as resolved
- `.kiro/specs/alb-connectivity-fix/design.md` - Add resolution notes
- `.kiro/specs/alb-connectivity-fix/tasks.md` - Mark all tasks complete

---

## Task 6: Create New ECS Service with ALB (Long-Term Solution)

**Status:** ⏳ Not Started  
**Priority:** P1 (After immediate fix)  
**Estimated Time:** 90 minutes  
**Dependencies:** Task 3 (Load balancer connectivity verified)

### Objectives
- Create a script to set up a new ECS service with the ALB target group
- Implement proper architectural solution (cannot change LB on existing service)
- Enable blue-green deployment capability
- Provide clean migration path from current service
- Document the proper way to switch load balancers in ECS

### Background

**Root Cause from Analysis:**
- CloudFront is unreachable because we updated it to point to an NLB (Network Load Balancer)
- NLBs are designed for TCP/UDP traffic, not HTTP/HTTPS
- NLBs don't work well with CloudFront for web applications
- We need an ALB (Application Load Balancer) instead

**The Problem:**
- NLB: Layer 4 (TCP/UDP) - wrong for HTTP traffic with CloudFront
- ALB: Layer 7 (HTTP/HTTPS) - correct for web applications with CloudFront

**Current Status:**
- ✅ CloudFront is configured to use ALB-v2
- ✅ ECS service is still using NLB
- ❌ Cannot change load balancer on existing ECS service (AWS limitation)

**Recommended Solution:**
Create a new ECS service with the ALB target group, then switch traffic. This is the proper architectural solution.

**Temporary Workaround:**
Use the NLB directly (no CloudFront): `http://multimodal-lib-prod-nlb-9f03ee5dda51903f.elb.us-east-1.amazonaws.com:8000`

### Acceptance Criteria
- [ ] Script created: `scripts/create-ecs-service-with-alb.py`
- [ ] Script validates ALB and target group exist
- [ ] Script creates new ECS service with ALB configuration
- [ ] New service uses same task definition as current service
- [ ] New service has proper health check grace period
- [ ] Script includes rollback capability
- [ ] Documentation created for migration process
- [ ] Blue-green deployment strategy documented
- [ ] Cost analysis for running dual services temporarily

### Implementation Steps

1. **Create ECS Service Creation Script**
   ```python
   # scripts/create-ecs-service-with-alb.py
   
   import boto3
   import json
   from datetime import datetime
   
   def create_ecs_service_with_alb():
       """
       Create a new ECS service with ALB target group.
       
       This is the proper solution because:
       1. Cannot change load balancer on existing ECS service
       2. ALB is correct for HTTP/HTTPS traffic with CloudFront
       3. Enables blue-green deployment
       """
       
       ecs = boto3.client('ecs')
       elbv2 = boto3.client('elbv2')
       
       # Configuration
       cluster_name = "multimodal-lib-prod-cluster"
       old_service_name = "multimodal-lib-prod-service"
       new_service_name = "multimodal-lib-prod-service-alb"
       alb_target_group_arn = "<alb-target-group-arn>"  # From Task 3
       
       # 1. Get current service configuration
       print("Getting current service configuration...")
       current_service = ecs.describe_services(
           cluster=cluster_name,
           services=[old_service_name]
       )['services'][0]
       
       # 2. Validate ALB target group exists
       print("Validating ALB target group...")
       target_group = elbv2.describe_target_groups(
           TargetGroupArns=[alb_target_group_arn]
       )['TargetGroups'][0]
       
       assert target_group['Protocol'] == 'HTTP', "Target group must be HTTP"
       assert target_group['Port'] == 8000, "Target group must be on port 8000"
       
       # 3. Create new service with ALB
       print(f"Creating new service: {new_service_name}...")
       
       response = ecs.create_service(
           cluster=cluster_name,
           serviceName=new_service_name,
           taskDefinition=current_service['taskDefinition'],
           loadBalancers=[
               {
                   'targetGroupArn': alb_target_group_arn,
                   'containerName': 'multimodal-lib-prod-app',
                   'containerPort': 8000
               }
           ],
           desiredCount=1,  # Start with 1, scale up after verification
           launchType='FARGATE',
           platformVersion='LATEST',
           networkConfiguration={
               'awsvpcConfiguration': {
                   'subnets': current_service['networkConfiguration']['awsvpcConfiguration']['subnets'],
                   'securityGroups': current_service['networkConfiguration']['awsvpcConfiguration']['securityGroups'],
                   'assignPublicIp': 'DISABLED'
               }
           },
           healthCheckGracePeriodSeconds=300,  # 5 minutes for startup
           deploymentConfiguration={
               'maximumPercent': 200,
               'minimumHealthyPercent': 100,
               'deploymentCircuitBreaker': {
                   'enable': True,
                   'rollback': True
               }
           },
           tags=[
               {'key': 'Name', 'value': new_service_name},
               {'key': 'Environment', 'value': 'production'},
               {'key': 'LoadBalancer', 'value': 'ALB'},
               {'key': 'CreatedDate', 'value': datetime.now().isoformat()}
           ]
       )
       
       print(f"✅ Service created: {new_service_name}")
       print(f"Service ARN: {response['service']['serviceArn']}")
       
       return response
   
   def wait_for_service_stable(cluster_name, service_name, timeout_minutes=10):
       """Wait for service to become stable"""
       ecs = boto3.client('ecs')
       
       print(f"Waiting for service {service_name} to become stable...")
       
       waiter = ecs.get_waiter('services_stable')
       waiter.wait(
           cluster=cluster_name,
           services=[service_name],
           WaiterConfig={
               'Delay': 15,
               'MaxAttempts': timeout_minutes * 4  # 15s * 4 = 1 minute
           }
       )
       
       print(f"✅ Service {service_name} is stable")
   
   def verify_target_health(target_group_arn):
       """Verify targets are healthy"""
       elbv2 = boto3.client('elbv2')
       
       print("Checking target health...")
       
       health = elbv2.describe_target_health(
           TargetGroupArn=target_group_arn
       )
       
       for target in health['TargetHealthDescriptions']:
           state = target['TargetHealth']['State']
           print(f"Target {target['Target']['Id']}: {state}")
           
           if state != 'healthy':
               reason = target['TargetHealth'].get('Reason', 'Unknown')
               print(f"  Reason: {reason}")
       
       healthy_count = sum(1 for t in health['TargetHealthDescriptions'] 
                          if t['TargetHealth']['State'] == 'healthy')
       
       return healthy_count > 0
   
   if __name__ == "__main__":
       # Create new service
       result = create_ecs_service_with_alb()
       
       # Wait for service to stabilize
       wait_for_service_stable(
           cluster_name="multimodal-lib-prod-cluster",
           service_name="multimodal-lib-prod-service-alb",
           timeout_minutes=10
       )
       
       # Verify target health
       target_group_arn = "<alb-target-group-arn>"
       if verify_target_health(target_group_arn):
           print("✅ New service is healthy and ready")
           print("\nNext steps:")
           print("1. Test ALB endpoint directly")
           print("2. Update CloudFront origin to ALB")
           print("3. Scale up new service")
           print("4. Scale down old service")
           print("5. Delete old service after verification")
       else:
           print("❌ Service is not healthy - investigate before proceeding")
   ```

2. **Create Migration Documentation**
   ```markdown
   # docs/deployment/alb-migration-guide.md
   
   # ECS Service Migration to ALB
   
   ## Overview
   
   This guide documents the process of migrating from NLB to ALB by creating
   a new ECS service. This is necessary because AWS does not allow changing
   the load balancer on an existing ECS service.
   
   ## Why This Approach?
   
   **Problem:**
   - Current service uses NLB (Layer 4 - TCP/UDP)
   - CloudFront needs ALB (Layer 7 - HTTP/HTTPS)
   - Cannot change load balancer on existing service
   
   **Solution:**
   - Create new service with ALB
   - Blue-green deployment
   - Zero-downtime migration
   
   ## Migration Steps
   
   ### Phase 1: Create New Service (30 minutes)
   
   1. Run creation script:
      ```bash
      python scripts/create-ecs-service-with-alb.py
      ```
   
   2. Verify service is healthy:
      ```bash
      aws ecs describe-services \
        --cluster multimodal-lib-prod-cluster \
        --services multimodal-lib-prod-service-alb
      ```
   
   3. Check target health:
      ```bash
      aws elbv2 describe-target-health \
        --target-group-arn <alb-tg-arn>
      ```
   
   ### Phase 2: Test New Service (15 minutes)
   
   1. Get ALB DNS:
      ```bash
      aws elbv2 describe-load-balancers \
        --names multimodal-lib-prod-alb-v2 \
        --query 'LoadBalancers[0].DNSName'
      ```
   
   2. Test health endpoint:
      ```bash
      curl http://<alb-dns>/api/health/simple
      ```
   
   3. Test application:
      ```bash
      curl http://<alb-dns>/
      ```
   
   ### Phase 3: Update CloudFront (15 minutes)
   
   1. Update CloudFront origin to ALB DNS
   2. Create cache invalidation
   3. Test HTTPS URL
   
   ### Phase 4: Scale and Migrate (30 minutes)
   
   1. Scale up new service:
      ```bash
      aws ecs update-service \
        --cluster multimodal-lib-prod-cluster \
        --service multimodal-lib-prod-service-alb \
        --desired-count 2
      ```
   
   2. Monitor for stability (15 minutes)
   
   3. Scale down old service:
      ```bash
      aws ecs update-service \
        --cluster multimodal-lib-prod-cluster \
        --service multimodal-lib-prod-service \
        --desired-count 0
      ```
   
   4. Monitor for issues (15 minutes)
   
   ### Phase 5: Cleanup (After 24 hours)
   
   1. Delete old service:
      ```bash
      aws ecs delete-service \
        --cluster multimodal-lib-prod-cluster \
        --service multimodal-lib-prod-service \
        --force
      ```
   
   2. Delete NLB (if no longer needed):
      ```bash
      aws elbv2 delete-load-balancer \
        --load-balancer-arn <nlb-arn>
      ```
   
   ## Rollback Procedure
   
   If issues occur:
   
   1. Scale up old service:
      ```bash
      aws ecs update-service \
        --cluster multimodal-lib-prod-cluster \
        --service multimodal-lib-prod-service \
        --desired-count 1
      ```
   
   2. Revert CloudFront origin to NLB
   
   3. Scale down new service:
      ```bash
      aws ecs update-service \
        --cluster multimodal-lib-prod-cluster \
        --service multimodal-lib-prod-service-alb \
        --desired-count 0
      ```
   
   4. Delete new service after verification
   
   ## Cost Analysis
   
   **During Migration (Dual Services):**
   - Old service: 1 task × 20GB = ~$100/month
   - New service: 1 task × 20GB = ~$100/month
   - Total: ~$200/month (temporary)
   
   **After Migration:**
   - New service: 1 task × 20GB = ~$100/month
   - Same as before
   
   **Duration:** Keep dual services for 24 hours for safety
   **Additional Cost:** ~$7 for 24 hours of dual services
   
   ## Success Criteria
   
   - ✅ New service running and healthy
   - ✅ ALB health checks passing
   - ✅ CloudFront routing to ALB
   - ✅ HTTPS URL returns 200 OK
   - ✅ Application fully functional
   - ✅ Old service scaled down
   - ✅ System stable for 24+ hours
   ```

3. **Create Blue-Green Deployment Strategy**
   ```markdown
   # docs/deployment/blue-green-deployment-strategy.md
   
   # Blue-Green Deployment Strategy for Load Balancer Migration
   
   ## Overview
   
   Blue-green deployment allows zero-downtime migration from NLB to ALB
   by running both services simultaneously and switching traffic.
   
   ## Architecture
   
   ```
   Blue Environment (Current):
   CloudFront → NLB → ECS Service (multimodal-lib-prod-service)
   
   Green Environment (New):
   CloudFront → ALB → ECS Service (multimodal-lib-prod-service-alb)
   ```
   
   ## Deployment Phases
   
   ### Phase 1: Green Environment Setup
   - Create ALB and target group
   - Create new ECS service with ALB
   - Verify green environment is healthy
   - Keep blue environment running
   
   ### Phase 2: Traffic Split Testing
   - Route 10% traffic to green (optional)
   - Monitor metrics and errors
   - Gradually increase to 50%
   - Verify performance is acceptable
   
   ### Phase 3: Full Cutover
   - Route 100% traffic to green
   - Monitor for issues
   - Keep blue environment running (standby)
   
   ### Phase 4: Blue Environment Decommission
   - After 24 hours of stability
   - Scale down blue environment
   - Delete blue service
   - Delete NLB (if no longer needed)
   
   ## Rollback Strategy
   
   At any phase, can instantly rollback:
   - Update CloudFront origin back to NLB
   - Scale up blue service if scaled down
   - Zero downtime rollback
   
   ## Monitoring During Migration
   
   - CloudWatch metrics for both services
   - ALB target health
   - Application logs
   - Error rates
   - Response times
   - User reports
   ```

4. **Create Validation Script**
   ```python
   # scripts/validate-alb-service.py
   
   import boto3
   import requests
   import time
   
   def validate_alb_service():
       """Comprehensive validation of new ALB service"""
       
       ecs = boto3.client('ecs')
       elbv2 = boto3.client('elbv2')
       
       cluster_name = "multimodal-lib-prod-cluster"
       service_name = "multimodal-lib-prod-service-alb"
       target_group_arn = "<alb-tg-arn>"
       
       checks = {}
       
       # 1. Check service status
       print("1. Checking service status...")
       service = ecs.describe_services(
           cluster=cluster_name,
           services=[service_name]
       )['services'][0]
       
       checks['service_running'] = service['status'] == 'ACTIVE'
       checks['desired_count_met'] = service['runningCount'] == service['desiredCount']
       
       # 2. Check target health
       print("2. Checking target health...")
       health = elbv2.describe_target_health(
           TargetGroupArn=target_group_arn
       )
       
       healthy_targets = [t for t in health['TargetHealthDescriptions']
                         if t['TargetHealth']['State'] == 'healthy']
       checks['targets_healthy'] = len(healthy_targets) > 0
       
       # 3. Get ALB DNS
       print("3. Getting ALB DNS...")
       target_group = elbv2.describe_target_groups(
           TargetGroupArns=[target_group_arn]
       )['TargetGroups'][0]
       
       alb_arn = target_group['LoadBalancerArns'][0]
       alb = elbv2.describe_load_balancers(
           LoadBalancerArns=[alb_arn]
       )['LoadBalancers'][0]
       
       alb_dns = alb['DNSName']
       
       # 4. Test HTTP endpoint
       print("4. Testing HTTP endpoint...")
       try:
           response = requests.get(f"http://{alb_dns}/api/health/simple", timeout=10)
           checks['http_health_check'] = response.status_code == 200
       except Exception as e:
           print(f"   Error: {e}")
           checks['http_health_check'] = False
       
       # 5. Test application endpoint
       print("5. Testing application endpoint...")
       try:
           response = requests.get(f"http://{alb_dns}/", timeout=10)
           checks['http_application'] = response.status_code == 200
       except Exception as e:
           print(f"   Error: {e}")
           checks['http_application'] = False
       
       # 6. Check application logs
       print("6. Checking application logs...")
       logs = boto3.client('logs')
       try:
           events = logs.filter_log_events(
               logGroupName='/ecs/multimodal-lib-prod-app',
               startTime=int((time.time() - 300) * 1000),  # Last 5 minutes
               filterPattern='GET /api/health'
           )
           checks['logs_show_requests'] = len(events['events']) > 0
       except Exception as e:
           print(f"   Error: {e}")
           checks['logs_show_requests'] = False
       
       # Print results
       print("\n" + "="*50)
       print("VALIDATION RESULTS")
       print("="*50)
       
       for check, passed in checks.items():
           status = "✅ PASS" if passed else "❌ FAIL"
           print(f"{status}: {check}")
       
       all_passed = all(checks.values())
       
       print("="*50)
       if all_passed:
           print("✅ ALL CHECKS PASSED - Service is ready")
           print(f"\nALB DNS: {alb_dns}")
           print("\nNext steps:")
           print("1. Update CloudFront origin to ALB DNS")
           print("2. Test HTTPS URL")
           print("3. Scale up new service")
           print("4. Scale down old service")
       else:
           print("❌ SOME CHECKS FAILED - Investigate before proceeding")
       
       return all_passed, checks
   
   if __name__ == "__main__":
       validate_alb_service()
   ```

### Validation Commands
```bash
# Create new service
python scripts/create-ecs-service-with-alb.py

# Wait for service to stabilize
aws ecs wait services-stable \
  --cluster multimodal-lib-prod-cluster \
  --services multimodal-lib-prod-service-alb

# Validate service
python scripts/validate-alb-service.py

# Check service status
aws ecs describe-services \
  --cluster multimodal-lib-prod-cluster \
  --services multimodal-lib-prod-service-alb \
  --query 'services[0].{Status:status,Running:runningCount,Desired:desiredCount,Health:healthCheckGracePeriodSeconds}'

# Check target health
aws elbv2 describe-target-health \
  --target-group-arn <alb-tg-arn> \
  --query 'TargetHealthDescriptions[*].{Target:Target.Id,State:TargetHealth.State,Reason:TargetHealth.Reason}'

# Test ALB endpoint
ALB_DNS=$(aws elbv2 describe-load-balancers \
  --names multimodal-lib-prod-alb-v2 \
  --query 'LoadBalancers[0].DNSName' \
  --output text)

curl -v http://$ALB_DNS/api/health/simple
```

### Success Indicators
- ✅ New service created successfully
- ✅ Service status: ACTIVE
- ✅ Running count matches desired count
- ✅ Target health: "healthy"
- ✅ ALB health checks passing
- ✅ HTTP endpoint returns 200 OK
- ✅ Application logs show requests
- ✅ Ready for CloudFront migration

### Rollback Procedure
```bash
# If new service has issues, delete it
aws ecs update-service \
  --cluster multimodal-lib-prod-cluster \
  --service multimodal-lib-prod-service-alb \
  --desired-count 0

# Wait for tasks to stop
sleep 60

# Delete service
aws ecs delete-service \
  --cluster multimodal-lib-prod-cluster \
  --service multimodal-lib-prod-service-alb \
  --force

# Old service continues running unchanged
```

### Cost Analysis

**During Migration (Dual Services):**
- Old service (NLB): 1 task × 20GB × $0.04/GB/hour = ~$100/month
- New service (ALB): 1 task × 20GB × $0.04/GB/hour = ~$100/month
- **Total during migration:** ~$200/month

**Duration:** 24 hours for safety verification
**Additional cost:** ~$7 for 24 hours of dual services

**After Migration:**
- New service (ALB): 1 task × 20GB = ~$100/month
- **Same as before** (no long-term cost increase)

### Files to Create
- `scripts/create-ecs-service-with-alb.py` - Service creation script
- `scripts/validate-alb-service.py` - Validation script
- `docs/deployment/alb-migration-guide.md` - Migration documentation
- `docs/deployment/blue-green-deployment-strategy.md` - Deployment strategy
- `ECS_SERVICE_ALB_MIGRATION.md` - Summary document

---

## Summary

### Task Dependencies
```
Task 1 (Diagnostic) ⏳ READY TO START
    ↓
Task 2 (Implement Fix)
    ↓
Task 3 (Verify Connectivity)
    ↓
Task 4 (Update CloudFront)
    ↓
Task 5 (Cleanup & Documentation)
    ↓
Task 6 (Create New ECS Service with ALB) ⏳ LONG-TERM SOLUTION
```

### Total Estimated Time

**Immediate Fix (Tasks 1-5):**
- **Task 1:** 60 minutes (Comprehensive diagnostic)
- **Task 2:** 30 minutes (Implement network fix)
- **Task 3:** 15 minutes (Verify connectivity)
- **Task 4:** 15 minutes (Update CloudFront)
- **Task 5:** 30 minutes (Cleanup and documentation)
- **Subtotal:** 150 minutes (~2.5 hours)
- **Buffer:** +60 minutes for unexpected issues
- **Total with Buffer:** 3.5-4 hours

**Long-Term Solution (Task 6):**
- **Task 6:** 90 minutes (Create new ECS service with ALB)
- **Total for proper architecture:** 90 minutes (~1.5 hours)

### Critical Success Factors
1. Comprehensive diagnostic identifies specific issue
2. Fix addresses root cause (not just symptoms)
3. VPC Flow Logs show traffic reaching tasks
4. Target health status: "healthy"
5. CloudFront successfully routes to load balancer
6. HTTPS URL returns 200 OK (not 404 from S3)
7. System stable for 30+ minutes

### Key Differences from Original Plan

**Original Plan:**
- Recreate ALB with fresh configuration
- Assumption: AWS service-level issue

**Updated Plan:**
- Systematic network diagnosis first
- Identify specific configuration issue
- Implement targeted fix
- Fallback to ALB recreation if no config issue found

**Why the Change:**
- ALB switch attempt failed (same issue)
- NLB also has connectivity issues
- CloudFront completely misconfigured
- Indicates deeper networking problem
- Need to fix root cause, not just recreate resources

### Next Steps

**Ready to start:** Task 1 - Run comprehensive network diagnostic

```bash
# Create and run diagnostic script
python scripts/diagnose-infrastructure-networking.py > infrastructure-diagnosis-$(date +%s).json

# Review diagnostic report
cat infrastructure-diagnosis-*.json | jq '.recommendation'
```

The diagnostic will identify the specific issue and provide a clear recommendation for the fix.

---

**Document Status:** Ready for Implementation  
**Last Updated:** January 16, 2026  
**Next Action:** Execute Task 1 - Run comprehensive network diagnostic

</content>
</file>
