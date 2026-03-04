# Lambda Container Failure Monitor

## Overview

The Container Failure Monitor is an AWS Lambda function that automatically detects infrastructure-level container failures (OOM kills, segfaults, etc.) by checking ECS task exit codes and stop reasons. It runs on a schedule and sends alerts via SNS when failures are detected.

## Why Lambda?

Container-level failures happen at the kernel level and never appear in application logs. A Lambda function provides:

- **Automated Monitoring**: Runs every 5 minutes without manual intervention
- **Immediate Alerts**: SNS notifications when failures are detected
- **Cost Effective**: Only runs when scheduled, minimal cost
- **Separation of Concerns**: Infrastructure monitoring separate from application
- **No Additional Infrastructure**: Serverless, no servers to manage

## Architecture

```
┌─────────────────┐
│  EventBridge    │  Triggers every 5 minutes
│  (Schedule)     │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Lambda         │  Checks ECS tasks
│  Function       │  for failures
└────────┬────────┘
         │
         ├──────────────┐
         │              │
         ▼              ▼
┌─────────────────┐  ┌─────────────────┐
│  ECS API        │  │  SNS Topic      │
│  (Read Only)    │  │  (Alerts)       │
└─────────────────┘  └────────┬────────┘
                              │
                              ▼
                     ┌─────────────────┐
                     │  Email          │
                     │  Subscription   │
                     └─────────────────┘
```

## Deployment

### Prerequisites

- Terraform installed
- AWS CLI configured with appropriate credentials
- ECS cluster and service already deployed

### Deploy with Terraform

```bash
# Deploy with email alerts
python scripts/deploy-container-failure-monitor.py --email your-email@example.com

# Dry run (plan only)
python scripts/deploy-container-failure-monitor.py --email your-email@example.com --dry-run

# Deploy without email (logs only)
python scripts/deploy-container-failure-monitor.py
```

### Manual Terraform Deployment

```bash
cd infrastructure/aws-native

# Initialize
terraform init

# Plan
terraform plan \
  -var="alert_email=your-email@example.com" \
  -var="enable_container_failure_monitor=true" \
  -target="module.monitoring.aws_lambda_function.container_failure_monitor"

# Apply
terraform apply \
  -var="alert_email=your-email@example.com" \
  -var="enable_container_failure_monitor=true" \
  -target="module.monitoring.aws_lambda_function.container_failure_monitor"
```

### Configuration Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `enable_container_failure_monitor` | Enable/disable the Lambda | `true` |
| `alert_email` | Email for SNS alerts | `""` (no email) |
| `check_window_minutes` | Minutes back to check | `5` |
| `ecs_cluster_name` | ECS cluster to monitor | From module |
| `ecs_service_name` | ECS service to monitor | From module |

## How It Works

### Detection Process

1. **Scheduled Trigger**: EventBridge triggers Lambda every 5 minutes
2. **Query ECS**: Lambda lists stopped tasks from the last 5 minutes
3. **Analyze Failures**: Checks exit codes and stop reasons
4. **Classify**: Determines if failure is infrastructure-level
5. **Alert**: Sends SNS notification if infrastructure failures found

### Detected Failure Types

| Exit Code | Type | Description |
|-----------|------|-------------|
| 137 | OOM Kill | Container exceeded memory limits |
| 139 | Segmentation Fault | Invalid memory access |
| 143 | Orchestrator Termination | ECS stopped the task |
| N/A | Resource Exhaustion | Detected from stop reason |

### Alert Content

Alerts include:
- Failure summary (counts by type)
- Task details (ID, exit code, stop reason, runtime)
- Resource limits (memory, CPU)
- Actionable recommendations
- Investigation commands

## Testing

### Manual Invocation

```bash
# Invoke Lambda manually
aws lambda invoke \
  --function-name multimodal-lib-prod-container-failure-monitor \
  --region us-east-1 \
  output.json

# View output
cat output.json
```

### Check Logs

```bash
# View Lambda logs
aws logs tail /aws/lambda/multimodal-lib-prod-container-failure-monitor \
  --follow \
  --region us-east-1

# Search for specific events
aws logs filter-log-events \
  --log-group-name /aws/lambda/multimodal-lib-prod-container-failure-monitor \
  --filter-pattern "ALERT_SENT" \
  --region us-east-1
```

