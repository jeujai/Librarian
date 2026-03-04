"""
Test: Essential Models Loaded Within 2 Minutes

This test validates the critical success criterion that essential models
must be loaded within 2 minutes of application startup.

Success Criteria:
- All essential models (text-embedding-small, chat-model-base, search-index) loaded
- Total loading time <= 120 seconds
- No model loading failures
- Essential phase transition completes successfully
"""

import asyncio
import logging
import time
from datetime import datetime, timedelta
from typing import Dict, Any, List

import pytest

from src.multimodal_librarian.startup.phase_manager import (
    StartupPhaseManager,
    StartupPhase,
    ModelLoadingStatus
)
from src.multimodal_librarian.models.model_manager import (
    get_model_manager,
    ModelPriority,
    ModelStatus
)
from src.multimodal_librarian.startup.progressive_loader import (
    get_progressive_loader,
    initialize_progressive_loader
)

logger = logging.getLogger(__name__)


class EssentialModelsLoadingValidator:
    """Validator for essential models loading within 2 minutes."""
    
    def __init__(self):
        self.startup_phase_manager: StartupPhaseManager = None
        self.model_manager = None
        self.progressive_loader = None
        self.start_time: datetime = None
        self.essential_models = [
            "text-embedding-small",
            "chat-model-base",
            "search-index"
        ]
        self.validation_results = {
            "success": False,
            "total_time_seconds": 0.0,
            "models_loaded": [],
            "models_failed": [],
            "phase_transition_time": 0.0,
            "individual_load_times": {},
            "errors": []
        }
    
    async def setup(self):
        """Set up test environment."""
        logger.info("Setting up essential models loading test")
        
        # Initialize startup phase manager
        self.startup_phase_manager = StartupPhaseManager()
        
        # Initialize model manager
        self.model_manager = get_model_manager()
        
        # Initialize progressive loader with phase manager
        self.progressive_loader = await initialize_progressive_loader(
            self.startup_phase_manager
        )
        
        logger.info("Test environment setup complete")
    
    async def run_validation(self) -> Dict[str, Any]:
        """Run the validation test."""
        logger.info("=" * 80)
        logger.info("VALIDATION: Essential Models Loaded Within 2 Minutes")
        logger.info("=" * 80)
        
        self.start_time = datetime.now()
        
        try:
            # Start the startup phase progression
            await self.startup_phase_manager.start_phase_progression()
            
            # Monitor essential models loading
            await self._monitor_essential_models_loading()
            
            # Calculate total time
            end_time = datetime.now()
            total_time = (end_time - self.start_time).total_seconds()
            self.validation_results["total_time_seconds"] = total_time
            
            # Validate results
            await self._validate_results()
            
            # Log results
            self._log_results()
            
            return self.validation_results
            
        except Exception as e:
            logger.error(f"Validation failed with error: {e}")
            self.validation_results["errors"].append(str(e))
            self.validation_results["success"] = False
            return self.validation_results
    
    async def _monitor_essential_models_loading(self):
        """Monitor the loading of essential models."""
        logger.info("Monitoring essential models loading...")
        
        max_wait_time = 150.0  # 2.5 minutes max (with buffer)
        check_interval = 2.0  # Check every 2 seconds
        elapsed = 0.0
        
        all_loaded = False
        
        while elapsed < max_wait_time and not all_loaded:
            await asyncio.sleep(check_interval)
            elapsed += check_interval
            
            # Check status of each essential model
            all_loaded = True
            for model_name in self.essential_models:
                status = self.model_manager.get_model_status(model_name)
                
                if status:
                    if status["status"] == "loaded":
                        if model_name not in self.validation_results["models_loaded"]:
                            load_time = status.get("actual_load_time", 0.0)
                            self.validation_results["models_loaded"].append(model_name)
                            self.validation_results["individual_load_times"][model_name] = load_time
                            logger.info(f"✓ {model_name} loaded in {load_time:.2f}s")
                    elif status["status"] == "failed":
                        if model_name not in self.validation_results["models_failed"]:
                            self.validation_results["models_failed"].append(model_name)
                            error_msg = status.get("error_message", "Unknown error")
                            logger.error(f"✗ {model_name} failed to load: {error_msg}")
                        all_loaded = False
                    elif status["status"] in ["pending", "loading"]:
                        all_loaded = False
                else:
                    all_loaded = False
            
            # Check if we've transitioned to essential phase
            if self.startup_phase_manager.current_phase == StartupPhase.ESSENTIAL:
                if self.validation_results["phase_transition_time"] == 0.0:
                    self.validation_results["phase_transition_time"] = elapsed
                    logger.info(f"✓ Transitioned to ESSENTIAL phase at {elapsed:.2f}s")
            
            # Log progress
            if int(elapsed) % 10 == 0:  # Every 10 seconds
                loaded_count = len(self.validation_results["models_loaded"])
                total_count = len(self.essential_models)
                logger.info(f"Progress: {loaded_count}/{total_count} essential models loaded ({elapsed:.0f}s elapsed)")
        
        if not all_loaded:
            logger.warning(f"Not all essential models loaded after {elapsed:.2f}s")
    
    async def _validate_results(self):
        """Validate the test results against success criteria."""
        logger.info("\nValidating results against success criteria...")
        
        success = True
        
        # Criterion 1: All essential models loaded
        if len(self.validation_results["models_loaded"]) != len(self.essential_models):
            success = False
            missing = set(self.essential_models) - set(self.validation_results["models_loaded"])
            error_msg = f"Not all essential models loaded. Missing: {missing}"
            self.validation_results["errors"].append(error_msg)
            logger.error(f"✗ {error_msg}")
        else:
            logger.info(f"✓ All {len(self.essential_models)} essential models loaded")
        
        # Criterion 2: Total loading time <= 120 seconds
        if self.validation_results["total_time_seconds"] > 120.0:
            success = False
            error_msg = f"Loading time {self.validation_results['total_time_seconds']:.2f}s exceeds 120s limit"
            self.validation_results["errors"].append(error_msg)
            logger.error(f"✗ {error_msg}")
        else:
            logger.info(f"✓ Loading time {self.validation_results['total_time_seconds']:.2f}s within 120s limit")
        
        # Criterion 3: No model loading failures
        if len(self.validation_results["models_failed"]) > 0:
            success = False
            error_msg = f"Model loading failures: {self.validation_results['models_failed']}"
            self.validation_results["errors"].append(error_msg)
            logger.error(f"✗ {error_msg}")
        else:
            logger.info("✓ No model loading failures")
        
        # Criterion 4: Essential phase transition completed
        if self.startup_phase_manager.current_phase != StartupPhase.ESSENTIAL:
            # Check if we at least reached essential phase
            reached_essential = any(
                t.to_phase == StartupPhase.ESSENTIAL and t.success
                for t in self.startup_phase_manager.status.phase_transitions
            )
            
            if not reached_essential:
                success = False
                error_msg = "Essential phase transition did not complete successfully"
                self.validation_results["errors"].append(error_msg)
                logger.error(f"✗ {error_msg}")
        else:
            logger.info("✓ Essential phase transition completed")
        
        self.validation_results["success"] = success
    
    def _log_results(self):
        """Log detailed test results."""
        logger.info("\n" + "=" * 80)
        logger.info("VALIDATION RESULTS")
        logger.info("=" * 80)
        
        logger.info(f"\nOverall Success: {'✓ PASS' if self.validation_results['success'] else '✗ FAIL'}")
        logger.info(f"Total Time: {self.validation_results['total_time_seconds']:.2f}s / 120.0s")
        logger.info(f"Models Loaded: {len(self.validation_results['models_loaded'])}/{len(self.essential_models)}")
        
        if self.validation_results["individual_load_times"]:
            logger.info("\nIndividual Model Load Times:")
            for model_name, load_time in self.validation_results["individual_load_times"].items():
                logger.info(f"  - {model_name}: {load_time:.2f}s")
        
        if self.validation_results["phase_transition_time"] > 0:
            logger.info(f"\nPhase Transition Time: {self.validation_results['phase_transition_time']:.2f}s")
        
        if self.validation_results["models_failed"]:
            logger.info(f"\nFailed Models: {self.validation_results['models_failed']}")
        
        if self.validation_results["errors"]:
            logger.info("\nErrors:")
            for error in self.validation_results["errors"]:
                logger.info(f"  - {error}")
        
        logger.info("=" * 80)
    
    async def cleanup(self):
        """Clean up test resources."""
        logger.info("Cleaning up test resources...")
        
        try:
            if self.progressive_loader:
                await self.progressive_loader.shutdown()
            
            if self.model_manager:
                await self.model_manager.shutdown()
            
            if self.startup_phase_manager:
                await self.startup_phase_manager.shutdown()
        
        except Exception as e:
            logger.warning(f"Error during cleanup: {e}")
        
        logger.info("Cleanup complete")


