# Startup Phase Management

## Overview

The Multimodal Librarian application implements a multi-phase startup system designed to provide immediate user feedback while progressively loading AI models in the background. This approach balances fast startup times with full functionality, ensuring users never experience long wait times for basic operations.

## Core Principle

**Users expecting real-time responses will not wait 5 minutes for models to load.** The system provides immediate functionality and progressively enhances capabilities as models become available.

## Startup Phases

### Phase 1: MINIMAL (0-30 seconds)

**Goal**: Get the application responding to health checks and basic requests as quickly as possible.

**What's Available**:
- ✅ HTTP server is running and accepting connections
- ✅ Health endpoints (`/health/minimal`, `/health/ready`, `/health/full`)
- ✅ Basic API endpoints respond with loading status
- ✅ Request queuing system for advanced operations
- ✅ Model status reporting
- ✅ Simple text-based operations

**What's Loading**:
- 🔄 Essential AI models
- 🔄 Database connections
- 🔄 Vector store initialization

**User Experience**:
- Users receive immediate responses indicating the system is starting up
- Clear messaging about what's available and what's loading
- Estimated time until full functionality is ready

**Technical Details**:
```python
# Phase transition occurs when:
- HTTP server is listening on configured port
- Health endpoints are responding
- Basic middleware is initialized
- Request routing is functional
```

**Health Check Status**: ✅ HEALTHY (passes ECS health checks)

---

### Phase 2: ESSENTIAL (30 seconds - 2 minutes)

**Goal**: Load the most frequently used models to serve 80% of user requests with minimal delay.

**What's Available**:
- ✅ All Phase 1 capabilities
- ✅ Text embedding model (lightweight, ~50MB)
- ✅ Basic chat model (smaller variant, ~200MB)
- ✅ Simple search functionality
- ✅ Document text extraction
- ✅ Basic conversation management

**What's Loading**:
- 🔄 Large language models
- 🔄 Multimodal models
- 🔄 Advanced analysis models
- 🔄 Specialized processors

**User Experience**:
- Most requests can be served with <10 second response times
- Basic AI chat functionality is available
- Simple document search works
- Advanced features show "loading" status with ETAs

**Technical Details**:
```python
# Models loaded in priority order:
1. text-embedding-small (5 seconds)
2. chat-model-base (15 seconds)
3. search-index (10 seconds)

# Phase transition occurs when:
- All essential models are loaded and validated
- Database connections are established
- Vector store is operational
```

**Health Check Status**: ✅ READY (can serve traffic)

---

### Phase 3: FULL (2-5 minutes)

**Goal**: Load all remaining models and enable complete functionality.

**What's Available**:
- ✅ All Phase 2 capabilities
- ✅ Large language models (advanced reasoning)
- ✅ Multimodal models (image/video processing)
- ✅ Complex document analysis
- ✅ Advanced search with semantic understanding
- ✅ Knowledge graph operations
- ✅ Specialized analysis tools

**User Experience**:
- All features are fully operational
- No limitations or degraded functionality
- Maximum response quality and capabilities

**Technical Details**:
```python
# Additional models loaded:
1. chat-model-large (60 seconds)
2. document-processor (30 seconds)
3. multimodal-model (120 seconds)
4. specialized-analyzers (90 seconds)

# Phase transition occurs when:
- All models are loaded and validated
- All services are fully initialized
- System is ready for production load
```

**Health Check Status**: ✅ FULL (all capabilities ready)

## Phase Transitions

### Automatic Transitions

The system automatically transitions between phases based on component readiness:

```python
class StartupPhaseManager:
    def check_phase_transition(self):
        if self.current_phase == StartupPhase.MINIMAL:
            if self.essential_models_loaded():
                self.transition_to(StartupPhase.ESSENTIAL)
        
        elif self.current_phase == StartupPhase.ESSENTIAL:
            if self.all_models_loaded():
                self.transition_to(StartupPhase.FULL)
```

### Transition Events

Each phase transition triggers:
1. **Logging**: Detailed logs of the transition and timing
2. **Metrics**: Performance metrics for monitoring
3. **Notifications**: Internal events for dependent services
4. **Status Updates**: Updated health endpoint responses

## Model Loading Strategy

### Priority Classification

Models are classified by priority to determine loading order:

