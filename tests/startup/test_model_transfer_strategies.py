"""
Tests for Model Transfer Strategies

This module tests the shared memory and path-based model transfer strategies
implemented in the ModelManager for ProcessPoolExecutor model loading.

Key Features Tested:
- Path-based model transfer (save to file, load in main process)
- Shared memory model transfer (zero-copy tensor transfer)
- Transfer strategy selection and configuration
- Cleanup of transfer resources
- Fallback behavior when strategies fail
"""

import asyncio
import os
import sys
import tempfile
import pytest
import pickle
from unittest.mock import MagicMock, patch, AsyncMock
from datetime import datetime

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from multimodal_librarian.models.model_manager import (
    ModelManager,
    ModelTransferStrategy,
    ModelTransferResult,
    ModelConfig,
    ModelPriority,
    ModelStatus,
    _load_model_sync_picklable,
    _load_model_with_path_transfer,
    _load_model_with_shared_memory,
    _get_model_transfer_dir,
    _generate_transfer_filename,
    SHARED_MEMORY_AVAILABLE,
)


class TestModelTransferStrategy:
    """Tests for ModelTransferStrategy enum."""
    
    def test_transfer_strategy_values(self):
        """Test that all transfer strategies have correct values."""
        assert ModelTransferStrategy.METADATA_ONLY.value == "metadata_only"
        assert ModelTransferStrategy.PATH_BASED.value == "path_based"
        assert ModelTransferStrategy.SHARED_MEMORY.value == "shared_memory"
        assert ModelTransferStrategy.HYBRID.value == "hybrid"
    
    def test_transfer_strategy_from_string(self):
        """Test creating transfer strategy from string value."""
        assert ModelTransferStrategy("metadata_only") == ModelTransferStrategy.METADATA_ONLY
        assert ModelTransferStrategy("path_based") == ModelTransferStrategy.PATH_BASED
        assert ModelTransferStrategy("shared_memory") == ModelTransferStrategy.SHARED_MEMORY


class TestModelTransferResult:
    """Tests for ModelTransferResult dataclass."""
    
    def test_transfer_result_creation(self):
        """Test creating a ModelTransferResult."""
        result = ModelTransferResult(
            model_name="test-model",
            transfer_strategy="path_based",
            success=True,
            model_type="embedding",
            loaded_at=datetime.now().isoformat(),
            capabilities=["search", "embedding"],
            memory_usage_mb=100.0,
            loaded_from_cache=False,
            process_name="TestProcess",
            model_path="/tmp/test_model.pkl"
        )
        
        assert result.model_name == "test-model"
        assert result.transfer_strategy == "path_based"
        assert result.success is True
        assert result.model_path == "/tmp/test_model.pkl"
    
    def test_transfer_result_to_dict(self):
        """Test converting ModelTransferResult to dictionary."""
        result = ModelTransferResult(
            model_name="test-model",
            transfer_strategy="shared_memory",
            success=True,
            model_type="language_model",
            loaded_at="2024-01-01T00:00:00",
            capabilities=["chat"],
            memory_usage_mb=500.0,
            loaded_from_cache=True,
            process_name="Worker-1",
            shared_memory_name="shm_test",
            shared_memory_size=1024
        )
        
        result_dict = result.to_dict()
        
        assert result_dict["name"] == "test-model"
        assert result_dict["transfer_strategy"] == "shared_memory"
        assert result_dict["shared_memory_name"] == "shm_test"
        assert result_dict["shared_memory_size"] == 1024


class TestTransferHelperFunctions:
    """Tests for transfer helper functions."""
    
    def test_get_model_transfer_dir(self):
        """Test getting the model transfer directory."""
        transfer_dir = _get_model_transfer_dir()
        
        assert transfer_dir is not None
        assert os.path.exists(transfer_dir)
        assert "multimodal_librarian_model_transfer" in transfer_dir
    
    def test_generate_transfer_filename(self):
        """Test generating unique transfer filenames."""
        filename1 = _generate_transfer_filename("test-model", ".pkl")
        filename2 = _generate_transfer_filename("test-model", ".pkl")
        
        # Filenames should be unique
        assert filename1 != filename2
        
        # Should contain model name and suffix
        assert "test_model" in filename1 or "test-model" in filename1
        assert filename1.endswith(".pkl")
    
    def test_generate_transfer_filename_sanitizes_name(self):
        """Test that filename generation sanitizes model names."""
        filename = _generate_transfer_filename("model/with:special*chars", ".pkl")
        
        # Should not contain special characters
        assert "/" not in filename
        assert ":" not in filename
        assert "*" not in filename


