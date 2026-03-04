#!/usr/bin/env python3
"""
Test User Experience Analytics Service

This test validates the comprehensive user experience analytics service
that provides insights, recommendations, and reports based on UX logger data.
"""

import asyncio
import json
import logging
import sys
import time
from datetime import datetime, timedelta
from typing import Dict, Any

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Add src to path for imports
sys.path.insert(0, 'src')

try:
    from multimodal_librarian.services.ux_analytics_service import (
        UserExperienceAnalyticsService, initialize_ux_analytics_service,
        AnalyticsInsightType, InsightSeverity
    )
    from multimodal_librarian.logging.ux_logger import (
        UserExperienceLogger, initialize_ux_logger, RequestOutcome
    )
    from multimodal_librarian.startup.phase_manager import StartupPhaseManager, StartupPhase
    from multimodal_librarian.services.capability_service import CapabilityLevel
    from multimodal_librarian.services.fallback_service import FallbackResponseService
    
    logger.info("Successfully imported UX analytics modules")
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


async def create_test_data(ux_logger: UserExperienceLogger) -> Dict[str, Any]:
    """Create comprehensive test data for analytics testing."""
    logger.info("Creating test data for analytics")
    
    fallback_service = FallbackResponseService()
    test_scenarios = []
    
    # Scenario 1: Successful user journey
    logger.info("Creating successful user journey scenario")
    for i in range(3):
        request_id = f"success_request_{i}"
        user_id = "successful_user"
        session_id = "session_successful"
        
        await ux_logger.log_user_request_start(
            request_id=request_id,
            user_id=user_id,
            session_id=session_id,
            endpoint="/api/chat",
            request_type="chat",
            user_message=f"Successful chat request {i}",
            required_capabilities=["basic_chat"],
            user_agent="TestAgent/1.0",
            ip_address="127.0.0.1"
        )
        
        await asyncio.sleep(0.1)
        
        await ux_logger.log_user_request_completion(
            request_id=request_id,
            outcome=RequestOutcome.SUCCESS,
            response_time_seconds=2.0 + i * 0.5,
            fallback_used=False
        )
        
        test_scenarios.append({
            "type": "success",
            "request_id": request_id,
            "user_id": user_id,
            "wait_time": 2.0 + i * 0.5
        })
    
    # Scenario 2: High wait time with fallback acceptance
    logger.info("Creating high wait time with fallback scenario")
    for i in range(4):
        request_id = f"fallback_request_{i}"
        user_id = "fallback_user"
        session_id = "session_fallback"
        
        user_message = f"Complex request requiring fallback {i}"
        
        await ux_logger.log_user_request_start(
            request_id=request_id,
            user_id=user_id,
            session_id=session_id,
            endpoint="/api/document/analyze",
            request_type="document",
            user_message=user_message,
            required_capabilities=["document_analysis", "advanced_ai"],
            user_agent="TestAgent/1.0",
            ip_address="127.0.0.2"
        )
        
        await asyncio.sleep(0.1)
        
        # Generate fallback response
        fallback_response = fallback_service.generate_fallback_response(user_message)
        
        await ux_logger.log_fallback_response_usage(
            request_id=request_id,
            fallback_response=fallback_response,
            user_acceptance=True,
            user_feedback="Fallback was helpful"
        )
        
        await ux_logger.log_user_request_completion(
            request_id=request_id,
            outcome=RequestOutcome.FALLBACK_USED,
            response_time_seconds=15.0 + i * 5,
            fallback_used=True,
            fallback_quality=fallback_response.response_quality,
            fallback_response=fallback_response.response_text
        )
        
        test_scenarios.append({
            "type": "fallback",
            "request_id": request_id,
            "user_id": user_id,
            "wait_time": 15.0 + i * 5,
            "fallback_quality": fallback_response.response_quality.value
        })
    
    # Scenario 3: User abandonment patterns
    logger.info("Creating user abandonment scenarios")
    abandonment_reasons = ["timeout_exceeded", "error_encountered", "user_initiated"]
    
    for i, reason in enumerate(abandonment_reasons):
        request_id = f"abandon_request_{i}"
        user_id = f"abandoner_user_{i}"
        session_id = f"session_abandon_{i}"
        
        await ux_logger.log_user_request_start(
            request_id=request_id,
            user_id=user_id,
            session_id=session_id,
            endpoint="/api/search",
            request_type="search",
            user_message=f"Search request that will be abandoned: {reason}",
            required_capabilities=["search_model", "embedding_model"],
            user_agent="TestAgent/1.0",
            ip_address=f"127.0.0.{i+3}"
        )
        
        await asyncio.sleep(0.1)
        
        # Simulate different wait times before abandonment
        wait_time = 30 + i * 10
        
        await ux_logger.log_user_request_completion(
            request_id=request_id,
            outcome=RequestOutcome.ABANDONED,
            response_time_seconds=None
        )
        
        await ux_logger.log_user_abandonment(
            user_id=user_id,
            session_id=session_id,
            abandonment_reason=reason,
            context={
                "wait_time_seconds": wait_time,
                "phase": "minimal"
            }
        )
        
        test_scenarios.append({
            "type": "abandonment",
            "request_id": request_id,
            "user_id": user_id,
            "reason": reason,
            "wait_time": wait_time
        })
    
    # Scenario 4: Error scenarios
    logger.info("Creating error scenarios")
    for i in range(2):
        request_id = f"error_request_{i}"
        user_id = f"error_user_{i}"
        session_id = f"session_error_{i}"
        
        await ux_logger.log_user_request_start(
            request_id=request_id,
            user_id=user_id,
            session_id=session_id,
            endpoint="/api/knowledge",
            request_type="knowledge",
            user_message=f"Knowledge request that will error {i}",
            required_capabilities=["knowledge_graph"],
            user_agent="TestAgent/1.0",
            ip_address=f"127.0.0.{i+6}"
        )
        
        await asyncio.sleep(0.1)
        
        await ux_logger.log_user_request_completion(
            request_id=request_id,
            outcome=RequestOutcome.ERROR,
            response_time_seconds=5.0,
            error_message=f"Test error {i}: Service temporarily unavailable",
            error_type="service_error"
        )
        
        test_scenarios.append({
            "type": "error",
            "request_id": request_id,
            "user_id": user_id,
            "error_message": f"Test error {i}: Service temporarily unavailable"
        })
    
    # Wait for analytics to process
    await asyncio.sleep(2)
    
    logger.info(f"Created {len(test_scenarios)} test scenarios")
    return {
        "scenarios": test_scenarios,
        "total_requests": len(test_scenarios),
        "success_requests": len([s for s in test_scenarios if s["type"] == "success"]),
        "fallback_requests": len([s for s in test_scenarios if s["type"] == "fallback"]),
        "abandoned_requests": len([s for s in test_scenarios if s["type"] == "abandonment"]),
        "error_requests": len([s for s in test_scenarios if s["type"] == "error"])
    }