**Essential Priority** (Load First):
- Small, frequently used models
- Required for basic functionality
- Fast loading times (<30 seconds total)

**Standard Priority** (Load Second):
- Medium-sized models
- Used for common operations
- Moderate loading times (30-120 seconds)

**Advanced Priority** (Load Last):
- Large, specialized models
- Used for advanced features
- Longer loading times (>120 seconds)

### Progressive Loading

Models load in the background without blocking the main application:

```python
async def load_models_progressively():
    # Phase 1: Essential models (parallel loading)
    await asyncio.gather(
        load_model("text-embedding-small"),
        load_model("chat-model-base"),
        load_model("search-index")
    )
    
    # Phase 2: Standard models (parallel loading)
    await asyncio.gather(
        load_model("chat-model-large"),
        load_model("document-processor")
    )
    
    # Phase 3: Advanced models (parallel loading)
    await asyncio.gather(
        load_model("multimodal-model"),
        load_model("specialized-analyzers")
    )
```

## Health Endpoints

### `/health/minimal`

**Purpose**: Basic liveness check for ECS health monitoring

**Returns**:
```json
{
  "status": "healthy",
  "phase": "minimal",
  "timestamp": "2024-01-13T10:30:00Z",
  "uptime_seconds": 25
}
```

**Use Case**: ECS uses this endpoint to determine if the container should be restarted

---

### `/health/ready`

**Purpose**: Readiness check for load balancer traffic routing

**Returns**:
```json
{
  "status": "ready",
  "phase": "essential",
  "capabilities": {
    "chat": true,
    "search": true,
    "document_processing": true,
    "advanced_analysis": false
  },
  "loading_progress": {
    "total_models": 7,
    "loaded_models": 3,
    "percentage": 43
  }
}
```

**Use Case**: ALB uses this to determine if the instance should receive traffic

---

### `/health/full`

**Purpose**: Complete functionality check

**Returns**:
```json
{
  "status": "full",
  "phase": "full",
  "all_models_loaded": true,
  "capabilities": {
    "chat": true,
    "search": true,
    "document_processing": true,
    "advanced_analysis": true,
    "multimodal": true
  },
  "model_details": {
    "text-embedding-small": "loaded",
    "chat-model-base": "loaded",
    "chat-model-large": "loaded",
    "multimodal-model": "loaded"
  }
}
```

**Use Case**: Monitoring and debugging to verify full system readiness

## User Experience During Startup

### Immediate Response Pattern

All API endpoints respond immediately, even during startup:

```python
@app.post("/chat")
async def chat_endpoint(request: ChatRequest):
    if not chat_model.is_loaded():
        return {
            "status": "loading",
            "message": "AI model is starting up. Please wait 30-60 seconds.",
            "estimated_ready_time": chat_model.estimated_load_time(),
            "fallback_response": generate_contextual_fallback(request.message),
            "response_quality": "basic"
        }
    
    return await chat_model.process(request)
```

### Response Quality Indicators

The system uses clear indicators to communicate response quality:

- **⚡ Basic**: Quick response mode - Simple text processing only
- **🔄 Enhanced**: Partial AI mode - Some advanced features available
- **🧠 Full**: Full AI mode - All capabilities ready

### Loading Progress

Users see real-time progress updates:

```json
{
  "loading_status": {
    "phase": "essential",
    "progress_percentage": 65,
    "estimated_completion_seconds": 45,
    "currently_loading": "chat-model-large",
    "available_features": ["basic_chat", "simple_search"],
    "loading_features": ["advanced_chat", "document_analysis"]
  }
}
```

## Monitoring and Metrics

### Key Metrics

**Phase Completion Times**:
- `startup.phase.minimal.duration` - Time to reach minimal phase
- `startup.phase.essential.duration` - Time to reach essential phase
- `startup.phase.full.duration` - Time to reach full phase

**Model Loading Performance**:
- `model.load.duration` - Time to load each model
- `model.load.success_rate` - Percentage of successful loads
- `model.load.failures` - Count of failed model loads

**User Experience**:
- `user.wait_time.average` - Average wait time for requests
- `user.fallback_response.rate` - Percentage of fallback responses
- `user.request.queue_depth` - Number of queued requests

### Alerting Thresholds

**Critical Alerts**:
- Minimal phase takes >60 seconds
- Essential phase takes >3 minutes
- Model loading failures
- Health check failures

