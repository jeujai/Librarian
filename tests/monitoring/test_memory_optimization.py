"""
Tests for memory optimization functionality.

This module tests:
- Memory usage monitoring
- Memory leak detection
- Garbage collection optimization
- Memory profiling and analysis
"""

import pytest
import asyncio
import time
import gc
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock

from src.multimodal_librarian.monitoring.memory_optimizer import (
    MemoryOptimizer,
    MemoryProfiler,
    MemoryLeakDetector,
    GarbageCollectionOptimizer,
    MemorySnapshot,
    MemoryLeak,
    GCOptimization
)


class TestMemoryProfiler:
    """Test memory profiler functionality."""
    
    def test_profiler_initialization(self):
        """Test memory profiler initialization."""
        profiler = MemoryProfiler()
        assert not profiler._profiling_active
        assert len(profiler._snapshots) == 0
    
    def test_start_stop_profiling(self):
        """Test starting and stopping memory profiling."""
        profiler = MemoryProfiler()
        
        # Start profiling
        profiler.start_profiling()
        assert profiler._profiling_active
        
        # Stop profiling
        profiler.stop_profiling()
        assert not profiler._profiling_active
    
    @patch('tracemalloc.take_snapshot')
    def test_take_snapshot(self, mock_take_snapshot):
        """Test taking memory snapshots."""
        profiler = MemoryProfiler()
        profiler.start_profiling()
        
        # Mock snapshot
        mock_snapshot = Mock()
        mock_take_snapshot.return_value = mock_snapshot
        
        # Take snapshot
        result = profiler.take_snapshot()
        
        assert result == mock_snapshot
        assert len(profiler._snapshots) == 1
        mock_take_snapshot.assert_called_once()
    
    def test_take_snapshot_when_not_profiling(self):
        """Test taking snapshot when profiling is not active."""
        profiler = MemoryProfiler()
        result = profiler.take_snapshot()
        assert result is None
    
    @patch('tracemalloc.take_snapshot')
    def test_get_top_memory_consumers(self, mock_take_snapshot):
        """Test getting top memory consumers."""
        profiler = MemoryProfiler()
        profiler.start_profiling()
        
        # Mock snapshot and statistics
        mock_stat = Mock()
        mock_stat.traceback = Mock()
        mock_stat.traceback.format.return_value = ['test_file.py:10']
        mock_stat.traceback.__getitem__ = Mock(return_value=Mock(lineno=10))
        mock_stat.size = 1024 * 1024  # 1MB
        mock_stat.count = 100
        
        mock_snapshot = Mock()
        mock_snapshot.statistics.return_value = [mock_stat]
        mock_take_snapshot.return_value = mock_snapshot
        
        # Take snapshot first
        profiler.take_snapshot()
        
        # Get top consumers
        consumers = profiler.get_top_memory_consumers(5)
        
        assert len(consumers) == 1
        assert consumers[0]['filename'] == 'test_file.py:10'
        assert consumers[0]['line_number'] == 10
        assert consumers[0]['size_mb'] == 1.0
        assert consumers[0]['count'] == 100


class TestMemoryLeakDetector:
    """Test memory leak detection functionality."""
    
    def test_detector_initialization(self):
        """Test memory leak detector initialization."""
        detector = MemoryLeakDetector()
        assert len(detector._object_tracking) == 0
        assert len(detector._detected_leaks) == 0
    
    @patch('gc.get_objects')
    def test_track_objects(self, mock_get_objects):
        """Test object tracking for leak detection."""
        detector = MemoryLeakDetector()
        
        # Mock objects
        mock_objects = [Mock(), Mock(), Mock()]
        for i, obj in enumerate(mock_objects):
            type(obj).__name__ = f'TestObject{i}'
        
        mock_get_objects.return_value = mock_objects
        
        # Track objects
        detector.track_objects()
        
        # Verify tracking data
        assert len(detector._object_tracking) > 0
        mock_get_objects.assert_called_once()
    
    def test_calculate_leak_severity(self):
        """Test leak severity calculation."""
        detector = MemoryLeakDetector()
        
        # Test different severity levels
        assert detector._calculate_leak_severity(15000, 250) == "critical"
        assert detector._calculate_leak_severity(7000, 150) == "high"
        assert detector._calculate_leak_severity(3000, 75) == "medium"
        assert detector._calculate_leak_severity(1500, 25) == "low"
    
    def test_get_detected_leaks(self):
        """Test getting detected leaks within time period."""
        detector = MemoryLeakDetector()
        
        # Add mock leaks
        now = datetime.now()
        old_leak = MemoryLeak(
            object_type="OldObject",
            count_increase=1000,
            size_increase_mb=50,
            detection_time=now - timedelta(hours=25),
            severity="medium",
            description="Old leak"
        )
        recent_leak = MemoryLeak(
            object_type="RecentObject",
            count_increase=2000,
            size_increase_mb=100,
            detection_time=now - timedelta(hours=1),
            severity="high",
            description="Recent leak"
        )
        
        detector._detected_leaks.extend([old_leak, recent_leak])
        
        # Get leaks from last 24 hours
        recent_leaks = detector.get_detected_leaks(24)
        
        assert len(recent_leaks) == 1
        assert recent_leaks[0]['object_type'] == "RecentObject"
        assert recent_leaks[0]['severity'] == "high"


