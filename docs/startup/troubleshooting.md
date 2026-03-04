# Startup Issues Troubleshooting Guide

## Overview

This guide provides comprehensive troubleshooting procedures for application startup issues in the Multimodal Librarian system. It covers common problems, diagnostic steps, and solutions for each startup phase.

## Quick Diagnostic Checklist

Before diving into specific issues, run through this quick checklist:

- [ ] Check ECS task status in AWS Console
- [ ] Review CloudWatch logs for error messages
- [ ] Verify health endpoint responses (`/health/minimal`, `/health/ready`, `/health/full`)
- [ ] Check container resource utilization (CPU, memory)
- [ ] Verify network connectivity to dependencies (S3, Secrets Manager, databases)
- [ ] Confirm model cache availability and integrity
- [ ] Review recent deployment changes

## Common Startup Issues

### Issue 1: Container Fails to Start (Never Reaches Minimal Phase)

**Symptoms**:
- ECS task status shows "STOPPED" or continuously restarting
- No logs appear in CloudWatch
- Health checks never succeed
- Container exits immediately after starting

**Diagnostic Steps**:

```bash
# Check ECS task status
aws ecs describe-tasks --cluster multimodal-librarian-prod --tasks <task-id>

# Check stopped task reason
aws ecs describe-tasks --cluster multimodal-librarian-prod \
  --tasks <task-id> --query 'tasks[0].stoppedReason'

# View container logs (if any)
aws logs tail /ecs/multimodal-librarian-prod --follow
```

**Common Causes & Solutions**:


**1. Port Binding Failure**
```
Error: Address already in use
```
- **Cause**: Another process is using port 8000
- **Solution**: Check for conflicting services or update port configuration
- **Verification**: `netstat -tulpn | grep 8000`

**2. Missing Environment Variables**
```
Error: Required environment variable not set
```
- **Cause**: Critical environment variables missing from task definition
- **Solution**: Verify all required variables in task definition:
  - `AWS_REGION`
  - `ENVIRONMENT`
  - `MODEL_CACHE_PATH`
  - Database connection strings
- **Verification**: Check task definition JSON

**3. Secrets Manager Access Denied**
```
Error: AccessDeniedException when calling GetSecretValue
```
- **Cause**: Task execution role lacks Secrets Manager permissions
- **Solution**: Add IAM policy to task execution role:
```json
{
  "Effect": "Allow",
  "Action": [
    "secretsmanager:GetSecretValue",
    "secretsmanager:DescribeSecret"
  ],
  "Resource": "arn:aws:secretsmanager:*:*:secret:multimodal-librarian/*"
}
```
- **Verification**: Test with `scripts/test_secrets_access.py`

**4. Out of Memory (OOM) During Initialization**
```
Error: Container killed due to memory exhaustion
```
- **Cause**: Insufficient memory allocation for startup
- **Solution**: 
  - Increase task memory to at least 4GB
  - Enable progressive model loading
  - Optimize model loading order
- **Verification**: Monitor memory metrics in CloudWatch


---

### Issue 2: Stuck in Minimal Phase (>60 seconds)

**Symptoms**:
- Health endpoint returns `"phase": "minimal"` for extended period
- Essential models not loading
- Application responds but with limited functionality
- Logs show model loading attempts but no completion

**Diagnostic Steps**:

```bash
# Check current phase status
curl http://localhost:8000/health/full

# Check model loading progress
curl http://localhost:8000/api/loading/progress

# Review model loading logs
aws logs filter-pattern "model.load" \
  --log-group-name /ecs/multimodal-librarian-prod \
  --start-time $(date -u -d '10 minutes ago' +%s)000

# Check startup metrics
aws cloudwatch get-metric-statistics \
  --namespace MultimodalLibrarian \
  --metric-name startup.phase.essential.duration \
  --start-time $(date -u -d '1 hour ago' --iso-8601) \
  --end-time $(date -u --iso-8601) \
  --period 300 \
  --statistics Average,Maximum
```

**Common Causes & Solutions**:

**1. Model Download Timeout**
```
Error: Timeout downloading model from S3
```
- **Cause**: Slow network connection to S3 or large model files
- **Solution**:
  - Enable model caching on EFS
  - Pre-warm cache during deployment
  - Increase download timeout: `MODEL_DOWNLOAD_TIMEOUT=600`
  - Use VPC endpoints for S3 to improve speed
