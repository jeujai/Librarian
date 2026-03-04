"""
Model Manager for Progressive Loading

This module implements a model manager that handles progressive loading of ML models
with priority classification, availability checking, and graceful degradation.

Key Features:
- Model priority classification (essential, standard, advanced)
- Background model loading with progress tracking
- Model availability checking before processing requests
- Graceful degradation for unavailable models
- Integration with startup phase manager
- Shared memory and path-based model transfer for ProcessPoolExecutor
"""

import asyncio
import hashlib
import logging
import multiprocessing
import os
import pickle
import tempfile
import threading
import time
from concurrent.futures import BrokenExecutor, ProcessPoolExecutor, ThreadPoolExecutor
from concurrent.futures.process import BrokenProcessPool
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Union

# Import shared_memory for Python 3.8+
try:
    from multiprocessing import shared_memory
    SHARED_MEMORY_AVAILABLE = True
except ImportError:
    SHARED_MEMORY_AVAILABLE = False

from ..cache.model_cache import ModelCache, get_model_cache
from ..utils.memory_manager import MemoryManager, get_memory_manager

logger = logging.getLogger(__name__)


class ModelTransferStrategy(Enum):
    """Strategy for transferring model objects from subprocess to main process."""
    METADATA_ONLY = "metadata_only"      # Return only metadata (current behavior)
    PATH_BASED = "path_based"            # Save to file, return path for main process to load
    SHARED_MEMORY = "shared_memory"      # Use shared memory for large tensors
    HYBRID = "hybrid"                    # Use shared memory for weights, path for config


