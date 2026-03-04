"""
Startup Phase Manager for Multimodal Librarian Application

This module implements a multi-phase startup system that allows the application
to become available quickly while models load in the background.

Key Features:
- Three-phase startup: MINIMAL, ESSENTIAL, FULL
- Progressive model loading with priority classification
- Health check optimization for AWS ECS
- Real-time status tracking and reporting
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


class StartupPhase(Enum):
    """Startup phases for progressive application initialization."""
    MINIMAL = "minimal"      # <30s - Basic API ready
    ESSENTIAL = "essential"  # 1-2min - Core models loaded  
    FULL = "full"           # 3-5min - All models loaded


@dataclass
class PhaseTransition:
    """Represents a phase transition with timing and status information."""
    from_phase: Optional[StartupPhase]
    to_phase: StartupPhase
    started_at: datetime
    completed_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None
    success: bool = False
    error_message: Optional[str] = None
    retry_count: int = 0
    timeout_seconds: float = 300.0  # 5 minute default timeout
    dependencies_met: bool = False
    prerequisites: List[str] = field(default_factory=list)


@dataclass
class PhaseConfiguration:
    """Configuration for a startup phase."""
    phase: StartupPhase
    timeout_seconds: float
    max_retries: int
    prerequisites: List[str]
    required_models: List[str]
    required_capabilities: List[str]
    adaptive_timing: bool = True
    min_duration_seconds: float = 0.0
    max_duration_seconds: float = 300.0


@dataclass
class ResourceDependency:
    """Represents a resource dependency for phase transitions."""
    name: str
    type: str  # "model", "service", "connection", "capability"
    required_for_phases: List[StartupPhase]
    status: str = "pending"  # "pending", "initializing", "ready", "failed"
    last_check: Optional[datetime] = None
    error_message: Optional[str] = None
    retry_count: int = 0
    max_retries: int = 3


@dataclass
class ModelLoadingStatus:
    """Status information for model loading operations."""
    model_name: str
    priority: str  # "essential", "standard", "advanced"
    status: str    # "pending", "loading", "loaded", "failed"
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None
    error_message: Optional[str] = None
    size_mb: Optional[float] = None
    estimated_load_time_seconds: Optional[float] = None


@dataclass
class StartupStatus:
    """Complete startup status information."""
    current_phase: StartupPhase
    phase_start_time: datetime
    total_startup_time: float
    phase_transitions: List[PhaseTransition] = field(default_factory=list)
    model_statuses: Dict[str, ModelLoadingStatus] = field(default_factory=dict)
    capabilities: Dict[str, bool] = field(default_factory=dict)
    estimated_completion_times: Dict[str, float] = field(default_factory=dict)
    health_check_ready: bool = False
    user_requests_ready: bool = False
    resource_dependencies: Dict[str, ResourceDependency] = field(default_factory=dict)
    phase_timeouts: Dict[StartupPhase, float] = field(default_factory=dict)
    adaptive_timing_enabled: bool = True
    last_progress_update: Optional[datetime] = None


class StartupPhaseManager:
    """
    Manages the multi-phase startup process for the Multimodal Librarian application.
    
    This class coordinates the progressive loading of models and services, ensuring
    that basic functionality is available quickly while advanced features load
    in the background.
    """
    
    def __init__(self):
        """Initialize the startup phase manager."""
        self.startup_time = datetime.now()
        self.current_phase = StartupPhase.MINIMAL
        self.phase_start_time = self.startup_time
        self.status = StartupStatus(
            current_phase=StartupPhase.MINIMAL,
            phase_start_time=self.startup_time,
            total_startup_time=0.0,
            last_progress_update=self.startup_time
        )
        
        # Phase configurations with adaptive timing
        self.phase_configs = {
            StartupPhase.MINIMAL: PhaseConfiguration(
                phase=StartupPhase.MINIMAL,
                timeout_seconds=60.0,  # 1 minute max for minimal phase
                max_retries=2,
                prerequisites=["basic_server"],
                required_models=[],
                required_capabilities=["health_endpoints", "basic_api"],
                min_duration_seconds=5.0,  # At least 5 seconds
                max_duration_seconds=60.0
            ),
            StartupPhase.ESSENTIAL: PhaseConfiguration(
                phase=StartupPhase.ESSENTIAL,
                timeout_seconds=180.0,  # 3 minutes max for essential phase
                max_retries=3,
                prerequisites=["minimal_phase_complete"],
                required_models=["text-embedding-small", "chat-model-base", "search-index"],
                required_capabilities=["basic_chat", "simple_search", "text_processing"],
                min_duration_seconds=30.0,  # At least 30 seconds
                max_duration_seconds=180.0
            ),
            StartupPhase.FULL: PhaseConfiguration(
                phase=StartupPhase.FULL,
                timeout_seconds=600.0,  # 10 minutes max for full phase
                max_retries=2,
                prerequisites=["essential_phase_complete"],
                required_models=["chat-model-large", "document-processor", "multimodal-model", "specialized-analyzers"],
                required_capabilities=["advanced_ai", "document_analysis", "multimodal_processing"],
                min_duration_seconds=120.0,  # At least 2 minutes
                max_duration_seconds=600.0
            )
        }
        
        # Phase transition callbacks
        self._phase_callbacks: Dict[StartupPhase, List[Callable]] = {
            StartupPhase.MINIMAL: [],
            StartupPhase.ESSENTIAL: [],
            StartupPhase.FULL: []
        }
        
        # Model loading configuration
        self.model_priorities = {
            "essential": [
                {"name": "text-embedding-small", "size_mb": 50, "estimated_load_time": 5},
                {"name": "chat-model-base", "size_mb": 200, "estimated_load_time": 15},
                {"name": "search-index", "size_mb": 100, "estimated_load_time": 10}
            ],
            "standard": [
                {"name": "chat-model-large", "size_mb": 1000, "estimated_load_time": 60},
                {"name": "document-processor", "size_mb": 500, "estimated_load_time": 30}
            ],
            "advanced": [
                {"name": "multimodal-model", "size_mb": 2000, "estimated_load_time": 120},
                {"name": "specialized-analyzers", "size_mb": 1500, "estimated_load_time": 90}
            ]
        }
        
        # Initialize model statuses
        for priority, models in self.model_priorities.items():
            for model_config in models:
                model_status = ModelLoadingStatus(
                    model_name=model_config["name"],
                    priority=priority,
                    status="pending",
                    size_mb=model_config["size_mb"],
                    estimated_load_time_seconds=model_config["estimated_load_time"]
                )
                self.status.model_statuses[model_config["name"]] = model_status
        
        # Initialize resource dependencies
        self._initialize_resource_dependencies()
        
        # Background tasks
        self._background_tasks: List[asyncio.Task] = []
        self._shutdown_event = asyncio.Event()
        self._phase_transition_lock = asyncio.Lock()
        
        # Timing and monitoring
        self._progress_monitor_task: Optional[asyncio.Task] = None
        self._adaptive_timing_enabled = True
        
        logger.info(f"StartupPhaseManager initialized at {self.startup_time}")
    
    def _initialize_resource_dependencies(self) -> None:
        """Initialize resource dependencies for phase transitions."""
        dependencies = [
            ResourceDependency(
                name="basic_server",
                type="service",
                required_for_phases=[StartupPhase.MINIMAL]
            ),
            ResourceDependency(
                name="minimal_phase_complete",
                type="capability",
                required_for_phases=[StartupPhase.ESSENTIAL]
            ),
            ResourceDependency(
                name="essential_phase_complete",
                type="capability",
                required_for_phases=[StartupPhase.FULL]
            ),
            ResourceDependency(
                name="database_connection",
                type="connection",
                required_for_phases=[StartupPhase.ESSENTIAL, StartupPhase.FULL]
            ),
            ResourceDependency(
                name="aws_secrets_access",
                type="connection",
                required_for_phases=[StartupPhase.ESSENTIAL, StartupPhase.FULL]
            )
        ]
        
        # Add model dependencies
        for priority, models in self.model_priorities.items():
            for model_config in models:
                phases = []
                if priority == "essential":
                    phases = [StartupPhase.ESSENTIAL, StartupPhase.FULL]
                elif priority in ["standard", "advanced"]:
                    phases = [StartupPhase.FULL]
                
                dependency = ResourceDependency(
                    name=model_config["name"],
                    type="model",
                    required_for_phases=phases
                )
                dependencies.append(dependency)
        
        # Store dependencies
        for dep in dependencies:
            self.status.resource_dependencies[dep.name] = dep
    
    async def start_phase_progression(self) -> None:
        """Start the automatic phase progression process with adaptive timing."""
        logger.info("Starting phase progression with adaptive timing")
        
        # Start progress monitoring
        self._progress_monitor_task = asyncio.create_task(self._monitor_progress())
        self._background_tasks.append(self._progress_monitor_task)
        
        # Start with minimal phase (immediate)
        await self._transition_to_phase(StartupPhase.MINIMAL)
        
        # Start model loading in background immediately
        model_loading_task = asyncio.create_task(self._start_model_loading())
        self._background_tasks.append(model_loading_task)
        
        # Schedule adaptive phase transitions
        essential_task = asyncio.create_task(
            self._adaptive_phase_transition(StartupPhase.ESSENTIAL)
        )
        self._background_tasks.append(essential_task)
        
        full_task = asyncio.create_task(
            self._adaptive_phase_transition(StartupPhase.FULL)
        )
        self._background_tasks.append(full_task)
    
    async def _adaptive_phase_transition(self, target_phase: StartupPhase) -> None:
        """Handle adaptive phase transition based on readiness and timing."""
        config = self.phase_configs[target_phase]
        
        try:
            # Wait for minimum duration of current phase
            if target_phase == StartupPhase.ESSENTIAL:
                min_wait = self.phase_configs[StartupPhase.MINIMAL].min_duration_seconds
                await asyncio.sleep(min_wait)
            elif target_phase == StartupPhase.FULL:
                min_wait = self.phase_configs[StartupPhase.ESSENTIAL].min_duration_seconds
                await asyncio.sleep(min_wait)
            
            # Check readiness periodically
            check_interval = 5.0  # Check every 5 seconds
            max_wait_time = config.max_duration_seconds
            start_time = time.time()
            
            while time.time() - start_time < max_wait_time:
                if self._shutdown_event.is_set():
                    return
                
                # Check if we're ready for this phase
                if await self._check_phase_readiness(target_phase):
                    logger.info(f"Prerequisites met for {target_phase.value}, initiating transition")
                    await self._transition_to_phase(target_phase)
                    return
                
                # Wait before next check
                await asyncio.sleep(check_interval)
            
            # Timeout reached - attempt transition anyway with warning
            logger.warning(f"Timeout reached for {target_phase.value} transition, attempting anyway")
            await self._transition_to_phase(target_phase)
            
        except asyncio.CancelledError:
            logger.info(f"Adaptive phase transition to {target_phase.value} cancelled")
            raise
        except Exception as e:
            logger.error(f"Error during adaptive phase transition to {target_phase.value}: {e}")
    
    async def _check_phase_readiness(self, phase: StartupPhase) -> bool:
        """Check if all prerequisites for a phase are met."""
        config = self.phase_configs[phase]
        
        # Check prerequisites
        for prereq in config.prerequisites:
            dependency = self.status.resource_dependencies.get(prereq)
            if not dependency or dependency.status != "ready":
                logger.debug(f"Prerequisite {prereq} not ready for {phase.value}")
                return False
        
        # Check required models (if adaptive timing is enabled)
        if self._adaptive_timing_enabled:
            for model_name in config.required_models:
                model_status = self.status.model_statuses.get(model_name)
                if not model_status or model_status.status != "loaded":
                    logger.debug(f"Required model {model_name} not loaded for {phase.value}")
                    return False
        
        return True
    
    async def _monitor_progress(self) -> None:
        """Monitor startup progress and update status."""
        try:
            while not self._shutdown_event.is_set():
                await self._update_progress_status()
                await asyncio.sleep(2.0)  # Update every 2 seconds
        except asyncio.CancelledError:
            logger.info("Progress monitoring cancelled")
            raise
        except Exception as e:
            logger.error(f"Error in progress monitoring: {e}")
    
    async def _update_progress_status(self) -> None:
        """Update progress status and resource dependencies."""
        current_time = datetime.now()
        self.status.last_progress_update = current_time
        
        # Update resource dependency statuses
        await self._update_resource_dependencies()
        
        # Update phase timeouts
        for phase, config in self.phase_configs.items():
            if phase == self.current_phase:
                elapsed = (current_time - self.phase_start_time).total_seconds()
                remaining = max(0, config.timeout_seconds - elapsed)
                self.status.phase_timeouts[phase] = remaining
        
        # Update estimated completion times based on current progress
        await self._update_estimated_completion_times()
    
    async def _update_resource_dependencies(self) -> None:
        """Update the status of resource dependencies."""
        current_time = datetime.now()
        
        for name, dependency in self.status.resource_dependencies.items():
            dependency.last_check = current_time
            
            # Update dependency status based on type
            if dependency.type == "model":
                model_status = self.status.model_statuses.get(name)
                if model_status:
                    if model_status.status == "loaded":
                        dependency.status = "ready"
                    elif model_status.status == "loading":
                        dependency.status = "initializing"
                    elif model_status.status == "failed":
                        dependency.status = "failed"
                        dependency.error_message = model_status.error_message
            
            elif dependency.type == "capability":
                # Check capability-based dependencies
                if name == "minimal_phase_complete":
                    # This is handled by _mark_phase_complete, don't override here
                    pass
                elif name == "essential_phase_complete":
                    # This is handled by _mark_phase_complete, don't override here
                    pass
            
            elif dependency.type == "service":
                # For now, assume basic services are ready
                # In real implementation, this would check actual service status
                if name == "basic_server":
                    dependency.status = "ready"
            
            elif dependency.type == "connection":
                # For now, assume connections are ready
                # In real implementation, this would test actual connections
                dependency.status = "ready"
    
    async def _update_estimated_completion_times(self) -> None:
        """Update estimated completion times based on current progress."""
        current_time = datetime.now()
        
        # Clear old estimates
        self.status.estimated_completion_times.clear()
        
        # Calculate estimates based on current phase and model loading progress
        if self.current_phase == StartupPhase.MINIMAL:
            # Estimate time to essential phase
            essential_models = [m for m in self.status.model_statuses.values() if m.priority == "essential"]
            essential_time = sum(
                m.estimated_load_time_seconds for m in essential_models 
                if m.status in ["pending", "loading"]
            )
            self.status.estimated_completion_times["essential_capabilities"] = essential_time + 30
            
            # Estimate time to full capabilities
            all_remaining_models = [
                m for m in self.status.model_statuses.values() 
                if m.status in ["pending", "loading"]
            ]
            full_time = sum(m.estimated_load_time_seconds for m in all_remaining_models)
            self.status.estimated_completion_times["full_capabilities"] = full_time + 60
        
        elif self.current_phase == StartupPhase.ESSENTIAL:
            # Estimate time to full capabilities
            remaining_models = [
                m for m in self.status.model_statuses.values() 
                if m.status in ["pending", "loading"] and m.priority in ["standard", "advanced"]
            ]
            full_time = sum(m.estimated_load_time_seconds for m in remaining_models)
            self.status.estimated_completion_times["full_capabilities"] = full_time + 30

    
    async def _transition_to_phase(self, target_phase: StartupPhase) -> None:
        """Transition to a new startup phase with enhanced error handling and retry logic."""
        # Always initialize the phase, even if we're already in it (for startup case)
        should_initialize = target_phase == self.current_phase and len(self.status.phase_transitions) == 0
        
        if target_phase == self.current_phase and not should_initialize:
            return
        
        async with self._phase_transition_lock:
            config = self.phase_configs[target_phase]
            previous_phase = self.current_phase
            transition_start = datetime.now()
            
            # Create transition record
            transition = PhaseTransition(
                from_phase=previous_phase,
                to_phase=target_phase,
                started_at=transition_start,
                timeout_seconds=config.timeout_seconds,
                prerequisites=config.prerequisites.copy()
            )
            
            # Log phase transition start
            try:
                from ..logging.startup_logger import log_phase_transition_start
                log_phase_transition_start(previous_phase, target_phase)
            except ImportError:
                pass  # Startup logger not available
            
            logger.info(f"Transitioning from {previous_phase.value} to {target_phase.value}")
            
            # Attempt transition with retries
            for attempt in range(config.max_retries + 1):
                try:
                    transition.retry_count = attempt
                    
                    # Check prerequisites
                    if not await self._verify_prerequisites(target_phase):
                        if attempt < config.max_retries:
                            # For minimal phase, don't wait as long since it should be immediate
                            wait_time = 2.0 if target_phase == StartupPhase.MINIMAL else 10.0
                            logger.warning(f"Prerequisites not met for {target_phase.value}, retrying in {wait_time}s (attempt {attempt + 1})")
                            await asyncio.sleep(wait_time)
                            continue
                        else:
                            raise Exception("Prerequisites not met after maximum retries")
                    
                    transition.dependencies_met = True
                    
                    # Update current phase
                    self.current_phase = target_phase
                    self.phase_start_time = transition_start
                    self.status.current_phase = target_phase
                    self.status.phase_start_time = transition_start
                    
                    # Execute phase-specific initialization
                    await self._initialize_phase(target_phase)
                    
                    # Mark transition as successful
                    transition.completed_at = datetime.now()
                    transition.duration_seconds = (transition.completed_at - transition.started_at).total_seconds()
                    transition.success = True
                    
                    # Execute callbacks
                    await self._execute_phase_callbacks(target_phase)
                    
                    # Update resource dependencies
                    await self._mark_phase_complete(target_phase)
                    
                    logger.info(f"Successfully transitioned to {target_phase.value} in {transition.duration_seconds:.2f}s")
                    break
                    
                except Exception as e:
                    error_msg = f"Attempt {attempt + 1} failed: {str(e)}"
                    logger.error(f"Phase transition error: {error_msg}")
                    
                    if attempt < config.max_retries:
                        # Wait before retry with exponential backoff
                        wait_time = min(30, 5 * (2 ** attempt))
                        logger.info(f"Retrying phase transition in {wait_time}s")
                        await asyncio.sleep(wait_time)
                    else:
                        # Final failure
                        transition.completed_at = datetime.now()
                        transition.duration_seconds = (transition.completed_at - transition.started_at).total_seconds()
                        transition.success = False
                        transition.error_message = error_msg
                        
                        logger.error(f"Failed to transition to {target_phase.value} after {config.max_retries + 1} attempts")
                        raise
            
            # Log phase transition completion
            try:
                from ..logging.startup_logger import log_phase_transition_complete
                log_phase_transition_complete(transition)
            except ImportError:
                pass  # Startup logger not available
            
            # Record transition
            self.status.phase_transitions.append(transition)
    
    async def _verify_prerequisites(self, phase: StartupPhase) -> bool:
        """Verify that all prerequisites for a phase are met."""
        config = self.phase_configs[phase]
        
        for prereq in config.prerequisites:
            dependency = self.status.resource_dependencies.get(prereq)
            if not dependency:
                logger.warning(f"Unknown prerequisite: {prereq}")
                return False
            
            # Special handling for minimal phase - basic_server should be immediately ready
            if phase == StartupPhase.MINIMAL and prereq == "basic_server":
                dependency.status = "ready"
                continue
            
            if dependency.status not in ["ready", "initializing"]:
                logger.debug(f"Prerequisite {prereq} status: {dependency.status}")
                return False
        
        return True
    
    async def _execute_phase_callbacks(self, phase: StartupPhase) -> None:
        """Execute callbacks for a phase with error handling."""
        callbacks = self._phase_callbacks.get(phase, [])
        
        for callback in callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback()
                else:
                    callback()
            except Exception as e:
                logger.error(f"Error in phase callback for {phase.value}: {e}")
                # Continue with other callbacks even if one fails
    
    async def _mark_phase_complete(self, phase: StartupPhase) -> None:
        """Mark a phase as complete in resource dependencies."""
        if phase == StartupPhase.MINIMAL:
            dep = self.status.resource_dependencies.get("minimal_phase_complete")
            if dep:
                dep.status = "ready"
                logger.info("Marked minimal_phase_complete as ready")
        elif phase == StartupPhase.ESSENTIAL:
            dep = self.status.resource_dependencies.get("essential_phase_complete")
            if dep:
                dep.status = "ready"
                logger.info("Marked essential_phase_complete as ready")
    
    async def _initialize_phase(self, phase: StartupPhase) -> None:
        """Initialize phase-specific functionality."""
        if phase == StartupPhase.MINIMAL:
            await self._initialize_minimal_phase()
        elif phase == StartupPhase.ESSENTIAL:
            await self._initialize_essential_phase()
        elif phase == StartupPhase.FULL:
            await self._initialize_full_phase()
    
    async def _initialize_minimal_phase(self) -> None:
        """Initialize minimal phase - basic HTTP server ready."""
        logger.info("Initializing minimal phase")
        
        # Update capabilities
        self.status.capabilities.update({
            "health_endpoints": True,
            "basic_api": True,
            "status_reporting": True,
            "request_queuing": True
        })
        
        # Mark health check as ready
        self.status.health_check_ready = True
        
        # Basic user requests can be handled (with fallback responses)
        self.status.user_requests_ready = True
        
        logger.info("Minimal phase initialized - health checks ready")
    
    async def _initialize_essential_phase(self) -> None:
        """Initialize essential phase - core models loading."""
        logger.info("Initializing essential phase")
        
        # Update capabilities
        self.status.capabilities.update({
            "basic_chat": True,
            "simple_search": True,
            "text_processing": True
        })
        
        # Update estimated completion times
        self.status.estimated_completion_times.update({
            "full_ai_capabilities": 180.0,  # 3 minutes from now
            "document_analysis": 240.0,     # 4 minutes from now
            "advanced_search": 120.0        # 2 minutes from now
        })
        
        logger.info("Essential phase initialized - core capabilities available")
    
    async def _initialize_full_phase(self) -> None:
        """Initialize full phase - all models loaded."""
        logger.info("Initializing full phase")
        
        # Update capabilities
        self.status.capabilities.update({
            "advanced_ai": True,
            "document_analysis": True,
            "multimodal_processing": True,
            "complex_reasoning": True,
            "specialized_analysis": True
        })
        
        # Clear estimated completion times (everything is ready)
        self.status.estimated_completion_times.clear()
        
        logger.info("Full phase initialized - all capabilities available")
    
    async def _start_model_loading(self) -> None:
        """Start background model loading process."""
        logger.info("Starting background model loading")
        
        try:
            # Load essential models first
            await self._load_models_by_priority("essential")
            
            # Wait a bit before loading standard models
            await asyncio.sleep(10)
            await self._load_models_by_priority("standard")
            
            # Wait a bit before loading advanced models
            await asyncio.sleep(20)
            await self._load_models_by_priority("advanced")
            
        except asyncio.CancelledError:
            logger.info("Model loading cancelled")
            raise
        except Exception as e:
            logger.error(f"Error during model loading: {e}")
    
    async def _load_models_by_priority(self, priority: str) -> None:
        """Load models of a specific priority level."""
        models = self.model_priorities.get(priority, [])
        if not models:
            return
        
        logger.info(f"Loading {priority} priority models: {[m['name'] for m in models]}")
        
        # Load models in parallel for better performance
        tasks = []
        for model_config in models:
            task = asyncio.create_task(self._load_single_model(model_config))
            tasks.append(task)
        
        # Wait for all models in this priority to complete
        await asyncio.gather(*tasks, return_exceptions=True)
        
        logger.info(f"Completed loading {priority} priority models")
    
    async def _load_single_model(self, model_config: Dict[str, Any]) -> None:
        """Load a single model using the real model loader."""
        model_name = model_config["name"]
        model_status = self.status.model_statuses[model_name]
        
        # Log model loading start
        try:
            from ..logging.startup_logger import log_model_loading_start
            log_model_loading_start(model_name, model_status)
        except ImportError:
            pass  # Startup logger not available
        
        logger.info(f"Starting to load model: {model_name}")
        
        # Update status to loading
        model_status.status = "loading"
        model_status.started_at = datetime.now()
        
        try:
            # Use the real async model loader (non-blocking)
            from ..models.real_model_loader import load_model_async

            # Determine model type from name
            if "embedding" in model_name.lower() or model_name == "search-index":
                model_type = "embedding"
            elif "chat" in model_name.lower():
                model_type = "chat"
            elif "document" in model_name.lower():
                model_type = "document_processor"
            else:
                model_type = "unknown"
            
            # Load the model asynchronously (runs in thread pool, doesn't block)
            result = await load_model_async(model_name, model_type)
            
            if result.get("status") == "loaded":
                # Mark as loaded
                model_status.status = "loaded"
                model_status.completed_at = datetime.now()
                model_status.duration_seconds = (
                    model_status.completed_at - model_status.started_at
                ).total_seconds()
                
                logger.info(f"Successfully loaded model {model_name} in {model_status.duration_seconds:.2f}s")
            else:
                # Mark as failed but don't raise - graceful degradation
                model_status.status = "failed"
                model_status.completed_at = datetime.now()
                model_status.error_message = result.get("error", "Unknown error")
                model_status.duration_seconds = (
                    model_status.completed_at - model_status.started_at
                ).total_seconds()
                
                logger.warning(f"Model {model_name} failed to load: {model_status.error_message}")
            
        except Exception as e:
            # Mark as failed
            model_status.status = "failed"
            model_status.completed_at = datetime.now()
            model_status.error_message = str(e)
            model_status.duration_seconds = (
                model_status.completed_at - model_status.started_at
            ).total_seconds()
            
            logger.error(f"Failed to load model {model_name}: {e}")
        
        # Log model loading completion
        try:
            from ..logging.startup_logger import log_model_loading_complete
            log_model_loading_complete(model_name, model_status)
        except ImportError:
            pass  # Startup logger not available
    
    def register_phase_callback(self, phase: StartupPhase, callback: Callable) -> None:
        """Register a callback to be executed when a phase is reached."""
        self._phase_callbacks[phase].append(callback)
        logger.info(f"Registered callback for phase {phase.value}")
    
    def get_current_status(self) -> StartupStatus:
        """Get the current startup status."""
        # Update total startup time
        self.status.total_startup_time = (datetime.now() - self.startup_time).total_seconds()
        return self.status
    
    def get_phase_progress(self) -> Dict[str, Any]:
        """Get detailed phase progress information with enhanced timing data."""
        current_time = datetime.now()
        phase_duration = (current_time - self.phase_start_time).total_seconds()
        total_duration = (current_time - self.startup_time).total_seconds()
        
        # Get current phase configuration
        current_config = self.phase_configs[self.current_phase]
        phase_timeout_remaining = max(0, current_config.timeout_seconds - phase_duration)
        
        # Calculate model loading progress
        model_progress = {}
        for priority in ["essential", "standard", "advanced"]:
            priority_models = [
                status for status in self.status.model_statuses.values()
                if status.priority == priority
            ]
            
            if priority_models:
                loaded_count = sum(1 for m in priority_models if m.status == "loaded")
                loading_count = sum(1 for m in priority_models if m.status == "loading")
                failed_count = sum(1 for m in priority_models if m.status == "failed")
                total_count = len(priority_models)
                progress_percent = (loaded_count / total_count) * 100
                
                model_progress[priority] = {
                    "loaded": loaded_count,
                    "loading": loading_count,
                    "failed": failed_count,
                    "total": total_count,
                    "progress_percent": progress_percent,
                    "models": [
                        {
                            "name": m.model_name,
                            "status": m.status,
                            "duration": m.duration_seconds,
                            "estimated_time": m.estimated_load_time_seconds,
                            "error": m.error_message
                        }
                        for m in priority_models
                    ]
                }
        
        # Calculate overall progress
        all_models = list(self.status.model_statuses.values())
        overall_loaded = sum(1 for m in all_models if m.status == "loaded")
        overall_total = len(all_models)
        overall_progress = (overall_loaded / overall_total) * 100 if overall_total > 0 else 0
        
        # Get resource dependency status
        dependency_status = {}
        for name, dep in self.status.resource_dependencies.items():
            dependency_status[name] = {
                "status": dep.status,
                "type": dep.type,
                "required_for": [p.value for p in dep.required_for_phases],
                "last_check": dep.last_check.isoformat() if dep.last_check else None,
                "error": dep.error_message,
                "retry_count": dep.retry_count
            }
        
        return {
            "current_phase": self.current_phase.value,
            "phase_duration_seconds": phase_duration,
            "phase_timeout_remaining_seconds": phase_timeout_remaining,
            "total_duration_seconds": total_duration,
            "overall_progress_percent": overall_progress,
            "health_check_ready": self.status.health_check_ready,
            "user_requests_ready": self.status.user_requests_ready,
            "capabilities": self.status.capabilities,
            "estimated_completion_times": self.status.estimated_completion_times,
            "model_loading_progress": model_progress,
            "resource_dependencies": dependency_status,
            "adaptive_timing_enabled": self._adaptive_timing_enabled,
            "last_progress_update": self.status.last_progress_update.isoformat() if self.status.last_progress_update else None,
            "phase_transitions": [
                {
                    "from_phase": t.from_phase.value if t.from_phase else None,
                    "to_phase": t.to_phase.value,
                    "duration_seconds": t.duration_seconds,
                    "success": t.success,
                    "error": t.error_message,
                    "retry_count": t.retry_count,
                    "dependencies_met": t.dependencies_met,
                    "started_at": t.started_at.isoformat(),
                    "completed_at": t.completed_at.isoformat() if t.completed_at else None
                }
                for t in self.status.phase_transitions
            ]
        }
    
    def get_timing_metrics(self) -> Dict[str, Any]:
        """Get detailed timing metrics for monitoring and optimization."""
        current_time = datetime.now()
        
        # Phase timing metrics
        phase_metrics = {}
        for phase, config in self.phase_configs.items():
            transitions = [t for t in self.status.phase_transitions if t.to_phase == phase]
            
            if transitions:
                latest_transition = transitions[-1]
                phase_metrics[phase.value] = {
                    "configured_timeout": config.timeout_seconds,
                    "min_duration": config.min_duration_seconds,
                    "max_duration": config.max_duration_seconds,
                    "actual_duration": latest_transition.duration_seconds,
                    "success": latest_transition.success,
                    "retry_count": latest_transition.retry_count,
                    "within_timeout": latest_transition.duration_seconds <= config.timeout_seconds if latest_transition.duration_seconds else False
                }
        
        # Model loading timing
        model_timing = {}
        for model_name, status in self.status.model_statuses.items():
            model_timing[model_name] = {
                "estimated_time": status.estimated_load_time_seconds,
                "actual_time": status.duration_seconds,
                "efficiency_ratio": (status.estimated_load_time_seconds / status.duration_seconds) if status.duration_seconds else None,
                "status": status.status
            }
        
        return {
            "total_startup_time": (current_time - self.startup_time).total_seconds(),
            "current_phase_duration": (current_time - self.phase_start_time).total_seconds(),
            "phase_metrics": phase_metrics,
            "model_timing": model_timing,
            "adaptive_timing_enabled": self._adaptive_timing_enabled
        }
    
    def set_adaptive_timing(self, enabled: bool) -> None:
        """Enable or disable adaptive timing for phase transitions."""
        self._adaptive_timing_enabled = enabled
        self.status.adaptive_timing_enabled = enabled
        logger.info(f"Adaptive timing {'enabled' if enabled else 'disabled'}")
    
    def update_phase_timeout(self, phase: StartupPhase, timeout_seconds: float) -> None:
        """Update the timeout for a specific phase."""
        if phase in self.phase_configs:
            old_timeout = self.phase_configs[phase].timeout_seconds
            self.phase_configs[phase].timeout_seconds = timeout_seconds
            logger.info(f"Updated {phase.value} timeout from {old_timeout}s to {timeout_seconds}s")
        else:
            logger.warning(f"Unknown phase: {phase}")
    
    def force_phase_transition(self, target_phase: StartupPhase) -> asyncio.Task:
        """Force an immediate phase transition (for emergency situations)."""
        logger.warning(f"Forcing immediate transition to {target_phase.value}")
        return asyncio.create_task(self._transition_to_phase(target_phase))
    
    async def wait_for_phase(self, target_phase: StartupPhase, timeout_seconds: Optional[float] = None) -> bool:
        """Wait for a specific phase to be reached."""
        if self.current_phase == target_phase:
            return True
        
        start_time = time.time()
        check_interval = 1.0
        
        while timeout_seconds is None or (time.time() - start_time) < timeout_seconds:
            if self.current_phase == target_phase:
                return True
            
            if self._shutdown_event.is_set():
                return False
            
            await asyncio.sleep(check_interval)
        
        return False
    
    def get_phase_health_status(self) -> Dict[str, Any]:
        """Get health status information optimized for health checks."""
        current_time = datetime.now()
        phase_duration = (current_time - self.phase_start_time).total_seconds()
        config = self.phase_configs[self.current_phase]
        
        # Determine health status
        is_healthy = True
        health_issues = []
        
        # Check if phase is taking too long
        if phase_duration > config.timeout_seconds:
            is_healthy = False
            health_issues.append(f"Phase {self.current_phase.value} exceeded timeout ({phase_duration:.1f}s > {config.timeout_seconds}s)")
        
        # Check for failed models
        failed_models = [m for m in self.status.model_statuses.values() if m.status == "failed"]
        if failed_models:
            critical_failures = [m for m in failed_models if m.priority == "essential"]
            if critical_failures:
                is_healthy = False
                health_issues.append(f"Critical model failures: {[m.model_name for m in critical_failures]}")
        
        # Check resource dependencies
        failed_deps = [d for d in self.status.resource_dependencies.values() if d.status == "failed"]
        if failed_deps:
            is_healthy = False
            health_issues.append(f"Failed dependencies: {[d.name for d in failed_deps]}")
        
        return {
            "healthy": is_healthy,
            "current_phase": self.current_phase.value,
            "phase_duration": phase_duration,
            "timeout_remaining": max(0, config.timeout_seconds - phase_duration),
            "ready_for_traffic": self.status.user_requests_ready,
            "health_check_ready": self.status.health_check_ready,
            "issues": health_issues,
            "capabilities_available": list(self.status.capabilities.keys()),
            "estimated_full_ready_time": self.status.estimated_completion_times.get("full_capabilities", 0)
        }
    
    def is_model_available(self, model_name: str) -> bool:
        """Check if a specific model is available for use."""
        model_status = self.status.model_statuses.get(model_name)
        return model_status is not None and model_status.status == "loaded"
    
    def get_available_capabilities(self) -> Dict[str, bool]:
        """Get currently available capabilities."""
        return self.status.capabilities.copy()
    
    def get_estimated_ready_time(self, capability: str) -> Optional[float]:
        """Get estimated time until a capability is ready (in seconds)."""
        return self.status.estimated_completion_times.get(capability)
    
    async def shutdown(self) -> None:
        """Shutdown the startup phase manager and cleanup resources."""
        logger.info("Shutting down StartupPhaseManager")
        
        # Signal shutdown
        self._shutdown_event.set()
        
        # Cancel all background tasks
        for task in self._background_tasks:
            if not task.done():
                task.cancel()
        
        # Wait for tasks to complete with timeout
        if self._background_tasks:
            try:
                await asyncio.wait_for(
                    asyncio.gather(*self._background_tasks, return_exceptions=True),
                    timeout=10.0
                )
            except asyncio.TimeoutError:
                logger.warning("Some background tasks did not complete within timeout")
        
        logger.info("StartupPhaseManager shutdown complete")


# Global phase manager instance
_phase_manager = None

def get_phase_manager() -> Optional[StartupPhaseManager]:
    """Get the global phase manager instance."""
    global _phase_manager
    return _phase_manager

def set_phase_manager(manager: StartupPhaseManager):
    """Set the global phase manager instance."""
    global _phase_manager
    _phase_manager = manager
