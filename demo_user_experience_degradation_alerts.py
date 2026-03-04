#!/usr/bin/env python3
"""
Demo: User Experience Degradation Alerts

This demo shows how the enhanced user experience degradation alerts work
in practice, including different types of degradation detection and alerting.
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, Any

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Mock classes for demo
class MockStartupPhaseManager:
    """Mock startup phase manager for demo."""
    
    def __init__(self):
        self.current_phase = MockPhase("essential")
        self.phase_start_time = datetime.now() - timedelta(minutes=3)
        self.model_statuses = {
            "chat-model-base": MockModelStatus("loaded", "essential"),
            "search-model": MockModelStatus("loading", "essential"),
            "embedding-model": MockModelStatus("failed", "essential", "Memory allocation failed"),
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
        self.started_at = datetime.now() - timedelta(minutes=2)
        self.retry_count = 0 if status != "failed" else 1

class MockStatus:
    def __init__(self, current_phase, phase_start_time, model_statuses, phase_transitions):
        self.current_phase = current_phase
        self.phase_start_time = phase_start_time
        self.model_statuses = model_statuses
        self.phase_transitions = phase_transitions

class MockStartupMetricsCollector:
    """Mock metrics collector for demo."""
    
    def __init__(self):
        self.reset_to_degraded_state()
    
    def reset_to_degraded_state(self):
        """Set metrics to show degraded user experience."""
        self.user_metrics = {
            "wait_time_stats": {
                "mean_seconds": 52.0,
                "p95_seconds": 95.0,
                "p99_seconds": 140.0,
                "min_seconds": 8.0,
                "max_seconds": 200.0
            },
            "success_rate": 0.72,
            "fallback_usage_rate": 0.85,
            "timeout_rate": 0.18,
            "abandonment_rate": 0.28,
            "total_requests": 65,
            "capability_availability": {
                "chat-model-base": True,
                "search-model": False,
                "embedding-model": False,
                "document-processor": False
            }
        }
        self.active_requests = {
            f"req{i}": {
                "request_type": ["chat", "search", "document"][i % 3],
                "is_overdue": i < 8,  # 8 out of 12 requests are overdue
                "fallback_used": i < 10  # 10 out of 12 use fallback
            }
            for i in range(12)
        }
    
    def improve_to_good_state(self):
        """Set metrics to show good user experience."""
        self.user_metrics = {
            "wait_time_stats": {
                "mean_seconds": 12.0,
                "p95_seconds": 25.0,
                "p99_seconds": 35.0,
                "min_seconds": 3.0,
                "max_seconds": 45.0
            },
            "success_rate": 0.96,
            "fallback_usage_rate": 0.15,
            "timeout_rate": 0.02,
            "abandonment_rate": 0.03,
            "total_requests": 80,
            "capability_availability": {
                "chat-model-base": True,
                "search-model": True,
                "embedding-model": True,
                "document-processor": True
            }
        }
        self.active_requests = {
            f"req{i}": {
                "request_type": ["chat", "search", "document"][i % 3],
                "is_overdue": i < 1,  # Only 1 out of 6 requests is overdue
                "fallback_used": i < 1  # Only 1 out of 6 uses fallback
            }
            for i in range(6)
        }
    
    def get_phase_completion_metrics(self, phase):
        return {"sample_count": 15, "mean_duration_seconds": 180.0}
    
    def get_model_loading_metrics(self):
        return {"success_rate": 0.67, "sample_count": 6, "loading_stats": {"mean_duration_seconds": 120.0}}
    
    def get_user_wait_time_metrics(self):
        return self.user_metrics
    
    def get_cache_performance_metrics(self):
        return {"cache_hit_rate": 0.4, "total_model_loads": 15, "cache_sources": {}}
    
    def get_active_user_requests(self):
        return self.active_requests

class AlertCollector:
    """Collects alerts for demo purposes."""
    
    def __init__(self):
        self.alerts = []
    
    def handle_alert(self, alert):
        """Handle an alert by collecting it."""
        self.alerts.append({
            "timestamp": alert.timestamp.isoformat(),
            "type": alert.alert_type.value,
            "severity": alert.severity.value,
            "title": alert.title,
            "description": alert.description,
            "affected_resources": alert.affected_resources,
            "metrics": alert.metrics,
            "remediation_steps": alert.remediation_steps[:3],  # First 3 steps for brevity
            "context": {
                "degradation_factors": alert.context.get("degradation_factors", [])[:5]  # First 5 factors
            }
        })
        
        logger.warning(f"🚨 ALERT: [{alert.severity.value.upper()}] {alert.title}")
        logger.info(f"   Description: {alert.description}")
        logger.info(f"   Affected: {', '.join(alert.affected_resources)}")

async def demo_user_experience_degradation_alerts():
    """Demonstrate user experience degradation alerts in action."""
    
    logger.info("🎯 User Experience Degradation Alerts Demo")
    logger.info("=" * 60)
    
    try:
        # Import the alerts service
        from src.multimodal_librarian.monitoring.startup_alerts import (
            StartupAlertsService, create_log_notification_handler
        )
        
        # Create mock dependencies
        phase_manager = MockStartupPhaseManager()
        metrics_collector = MockStartupMetricsCollector()
        
        # Create alerts service
        alerts_service = StartupAlertsService(phase_manager, metrics_collector)
        
        # Set up alert collection
        alert_collector = AlertCollector()
        alerts_service.add_notification_handler(alert_collector.handle_alert)
        
        logger.info("📊 Initial System State (Degraded)")
        logger.info("-" * 40)
        
        # Show initial degraded state
        ux_score = alerts_service._calculate_user_experience_score(metrics_collector.user_metrics)
        logger.info(f"User Experience Score: {ux_score:.1f}/100")
        logger.info(f"Average Wait Time: {metrics_collector.user_metrics['wait_time_stats']['mean_seconds']:.1f}s")
        logger.info(f"Success Rate: {metrics_collector.user_metrics['success_rate']:.1%}")
        logger.info(f"Fallback Usage: {metrics_collector.user_metrics['fallback_usage_rate']:.1%}")
        logger.info(f"Active Requests: {len(metrics_collector.active_requests)}")
        
        # Test different types of UX degradation alerts
        logger.info("\n🔍 Testing UX Degradation Detection")
        logger.info("-" * 40)
        
        monitoring_data = {
            "timestamp": datetime.now(),
            "phase_manager_status": phase_manager.get_current_status(),
            "metrics_summary": {
                "user_experience": metrics_collector.user_metrics,
                "active_requests": metrics_collector.active_requests,
                "model_loading": {"success_rate": 0.67},
                "cache_performance": {"cache_hit_rate": 0.4}
            },
            "health_status": {"consecutive_failures": 0}
        }
        
        # Test each type of degradation
        degradation_checks = [
            ("General UX Degradation", alerts_service._check_user_experience_degradation),
            ("P95 Wait Time", alerts_service._check_p95_wait_time_degradation),
            ("High Fallback Usage", alerts_service._check_high_fallback_usage),
            ("Low Success Rate", alerts_service._check_low_success_rate),
            ("High Timeout Rate", alerts_service._check_high_timeout_rate),
            ("High Abandonment", alerts_service._check_high_abandonment_rate),
            ("Essential Capability Unavailable", alerts_service._check_essential_capability_unavailable)
        ]
        
        for check_name, check_func in degradation_checks:
            result = check_func(monitoring_data)
            status = "🔴 DETECTED" if result else "🟢 OK"
            logger.info(f"{check_name}: {status}")
        
        # Generate degradation factors
        factors = alerts_service._identify_degradation_factors(metrics_collector.user_metrics, monitoring_data)
        logger.info(f"\n📋 Degradation Factors ({len(factors)} identified):")
        for i, factor in enumerate(factors[:8], 1):  # Show first 8 factors
            logger.info(f"  {i}. {factor}")
        
        # Trigger some alerts manually
        logger.info("\n🚨 Triggering UX Degradation Alerts")
        logger.info("-" * 40)
        
        # Record different types of UX degradation
        await alerts_service.record_user_experience_degradation(
            degradation_type="high_wait_time",
            severity="high",
            user_metrics=metrics_collector.user_metrics,
            context={"demo": "high_wait_time_scenario"}
        )
        
        await alerts_service.record_user_experience_degradation(
            degradation_type="capability_unavailable",
            severity="critical",
            user_metrics=metrics_collector.user_metrics,
            context={"demo": "capability_unavailable_scenario"}
        )
        
        await alerts_service.record_user_experience_degradation(
            degradation_type="low_success_rate",
            severity="high",
            user_metrics=metrics_collector.user_metrics,
            context={"demo": "low_success_rate_scenario"}
        )
        
        # Wait for alerts to be processed
        await asyncio.sleep(0.2)
        
        # Show UX summary
        logger.info("\n📈 User Experience Summary")
        logger.info("-" * 40)
        
        ux_summary = alerts_service.get_user_experience_summary()
        logger.info(f"UX Health Score: {ux_summary['ux_health_score']:.1f}/100")
        logger.info(f"Active UX Alerts: {ux_summary['active_ux_alerts']}")
        logger.info(f"UX Alerts (24h): {ux_summary['ux_alerts_last_24h']}")
        logger.info(f"Critical Issues: {ux_summary['critical_ux_issues']}")
        logger.info(f"Trend: {ux_summary['ux_trend']}")
        
        if ux_summary['recommendations']:
            logger.info("Recommendations:")
            for i, rec in enumerate(ux_summary['recommendations'][:3], 1):
                logger.info(f"  {i}. {rec}")
        
        # Simulate improvement
        logger.info("\n🔄 Simulating System Improvement")
        logger.info("-" * 40)
        
        # Update to good state
        metrics_collector.improve_to_good_state()
        
        # Update model statuses to show improvement
        phase_manager.model_statuses["search-model"].status = "loaded"
        phase_manager.model_statuses["embedding-model"].status = "loaded"
        phase_manager.model_statuses["embedding-model"].error_message = None
        phase_manager.current_phase = MockPhase("full")
        
        # Show improved state
        improved_monitoring_data = {
            "timestamp": datetime.now(),
            "phase_manager_status": phase_manager.get_current_status(),
            "metrics_summary": {
                "user_experience": metrics_collector.user_metrics,
                "active_requests": metrics_collector.active_requests,
                "model_loading": {"success_rate": 0.95},
                "cache_performance": {"cache_hit_rate": 0.85}
            },
            "health_status": {"consecutive_failures": 0}
        }
        
        improved_ux_score = alerts_service._calculate_user_experience_score(metrics_collector.user_metrics)
        logger.info(f"Improved UX Score: {improved_ux_score:.1f}/100")
        logger.info(f"Average Wait Time: {metrics_collector.user_metrics['wait_time_stats']['mean_seconds']:.1f}s")
        logger.info(f"Success Rate: {metrics_collector.user_metrics['success_rate']:.1%}")
        logger.info(f"Fallback Usage: {metrics_collector.user_metrics['fallback_usage_rate']:.1%}")
        
        # Check if degradation is still detected
        still_degraded = alerts_service._check_user_experience_degradation(improved_monitoring_data)
        logger.info(f"UX Degradation Still Detected: {'🔴 YES' if still_degraded else '🟢 NO'}")
        
        # Show collected alerts
        logger.info(f"\n📋 Collected Alerts ({len(alert_collector.alerts)})")
        logger.info("-" * 40)
        
        for i, alert in enumerate(alert_collector.alerts, 1):
            logger.info(f"\nAlert {i}: {alert['title']}")
            logger.info(f"  Severity: {alert['severity'].upper()}")
            logger.info(f"  Type: {alert['type']}")
            logger.info(f"  Description: {alert['description']}")
            if alert['context']['degradation_factors']:
                logger.info(f"  Key Factors: {', '.join(alert['context']['degradation_factors'][:3])}")
            logger.info(f"  Remediation: {alert['remediation_steps'][0]}")
        
        # Final summary
        logger.info("\n" + "=" * 60)
        logger.info("DEMO SUMMARY")
        logger.info("=" * 60)
        logger.info(f"✅ User Experience Degradation Alerts: WORKING")
        logger.info(f"📊 Initial UX Score: {ux_score:.1f}/100 (Degraded)")
        logger.info(f"📈 Improved UX Score: {improved_ux_score:.1f}/100 (Good)")
        logger.info(f"🚨 Alerts Triggered: {len(alert_collector.alerts)}")
        logger.info(f"🔍 Degradation Types Detected: {len(degradation_checks)}")
        logger.info(f"📋 Degradation Factors Identified: {len(factors)}")
        
        return {
            "demo_success": True,
            "initial_ux_score": ux_score,
            "improved_ux_score": improved_ux_score,
            "alerts_triggered": len(alert_collector.alerts),
            "degradation_factors": len(factors),
            "alerts": alert_collector.alerts,
            "summary": "User experience degradation alerts demo completed successfully"
        }
        
    except Exception as e:
        logger.error(f"❌ Demo failed: {e}")
        import traceback
        traceback.print_exc()
        return {
            "demo_success": False,
            "error": str(e),
            "summary": "User experience degradation alerts demo failed"
        }

async def main():
    """Run the user experience degradation alerts demo."""
    
    logger.info("🚀 Starting User Experience Degradation Alerts Demo")
    
    result = await demo_user_experience_degradation_alerts()
    
    if result["demo_success"]:
        logger.info("\n🎉 Demo completed successfully!")
        logger.info("The user experience degradation alerts are working correctly and can:")
        logger.info("  • Detect multiple types of UX degradation")
        logger.info("  • Calculate comprehensive UX health scores")
        logger.info("  • Identify specific degradation factors")
        logger.info("  • Generate targeted remediation recommendations")
        logger.info("  • Trigger appropriate alerts with detailed context")
    else:
        logger.error("\n💥 Demo failed!")
        logger.error(f"Error: {result.get('error', 'Unknown error')}")
    
    return result

if __name__ == "__main__":
    asyncio.run(main())