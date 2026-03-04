# Startup Monitoring Deployment Checklist

## Pre-Deployment Checklist

### Infrastructure Preparation
- [ ] AWS credentials configured with appropriate permissions
- [ ] Terraform state backend configured
- [ ] Environment variables set (ENVIRONMENT, AWS_REGION)
- [ ] Existing monitoring module deployed
- [ ] Application log group exists

### Configuration Preparation
- [ ] Alert email addresses identified
- [ ] On-call phone numbers collected (optional)
- [ ] Incident management system integration planned (optional)
- [ ] Alert severity levels reviewed and approved

## Deployment Steps

### Step 1: Review Configuration
```bash
# Review Terraform changes
cd infrastructure/aws-native
terraform plan -target=module.monitoring

# Expected resources to be created:
# - 1 SNS topic (startup-alerts)
# - 11 CloudWatch metric filters
# - 11 CloudWatch alarms
# - 1 CloudWatch composite alarm
# - 1 CloudWatch dashboard
# - 4 CloudWatch Insights queries
```

**Validation**:
- [ ] No unexpected resource deletions
- [ ] All alarm thresholds are appropriate
- [ ] SNS topic encryption is enabled
- [ ] Dashboard widgets are correctly configured

### Step 2: Deploy Infrastructure
```bash
# Apply Terraform configuration
terraform apply -target=module.monitoring

# Confirm deployment
# Type 'yes' when prompted
```

**Validation**:
- [ ] Terraform apply completed successfully
- [ ] No errors in Terraform output
- [ ] All resources created as expected
- [ ] Resource tags are correct

### Step 3: Configure SNS Subscriptions
```bash
# Configure email subscriptions
python scripts/configure-startup-monitoring.py \
  --environment prod \
  --email devops@example.com \
  --email oncall@example.com

# Optional: Add SMS subscriptions
python scripts/configure-startup-monitoring.py \
  --environment prod \
  --email devops@example.com \
  --phone +1234567890
```

**Validation**:
- [ ] Script completed successfully
- [ ] Subscription confirmation emails received
- [ ] All email addresses subscribed

### Step 4: Confirm Email Subscriptions
```bash
# Check email inbox for each subscribed address
# Click "Confirm subscription" link in each email
```

**Validation**:
- [ ] All email subscriptions confirmed
- [ ] Confirmation page displayed successfully
- [ ] No pending subscriptions remain

### Step 5: Validate Configuration
```bash
# Run validation script
python scripts/configure-startup-monitoring.py \
  --environment prod \
  --validate-only \
  --output monitoring-validation-report.json

# Review validation report
cat monitoring-validation-report.json
```

**Validation**:
- [ ] All alarms configured (11/11)
- [ ] All metric filters configured (11/11)
- [ ] All dashboards configured (1/1)
- [ ] Alarm actions valid
- [ ] Overall status: CONFIGURED

### Step 6: Run Infrastructure Tests
```bash
# Run test suite
ENVIRONMENT=prod AWS_REGION=us-east-1 \
  python -m pytest tests/infrastructure/test_startup_monitoring_configuration.py -v

# Expected: All tests should pass
```

**Validation**:
- [ ] All alarm tests pass
- [ ] All metric filter tests pass
- [ ] SNS topic tests pass
- [ ] Dashboard tests pass
- [ ] Insights query tests pass

### Step 7: Test Alert Notifications
```bash
# Manually trigger test alarm
aws cloudwatch set-alarm-state \
  --alarm-name "multimodal-librarian-prod-minimal-phase-timeout" \
  --state-value ALARM \
  --state-reason "Manual deployment test"

# Wait 1-2 minutes for notification
```

**Validation**:
- [ ] Alert notification received via email
- [ ] Alert contains correct information
- [ ] Alert severity is appropriate
- [ ] Alert includes remediation steps

```bash
# Reset alarm to OK state
aws cloudwatch set-alarm-state \
  --alarm-name "multimodal-librarian-prod-minimal-phase-timeout" \
  --state-value OK \
  --state-reason "Test complete"
```

**Validation**:
- [ ] OK notification received
- [ ] Alarm state reset successfully

### Step 8: Verify Dashboard Access
```bash
# Open CloudWatch console
# Navigate to Dashboards
# Select: multimodal-librarian-prod-startup-monitoring
```

**Validation**:
- [ ] Dashboard loads successfully
- [ ] All widgets display correctly
- [ ] Metrics are visible (may be empty initially)
- [ ] Annotations are visible
- [ ] Log insights widget works

### Step 9: Test CloudWatch Insights Queries
```bash
# In CloudWatch console:
# Navigate to Logs > Insights
# Select saved queries
# Run: multimodal-librarian-prod-startup-phase-analysis
```

