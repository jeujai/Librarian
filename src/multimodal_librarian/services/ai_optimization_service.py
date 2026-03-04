"""
AI Optimization Service - Advanced AI API usage optimization

This service provides intelligent optimization for AI API usage including:
- Request batching for efficiency
- Intelligent prompt optimization
- Cost monitoring and alerting
- Graceful degradation for API limits
- Usage analytics and recommendations
"""

import asyncio
import json
import time
import logging
from typing import Dict, List, Optional, Any, Tuple, Union
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from enum import Enum
import hashlib
import re

from .ai_service_cached import CachedAIService, AIResponse, AIProvider
from .cache_service import get_cache_service, CacheType
from ..config import get_settings

logger = logging.getLogger(__name__)

class OptimizationStrategy(str, Enum):
    """AI optimization strategies."""
    BATCH_REQUESTS = "batch_requests"
    PROMPT_COMPRESSION = "prompt_compression"
    RESPONSE_CACHING = "response_caching"
    PROVIDER_SELECTION = "provider_selection"
    RATE_LIMITING = "rate_limiting"

class CostTier(str, Enum):
    """Cost tiers for different AI providers."""
    LOW = "low"          # Gemini, Claude Haiku
    MEDIUM = "medium"    # GPT-4o-mini, Claude Sonnet
    HIGH = "high"        # GPT-4, Claude Opus
    PREMIUM = "premium"  # GPT-4 Turbo, latest models

@dataclass
class ProviderCostInfo:
    """Cost information for AI providers."""
    provider: str
    model: str
    cost_tier: CostTier
    input_cost_per_1k: float  # Cost per 1K input tokens
    output_cost_per_1k: float  # Cost per 1K output tokens
    embedding_cost_per_1k: float  # Cost per 1K embedding tokens
    rate_limit_rpm: int  # Requests per minute
    rate_limit_tpm: int  # Tokens per minute

@dataclass
class OptimizationResult:
    """Result of AI optimization."""
    original_request: Dict[str, Any]
    optimized_request: Dict[str, Any]
    strategy_used: OptimizationStrategy
    tokens_saved: int
    cost_saved: float
    processing_time_ms: int
    success: bool
    metadata: Dict[str, Any] = None

@dataclass
class UsageMetrics:
    """AI usage metrics for monitoring."""
    provider: str
    model: str
    requests_count: int
    total_tokens: int
    input_tokens: int
    output_tokens: int
    total_cost: float
    avg_response_time_ms: float
    error_rate: float
    cache_hit_rate: float
    timestamp: datetime

