"""
AI Optimization API Router - Management endpoints for AI optimization

This router provides endpoints for managing AI optimization features including:
- Usage analytics and cost monitoring
- Optimization settings configuration
- Provider performance metrics
- Cost breakdown and recommendations
"""

import logging
from typing import Dict, List, Optional, Any
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query, Body
from pydantic import BaseModel, Field

from ...services.ai_optimization_service import (
    get_ai_optimization_service, 
    AIOptimizationService,
    OptimizationStrategy,
    CostTier
)
from ...services.ai_service import AIProvider

logger = logging.getLogger(__name__)

# Request/Response Models
class OptimizationSettings(BaseModel):
    """AI optimization settings configuration."""
    enable_batching: bool = Field(default=True, description="Enable request batching")
    enable_prompt_optimization: bool = Field(default=True, description="Enable prompt optimization")
    enable_cost_optimization: bool = Field(default=True, description="Enable cost optimization")
    enable_rate_limiting: bool = Field(default=True, description="Enable rate limiting")
    batch_size: int = Field(default=5, ge=1, le=20, description="Batch size for requests")
    batch_timeout: float = Field(default=2.0, ge=0.1, le=10.0, description="Batch timeout in seconds")
    daily_cost_limit: float = Field(default=50.0, ge=0.0, description="Daily cost limit in USD")
    hourly_cost_limit: float = Field(default=5.0, ge=0.0, description="Hourly cost limit in USD")

class ChatRequest(BaseModel):
    """Optimized chat request."""
    messages: List[Dict[str, str]] = Field(..., description="Conversation messages")
    context: Optional[str] = Field(default=None, description="Additional context")
    temperature: float = Field(default=0.7, ge=0.0, le=2.0, description="Response randomness")
    max_tokens: int = Field(default=2048, ge=1, le=8192, description="Maximum response tokens")
    preferred_provider: Optional[str] = Field(default=None, description="Preferred AI provider")
    enable_optimization: bool = Field(default=True, description="Enable optimization")

class BatchChatRequest(BaseModel):
    """Batch chat request."""
    requests: List[ChatRequest] = Field(..., description="List of chat requests")
    enable_optimization: bool = Field(default=True, description="Enable optimization")

class UsageAnalyticsResponse(BaseModel):
    """Usage analytics response."""
    summary: Dict[str, Any]
    provider_performance: Dict[str, Any]
    optimization_settings: Dict[str, Any]
    recommendations: List[str]
    timestamp: str

class CostBreakdownResponse(BaseModel):
    """Cost breakdown response."""
    last_hour: Dict[str, Any]
    last_24_hours: Dict[str, Any]
    last_7_days: Dict[str, Any]
    last_30_days: Dict[str, Any]

class HealthCheckResponse(BaseModel):
    """AI optimization health check response."""
    status: str
    ai_service: Dict[str, Any]
    optimization_features: Dict[str, Any]
    rate_limiting: Dict[str, Any]
    cost_monitoring: Dict[str, Any]
    cache_service: bool
    providers_available: int
    total_requests_tracked: int

# Create router
router = APIRouter(prefix="/api/ai-optimization", tags=["AI Optimization"])

@router.get("/health", response_model=HealthCheckResponse)
async def get_optimization_health():
    """Get AI optimization service health status."""
    try:
        optimization_service = get_ai_optimization_service()
        health_data = await optimization_service.health_check()
        
        return HealthCheckResponse(**health_data)
        
    except Exception as e:
        logger.error(f"AI optimization health check failed: {e}")
        raise HTTPException(status_code=500, detail=f"Health check failed: {str(e)}")

@router.get("/analytics", response_model=UsageAnalyticsResponse)
async def get_usage_analytics():
    """Get comprehensive AI usage analytics."""
    try:
        optimization_service = get_ai_optimization_service()
        analytics = optimization_service.get_usage_analytics()
        
        return UsageAnalyticsResponse(**analytics)
        
    except Exception as e:
        logger.error(f"Failed to get usage analytics: {e}")
        raise HTTPException(status_code=500, detail=f"Analytics retrieval failed: {str(e)}")