**Validation**:
- [ ] Query executes successfully
- [ ] Results display correctly (may be empty initially)
- [ ] Query syntax is valid
- [ ] All 4 saved queries work

### Step 10: Document Deployment
```bash
# Create deployment record
cat > deployment-record-$(date +%Y%m%d).md << EOF
# Startup Monitoring Deployment

**Date**: $(date)
**Environment**: prod
**Deployed By**: [Your Name]
**Status**: SUCCESS

## Resources Created
- SNS Topic: multimodal-librarian-prod-startup-alerts
- CloudWatch Alarms: 11
- Metric Filters: 11
- Dashboard: multimodal-librarian-prod-startup-monitoring
- Insights Queries: 4

## Subscriptions Configured
- Email: devops@example.com (confirmed)
- Email: oncall@example.com (confirmed)

## Validation Results
- All tests passed
- Test alert received successfully
- Dashboard accessible
- Insights queries working

## Next Steps
- Monitor for false positives
- Tune thresholds as needed
- Add additional team members
EOF
```

**Validation**:
- [ ] Deployment record created
- [ ] All information documented
- [ ] Record stored in appropriate location

## Post-Deployment Checklist

### Immediate (Day 1)
- [ ] Monitor for any alarm triggers
- [ ] Check that metrics are being published
- [ ] Verify log metric filters are working
- [ ] Review dashboard for data population
- [ ] Test alert response procedures

### Short Term (Week 1)
- [ ] Review alarm history for false positives
- [ ] Tune thresholds based on actual performance
- [ ] Add additional team members to SNS subscriptions
- [ ] Document any issues or improvements needed
- [ ] Update runbooks with monitoring information

### Medium Term (Month 1)
- [ ] Analyze performance trends
- [ ] Identify optimization opportunities
- [ ] Review and update alert thresholds
- [ ] Validate cost estimates
- [ ] Conduct alert response drill

## Rollback Procedure

If issues occur during deployment:

### Step 1: Identify Issue
```bash
# Check Terraform state
terraform show

# Check AWS resources
aws cloudwatch describe-alarms --alarm-name-prefix "multimodal-librarian-prod"
```

### Step 2: Remove Problematic Resources
```bash
# Remove specific alarm
terraform destroy -target=aws_cloudwatch_metric_alarm.minimal_phase_timeout

# Or remove all startup monitoring
terraform destroy -target=module.monitoring.aws_cloudwatch_dashboard.startup_monitoring
```

### Step 3: Fix Configuration
```bash
# Edit Terraform files
vim infrastructure/aws-native/modules/monitoring/startup_monitoring.tf

# Validate changes
terraform validate
terraform plan
```

### Step 4: Redeploy
```bash
# Apply corrected configuration
terraform apply -target=module.monitoring
```

## Troubleshooting

### Issue: Terraform Apply Fails

**Symptoms**: Terraform errors during apply

**Resolution**:
1. Check AWS credentials and permissions
2. Verify Terraform state is not locked
3. Review error messages for specific issues
4. Check AWS service limits

### Issue: Metrics Not Appearing

**Symptoms**: Dashboard shows no data

**Resolution**:
1. Verify application is running and publishing logs
2. Check metric filter patterns match log format
3. Verify log group name is correct
4. Wait 5-10 minutes for initial data

### Issue: Alarms Not Triggering

**Symptoms**: No alerts received despite threshold breach

**Resolution**:
1. Check alarm state in CloudWatch console
2. Verify SNS subscriptions are confirmed
3. Check alarm evaluation periods
4. Review alarm history for state changes

### Issue: Notifications Not Received

**Symptoms**: Alarms trigger but no emails received

**Resolution**:
1. Check email spam folder
2. Verify SNS subscription is confirmed
3. Test SNS topic manually
4. Check email address is correct

## Success Criteria

Deployment is successful when:
- ✅ All Terraform resources created
- ✅ All tests passing
- ✅ SNS subscriptions confirmed
- ✅ Test alert received
- ✅ Dashboard accessible
- ✅ Insights queries working
- ✅ No errors in logs
- ✅ Documentation complete

## Sign-Off

**Deployed By**: _____________________ **Date**: _____________________

**Reviewed By**: _____________________ **Date**: _____________________

**Approved By**: _____________________ **Date**: _____________________

## References

- [Monitoring Configuration Guide](./monitoring-configuration.md)
- [Quick Start Guide](./MONITORING_QUICKSTART.md)
- [Troubleshooting Guide](./troubleshooting.md)
- [Terraform Documentation](../../infrastructure/aws-native/README.md)
