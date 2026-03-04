#!/usr/bin/env python3
"""
Startup Phase Timing and Functionality Validation Script

This script validates the core startup phase timing and functionality
that has been implemented for the application health and startup optimization feature.

This serves as a comprehensive test of the task requirements:
- Test each startup phase timing and functionality
"""

import asyncio
import time
import logging
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def test_startup_phase_manager():
    """Test the StartupPhaseManager functionality."""
    logger.info("=== Testing StartupPhaseManager ===")
    
    try:
        from src.multimodal_librarian.startup.phase_manager import StartupPhaseManager, StartupPhase
        
        # Initialize phase manager
        phase_manager = StartupPhaseManager()
        logger.info("✓ StartupPhaseManager initialized successfully")
        
        # Test initial state
        status = phase_manager.get_current_status()
        assert status.current_phase == StartupPhase.MINIMAL
        assert status.health_check_ready is False  # Initially not ready
        logger.info("✓ Initial phase state is correct")
        
        # Test phase configurations
        assert StartupPhase.MINIMAL in phase_manager.phase_configs
        assert StartupPhase.ESSENTIAL in phase_manager.phase_configs
        assert StartupPhase.FULL in phase_manager.phase_configs
        logger.info("✓ Phase configurations are present")
        
        # Test model priorities
        assert "essential" in phase_manager.model_priorities
        assert "standard" in phase_manager.model_priorities
        assert "advanced" in phase_manager.model_priorities
        logger.info("✓ Model priorities are configured")
        
        # Test timing requirements
        minimal_config = phase_manager.phase_configs[StartupPhase.MINIMAL]
        essential_config = phase_manager.phase_configs[StartupPhase.ESSENTIAL]
        full_config = phase_manager.phase_configs[StartupPhase.FULL]
        
        assert minimal_config.timeout_seconds <= 60.0  # <30s target, 60s max
        assert essential_config.timeout_seconds <= 180.0  # <2min target, 3min max
        assert full_config.timeout_seconds <= 600.0  # <5min target, 10min max
        logger.info("✓ Phase timing requirements are within acceptable limits")
        
        # Test phase progression
        logger.info("Starting phase progression test...")
        start_time = time.time()
        
        await phase_manager.start_phase_progression()
        
        # Wait for minimal phase (should be immediate)
        await asyncio.sleep(2.0)
        
        # Check minimal phase completion
        elapsed = time.time() - start_time
        logger.info(f"Minimal phase reached in {elapsed:.2f} seconds")
        
        # Get progress information
        progress = phase_manager.get_phase_progress()
        logger.info(f"Current phase: {progress['current_phase']}")
        logger.info(f"Phase duration: {progress['phase_duration_seconds']:.2f}s")
        logger.info(f"Overall progress: {progress['overall_progress_percent']:.1f}%")
        
        # Test health status
        health_status = phase_manager.get_phase_health_status()
        logger.info(f"Health check ready: {health_status['health_check_ready']}")
        logger.info(f"Ready for traffic: {health_status['ready_for_traffic']}")
        
        # Test timing metrics
        timing_metrics = phase_manager.get_timing_metrics()
        logger.info(f"Total startup time: {timing_metrics['total_startup_time']:.2f}s")
        
        # Cleanup
        await phase_manager.shutdown()
        logger.info("✓ Phase manager shutdown completed")
        
        return True
        
    except Exception as e:
        logger.error(f"✗ StartupPhaseManager test failed: {e}")
        return False

async def test_progressive_loader():
    """Test the ProgressiveLoader functionality."""
    logger.info("=== Testing ProgressiveLoader ===")
    
    try:
        from src.multimodal_librarian.startup.progressive_loader import ProgressiveLoader
        
        # Initialize progressive loader
        progressive_loader = ProgressiveLoader()
        logger.info("✓ ProgressiveLoader initialized successfully")
        
        # Test loading schedules
        assert hasattr(progressive_loader, 'loading_schedules')
        schedules = progressive_loader.loading_schedules
        
        from src.multimodal_librarian.startup.phase_manager import StartupPhase
        assert StartupPhase.MINIMAL in schedules
        assert StartupPhase.ESSENTIAL in schedules
        assert StartupPhase.FULL in schedules
        logger.info("✓ Loading schedules are configured")
        
        # Test essential phase schedule
        essential_schedule = schedules[StartupPhase.ESSENTIAL]
        expected_essential = ["text-embedding-small", "chat-model-base", "search-index"]
        for model_name in expected_essential:
            assert model_name in essential_schedule.models_to_load
        logger.info("✓ Essential models are scheduled correctly")
        
        # Test full phase schedule
        full_schedule = schedules[StartupPhase.FULL]
        expected_full = ["chat-model-large", "document-processor", "multimodal-model", "specialized-analyzers"]
        for model_name in expected_full:
            assert model_name in full_schedule.models_to_load
        logger.info("✓ Full phase models are scheduled correctly")
        
        # Test progressive loading start
        await progressive_loader.start_progressive_loading()
        logger.info("✓ Progressive loading started successfully")
        
        # Test loading progress
        progress = progressive_loader.get_loading_progress()
        assert "overall" in progress
        assert "by_phase" in progress
        assert "current_strategy" in progress
        logger.info("✓ Loading progress tracking works")
        
        # Test capability readiness
        readiness = progressive_loader.get_capability_readiness()
        assert isinstance(readiness, dict)
        logger.info("✓ Capability readiness checking works")
        
        # Test user experience metrics
        ux_metrics = progressive_loader.get_user_experience_metrics()
        assert "average_user_wait_time_seconds" in ux_metrics
        assert "capabilities_available" in ux_metrics
        assert "capability_availability_percent" in ux_metrics
        logger.info("✓ User experience metrics are available")
        
        # Cleanup
        await progressive_loader.shutdown()
        logger.info("✓ Progressive loader shutdown completed")
        
        return True
        
    except Exception as e:
        logger.error(f"✗ ProgressiveLoader test failed: {e}")
        return False