- **Verification**: Check S3 transfer metrics

**2. Model Cache Corruption**
```
Error: Failed to load model from cache: Invalid format
```
- **Cause**: Corrupted cached model files
- **Solution**:
  - Clear model cache: `rm -rf /efs/model-cache/*`
  - Restart task to re-download models
  - Implement cache validation on startup
- **Verification**: Check cache integrity with `scripts/validate-model-cache.py`


**3. Insufficient Memory for Model Loading**
```
Error: RuntimeError: CUDA out of memory
```
- **Cause**: Not enough memory to load essential models
- **Solution**:
  - Increase container memory allocation
  - Load models sequentially instead of parallel
  - Use smaller model variants for essential phase
  - Enable model quantization: `MODEL_QUANTIZATION=true`
- **Verification**: Monitor memory usage during startup

**4. Database Connection Failures**
```
Error: Could not connect to PostgreSQL
```
- **Cause**: Database not accessible or credentials invalid
- **Solution**:
  - Verify security group allows traffic from ECS tasks
  - Check database endpoint and port configuration
  - Validate credentials in Secrets Manager
  - Implement connection retry with exponential backoff
- **Verification**: Test connection with `psql` from container

**5. Vector Store Initialization Timeout**
```
Error: Timeout initializing Milvus connection
```
- **Cause**: Vector store not ready or network issues
- **Solution**:
  - Increase initialization timeout
  - Verify Milvus/OpenSearch is running and accessible
  - Check VPC endpoint configuration
  - Implement health check for vector store before initialization
- **Verification**: Test vector store connectivity independently

---

### Issue 3: Health Checks Failing (ECS Restarts Container)

**Symptoms**:
- ECS task status shows "UNHEALTHY"
- Container restarts repeatedly
- Logs show health check endpoint being called
- Application appears to be running but marked unhealthy

**Diagnostic Steps**:

```bash
# Check health check configuration
aws ecs describe-task-definition \
  --task-definition multimodal-librarian-prod \
  --query 'taskDefinition.containerDefinitions[0].healthCheck'

# Test health endpoint manually
docker exec <container-id> curl -f http://localhost:8000/health/minimal

# Check health check logs
aws logs filter-pattern "health_check" \
  --log-group-name /ecs/multimodal-librarian-prod
```


**Common Causes & Solutions**:

**1. Start Period Too Short**
```
Health check failing before application ready
```
- **Cause**: `startPeriod` less than actual startup time
- **Solution**: Increase start period in task definition:
```json
{
  "healthCheck": {
    "command": ["CMD-SHELL", "curl -f http://localhost:8000/health/minimal || exit 1"],
    "interval": 30,
    "timeout": 10,
    "retries": 3,
    "startPeriod": 300
  }
}
```
- **Verification**: Monitor startup time metrics

**2. Health Endpoint Timeout**
```
Health check command timed out
```
- **Cause**: Health endpoint takes too long to respond
- **Solution**:
  - Increase timeout to 15 seconds
  - Optimize health endpoint to return quickly
  - Cache health status instead of computing on each request
- **Verification**: Measure health endpoint response time

**3. Wrong Health Check Command**
```
curl: command not found
```
- **Cause**: curl not installed in container
- **Solution**: 
  - Install curl in Dockerfile: `RUN apt-get update && apt-get install -y curl`
  - Or use Python-based health check
- **Verification**: Test command in running container

**4. Application Crashes During Startup**
```
Connection refused on health check
```
- **Cause**: Application exits before health check succeeds
- **Solution**:
  - Review application logs for crash causes
  - Fix startup errors (see Issue 1)
  - Implement proper error handling in startup code
- **Verification**: Check for exit codes in task events

---

### Issue 4: Models Fail to Load

**Symptoms**:
- Model status shows "failed" in health endpoint
- Logs show model loading errors
- Application stuck in minimal or essential phase
- Specific features unavailable


**Diagnostic Steps**:

```bash
# Check model status
curl http://localhost:8000/health/full | jq '.model_details'

# Review model loading logs
aws logs filter-pattern "ERROR.*model" \
  --log-group-name /ecs/multimodal-librarian-prod

# Check model files
ls -lh /efs/model-cache/

# Verify model integrity
python scripts/validate-model-files.py
```

