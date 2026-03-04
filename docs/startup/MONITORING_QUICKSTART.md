# Startup Monitoring Quick Start Guide

## 🚀 Quick Setup (5 minutes)

### Step 1: Deploy Monitoring Infrastructure

```bash
cd infrastructure/aws-native
terraform apply -target=module.monitoring
```

### Step 2: Configure Alert Notifications

```bash
python scripts/configure-startup-monitoring.py \
  --environment prod \
  --email your-email@example.com
```

### Step 3: Confirm Email Subscription

Check your email and click the SNS confirmation link.

### Step 4: Verify Configuration

```bash
python scripts/configure-startup-monitoring.py \
  --environment prod \
  --validate-only
```

## 📊 Access Dashboards

### CloudWatch Console

1. Go to AWS CloudWatch Console
2. Navigate to "Dashboards"
3. Select `multimodal-librarian-{env}-startup-monitoring`

### Direct Links

- **Startup Dashboard**: https://console.aws.amazon.com/cloudwatch/home?region=us-east-1#dashboards:name=multimodal-librarian-prod-startup-monitoring
- **Operational Dashboard**: https://console.aws.amazon.com/cloudwatch/home?region=us-east-1#dashboards:name=multimodal-librarian-prod-operational-dashboard

## 🔔 Key Alarms

| Alarm | Threshold | Severity | Action |
|-------|-----------|----------|--------|
| Minimal Phase Timeout | >60s | Critical | Check logs, verify resources |
| Model Loading Failures | >2 failures | Critical | Check model files, storage |
| User Wait Time P95 | >60s | Critical | Review performance bottlenecks |
| Health Check Failures | >3 failures | Critical | Check application health |

## 📈 Key Metrics

### Startup Performance
- **MinimalPhaseCompletionTime**: Target <30s, Alert >60s
- **EssentialPhaseCompletionTime**: Target <120s, Alert >180s
- **FullPhaseCompletionTime**: Target <300s, Alert >600s

### Model Loading
- **ModelLoadingDuration**: Target <60s, Alert >180s
- **ModelLoadingFailureCount**: Alert >2 per 5min

### User Experience
- **UserWaitTime**: Target <10s avg, Alert >30s avg
- **UserWaitTime P95**: Target <30s, Alert >60s
- **FallbackResponseCount**: Alert >50 per 5min

### Cache Performance
- **Cache Hit Rate**: Target >70%, Alert <50%

## 🔍 Quick Troubleshooting

### No Metrics Showing?

```bash
# Check if metrics are being published
aws cloudwatch list-metrics \
  --namespace "MultimodalLibrarian/prod/Startup"

# Check application logs
aws logs tail /aws/application/multimodal-librarian-prod --follow
```

### Alarms Not Triggering?

```bash
# Check alarm state
aws cloudwatch describe-alarms \
  --alarm-names "multimodal-librarian-prod-minimal-phase-timeout"

# Test alarm manually
aws cloudwatch set-alarm-state \
  --alarm-name "multimodal-librarian-prod-minimal-phase-timeout" \
  --state-value ALARM \
  --state-reason "Manual test"
```

### Not Receiving Notifications?

```bash
# Check subscription status
aws sns list-subscriptions-by-topic \
  --topic-arn "arn:aws:sns:us-east-1:ACCOUNT:multimodal-librarian-prod-startup-alerts"

# Resend confirmation
python scripts/configure-startup-monitoring.py \
  --environment prod \
  --email your-email@example.com
```

## 📝 CloudWatch Insights Queries

### Startup Phase Performance

```sql
fields @timestamp, phase, duration, status
| filter component = "StartupPhaseManager"
| filter message like /Phase transition/
| stats avg(duration) as avg_duration by phase
| sort phase asc
```

### Model Loading Analysis

```sql
fields @timestamp, model_name, duration_seconds, cache_hit
| filter component = "ModelManager"
| filter message like /Model loaded/
| stats avg(duration_seconds) as avg_load_time, 
        sum(cache_hit) as cache_hits by model_name
| sort avg_load_time desc
```

### User Wait Times by Phase

```sql
fields @timestamp, wait_time_ms, startup_phase
| filter component = "UserWaitTracking"
| stats avg(wait_time_ms) as avg_wait by startup_phase
| sort startup_phase asc
```

## 🎯 Daily Monitoring Checklist

- [ ] Check startup monitoring dashboard
- [ ] Review any active alarms
- [ ] Verify all metrics are reporting
- [ ] Check for performance trends
- [ ] Review CloudWatch Insights for anomalies

## 📚 Additional Resources

- [Full Monitoring Configuration Guide](./monitoring-configuration.md)
- [Startup Phase Management](./phase-management.md)
- [Troubleshooting Guide](./troubleshooting.md)
- [Model Loading Optimization](./model-loading-optimization.md)

## 🆘 Support

For issues or questions:
1. Check [Troubleshooting Guide](./troubleshooting.md)
2. Review CloudWatch Insights queries
3. Check application logs
4. Contact DevOps team

## 💰 Cost Estimate

**Monthly monitoring costs**: ~$15-25
- Custom metrics: ~$10
- Log storage: ~$5
- API requests: ~$5
- Alarms: Included

## 🔄 Regular Maintenance

### Weekly
- Review alarm history
- Check for false positives
- Update thresholds if needed

### Monthly
- Analyze performance trends
- Review and optimize metric costs
- Update documentation

### Quarterly
- Review alert response times
- Optimize alarm configurations
- Update runbooks based on incidents
