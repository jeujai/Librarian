"""
Tests for subprocess error handling in model loading.

This module tests the error handling for subprocess failures during model loading,
including BrokenProcessPool, pickling errors, memory errors, and OS errors.
"""

import pytest
import asyncio
import pickle
from unittest.mock import patch, MagicMock, AsyncMock
from concurrent.futures import BrokenExecutor
from concurrent.futures.process import BrokenProcessPool


class TestSubprocessError:
    """Tests for the SubprocessError exception class."""
    
    def test_subprocess_error_creation(self):
        """Test basic SubprocessError creation."""
        from multimodal_librarian.models.model_manager import SubprocessError
        
        original_error = RuntimeError("Test error")
        error = SubprocessError(
            model_name="test-model",
            original_error=original_error,
            error_type="test_error",
            is_recoverable=True,
            suggested_action="retry"
        )
        
        assert error.model_name == "test-model"
        assert error.original_error == original_error
        assert error.error_type == "test_error"
        assert error.is_recoverable is True
        assert error.suggested_action == "retry"
        assert "test-model" in str(error)
        assert "test_error" in str(error)
    
    def test_from_broken_process_pool(self):
        """Test SubprocessError.from_exception with BrokenProcessPool."""
        from multimodal_librarian.models.model_manager import SubprocessError
        
        original_error = BrokenProcessPool("Worker died")
        error = SubprocessError.from_exception("test-model", original_error)
        
        assert error.model_name == "test-model"
        assert error.error_type == "broken_process_pool"
        assert error.is_recoverable is True
        assert error.suggested_action == "recreate_pool_and_retry"
    
    def test_from_broken_executor(self):
        """Test SubprocessError.from_exception with BrokenExecutor."""
        from multimodal_librarian.models.model_manager import SubprocessError
        
        original_error = BrokenExecutor("Executor broken")
        error = SubprocessError.from_exception("test-model", original_error)
        
        assert error.error_type == "broken_executor"
        assert error.is_recoverable is True
        assert error.suggested_action == "recreate_pool_and_retry"
    
    def test_from_pickling_error(self):
        """Test SubprocessError.from_exception with PicklingError."""
        from multimodal_librarian.models.model_manager import SubprocessError
        
        original_error = pickle.PicklingError("Cannot pickle object")
        error = SubprocessError.from_exception("test-model", original_error)
        
        assert error.error_type == "pickling_error"
        assert error.is_recoverable is False
        assert error.suggested_action == "use_thread_pool_fallback"
    
    def test_from_timeout_error(self):
        """Test SubprocessError.from_exception with TimeoutError."""
        from multimodal_librarian.models.model_manager import SubprocessError
        
        original_error = asyncio.TimeoutError("Operation timed out")
        error = SubprocessError.from_exception("test-model", original_error)
        
        assert error.error_type == "timeout"
        assert error.is_recoverable is True
        assert error.suggested_action == "retry_with_longer_timeout"
    
    def test_from_memory_error(self):
        """Test SubprocessError.from_exception with MemoryError."""
        from multimodal_librarian.models.model_manager import SubprocessError
        
        original_error = MemoryError("Out of memory")
        error = SubprocessError.from_exception("test-model", original_error)
        
        assert error.error_type == "memory_error"
        assert error.is_recoverable is True
        assert error.suggested_action == "unload_models_and_retry"
    
    def test_from_os_error_resource(self):
        """Test SubprocessError.from_exception with resource-related OSError."""
        from multimodal_librarian.models.model_manager import SubprocessError
        
        original_error = OSError("Cannot allocate memory")
        error = SubprocessError.from_exception("test-model", original_error)
        
        assert error.error_type == "resource_exhaustion"
        assert error.is_recoverable is True
        assert error.suggested_action == "wait_and_retry"
    
    def test_from_cuda_error(self):
        """Test SubprocessError.from_exception with CUDA RuntimeError."""
        from multimodal_librarian.models.model_manager import SubprocessError
        
        original_error = RuntimeError("CUDA out of memory")
        error = SubprocessError.from_exception("test-model", original_error)
        
        assert error.error_type == "cuda_error"
        assert error.is_recoverable is True
        assert error.suggested_action == "retry_on_cpu"
    
    def test_from_unknown_error(self):
        """Test SubprocessError.from_exception with unknown error type."""
        from multimodal_librarian.models.model_manager import SubprocessError
        
        original_error = ValueError("Unknown error")
        error = SubprocessError.from_exception("test-model", original_error)
        
        assert error.error_type == "unknown"
        assert error.is_recoverable is True
        assert error.suggested_action == "retry"


