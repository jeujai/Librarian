"""
Cache Warmer for Model Cache System

This module implements cache warming strategies to pre-populate the model cache
with frequently used models, reducing startup times and improving user experience.

Key Features:
- Pre-warming of essential models
- Intelligent cache warming based on usage patterns
- Background warming without blocking startup
- Integration with model manager and cache system
"""

import asyncio
import logging
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum

from ..cache.model_cache import ModelCache, get_model_cache
from ..models.model_manager import ModelManager, ModelPriority, get_model_manager

logger = logging.getLogger(__name__)


class WarmingStrategy(Enum):
    """Cache warming strategies."""
    ESSENTIAL_ONLY = "essential_only"      # Warm only essential models
    PRIORITY_BASED = "priority_based"      # Warm based on model priority
    USAGE_BASED = "usage_based"           # Warm based on historical usage
    PREDICTIVE = "predictive"             # Warm based on predicted usage
    FULL = "full"                         # Warm all available models


@dataclass
class WarmingConfig:
    """Configuration for cache warming."""
    strategy: WarmingStrategy = WarmingStrategy.PRIORITY_BASED
    max_concurrent_warming: int = 2
    warming_timeout_seconds: int = 1800  # 30 minutes
    essential_models_only: bool = False
    background_warming: bool = True
    warm_on_startup: bool = True
    usage_history_days: int = 7
    min_usage_count: int = 1
    
    # Model URLs - in production these would come from configuration
    model_urls: Dict[str, str] = field(default_factory=lambda: {
        "text-embedding-small": "https://example.com/models/text-embedding-small.bin",
        "chat-model-base": "https://example.com/models/chat-model-base.bin",
        "search-index": "https://example.com/models/search-index.bin",
        "chat-model-large": "https://example.com/models/chat-model-large.bin",
        "document-processor": "https://example.com/models/document-processor.bin",
        "multimodal-model": "https://example.com/models/multimodal-model.bin",
        "specialized-analyzers": "https://example.com/models/specialized-analyzers.bin"
    })


