"""
Capability Service

This service manages and advertises system capabilities based on the current
startup phase and loaded models. It provides real-time information about
what features are available and what's still loading.

Key Features:
- Real-time capability advertising
- Loading progress tracking
- Estimated completion times
- Request routing based on capabilities

Updated to use ModelStatusService as the single source of truth for model
availability, replacing the fragmented status tracking.
"""

import logging
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional

from ..logging_config import get_logger
from ..startup.minimal_server import get_minimal_server
from ..startup.phase_manager import StartupPhase
from .realistic_eta_calculator import get_eta_calculator

logger = get_logger("capability_service")


class CapabilityLevel(Enum):
    """Capability levels indicating response quality."""
    BASIC = "basic"           # Simple text responses, limited reasoning
    ENHANCED = "enhanced"     # Some AI features, basic document processing  
    FULL = "full"            # All AI capabilities, advanced analysis


@dataclass
class CapabilityInfo:
    """Information about a specific capability."""
    name: str
    available: bool
    level: CapabilityLevel
    description: str
    estimated_ready_time: Optional[int] = None  # seconds from now
    dependencies: List[str] = None
    quality_indicator: str = ""
    
    def __post_init__(self):
        if self.dependencies is None:
            self.dependencies = []
        
        # Set quality indicator based on level
        if not self.quality_indicator:
            indicators = {
                CapabilityLevel.BASIC: "⚡",
                CapabilityLevel.ENHANCED: "🔄", 
                CapabilityLevel.FULL: "🧠"
            }
            self.quality_indicator = indicators.get(self.level, "❓")


