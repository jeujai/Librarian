# Startup Optimization Rollback Guide

Quick reference guide for rolling back startup optimization features.

## Quick Links

- **Full Documentation**: [rollback-procedures.md](./rollback-procedures.md)
- **General Rollback Procedures**: [../deployment/rollback-procedures.md](../deployment/rollback-procedures.md)

## When to Rollback

### Critical Issues (Immediate Rollback)
- Health checks failing consistently
- Service unable to reach stable state
- Complete service outage
- Data corruption or loss

**Action**: Run emergency rollback immediately
```bash
./scripts/emergency-startup-rollback.sh production
```

### High Priority Issues (Rollback within 15 minutes)
- Models not loading
- Startup timeouts
- Significant performance degradation
- User-facing errors

**Action**: Run full rollback
```bash
./scripts/rollback-startup-optimization.sh production
```

### Medium Priority Issues (Rollback within 1 hour)
- Cache corruption
- Incorrect loading states
- Fallback responses not working
- Monitoring issues

**Action**: Run targeted component rollback (see below)

## Rollback Scripts

### 1. Emergency Rollback (< 5 minutes)
For critical production issues requiring immediate action.

```bash
./scripts/emergency-startup-rollback.sh production
```

**What it does:**
- Rolls back to emergency stable version
- Clears model cache
- Disables all optimization features
- Sends emergency notifications
- Performs basic health check

**Time**: ~3-5 minutes

### 2. Full Rollback (< 15 minutes)
Complete rollback of all startup optimization features.

```bash
./scripts/rollback-startup-optimization.sh production
```

**What it does:**
- Backs up current configuration
- Reverts health check configuration
- Disables progressive loading
- Clears model cache
- Disables smart UX features
- Resets phase manager
- Disables monitoring alarms
- Deploys pre-optimization version

**Time**: ~10-15 minutes

### 3. Verification
Verify rollback was successful.

```bash
./scripts/verify-startup-rollback.sh production
```

**What it checks:**
- Service health
- Configuration rollback
- Task definition
- Alarm status
- Cache status
- Application health endpoint

**Time**: ~2-3 minutes

## Component-Specific Rollbacks

### Rollback Health Checks Only
```bash
# Revert to previous task definition
aws ecs update-service \
    --cluster multimodal-librarian-prod \
    --service multimodal-librarian-service \
    --task-definition multimodal-librarian-prod:previous \
    --force-new-deployment
```

### Disable Progressive Loading
```python
python scripts/disable-progressive-loading.py
```

### Clear Model Cache
```bash
./scripts/clear-model-cache.sh
```

### Disable Smart UX Features
```python
python scripts/disable-loading-states.py
python scripts/disable-fallback-responses.py
```

### Reset Phase Manager
```python
python scripts/reset-phase-manager.py
```

## Gradual Re-enablement

After a successful rollback, re-enable features gradually:

### Phase 1: Health Check Optimization (Day 1)
```bash
./scripts/gradual-reenable.sh production 1
```
Monitor for 24 hours.

### Phase 2: Model Cache (Day 2)
```bash
./scripts/gradual-reenable.sh production 2
```
Monitor cache performance for 24 hours.

### Phase 3: Progressive Loading (Day 3)
```bash
./scripts/gradual-reenable.sh production 3
```
Monitor startup phases for 24 hours.

### Phase 4: Smart UX Features (Day 4)
```bash
./scripts/gradual-reenable.sh production 4
```
Monitor user experience for 24 hours.

### Phase 5: Full Monitoring (Day 5)
```bash
./scripts/gradual-reenable.sh production 5
```
Continue monitoring for 7 days.

## Verification Checklist

After any rollback:

- [ ] Service is stable (running count = desired count)
- [ ] Health checks are passing
- [ ] Application logs show no errors
- [ ] API endpoints are responding
- [ ] Users can access the application
- [ ] Performance metrics are normal
- [ ] No alerts firing

## Common Issues and Solutions

### Issue: Health checks still failing after rollback
**Solution:**
1. Check ECS task logs
2. Verify task definition was actually updated
3. Ensure service has restarted with new task definition
4. Consider increasing health check start period manually

### Issue: Service won't stabilize
**Solution:**
1. Check for resource constraints (CPU/memory)
2. Review application logs for startup errors
3. Verify network connectivity
4. Check security group rules

### Issue: Cache clearing failed
**Solution:**
1. Manually clear S3 bucket: `aws s3 rm s3://multimodal-librarian-model-cache-prod/ --recursive`
2. Verify bucket permissions
3. Check if cache is actually causing issues

### Issue: Configuration not updating
**Solution:**
1. Verify Secrets Manager was updated
2. Force service restart: `aws ecs update-service --force-new-deployment`
3. Check IAM permissions for Secrets Manager access

## Monitoring After Rollback

### Key Metrics to Watch
- Service stability (running tasks)
- Health check success rate
- API response times
- Error rates
- User wait times
- Model loading times

### CloudWatch Dashboards
- Service Health: [Link to dashboard]
- Application Performance: [Link to dashboard]
- User Experience: [Link to dashboard]

### Log Groups
```bash
# Application logs
aws logs tail /ecs/multimodal-librarian --follow

# Health check logs
aws logs tail /ecs/multimodal-librarian/health --follow
```

## Escalation

### Level 1: On-call Engineer
- Can execute emergency rollback
- Can disable specific features
- Can clear cache

### Level 2: Team Lead
- Approves full rollback
- Decides on re-enablement timeline
- Coordinates incident response

### Level 3: Engineering Manager
- Approves database rollback
- Handles critical incidents
- Coordinates with stakeholders

## Contact Information

- **On-call Engineer**: [Pager/Phone]
- **Team Lead**: [Contact]
- **Engineering Manager**: [Contact]
- **Incident Channel**: #incidents-prod
- **Status Page**: [URL]

## Post-Rollback Actions

1. **Document Incident**
   - Create incident report
   - Document root cause
   - List actions taken
   - Note lessons learned

2. **Review Logs**
   - Application logs
   - Health check logs
   - CloudWatch metrics
   - User reports

3. **Plan Prevention**
   - Identify root cause
   - Implement fixes
   - Add monitoring
   - Update documentation

4. **Schedule Post-Mortem**
   - Within 48 hours of incident
   - Include all stakeholders
   - Document action items
   - Assign owners

## Testing Rollback Procedures

### Monthly Drill
Test partial rollback in staging:
```bash
./scripts/rollback-startup-optimization.sh staging
./scripts/verify-startup-rollback.sh staging
```

### Quarterly Drill
Test full rollback in staging:
```bash
./scripts/emergency-startup-rollback.sh staging
./scripts/verify-startup-rollback.sh staging
./scripts/gradual-reenable.sh staging 1
```

## Additional Resources

- [Startup Optimization Design](./design.md)
- [Phase Management Guide](./phase-management.md)
- [Troubleshooting Guide](./troubleshooting.md)
- [Deployment Procedures](../deployment/startup-optimization-deployment.md)
- [General Rollback Procedures](../deployment/rollback-procedures.md)

---

**Last Updated**: January 2025
**Document Owner**: DevOps Team
**Review Frequency**: Monthly
