"""
Cold Start Optimizer for Multimodal Librarian

This module provides optimizations specifically for minimizing cold start times
in local development environments. It implements lazy loading, parallel initialization,
and resource pre-allocation strategies.
"""

import asyncio
import logging
import os
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


@dataclass
class ColdStartMetrics:
    """Metrics for cold start performance tracking."""
    startup_start_time: float
    health_check_ready_time: Optional[float] = None
    essential_services_ready_time: Optional[float] = None
    full_startup_complete_time: Optional[float] = None
    models_loaded: Dict[str, float] = field(default_factory=dict)
    services_initialized: Dict[str, float] = field(default_factory=dict)
    optimization_flags: Dict[str, bool] = field(default_factory=dict)


class ColdStartOptimizer:
    """
    Cold start optimizer that implements various strategies to minimize
    container startup times.
    """
    
    def __init__(self):
        self.metrics = ColdStartMetrics(startup_start_time=time.time())
        # Models are served by model-server container, not loaded locally
        # These sets track which model capabilities we need from model-server
        self.essential_models: Set[str] = {
            "embeddings"  # Embedding capability from model-server
        }
        self.deferred_models: Set[str] = {
            "nlp"  # NLP capability from model-server
        }
        self.critical_services: Set[str] = {
            "health_check",
            "basic_api",
            "websocket"
        }
        self.deferred_services: Set[str] = {
            "vector_search",
            "knowledge_graph",
            "ai_chat",
            "document_processing"
        }
        self._background_tasks: List[asyncio.Task] = []
        self._service_registry: Dict[str, Any] = {}
        self._model_cache: Dict[str, Any] = {}
        
    def is_cold_start_enabled(self) -> bool:
        """Check if cold start optimization is enabled."""
        return os.getenv("COLD_START_OPTIMIZATION", "false").lower() == "true"
    
    def get_startup_mode(self) -> str:
        """Get the startup mode (fast, normal, full)."""
        return os.getenv("STARTUP_MODE", "normal").lower()
    
    async def optimize_startup_sequence(self) -> Dict[str, Any]:
        """
        Optimize the startup sequence for minimal cold start time.
        
        Returns:
            Dict containing startup status and timing information
        """
        if not self.is_cold_start_enabled():
            logger.info("Cold start optimization disabled")
            return {"optimized": False, "reason": "disabled"}
        
        startup_mode = self.get_startup_mode()
        logger.info(f"Starting cold start optimization in {startup_mode} mode")
        
        # Phase 1: Critical services (must complete quickly)
        await self._initialize_critical_services()
        self.metrics.health_check_ready_time = time.time()
        
        # Phase 2: Essential models (parallel loading)
        if startup_mode in ["normal", "full"]:
            await self._load_essential_models()
            self.metrics.essential_services_ready_time = time.time()
        
        # Phase 3: Background initialization (non-blocking)
        if startup_mode == "full":
            self._start_background_initialization()
        
        return {
            "optimized": True,
            "startup_mode": startup_mode,
            "metrics": self._get_startup_metrics(),
            "services_ready": list(self._service_registry.keys()),
            "models_loaded": list(self._model_cache.keys())
        }
    
    async def _initialize_critical_services(self):
        """Initialize critical services required for health checks."""
        logger.info("Initializing critical services for cold start...")
        
        # Initialize services in parallel
        tasks = []
        
        for service_name in self.critical_services:
            task = asyncio.create_task(
                self._initialize_service(service_name),
                name=f"init_{service_name}"
            )
            tasks.append(task)
        
        # Wait for all critical services with timeout
        try:
            await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True),
                timeout=10.0  # 10 second timeout for critical services
            )
            logger.info("Critical services initialized successfully")
        except asyncio.TimeoutError:
            logger.warning("Some critical services took longer than expected")
        
        # Record initialization times
        for task in tasks:
            if task.done() and not task.exception():
                service_name = task.get_name().replace("init_", "")
                self.metrics.services_initialized[service_name] = time.time()
    
    async def _load_essential_models(self):
        """Check essential model availability via model server."""
        logger.info("Checking essential model availability from model-server...")
        
        # Check model server readiness instead of loading models locally
        try:
            from ..clients.model_server_client import (
                get_model_client,
                initialize_model_client,
            )
            
            client = get_model_client()
            if client is None:
                client = await initialize_model_client()
            
            # Wait for model server with timeout
            is_ready = await client.wait_for_ready(timeout=30.0, poll_interval=2.0)
            
            if is_ready:
                for model_name in self.essential_models:
                    self._model_cache[model_name] = {
                        "status": "available",
                        "source": "model-server"
                    }
                    self.metrics.models_loaded[model_name] = time.time()
                    logger.info(f"Essential model capability available: {model_name}")
            else:
                logger.warning("Model server not ready, essential models unavailable")
                
        except Exception as e:
            logger.error(f"Failed to check model server: {e}")
    
    def _start_background_initialization(self):
        """Start background initialization tasks."""
        logger.info("Starting background initialization...")
        
        # Start deferred model loading
        for model_name in self.deferred_models:
            task = asyncio.create_task(
                self._load_model_async(model_name),
                name=f"load_{model_name}"
            )
            self._background_tasks.append(task)
        
        # Start deferred service initialization
        for service_name in self.deferred_services:
            task = asyncio.create_task(
                self._initialize_service(service_name),
                name=f"init_{service_name}"
            )
            self._background_tasks.append(task)
        
        # Monitor background tasks
        asyncio.create_task(self._monitor_background_tasks())
    
    async def _initialize_service(self, service_name: str) -> bool:
        """Initialize a specific service."""
        try:
            start_time = time.time()
            
            if service_name == "health_check":
                # Ultra-fast health check service
                self._service_registry[service_name] = {
                    "status": "ready",
                    "initialized_at": start_time
                }
                
            elif service_name == "basic_api":
                # Basic API endpoints
                self._service_registry[service_name] = {
                    "status": "ready",
                    "endpoints": ["/", "/health/simple", "/features"],
                    "initialized_at": start_time
                }
                
            elif service_name == "websocket":
                # WebSocket connection manager
                self._service_registry[service_name] = {
                    "status": "ready",
                    "connections": 0,
                    "initialized_at": start_time
                }
                
            elif service_name == "vector_search":
                # Vector search service (deferred)
                await asyncio.sleep(0.1)  # Simulate initialization
                self._service_registry[service_name] = {
                    "status": "ready",
                    "backend": "milvus",
                    "initialized_at": start_time
                }
                
            elif service_name == "knowledge_graph":
                # Knowledge graph service (deferred)
                await asyncio.sleep(0.1)  # Simulate initialization
                self._service_registry[service_name] = {
                    "status": "ready",
                    "backend": "neo4j",
                    "initialized_at": start_time
                }
                
            elif service_name == "ai_chat":
                # AI chat service (deferred)
                await asyncio.sleep(0.1)  # Simulate initialization
                self._service_registry[service_name] = {
                    "status": "ready",
                    "providers": ["openai", "fallback"],
                    "initialized_at": start_time
                }
                
            elif service_name == "document_processing":
                # Document processing service (deferred)
                await asyncio.sleep(0.1)  # Simulate initialization
                self._service_registry[service_name] = {
                    "status": "ready",
                    "processors": ["pdf", "text"],
                    "initialized_at": start_time
                }
            
            duration = time.time() - start_time
            logger.debug(f"Service {service_name} initialized in {duration:.3f}s")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize service {service_name}: {e}")
            return False
    
    def _load_model_sync(self, model_name: str) -> Any:
        """
        Check model availability via model server (for thread pool execution).
        
        Note: Models are loaded in the model-server container, not locally.
        This function returns a status dict indicating model server readiness.
        """
        try:
            # Models are served by model-server container
            # Return a status indicator instead of loading locally
            logger.info(f"Model {model_name} will be served by model-server")
            return {
                "name": model_name,
                "status": "available_via_model_server",
                "note": "Model loaded in model-server container"
            }
        except Exception as e:
            logger.error(f"Failed to check model {model_name}: {e}")
            return None
    
    async def _load_model_async(self, model_name: str) -> Any:
        """Check model availability via model server asynchronously."""
        try:
            from ..clients.model_server_client import get_model_client
            
            client = get_model_client()
            if client is None:
                logger.warning(f"Model server client not available for {model_name}")
                return None
            
            # Check if model server is ready
            is_ready = await client.is_ready()
            
            if is_ready:
                self._model_cache[model_name] = {
                    "status": "available",
                    "source": "model-server"
                }
                self.metrics.models_loaded[model_name] = time.time()
                logger.info(f"Background model capability available: {model_name}")
                return self._model_cache[model_name]
            else:
                logger.warning(f"Model server not ready for {model_name}")
                return None
                
        except Exception as e:
            logger.error(f"Failed to check model {model_name} in background: {e}")
            return None
    
    async def _monitor_background_tasks(self):
        """Monitor background initialization tasks."""
        logger.info("Monitoring background initialization tasks...")
        
        while self._background_tasks:
            # Check for completed tasks
            completed_tasks = [task for task in self._background_tasks if task.done()]
            
            for task in completed_tasks:
                self._background_tasks.remove(task)
                
                if task.exception():
                    logger.error(f"Background task failed: {task.get_name()}: {task.exception()}")
                else:
                    logger.debug(f"Background task completed: {task.get_name()}")
            
            # Wait before next check
            await asyncio.sleep(1.0)
        
        self.metrics.full_startup_complete_time = time.time()
        logger.info("All background initialization tasks completed")
    
    def _get_startup_metrics(self) -> Dict[str, Any]:
        """Get startup performance metrics."""
        current_time = time.time()
        startup_duration = current_time - self.metrics.startup_start_time
        
        metrics = {
            "total_startup_time": startup_duration,
            "health_check_ready_time": (
                self.metrics.health_check_ready_time - self.metrics.startup_start_time
                if self.metrics.health_check_ready_time else None
            ),
            "essential_services_ready_time": (
                self.metrics.essential_services_ready_time - self.metrics.startup_start_time
                if self.metrics.essential_services_ready_time else None
            ),
            "full_startup_complete_time": (
                self.metrics.full_startup_complete_time - self.metrics.startup_start_time
                if self.metrics.full_startup_complete_time else None
            ),
            "models_loaded_count": len(self.metrics.models_loaded),
            "services_initialized_count": len(self.metrics.services_initialized),
            "background_tasks_active": len(self._background_tasks)
        }
        
        return metrics
    
    def get_service_status(self, service_name: str) -> Optional[Dict[str, Any]]:
        """Get the status of a specific service."""
        return self._service_registry.get(service_name)
    
    def get_model(self, model_name: str) -> Optional[Any]:
        """Get a loaded model."""
        return self._model_cache.get(model_name)
    
    def is_service_ready(self, service_name: str) -> bool:
        """Check if a service is ready."""
        service = self._service_registry.get(service_name)
        return service is not None and service.get("status") == "ready"
    
    def is_model_loaded(self, model_name: str) -> bool:
        """Check if a model is loaded."""
        return model_name in self._model_cache
    
    async def shutdown(self):
        """Shutdown the cold start optimizer and clean up resources."""
        logger.info("Shutting down cold start optimizer...")
        
        # Cancel background tasks
        for task in self._background_tasks:
            if not task.done():
                task.cancel()
        
        # Wait for tasks to complete or be cancelled
        if self._background_tasks:
            await asyncio.gather(*self._background_tasks, return_exceptions=True)
        
        # Clear caches
        self._service_registry.clear()
        self._model_cache.clear()
        self._background_tasks.clear()
        
        logger.info("Cold start optimizer shutdown completed")