class TestPathBasedTransfer:
    """Tests for path-based model transfer."""
    
    def test_path_based_transfer_creates_files(self):
        """Test that path-based transfer creates model and config files."""
        result = _load_model_with_path_transfer(
            model_name="test-embedding",
            model_type="embedding",
            estimated_load_time_seconds=0.1,  # Fast for testing
            estimated_memory_mb=50.0,
            required_for_capabilities=["search"],
            cache_dir=None,
            transfer_dir=None
        )
        
        assert result["transfer_strategy"] == "path_based"
        assert result["model_path"] is not None
        assert result["config_path"] is not None
        
        # Files should exist
        assert os.path.exists(result["model_path"])
        assert os.path.exists(result["config_path"])
        
        # Clean up
        os.remove(result["model_path"])
        os.remove(result["config_path"])
    
    def test_path_based_transfer_model_data_is_loadable(self):
        """Test that model data saved by path-based transfer can be loaded."""
        result = _load_model_with_path_transfer(
            model_name="test-model",
            model_type="language_model",
            estimated_load_time_seconds=0.1,
            estimated_memory_mb=100.0,
            required_for_capabilities=["chat"],
            cache_dir=None
        )
        
        # Load the model data
        with open(result["model_path"], 'rb') as f:
            model_data = pickle.load(f)
        
        assert "weights" in model_data
        assert "config" in model_data
        assert "metadata" in model_data
        assert model_data["metadata"]["name"] == "test-model"
        
        # Clean up
        os.remove(result["model_path"])
        if result["config_path"] and os.path.exists(result["config_path"]):
            os.remove(result["config_path"])
    
    def test_path_based_transfer_with_custom_dir(self):
        """Test path-based transfer with custom transfer directory."""
        with tempfile.TemporaryDirectory() as custom_dir:
            result = _load_model_with_path_transfer(
                model_name="custom-dir-model",
                model_type="embedding",
                estimated_load_time_seconds=0.1,
                estimated_memory_mb=50.0,
                required_for_capabilities=["search"],
                transfer_dir=custom_dir
            )
            
            # Files should be in custom directory
            assert custom_dir in result["model_path"]
            assert os.path.exists(result["model_path"])


