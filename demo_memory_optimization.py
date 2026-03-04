#!/usr/bin/env python3
"""
Memory Optimization Demo Script

This script demonstrates the memory optimization functionality including:
- Real-time memory monitoring
- Memory leak detection
- Garbage collection optimization
- Memory profiling and analysis
"""

import asyncio
import time
import json
from datetime import datetime
from typing import Dict, Any

from src.multimodal_librarian.monitoring.memory_optimizer import MemoryOptimizer


class MemoryOptimizationDemo:
    """Demo class for memory optimization functionality."""
    
    def __init__(self):
        self.optimizer = MemoryOptimizer()
        self.demo_results = {}
    
    async def run_demo(self) -> Dict[str, Any]:
        """Run comprehensive memory optimization demo."""
        print("🧠 Memory Optimization Demo Starting...")
        print("=" * 60)
        
        demo_results = {
            'demo_timestamp': datetime.now().isoformat(),
            'tests_performed': [],
            'results': {}
        }
        
        try:
            # Test 1: Memory Status Monitoring
            print("\n📊 Test 1: Memory Status Monitoring")
            status_result = await self.test_memory_status()
            demo_results['tests_performed'].append('memory_status_monitoring')
            demo_results['results']['memory_status'] = status_result
            
            # Test 2: Memory Optimization
            print("\n🔧 Test 2: Memory Optimization")
            optimization_result = await self.test_memory_optimization()
            demo_results['tests_performed'].append('memory_optimization')
            demo_results['results']['memory_optimization'] = optimization_result
            
            # Test 3: Garbage Collection Optimization
            print("\n🗑️ Test 3: Garbage Collection Optimization")
            gc_result = await self.test_gc_optimization()
            demo_results['tests_performed'].append('gc_optimization')
            demo_results['results']['gc_optimization'] = gc_result
            
            # Test 4: Memory Leak Detection
            print("\n🔍 Test 4: Memory Leak Detection")
            leak_result = await self.test_leak_detection()
            demo_results['tests_performed'].append('leak_detection')
            demo_results['results']['leak_detection'] = leak_result
            
            # Test 5: Memory Profiling
            print("\n📈 Test 5: Memory Profiling")
            profiling_result = await self.test_memory_profiling()
            demo_results['tests_performed'].append('memory_profiling')
            demo_results['results']['memory_profiling'] = profiling_result
            
            # Test 6: Memory Health Assessment
            print("\n🏥 Test 6: Memory Health Assessment")
            health_result = await self.test_memory_health()
            demo_results['tests_performed'].append('memory_health')
            demo_results['results']['memory_health'] = health_result
            
            # Test 7: Memory Report Generation
            print("\n📋 Test 7: Memory Report Generation")
            report_result = await self.test_memory_report()
            demo_results['tests_performed'].append('memory_report')
            demo_results['results']['memory_report'] = report_result
            
            print("\n✅ All memory optimization tests completed successfully!")
            
        except Exception as e:
            print(f"\n❌ Demo failed with error: {e}")
            demo_results['error'] = str(e)
        
        return demo_results
    
    async def test_memory_status(self) -> Dict[str, Any]:
        """Test memory status monitoring."""
        print("   Getting current memory status...")
        
        try:
            # Get memory status
            status = self.optimizer.get_memory_status()
            
            # Extract key metrics
            system_memory = status.get('system_memory', {})
            process_memory = status.get('process_memory', {})
            gc_stats = status.get('garbage_collection', {})
            
            print(f"   ✓ System Memory Usage: {system_memory.get('usage_percent', 0):.1f}%")
            print(f"   ✓ Process Memory Usage: {process_memory.get('used_mb', 0):.1f} MB")
            print(f"   ✓ GC Objects: {gc_stats.get('current_state', {}).get('total_objects', 0)}")
            print(f"   ✓ Monitoring Status: {status.get('monitoring_status', 'unknown')}")
            
            return {
                'success': True,
                'system_memory_percent': system_memory.get('usage_percent', 0),
                'process_memory_mb': process_memory.get('used_mb', 0),
                'monitoring_active': status.get('monitoring_status') == 'active',
                'total_gc_objects': gc_stats.get('current_state', {}).get('total_objects', 0)
            }
            
        except Exception as e:
            print(f"   ❌ Memory status test failed: {e}")
            return {'success': False, 'error': str(e)}
    
    async def test_memory_optimization(self) -> Dict[str, Any]:
        """Test memory optimization process."""
        print("   Running memory optimization...")
        
        try:
            # Run optimization
            optimization_result = self.optimizer.optimize_memory()
            
            # Extract results
            memory_before = optimization_result.get('memory_before', {})
            memory_after = optimization_result.get('memory_after', {})
            performance_impact = optimization_result.get('performance_impact', {})
            optimizations = optimization_result.get('optimizations_applied', [])
            
            print(f"   ✓ Optimizations Applied: {len(optimizations)}")
            print(f"   ✓ Memory Saved: {performance_impact.get('memory_saved_mb', 0):.2f} MB")
            print(f"   ✓ Optimization Time: {performance_impact.get('total_time_ms', 0):.2f} ms")
            print(f"   ✓ System Memory Improvement: {performance_impact.get('system_memory_improvement_percent', 0):.2f}%")
            
            return {
                'success': True,
                'optimizations_count': len(optimizations),
                'memory_saved_mb': performance_impact.get('memory_saved_mb', 0),
                'optimization_time_ms': performance_impact.get('total_time_ms', 0),
                'system_improvement_percent': performance_impact.get('system_memory_improvement_percent', 0),
                'memory_before_mb': memory_before.get('process_mb', 0),
                'memory_after_mb': memory_after.get('process_mb', 0)
            }
            
        except Exception as e:
            print(f"   ❌ Memory optimization test failed: {e}")
            return {'success': False, 'error': str(e)}
    
    async def test_gc_optimization(self) -> Dict[str, Any]:
        """Test garbage collection optimization."""
        print("   Optimizing garbage collection...")
        
        try:
            # Get initial GC stats
            initial_stats = self.optimizer.gc_optimizer.get_gc_statistics()
            
            # Run GC optimization
            optimizations = self.optimizer.gc_optimizer.optimize_garbage_collection()
            
            # Get final GC stats
            final_stats = self.optimizer.gc_optimizer.get_gc_statistics()
            
            # Calculate results
            total_objects_collected = sum(opt.objects_collected for opt in optimizations)
            total_memory_freed = sum(opt.memory_freed_mb for opt in optimizations)
            total_time_taken = sum(opt.time_taken_ms for opt in optimizations)
            
            print(f"   ✓ Generations Optimized: {len(optimizations)}")
            print(f"   ✓ Objects Collected: {total_objects_collected}")
            print(f"   ✓ Memory Freed: {total_memory_freed:.2f} MB")
            print(f"   ✓ Total Time: {total_time_taken:.2f} ms")
            
            return {
                'success': True,
                'generations_optimized': len(optimizations),
                'total_objects_collected': total_objects_collected,
                'total_memory_freed_mb': total_memory_freed,
                'total_time_ms': total_time_taken,
                'initial_objects': initial_stats.get('current_state', {}).get('total_objects', 0),
                'final_objects': final_stats.get('current_state', {}).get('total_objects', 0)
            }
            
        except Exception as e:
            print(f"   ❌ GC optimization test failed: {e}")
            return {'success': False, 'error': str(e)}
    
    async def test_leak_detection(self) -> Dict[str, Any]:
        """Test memory leak detection."""
        print("   Testing memory leak detection...")
        
        try:
            # Simulate some object creation to potentially detect patterns
            test_objects = []
            for i in range(1000):
                test_objects.append(f"test_object_{i}" * 10)
            
            # Track objects
            self.optimizer.leak_detector.track_objects()
            
            # Wait a bit and track again
            await asyncio.sleep(1)
            self.optimizer.leak_detector.track_objects()
            
            # Get detected leaks
            detected_leaks = self.optimizer.leak_detector.get_detected_leaks(1)  # Last hour
            
            # Categorize leaks by severity
            leak_counts = {
                'critical': len([leak for leak in detected_leaks if leak['severity'] == 'critical']),
                'high': len([leak for leak in detected_leaks if leak['severity'] == 'high']),
                'medium': len([leak for leak in detected_leaks if leak['severity'] == 'medium']),
                'low': len([leak for leak in detected_leaks if leak['severity'] == 'low'])
            }
            
            print(f"   ✓ Total Leaks Detected: {len(detected_leaks)}")
            print(f"   ✓ Critical Leaks: {leak_counts['critical']}")
            print(f"   ✓ High Severity Leaks: {leak_counts['high']}")
            print(f"   ✓ Medium Severity Leaks: {leak_counts['medium']}")
            print(f"   ✓ Low Severity Leaks: {leak_counts['low']}")
            
            # Clean up test objects
            del test_objects
            
            return {
                'success': True,
                'total_leaks': len(detected_leaks),
                'leak_counts': leak_counts,
                'detected_leaks': detected_leaks[:3]  # First 3 leaks for details
            }
            
        except Exception as e:
            print(f"   ❌ Leak detection test failed: {e}")
            return {'success': False, 'error': str(e)}
    
    async def test_memory_profiling(self) -> Dict[str, Any]:
        """Test memory profiling functionality."""
        print("   Testing memory profiling...")
        
        try:
            # Take memory snapshot
            snapshot = self.optimizer.profiler.take_snapshot()
            
            # Get top memory consumers
            top_consumers = self.optimizer.profiler.get_top_memory_consumers(5)
            
            # Compare snapshots if we have multiple
            comparison = None
            if len(self.optimizer.profiler._snapshots) >= 2:
                comparison = self.optimizer.profiler.compare_snapshots()
            
            print(f"   ✓ Snapshot Taken: {'Yes' if snapshot else 'No'}")
            print(f"   ✓ Top Consumers Found: {len(top_consumers)}")
            print(f"   ✓ Snapshot Comparison: {'Available' if comparison else 'Not enough snapshots'}")
            
            # Display top consumers
            if top_consumers:
                print("   ✓ Top Memory Consumers:")
                for i, consumer in enumerate(top_consumers[:3], 1):
                    print(f"      {i}. {consumer.get('filename', 'unknown')}: {consumer.get('size_mb', 0):.2f} MB")
            
            return {
                'success': True,
                'snapshot_taken': snapshot is not None,
                'top_consumers_count': len(top_consumers),
                'top_consumers': top_consumers[:3],
                'comparison_available': comparison is not None,
                'comparison_data': comparison if comparison and 'error' not in comparison else None
            }
            
        except Exception as e:
            print(f"   ❌ Memory profiling test failed: {e}")
            return {'success': False, 'error': str(e)}
    
    async def test_memory_health(self) -> Dict[str, Any]:
        """Test memory health assessment."""
        print("   Assessing memory health...")
        
        try:
            # Get memory status
            memory_status = self.optimizer.get_memory_status()
            
            # Calculate health score
            health_score = self.optimizer._calculate_memory_health_score(memory_status)
            
            # Get recommendations
            recommendations = self.optimizer._generate_memory_recommendations(memory_status)
            
            print(f"   ✓ Health Score: {health_score['score']}/100")
            print(f"   ✓ Health Status: {health_score['status']}")
            print(f"   ✓ Recommendations: {len(recommendations)}")
            
            # Display critical recommendations
            critical_recs = [rec for rec in recommendations if rec.get('severity') == 'critical']
            if critical_recs:
                print("   ⚠️ Critical Recommendations:")
                for rec in critical_recs[:2]:
                    print(f"      - {rec.get('message', 'Unknown issue')}")
            
            return {
                'success': True,
                'health_score': health_score['score'],
                'health_status': health_score['status'],
                'health_factors': health_score.get('factors', []),
                'recommendations_count': len(recommendations),
                'critical_recommendations': len(critical_recs),
                'recommendations': recommendations[:3]  # Top 3 recommendations
            }
            
        except Exception as e:
            print(f"   ❌ Memory health test failed: {e}")
            return {'success': False, 'error': str(e)}
    
    async def test_memory_report(self) -> Dict[str, Any]:
        """Test memory report generation."""
        print("   Generating memory report...")
        
        try:
            # Generate comprehensive report
            report = self.optimizer.get_memory_report()
            
            # Extract key information
            current_status = report.get('current_status', {})
            historical_data = report.get('historical_data', [])
            recommendations = report.get('recommendations', [])
            health_score = report.get('health_score', {})
            
            print(f"   ✓ Report Generated: {report.get('report_timestamp', 'Unknown time')}")
            print(f"   ✓ Historical Data Points: {len(historical_data)}")
            print(f"   ✓ Recommendations: {len(recommendations)}")
            print(f"   ✓ Overall Health: {health_score.get('status', 'unknown')}")
            
            return {
                'success': True,
                'report_timestamp': report.get('report_timestamp'),
                'historical_data_points': len(historical_data),
                'recommendations_count': len(recommendations),
                'health_status': health_score.get('status'),
                'health_score': health_score.get('score', 0),
                'system_memory_percent': current_status.get('system_memory', {}).get('usage_percent', 0),
                'process_memory_mb': current_status.get('process_memory', {}).get('used_mb', 0)
            }
            
        except Exception as e:
            print(f"   ❌ Memory report test failed: {e}")
            return {'success': False, 'error': str(e)}
    
    def create_memory_load(self, size_mb: int = 50) -> list:
        """Create memory load for testing purposes."""
        print(f"   Creating {size_mb}MB memory load for testing...")
        
        # Create large objects to consume memory
        memory_load = []
        bytes_per_mb = 1024 * 1024
        
        for i in range(size_mb):
            # Create 1MB of data
            data = bytearray(bytes_per_mb)
            memory_load.append(data)
        
        return memory_load
    
    async def demonstrate_memory_optimization_cycle(self) -> Dict[str, Any]:
        """Demonstrate a complete memory optimization cycle."""
        print("\n🔄 Demonstrating Memory Optimization Cycle")
        print("-" * 50)
        
        try:
            # Step 1: Get baseline memory usage
            print("1. Getting baseline memory usage...")
            baseline_status = self.optimizer.get_memory_status()
            baseline_memory = baseline_status.get('process_memory', {}).get('used_mb', 0)
            print(f"   Baseline Memory: {baseline_memory:.1f} MB")
            
            # Step 2: Create memory load
            print("2. Creating memory load...")
            memory_load = self.create_memory_load(100)  # 100MB load
            
            # Step 3: Check memory usage after load
            print("3. Checking memory usage after load...")
            loaded_status = self.optimizer.get_memory_status()
            loaded_memory = loaded_status.get('process_memory', {}).get('used_mb', 0)
            memory_increase = loaded_memory - baseline_memory
            print(f"   Memory After Load: {loaded_memory:.1f} MB (+{memory_increase:.1f} MB)")
            
            # Step 4: Run memory optimization
            print("4. Running memory optimization...")
            optimization_result = self.optimizer.optimize_memory()
            
            # Step 5: Clear the memory load
            print("5. Clearing memory load...")
            del memory_load
            
            # Step 6: Check final memory usage
            print("6. Checking final memory usage...")
            final_status = self.optimizer.get_memory_status()
            final_memory = final_status.get('process_memory', {}).get('used_mb', 0)
            total_reduction = loaded_memory - final_memory
            print(f"   Final Memory: {final_memory:.1f} MB (-{total_reduction:.1f} MB)")
            
            # Step 7: Generate summary
            cycle_summary = {
                'baseline_memory_mb': baseline_memory,
                'loaded_memory_mb': loaded_memory,
                'final_memory_mb': final_memory,
                'memory_increase_mb': memory_increase,
                'memory_reduction_mb': total_reduction,
                'optimization_effectiveness': (total_reduction / memory_increase * 100) if memory_increase > 0 else 0,
                'optimization_details': optimization_result
            }
            
            print(f"   ✓ Optimization Effectiveness: {cycle_summary['optimization_effectiveness']:.1f}%")
            
            return {
                'success': True,
                'cycle_summary': cycle_summary
            }
            
        except Exception as e:
            print(f"   ❌ Memory optimization cycle failed: {e}")
            return {'success': False, 'error': str(e)}


