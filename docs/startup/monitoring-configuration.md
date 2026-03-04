# Startup Monitoring and Alerting Configuration

## Overview

This document describes the monitoring and alerting configuration for the application health and startup optimization system. The monitoring system provides comprehensive visibility into startup performance, model loading, and user experience metrics.

## Architecture

### Components

1. **CloudWatch Metrics**: Custom metrics for startup phases, model loading, and user experience
2. **CloudWatch Alarms**: Automated alerts for threshold breaches and anomalies
3. **SNS Topics**: Notification delivery for alerts
4. **CloudWatch Dashboards**: Visual monitoring and analytics
5. **CloudWatch Insights**: Log analysis and troubleshooting queries

### Metric Namespaces

All startup metrics are published to the namespace:
```
MultimodalLibrarian/{environment}/Startup
```

## Metrics

### Startup Phase Metrics

| Metric Name | Description | Unit | Threshold |
|------------|-------------|------|-----------|
| `MinimalPhaseCompletionTime` | Time to complete minimal startup phase | Seconds | 60s (warning) |
| `EssentialPhaseCompletionTime` | Time to complete essential startup phase | Seconds | 180s (warning) |
| `FullPhaseCompletionTime` | Time to complete full startup phase | Seconds | 600s (warning) |

### Model Loading Metrics

| Metric Name | Description | Unit | Threshold |
|------------|-------------|------|-----------|
| `ModelLoadingSuccessCount` | Number of successful model loads | Count | N/A |
| `ModelLoadingFailureCount` | Number of failed model loads | Count | 2 (critical) |
| `ModelLoadingDuration` | Time to load models | Seconds | 180s (warning) |

### User Experience Metrics

| Metric Name | Description | Unit | Threshold |
|------------|-------------|------|-----------|
| `UserWaitTime` | User request wait time | Milliseconds | 30000ms avg (warning), 60000ms p95 (critical) |
| `FallbackResponseCount` | Number of fallback responses | Count | 50 per 5min (warning) |

### Cache Performance Metrics

| Metric Name | Description | Unit | Threshold |
|------------|-------------|------|-----------|
| `ModelCacheHitCount` | Number of cache hits | Count | N/A |
| `ModelCacheMissCount` | Number of cache misses | Count | N/A |
| Cache Hit Rate | Calculated: hits/(hits+misses)*100 | Percentage | 50% (warning) |

### Health Check Metrics

| Metric Name | Description | Unit | Threshold |
|------------|-------------|------|-----------|
| `HealthCheckFailureCount` | Number of health check failures | Count | 3 (critical) |

## Alarms

### Critical Alarms

These alarms indicate severe issues requiring immediate attention:

1. **minimal-phase-timeout**: Minimal startup phase exceeds 60 seconds
   - **Action**: Check application logs, verify resource availability
   - **SNS Topics**: startup-alerts, critical-alerts

2. **model-loading-failures**: Multiple model loading failures detected
   - **Action**: Check model files, storage access, memory availability
   - **SNS Topics**: startup-alerts, critical-alerts

3. **user-wait-time-p95-high**: P95 user wait times exceed 60 seconds
   - **Action**: Review startup performance, check for bottlenecks
   - **SNS Topics**: startup-alerts, critical-alerts

4. **health-check-failures**: Multiple consecutive health check failures
   - **Action**: Check application health, verify dependencies
   - **SNS Topics**: startup-alerts, critical-alerts

5. **startup-failure-composite**: Composite alarm for overall startup failure
   - **Action**: Comprehensive startup system check required
   - **SNS Topics**: startup-alerts, critical-alerts

### Warning Alarms

These alarms indicate performance degradation or potential issues:

1. **essential-phase-timeout**: Essential startup phase exceeds 3 minutes
2. **full-phase-timeout**: Full startup phase exceeds 10 minutes
3. **model-loading-slow**: Average model loading time exceeds 3 minutes
4. **user-wait-time-high**: Average user wait time exceeds 30 seconds
5. **high-fallback-usage**: High fallback response usage (>50 per 5min)
6. **low-cache-hit-rate**: Cache hit rate below 50%

## SNS Topics

### startup-alerts

Primary topic for all startup-related alerts.

**Subscriptions**:
- Email notifications for DevOps team
- Optional SMS for critical alerts
- Integration with incident management systems