**Common Causes & Solutions**:

**1. Model File Corruption**
```
Error: Unable to load model: Invalid checkpoint format
```
- **Cause**: Corrupted model files in cache
- **Solution**:
  - Delete corrupted model: `rm /efs/model-cache/<model-name>`
  - Re-download model on next startup
  - Implement checksum validation
- **Verification**: Compare checksums with source

**2. Incompatible Model Version**
```
Error: Model version mismatch
```
- **Cause**: Model format incompatible with loading library
- **Solution**:
  - Update model loading libraries
  - Convert model to compatible format
  - Use correct model version for library
- **Verification**: Check library and model versions

**3. Insufficient GPU Memory**
```
Error: CUDA out of memory during model load
```
- **Cause**: GPU memory exhausted
- **Solution**:
  - Use CPU-only mode for some models
  - Load models sequentially
  - Use model quantization
  - Increase GPU memory allocation
- **Verification**: Monitor GPU memory usage

**4. Network Timeout Downloading Model**
```
Error: Connection timeout downloading from S3
```
- **Cause**: Network issues or slow connection
- **Solution**:
  - Increase download timeout
  - Use VPC endpoints for S3
  - Pre-download models to cache
  - Implement retry logic with exponential backoff
- **Verification**: Test S3 connectivity and speed


---

### Issue 5: High User Wait Times / Fallback Response Rate

**Symptoms**:
- Many users receiving fallback responses
- High average wait times (>30 seconds)
- Request queue depth increasing
- User complaints about slow responses

**Diagnostic Steps**:

```bash
# Check fallback response rate
curl http://localhost:8000/api/ux/analytics | jq '.fallback_response_rate'

# Monitor user wait times
aws cloudwatch get-metric-statistics \
  --namespace MultimodalLibrarian \
  --metric-name user.wait_time.average \
  --start-time $(date -u -d '1 hour ago' --iso-8601) \
  --end-time $(date -u --iso-8601) \
  --period 300 \
  --statistics Average,Maximum

# Check request queue depth
curl http://localhost:8000/api/loading/progress | jq '.queue_depth'

# Review UX logs
aws logs filter-pattern "fallback_response" \
  --log-group-name /ecs/multimodal-librarian-prod
```

**Common Causes & Solutions**:

**1. Models Loading Too Slowly**
```
Essential phase taking >3 minutes
```
- **Cause**: Slow model loading process
- **Solution**:
  - Enable parallel model loading
  - Pre-warm model cache
  - Use faster storage (EFS with provisioned throughput)
  - Optimize model loading code
- **Verification**: Monitor model load duration metrics

**2. High Request Volume During Startup**
```
Queue depth >100 requests
```
- **Cause**: Many users hitting system during startup
- **Solution**:
  - Implement request rate limiting during startup
  - Use blue-green deployment to avoid cold starts
  - Keep warm instances running
  - Scale horizontally with more instances
- **Verification**: Monitor request rate and queue depth

**3. Insufficient Model Capacity**
```
Models loaded but responses still slow
```
- **Cause**: Models can't handle request volume
- **Solution**:
  - Scale horizontally with more instances
  - Implement request batching
  - Use model caching for repeated queries
  - Optimize model inference performance
- **Verification**: Monitor model inference latency


---

### Issue 6: Memory Issues During Startup

**Symptoms**:
- Container killed with OOM error
- Memory usage spikes during model loading
- Application becomes unresponsive
- Swap usage increasing

**Diagnostic Steps**:

```bash
# Check container memory usage
aws ecs describe-tasks --cluster multimodal-librarian-prod \
  --tasks <task-id> --query 'tasks[0].containers[0].memory'

# Monitor memory metrics
aws cloudwatch get-metric-statistics \
  --namespace AWS/ECS \
  --metric-name MemoryUtilization \
  --dimensions Name=ServiceName,Value=multimodal-librarian-prod \
  --start-time $(date -u -d '1 hour ago' --iso-8601) \
  --end-time $(date -u --iso-8601) \
  --period 60 \
  --statistics Average,Maximum

# Check memory usage in container
docker stats <container-id>

# Review memory-related logs
aws logs filter-pattern "memory\|OOM" \
  --log-group-name /ecs/multimodal-librarian-prod
```

