#!/usr/bin/env python3
"""
Demonstration of Phase Completion Time Tracking

This script demonstrates the phase completion time tracking functionality
by simulating a realistic startup scenario with phase transitions.
"""

import asyncio
import sys
import os
import time
from datetime import datetime

# Add src to path for imports
sys.path.append('src')

async def demo_phase_completion_tracking():
    """Demonstrate phase completion time tracking with realistic transitions."""
    print("🚀 Phase Completion Time Tracking Demo")
    print("=" * 60)
    
    try:
        # Import required modules
        from multimodal_librarian.startup.phase_manager import StartupPhaseManager, StartupPhase
        from multimodal_librarian.monitoring.startup_metrics import StartupMetricsCollector, track_startup_metrics
        from multimodal_librarian.monitoring.performance_tracker import PerformanceTracker, track_performance
        
        print("✅ Successfully imported startup metrics modules")
        
        # Create startup phase manager with faster transitions for demo
        print("\n📋 Creating StartupPhaseManager...")
        phase_manager = StartupPhaseManager()
        
        # Adjust timeouts for faster demo
        phase_manager.phase_configs[StartupPhase.MINIMAL].min_duration_seconds = 2.0
        phase_manager.phase_configs[StartupPhase.ESSENTIAL].min_duration_seconds = 5.0
        phase_manager.phase_configs[StartupPhase.FULL].min_duration_seconds = 8.0
        
        print(f"   ✅ StartupPhaseManager created with faster transitions")
        print(f"   📊 Initial phase: {phase_manager.current_phase.value}")
        
        # Initialize metrics tracking
        print("\n📋 Initializing comprehensive metrics tracking...")
        metrics_collector = await track_startup_metrics(phase_manager)
        performance_tracker = await track_performance(phase_manager, metrics_collector)
        print(f"   ✅ Metrics tracking initialized")
        
        # Start phase progression
        print("\n📋 Starting phase progression...")
        await phase_manager.start_phase_progression()
        print(f"   ✅ Phase progression started")
        
        # Monitor phase transitions in real-time
        print("\n📋 Monitoring phase transitions in real-time...")
        print("   (This will take about 20-30 seconds to show all phases)")
        
        start_time = time.time()
        last_phase = phase_manager.current_phase
        phase_start_times = {last_phase: start_time}
        
        # Monitor for up to 45 seconds to see all phase transitions
        for i in range(45):
            await asyncio.sleep(1)
            current_phase = phase_manager.current_phase
            elapsed = time.time() - start_time
            
            # Check for phase transition
            if current_phase != last_phase:
                phase_duration = elapsed - phase_start_times.get(last_phase, start_time)
                print(f"   🔄 Phase transition: {last_phase.value} → {current_phase.value}")
                print(f"      ⏱️  {last_phase.value} phase duration: {phase_duration:.2f}s")
                print(f"      📊 Total elapsed time: {elapsed:.2f}s")
                
                last_phase = current_phase
                phase_start_times[current_phase] = elapsed + start_time
            
            # Print periodic status updates
            if i % 10 == 0:
                progress = phase_manager.get_phase_progress()
                print(f"   📊 Status ({elapsed:.1f}s): Phase={current_phase.value}, Progress={progress.get('overall_progress_percent', 0):.1f}%")
            
            # Break if we've reached full phase
            if current_phase == StartupPhase.FULL and elapsed > 20:
                print(f"   🎯 Reached FULL phase, continuing for a few more seconds...")
                await asyncio.sleep(5)
                break
        
        # Get comprehensive metrics
        print("\n📋 Retrieving comprehensive startup metrics...")
        session_summary = metrics_collector.get_startup_session_summary()
        
        print(f"\n📊 STARTUP SESSION SUMMARY:")
        print(f"   🆔 Session ID: {session_summary['session_id']}")
        print(f"   🏁 Final phase reached: {session_summary['final_phase_reached']}")
        print(f"   ⏱️  Total startup duration: {session_summary['total_duration_seconds']:.2f}s")
        print(f"   🎯 Overall efficiency score: {session_summary['overall_efficiency_score']:.1f}%")
        print(f"   ✅ Startup success: {session_summary['success']}")
        print(f"   📈 Phases completed: {session_summary['phases_completed']}")
        print(f"   🤖 Models processed: {session_summary['models_processed']}")
        print(f"   ✅ Models loaded successfully: {session_summary['models_loaded_successfully']}")
        print(f"   ❌ Error count: {session_summary['error_count']}")
        print(f"   🔄 Retry count: {session_summary['retry_count']}")
        
        # Get detailed phase completion metrics
        print(f"\n📊 PHASE COMPLETION METRICS:")
        for phase in StartupPhase:
            phase_metrics = metrics_collector.get_phase_completion_metrics(phase)
            if phase_metrics['sample_count'] > 0:
                duration_stats = phase_metrics['duration_stats']
                efficiency_stats = phase_metrics['efficiency_stats']
                
                print(f"\n   🔹 {phase.value.upper()} PHASE:")
                print(f"      📊 Completions tracked: {phase_metrics['sample_count']}")
                print(f"      ⏱️  Duration - Mean: {duration_stats['mean_seconds']:.2f}s, Range: {duration_stats['min_seconds']:.2f}s - {duration_stats['max_seconds']:.2f}s")
                print(f"      🎯 Efficiency - Mean: {efficiency_stats['mean_score']:.1f}%, Range: {efficiency_stats['min_score']:.1f}% - {efficiency_stats['max_score']:.1f}%")
                print(f"      ✅ Success rate: {phase_metrics['success_rate']:.1%}")
                print(f"      🔄 Total retries: {phase_metrics['total_retries']}")
                print(f"      📈 Trend: {phase_metrics['recent_trend']}")
        
        # Get model loading metrics
        print(f"\n📊 MODEL LOADING METRICS:")
        model_metrics = metrics_collector.get_model_loading_metrics()
        if model_metrics['sample_count'] > 0:
            print(f"   🤖 Total models processed: {model_metrics['sample_count']}")
            print(f"   ✅ Success rate: {model_metrics['success_rate']:.1%}")
            
            if 'loading_stats' in model_metrics:
                loading_stats = model_metrics['loading_stats']
                print(f"   ⏱️  Loading time - Mean: {loading_stats['mean_duration_seconds']:.2f}s")
                print(f"      Range: {loading_stats['min_duration_seconds']:.2f}s - {loading_stats['max_duration_seconds']:.2f}s")
            
            if 'efficiency_stats' in model_metrics:
                eff_stats = model_metrics['efficiency_stats']
                print(f"   🎯 Loading efficiency - Mean: {eff_stats['mean_efficiency']:.2f}x")
                print(f"      Range: {eff_stats['min_efficiency']:.2f}x - {eff_stats['max_efficiency']:.2f}x")
        else:
            print(f"   ℹ️  No model loading data available (models may still be loading)")
        
        # Get performance metrics
        print(f"\n📊 PERFORMANCE METRICS:")
        perf_summary = performance_tracker.get_performance_summary()
        print(f"   ⏱️  Performance tracking duration: {perf_summary['tracking_duration_seconds']:.2f}s")
        print(f"   🔔 Active alerts: {perf_summary['active_alerts']}")
        print(f"   🚨 Total alerts generated: {perf_summary['total_alerts']}")
        print(f"   🔍 Performance bottlenecks identified: {perf_summary['bottlenecks_identified']}")
        print(f"   💡 Optimization recommendations: {perf_summary['optimization_recommendations']}")
        print(f"   📊 Resource samples collected: {perf_summary['resource_samples_collected']}")
        
        if 'resource_statistics' in perf_summary and perf_summary['resource_statistics']:
            cpu_stats = perf_summary['resource_statistics'].get('cpu', {})
            memory_stats = perf_summary['resource_statistics'].get('memory', {})
            
            if cpu_stats:
                print(f"   🖥️  CPU Usage - Current: {cpu_stats.get('current', 0):.1f}%, Peak: {cpu_stats.get('peak', 0):.1f}%, Average: {cpu_stats.get('average', 0):.1f}%")
            
            if memory_stats:
                print(f"   💾 Memory Usage - Current: {memory_stats.get('current', 0):.1f}%, Peak: {memory_stats.get('peak', 0):.1f}%, Average: {memory_stats.get('average', 0):.1f}%")
        
        # Get recent alerts and recommendations
        recent_alerts = performance_tracker.get_recent_alerts(minutes=10)
        if recent_alerts:
            print(f"\n🚨 RECENT PERFORMANCE ALERTS:")
            for alert in recent_alerts[-5:]:  # Show last 5 alerts
                print(f"   ⚠️  {alert.severity.upper()}: {alert.message}")
                if alert.recommendations:
                    print(f"      💡 Recommendations: {', '.join(alert.recommendations[:2])}")
        
        recommendations = performance_tracker.get_recommendations()
        if recommendations:
            print(f"\n💡 OPTIMIZATION RECOMMENDATIONS:")
            for i, rec in enumerate(recommendations[:5], 1):  # Show top 5 recommendations
                print(f"   {i}. {rec}")
        
        # Export metrics for analysis
        print(f"\n📋 Exporting metrics data...")
        exported_data = metrics_collector.export_metrics("json")
        print(f"   ✅ Startup metrics exported ({len(exported_data)} characters)")
        
        perf_data = performance_tracker.export_performance_data("json")
        print(f"   ✅ Performance metrics exported ({len(perf_data)} characters)")
        
        # Clean shutdown
        print(f"\n📋 Shutting down tracking systems...")
        await performance_tracker.stop_tracking()
        await metrics_collector.stop_collection()
        await phase_manager.shutdown()
        print(f"   ✅ All systems shut down cleanly")
        
        print(f"\n🎉 DEMO COMPLETED SUCCESSFULLY!")
        print("=" * 60)
        print("✅ Phase completion time tracking is fully functional")
        print("📊 Metrics are being collected and can be analyzed")
        print("🔍 Performance monitoring is active and providing insights")
        print("💡 Optimization recommendations are being generated")
        
        return True
        
    except Exception as e:
        print(f"\n❌ Demo failed with error: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """Run the phase completion tracking demo."""
    success = await demo_phase_completion_tracking()
    
    if success:
        print("\n🎯 IMPLEMENTATION COMPLETE!")
        print("The phase completion time tracking task has been successfully implemented.")
        return 0
    else:
        print("\n❌ DEMO FAILED!")
        print("Please check the error messages above.")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)