**Configuration**:
```bash
python scripts/configure-startup-monitoring.py \
  --environment prod \
  --email devops@example.com \
  --email oncall@example.com
```

### Integration with Existing Topics

Startup alarms also publish to existing alert topics:
- `critical-alerts`: For critical severity issues
- `warning-alerts`: For warning severity issues
- `info-alerts`: For alarm resolution notifications

## Dashboards

### Startup Monitoring Dashboard

**Name**: `{name-prefix}-startup-monitoring`

**Widgets**:

1. **Startup Phase Completion Times**
   - Line chart showing minimal, essential, and full phase durations
   - Annotations for target and threshold values
   - Helps identify phase-specific performance issues

2. **Model Loading Performance**
   - Average, maximum, and P95 model loading times
   - Identifies slow model loading patterns

3. **Model Loading Success vs Failures**
   - Stacked area chart of successful and failed loads
   - Quick visual indicator of loading reliability

4. **Model Cache Hit Rate**
   - Calculated metric showing cache effectiveness
   - Annotations for target (70%) and threshold (50%)

5. **User Wait Times**
   - Average, P95, and maximum user wait times
   - Annotations for acceptable thresholds

6. **User Experience & Health Indicators**
   - Fallback response count
   - Health check failure count
   - Combined view of UX degradation signals

7. **Recent Startup Phase Transitions**
   - Log insights table showing recent phase transitions
   - Useful for troubleshooting specific startup events

**Access**: CloudWatch Console → Dashboards → Select dashboard name

### Operational Dashboard

**Name**: `{name-prefix}-operational-dashboard`

Includes startup metrics alongside infrastructure metrics (ECS, ALB, Neptune, OpenSearch).

## CloudWatch Insights Queries

### Startup Phase Analysis

Analyzes startup phase performance over time:

```sql
fields @timestamp, phase, duration, status
| filter component = "StartupPhaseManager"
| filter message like /Phase transition/
| stats avg(duration) as avg_duration, 
        max(duration) as max_duration, 
        min(duration) as min_duration by phase
| sort phase asc
```

### Model Loading Analysis

Analyzes model loading performance and cache effectiveness:

```sql
fields @timestamp, model_name, duration_seconds, cache_hit, memory_usage_mb
| filter component = "ModelManager"
| filter message like /Model loaded/
| stats avg(duration_seconds) as avg_load_time, 
        count(*) as load_count, 
        sum(cache_hit) as cache_hits by model_name
| sort avg_load_time desc
```

### User Experience Analysis

Analyzes user wait times and fallback usage by startup phase:

```sql
fields @timestamp, wait_time_ms, fallback_used, startup_phase
| filter component = "UserWaitTracking"
| stats avg(wait_time_ms) as avg_wait, 
        max(wait_time_ms) as max_wait, 
        count(*) as request_count, 
        sum(fallback_used) as fallback_count by startup_phase
| sort startup_phase asc
```

### Startup Errors

Identifies and categorizes startup-related errors:

```sql
fields @timestamp, component, message, error_type
| filter level = "ERROR"
| filter component in ["StartupPhaseManager", "ModelManager", "HealthCheck", "ModelCache"]
| stats count(*) as error_count by component, error_type
| sort error_count desc
```

## Configuration

### Prerequisites

1. Terraform infrastructure deployed
2. AWS credentials configured
3. Python 3.8+ with boto3 installed

### Initial Setup

1. **Deploy Infrastructure**:
   ```bash
   cd infrastructure/aws-native
   terraform apply
   ```

2. **Configure SNS Subscriptions**:
   ```bash
   python scripts/configure-startup-monitoring.py \
     --environment prod \
     --region us-east-1 \
     --email devops@example.com \
     --email oncall@example.com
   ```

3. **Confirm Email Subscriptions**:
   - Check email for SNS subscription confirmation
   - Click confirmation link in each email

4. **Validate Configuration**:
   ```bash
   python scripts/configure-startup-monitoring.py \
     --environment prod \
     --validate-only \
     --output monitoring-validation-report.json
   ```

### Validation

The configuration script validates:
- ✓ All CloudWatch alarms are created
- ✓ All metric filters are configured
- ✓ Dashboards are available
- ✓ SNS subscriptions are confirmed
- ✓ Alarm actions are properly configured

