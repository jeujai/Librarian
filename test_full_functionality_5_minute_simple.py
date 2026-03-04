"""
Simple Test: Full Functionality Available Within 5 Minutes

This test validates that all application functionality becomes available within 5 minutes
of startup, including all models loaded and all capabilities ready.

Success Criteria:
- All models (essential, standard, advanced) loaded within 5 minutes
- All capabilities available within 5 minutes
- FULL phase reached within 5 minutes
"""

import asyncio
import sys
from datetime import datetime, timedelta

from src.multimodal_librarian.startup.phase_manager import (
    StartupPhaseManager,
    StartupPhase
)
from src.multimodal_librarian.startup.progressive_loader import ProgressiveLoader
from src.multimodal_librarian.models.model_manager import get_model_manager


async def test_full_functionality_within_5_minutes():
    """
    Test that full functionality is available within 5 minutes.
    
    This is the main validation test for the success criterion.
    """
    # Create startup phase manager
    phase_manager = StartupPhaseManager()
    
    # Create progressive loader with phase manager
    progressive_loader = ProgressiveLoader(phase_manager)
    
    # Get model manager
    model_manager = get_model_manager()
    
    # Record start time
    start_time = datetime.now()
    max_duration = timedelta(minutes=5)
    
    print(f"\n{'='*80}")
    print(f"FULL FUNCTIONALITY 5-MINUTE VALIDATION TEST")
    print(f"{'='*80}")
    print(f"Start time: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Maximum allowed duration: {max_duration.total_seconds()} seconds")
    print(f"{'='*80}\n")
    
    try:
        # Start the startup process
        print("Starting startup phase progression...")
        await phase_manager.start_phase_progression()
        await progressive_loader.start_progressive_loading()
        
        # Monitor progress until full functionality is reached or timeout
        check_interval = 5.0  # Check every 5 seconds
        checks_performed = 0
        full_functionality_reached = False
        full_functionality_time = None
        
        while True:
            current_time = datetime.now()
            elapsed = (current_time - start_time).total_seconds()
            
            # Check if we've exceeded 5 minutes
            if elapsed > max_duration.total_seconds():
                print(f"\n⏰ TIMEOUT: 5 minutes exceeded ({elapsed:.1f}s)")
                break
            
            # Get current status
            status = phase_manager.get_current_status()
            loading_progress = progressive_loader.get_loading_progress()
            model_statuses = model_manager.get_all_model_statuses()
            
            # Log progress
            checks_performed += 1
            
            # Print progress update
            print(f"\n[Check #{checks_performed}] Elapsed: {elapsed:.1f}s / {max_duration.total_seconds()}s")
            print(f"  Phase: {status.current_phase.value}")
            print(f"  Models: {loading_progress['overall']['loaded_models']}/{loading_progress['overall']['total_models']} loaded ({loading_progress['overall']['progress_percent']:.1f}%)")
            
            # Check if full functionality is reached
            if is_full_functionality_available(status, loading_progress, model_statuses):
                full_functionality_reached = True
                full_functionality_time = elapsed
                print(f"\n✅ FULL FUNCTIONALITY REACHED at {elapsed:.1f}s")
                break
            
            # Wait before next check
            await asyncio.sleep(check_interval)
        
        # Calculate final metrics
        final_elapsed = (datetime.now() - start_time).total_seconds()
        
        # Print detailed results
        print(f"\n{'='*80}")
        print(f"TEST RESULTS")
        print(f"{'='*80}")
        print(f"Total elapsed time: {final_elapsed:.2f}s ({final_elapsed/60:.2f} minutes)")
        print(f"Checks performed: {checks_performed}")
        print(f"Full functionality reached: {full_functionality_reached}")
        
        if full_functionality_reached:
            print(f"Time to full functionality: {full_functionality_time:.2f}s ({full_functionality_time/60:.2f} minutes)")
            print(f"Margin: {max_duration.total_seconds() - full_functionality_time:.2f}s under limit")
        
        # Print final status
        final_status = phase_manager.get_current_status()
        final_progress = progressive_loader.get_loading_progress()
        
        print(f"\nFinal Phase: {final_status.current_phase.value}")
        print(f"Final Model Loading: {final_progress['overall']['loaded_models']}/{final_progress['overall']['total_models']}")
        print(f"Final Progress: {final_progress['overall']['progress_percent']:.1f}%")
        
        # Print phase transition timeline
        print(f"\nPhase Transition Timeline:")
        for transition in final_status.phase_transitions:
            if transition.completed_at:
                duration = transition.duration_seconds
                print(f"  {transition.from_phase.value if transition.from_phase else 'START'} -> {transition.to_phase.value}: {duration:.2f}s")
        
        # Print model loading timeline
        print(f"\nModel Loading Timeline:")
        all_model_statuses = model_manager.get_all_model_statuses()
        for model_name, model_status in sorted(all_model_statuses.items(), 
                                               key=lambda x: x[1].get('actual_load_time', 999) or 999):
            if model_status['status'] == 'loaded':
                load_time = model_status.get('actual_load_time', 'N/A')
                priority = model_status.get('priority', 'unknown')
                print(f"  {model_name} ({priority}): {load_time:.2f}s" if isinstance(load_time, (int, float)) else f"  {model_name} ({priority}): {load_time}")
        
        # Print capability readiness
        print(f"\nCapability Readiness:")
        capability_readiness = progressive_loader.get_capability_readiness()
        for capability, status_info in sorted(capability_readiness.items()):
            available = "✅" if status_info.get("available") else "❌"
            print(f"  {available} {capability}")
        
        print(f"{'='*80}\n")
        
        # Validate results
        if not full_functionality_reached:
            print(f"❌ FAILED: Full functionality was not reached within 5 minutes (elapsed: {final_elapsed:.2f}s)")
            return False
        
        if full_functionality_time > max_duration.total_seconds():
            print(f"❌ FAILED: Full functionality took {full_functionality_time:.2f}s, exceeding 5-minute limit")
            return False
        
        if final_status.current_phase != StartupPhase.FULL:
            print(f"❌ FAILED: Expected FULL phase, got {final_status.current_phase.value}")
            return False
        
        if final_progress['overall']['progress_percent'] < 100.0:
            print(f"❌ FAILED: Expected 100% model loading, got {final_progress['overall']['progress_percent']:.1f}%")
            return False
        
        # Verify all capabilities are available
        all_capabilities_available = all(
            status_info.get("available", False) 
            for status_info in capability_readiness.values()
        )
        if not all_capabilities_available:
            print(f"❌ FAILED: Not all capabilities are available after reaching full functionality")
            return False
        
        print(f"✅ SUCCESS: Full functionality validated within 5 minutes!")
        print(f"   Actual time: {full_functionality_time:.2f}s ({full_functionality_time/60:.2f} minutes)")
        print(f"   Performance: {(full_functionality_time/max_duration.total_seconds())*100:.1f}% of allowed time")
        
        return True
        
    finally:
        # Cleanup
        try:
            await progressive_loader.shutdown()
        except:
            pass
        
        try:
            await model_manager.shutdown()
        except:
            pass


