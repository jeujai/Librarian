"""
Test Helpers

This module provides utility functions for testing.
"""

import time
import asyncio
from typing import Any, Dict, Optional
from contextlib import asynccontextmanager

class TestTimer:
    """Simple timer for performance testing."""
    
    def __init__(self):
        self.start_time = None
        self.end_time = None
    
    def start(self):
        """Start the timer."""
        self.start_time = time.time()
    
    def stop(self):
        """Stop the timer."""
        self.end_time = time.time()
    
    @property
    def elapsed(self) -> float:
        """Get elapsed time in seconds."""
        if self.start_time is None:
            return 0.0
        end = self.end_time or time.time()
        return end - self.start_time

@asynccontextmanager
async def async_timer():
    """Async context manager for timing operations."""
    timer = TestTimer()
    timer.start()
    try:
        yield timer
    finally:
        timer.stop()

def assert_performance(timer: TestTimer, max_duration: float, operation: str = "operation"):
    """Assert that an operation completed within the expected time."""
    assert timer.elapsed <= max_duration, (
        f"{operation} took {timer.elapsed:.2f}s, expected <= {max_duration}s"
    )

def wait_for_condition(condition_func, timeout: float = 10.0, interval: float = 0.1):
    """Wait for a condition to become true."""
    start_time = time.time()
    while time.time() - start_time < timeout:
        if condition_func():
            return True
        time.sleep(interval)
    return False

async def async_wait_for_condition(condition_func, timeout: float = 10.0, interval: float = 0.1):
    """Async version of wait_for_condition."""
    start_time = time.time()
    while time.time() - start_time < timeout:
        if await condition_func() if asyncio.iscoroutinefunction(condition_func) else condition_func():
            return True
        await asyncio.sleep(interval)
    return False
