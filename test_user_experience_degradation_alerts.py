#!/usr/bin/env python3
"""
Test User Experience Degradation Alerts

This test validates that the enhanced user experience degradation alerts
are working correctly and can detect various types of UX issues.
"""

import asyncio
import time
import logging
from datetime import datetime, timedelta
from typing import Dict, Any

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Mock imports for testing
class MockStartupPhaseManager:
    """Mock startup phase manager for testing."""
    
    def __init__(self):
        self.current_phase = MockPhase("essential")
        self.phase_start_time = datetime.now() - timedelta(minutes=2)
        self.model_statuses = {
            "chat-model-base": MockModelStatus("loaded", "essential"),
            "search-model": MockModelStatus("loading", "essential"),
            "embedding-model": MockModelStatus("failed", "essential", "Out of memory"),
            "document-processor": MockModelStatus("loading", "standard"),
            "multimodal-model": MockModelStatus("not_loaded", "advanced")
        }
        self.phase_transitions = []
    
    def get_current_status(self):
        return MockStatus(self.current_phase, self.phase_start_time, self.model_statuses, self.phase_transitions)

class MockPhase:
    def __init__(self, value):
        self.value = value

class MockModelStatus:
    def __init__(self, status, priority, error_message=None):
        self.status = status
        self.priority = priority
        self.error_message = error_message
        self.started_at = datetime.now() - timedelta(minutes=1)
        self.retry_count = 0

class MockStatus:
    def __init__(self, current_phase, phase_start_time, model_statuses, phase_transitions):
        self.current_phase = current_phase
        self.phase_start_time = phase_start_time
        self.model_statuses = model_statuses
        self.phase_transitions = phase_transitions

class MockStartupMetricsCollector:
    """Mock metrics collector for testing."""
    
    def __init__(self):
        self.user_metrics = {
            "wait_time_stats": {
                "mean_seconds": 45.0,
                "p95_seconds": 85.0,
                "p99_seconds": 120.0,
                "min_seconds": 5.0,
                "max_seconds": 180.0
            },
            "success_rate": 0.75,
            "fallback_usage_rate": 0.8,
            "timeout_rate": 0.15,
            "abandonment_rate": 0.25,
            "total_requests": 50,
            "capability_availability": {
                "chat-model-base": True,
                "search-model": False,
                "embedding-model": False,
                "document-processor": False
            }
        }
        self.active_requests = {
            "req1": {"request_type": "chat", "is_overdue": True, "fallback_used": True},
            "req2": {"request_type": "search", "is_overdue": True, "fallback_used": False},
            "req3": {"request_type": "document", "is_overdue": False, "fallback_used": True},
            "req4": {"request_type": "chat", "is_overdue": True, "fallback_used": True}
        }
    
    def get_phase_completion_metrics(self, phase):
        return {"sample_count": 10, "mean_duration_seconds": 120.0}
    
    def get_model_loading_metrics(self):
        return {"success_rate": 0.6, "sample_count": 5, "loading_stats": {"mean_duration_seconds": 90.0}}
    
    def get_user_wait_time_metrics(self):
        return self.user_metrics
    
    def get_cache_performance_metrics(self):
        return {"cache_hit_rate": 0.3, "total_model_loads": 10, "cache_sources": {}}
    
    def get_active_user_requests(self):
        return self.active_requests