class TestGarbageCollectionOptimizer:
    """Test garbage collection optimization functionality."""
    
    def test_optimizer_initialization(self):
        """Test GC optimizer initialization."""
        optimizer = GarbageCollectionOptimizer()
        assert len(optimizer._gc_stats) == 0
        assert len(optimizer._optimization_history) == 0
        assert 'generation_0' in optimizer._gc_thresholds
    
    @patch('gc.collect')
    @patch('psutil.Process')
    def test_optimize_garbage_collection(self, mock_process, mock_gc_collect):
        """Test garbage collection optimization."""
        optimizer = GarbageCollectionOptimizer()
        
        # Mock process memory info
        mock_memory_info = Mock()
        mock_memory_info.rss = 1024 * 1024 * 1024  # 1GB
        mock_process.return_value.memory_info.return_value = mock_memory_info
        
        # Mock GC collection results
        mock_gc_collect.side_effect = [100, 50, 25]  # Objects collected per generation
        
        # Run optimization
        optimizations = optimizer.optimize_garbage_collection()
        
        assert len(optimizations) == 3
        assert all(isinstance(opt, GCOptimization) for opt in optimizations)
        assert mock_gc_collect.call_count == 3
    
    @patch('gc.get_count')
    @patch('gc.get_stats')
    def test_get_gc_statistics(self, mock_get_stats, mock_get_count):
        """Test getting GC statistics."""
        optimizer = GarbageCollectionOptimizer()
        
        # Mock GC data
        mock_get_count.return_value = (100, 10, 5)
        mock_get_stats.return_value = [
            {'collections': 50, 'collected': 1000, 'uncollectable': 0},
            {'collections': 5, 'collected': 100, 'uncollectable': 0},
            {'collections': 1, 'collected': 10, 'uncollectable': 0}
        ]
        
        # Get statistics
        stats = optimizer.get_gc_statistics()
        
        assert 'current_state' in stats
        assert 'recent_activity' in stats
        assert 'generation_stats' in stats
        assert stats['current_state']['total_objects'] == 115
    
    def test_tune_gc_thresholds(self):
        """Test tuning GC thresholds."""
        optimizer = GarbageCollectionOptimizer()
        
        # Tune thresholds
        result = optimizer.tune_gc_thresholds(gen0=800, gen1=15, gen2=15)
        
        assert result is True
        assert optimizer._gc_thresholds['generation_0'] == 800
        assert optimizer._gc_thresholds['generation_1'] == 15
        assert optimizer._gc_thresholds['generation_2'] == 15


