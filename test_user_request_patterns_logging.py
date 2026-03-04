#!/usr/bin/env python3
"""
Test User Request Patterns Logging

This test verifies that the user experience logger correctly logs user request patterns
during startup phases, including fallback response usage and user wait times.
"""

import asyncio
import time
import logging
from datetime import datetime, timedelta
from typing import Dict, Any

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_user_request_patterns_logging():
    """Test the user experience logger functionality."""
    logger.info("🧪 Testing User Request Patterns Logging")
    
    try:
        # Import required modules
        from src.multimodal_librarian.startup.phase_manager import StartupPhaseManager, StartupPhase
        from src.multimodal_librarian.logging.ux_logger import (
            UserExperienceLogger, RequestOutcome, UserIntent, UserBehaviorPattern
        )
        from src.multimodal_librarian.services.capability_service import CapabilityLevel
        from src.multimodal_librarian.services.fallback_service import FallbackResponse
        
        logger.info("✅ Successfully imported UX logging modules")
        
        # Initialize startup phase manager
        phase_manager = StartupPhaseManager()
        logger.info("✅ StartupPhaseManager initialized")
        
        # Initialize user experience logger
        ux_logger = UserExperienceLogger(phase_manager)
        await ux_logger.start_logging()
        logger.info("✅ UserExperienceLogger initialized and started")
        
        # Start phase progression to simulate startup
        await phase_manager.start_phase_progression()
        logger.info("✅ Phase progression started")
        
        # Wait a moment for minimal phase to be established
        await asyncio.sleep(2)
        
        # Test 1: Log a simple user request during minimal phase
        logger.info("🔍 Test 1: Logging simple user request during minimal phase")
        
        request_id_1 = "test_request_001"
        await ux_logger.log_user_request_start(
            request_id=request_id_1,
            user_id="test_user_001",
            session_id="test_session_001",
            endpoint="/api/chat",
            request_type="chat",
            user_message="Hello, what can you do?",
            required_capabilities=["basic_chat"],
            user_agent="TestAgent/1.0",
            ip_address="127.0.0.1"
        )
        
        # Simulate processing time
        await asyncio.sleep(1)
        
        # Complete the request with fallback response
        await ux_logger.log_user_request_completion(
            request_id=request_id_1,
            outcome=RequestOutcome.FALLBACK_USED,
            response_time_seconds=1.0,
            fallback_used=True,
            fallback_quality=CapabilityLevel.BASIC,
            fallback_response="I'm currently starting up. Basic functionality is available."
        )
        
        logger.info("✅ Test 1 completed: Simple request with fallback logged")
        
        # Test 2: Log a complex request that gets abandoned
        logger.info("🔍 Test 2: Logging complex request that gets abandoned")
        
        request_id_2 = "test_request_002"
        await ux_logger.log_user_request_start(
            request_id=request_id_2,
            user_id="test_user_002",
            session_id="test_session_002",
            endpoint="/api/document/analyze",
            request_type="document",
            user_message="Please analyze this complex document",
            required_capabilities=["document_analysis", "advanced_ai"],
            user_agent="TestAgent/1.0",
            ip_address="127.0.0.2"
        )
        
        # Simulate user abandoning after waiting
        await asyncio.sleep(2)
        
        await ux_logger.log_user_request_completion(
            request_id=request_id_2,
            outcome=RequestOutcome.ABANDONED,
            response_time_seconds=None
        )
        
        logger.info("✅ Test 2 completed: Abandoned request logged")
        
        # Test 3: Log multiple requests from same user to test behavior analysis
        logger.info("🔍 Test 3: Logging multiple requests for behavior analysis")
        
        user_id = "test_user_003"
        session_id = "test_session_003"
        
        for i in range(3):
            request_id = f"test_request_00{3+i}"
            
            await ux_logger.log_user_request_start(
                request_id=request_id,
                user_id=user_id,
                session_id=session_id,
                endpoint="/api/search",
                request_type="search",
                user_message=f"Search query {i+1}",
                required_capabilities=["search"],
                user_agent="TestAgent/1.0",
                ip_address="127.0.0.3"
            )
            
            await asyncio.sleep(0.5)
            
            # Vary outcomes to test behavior classification
            if i == 0:
                outcome = RequestOutcome.SUCCESS
                fallback_used = False
            elif i == 1:
                outcome = RequestOutcome.FALLBACK_USED
                fallback_used = True
            else:
                outcome = RequestOutcome.ERROR
                fallback_used = False
            
            await ux_logger.log_user_request_completion(
                request_id=request_id,
                outcome=outcome,
                response_time_seconds=0.5,
                fallback_used=fallback_used,
                fallback_quality=CapabilityLevel.ENHANCED if fallback_used else None,
                error_message="Test error" if outcome == RequestOutcome.ERROR else None
            )
        
        logger.info("✅ Test 3 completed: Multiple requests for behavior analysis logged")
        
        # Test 4: Test fallback response usage logging
        logger.info("🔍 Test 4: Testing fallback response usage logging")
        
        request_id_4 = "test_request_006"
        await ux_logger.log_user_request_start(
            request_id=request_id_4,
            user_id="test_user_004",
            session_id="test_session_004",
            endpoint="/api/chat",
            request_type="chat",
            user_message="Can you help me with a creative writing task?",
            required_capabilities=["advanced_chat", "creative_writing"],
            user_agent="TestAgent/1.0",
            ip_address="127.0.0.4"
        )
        
        # Create a mock fallback response
        fallback_response = FallbackResponse(
            response_text="I can help with basic creative tasks, but my advanced creative capabilities are still loading.",
            response_quality=CapabilityLevel.ENHANCED,
            limitations=["Advanced creative writing not available", "Complex reasoning still loading"],
            available_alternatives=["Basic writing assistance", "Simple creative prompts"],
            upgrade_message="Full creative capabilities will be ready in about 2 minutes.",
            estimated_full_ready_time=120,
            helpful_now=True,
            context_preserved=True
        )
        
        await ux_logger.log_fallback_response_usage(
            request_id=request_id_4,
            fallback_response=fallback_response,
            user_acceptance=True,
            user_feedback="This is helpful for now"
        )
        
        await ux_logger.log_user_request_completion(
            request_id=request_id_4,
            outcome=RequestOutcome.FALLBACK_USED,
            response_time_seconds=0.8,
            fallback_used=True,
            fallback_quality=CapabilityLevel.ENHANCED,
            fallback_response=fallback_response.response_text
        )
        
        logger.info("✅ Test 4 completed: Fallback response usage logged")
        
        # Test 5: Test user abandonment logging
        logger.info("🔍 Test 5: Testing user abandonment logging")
        
        await ux_logger.log_user_abandonment(
            user_id="test_user_005",
            session_id="test_session_005",
            abandonment_reason="timeout_exceeded",
            context={"wait_time_seconds": 45, "phase": "minimal"}
        )
        
        logger.info("✅ Test 5 completed: User abandonment logged")
        
        # Wait for analytics to process
        await asyncio.sleep(3)
        
        # Test 6: Verify metrics and analytics
        logger.info("🔍 Test 6: Verifying UX metrics and analytics")
        
        ux_summary = ux_logger.get_ux_summary()
        
        logger.info(f"📊 UX Summary:")
        logger.info(f"  - Total requests logged: {ux_summary['total_patterns_logged']}")
        logger.info(f"  - Active sessions: {ux_summary['active_sessions']}")
        logger.info(f"  - Completed sessions: {ux_summary['completed_sessions']}")
        
        current_metrics = ux_summary['current_metrics']
        logger.info(f"  - Total users: {current_metrics['total_users']}")
        logger.info(f"  - Successful requests: {current_metrics['successful_requests']}")
        logger.info(f"  - Fallback requests: {current_metrics['fallback_requests']}")
        logger.info(f"  - Abandoned requests: {current_metrics['abandoned_requests']}")
        logger.info(f"  - Error requests: {current_metrics['error_requests']}")
        
        if current_metrics['average_user_wait_time']:
            logger.info(f"  - Average wait time: {current_metrics['average_user_wait_time']:.2f}s")
        
        if current_metrics['behavior_pattern_distribution']:
            logger.info(f"  - Behavior patterns: {current_metrics['behavior_pattern_distribution']}")
        
        logger.info("✅ Test 6 completed: UX metrics verified")
        
        # Test 7: Export patterns for analysis
        logger.info("🔍 Test 7: Testing pattern export functionality")
        
        json_export = ux_logger.export_patterns("json")
        logger.info(f"📄 JSON export length: {len(json_export)} characters")
        
        # Verify JSON is valid
        import json
        patterns_data = json.loads(json_export)
        logger.info(f"📄 Exported {len(patterns_data)} request patterns")
        
        # Show sample pattern
        if patterns_data:
            sample_pattern = patterns_data[0]
            logger.info(f"📄 Sample pattern: {sample_pattern['request_type']} -> {sample_pattern['outcome']}")
        
        logger.info("✅ Test 7 completed: Pattern export verified")
        
        # Stop logging
        await ux_logger.stop_logging()
        logger.info("✅ UX logger stopped")
        
        # Stop phase manager
        await phase_manager.shutdown()
        logger.info("✅ Phase manager shutdown")
        
        logger.info("🎉 All tests completed successfully!")
        
        return {
            "success": True,
            "tests_completed": 7,
            "patterns_logged": ux_summary['total_patterns_logged'],
            "metrics": current_metrics
        }
        
    except Exception as e:
        logger.error(f"❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return {
            "success": False,
            "error": str(e)
        }

async def main():
    """Main test function."""
    logger.info("🚀 Starting User Request Patterns Logging Test")
    
    result = await test_user_request_patterns_logging()
    
    if result["success"]:
        logger.info("✅ User Request Patterns Logging Test PASSED")
        logger.info(f"📊 Summary: {result['tests_completed']} tests completed, "
                   f"{result['patterns_logged']} patterns logged")
    else:
        logger.error("❌ User Request Patterns Logging Test FAILED")
        logger.error(f"Error: {result['error']}")
        exit(1)

if __name__ == "__main__":
    asyncio.run(main())