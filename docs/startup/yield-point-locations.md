# Yield Point Locations for Event Loop Protection

This document describes the locations of `await asyncio.sleep(0)` yield points inserted into the codebase to ensure health checks can respond during long-running async operations.

## Overview

Python's Global Interpreter Lock (GIL) can cause CPU-bound operations to block the event loop, preventing health check endpoints from responding. While ProcessPoolExecutor is used for the most CPU-intensive model loading operations, yield points are still needed in async code to ensure the event loop can process health check requests between operations.

## Yield Point Strategy

Yield points are inserted:
1. **Before acquiring locks** - Allow health checks before potentially blocking operations
2. **After completing executor operations** - Allow health checks after CPU-intensive work
3. **In loops processing multiple items** - Periodic yields (every 2-3 items) to prevent starvation
4. **Before and after heavy operations** - Even when using executors, yield around the call

## File: `src/multimodal_librarian/models/model_manager.py`

### `_queue_models_by_priority()`
- **Before queuing loop**: Yield after sorting models, before starting to queue
- **During queuing loop**: Yield every 3 models to allow health checks

### `_background_loader()`
- **Before processing delay**: Yield after getting model from queue
- **After delay completes**: Yield before checking capacity
- **Before starting model load**: Yield before creating the loading task

### `_load_model_async()`
- **Before dependency check**: Yield before checking model dependencies
- **Before acquiring lock**: Yield before `async with self._loading_lock`
- **Before executor operation**: Yield before calling `run_in_executor`
- **After config extraction**: Yield after extracting picklable config
- **After executor completes**: Yield after process pool or thread pool returns
- **Before updating model instance**: Yield before final status update

## File: `src/multimodal_librarian/startup/progressive_loader.py`

### `_load_phase_models()`
- **Before creating semaphore**: Yield before setting up concurrency control
- **During task creation loop**: Yield every 2 tasks created
- **Before waiting for tasks**: Yield before `asyncio.gather()`
- **After tasks complete**: Yield after all loading tasks finish

### `_load_model_with_delay()`
- **Before acquiring semaphore**: Yield before `async with semaphore`
- **After acquiring semaphore**: Yield after semaphore is acquired, before loading

### `_monitor_user_requests()`
- **Before processing requests**: Yield before processing the request queue
- **After processing requests**: Yield after processing, before strategy update

### `_process_user_requests()`
- **During capability loop**: Yield every 3 capabilities processed
- **Before removing requests**: Yield before modifying the request queue

## Best Practices for Future Maintenance

When adding new async methods that involve:
1. **Loops over collections**: Add `await asyncio.sleep(0)` every 2-5 iterations
2. **Lock acquisition**: Add yield point before `async with lock:`
3. **Executor calls**: Add yield points before and after `run_in_executor()`
4. **Long-running operations**: Add yield points at logical breakpoints

### Example Pattern

```python
async def process_items(self, items: List[Item]) -> None:
    """Process items with yield points for health check responsiveness.
    
    YIELD POINTS: This method contains yield points to ensure health checks
    can respond during item processing.
    """
    # YIELD POINT: Allow health checks before starting
    await asyncio.sleep(0)
    
    for i, item in enumerate(items):
        await self._process_single_item(item)
        
        # YIELD POINT: Every 3 items, yield to allow health checks
        if (i + 1) % 3 == 0:
            await asyncio.sleep(0)
    
    # YIELD POINT: Allow health checks after completion
    await asyncio.sleep(0)
```

## Testing Yield Points

To verify yield points are effective:
1. Run health check responsiveness tests during model loading
2. Monitor health check latency metrics
3. Check for GIL contention warnings in logs

See `tests/startup/test_event_loop_protection.py` and `tests/startup/test_health_check_responsiveness.py` for test implementations.

## Related Documentation

- Design Document: `.kiro/specs/application-health-startup-optimization/design.md`
- Event Loop Protection section in design document
- Health Check Response Time Monitoring in `startup_metrics.py`