### Simulate OOM Kill

To test the monitoring:

```bash
# Temporarily reduce memory in task definition
# Deploy and wait for OOM kill
# Lambda will detect and alert within 5 minutes
```

## Monitoring the Monitor

### CloudWatch Metrics

The Lambda function publishes metrics:
- **Invocations**: How often it runs
- **Errors**: Lambda execution errors
- **Duration**: Execution time
- **Throttles**: Rate limiting

### Alarms

An alarm is automatically created for Lambda errors:
- **Name**: `multimodal-lib-prod-container-failure-monitor-errors`
- **Threshold**: > 0 errors
- **Action**: Sends alert to SNS topic

## Cost Estimation

Assuming:
- Runs every 5 minutes (288 times/day)
- 256 MB memory
- 5 second average duration

**Monthly Cost**: ~$0.10 - $0.20

Breakdown:
- Lambda invocations: 8,640/month (free tier: 1M)
- Compute time: ~43,200 seconds (free tier: 400,000 GB-seconds)
- CloudWatch Logs: Minimal
- SNS: $0.50 per million notifications

**Total**: Essentially free within AWS free tier

## Troubleshooting

### Lambda Not Running

Check EventBridge rule:
```bash
aws events describe-rule \
  --name multimodal-lib-prod-container-failure-monitor \
  --region us-east-1
```

### No Alerts Received

1. Check SNS subscription status:
```bash
aws sns list-subscriptions-by-topic \
  --topic-arn <topic-arn> \
  --region us-east-1
```

2. Confirm email subscription (check spam folder)

3. Check Lambda logs for errors

### Permission Errors

Verify IAM role has required permissions:
- `ecs:ListTasks`
- `ecs:DescribeTasks`
- `ecs:DescribeTaskDefinition`
- `sns:Publish`
- `logs:CreateLogGroup`, `logs:CreateLogStream`, `logs:PutLogEvents`

## Integration with Existing Tools

### Use with Local Script

The Lambda function complements the local diagnostic script:

```bash
# Lambda: Automated continuous monitoring
# Runs every 5 minutes, sends alerts

# Local script: On-demand detailed analysis
python scripts/diagnose-container-failures.py
```

### CI/CD Integration

Add to deployment pipeline:

```yaml
# .github/workflows/deploy.yml
- name: Check for recent container failures
  run: |
    aws lambda invoke \
      --function-name container-failure-monitor \
      --region us-east-1 \
      output.json
    
    # Parse output and fail if failures detected
    if grep -q "ALERT_SENT" output.json; then
      echo "Container failures detected - investigate before deploying"
      exit 1
    fi
```

## Customization

### Adjust Check Frequency

Change the schedule in Terraform:

```hcl
variable "check_window_minutes" {
  default = 10  # Check every 10 minutes instead of 5
}
```

### Add Slack Notifications

Modify Lambda to post to Slack webhook:

```python
import requests

def send_slack_alert(message):
    webhook_url = os.environ.get('SLACK_WEBHOOK_URL')
    requests.post(webhook_url, json={'text': message})
```

### Filter Specific Failure Types

Modify Lambda to only alert on OOM kills:

```python
if failure_type == "OOM Kill":
    send_alert(failures)
```

## Comparison: Lambda vs Local Script

| Feature | Lambda Function | Local Script |
|---------|----------------|--------------|
| **Automation** | Fully automated | Manual execution |
| **Alerting** | SNS notifications | Console output |
| **Cost** | ~$0.10/month | Free (local) |
| **Latency** | 5 minute detection | Immediate |
| **Detail** | Summary | Comprehensive |
| **Use Case** | Continuous monitoring | Deep investigation |

**Recommendation**: Use both - Lambda for automated monitoring, local script for detailed analysis.

## Related Documentation

- [Container Failure Detection](./container-failure-detection.md)
- [Diagnostic Script Usage](./container-failure-detection.md#diagnostic-script)
- [Startup Troubleshooting](../startup/troubleshooting.md)
- [Memory Optimization](../startup/model-loading-optimization.md)

## Support

For issues or questions:
1. Check Lambda logs in CloudWatch
2. Review SNS topic subscriptions
3. Verify IAM permissions
4. Run local diagnostic script for comparison
5. Check ECS task exit codes manually