class CacheWarmer:
    """
    Cache warming system for pre-populating model cache.
    
    This class implements various strategies for warming the model cache
    to reduce startup times and improve user experience.
    """
    
    def __init__(self, config: Optional[WarmingConfig] = None):
        """Initialize the cache warmer."""
        self.config = config or WarmingConfig()
        self.model_cache: Optional[ModelCache] = None
        self.model_manager: Optional[ModelManager] = None
        
        # Warming state
        self.warming_tasks: Dict[str, asyncio.Task] = {}
        self.warming_semaphore = asyncio.Semaphore(self.config.max_concurrent_warming)
        self._shutdown_event = asyncio.Event()
        
        # Statistics
        self.stats = {
            "warming_sessions": 0,
            "models_warmed": 0,
            "warming_failures": 0,
            "total_warming_time": 0.0,
            "cache_hits_after_warming": 0
        }
        
        logger.info(f"CacheWarmer initialized with strategy: {self.config.strategy.value}")
    
    async def initialize(self) -> None:
        """Initialize the cache warmer."""
        try:
            # Get cache and model manager instances
            self.model_cache = get_model_cache()
            self.model_manager = get_model_manager()
            
            logger.info("CacheWarmer initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize CacheWarmer: {e}")
            raise
    
    async def warm_cache(self, strategy: Optional[WarmingStrategy] = None) -> Dict[str, Any]:
        """Warm the cache using the specified strategy."""
        strategy = strategy or self.config.strategy
        
        logger.info(f"Starting cache warming with strategy: {strategy.value}")
        start_time = datetime.now()
        
        warming_results = {
            "strategy": strategy.value,
            "start_time": start_time.isoformat(),
            "models_to_warm": [],
            "models_warmed": [],
            "models_failed": [],
            "models_skipped": [],
            "total_time_seconds": 0.0,
            "success_rate": 0.0
        }
        
        try:
            # Get models to warm based on strategy
            models_to_warm = await self._get_models_to_warm(strategy)
            warming_results["models_to_warm"] = [
                {"name": name, "version": version, "priority": priority}
                for name, version, priority in models_to_warm
            ]
            
            logger.info(f"Found {len(models_to_warm)} models to warm")
            
            # Warm models
            warming_tasks = []
            for model_name, model_version, priority in models_to_warm:
                task = asyncio.create_task(
                    self._warm_model(model_name, model_version, priority)
                )
                warming_tasks.append((model_name, model_version, task))
            
            # Wait for all warming tasks to complete
            for model_name, model_version, task in warming_tasks:
                try:
                    success = await task
                    if success:
                        warming_results["models_warmed"].append({
                            "name": model_name,
                            "version": model_version
                        })
                    else:
                        warming_results["models_failed"].append({
                            "name": model_name,
                            "version": model_version,
                            "reason": "warming_failed"
                        })
                except Exception as e:
                    warming_results["models_failed"].append({
                        "name": model_name,
                        "version": model_version,
                        "reason": str(e)
                    })
                    logger.error(f"Failed to warm {model_name}:{model_version}: {e}")
            
            # Calculate results
            end_time = datetime.now()
            total_time = (end_time - start_time).total_seconds()
            
            warming_results["end_time"] = end_time.isoformat()
            warming_results["total_time_seconds"] = total_time
            
            total_models = len(models_to_warm)
            warmed_models = len(warming_results["models_warmed"])
            warming_results["success_rate"] = (warmed_models / total_models * 100) if total_models > 0 else 0
            
            # Update statistics
            self.stats["warming_sessions"] += 1
            self.stats["models_warmed"] += warmed_models
            self.stats["warming_failures"] += len(warming_results["models_failed"])
            self.stats["total_warming_time"] += total_time
            
            logger.info(f"Cache warming completed: {warmed_models}/{total_models} models warmed "
                       f"in {total_time:.1f}s ({warming_results['success_rate']:.1f}% success rate)")
            
            return warming_results
            
        except Exception as e:
            logger.error(f"Cache warming failed: {e}")
            warming_results["error"] = str(e)
            return warming_results
    
    async def _get_models_to_warm(self, strategy: WarmingStrategy) -> List[Tuple[str, str, str]]:
        """Get list of models to warm based on strategy."""
        models_to_warm = []
        
        if strategy == WarmingStrategy.ESSENTIAL_ONLY:
            # Only warm essential models
            for model_name, config in self.model_manager.model_configs.items():
                if config.priority == ModelPriority.ESSENTIAL:
                    models_to_warm.append((model_name, "latest", "essential"))
        
        elif strategy == WarmingStrategy.PRIORITY_BASED:
            # Warm models based on priority order
            priority_order = [ModelPriority.ESSENTIAL, ModelPriority.STANDARD, ModelPriority.ADVANCED]
            
            for priority in priority_order:
                for model_name, config in self.model_manager.model_configs.items():
                    if config.priority == priority:
                        models_to_warm.append((model_name, "latest", priority.value))
        
        elif strategy == WarmingStrategy.USAGE_BASED:
            # Warm models based on historical usage
            models_to_warm = await self._get_usage_based_models()
        
        elif strategy == WarmingStrategy.PREDICTIVE:
            # Warm models based on predicted usage
            models_to_warm = await self._get_predictive_models()
        
        elif strategy == WarmingStrategy.FULL:
            # Warm all available models
            for model_name, config in self.model_manager.model_configs.items():
                models_to_warm.append((model_name, "latest", config.priority.value))
        
        # Filter out models that are already cached
        filtered_models = []
        for model_name, model_version, priority in models_to_warm:
            if not self.model_cache.is_cached(model_name, model_version):
                filtered_models.append((model_name, model_version, priority))
            else:
                logger.debug(f"Model {model_name}:{model_version} already cached, skipping")
        
        return filtered_models
    
    async def _get_usage_based_models(self) -> List[Tuple[str, str, str]]:
        """Get models to warm based on historical usage."""
        # In a real implementation, this would query usage statistics
        # For now, return a mock list based on assumed usage patterns
        
        usage_models = [
            ("text-embedding-small", "latest", "high_usage"),
            ("chat-model-base", "latest", "high_usage"),
            ("search-index", "latest", "medium_usage"),
            ("chat-model-large", "latest", "medium_usage"),
            ("document-processor", "latest", "low_usage")
        ]
        
        logger.debug(f"Usage-based warming: {len(usage_models)} models selected")
        return usage_models
    
    async def _get_predictive_models(self) -> List[Tuple[str, str, str]]:
        """Get models to warm based on predicted usage."""
        # In a real implementation, this would use ML to predict usage
        # For now, return a mock list based on time of day, user patterns, etc.
        
        current_hour = datetime.now().hour
        
        # Different models for different times of day
        if 9 <= current_hour <= 17:  # Business hours
            predictive_models = [
                ("text-embedding-small", "latest", "business_hours"),
                ("chat-model-large", "latest", "business_hours"),
                ("document-processor", "latest", "business_hours")
            ]
        else:  # Off hours
            predictive_models = [
                ("text-embedding-small", "latest", "off_hours"),
                ("chat-model-base", "latest", "off_hours")
            ]
        
        logger.debug(f"Predictive warming: {len(predictive_models)} models selected for hour {current_hour}")
        return predictive_models
    
    async def _warm_model(self, model_name: str, model_version: str, priority: str) -> bool:
        """Warm a specific model."""
        async with self.warming_semaphore:
            try:
                # Check if model URL is available
                if model_name not in self.config.model_urls:
                    logger.warning(f"No URL configured for model {model_name}")
                    return False
                
                model_url = self.config.model_urls[model_name]
                
                logger.info(f"Warming model {model_name}:{model_version} (priority: {priority})")
                
                # Download and cache the model
                cached_path = await self.model_cache.download_and_cache_model(
                    model_name=model_name,
                    model_url=model_url,
                    model_version=model_version,
                    priority=priority,
                    metadata={
                        "warmed_at": datetime.now().isoformat(),
                        "warming_priority": priority,
                        "warming_strategy": self.config.strategy.value
                    }
                )
                
                if cached_path:
                    logger.info(f"Successfully warmed model {model_name}:{model_version}")
                    return True
                else:
                    logger.error(f"Failed to warm model {model_name}:{model_version}")
                    return False
                
            except Exception as e:
                logger.error(f"Error warming model {model_name}:{model_version}: {e}")
                return False
    
    async def warm_essential_models(self) -> Dict[str, Any]:
        """Warm only essential models for quick startup."""
        return await self.warm_cache(WarmingStrategy.ESSENTIAL_ONLY)
    
    async def background_warm_cache(self) -> None:
        """Perform background cache warming without blocking."""
        if not self.config.background_warming:
            return
        
        logger.info("Starting background cache warming")
        
        try:
            # Use a less aggressive strategy for background warming
            strategy = WarmingStrategy.USAGE_BASED
            await self.warm_cache(strategy)
            
        except Exception as e:
            logger.error(f"Background cache warming failed: {e}")
    
    async def warm_on_demand(self, model_names: List[str]) -> Dict[str, Any]:
        """Warm specific models on demand."""
        logger.info(f"On-demand warming for models: {model_names}")
        
        start_time = datetime.now()
        results = {
            "strategy": "on_demand",
            "requested_models": model_names,
            "models_warmed": [],
            "models_failed": [],
            "models_skipped": []
        }
        
        for model_name in model_names:
            try:
                # Check if already cached
                if self.model_cache.is_cached(model_name, "latest"):
                    results["models_skipped"].append({
                        "name": model_name,
                        "reason": "already_cached"
                    })
                    continue
                
                # Warm the model
                success = await self._warm_model(model_name, "latest", "on_demand")
                
                if success:
                    results["models_warmed"].append({"name": model_name})
                else:
                    results["models_failed"].append({
                        "name": model_name,
                        "reason": "warming_failed"
                    })
                    
            except Exception as e:
                results["models_failed"].append({
                    "name": model_name,
                    "reason": str(e)
                })
        
        end_time = datetime.now()
        results["total_time_seconds"] = (end_time - start_time).total_seconds()
        
        return results
    
    def get_warming_statistics(self) -> Dict[str, Any]:
        """Get cache warming statistics."""
        cache_stats = self.model_cache.get_cache_statistics() if self.model_cache else {}
        
        return {
            "warming_stats": self.stats.copy(),
            "cache_stats": cache_stats,
            "config": {
                "strategy": self.config.strategy.value,
                "max_concurrent_warming": self.config.max_concurrent_warming,
                "background_warming": self.config.background_warming,
                "warm_on_startup": self.config.warm_on_startup
            },
            "active_warming_tasks": len([t for t in self.warming_tasks.values() if not t.done()])
        }
    
    async def shutdown(self) -> None:
        """Shutdown the cache warmer."""
        logger.info("Shutting down CacheWarmer")
        
        # Signal shutdown
        self._shutdown_event.set()
        
        # Cancel warming tasks
        for task in self.warming_tasks.values():
            if not task.done():
                task.cancel()
        
        # Wait for tasks to complete
        if self.warming_tasks:
            await asyncio.gather(*self.warming_tasks.values(), return_exceptions=True)
        
        logger.info("CacheWarmer shutdown complete")


# Global cache warmer instance
_cache_warmer: Optional[CacheWarmer] = None


def get_cache_warmer() -> CacheWarmer:
    """Get the global cache warmer instance."""
    global _cache_warmer
    if _cache_warmer is None:
        _cache_warmer = CacheWarmer()
    return _cache_warmer


async def initialize_cache_warmer(config: Optional[WarmingConfig] = None) -> CacheWarmer:
    """Initialize and start the cache warmer."""
    global _cache_warmer
    _cache_warmer = CacheWarmer(config)
    await _cache_warmer.initialize()
    return _cache_warmer