async def test_user_experience_degradation_alerts():
    """Test user experience degradation alerts functionality."""
    
    try:
        # Import the alerts service
        from src.multimodal_librarian.monitoring.startup_alerts import StartupAlertsService, AlertType, AlertSeverity
        
        logger.info("Testing User Experience Degradation Alerts")
        
        # Create mock dependencies
        phase_manager = MockStartupPhaseManager()
        metrics_collector = MockStartupMetricsCollector()
        
        # Create alerts service
        alerts_service = StartupAlertsService(phase_manager, metrics_collector)
        
        # Test 1: Check user experience degradation detection
        logger.info("Test 1: Basic user experience degradation detection")
        
        monitoring_data = {
            "timestamp": datetime.now(),
            "phase_manager_status": phase_manager.get_current_status(),
            "metrics_summary": {
                "user_experience": metrics_collector.user_metrics,
                "active_requests": metrics_collector.active_requests,
                "model_loading": {"success_rate": 0.6},
                "cache_performance": {"cache_hit_rate": 0.3}
            },
            "health_status": {"consecutive_failures": 0}
        }
        
        # Test basic UX degradation check
        ux_degraded = alerts_service._check_user_experience_degradation(monitoring_data)
        logger.info(f"UX degradation detected: {ux_degraded}")
        assert ux_degraded, "Should detect UX degradation with high wait times and low success rate"
        
        # Test 2: Check specific degradation types
        logger.info("Test 2: Specific degradation type detection")
        
        # Test P95 wait time degradation
        p95_degraded = alerts_service._check_p95_wait_time_degradation(monitoring_data)
        logger.info(f"P95 wait time degradation: {p95_degraded}")
        assert p95_degraded, "Should detect P95 wait time degradation"
        
        # Test high fallback usage
        fallback_degraded = alerts_service._check_high_fallback_usage(monitoring_data)
        logger.info(f"High fallback usage: {fallback_degraded}")
        assert fallback_degraded, "Should detect high fallback usage"
        
        # Test low success rate
        success_degraded = alerts_service._check_low_success_rate(monitoring_data)
        logger.info(f"Low success rate: {success_degraded}")
        assert success_degraded, "Should detect low success rate"
        
        # Test high timeout rate
        timeout_degraded = alerts_service._check_high_timeout_rate(monitoring_data)
        logger.info(f"High timeout rate: {timeout_degraded}")
        assert timeout_degraded, "Should detect high timeout rate"
        
        # Test high abandonment rate
        abandonment_degraded = alerts_service._check_high_abandonment_rate(monitoring_data)
        logger.info(f"High abandonment rate: {abandonment_degraded}")
        assert abandonment_degraded, "Should detect high abandonment rate"
        
        # Test essential capability unavailable
        capability_degraded = alerts_service._check_essential_capability_unavailable(monitoring_data)
        logger.info(f"Essential capability unavailable: {capability_degraded}")
        assert capability_degraded, "Should detect essential capability unavailable"
        
        # Test 3: User experience score calculation
        logger.info("Test 3: User experience score calculation")
        
        ux_score = alerts_service._calculate_user_experience_score(metrics_collector.user_metrics)
        logger.info(f"User experience score: {ux_score:.1f}/100")
        assert 0 <= ux_score <= 100, "UX score should be between 0 and 100"
        assert ux_score < 50, "UX score should be low due to multiple issues"
        
        # Test 4: Degradation factors identification
        logger.info("Test 4: Degradation factors identification")
        
        factors = alerts_service._identify_degradation_factors(metrics_collector.user_metrics, monitoring_data)
        logger.info(f"Degradation factors: {factors}")
        assert len(factors) > 0, "Should identify multiple degradation factors"
        assert any("wait time" in factor.lower() for factor in factors), "Should identify wait time issues"
        assert any("success rate" in factor.lower() for factor in factors), "Should identify success rate issues"
        
        # Test 5: Alert creation for UX degradation
        logger.info("Test 5: UX degradation alert creation")
        
        await alerts_service.record_user_experience_degradation(
            degradation_type="high_wait_time",
            severity="high",
            user_metrics=metrics_collector.user_metrics,
            context={"test": "user_experience_alerts"}
        )
        
        # Wait a moment for alert processing
        await asyncio.sleep(0.1)
        
        # Test 6: UX summary generation
        logger.info("Test 6: User experience summary")
        
        ux_summary = alerts_service.get_user_experience_summary()
        logger.info(f"UX summary: {ux_summary}")
        assert "ux_health_score" in ux_summary, "Should include UX health score"
        assert "recommendations" in ux_summary, "Should include recommendations"
        
        # Test 7: Alert rule configuration
        logger.info("Test 7: Alert rule configuration")
        
        # Check that UX alert rules are properly configured
        ux_rules = [
            rule_id for rule_id, rule in alerts_service.alert_rules.items()
            if rule.alert_type == AlertType.USER_EXPERIENCE_DEGRADATION
        ]
        
        logger.info(f"UX alert rules configured: {ux_rules}")
        expected_rules = [
            "user_experience_degradation",
            "user_p95_wait_time_degradation", 
            "high_fallback_usage",
            "low_user_success_rate",
            "high_timeout_rate",
            "high_abandonment_rate",
            "essential_capability_unavailable"
        ]
        
        for expected_rule in expected_rules:
            assert expected_rule in ux_rules, f"Should have {expected_rule} rule configured"
        
        # Test 8: Threshold configuration
        logger.info("Test 8: Threshold configuration")
        
        # Check that UX thresholds are properly configured
        ux_thresholds = [
            "user_wait_time_threshold",
            "user_p95_wait_time_threshold",
            "high_fallback_usage_threshold",
            "low_success_rate_threshold",
            "high_timeout_rate_threshold",
            "high_abandonment_rate_threshold",
            "essential_capability_unavailable_threshold"
        ]
        
        for threshold_name in ux_thresholds:
            assert threshold_name in alerts_service.default_thresholds, f"Should have {threshold_name} configured"
            threshold = alerts_service.default_thresholds[threshold_name]
            assert threshold.threshold_value > 0, f"{threshold_name} should have positive threshold value"
            assert threshold.remediation_steps, f"{threshold_name} should have remediation steps"
        
        logger.info("✅ All user experience degradation alert tests passed!")
        
        return {
            "test_passed": True,
            "ux_degradation_detected": ux_degraded,
            "ux_score": ux_score,
            "degradation_factors_count": len(factors),
            "ux_rules_configured": len(ux_rules),
            "thresholds_configured": len(ux_thresholds),
            "summary": "User experience degradation alerts are working correctly"
        }
        
    except Exception as e:
        logger.error(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return {
            "test_passed": False,
            "error": str(e),
            "summary": "User experience degradation alert test failed"
        }

async def test_ux_alert_scenarios():
    """Test specific UX alert scenarios."""
    
    logger.info("Testing specific UX alert scenarios")
    
    try:
        from src.multimodal_librarian.monitoring.startup_alerts import StartupAlertsService
        
        # Create test scenarios
        scenarios = [
            {
                "name": "High Wait Time Scenario",
                "user_metrics": {
                    "wait_time_stats": {"mean_seconds": 45.0, "p95_seconds": 30.0},
                    "success_rate": 0.95,
                    "fallback_usage_rate": 0.2,
                    "timeout_rate": 0.02,
                    "abandonment_rate": 0.05,
                    "total_requests": 20,
                    "capability_availability": {"chat-model-base": True, "search-model": True}
                },
                "expected_degradation": True,
                "expected_factors": ["wait time"]
            },
            {
                "name": "Low Success Rate Scenario", 
                "user_metrics": {
                    "wait_time_stats": {"mean_seconds": 15.0, "p95_seconds": 25.0},
                    "success_rate": 0.65,
                    "fallback_usage_rate": 0.3,
                    "timeout_rate": 0.05,
                    "abandonment_rate": 0.1,
                    "total_requests": 30,
                    "capability_availability": {"chat-model-base": True, "search-model": True}
                },
                "expected_degradation": True,
                "expected_factors": ["success rate"]
            },
            {
                "name": "Good UX Scenario",
                "user_metrics": {
                    "wait_time_stats": {"mean_seconds": 8.0, "p95_seconds": 15.0},
                    "success_rate": 0.98,
                    "fallback_usage_rate": 0.1,
                    "timeout_rate": 0.01,
                    "abandonment_rate": 0.02,
                    "total_requests": 25,
                    "capability_availability": {"chat-model-base": True, "search-model": True, "embedding-model": True}
                },
                "expected_degradation": False,
                "expected_factors": []
            }
        ]
        
        phase_manager = MockStartupPhaseManager()
        metrics_collector = MockStartupMetricsCollector()
        alerts_service = StartupAlertsService(phase_manager, metrics_collector)
        
        results = []
        
        for scenario in scenarios:
            logger.info(f"Testing scenario: {scenario['name']}")
            
            # Update metrics collector with scenario data
            metrics_collector.user_metrics = scenario["user_metrics"]
            
            monitoring_data = {
                "timestamp": datetime.now(),
                "phase_manager_status": phase_manager.get_current_status(),
                "metrics_summary": {
                    "user_experience": scenario["user_metrics"],
                    "active_requests": {},
                    "model_loading": {"success_rate": 0.8},
                    "cache_performance": {"cache_hit_rate": 0.7}
                },
                "health_status": {"consecutive_failures": 0}
            }
            
            # Test degradation detection
            degradation_detected = alerts_service._check_user_experience_degradation(monitoring_data)
            
            # Calculate UX score
            ux_score = alerts_service._calculate_user_experience_score(scenario["user_metrics"])
            
            # Identify factors
            factors = alerts_service._identify_degradation_factors(scenario["user_metrics"], monitoring_data)
            
            result = {
                "scenario": scenario["name"],
                "degradation_detected": degradation_detected,
                "expected_degradation": scenario["expected_degradation"],
                "ux_score": ux_score,
                "factors": factors,
                "test_passed": degradation_detected == scenario["expected_degradation"]
            }
            
            results.append(result)
            
            logger.info(f"  Degradation detected: {degradation_detected} (expected: {scenario['expected_degradation']})")
            logger.info(f"  UX score: {ux_score:.1f}")
            logger.info(f"  Factors: {factors}")
            logger.info(f"  Test passed: {result['test_passed']}")
        
        all_passed = all(result["test_passed"] for result in results)
        
        if all_passed:
            logger.info("✅ All UX alert scenarios passed!")
        else:
            logger.error("❌ Some UX alert scenarios failed!")
        
        return {
            "test_passed": all_passed,
            "scenarios_tested": len(scenarios),
            "scenarios_passed": sum(1 for r in results if r["test_passed"]),
            "results": results,
            "summary": f"UX alert scenarios: {sum(1 for r in results if r['test_passed'])}/{len(scenarios)} passed"
        }
        
    except Exception as e:
        logger.error(f"❌ UX scenario test failed: {e}")
        import traceback
        traceback.print_exc()
        return {
            "test_passed": False,
            "error": str(e),
            "summary": "UX alert scenario test failed"
        }

async def main():
    """Run all user experience degradation alert tests."""
    
    logger.info("🚀 Starting User Experience Degradation Alert Tests")
    
    # Run basic functionality tests
    basic_results = await test_user_experience_degradation_alerts()
    
    # Run scenario tests
    scenario_results = await test_ux_alert_scenarios()
    
    # Summary
    logger.info("\n" + "="*60)
    logger.info("TEST SUMMARY")
    logger.info("="*60)
    logger.info(f"Basic functionality: {'✅ PASSED' if basic_results['test_passed'] else '❌ FAILED'}")
    logger.info(f"Scenario tests: {'✅ PASSED' if scenario_results['test_passed'] else '❌ FAILED'}")
    
    overall_success = basic_results["test_passed"] and scenario_results["test_passed"]
    logger.info(f"Overall result: {'✅ ALL TESTS PASSED' if overall_success else '❌ SOME TESTS FAILED'}")
    
    return {
        "overall_success": overall_success,
        "basic_tests": basic_results,
        "scenario_tests": scenario_results,
        "summary": "User experience degradation alerts implementation complete and tested"
    }

if __name__ == "__main__":
    asyncio.run(main())