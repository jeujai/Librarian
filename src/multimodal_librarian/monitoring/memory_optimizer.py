"""
Memory optimization service for monitoring and managing system memory usage.

This module provides comprehensive memory management including:
- Real-time memory usage monitoring
- Memory leak detection and prevention
- Garbage collection optimization
- Memory usage alerts and recommendations
- Memory profiling and analysis
"""

import gc
import sys
import time
import psutil
import threading
import tracemalloc
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from collections import deque, defaultdict
import weakref
import asyncio

from ..config import get_settings
from ..logging_config import get_logger


@dataclass
class MemorySnapshot:
    """Memory usage snapshot at a point in time."""
    timestamp: datetime
    total_memory_mb: float
    used_memory_mb: float
    available_memory_mb: float
    memory_percent: float
    process_memory_mb: float
    process_memory_percent: float
    gc_stats: Dict[str, int]
    top_objects: List[Dict[str, Any]]


@dataclass
class MemoryLeak:
    """Memory leak detection result."""
    object_type: str
    count_increase: int
    size_increase_mb: float
    detection_time: datetime
    severity: str  # low, medium, high, critical
    description: str


@dataclass
class GCOptimization:
    """Garbage collection optimization result."""
    generation: int
    objects_collected: int
    time_taken_ms: float
    memory_freed_mb: float
    optimization_applied: str