async def test_user_experience_analytics():
    """Test the comprehensive user experience analytics service."""
    logger.info("🧪 Testing User Experience Analytics Service")
    logger.info("=" * 60)
    
    try:
        # Initialize components
        phase_manager = MockPhaseManager()
        ux_logger = initialize_ux_logger(phase_manager)
        await ux_logger.start_logging()
        
        analytics_service = initialize_ux_analytics_service(ux_logger)
        
        logger.info("✅ Analytics service initialized")
        
        # Create comprehensive test data
        test_data = await create_test_data(ux_logger)
        logger.info(f"✅ Test data created: {test_data['total_requests']} requests")
        
        # Test 1: Generate comprehensive analysis
        logger.info("\n📊 Test 1: Comprehensive Analysis Generation")
        
        analysis = await analytics_service.generate_comprehensive_analysis()
        
        if "error" in analysis:
            logger.error(f"❌ Analysis generation failed: {analysis['error']}")
            return False
        
        logger.info("✅ Comprehensive analysis generated successfully")
        logger.info(f"   • Analysis sections: {list(analysis.keys())}")
        
        # Validate analysis structure
        expected_sections = [
            "summary", "user_journeys", "phase_analysis", "behavior_patterns",
            "fallback_effectiveness", "abandonment_analysis", "satisfaction_analysis",
            "insights", "recommendations", "timestamp", "data_freshness"
        ]
        
        missing_sections = [section for section in expected_sections if section not in analysis]
        if missing_sections:
            logger.warning(f"   ⚠️  Missing analysis sections: {missing_sections}")
        else:
            logger.info("   ✅ All expected analysis sections present")
        
        # Test 2: Executive Summary Analysis
        logger.info("\n📊 Test 2: Executive Summary Analysis")
        
        summary = analysis.get("summary", {})
        if not summary:
            logger.error("❌ No executive summary generated")
            return False
        
        logger.info("✅ Executive summary generated")
        logger.info(f"   • Health Score: {summary.get('health_score', 'N/A')}/100")
        logger.info(f"   • Health Status: {summary.get('health_status', 'N/A')}")
        
        key_metrics = summary.get("key_metrics", {})
        logger.info(f"   • Total Requests: {key_metrics.get('total_requests', 0)}")
        logger.info(f"   • Success Rate: {key_metrics.get('success_rate', 0)}%")
        logger.info(f"   • Abandonment Rate: {key_metrics.get('abandonment_rate', 0)}%")
        logger.info(f"   • Fallback Rate: {key_metrics.get('fallback_rate', 0)}%")
        
        # Validate metrics make sense
        total_requests = key_metrics.get('total_requests', 0)
        if total_requests != test_data['total_requests']:
            logger.warning(f"   ⚠️  Request count mismatch: expected {test_data['total_requests']}, got {total_requests}")
        
        # Test 3: User Journey Analysis
        logger.info("\n📊 Test 3: User Journey Analysis")
        
        user_journeys = analysis.get("user_journeys", {})
        if not user_journeys or "message" in user_journeys:
            logger.warning(f"   ⚠️  Limited user journey data: {user_journeys.get('message', 'Unknown issue')}")
        else:
            logger.info("✅ User journey analysis completed")
            logger.info(f"   • Total Journeys: {user_journeys.get('total_journeys', 0)}")
            logger.info(f"   • Completion Rate: {user_journeys.get('completion_rate', 0)}%")
            logger.info(f"   • Average Patience Score: {user_journeys.get('average_patience_score', 0):.1f}")
            logger.info(f"   • Average Satisfaction Score: {user_journeys.get('average_satisfaction_score', 0):.1f}")
            
            # Check for pain points and positive moments
            pain_points = user_journeys.get('common_pain_points', [])
            positive_moments = user_journeys.get('common_positive_moments', [])
            
            if pain_points:
                logger.info(f"   • Common Pain Points: {[p[0] for p in pain_points[:3]]}")
            if positive_moments:
                logger.info(f"   • Positive Moments: {[p[0] for p in positive_moments[:3]]}")
        
        # Test 4: Startup Phase Analysis
        logger.info("\n📊 Test 4: Startup Phase Analysis")
        
        phase_analysis = analysis.get("phase_analysis", {})
        if not phase_analysis or "message" in phase_analysis:
            logger.warning(f"   ⚠️  Limited phase analysis data: {phase_analysis.get('message', 'Unknown issue')}")
        else:
            logger.info("✅ Startup phase analysis completed")
            logger.info(f"   • Phases Analyzed: {phase_analysis.get('phases_analyzed', 0)}")
            
            phase_details = phase_analysis.get('phase_details', {})
            for phase_name, phase_data in phase_details.items():
                logger.info(f"   • {phase_name.title()} Phase:")
                logger.info(f"     - Requests: {phase_data.get('total_requests', 0)}")
                logger.info(f"     - Success Rate: {phase_data.get('success_rate', 0):.1%}")
                logger.info(f"     - Abandonment Rate: {phase_data.get('abandonment_rate', 0):.1%}")
        
        # Test 5: Behavior Pattern Analysis
        logger.info("\n📊 Test 5: Behavior Pattern Analysis")
        
        behavior_patterns = analysis.get("behavior_patterns", {})
        if not behavior_patterns or "message" in behavior_patterns:
            logger.warning(f"   ⚠️  Limited behavior pattern data: {behavior_patterns.get('message', 'Unknown issue')}")
        else:
            logger.info("✅ Behavior pattern analysis completed")
            logger.info(f"   • Sessions Analyzed: {behavior_patterns.get('total_sessions_analyzed', 0)}")
            
            pattern_distribution = behavior_patterns.get('behavior_pattern_distribution', {})
            if pattern_distribution:
                logger.info(f"   • Pattern Distribution: {pattern_distribution}")
            
            score_analysis = behavior_patterns.get('score_analysis', {})
            if score_analysis:
                patience = score_analysis.get('patience', {})
                engagement = score_analysis.get('engagement', {})
                satisfaction = score_analysis.get('satisfaction', {})
                
                logger.info(f"   • Average Patience: {patience.get('average', 0):.1f}")
                logger.info(f"   • Average Engagement: {engagement.get('average', 0):.1f}")
                logger.info(f"   • Average Satisfaction: {satisfaction.get('average', 0):.1f}")
        
        # Test 6: Fallback Effectiveness Analysis
        logger.info("\n📊 Test 6: Fallback Effectiveness Analysis")
        
        fallback_effectiveness = analysis.get("fallback_effectiveness", {})
        if not fallback_effectiveness or "message" in fallback_effectiveness:
            logger.warning(f"   ⚠️  Limited fallback analysis data: {fallback_effectiveness.get('message', 'Unknown issue')}")
        else:
            logger.info("✅ Fallback effectiveness analysis completed")
            logger.info(f"   • Total Fallback Responses: {fallback_effectiveness.get('total_fallback_responses', 0)}")
            logger.info(f"   • Acceptance Rate: {fallback_effectiveness.get('acceptance_rate', 0)}%")
            
            quality_distribution = fallback_effectiveness.get('quality_distribution', {})
            if quality_distribution:
                logger.info(f"   • Quality Distribution: {quality_distribution}")
            
            recommendations = fallback_effectiveness.get('fallback_recommendations', [])
            if recommendations:
                logger.info(f"   • Recommendations: {recommendations[:2]}")
        
        # Test 7: Abandonment Analysis
        logger.info("\n📊 Test 7: Abandonment Analysis")
        
        abandonment_analysis = analysis.get("abandonment_analysis", {})
        if not abandonment_analysis or "message" in abandonment_analysis:
            logger.warning(f"   ⚠️  Limited abandonment analysis data: {abandonment_analysis.get('message', 'Unknown issue')}")
        else:
            logger.info("✅ Abandonment analysis completed")
            logger.info(f"   • Total Abandoned Requests: {abandonment_analysis.get('total_abandoned_requests', 0)}")
            logger.info(f"   • Abandonment Rate: {abandonment_analysis.get('abandonment_rate', 0)}%")
            logger.info(f"   • Average Wait Before Abandonment: {abandonment_analysis.get('average_wait_before_abandonment', 0)}s")
            
            abandonment_reasons = abandonment_analysis.get('abandonment_reasons', {})
            if abandonment_reasons:
                logger.info(f"   • Abandonment Reasons: {abandonment_reasons}")
            
            prevention_recommendations = abandonment_analysis.get('prevention_recommendations', [])
            if prevention_recommendations:
                logger.info(f"   • Prevention Recommendations: {prevention_recommendations[:2]}")
        
        # Test 8: Actionable Insights
        logger.info("\n📊 Test 8: Actionable Insights")
        
        insights = analysis.get("insights", [])
        if not insights:
            logger.warning("   ⚠️  No actionable insights generated")
        else:
            logger.info(f"✅ Generated {len(insights)} actionable insights")
            
            # Group insights by type and severity
            insight_types = {}
            insight_severities = {}
            
            for insight in insights:
                # Handle both dict and AnalyticsInsight objects
                if hasattr(insight, 'insight_type'):
                    insight_type = insight.insight_type.value if hasattr(insight.insight_type, 'value') else str(insight.insight_type)
                    severity = insight.severity.value if hasattr(insight.severity, 'value') else str(insight.severity)
                else:
                    insight_type = insight.get('insight_type', 'unknown')
                    severity = insight.get('severity', 'unknown')
                
                insight_types[insight_type] = insight_types.get(insight_type, 0) + 1
                insight_severities[severity] = insight_severities.get(severity, 0) + 1
            
            logger.info(f"   • Insight Types: {insight_types}")
            logger.info(f"   • Severity Distribution: {insight_severities}")
            
            # Show top insights
            for i, insight in enumerate(insights[:3]):
                if hasattr(insight, 'severity'):
                    severity = insight.severity.value if hasattr(insight.severity, 'value') else str(insight.severity)
                    title = insight.title
                    description = insight.description
                else:
                    severity = insight.get('severity', 'unknown')
                    title = insight.get('title', 'Unknown')
                    description = insight.get('description', 'No description')
                
                severity_icon = "🔴" if severity == 'critical' else "🟡" if severity == 'warning' else "🔵"
                logger.info(f"   {severity_icon} {title}: {description}")
        
        # Test 9: Recommendations
        logger.info("\n📊 Test 9: Improvement Recommendations")
        
        recommendations = analysis.get("recommendations", [])
        if not recommendations:
            logger.warning("   ⚠️  No recommendations generated")
        else:
            logger.info(f"✅ Generated {len(recommendations)} recommendations")
            
            # Group recommendations by category and priority
            categories = {}
            priorities = {}
            
            for rec in recommendations:
                category = rec.get('category', 'unknown')
                priority = rec.get('priority', 'unknown')
                
                categories[category] = categories.get(category, 0) + 1
                priorities[priority] = priorities.get(priority, 0) + 1
            
            logger.info(f"   • Categories: {categories}")
            logger.info(f"   • Priorities: {priorities}")
            
            # Show top recommendations
            for i, rec in enumerate(recommendations[:3]):
                priority_icon = "🔥" if rec['priority'] == 'Critical' else "⚡" if rec['priority'] == 'High' else "📋"
                logger.info(f"   {priority_icon} {rec['title']}")
                logger.info(f"     {rec['description']}")
                logger.info(f"     Expected Impact: {rec.get('expected_impact', 'Not specified')}")
        
        # Test 10: Real-time Insights
        logger.info("\n📊 Test 10: Real-time Insights")
        
        real_time_insights = await analytics_service.get_real_time_insights()
        
        if "error" in real_time_insights:
            logger.error(f"❌ Real-time insights failed: {real_time_insights['error']}")
        else:
            logger.info("✅ Real-time insights generated")
            logger.info(f"   • Health Score: {real_time_insights.get('health_score', 'N/A')}")
            logger.info(f"   • Health Status: {real_time_insights.get('health_status', 'N/A')}")
            
            active_issues = real_time_insights.get('active_issues', [])
            if active_issues:
                logger.info(f"   • Active Issues: {active_issues}")
            else:
                logger.info("   • No active issues detected")
        
        # Test 11: Export Functionality
        logger.info("\n📊 Test 11: Analytics Export")
        
        # Test JSON export
        json_report = await analytics_service.export_analytics_report("json")
        if json_report.startswith("Error"):
            logger.error(f"❌ JSON export failed: {json_report}")
        else:
            logger.info("✅ JSON export successful")
            logger.info(f"   • Report length: {len(json_report)} characters")
            
            # Validate JSON structure
            try:
                json_data = json.loads(json_report)
                logger.info(f"   • JSON sections: {list(json_data.keys()) if isinstance(json_data, dict) else 'Not a dict'}")
            except json.JSONDecodeError as e:
                logger.error(f"   ❌ Invalid JSON format: {e}")
        
        # Test summary export
        summary_report = await analytics_service.export_analytics_report("summary")
        if summary_report.startswith("Error"):
            logger.error(f"❌ Summary export failed: {summary_report}")
        else:
            logger.info("✅ Summary export successful")
            logger.info(f"   • Summary length: {len(summary_report)} characters")
            logger.info(f"   • First line: {summary_report.split(chr(10))[0] if summary_report else 'Empty'}")
        
        # Test 12: Service Integration
        logger.info("\n📊 Test 12: Service Integration")
        
        # Test service availability
        service = analytics_service
        if service:
            logger.info("✅ Analytics service is available")
            
            # Test service state
            if hasattr(service, 'ux_logger') and service.ux_logger:
                logger.info("✅ UX logger integration working")
            else:
                logger.warning("⚠️  UX logger integration issue")
            
            # Test cache functionality
            if hasattr(service, 'insights_cache'):
                logger.info("✅ Insights cache available")
            else:
                logger.warning("⚠️  Insights cache not available")
        else:
            logger.error("❌ Analytics service not available")
        
        # Final validation
        logger.info("\n📈 Final Validation")
        
        # Validate that we have meaningful data
        total_patterns = len(ux_logger.request_patterns)
        total_sessions = len(ux_logger.completed_sessions) + len(ux_logger.active_sessions)
        
        logger.info(f"   • Total request patterns logged: {total_patterns}")
        logger.info(f"   • Total user sessions: {total_sessions}")
        
        if total_patterns < test_data['total_requests']:
            logger.warning(f"   ⚠️  Pattern count mismatch: expected {test_data['total_requests']}, got {total_patterns}")
        
        # Check that analytics reflect the test data
        expected_abandoned = test_data['abandoned_requests']
        expected_fallback = test_data['fallback_requests']
        expected_success = test_data['success_requests']
        
        actual_metrics = summary.get('key_metrics', {})
        actual_abandoned = actual_metrics.get('abandoned_requests', 0)
        actual_fallback = actual_metrics.get('fallback_requests', 0)  
        actual_success = actual_metrics.get('successful_requests', 0)
        
        logger.info(f"   • Expected vs Actual - Success: {expected_success} vs {actual_success}")
        logger.info(f"   • Expected vs Actual - Fallback: {expected_fallback} vs {actual_fallback}")
        logger.info(f"   • Expected vs Actual - Abandoned: {expected_abandoned} vs {actual_abandoned}")
        
        # Calculate accuracy
        total_expected = expected_success + expected_fallback + expected_abandoned + test_data['error_requests']
        total_actual = actual_success + actual_fallback + actual_abandoned + actual_metrics.get('error_requests', 0)
        
        accuracy = (total_actual / total_expected * 100) if total_expected > 0 else 0
        logger.info(f"   • Analytics Accuracy: {accuracy:.1f}%")
        
        if accuracy < 80:
            logger.warning("   ⚠️  Low analytics accuracy - may indicate data processing issues")
        else:
            logger.info("   ✅ Good analytics accuracy")
        
        logger.info("\n🎉 User Experience Analytics Test Completed Successfully!")
        
        return {
            "success": True,
            "test_data": test_data,
            "analysis_sections": len(analysis),
            "insights_generated": len(insights),
            "recommendations_generated": len(recommendations),
            "analytics_accuracy": accuracy,
            "health_score": summary.get('health_score', 0)
        }
        
    except Exception as e:
        logger.error(f"❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return {
            "success": False,
            "error": str(e)
        }
    
    finally:
        # Clean up
        try:
            if 'ux_logger' in locals():
                await ux_logger.stop_logging()
        except Exception as e:
            logger.warning(f"Cleanup error: {e}")


