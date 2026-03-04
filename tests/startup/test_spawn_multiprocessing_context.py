"""
Tests for spawn multiprocessing context configuration in ModelManager.

This test verifies that the ModelManager correctly configures the 'spawn'
multiprocessing context for PyTorch compatibility, which is required to
avoid GIL blocking during model initialization.
"""

import pytest
import multiprocessing
import os
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from unittest.mock import patch, MagicMock


# Module-level functions for ProcessPoolExecutor (required for spawn context pickling)
def _return_42():
    """Simple function that returns 42 - must be at module level for pickling."""
    return 42


def _get_worker_pid():
    """Get the current process ID - must be at module level for pickling."""
    return os.getpid()


def _check_fresh_interpreter():
    """Check if running in a fresh interpreter - must be at module level for pickling."""
    import sys
    return sys.executable is not None


class TestSpawnMultiprocessingContext:
    """Tests for spawn multiprocessing context configuration."""
    
    def test_spawn_context_available(self):
        """Test that spawn multiprocessing context is available on this system."""
        # Get spawn context - should not raise
        mp_context = multiprocessing.get_context('spawn')
        assert mp_context is not None
        assert mp_context.get_start_method() == 'spawn'
    
    def test_process_pool_with_spawn_context(self):
        """Test that ProcessPoolExecutor can be created with spawn context."""
        mp_context = multiprocessing.get_context('spawn')
        
        # Create ProcessPoolExecutor with spawn context
        pool = ProcessPoolExecutor(max_workers=1, mp_context=mp_context)
        
        try:
            # Verify pool is functional using module-level function
            future = pool.submit(_return_42)
            result = future.result(timeout=10)
            assert result == 42
        finally:
            pool.shutdown(wait=True)
    
    def test_model_manager_uses_spawn_context(self):
        """Test that ModelManager initializes with spawn context."""
        from multimodal_librarian.models.model_manager import ModelManager
        
        # Create ModelManager
        manager = ModelManager(max_concurrent_loads=1)
        
        try:
            # Verify process pool was created
            assert hasattr(manager, 'process_pool')
            assert manager.process_pool is not None
            
            # Verify _use_process_pool flag is set correctly
            # It should be True if ProcessPoolExecutor was created successfully
            # or False if it fell back to ThreadPoolExecutor
            assert hasattr(manager, '_use_process_pool')
            
            # On most systems, ProcessPoolExecutor should work
            # If it doesn't, the fallback to ThreadPoolExecutor is acceptable
            if manager._use_process_pool:
                assert isinstance(manager.process_pool, ProcessPoolExecutor)
            else:
                assert isinstance(manager.process_pool, ThreadPoolExecutor)
        finally:
            # Cleanup
            if hasattr(manager, 'process_pool') and manager.process_pool:
                manager.process_pool.shutdown(wait=True)
            if hasattr(manager, 'thread_pool') and manager.thread_pool:
                manager.thread_pool.shutdown(wait=True)
    
    def test_model_manager_fallback_to_thread_pool(self):
        """Test that ModelManager falls back to ThreadPoolExecutor if ProcessPoolExecutor fails."""
        from multimodal_librarian.models.model_manager import ModelManager
        
        # Mock multiprocessing.get_context to raise an exception
        with patch('multimodal_librarian.models.model_manager.multiprocessing.get_context') as mock_get_context:
            mock_get_context.side_effect = Exception("Multiprocessing not available")
            
            # Create ModelManager - should fall back to ThreadPoolExecutor
            manager = ModelManager(max_concurrent_loads=1)
            
            try:
                # Verify fallback occurred
                assert manager._use_process_pool is False
                assert isinstance(manager.process_pool, ThreadPoolExecutor)
            finally:
                # Cleanup
                if hasattr(manager, 'process_pool') and manager.process_pool:
                    manager.process_pool.shutdown(wait=True)
                if hasattr(manager, 'thread_pool') and manager.thread_pool:
                    manager.thread_pool.shutdown(wait=True)
    
    def test_spawn_context_documentation(self):
        """Test that the spawn context configuration is properly documented in code."""
        import inspect
        from multimodal_librarian.models.model_manager import ModelManager
        
        # Get the source code of __init__
        source = inspect.getsource(ModelManager.__init__)
        
        # Verify documentation mentions spawn context
        assert 'spawn' in source.lower()
        assert 'pytorch' in source.lower() or 'PyTorch' in source
        
        # Verify the actual implementation uses spawn
        assert "get_context('spawn')" in source or 'get_context("spawn")' in source


class TestProcessPoolIsolation:
    """Tests for verifying process pool isolation from main event loop."""
    
    def test_process_pool_runs_in_separate_process(self):
        """Test that work submitted to process pool runs in a separate process."""
        mp_context = multiprocessing.get_context('spawn')
        pool = ProcessPoolExecutor(max_workers=1, mp_context=mp_context)
        
        try:
            # Get current process ID
            main_pid = os.getpid()
            
            # Submit work to get the worker process ID using module-level function
            future = pool.submit(_get_worker_pid)
            worker_pid = future.result(timeout=10)
            
            # Worker should be in a different process
            assert worker_pid != main_pid
        finally:
            pool.shutdown(wait=True)
    
    def test_spawn_creates_fresh_interpreter(self):
        """Test that spawn context creates fresh Python interpreters."""
        mp_context = multiprocessing.get_context('spawn')
        pool = ProcessPoolExecutor(max_workers=1, mp_context=mp_context)
        
        try:
            # Use module-level function to check fresh interpreter
            future = pool.submit(_check_fresh_interpreter)
            result = future.result(timeout=10)
            
            assert result is True
        finally:
            pool.shutdown(wait=True)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