@router.get("/cost-breakdown", response_model=CostBreakdownResponse)
async def get_cost_breakdown():
    """Get detailed cost breakdown by provider and time period."""
    try:
        optimization_service = get_ai_optimization_service()
        cost_data = optimization_service.get_cost_breakdown()
        
        return CostBreakdownResponse(**cost_data)
        
    except Exception as e:
        logger.error(f"Failed to get cost breakdown: {e}")
        raise HTTPException(status_code=500, detail=f"Cost breakdown retrieval failed: {str(e)}")

@router.get("/settings")
async def get_optimization_settings():
    """Get current AI optimization settings."""
    try:
        optimization_service = get_ai_optimization_service()
        
        settings = {
            "enable_batching": optimization_service.enable_batching,
            "enable_prompt_optimization": optimization_service.enable_prompt_optimization,
            "enable_cost_optimization": optimization_service.enable_cost_optimization,
            "enable_rate_limiting": optimization_service.enable_rate_limiting,
            "batch_size": optimization_service.batch_size,
            "batch_timeout": optimization_service.batch_timeout,
            "daily_cost_limit": optimization_service.daily_cost_limit,
            "hourly_cost_limit": optimization_service.hourly_cost_limit
        }
        
        return {
            "status": "success",
            "settings": settings,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Failed to get optimization settings: {e}")
        raise HTTPException(status_code=500, detail=f"Settings retrieval failed: {str(e)}")

@router.put("/settings")
async def update_optimization_settings(settings: OptimizationSettings):
    """Update AI optimization settings."""
    try:
        optimization_service = get_ai_optimization_service()
        
        # Update settings
        optimization_service.enable_batching = settings.enable_batching
        optimization_service.enable_prompt_optimization = settings.enable_prompt_optimization
        optimization_service.enable_cost_optimization = settings.enable_cost_optimization
        optimization_service.enable_rate_limiting = settings.enable_rate_limiting
        optimization_service.batch_size = settings.batch_size
        optimization_service.batch_timeout = settings.batch_timeout
        optimization_service.daily_cost_limit = settings.daily_cost_limit
        optimization_service.hourly_cost_limit = settings.hourly_cost_limit
        
        logger.info("AI optimization settings updated successfully")
        
        return {
            "status": "success",
            "message": "Optimization settings updated successfully",
            "settings": settings.dict(),
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Failed to update optimization settings: {e}")
        raise HTTPException(status_code=500, detail=f"Settings update failed: {str(e)}")

@router.post("/chat/optimized")
async def generate_optimized_response(request: ChatRequest):
    """Generate AI response with optimization."""
    try:
        optimization_service = get_ai_optimization_service()
        
        # Convert preferred_provider string to enum if provided
        preferred_provider = None
        if request.preferred_provider:
            try:
                preferred_provider = AIProvider(request.preferred_provider.lower())
            except ValueError:
                raise HTTPException(
                    status_code=400, 
                    detail=f"Invalid provider: {request.preferred_provider}"
                )
        
        # Generate optimized response
        response, optimization_result = await optimization_service.optimize_and_generate_response(
            messages=request.messages,
            context=request.context,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
            preferred_provider=preferred_provider,
            enable_optimization=request.enable_optimization
        )
        
        return {
            "status": "success",
            "response": {
                "content": response.content,
                "provider": response.provider,
                "model": response.model,
                "tokens_used": response.tokens_used,
                "processing_time_ms": response.processing_time_ms,
                "confidence_score": response.confidence_score,
                "metadata": response.metadata
            },
            "optimization": {
                "strategy_used": optimization_result.strategy_used.value,
                "tokens_saved": optimization_result.tokens_saved,
                "cost_saved": optimization_result.cost_saved,
                "processing_time_ms": optimization_result.processing_time_ms,
                "success": optimization_result.success,
                "metadata": optimization_result.metadata
            },
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Optimized response generation failed: {e}")
        raise HTTPException(status_code=500, detail=f"Response generation failed: {str(e)}")

@router.post("/chat/batch")
async def generate_batch_responses(request: BatchChatRequest):
    """Generate multiple AI responses with batch optimization."""
    try:
        optimization_service = get_ai_optimization_service()
        
        # Convert requests to the format expected by the service
        batch_requests = []
        for chat_request in request.requests:
            preferred_provider = None
            if chat_request.preferred_provider:
                try:
                    preferred_provider = AIProvider(chat_request.preferred_provider.lower())
                except ValueError:
                    raise HTTPException(
                        status_code=400, 
                        detail=f"Invalid provider: {chat_request.preferred_provider}"
                    )
            
            batch_requests.append({
                "messages": chat_request.messages,
                "context": chat_request.context,
                "temperature": chat_request.temperature,
                "max_tokens": chat_request.max_tokens,
                "preferred_provider": preferred_provider,
                "enable_optimization": chat_request.enable_optimization
            })
        
        # Process batch
        results = await optimization_service.batch_generate_responses(
            batch_requests, 
            enable_optimization=request.enable_optimization
        )
        
        # Format response
        batch_results = []
        total_tokens_saved = 0
        total_cost_saved = 0.0
        successful_requests = 0
        
        for response, optimization_result in results:
            if response is not None:
                successful_requests += 1
                total_tokens_saved += optimization_result.tokens_saved
                total_cost_saved += optimization_result.cost_saved
                
                batch_results.append({
                    "success": True,
                    "response": {
                        "content": response.content,
                        "provider": response.provider,
                        "model": response.model,
                        "tokens_used": response.tokens_used,
                        "processing_time_ms": response.processing_time_ms,
                        "confidence_score": response.confidence_score,
                        "metadata": response.metadata
                    },
                    "optimization": {
                        "strategy_used": optimization_result.strategy_used.value,
                        "tokens_saved": optimization_result.tokens_saved,
                        "cost_saved": optimization_result.cost_saved,
                        "processing_time_ms": optimization_result.processing_time_ms,
                        "success": optimization_result.success,
                        "metadata": optimization_result.metadata
                    }
                })
            else:
                batch_results.append({
                    "success": False,
                    "error": optimization_result.metadata.get("error", "Unknown error"),
                    "optimization": {
                        "strategy_used": optimization_result.strategy_used.value,
                        "tokens_saved": 0,
                        "cost_saved": 0.0,
                        "processing_time_ms": optimization_result.processing_time_ms,
                        "success": False,
                        "metadata": optimization_result.metadata
                    }
                })
        
        return {
            "status": "success",
            "batch_summary": {
                "total_requests": len(request.requests),
                "successful_requests": successful_requests,
                "failed_requests": len(request.requests) - successful_requests,
                "total_tokens_saved": total_tokens_saved,
                "total_cost_saved": round(total_cost_saved, 6),
                "success_rate": round(successful_requests / len(request.requests), 3)
            },
            "results": batch_results,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Batch response generation failed: {e}")
        raise HTTPException(status_code=500, detail=f"Batch processing failed: {str(e)}")

@router.get("/providers")
async def get_provider_info():
    """Get information about available AI providers and their costs."""
    try:
        optimization_service = get_ai_optimization_service()
        
        # Get provider information
        provider_info = {}
        for provider, cost_info in optimization_service.provider_costs.items():
            provider_info[provider.value] = {
                "model": cost_info.model,
                "cost_tier": cost_info.cost_tier.value,
                "input_cost_per_1k_tokens": cost_info.input_cost_per_1k,
                "output_cost_per_1k_tokens": cost_info.output_cost_per_1k,
                "embedding_cost_per_1k_tokens": cost_info.embedding_cost_per_1k,
                "rate_limit_rpm": cost_info.rate_limit_rpm,
                "rate_limit_tpm": cost_info.rate_limit_tpm,
                "available": provider in optimization_service.ai_service.providers
            }
        
        # Get current usage metrics
        usage_metrics = {}
        for provider_key, metrics in optimization_service.usage_metrics.items():
            usage_metrics[provider_key] = {
                "requests_count": metrics.requests_count,
                "total_tokens": metrics.total_tokens,
                "total_cost": round(metrics.total_cost, 6),
                "avg_response_time_ms": round(metrics.avg_response_time_ms, 2),
                "error_rate": round(metrics.error_rate, 3),
                "cache_hit_rate": round(metrics.cache_hit_rate, 3)
            }
        
        return {
            "status": "success",
            "providers": provider_info,
            "usage_metrics": usage_metrics,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Failed to get provider info: {e}")
        raise HTTPException(status_code=500, detail=f"Provider info retrieval failed: {str(e)}")

@router.post("/reset-metrics")
async def reset_usage_metrics():
    """Reset usage metrics and cost tracking."""
    try:
        optimization_service = get_ai_optimization_service()
        
        # Clear metrics
        optimization_service.usage_metrics.clear()
        optimization_service.request_counts.clear()
        optimization_service.cost_alerts_sent.clear()
        
        logger.info("AI optimization metrics reset successfully")
        
        return {
            "status": "success",
            "message": "Usage metrics and cost tracking reset successfully",
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Failed to reset metrics: {e}")
        raise HTTPException(status_code=500, detail=f"Metrics reset failed: {str(e)}")

@router.get("/recommendations")
async def get_optimization_recommendations():
    """Get AI optimization recommendations based on usage patterns."""
    try:
        optimization_service = get_ai_optimization_service()
        analytics = optimization_service.get_usage_analytics()
        
        # Generate detailed recommendations
        detailed_recommendations = []
        
        # Cost-based recommendations
        summary = analytics["summary"]
        if summary["daily_cost"] > optimization_service.daily_cost_limit * 0.9:
            detailed_recommendations.append({
                "type": "cost_warning",
                "priority": "high",
                "title": "Daily cost limit approaching",
                "description": f"Current daily cost (${summary['daily_cost']:.2f}) is near the limit (${optimization_service.daily_cost_limit:.2f})",
                "action": "Consider reducing AI usage or switching to cheaper providers"
            })
        
        # Provider-based recommendations
        provider_performance = analytics["provider_performance"]
        if provider_performance:
            # Find most expensive provider
            most_expensive = max(
                provider_performance.items(),
                key=lambda x: x[1]["cost"]
            )
            
            if most_expensive[1]["cost"] > summary["total_cost"] * 0.6:
                detailed_recommendations.append({
                    "type": "cost_optimization",
                    "priority": "medium",
                    "title": f"High usage of expensive provider: {most_expensive[0]}",
                    "description": f"Provider {most_expensive[0]} accounts for {(most_expensive[1]['cost']/summary['total_cost']*100):.1f}% of total costs",
                    "action": "Consider using cheaper alternatives like Gemini for suitable tasks"
                })
            
            # Check for high error rates
            for provider, metrics in provider_performance.items():
                if metrics["error_rate"] > 0.1:  # 10% error rate
                    detailed_recommendations.append({
                        "type": "reliability",
                        "priority": "high",
                        "title": f"High error rate for {provider}",
                        "description": f"Provider {provider} has {metrics['error_rate']*100:.1f}% error rate",
                        "action": "Check provider status or switch to more reliable alternatives"
                    })
        
        # Optimization feature recommendations
        settings = analytics["optimization_settings"]
        if not settings["prompt_optimization_enabled"]:
            detailed_recommendations.append({
                "type": "feature",
                "priority": "low",
                "title": "Prompt optimization disabled",
                "description": "Enabling prompt optimization can reduce token usage and costs",
                "action": "Enable prompt optimization in settings"
            })
        
        if not settings["cost_optimization_enabled"]:
            detailed_recommendations.append({
                "type": "feature",
                "priority": "medium",
                "title": "Cost optimization disabled",
                "description": "Enabling cost optimization can automatically select cheaper providers",
                "action": "Enable cost optimization in settings"
            })
        
        return {
            "status": "success",
            "recommendations": detailed_recommendations,
            "summary_recommendations": analytics["recommendations"],
            "optimization_score": min(100, max(0, 100 - len(detailed_recommendations) * 10)),
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Failed to get recommendations: {e}")
        raise HTTPException(status_code=500, detail=f"Recommendations retrieval failed: {str(e)}")

# Add router description
router.description = """
AI Optimization API provides comprehensive management of AI usage optimization including:

- **Usage Analytics**: Monitor AI usage, costs, and performance metrics
- **Cost Management**: Track spending and set limits with alerts
- **Provider Optimization**: Automatically select optimal providers based on cost and performance
- **Batch Processing**: Efficiently process multiple requests together
- **Rate Limiting**: Graceful handling of API rate limits
- **Prompt Optimization**: Intelligent prompt compression to reduce token usage
- **Recommendations**: Get actionable insights to optimize AI usage

This API helps reduce AI costs while maintaining performance and reliability.
"""