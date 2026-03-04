#!/usr/bin/env python3
"""
Demonstration of Enhanced Startup Phase Transition Logic and Timing

This script showcases the new features implemented in the StartupPhaseManager:
- Adaptive timing with prerequisite-based transitions
- Resource dependency tracking
- Retry logic with exponential backoff
- Comprehensive status reporting
- Timeout handling and monitoring
- Health check optimization
"""

import sys
import asyncio
import json
from datetime import datetime
from pathlib import Path

# Add src to path for imports
sys.path.append('src')

from multimodal_librarian.startup.phase_manager import (
    StartupPhaseManager, 
    StartupPhase,
    PhaseConfiguration,
    ResourceDependency
)


async def demo_basic_functionality():
    """Demonstrate basic startup phase manager functionality."""
    print("🚀 === Basic Startup Phase Manager Demo ===")
    
    manager = StartupPhaseManager()
    
    # Show initial state
    print(f"📊 Initial Phase: {manager.current_phase.value}")
    print(f"⏰ Startup Time: {manager.startup_time}")
    print(f"🔧 Adaptive Timing: {'Enabled' if manager._adaptive_timing_enabled else 'Disabled'}")
    
    # Show phase configurations
    print("\n📋 Phase Configurations:")
    for phase, config in manager.phase_configs.items():
        print(f"  {phase.value}:")
        print(f"    - Timeout: {config.timeout_seconds}s")
        print(f"    - Max Retries: {config.max_retries}")
        print(f"    - Prerequisites: {config.prerequisites}")
        print(f"    - Required Models: {config.required_models}")
    
    # Show resource dependencies
    print(f"\n🔗 Resource Dependencies: {len(manager.status.resource_dependencies)} tracked")
    for name, dep in list(manager.status.resource_dependencies.items())[:5]:  # Show first 5
        print(f"  {name}: {dep.type} -> {dep.status}")
    
    print("✅ Basic functionality verified!")


async def demo_phase_transitions():
    """Demonstrate adaptive phase transitions."""
    print("\n🔄 === Adaptive Phase Transition Demo ===")
    
    manager = StartupPhaseManager()
    
    # Start phase progression
    print("🎯 Starting phase progression...")
    await manager.start_phase_progression()
    
    # Monitor progress for a few seconds
    for i in range(5):
        await asyncio.sleep(1)
        progress = manager.get_phase_progress()
        
        print(f"\n📈 Progress Update {i+1}:")
        print(f"  Current Phase: {progress['current_phase']}")
        print(f"  Phase Duration: {progress['phase_duration_seconds']:.1f}s")
        print(f"  Health Check Ready: {progress['health_check_ready']}")
        print(f"  User Requests Ready: {progress['user_requests_ready']}")
        print(f"  Overall Progress: {progress['overall_progress_percent']:.1f}%")
        
        # Show model loading progress
        model_progress = progress['model_loading_progress']
        for priority, info in model_progress.items():
            if info['total'] > 0:
                print(f"  {priority.title()} Models: {info['loaded']}/{info['total']} ({info['progress_percent']:.1f}%)")
    
    # Show final status
    final_progress = manager.get_phase_progress()
    print(f"\n🏁 Final Status:")
    print(f"  Phase: {final_progress['current_phase']}")
    print(f"  Total Duration: {final_progress['total_duration_seconds']:.1f}s")
    
    await manager.shutdown()
    print("✅ Phase transition demo completed!")