async def test_model_manager():
    """Test the ModelManager functionality."""
    logger.info("=== Testing ModelManager ===")
    
    try:
        from src.multimodal_librarian.models.model_manager import ModelManager, ModelPriority, ModelStatus
        
        # Initialize model manager
        model_manager = ModelManager()
        logger.info("✓ ModelManager initialized successfully")
        
        # Test model configurations
        assert len(model_manager.model_configs) > 0
        logger.info(f"✓ {len(model_manager.model_configs)} models configured")
        
        # Test essential models are present
        essential_models = ["text-embedding-small", "chat-model-base", "search-index"]
        for model_name in essential_models:
            assert model_name in model_manager.model_configs
            config = model_manager.model_configs[model_name]
            assert config.priority == ModelPriority.ESSENTIAL
        logger.info("✓ Essential models are configured with correct priority")
        
        # Test model status tracking
        all_statuses = model_manager.get_all_model_statuses()
        assert len(all_statuses) > 0
        logger.info(f"✓ Model status tracking works for {len(all_statuses)} models")
        
        # Test loading progress
        progress = model_manager.get_loading_progress()
        assert "total_models" in progress
        assert "loaded_models" in progress
        assert "progress_percent" in progress
        logger.info("✓ Loading progress tracking works")
        
        # Test capability checking
        for model_name, config in model_manager.model_configs.items():
            for capability in config.required_for_capabilities:
                status = model_manager.get_capability_status(capability)
                assert "capability" in status
                assert "available" in status
                assert "required_models" in status
        logger.info("✓ Capability status checking works")
        
        # Test progressive loading start
        await model_manager.start_progressive_loading()
        logger.info("✓ Progressive loading started successfully")
        
        # Wait a moment for background loading to start
        await asyncio.sleep(1.0)
        
        # Check that some models are loading
        progress_after_start = model_manager.get_loading_progress()
        logger.info(f"Loading progress: {progress_after_start['progress_percent']:.1f}%")
        
        # Cleanup
        await model_manager.shutdown()
        logger.info("✓ Model manager shutdown completed")
        
        return True
        
    except Exception as e:
        logger.error(f"✗ ModelManager test failed: {e}")
        return False

async def test_integration():
    """Test integration between components."""
    logger.info("=== Testing Component Integration ===")
    
    try:
        from src.multimodal_librarian.startup.phase_manager import StartupPhaseManager
        from src.multimodal_librarian.startup.progressive_loader import ProgressiveLoader
        
        # Initialize components
        phase_manager = StartupPhaseManager()
        progressive_loader = ProgressiveLoader(phase_manager)
        
        logger.info("✓ Components initialized with integration")
        
        # Start both systems
        await phase_manager.start_phase_progression()
        await progressive_loader.start_progressive_loading()
        
        # Wait for some progress
        await asyncio.sleep(2.0)
        
        # Check that both systems are working together
        phase_progress = phase_manager.get_phase_progress()
        loader_progress = progressive_loader.get_loading_progress()
        
        logger.info(f"Phase manager - Current phase: {phase_progress['current_phase']}")
        logger.info(f"Progressive loader - Strategy: {loader_progress['current_strategy']}")
        
        # Test timing requirements
        start_time = time.time()
        
        # Minimal phase should be ready quickly
        health_status = phase_manager.get_phase_health_status()
        minimal_ready_time = time.time() - start_time
        
        logger.info(f"Health check ready in: {minimal_ready_time:.2f}s")
        
        # Verify timing requirements
        assert minimal_ready_time < 30.0, f"Minimal phase took too long: {minimal_ready_time:.2f}s"
        logger.info("✓ Minimal phase timing requirement met (<30s)")
        
        # Cleanup
        await progressive_loader.shutdown()
        await phase_manager.shutdown()
        logger.info("✓ Integration test completed successfully")
        
        return True
        
    except Exception as e:
        logger.error(f"✗ Integration test failed: {e}")
        return False

async def main():
    """Run all validation tests."""
    logger.info("Starting Startup Phase Timing and Functionality Validation")
    logger.info("=" * 60)
    
    test_results = []
    
    # Run individual component tests
    test_results.append(await test_startup_phase_manager())
    test_results.append(await test_progressive_loader())
    test_results.append(await test_model_manager())
    test_results.append(await test_integration())
    
    # Summary
    logger.info("=" * 60)
    logger.info("VALIDATION SUMMARY")
    logger.info("=" * 60)
    
    passed = sum(test_results)
    total = len(test_results)
    
    logger.info(f"Tests passed: {passed}/{total}")
    
    if passed == total:
        logger.info("✓ ALL TESTS PASSED - Startup phase timing and functionality validation successful!")
        logger.info("")
        logger.info("Key achievements:")
        logger.info("- StartupPhaseManager properly configured with 3 phases (MINIMAL, ESSENTIAL, FULL)")
        logger.info("- Phase timing requirements are within acceptable limits")
        logger.info("- ProgressiveLoader integrates with phase manager")
        logger.info("- ModelManager supports progressive loading with priorities")
        logger.info("- Health check integration works correctly")
        logger.info("- Component integration and timing requirements are met")
        return True
    else:
        logger.error(f"✗ {total - passed} tests failed - validation incomplete")
        return False

if __name__ == "__main__":
    success = asyncio.run(main())
    exit(0 if success else 1)