"""
Progressive Model Loader

This module implements progressive model loading that integrates with the startup
phase manager to provide smooth, priority-based model loading with user experience
optimization.

Key Features:
- Integration with startup phase manager
- Priority-based loading schedules
- User experience optimization
- Capability-based loading decisions
- Memory management and optimization
"""

import asyncio
import logging
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum

from ..models.model_manager import get_model_manager, ModelPriority, ModelStatus
from .phase_manager import StartupPhase, StartupPhaseManager

logger = logging.getLogger(__name__)


class LoadingStrategy(Enum):
    """Loading strategies for different scenarios."""
    AGGRESSIVE = "aggressive"      # Load as fast as possible
    BALANCED = "balanced"          # Balance speed and resource usage
    CONSERVATIVE = "conservative"  # Minimize resource impact
    USER_DRIVEN = "user_driven"    # Load based on user requests


@dataclass
class LoadingSchedule:
    """Schedule for loading models during startup phases."""
    phase: StartupPhase
    models_to_load: List[str]
    max_concurrent: int
    delay_between_models: float
    timeout_per_model: float
    strategy: LoadingStrategy


class ProgressiveLoader:
    """
    Progressive model loader that coordinates with startup phases.
    
    This class manages the loading of models in a way that optimizes both
    startup time and user experience, ensuring critical models load first
    while providing graceful degradation.
    """
    
    def __init__(self, startup_phase_manager: Optional[StartupPhaseManager] = None):
        """Initialize the progressive loader."""
        self.startup_phase_manager = startup_phase_manager
        self.model_manager = get_model_manager()
        
        # Loading schedules for each phase
        self.loading_schedules = self._create_loading_schedules()
        
        # State tracking
        self.current_strategy = LoadingStrategy.BALANCED
        self.loading_tasks: Dict[str, asyncio.Task] = {}
        self.phase_loading_tasks: Dict[StartupPhase, asyncio.Task] = {}
        self.user_request_queue: List[str] = []  # Capabilities requested by users
        
        # Callbacks
        self.progress_callbacks: List[Callable] = []
        self.completion_callbacks: Dict[StartupPhase, List[Callable]] = {}
        
        # Statistics
        self.loading_stats = {
            "phase_completion_times": {},
            "user_wait_times": [],
            "capability_ready_times": {},
            "memory_usage_over_time": []
        }
        
        logger.info("ProgressiveLoader initialized")
    
    def _create_loading_schedules(self) -> Dict[StartupPhase, LoadingSchedule]:
        """Create loading schedules for each startup phase."""
        return {
            StartupPhase.MINIMAL: LoadingSchedule(
                phase=StartupPhase.MINIMAL,
                models_to_load=[],  # No models needed for minimal phase
                max_concurrent=1,
                delay_between_models=0.0,
                timeout_per_model=30.0,
                strategy=LoadingStrategy.AGGRESSIVE
            ),
            
            StartupPhase.ESSENTIAL: LoadingSchedule(
                phase=StartupPhase.ESSENTIAL,
                models_to_load=[
                    "text-embedding-small",
                    "chat-model-base", 
                    "search-index"
                ],
                max_concurrent=2,
                delay_between_models=5.0,
                timeout_per_model=60.0,
                strategy=LoadingStrategy.BALANCED
            ),
            
            StartupPhase.FULL: LoadingSchedule(
                phase=StartupPhase.FULL,
                models_to_load=[
                    "chat-model-large",
                    "document-processor",
                    "multimodal-model",
                    "specialized-analyzers"
                ],
                max_concurrent=2,
                delay_between_models=10.0,
                timeout_per_model=180.0,
                strategy=LoadingStrategy.CONSERVATIVE
            )
        }
    
    async def start_progressive_loading(self) -> None:
        """Start the progressive loading process."""
        logger.info("Starting progressive model loading")
        
        # Start model manager
        await self.model_manager.start_progressive_loading()
        
        # Register phase callbacks if startup phase manager is available
        if self.startup_phase_manager:
            self.startup_phase_manager.register_phase_callback(
                StartupPhase.MINIMAL, self._on_minimal_phase
            )
            self.startup_phase_manager.register_phase_callback(
                StartupPhase.ESSENTIAL, self._on_essential_phase
            )
            self.startup_phase_manager.register_phase_callback(
                StartupPhase.FULL, self._on_full_phase
            )
        
        # Start user-driven loading monitor
        asyncio.create_task(self._monitor_user_requests())
        
        logger.info("Progressive loading started")
    
    async def _on_minimal_phase(self) -> None:
        """Handle transition to minimal phase."""
        logger.info("Minimal phase reached - no models required")
        await self._execute_phase_loading(StartupPhase.MINIMAL)
    
    async def _on_essential_phase(self) -> None:
        """Handle transition to essential phase."""
        logger.info("Essential phase reached - loading core models")
        await self._execute_phase_loading(StartupPhase.ESSENTIAL)
    
    async def _on_full_phase(self) -> None:
        """Handle transition to full phase."""
        logger.info("Full phase reached - loading all remaining models")
        await self._execute_phase_loading(StartupPhase.FULL)
    
    async def _execute_phase_loading(self, phase: StartupPhase) -> None:
        """Execute model loading for a specific phase."""
        if phase in self.phase_loading_tasks:
            return  # Already loading for this phase
        
        schedule = self.loading_schedules[phase]
        task = asyncio.create_task(self._load_phase_models(schedule))
        self.phase_loading_tasks[phase] = task
        
        try:
            await task
            logger.info(f"Completed loading for phase: {phase.value}")
            
            # Record completion time
            self.loading_stats["phase_completion_times"][phase.value] = datetime.now()
            
            # Notify completion callbacks
            callbacks = self.completion_callbacks.get(phase, [])
            for callback in callbacks:
                try:
                    if asyncio.iscoroutinefunction(callback):
                        await callback(phase)
                    else:
                        callback(phase)
                except Exception as e:
                    logger.error(f"Error in phase completion callback: {e}")
        
        except Exception as e:
            logger.error(f"Error loading models for phase {phase.value}: {e}")
    
    async def _load_phase_models(self, schedule: LoadingSchedule) -> None:
        """Load models according to a phase schedule.
        
        YIELD POINTS: This method contains yield points to ensure health checks
        can respond during phase model loading operations.
        """
        if not schedule.models_to_load:
            return
        
        logger.info(f"Loading {len(schedule.models_to_load)} models for {schedule.phase.value} phase")
        
        # YIELD POINT: Allow health checks before creating semaphore
        await asyncio.sleep(0)
        
        # Create semaphore for concurrent loading control
        semaphore = asyncio.Semaphore(schedule.max_concurrent)
        
        # Create loading tasks
        tasks = []
        for i, model_name in enumerate(schedule.models_to_load):
            # Add delay between model starts
            delay = i * schedule.delay_between_models
            task = asyncio.create_task(
                self._load_model_with_delay(model_name, delay, semaphore, schedule.timeout_per_model)
            )
            tasks.append(task)
            
            # YIELD POINT: Every 2 tasks, yield to allow health checks
            if (i + 1) % 2 == 0:
                await asyncio.sleep(0)
        
        # YIELD POINT: Allow health checks before waiting for all tasks
        await asyncio.sleep(0)
        
        # Wait for all models to load (or timeout)
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # YIELD POINT: Allow health checks after all tasks complete
        await asyncio.sleep(0)
        
        # Log results
        successful = sum(1 for r in results if r is True)
        failed = len(results) - successful
        
        logger.info(f"Phase {schedule.phase.value} loading complete: {successful} successful, {failed} failed")
    
    async def _load_model_with_delay(self, model_name: str, delay: float, 
                                   semaphore: asyncio.Semaphore, timeout: float) -> bool:
        """Load a model with initial delay and concurrency control.
        
        YIELD POINTS: This method contains yield points to ensure health checks
        can respond during model loading with delays.
        """
        # Wait for delay
        if delay > 0:
            await asyncio.sleep(delay)
        
        # YIELD POINT: Allow health checks before acquiring semaphore
        await asyncio.sleep(0)
        
        # Acquire semaphore for concurrency control
        async with semaphore:
            try:
                # YIELD POINT: Allow health checks after acquiring semaphore
                await asyncio.sleep(0)
                
                # Load model with timeout
                return await asyncio.wait_for(
                    self.model_manager.force_load_model(model_name),
                    timeout=timeout
                )
            except asyncio.TimeoutError:
                logger.warning(f"Timeout loading model {model_name}")
                return False
            except Exception as e:
                logger.error(f"Error loading model {model_name}: {e}")
                return False
    
    async def _monitor_user_requests(self) -> None:
        """Monitor user requests and prioritize model loading accordingly.
        
        YIELD POINTS: This method contains yield points to ensure health checks
        can respond during user request monitoring.
        """
        try:
            while True:
                await asyncio.sleep(5.0)  # Check every 5 seconds
                
                # YIELD POINT: Allow health checks before processing requests
                await asyncio.sleep(0)
                
                # Process queued user requests
                if self.user_request_queue:
                    await self._process_user_requests()
                
                # YIELD POINT: Allow health checks after processing requests
                await asyncio.sleep(0)
                
                # Update loading strategy based on usage patterns
                await self._update_loading_strategy()
                
        except asyncio.CancelledError:
            logger.info("User request monitoring cancelled")
            raise
        except Exception as e:
            logger.error(f"Error in user request monitoring: {e}")
    
    async def _process_user_requests(self) -> None:
        """Process queued user capability requests.
        
        YIELD POINTS: This method contains yield points to ensure health checks
        can respond during user request processing.
        """
        processed_requests = []
        
        for i, capability in enumerate(self.user_request_queue):
            # Check if capability is available
            if self.model_manager.can_handle_capability(capability):
                processed_requests.append(capability)
                continue
            
            # Find models that provide this capability
            required_models = []
            for model_name, config in self.model_manager.model_configs.items():
                if capability in config.required_for_capabilities:
                    required_models.append(model_name)
            
            # Prioritize loading of required models
            for model_name in required_models:
                if not self.model_manager.is_model_available(model_name):
                    logger.info(f"Prioritizing {model_name} for user-requested capability: {capability}")
                    # Force load this model
                    asyncio.create_task(self.model_manager.force_load_model(model_name))
            
            processed_requests.append(capability)
            
            # YIELD POINT: Every 3 capabilities, yield to allow health checks
            if (i + 1) % 3 == 0:
                await asyncio.sleep(0)
        
        # YIELD POINT: Allow health checks before removing processed requests
        await asyncio.sleep(0)
        
        # Remove processed requests
        for capability in processed_requests:
            if capability in self.user_request_queue:
                self.user_request_queue.remove(capability)
    
    async def _update_loading_strategy(self) -> None:
        """Update loading strategy based on current conditions."""
        # Get current system state
        progress = self.model_manager.get_loading_progress()
        
        # Adjust strategy based on progress and user activity
        if len(self.user_request_queue) > 3:
            # High user demand - be more aggressive
            self.current_strategy = LoadingStrategy.AGGRESSIVE
        elif progress["progress_percent"] > 80:
            # Most models loaded - be conservative
            self.current_strategy = LoadingStrategy.CONSERVATIVE
        else:
            # Normal operation
            self.current_strategy = LoadingStrategy.BALANCED
    
    def request_capability(self, capability: str) -> Dict[str, Any]:
        """Request a capability, triggering prioritized loading if needed."""
        logger.info(f"User requested capability: {capability}")
        
        # Check if capability is immediately available
        if self.model_manager.can_handle_capability(capability):
            return {
                "capability": capability,
                "available": True,
                "models": self.model_manager.get_models_for_capability(capability),
                "wait_time_seconds": 0
            }
        
        # Add to request queue for prioritized loading
        if capability not in self.user_request_queue:
            self.user_request_queue.append(capability)
        
        # Get capability status
        status = self.model_manager.get_capability_status(capability)
        
        # Estimate wait time
        wait_time = self._estimate_capability_wait_time(capability)
        
        return {
            "capability": capability,
            "available": False,
            "status": status,
            "estimated_wait_time_seconds": wait_time,
            "fallback_available": status.get("fallback_available", False)
        }
    
    def _estimate_capability_wait_time(self, capability: str) -> float:
        """Estimate how long until a capability becomes available."""
        total_wait_time = 0.0
        
        # Find models needed for this capability
        for model_name, config in self.model_manager.model_configs.items():
            if capability in config.required_for_capabilities:
                model_instance = self.model_manager.models[model_name]
                
                if model_instance.status == ModelStatus.PENDING:
                    total_wait_time += config.estimated_load_time_seconds
                elif model_instance.status == ModelStatus.LOADING:
                    # Estimate remaining time
                    if model_instance.load_start_time:
                        elapsed = (datetime.now() - model_instance.load_start_time).total_seconds()
                        remaining = max(0, config.estimated_load_time_seconds - elapsed)
                        total_wait_time += remaining
        
        return total_wait_time
    
    def get_loading_progress(self) -> Dict[str, Any]:
        """Get comprehensive loading progress information."""
        model_progress = self.model_manager.get_loading_progress()
        
        # Add phase-specific information
        phase_progress = {}
        for phase, schedule in self.loading_schedules.items():
            models_in_phase = schedule.models_to_load
            loaded_in_phase = sum(
                1 for model_name in models_in_phase
                if self.model_manager.is_model_available(model_name)
            )
            
            phase_progress[phase.value] = {
                "total_models": len(models_in_phase),
                "loaded_models": loaded_in_phase,
                "progress_percent": (loaded_in_phase / len(models_in_phase)) * 100 if models_in_phase else 100,
                "models": models_in_phase,
                "completed": loaded_in_phase == len(models_in_phase)
            }
        
        return {
            "overall": model_progress,
            "by_phase": phase_progress,
            "current_strategy": self.current_strategy.value,
            "user_requests_queued": len(self.user_request_queue),
            "statistics": self.loading_stats
        }
    
    def get_capability_readiness(self) -> Dict[str, Dict[str, Any]]:
        """Get readiness status for all capabilities."""
        capabilities = set()
        
        # Collect all capabilities
        for config in self.model_manager.model_configs.values():
            capabilities.update(config.required_for_capabilities)
        
        # Get status for each capability
        readiness = {}
        for capability in capabilities:
            readiness[capability] = self.model_manager.get_capability_status(capability)
        
        return readiness
    
    def register_progress_callback(self, callback: Callable) -> None:
        """Register a callback for loading progress updates."""
        self.progress_callbacks.append(callback)
    
    def register_phase_completion_callback(self, phase: StartupPhase, callback: Callable) -> None:
        """Register a callback for phase completion."""
        if phase not in self.completion_callbacks:
            self.completion_callbacks[phase] = []
        self.completion_callbacks[phase].append(callback)
    
    def set_loading_strategy(self, strategy: LoadingStrategy) -> None:
        """Set the loading strategy."""
        self.current_strategy = strategy
        logger.info(f"Loading strategy set to: {strategy.value}")
    
    def get_user_experience_metrics(self) -> Dict[str, Any]:
        """Get metrics related to user experience."""
        # Calculate average wait times
        avg_wait_time = (
            sum(self.loading_stats["user_wait_times"]) / len(self.loading_stats["user_wait_times"])
            if self.loading_stats["user_wait_times"] else 0
        )
        
        # Get capability availability
        readiness = self.get_capability_readiness()
        available_capabilities = sum(1 for status in readiness.values() if status["available"])
        total_capabilities = len(readiness)
        
        return {
            "average_user_wait_time_seconds": avg_wait_time,
            "capabilities_available": available_capabilities,
            "total_capabilities": total_capabilities,
            "capability_availability_percent": (available_capabilities / total_capabilities) * 100 if total_capabilities > 0 else 0,
            "user_requests_in_queue": len(self.user_request_queue),
            "loading_strategy": self.current_strategy.value
        }
    
    async def shutdown(self) -> None:
        """Shutdown the progressive loader."""
        logger.info("Shutting down ProgressiveLoader")
        
        # Cancel all loading tasks
        for task in self.loading_tasks.values():
            if not task.done():
                task.cancel()
        
        for task in self.phase_loading_tasks.values():
            if not task.done():
                task.cancel()
        
        # Wait for tasks to complete
        all_tasks = list(self.loading_tasks.values()) + list(self.phase_loading_tasks.values())
        if all_tasks:
            await asyncio.gather(*all_tasks, return_exceptions=True)
        
        # Shutdown model manager
        await self.model_manager.shutdown()
        
        logger.info("ProgressiveLoader shutdown complete")


# Global progressive loader instance
_progressive_loader: Optional[ProgressiveLoader] = None


def get_progressive_loader() -> ProgressiveLoader:
    """Get the global progressive loader instance."""
    global _progressive_loader
    if _progressive_loader is None:
        _progressive_loader = ProgressiveLoader()
    return _progressive_loader


async def initialize_progressive_loader(startup_phase_manager: Optional[StartupPhaseManager] = None) -> ProgressiveLoader:
    """Initialize and start the progressive loader."""
    global _progressive_loader
    _progressive_loader = ProgressiveLoader(startup_phase_manager)
    await _progressive_loader.start_progressive_loading()
    return _progressive_loader