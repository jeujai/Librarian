# ECS Service Migration to ALB

## Overview

This guide documents the process of migrating from NLB to ALB by creating a new ECS service. This is necessary because AWS does not allow changing the load balancer on an existing ECS service.

## Why This Approach?

**Problem:**
- Current service uses NLB (Layer 4 - TCP/UDP)
- CloudFront needs ALB (Layer 7 - HTTP/HTTPS)
- Cannot change load balancer on existing service

**Solution:**
- Create new service with ALB
- Blue-green deployment
- Zero-downtime migration

## Architecture

### Before Migration
```
CloudFront → NLB → ECS Service (multimodal-lib-prod-service)
```

### During Migration (Blue-Green)
```
Blue (Old):  CloudFront → NLB → ECS Service (multimodal-lib-prod-service)
Green (New): CloudFront → ALB → ECS Service (multimodal-lib-prod-service-alb)
```

### After Migration
```
CloudFront → ALB → ECS Service (multimodal-lib-prod-service-alb)
```

## Prerequisites

1. ALB and target group already created
2. Target group configured for HTTP on port 8000
3. Security groups allow ALB → ECS traffic
4. Current service running and healthy

## Migration Steps

### Phase 1: Create New Service (30 minutes)

1. **Get target group ARN:**
   ```bash
   aws elbv2 describe-target-groups \
     --names multimodal-lib-prod-tg-v2 \
     --query 'TargetGroups[0].TargetGroupArn' \
     --output text
   ```

2. **Create new service:**
   ```bash
   python scripts/create-ecs-service-with-alb.py \
     --target-group-arn <target-group-arn>
   ```

3. **Wait for service to stabilize** (script does this automatically)

4. **Verify service is healthy:**
   ```bash
   aws ecs describe-services \
     --cluster multimodal-lib-prod-cluster \
     --services multimodal-lib-prod-service-alb \
     --query 'services[0].{Status:status,Running:runningCount,Desired:desiredCount}'
   ```

### Phase 2: Validate New Service (15 minutes)

1. **Run validation script:**
   ```bash
   python scripts/validate-alb-service.py \
     --target-group-arn <target-group-arn>
   ```

2. **Check target health:**
   ```bash
   aws elbv2 describe-target-health \
     --target-group-arn <target-group-arn>
   ```

3. **Test ALB endpoint directly:**
   ```bash
   ALB_DNS=$(aws elbv2 describe-load-balancers \
     --names multimodal-lib-prod-alb-v2 \
     --query 'LoadBalancers[0].DNSName' \
     --output text)
   
   curl http://$ALB_DNS/api/health/simple
   curl http://$ALB_DNS/
   ```

### Phase 3: Update CloudFront (15 minutes)

1. **Update CloudFront origin to ALB:**
   ```bash
   python scripts/update-cloudfront-to-working-lb.py \
     --distribution-id E3NVIH7ET1R4G9 \
     --origin-dns $ALB_DNS
   ```

2. **Wait for CloudFront deployment** (5-10 minutes)

3. **Test HTTPS URL:**
   ```bash
   curl https://d3a2xw711pvw5j.cloudfront.net/api/health/simple
   curl https://d3a2xw711pvw5j.cloudfront.net/
   ```

### Phase 4: Monitor and Scale (24 hours)

1. **Monitor new service for 24 hours:**
   - Check CloudWatch metrics
   - Monitor application logs
   - Watch for errors
   - Verify user access

2. **After 24 hours of stability, scale up new service:**
   ```bash
   aws ecs update-service \
     --cluster multimodal-lib-prod-cluster \
     --service multimodal-lib-prod-service-alb \
     --desired-count 2
   ```

3. **Scale down old service:**
   ```bash
   aws ecs update-service \
     --cluster multimodal-lib-prod-cluster \
     --service multimodal-lib-prod-service \
     --desired-count 0
   ```

4. **Monitor for another 24 hours**

### Phase 5: Cleanup (After 48 hours total)

