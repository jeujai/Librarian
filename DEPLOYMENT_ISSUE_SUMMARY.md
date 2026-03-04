# Deployment Issue Summary

## Problem Statement
Production deployment failing health checks with no visibility into root cause.

## Investigation Timeline

### Initial Hypothesis
Missing startup logging preventing diagnosis of health check failures.

### Investigation Steps
1. Checked deployment status - tasks running but health status UNKNOWN
2. Examined logs - saw model loading but no startup event logs
3. Added comprehensive STEP-by-step logging with timeouts
4. Discovered startup event wasn't being called
5. Identified Uvicorn running with `--workers 4` preventing startup event execution
6. Removed workers to enable single-process mode for debugging
7. Redeployed and monitored

### Root Cause Discovered
**Out of Memory Error (Exit Code 137)**

```
StoppedReason: "Essential container in task exited"
ExitCode: 137
Reason: "OutOfMemoryError: Container killed due to memory usage"
```

## The Real Problem

The application is being killed by the container orchestrator due to excessive memory usage during startup. This explains:

1. **Why health checks fail**: Container is killed before health checks can pass
2. **Why logs stop abruptly**: Process is terminated mid-startup
3. **Why there's no error logging**: OOM kills happen at the kernel level

## Memory Analysis

The startup process loads multiple heavy ML models:
- SentenceTransformer models (all-MiniLM-L6-v2) - multiple instances
- Cross-encoder models
- SpaCy NLP pipelines
- DialoGPT models
- Multiple worker processes (4x) multiplying memory usage

With 4 workers, each loading these models independently, memory consumption exceeds container limits.

## Solution Options

### Option 1: Increase Container Memory (Immediate)
- Current: Likely 2GB or less
- Recommended: 4-8GB for ML workloads
- Trade-off: Higher cost (~$20-40/month additional)

### Option 2: Optimize Model Loading (Better)
- Load models once and share across workers
- Use model caching/warming
- Lazy load non-essential models
- Implement progressive loading properly

### Option 3: Reduce Workers (Quick Fix)
- Use single worker (already done)
- Reduces memory footprint by 4x
- Trade-off: Lower concurrency

### Option 4: Use Lighter Models
- Replace heavy models with lighter alternatives
- Quantize models
- Use distilled versions

## Recommended Action Plan

1. **Immediate**: Keep single worker configuration (already deployed)
2. **Short-term**: Increase container memory to 4GB
3. **Medium-term**: Implement proper model caching and sharing
4. **Long-term**: Optimize model selection and loading strategy

## Task Definition Memory Settings

Check current memory allocation:
```bash
aws ecs describe-task-definition \
  --task-definition multimodal-lib-prod-app:26 \
  --region us-east-1 \
  --query 'taskDefinition.{Memory:memory,ContainerMemory:containerDefinitions[0].memory}'
```

## Next Steps

1. Check current memory allocation
2. Increase to 4096 MB (4GB) if below that
3. Monitor memory usage during startup
4. Implement model caching if memory issues persist
5. Re-enable workers once memory is stable

## Lessons Learned

1. **OOM errors are silent**: No application-level logging can catch them
2. **Health check failures need multiple diagnostic angles**: Not just logging
3. **ML workloads need significant memory**: Plan for 2-4GB per model set
4. **Worker processes multiply resource usage**: Consider carefully for ML apps
5. **Container metrics are essential**: Monitor memory, CPU, not just logs

## Files Modified

- `Dockerfile`: Removed `--workers 4` flag
- `src/multimodal_librarian/main.py`: Added comprehensive startup logging with print statements

## Status

**BLOCKED**: Deployment failing due to OOM, not logging issues.
**ACTION REQUIRED**: Increase container memory allocation.