class CapabilityService:
    """Service for managing and advertising system capabilities."""
    
    def __init__(self):
        self.start_time = time.time()
        self._capability_definitions = self._define_capabilities()
        self._model_load_times = self._get_model_load_estimates()
        self.eta_calculator = get_eta_calculator()
        
    def _define_capabilities(self) -> Dict[str, CapabilityInfo]:
        """Define all system capabilities with their requirements."""
        return {
            # Basic capabilities (available immediately)
            "health_check": CapabilityInfo(
                name="health_check",
                available=True,
                level=CapabilityLevel.BASIC,
                description="Monitor system health and status",
                dependencies=[]
            ),
            "simple_text": CapabilityInfo(
                name="simple_text",
                available=True,
                level=CapabilityLevel.BASIC,
                description="Process basic text and provide responses",
                dependencies=[]
            ),
            "status_updates": CapabilityInfo(
                name="status_updates",
                available=True,
                level=CapabilityLevel.BASIC,
                description="Provide real-time system status and progress updates",
                dependencies=[]
            ),
            
            # Enhanced capabilities (require basic models)
            "basic_chat": CapabilityInfo(
                name="basic_chat",
                available=False,
                level=CapabilityLevel.ENHANCED,
                description="Handle basic conversations with simple reasoning",
                dependencies=["chat-model-base", "text-embedding-small"]
            ),
            "simple_search": CapabilityInfo(
                name="simple_search",
                available=False,
                level=CapabilityLevel.ENHANCED,
                description="Search and retrieve basic text content",
                dependencies=["search-index", "text-embedding-small"]
            ),
            "document_upload": CapabilityInfo(
                name="document_upload",
                available=False,
                level=CapabilityLevel.ENHANCED,
                description="Process document uploads and basic analysis",
                dependencies=["document-processor"]
            ),
            
            # Full capabilities (require advanced models)
            "advanced_chat": CapabilityInfo(
                name="advanced_chat",
                available=False,
                level=CapabilityLevel.FULL,
                description="Handle advanced conversations with complex reasoning",
                dependencies=["chat-model-large", "multimodal-model"]
            ),
            "semantic_search": CapabilityInfo(
                name="semantic_search",
                available=False,
                level=CapabilityLevel.FULL,
                description="Analyze and search content semantically",
                dependencies=["multimodal-model", "specialized-analyzers"]
            ),
            "document_analysis": CapabilityInfo(
                name="document_analysis",
                available=False,
                level=CapabilityLevel.FULL,
                description="Analyze and understand advanced document content",
                dependencies=["multimodal-model", "document-processor", "specialized-analyzers"]
            ),
            "complex_reasoning": CapabilityInfo(
                name="complex_reasoning",
                available=False,
                level=CapabilityLevel.FULL,
                description="Process complex multi-step reasoning and analysis",
                dependencies=["chat-model-large", "multimodal-model", "specialized-analyzers"]
            ),
            "multimodal_processing": CapabilityInfo(
                name="multimodal_processing",
                available=False,
                level=CapabilityLevel.FULL,
                description="Process multimodal content including text, images, and media",
                dependencies=["multimodal-model", "specialized-analyzers"]
            )
        }
    
    def _get_model_load_estimates(self) -> Dict[str, int]:
        """Get estimated load times for different models."""
        return {
            "text-embedding-small": 5,      # 5 seconds
            "chat-model-base": 15,           # 15 seconds
            "search-index": 10,              # 10 seconds
            "document-processor": 30,        # 30 seconds
            "chat-model-large": 60,          # 60 seconds
            "multimodal-model": 120,         # 2 minutes
            "specialized-analyzers": 90      # 1.5 minutes
        }
    
    def get_current_capabilities(self) -> Dict[str, CapabilityInfo]:
        """Get current system capabilities with real-time status.
        
        Uses ModelStatusService as the primary source of truth for model
        availability, with fallback to MinimalServer for backward compatibility.
        """
        try:
            # Try to use ModelStatusService first (single source of truth)
            model_status_service = self._get_model_status_service()
            
            if model_status_service is not None:
                return self._get_capabilities_from_model_status_service(model_status_service)
            
            # Fallback to MinimalServer for backward compatibility
            logger.debug("ModelStatusService not available, falling back to MinimalServer")
            return self._get_capabilities_from_minimal_server()
            
        except Exception as e:
            logger.error(f"Error getting current capabilities: {e}")
            # Return basic capabilities only on error
            return {
                name: cap for name, cap in self._capability_definitions.items()
                if cap.level == CapabilityLevel.BASIC
            }
    
    def _get_model_status_service(self):
        """Get the ModelStatusService instance if available."""
        try:
            # First try to get from the DI system's cached instance
            from ..api.dependencies.services import _model_status_service
            if _model_status_service is not None:
                return _model_status_service
            
            # Fallback to the service module's global instance
            from .model_status_service import get_model_status_service
            return get_model_status_service()
        except ImportError:
            return None
        except Exception:
            return None
    
    def _get_capabilities_from_model_status_service(self, model_status_service) -> Dict[str, CapabilityInfo]:
        """Get capabilities using ModelStatusService as the source of truth."""
        capabilities = {}
        
        # Get available capabilities directly from ModelStatusService
        available_capabilities = model_status_service.get_available_capabilities()
        
        for cap_name, capability_def in self._capability_definitions.items():
            # Create a copy of the capability definition
            capability = CapabilityInfo(
                name=capability_def.name,
                available=capability_def.available,
                level=capability_def.level,
                description=capability_def.description,
                estimated_ready_time=capability_def.estimated_ready_time,
                dependencies=capability_def.dependencies.copy() if capability_def.dependencies else [],
                quality_indicator=capability_def.quality_indicator
            )
            
            # Check if capability is available from ModelStatusService
            if cap_name in available_capabilities:
                capability.available = True
            elif capability.level == CapabilityLevel.BASIC:
                # Basic capabilities are always available
                capability.available = True
            else:
                capability.available = False
                # Calculate estimated ready time for unavailable capabilities
                capability.estimated_ready_time = self._calculate_ready_time_from_model_status(
                    capability.dependencies, model_status_service
                )
            
            capabilities[cap_name] = capability
        
        return capabilities
    
    def _calculate_ready_time_from_model_status(self, dependencies: List[str], model_status_service) -> int:
        """Calculate estimated time until capability is ready using ModelStatusService."""
        if not dependencies:
            return 0
        
        max_time = 0
        
        # Map old model names to new model server models
        model_mapping = {
            "text-embedding-small": "embedding",
            "chat-model-base": "nlp",
            "search-index": "embedding",
            "document-processor": "embedding",
            "chat-model-large": "nlp",
            "multimodal-model": "embedding",
            "specialized-analyzers": "nlp"
        }
        
        for dep in dependencies:
            # Map to model server model name
            model_name = model_mapping.get(dep, dep)
            
            if model_status_service.is_model_loaded(model_name):
                continue
            
            # Use realistic ETA calculator for better estimates
            eta, confidence = self.eta_calculator.get_realistic_eta(dep)
            max_time = max(max_time, eta)
        
        return int(max_time)
    
    def _get_capabilities_from_minimal_server(self) -> Dict[str, CapabilityInfo]:
        """Get capabilities using MinimalServer (legacy fallback)."""
        server = get_minimal_server()
        status = server.get_status()
        
        # Update capability availability based on current system state
        capabilities = {}
        
        for cap_name, capability_def in self._capability_definitions.items():
            # Create a copy of the capability definition
            capability = CapabilityInfo(
                name=capability_def.name,
                available=capability_def.available,
                level=capability_def.level,
                description=capability_def.description,
                estimated_ready_time=capability_def.estimated_ready_time,
                dependencies=capability_def.dependencies.copy() if capability_def.dependencies else [],
                quality_indicator=capability_def.quality_indicator
            )
            
            # Check if all dependencies are met
            if capability.dependencies:
                all_loaded = all(
                    status.model_statuses.get(dep) == "loaded" 
                    for dep in capability.dependencies
                )
                capability.available = all_loaded
                
                # Calculate estimated ready time for unavailable capabilities
                if not all_loaded:
                    capability.estimated_ready_time = self._calculate_ready_time(
                        capability.dependencies, status.model_statuses
                    )
            else:
                # Basic capabilities are always available
                capability.available = True
            
            capabilities[cap_name] = capability
        
        return capabilities
    
    def _calculate_ready_time(self, dependencies: List[str], model_statuses: Dict[str, str]) -> int:
        """Calculate estimated time until capability is ready using realistic ETA calculator."""
        max_time = 0
        
        for model in dependencies:
            model_status = model_statuses.get(model, "pending")
            
            if model_status == "loaded":
                continue
            
            # Use realistic ETA calculator for better estimates
            eta, confidence = self.eta_calculator.get_realistic_eta(model)
            max_time = max(max_time, eta)
        
        return int(max_time)
    
    def get_capability_summary(self) -> Dict[str, Any]:
        """Get a summary of current capabilities organized by level."""
        capabilities = self.get_current_capabilities()
        
        summary = {
            "basic": {"available": [], "loading": [], "count": 0},
            "enhanced": {"available": [], "loading": [], "count": 0},
            "full": {"available": [], "loading": [], "count": 0}
        }
        
        # Define capability-specific indicators
        capability_indicators = {
            'health_check': '✅',
            'simple_text': '📝',
            'status_updates': '📊',
            'basic_chat': '💬',
            'simple_search': '🔍',
            'document_upload': '📤',
            'advanced_chat': '🧠',
            'semantic_search': '🎯',
            'document_analysis': '📄',
            'complex_reasoning': '🧮',
            'multimodal_processing': '🎨'
        }
        
        for cap_name, capability in capabilities.items():
            level_key = capability.level.value
            summary[level_key]["count"] += 1
            
            # Use capability-specific indicator if available
            indicator = capability_indicators.get(cap_name, capability.quality_indicator)
            
            if capability.available:
                summary[level_key]["available"].append({
                    "name": cap_name,
                    "description": capability.description,
                    "indicator": indicator
                })
            else:
                summary[level_key]["loading"].append({
                    "name": cap_name,
                    "description": capability.description,
                    "indicator": indicator,
                    "eta_seconds": capability.estimated_ready_time,
                    "progress_percent": self._get_capability_progress(cap_name, capability.dependencies)
                })
        
        # Calculate overall readiness
        total_capabilities = sum(summary[level]["count"] for level in summary)
        available_capabilities = sum(len(summary[level]["available"]) for level in summary)
        
        summary["overall"] = {
            "total_capabilities": total_capabilities,
            "available_capabilities": available_capabilities,
            "readiness_percent": (available_capabilities / total_capabilities * 100) if total_capabilities > 0 else 0,
            "current_level": self._determine_current_level(summary)
        }
        
        return summary
    
    def _get_capability_progress(self, cap_name: str, dependencies: List[str]) -> float:
        """Get progress percentage for a capability based on its dependencies."""
        if not dependencies:
            return 100.0
        
        total_progress = 0.0
        for dep in dependencies:
            progress_info = self.eta_calculator.get_progress_with_eta(dep)
            total_progress += progress_info.get("smoothed_progress", 0)
        
        return total_progress / len(dependencies)
    
    def _determine_current_level(self, summary: Dict[str, Any]) -> str:
        """Determine the current overall capability level."""
        if len(summary["full"]["available"]) > 0:
            return "full"
        elif len(summary["enhanced"]["available"]) > 0:
            return "enhanced"
        else:
            return "basic"
    
    def get_loading_progress(self) -> Dict[str, Any]:
        """Get detailed loading progress information."""
        try:
            server = get_minimal_server()
            status = server.get_status()
            
            # Calculate phase progress
            uptime = status.uptime_seconds
            phase_progress = {
                "minimal": {
                    "target_time": 30,
                    "current_time": min(uptime, 30),
                    "complete": uptime >= 30 or status.health_check_ready,
                    "progress_percent": 100 if (uptime >= 30 or status.health_check_ready) else min(100, (uptime / 30) * 100)
                },
                "essential": {
                    "target_time": 120,
                    "current_time": min(uptime, 120),
                    "complete": uptime >= 120 or any(status.capabilities.values()),
                    "progress_percent": 100 if (uptime >= 120 or any(status.capabilities.values())) else min(100, (uptime / 120) * 100)
                },
                "full": {
                    "target_time": 300,
                    "current_time": min(uptime, 300),
                    "complete": uptime >= 300 or status.status.value == "ready",
                    "progress_percent": 100 if (uptime >= 300 or status.status.value == "ready") else min(100, (uptime / 300) * 100)
                }
            }
            
            # Model loading progress with realistic ETAs
            model_progress = {}
            for model_name, model_status in status.model_statuses.items():
                progress_info = self.eta_calculator.get_progress_with_eta(model_name)
                
                model_progress[model_name] = {
                    "status": model_status,
                    "progress_percent": progress_info["smoothed_progress"],
                    "estimated_time": progress_info["eta_seconds"],
                    "eta_confidence": progress_info["eta_confidence"],
                    "eta_range": progress_info["eta_range"],
                    "velocity": progress_info["velocity"]
                }
            
            # Calculate overall progress using capability-based approach for consistency
            capabilities = self.get_current_capabilities()
            total_caps = len(capabilities)
            available_caps = sum(1 for cap in capabilities.values() if cap.available)
            capability_based_progress = (available_caps / total_caps * 100) if total_caps > 0 else 0
            
            # Use capability-based progress as primary, with phase/model as secondary
            overall_progress = capability_based_progress
            
            return {
                "phase_progress": phase_progress,
                "model_progress": model_progress,
                "overall_progress": overall_progress,
                "estimated_completion": self._estimate_completion_time(status)
            }
            
        except Exception as e:
            logger.error(f"Error getting loading progress: {e}")
            return {
                "phase_progress": {},
                "model_progress": {},
                "overall_progress": 0,
                "estimated_completion": None
            }
    
    def _calculate_overall_progress(self, phase_progress: Dict, model_progress: Dict) -> float:
        """Calculate overall system loading progress."""
        # Weight phases and models
        phase_weight = 0.3
        model_weight = 0.7
        
        # Calculate phase progress (average of all phases)
        if phase_progress:
            phase_avg = sum(p["progress_percent"] for p in phase_progress.values()) / len(phase_progress)
        else:
            phase_avg = 0
        
        # Calculate model progress (average of all models)
        if model_progress:
            model_avg = sum(m["progress_percent"] for m in model_progress.values()) / len(model_progress)
        else:
            model_avg = 0
        
        # If no models are defined yet, use phase progress only
        if not model_progress:
            return phase_avg
        
        return (phase_avg * phase_weight) + (model_avg * model_weight)
    
    def _estimate_completion_time(self, status) -> Optional[str]:
        """Estimate when full system will be ready using realistic ETA calculator."""
        try:
            # Find the model that will take longest to load
            max_remaining_time = 0
            max_confidence = 1.0
            
            for model_name, model_status in status.model_statuses.items():
                if model_status not in ["loaded"]:
                    eta, confidence = self.eta_calculator.get_realistic_eta(model_name)
                    if eta > max_remaining_time:
                        max_remaining_time = eta
                        max_confidence = confidence
            
            if max_remaining_time > 0:
                # Use confidence to adjust the estimate
                # Lower confidence = add buffer time
                buffer_factor = 1.0 + (1.0 - max_confidence) * 0.3
                adjusted_time = max_remaining_time * buffer_factor
                
                completion_time = datetime.now() + timedelta(seconds=adjusted_time)
                return completion_time.isoformat()
            else:
                return None
                
        except Exception as e:
            logger.error(f"Error estimating completion time: {e}")
            return None
    
    def can_handle_request(self, request_type: str, required_capabilities: List[str]) -> Dict[str, Any]:
        """Check if the system can currently handle a specific request type."""
        capabilities = self.get_current_capabilities()
        
        # Check if all required capabilities are available
        available_caps = []
        missing_caps = []
        
        for cap_name in required_capabilities:
            if cap_name in capabilities and capabilities[cap_name].available:
                available_caps.append(cap_name)
            else:
                missing_caps.append(cap_name)
        
        can_handle = len(missing_caps) == 0
        
        # Determine response quality level
        if can_handle:
            # Find the highest level among available capabilities
            levels = [capabilities[cap].level for cap in available_caps]
            if CapabilityLevel.FULL in levels:
                quality_level = CapabilityLevel.FULL
            elif CapabilityLevel.ENHANCED in levels:
                quality_level = CapabilityLevel.ENHANCED
            else:
                quality_level = CapabilityLevel.BASIC
        else:
            quality_level = CapabilityLevel.BASIC  # Fallback level
        
        # Calculate ETA for missing capabilities
        eta_seconds = 0
        if missing_caps:
            for cap_name in missing_caps:
                if cap_name in capabilities:
                    cap_eta = capabilities[cap_name].estimated_ready_time or 0
                    eta_seconds = max(eta_seconds, cap_eta)
        
        return {
            "can_handle": can_handle,
            "quality_level": quality_level.value,
            "quality_indicator": capabilities[available_caps[0]].quality_indicator if available_caps else "⚡",
            "available_capabilities": available_caps,
            "missing_capabilities": missing_caps,
            "eta_seconds": eta_seconds,
            "fallback_available": True,  # We always provide some response
            "recommendation": self._get_handling_recommendation(can_handle, quality_level, eta_seconds)
        }
    
    def _get_handling_recommendation(self, can_handle: bool, quality_level: CapabilityLevel, eta_seconds: int) -> str:
        """Get a recommendation for handling the request."""
        if can_handle:
            if quality_level == CapabilityLevel.FULL:
                return "Process with full capabilities"
            elif quality_level == CapabilityLevel.ENHANCED:
                return "Process with enhanced capabilities"
            else:
                return "Process with basic capabilities"
        else:
            if eta_seconds <= 30:
                return f"Queue request - full capabilities ready in {eta_seconds}s"
            elif eta_seconds <= 120:
                return f"Provide fallback response - full capabilities ready in {eta_seconds//60}m"
            else:
                return "Provide fallback response with clear expectations"


# Global capability service instance
_capability_service = None

def get_capability_service() -> CapabilityService:
    """Get the global capability service instance."""
    global _capability_service
    if _capability_service is None:
        _capability_service = CapabilityService()
    return _capability_service