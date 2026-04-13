# Design Document: Shared Ollama Thread Pool

## Overview

This design consolidates two separate concurrency mechanisms for Ollama-based processing into a single shared 20-thread pool with weighted fair share scheduling and dynamic concurrency scaling. Currently:

- **Bridge Generation** (`SmartBridgeGenerator`): Uses a private `ThreadPoolExecutor` with 15 workers (`_ollama_pool`)
- **KG Processing** (`celery_service.py`): Uses `asyncio.Semaphore(15)` to limit concurrent Ollama calls

Since Ollama is configured with `OLLAMA_NUM_PARALLEL=20`, the current architecture leaves capacity unused when one task finishes faster than the other. A shared pool with fair share scheduling enables natural load balancing while preventing starvation. Dynamic concurrency scaling automatically halves active concurrency when Ollama is overwhelmed (high timeout rate) and ramps back up when it recovers.

### Key Design Decisions

1. **Singleton ThreadPoolExecutor**: A single process-level pool managed by a new `Pool_Manager` module
2. **Weighted Fair Share Scheduling**: Prioritizes the task type that is behind its target share to prevent starvation
3. **Dynamic Concurrency Scaling**: Halves active concurrency on high timeout rate (20 → 10 → 5 → 3 → 2 → 1), doubles back on recovery
4. **Lazy Initialization**: Pool created on first use, not at import time (Celery-compatible)
5. **Thread-Local Event Loops**: Each worker thread maintains its own event loop for async Ollama calls
6. **Graceful Degradation**: Fallback to synchronous execution when pool is unavailable or exhausted
7. **Observability**: Pool statistics, fair share metrics, and concurrency scaling state exposed via health endpoint

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           Celery Worker Process                              │
│                                                                              │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │                        OllamaPoolManager                                │ │
│  │                                                                         │ │
│  │   ┌─────────────────┐    ┌─────────────────┐                           │ │
│  │   │  Bridge Queue   │    │    KG Queue     │                           │ │
│  │   │   (pending)     │    │   (pending)     │                           │ │
│  │   └────────┬────────┘    └────────┬────────┘                           │ │
│  │            │                      │                                     │ │
│  │            └──────────┬───────────┘                                     │ │
│  │                       ▼                                                 │ │
│  │            ┌─────────────────────┐                                      │ │
│  │            │  Fair Share Picker  │                                      │ │
│  │            │  (picks from queue  │                                      │ │
│  │            │   that's behind)    │                                      │ │
│  │            └──────────┬──────────┘                                      │ │
│  │                       ▼                                                 │ │
│  │   ┌─────────────────────────────────────────────────────────────────┐  │ │
│  │   │              ThreadPoolExecutor (20 workers)                     │  │ │
│  │   │  ┌─────────┐ ┌─────────┐ ┌─────────┐       ┌─────────┐         │  │ │
│  │   │  │Worker 1 │ │Worker 2 │ │Worker 3 │  ...  │Worker 20│         │  │ │
│  │   │  │EventLoop│ │EventLoop│ │EventLoop│       │EventLoop│         │  │ │
│  │   │  └────┬────┘ └────┬────┘ └────┬────┘       └────┬────┘         │  │ │
│  │   └───────┼──────────┼──────────┼────────────────┼─────────────────┘  │ │
│  └───────────┼──────────┼──────────┼────────────────┼─────────────────────┘ │
│              └──────────┴──────────┴────────────────┘                       │
│                                    │                                         │
└────────────────────────────────────┼─────────────────────────────────────────┘
                                     ▼
                        ┌─────────────────────────┐
                        │     Ollama Server       │
                        │  OLLAMA_NUM_PARALLEL=20 │
                        └─────────────────────────┘
```

## Components and Interfaces

### Pool_Manager Module

**Location**: `src/multimodal_librarian/services/ollama_pool_manager.py`


```python
"""
Shared Ollama Thread Pool Manager with Weighted Fair Share Scheduling.

Provides a singleton ThreadPoolExecutor for all Ollama-based processing
(bridge generation and KG concept extraction) to share, with fair share
scheduling to prevent starvation.
"""

import asyncio
import logging
import os
import queue
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Coroutine, Dict, Optional, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar('T')


class TaskType(Enum):
    BRIDGE = "bridge"
    KG = "kg"
    UNKNOWN = "unknown"


class PoolExhaustedError(Exception):
    """Raised when the shared pool cannot accept new work."""
    pass


@dataclass
class FairShareState:
    """Tracks fair share statistics for scheduling."""
    bridge_completed: int = 0
    kg_completed: int = 0
    bridge_target_ratio: float = 0.5  # Default 1:1 means 50% each
    kg_target_ratio: float = 0.5
    
    @property
    def total_completed(self) -> int:
        return self.bridge_completed + self.kg_completed
    
    @property
    def bridge_actual_ratio(self) -> float:
        if self.total_completed == 0:
            return 0.5
        return self.bridge_completed / self.total_completed
    
    @property
    def kg_actual_ratio(self) -> float:
        if self.total_completed == 0:
            return 0.5
        return self.kg_completed / self.total_completed
    
    @property
    def bridge_deficit(self) -> float:
        """Positive means bridge is behind its target."""
        return self.bridge_target_ratio - self.bridge_actual_ratio
    
    @property
    def kg_deficit(self) -> float:
        """Positive means KG is behind its target."""
        return self.kg_target_ratio - self.kg_actual_ratio


@dataclass
class PoolStats:
    """Statistics for the shared Ollama pool."""
    pool_size: int = 0
    queue_capacity: int = 0
    bridge_pending: int = 0
    kg_pending: int = 0
    bridge_completed: int = 0
    kg_completed: int = 0
    failed_tasks: int = 0
    # Fair share metrics
    bridge_target_ratio: float = 0.5
    kg_target_ratio: float = 0.5
    bridge_actual_ratio: float = 0.5
    kg_actual_ratio: float = 0.5
    bridge_deficit: float = 0.0
    kg_deficit: float = 0.0
    high_utilization_since: Optional[float] = None


@dataclass
class ConcurrencyScalingState:
    """Tracks dynamic concurrency scaling state."""
    max_capacity: int = 20              # Configured OLLAMA_NUM_PARALLEL
    active_limit: int = 20              # Current active concurrency limit
    active_count: int = 0               # Currently executing tasks
    timeout_window: int = 20            # Sliding window size
    timeout_threshold: float = 0.5      # 50% timeout rate triggers scale-down
    recovery_period: float = 30.0       # Seconds below threshold before scale-up
    recent_results: list = field(default_factory=list)  # Sliding window: True=timeout, False=success
    last_scale_down: Optional[float] = None
    below_threshold_since: Optional[float] = None
    
    @property
    def timeout_rate(self) -> float:
        if not self.recent_results:
            return 0.0
        return sum(1 for r in self.recent_results if r) / len(self.recent_results)
    
    def record_result(self, timed_out: bool):
        """Record a task result in the sliding window."""
        self.recent_results.append(timed_out)
        if len(self.recent_results) > self.timeout_window:
            self.recent_results.pop(0)
    
    def should_scale_down(self) -> bool:
        """Check if we should halve concurrency."""
        if len(self.recent_results) < self.timeout_window // 2:
            return False  # Not enough data yet
        return self.timeout_rate >= self.timeout_threshold and self.active_limit > 1
    
    def should_scale_up(self) -> bool:
        """Check if we should double concurrency."""
        if self.active_limit >= self.max_capacity:
            return False
        if self.timeout_rate >= self.timeout_threshold:
            self.below_threshold_since = None
            return False
        now = time.time()
        if self.below_threshold_since is None:
            self.below_threshold_since = now
            return False
        return (now - self.below_threshold_since) >= self.recovery_period
    
    def scale_down(self):
        """Halve the active concurrency limit."""
        self.active_limit = max(1, self.active_limit // 2)
        self.last_scale_down = time.time()
        self.below_threshold_since = None
    
    def scale_up(self):
        """Double the active concurrency limit (up to max)."""
        self.active_limit = min(self.max_capacity, self.active_limit * 2)
        self.below_threshold_since = None


class OllamaPoolManager:
    """
    Singleton manager for the shared Ollama thread pool with fair share scheduling.
    
    Uses separate queues per task type and picks from the queue whose task type
    is furthest behind its fair share target.
    """
    
    _instance: Optional['OllamaPoolManager'] = None
    _lock = threading.Lock()
    
    def __new__(cls) -> 'OllamaPoolManager':
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._pool: Optional[ThreadPoolExecutor] = None
        self._pool_lock = threading.Lock()
        self._thread_local = threading.local()
        
        # Separate queues per task type for fair share scheduling
        self._bridge_queue: queue.Queue = queue.Queue()
        self._kg_queue: queue.Queue = queue.Queue()
        
        # Fair share state
        self._fair_share = FairShareState()
        self._parse_fair_share_ratio()
        
        # Statistics
        self._stats_lock = threading.Lock()
        self._shutdown_event = threading.Event()
        self._queue_capacity = int(os.environ.get('OLLAMA_POOL_QUEUE_SIZE', '1000'))
        
        # Worker dispatch thread
        self._dispatcher_thread: Optional[threading.Thread] = None
        self._dispatcher_running = False
        
        # Dynamic concurrency scaling
        self._scaling = ConcurrencyScalingState(
            max_capacity=self.pool_size,
            active_limit=self.pool_size,
            timeout_window=int(os.environ.get('OLLAMA_TIMEOUT_WINDOW', '20')),
            timeout_threshold=float(os.environ.get('OLLAMA_TIMEOUT_THRESHOLD', '0.5')),
            recovery_period=float(os.environ.get('OLLAMA_RECOVERY_PERIOD', '30')),
        )
        
        self._initialized = True
        logger.info("OllamaPoolManager singleton created (pool not yet initialized)")
    
    def _parse_fair_share_ratio(self):
        """Parse OLLAMA_FAIR_SHARE_RATIO env var (format: 'bridge:kg', e.g., '1:1' or '2:1')."""
        ratio_str = os.environ.get('OLLAMA_FAIR_SHARE_RATIO', '1:1')
        try:
            parts = ratio_str.split(':')
            bridge_weight = float(parts[0])
            kg_weight = float(parts[1])
            total = bridge_weight + kg_weight
            self._fair_share.bridge_target_ratio = bridge_weight / total
            self._fair_share.kg_target_ratio = kg_weight / total
            logger.info(f"Fair share ratio: bridge={self._fair_share.bridge_target_ratio:.2f}, "
                       f"kg={self._fair_share.kg_target_ratio:.2f}")
        except (ValueError, IndexError):
            logger.warning(f"Invalid OLLAMA_FAIR_SHARE_RATIO '{ratio_str}', using 1:1")
            self._fair_share.bridge_target_ratio = 0.5
            self._fair_share.kg_target_ratio = 0.5
    
    @property
    def pool_size(self) -> int:
        """Get configured pool size from environment."""
        return int(os.environ.get('OLLAMA_NUM_PARALLEL', '20'))
    
    def _ensure_pool(self) -> ThreadPoolExecutor:
        """Lazily initialize the thread pool and dispatcher on first use."""
        if self._pool is None:
            with self._pool_lock:
                if self._pool is None:
                    size = self.pool_size
                    self._pool = ThreadPoolExecutor(
                        max_workers=size,
                        thread_name_prefix="ollama_shared"
                    )
                    
                    # Start dispatcher thread
                    self._dispatcher_running = True
                    self._dispatcher_thread = threading.Thread(
                        target=self._dispatch_loop,
                        name="ollama_dispatcher",
                        daemon=True
                    )
                    self._dispatcher_thread.start()
                    
                    logger.info(
                        f"Shared Ollama pool initialized: "
                        f"{size} workers, queue capacity {self._queue_capacity}"
                    )
        return self._pool
    
    def _get_thread_event_loop(self) -> asyncio.AbstractEventLoop:
        """Get or create an event loop for the current worker thread."""
        loop = getattr(self._thread_local, 'event_loop', None)
        if loop is None or loop.is_closed():
            loop = asyncio.new_event_loop()
            self._thread_local.event_loop = loop
            logger.debug(f"Created event loop for thread {threading.current_thread().name}")
        return loop
    
    def _pick_next_task_type(self) -> Optional[TaskType]:
        """
        Pick which queue to pull from based on fair share deficit.
        
        Returns the task type that is furthest behind its target ratio,
        or None if both queues are empty.
        """
        bridge_has_work = not self._bridge_queue.empty()
        kg_has_work = not self._kg_queue.empty()
        
        if not bridge_has_work and not kg_has_work:
            return None
        if bridge_has_work and not kg_has_work:
            return TaskType.BRIDGE
        if kg_has_work and not bridge_has_work:
            return TaskType.KG
        
        # Both have work - pick the one with larger deficit
        if self._fair_share.bridge_deficit >= self._fair_share.kg_deficit:
            return TaskType.BRIDGE
        else:
            return TaskType.KG
    
    def _dispatch_loop(self):
        """Background thread that dispatches tasks to the pool with fair share scheduling
        and dynamic concurrency scaling."""
        while self._dispatcher_running and not self._shutdown_event.is_set():
            try:
                # Check concurrency scaling
                with self._stats_lock:
                    if self._scaling.should_scale_down():
                        old_limit = self._scaling.active_limit
                        self._scaling.scale_down()
                        logger.warning(
                            f"Scaling down concurrency: {old_limit} → {self._scaling.active_limit} "
                            f"(timeout_rate={self._scaling.timeout_rate:.1%})"
                        )
                    elif self._scaling.should_scale_up():
                        old_limit = self._scaling.active_limit
                        self._scaling.scale_up()
                        logger.info(
                            f"Scaling up concurrency: {old_limit} → {self._scaling.active_limit}"
                        )
                
                # Respect active concurrency limit
                if self._scaling.active_count >= self._scaling.active_limit:
                    time.sleep(0.01)
                    continue
                
                task_type = self._pick_next_task_type()
                
                if task_type is None:
                    time.sleep(0.01)
                    continue
                
                # Get task from appropriate queue
                try:
                    if task_type == TaskType.BRIDGE:
                        work_item = self._bridge_queue.get_nowait()
                    else:
                        work_item = self._kg_queue.get_nowait()
                except queue.Empty:
                    continue
                
                fn, args, kwargs, future, actual_task_type = work_item
                
                with self._stats_lock:
                    self._scaling.active_count += 1
                
                # Submit to thread pool
                def execute_and_complete():
                    timed_out = False
                    try:
                        result = fn(*args, **kwargs)
                        future.set_result(result)
                        
                        # Update fair share stats
                        with self._stats_lock:
                            if actual_task_type == TaskType.BRIDGE:
                                self._fair_share.bridge_completed += 1
                            elif actual_task_type == TaskType.KG:
                                self._fair_share.kg_completed += 1
                    except Exception as e:
                        future.set_exception(e)
                        # Detect timeouts for concurrency scaling
                        if "timed out" in str(e).lower() or "timeout" in str(e).lower():
                            timed_out = True
                    finally:
                        with self._stats_lock:
                            self._scaling.active_count -= 1
                            self._scaling.record_result(timed_out)
                
                self._pool.submit(execute_and_complete)
                
            except Exception as e:
                logger.error(f"Dispatcher error: {e}")
                time.sleep(0.1)
    
    def _total_pending(self) -> int:
        """Get total pending tasks across both queues."""
        return self._bridge_queue.qsize() + self._kg_queue.qsize()
    
    def submit_ollama_work(
        self,
        fn: Callable[..., T],
        *args,
        task_type: str = "unknown",
        **kwargs
    ) -> Future[T]:
        """
        Submit synchronous work to the shared pool.
        
        Args:
            fn: Callable to execute
            *args: Positional arguments for fn
            task_type: "bridge" or "kg" for fair share scheduling
            **kwargs: Keyword arguments for fn
            
        Returns:
            Future for the result
            
        Raises:
            PoolExhaustedError: If queue is full
        """
        if self._total_pending() >= self._queue_capacity:
            raise PoolExhaustedError(
                f"Pool queue full ({self._total_pending()}/{self._queue_capacity})"
            )
        
        self._ensure_pool()
        
        # Create future for result
        future: Future[T] = Future()
        
        # Determine task type enum
        if task_type == "bridge":
            tt = TaskType.BRIDGE
            self._bridge_queue.put((fn, args, kwargs, future, tt))
        elif task_type == "kg":
            tt = TaskType.KG
            self._kg_queue.put((fn, args, kwargs, future, tt))
        else:
            # Unknown tasks go to whichever queue is shorter
            tt = TaskType.UNKNOWN
            if self._bridge_queue.qsize() <= self._kg_queue.qsize():
                self._bridge_queue.put((fn, args, kwargs, future, tt))
            else:
                self._kg_queue.put((fn, args, kwargs, future, tt))
        
        logger.debug(
            f"Submitted {task_type} task (bridge_pending={self._bridge_queue.qsize()}, "
            f"kg_pending={self._kg_queue.qsize()})"
        )
        
        return future
    
    async def submit_ollama_work_async(
        self,
        coro_fn: Callable[..., Coroutine[Any, Any, T]],
        *args,
        task_type: str = "unknown",
        **kwargs
    ) -> T:
        """
        Submit async work to the shared pool.
        
        Wraps the coroutine to run in a worker thread's event loop.
        """
        def run_in_thread():
            loop = self._get_thread_event_loop()
            return loop.run_until_complete(coro_fn(*args, **kwargs))
        
        future = self.submit_ollama_work(
            run_in_thread,
            task_type=task_type
        )
        
        # Await the future from the calling async context
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, future.result)
    
    def get_pool_stats(self) -> Dict[str, Any]:
        """Get current pool statistics including fair share metrics."""
        with self._stats_lock:
            utilization = self._total_pending() / self._queue_capacity if self._queue_capacity > 0 else 0
            
            # Check for high utilization warning
            if utilization > 0.9:
                if not hasattr(self, '_high_util_since') or self._high_util_since is None:
                    self._high_util_since = time.time()
                elif time.time() - self._high_util_since > 10:
                    logger.warning(
                        f"Pool utilization >90% for >10s: "
                        f"{self._total_pending()}/{self._queue_capacity} pending"
                    )
            else:
                self._high_util_since = None
            
            return {
                "pool_size": self.pool_size,
                "queue_capacity": self._queue_capacity,
                "bridge_pending": self._bridge_queue.qsize(),
                "kg_pending": self._kg_queue.qsize(),
                "total_pending": self._total_pending(),
                "bridge_completed": self._fair_share.bridge_completed,
                "kg_completed": self._fair_share.kg_completed,
                "total_completed": self._fair_share.total_completed,
                "utilization_pct": round(utilization * 100, 1),
                "initialized": self._pool is not None,
                # Fair share metrics
                "fair_share": {
                    "bridge_target_ratio": round(self._fair_share.bridge_target_ratio, 3),
                    "kg_target_ratio": round(self._fair_share.kg_target_ratio, 3),
                    "bridge_actual_ratio": round(self._fair_share.bridge_actual_ratio, 3),
                    "kg_actual_ratio": round(self._fair_share.kg_actual_ratio, 3),
                    "bridge_deficit": round(self._fair_share.bridge_deficit, 3),
                    "kg_deficit": round(self._fair_share.kg_deficit, 3),
                },
                # Dynamic concurrency scaling metrics
                "concurrency": {
                    "max_capacity": self._scaling.max_capacity,
                    "active_limit": self._scaling.active_limit,
                    "active_count": self._scaling.active_count,
                    "timeout_rate": round(self._scaling.timeout_rate, 3),
                    "timeout_window": self._scaling.timeout_window,
                    "timeout_threshold": self._scaling.timeout_threshold,
                    "recovery_period": self._scaling.recovery_period,
                    "scaled_down": self._scaling.active_limit < self._scaling.max_capacity,
                }
            }
    
    def shutdown(self, wait: bool = True) -> None:
        """Gracefully shutdown the pool."""
        self._shutdown_event.set()
        self._dispatcher_running = False
        
        if self._dispatcher_thread is not None:
            self._dispatcher_thread.join(timeout=5.0)
        
        if self._pool is not None:
            with self._pool_lock:
                if self._pool is not None:
                    logger.info("Shutting down shared Ollama pool...")
                    self._pool.shutdown(wait=wait)
                    self._pool = None
                    logger.info("Shared Ollama pool shutdown complete")


# Module-level singleton accessor
_pool_manager: Optional[OllamaPoolManager] = None


def get_pool_manager() -> OllamaPoolManager:
    """Get the singleton pool manager instance."""
    global _pool_manager
    if _pool_manager is None:
        _pool_manager = OllamaPoolManager()
    return _pool_manager


def submit_ollama_work(
    fn: Callable[..., T],
    *args,
    task_type: str = "unknown",
    **kwargs
) -> Future[T]:
    """Convenience function to submit work to the shared pool."""
    return get_pool_manager().submit_ollama_work(fn, *args, task_type=task_type, **kwargs)


async def submit_ollama_work_async(
    coro_fn: Callable[..., Coroutine[Any, Any, T]],
    *args,
    task_type: str = "unknown",
    **kwargs
) -> T:
    """Convenience function to submit async work to the shared pool."""
    return await get_pool_manager().submit_ollama_work_async(
        coro_fn, *args, task_type=task_type, **kwargs
    )


def get_pool_stats() -> Dict[str, Any]:
    """Get pool statistics."""
    return get_pool_manager().get_pool_stats()


def shutdown_pool(wait: bool = True) -> None:
    """Shutdown the shared pool."""
    global _pool_manager
    if _pool_manager is not None:
        _pool_manager.shutdown(wait=wait)
        _pool_manager = None
```


### Bridge Generator Integration

**Changes to**: `src/multimodal_librarian/components/chunking_framework/bridge_generator.py`

```python
# Remove private pool
# OLD:
# self._ollama_pool = ThreadPoolExecutor(max_workers=15, thread_name_prefix="ollama")

# NEW: Use shared pool with task_type="bridge"
from ...services.ollama_pool_manager import (
    submit_ollama_work_async,
    PoolExhaustedError,
)

class SmartBridgeGenerator:
    def __init__(self):
        # ... existing init code ...
        
        # REMOVED: self._ollama_pool = ThreadPoolExecutor(...)
        # Thread-local state preserved for httpx.AsyncClient compatibility
        self._thread_local = threading.local()
        
    async def _async_generate_bridge(self, request: BridgeGenerationRequest) -> BridgeGenerationResult:
        """Generate bridge using shared pool."""
        try:
            return await submit_ollama_work_async(
                self._generate_bridge_impl,
                request,
                task_type="bridge"  # Identifies this as bridge work for fair share
            )
        except PoolExhaustedError:
            logger.warning("Shared pool exhausted, falling back to mechanical bridge")
            return self._generate_mechanical_fallback_result(request)
```

### KG Builder Integration

**Changes to**: `src/multimodal_librarian/services/celery_service.py`

```python
# In _update_knowledge_graph (async function within update_knowledge_graph_task)

# OLD:
# semaphore = asyncio.Semaphore(MAX_CONCURRENT)
# async def process_chunk_with_semaphore(chunk):
#     async with semaphore:
#         return await kg_builder.process_knowledge_chunk_extract_only(chunk)

# NEW: Use shared pool with task_type="kg"
from ..services.ollama_pool_manager import (
    submit_ollama_work_async,
    PoolExhaustedError,
)

async def process_chunk_via_pool(chunk: KnowledgeChunk):
    """Process chunk using shared Ollama pool."""
    try:
        return await submit_ollama_work_async(
            kg_builder.process_knowledge_chunk_extract_only,
            chunk,
            task_type="kg"  # Identifies this as KG work for fair share
        )
    except PoolExhaustedError:
        logger.warning(f"Pool exhausted for chunk {chunk.id}, using regex/NER only")
        return await kg_builder.process_knowledge_chunk_regex_only(chunk)

tasks = [process_chunk_via_pool(chunk) for chunk in batch]
extractions = await asyncio.gather(*tasks, return_exceptions=True)
```

### KG Concept Extraction Gemini Failover

**Changes to**: `src/multimodal_librarian/components/knowledge_graph/kg_builder.py`

```python
class ConceptExtractor:
    def __init__(self):
        # ... existing init ...
        
        # Lazy Gemini init for concept extraction failover
        self._gemini_model = None
        self._gemini_initialized = False
        
        # Provider statistics
        self._concept_stats = {
            'ollama_success': 0,
            'gemini_fallback': 0,
            'both_failed': 0,
        }
    
    def _ensure_gemini(self):
        """Lazily initialize Gemini for concept extraction failover."""
        if not self._gemini_initialized:
            try:
                import google.generativeai as genai
                genai.configure()
                self._gemini_model = genai.GenerativeModel('gemini-2.5-flash')
                self._gemini_initialized = True
                logger.info("Initialized Gemini for KG concept extraction failover (lazy init)")
            except Exception as e:
                logger.warning(f"Gemini init failed for concept extraction: {e}")
                self._gemini_initialized = True  # Don't retry
    
    async def _extract_concepts_gemini(
        self, text: str, prompt: str
    ) -> List[ConceptNode]:
        """Extract concepts via Gemini (failover from Ollama)."""
        self._ensure_gemini()
        if self._gemini_model is None:
            return []
        
        try:
            response = await self._gemini_model.generate_content_async(prompt)
            entries = self._extract_json_array(response.text)
            if entries is None:
                return []
            grounded = self._filter_by_rationale(entries, text)
            # ... same concept building logic as extract_concepts_ollama ...
        except Exception as e:
            logger.warning(f"Gemini concept extraction also failed: {e}")
            return []
    
    async def extract_concepts_ollama(
        self, text: str, content_type: ContentType = ContentType.GENERAL
    ) -> List[ConceptNode]:
        """Extract concepts via Ollama, falling back to Gemini on failure."""
        # Build prompt (shared between Ollama and Gemini)
        config = DOMAIN_PROMPT_REGISTRY[content_type]
        prompt = CONCEPT_EXTRACTION_PROMPT_TEMPLATE.format(
            domain_description=config["domain_description"],
            concept_types=", ".join(config["concept_types"]),
            text=text[:2000],
        )
        
        # Try Ollama first
        client = await self._get_ollama_client()
        if client is not None:
            response = await client.generate(prompt, temperature=0.2, max_tokens=1000)
            if response.is_successful():
                concepts = self._parse_concept_response(response.content, text, content_type)
                if concepts:
                    self._concept_stats['ollama_success'] += 1
                    return concepts
        
        # Fallback to Gemini
        logger.info("Ollama concept extraction failed, falling back to Gemini")
        concepts = await self._extract_concepts_gemini(text, prompt)
        if concepts:
            self._concept_stats['gemini_fallback'] += 1
            return concepts
        
        self._concept_stats['both_failed'] += 1
        return []
```

## Data Models

### FairShareState

```python
@dataclass
class FairShareState:
    """Tracks fair share statistics for scheduling."""
    bridge_completed: int = 0       # Total bridge tasks completed
    kg_completed: int = 0           # Total KG tasks completed
    bridge_target_ratio: float = 0.5  # Target ratio (from OLLAMA_FAIR_SHARE_RATIO)
    kg_target_ratio: float = 0.5
    
    # Computed properties:
    # - bridge_actual_ratio: Current actual ratio of bridge completions
    # - kg_actual_ratio: Current actual ratio of KG completions
    # - bridge_deficit: Positive means bridge is behind target
    # - kg_deficit: Positive means KG is behind target
```

### Health Endpoint Response

```python
# GET /health/ollama-pool
{
    "status": "healthy",
    "pool": {
        "pool_size": 20,
        "queue_capacity": 1000,
        "bridge_pending": 12,
        "kg_pending": 8,
        "total_pending": 20,
        "bridge_completed": 450,
        "kg_completed": 380,
        "total_completed": 830,
        "utilization_pct": 2.0,
        "initialized": true,
        "fair_share": {
            "bridge_target_ratio": 0.5,
            "kg_target_ratio": 0.5,
            "bridge_actual_ratio": 0.542,
            "kg_actual_ratio": 0.458,
            "bridge_deficit": -0.042,
            "kg_deficit": 0.042
        },
        "concurrency": {
            "max_capacity": 20,
            "active_limit": 13,
            "active_count": 11,
            "timeout_rate": 0.6,
            "timeout_window": 20,
            "timeout_threshold": 0.5,
            "recovery_period": 30.0,
            "scaled_down": true
        }
    }
}
```

## Correctness Properties

### Property 1: Singleton Pool Instance

*For any* number of concurrent calls to `get_pool_manager()` from any threads within the same process, the function SHALL return the same `OllamaPoolManager` instance.

**Validates: Requirements 1.1, 7.4, 7.5**

### Property 2: Work Submission Returns Results

*For any* callable `fn` with arguments, calling `submit_ollama_work(fn, *args, task_type=t, **kwargs)` SHALL return a `Future` that resolves to `fn(*args, **kwargs)`.

**Validates: Requirements 1.3, 1.4**

### Property 3: Fair Share Scheduling Prevents Starvation

*For any* sequence of task submissions where both task types have pending work, the scheduler SHALL eventually execute tasks from both types. Specifically, if task type A has pending work and task type B completes N tasks, then task type A SHALL complete at least 1 task before B completes another N tasks (where N = pool_size).

**Validates: Requirements 8.3, 8.5**

### Property 4: Fair Share Deficit Drives Selection

*For any* state where both queues have pending work, the scheduler SHALL select from the queue whose task type has the larger deficit (target_ratio - actual_ratio).

**Validates: Requirements 8.3**

### Property 5: Single Queue Gets Full Capacity

*For any* state where only one task type has pending work, that task type SHALL be able to use all available pool capacity (no artificial limiting).

**Validates: Requirements 8.5**

### Property 6: Bounded Queue Enforcement

*For any* state where `total_pending >= queue_capacity`, subsequent calls to `submit_ollama_work()` SHALL raise `PoolExhaustedError`.

**Validates: Requirements 6.2, 6.5**

### Property 7: Configuration from Environment

*For any* value `N` set in `OLLAMA_NUM_PARALLEL`, the pool SHALL have `max_workers=N`. *For any* value `"A:B"` set in `OLLAMA_FAIR_SHARE_RATIO`, the target ratios SHALL be `A/(A+B)` and `B/(A+B)`.

**Validates: Requirements 1.2, 5.1, 8.7**

### Property 8: Fair Share Statistics Accuracy

*For any* sequence where bridge completes `b` tasks and KG completes `k` tasks, `get_pool_stats()` SHALL return `bridge_completed=b`, `kg_completed=k`, and `bridge_actual_ratio=b/(b+k)`.

**Validates: Requirements 5.2, 8.6**

### Property 9: Thread-Local Event Loop Reuse

*For any* worker thread, all async tasks on that thread SHALL use the same event loop instance until pool shutdown.

**Validates: Requirements 4.1, 4.2, 4.3, 4.4**

### Property 10: Concurrency Scale-Down on High Timeout Rate

*For any* sliding window of N results where the timeout rate exceeds the threshold, the active concurrency limit SHALL be halved (floor division, minimum 1). The sequence for capacity 20 SHALL be: 20 → 10 → 5 → 3 → 2 → 1.

**Validates: Requirements 9.2, 9.8**

### Property 11: Concurrency Scale-Up on Recovery

*For any* state where the timeout rate is below the threshold for at least the recovery period, the active concurrency limit SHALL be doubled (up to max capacity). The dispatcher SHALL NOT dispatch more tasks than the active concurrency limit.

**Validates: Requirements 9.3, 9.4**

### Property 12: Concurrency Limit Bounds

*For any* sequence of scale-down and scale-up operations, the active concurrency limit SHALL always satisfy: `1 <= active_limit <= max_capacity`.

**Validates: Requirements 9.2, 9.4**

## Error Handling

### PoolExhaustedError

Raised when the bounded queue is full. Both Bridge Generator and KG Builder have fallback paths.

### Worker Thread Failures

`ThreadPoolExecutor` automatically replaces dead workers. The dispatcher continues operation.

### Celery Worker Shutdown

```python
from celery.signals import worker_shutdown

@worker_shutdown.connect
def shutdown_ollama_pool(sender, **kwargs):
    from ..services.ollama_pool_manager import shutdown_pool
    shutdown_pool(wait=True)
```

## Task Deduplication via Distributed Locking

### Problem

Long-running Celery tasks (`generate_bridges_task`, `update_knowledge_graph_task`) use `ack_late` semantics. When a task hits its `soft_time_limit` and is killed, the unacknowledged message is redelivered by Redis. This spawns duplicate instances of the same task for the same document, multiplying Ollama load.

### Design

A reusable `@redis_task_lock` decorator that acquires a Redis distributed lock before task execution and releases it on completion.

```python
import functools
import redis
import threading
import time
import logging

logger = logging.getLogger(__name__)


class RedisTaskLock:
    """
    Distributed lock for Celery task deduplication.
    
    Uses Redis SET NX EX for atomic lock acquisition.
    Runs a background heartbeat thread to extend TTL while the task is alive.
    """
    
    def __init__(self, redis_client, lock_key: str, ttl: int):
        self.redis = redis_client
        self.lock_key = lock_key
        self.ttl = ttl
        self.lock_value = f"{threading.current_thread().name}:{time.time()}"
        self._heartbeat_thread = None
        self._stop_heartbeat = threading.Event()
    
    def acquire(self) -> bool:
        """Atomically acquire the lock. Returns True if acquired."""
        acquired = self.redis.set(
            self.lock_key, self.lock_value, nx=True, ex=self.ttl
        )
        if acquired:
            self._start_heartbeat()
        return bool(acquired)
    
    def release(self):
        """Release the lock if we still hold it (compare-and-delete)."""
        self._stop_heartbeat.set()
        if self._heartbeat_thread:
            self._heartbeat_thread.join(timeout=5)
        
        # Lua script for atomic compare-and-delete
        lua = """
        if redis.call("get", KEYS[1]) == ARGV[1] then
            return redis.call("del", KEYS[1])
        else
            return 0
        end
        """
        self.redis.eval(lua, 1, self.lock_key, self.lock_value)
    
    def _start_heartbeat(self):
        """Extend TTL periodically while task is running."""
        def heartbeat():
            interval = self.ttl / 3
            while not self._stop_heartbeat.wait(timeout=interval):
                # Only extend if we still hold the lock
                lua = """
                if redis.call("get", KEYS[1]) == ARGV[1] then
                    return redis.call("expire", KEYS[1], ARGV[2])
                else
                    return 0
                end
                """
                result = self.redis.eval(
                    lua, 1, self.lock_key, self.lock_value, str(self.ttl)
                )
                if not result:
                    break  # Lost the lock
        
        self._heartbeat_thread = threading.Thread(
            target=heartbeat, daemon=True, name=f"lock-heartbeat-{self.lock_key}"
        )
        self._heartbeat_thread.start()


def redis_task_lock(lock_key_template: str, ttl: int = None):
    """
    Decorator for Celery task deduplication.
    
    Args:
        lock_key_template: Redis key template with {document_id} placeholder
        ttl: Lock TTL in seconds. Defaults to task's soft_time_limit.
    
    Usage:
        @celery_app.task(soft_time_limit=3600)
        @redis_task_lock("bridge_lock:{document_id}")
        def generate_bridges_task(upstream_result, document_id):
            ...
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # Extract document_id from args
            document_id = kwargs.get('document_id') or args[1] if len(args) > 1 else 'unknown'
            lock_key = lock_key_template.format(document_id=document_id)
            
            # Determine TTL
            lock_ttl = ttl or getattr(func, 'soft_time_limit', 3600) or 3600
            
            # Get Redis client
            from ..services.celery_service import celery_app
            redis_client = celery_app.backend.client
            
            lock = RedisTaskLock(redis_client, lock_key, lock_ttl)
            
            if not lock.acquire():
                logger.warning(
                    f"Task {func.__name__} skipped for document {document_id}: "
                    f"lock {lock_key} already held (duplicate redelivery)"
                )
                return {'status': 'skipped_duplicate', 'document_id': document_id}
            
            try:
                return func(*args, **kwargs)
            finally:
                lock.release()
        
        return wrapper
    return decorator
```

### Integration with Celery Tasks

```python
# In celery_service.py

@celery_app.task(name='generate_bridges_task', time_limit=TASK_HARD_TIME_LIMIT, soft_time_limit=TASK_SOFT_TIME_LIMIT)
@redis_task_lock("bridge_lock:{document_id}")
def generate_bridges_task(upstream_result, document_id):
    ...

@celery_app.task(name='update_knowledge_graph_task', time_limit=TASK_HARD_TIME_LIMIT, soft_time_limit=TASK_SOFT_TIME_LIMIT)
@redis_task_lock("kg_lock:{document_id}")
def update_knowledge_graph_task(upstream_result, document_id):
    ...
```

### Correctness Property

**Property 13: Task Deduplication**

*For any* document_id, at most one instance of `generate_bridges_task` and at most one instance of `update_knowledge_graph_task` SHALL execute concurrently. If a second instance is delivered while the first holds the lock, the second SHALL return `skipped_duplicate` without executing.

**Validates: Requirements 10.1, 10.2, 10.3, 10.6**

**Property 14: Lock Auto-Expiry**

*For any* lock acquired with TTL `T`, if the lock holder is killed without releasing the lock and without heartbeat renewal, the lock SHALL expire after at most `T` seconds, allowing a new task instance to acquire it.

**Validates: Requirements 10.5**

### Property 15: KG Concept Extraction Gemini Failover

*For any* call to `extract_concepts_ollama()` where Ollama fails (timeout, error, or empty result), the method SHALL attempt extraction via Gemini using the same prompt. If Gemini succeeds, the result SHALL contain valid `ConceptNode` objects. If both fail, the result SHALL be `[]`.

**Validates: Requirements 11.1, 11.4**

## Testing Strategy

### Property-Based Tests

```python
from hypothesis import given, strategies as st, settings

@settings(max_examples=100)
@given(
    bridge_tasks=st.integers(min_value=0, max_value=100),
    kg_tasks=st.integers(min_value=0, max_value=100),
)
def test_fair_share_prevents_starvation(bridge_tasks, kg_tasks):
    """
    Feature: shared-ollama-thread-pool, Property 3: Fair Share Prevents Starvation
    
    When both task types have work, neither should be starved.
    """
    # Submit bridge_tasks and kg_tasks concurrently
    # Verify both make progress within bounded time
    ...

@settings(max_examples=100)
@given(
    bridge_ratio=st.floats(min_value=0.1, max_value=10.0),
    kg_ratio=st.floats(min_value=0.1, max_value=10.0),
)
def test_fair_share_ratio_parsing(bridge_ratio, kg_ratio):
    """
    Feature: shared-ollama-thread-pool, Property 7: Configuration from Environment
    
    OLLAMA_FAIR_SHARE_RATIO should be parsed correctly.
    """
    ratio_str = f"{bridge_ratio}:{kg_ratio}"
    expected_bridge = bridge_ratio / (bridge_ratio + kg_ratio)
    expected_kg = kg_ratio / (bridge_ratio + kg_ratio)
    # Verify parsed ratios match expected
    ...
```

### Unit Tests

1. Singleton behavior across threads
2. Lazy initialization
3. Default configuration (30 workers, 1:1 ratio)
4. Fair share deficit calculation
5. Queue selection logic
6. Health endpoint format
7. Shutdown behavior
8. Fallback paths in Bridge Generator and KG Builder
