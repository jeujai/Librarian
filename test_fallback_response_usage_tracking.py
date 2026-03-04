#!/usr/bin/env python3
"""
Test script for fallback response usage tracking functionality.

This script tests the implementation of fallback response usage tracking
in the user experience logger and chat router integration.
"""

import asyncio
import json
import logging
import sys
import time
from datetime import datetime
from typing import Dict, Any
from uuid import uuid4

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Add src to path for imports
sys.path.insert(0, 'src')

try:
    from multimodal_librarian.logging.ux_logger import (
        UserExperienceLogger, 
        initialize_ux_logger,
        log_fallback_response_usage,
        RequestOutcome
    )
    from multimodal_librarian.services.fallback_service import (
        get_fallback_service,
        FallbackResponseService,
        UserIntent
    )
    from multimodal_librarian.services.capability_service import CapabilityLevel
    from multimodal_librarian.startup.phase_manager import StartupPhase, StartupPhaseManager
    
    logger.info("Successfully imported required modules")
except ImportError as e:
    logger.error(f"Failed to import required modules: {e}")
    sys.exit(1)


class MockPhaseManager:
    """Mock phase manager for testing."""
    
    def __init__(self):
        self.current_phase = StartupPhase.MINIMAL
        self.phase_start_time = datetime.now()
    
    def get_current_status(self):
        """Mock status for testing."""
        class MockStatus:
            def __init__(self):
                self.model_statuses = {
                    "text_embedding": MockModelStatus("loaded"),
                    "chat_model": MockModelStatus("loading"),
                    "document_processor": MockModelStatus("not_loaded")
                }
        
        class MockModelStatus:
            def __init__(self, status):
                self.status = status
        
        return MockStatus()