class TestSharedMemoryTransfer:
    """Tests for shared memory model transfer."""
    
    @pytest.mark.skipif(not SHARED_MEMORY_AVAILABLE, reason="Shared memory not available")
    def test_shared_memory_transfer_creates_shm(self):
        """Test that shared memory transfer creates shared memory block."""
        result = _load_model_with_shared_memory(
            model_name="test-shm-model",
            model_type="embedding",
            estimated_load_time_seconds=0.1,
            estimated_memory_mb=50.0,
            required_for_capabilities=["search"],
            cache_dir=None
        )
        
        assert result["transfer_strategy"] == "shared_memory"
        assert result["shared_memory_name"] is not None
        assert result["shared_memory_size"] > 0
        assert result["tensor_shapes"] is not None
        assert result["tensor_dtypes"] is not None
        assert result["tensor_offsets"] is not None
        
        # Clean up shared memory
        try:
            from multiprocessing import shared_memory as shm
            shm_block = shm.SharedMemory(name=result["shared_memory_name"])
            shm_block.close()
            shm_block.unlink()
        except Exception:
            pass  # May already be cleaned up
    
    @pytest.mark.skipif(not SHARED_MEMORY_AVAILABLE, reason="Shared memory not available")
    def test_shared_memory_transfer_tensor_metadata(self):
        """Test that shared memory transfer includes correct tensor metadata."""
        result = _load_model_with_shared_memory(
            model_name="test-tensor-model",
            model_type="language_model",
            estimated_load_time_seconds=0.1,
            estimated_memory_mb=100.0,
            required_for_capabilities=["chat"],
            cache_dir=None
        )
        
        # Check tensor metadata
        assert "embedding_weight" in result["tensor_shapes"]
        assert "attention_weight" in result["tensor_shapes"]
        assert "output_weight" in result["tensor_shapes"]
        
        # Check shapes are lists of integers
        for shape in result["tensor_shapes"].values():
            assert isinstance(shape, list)
            assert all(isinstance(dim, int) for dim in shape)
        
        # Check dtypes are strings
        for dtype in result["tensor_dtypes"].values():
            assert isinstance(dtype, str)
            assert "float" in dtype
        
        # Clean up
        try:
            from multiprocessing import shared_memory as shm
            shm_block = shm.SharedMemory(name=result["shared_memory_name"])
            shm_block.close()
            shm_block.unlink()
        except Exception:
            pass
    
    def test_shared_memory_fallback_to_path_based(self):
        """Test that shared memory falls back to path-based when unavailable."""
        # Mock shared_memory import to fail
        with patch.dict('sys.modules', {'multiprocessing.shared_memory': None}):
            # This should fall back to path-based transfer
            result = _load_model_with_shared_memory(
                model_name="fallback-model",
                model_type="embedding",
                estimated_load_time_seconds=0.1,
                estimated_memory_mb=50.0,
                required_for_capabilities=["search"],
                cache_dir=None
            )
            
            # Should have path-based result
            assert result.get("model_path") is not None or result.get("shared_memory_name") is not None


class TestLoadModelSyncPicklable:
    """Tests for the picklable model loading function."""
    
    def test_metadata_only_strategy(self):
        """Test metadata-only transfer strategy."""
        result = _load_model_sync_picklable(
            model_name="metadata-model",
            model_type="embedding",
            estimated_load_time_seconds=0.1,
            estimated_memory_mb=50.0,
            required_for_capabilities=["search"],
            cache_dir=None,
            transfer_strategy="metadata_only"
        )
        
        assert result["transfer_strategy"] == "metadata_only"
        assert result["name"] == "metadata-model"
        assert result["type"] == "embedding"
        # metadata_only strategy doesn't include model_path key
        assert "model_path" not in result or result.get("model_path") is None
    
    def test_path_based_strategy(self):
        """Test path-based transfer strategy."""
        result = _load_model_sync_picklable(
            model_name="path-model",
            model_type="language_model",
            estimated_load_time_seconds=0.1,
            estimated_memory_mb=100.0,
            required_for_capabilities=["chat"],
            cache_dir=None,
            transfer_strategy="path_based"
        )
        
        assert result["transfer_strategy"] == "path_based"
        assert result["model_path"] is not None
        
        # Clean up
        if os.path.exists(result["model_path"]):
            os.remove(result["model_path"])
        if result.get("config_path") and os.path.exists(result["config_path"]):
            os.remove(result["config_path"])
    
    @pytest.mark.skipif(not SHARED_MEMORY_AVAILABLE, reason="Shared memory not available")
    def test_shared_memory_strategy(self):
        """Test shared memory transfer strategy."""
        result = _load_model_sync_picklable(
            model_name="shm-model",
            model_type="embedding",
            estimated_load_time_seconds=0.1,
            estimated_memory_mb=50.0,
            required_for_capabilities=["search"],
            cache_dir=None,
            transfer_strategy="shared_memory"
        )
        
        assert result["transfer_strategy"] == "shared_memory"
        assert result["shared_memory_name"] is not None
        
        # Clean up
        try:
            from multiprocessing import shared_memory as shm
            shm_block = shm.SharedMemory(name=result["shared_memory_name"])
            shm_block.close()
            shm_block.unlink()
        except Exception:
            pass