1. **Delete old service:**
   ```bash
   aws ecs delete-service \
     --cluster multimodal-lib-prod-cluster \
     --service multimodal-lib-prod-service \
     --force
   ```

2. **Delete NLB (if no longer needed):**
   ```bash
   aws elbv2 delete-load-balancer \
     --load-balancer-arn <nlb-arn>
   ```

3. **Delete NLB target group:**
   ```bash
   aws elbv2 delete-target-group \
     --target-group-arn <nlb-tg-arn>
   ```

## Rollback Procedure

If issues occur at any phase:

### Immediate Rollback (During Phase 3)

1. **Revert CloudFront origin to NLB:**
   ```bash
   aws cloudfront update-distribution \
     --id E3NVIH7ET1R4G9 \
     --distribution-config file://cloudfront-config-backup.json \
     --if-match <etag>
   ```

2. **Scale down new service:**
   ```bash
   aws ecs update-service \
     --cluster multimodal-lib-prod-cluster \
     --service multimodal-lib-prod-service-alb \
     --desired-count 0
   ```

3. **Old service continues running unchanged**

### Complete Rollback (After Phase 4)

1. **Scale up old service:**
   ```bash
   aws ecs update-service \
     --cluster multimodal-lib-prod-cluster \
     --service multimodal-lib-prod-service \
     --desired-count 1
   ```

2. **Revert CloudFront origin**

3. **Delete new service after verification**

## Cost Analysis

**During Migration (Dual Services):**
- Old service: 1 task × 20GB = ~$100/month
- New service: 1 task × 20GB = ~$100/month
- **Total:** ~$200/month (temporary)

**Duration:** 24-48 hours for safety
**Additional cost:** ~$7-14 for dual services

**After Migration:**
- New service: 1 task × 20GB = ~$100/month
- **Same as before** (no long-term cost increase)

## Monitoring

### Key Metrics to Watch

1. **ECS Service:**
   - Running task count
   - Desired vs running count
   - Service events
   - Task health

2. **ALB:**
   - Target health status
   - Request count
   - Response times
   - Error rates (4xx, 5xx)

3. **Application:**
   - Application logs
   - Error logs
   - Request patterns
   - User reports

### CloudWatch Dashboards

Monitor these metrics:
- `AWS/ECS` - Service CPU/Memory
- `AWS/ApplicationELB` - Target health, request count
- `/ecs/multimodal-lib-prod-app` - Application logs

## Troubleshooting

### Service Won't Stabilize

**Symptoms:** Service stays in "draining" or tasks keep restarting

**Solutions:**
1. Check task logs for errors
2. Verify security groups allow ALB → ECS traffic
3. Check health check configuration
4. Increase health check grace period

### Targets Unhealthy

**Symptoms:** Target health shows "unhealthy" or "initial"

**Solutions:**
1. Verify application is listening on port 8000
2. Check health endpoint returns 200 OK
3. Review VPC Flow Logs
4. Check security group rules

### CloudFront Returns Errors

**Symptoms:** 502 Bad Gateway or 504 Gateway Timeout

**Solutions:**
1. Verify ALB DNS is correct in CloudFront
2. Check ALB is responding
3. Verify origin protocol policy (HTTP)
4. Check cache behavior settings

## Success Criteria

- ✅ New service running and stable
- ✅ Target health: "healthy"
- ✅ ALB health checks passing
- ✅ HTTP endpoint returns 200 OK
- ✅ CloudFront HTTPS URL works
- ✅ Application fully functional
- ✅ No errors in logs
- ✅ System stable for 24+ hours

## References

- [Blue-Green Deployment Strategy](./blue-green-deployment-strategy.md)
- [ALB Connectivity Fix Design](.kiro/specs/alb-connectivity-fix/design.md)
- [ECS Service Creation Script](../../scripts/create-ecs-service-with-alb.py)
- [Validation Script](../../scripts/validate-alb-service.py)