class MemoryProfiler:
    """Memory profiler for detailed memory analysis."""
    
    def __init__(self):
        self.logger = get_logger("memory_profiler")
        self._profiling_active = False
        self._snapshots = deque(maxlen=100)
        
    def start_profiling(self) -> None:
        """Start memory profiling."""
        if not self._profiling_active:
            tracemalloc.start()
            self._profiling_active = True
            self.logger.info("Memory profiling started")
    
    def stop_profiling(self) -> None:
        """Stop memory profiling."""
        if self._profiling_active:
            tracemalloc.stop()
            self._profiling_active = False
            self.logger.info("Memory profiling stopped")
    
    def take_snapshot(self) -> Optional[Any]:
        """Take a memory snapshot."""
        if not self._profiling_active:
            return None
        
        snapshot = tracemalloc.take_snapshot()
        self._snapshots.append({
            'timestamp': datetime.now(),
            'snapshot': snapshot
        })
        return snapshot
    
    def get_top_memory_consumers(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get top memory consuming objects."""
        if not self._profiling_active or not self._snapshots:
            return []
        
        latest_snapshot = self._snapshots[-1]['snapshot']
        top_stats = latest_snapshot.statistics('lineno')
        
        consumers = []
        for stat in top_stats[:limit]:
            # Handle traceback formatting safely
            filename = 'unknown'
            line_number = 0
            
            if stat.traceback:
                try:
                    formatted = stat.traceback.format()
                    if formatted and len(formatted) > 0:
                        filename = formatted[0]
                    line_number = stat.traceback[0].lineno
                except (AttributeError, IndexError):
                    pass
            
            consumers.append({
                'filename': filename,
                'line_number': line_number,
                'size_mb': stat.size / 1024 / 1024,
                'count': stat.count
            })
        
        return consumers
    
    def compare_snapshots(self, snapshot1_idx: int = -2, snapshot2_idx: int = -1) -> Dict[str, Any]:
        """Compare two memory snapshots to detect changes."""
        if len(self._snapshots) < 2:
            return {'error': 'Not enough snapshots for comparison'}
        
        try:
            snapshot1 = self._snapshots[snapshot1_idx]['snapshot']
            snapshot2 = self._snapshots[snapshot2_idx]['snapshot']
            
            top_stats = snapshot2.compare_to(snapshot1, 'lineno')
            
            changes = []
            for stat in top_stats[:10]:
                # Handle traceback formatting safely
                filename = 'unknown'
                line_number = 0
                
                if stat.traceback:
                    try:
                        formatted = stat.traceback.format()
                        if formatted and len(formatted) > 0:
                            filename = formatted[0]
                        line_number = stat.traceback[0].lineno
                    except (AttributeError, IndexError):
                        pass
                
                changes.append({
                    'filename': filename,
                    'line_number': line_number,
                    'size_diff_mb': stat.size_diff / 1024 / 1024,
                    'count_diff': stat.count_diff,
                    'size_mb': stat.size / 1024 / 1024
                })
            
            return {
                'timestamp1': self._snapshots[snapshot1_idx]['timestamp'].isoformat(),
                'timestamp2': self._snapshots[snapshot2_idx]['timestamp'].isoformat(),
                'changes': changes
            }
            
        except Exception as e:
            self.logger.error(f"Error comparing snapshots: {e}")
            return {'error': str(e)}


class MemoryLeakDetector:
    """Detects potential memory leaks by monitoring object counts and sizes."""
    
    def __init__(self):
        self.logger = get_logger("memory_leak_detector")
        self._object_tracking = defaultdict(lambda: {'count': 0, 'size': 0, 'history': deque(maxlen=100)})
        self._leak_threshold = {
            'count_increase': 1000,  # Objects
            'size_increase_mb': 50,  # MB
            'time_window_minutes': 30
        }
        self._detected_leaks = deque(maxlen=50)
    
    def track_objects(self) -> None:
        """Track current object counts and sizes."""
        try:
            # Get object counts by type
            object_counts = defaultdict(int)
            total_size = 0
            
            for obj in gc.get_objects():
                obj_type = type(obj).__name__
                object_counts[obj_type] += 1
                try:
                    total_size += sys.getsizeof(obj)
                except (TypeError, AttributeError):
                    pass
            
            timestamp = datetime.now()
            
            # Update tracking data
            for obj_type, count in object_counts.items():
                self._object_tracking[obj_type]['history'].append({
                    'timestamp': timestamp,
                    'count': count,
                    'size': total_size  # Approximate
                })
            
            # Check for potential leaks
            self._check_for_leaks(timestamp)
            
        except Exception as e:
            self.logger.error(f"Error tracking objects: {e}")
    
    def _check_for_leaks(self, current_time: datetime) -> None:
        """Check for potential memory leaks."""
        cutoff_time = current_time - timedelta(minutes=self._leak_threshold['time_window_minutes'])
        
        for obj_type, tracking_data in self._object_tracking.items():
            history = tracking_data['history']
            
            if len(history) < 2:
                continue
            
            # Get data points within time window
            recent_data = [
                point for point in history
                if point['timestamp'] >= cutoff_time
            ]
            
            if len(recent_data) < 2:
                continue
            
            # Calculate increases
            oldest_point = recent_data[0]
            newest_point = recent_data[-1]
            
            count_increase = newest_point['count'] - oldest_point['count']
            size_increase_mb = (newest_point['size'] - oldest_point['size']) / 1024 / 1024
            
            # Check thresholds
            if (count_increase >= self._leak_threshold['count_increase'] or 
                size_increase_mb >= self._leak_threshold['size_increase_mb']):
                
                severity = self._calculate_leak_severity(count_increase, size_increase_mb)
                
                leak = MemoryLeak(
                    object_type=obj_type,
                    count_increase=count_increase,
                    size_increase_mb=size_increase_mb,
                    detection_time=current_time,
                    severity=severity,
                    description=f"Detected {count_increase} new {obj_type} objects ({size_increase_mb:.2f} MB increase)"
                )
                
                self._detected_leaks.append(leak)
                self.logger.warning(f"Memory leak detected: {leak.description}")
    
    def _calculate_leak_severity(self, count_increase: int, size_increase_mb: float) -> str:
        """Calculate severity of detected memory leak."""
        if size_increase_mb >= 200 or count_increase >= 10000:
            return "critical"
        elif size_increase_mb >= 100 or count_increase >= 5000:
            return "high"
        elif size_increase_mb >= 50 or count_increase >= 2000:
            return "medium"
        else:
            return "low"
    
    def get_detected_leaks(self, hours: int = 24) -> List[Dict[str, Any]]:
        """Get detected memory leaks within the specified time period."""
        cutoff_time = datetime.now() - timedelta(hours=hours)
        
        recent_leaks = [
            leak for leak in self._detected_leaks
            if leak.detection_time >= cutoff_time
        ]
        
        return [
            {
                'object_type': leak.object_type,
                'count_increase': leak.count_increase,
                'size_increase_mb': leak.size_increase_mb,
                'detection_time': leak.detection_time.isoformat(),
                'severity': leak.severity,
                'description': leak.description
            }
            for leak in recent_leaks
        ]


class GarbageCollectionOptimizer:
    """Optimizes garbage collection for better memory management."""
    
    def __init__(self):
        self.logger = get_logger("gc_optimizer")
        self._gc_stats = deque(maxlen=1000)
        self._optimization_history = deque(maxlen=100)
        
        # GC tuning parameters
        self._gc_thresholds = {
            'generation_0': 700,   # Default: 700
            'generation_1': 10,    # Default: 10
            'generation_2': 10     # Default: 10
        }
        
        self._apply_gc_tuning()
    
    def _apply_gc_tuning(self) -> None:
        """Apply garbage collection tuning."""
        try:
            # Set custom GC thresholds
            gc.set_threshold(
                self._gc_thresholds['generation_0'],
                self._gc_thresholds['generation_1'],
                self._gc_thresholds['generation_2']
            )
            
            self.logger.info(f"Applied GC thresholds: {self._gc_thresholds}")
            
        except Exception as e:
            self.logger.error(f"Error applying GC tuning: {e}")
    
    def optimize_garbage_collection(self) -> List[GCOptimization]:
        """Perform optimized garbage collection."""
        optimizations = []
        
        try:
            # Get initial memory usage
            initial_memory = psutil.Process().memory_info().rss / 1024 / 1024
            
            # Collect garbage for each generation
            for generation in range(3):
                start_time = time.time()
                
                # Force collection for this generation
                collected = gc.collect(generation)
                
                end_time = time.time()
                time_taken_ms = (end_time - start_time) * 1000
                
                # Calculate memory freed (approximate)
                current_memory = psutil.Process().memory_info().rss / 1024 / 1024
                memory_freed = max(0, initial_memory - current_memory)
                initial_memory = current_memory
                
                optimization = GCOptimization(
                    generation=generation,
                    objects_collected=collected,
                    time_taken_ms=time_taken_ms,
                    memory_freed_mb=memory_freed,
                    optimization_applied=f"Generation {generation} collection"
                )
                
                optimizations.append(optimization)
                self._optimization_history.append(optimization)
                
                self.logger.debug(f"GC Gen {generation}: {collected} objects, {time_taken_ms:.2f}ms, {memory_freed:.2f}MB freed")
            
            # Record GC stats
            self._record_gc_stats()
            
        except Exception as e:
            self.logger.error(f"Error in garbage collection optimization: {e}")
        
        return optimizations
    
    def _record_gc_stats(self) -> None:
        """Record current garbage collection statistics."""
        try:
            stats = gc.get_stats()
            counts = gc.get_count()
            
            gc_data = {
                'timestamp': datetime.now(),
                'generation_counts': counts,
                'generation_stats': stats,
                'total_objects': sum(counts)
            }
            
            self._gc_stats.append(gc_data)
            
        except Exception as e:
            self.logger.error(f"Error recording GC stats: {e}")
    
    def get_gc_statistics(self) -> Dict[str, Any]:
        """Get garbage collection statistics."""
        try:
            current_counts = gc.get_count()
            current_stats = gc.get_stats()
            current_thresholds = gc.get_threshold()
            
            # Calculate recent GC activity
            recent_optimizations = list(self._optimization_history)[-10:]
            
            total_objects_collected = sum(opt.objects_collected for opt in recent_optimizations)
            total_memory_freed = sum(opt.memory_freed_mb for opt in recent_optimizations)
            avg_collection_time = (
                sum(opt.time_taken_ms for opt in recent_optimizations) / 
                max(1, len(recent_optimizations))
            )
            
            return {
                'current_state': {
                    'generation_counts': current_counts,
                    'generation_thresholds': current_thresholds,
                    'total_objects': sum(current_counts)
                },
                'recent_activity': {
                    'total_objects_collected': total_objects_collected,
                    'total_memory_freed_mb': round(total_memory_freed, 2),
                    'avg_collection_time_ms': round(avg_collection_time, 2),
                    'collections_performed': len(recent_optimizations)
                },
                'generation_stats': current_stats,
                'tuning_parameters': self._gc_thresholds
            }
            
        except Exception as e:
            self.logger.error(f"Error getting GC statistics: {e}")
            return {'error': str(e)}
    
    def tune_gc_thresholds(self, gen0: Optional[int] = None, gen1: Optional[int] = None, 
                          gen2: Optional[int] = None) -> bool:
        """Tune garbage collection thresholds."""
        try:
            if gen0 is not None:
                self._gc_thresholds['generation_0'] = gen0
            if gen1 is not None:
                self._gc_thresholds['generation_1'] = gen1
            if gen2 is not None:
                self._gc_thresholds['generation_2'] = gen2
            
            self._apply_gc_tuning()
            self.logger.info(f"Updated GC thresholds: {self._gc_thresholds}")
            return True
            
        except Exception as e:
            self.logger.error(f"Error tuning GC thresholds: {e}")
            return False


class MemoryOptimizer:
    """Main memory optimization service."""
    
    def __init__(self):
        self.settings = get_settings()
        self.logger = get_logger("memory_optimizer")
        
        # Initialize components
        self.profiler = MemoryProfiler()
        self.leak_detector = MemoryLeakDetector()
        self.gc_optimizer = GarbageCollectionOptimizer()
        
        # Memory monitoring data
        self._memory_snapshots = deque(maxlen=1440)  # 24 hours at 1-minute intervals
        self._monitoring_active = False
        self._lock = threading.Lock()
        
        # Memory thresholds
        self._memory_thresholds = {
            'warning_percent': 80,
            'critical_percent': 90,
            'process_warning_mb': 1024,  # 1GB
            'process_critical_mb': 2048  # 2GB
        }
        
        # Start profiling and monitoring
        self.profiler.start_profiling()
        
        # Take initial snapshot
        initial_snapshot = self._take_memory_snapshot()
        with self._lock:
            self._memory_snapshots.append(initial_snapshot)
        
        self._start_monitoring()
    
    def _start_monitoring(self) -> None:
        """Start memory monitoring loop."""
        if self._monitoring_active:
            return  # Already monitoring
            
        async def monitoring_loop():
            self._monitoring_active = True
            self.logger.info("Memory monitoring started")
            
            while self._monitoring_active:
                try:
                    # Take memory snapshot
                    snapshot = self._take_memory_snapshot()
                    
                    with self._lock:
                        self._memory_snapshots.append(snapshot)
                    
                    # Check for memory issues
                    self._check_memory_thresholds(snapshot)
                    
                    # Track objects for leak detection
                    self.leak_detector.track_objects()
                    
                    # Periodic garbage collection optimization
                    if len(self._memory_snapshots) % 10 == 0:  # Every 10 minutes
                        self.gc_optimizer.optimize_garbage_collection()
                    
                    # Sleep for 1 minute
                    await asyncio.sleep(60)
                    
                except Exception as e:
                    self.logger.error(f"Error in memory monitoring loop: {e}")
                    await asyncio.sleep(60)
        
        # Start monitoring in background - handle event loop properly
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(monitoring_loop())
        except RuntimeError:
            # No event loop running, start monitoring in thread instead
            import threading
            
            def sync_monitoring_loop():
                # Flag is already set before thread starts
                self.logger.info("Memory monitoring started (sync mode)")
                
                while self._monitoring_active:
                    try:
                        # Take memory snapshot
                        snapshot = self._take_memory_snapshot()
                        
                        with self._lock:
                            self._memory_snapshots.append(snapshot)
                        
                        # Check for memory issues
                        self._check_memory_thresholds(snapshot)
                        
                        # Track objects for leak detection
                        self.leak_detector.track_objects()
                        
                        # Periodic garbage collection optimization
                        if len(self._memory_snapshots) % 10 == 0:  # Every 10 minutes
                            self.gc_optimizer.optimize_garbage_collection()
                        
                        # Sleep for 1 minute
                        time.sleep(60)
                        
                    except Exception as e:
                        self.logger.error(f"Error in memory monitoring loop: {e}")
                        time.sleep(60)
            
            # Start monitoring thread
            self._monitoring_active = True  # Set flag before starting thread
            monitor_thread = threading.Thread(target=sync_monitoring_loop, daemon=True)
            monitor_thread.start()
            # Give thread a moment to start
            time.sleep(0.1)
    
    def _take_memory_snapshot(self) -> MemorySnapshot:
        """Take a comprehensive memory snapshot."""
        try:
            # System memory
            system_memory = psutil.virtual_memory()
            
            # Process memory
            process = psutil.Process()
            process_memory = process.memory_info()
            
            # Garbage collection stats
            gc_counts = gc.get_count()
            gc_stats = {
                f'generation_{i}': count 
                for i, count in enumerate(gc_counts)
            }
            gc_stats['total_objects'] = sum(gc_counts)
            
            # Top memory consumers
            top_objects = self.profiler.get_top_memory_consumers(5)
            
            return MemorySnapshot(
                timestamp=datetime.now(),
                total_memory_mb=system_memory.total / 1024 / 1024,
                used_memory_mb=system_memory.used / 1024 / 1024,
                available_memory_mb=system_memory.available / 1024 / 1024,
                memory_percent=system_memory.percent,
                process_memory_mb=process_memory.rss / 1024 / 1024,
                process_memory_percent=(process_memory.rss / system_memory.total) * 100,
                gc_stats=gc_stats,
                top_objects=top_objects
            )
            
        except Exception as e:
            self.logger.error(f"Error taking memory snapshot: {e}")
            return MemorySnapshot(
                timestamp=datetime.now(),
                total_memory_mb=0,
                used_memory_mb=0,
                available_memory_mb=0,
                memory_percent=0,
                process_memory_mb=0,
                process_memory_percent=0,
                gc_stats={},
                top_objects=[]
            )
    
    def _check_memory_thresholds(self, snapshot: MemorySnapshot) -> None:
        """Check if memory usage exceeds thresholds."""
        # System memory threshold check
        if snapshot.memory_percent >= self._memory_thresholds['critical_percent']:
            self.logger.critical(f"Critical system memory usage: {snapshot.memory_percent:.1f}%")
            # Trigger aggressive garbage collection
            self.gc_optimizer.optimize_garbage_collection()
            
        elif snapshot.memory_percent >= self._memory_thresholds['warning_percent']:
            self.logger.warning(f"High system memory usage: {snapshot.memory_percent:.1f}%")
        
        # Process memory threshold check
        if snapshot.process_memory_mb >= self._memory_thresholds['process_critical_mb']:
            self.logger.critical(f"Critical process memory usage: {snapshot.process_memory_mb:.1f} MB")
            # Trigger garbage collection
            self.gc_optimizer.optimize_garbage_collection()
            
        elif snapshot.process_memory_mb >= self._memory_thresholds['process_warning_mb']:
            self.logger.warning(f"High process memory usage: {snapshot.process_memory_mb:.1f} MB")
    
    def get_memory_status(self) -> Dict[str, Any]:
        """Get current memory status and statistics."""
        with self._lock:
            if not self._memory_snapshots:
                return {'error': 'No memory data available'}
            
            latest_snapshot = self._memory_snapshots[-1]
            
            # Calculate trends
            trends = self._calculate_memory_trends()
            
            # Get leak detection results
            detected_leaks = self.leak_detector.get_detected_leaks(24)
            
            # Get GC statistics
            gc_stats = self.gc_optimizer.get_gc_statistics()
            
            return {
                'timestamp': latest_snapshot.timestamp.isoformat(),
                'system_memory': {
                    'total_mb': round(latest_snapshot.total_memory_mb, 2),
                    'used_mb': round(latest_snapshot.used_memory_mb, 2),
                    'available_mb': round(latest_snapshot.available_memory_mb, 2),
                    'usage_percent': round(latest_snapshot.memory_percent, 2)
                },
                'process_memory': {
                    'used_mb': round(latest_snapshot.process_memory_mb, 2),
                    'usage_percent': round(latest_snapshot.process_memory_percent, 2)
                },
                'garbage_collection': gc_stats,
                'memory_trends': trends,
                'detected_leaks': detected_leaks,
                'top_memory_consumers': latest_snapshot.top_objects,
                'thresholds': self._memory_thresholds,
                'monitoring_status': 'active' if self._monitoring_active else 'inactive'
            }
    
    def _calculate_memory_trends(self) -> Dict[str, Any]:
        """Calculate memory usage trends."""
        if len(self._memory_snapshots) < 2:
            return {}
        
        # Get data from last hour and previous hour
        now = datetime.now()
        one_hour_ago = now - timedelta(hours=1)
        two_hours_ago = now - timedelta(hours=2)
        
        recent_snapshots = [
            snapshot for snapshot in self._memory_snapshots
            if snapshot.timestamp >= one_hour_ago
        ]
        
        previous_snapshots = [
            snapshot for snapshot in self._memory_snapshots
            if two_hours_ago <= snapshot.timestamp < one_hour_ago
        ]
        
        if not recent_snapshots or not previous_snapshots:
            return {}
        
        # Calculate averages
        recent_avg_system = sum(s.memory_percent for s in recent_snapshots) / len(recent_snapshots)
        previous_avg_system = sum(s.memory_percent for s in previous_snapshots) / len(previous_snapshots)
        
        recent_avg_process = sum(s.process_memory_mb for s in recent_snapshots) / len(recent_snapshots)
        previous_avg_process = sum(s.process_memory_mb for s in previous_snapshots) / len(previous_snapshots)
        
        # Calculate trends
        system_trend = ((recent_avg_system - previous_avg_system) / previous_avg_system) * 100
        process_trend = ((recent_avg_process - previous_avg_process) / previous_avg_process) * 100
        
        return {
            'system_memory': {
                'current_avg_percent': round(recent_avg_system, 2),
                'previous_avg_percent': round(previous_avg_system, 2),
                'trend_percent': round(system_trend, 2),
                'trend_direction': 'increasing' if system_trend > 5 else 'decreasing' if system_trend < -5 else 'stable'
            },
            'process_memory': {
                'current_avg_mb': round(recent_avg_process, 2),
                'previous_avg_mb': round(previous_avg_process, 2),
                'trend_percent': round(process_trend, 2),
                'trend_direction': 'increasing' if process_trend > 5 else 'decreasing' if process_trend < -5 else 'stable'
            }
        }
    
    def optimize_memory(self) -> Dict[str, Any]:
        """Perform comprehensive memory optimization."""
        optimization_results = {
            'timestamp': datetime.now().isoformat(),
            'optimizations_applied': [],
            'memory_before': {},
            'memory_after': {},
            'performance_impact': {}
        }
        
        try:
            # Get initial memory state
            initial_snapshot = self._take_memory_snapshot()
            optimization_results['memory_before'] = {
                'system_percent': initial_snapshot.memory_percent,
                'process_mb': initial_snapshot.process_memory_mb
            }
            
            start_time = time.time()
            
            # 1. Garbage collection optimization
            gc_optimizations = self.gc_optimizer.optimize_garbage_collection()
            optimization_results['optimizations_applied'].extend([
                {
                    'type': 'garbage_collection',
                    'generation': opt.generation,
                    'objects_collected': opt.objects_collected,
                    'memory_freed_mb': opt.memory_freed_mb,
                    'time_taken_ms': opt.time_taken_ms
                }
                for opt in gc_optimizations
            ])
            
            # 2. Clear weak references
            try:
                import weakref
                weakref.WeakSet()._data.clear()
                optimization_results['optimizations_applied'].append({
                    'type': 'weak_references',
                    'description': 'Cleared weak reference caches'
                })
            except Exception as e:
                self.logger.warning(f"Could not clear weak references: {e}")
            
            # 3. Clear import caches (safer approach)
            try:
                # Only clear specific cache types that are safe to clear
                import importlib
                if hasattr(importlib, '_bootstrap'):
                    # Clear importlib caches safely
                    importlib.invalidate_caches()
                optimization_results['optimizations_applied'].append({
                    'type': 'import_cache',
                    'description': 'Invalidated import caches safely'
                })
            except Exception as e:
                self.logger.warning(f"Could not clear import caches: {e}")
            
            # Get final memory state
            final_snapshot = self._take_memory_snapshot()
            optimization_results['memory_after'] = {
                'system_percent': final_snapshot.memory_percent,
                'process_mb': final_snapshot.process_memory_mb
            }
            
            # Calculate performance impact
            end_time = time.time()
            optimization_results['performance_impact'] = {
                'total_time_ms': round((end_time - start_time) * 1000, 2),
                'memory_saved_mb': round(
                    initial_snapshot.process_memory_mb - final_snapshot.process_memory_mb, 2
                ),
                'system_memory_improvement_percent': round(
                    initial_snapshot.memory_percent - final_snapshot.memory_percent, 2
                )
            }
            
            self.logger.info(f"Memory optimization completed: {optimization_results['performance_impact']}")
            
        except Exception as e:
            self.logger.error(f"Error during memory optimization: {e}")
            optimization_results['error'] = str(e)
        
        return optimization_results
    
    def get_memory_report(self) -> Dict[str, Any]:
        """Generate comprehensive memory usage report."""
        memory_status = self.get_memory_status()
        
        # Get historical data
        with self._lock:
            historical_data = []
            for snapshot in list(self._memory_snapshots)[-60:]:  # Last hour
                historical_data.append({
                    'timestamp': snapshot.timestamp.isoformat(),
                    'system_percent': snapshot.memory_percent,
                    'process_mb': snapshot.process_memory_mb
                })
        
        # Generate recommendations
        recommendations = self._generate_memory_recommendations(memory_status)
        
        return {
            'report_timestamp': datetime.now().isoformat(),
            'current_status': memory_status,
            'historical_data': historical_data,
            'recommendations': recommendations,
            'health_score': self._calculate_memory_health_score(memory_status)
        }
    
    def _generate_memory_recommendations(self, memory_status: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Generate memory optimization recommendations."""
        recommendations = []
        
        system_memory = memory_status.get('system_memory', {})
        process_memory = memory_status.get('process_memory', {})
        detected_leaks = memory_status.get('detected_leaks', [])
        
        # System memory recommendations
        if system_memory.get('usage_percent', 0) > 85:
            recommendations.append({
                'type': 'system_memory',
                'severity': 'high',
                'message': 'High system memory usage detected',
                'suggestion': 'Consider adding more RAM or reducing memory-intensive processes',
                'current_value': system_memory.get('usage_percent', 0),
                'target_value': 80
            })
        
        # Process memory recommendations
        if process_memory.get('used_mb', 0) > 1500:
            recommendations.append({
                'type': 'process_memory',
                'severity': 'medium',
                'message': 'High process memory usage',
                'suggestion': 'Review application memory usage and implement memory optimization',
                'current_value': process_memory.get('used_mb', 0),
                'target_value': 1024
            })
        
        # Memory leak recommendations
        critical_leaks = [leak for leak in detected_leaks if leak['severity'] == 'critical']
        if critical_leaks:
            recommendations.append({
                'type': 'memory_leaks',
                'severity': 'critical',
                'message': f'Critical memory leaks detected ({len(critical_leaks)} leaks)',
                'suggestion': 'Investigate and fix memory leaks immediately',
                'details': critical_leaks[:3]  # Top 3 critical leaks
            })
        
        # Garbage collection recommendations
        gc_stats = memory_status.get('garbage_collection', {})
        recent_activity = gc_stats.get('recent_activity', {})
        if recent_activity.get('avg_collection_time_ms', 0) > 100:
            recommendations.append({
                'type': 'garbage_collection',
                'severity': 'medium',
                'message': 'Slow garbage collection detected',
                'suggestion': 'Consider tuning GC thresholds or reducing object creation',
                'current_value': recent_activity.get('avg_collection_time_ms', 0),
                'target_value': 50
            })
        
        return recommendations
    
    def _calculate_memory_health_score(self, memory_status: Dict[str, Any]) -> Dict[str, Any]:
        """Calculate overall memory health score."""
        score = 100
        factors = []
        
        system_memory = memory_status.get('system_memory', {})
        process_memory = memory_status.get('process_memory', {})
        detected_leaks = memory_status.get('detected_leaks', [])
        
        # System memory scoring
        system_usage = system_memory.get('usage_percent', 0)
        if system_usage > 90:
            score -= 30
            factors.append('Critical system memory usage')
        elif system_usage > 80:
            score -= 15
            factors.append('High system memory usage')
        
        # Process memory scoring
        process_usage = process_memory.get('used_mb', 0)
        if process_usage > 2048:
            score -= 25
            factors.append('Critical process memory usage')
        elif process_usage > 1024:
            score -= 10
            factors.append('High process memory usage')
        
        # Memory leak scoring
        critical_leaks = [leak for leak in detected_leaks if leak['severity'] == 'critical']
        high_leaks = [leak for leak in detected_leaks if leak['severity'] == 'high']
        
        if critical_leaks:
            score -= 40
            factors.append(f'{len(critical_leaks)} critical memory leaks')
        elif high_leaks:
            score -= 20
            factors.append(f'{len(high_leaks)} high-severity memory leaks')
        
        # Ensure score doesn't go below 0
        score = max(0, score)
        
        # Determine health status
        if score >= 80:
            status = 'excellent'
        elif score >= 60:
            status = 'good'
        elif score >= 40:
            status = 'fair'
        elif score >= 20:
            status = 'poor'
        else:
            status = 'critical'
        
        return {
            'score': score,
            'status': status,
            'factors': factors
        }
    
    def stop_monitoring(self) -> None:
        """Stop memory monitoring."""
        self._monitoring_active = False
        self.profiler.stop_profiling()
        self.logger.info("Memory monitoring stopped")