**Common Causes & Solutions**:

**1. Insufficient Memory Allocation**
```
Container killed: Out of memory
```
- **Cause**: Task memory limit too low for model loading
- **Solution**:
  - Increase task memory to 8GB or more
  - Update task definition memory settings
  - Monitor actual memory usage and adjust
- **Verification**: Check memory usage during startup

**2. Memory Leak During Model Loading**
```
Memory usage continuously increasing
```
- **Cause**: Models not properly released after loading
- **Solution**:
  - Implement proper model cleanup
  - Use context managers for model loading
  - Profile memory usage to find leaks
  - Update model loading libraries
- **Verification**: Monitor memory over time

**3. Too Many Models Loading Simultaneously**
```
Memory spike during parallel loading
```
- **Cause**: Loading too many large models at once
- **Solution**:
  - Load models sequentially
  - Limit parallel loading to 2-3 models
  - Load smaller models first
  - Implement memory-aware loading scheduler
- **Verification**: Monitor memory during each model load


---

### Issue 7: Network Connectivity Problems

**Symptoms**:
- Cannot connect to AWS services
- Timeout errors accessing S3, Secrets Manager, or databases
- VPC endpoint errors
- DNS resolution failures

**Diagnostic Steps**:

```bash
# Test S3 connectivity
aws s3 ls s3://multimodal-librarian-models/ --region us-east-1

# Test Secrets Manager connectivity
aws secretsmanager get-secret-value \
  --secret-id multimodal-librarian/prod/database

# Test database connectivity
psql -h <db-endpoint> -U <username> -d multimodal_librarian

# Check VPC endpoints
aws ec2 describe-vpc-endpoints \
  --filters "Name=vpc-id,Values=<vpc-id>"

# Test DNS resolution
nslookup <service-endpoint>

# Check security groups
aws ec2 describe-security-groups \
  --group-ids <security-group-id>
```

**Common Causes & Solutions**:

**1. Security Group Misconfiguration**
```
Error: Connection timeout to database
```
- **Cause**: Security group doesn't allow traffic from ECS tasks
- **Solution**:
  - Add inbound rule to database security group
  - Allow traffic from ECS task security group
  - Verify port numbers (5432 for PostgreSQL, 9200 for OpenSearch)
- **Verification**: Test connection from ECS task

**2. VPC Endpoint Not Configured**
```
Error: Could not connect to S3
```
- **Cause**: No VPC endpoint for S3, causing internet routing
- **Solution**:
  - Create VPC endpoints for S3, Secrets Manager, ECR
  - Update route tables to use endpoints
  - Verify endpoint policy allows access
- **Verification**: Check VPC endpoint status

**3. Subnet Routing Issues**
```
Error: No route to host
```
- **Cause**: Subnet doesn't have route to required services
- **Solution**:
  - Verify subnet route tables
  - Add NAT Gateway for internet access if needed
  - Use private subnets with VPC endpoints
- **Verification**: Check route table configuration


---

## Advanced Troubleshooting

### Debugging Startup Sequence

**Enable Debug Logging**:

```bash
# Set environment variable in task definition
LOG_LEVEL=DEBUG

# Or temporarily in running container
docker exec <container-id> \
  python -c "import logging; logging.basicConfig(level=logging.DEBUG)"
```

**Trace Startup Phases**:

```python
# Add to startup code
import logging
logger = logging.getLogger(__name__)

logger.info("=== STARTUP PHASE: MINIMAL ===")
# ... minimal startup code ...
logger.info("=== STARTUP PHASE: ESSENTIAL ===")
# ... essential startup code ...
logger.info("=== STARTUP PHASE: FULL ===")
# ... full startup code ...
```

**Monitor Startup Metrics**:

```bash
# Watch startup progress in real-time
watch -n 5 'curl -s http://localhost:8000/health/full | jq'

# Monitor CloudWatch metrics
aws cloudwatch get-metric-statistics \
  --namespace MultimodalLibrarian \
  --metric-name startup.phase.duration \
  --dimensions Name=Phase,Value=essential \
  --start-time $(date -u -d '1 hour ago' --iso-8601) \
  --end-time $(date -u --iso-8601) \
  --period 60 \
  --statistics Average,Maximum,Minimum
```