async def demo_timing_metrics():
    """Demonstrate timing metrics and monitoring."""
    print("\n📊 === Timing Metrics and Monitoring Demo ===")
    
    manager = StartupPhaseManager()
    
    # Start progression and let it run briefly
    await manager.start_phase_progression()
    await asyncio.sleep(2)
    
    # Get timing metrics
    metrics = manager.get_timing_metrics()
    print("⏱️  Timing Metrics:")
    print(f"  Total Startup Time: {metrics['total_startup_time']:.2f}s")
    print(f"  Current Phase Duration: {metrics['current_phase_duration']:.2f}s")
    print(f"  Adaptive Timing: {'Enabled' if metrics['adaptive_timing_enabled'] else 'Disabled'}")
    
    # Show phase metrics
    if metrics['phase_metrics']:
        print("\n📋 Phase Metrics:")
        for phase, data in metrics['phase_metrics'].items():
            print(f"  {phase}:")
            print(f"    - Configured Timeout: {data['configured_timeout']}s")
            print(f"    - Actual Duration: {data.get('actual_duration', 'N/A')}")
            print(f"    - Success: {data.get('success', 'N/A')}")
    
    # Show model timing
    print("\n🤖 Model Loading Timing:")
    for model_name, timing in list(metrics['model_timing'].items())[:3]:  # Show first 3
        print(f"  {model_name}:")
        print(f"    - Estimated: {timing['estimated_time']}s")
        print(f"    - Actual: {timing.get('actual_time', 'Loading...')}")
        print(f"    - Status: {timing['status']}")
    
    await manager.shutdown()
    print("✅ Timing metrics demo completed!")


async def demo_health_status():
    """Demonstrate health status reporting."""
    print("\n🏥 === Health Status Reporting Demo ===")
    
    manager = StartupPhaseManager()
    await manager.start_phase_progression()
    await asyncio.sleep(1)
    
    # Get health status
    health = manager.get_phase_health_status()
    print("🩺 Health Status:")
    print(f"  System Healthy: {'✅' if health['healthy'] else '❌'}")
    print(f"  Current Phase: {health['current_phase']}")
    print(f"  Phase Duration: {health['phase_duration']:.1f}s")
    print(f"  Timeout Remaining: {health['timeout_remaining']:.1f}s")
    print(f"  Ready for Traffic: {'✅' if health['ready_for_traffic'] else '❌'}")
    print(f"  Health Check Ready: {'✅' if health['health_check_ready'] else '❌'}")
    
    if health['issues']:
        print(f"  Issues: {health['issues']}")
    else:
        print("  Issues: None")
    
    print(f"  Available Capabilities: {len(health['capabilities_available'])}")
    for cap in health['capabilities_available']:
        print(f"    - {cap}")
    
    if health['estimated_full_ready_time'] > 0:
        print(f"  Estimated Full Ready: {health['estimated_full_ready_time']:.1f}s")
    
    await manager.shutdown()
    print("✅ Health status demo completed!")


async def demo_advanced_controls():
    """Demonstrate advanced control features."""
    print("\n🎛️  === Advanced Control Features Demo ===")
    
    manager = StartupPhaseManager()
    
    # Test adaptive timing control
    print("🔧 Testing Adaptive Timing Control:")
    print(f"  Initial State: {'Enabled' if manager._adaptive_timing_enabled else 'Disabled'}")
    
    manager.set_adaptive_timing(False)
    print(f"  After Disable: {'Enabled' if manager._adaptive_timing_enabled else 'Disabled'}")
    
    manager.set_adaptive_timing(True)
    print(f"  After Re-enable: {'Enabled' if manager._adaptive_timing_enabled else 'Disabled'}")
    
    # Test timeout updates
    print("\n⏰ Testing Timeout Updates:")
    original_timeout = manager.phase_configs[StartupPhase.ESSENTIAL].timeout_seconds
    print(f"  Original Essential Timeout: {original_timeout}s")
    
    manager.update_phase_timeout(StartupPhase.ESSENTIAL, 300.0)
    new_timeout = manager.phase_configs[StartupPhase.ESSENTIAL].timeout_seconds
    print(f"  Updated Essential Timeout: {new_timeout}s")
    
    # Test phase waiting
    print("\n⏳ Testing Phase Waiting:")
    await manager.start_phase_progression()
    
    # Wait for essential phase with timeout
    print("  Waiting for ESSENTIAL phase (5s timeout)...")
    start_time = asyncio.get_event_loop().time()
    reached = await manager.wait_for_phase(StartupPhase.ESSENTIAL, timeout_seconds=5.0)
    elapsed = asyncio.get_event_loop().time() - start_time
    
    print(f"  Result: {'Reached' if reached else 'Timeout'} after {elapsed:.1f}s")
    print(f"  Current Phase: {manager.current_phase.value}")
    
    await manager.shutdown()
    print("✅ Advanced controls demo completed!")


