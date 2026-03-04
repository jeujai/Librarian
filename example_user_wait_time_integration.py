#!/usr/bin/env python3
"""
Example: User Wait Time Measurements Integration

This example shows how to integrate user wait time measurements into a FastAPI application
during startup phases.
"""

import asyncio
import logging
from datetime import datetime
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

# Import the startup and monitoring components
from src.multimodal_librarian.startup.phase_manager import StartupPhaseManager, StartupPhase
from src.multimodal_librarian.monitoring.startup_metrics import (
    StartupMetricsCollector, 
    set_global_metrics_collector,
    track_startup_metrics
)
from src.multimodal_librarian.monitoring.performance_tracker import track_performance
from src.multimodal_librarian.api.middleware.user_wait_tracking_middleware import UserWaitTrackingMiddleware

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global components
app = FastAPI(title="Multimodal Librarian with User Wait Time Tracking")
phase_manager = None
metrics_collector = None
performance_tracker = None


@app.on_event("startup")
async def startup_event():
    """Initialize startup tracking and user wait time measurements."""
    global phase_manager, metrics_collector, performance_tracker
    
    logger.info("🚀 Starting application with user wait time tracking")
    
    # Initialize phase manager
    phase_manager = StartupPhaseManager()
    await phase_manager.start_phase_progression()
    
    # Initialize metrics collector with user wait time tracking
    metrics_collector = await track_startup_metrics(phase_manager)
    set_global_metrics_collector(metrics_collector)
    
    # Initialize performance tracker
    performance_tracker = await track_performance(phase_manager, metrics_collector)
    
    logger.info("✅ Startup tracking initialized")


@app.on_event("shutdown")
async def shutdown_event():
    """Clean up tracking components."""
    global phase_manager, metrics_collector, performance_tracker
    
    logger.info("🛑 Shutting down application")
    
    if metrics_collector:
        await metrics_collector.stop_collection()
    
    if performance_tracker:
        await performance_tracker.stop_tracking()
    
    if phase_manager:
        await phase_manager.shutdown()
    
    logger.info("✅ Shutdown complete")


# Add user wait time tracking middleware
app.add_middleware(UserWaitTrackingMiddleware, enabled=True)


@app.get("/api/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "startup_phase": phase_manager.current_phase.value if phase_manager else "unknown"
    }


@app.post("/api/chat")
async def chat_endpoint(message: dict):
    """
    Chat endpoint that demonstrates user wait time tracking.
    
    This endpoint requires chat capabilities and may use fallback responses.
    """
    if not phase_manager:
        raise HTTPException(status_code=503, detail="Service not ready")
    
    current_status = phase_manager.get_current_status()
    
    # Check if chat model is available
    chat_model_available = current_status.model_statuses.get("chat-model-base", {}).get("status") == "loaded"
    
    if chat_model_available:
        # Full AI response
        response = {
            "response": f"AI response to: {message.get('text', '')}",
            "mode": "full_ai",
            "quality": "full",
            "capabilities": ["reasoning", "context", "personality"]
        }
    else:
        # Fallback response during startup
        response = {
            "response": f"I'm starting up my AI models. Basic response to: {message.get('text', '')}",
            "mode": "fallback",
            "quality": "basic",
            "capabilities": ["basic_text"],
            "estimated_full_ready_seconds": 45
        }
        
        # Add fallback headers for middleware detection
        return JSONResponse(
            content=response,
            headers={
                "X-Response-Mode": "fallback",
                "X-Response-Quality": "basic",
                "X-Loading-State": "loading"
            }
        )
    
    return response


@app.get("/api/search")
async def search_endpoint(query: str):
    """
    Search endpoint that demonstrates capability-based responses.
    """
    if not phase_manager:
        raise HTTPException(status_code=503, detail="Service not ready")
    
    current_status = phase_manager.get_current_status()
    
    # Check available search capabilities
    search_available = current_status.model_statuses.get("search-model", {}).get("status") == "loaded"
    embedding_available = current_status.model_statuses.get("embedding-model", {}).get("status") == "loaded"
    
    if search_available and embedding_available:
        # Full semantic search
        results = [
            {"title": f"Result 1 for {query}", "score": 0.95},
            {"title": f"Result 2 for {query}", "score": 0.87},
            {"title": f"Result 3 for {query}", "score": 0.82}
        ]
        response = {
            "results": results,
            "search_type": "semantic",
            "quality": "full"
        }
    elif search_available:
        # Basic text search
        results = [
            {"title": f"Basic result for {query}", "score": 0.75}
        ]
        response = {
            "results": results,
            "search_type": "text",
            "quality": "enhanced"
        }
        
        return JSONResponse(
            content=response,
            headers={
                "X-Response-Mode": "fallback",
                "X-Response-Quality": "enhanced"
            }
        )
    else:
        # Fallback search
        response = {
            "results": [],
            "search_type": "unavailable",
            "quality": "basic",
            "message": "Search capabilities are loading. Please try again in 30 seconds."
        }
        
        return JSONResponse(
            content=response,
            headers={
                "X-Response-Mode": "fallback",
                "X-Response-Quality": "basic",
                "X-Loading-State": "loading"
            }
        )
    
    return response


