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
    max_capacity: int = 16              # Configured OLLAMA_NUM_PARALLEL
    active_limit: int = 16              # Current active concurrency limit
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
        return int(os.environ.get('OLLAMA_NUM_PARALLEL', '16'))

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

                # Submit to thread pool — use default args to capture variables correctly
                def execute_and_complete(fn=fn, args=args, kwargs=kwargs, future=future, actual_task_type=actual_task_type):
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
        *args: Any,
        task_type: str = "unknown",
        **kwargs: Any
    ) -> 'Future[T]':
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
        future: Future = Future()

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
        *args: Any,
        task_type: str = "unknown",
        **kwargs: Any
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

        # Await the future from the calling async context.
        # Use a timeout to prevent infinite hangs if a worker thread deadlocks.
        timeout = float(os.environ.get('OLLAMA_POOL_FUTURE_TIMEOUT', '120'))
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, lambda: future.result(timeout=timeout))

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
    *args: Any,
    task_type: str = "unknown",
    **kwargs: Any
) -> 'Future[T]':
    """Convenience function to submit work to the shared pool."""
    return get_pool_manager().submit_ollama_work(fn, *args, task_type=task_type, **kwargs)


async def submit_ollama_work_async(
    coro_fn: Callable[..., Coroutine[Any, Any, T]],
    *args: Any,
    task_type: str = "unknown",
    **kwargs: Any
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