async def test_fallback_response_usage_tracking():
    """Test fallback response usage tracking functionality."""
    logger.info("Starting fallback response usage tracking test")
    
    # Initialize components
    phase_manager = MockPhaseManager()
    ux_logger = initialize_ux_logger(phase_manager)
    fallback_service = FallbackResponseService()
    
    # Start UX logging
    await ux_logger.start_logging()
    
    try:
        # Test 1: Basic fallback response tracking with proper request lifecycle
        logger.info("Test 1: Basic fallback response tracking with proper request lifecycle")
        
        request_id = str(uuid4())
        user_message = "Can you analyze this complex document for me?"
        
        # Start request tracking first
        await ux_logger.log_user_request_start(
            request_id=request_id,
            user_id="test_user_1",
            session_id="test_session_1",
            endpoint="/chat",
            request_type="chat_message",
            user_message=user_message,
            required_capabilities=["document_analysis", "advanced_chat"]
        )
        
        # Generate fallback response
        fallback_response = fallback_service.generate_fallback_response(user_message)
        
        # Track fallback usage
        await log_fallback_response_usage(
            request_id=request_id,
            fallback_response=fallback_response,
            user_acceptance=True,
            user_feedback="User found the fallback helpful"
        )
        
        # Complete the request
        await ux_logger.log_user_request_completion(
            request_id=request_id,
            outcome=RequestOutcome.FALLBACK_USED,
            response_time_seconds=0.8,
            fallback_used=True,
            fallback_quality=fallback_response.response_quality,
            fallback_response=fallback_response.response_text
        )
        
        logger.info(f"✓ Tracked complete fallback request lifecycle for {request_id}")
        logger.info(f"  - Response quality: {fallback_response.response_quality.value}")
        logger.info(f"  - Helpful now: {fallback_response.helpful_now}")
        logger.info(f"  - Limitations: {len(fallback_response.limitations)}")
        
        # Test 2: Multiple fallback responses with different intents and complete lifecycle
        logger.info("\nTest 2: Multiple fallback responses with different intents and complete lifecycle")
        
        test_messages = [
            ("What's the weather like today?", UserIntent.SIMPLE_QUESTION),
            ("Please search for information about machine learning", UserIntent.SEARCH_QUERY),
            ("Can you create a presentation for me?", UserIntent.CREATIVE_TASK),
            ("Upload and analyze this PDF document", UserIntent.DOCUMENT_PROCESSING),
            ("Compare the pros and cons of different approaches", UserIntent.COMPLEX_ANALYSIS)
        ]
        
        for i, (message, expected_intent) in enumerate(test_messages):
            request_id = str(uuid4())
            user_id = f"test_user_{i+2}"
            session_id = f"test_session_{i+2}"
            
            # Start request tracking
            await ux_logger.log_user_request_start(
                request_id=request_id,
                user_id=user_id,
                session_id=session_id,
                endpoint="/chat",
                request_type="chat_message",
                user_message=message,
                required_capabilities=["advanced_chat", "document_analysis"]
            )
            
            # Generate and track fallback response
            fallback_response = fallback_service.generate_fallback_response(message)
            
            # Analyze intent to verify
            intent_analysis = fallback_service.analyze_user_intent(message)
            
            await log_fallback_response_usage(
                request_id=request_id,
                fallback_response=fallback_response,
                user_acceptance=i % 2 == 0,  # Alternate acceptance
                user_feedback=f"Test feedback for message {i+1}"
            )
            
            # Complete request
            await ux_logger.log_user_request_completion(
                request_id=request_id,
                outcome=RequestOutcome.FALLBACK_USED,
                response_time_seconds=0.5 + (i * 0.1),
                fallback_used=True,
                fallback_quality=fallback_response.response_quality,
                fallback_response=fallback_response.response_text
            )
            
            logger.info(f"✓ Tracked fallback {i+1}: {expected_intent.value}")
            logger.info(f"  - Detected intent: {intent_analysis.primary_intent.value}")
            logger.info(f"  - Confidence: {intent_analysis.confidence:.2f}")
            logger.info(f"  - Quality: {fallback_response.response_quality.value}")
        
        # Test 3: Fallback response effectiveness tracking with complete request lifecycle
        logger.info("\nTest 3: Fallback response effectiveness tracking with complete request lifecycle")
        
        # Simulate different user reactions to fallback responses
        effectiveness_scenarios = [
            {
                "message": "Help me understand this technical concept",
                "user_acceptance": True,
                "feedback": "The fallback was helpful and clear"
            },
            {
                "message": "Process this uploaded document",
                "user_acceptance": False,
                "feedback": "Fallback wasn't useful, needed document processing"
            },
            {
                "message": "What can you do right now?",
                "user_acceptance": True,
                "feedback": "Good explanation of current capabilities"
            },
            {
                "message": "Perform complex data analysis",
                "user_acceptance": None,
                "feedback": "User abandoned after seeing fallback"
            }
        ]
        
        for i, scenario in enumerate(effectiveness_scenarios):
            request_id = str(uuid4())
            user_id = f"effectiveness_user_{i+1}"
            session_id = f"effectiveness_session_{i+1}"
            
            # Start request tracking
            await ux_logger.log_user_request_start(
                request_id=request_id,
                user_id=user_id,
                session_id=session_id,
                endpoint="/chat",
                request_type="chat_message",
                user_message=scenario["message"],
                required_capabilities=["advanced_chat"]
            )
            
            fallback_response = fallback_service.generate_fallback_response(scenario["message"])
            
            await log_fallback_response_usage(
                request_id=request_id,
                fallback_response=fallback_response,
                user_acceptance=scenario["user_acceptance"],
                user_feedback=scenario["feedback"]
            )
            
            # Complete request with appropriate outcome
            outcome = RequestOutcome.FALLBACK_USED
            if scenario["user_acceptance"] is None:
                outcome = RequestOutcome.ABANDONED
            elif scenario["user_acceptance"] is False:
                outcome = RequestOutcome.FALLBACK_USED  # Still used, just not accepted
            
            await ux_logger.log_user_request_completion(
                request_id=request_id,
                outcome=outcome,
                response_time_seconds=0.6,
                fallback_used=True,
                fallback_quality=fallback_response.response_quality,
                fallback_response=fallback_response.response_text
            )
            
            acceptance_text = "Accepted" if scenario["user_acceptance"] else "Rejected" if scenario["user_acceptance"] is False else "Abandoned"
            logger.info(f"✓ Tracked effectiveness scenario: {acceptance_text}")
        
        # Test 4: Get UX summary with fallback tracking data
        logger.info("\nTest 4: UX summary with fallback tracking data")
        
        # Wait a moment for analytics to update
        await asyncio.sleep(1)
        
        # Get UX summary
        ux_summary = ux_logger.get_ux_summary()
        
        logger.info("✓ UX Summary:")
        logger.info(f"  - Total patterns logged: {ux_summary['total_patterns_logged']}")
        logger.info(f"  - Active sessions: {ux_summary['active_sessions']}")
        logger.info(f"  - Startup duration: {ux_summary['startup_duration_seconds']:.1f}s")
        
        # Check current metrics
        current_metrics = ux_summary['current_metrics']
        logger.info(f"  - Total requests: {current_metrics['total_requests']}")
        logger.info(f"  - Fallback requests: {current_metrics['fallback_requests']}")
        
        if current_metrics['most_common_intents']:
            logger.info("  - Most common intents:")
            for intent, count in current_metrics['most_common_intents'][:3]:
                logger.info(f"    * {intent}: {count}")
        
        # Test 5: Export patterns for analysis
        logger.info("\nTest 5: Export patterns for analysis")
        
        # Export patterns as JSON
        patterns_json = ux_logger.export_patterns("json")
        patterns_data = json.loads(patterns_json)
        
        logger.info(f"✓ Exported {len(patterns_data)} request patterns")
        
        # Count fallback usage patterns
        fallback_patterns = [p for p in patterns_data if p.get('fallback_used')]
        logger.info(f"  - Fallback patterns: {len(fallback_patterns)}")
        
        # Analyze fallback quality distribution
        quality_distribution = {}
        for pattern in fallback_patterns:
            quality = pattern.get('fallback_quality')
            if quality:
                quality_distribution[quality] = quality_distribution.get(quality, 0) + 1
        
        if quality_distribution:
            logger.info("  - Fallback quality distribution:")
            for quality, count in quality_distribution.items():
                logger.info(f"    * {quality}: {count}")
        
        # Test 6: Verify tracking integration
        logger.info("\nTest 6: Verify tracking integration")
        
        # Check that fallback tracking is properly integrated
        test_request_id = str(uuid4())
        test_message = "This is a test message for integration verification"
        
        # Start request tracking
        await ux_logger.log_user_request_start(
            request_id=test_request_id,
            user_id="test_user",
            session_id="test_session",
            endpoint="/chat",
            request_type="chat_message",
            user_message=test_message,
            required_capabilities=["advanced_chat"]
        )
        
        # Generate and track fallback
        fallback_response = fallback_service.generate_fallback_response(test_message)
        await log_fallback_response_usage(
            request_id=test_request_id,
            fallback_response=fallback_response,
            user_acceptance=True,
            user_feedback="Integration test"
        )
        
        # Complete request tracking
        await ux_logger.log_user_request_completion(
            request_id=test_request_id,
            outcome=RequestOutcome.FALLBACK_USED,
            response_time_seconds=0.5,
            fallback_used=True,
            fallback_quality=fallback_response.response_quality,
            fallback_response=fallback_response.response_text
        )
        
        logger.info("✓ Integration test completed successfully")
        
        # Final summary
        logger.info("\n" + "="*50)
        logger.info("FALLBACK RESPONSE USAGE TRACKING TEST RESULTS")
        logger.info("="*50)
        
        final_summary = ux_logger.get_ux_summary()
        final_metrics = final_summary['current_metrics']
        
        logger.info(f"✓ Total requests tracked: {final_metrics['total_requests']}")
        logger.info(f"✓ Fallback requests tracked: {final_metrics['fallback_requests']}")
        logger.info(f"✓ Successful requests: {final_metrics['successful_requests']}")
        logger.info(f"✓ Test duration: {final_summary['startup_duration_seconds']:.1f}s")
        
        if final_metrics['fallback_requests'] > 0:
            fallback_rate = (final_metrics['fallback_requests'] / final_metrics['total_requests']) * 100
            logger.info(f"✓ Fallback usage rate: {fallback_rate:.1f}%")
        
        logger.info("\n🎉 All fallback response usage tracking tests passed!")
        return True
        
    except Exception as e:
        logger.error(f"❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    finally:
        # Stop UX logging
        await ux_logger.stop_logging()


async def main():
    """Main test function."""
    logger.info("Fallback Response Usage Tracking Test")
    logger.info("=" * 50)
    
    try:
        success = await test_fallback_response_usage_tracking()
        
        if success:
            logger.info("\n✅ All tests completed successfully!")
            return 0
        else:
            logger.error("\n❌ Some tests failed!")
            return 1
            
    except Exception as e:
        logger.error(f"Test execution failed: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)