class TestMemoryOptimizer:
    """Test main memory optimizer functionality."""
    
    @patch('src.multimodal_librarian.monitoring.memory_optimizer.MemoryProfiler')
    @patch('src.multimodal_librarian.monitoring.memory_optimizer.MemoryLeakDetector')
    @patch('src.multimodal_librarian.monitoring.memory_optimizer.GarbageCollectionOptimizer')
    def test_optimizer_initialization(self, mock_gc_opt, mock_leak_det, mock_profiler):
        """Test memory optimizer initialization."""
        optimizer = MemoryOptimizer()
        
        assert optimizer.profiler is not None
        assert optimizer.leak_detector is not None
        assert optimizer.gc_optimizer is not None
        # Now we expect at least one snapshot (initial snapshot)
        assert len(optimizer._memory_snapshots) >= 1
    
    @patch('psutil.virtual_memory')
    @patch('psutil.Process')
    @patch('gc.get_count')
    def test_take_memory_snapshot(self, mock_gc_count, mock_process, mock_virtual_memory):
        """Test taking memory snapshots."""
        optimizer = MemoryOptimizer()
        
        # Mock system memory
        mock_memory = Mock()
        mock_memory.total = 8 * 1024 * 1024 * 1024  # 8GB
        mock_memory.used = 4 * 1024 * 1024 * 1024   # 4GB
        mock_memory.available = 4 * 1024 * 1024 * 1024  # 4GB
        mock_memory.percent = 50.0
        mock_virtual_memory.return_value = mock_memory
        
        # Mock process memory
        mock_process_memory = Mock()
        mock_process_memory.rss = 512 * 1024 * 1024  # 512MB
        mock_process.return_value.memory_info.return_value = mock_process_memory
        
        # Mock GC counts
        mock_gc_count.return_value = (100, 10, 5)
        
        # Mock profiler
        optimizer.profiler.get_top_memory_consumers = Mock(return_value=[])
        
        # Take snapshot
        snapshot = optimizer._take_memory_snapshot()
        
        assert isinstance(snapshot, MemorySnapshot)
        assert snapshot.total_memory_mb == 8192.0
        assert snapshot.used_memory_mb == 4096.0
        assert snapshot.memory_percent == 50.0
        assert snapshot.process_memory_mb == 512.0
    
    def test_check_memory_thresholds(self):
        """Test memory threshold checking."""
        optimizer = MemoryOptimizer()
        
        # Mock GC optimizer
        optimizer.gc_optimizer.optimize_garbage_collection = Mock(return_value=[])
        
        # Test critical system memory
        critical_snapshot = MemorySnapshot(
            timestamp=datetime.now(),
            total_memory_mb=8192,
            used_memory_mb=7372,  # 90%+
            available_memory_mb=820,
            memory_percent=95.0,
            process_memory_mb=512,
            process_memory_percent=6.25,
            gc_stats={},
            top_objects=[]
        )
        
        with patch.object(optimizer.logger, 'critical') as mock_critical:
            optimizer._check_memory_thresholds(critical_snapshot)
            mock_critical.assert_called_once()
            optimizer.gc_optimizer.optimize_garbage_collection.assert_called_once()
    
    def test_get_memory_status(self):
        """Test getting memory status."""
        optimizer = MemoryOptimizer()
        
        # Add mock snapshot
        mock_snapshot = MemorySnapshot(
            timestamp=datetime.now(),
            total_memory_mb=8192,
            used_memory_mb=4096,
            available_memory_mb=4096,
            memory_percent=50.0,
            process_memory_mb=512,
            process_memory_percent=6.25,
            gc_stats={'total_objects': 115},
            top_objects=[]
        )
        
        optimizer._memory_snapshots.append(mock_snapshot)
        
        # Mock components
        optimizer.leak_detector.get_detected_leaks = Mock(return_value=[])
        optimizer.gc_optimizer.get_gc_statistics = Mock(return_value={})
        
        # Get status
        status = optimizer.get_memory_status()
        
        assert 'system_memory' in status
        assert 'process_memory' in status
        assert 'garbage_collection' in status
        assert status['system_memory']['usage_percent'] == 50.0
        assert status['process_memory']['used_mb'] == 512.0
    
    def test_optimize_memory(self):
        """Test memory optimization process."""
        optimizer = MemoryOptimizer()
        
        # Mock components
        mock_gc_optimization = GCOptimization(
            generation=0,
            objects_collected=100,
            time_taken_ms=50.0,
            memory_freed_mb=10.0,
            optimization_applied="Generation 0 collection"
        )
        
        optimizer.gc_optimizer.optimize_garbage_collection = Mock(
            return_value=[mock_gc_optimization]
        )
        
        # Mock memory snapshots
        optimizer._take_memory_snapshot = Mock(side_effect=[
            MemorySnapshot(
                timestamp=datetime.now(),
                total_memory_mb=8192,
                used_memory_mb=4096,
                available_memory_mb=4096,
                memory_percent=50.0,
                process_memory_mb=600,
                process_memory_percent=7.3,
                gc_stats={},
                top_objects=[]
            ),
            MemorySnapshot(
                timestamp=datetime.now(),
                total_memory_mb=8192,
                used_memory_mb=4086,
                available_memory_mb=4106,
                memory_percent=49.9,
                process_memory_mb=590,
                process_memory_percent=7.2,
                gc_stats={},
                top_objects=[]
            )
        ])
        
        # Run optimization
        result = optimizer.optimize_memory()
        
        assert 'optimizations_applied' in result
        assert 'memory_before' in result
        assert 'memory_after' in result
        assert 'performance_impact' in result
        assert len(result['optimizations_applied']) > 0
    
    def test_generate_memory_recommendations(self):
        """Test memory recommendation generation."""
        optimizer = MemoryOptimizer()
        
        # Mock high memory usage status
        high_memory_status = {
            'system_memory': {'usage_percent': 90},
            'process_memory': {'used_mb': 2048},
            'detected_leaks': [
                {'severity': 'critical', 'object_type': 'TestObject'}
            ],
            'garbage_collection': {
                'recent_activity': {'avg_collection_time_ms': 150}
            }
        }
        
        recommendations = optimizer._generate_memory_recommendations(high_memory_status)
        
        assert len(recommendations) >= 3  # Should have multiple recommendations
        
        # Check for specific recommendation types
        rec_types = [rec['type'] for rec in recommendations]
        assert 'system_memory' in rec_types
        assert 'process_memory' in rec_types
        assert 'memory_leaks' in rec_types
    
    def test_calculate_memory_health_score(self):
        """Test memory health score calculation."""
        optimizer = MemoryOptimizer()
        
        # Test healthy memory status
        healthy_status = {
            'system_memory': {'usage_percent': 60},
            'process_memory': {'used_mb': 800},
            'detected_leaks': []
        }
        
        health_score = optimizer._calculate_memory_health_score(healthy_status)
        
        assert health_score['score'] >= 80
        assert health_score['status'] in ['excellent', 'good']
        
        # Test unhealthy memory status
        unhealthy_status = {
            'system_memory': {'usage_percent': 95},
            'process_memory': {'used_mb': 3000},
            'detected_leaks': [
                {'severity': 'critical'},
                {'severity': 'critical'}
            ]
        }
        
        unhealthy_health_score = optimizer._calculate_memory_health_score(unhealthy_status)
        
        assert unhealthy_health_score['score'] < 50
        assert unhealthy_health_score['status'] in ['poor', 'critical']