### Updating Configuration

To update alarm thresholds or add new metrics:

1. Modify `infrastructure/aws-native/modules/monitoring/startup_monitoring.tf`
2. Run `terraform plan` to review changes
3. Run `terraform apply` to apply changes
4. Validate with configuration script

## Monitoring Best Practices

### Alert Response

1. **Critical Alerts**: Respond within 15 minutes
   - Check application logs immediately
   - Review CloudWatch dashboard for context
   - Escalate if not resolved within 30 minutes

2. **Warning Alerts**: Respond within 1 hour
   - Investigate root cause
   - Document findings
   - Plan remediation if pattern persists

3. **Info Alerts**: Review during business hours
   - Track for trends
   - Update documentation if needed

### Dashboard Usage

1. **Daily Health Check**:
   - Review startup monitoring dashboard
   - Check for anomalies or trends
   - Verify all metrics are reporting

2. **Performance Analysis**:
   - Use CloudWatch Insights queries
   - Identify optimization opportunities
   - Track improvements over time

3. **Incident Investigation**:
   - Start with dashboard overview
   - Drill down with Insights queries
   - Correlate with application logs

### Metric Retention

- **High-resolution metrics**: 3 hours
- **Standard metrics**: 15 days
- **Aggregated metrics**: 63 days
- **Log data**: 30 days (configurable)

## Troubleshooting

### No Metrics Appearing

1. Check application is publishing metrics:
   ```python
   # In application code
   from src.multimodal_librarian.monitoring.startup_metrics import StartupMetricsCollector
   # Verify metrics collector is initialized and started
   ```

2. Verify CloudWatch permissions:
   ```bash
   aws cloudwatch list-metrics --namespace "MultimodalLibrarian/prod/Startup"
   ```

3. Check metric filters are processing logs:
   ```bash
   aws logs describe-metric-filters --log-group-name "/aws/application/multimodal-librarian-prod"
   ```

### Alarms Not Triggering

1. Verify alarm state:
   ```bash
   aws cloudwatch describe-alarms --alarm-names "multimodal-librarian-prod-minimal-phase-timeout"
   ```

2. Check alarm history:
   ```bash
   aws cloudwatch describe-alarm-history --alarm-name "multimodal-librarian-prod-minimal-phase-timeout"
   ```

3. Test alarm manually:
   ```bash
   aws cloudwatch set-alarm-state \
     --alarm-name "multimodal-librarian-prod-minimal-phase-timeout" \
     --state-value ALARM \
     --state-reason "Manual test"
   ```

### SNS Notifications Not Received

1. Verify subscription status:
   ```bash
   aws sns list-subscriptions-by-topic --topic-arn "arn:aws:sns:us-east-1:ACCOUNT:multimodal-librarian-prod-startup-alerts"
   ```

2. Check email spam folder

3. Reconfirm subscription if needed

## Cost Optimization

### Metric Costs

- Custom metrics: $0.30 per metric per month
- High-resolution metrics: $0.30 per metric per month
- API requests: $0.01 per 1,000 requests

**Estimated monthly cost**: ~$15-25 for startup monitoring

### Optimization Tips

1. Use metric filters instead of custom metrics where possible
2. Aggregate metrics at application level before publishing
3. Use appropriate metric resolution (standard vs high-resolution)
4. Set appropriate log retention periods

## Integration

### Application Integration

The monitoring system integrates with:
- `StartupPhaseManager`: Phase timing metrics
- `ModelManager`: Model loading metrics
- `StartupMetricsCollector`: Centralized metrics collection
- `StartupAlertsService`: Alert generation and management

### External Integration

Can integrate with:
- PagerDuty: For incident management
- Slack: For team notifications
- Datadog: For unified monitoring
- Grafana: For custom dashboards

## References

- [CloudWatch Metrics Documentation](https://docs.aws.amazon.com/cloudwatch/latest/monitoring/working_with_metrics.html)
- [CloudWatch Alarms Documentation](https://docs.aws.amazon.com/cloudwatch/latest/monitoring/AlarmThatSendsEmail.html)
- [SNS Documentation](https://docs.aws.amazon.com/sns/latest/dg/welcome.html)
- [Startup Optimization Design](./phase-management.md)
- [Troubleshooting Guide](./troubleshooting.md)