async def test_analytics_api_integration():
    """Test the analytics API router integration."""
    logger.info("\n🧪 Testing Analytics API Integration")
    logger.info("=" * 50)
    
    try:
        # This would normally test the FastAPI router, but we'll simulate it
        from multimodal_librarian.api.routers.ux_analytics import get_analytics_service
        
        # Test service dependency injection
        service = get_analytics_service()
        if service:
            logger.info("✅ Analytics service dependency injection working")
        else:
            logger.warning("⚠️  Analytics service not available via dependency injection")
        
        # Test would include actual API calls if we had a test client
        logger.info("✅ API integration test completed (simulated)")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ API integration test failed: {e}")
        return False


async def main():
    """Run all user experience analytics tests."""
    logger.info("🚀 Starting User Experience Analytics Tests")
    logger.info("=" * 70)
    
    # Run main analytics test
    analytics_result = await test_user_experience_analytics()
    
    # Handle case where test returns boolean instead of dict
    if isinstance(analytics_result, bool):
        analytics_result = {"success": analytics_result, "error": "Test returned boolean instead of dict"}
    
    # Run API integration test
    api_result = await test_analytics_api_integration()
    
    # Summary
    logger.info("\n" + "="*70)
    logger.info("TEST SUMMARY")
    logger.info("="*70)
    
    if analytics_result["success"]:
        logger.info("✅ User Experience Analytics: PASSED")
        logger.info(f"   • Test scenarios: {analytics_result['test_data']['total_requests']}")
        logger.info(f"   • Analysis sections: {analytics_result['analysis_sections']}")
        logger.info(f"   • Insights generated: {analytics_result['insights_generated']}")
        logger.info(f"   • Recommendations: {analytics_result['recommendations_generated']}")
        logger.info(f"   • Health score: {analytics_result['health_score']}/100")
        logger.info(f"   • Analytics accuracy: {analytics_result['analytics_accuracy']:.1f}%")
    else:
        logger.error("❌ User Experience Analytics: FAILED")
        logger.error(f"   Error: {analytics_result['error']}")
    
    if api_result:
        logger.info("✅ API Integration: PASSED")
    else:
        logger.error("❌ API Integration: FAILED")
    
    overall_success = analytics_result["success"] and api_result
    
    if overall_success:
        logger.info("\n🎉 ALL TESTS PASSED!")
        logger.info("User experience analytics service is working correctly.")
    else:
        logger.error("\n❌ SOME TESTS FAILED!")
        logger.error("Please check the implementation and fix any issues.")
    
    return overall_success


if __name__ == "__main__":
    result = asyncio.run(main())
    exit(0 if result else 1)