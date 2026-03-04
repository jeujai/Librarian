"""
Memory Manager for Model Loading

This module implements intelligent memory management for model loading including:
- Memory pressure monitoring
- Memory reservation and allocation
- Garbage collection optimization
- Memory-aware loading strategies
- Resource cleanup and optimization

Key Features:
- Real-time memory monitoring
- Memory pressure detection
- Resource reservation system
- Automatic cleanup strategies
- Memory optimization recommendations
"""

import asyncio
import logging
import psutil
import gc
import threading
import time
from typing import Dict, List, Optional, Any, Tuple, Set
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
import weakref

logger = logging.getLogger(__name__)


class MemoryPressureLevel(Enum):
    """Memory pressure levels."""
    LOW = "low"           # < 60% memory usage
    MEDIUM = "medium"     # 60-80% memory usage
    HIGH = "high"         # 80-90% memory usage
    CRITICAL = "critical" # > 90% memory usage


class CleanupStrategy(Enum):
    """Memory cleanup strategies."""
    CONSERVATIVE = "conservative"  # Minimal cleanup
    BALANCED = "balanced"         # Balanced cleanup
    AGGRESSIVE = "aggressive"     # Aggressive cleanup


@dataclass
class MemoryReservation:
    """Represents a memory reservation."""
    resource_id: str
    amount_mb: float
    reserved_at: datetime
    expires_at: Optional[datetime] = None
    priority: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class MemoryInfo:
    """Memory information snapshot."""
    total_mb: float
    available_mb: float
    used_mb: float
    usage_percent: float
    memory_pressure: float
    pressure_level: MemoryPressureLevel
    swap_used_mb: float
    swap_total_mb: float
    timestamp: datetime = field(default_factory=datetime.now)


