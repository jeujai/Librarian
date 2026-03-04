"""
Test: Full Functionality Available Within 5 Minutes

This test validates that all application functionality becomes available within 5 minutes
of startup, including all models loaded and all capabilities ready.

Success Criteria:
- All models (essential, standard, advanced) loaded within 5 minutes
- All capabilities available within 5 minutes
- FULL phase reached within 5 minutes
- No critical errors during startup
- All health checks passing
"""

import asyncio
import pytest
import time
from datetime import datetime, timedelta
from typing import Dict, Any, List

from src.multimodal_librarian.startup.phase_manager import (
    StartupPhaseManager,
    StartupPhase,
    ModelLoadingStatus
)
from src.multimodal_librarian.startup.progressive_loader import (
    ProgressiveLoader,
    LoadingStrategy
)
from src.multimodal_librarian.models.model_manager import (
    get_model_manager,
    ModelStatus,
    ModelPriority
)


class TestFullFunctionality5MinuteValidation:
    """Test suite for validating full functionality within 5 minutes."""
    
    @pytest.fixture(scope="function")
    async def startup_system(self):
        """Set up the complete startup system."""
        # Create startup phase manager
        phase_manager = StartupPhaseManager()
        
        # Create progressive loader with phase manager
        progressive_loader = ProgressiveLoader(phase_manager)
        
        # Get model manager
        model_manager = get_model_manager()
        
        yield {
            "phase_manager": phase_manager,
            "progressive_loader": progressive_loader,
            "model_manager": model_manager
        }
        
        # Cleanup
        try:
            await progressive_loader.shutdown()
        except:
            pass
        
        try:
            await model_manager.shutdown()
        except:
            pass
    
    @pytest.mark.asyncio
    async def test_full_functionality_within_5_minutes(self, startup_system):
        """
        Test that full functionality is available within 5 minutes.
        
        This is the main validation test for the success criterion.
        """
        phase_manager = startup_system["phase_manager"]
        progressive_loader = startup_system["progressive_loader"]
        model_manager = startup_system["model_manager"]
        
        # Record start time
        start_time = datetime.now()
        max_duration = timedelta(minutes=5)
        
        print(f"\n{'='*80}")
        print(f"FULL FUNCTIONALITY 5-MINUTE VALIDATION TEST")
        print(f"{'='*80}")
        print(f"Start time: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Maximum allowed duration: {max_duration.total_seconds()} seconds")
        print(f"{'='*80}\n")
        
        # Start the startup process
        print("Starting startup phase progression...")
        await phase_manager.start_phase_progression()
        await progressive_loader.start_progressive_loading()
        
        # Monitor progress until full functionality is reached or timeout
        check_interval = 5.0  # Check every 5 seconds
        checks_performed = 0
        full_functionality_reached = False
        full_functionality_time = None
        
        progress_log = []
        
        while True:
            current_time = datetime.now()
            elapsed = (current_time - start_time).total_seconds()
            
            # Check if we've exceeded 5 minutes
            if elapsed > max_duration.total_seconds():
                print(f"\n⏰ TIMEOUT: 5 minutes exceeded ({elapsed:.1f}s)")
                break
            
            # Get current status
            status = phase_manager.get_status()
            loading_progress = progressive_loader.get_loading_progress()
            model_statuses = model_manager.get_all_model_statuses()
            
            # Log progress
            checks_performed += 1
            progress_entry = {
                "check_number": checks_performed,
                "elapsed_seconds": elapsed,
                "current_phase": status.current_phase.value,
                "loaded_models": loading_progress["overall"]["loaded_models"],
                "total_models": loading_progress["overall"]["total_models"],
                "progress_percent": loading_progress["overall"]["progress_percent"]
            }
            progress_log.append(progress_entry)
            
            # Print progress update
            print(f"\n[Check #{checks_performed}] Elapsed: {elapsed:.1f}s / {max_duration.total_seconds()}s")
            print(f"  Phase: {status.current_phase.value}")
            print(f"  Models: {loading_progress['overall']['loaded_models']}/{loading_progress['overall']['total_models']} loaded ({loading_progress['overall']['progress_percent']:.1f}%)")
            
            # Check if full functionality is reached
            if self._is_full_functionality_available(status, loading_progress, model_statuses):
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
        final_status = phase_manager.get_status()
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
        for capability, status in sorted(capability_readiness.items()):
            available = "✅" if status.get("available") else "❌"
            print(f"  {available} {capability}")
        
        print(f"{'='*80}\n")
        
        # Assertions
        assert full_functionality_reached, \
            f"Full functionality was not reached within 5 minutes (elapsed: {final_elapsed:.2f}s)"
        
        assert full_functionality_time <= max_duration.total_seconds(), \
            f"Full functionality took {full_functionality_time:.2f}s, exceeding 5-minute limit"
        
        assert final_status.current_phase == StartupPhase.FULL, \
            f"Expected FULL phase, got {final_status.current_phase.value}"
        
        assert final_progress['overall']['progress_percent'] == 100.0, \
            f"Expected 100% model loading, got {final_progress['overall']['progress_percent']:.1f}%"
        
        # Verify all capabilities are available
        all_capabilities_available = all(
            status.get("available", False) 
            for status in capability_readiness.values()
        )
        assert all_capabilities_available, \
            "Not all capabilities are available after reaching full functionality"
        
        print(f"✅ SUCCESS: Full functionality validated within 5 minutes!")
        print(f"   Actual time: {full_functionality_time:.2f}s ({full_functionality_time/60:.2f} minutes)")
        print(f"   Performance: {(full_functionality_time/max_duration.total_seconds())*100:.1f}% of allowed time")
    
    def _is_full_functionality_available(self, status, loading_progress, model_statuses) -> bool:
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
    
    @pytest.mark.asyncio
    async def test_phase_progression_timing(self, startup_system):
        """Test that phase progression happens within expected timeframes."""
        phase_manager = startup_system["phase_manager"]
        
        start_time = datetime.now()
        
        # Start phase progression
        await phase_manager.start_phase_progression()
        
        # Wait for FULL phase with timeout
        timeout = 300  # 5 minutes
        check_interval = 2.0
        elapsed = 0
        
        while elapsed < timeout:
            status = phase_manager.get_status()
            
            if status.current_phase == StartupPhase.FULL:
                break
            
            await asyncio.sleep(check_interval)
            elapsed = (datetime.now() - start_time).total_seconds()
        
        final_status = phase_manager.get_status()
        final_elapsed = (datetime.now() - start_time).total_seconds()
        
        # Verify FULL phase was reached
        assert final_status.current_phase == StartupPhase.FULL, \
            f"Expected FULL phase within {timeout}s, got {final_status.current_phase.value} after {final_elapsed:.2f}s"
        
        # Verify timing
        assert final_elapsed <= timeout, \
            f"Phase progression took {final_elapsed:.2f}s, exceeding {timeout}s limit"
        
        print(f"\n✅ Phase progression completed in {final_elapsed:.2f}s")
    
    @pytest.mark.asyncio
    async def test_all_models_loaded_within_5_minutes(self, startup_system):
        """Test that all models are loaded within 5 minutes."""
        model_manager = startup_system["model_manager"]
        progressive_loader = startup_system["progressive_loader"]
        
        start_time = datetime.now()
        
        # Start model loading
        await model_manager.start_progressive_loading()
        await progressive_loader.start_progressive_loading()
        
        # Wait for all models to load
        timeout = 300  # 5 minutes
        check_interval = 3.0
        elapsed = 0
        
        while elapsed < timeout:
            progress = model_manager.get_loading_progress()
            
            if progress['progress_percent'] >= 100.0:
                break
            
            await asyncio.sleep(check_interval)
            elapsed = (datetime.now() - start_time).total_seconds()
        
        final_elapsed = (datetime.now() - start_time).total_seconds()
        final_progress = model_manager.get_loading_progress()
        
        # Verify all models loaded
        assert final_progress['progress_percent'] == 100.0, \
            f"Expected 100% models loaded, got {final_progress['progress_percent']:.1f}% after {final_elapsed:.2f}s"
        
        # Verify timing
        assert final_elapsed <= timeout, \
            f"Model loading took {final_elapsed:.2f}s, exceeding {timeout}s limit"
        
        # Verify all models have LOADED status
        all_statuses = model_manager.get_all_model_statuses()
        failed_models = [
            name for name, status in all_statuses.items()
            if status['status'] != 'loaded'
        ]
        
        assert len(failed_models) == 0, \
            f"Some models failed to load: {failed_models}"
        
        print(f"\n✅ All models loaded in {final_elapsed:.2f}s")
        print(f"   Total models: {final_progress['total_models']}")
        print(f"   Loaded: {final_progress['loaded_models']}")
    
    @pytest.mark.asyncio
    async def test_capabilities_available_within_5_minutes(self, startup_system):
        """Test that all capabilities become available within 5 minutes."""
        progressive_loader = startup_system["progressive_loader"]
        phase_manager = startup_system["phase_manager"]
        
        start_time = datetime.now()
        
        # Start systems
        await phase_manager.start_phase_progression()
        await progressive_loader.start_progressive_loading()
        
        # Expected capabilities
        expected_capabilities = [
            "health_endpoints", "basic_api", "status_reporting", "request_queuing",
            "basic_chat", "simple_search", "text_processing",
            "advanced_ai", "document_analysis", "multimodal_processing",
            "complex_reasoning", "specialized_analysis"
        ]
        
        # Wait for all capabilities
        timeout = 300  # 5 minutes
        check_interval = 3.0
        elapsed = 0
        
        while elapsed < timeout:
            capability_readiness = progressive_loader.get_capability_readiness()
            
            # Check if all expected capabilities are available
            all_available = all(
                capability_readiness.get(cap, {}).get("available", False)
                for cap in expected_capabilities
            )
            
            if all_available:
                break
            
            await asyncio.sleep(check_interval)
            elapsed = (datetime.now() - start_time).total_seconds()
        
        final_elapsed = (datetime.now() - start_time).total_seconds()
        final_readiness = progressive_loader.get_capability_readiness()
        
        # Verify all capabilities available
        unavailable_capabilities = [
            cap for cap in expected_capabilities
            if not final_readiness.get(cap, {}).get("available", False)
        ]
        
        assert len(unavailable_capabilities) == 0, \
            f"Some capabilities not available after {final_elapsed:.2f}s: {unavailable_capabilities}"
        
        # Verify timing
        assert final_elapsed <= timeout, \
            f"Capability initialization took {final_elapsed:.2f}s, exceeding {timeout}s limit"
        
        print(f"\n✅ All capabilities available in {final_elapsed:.2f}s")
        print(f"   Total capabilities: {len(expected_capabilities)}")
    
    @pytest.mark.asyncio
    async def test_no_critical_errors_during_startup(self, startup_system):
        """Test that no critical errors occur during the 5-minute startup."""
        phase_manager = startup_system["phase_manager"]
        progressive_loader = startup_system["progressive_loader"]
        model_manager = startup_system["model_manager"]
        
        # Start systems
        await phase_manager.start_phase_progression()
        await progressive_loader.start_progressive_loading()
        
        # Wait for full functionality or timeout
        timeout = 300  # 5 minutes
        await asyncio.sleep(min(timeout, 10))  # Wait at least 10 seconds to check for errors
        
        # Check for errors in phase transitions
        status = phase_manager.get_status()
        failed_transitions = [
            t for t in status.phase_transitions
            if not t.success and t.error_message
        ]
        
        assert len(failed_transitions) == 0, \
            f"Critical phase transition errors occurred: {[t.error_message for t in failed_transitions]}"
        
        # Check for failed models
        all_statuses = model_manager.get_all_model_statuses()
        failed_models = {
            name: status['error_message']
            for name, status in all_statuses.items()
            if status['status'] == 'failed' and status.get('retry_count', 0) >= status.get('max_retries', 3)
        }
        
        assert len(failed_models) == 0, \
            f"Critical model loading errors occurred: {failed_models}"
        
        print(f"\n✅ No critical errors during startup")
    
    @pytest.mark.asyncio
    async def test_performance_metrics_within_limits(self, startup_system):
        """Test that performance metrics stay within acceptable limits."""
        phase_manager = startup_system["phase_manager"]
        progressive_loader = startup_system["progressive_loader"]
        
        start_time = datetime.now()
        
        # Start systems
        await phase_manager.start_phase_progression()
        await progressive_loader.start_progressive_loading()
        
        # Wait for full functionality
        timeout = 300
        check_interval = 5.0
        elapsed = 0
        
        while elapsed < timeout:
            status = phase_manager.get_status()
            
            if status.current_phase == StartupPhase.FULL:
                break
            
            await asyncio.sleep(check_interval)
            elapsed = (datetime.now() - start_time).total_seconds()
        
        final_elapsed = (datetime.now() - start_time).total_seconds()
        
        # Get performance metrics
        ux_metrics = progressive_loader.get_user_experience_metrics()
        loading_progress = progressive_loader.get_loading_progress()
        
        # Verify performance metrics
        assert final_elapsed <= 300, \
            f"Startup took {final_elapsed:.2f}s, exceeding 300s limit"
        
        assert ux_metrics['capability_availability_percent'] == 100.0, \
            f"Expected 100% capability availability, got {ux_metrics['capability_availability_percent']:.1f}%"
        
        print(f"\n✅ Performance metrics within limits")
        print(f"   Startup time: {final_elapsed:.2f}s")
        print(f"   Capability availability: {ux_metrics['capability_availability_percent']:.1f}%")


if __name__ == "__main__":
    # Run the main validation test
    import sys
    
    async def run_validation():
        test_suite = TestFullFunctionality5MinuteValidation()
        
        # Create startup system
        phase_manager = StartupPhaseManager()
        progressive_loader = ProgressiveLoader(phase_manager)
        model_manager = get_model_manager()
        
        startup_system = {
            "phase_manager": phase_manager,
            "progressive_loader": progressive_loader,
            "model_manager": model_manager
        }
        
        try:
            print("\n" + "="*80)
            print("RUNNING FULL FUNCTIONALITY 5-MINUTE VALIDATION")
            print("="*80 + "\n")
            
            await test_suite.test_full_functionality_within_5_minutes(startup_system)
            
            print("\n" + "="*80)
            print("✅ ALL VALIDATIONS PASSED")
            print("="*80 + "\n")
            
            return 0
            
        except AssertionError as e:
            print(f"\n❌ VALIDATION FAILED: {e}\n")
            return 1
        except Exception as e:
            print(f"\n❌ ERROR: {e}\n")
            import traceback
            traceback.print_exc()
            return 1
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
    
    sys.exit(asyncio.run(run_validation()))