@dataclass
class ModelTransferResult:
    """Result of model transfer from subprocess to main process.
    
    This dataclass encapsulates all information needed to reconstruct
    a model object in the main process after loading in a subprocess.
    All fields are primitive types for picklability.
    """
    model_name: str
    transfer_strategy: str  # String value of ModelTransferStrategy
    success: bool
    
    # Metadata about the loaded model
    model_type: str
    loaded_at: str  # ISO format datetime string
    capabilities: List[str]
    memory_usage_mb: float
    loaded_from_cache: bool
    process_name: str
    
    # Path-based transfer fields
    model_path: Optional[str] = None  # Path to saved model file
    config_path: Optional[str] = None  # Path to saved config file
    
    # Shared memory transfer fields
    shared_memory_name: Optional[str] = None  # Name of shared memory block
    shared_memory_size: Optional[int] = None  # Size of shared memory in bytes
    tensor_shapes: Optional[Dict[str, List[int]]] = None  # Shapes of tensors in shared memory
    tensor_dtypes: Optional[Dict[str, str]] = None  # Data types of tensors
    tensor_offsets: Optional[Dict[str, int]] = None  # Byte offsets in shared memory
    
    # Error information
    error_message: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for backward compatibility."""
        return {
            "name": self.model_name,
            "type": self.model_type,
            "loaded_at": self.loaded_at,
            "capabilities": self.capabilities,
            "memory_usage_mb": self.memory_usage_mb,
            "loaded_from_cache": self.loaded_from_cache,
            "loaded_in_process": True,
            "process_name": self.process_name,
            "transfer_strategy": self.transfer_strategy,
            "model_path": self.model_path,
            "config_path": self.config_path,
            "shared_memory_name": self.shared_memory_name,
            "shared_memory_size": self.shared_memory_size,
            "tensor_shapes": self.tensor_shapes,
            "tensor_dtypes": self.tensor_dtypes,
            "tensor_offsets": self.tensor_offsets,
            "error_message": self.error_message
        }


def _load_model_in_process(
    model_name: str,
    model_type: str,
    estimated_load_time_seconds: float,
    estimated_memory_mb: float,
    required_for_capabilities: List[str]
) -> Dict[str, Any]:
    """
    Check model availability (models are served by model-server container).
    
    This function is defined at module level (not as a method) so it can be pickled
    and sent to ProcessPoolExecutor workers. Since models are now served by the
    model-server container, this function returns metadata indicating the model
    should be accessed via the model server API.
    
    Args:
        model_name: Name of the model to check
        model_type: Type of the model (embedding, language_model, etc.)
        estimated_load_time_seconds: Expected loading time (for metadata)
        estimated_memory_mb: Expected memory usage (for metadata)
        required_for_capabilities: List of capabilities this model provides
    
    Returns:
        Dict containing model information and availability status
    """
    import time
    from datetime import datetime

    # Configure logging for the subprocess
    logging.basicConfig(level=logging.INFO)
    subprocess_logger = logging.getLogger(__name__)
    
    process_name = multiprocessing.current_process().name
    subprocess_logger.info(f"[Process {process_name}] Checking {model_type} model: {model_name}")
    
    load_start = time.time()
    
    # Models are served by model-server container
    # Return metadata indicating model should be accessed via model server
    if model_type == "embedding" or model_name in ["text-embedding-small", "search-index"]:
        subprocess_logger.info(f"[Process {process_name}] Embedding model {model_name} available via model-server")
        actual_model_loaded = True
    elif "chat" in model_name.lower():
        # Chat models use external APIs
        subprocess_logger.info(f"[Process {process_name}] Chat model ready (uses external API)")
        actual_model_loaded = True
    elif "document" in model_name.lower():
        # Document processing via model-server NLP endpoint
        subprocess_logger.info(f"[Process {process_name}] Document processor available via model-server")
        actual_model_loaded = True
    else:
        # For other models, mark as ready (placeholder)
        subprocess_logger.info(f"[Process {process_name}] Model {model_name} marked as ready")
        actual_model_loaded = True
    
    load_duration = time.time() - load_start
    
    # Return a model object representation
    model_object = {
        "name": model_name,
        "type": model_type,
        "loaded_at": datetime.now().isoformat(),
        "capabilities": required_for_capabilities,
        "memory_usage_mb": estimated_memory_mb,
        "loaded_from_cache": False,
        "loaded_in_process": True,
        "process_name": process_name,
        "load_duration_seconds": load_duration,
        "actual_model_loaded": actual_model_loaded,
        "source": "model-server"
    }
    
    subprocess_logger.info(f"[Process {process_name}] Model {model_name} ready in {load_duration:.2f}s")
    
    return model_object


def _get_model_transfer_dir() -> str:
    """Get the directory for model transfer files.
    
    Returns a directory path that can be used for path-based model transfer.
    Creates the directory if it doesn't exist.
    """
    transfer_dir = os.path.join(tempfile.gettempdir(), "multimodal_librarian_model_transfer")
    os.makedirs(transfer_dir, exist_ok=True)
    return transfer_dir


def _generate_transfer_filename(model_name: str, suffix: str = ".pkl") -> str:
    """Generate a unique filename for model transfer.
    
    Args:
        model_name: Name of the model
        suffix: File suffix (e.g., .pkl, .pt, .json)
    
    Returns:
        Unique filename for the model transfer file
    """
    # Create a unique identifier using model name, process ID, and timestamp
    unique_id = hashlib.md5(
        f"{model_name}_{os.getpid()}_{time.time()}".encode()
    ).hexdigest()[:12]
    
    # Sanitize model name for filename
    safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in model_name)
    
    return f"{safe_name}_{unique_id}{suffix}"


def _load_model_with_path_transfer(
    model_name: str,
    model_type: str,
    estimated_load_time_seconds: float,
    estimated_memory_mb: float,
    required_for_capabilities: List[str],
    cache_dir: Optional[str] = None,
    transfer_dir: Optional[str] = None
) -> Dict[str, Any]:
    """
    Check model availability (models are served by model-server container).
    
    This function implements path-based model transfer metadata. Since models
    are now served by the model-server container, this returns metadata
    indicating the model should be accessed via the model server API.
    
    Args:
        model_name: Name of the model to check
        model_type: Type of the model (embedding, language_model, etc.)
        estimated_load_time_seconds: Expected loading time for metadata
        estimated_memory_mb: Expected memory usage
        required_for_capabilities: List of capabilities this model provides
        cache_dir: Optional path to model cache directory (unused)
        transfer_dir: Directory for saving transfer files (unused)
    
    Returns:
        Dict containing model metadata for main process
    """
    import time
    from datetime import datetime

    # Configure logging for the subprocess
    logging.basicConfig(level=logging.INFO)
    subprocess_logger = logging.getLogger(__name__)
    
    process_name = multiprocessing.current_process().name
    subprocess_logger.info(f"[{process_name}] Checking {model_type} model: {model_name}")
    
    load_start = time.time()
    
    # Models are served by model-server container
    # Return metadata indicating model should be accessed via model server
    model_data = {
        "metadata": {
            "name": model_name,
            "type": model_type,
            "version": "1.0.0",
            "source": "model-server"
        }
    }
    
    load_duration = time.time() - load_start
    subprocess_logger.info(f"[{process_name}] Model {model_name} available via model-server")
    
    # Return transfer result with metadata
    return {
        "name": model_name,
        "type": model_type,
        "loaded_at": datetime.now().isoformat(),
        "capabilities": list(required_for_capabilities),
        "memory_usage_mb": float(estimated_memory_mb),
        "loaded_from_cache": False,
        "loaded_in_process": True,
        "process_name": process_name,
        "transfer_strategy": ModelTransferStrategy.PATH_BASED.value,
        "model_path": None,  # No local path - model is in model-server
        "config_path": None,
        "source": "model-server"
    }


def _load_model_with_shared_memory(
    model_name: str,
    model_type: str,
    estimated_load_time_seconds: float,
    estimated_memory_mb: float,
    required_for_capabilities: List[str],
    cache_dir: Optional[str] = None
) -> Dict[str, Any]:
    """
    Check model availability (models are served by model-server container).
    
    This function implements shared memory model transfer metadata. Since models
    are now served by the model-server container, this returns metadata
    indicating the model should be accessed via the model server API.
    
    Args:
        model_name: Name of the model to check
        model_type: Type of the model (embedding, language_model, etc.)
        estimated_load_time_seconds: Expected loading time for metadata
        estimated_memory_mb: Expected memory usage
        required_for_capabilities: List of capabilities this model provides
        cache_dir: Optional path to model cache directory (unused)
    
    Returns:
        Dict containing model metadata for main process
    """
    import time
    from datetime import datetime

    # Configure logging for the subprocess
    logging.basicConfig(level=logging.INFO)
    subprocess_logger = logging.getLogger(__name__)
    
    process_name = multiprocessing.current_process().name
    subprocess_logger.info(f"[{process_name}] Checking {model_type} model: {model_name}")
    
    load_start = time.time()
    
    # Models are served by model-server container
    # Return metadata indicating model should be accessed via model server
    load_duration = time.time() - load_start
    subprocess_logger.info(f"[{process_name}] Model {model_name} available via model-server")
    
    # Return transfer result with metadata (no shared memory needed)
    return {
        "name": model_name,
        "type": model_type,
        "loaded_at": datetime.now().isoformat(),
        "capabilities": list(required_for_capabilities),
        "memory_usage_mb": float(estimated_memory_mb),
        "loaded_from_cache": False,
        "loaded_in_process": True,
        "process_name": process_name,
        "transfer_strategy": ModelTransferStrategy.SHARED_MEMORY.value,
        "shared_memory_name": None,  # No shared memory - model is in model-server
        "shared_memory_size": 0,
        "tensor_shapes": {},
        "tensor_dtypes": {},
        "tensor_offsets": {},
        "source": "model-server"
    }


def _load_model_sync_picklable(
    model_name: str,
    model_type: str,
    estimated_load_time_seconds: float,
    estimated_memory_mb: float,
    required_for_capabilities: List[str],
    cache_dir: Optional[str] = None,
    transfer_strategy: str = "metadata_only"
) -> Dict[str, Any]:
    """
    Check model availability synchronously in a picklable way.
    
    This is a module-level function (not a method) that can be pickled and sent
    to ProcessPoolExecutor workers. Since models are now served by the model-server
    container, this function returns metadata indicating the model should be
    accessed via the model server API.
    
    This function is designed to be process-safe:
    - No closures or lambdas
    - No instance variables (self.*)
    - All arguments are primitive/picklable types
    - Returns only picklable data (dict with primitives)
    
    Transfer Strategies:
    - metadata_only: Return only metadata (lightweight)
    - path_based: Return metadata with path info
    - shared_memory: Return metadata with shared memory info
    - hybrid: Return metadata with hybrid info
    
    Args:
        model_name: Name of the model to check
        model_type: Type of the model (embedding, language_model, etc.)
        estimated_load_time_seconds: Expected loading time for metadata
        estimated_memory_mb: Expected memory usage
        required_for_capabilities: List of capabilities this model provides
        cache_dir: Optional path to model cache directory (unused)
        transfer_strategy: Strategy for transfer metadata
    
    Returns:
        Dict containing model information and availability status
    """
    import time
    from datetime import datetime

    # Configure logging for the subprocess/thread
    logging.basicConfig(level=logging.INFO)
    sync_logger = logging.getLogger(__name__)
    
    process_name = multiprocessing.current_process().name
    sync_logger.info(f"[{process_name}] Checking {model_type} model: {model_name} (strategy: {transfer_strategy})")
    
    # Route to appropriate transfer strategy
    if transfer_strategy == ModelTransferStrategy.PATH_BASED.value:
        return _load_model_with_path_transfer(
            model_name=model_name,
            model_type=model_type,
            estimated_load_time_seconds=estimated_load_time_seconds,
            estimated_memory_mb=estimated_memory_mb,
            required_for_capabilities=required_for_capabilities,
            cache_dir=cache_dir
        )
    
    elif transfer_strategy == ModelTransferStrategy.SHARED_MEMORY.value:
        return _load_model_with_shared_memory(
            model_name=model_name,
            model_type=model_type,
            estimated_load_time_seconds=estimated_load_time_seconds,
            estimated_memory_mb=estimated_memory_mb,
            required_for_capabilities=required_for_capabilities,
            cache_dir=cache_dir
        )
    
    elif transfer_strategy == ModelTransferStrategy.HYBRID.value:
        # Hybrid: Use shared memory metadata
        return _load_model_with_shared_memory(
            model_name=model_name,
            model_type=model_type,
            estimated_load_time_seconds=estimated_load_time_seconds,
            estimated_memory_mb=estimated_memory_mb,
            required_for_capabilities=required_for_capabilities,
            cache_dir=cache_dir
        )
    
    # Default: metadata_only strategy - models are served by model-server
    load_start = time.time()
    
    # Models are served by model-server container
    if model_type == "embedding" or model_name in ["text-embedding-small", "search-index"]:
        sync_logger.info(f"[{process_name}] Embedding model {model_name} available via model-server")
    elif "chat" in model_name.lower():
        sync_logger.info(f"[{process_name}] Chat model {model_name} ready (uses external API)")
    elif "document" in model_name.lower():
        sync_logger.info(f"[{process_name}] Document processor {model_name} available via model-server")
    else:
        sync_logger.info(f"[{process_name}] Model {model_name} marked as ready")
    
    load_duration = time.time() - load_start
    
    # Return a model object representation
    model_object = {
        "name": model_name,
        "type": model_type,
        "loaded_at": datetime.now().isoformat(),
        "capabilities": list(required_for_capabilities),
        "memory_usage_mb": float(estimated_memory_mb),
        "loaded_from_cache": False,
        "cache_path": None,
        "loaded_in_process": True,
        "process_name": process_name,
        "transfer_strategy": ModelTransferStrategy.METADATA_ONLY.value,
        "load_duration_seconds": load_duration,
        "actual_model_loaded": True,
        "source": "model-server"
    }
    
    sync_logger.info(f"[{process_name}] Model {model_name} ready in {load_duration:.2f}s")
    
    return model_object


# Type alias for model config data that can be pickled
# This is used to extract picklable data from ModelConfig objects
ModelConfigData = Dict[str, Any]


def extract_picklable_config(config: 'ModelConfig') -> ModelConfigData:
    """
    Extract picklable data from a ModelConfig object.
    
    This function converts a ModelConfig dataclass (which may contain
    non-picklable elements) into a plain dictionary with only primitive types.
    
    Args:
        config: ModelConfig object to extract data from
    
    Returns:
        Dictionary with only picklable primitive types
    """
    return {
        "name": str(config.name),
        "model_type": str(config.model_type),
        "estimated_load_time_seconds": float(config.estimated_load_time_seconds),
        "estimated_memory_mb": float(config.estimated_memory_mb),
        "required_for_capabilities": list(config.required_for_capabilities),
        "priority": str(config.priority.value),
        "fallback_models": list(config.fallback_models),
        "max_retries": int(config.max_retries),
        "timeout_seconds": float(config.timeout_seconds),
        "lazy_load": bool(config.lazy_load),
        "preload": bool(config.preload),
        "model_path": str(config.model_path) if config.model_path else None,
        "dependencies": list(config.dependencies)
    }


class ModelPriority(Enum):
    """Model priority levels for progressive loading."""
    ESSENTIAL = "essential"    # Must load first - basic functionality
    STANDARD = "standard"      # Load second - enhanced functionality  
    ADVANCED = "advanced"      # Load last - advanced features


class ModelStatus(Enum):
    """Model loading status."""
    PENDING = "pending"        # Not started loading
    LOADING = "loading"        # Currently loading
    LOADED = "loaded"          # Successfully loaded and ready
    FAILED = "failed"          # Failed to load
    UNLOADING = "unloading"    # Being unloaded to free memory
    UNLOADED = "unloaded"      # Unloaded from memory


@dataclass
class ModelConfig:
    """Configuration for a model."""
    name: str
    priority: ModelPriority
    estimated_load_time_seconds: float
    estimated_memory_mb: float
    required_for_capabilities: List[str]
    fallback_models: List[str] = field(default_factory=list)
    max_retries: int = 3
    timeout_seconds: float = 300.0
    lazy_load: bool = True
    preload: bool = False
    model_path: Optional[str] = None
    model_type: str = "generic"
    dependencies: List[str] = field(default_factory=list)


@dataclass
class ModelInstance:
    """Represents a loaded model instance."""
    config: ModelConfig
    status: ModelStatus
    model_object: Optional[Any] = None
    load_start_time: Optional[datetime] = None
    load_end_time: Optional[datetime] = None
    last_used: Optional[datetime] = None
    error_message: Optional[str] = None
    retry_count: int = 0
    memory_usage_mb: Optional[float] = None
    load_duration_seconds: Optional[float] = None


class SubprocessError(Exception):
    """Exception raised when a subprocess fails during model loading.
    
    This exception wraps various subprocess-related failures including:
    - BrokenProcessPool: Worker process died unexpectedly
    - PicklingError: Arguments couldn't be serialized for subprocess
    - TimeoutError: Subprocess took too long to complete
    - OSError: System-level errors (e.g., out of memory, resource limits)
    - RuntimeError: General subprocess runtime failures
    
    Attributes:
        model_name: Name of the model that failed to load
        original_error: The original exception that caused the failure
        error_type: Classification of the error type
        is_recoverable: Whether the error might be recoverable with retry
        suggested_action: Recommended action to resolve the error
    """
    
    def __init__(
        self, 
        model_name: str, 
        original_error: Exception,
        error_type: str = "unknown",
        is_recoverable: bool = True,
        suggested_action: str = "retry"
    ):
        self.model_name = model_name
        self.original_error = original_error
        self.error_type = error_type
        self.is_recoverable = is_recoverable
        self.suggested_action = suggested_action
        
        message = (
            f"Subprocess failed while loading model '{model_name}': "
            f"{error_type} - {str(original_error)}"
        )
        super().__init__(message)
    
    @classmethod
    def from_exception(cls, model_name: str, error: Exception) -> 'SubprocessError':
        """Create a SubprocessError from a caught exception.
        
        This factory method classifies the error and determines appropriate
        recovery strategies based on the exception type.
        
        Args:
            model_name: Name of the model that failed to load
            error: The original exception
            
        Returns:
            SubprocessError with appropriate classification
        """
        # Classify the error type and determine recovery strategy
        if isinstance(error, BrokenProcessPool):
            return cls(
                model_name=model_name,
                original_error=error,
                error_type="broken_process_pool",
                is_recoverable=True,
                suggested_action="recreate_pool_and_retry"
            )
        elif isinstance(error, BrokenExecutor):
            return cls(
                model_name=model_name,
                original_error=error,
                error_type="broken_executor",
                is_recoverable=True,
                suggested_action="recreate_pool_and_retry"
            )
        elif isinstance(error, (pickle.PicklingError, TypeError)) and "pickle" in str(error).lower():
            return cls(
                model_name=model_name,
                original_error=error,
                error_type="pickling_error",
                is_recoverable=False,
                suggested_action="use_thread_pool_fallback"
            )
        elif isinstance(error, asyncio.TimeoutError):
            return cls(
                model_name=model_name,
                original_error=error,
                error_type="timeout",
                is_recoverable=True,
                suggested_action="retry_with_longer_timeout"
            )
        elif isinstance(error, OSError):
            error_str = str(error).lower()
            if "memory" in error_str or "resource" in error_str:
                return cls(
                    model_name=model_name,
                    original_error=error,
                    error_type="resource_exhaustion",
                    is_recoverable=True,
                    suggested_action="wait_and_retry"
                )
            else:
                return cls(
                    model_name=model_name,
                    original_error=error,
                    error_type="os_error",
                    is_recoverable=True,
                    suggested_action="retry"
                )
        elif isinstance(error, RuntimeError):
            error_str = str(error).lower()
            if "cuda" in error_str or "gpu" in error_str:
                return cls(
                    model_name=model_name,
                    original_error=error,
                    error_type="cuda_error",
                    is_recoverable=True,
                    suggested_action="retry_on_cpu"
                )
            else:
                return cls(
                    model_name=model_name,
                    original_error=error,
                    error_type="runtime_error",
                    is_recoverable=True,
                    suggested_action="retry"
                )
        elif isinstance(error, MemoryError):
            return cls(
                model_name=model_name,
                original_error=error,
                error_type="memory_error",
                is_recoverable=True,
                suggested_action="unload_models_and_retry"
            )
        else:
            return cls(
                model_name=model_name,
                original_error=error,
                error_type="unknown",
                is_recoverable=True,
                suggested_action="retry"
            )


class ModelManager:
    """
    Manages progressive loading and lifecycle of ML models.
    
    This class handles model loading with priority-based scheduling,
    availability checking, and graceful degradation when models are unavailable.
    
    Supports multiple model transfer strategies for ProcessPoolExecutor:
    - METADATA_ONLY: Return only metadata (lightweight, for simulated models)
    - PATH_BASED: Save model to file, return path for main process to load
    - SHARED_MEMORY: Use shared memory for large tensor data
    - HYBRID: Use shared memory for weights, path for config
    """
    
    def __init__(self, max_concurrent_loads: int = 2, 
                 transfer_strategy: ModelTransferStrategy = ModelTransferStrategy.METADATA_ONLY):
        """Initialize the model manager.
        
        Args:
            max_concurrent_loads: Maximum number of models to load concurrently
            transfer_strategy: Strategy for transferring models from subprocess to main process
        """
        self.max_concurrent_loads = max_concurrent_loads
        self.transfer_strategy = transfer_strategy
        self.models: Dict[str, ModelInstance] = {}
        self.model_configs: Dict[str, ModelConfig] = {}
        self.loading_queue: asyncio.Queue = asyncio.Queue()
        self.loading_tasks: Dict[str, asyncio.Task] = {}
        self.availability_callbacks: Dict[str, List[Callable]] = {}
        
        # Model cache integration
        self.model_cache: Optional[ModelCache] = None
        
        # Memory manager integration
        self.memory_manager: Optional[MemoryManager] = None
        
        # Transfer directory for path-based model transfer
        self._transfer_dir = _get_model_transfer_dir()
        
        # Shared memory tracking for cleanup
        self._shared_memory_blocks: Dict[str, Any] = {}  # model_name -> SharedMemory object
        
        # Process pool for CPU-intensive model loading
        # Using ProcessPoolExecutor instead of ThreadPoolExecutor to avoid GIL blocking
        # during model initialization. Each process has its own GIL, so health checks
        # can respond while models load in separate processes.
        # 
        # IMPORTANT: Using 'spawn' context for PyTorch compatibility.
        # PyTorch requires 'spawn' (not 'fork') to avoid issues with CUDA and
        # multiprocessing. The 'spawn' context creates fresh Python interpreters.
        try:
            mp_context = multiprocessing.get_context('spawn')
            self.process_pool = ProcessPoolExecutor(
                max_workers=max_concurrent_loads,
                mp_context=mp_context
            )
            self._use_process_pool = True
            logger.info(f"ProcessPoolExecutor initialized with 'spawn' context ({max_concurrent_loads} workers)")
        except Exception as e:
            # Fallback to ThreadPoolExecutor if ProcessPoolExecutor fails
            # This can happen in some environments where multiprocessing is restricted
            logger.warning(f"Failed to create ProcessPoolExecutor: {e}. Falling back to ThreadPoolExecutor.")
            self.process_pool = ThreadPoolExecutor(max_workers=max_concurrent_loads)
            self._use_process_pool = False
        
        # Keep a thread pool for lightweight async operations that don't need process isolation
        self.thread_pool = ThreadPoolExecutor(max_workers=max_concurrent_loads)
        
        # Optimized loader integration
        self._optimized_loader: Optional[Any] = None  # Will be imported dynamically to avoid circular imports
        self._use_optimized_loading = True
        
        # Loading state
        self._loading_lock = asyncio.Lock()
        self._shutdown_event = asyncio.Event()
        self._background_loader_task: Optional[asyncio.Task] = None
        
        # Statistics
        self.load_statistics = {
            "total_loads": 0,
            "successful_loads": 0,
            "failed_loads": 0,
            "total_load_time": 0.0,
            "average_load_time": 0.0,
            "cache_hits": 0,
            "cache_misses": 0,
            "process_pool_loads": 0,
            "thread_pool_loads": 0,
            "path_based_transfers": 0,
            "shared_memory_transfers": 0,
            "metadata_only_transfers": 0
        }
        
        logger.info(f"ModelManager initialized with transfer_strategy={transfer_strategy.value}")
        
        # Initialize default model configurations
        self._initialize_default_models()
    
    def _initialize_default_models(self) -> None:
        """Initialize default model configurations."""
        default_models = [
            # Essential models - must load first
            ModelConfig(
                name="text-embedding-small",
                priority=ModelPriority.ESSENTIAL,
                estimated_load_time_seconds=5.0,
                estimated_memory_mb=50.0,
                required_for_capabilities=["basic_search", "text_processing"],
                model_type="embedding",
                preload=True
            ),
            ModelConfig(
                name="chat-model-base",
                priority=ModelPriority.ESSENTIAL,
                estimated_load_time_seconds=15.0,
                estimated_memory_mb=200.0,
                required_for_capabilities=["basic_chat", "simple_responses"],
                model_type="language_model",
                fallback_models=["chat-model-tiny"]
            ),
            ModelConfig(
                name="search-index",
                priority=ModelPriority.ESSENTIAL,
                estimated_load_time_seconds=10.0,
                estimated_memory_mb=100.0,
                required_for_capabilities=["simple_search", "keyword_search"],
                model_type="search_index"
            ),
            
            # Standard models - enhanced functionality
            ModelConfig(
                name="chat-model-large",
                priority=ModelPriority.STANDARD,
                estimated_load_time_seconds=60.0,
                estimated_memory_mb=1000.0,
                required_for_capabilities=["advanced_chat", "complex_reasoning"],
                model_type="language_model",
                fallback_models=["chat-model-base"],
                dependencies=["text-embedding-small"]
            ),
            ModelConfig(
                name="document-processor",
                priority=ModelPriority.STANDARD,
                estimated_load_time_seconds=30.0,
                estimated_memory_mb=500.0,
                required_for_capabilities=["document_analysis", "text_extraction"],
                model_type="document_processor",
                dependencies=["text-embedding-small"]
            ),
            
            # Advanced models - specialized features
            ModelConfig(
                name="multimodal-model",
                priority=ModelPriority.ADVANCED,
                estimated_load_time_seconds=120.0,
                estimated_memory_mb=2000.0,
                required_for_capabilities=["multimodal_processing", "image_analysis"],
                model_type="multimodal",
                dependencies=["text-embedding-small", "chat-model-base"]
            ),
            ModelConfig(
                name="specialized-analyzers",
                priority=ModelPriority.ADVANCED,
                estimated_load_time_seconds=90.0,
                estimated_memory_mb=1500.0,
                required_for_capabilities=["specialized_analysis", "domain_expertise"],
                model_type="analyzer_suite",
                dependencies=["document-processor"]
            )
        ]
        
        # Register all default models
        for config in default_models:
            self.register_model(config)
    
    def register_model(self, config: ModelConfig) -> None:
        """Register a model configuration."""
        self.model_configs[config.name] = config
        self.models[config.name] = ModelInstance(
            config=config,
            status=ModelStatus.PENDING
        )
        logger.info(f"Registered model: {config.name} (priority: {config.priority.value})")
    
    async def start_progressive_loading(self) -> None:
        """Start the progressive model loading process."""
        logger.info("Starting progressive model loading")
        
        # Initialize model cache
        try:
            self.model_cache = get_model_cache()
            logger.info("Model cache integration enabled")
        except Exception as e:
            logger.warning(f"Failed to initialize model cache: {e}")
            self.model_cache = None
        
        # Initialize memory manager
        try:
            self.memory_manager = get_memory_manager()
            logger.info("Memory manager integration enabled")
        except Exception as e:
            logger.warning(f"Failed to initialize memory manager: {e}")
            self.memory_manager = None
        
        # Initialize optimized loader if available
        if self._use_optimized_loading:
            try:
                # Dynamic import to avoid circular imports
                from .loader_optimized import get_optimized_loader
                self._optimized_loader = get_optimized_loader()
                logger.info("Optimized parallel loading enabled")
            except Exception as e:
                logger.warning(f"Failed to initialize optimized loader: {e}")
                self._optimized_loader = None
                self._use_optimized_loading = False
        
        # Start background loader
        self._background_loader_task = asyncio.create_task(self._background_loader())
        
        # Queue models by priority
        await self._queue_models_by_priority()
        
        logger.info("Progressive model loading started")
    
    async def _queue_models_by_priority(self) -> None:
        """Queue models for loading based on priority.
        
        YIELD POINTS: This method contains yield points to allow health checks
        to respond during model queuing operations.
        """
        # Sort models by priority and preload flag
        models_to_load = []
        
        for config in self.model_configs.values():
            if config.preload or config.priority == ModelPriority.ESSENTIAL:
                models_to_load.append((config, 0))  # Load immediately
            elif config.priority == ModelPriority.STANDARD:
                models_to_load.append((config, 30))  # Load after 30 seconds
            else:  # ADVANCED
                models_to_load.append((config, 120))  # Load after 2 minutes
        
        # Sort by delay, then by priority
        models_to_load.sort(key=lambda x: (x[1], x[0].priority.value))
        
        # YIELD POINT: Allow event loop to process health checks before queuing
        await asyncio.sleep(0)
        
        # Queue models with delays
        for i, (config, delay) in enumerate(models_to_load):
            await asyncio.sleep(0.1)  # Small delay between queuing
            await self.loading_queue.put((config.name, delay))
            
            # YIELD POINT: Every 3 models, yield to allow health checks
            if (i + 1) % 3 == 0:
                await asyncio.sleep(0)
    
    async def _background_loader(self) -> None:
        """Background task that processes the model loading queue.
        
        YIELD POINTS: This method contains yield points to ensure health checks
        can respond during background loading operations.
        """
        try:
            while not self._shutdown_event.is_set():
                try:
                    # Get next model to load with timeout
                    model_name, delay = await asyncio.wait_for(
                        self.loading_queue.get(), timeout=1.0
                    )
                    
                    # YIELD POINT: Allow health checks before processing delay
                    await asyncio.sleep(0)
                    
                    # Wait for delay if specified
                    if delay > 0:
                        logger.info(f"Delaying load of {model_name} by {delay} seconds")
                        await asyncio.sleep(delay)
                    
                    # YIELD POINT: Allow health checks after delay
                    await asyncio.sleep(0)
                    
                    # Check if we have capacity for concurrent loading
                    active_loads = len([t for t in self.loading_tasks.values() if not t.done()])
                    if active_loads >= self.max_concurrent_loads:
                        # Wait for a slot to become available
                        await asyncio.sleep(1.0)
                        # Re-queue the model
                        await self.loading_queue.put((model_name, 0))
                        continue
                    
                    # YIELD POINT: Allow health checks before starting model load
                    await asyncio.sleep(0)
                    
                    # Start loading the model
                    if model_name not in self.loading_tasks or self.loading_tasks[model_name].done():
                        task = asyncio.create_task(self._load_model_async(model_name))
                        self.loading_tasks[model_name] = task
                        logger.info(f"Started loading model: {model_name}")
                    
                except asyncio.TimeoutError:
                    # No models in queue, continue
                    continue
                except Exception as e:
                    logger.error(f"Error in background loader: {e}")
                    await asyncio.sleep(1.0)
        
        except asyncio.CancelledError:
            logger.info("Background loader cancelled")
            raise
        except Exception as e:
            logger.error(f"Background loader error: {e}")
    
    async def _load_model_async(self, model_name: str) -> bool:
        """Load a model asynchronously.
        
        YIELD POINTS: This method contains yield points to ensure health checks
        can respond during model loading operations. The actual CPU-intensive
        loading is done in ProcessPoolExecutor to avoid GIL blocking.
        """
        if model_name not in self.models:
            logger.error(f"Unknown model: {model_name}")
            return False
        
        model_instance = self.models[model_name]
        config = model_instance.config
        
        # YIELD POINT: Allow health checks before dependency check
        await asyncio.sleep(0)
        
        # Check dependencies
        if not await self._check_dependencies(model_name):
            logger.warning(f"Dependencies not met for {model_name}, retrying later")
            # Re-queue with delay
            await asyncio.sleep(10)
            await self.loading_queue.put((model_name, 10))
            return False
        
        # YIELD POINT: Allow health checks before acquiring lock
        await asyncio.sleep(0)
        
        async with self._loading_lock:
            # Update status
            model_instance.status = ModelStatus.LOADING
            model_instance.load_start_time = datetime.now()
            model_instance.retry_count += 1
            
            logger.info(f"Loading model {model_name} (attempt {model_instance.retry_count}, strategy: {self.transfer_strategy.value})")
            
            # Log model loading start with startup logger
            try:
                from ..logging.startup_logger import log_model_loading_start
                from ..startup.phase_manager import ModelLoadingStatus
                
                model_loading_status = ModelLoadingStatus(
                    model_name=model_name,
                    priority=config.priority.value,
                    status="loading",
                    started_at=model_instance.load_start_time,
                    size_mb=config.estimated_memory_mb,
                    estimated_load_time_seconds=config.estimated_load_time_seconds
                )
                
                log_model_loading_start(model_name, model_loading_status)
            except ImportError:
                pass  # Startup logger not available
        
        try:
            # YIELD POINT: Allow health checks before starting executor operation
            await asyncio.sleep(0)
            
            # Load model in process pool to avoid blocking the event loop
            # ProcessPoolExecutor runs in separate processes with their own GIL,
            # so health checks can respond while models load.
            loop = asyncio.get_event_loop()
            
            # Extract picklable config data for subprocess transfer
            # This ensures all data passed to the executor is serializable
            picklable_config = extract_picklable_config(config)
            cache_dir = self._get_cache_dir()
            
            # YIELD POINT: Allow health checks after config extraction
            await asyncio.sleep(0)
            
            # Use process pool for CPU-intensive model loading
            # This prevents GIL contention that would block health check responses
            if self._use_process_pool:
                # Use the module-level picklable function directly
                # All arguments are primitive types that can be pickled
                # Pass the transfer strategy to determine how model is returned
                model_object = await loop.run_in_executor(
                    self.process_pool,
                    _load_model_sync_picklable,  # Module-level picklable function
                    picklable_config["name"],
                    picklable_config["model_type"],
                    picklable_config["estimated_load_time_seconds"],
                    picklable_config["estimated_memory_mb"],
                    picklable_config["required_for_capabilities"],
                    cache_dir,
                    self.transfer_strategy.value  # Pass transfer strategy
                )
                self.load_statistics["process_pool_loads"] += 1
                
                # YIELD POINT: Allow health checks after executor completes
                await asyncio.sleep(0)
                
                # Handle the transfer result based on strategy
                model_object = await self._handle_transfer_result(model_name, model_object)
                
                # Update cache statistics based on result
                if model_object.get("loaded_from_cache", False):
                    self.load_statistics["cache_hits"] += 1
                else:
                    self.load_statistics["cache_misses"] += 1
            else:
                # Fallback to thread pool if process pool is not available
                # ThreadPoolExecutor doesn't require pickling, so we can use
                # the wrapper method that handles instance-specific logic
                model_object = await loop.run_in_executor(
                    self.thread_pool,
                    self._load_model_sync,
                    config
                )
                self.load_statistics["thread_pool_loads"] += 1
                
                # YIELD POINT: Allow health checks after thread pool executor completes
                await asyncio.sleep(0)
            
            # YIELD POINT: Allow health checks before updating model instance
            await asyncio.sleep(0)
            
            # Update model instance
            async with self._loading_lock:
                model_instance.model_object = model_object
                model_instance.status = ModelStatus.LOADED
                model_instance.load_end_time = datetime.now()
                model_instance.load_duration_seconds = (
                    model_instance.load_end_time - model_instance.load_start_time
                ).total_seconds()
                model_instance.last_used = datetime.now()
                
                # Update statistics
                self.load_statistics["total_loads"] += 1
                self.load_statistics["successful_loads"] += 1
                self.load_statistics["total_load_time"] += model_instance.load_duration_seconds
                self.load_statistics["average_load_time"] = (
                    self.load_statistics["total_load_time"] / self.load_statistics["total_loads"]
                )
                
                # Log model loading completion with startup logger
                try:
                    from ..logging.startup_logger import log_model_loading_complete
                    from ..startup.phase_manager import ModelLoadingStatus
                    
                    model_loading_status = ModelLoadingStatus(
                        model_name=model_name,
                        priority=config.priority.value,
                        status="loaded",
                        started_at=model_instance.load_start_time,
                        completed_at=model_instance.load_end_time,
                        duration_seconds=model_instance.load_duration_seconds,
                        size_mb=config.estimated_memory_mb,
                        estimated_load_time_seconds=config.estimated_load_time_seconds
                    )
                    
                    log_model_loading_complete(model_name, model_loading_status)
                except ImportError:
                    pass  # Startup logger not available
            
            logger.info(f"Successfully loaded model {model_name} in {model_instance.load_duration_seconds:.2f}s")
            
            # Notify availability callbacks
            await self._notify_availability_callbacks(model_name, True)
            
            return True
            
        except (BrokenProcessPool, BrokenExecutor) as e:
            # Handle broken process pool - worker process died unexpectedly
            # This requires recreating the process pool before retrying
            subprocess_error = SubprocessError.from_exception(model_name, e)
            logger.error(
                f"Subprocess pool broken while loading {model_name}: {subprocess_error.error_type} - {e}"
            )
            
            # Attempt to recreate the process pool
            await self._handle_broken_process_pool(model_name, subprocess_error)
            
            # Update model instance with failure info
            async with self._loading_lock:
                model_instance.status = ModelStatus.FAILED
                model_instance.error_message = f"Subprocess failure ({subprocess_error.error_type}): {str(e)}"
                model_instance.load_end_time = datetime.now()
                
                # Update statistics
                self.load_statistics["total_loads"] += 1
                self.load_statistics["failed_loads"] += 1
                self.load_statistics["subprocess_failures"] = self.load_statistics.get("subprocess_failures", 0) + 1
                
                # Log model loading failure with startup logger
                try:
                    from ..logging.startup_logger import log_model_loading_complete
                    from ..startup.phase_manager import ModelLoadingStatus
                    
                    model_loading_status = ModelLoadingStatus(
                        model_name=model_name,
                        priority=config.priority.value,
                        status="failed",
                        started_at=model_instance.load_start_time,
                        completed_at=model_instance.load_end_time,
                        duration_seconds=(model_instance.load_end_time - model_instance.load_start_time).total_seconds() if model_instance.load_start_time else None,
                        error_message=f"Subprocess failure: {subprocess_error.error_type}",
                        size_mb=config.estimated_memory_mb,
                        estimated_load_time_seconds=config.estimated_load_time_seconds
                    )
                    
                    log_model_loading_complete(model_name, model_loading_status)
                except ImportError:
                    pass  # Startup logger not available
            
            # Retry with recreated pool if recoverable
            if subprocess_error.is_recoverable and model_instance.retry_count < config.max_retries:
                retry_delay = min(60, 15 * model_instance.retry_count)  # Longer delay for subprocess failures
                logger.info(f"Retrying {model_name} in {retry_delay} seconds after subprocess failure")
                await asyncio.sleep(retry_delay)
                await self.loading_queue.put((model_name, 0))
            else:
                logger.error(f"Cannot recover from subprocess failure for model {model_name}")
                await self._notify_availability_callbacks(model_name, False)
            
            return False
            
        except (pickle.PicklingError, TypeError) as e:
            # Handle pickling errors - arguments couldn't be serialized
            # Fall back to thread pool which doesn't require pickling
            if "pickle" in str(e).lower() or isinstance(e, pickle.PicklingError):
                subprocess_error = SubprocessError.from_exception(model_name, e)
                logger.warning(
                    f"Pickling error for {model_name}, falling back to thread pool: {e}"
                )
                
                # Try loading with thread pool instead
                try:
                    loop = asyncio.get_event_loop()
                    model_object = await loop.run_in_executor(
                        self.thread_pool,
                        self._load_model_sync,
                        config
                    )
                    self.load_statistics["thread_pool_loads"] += 1
                    self.load_statistics["pickling_fallbacks"] = self.load_statistics.get("pickling_fallbacks", 0) + 1
                    
                    # Update model instance with success
                    async with self._loading_lock:
                        model_instance.model_object = model_object
                        model_instance.status = ModelStatus.LOADED
                        model_instance.load_end_time = datetime.now()
                        model_instance.load_duration_seconds = (
                            model_instance.load_end_time - model_instance.load_start_time
                        ).total_seconds()
                        model_instance.last_used = datetime.now()
                        
                        self.load_statistics["total_loads"] += 1
                        self.load_statistics["successful_loads"] += 1
                        self.load_statistics["total_load_time"] += model_instance.load_duration_seconds
                        self.load_statistics["average_load_time"] = (
                            self.load_statistics["total_load_time"] / self.load_statistics["total_loads"]
                        )
                    
                    logger.info(f"Successfully loaded {model_name} via thread pool fallback")
                    await self._notify_availability_callbacks(model_name, True)
                    return True
                    
                except Exception as fallback_error:
                    logger.error(f"Thread pool fallback also failed for {model_name}: {fallback_error}")
                    # Continue to general error handling below
                    e = fallback_error
            
            # If we get here, both process pool and thread pool failed
            async with self._loading_lock:
                model_instance.status = ModelStatus.FAILED
                model_instance.error_message = f"Pickling and fallback failed: {str(e)}"
                model_instance.load_end_time = datetime.now()
                
                self.load_statistics["total_loads"] += 1
                self.load_statistics["failed_loads"] += 1
            
            logger.error(f"Failed to load model {model_name}: {e}")
            
            if model_instance.retry_count < config.max_retries:
                retry_delay = min(60, 10 * model_instance.retry_count)
                logger.info(f"Retrying {model_name} in {retry_delay} seconds")
                await asyncio.sleep(retry_delay)
                await self.loading_queue.put((model_name, 0))
            else:
                logger.error(f"Max retries exceeded for model {model_name}")
                await self._notify_availability_callbacks(model_name, False)
            
            return False
            
        except MemoryError as e:
            # Handle memory errors - try to free memory and retry
            subprocess_error = SubprocessError.from_exception(model_name, e)
            logger.error(f"Memory error while loading {model_name}: {e}")
            
            # Try to free memory by unloading non-essential models
            await self._handle_memory_error(model_name)
            
            async with self._loading_lock:
                model_instance.status = ModelStatus.FAILED
                model_instance.error_message = f"Memory error: {str(e)}"
                model_instance.load_end_time = datetime.now()
                
                self.load_statistics["total_loads"] += 1
                self.load_statistics["failed_loads"] += 1
                self.load_statistics["memory_errors"] = self.load_statistics.get("memory_errors", 0) + 1
            
            # Retry with longer delay to allow memory to be freed
            if model_instance.retry_count < config.max_retries:
                retry_delay = min(120, 30 * model_instance.retry_count)  # Longer delay for memory issues
                logger.info(f"Retrying {model_name} in {retry_delay} seconds after memory error")
                await asyncio.sleep(retry_delay)
                await self.loading_queue.put((model_name, 0))
            else:
                logger.error(f"Max retries exceeded for model {model_name} due to memory errors")
                await self._notify_availability_callbacks(model_name, False)
            
            return False
            
        except OSError as e:
            # Handle OS-level errors (resource limits, file descriptors, etc.)
            subprocess_error = SubprocessError.from_exception(model_name, e)
            logger.error(f"OS error while loading {model_name}: {subprocess_error.error_type} - {e}")
            
            async with self._loading_lock:
                model_instance.status = ModelStatus.FAILED
                model_instance.error_message = f"OS error ({subprocess_error.error_type}): {str(e)}"
                model_instance.load_end_time = datetime.now()
                
                self.load_statistics["total_loads"] += 1
                self.load_statistics["failed_loads"] += 1
                self.load_statistics["os_errors"] = self.load_statistics.get("os_errors", 0) + 1
            
            if subprocess_error.is_recoverable and model_instance.retry_count < config.max_retries:
                retry_delay = min(60, 15 * model_instance.retry_count)
                logger.info(f"Retrying {model_name} in {retry_delay} seconds after OS error")
                await asyncio.sleep(retry_delay)
                await self.loading_queue.put((model_name, 0))
            else:
                logger.error(f"Cannot recover from OS error for model {model_name}")
                await self._notify_availability_callbacks(model_name, False)
            
            return False
            
        except Exception as e:
            # Handle all other loading failures
            async with self._loading_lock:
                model_instance.status = ModelStatus.FAILED
                model_instance.error_message = str(e)
                model_instance.load_end_time = datetime.now()
                
                # Update statistics
                self.load_statistics["total_loads"] += 1
                self.load_statistics["failed_loads"] += 1
                
                # Log model loading failure with startup logger
                try:
                    from ..logging.startup_logger import log_model_loading_complete
                    from ..startup.phase_manager import ModelLoadingStatus
                    
                    model_loading_status = ModelLoadingStatus(
                        model_name=model_name,
                        priority=config.priority.value,
                        status="failed",
                        started_at=model_instance.load_start_time,
                        completed_at=model_instance.load_end_time,
                        duration_seconds=(model_instance.load_end_time - model_instance.load_start_time).total_seconds() if model_instance.load_start_time else None,
                        error_message=str(e),
                        size_mb=config.estimated_memory_mb,
                        estimated_load_time_seconds=config.estimated_load_time_seconds
                    )
                    
                    log_model_loading_complete(model_name, model_loading_status)
                except ImportError:
                    pass  # Startup logger not available
            
            logger.error(f"Failed to load model {model_name}: {e}")
            
            # Retry if we haven't exceeded max retries
            if model_instance.retry_count < config.max_retries:
                retry_delay = min(60, 10 * model_instance.retry_count)  # Exponential backoff
                logger.info(f"Retrying {model_name} in {retry_delay} seconds")
                await asyncio.sleep(retry_delay)
                await self.loading_queue.put((model_name, 0))
            else:
                logger.error(f"Max retries exceeded for model {model_name}")
                await self._notify_availability_callbacks(model_name, False)
            
            return False
    
    async def _handle_broken_process_pool(self, model_name: str, error: SubprocessError) -> None:
        """Handle a broken process pool by recreating it.
        
        When a worker process dies unexpectedly (e.g., due to segfault, OOM kill),
        the ProcessPoolExecutor becomes broken and cannot accept new tasks.
        This method recreates the pool to allow continued operation.
        
        Args:
            model_name: Name of the model that triggered the failure
            error: The SubprocessError with details about the failure
        """
        logger.warning(f"Recreating process pool after failure loading {model_name}")
        
        try:
            # Shutdown the broken pool
            if hasattr(self, 'process_pool') and self.process_pool:
                try:
                    self.process_pool.shutdown(wait=False, cancel_futures=True)
                except TypeError:
                    # Python < 3.9 doesn't support cancel_futures
                    self.process_pool.shutdown(wait=False)
                except Exception as shutdown_error:
                    logger.warning(f"Error shutting down broken pool: {shutdown_error}")
            
            # Create a new process pool
            mp_context = multiprocessing.get_context('spawn')
            self.process_pool = ProcessPoolExecutor(
                max_workers=self.max_concurrent_loads,
                mp_context=mp_context
            )
            self._use_process_pool = True
            
            logger.info("Successfully recreated ProcessPoolExecutor")
            self.load_statistics["pool_recreations"] = self.load_statistics.get("pool_recreations", 0) + 1
            
        except Exception as e:
            # If we can't recreate the process pool, fall back to thread pool
            logger.error(f"Failed to recreate process pool: {e}. Falling back to thread pool.")
            self.process_pool = ThreadPoolExecutor(max_workers=self.max_concurrent_loads)
            self._use_process_pool = False
            self.load_statistics["pool_fallbacks"] = self.load_statistics.get("pool_fallbacks", 0) + 1
    
    async def _handle_memory_error(self, model_name: str) -> None:
        """Handle memory errors by attempting to free memory.
        
        When a memory error occurs during model loading, this method attempts
        to free memory by:
        1. Running garbage collection
        2. Unloading non-essential models that haven't been used recently
        3. Clearing caches
        
        Args:
            model_name: Name of the model that triggered the memory error
        """
        logger.warning(f"Attempting to free memory after error loading {model_name}")
        
        import gc

        # Force garbage collection
        gc.collect()
        
        # Try to unload non-essential models that haven't been used recently
        models_to_unload = []
        current_time = datetime.now()
        
        for name, instance in self.models.items():
            if name == model_name:
                continue  # Don't unload the model we're trying to load
            
            if instance.status != ModelStatus.LOADED:
                continue
            
            config = instance.config
            
            # Consider unloading if:
            # 1. Model is ADVANCED priority (non-essential)
            # 2. Model hasn't been used in the last 5 minutes
            if config.priority == ModelPriority.ADVANCED:
                if instance.last_used:
                    time_since_use = (current_time - instance.last_used).total_seconds()
                    if time_since_use > 300:  # 5 minutes
                        models_to_unload.append(name)
                else:
                    models_to_unload.append(name)
        
        # Unload selected models
        for name in models_to_unload[:2]:  # Unload at most 2 models
            try:
                await self.unload_model(name)
                logger.info(f"Unloaded {name} to free memory")
            except Exception as e:
                logger.warning(f"Failed to unload {name}: {e}")
        
        # Run garbage collection again
        gc.collect()
        
        logger.info(f"Memory cleanup complete, unloaded {len(models_to_unload[:2])} models")
    
    def _load_model_sync(self, config: ModelConfig) -> Any:
        """
        Load a model synchronously (runs in thread pool).
        
        This method is a wrapper that handles instance-specific logic (cache, statistics)
        and delegates the actual loading to the picklable module-level function.
        
        Note: This method is NOT picklable because it uses self.* references.
        It should only be used with ThreadPoolExecutor (which doesn't require pickling).
        For ProcessPoolExecutor, use _load_model_sync_picklable directly.
        
        Args:
            config: ModelConfig object with model configuration
            
        Returns:
            Dict containing model information and loaded status
        """
        # Get cache directory if model cache is available
        cache_dir = None
        if self.model_cache:
            try:
                cache_dir = self.model_cache.cache_dir
            except Exception as e:
                logger.warning(f"Failed to get cache directory: {e}")
        
        # Use the picklable function for actual loading
        # This ensures the loading logic is consistent whether using
        # ThreadPoolExecutor or ProcessPoolExecutor
        model_object = _load_model_sync_picklable(
            model_name=config.name,
            model_type=config.model_type,
            estimated_load_time_seconds=config.estimated_load_time_seconds,
            estimated_memory_mb=config.estimated_memory_mb,
            required_for_capabilities=list(config.required_for_capabilities),
            cache_dir=cache_dir
        )
        
        # Update cache statistics based on result
        # This is done here (not in the picklable function) because
        # self.load_statistics is not picklable
        if model_object.get("loaded_from_cache", False):
            self.load_statistics["cache_hits"] += 1
        else:
            self.load_statistics["cache_misses"] += 1
        
        return model_object
    
    def _get_cache_dir(self) -> Optional[str]:
        """
        Get the cache directory path if available.
        
        This is a helper method to extract the cache directory path
        for passing to picklable functions.
        
        Returns:
            Cache directory path as string, or None if not available
        """
        if self.model_cache:
            try:
                return str(self.model_cache.cache_dir)
            except Exception:
                pass
        return None
    
    async def _handle_transfer_result(self, model_name: str, transfer_result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle the model transfer result from subprocess.
        
        This method processes the transfer result based on the strategy used:
        - METADATA_ONLY: Return the result as-is
        - PATH_BASED: Load model from the file path
        - SHARED_MEMORY: Map shared memory and reconstruct model
        - HYBRID: Combine shared memory and path-based loading
        
        Args:
            model_name: Name of the model
            transfer_result: Result dictionary from subprocess
        
        Returns:
            Processed model object ready for use
        """
        transfer_strategy = transfer_result.get("transfer_strategy", ModelTransferStrategy.METADATA_ONLY.value)
        
        logger.info(f"Handling transfer result for {model_name} (strategy: {transfer_strategy})")
        
        if transfer_strategy == ModelTransferStrategy.PATH_BASED.value:
            return await self._load_model_from_path(model_name, transfer_result)
        
        elif transfer_strategy == ModelTransferStrategy.SHARED_MEMORY.value:
            return await self._load_model_from_shared_memory(model_name, transfer_result)
        
        elif transfer_strategy == ModelTransferStrategy.HYBRID.value:
            # Hybrid uses shared memory, so delegate to that handler
            return await self._load_model_from_shared_memory(model_name, transfer_result)
        
        # METADATA_ONLY: Return as-is
        self.load_statistics["metadata_only_transfers"] += 1
        return transfer_result
    
    async def _load_model_from_path(self, model_name: str, transfer_result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Load model from file path saved by subprocess.
        
        This method loads the model data from the file path provided in the
        transfer result, then cleans up the temporary file.
        
        Args:
            model_name: Name of the model
            transfer_result: Transfer result containing model_path
        
        Returns:
            Model object with loaded data
        """
        model_path = transfer_result.get("model_path")
        config_path = transfer_result.get("config_path")
        
        if not model_path or not os.path.exists(model_path):
            logger.error(f"Model path not found for {model_name}: {model_path}")
            # Fall back to metadata-only
            return transfer_result
        
        try:
            # Load model data from file
            with open(model_path, 'rb') as f:
                model_data = pickle.load(f)
            
            logger.info(f"Loaded model {model_name} from path: {model_path}")
            
            # Load config if available
            config_data = None
            if config_path and os.path.exists(config_path):
                import json
                with open(config_path, 'r') as f:
                    config_data = json.load(f)
            
            # Clean up temporary files
            try:
                os.remove(model_path)
                if config_path and os.path.exists(config_path):
                    os.remove(config_path)
                logger.debug(f"Cleaned up transfer files for {model_name}")
            except Exception as e:
                logger.warning(f"Failed to clean up transfer files for {model_name}: {e}")
            
            # Update statistics
            self.load_statistics["path_based_transfers"] += 1
            
            # Merge loaded data with transfer result
            result = transfer_result.copy()
            result["model_data"] = model_data
            result["config_data"] = config_data
            result["transfer_completed"] = True
            
            return result
            
        except Exception as e:
            logger.error(f"Failed to load model from path for {model_name}: {e}")
            # Fall back to metadata-only
            return transfer_result
    
    async def _load_model_from_shared_memory(self, model_name: str, transfer_result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Load model from shared memory created by subprocess.
        
        This method maps the shared memory block, reconstructs the tensors,
        and then releases the shared memory.
        
        Args:
            model_name: Name of the model
            transfer_result: Transfer result containing shared memory info
        
        Returns:
            Model object with loaded tensors
        """
        shm_name = transfer_result.get("shared_memory_name")
        shm_size = transfer_result.get("shared_memory_size")
        tensor_shapes = transfer_result.get("tensor_shapes")
        tensor_dtypes = transfer_result.get("tensor_dtypes")
        tensor_offsets = transfer_result.get("tensor_offsets")
        
        if not shm_name or not SHARED_MEMORY_AVAILABLE:
            logger.warning(f"Shared memory not available for {model_name}, using metadata only")
            return transfer_result
        
        try:
            from multiprocessing import shared_memory as shm

            import numpy as np

            # Attach to existing shared memory block
            shm_block = shm.SharedMemory(name=shm_name)
            
            # Reconstruct tensors from shared memory
            tensors = {}
            for tensor_name, shape in tensor_shapes.items():
                dtype = np.dtype(tensor_dtypes[tensor_name])
                offset = tensor_offsets[tensor_name]
                size = np.prod(shape) * dtype.itemsize
                
                # Create numpy array from shared memory buffer
                tensor_data = np.frombuffer(
                    shm_block.buf[offset:offset + size],
                    dtype=dtype
                ).reshape(shape)
                
                # Copy the data to release shared memory dependency
                tensors[tensor_name] = tensor_data.copy()
            
            logger.info(f"Loaded {len(tensors)} tensors from shared memory for {model_name}")
            
            # Store reference for cleanup
            self._shared_memory_blocks[model_name] = shm_block
            
            # Clean up shared memory
            try:
                shm_block.close()
                shm_block.unlink()
                del self._shared_memory_blocks[model_name]
                logger.debug(f"Cleaned up shared memory for {model_name}")
            except Exception as e:
                logger.warning(f"Failed to clean up shared memory for {model_name}: {e}")
            
            # Update statistics
            self.load_statistics["shared_memory_transfers"] += 1
            
            # Merge loaded tensors with transfer result
            result = transfer_result.copy()
            result["tensors"] = tensors
            result["transfer_completed"] = True
            
            return result
            
        except Exception as e:
            logger.error(f"Failed to load model from shared memory for {model_name}: {e}")
            # Fall back to metadata-only
            return transfer_result
    
    def set_transfer_strategy(self, strategy: ModelTransferStrategy) -> None:
        """
        Set the model transfer strategy.
        
        Args:
            strategy: The transfer strategy to use for future model loads
        """
        self.transfer_strategy = strategy
        logger.info(f"Transfer strategy set to: {strategy.value}")
    
    def get_transfer_statistics(self) -> Dict[str, Any]:
        """
        Get statistics about model transfers.
        
        Returns:
            Dictionary with transfer statistics
        """
        return {
            "current_strategy": self.transfer_strategy.value,
            "path_based_transfers": self.load_statistics.get("path_based_transfers", 0),
            "shared_memory_transfers": self.load_statistics.get("shared_memory_transfers", 0),
            "metadata_only_transfers": self.load_statistics.get("metadata_only_transfers", 0),
            "shared_memory_available": SHARED_MEMORY_AVAILABLE,
            "transfer_dir": self._transfer_dir,
            "active_shared_memory_blocks": len(self._shared_memory_blocks)
        }
    
    async def _check_dependencies(self, model_name: str) -> bool:
        """Check if model dependencies are satisfied."""
        config = self.model_configs[model_name]
        
        for dep_name in config.dependencies:
            if dep_name not in self.models:
                return False
            
            dep_model = self.models[dep_name]
            if dep_model.status != ModelStatus.LOADED:
                return False
        
        return True
    
    async def _notify_availability_callbacks(self, model_name: str, available: bool) -> None:
        """Notify callbacks about model availability changes."""
        callbacks = self.availability_callbacks.get(model_name, [])
        
        for callback in callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(model_name, available)
                else:
                    callback(model_name, available)
            except Exception as e:
                logger.error(f"Error in availability callback for {model_name}: {e}")
    
    def is_model_available(self, model_name: str) -> bool:
        """Check if a model is available for use."""
        if model_name not in self.models:
            return False
        
        model_instance = self.models[model_name]
        return model_instance.status == ModelStatus.LOADED
    
    def get_model(self, model_name: str) -> Optional[Any]:
        """Get a loaded model object."""
        if not self.is_model_available(model_name):
            return None
        
        model_instance = self.models[model_name]
        model_instance.last_used = datetime.now()
        return model_instance.model_object
    
    def get_fallback_model(self, model_name: str) -> Optional[str]:
        """Get a fallback model if the requested model is unavailable."""
        if model_name not in self.model_configs:
            return None
        
        config = self.model_configs[model_name]
        
        for fallback_name in config.fallback_models:
            if self.is_model_available(fallback_name):
                logger.info(f"Using fallback model {fallback_name} for {model_name}")
                return fallback_name
        
        return None
    
    def get_models_for_capability(self, capability: str) -> List[str]:
        """Get all models that provide a specific capability."""
        available_models = []
        
        for model_name, config in self.model_configs.items():
            if capability in config.required_for_capabilities:
                if self.is_model_available(model_name):
                    available_models.append(model_name)
        
        return available_models
    
    def can_handle_capability(self, capability: str) -> bool:
        """Check if any model can handle a specific capability."""
        models = self.get_models_for_capability(capability)
        return len(models) > 0
    
    def get_capability_status(self, capability: str) -> Dict[str, Any]:
        """Get detailed status for a capability."""
        required_models = []
        available_models = []
        loading_models = []
        failed_models = []
        
        for model_name, config in self.model_configs.items():
            if capability in config.required_for_capabilities:
                required_models.append(model_name)
                
                model_instance = self.models[model_name]
                if model_instance.status == ModelStatus.LOADED:
                    available_models.append(model_name)
                elif model_instance.status == ModelStatus.LOADING:
                    loading_models.append(model_name)
                elif model_instance.status == ModelStatus.FAILED:
                    failed_models.append(model_name)
        
        return {
            "capability": capability,
            "available": len(available_models) > 0,
            "required_models": required_models,
            "available_models": available_models,
            "loading_models": loading_models,
            "failed_models": failed_models,
            "fallback_available": any(
                self.get_fallback_model(model) for model in required_models
            )
        }
    
    def register_availability_callback(self, model_name: str, callback: Callable) -> None:
        """Register a callback for model availability changes."""
        if model_name not in self.availability_callbacks:
            self.availability_callbacks[model_name] = []
        
        self.availability_callbacks[model_name].append(callback)
        logger.info(f"Registered availability callback for {model_name}")
    
    def get_model_status(self, model_name: str) -> Optional[Dict[str, Any]]:
        """Get detailed status for a specific model."""
        if model_name not in self.models:
            return None
        
        model_instance = self.models[model_name]
        config = model_instance.config
        
        # Check dependencies synchronously to avoid event loop issues
        dependencies_met = True
        if model_instance.status != ModelStatus.LOADED:
            for dep_name in config.dependencies:
                if dep_name not in self.models:
                    dependencies_met = False
                    break
                dep_model = self.models[dep_name]
                if dep_model.status != ModelStatus.LOADED:
                    dependencies_met = False
                    break
        
        return {
            "name": model_name,
            "status": model_instance.status.value,
            "priority": config.priority.value,
            "type": config.model_type,
            "capabilities": config.required_for_capabilities,
            "estimated_load_time": config.estimated_load_time_seconds,
            "actual_load_time": model_instance.load_duration_seconds,
            "estimated_memory": config.estimated_memory_mb,
            "actual_memory": model_instance.memory_usage_mb,
            "load_start_time": model_instance.load_start_time.isoformat() if model_instance.load_start_time else None,
            "load_end_time": model_instance.load_end_time.isoformat() if model_instance.load_end_time else None,
            "last_used": model_instance.last_used.isoformat() if model_instance.last_used else None,
            "retry_count": model_instance.retry_count,
            "max_retries": config.max_retries,
            "error_message": model_instance.error_message,
            "fallback_models": config.fallback_models,
            "dependencies": config.dependencies,
            "dependencies_met": dependencies_met
        }
    
    def get_all_model_statuses(self) -> Dict[str, Dict[str, Any]]:
        """Get status for all registered models."""
        return {
            model_name: self.get_model_status(model_name)
            for model_name in self.models.keys()
        }
    
    def get_loading_progress(self) -> Dict[str, Any]:
        """Get overall loading progress."""
        total_models = len(self.models)
        loaded_models = len([m for m in self.models.values() if m.status == ModelStatus.LOADED])
        loading_models = len([m for m in self.models.values() if m.status == ModelStatus.LOADING])
        failed_models = len([m for m in self.models.values() if m.status == ModelStatus.FAILED])
        pending_models = len([m for m in self.models.values() if m.status == ModelStatus.PENDING])
        
        progress_percent = (loaded_models / total_models) * 100 if total_models > 0 else 0
        
        # Calculate estimated time remaining
        loading_time_remaining = 0.0
        for model_instance in self.models.values():
            if model_instance.status == ModelStatus.LOADING:
                elapsed = (datetime.now() - model_instance.load_start_time).total_seconds()
                estimated_total = model_instance.config.estimated_load_time_seconds
                remaining = max(0, estimated_total - elapsed)
                loading_time_remaining += remaining
            elif model_instance.status == ModelStatus.PENDING:
                loading_time_remaining += model_instance.config.estimated_load_time_seconds
        
        # Include cache statistics if available
        cache_stats = {}
        if self.model_cache:
            try:
                cache_stats = self.model_cache.get_cache_statistics()
            except Exception as e:
                logger.warning(f"Failed to get cache statistics: {e}")
        
        return {
            "total_models": total_models,
            "loaded_models": loaded_models,
            "loading_models": loading_models,
            "failed_models": failed_models,
            "pending_models": pending_models,
            "progress_percent": progress_percent,
            "estimated_time_remaining_seconds": loading_time_remaining,
            "statistics": self.load_statistics.copy(),
            "cache_statistics": cache_stats
        }
    
    async def force_load_model(self, model_name: str) -> bool:
        """Force immediate loading of a specific model."""
        if model_name not in self.models:
            logger.error(f"Unknown model: {model_name}")
            return False
        
        model_instance = self.models[model_name]
        if model_instance.status == ModelStatus.LOADED:
            return True
        
        if model_instance.status == ModelStatus.LOADING:
            # Wait for current loading to complete
            while model_instance.status == ModelStatus.LOADING:
                await asyncio.sleep(0.5)
            return model_instance.status == ModelStatus.LOADED
        
        # Force load immediately
        logger.info(f"Force loading model: {model_name}")
        return await self._load_model_async(model_name)
    
    async def unload_model(self, model_name: str) -> bool:
        """Unload a model to free memory."""
        if model_name not in self.models:
            return False
        
        model_instance = self.models[model_name]
        if model_instance.status != ModelStatus.LOADED:
            return False
        
        try:
            model_instance.status = ModelStatus.UNLOADING
            
            # Clear model object (in real implementation, this would properly cleanup)
            model_instance.model_object = None
            model_instance.status = ModelStatus.UNLOADED
            
            logger.info(f"Unloaded model: {model_name}")
            await self._notify_availability_callbacks(model_name, False)
            
            return True
            
        except Exception as e:
            logger.error(f"Error unloading model {model_name}: {e}")
            model_instance.status = ModelStatus.FAILED
            model_instance.error_message = str(e)
            return False
    
    async def load_models_parallel(self, model_names: Optional[List[str]] = None) -> Dict[str, bool]:
        """Load multiple models in parallel using the optimized loader."""
        if not self._use_optimized_loading or not self._optimized_loader:
            logger.warning("Optimized parallel loading not available, falling back to sequential loading")
            return await self._load_models_sequential(model_names)
        
        # Determine which models to load
        if model_names is None:
            models_to_load = {name: config for name, config in self.model_configs.items()}
        else:
            models_to_load = {name: self.model_configs[name] for name in model_names if name in self.model_configs}
        
        if not models_to_load:
            logger.warning("No valid models to load")
            return {}
        
        logger.info(f"Starting parallel loading of {len(models_to_load)} models")
        
        # Log start of parallel loading for each model
        for model_name, config in models_to_load.items():
            if model_name in self.models:
                model_instance = self.models[model_name]
                model_instance.load_start_time = datetime.now()
                
                # Log model loading start with startup logger
                try:
                    from ..logging.startup_logger import log_model_loading_start
                    from ..startup.phase_manager import ModelLoadingStatus
                    
                    model_loading_status = ModelLoadingStatus(
                        model_name=model_name,
                        priority=config.priority.value,
                        status="loading",
                        started_at=model_instance.load_start_time,
                        size_mb=config.estimated_memory_mb,
                        estimated_load_time_seconds=config.estimated_load_time_seconds
                    )
                    
                    log_model_loading_start(model_name, model_loading_status)
                except ImportError:
                    pass  # Startup logger not available
        
        try:
            # Use optimized loader for parallel loading
            results = await self._optimized_loader.load_models_parallel(models_to_load)
            
            # Update model instances with results
            for model_name, success in results.items():
                if model_name in self.models:
                    model_instance = self.models[model_name]
                    config = self.model_configs[model_name]
                    
                    if success:
                        model_instance.status = ModelStatus.LOADED
                        model_instance.load_end_time = datetime.now()
                        if model_instance.load_start_time:
                            model_instance.load_duration_seconds = (
                                model_instance.load_end_time - model_instance.load_start_time
                            ).total_seconds()
                        
                        # Get the loaded model object from optimized loader
                        model_instance.model_object = self._get_model_from_optimized_loader(model_name)
                        
                        # Update statistics
                        self.load_statistics["total_loads"] += 1
                        self.load_statistics["successful_loads"] += 1
                        if model_instance.load_duration_seconds:
                            self.load_statistics["total_load_time"] += model_instance.load_duration_seconds
                            self.load_statistics["average_load_time"] = (
                                self.load_statistics["total_load_time"] / self.load_statistics["total_loads"]
                            )
                        
                        # Log parallel loading success with startup logger
                        try:
                            from ..logging.startup_logger import (
                                log_model_loading_complete,
                            )
                            from ..startup.phase_manager import ModelLoadingStatus
                            
                            model_loading_status = ModelLoadingStatus(
                                model_name=model_name,
                                priority=config.priority.value,
                                status="loaded",
                                started_at=model_instance.load_start_time,
                                completed_at=model_instance.load_end_time,
                                duration_seconds=model_instance.load_duration_seconds,
                                size_mb=config.estimated_memory_mb,
                                estimated_load_time_seconds=config.estimated_load_time_seconds
                            )
                            
                            log_model_loading_complete(model_name, model_loading_status)
                        except ImportError:
                            pass  # Startup logger not available
                        
                        # Notify availability callbacks
                        await self._notify_availability_callbacks(model_name, True)
                        
                        logger.info(f"Parallel loading successful for {model_name}")
                    else:
                        model_instance.status = ModelStatus.FAILED
                        model_instance.error_message = "Parallel loading failed"
                        model_instance.load_end_time = datetime.now()
                        
                        # Update statistics
                        self.load_statistics["total_loads"] += 1
                        self.load_statistics["failed_loads"] += 1
                        
                        # Log parallel loading failure with startup logger
                        try:
                            from ..logging.startup_logger import (
                                log_model_loading_complete,
                            )
                            from ..startup.phase_manager import ModelLoadingStatus
                            
                            model_loading_status = ModelLoadingStatus(
                                model_name=model_name,
                                priority=config.priority.value,
                                status="failed",
                                started_at=model_instance.load_start_time,
                                completed_at=model_instance.load_end_time,
                                duration_seconds=(model_instance.load_end_time - model_instance.load_start_time).total_seconds() if model_instance.load_start_time else None,
                                error_message="Parallel loading failed",
                                size_mb=config.estimated_memory_mb,
                                estimated_load_time_seconds=config.estimated_load_time_seconds
                            )
                            
                            log_model_loading_complete(model_name, model_loading_status)
                        except ImportError:
                            pass  # Startup logger not available
                        
                        # Notify availability callbacks
                        await self._notify_availability_callbacks(model_name, False)
                        
                        logger.error(f"Parallel loading failed for {model_name}")
            
            successful_loads = sum(results.values())
            logger.info(f"Parallel loading completed: {successful_loads}/{len(results)} successful")
            
            return results
            
        except Exception as e:
            logger.error(f"Error in parallel model loading: {e}")
            # Fall back to sequential loading
            return await self._load_models_sequential(model_names)
    
    async def _load_models_sequential(self, model_names: Optional[List[str]] = None) -> Dict[str, bool]:
        """Load models sequentially as fallback."""
        if model_names is None:
            model_names = list(self.model_configs.keys())
        
        results = {}
        for model_name in model_names:
            try:
                success = await self._load_model_async(model_name)
                results[model_name] = success
            except Exception as e:
                logger.error(f"Error loading model {model_name}: {e}")
                results[model_name] = False
        
        return results
    
    def _get_model_from_optimized_loader(self, model_name: str) -> Optional[Any]:
        """Get a model object from the optimized loader."""
        if not self._optimized_loader:
            return None
        
        try:
            # This would get the actual model object from the optimized loader's cache
            # For now, return a placeholder that indicates optimized loading was used
            return {
                "name": model_name,
                "loaded_via": "optimized_parallel_loader",
                "loaded_at": datetime.now(),
                "optimized": True
            }
        except Exception as e:
            logger.error(f"Error getting model from optimized loader: {e}")
            return None
    
    def enable_parallel_loading(self, enable: bool = True) -> None:
        """Enable or disable parallel loading optimization."""
        self._use_optimized_loading = enable
        
        if enable and not self._optimized_loader:
            try:
                from .loader_optimized import get_optimized_loader
                self._optimized_loader = get_optimized_loader()
                logger.info("Parallel loading enabled")
            except Exception as e:
                logger.error(f"Failed to enable parallel loading: {e}")
                self._use_optimized_loading = False
        elif not enable:
            self._optimized_loader = None
            logger.info("Parallel loading disabled")
    
    def get_parallel_loading_stats(self) -> Dict[str, Any]:
        """Get statistics about parallel loading performance."""
        if not self._optimized_loader:
            return {"parallel_loading_enabled": False}
        
        try:
            optimization_stats = self._optimized_loader.get_optimization_statistics()
            return {
                "parallel_loading_enabled": True,
                "optimization_statistics": optimization_stats
            }
        except Exception as e:
            logger.error(f"Error getting parallel loading stats: {e}")
            return {"parallel_loading_enabled": True, "error": str(e)}
    
    async def switch_model(self, old_model: str, new_model: str, strategy: str = "hot_swap") -> bool:
        """Switch between models efficiently using the optimized loader."""
        logger.info(f"Switching model from {old_model} to {new_model} using {strategy} strategy")
        
        try:
            # Validate models exist in configuration
            if old_model not in self.model_configs:
                logger.error(f"Old model {old_model} not found in configuration")
                return False
            
            if new_model not in self.model_configs:
                logger.error(f"New model {new_model} not found in configuration")
                return False
            
            # Use optimized loader if available
            if self._optimized_loader:
                success = await self._optimized_loader.switch_models(old_model, new_model, strategy)
                
                if success:
                    # Update model statuses
                    if old_model in self.models:
                        old_instance = self.models[old_model]
                        old_instance.last_used = datetime.now() - timedelta(hours=1)  # Mark as less recent
                    
                    if new_model in self.models:
                        new_instance = self.models[new_model]
                        new_instance.status = ModelStatus.LOADED
                        new_instance.last_used = datetime.now()
                        
                        # Notify availability callbacks
                        await self._notify_availability_callbacks(new_model, True)
                    
                    logger.info(f"Model switch successful: {old_model} -> {new_model}")
                    return True
                else:
                    logger.error(f"Optimized loader failed to switch models: {old_model} -> {new_model}")
                    return False
            else:
                # Fallback to basic switching without optimized loader
                logger.warning("Optimized loader not available, using basic model switching")
                return await self._basic_model_switch(old_model, new_model)
                
        except Exception as e:
            logger.error(f"Error switching models {old_model} -> {new_model}: {e}")
            return False
    
    async def _basic_model_switch(self, old_model: str, new_model: str) -> bool:
        """Basic model switching without optimized loader."""
        try:
            # Check if new model is already loaded
            if self.is_model_available(new_model):
                logger.info(f"Model {new_model} already available, performing instant switch")
                
                # Update usage timestamps
                if old_model in self.models:
                    self.models[old_model].last_used = datetime.now() - timedelta(hours=1)
                
                if new_model in self.models:
                    self.models[new_model].last_used = datetime.now()
                
                return True
            
            # Load new model if not available
            logger.info(f"Loading new model {new_model} for basic switch")
            success = await self.force_load_model(new_model)
            
            if success:
                # Optionally unload old model to free memory
                await asyncio.sleep(1.0)  # Brief delay
                await self.unload_model(old_model)
                
                logger.info(f"Basic model switch completed: {old_model} -> {new_model}")
                return True
            else:
                logger.error(f"Failed to load new model {new_model} for basic switch")
                return False
                
        except Exception as e:
            logger.error(f"Error in basic model switch: {e}")
            return False
    
    async def get_switch_recommendations(self, current_model: str, target_models: List[str]) -> Dict[str, Dict[str, Any]]:
        """Get recommendations for switching to different models."""
        if self._optimized_loader:
            return await self._optimized_loader.get_switch_recommendations(current_model, target_models)
        else:
            # Basic recommendations without optimized loader
            recommendations = {}
            
            for target_model in target_models:
                is_available = self.is_model_available(target_model)
                
                recommendations[target_model] = {
                    "recommended_strategy": "instant" if is_available else "basic_load",
                    "estimated_switch_time_seconds": 0.1 if is_available else 30.0,
                    "memory_required_mb": self.model_configs[target_model].estimated_memory_mb if target_model in self.model_configs else 500.0,
                    "is_cached": is_available,
                    "is_compressed": False,
                    "memory_pressure_impact": "unknown",
                    "confidence": 0.7 if is_available else 0.5
                }
            
            return recommendations
    
    async def batch_switch_models(self, switches: List[Tuple[str, str]], strategy: str = "auto") -> Dict[str, bool]:
        """Perform multiple model switches efficiently."""
        if self._optimized_loader:
            return await self._optimized_loader.batch_switch_models(switches, strategy)
        else:
            # Basic batch switching
            results = {}
            
            for old_model, new_model in switches:
                success = await self.switch_model(old_model, new_model, "basic")
                results[f"{old_model}->{new_model}"] = success
                
                # Brief pause between switches
                await asyncio.sleep(0.5)
            
            return results
    
    def get_switchable_models(self, current_model: str) -> List[Dict[str, Any]]:
        """Get list of models that can be switched to from current model."""
        switchable = []
        
        if current_model not in self.model_configs:
            return switchable
        
        current_config = self.model_configs[current_model]
        
        for model_name, config in self.model_configs.items():
            if model_name == current_model:
                continue
            
            # Check if models are compatible (same capabilities or similar type)
            compatibility_score = 0.0
            
            # Check capability overlap
            current_caps = set(current_config.required_for_capabilities)
            target_caps = set(config.required_for_capabilities)
            
            if current_caps & target_caps:  # Has overlapping capabilities
                compatibility_score += 0.5
            
            # Check model type similarity
            if current_config.model_type == config.model_type:
                compatibility_score += 0.3
            
            # Check priority compatibility
            if current_config.priority == config.priority:
                compatibility_score += 0.2
            
            if compatibility_score > 0.3:  # Minimum compatibility threshold
                model_info = {
                    "name": model_name,
                    "type": config.model_type,
                    "priority": config.priority.value,
                    "capabilities": config.required_for_capabilities,
                    "estimated_memory_mb": config.estimated_memory_mb,
                    "estimated_load_time_seconds": config.estimated_load_time_seconds,
                    "compatibility_score": compatibility_score,
                    "is_loaded": self.is_model_available(model_name),
                    "status": self.models[model_name].status.value if model_name in self.models else "unknown"
                }
                
                switchable.append(model_info)
        
        # Sort by compatibility score and load status
        switchable.sort(key=lambda x: (x["is_loaded"], x["compatibility_score"]), reverse=True)
        
        return switchable
    
    async def preload_for_switching(self, models: List[str], priority: int = 500) -> Dict[str, bool]:
        """Preload models for efficient switching."""
        logger.info(f"Preloading {len(models)} models for efficient switching")
        
        results = {}
        
        for model_name in models:
            if model_name not in self.model_configs:
                logger.warning(f"Model {model_name} not found in configuration, skipping preload")
                results[model_name] = False
                continue
            
            if self.is_model_available(model_name):
                logger.info(f"Model {model_name} already loaded, skipping preload")
                results[model_name] = True
                continue
            
            # Add to loading queue with specified priority
            try:
                await self.loading_queue.put((model_name, 0))  # No delay for preloading
                logger.info(f"Queued {model_name} for preloading")
                results[model_name] = True
            except Exception as e:
                logger.error(f"Error queuing {model_name} for preload: {e}")
                results[model_name] = False
        
        return results
    
    def get_model_switching_stats(self) -> Dict[str, Any]:
        """Get statistics about model switching operations."""
        stats = {
            "optimized_loader_available": self._optimized_loader is not None,
            "total_models": len(self.models),
            "loaded_models": len([m for m in self.models.values() if m.status == ModelStatus.LOADED]),
            "loading_models": len([m for m in self.models.values() if m.status == ModelStatus.LOADING]),
            "failed_models": len([m for m in self.models.values() if m.status == ModelStatus.FAILED]),
            "model_usage_stats": {}
        }
        
        # Add usage statistics for each model
        for model_name, model_instance in self.models.items():
            stats["model_usage_stats"][model_name] = {
                "status": model_instance.status.value,
                "last_used": model_instance.last_used.isoformat() if model_instance.last_used else None,
                "load_duration_seconds": model_instance.load_duration_seconds,
                "retry_count": model_instance.retry_count,
                "memory_usage_mb": model_instance.memory_usage_mb
            }
        
        # Add optimized loader stats if available
        if self._optimized_loader:
            try:
                optimization_stats = self._optimized_loader.get_optimization_statistics()
                stats["optimization_statistics"] = optimization_stats
            except Exception as e:
                logger.error(f"Error getting optimization statistics: {e}")
                stats["optimization_statistics"] = {"error": str(e)}
        
        return stats

    async def shutdown(self) -> None:
        """Shutdown the model manager and cleanup resources."""
        logger.info("Shutting down ModelManager")
        
        # Signal shutdown
        self._shutdown_event.set()
        
        # Cancel background loader
        if self._background_loader_task and not self._background_loader_task.done():
            self._background_loader_task.cancel()
            try:
                await self._background_loader_task
            except asyncio.CancelledError:
                pass
        
        # Cancel all loading tasks
        for task in self.loading_tasks.values():
            if not task.done():
                task.cancel()
        
        # Wait for tasks to complete
        if self.loading_tasks:
            await asyncio.gather(*self.loading_tasks.values(), return_exceptions=True)
        
        # Clean up shared memory blocks
        if hasattr(self, '_shared_memory_blocks') and self._shared_memory_blocks:
            for model_name, shm_block in list(self._shared_memory_blocks.items()):
                try:
                    shm_block.close()
                    shm_block.unlink()
                    logger.debug(f"Cleaned up shared memory for {model_name}")
                except Exception as e:
                    logger.warning(f"Error cleaning up shared memory for {model_name}: {e}")
            self._shared_memory_blocks.clear()
            logger.info("Shared memory cleanup complete")
        
        # Clean up transfer directory
        if hasattr(self, '_transfer_dir') and self._transfer_dir:
            try:
                import shutil

                # Only clean up files we created (with our naming pattern)
                for filename in os.listdir(self._transfer_dir):
                    if filename.endswith('.pkl') or filename.endswith('_config.json'):
                        filepath = os.path.join(self._transfer_dir, filename)
                        try:
                            os.remove(filepath)
                        except Exception:
                            pass
                logger.info("Transfer directory cleanup complete")
            except Exception as e:
                logger.warning(f"Error cleaning up transfer directory: {e}")
        
        # Shutdown optimized loader
        if self._optimized_loader:
            try:
                await self._optimized_loader.shutdown()
            except Exception as e:
                logger.error(f"Error shutting down optimized loader: {e}")
        
        # Shutdown memory manager
        if self.memory_manager:
            try:
                await self.memory_manager.shutdown()
            except Exception as e:
                logger.error(f"Error shutting down memory manager: {e}")
        
        # Shutdown process pool (used for CPU-intensive model loading)
        if hasattr(self, 'process_pool') and self.process_pool:
            try:
                self.process_pool.shutdown(wait=True, cancel_futures=True)
                logger.info("ProcessPoolExecutor shutdown complete")
            except TypeError:
                # Python < 3.9 doesn't support cancel_futures
                self.process_pool.shutdown(wait=True)
                logger.info("ProcessPoolExecutor shutdown complete (legacy mode)")
            except Exception as e:
                logger.error(f"Error shutting down process pool: {e}")
        
        # Shutdown thread pool (used for lightweight operations)
        if hasattr(self, 'thread_pool') and self.thread_pool:
            try:
                self.thread_pool.shutdown(wait=True, cancel_futures=True)
                logger.info("ThreadPoolExecutor shutdown complete")
            except TypeError:
                # Python < 3.9 doesn't support cancel_futures
                self.thread_pool.shutdown(wait=True)
                logger.info("ThreadPoolExecutor shutdown complete (legacy mode)")
            except Exception as e:
                logger.error(f"Error shutting down thread pool: {e}")
        
        logger.info("ModelManager shutdown complete")


# Global model manager instance
_model_manager: Optional[ModelManager] = None


def get_model_manager() -> ModelManager:
    """Get the global model manager instance."""
    global _model_manager
    if _model_manager is None:
        _model_manager = ModelManager()
    return _model_manager


async def initialize_model_manager() -> ModelManager:
    """Initialize and start the model manager."""
    manager = get_model_manager()
    await manager.start_progressive_loading()
    return manager
async def initialize_model_manager() -> ModelManager:
    """Initialize and start the model manager."""
    manager = get_model_manager()
    await manager.start_progressive_loading()
    return manager