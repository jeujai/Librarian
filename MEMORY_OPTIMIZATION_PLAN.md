# Memory Optimization Plan - OOM Kill Resolution

**Date:** January 15, 2026  
**Issue:** Containers being OOM killed after ~6 minutes with 4GB memory limit  
**Diagnosis:** All 4 recent tasks killed with Exit 137 (OOM Kill)

## Current Situation

- **Task Memory:** 4096 MB (4 GB)
- **Task CPU:** 2048 (2 vCPU)
- **Uvicorn Workers:** 1 (single worker)
- **Failure Pattern:** OOM kills at 346-370 seconds (~6 minutes)
- **Root Cause:** ML models (PyTorch, Transformers, Sentence Transformers) exceed 4GB during loading

## Memory Breakdown (Estimated)

Based on your application loading multiple ML models:

```
Base Python + Dependencies:     ~500 MB
Sentence Transformer Model:     ~400 MB
SpaCy Model (en_core_web_sm):   ~50 MB
NLTK Data:                      ~100 MB
Application Code:               ~200 MB
Uvicorn + FastAPI:              ~150 MB
PyTorch Runtime:                ~800 MB
Working Memory (buffers):       ~500 MB
Peak Loading Overhead:          ~1500 MB
----------------------------------------
TOTAL ESTIMATED:                ~4200 MB
```

The issue is that during model loading, memory spikes above 4GB, triggering OOM kills.

## Recommended Solutions (In Priority Order)

### Option 1: Increase Memory to 8GB (RECOMMENDED - Quick Fix)

**Pros:**
- Immediate fix
- Simple deployment
- Handles current workload
- Room for growth

**Cons:**
- Increased cost (~$0.04/hour more = ~$30/month)
- Doesn't address underlying efficiency

**Implementation:**
```bash
# Update task definition memory from 4096 to 8192
python scripts/increase-task-memory.py --memory 8192
```

**Cost Impact:**
- Current: 4GB = ~$0.08/hour = ~$60/month
- New: 8GB = ~$0.12/hour = ~$90/month
- Increase: ~$30/month

### Option 2: Optimize Model Loading (BEST LONG-TERM)

Implement lazy loading and model caching to reduce peak memory:

**Changes Needed:**
1. Load models on-demand instead of at startup
2. Use model quantization (reduce precision)
3. Implement model unloading for unused models
4. Use smaller model variants where possible

**Implementation:**
```python
# Instead of loading all models at startup:
# - Load sentence-transformers/all-MiniLM-L6-v2 (90MB) instead of larger models
# - Load models only when endpoints are called
# - Unload models after 5 minutes of inactivity
```

**Pros:**
- Lower memory footprint
- Better resource utilization
- Can stay at 4GB or use 6GB

**Cons:**
- Requires code changes
- First request to each endpoint will be slower
- More complex implementation

### Option 3: Use Smaller Models (COMPROMISE)

Replace large models with smaller, more efficient alternatives:

**Model Replacements:**
```
Current: all-MiniLM-L6-v2 (90MB)
Alternative: paraphrase-MiniLM-L3-v2 (60MB) - 33% smaller

Current: en_core_web_sm (50MB)
Alternative: en_core_web_sm (already smallest)

Consider: Distilled models for specific tasks
```

**Pros:**
- Reduced memory usage
- Faster inference
- Can work with 4-6GB

**Cons:**
- Slightly lower accuracy
- May need to test quality impact

### Option 4: Increase to 6GB (MIDDLE GROUND)

**Pros:**
- More headroom than 4GB
- Lower cost than 8GB
- Should handle current models

**Cons:**
- May still be tight during peak loading
- Less room for growth

**Cost Impact:**
- 6GB = ~$0.10/hour = ~$75/month
- Increase: ~$15/month

## Immediate Recommendation

**Deploy with 8GB memory NOW, then optimize later:**

1. **Immediate (Today):**
   - Increase task memory to 8GB
   - Deploy and verify stability
   - Monitor memory usage with CloudWatch

2. **Short-term (This Week):**
   - Implement progressive model loading
   - Add memory monitoring to startup phases
   - Test with 6GB to see if sufficient

