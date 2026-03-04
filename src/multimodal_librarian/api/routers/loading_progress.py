"""
Loading Progress API Router

This module provides endpoints for tracking loading progress and system capabilities.
It integrates with the capability service to provide real-time information about
what features are available and what's still loading.

Key Features:
- Real-time capability advertising
- Loading progress tracking
- Estimated completion times
- Request queuing status
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse

from ...api.middleware.loading_middleware import get_loading_state_injector
from ...logging_config import get_logger
from ...services.capability_service import get_capability_service
from ...services.realistic_eta_calculator import get_eta_calculator
from ...startup.minimal_server import get_minimal_server

router = APIRouter(prefix="/api/loading", tags=["Loading Progress"])
logger = get_logger("loading_progress_api")


def _get_model_priority(model_name: str) -> str:
    """Get priority level for a model."""
    essential_models = ["embedding", "nlp", "text-embedding-small", "chat-model-base", "search-index"]
    standard_models = ["chat-model-large", "document-processor"]
    
    if model_name in essential_models:
        return "essential"
    elif model_name in standard_models:
        return "standard"
    else:
        return "advanced"


@router.get("/capabilities")
async def get_current_capabilities():
    """
    Get current system capabilities with availability status.
    
    Returns detailed information about what features are currently
    available and what's still loading.
    
    Returns:
        Current capability status organized by level
    """
    try:
        capability_service = get_capability_service()
        capabilities = capability_service.get_current_capabilities()
        summary = capability_service.get_capability_summary()
        
        response = {
            "status": "success",
            "capabilities": {
                name: {
                    "available": cap.available,
                    "level": cap.level.value,
                    "description": cap.description,
                    "quality_indicator": cap.quality_indicator,
                    "estimated_ready_time": cap.estimated_ready_time,
                    "dependencies": cap.dependencies
                }
                for name, cap in capabilities.items()
            },
            "summary": summary,
            "timestamp": datetime.now().isoformat()
        }
        
        return response
        
    except Exception as e:
        logger.error(f"Error getting capabilities: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get capabilities: {str(e)}")


@router.get("/progress")
async def get_loading_progress():
    """
    Get detailed loading progress information.
    
    Returns progress information for startup phases, model loading,
    and overall system readiness.
    
    Returns:
        Detailed loading progress with percentages and ETAs
    """
    try:
        capability_service = get_capability_service()
        progress = capability_service.get_loading_progress()
        
        # Add additional progress metrics
        server = get_minimal_server()
        status = server.get_status()
        
        enhanced_progress = {
            **progress,
            "server_status": {
                "phase": status.status.value,
                "uptime_seconds": status.uptime_seconds,
                "health_check_ready": status.health_check_ready,
                "processed_requests": status.processed_requests,
                "failed_requests": status.failed_requests
            },
            "queue_status": server.get_queue_status(),
            "timestamp": datetime.now().isoformat()
        }
        
        return {
            "status": "success",
            "progress": enhanced_progress
        }
        
    except Exception as e:
        logger.error(f"Error getting loading progress: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get loading progress: {str(e)}")


@router.get("/eta")
async def get_estimated_completion_times():
    """
    Get estimated completion times for different capability levels with realistic ETAs.
    
    Returns ETAs for when basic, enhanced, and full capabilities
    will be available, including confidence intervals.
    
    Returns:
        Estimated completion times for each capability level with confidence scores
    """
    try:
        capability_service = get_capability_service()
        eta_calculator = get_eta_calculator()
        capabilities = capability_service.get_current_capabilities()
        progress = capability_service.get_loading_progress()
        
        # Calculate ETAs for each level with realistic estimates
        level_etas = {
            "basic": {"eta_seconds": 0, "confidence": 1.0, "status": "available"},
            "enhanced": {"eta_seconds": 0, "confidence": 1.0, "status": "available"},
            "full": {"eta_seconds": 0, "confidence": 1.0, "status": "available"}
        }
        
        # Find maximum ETA for each level with confidence
        for cap_name, capability in capabilities.items():
            if not capability.available and capability.dependencies:
                level = capability.level.value
                
                # Get realistic ETA for this capability
                cap_eta_info = eta_calculator.get_capability_eta(
                    cap_name, 
                    capability.dependencies
                )
                
                current_eta = level_etas[level]["eta_seconds"]
                if cap_eta_info["eta_seconds"] > current_eta:
                    level_etas[level] = {
                        "eta_seconds": cap_eta_info["eta_seconds"],
                        "confidence": cap_eta_info["eta_confidence"],
                        "status": cap_eta_info["status"],
                        "eta_range": cap_eta_info.get("eta_range", {})
                    }
        
        # Convert to human-readable format with confidence-aware descriptions
        eta_descriptions = {}
        for level, eta_info in level_etas.items():
            eta_seconds = eta_info["eta_seconds"]
            confidence = eta_info["confidence"]
            
            eta_descriptions[level] = eta_calculator.format_eta_for_display(
                eta_seconds, 
                confidence
            )
        
        response = {
            "status": "success",
            "estimated_completion_times": {
                "basic": {
                    **level_etas["basic"],
                    "description": eta_descriptions["basic"],
                    "indicator": "⚡",
                    "display_text": f"⚡ Basic: {eta_descriptions['basic']}"
                },
                "enhanced": {
                    **level_etas["enhanced"],
                    "description": eta_descriptions["enhanced"],
                    "indicator": "🔄",
                    "display_text": f"🔄 Enhanced: {eta_descriptions['enhanced']}"
                },
                "full": {
                    **level_etas["full"],
                    "description": eta_descriptions["full"],
                    "indicator": "🧠",
                    "display_text": f"🧠 Full AI: {eta_descriptions['full']}"
                }
            },
            "overall_completion": progress.get("estimated_completion"),
            "confidence_note": "ETAs include confidence intervals based on actual loading progress",
            "timestamp": datetime.now().isoformat()
        }
        
        return response
        
    except Exception as e:
        logger.error(f"Error getting ETAs: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get ETAs: {str(e)}")


@router.get("/status")
async def get_loading_status():
    """
    Get comprehensive loading status information.
    
    Combines capability status, progress information, and ETAs
    into a single comprehensive status report. Uses ModelStatusService
    as the source of truth for model availability.
    
    Returns:
        Comprehensive loading status report
    """
    try:
        from ...services.model_status_service import get_model_status_service
        
        capability_service = get_capability_service()
        
        # Get all status information
        capabilities = capability_service.get_current_capabilities()
        summary = capability_service.get_capability_summary()
        progress = capability_service.get_loading_progress()
        
        # Get server status
        server = get_minimal_server()
        server_status = server.get_status()
        
        # Get model status from ModelStatusService (source of truth)
        model_status_service = get_model_status_service()
        model_server_connected = False
        model_server_ready = False
        available_capabilities = []
        
        if model_status_service:
            status_snapshot = model_status_service.get_status_sync()
            model_server_connected = status_snapshot.server_status.value == "connected"
            model_server_ready = status_snapshot.server_ready
            available_capabilities = list(status_snapshot.capabilities)
            
            # Calculate readiness based on actual model server status
            if model_server_ready:
                overall_readiness = 100
            elif model_server_connected:
                # Calculate based on loaded models
                total_models = len(status_snapshot.models)
                loaded_models = len([m for m in status_snapshot.models.values() if m.status == "loaded"])
                overall_readiness = (loaded_models / max(total_models, 1)) * 100
            else:
                overall_readiness = summary["overall"]["readiness_percent"]
        else:
            overall_readiness = summary["overall"]["readiness_percent"]
        
        # Determine overall status based on model server
        if model_server_ready:
            overall_status = "ready"
        elif model_server_connected:
            overall_status = "partially_ready"
        elif overall_readiness >= 25:
            overall_status = "loading"
        else:
            overall_status = "starting"
        
        response = {
            "status": "success",
            "loading_status": {
                "overall_status": overall_status,
                "readiness_percent": overall_readiness,
                "current_level": summary["overall"]["current_level"],
                "server_phase": server_status.status.value,
                "uptime_seconds": server_status.uptime_seconds,
                "model_server": {
                    "connected": model_server_connected,
                    "ready": model_server_ready,
                    "available_capabilities": available_capabilities,
                },
                "capabilities_by_level": {
                    "basic": {
                        "available_count": len(summary["basic"]["available"]),
                        "total_count": summary["basic"]["count"],
                        "ready": len(summary["basic"]["available"]) > 0
                    },
                    "enhanced": {
                        "available_count": len(summary["enhanced"]["available"]),
                        "total_count": summary["enhanced"]["count"],
                        "ready": len(summary["enhanced"]["available"]) > 0
                    },
                    "full": {
                        "available_count": len(summary["full"]["available"]),
                        "total_count": summary["full"]["count"],
                        "ready": len(summary["full"]["available"]) > 0
                    }
                },
                "loading_progress": progress["overall_progress"],
                "estimated_completion": progress.get("estimated_completion"),
                "queue_size": len(server.request_queue) if hasattr(server, 'request_queue') else 0
            },
            "timestamp": datetime.now().isoformat()
        }
        
        return response
        
    except Exception as e:
        logger.error(f"Error getting loading status: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get loading status: {str(e)}")


@router.post("/check-request")
async def check_request_capability(
    request_type: str,
    required_capabilities: List[str] = None
):
    """
    Check if the system can currently handle a specific request type.
    
    Args:
        request_type: Type of request to check
        required_capabilities: List of required capabilities
    
    Returns:
        Capability check result with recommendations
    """
    try:
        if required_capabilities is None:
            required_capabilities = ["basic_chat"]
        
        capability_service = get_capability_service()
        check_result = capability_service.can_handle_request(
            request_type=request_type,
            required_capabilities=required_capabilities
        )
        
        response = {
            "status": "success",
            "request_type": request_type,
            "required_capabilities": required_capabilities,
            "capability_check": check_result,
            "timestamp": datetime.now().isoformat()
        }
        
        return response
        
    except Exception as e:
        logger.error(f"Error checking request capability: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to check request capability: {str(e)}")


@router.get("/queue")
async def get_queue_status():
    """
    Get current request queue status and statistics.
    
    Returns information about pending requests and queue processing.
    
    Returns:
        Request queue status and statistics
    """
    try:
        server = get_minimal_server()
        queue_status = server.get_queue_status()
        server_status = server.get_status()
        
        # Calculate queue metrics
        queue_size = len(server.request_queue) if hasattr(server, 'request_queue') else 0
        processing_rate = (
            server_status.processed_requests / max(server_status.uptime_seconds, 1)
        )
        
        response = {
            "status": "success",
            "queue_status": {
                **queue_status,
                "queue_size": queue_size,
                "processing_rate_per_second": processing_rate,
                "estimated_wait_time": queue_size / max(processing_rate, 0.1),  # Avoid division by zero
                "server_status": server_status.status.value,
                "uptime_seconds": server_status.uptime_seconds
            },
            "timestamp": datetime.now().isoformat()
        }
        
        return response
        
    except Exception as e:
        logger.error(f"Error getting queue status: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get queue status: {str(e)}")


@router.get("/models")
async def get_model_loading_status():
    """
    Get detailed model loading status and progress.
    
    Returns information about individual model loading progress
    and dependencies. Uses ModelStatusService as the source of truth
    for actual model server status.
    
    Returns:
        Detailed model loading status
    """
    try:
        from ...services.model_status_service import get_model_status_service

        # Get model status from the unified ModelStatusService
        model_status_service = get_model_status_service()
        
        if model_status_service:
            # Use ModelStatusService as source of truth
            status_snapshot = model_status_service.get_status_sync()
            
            # Build model info from actual model server status
            model_info = {}
            for model_name, model_data in status_snapshot.models.items():
                # Calculate progress based on status
                if model_data.status == "loaded":
                    progress_percent = 100
                elif model_data.status == "loading":
                    progress_percent = 50  # Approximate
                else:
                    progress_percent = 0
                
                model_info[model_name] = {
                    "status": model_data.status,
                    "progress_percent": progress_percent,
                    "estimated_load_time": model_data.load_time_seconds or 30,
                    "dependencies": [],
                    "size_mb": model_data.memory_mb or "unknown",
                    "device": model_data.device,
                    "model_type": model_data.model_type,
                    "priority": _get_model_priority(model_name),
                    "error_message": model_data.error_message,
                }
            
            # Calculate summary counts
            loaded_count = len([m for m in model_info.values() if m["status"] == "loaded"])
            loading_count = len([m for m in model_info.values() if m["status"] == "loading"])
            failed_count = len([m for m in model_info.values() if m["status"] in ("error", "failed")])
            pending_count = len([m for m in model_info.values() if m["status"] in ("pending", "not_loaded")])
            total_count = len(model_info)
            
            # Calculate overall progress
            if total_count > 0:
                overall_progress = (loaded_count / total_count) * 100
            else:
                overall_progress = 0
            
            response = {
                "status": "success",
                "model_loading_status": {
                    "models": model_info,
                    "summary": {
                        "total_models": total_count,
                        "loaded_models": loaded_count,
                        "loading_models": loading_count,
                        "failed_models": failed_count,
                        "pending_models": pending_count,
                    },
                    "overall_progress": overall_progress,
                    "server_connected": status_snapshot.server_status.value == "connected",
                    "server_ready": status_snapshot.server_ready,
                    "available_capabilities": list(status_snapshot.capabilities),
                },
                "timestamp": datetime.now().isoformat()
            }
        else:
            # Fallback if ModelStatusService not initialized
            response = {
                "status": "success",
                "model_loading_status": {
                    "models": {},
                    "summary": {
                        "total_models": 0,
                        "loaded_models": 0,
                        "loading_models": 0,
                        "failed_models": 0,
                        "pending_models": 0,
                    },
                    "overall_progress": 0,
                    "server_connected": False,
                    "server_ready": False,
                    "available_capabilities": [],
                    "note": "ModelStatusService not initialized"
                },
                "timestamp": datetime.now().isoformat()
            }
        
        return response
        
    except Exception as e:
        logger.error(f"Error getting model loading status: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get model loading status: {str(e)}")


@router.get("/summary")
async def get_loading_summary():
    """
    Get a concise loading summary suitable for UI display.
    
    Returns a simplified status report optimized for frontend
    loading indicators and progress bars.
    
    Returns:
        Concise loading summary for UI display
    """
    try:
        capability_service = get_capability_service()
        summary = capability_service.get_capability_summary()
        progress = capability_service.get_loading_progress()
        
        server = get_minimal_server()
        server_status = server.get_status()
        
        # Create simplified summary
        ui_summary = {
            "overall_progress": progress["overall_progress"],
            "current_level": summary["overall"]["current_level"],
            "level_indicators": {
                "basic": {
                    "ready": len(summary["basic"]["available"]) > 0,
                    "indicator": "⚡",
                    "label": "Basic"
                },
                "enhanced": {
                    "ready": len(summary["enhanced"]["available"]) > 0,
                    "indicator": "🔄",
                    "label": "Enhanced"
                },
                "full": {
                    "ready": len(summary["full"]["available"]) > 0,
                    "indicator": "🧠",
                    "label": "Full AI"
                }
            },
            "status_message": self._get_status_message(summary, server_status),
            "eta_message": self._get_eta_message(progress),
            "show_progress_bar": progress["overall_progress"] < 100,
            "uptime_seconds": server_status.uptime_seconds
        }
        
        response = {
            "status": "success",
            "summary": ui_summary,
            "timestamp": datetime.now().isoformat()
        }
        
        return response
        
    except Exception as e:
        logger.error(f"Error getting loading summary: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get loading summary: {str(e)}")
    
    def _get_status_message(self, summary: Dict, server_status) -> str:
        """Get user-friendly status message."""
        current_level = summary["overall"]["current_level"]
        readiness = summary["overall"]["readiness_percent"]
        
        if readiness >= 90:
            return "🎉 All systems ready!"
        elif current_level == "full":
            return "🧠 Full AI capabilities available"
        elif current_level == "enhanced":
            return "🔄 Enhanced features loading..."
        elif readiness >= 25:
            return "⚡ Basic features ready, more loading..."
        else:
            return "🚀 System starting up..."
    
    def _get_eta_message(self, progress: Dict) -> str:
        """Get user-friendly ETA message."""
        completion = progress.get("estimated_completion")
        if not completion:
            return "Full capabilities ready soon"
        
        try:
            from datetime import datetime
            completion_time = datetime.fromisoformat(completion.replace('Z', '+00:00'))
            now = datetime.now(completion_time.tzinfo)
            
            seconds_remaining = (completion_time - now).total_seconds()
            
            if seconds_remaining <= 30:
                return "Full capabilities ready in seconds"
            elif seconds_remaining <= 120:
                minutes = int(seconds_remaining // 60)
                return f"Full capabilities ready in {minutes} minute{'s' if minutes != 1 else ''}"
            else:
                return "Full capabilities loading..."
                
        except Exception:
            return "Full capabilities ready soon"