async def main():
    """Main demo function."""
    print("🚀 Starting Memory Optimization Demo")
    print("This demo will test all memory optimization features...")
    
    demo = MemoryOptimizationDemo()
    
    try:
        # Run main demo
        demo_results = await demo.run_demo()
        
        # Run optimization cycle demonstration
        cycle_results = await demo.demonstrate_memory_optimization_cycle()
        demo_results['optimization_cycle'] = cycle_results
        
        # Save results
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        results_file = f'memory_optimization_demo_results_{timestamp}.json'
        
        with open(results_file, 'w') as f:
            json.dump(demo_results, f, indent=2, default=str)
        
        print(f"\n📄 Demo results saved to: {results_file}")
        
        # Print summary
        print("\n📊 Demo Summary:")
        print(f"   Tests Performed: {len(demo_results.get('tests_performed', []))}")
        print(f"   Successful Tests: {sum(1 for test, result in demo_results.get('results', {}).items() if result.get('success', False))}")
        
        if 'error' not in demo_results:
            print("   Overall Status: ✅ SUCCESS")
        else:
            print(f"   Overall Status: ❌ FAILED - {demo_results['error']}")
        
        return demo_results
        
    except Exception as e:
        print(f"\n💥 Demo failed with error: {e}")
        return {'success': False, 'error': str(e)}
    
    finally:
        # Clean up
        if hasattr(demo, 'optimizer'):
            demo.optimizer.stop_monitoring()
            print("\n🧹 Cleanup completed")


if __name__ == "__main__":
    # Run the demo
    results = asyncio.run(main())
    
    # Exit with appropriate code
    exit(0 if results.get('success', False) else 1)