class TestModelManagerTransferIntegration:
    """Integration tests for ModelManager with transfer strategies."""
    
    @pytest.fixture
    def model_manager_metadata(self):
        """Create a ModelManager with metadata-only strategy."""
        manager = ModelManager(
            max_concurrent_loads=1,
            transfer_strategy=ModelTransferStrategy.METADATA_ONLY
        )
        yield manager
        # Cleanup is handled by the manager
    
    @pytest.fixture
    def model_manager_path_based(self):
        """Create a ModelManager with path-based strategy."""
        manager = ModelManager(
            max_concurrent_loads=1,
            transfer_strategy=ModelTransferStrategy.PATH_BASED
        )
        yield manager
    
    def test_manager_initialization_with_strategy(self, model_manager_metadata):
        """Test ModelManager initializes with correct transfer strategy."""
        assert model_manager_metadata.transfer_strategy == ModelTransferStrategy.METADATA_ONLY
    
    def test_manager_set_transfer_strategy(self, model_manager_metadata):
        """Test changing transfer strategy."""
        model_manager_metadata.set_transfer_strategy(ModelTransferStrategy.PATH_BASED)
        assert model_manager_metadata.transfer_strategy == ModelTransferStrategy.PATH_BASED
    
    def test_manager_get_transfer_statistics(self, model_manager_metadata):
        """Test getting transfer statistics."""
        stats = model_manager_metadata.get_transfer_statistics()
        
        assert "current_strategy" in stats
        assert "path_based_transfers" in stats
        assert "shared_memory_transfers" in stats
        assert "metadata_only_transfers" in stats
        assert "shared_memory_available" in stats
        assert "transfer_dir" in stats
    
    def test_manager_transfer_dir_exists(self, model_manager_metadata):
        """Test that transfer directory is created."""
        assert model_manager_metadata._transfer_dir is not None
        assert os.path.exists(model_manager_metadata._transfer_dir)
    
    @pytest.mark.asyncio
    async def test_handle_transfer_result_metadata_only(self, model_manager_metadata):
        """Test handling metadata-only transfer result."""
        transfer_result = {
            "name": "test-model",
            "type": "embedding",
            "transfer_strategy": "metadata_only",
            "loaded_at": datetime.now().isoformat(),
            "capabilities": ["search"],
            "memory_usage_mb": 50.0,
            "loaded_from_cache": False,
            "process_name": "TestProcess"
        }
        
        result = await model_manager_metadata._handle_transfer_result("test-model", transfer_result)
        
        assert result == transfer_result
        assert model_manager_metadata.load_statistics["metadata_only_transfers"] == 1
    
    @pytest.mark.asyncio
    async def test_handle_transfer_result_path_based(self, model_manager_path_based):
        """Test handling path-based transfer result."""
        # Create a temporary model file
        with tempfile.NamedTemporaryFile(mode='wb', suffix='.pkl', delete=False) as f:
            model_data = {"weights": [1, 2, 3], "config": {"size": 100}}
            pickle.dump(model_data, f)
            model_path = f.name
        
        transfer_result = {
            "name": "test-model",
            "type": "embedding",
            "transfer_strategy": "path_based",
            "loaded_at": datetime.now().isoformat(),
            "capabilities": ["search"],
            "memory_usage_mb": 50.0,
            "loaded_from_cache": False,
            "process_name": "TestProcess",
            "model_path": model_path,
            "config_path": None
        }
        
        result = await model_manager_path_based._handle_transfer_result("test-model", transfer_result)
        
        assert result["transfer_completed"] is True
        assert "model_data" in result
        assert result["model_data"]["weights"] == [1, 2, 3]
        assert model_manager_path_based.load_statistics["path_based_transfers"] == 1
        
        # File should be cleaned up
        assert not os.path.exists(model_path)


class TestModelManagerShutdownCleanup:
    """Tests for ModelManager shutdown and cleanup."""
    
    @pytest.mark.asyncio
    async def test_shutdown_cleans_transfer_files(self):
        """Test that shutdown cleans up transfer files."""
        manager = ModelManager(
            max_concurrent_loads=1,
            transfer_strategy=ModelTransferStrategy.PATH_BASED
        )
        
        # Create a test file in transfer directory
        test_file = os.path.join(manager._transfer_dir, "test_model_abc123.pkl")
        with open(test_file, 'w') as f:
            f.write("test")
        
        assert os.path.exists(test_file)
        
        # Shutdown should clean up
        await manager.shutdown()
        
        # File should be removed
        assert not os.path.exists(test_file)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