@pytest.mark.asyncio
class TestMemoryOptimizationIntegration:
    """Integration tests for memory optimization."""
    
    async def test_memory_monitoring_lifecycle(self):
        """Test complete memory monitoring lifecycle."""
        optimizer = MemoryOptimizer()
        
        # Give the monitoring thread time to start
        import time
        time.sleep(0.2)
        
        # Check that monitoring is working by verifying we can get status
        status = optimizer.get_memory_status()
        assert 'system_memory' in status
        assert 'process_memory' in status
        
        # Stop monitoring
        optimizer.stop_monitoring()
        assert not optimizer._monitoring_active
    
    async def test_memory_optimization_workflow(self):
        """Test complete memory optimization workflow."""
        optimizer = MemoryOptimizer()
        
        # Mock components for testing
        optimizer.gc_optimizer.optimize_garbage_collection = Mock(return_value=[])
        optimizer._take_memory_snapshot = Mock(return_value=MemorySnapshot(
            timestamp=datetime.now(),
            total_memory_mb=8192,
            used_memory_mb=4096,
            available_memory_mb=4096,
            memory_percent=50.0,
            process_memory_mb=512,
            process_memory_percent=6.25,
            gc_stats={},
            top_objects=[]
        ))
        
        # Run optimization workflow
        result = optimizer.optimize_memory()
        
        # Verify results
        assert 'optimizations_applied' in result
        assert 'performance_impact' in result
        assert result['performance_impact']['total_time_ms'] >= 0
    
    async def test_memory_leak_detection_workflow(self):
        """Test memory leak detection workflow."""
        optimizer = MemoryOptimizer()
        
        # Simulate leak detection
        with patch.object(optimizer.leak_detector, 'track_objects') as mock_track:
            # Manually trigger object tracking
            optimizer.leak_detector.track_objects()
            mock_track.assert_called_once()
        
        # Get detected leaks
        leaks = optimizer.leak_detector.get_detected_leaks(24)
        assert isinstance(leaks, list)


if __name__ == "__main__":
    pytest.main([__file__])