**Warning Alerts**:
- Full phase takes >6 minutes
- High fallback response rate (>20%)
- Elevated user wait times (>30 seconds average)

## Troubleshooting

### Startup Takes Too Long

**Symptoms**: Application doesn't reach essential phase within 2 minutes

**Possible Causes**:
1. Model download from remote storage is slow
2. Insufficient memory for model loading
3. CPU constraints limiting parallel loading
4. Network issues accessing model storage

**Solutions**:
1. Enable model caching on EFS/S3
2. Increase container memory allocation
3. Optimize model loading parallelization
4. Pre-warm model cache during deployment

---

### Health Checks Failing

**Symptoms**: ECS marks tasks as unhealthy and restarts them

**Possible Causes**:
1. Start period too short for model loading
2. Health endpoint timeout too aggressive
3. Application crashes during startup
4. Resource exhaustion (OOM)

**Solutions**:
1. Increase `startPeriod` to 300 seconds (already configured)
2. Increase health check timeout to 15 seconds (already configured)
3. Review application logs for crash causes
4. Increase memory limits or optimize model loading

---

### Models Fail to Load

**Symptoms**: Application stuck in minimal phase, models show "failed" status

**Possible Causes**:
1. Model files corrupted or missing
2. Insufficient memory for model
3. Model format incompatibility
4. Network issues downloading models

**Solutions**:
1. Validate model cache integrity
2. Increase memory allocation
3. Update model loading libraries
4. Check network connectivity to model storage

---

### High Fallback Response Rate

**Symptoms**: Many users receiving fallback responses instead of AI responses

**Possible Causes**:
1. Models loading too slowly
2. High request volume during startup
3. Model loading failures
4. Insufficient model capacity

**Solutions**:
1. Optimize model loading performance
2. Implement request queuing with better prioritization
3. Investigate and fix model loading failures
4. Scale horizontally with more instances

## Best Practices

### For Developers

1. **Always check model availability** before processing requests
2. **Provide fallback responses** for unavailable features
3. **Log phase transitions** for debugging
4. **Monitor loading metrics** to identify bottlenecks
5. **Test startup under load** to ensure reliability

### For Operations

1. **Monitor phase completion times** to detect degradation
2. **Set up alerts** for startup failures
3. **Pre-warm model cache** before deployments
4. **Use blue-green deployments** to avoid user impact
5. **Keep warm instances** to reduce cold start frequency

### For Users

1. **Expect immediate responses** even during startup
2. **Check quality indicators** to understand current capabilities
3. **Wait for full mode** for best results on complex tasks
4. **Use simple features first** while advanced features load

## Configuration

### Environment Variables

```bash
# Startup configuration
STARTUP_MINIMAL_TIMEOUT=30
STARTUP_ESSENTIAL_TIMEOUT=120
STARTUP_FULL_TIMEOUT=300

# Model loading
MODEL_CACHE_ENABLED=true
MODEL_CACHE_PATH=/efs/model-cache
MODEL_PARALLEL_LOADING=true
MODEL_LOAD_TIMEOUT=180

# Health checks
HEALTH_CHECK_ENABLED=true
HEALTH_CHECK_INTERVAL=30
HEALTH_CHECK_TIMEOUT=15
```

### Terraform Configuration

See `infrastructure/aws-native/modules/application/main.tf` for ECS task definition and health check configuration.

## Related Documentation

- [Health Check Parameter Adjustments](./health-check-parameter-adjustments.md)
- [Model Caching Strategy](../operations/model-caching.md)
- [Monitoring Guide](../operations/monitoring-guide.md)
- [Troubleshooting Guide](../troubleshooting/startup-issues.md)

## Requirements Validation

This implementation satisfies the following requirements:

- **REQ-1**: Health Check Optimization - Multi-phase approach allows proper health signaling
- **REQ-2**: Application Startup Optimization - Progressive loading optimizes startup
- **REQ-3**: Startup Logging Enhancement - Comprehensive logging at each phase
- **REQ-4**: Resource Initialization Optimization - Graceful handling of resource loading
- **REQ-5**: Health Endpoint Implementation - Multiple health endpoints for different purposes
- **REQ-6**: Configuration Management - Proper ECS configuration for AI applications
