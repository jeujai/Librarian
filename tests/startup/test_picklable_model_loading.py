"""
Tests for picklable model loading functions.

This test verifies that the model loading functions are properly picklable
and can be used with ProcessPoolExecutor for subprocess-based model loading.

Key requirements tested:
- _load_model_sync_picklable is at module level (not a method)
- _load_model_sync_picklable has no closures or lambdas
- _load_model_sync_picklable only uses primitive/picklable arguments
- extract_picklable_config correctly extracts picklable data from ModelConfig
"""

import pytest
import pickle
import multiprocessing
import os
from concurrent.futures import ProcessPoolExecutor
from typing import Dict, Any, List


class TestPicklableFunctions:
    """Tests for verifying functions are picklable."""
    
    def test_load_model_sync_picklable_is_module_level(self):
        """Test that _load_model_sync_picklable is defined at module level."""
        from multimodal_librarian.models import model_manager
        
        # Verify function exists at module level
        assert hasattr(model_manager, '_load_model_sync_picklable')
        
        # Verify it's a function, not a method
        import types
        assert isinstance(model_manager._load_model_sync_picklable, types.FunctionType)
    
    def test_load_model_sync_picklable_can_be_pickled(self):
        """Test that _load_model_sync_picklable can be pickled."""
        from multimodal_librarian.models.model_manager import _load_model_sync_picklable
        
        # Attempt to pickle the function
        pickled = pickle.dumps(_load_model_sync_picklable)
        
        # Verify it can be unpickled
        unpickled = pickle.loads(pickled)
        
        # Verify the unpickled function is callable
        assert callable(unpickled)
    
    def test_load_model_in_process_can_be_pickled(self):
        """Test that _load_model_in_process can be pickled."""
        from multimodal_librarian.models.model_manager import _load_model_in_process
        
        # Attempt to pickle the function
        pickled = pickle.dumps(_load_model_in_process)
        
        # Verify it can be unpickled
        unpickled = pickle.loads(pickled)
        
        # Verify the unpickled function is callable
        assert callable(unpickled)
    
    def test_extract_picklable_config_exists(self):
        """Test that extract_picklable_config function exists."""
        from multimodal_librarian.models import model_manager
        
        assert hasattr(model_manager, 'extract_picklable_config')
        
        import types
        assert isinstance(model_manager.extract_picklable_config, types.FunctionType)


class TestPicklableConfigExtraction:
    """Tests for extracting picklable config data."""
    
    def test_extract_picklable_config_returns_dict(self):
        """Test that extract_picklable_config returns a dictionary."""
        from multimodal_librarian.models.model_manager import (
            ModelConfig, ModelPriority, extract_picklable_config
        )
        
        config = ModelConfig(
            name="test-model",
            priority=ModelPriority.ESSENTIAL,
            estimated_load_time_seconds=5.0,
            estimated_memory_mb=100.0,
            required_for_capabilities=["test_capability"],
            model_type="test"
        )
        
        result = extract_picklable_config(config)
        
        assert isinstance(result, dict)
    
    def test_extract_picklable_config_all_values_are_primitive(self):
        """Test that all values in extracted config are primitive types."""
        from multimodal_librarian.models.model_manager import (
            ModelConfig, ModelPriority, extract_picklable_config
        )
        
        config = ModelConfig(
            name="test-model",
            priority=ModelPriority.ESSENTIAL,
            estimated_load_time_seconds=5.0,
            estimated_memory_mb=100.0,
            required_for_capabilities=["cap1", "cap2"],
            model_type="embedding",
            fallback_models=["fallback1"],
            dependencies=["dep1"]
        )
        
        result = extract_picklable_config(config)
        
        # Check all values are primitive types
        primitive_types = (str, int, float, bool, list, type(None))
        
        for key, value in result.items():
            if isinstance(value, list):
                for item in value:
                    assert isinstance(item, primitive_types), f"List item {item} in {key} is not primitive"
            else:
                assert isinstance(value, primitive_types), f"Value {value} for {key} is not primitive"
    
    def test_extract_picklable_config_can_be_pickled(self):
        """Test that extracted config can be pickled."""
        from multimodal_librarian.models.model_manager import (
            ModelConfig, ModelPriority, extract_picklable_config
        )
        
        config = ModelConfig(
            name="test-model",
            priority=ModelPriority.ESSENTIAL,
            estimated_load_time_seconds=5.0,
            estimated_memory_mb=100.0,
            required_for_capabilities=["test_capability"],
            model_type="test"
        )
        
        result = extract_picklable_config(config)
        
        # Attempt to pickle
        pickled = pickle.dumps(result)
        
        # Verify it can be unpickled
        unpickled = pickle.loads(pickled)
        
        assert unpickled == result