class MemoryManager:
    """
    Intelligent memory manager for model loading operations.
    
    This manager provides memory monitoring, reservation, and optimization
    capabilities to ensure stable model loading under memory constraints.
    Enhanced with multi-model management capabilities.
    """
    
    def __init__(self, 
                 memory_threshold_mb: Optional[float] = None,
                 reservation_timeout_minutes: float = 30.0,
                 monitoring_interval_seconds: float = 5.0,
                 max_concurrent_models: int = 5):
        """Initialize the memory manager."""
        
        # Get system memory info
        memory = psutil.virtual_memory()
        self.total_memory_mb = memory.total / (1024 * 1024)
        
        # Set memory threshold (default to 80% of total memory)
        self.memory_threshold_mb = memory_threshold_mb or (self.total_memory_mb * 0.8)
        
        # Configuration
        self.reservation_timeout = timedelta(minutes=reservation_timeout_minutes)
        self.monitoring_interval = monitoring_interval_seconds
        self.max_concurrent_models = max_concurrent_models
        
        # State tracking
        self.reservations: Dict[str, MemoryReservation] = {}
        self.memory_history: List[MemoryInfo] = []
        self.max_history_size = 100
        
        # Multi-model management
        self.active_models: Dict[str, Dict[str, Any]] = {}
        self.model_memory_usage: Dict[str, float] = {}
        self.model_access_patterns: Dict[str, List[datetime]] = {}
        self.model_priorities: Dict[str, int] = {}
        self.model_dependencies: Dict[str, Set[str]] = {}
        self.memory_pools: Dict[str, float] = {
            "essential": self.total_memory_mb * 0.4,  # 40% for essential models
            "standard": self.total_memory_mb * 0.3,   # 30% for standard models
            "advanced": self.total_memory_mb * 0.2,   # 20% for advanced models
            "buffer": self.total_memory_mb * 0.1      # 10% buffer
        }
        
        # Locks for thread safety
        self._reservation_lock = asyncio.Lock()
        self._cleanup_lock = asyncio.Lock()
        self._model_management_lock = asyncio.Lock()
        
        # Background tasks
        self._monitor_task: Optional[asyncio.Task] = None
        self._cleanup_task: Optional[asyncio.Task] = None
        self._model_optimizer_task: Optional[asyncio.Task] = None
        self._shutdown_event = asyncio.Event()
        
        # Statistics
        self.stats = {
            "reservations_made": 0,
            "reservations_released": 0,
            "reservations_expired": 0,
            "cleanup_operations": 0,
            "memory_pressure_events": 0,
            "gc_collections_forced": 0,
            "models_loaded": 0,
            "models_unloaded": 0,
            "memory_optimizations": 0,
            "pool_reallocations": 0
        }
        
        # Callbacks
        self.pressure_callbacks: List[callable] = []
        self.cleanup_callbacks: List[callable] = []
        self.model_callbacks: List[callable] = []
        
        logger.info(f"MemoryManager initialized: {self.total_memory_mb:.1f}MB total, "
                   f"{self.memory_threshold_mb:.1f}MB threshold, "
                   f"max {max_concurrent_models} concurrent models")
    
    async def start(self) -> None:
        """Start the memory manager."""
        logger.info("Starting memory manager")
        
        # Start background monitoring
        self._monitor_task = asyncio.create_task(self._memory_monitor())
        self._cleanup_task = asyncio.create_task(self._cleanup_monitor())
        self._model_optimizer_task = asyncio.create_task(self._model_optimizer())
        
        logger.info("Memory manager started")
    
    def get_memory_info(self) -> MemoryInfo:
        """Get current memory information."""
        memory = psutil.virtual_memory()
        swap = psutil.swap_memory()
        
        total_mb = memory.total / (1024 * 1024)
        available_mb = memory.available / (1024 * 1024)
        used_mb = memory.used / (1024 * 1024)
        usage_percent = memory.percent
        
        # Calculate memory pressure (0.0 to 1.0)
        memory_pressure = min(1.0, used_mb / self.memory_threshold_mb)
        
        # Determine pressure level
        if memory_pressure < 0.6:
            pressure_level = MemoryPressureLevel.LOW
        elif memory_pressure < 0.8:
            pressure_level = MemoryPressureLevel.MEDIUM
        elif memory_pressure < 0.9:
            pressure_level = MemoryPressureLevel.HIGH
        else:
            pressure_level = MemoryPressureLevel.CRITICAL
        
        return MemoryInfo(
            total_mb=total_mb,
            available_mb=available_mb,
            used_mb=used_mb,
            usage_percent=usage_percent,
            memory_pressure=memory_pressure,
            pressure_level=pressure_level,
            swap_used_mb=swap.used / (1024 * 1024),
            swap_total_mb=swap.total / (1024 * 1024)
        )
    
    def get_available_memory_mb(self) -> float:
        """Get available memory in MB."""
        memory_info = self.get_memory_info()
        
        # Subtract reserved memory
        reserved_total = sum(res.amount_mb for res in self.reservations.values())
        
        return max(0, memory_info.available_mb - reserved_total)
    
    async def reserve_memory(self, resource_id: str, amount_mb: float, 
                           priority: int = 0, timeout_minutes: Optional[float] = None) -> bool:
        """Reserve memory for a resource."""
        async with self._reservation_lock:
            # Check if already reserved
            if resource_id in self.reservations:
                logger.warning(f"Memory already reserved for {resource_id}")
                return False
            
            # Check if enough memory is available
            available = self.get_available_memory_mb()
            if available < amount_mb:
                logger.warning(f"Insufficient memory for {resource_id}: "
                             f"requested {amount_mb:.1f}MB, available {available:.1f}MB")
                return False
            
            # Create reservation
            expires_at = None
            if timeout_minutes:
                expires_at = datetime.now() + timedelta(minutes=timeout_minutes)
            else:
                expires_at = datetime.now() + self.reservation_timeout
            
            reservation = MemoryReservation(
                resource_id=resource_id,
                amount_mb=amount_mb,
                reserved_at=datetime.now(),
                expires_at=expires_at,
                priority=priority
            )
            
            self.reservations[resource_id] = reservation
            self.stats["reservations_made"] += 1
            
            logger.info(f"Reserved {amount_mb:.1f}MB for {resource_id}")
            return True
    
    async def release_memory(self, resource_id: str) -> bool:
        """Release memory reservation for a resource."""
        async with self._reservation_lock:
            if resource_id not in self.reservations:
                logger.warning(f"No memory reservation found for {resource_id}")
                return False
            
            reservation = self.reservations.pop(resource_id)
            self.stats["reservations_released"] += 1
            
            logger.info(f"Released {reservation.amount_mb:.1f}MB for {resource_id}")
            return True
    
    async def extend_reservation(self, resource_id: str, additional_minutes: float) -> bool:
        """Extend a memory reservation."""
        async with self._reservation_lock:
            if resource_id not in self.reservations:
                return False
            
            reservation = self.reservations[resource_id]
            if reservation.expires_at:
                reservation.expires_at += timedelta(minutes=additional_minutes)
                logger.info(f"Extended reservation for {resource_id} by {additional_minutes} minutes")
                return True
            
            return False
    
    def get_reservation_info(self, resource_id: str) -> Optional[Dict[str, Any]]:
        """Get information about a memory reservation."""
        if resource_id not in self.reservations:
            return None
        
        reservation = self.reservations[resource_id]
        
        return {
            "resource_id": reservation.resource_id,
            "amount_mb": reservation.amount_mb,
            "reserved_at": reservation.reserved_at.isoformat(),
            "expires_at": reservation.expires_at.isoformat() if reservation.expires_at else None,
            "priority": reservation.priority,
            "age_minutes": (datetime.now() - reservation.reserved_at).total_seconds() / 60,
            "metadata": reservation.metadata
        }
    
    def get_all_reservations(self) -> Dict[str, Dict[str, Any]]:
        """Get information about all memory reservations."""
        return {
            resource_id: self.get_reservation_info(resource_id)
            for resource_id in self.reservations.keys()
        }
    
    async def _memory_monitor(self) -> None:
        """Background memory monitoring task."""
        try:
            while not self._shutdown_event.is_set():
                # Get current memory info
                memory_info = self.get_memory_info()
                
                # Add to history
                self.memory_history.append(memory_info)
                if len(self.memory_history) > self.max_history_size:
                    self.memory_history.pop(0)
                
                # Check for memory pressure
                if memory_info.pressure_level in [MemoryPressureLevel.HIGH, MemoryPressureLevel.CRITICAL]:
                    self.stats["memory_pressure_events"] += 1
                    await self._handle_memory_pressure(memory_info)
                
                # Log memory status periodically
                if len(self.memory_history) % 12 == 0:  # Every minute at 5s intervals
                    logger.info(f"Memory status: {memory_info.used_mb:.1f}MB used "
                               f"({memory_info.usage_percent:.1f}%), "
                               f"pressure: {memory_info.pressure_level.value}")
                
                await asyncio.sleep(self.monitoring_interval)
        
        except asyncio.CancelledError:
            logger.info("Memory monitor cancelled")
            raise
        except Exception as e:
            logger.error(f"Error in memory monitor: {e}")
    
    async def _cleanup_monitor(self) -> None:
        """Background cleanup monitoring task."""
        try:
            while not self._shutdown_event.is_set():
                await asyncio.sleep(60.0)  # Check every minute
                
                # Clean up expired reservations
                await self._cleanup_expired_reservations()
                
                # Perform garbage collection if needed
                memory_info = self.get_memory_info()
                if memory_info.pressure_level in [MemoryPressureLevel.HIGH, MemoryPressureLevel.CRITICAL]:
                    await self._force_garbage_collection()
        
        except asyncio.CancelledError:
            logger.info("Cleanup monitor cancelled")
            raise
        except Exception as e:
            logger.error(f"Error in cleanup monitor: {e}")
    
    async def _handle_memory_pressure(self, memory_info: MemoryInfo) -> None:
        """Handle memory pressure situations."""
        logger.warning(f"Memory pressure detected: {memory_info.pressure_level.value} "
                      f"({memory_info.usage_percent:.1f}% used)")
        
        # Notify pressure callbacks
        for callback in self.pressure_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(memory_info)
                else:
                    callback(memory_info)
            except Exception as e:
                logger.error(f"Error in pressure callback: {e}")
        
        # Determine cleanup strategy
        if memory_info.pressure_level == MemoryPressureLevel.CRITICAL:
            strategy = CleanupStrategy.AGGRESSIVE
        elif memory_info.pressure_level == MemoryPressureLevel.HIGH:
            strategy = CleanupStrategy.BALANCED
        else:
            strategy = CleanupStrategy.CONSERVATIVE
        
        # Perform cleanup
        await self._perform_cleanup(strategy)
    
    async def _perform_cleanup(self, strategy: CleanupStrategy) -> None:
        """Perform memory cleanup based on strategy."""
        async with self._cleanup_lock:
            logger.info(f"Performing {strategy.value} memory cleanup")
            
            cleanup_actions = []
            
            if strategy == CleanupStrategy.AGGRESSIVE:
                # Aggressive cleanup
                cleanup_actions.extend([
                    self._cleanup_low_priority_reservations,
                    self._force_garbage_collection,
                    self._cleanup_weak_references,
                    self._suggest_model_unloading
                ])
            elif strategy == CleanupStrategy.BALANCED:
                # Balanced cleanup
                cleanup_actions.extend([
                    self._cleanup_expired_reservations,
                    self._force_garbage_collection,
                    self._cleanup_weak_references
                ])
            else:
                # Conservative cleanup
                cleanup_actions.extend([
                    self._cleanup_expired_reservations,
                    self._force_garbage_collection
                ])
            
            # Execute cleanup actions
            for action in cleanup_actions:
                try:
                    await action()
                except Exception as e:
                    logger.error(f"Error in cleanup action {action.__name__}: {e}")
            
            self.stats["cleanup_operations"] += 1
            
            # Notify cleanup callbacks
            for callback in self.cleanup_callbacks:
                try:
                    if asyncio.iscoroutinefunction(callback):
                        await callback(strategy)
                    else:
                        callback(strategy)
                except Exception as e:
                    logger.error(f"Error in cleanup callback: {e}")
    
    async def _cleanup_expired_reservations(self) -> None:
        """Clean up expired memory reservations."""
        now = datetime.now()
        expired_reservations = []
        
        for resource_id, reservation in self.reservations.items():
            if reservation.expires_at and now > reservation.expires_at:
                expired_reservations.append(resource_id)
        
        for resource_id in expired_reservations:
            await self.release_memory(resource_id)
            self.stats["reservations_expired"] += 1
            logger.info(f"Cleaned up expired reservation: {resource_id}")
    
    async def _cleanup_low_priority_reservations(self) -> None:
        """Clean up low priority reservations during memory pressure."""
        # Sort reservations by priority (lower priority first)
        sorted_reservations = sorted(
            self.reservations.items(),
            key=lambda x: x[1].priority
        )
        
        # Remove lowest priority reservations (up to 25%)
        to_remove = len(sorted_reservations) // 4
        
        for i in range(min(to_remove, len(sorted_reservations))):
            resource_id, reservation = sorted_reservations[i]
            if reservation.priority < 5:  # Only remove low priority
                await self.release_memory(resource_id)
                logger.info(f"Cleaned up low priority reservation: {resource_id}")
    
    async def _force_garbage_collection(self) -> None:
        """Force garbage collection to free memory."""
        logger.info("Forcing garbage collection")
        
        # Run garbage collection in thread pool to avoid blocking
        loop = asyncio.get_event_loop()
        
        def run_gc():
            collected = gc.collect()
            return collected
        
        collected = await loop.run_in_executor(None, run_gc)
        
        self.stats["gc_collections_forced"] += 1
        logger.info(f"Garbage collection completed, collected {collected} objects")
    
    async def _cleanup_weak_references(self) -> None:
        """Clean up dead weak references."""
        # This would be implemented based on specific weak reference usage
        logger.info("Cleaning up weak references")
        
        # Force cleanup of dead weak references
        gc.collect()
    
    async def _suggest_model_unloading(self) -> None:
        """Suggest models for unloading during critical memory pressure."""
        logger.warning("Critical memory pressure - suggesting model unloading")
        
        # This would integrate with the model manager to suggest unloading
        # For now, just log the suggestion
        memory_info = self.get_memory_info()
        logger.warning(f"Consider unloading unused models - current usage: {memory_info.usage_percent:.1f}%")
    
    def get_memory_recommendations(self) -> Dict[str, Any]:
        """Get memory optimization recommendations."""
        memory_info = self.get_memory_info()
        recommendations = []
        
        # Analyze memory usage patterns
        if len(self.memory_history) > 10:
            recent_usage = [info.usage_percent for info in self.memory_history[-10:]]
            avg_usage = sum(recent_usage) / len(recent_usage)
            
            if avg_usage > 85:
                recommendations.append({
                    "type": "critical",
                    "message": "Memory usage consistently high, consider reducing model count",
                    "action": "unload_models"
                })
            elif avg_usage > 70:
                recommendations.append({
                    "type": "warning",
                    "message": "Memory usage elevated, monitor closely",
                    "action": "monitor"
                })
        
        # Check reservation efficiency
        total_reserved = sum(res.amount_mb for res in self.reservations.values())
        if total_reserved > memory_info.available_mb * 0.5:
            recommendations.append({
                "type": "info",
                "message": "High memory reservation ratio, consider optimizing reservations",
                "action": "optimize_reservations"
            })
        
        # Multi-model specific recommendations
        if len(self.active_models) >= self.max_concurrent_models * 0.8:
            recommendations.append({
                "type": "warning",
                "message": f"Approaching maximum concurrent models ({len(self.active_models)}/{self.max_concurrent_models})",
                "action": "consider_model_unloading"
            })
        
        # Check pool utilization
        pool_status = self.get_memory_pool_status()
        for pool_name, status in pool_status.items():
            if status["utilization_percent"] > 90:
                recommendations.append({
                    "type": "warning",
                    "message": f"Memory pool '{pool_name}' is {status['utilization_percent']:.1f}% utilized",
                    "action": "rebalance_pools"
                })
        
        # Find underutilized models
        now = datetime.now()
        underutilized_models = []
        for model_name, model_info in self.active_models.items():
            idle_time = (now - model_info["last_accessed"]).total_seconds() / 3600  # hours
            if idle_time > 2 and model_info["access_count"] < 5:  # Idle for 2+ hours with few accesses
                underutilized_models.append(model_name)
        
        if underutilized_models:
            recommendations.append({
                "type": "info",
                "message": f"Found {len(underutilized_models)} underutilized models",
                "action": "consider_unloading",
                "models": underutilized_models[:3]  # Show top 3
            })
        
        return {
            "current_memory_info": {
                "usage_percent": memory_info.usage_percent,
                "pressure_level": memory_info.pressure_level.value,
                "available_mb": memory_info.available_mb
            },
            "reservations": {
                "count": len(self.reservations),
                "total_reserved_mb": total_reserved
            },
            "models": {
                "active_count": len(self.active_models),
                "max_concurrent": self.max_concurrent_models,
                "total_memory_mb": sum(self.model_memory_usage.values())
            },
            "memory_pools": pool_status,
            "recommendations": recommendations,
            "statistics": self.stats.copy()
        }
    
    def register_pressure_callback(self, callback: callable) -> None:
        """Register a callback for memory pressure events."""
        self.pressure_callbacks.append(callback)
        logger.info("Registered memory pressure callback")
    
    def register_cleanup_callback(self, callback: callable) -> None:
        """Register a callback for cleanup events."""
        self.cleanup_callbacks.append(callback)
        logger.info("Registered cleanup callback")
    
    def get_memory_history(self, minutes: int = 30) -> List[Dict[str, Any]]:
        """Get memory usage history for the specified time period."""
        cutoff_time = datetime.now() - timedelta(minutes=minutes)
        
        recent_history = [
            info for info in self.memory_history
            if info.timestamp >= cutoff_time
        ]
        
        return [
            {
                "timestamp": info.timestamp.isoformat(),
                "usage_percent": info.usage_percent,
                "used_mb": info.used_mb,
                "available_mb": info.available_mb,
                "pressure_level": info.pressure_level.value
            }
            for info in recent_history
        ]
    
    # Multi-Model Management Methods
    
    async def register_model(self, model_name: str, memory_mb: float, 
                           priority: int = 0, model_type: str = "standard",
                           dependencies: Optional[Set[str]] = None) -> bool:
        """Register a model with the memory manager."""
        async with self._model_management_lock:
            if model_name in self.active_models:
                logger.warning(f"Model {model_name} already registered")
                return False
            
            # Check if we can accommodate this model
            if len(self.active_models) >= self.max_concurrent_models:
                logger.warning(f"Maximum concurrent models ({self.max_concurrent_models}) reached")
                # Try to free up space by unloading low-priority models
                if not await self._make_space_for_model(memory_mb, priority):
                    return False
            
            # Check memory pool availability
            pool_name = self._get_memory_pool_for_type(model_type)
            if not await self._check_pool_availability(pool_name, memory_mb):
                # Try to reallocate pools
                if not await self._reallocate_memory_pools():
                    logger.warning(f"Insufficient memory in {pool_name} pool for {model_name}")
                    return False
            
            # Register the model
            self.active_models[model_name] = {
                "memory_mb": memory_mb,
                "priority": priority,
                "model_type": model_type,
                "dependencies": dependencies or set(),
                "registered_at": datetime.now(),
                "last_accessed": datetime.now(),
                "access_count": 0,
                "pool": pool_name
            }
            
            self.model_memory_usage[model_name] = memory_mb
            self.model_priorities[model_name] = priority
            self.model_dependencies[model_name] = dependencies or set()
            self.model_access_patterns[model_name] = [datetime.now()]
            
            # Update pool usage
            self.memory_pools[pool_name] -= memory_mb
            
            self.stats["models_loaded"] += 1
            
            logger.info(f"Registered model {model_name}: {memory_mb:.1f}MB, priority {priority}, pool {pool_name}")
            
            # Notify callbacks
            for callback in self.model_callbacks:
                try:
                    if asyncio.iscoroutinefunction(callback):
                        await callback("register", model_name, self.active_models[model_name])
                    else:
                        callback("register", model_name, self.active_models[model_name])
                except Exception as e:
                    logger.error(f"Error in model callback: {e}")
            
            return True
    
    async def unregister_model(self, model_name: str) -> bool:
        """Unregister a model from the memory manager."""
        async with self._model_management_lock:
            if model_name not in self.active_models:
                logger.warning(f"Model {model_name} not registered")
                return False
            
            model_info = self.active_models[model_name]
            memory_mb = model_info["memory_mb"]
            pool_name = model_info["pool"]
            
            # Check dependencies before unloading
            dependents = await self._get_model_dependents(model_name)
            if dependents:
                logger.warning(f"Cannot unregister {model_name}, has dependents: {dependents}")
                return False
            
            # Remove from tracking
            del self.active_models[model_name]
            del self.model_memory_usage[model_name]
            del self.model_priorities[model_name]
            del self.model_dependencies[model_name]
            del self.model_access_patterns[model_name]
            
            # Return memory to pool
            self.memory_pools[pool_name] += memory_mb
            
            self.stats["models_unloaded"] += 1
            
            logger.info(f"Unregistered model {model_name}: {memory_mb:.1f}MB returned to {pool_name} pool")
            
            # Notify callbacks
            for callback in self.model_callbacks:
                try:
                    if asyncio.iscoroutinefunction(callback):
                        await callback("unregister", model_name, model_info)
                    else:
                        callback("unregister", model_name, model_info)
                except Exception as e:
                    logger.error(f"Error in model callback: {e}")
            
            return True
    
    async def update_model_access(self, model_name: str) -> None:
        """Update model access patterns for optimization."""
        if model_name not in self.active_models:
            return
        
        now = datetime.now()
        self.active_models[model_name]["last_accessed"] = now
        self.active_models[model_name]["access_count"] += 1
        
        # Update access pattern history (keep last 100 accesses)
        if model_name not in self.model_access_patterns:
            self.model_access_patterns[model_name] = []
        
        self.model_access_patterns[model_name].append(now)
        if len(self.model_access_patterns[model_name]) > 100:
            self.model_access_patterns[model_name].pop(0)
    
    def get_model_info(self, model_name: str) -> Optional[Dict[str, Any]]:
        """Get information about a registered model."""
        if model_name not in self.active_models:
            return None
        
        model_info = self.active_models[model_name].copy()
        
        # Add computed metrics
        now = datetime.now()
        model_info["age_minutes"] = (now - model_info["registered_at"]).total_seconds() / 60
        model_info["idle_minutes"] = (now - model_info["last_accessed"]).total_seconds() / 60
        
        # Calculate access frequency (accesses per hour)
        access_times = self.model_access_patterns.get(model_name, [])
        recent_accesses = [t for t in access_times if (now - t).total_seconds() < 3600]
        model_info["accesses_per_hour"] = len(recent_accesses)
        
        return model_info
    
    def get_all_models_info(self) -> Dict[str, Dict[str, Any]]:
        """Get information about all registered models."""
        return {
            model_name: self.get_model_info(model_name)
            for model_name in self.active_models.keys()
        }
    
    def get_memory_pool_status(self) -> Dict[str, Dict[str, Any]]:
        """Get status of memory pools."""
        total_allocated = sum(
            model_info["memory_mb"] 
            for model_info in self.active_models.values()
        )
        
        pool_status = {}
        for pool_name, available_mb in self.memory_pools.items():
            allocated_mb = sum(
                model_info["memory_mb"]
                for model_info in self.active_models.values()
                if model_info["pool"] == pool_name
            )
            
            total_pool_mb = available_mb + allocated_mb
            
            pool_status[pool_name] = {
                "total_mb": total_pool_mb,
                "available_mb": available_mb,
                "allocated_mb": allocated_mb,
                "utilization_percent": (allocated_mb / total_pool_mb * 100) if total_pool_mb > 0 else 0,
                "models_count": sum(
                    1 for model_info in self.active_models.values()
                    if model_info["pool"] == pool_name
                )
            }
        
        return pool_status
    
    async def optimize_model_placement(self) -> Dict[str, Any]:
        """Optimize model placement across memory pools."""
        async with self._model_management_lock:
            logger.info("Optimizing model placement across memory pools")
            
            optimization_results = {
                "models_moved": 0,
                "memory_freed_mb": 0.0,
                "pools_rebalanced": 0,
                "recommendations": []
            }
            
            # Analyze current placement efficiency
            pool_status = self.get_memory_pool_status()
            
            # Find overutilized and underutilized pools
            overutilized_pools = []
            underutilized_pools = []
            
            for pool_name, status in pool_status.items():
                if status["utilization_percent"] > 90:
                    overutilized_pools.append((pool_name, status))
                elif status["utilization_percent"] < 30 and status["allocated_mb"] > 0:
                    underutilized_pools.append((pool_name, status))
            
            # Suggest model movements
            for pool_name, status in overutilized_pools:
                # Find models that could be moved to other pools
                models_in_pool = [
                    (name, info) for name, info in self.active_models.items()
                    if info["pool"] == pool_name
                ]
                
                # Sort by access frequency (move least accessed first)
                models_in_pool.sort(key=lambda x: x[1]["access_count"])
                
                for model_name, model_info in models_in_pool[:2]:  # Consider top 2 candidates
                    # Find suitable target pool
                    target_pool = self._find_best_pool_for_model(
                        model_info["memory_mb"], 
                        model_info["model_type"]
                    )
                    
                    if target_pool and target_pool != pool_name:
                        optimization_results["recommendations"].append({
                            "action": "move_model",
                            "model": model_name,
                            "from_pool": pool_name,
                            "to_pool": target_pool,
                            "memory_mb": model_info["memory_mb"],
                            "reason": f"Rebalance overutilized pool {pool_name}"
                        })
            
            # Suggest pool reallocation
            if len(overutilized_pools) > 0 and len(underutilized_pools) > 0:
                optimization_results["recommendations"].append({
                    "action": "reallocate_pools",
                    "reason": "Rebalance memory pools based on current usage patterns"
                })
            
            self.stats["memory_optimizations"] += 1
            
            logger.info(f"Model placement optimization completed: {len(optimization_results['recommendations'])} recommendations")
            
            return optimization_results
    
    async def _make_space_for_model(self, required_mb: float, priority: int) -> bool:
        """Make space for a new model by unloading lower priority models."""
        # Find models with lower priority that can be unloaded
        candidates = []
        for model_name, model_info in self.active_models.items():
            if model_info["priority"] < priority:
                # Check if model has dependents
                dependents = await self._get_model_dependents(model_name)
                if not dependents:
                    candidates.append((model_name, model_info))
        
        # Sort by priority (lowest first) and access frequency
        candidates.sort(key=lambda x: (x[1]["priority"], x[1]["access_count"]))
        
        freed_memory = 0.0
        models_to_unload = []
        
        for model_name, model_info in candidates:
            models_to_unload.append(model_name)
            freed_memory += model_info["memory_mb"]
            
            if freed_memory >= required_mb:
                break
        
        # Unload the selected models
        for model_name in models_to_unload:
            await self.unregister_model(model_name)
            logger.info(f"Unloaded {model_name} to make space for new model")
        
        return freed_memory >= required_mb
    
    def _get_memory_pool_for_type(self, model_type: str) -> str:
        """Get the appropriate memory pool for a model type."""
        type_to_pool = {
            "essential": "essential",
            "standard": "standard", 
            "advanced": "advanced",
            "embedding": "standard",
            "language_model": "advanced",
            "multimodal": "advanced"
        }
        return type_to_pool.get(model_type, "standard")
    
    async def _check_pool_availability(self, pool_name: str, required_mb: float) -> bool:
        """Check if a memory pool has enough space."""
        return self.memory_pools.get(pool_name, 0) >= required_mb
    
    async def _reallocate_memory_pools(self) -> bool:
        """Reallocate memory pools based on current usage patterns."""
        logger.info("Reallocating memory pools based on usage patterns")
        
        # Calculate current usage per pool
        pool_usage = {}
        for pool_name in self.memory_pools.keys():
            allocated = sum(
                model_info["memory_mb"]
                for model_info in self.active_models.values()
                if model_info["pool"] == pool_name
            )
            pool_usage[pool_name] = allocated
        
        # Calculate total available memory
        total_memory = sum(self.memory_pools.values()) + sum(pool_usage.values())
        
        # Reallocate based on usage patterns (with some buffer)
        new_allocation = {}
        for pool_name, used_mb in pool_usage.items():
            if used_mb > 0:
                # Allocate 150% of current usage for growth
                new_allocation[pool_name] = used_mb * 1.5
            else:
                # Minimum allocation for empty pools
                new_allocation[pool_name] = total_memory * 0.1
        
        # Ensure we don't exceed total memory
        total_new_allocation = sum(new_allocation.values())
        if total_new_allocation > total_memory:
            # Scale down proportionally
            scale_factor = total_memory / total_new_allocation
            for pool_name in new_allocation:
                new_allocation[pool_name] *= scale_factor
        
        # Update pool allocations
        for pool_name in self.memory_pools.keys():
            old_available = self.memory_pools[pool_name]
            new_total = new_allocation.get(pool_name, 0)
            used = pool_usage.get(pool_name, 0)
            new_available = max(0, new_total - used)
            
            self.memory_pools[pool_name] = new_available
            
            logger.info(f"Pool {pool_name}: {old_available:.1f}MB -> {new_available:.1f}MB available")
        
        self.stats["pool_reallocations"] += 1
        return True
    
    def _find_best_pool_for_model(self, memory_mb: float, model_type: str) -> Optional[str]:
        """Find the best memory pool for a model."""
        preferred_pool = self._get_memory_pool_for_type(model_type)
        
        # Check if preferred pool has space
        if self.memory_pools.get(preferred_pool, 0) >= memory_mb:
            return preferred_pool
        
        # Find alternative pools with space
        for pool_name, available_mb in self.memory_pools.items():
            if available_mb >= memory_mb:
                return pool_name
        
        return None
    
    async def _get_model_dependents(self, model_name: str) -> Set[str]:
        """Get models that depend on the given model."""
        dependents = set()
        for name, dependencies in self.model_dependencies.items():
            if model_name in dependencies:
                dependents.add(name)
        return dependents
    
    async def _model_optimizer(self) -> None:
        """Background task for model optimization."""
        try:
            while not self._shutdown_event.is_set():
                await asyncio.sleep(300)  # Run every 5 minutes
                
                try:
                    # Optimize model placement
                    await self.optimize_model_placement()
                    
                    # Clean up unused access patterns
                    await self._cleanup_access_patterns()
                    
                except Exception as e:
                    logger.error(f"Error in model optimizer: {e}")
        
        except asyncio.CancelledError:
            logger.info("Model optimizer cancelled")
            raise
    
    async def _cleanup_access_patterns(self) -> None:
        """Clean up old access pattern data."""
        cutoff_time = datetime.now() - timedelta(hours=24)
        
        for model_name, access_times in self.model_access_patterns.items():
            # Keep only recent access times
            recent_accesses = [t for t in access_times if t >= cutoff_time]
            self.model_access_patterns[model_name] = recent_accesses
    
    def register_model_callback(self, callback: callable) -> None:
        """Register a callback for model events."""
        self.model_callbacks.append(callback)
        logger.info("Registered model callback")
    
    async def shutdown(self) -> None:
        """Shutdown the memory manager."""
        logger.info("Shutting down MemoryManager")
        
        # Signal shutdown
        self._shutdown_event.set()
        
        # Cancel background tasks
        tasks_to_cancel = [
            self._monitor_task,
            self._cleanup_task,
            self._model_optimizer_task
        ]
        
        for task in tasks_to_cancel:
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        
        # Release all reservations
        async with self._reservation_lock:
            self.reservations.clear()
        
        # Clear model tracking
        async with self._model_management_lock:
            self.active_models.clear()
            self.model_memory_usage.clear()
            self.model_access_patterns.clear()
            self.model_priorities.clear()
            self.model_dependencies.clear()
        
        logger.info("MemoryManager shutdown complete")


# Global memory manager instance
_memory_manager: Optional[MemoryManager] = None


def get_memory_manager() -> MemoryManager:
    """Get the global memory manager instance."""
    global _memory_manager
    if _memory_manager is None:
        _memory_manager = MemoryManager()
    return _memory_manager


async def initialize_memory_manager(memory_threshold_mb: Optional[float] = None,
                                   max_concurrent_models: int = 5) -> MemoryManager:
    """Initialize and start the memory manager."""
    global _memory_manager
    _memory_manager = MemoryManager(
        memory_threshold_mb=memory_threshold_mb,
        max_concurrent_models=max_concurrent_models
    )
    await _memory_manager.start()
    return _memory_manager