### Performance Profiling

**Profile Model Loading**:

```python
import time
import cProfile
import pstats

def profile_model_loading():
    profiler = cProfile.Profile()
    profiler.enable()
    
    # Load models
    load_all_models()
    
    profiler.disable()
    stats = pstats.Stats(profiler)
    stats.sort_stats('cumulative')
    stats.print_stats(20)
```

**Memory Profiling**:

```python
from memory_profiler import profile

@profile
def load_model(model_name):
    # Model loading code
    pass
```

**Startup Timeline Analysis**:

```bash
# Extract startup events from logs
aws logs filter-pattern "STARTUP\|phase\|model.load" \
  --log-group-name /ecs/multimodal-librarian-prod \
  --start-time $(date -u -d '1 hour ago' +%s)000 \
  | jq -r '.events[] | [.timestamp, .message] | @tsv' \
  | sort -n > startup_timeline.txt
```


---

## Preventive Measures

### Pre-Deployment Checks

**1. Validate Configuration**:
```bash
# Run validation script
python scripts/validate-deployment-config.py

# Check task definition
aws ecs describe-task-definition \
  --task-definition multimodal-librarian-prod \
  | jq '.taskDefinition | {memory, cpu, healthCheck}'
```

**2. Test Model Cache**:
```bash
# Verify model cache integrity
python scripts/validate-model-cache.py

# Pre-warm cache if needed
python scripts/warm-model-cache.py
```

**3. Verify Resource Limits**:
```bash
# Check current resource usage
aws ecs describe-services \
  --cluster multimodal-librarian-prod \
  --services multimodal-librarian-prod \
  | jq '.services[0].deployments[0].desiredCount'

# Verify memory and CPU limits are sufficient
```

### Monitoring Setup

**1. Configure CloudWatch Alarms**:

```bash
# Alarm for startup phase timeout
aws cloudwatch put-metric-alarm \
  --alarm-name startup-phase-timeout \
  --alarm-description "Alert when startup takes too long" \
  --metric-name startup.phase.essential.duration \
  --namespace MultimodalLibrarian \
  --statistic Average \
  --period 300 \
  --threshold 180 \
  --comparison-operator GreaterThanThreshold \
  --evaluation-periods 1

# Alarm for health check failures
aws cloudwatch put-metric-alarm \
  --alarm-name health-check-failures \
  --alarm-description "Alert on health check failures" \
  --metric-name HealthCheckFailed \
  --namespace AWS/ECS \
  --statistic Sum \
  --period 60 \
  --threshold 3 \
  --comparison-operator GreaterThanThreshold \
  --evaluation-periods 1
```

**2. Set Up Log Insights Queries**:

```sql
-- Startup duration analysis
fields @timestamp, @message
| filter @message like /phase transition/
| stats avg(duration) as avg_duration, max(duration) as max_duration by phase

-- Model loading failures
fields @timestamp, @message
| filter @message like /ERROR.*model/
| stats count() by model_name

-- Health check failures
fields @timestamp, @message
| filter @message like /health_check.*failed/
| stats count() by bin(5m)
```


### Deployment Best Practices

**1. Use Blue-Green Deployments**:
- Keep old version running while new version starts
- Switch traffic only after new version is fully ready
- Allows instant rollback if issues occur

**2. Implement Gradual Rollout**:
- Deploy to single instance first
- Monitor for issues
- Gradually increase deployment percentage
- Full rollout only after validation

**3. Pre-Warm Model Cache**:
```bash
# Before deployment, ensure models are cached
python scripts/warm-model-cache.py --all-models

# Verify cache
ls -lh /efs/model-cache/
```

**4. Keep Warm Instances**:
- Maintain minimum number of running instances
- Reduces cold start frequency
- Improves user experience during scaling

**5. Test Startup in Staging**:
```bash
# Deploy to staging first
./scripts/deploy-to-staging.sh

# Run startup tests
python tests/startup/test_phase_manager.py
python tests/startup/test_health_check_reliability.py

# Monitor startup metrics
python scripts/monitor-startup-performance.py --environment staging
```

---

## Emergency Procedures

### Immediate Rollback

If startup issues are causing production outages:

