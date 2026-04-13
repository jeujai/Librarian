"""
Distributed locking for Celery task deduplication.

Provides a Redis-based distributed lock (`RedisTaskLock`) and a reusable
decorator (`redis_task_lock`) that prevents duplicate execution of
long-running Celery tasks when unacknowledged messages are redelivered.

Lock acquisition is atomic (SET NX EX).  A background heartbeat thread
extends the TTL while the task is alive.  Release uses a Lua
compare-and-delete script so only the holder can free the lock.

Requirements: 10.3, 10.5, 10.6, 10.7, 10.8
"""

import functools
import logging
import os
import threading
import time
from typing import Optional

from celery.exceptions import Ignore

logger = logging.getLogger(__name__)


# Lua script: atomic compare-and-delete
_RELEASE_LUA = """
if redis.call("get", KEYS[1]) == ARGV[1] then
    return redis.call("del", KEYS[1])
else
    return 0
end
"""

# Lua script: atomic compare-and-expire (heartbeat renewal)
_HEARTBEAT_LUA = """
if redis.call("get", KEYS[1]) == ARGV[1] then
    return redis.call("expire", KEYS[1], ARGV[2])
else
    return 0
end
"""


class RedisTaskLock:
    """
    Distributed lock for Celery task deduplication.

    Uses Redis ``SET NX EX`` for atomic lock acquisition.
    Runs a background heartbeat thread to extend TTL while the task is alive.
    """

    def __init__(self, redis_client, lock_key: str, ttl: int):
        self.redis = redis_client
        self.lock_key = lock_key
        self.ttl = ttl
        self.lock_value = f"{os.getpid()}:{threading.current_thread().name}:{time.time()}"
        self._heartbeat_thread: Optional[threading.Thread] = None
        self._stop_heartbeat = threading.Event()

    def acquire(self) -> bool:
        """Atomically acquire the lock. Returns True if acquired."""
        acquired = self.redis.set(
            self.lock_key, self.lock_value, nx=True, ex=self.ttl
        )
        if acquired:
            self._start_heartbeat()
            logger.debug(f"Lock acquired: {self.lock_key} (ttl={self.ttl}s)")
        return bool(acquired)

    def release(self):
        """Release the lock if we still hold it (compare-and-delete via Lua)."""
        self._stop_heartbeat.set()
        if self._heartbeat_thread is not None:
            self._heartbeat_thread.join(timeout=5)

        try:
            self.redis.eval(_RELEASE_LUA, 1, self.lock_key, self.lock_value)
            logger.debug(f"Lock released: {self.lock_key}")
        except Exception as exc:
            logger.warning(f"Failed to release lock {self.lock_key}: {exc}")

    def _start_heartbeat(self):
        """Extend TTL periodically (every TTL/3 seconds) while task is running."""
        interval = max(1, self.ttl // 3)

        def _heartbeat():
            while not self._stop_heartbeat.wait(timeout=interval):
                try:
                    result = self.redis.eval(
                        _HEARTBEAT_LUA, 1,
                        self.lock_key, self.lock_value, str(self.ttl),
                    )
                    if not result:
                        logger.warning(
                            f"Heartbeat lost lock {self.lock_key} — stopping renewal"
                        )
                        break
                except Exception as exc:
                    logger.warning(f"Heartbeat error for {self.lock_key}: {exc}")
                    break

        self._heartbeat_thread = threading.Thread(
            target=_heartbeat,
            daemon=True,
            name=f"lock-heartbeat-{self.lock_key}",
        )
        self._heartbeat_thread.start()


def _get_redis_client():
    """Get a Redis client from the Celery broker URL."""
    import redis as _redis

    broker_url = os.environ.get("CELERY_BROKER_URL", "redis://redis:6379/0")
    return _redis.Redis.from_url(broker_url)


def redis_task_lock(lock_key_template: str, ttl: Optional[int] = None):
    """
    Decorator for Celery task deduplication via distributed locking.

    Acquires a Redis lock keyed by *lock_key_template* (with ``{document_id}``
    interpolated) before the wrapped function executes.  If the lock is already
    held, the task returns ``{'status': 'skipped_duplicate', ...}`` immediately.

    Args:
        lock_key_template: Redis key template, e.g. ``"bridge_lock:{document_id}"``.
        ttl: Lock TTL in seconds.  Defaults to the Celery task's
             ``soft_time_limit`` if available, otherwise 3600.

    Usage::

        @celery_app.task(soft_time_limit=3600)
        @redis_task_lock("bridge_lock:{document_id}")
        def generate_bridges_task(upstream_result, document_id):
            ...

    Requirements: 10.3, 10.6, 10.8
    """

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # Extract document_id from kwargs or positional args
            # It could be the first arg (extract_pdf_content_task) or
            # the second arg (generate_chunks_task, generate_bridges_task, etc.)
            document_id = kwargs.get("document_id")
            if document_id is None:
                # Try to find document_id in positional args
                # Check args[1] first (most tasks have upstream_result as first arg)
                if len(args) > 1:
                    document_id = args[1]
                elif len(args) > 0:
                    # Single-arg tasks like extract_pdf_content_task
                    document_id = args[0]
            if document_id is None:
                document_id = "unknown"

            lock_key = lock_key_template.format(document_id=document_id)

            # Determine TTL: explicit > 600s default (heartbeat extends while alive)
            # A short initial TTL ensures stale locks from crashed workers
            # expire quickly, while the heartbeat thread keeps the lock
            # alive for the full duration of healthy task execution.
            lock_ttl = ttl
            if lock_ttl is None:
                lock_ttl = 600  # 10 minutes; heartbeat renews every TTL/3

            redis_client = _get_redis_client()
            lock = RedisTaskLock(redis_client, lock_key, lock_ttl)

            if not lock.acquire():
                logger.warning(
                    f"Task {func.__name__} skipped for document {document_id}: "
                    f"lock {lock_key} already held (duplicate redelivery)"
                )
                raise Ignore()

            try:
                return func(*args, **kwargs)
            finally:
                lock.release()

        return wrapper

    return decorator