class TestProcessPoolExecution:
    """Tests for executing picklable functions in ProcessPoolExecutor."""
    
    def test_load_model_sync_picklable_in_process_pool(self):
        """Test that _load_model_sync_picklable can run in ProcessPoolExecutor."""
        from multimodal_librarian.models.model_manager import _load_model_sync_picklable
        
        mp_context = multiprocessing.get_context('spawn')
        pool = ProcessPoolExecutor(max_workers=1, mp_context=mp_context)
        
        try:
            # Submit the picklable function with primitive arguments
            future = pool.submit(
                _load_model_sync_picklable,
                "test-model",           # model_name: str
                "embedding",            # model_type: str
                0.1,                    # estimated_load_time_seconds: float (short for test)
                50.0,                   # estimated_memory_mb: float
                ["test_capability"],    # required_for_capabilities: List[str]
                None                    # cache_dir: Optional[str]
            )
            
            # Get result with timeout
            result = future.result(timeout=30)
            
            # Verify result structure
            assert isinstance(result, dict)
            assert result["name"] == "test-model"
            assert result["type"] == "embedding"
            assert "loaded_at" in result
            assert result["capabilities"] == ["test_capability"]
            assert result["memory_usage_mb"] == 50.0
            assert result["loaded_in_process"] is True
            
        finally:
            pool.shutdown(wait=True)
    
    def test_load_model_in_process_in_process_pool(self):
        """Test that _load_model_in_process can run in ProcessPoolExecutor."""
        from multimodal_librarian.models.model_manager import _load_model_in_process
        
        mp_context = multiprocessing.get_context('spawn')
        pool = ProcessPoolExecutor(max_workers=1, mp_context=mp_context)
        
        try:
            # Submit the picklable function with primitive arguments
            future = pool.submit(
                _load_model_in_process,
                "test-model",           # model_name: str
                "language_model",       # model_type: str
                0.1,                    # estimated_load_time_seconds: float (short for test)
                200.0,                  # estimated_memory_mb: float
                ["chat", "reasoning"]   # required_for_capabilities: List[str]
            )
            
            # Get result with timeout
            result = future.result(timeout=30)
            
            # Verify result structure
            assert isinstance(result, dict)
            assert result["name"] == "test-model"
            assert result["type"] == "language_model"
            assert "loaded_at" in result
            assert result["capabilities"] == ["chat", "reasoning"]
            assert result["memory_usage_mb"] == 200.0
            assert result["loaded_in_process"] is True
            assert "process_name" in result
            
        finally:
            pool.shutdown(wait=True)


class TestModelManagerIntegration:
    """Integration tests for ModelManager with picklable functions."""
    
    def test_model_manager_uses_picklable_function(self):
        """Test that ModelManager uses the picklable function for process pool."""
        import inspect
        from multimodal_librarian.models.model_manager import ModelManager
        
        # Get the source code of _load_model_async
        source = inspect.getsource(ModelManager._load_model_async)
        
        # Verify it references the picklable function
        assert '_load_model_sync_picklable' in source or '_load_model_in_process' in source
    
    def test_model_manager_extracts_picklable_config(self):
        """Test that ModelManager extracts picklable config before subprocess transfer."""
        import inspect
        from multimodal_librarian.models.model_manager import ModelManager
        
        # Get the source code of _load_model_async
        source = inspect.getsource(ModelManager._load_model_async)
        
        # Verify it uses extract_picklable_config
        assert 'extract_picklable_config' in source or 'picklable_config' in source.lower()
    
    def test_model_manager_get_cache_dir_method(self):
        """Test that ModelManager has _get_cache_dir helper method."""
        from multimodal_librarian.models.model_manager import ModelManager
        
        manager = ModelManager(max_concurrent_loads=1)
        
        try:
            # Verify method exists
            assert hasattr(manager, '_get_cache_dir')
            
            # Verify it returns None or a string
            result = manager._get_cache_dir()
            assert result is None or isinstance(result, str)
            
        finally:
            if hasattr(manager, 'process_pool') and manager.process_pool:
                manager.process_pool.shutdown(wait=True)
            if hasattr(manager, 'thread_pool') and manager.thread_pool:
                manager.thread_pool.shutdown(wait=True)


class TestNoClosuresOrLambdas:
    """Tests to verify functions don't use closures or lambdas."""
    
    def test_load_model_sync_picklable_no_closures(self):
        """Test that _load_model_sync_picklable has no closure variables."""
        from multimodal_librarian.models.model_manager import _load_model_sync_picklable
        
        # Check for closure variables
        closure = _load_model_sync_picklable.__closure__
        
        # Should have no closure (None or empty)
        assert closure is None or len(closure) == 0
    
    def test_load_model_in_process_no_closures(self):
        """Test that _load_model_in_process has no closure variables."""
        from multimodal_librarian.models.model_manager import _load_model_in_process
        
        # Check for closure variables
        closure = _load_model_in_process.__closure__
        
        # Should have no closure (None or empty)
        assert closure is None or len(closure) == 0
    
    def test_extract_picklable_config_no_closures(self):
        """Test that extract_picklable_config has no closure variables."""
        from multimodal_librarian.models.model_manager import extract_picklable_config
        
        # Check for closure variables
        closure = extract_picklable_config.__closure__
        
        # Should have no closure (None or empty)
        assert closure is None or len(closure) == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