```bash
# 1. Identify last working task definition
aws ecs list-task-definitions \
  --family-prefix multimodal-librarian-prod \
  --status ACTIVE \
  --sort DESC

# 2. Update service to use previous version
aws ecs update-service \
  --cluster multimodal-librarian-prod \
  --service multimodal-librarian-prod \
  --task-definition multimodal-librarian-prod:<previous-revision>

# 3. Monitor rollback
aws ecs describe-services \
  --cluster multimodal-librarian-prod \
  --services multimodal-librarian-prod \
  | jq '.services[0].deployments'

# 4. Verify health
curl https://api.multimodal-librarian.com/health/ready
```

### Force Container Restart

If container is stuck but not failing health checks:

```bash
# Stop current task (ECS will start new one)
aws ecs stop-task \
  --cluster multimodal-librarian-prod \
  --task <task-id> \
  --reason "Manual restart for troubleshooting"

# Monitor new task startup
aws ecs describe-tasks \
  --cluster multimodal-librarian-prod \
  --tasks <new-task-id>
```


### Clear Model Cache

If model cache is causing issues:

```bash
# 1. Scale service to 0 (stop all tasks)
aws ecs update-service \
  --cluster multimodal-librarian-prod \
  --service multimodal-librarian-prod \
  --desired-count 0

# 2. Clear model cache
aws ecs run-task \
  --cluster multimodal-librarian-prod \
  --task-definition cache-cleanup \
  --overrides '{
    "containerOverrides": [{
      "name": "cleanup",
      "command": ["rm", "-rf", "/efs/model-cache/*"]
    }]
  }'

# 3. Scale service back up
aws ecs update-service \
  --cluster multimodal-librarian-prod \
  --service multimodal-librarian-prod \
  --desired-count 2

# 4. Monitor startup with fresh cache
watch -n 5 'curl -s https://api.multimodal-librarian.com/health/full | jq'
```

---

## Useful Scripts and Tools

### Diagnostic Scripts

**1. Comprehensive Startup Diagnostics**:
```bash
python scripts/diagnose-startup-issues.py \
  --cluster multimodal-librarian-prod \
  --service multimodal-librarian-prod \
  --output startup-diagnostics.json
```

**2. Model Cache Validation**:
```bash
python scripts/validate-model-cache.py \
  --cache-path /efs/model-cache \
  --verify-checksums
```

**3. Health Check Testing**:
```bash
python scripts/test-health-endpoints.py \
  --endpoint http://localhost:8000 \
  --all-phases
```

**4. Startup Performance Analysis**:
```bash
python scripts/analyze-startup-performance.py \
  --log-group /ecs/multimodal-librarian-prod \
  --time-range 1h \
  --output startup-analysis.html
```

### Monitoring Dashboards

**CloudWatch Dashboard**:
- Startup phase durations
- Model loading times
- Health check success rate
- Memory and CPU utilization
- User wait times
- Fallback response rate

**Access**: AWS Console → CloudWatch → Dashboards → multimodal-librarian-startup

### Log Analysis Tools

**1. Startup Timeline Viewer**:
```bash
python scripts/view-startup-timeline.py \
  --task-id <task-id> \
  --output timeline.html
```

**2. Model Loading Analysis**:
```bash
python scripts/analyze-model-loading.py \
  --log-group /ecs/multimodal-librarian-prod \
  --time-range 24h
```


---

## Troubleshooting Decision Tree