def is_full_functionality_available(status, loading_progress, model_statuses) -> bool:
    """Check if full functionality is available."""
    # Check 1: Must be in FULL phase
    if status.current_phase != StartupPhase.FULL:
        return False
    
    # Check 2: All models must be loaded
    if loading_progress['overall']['progress_percent'] < 100.0:
        return False
    
    # Check 3: All models must have LOADED status
    for model_name, model_status in model_statuses.items():
        if model_status['status'] != 'loaded':
            return False
    
    # Check 4: All capabilities must be available
    all_capabilities_ready = all(
        status.capabilities.get(cap, False)
        for cap in [
            "health_endpoints", "basic_api", "status_reporting", "request_queuing",
            "basic_chat", "simple_search", "text_processing",
            "advanced_ai", "document_analysis", "multimodal_processing",
            "complex_reasoning", "specialized_analysis"
        ]
    )
    
    if not all_capabilities_ready:
        return False
    
    return True


if __name__ == "__main__":
    print("\n" + "="*80)
    print("RUNNING FULL FUNCTIONALITY 5-MINUTE VALIDATION")
    print("="*80 + "\n")
    
    success = asyncio.run(test_full_functionality_within_5_minutes())
    
    if success:
        print("\n" + "="*80)
        print("✅ ALL VALIDATIONS PASSED")
        print("="*80 + "\n")
        sys.exit(0)
    else:
        print("\n" + "="*80)
        print("❌ VALIDATION FAILED")
        print("="*80 + "\n")
        sys.exit(1)