@app.get("/api/metrics/user-wait-times")
async def get_user_wait_metrics():
    """Get user wait time metrics."""
    if not metrics_collector:
        raise HTTPException(status_code=503, detail="Metrics not available")
    
    return {
        "overall_metrics": metrics_collector.get_user_wait_time_metrics(),
        "user_experience_summary": metrics_collector.get_user_experience_summary(),
        "active_requests": metrics_collector.get_active_user_requests()
    }


@app.get("/api/metrics/startup")
async def get_startup_metrics():
    """Get comprehensive startup metrics including user wait times."""
    if not metrics_collector:
        raise HTTPException(status_code=503, detail="Metrics not available")
    
    return {
        "session_summary": metrics_collector.get_startup_session_summary(),
        "phase_metrics": {
            phase.value: metrics_collector.get_phase_completion_metrics(phase)
            for phase in StartupPhase
        },
        "user_wait_metrics": metrics_collector.get_user_wait_time_metrics(),
        "performance_summary": performance_tracker.get_performance_summary() if performance_tracker else None
    }


async def simulate_user_requests():
    """Simulate user requests to demonstrate wait time tracking."""
    import httpx
    import random
    
    base_url = "http://localhost:8000"
    
    print("🧪 Simulating user requests to test wait time tracking...")
    
    async with httpx.AsyncClient() as client:
        # Simulate various types of requests
        requests = [
            ("POST", "/api/chat", {"json": {"text": "Hello, how are you?"}}),
            ("GET", "/api/search", {"params": {"query": "machine learning"}}),
            ("POST", "/api/chat", {"json": {"text": "What is AI?"}}),
            ("GET", "/api/search", {"params": {"query": "neural networks"}}),
            ("GET", "/api/health", {}),
        ]
        
        for i, (method, endpoint, kwargs) in enumerate(requests):
            try:
                print(f"📤 Request {i+1}: {method} {endpoint}")
                
                if method == "POST":
                    response = await client.post(f"{base_url}{endpoint}", **kwargs)
                else:
                    response = await client.get(f"{base_url}{endpoint}", **kwargs)
                
                print(f"📥 Response {i+1}: {response.status_code}")
                
                # Check for wait tracking headers
                tracking_id = response.headers.get("x-wait-tracking-id")
                fallback_used = response.headers.get("x-fallback-used") == "true"
                
                if tracking_id:
                    print(f"   🔍 Tracking ID: {tracking_id[:8]}...")
                if fallback_used:
                    quality = response.headers.get("x-fallback-quality", "unknown")
                    print(f"   🔄 Fallback used: {quality} quality")
                
                # Random delay between requests
                await asyncio.sleep(random.uniform(0.5, 2.0))
                
            except Exception as e:
                print(f"❌ Request {i+1} failed: {e}")
        
        # Get final metrics
        try:
            response = await client.get(f"{base_url}/api/metrics/user-wait-times")
            if response.status_code == 200:
                metrics = response.json()
                print("\n📊 Final User Wait Time Metrics:")
                
                overall = metrics.get("overall_metrics", {})
                print(f"   • Total requests: {overall.get('sample_count', 0)}")
                print(f"   • Success rate: {overall.get('success_rate', 0):.1%}")
                print(f"   • Fallback usage: {overall.get('fallback_usage_rate', 0):.1%}")
                
                wait_stats = overall.get("wait_time_stats", {})
                if wait_stats:
                    print(f"   • Average wait: {wait_stats.get('mean_seconds', 0):.2f}s")
                    print(f"   • Max wait: {wait_stats.get('max_seconds', 0):.2f}s")
                
                ux_summary = metrics.get("user_experience_summary", {})
                quality = ux_summary.get("user_experience_quality", "unknown")
                print(f"   • User experience quality: {quality}")
                
        except Exception as e:
            print(f"❌ Failed to get final metrics: {e}")


if __name__ == "__main__":
    import uvicorn
    
    print("🚀 Starting Multimodal Librarian with User Wait Time Tracking")
    print("=" * 60)
    print("This example demonstrates:")
    print("• Automatic user wait time tracking via middleware")
    print("• Fallback response detection")
    print("• Capability-based response quality")
    print("• Comprehensive user experience metrics")
    print("=" * 60)
    
    # Start the server
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info"
    )