@pytest.mark.asyncio
async def test_essential_models_load_within_2_minutes():
    """
    Test that essential models load within 2 minutes.
    
    This is a critical success criterion for the application health
    and startup optimization feature.
    """
    validator = EssentialModelsLoadingValidator()
    
    try:
        # Setup
        await validator.setup()
        
        # Run validation
        results = await validator.run_validation()
        
        # Assert success
        assert results["success"], f"Essential models loading validation failed: {results['errors']}"
        assert results["total_time_seconds"] <= 120.0, f"Loading time {results['total_time_seconds']:.2f}s exceeds 120s"
        assert len(results["models_loaded"]) == 3, f"Expected 3 models loaded, got {len(results['models_loaded'])}"
        assert len(results["models_failed"]) == 0, f"Model loading failures: {results['models_failed']}"
        
    finally:
        # Cleanup
        await validator.cleanup()


@pytest.mark.asyncio
async def test_individual_essential_model_load_times():
    """
    Test that each individual essential model loads within reasonable time.
    
    Expected load times:
    - text-embedding-small: <= 10s
    - chat-model-base: <= 30s
    - search-index: <= 20s
    """
    validator = EssentialModelsLoadingValidator()
    
    try:
        await validator.setup()
        results = await validator.run_validation()
        
        # Check individual load times
        expected_times = {
            "text-embedding-small": 10.0,
            "chat-model-base": 30.0,
            "search-index": 20.0
        }
        
        for model_name, max_time in expected_times.items():
            actual_time = results["individual_load_times"].get(model_name, float('inf'))
            assert actual_time <= max_time, f"{model_name} took {actual_time:.2f}s, expected <= {max_time}s"
            logger.info(f"✓ {model_name} loaded in {actual_time:.2f}s (limit: {max_time}s)")
    
    finally:
        await validator.cleanup()


@pytest.mark.asyncio
async def test_essential_phase_transition_timing():
    """
    Test that transition to essential phase happens within expected timeframe.
    
    The essential phase should be reached within 60 seconds of startup,
    even if models are still loading.
    """
    validator = EssentialModelsLoadingValidator()
    
    try:
        await validator.setup()
        results = await validator.run_validation()
        
        # Check phase transition timing
        transition_time = results.get("phase_transition_time", float('inf'))
        assert transition_time <= 60.0, f"Essential phase transition took {transition_time:.2f}s, expected <= 60s"
        logger.info(f"✓ Essential phase transition completed in {transition_time:.2f}s")
    
    finally:
        await validator.cleanup()


async def main():
    """Run the validation as a standalone script."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    validator = EssentialModelsLoadingValidator()
    
    try:
        await validator.setup()
        results = await validator.run_validation()
        
        # Exit with appropriate code
        exit_code = 0 if results["success"] else 1
        return exit_code
    
    finally:
        await validator.cleanup()


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)