```
Container won't start?
├─ Yes → Check Issue 1: Container Fails to Start
│   ├─ Port binding error? → Check for port conflicts
│   ├─ Missing env vars? → Verify task definition
│   ├─ Secrets access denied? → Check IAM permissions
│   └─ OOM during init? → Increase memory allocation
│
└─ No → Container starts but...
    │
    ├─ Stuck in minimal phase?
    │   └─ Yes → Check Issue 2: Stuck in Minimal Phase
    │       ├─ Model download timeout? → Enable caching
    │       ├─ Cache corruption? → Clear and rebuild cache
    │       ├─ Memory issues? → Increase allocation
    │       ├─ Database connection fails? → Check connectivity
    │       └─ Vector store timeout? → Verify service health
    │
    ├─ Health checks failing?
    │   └─ Yes → Check Issue 3: Health Checks Failing
    │       ├─ Start period too short? → Increase to 300s
    │       ├─ Endpoint timeout? → Increase timeout
    │       ├─ curl not found? → Install in container
    │       └─ App crashes? → Review logs for errors
    │
    ├─ Models fail to load?
    │   └─ Yes → Check Issue 4: Models Fail to Load
    │       ├─ File corruption? → Delete and re-download
    │       ├─ Version mismatch? → Update libraries
    │       ├─ GPU OOM? → Use CPU or quantization
    │       └─ Network timeout? → Increase timeout, use VPC endpoints
    │
    ├─ High user wait times?
    │   └─ Yes → Check Issue 5: High User Wait Times
    │       ├─ Slow model loading? → Enable parallel loading
    │       ├─ High request volume? → Scale horizontally
    │       └─ Insufficient capacity? → Add more instances
    │
    ├─ Memory issues?
    │   └─ Yes → Check Issue 6: Memory Issues
    │       ├─ Insufficient allocation? → Increase task memory
    │       ├─ Memory leak? → Profile and fix leaks
    │       └─ Too many parallel loads? → Load sequentially
    │
    └─ Network connectivity problems?
        └─ Yes → Check Issue 7: Network Connectivity
            ├─ Security group issue? → Update rules
            ├─ No VPC endpoint? → Create endpoints
            └─ Routing issue? → Check route tables
```

---

## Getting Help

### Internal Resources

1. **Documentation**:
   - [Phase Management Guide](./phase-management.md)
   - [Health Check Configuration](./health-check-parameter-adjustments.md)
   - [Deployment Guide](../deployment/deployment-procedures.md)

2. **Monitoring**:
   - CloudWatch Dashboard: multimodal-librarian-startup
   - Log Insights: /ecs/multimodal-librarian-prod
   - Metrics: MultimodalLibrarian namespace

3. **Team Contacts**:
   - DevOps Team: #devops-support
   - Platform Team: #platform-engineering
   - On-Call: PagerDuty escalation

### External Resources

1. **AWS Documentation**:
   - [ECS Health Checks](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task_definition_parameters.html#container_definition_healthcheck)
   - [ECS Troubleshooting](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/troubleshooting.html)
   - [CloudWatch Logs Insights](https://docs.aws.amazon.com/AmazonCloudWatch/latest/logs/AnalyzingLogData.html)

2. **Community Resources**:
   - AWS Forums
   - Stack Overflow (tag: amazon-ecs)
   - GitHub Issues

---

## Appendix: Common Error Messages

### Error Message Reference

| Error Message | Likely Cause | Solution Reference |
|--------------|--------------|-------------------|
| `Address already in use` | Port conflict | Issue 1.1 |
| `Required environment variable not set` | Missing config | Issue 1.2 |
| `AccessDeniedException` | IAM permissions | Issue 1.3 |
| `Container killed due to memory` | OOM | Issue 1.4, Issue 6 |
| `Timeout downloading model` | Network/S3 issue | Issue 2.1 |
| `Invalid checkpoint format` | Cache corruption | Issue 2.2 |
| `CUDA out of memory` | GPU memory | Issue 2.3, Issue 4.3 |
| `Could not connect to PostgreSQL` | Database connectivity | Issue 2.4 |
| `Timeout initializing Milvus` | Vector store issue | Issue 2.5 |
| `Health check command timed out` | Slow health endpoint | Issue 3.2 |
| `curl: command not found` | Missing dependency | Issue 3.3 |
| `Connection refused` | App not running | Issue 3.4 |
| `Model version mismatch` | Incompatible version | Issue 4.2 |
| `Connection timeout to S3` | Network issue | Issue 4.4, Issue 7 |
| `No route to host` | Routing issue | Issue 7.3 |

---

## Document History

- **Version 1.0** (2024-01-13): Initial troubleshooting guide
- **Maintainer**: Platform Engineering Team
- **Last Updated**: 2024-01-13
- **Review Schedule**: Monthly

## Related Documentation

- [Phase Management Guide](./phase-management.md)
- [Health Check Parameter Adjustments](./health-check-parameter-adjustments.md)
- [Model Caching Strategy](../operations/model-caching.md)
- [Deployment Procedures](../deployment/deployment-procedures.md)
- [Monitoring Guide](../operations/monitoring-guide.md)
- [System Architecture](../architecture/system-architecture.md)