# Global instance
_cold_start_optimizer: Optional[ColdStartOptimizer] = None


def get_cold_start_optimizer() -> ColdStartOptimizer:
    """Get the global cold start optimizer instance."""
    global _cold_start_optimizer
    if _cold_start_optimizer is None:
        _cold_start_optimizer = ColdStartOptimizer()
    return _cold_start_optimizer


async def initialize_cold_start_optimization() -> Dict[str, Any]:
    """Initialize cold start optimization."""
    optimizer = get_cold_start_optimizer()
    return await optimizer.optimize_startup_sequence()


@asynccontextmanager
async def cold_start_context():
    """Context manager for cold start optimization."""
    optimizer = get_cold_start_optimizer()
    
    try:
        # Initialize optimization
        result = await optimizer.optimize_startup_sequence()
        logger.info(f"Cold start optimization initialized: {result}")
        yield optimizer
    finally:
        # Cleanup
        await optimizer.shutdown()


# Utility functions for integration with existing code
def is_cold_start_mode() -> bool:
    """Check if cold start optimization is enabled."""
    return os.getenv("COLD_START_OPTIMIZATION", "false").lower() == "true"


def get_startup_mode() -> str:
    """Get the current startup mode."""
    return os.getenv("STARTUP_MODE", "normal").lower()


def should_defer_service(service_name: str) -> bool:
    """Check if a service should be deferred during cold start."""
    if not is_cold_start_mode():
        return False
    
    optimizer = get_cold_start_optimizer()
    return service_name in optimizer.deferred_services


def should_defer_model(model_name: str) -> bool:
    """Check if a model should be deferred during cold start."""
    if not is_cold_start_mode():
        return False
    
    optimizer = get_cold_start_optimizer()
    return model_name in optimizer.deferred_models


async def wait_for_service(service_name: str, timeout: float = 30.0) -> bool:
    """Wait for a service to be ready."""
    optimizer = get_cold_start_optimizer()
    
    start_time = time.time()
    while time.time() - start_time < timeout:
        if optimizer.is_service_ready(service_name):
            return True
        await asyncio.sleep(0.1)
    
    return False


async def wait_for_model(model_name: str, timeout: float = 60.0) -> Optional[Any]:
    """Wait for a model to be loaded."""
    optimizer = get_cold_start_optimizer()
    
    start_time = time.time()
    while time.time() - start_time < timeout:
        if optimizer.is_model_loaded(model_name):
            return optimizer.get_model(model_name)
        await asyncio.sleep(0.1)
    
    return None        await asyncio.sleep(0.1)
    
    return None