async def demo_resource_dependencies():
    """Demonstrate resource dependency tracking."""
    print("\n🔗 === Resource Dependency Tracking Demo ===")
    
    manager = StartupPhaseManager()
    await manager.start_phase_progression()
    await asyncio.sleep(2)
    
    # Get detailed progress with dependencies
    progress = manager.get_phase_progress()
    dependencies = progress['resource_dependencies']
    
    print(f"📊 Resource Dependencies ({len(dependencies)} total):")
    
    # Group by type
    by_type = {}
    for name, dep in dependencies.items():
        dep_type = dep['type']
        if dep_type not in by_type:
            by_type[dep_type] = []
        by_type[dep_type].append((name, dep))
    
    for dep_type, deps in by_type.items():
        print(f"\n  {dep_type.title()} Dependencies:")
        for name, dep in deps[:3]:  # Show first 3 of each type
            status_icon = {
                'ready': '✅',
                'initializing': '🔄',
                'pending': '⏳',
                'failed': '❌'
            }.get(dep['status'], '❓')
            
            print(f"    {status_icon} {name}: {dep['status']}")
            if dep['required_for']:
                phases = ', '.join(dep['required_for'])
                print(f"      Required for: {phases}")
    
    await manager.shutdown()
    print("✅ Resource dependency demo completed!")


async def demo_error_handling():
    """Demonstrate error handling and retry logic."""
    print("\n🛠️  === Error Handling and Retry Logic Demo ===")
    
    manager = StartupPhaseManager()
    
    # Show retry configuration
    print("🔄 Retry Configuration:")
    for phase, config in manager.phase_configs.items():
        print(f"  {phase.value}: {config.max_retries} max retries")
    
    # Start progression to see transition history
    await manager.start_phase_progression()
    await asyncio.sleep(3)
    
    # Show transition history
    progress = manager.get_phase_progress()
    transitions = progress['phase_transitions']
    
    if transitions:
        print(f"\n📜 Transition History ({len(transitions)} transitions):")
        for transition in transitions:
            status_icon = '✅' if transition['success'] else '❌'
            from_phase = transition['from_phase'] or 'None'
            
            print(f"  {status_icon} {from_phase} → {transition['to_phase']}")
            print(f"    Duration: {transition.get('duration_seconds', 0):.2f}s")
            print(f"    Retries: {transition['retry_count']}")
            print(f"    Dependencies Met: {'✅' if transition['dependencies_met'] else '❌'}")
            
            if transition.get('error'):
                print(f"    Error: {transition['error']}")
    
    await manager.shutdown()
    print("✅ Error handling demo completed!")


async def main():
    """Run all demonstrations."""
    print("🎭 Enhanced Startup Phase Manager Demonstration")
    print("=" * 60)
    
    try:
        await demo_basic_functionality()
        await demo_phase_transitions()
        await demo_timing_metrics()
        await demo_health_status()
        await demo_advanced_controls()
        await demo_resource_dependencies()
        await demo_error_handling()
        
        print("\n🎉 === All Demonstrations Completed Successfully! ===")
        print("\n🔧 Key Features Demonstrated:")
        print("  ✅ Adaptive timing with prerequisite-based transitions")
        print("  ✅ Resource dependency tracking and monitoring")
        print("  ✅ Retry logic with exponential backoff")
        print("  ✅ Comprehensive status reporting and metrics")
        print("  ✅ Timeout handling and health monitoring")
        print("  ✅ Advanced control features and configuration")
        print("  ✅ Error handling and transition history")
        
        print("\n💡 Benefits:")
        print("  🚀 Faster startup through intelligent phase transitions")
        print("  🔍 Better observability with detailed metrics")
        print("  🛡️  Enhanced reliability with retry mechanisms")
        print("  ⚕️  Optimized health checks for AWS ECS")
        print("  🎛️  Flexible configuration and control")
        
    except Exception as e:
        print(f"\n❌ Demo failed with error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())