class AIOptimizationService:
    """
    Advanced AI optimization service for cost and performance optimization.
    
    Features:
    - Intelligent request batching
    - Prompt optimization and compression
    - Cost monitoring and alerting
    - Provider selection optimization
    - Rate limiting and graceful degradation
    - Usage analytics and recommendations
    """
    
    def __init__(self):
        """Initialize AI optimization service."""
        self.settings = get_settings()
        self.ai_service = CachedAIService()
        self.cache_service = None
        
        # Cost information for providers
        self.provider_costs = {
            AIProvider.GEMINI: ProviderCostInfo(
                provider="gemini",
                model="gemini-2.0-flash-exp",
                cost_tier=CostTier.LOW,
                input_cost_per_1k=0.000075,  # $0.075 per 1M tokens
                output_cost_per_1k=0.0003,   # $0.30 per 1M tokens
                embedding_cost_per_1k=0.00001,  # $0.01 per 1M tokens
                rate_limit_rpm=15,
                rate_limit_tpm=1000000
            ),
            AIProvider.OPENAI: ProviderCostInfo(
                provider="openai",
                model="gpt-4o-mini",
                cost_tier=CostTier.MEDIUM,
                input_cost_per_1k=0.00015,   # $0.15 per 1M tokens
                output_cost_per_1k=0.0006,   # $0.60 per 1M tokens
                embedding_cost_per_1k=0.00002,  # $0.02 per 1M tokens
                rate_limit_rpm=30,
                rate_limit_tpm=200000
            ),
            AIProvider.ANTHROPIC: ProviderCostInfo(
                provider="anthropic",
                model="claude-3-haiku-20240307",
                cost_tier=CostTier.LOW,
                input_cost_per_1k=0.00025,   # $0.25 per 1M tokens
                output_cost_per_1k=0.00125,  # $1.25 per 1M tokens
                embedding_cost_per_1k=0.0,   # No embedding support
                rate_limit_rpm=50,
                rate_limit_tpm=100000
            )
        }
        
        # Usage tracking
        self.usage_metrics = {}
        self.request_queue = []
        self.batch_size = 5
        self.batch_timeout = 2.0  # seconds
        
        # Rate limiting
        self.rate_limits = {}
        self.request_counts = {}
        
        # Cost monitoring
        self.daily_cost_limit = 50.0  # $50 daily limit
        self.hourly_cost_limit = 5.0  # $5 hourly limit
        self.cost_alerts_sent = set()
        
        # Optimization settings
        self.enable_batching = True
        self.enable_prompt_optimization = True
        self.enable_cost_optimization = True
        self.enable_rate_limiting = True
        
        logger.info("AI Optimization Service initialized")
    
    async def _ensure_cache_initialized(self):
        """Ensure cache service is initialized."""
        if self.cache_service is None:
            try:
                self.cache_service = await get_cache_service()
            except Exception as e:
                logger.warning(f"Failed to initialize cache service: {e}")
    
    def _estimate_tokens(self, text: str) -> int:
        """Estimate token count for text."""
        # Rough estimation: ~4 characters per token
        return max(1, len(text) // 4)
    
    def _calculate_cost(
        self, 
        provider: AIProvider, 
        input_tokens: int, 
        output_tokens: int
    ) -> float:
        """Calculate cost for AI request."""
        if provider not in self.provider_costs:
            return 0.0
        
        cost_info = self.provider_costs[provider]
        input_cost = (input_tokens / 1000) * cost_info.input_cost_per_1k
        output_cost = (output_tokens / 1000) * cost_info.output_cost_per_1k
        
        return input_cost + output_cost
    
    def _optimize_prompt(self, messages: List[Dict[str, str]]) -> Tuple[List[Dict[str, str]], int]:
        """
        Optimize prompt for efficiency while maintaining meaning.
        
        Returns:
            Tuple of (optimized_messages, tokens_saved)
        """
        if not self.enable_prompt_optimization:
            return messages, 0
        
        optimized_messages = []
        tokens_saved = 0
        
        for message in messages:
            content = message.get("content", "")
            original_tokens = self._estimate_tokens(content)
            
            # Apply optimization techniques
            optimized_content = self._compress_text(content)
            optimized_tokens = self._estimate_tokens(optimized_content)
            
            tokens_saved += max(0, original_tokens - optimized_tokens)
            
            optimized_messages.append({
                **message,
                "content": optimized_content
            })
        
        return optimized_messages, tokens_saved
    
    def _compress_text(self, text: str) -> str:
        """
        Compress text while maintaining meaning.
        
        Techniques:
        - Remove redundant whitespace
        - Simplify verbose phrases
        - Remove filler words
        - Compress common patterns
        """
        # Remove extra whitespace
        compressed = re.sub(r'\s+', ' ', text.strip())
        
        # Common phrase replacements for efficiency
        replacements = {
            r'\bplease\s+': '',
            r'\bkindly\s+': '',
            r'\bI would like to\b': 'I want to',
            r'\bCould you please\b': 'Can you',
            r'\bWould you mind\b': 'Can you',
            r'\bin order to\b': 'to',
            r'\bdue to the fact that\b': 'because',
            r'\bat this point in time\b': 'now',
            r'\bfor the purpose of\b': 'for',
            r'\bin the event that\b': 'if',
        }
        
        for pattern, replacement in replacements.items():
            compressed = re.sub(pattern, replacement, compressed, flags=re.IGNORECASE)
        
        # Remove redundant punctuation
        compressed = re.sub(r'[.]{2,}', '.', compressed)
        compressed = re.sub(r'[!]{2,}', '!', compressed)
        compressed = re.sub(r'[?]{2,}', '?', compressed)
        
        return compressed.strip()
    
    def _select_optimal_provider(
        self, 
        messages: List[Dict[str, str]], 
        context: Optional[str] = None,
        preferred_provider: Optional[AIProvider] = None
    ) -> AIProvider:
        """
        Select optimal provider based on cost, availability, and performance.
        
        Returns:
            Optimal provider for the request
        """
        if not self.enable_cost_optimization:
            return preferred_provider or self.ai_service.primary_provider
        
        # Calculate estimated tokens
        total_text = " ".join([msg.get("content", "") for msg in messages])
        if context:
            total_text += " " + context
        
        estimated_tokens = self._estimate_tokens(total_text)
        
        # Score providers based on cost and availability
        provider_scores = {}
        
        for provider in self.ai_service.providers.keys():
            if provider not in self.provider_costs:
                continue
            
            cost_info = self.provider_costs[provider]
            
            # Calculate estimated cost
            estimated_cost = self._calculate_cost(provider, estimated_tokens, estimated_tokens // 2)
            
            # Check rate limits
            current_time = time.time()
            provider_key = provider.value
            
            if provider_key in self.request_counts:
                recent_requests = [
                    t for t in self.request_counts[provider_key] 
                    if current_time - t < 60  # Last minute
                ]
                if len(recent_requests) >= cost_info.rate_limit_rpm:
                    continue  # Skip if rate limited
            
            # Calculate score (lower is better)
            score = estimated_cost
            
            # Prefer providers with better performance history
            if provider_key in self.usage_metrics:
                metrics = self.usage_metrics[provider_key]
                if metrics.error_rate < 0.05:  # Less than 5% error rate
                    score *= 0.9  # 10% bonus
                if metrics.cache_hit_rate > 0.5:  # Good cache performance
                    score *= 0.95  # 5% bonus
            
            provider_scores[provider] = score
        
        # Select provider with best score
        if provider_scores:
            optimal_provider = min(provider_scores.keys(), key=lambda p: provider_scores[p])
            logger.debug(f"Selected optimal provider: {optimal_provider.value} (score: {provider_scores[optimal_provider]:.6f})")
            return optimal_provider
        
        # Fallback to preferred or primary provider
        return preferred_provider or self.ai_service.primary_provider
    
    async def _check_rate_limits(self, provider: AIProvider) -> bool:
        """
        Check if provider is within rate limits.
        
        Returns:
            True if within limits, False if rate limited
        """
        if not self.enable_rate_limiting:
            return True
        
        if provider not in self.provider_costs:
            return True
        
        cost_info = self.provider_costs[provider]
        provider_key = provider.value
        current_time = time.time()
        
        # Initialize tracking if needed
        if provider_key not in self.request_counts:
            self.request_counts[provider_key] = []
        
        # Clean old requests (older than 1 minute)
        self.request_counts[provider_key] = [
            t for t in self.request_counts[provider_key] 
            if current_time - t < 60
        ]
        
        # Check if within rate limit
        if len(self.request_counts[provider_key]) >= cost_info.rate_limit_rpm:
            logger.warning(f"Rate limit exceeded for provider {provider_key}")
            return False
        
        return True
    
    async def _track_request(self, provider: AIProvider, response: AIResponse):
        """Track request for rate limiting and metrics."""
        provider_key = provider.value
        current_time = time.time()
        
        # Track for rate limiting
        if provider_key not in self.request_counts:
            self.request_counts[provider_key] = []
        self.request_counts[provider_key].append(current_time)
        
        # Update usage metrics
        if provider_key not in self.usage_metrics:
            self.usage_metrics[provider_key] = UsageMetrics(
                provider=provider_key,
                model=response.model,
                requests_count=0,
                total_tokens=0,
                input_tokens=0,
                output_tokens=0,
                total_cost=0.0,
                avg_response_time_ms=0.0,
                error_rate=0.0,
                cache_hit_rate=0.0,
                timestamp=datetime.utcnow()
            )
        
        metrics = self.usage_metrics[provider_key]
        
        # Update metrics
        metrics.requests_count += 1
        metrics.total_tokens += response.tokens_used
        
        # Estimate input/output tokens (rough approximation)
        estimated_output = response.tokens_used // 3
        estimated_input = response.tokens_used - estimated_output
        
        metrics.input_tokens += estimated_input
        metrics.output_tokens += estimated_output
        
        # Calculate cost
        cost = self._calculate_cost(provider, estimated_input, estimated_output)
        metrics.total_cost += cost
        
        # Update average response time
        metrics.avg_response_time_ms = (
            (metrics.avg_response_time_ms * (metrics.requests_count - 1) + response.processing_time_ms) 
            / metrics.requests_count
        )
        
        metrics.timestamp = datetime.utcnow()
        
        # Check cost alerts
        await self._check_cost_alerts(cost)
    
    async def _check_cost_alerts(self, request_cost: float):
        """Check if cost alerts should be sent."""
        current_hour = datetime.utcnow().replace(minute=0, second=0, microsecond=0)
        current_day = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        
        # Calculate hourly and daily costs
        hourly_cost = sum(
            metrics.total_cost for metrics in self.usage_metrics.values()
            if metrics.timestamp >= current_hour
        )
        
        daily_cost = sum(
            metrics.total_cost for metrics in self.usage_metrics.values()
            if metrics.timestamp >= current_day
        )
        
        # Check hourly limit
        if hourly_cost > self.hourly_cost_limit:
            alert_key = f"hourly_{current_hour.isoformat()}"
            if alert_key not in self.cost_alerts_sent:
                logger.warning(f"Hourly cost limit exceeded: ${hourly_cost:.2f} > ${self.hourly_cost_limit}")
                self.cost_alerts_sent.add(alert_key)
        
        # Check daily limit
        if daily_cost > self.daily_cost_limit:
            alert_key = f"daily_{current_day.isoformat()}"
            if alert_key not in self.cost_alerts_sent:
                logger.error(f"Daily cost limit exceeded: ${daily_cost:.2f} > ${self.daily_cost_limit}")
                self.cost_alerts_sent.add(alert_key)
    
    async def optimize_and_generate_response(
        self,
        messages: List[Dict[str, str]],
        context: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        preferred_provider: Optional[AIProvider] = None,
        enable_optimization: bool = True
    ) -> Tuple[AIResponse, OptimizationResult]:
        """
        Generate AI response with comprehensive optimization.
        
        Args:
            messages: Conversation messages
            context: Additional context
            temperature: Response randomness
            max_tokens: Maximum response tokens
            preferred_provider: Preferred AI provider
            enable_optimization: Whether to apply optimizations
            
        Returns:
            Tuple of (AI response, optimization result)
        """
        start_time = time.time()
        
        # Store original request for comparison
        original_request = {
            "messages": messages.copy(),
            "context": context,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "preferred_provider": preferred_provider.value if preferred_provider else None
        }
        
        optimized_messages = messages
        tokens_saved = 0
        strategy_used = OptimizationStrategy.PROVIDER_SELECTION
        
        try:
            # Apply optimizations if enabled
            if enable_optimization:
                # 1. Optimize prompts
                if self.enable_prompt_optimization:
                    optimized_messages, prompt_tokens_saved = self._optimize_prompt(messages)
                    tokens_saved += prompt_tokens_saved
                    if prompt_tokens_saved > 0:
                        strategy_used = OptimizationStrategy.PROMPT_COMPRESSION
                
                # 2. Select optimal provider
                if self.enable_cost_optimization:
                    optimal_provider = self._select_optimal_provider(
                        optimized_messages, context, preferred_provider
                    )
                else:
                    optimal_provider = preferred_provider or self.ai_service.primary_provider
            else:
                optimal_provider = preferred_provider or self.ai_service.primary_provider
            
            # 3. Check rate limits
            if not await self._check_rate_limits(optimal_provider):
                # Try fallback providers
                for fallback_provider in self.ai_service.fallback_providers:
                    if await self._check_rate_limits(fallback_provider):
                        optimal_provider = fallback_provider
                        strategy_used = OptimizationStrategy.RATE_LIMITING
                        break
                else:
                    # All providers rate limited - implement graceful degradation
                    logger.warning("All providers rate limited - implementing graceful degradation")
                    await asyncio.sleep(1)  # Brief delay
                    optimal_provider = self.ai_service.primary_provider
            
            # 4. Generate response
            response = await self.ai_service.generate_response(
                messages=optimized_messages,
                context=context,
                temperature=temperature,
                max_tokens=max_tokens,
                preferred_provider=optimal_provider
            )
            
            # 5. Track usage
            await self._track_request(optimal_provider, response)
            
            # Calculate optimization results
            processing_time = int((time.time() - start_time) * 1000)
            
            # Estimate cost savings
            original_tokens = sum(self._estimate_tokens(msg.get("content", "")) for msg in messages)
            optimized_tokens = sum(self._estimate_tokens(msg.get("content", "")) for msg in optimized_messages)
            
            cost_saved = 0.0
            if optimal_provider in self.provider_costs:
                cost_info = self.provider_costs[optimal_provider]
                cost_saved = ((original_tokens - optimized_tokens) / 1000) * cost_info.input_cost_per_1k
            
            optimization_result = OptimizationResult(
                original_request=original_request,
                optimized_request={
                    "messages": optimized_messages,
                    "context": context,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                    "selected_provider": optimal_provider.value
                },
                strategy_used=strategy_used,
                tokens_saved=tokens_saved,
                cost_saved=cost_saved,
                processing_time_ms=processing_time,
                success=True,
                metadata={
                    "original_tokens": original_tokens,
                    "optimized_tokens": optimized_tokens,
                    "provider_selected": optimal_provider.value,
                    "rate_limited": False
                }
            )
            
            return response, optimization_result
            
        except Exception as e:
            logger.error(f"Optimized response generation failed: {e}")
            
            # Return error optimization result
            optimization_result = OptimizationResult(
                original_request=original_request,
                optimized_request=original_request,
                strategy_used=strategy_used,
                tokens_saved=0,
                cost_saved=0.0,
                processing_time_ms=int((time.time() - start_time) * 1000),
                success=False,
                metadata={"error": str(e)}
            )
            
            raise e
    
    async def batch_generate_responses(
        self,
        request_batch: List[Dict[str, Any]],
        enable_optimization: bool = True
    ) -> List[Tuple[AIResponse, OptimizationResult]]:
        """
        Generate multiple AI responses with batch optimization.
        
        Args:
            request_batch: List of request dictionaries
            enable_optimization: Whether to apply optimizations
            
        Returns:
            List of (response, optimization_result) tuples
        """
        if not self.enable_batching or len(request_batch) == 1:
            # Process individually
            results = []
            for request in request_batch:
                try:
                    result = await self.optimize_and_generate_response(
                        **request, enable_optimization=enable_optimization
                    )
                    results.append(result)
                except Exception as e:
                    logger.error(f"Batch request failed: {e}")
                    # Add error result
                    error_result = (
                        None,
                        OptimizationResult(
                            original_request=request,
                            optimized_request=request,
                            strategy_used=OptimizationStrategy.BATCH_REQUESTS,
                            tokens_saved=0,
                            cost_saved=0.0,
                            processing_time_ms=0,
                            success=False,
                            metadata={"error": str(e)}
                        )
                    )
                    results.append(error_result)
            return results
        
        # Process as batch with optimization
        logger.info(f"Processing batch of {len(request_batch)} requests")
        
        # Group requests by optimal provider
        provider_groups = {}
        for i, request in enumerate(request_batch):
            optimal_provider = self._select_optimal_provider(
                request.get("messages", []),
                request.get("context"),
                request.get("preferred_provider")
            )
            
            if optimal_provider not in provider_groups:
                provider_groups[optimal_provider] = []
            provider_groups[optimal_provider].append((i, request))
        
        # Process each provider group concurrently
        results = [None] * len(request_batch)
        
        async def process_provider_group(provider, group_requests):
            for index, request in group_requests:
                try:
                    result = await self.optimize_and_generate_response(
                        **request, 
                        preferred_provider=provider,
                        enable_optimization=enable_optimization
                    )
                    results[index] = result
                except Exception as e:
                    logger.error(f"Batch request {index} failed: {e}")
                    results[index] = (
                        None,
                        OptimizationResult(
                            original_request=request,
                            optimized_request=request,
                            strategy_used=OptimizationStrategy.BATCH_REQUESTS,
                            tokens_saved=0,
                            cost_saved=0.0,
                            processing_time_ms=0,
                            success=False,
                            metadata={"error": str(e)}
                        )
                    )
        
        # Process all provider groups concurrently
        tasks = [
            process_provider_group(provider, group_requests)
            for provider, group_requests in provider_groups.items()
        ]
        
        await asyncio.gather(*tasks, return_exceptions=True)
        
        return results
    
    def get_usage_analytics(self) -> Dict[str, Any]:
        """Get comprehensive usage analytics."""
        current_time = datetime.utcnow()
        
        # Calculate totals
        total_requests = sum(metrics.requests_count for metrics in self.usage_metrics.values())
        total_tokens = sum(metrics.total_tokens for metrics in self.usage_metrics.values())
        total_cost = sum(metrics.total_cost for metrics in self.usage_metrics.values())
        
        # Calculate hourly and daily costs
        current_hour = current_time.replace(minute=0, second=0, microsecond=0)
        current_day = current_time.replace(hour=0, minute=0, second=0, microsecond=0)
        
        hourly_cost = sum(
            metrics.total_cost for metrics in self.usage_metrics.values()
            if metrics.timestamp >= current_hour
        )
        
        daily_cost = sum(
            metrics.total_cost for metrics in self.usage_metrics.values()
            if metrics.timestamp >= current_day
        )
        
        # Provider performance
        provider_performance = {}
        for provider_key, metrics in self.usage_metrics.items():
            avg_cost_per_request = metrics.total_cost / max(1, metrics.requests_count)
            
            provider_performance[provider_key] = {
                "requests": metrics.requests_count,
                "tokens": metrics.total_tokens,
                "cost": metrics.total_cost,
                "avg_response_time_ms": metrics.avg_response_time_ms,
                "avg_cost_per_request": avg_cost_per_request,
                "error_rate": metrics.error_rate,
                "cache_hit_rate": metrics.cache_hit_rate,
                "cost_tier": self.provider_costs.get(
                    AIProvider(provider_key), 
                    ProviderCostInfo("unknown", "unknown", CostTier.MEDIUM, 0, 0, 0, 0, 0)
                ).cost_tier.value
            }
        
        # Optimization recommendations
        recommendations = []
        
        if total_cost > 0:
            if hourly_cost > self.hourly_cost_limit * 0.8:
                recommendations.append("Consider reducing AI usage - approaching hourly cost limit")
            
            if daily_cost > self.daily_cost_limit * 0.8:
                recommendations.append("Consider reducing AI usage - approaching daily cost limit")
            
            # Find most expensive provider
            if self.usage_metrics:
                most_expensive = max(
                    self.usage_metrics.items(),
                    key=lambda x: x[1].total_cost
                )
                if most_expensive[1].total_cost > total_cost * 0.5:
                    recommendations.append(f"Consider using cheaper alternatives to {most_expensive[0]}")
        
        return {
            "summary": {
                "total_requests": total_requests,
                "total_tokens": total_tokens,
                "total_cost": round(total_cost, 4),
                "hourly_cost": round(hourly_cost, 4),
                "daily_cost": round(daily_cost, 4),
                "cost_limits": {
                    "hourly_limit": self.hourly_cost_limit,
                    "daily_limit": self.daily_cost_limit,
                    "hourly_usage_percent": round((hourly_cost / self.hourly_cost_limit) * 100, 1),
                    "daily_usage_percent": round((daily_cost / self.daily_cost_limit) * 100, 1)
                }
            },
            "provider_performance": provider_performance,
            "optimization_settings": {
                "batching_enabled": self.enable_batching,
                "prompt_optimization_enabled": self.enable_prompt_optimization,
                "cost_optimization_enabled": self.enable_cost_optimization,
                "rate_limiting_enabled": self.enable_rate_limiting,
                "batch_size": self.batch_size,
                "batch_timeout": self.batch_timeout
            },
            "recommendations": recommendations,
            "timestamp": current_time.isoformat()
        }
    
    def get_cost_breakdown(self) -> Dict[str, Any]:
        """Get detailed cost breakdown by provider and time period."""
        current_time = datetime.utcnow()
        
        # Time periods
        periods = {
            "last_hour": current_time - timedelta(hours=1),
            "last_24_hours": current_time - timedelta(hours=24),
            "last_7_days": current_time - timedelta(days=7),
            "last_30_days": current_time - timedelta(days=30)
        }
        
        cost_breakdown = {}
        
        for period_name, start_time in periods.items():
            period_costs = {}
            period_total = 0.0
            
            for provider_key, metrics in self.usage_metrics.items():
                if metrics.timestamp >= start_time:
                    period_costs[provider_key] = metrics.total_cost
                    period_total += metrics.total_cost
            
            cost_breakdown[period_name] = {
                "total": round(period_total, 4),
                "by_provider": {k: round(v, 4) for k, v in period_costs.items()}
            }
        
        return cost_breakdown
    
    async def health_check(self) -> Dict[str, Any]:
        """Perform health check for AI optimization service."""
        await self._ensure_cache_initialized()
        
        # Check AI service health
        ai_status = await self.ai_service.get_enhanced_status()
        
        # Check rate limiting status
        rate_limit_status = {}
        for provider in self.ai_service.providers.keys():
            within_limits = await self._check_rate_limits(provider)
            rate_limit_status[provider.value] = {
                "within_limits": within_limits,
                "recent_requests": len(self.request_counts.get(provider.value, [])),
                "limit_rpm": self.provider_costs.get(provider, ProviderCostInfo("", "", CostTier.MEDIUM, 0, 0, 0, 60, 0)).rate_limit_rpm
            }
        
        # Calculate current costs
        current_hour = datetime.utcnow().replace(minute=0, second=0, microsecond=0)
        current_day = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        
        hourly_cost = sum(
            metrics.total_cost for metrics in self.usage_metrics.values()
            if metrics.timestamp >= current_hour
        )
        
        daily_cost = sum(
            metrics.total_cost for metrics in self.usage_metrics.values()
            if metrics.timestamp >= current_day
        )
        
        return {
            "status": "healthy",
            "ai_service": ai_status,
            "optimization_features": {
                "batching": self.enable_batching,
                "prompt_optimization": self.enable_prompt_optimization,
                "cost_optimization": self.enable_cost_optimization,
                "rate_limiting": self.enable_rate_limiting
            },
            "rate_limiting": rate_limit_status,
            "cost_monitoring": {
                "hourly_cost": round(hourly_cost, 4),
                "daily_cost": round(daily_cost, 4),
                "hourly_limit": self.hourly_cost_limit,
                "daily_limit": self.daily_cost_limit,
                "within_limits": hourly_cost <= self.hourly_cost_limit and daily_cost <= self.daily_cost_limit
            },
            "cache_service": self.cache_service is not None,
            "providers_available": len(self.ai_service.providers),
            "total_requests_tracked": sum(metrics.requests_count for metrics in self.usage_metrics.values())
        }

# Global AI optimization service instance
_ai_optimization_service = None

def get_ai_optimization_service() -> AIOptimizationService:
    """Get global AI optimization service instance."""
    global _ai_optimization_service
    if _ai_optimization_service is None:
        _ai_optimization_service = AIOptimizationService()
    return _ai_optimization_service