class TestModelManagerSubprocessErrorHandling:
    """Tests for ModelManager subprocess error handling."""
    
    @pytest.fixture
    def model_manager(self):
        """Create a ModelManager instance for testing."""
        from multimodal_librarian.models.model_manager import ModelManager
        manager = ModelManager(max_concurrent_loads=2)
        return manager
    
    def test_model_manager_has_subprocess_statistics(self, model_manager):
        """Test that ModelManager tracks subprocess-related statistics."""
        stats = model_manager.load_statistics
        
        # These statistics should be tracked
        assert "process_pool_loads" in stats
        assert "thread_pool_loads" in stats
        assert stats["process_pool_loads"] == 0
        assert stats["thread_pool_loads"] == 0
    
    def test_handle_broken_process_pool_method_exists(self, model_manager):
        """Test that _handle_broken_process_pool method exists."""
        assert hasattr(model_manager, '_handle_broken_process_pool')
        assert asyncio.iscoroutinefunction(model_manager._handle_broken_process_pool)
    
    def test_handle_memory_error_method_exists(self, model_manager):
        """Test that _handle_memory_error method exists."""
        assert hasattr(model_manager, '_handle_memory_error')
        assert asyncio.iscoroutinefunction(model_manager._handle_memory_error)
    
    @pytest.mark.asyncio
    async def test_handle_broken_process_pool_recreates_pool(self, model_manager):
        """Test that _handle_broken_process_pool recreates the process pool."""
        from multimodal_librarian.models.model_manager import SubprocessError
        
        # Create a subprocess error
        original_error = BrokenProcessPool("Worker died")
        error = SubprocessError.from_exception("test-model", original_error)
        
        # Store reference to old pool
        old_pool = model_manager.process_pool
        
        # Handle the broken pool
        await model_manager._handle_broken_process_pool("test-model", error)
        
        # Verify pool was recreated
        assert model_manager.process_pool is not old_pool
        assert model_manager._use_process_pool is True
        
        # Verify statistics were updated
        assert model_manager.load_statistics.get("pool_recreations", 0) >= 1
        
        # Cleanup
        await model_manager.shutdown()
    
    @pytest.mark.asyncio
    async def test_handle_memory_error_runs_gc(self, model_manager):
        """Test that _handle_memory_error runs garbage collection."""
        import gc
        
        with patch.object(gc, 'collect') as mock_gc:
            await model_manager._handle_memory_error("test-model")
            
            # GC should be called at least twice (before and after unloading)
            assert mock_gc.call_count >= 2
        
        # Cleanup
        await model_manager.shutdown()


class TestSubprocessErrorRecovery:
    """Tests for subprocess error recovery strategies."""
    
    def test_broken_pool_is_recoverable(self):
        """Test that broken process pool errors are marked as recoverable."""
        from multimodal_librarian.models.model_manager import SubprocessError
        
        error = SubprocessError.from_exception("test", BrokenProcessPool("died"))
        assert error.is_recoverable is True
    
    def test_pickling_error_not_recoverable(self):
        """Test that pickling errors are marked as not recoverable."""
        from multimodal_librarian.models.model_manager import SubprocessError
        
        error = SubprocessError.from_exception("test", pickle.PicklingError("cannot pickle"))
        assert error.is_recoverable is False
    
    def test_memory_error_is_recoverable(self):
        """Test that memory errors are marked as recoverable."""
        from multimodal_librarian.models.model_manager import SubprocessError
        
        error = SubprocessError.from_exception("test", MemoryError("OOM"))
        assert error.is_recoverable is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