3. **Long-term (Next Sprint):**
   - Implement lazy loading
   - Add model quantization
   - Optimize model selection

## Implementation Steps

### Step 1: Increase Memory to 8GB

```bash
# Create script to update task definition
python scripts/increase-task-memory.py --memory 8192 --cpu 2048

# Or manually update and deploy
python scripts/rebuild-and-redeploy.py
```

### Step 2: Monitor Memory Usage

```bash
# Enable Container Insights if not already enabled
aws ecs update-cluster-settings \
  --cluster multimodal-lib-prod-cluster \
  --settings name=containerInsights,value=enabled

# View memory metrics
aws cloudwatch get-metric-statistics \
  --namespace AWS/ECS \
  --metric-name MemoryUtilization \
  --dimensions Name=ClusterName,Value=multimodal-lib-prod-cluster \
  --start-time $(date -u -d '1 hour ago' +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 300 \
  --statistics Average,Maximum
```

### Step 3: Implement Progressive Loading (Code Changes)

Update `src/multimodal_librarian/startup/progressive_loader.py`:

```python
# Add memory-aware loading
import psutil

def load_models_with_memory_check():
    """Load models progressively with memory monitoring."""
    memory = psutil.virtual_memory()
    
    # Only load if we have >2GB free
    if memory.available < 2 * 1024 * 1024 * 1024:
        logger.warning("Low memory, deferring model loading")
        return False
    
    # Load models one at a time
    load_sentence_transformer()
    load_spacy_model()
    # etc.
```

## Monitoring and Validation

### Key Metrics to Watch

1. **Memory Utilization:**
   - Target: <75% of limit
   - Alert: >85% of limit
   - Critical: >95% of limit

2. **OOM Kill Rate:**
   - Target: 0 kills/day
   - Current: 4 kills/hour

3. **Startup Time:**
   - Current: ~6 minutes before OOM
   - Target: <2 minutes to healthy

### CloudWatch Alarms

```bash
# Create alarm for high memory usage
aws cloudwatch put-metric-alarm \
  --alarm-name multimodal-lib-high-memory \
  --alarm-description "Alert when memory usage exceeds 85%" \
  --metric-name MemoryUtilization \
  --namespace AWS/ECS \
  --statistic Average \
  --period 300 \
  --evaluation-periods 2 \
  --threshold 85 \
  --comparison-operator GreaterThanThreshold \
  --dimensions Name=ClusterName,Value=multimodal-lib-prod-cluster
```

## Alternative: Use EFS for Model Cache

Instead of loading models into memory, mount EFS and load from disk:

**Pros:**
- Models stored on EFS (persistent)
- Faster container startup
- Lower memory usage

**Cons:**
- Slower inference (disk I/O)
- Additional EFS costs (~$10/month)
- More complex setup

## Cost Comparison

| Configuration | Memory | Monthly Cost | Notes |
|--------------|--------|--------------|-------|
| Current (4GB) | 4096 MB | ~$60 | OOM kills |
| Recommended (8GB) | 8192 MB | ~$90 | Stable |
| Middle Ground (6GB) | 6144 MB | ~$75 | May work |
| Optimized (4GB) | 4096 MB | ~$60 | Requires code changes |

## Decision Matrix

| Solution | Time to Implement | Cost Impact | Risk | Recommended |
|----------|------------------|-------------|------|-------------|
| 8GB Memory | 30 minutes | +$30/month | Low | ✅ YES (immediate) |
| 6GB Memory | 30 minutes | +$15/month | Medium | ⚠️ Maybe |
| Lazy Loading | 2-3 days | $0 | Medium | ✅ YES (long-term) |
| Smaller Models | 1-2 days | $0 | Medium | ⚠️ Test first |
| EFS Cache | 1 day | +$10/month | Low | ⚠️ Consider |

## Next Steps

1. **Immediate:** Increase to 8GB and deploy
2. **Monitor:** Watch memory usage for 24 hours
3. **Optimize:** Implement progressive loading
4. **Test:** Try reducing to 6GB after optimization
5. **Document:** Update deployment docs with memory requirements

---

**Recommendation:** Start with 8GB to get stable immediately, then optimize code to potentially reduce back to 6GB or even 4GB with lazy loading.
