#!/usr/bin/env python3
"""
Demo: Enhanced Model Loading Failure Notifications

This demo shows the enhanced model loading failure notification system
with detailed error classification, remediation suggestions, and different
alert types for various failure scenarios.
"""

import asyncio
import sys
import os
import logging
import json
from datetime import datetime, timedelta

# Add the src directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from multimodal_librarian.startup.phase_manager import (
    StartupPhaseManager, StartupPhase, ModelLoadingStatus
)
from multimodal_librarian.monitoring.startup_metrics import StartupMetricsCollector
from multimodal_librarian.monitoring.startup_alerts import (
    StartupAlertsService, Alert, AlertType, AlertSeverity,
    create_log_notification_handler
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class DemoPhaseManager:
    """Demo phase manager with various model failure scenarios."""
    
    def __init__(self):
        self.current_phase = StartupPhase.ESSENTIAL
        self.phase_start_time = datetime.now() - timedelta(seconds=45)
        self.model_statuses = {}
        self.phase_transitions = []
        self._setup_demo_scenarios()
    
    def _setup_demo_scenarios(self):
        """Set up various model failure scenarios for demonstration."""
        
        # Scenario 1: Essential model failure (critical)
        essential_model = ModelLoadingStatus(
            model_name="text-embedding-essential",
            priority="essential",
            status="failed",
            started_at=datetime.now() - timedelta(seconds=90),
            error_message="CUDA out of memory: tried to allocate 2.5GB",
            size_mb=1024.0,
            estimated_load_time_seconds=30.0
        )
        setattr(essential_model, 'retry_count', 2)
        self.model_statuses["text-embedding-essential"] = essential_model
        
        # Scenario 2: Repeated failure model (high severity)
        repeated_model = ModelLoadingStatus(
            model_name="chat-model-large",
            priority="standard",
            status="failed",
            started_at=datetime.now() - timedelta(seconds=300),
            error_message="Network timeout: failed to download model from S3",
            size_mb=2048.0,
            estimated_load_time_seconds=120.0
        )
        setattr(repeated_model, 'retry_count', 5)
        self.model_statuses["chat-model-large"] = repeated_model
        
        # Scenario 3: Timeout model (medium severity)
        timeout_model = ModelLoadingStatus(
            model_name="multimodal-analyzer",
            priority="advanced",
            status="loading",
            started_at=datetime.now() - timedelta(seconds=400),  # > 5 minutes
            size_mb=3072.0,
            estimated_load_time_seconds=180.0
        )
        self.model_statuses["multimodal-analyzer"] = timeout_model
        
        # Scenario 4: Storage corruption failure
        corrupt_model = ModelLoadingStatus(
            model_name="document-processor",
            priority="standard",
            status="failed",
            started_at=datetime.now() - timedelta(seconds=60),
            error_message="Model file corrupted: checksum mismatch",
            size_mb=512.0,
            estimated_load_time_seconds=45.0
        )
        setattr(corrupt_model, 'retry_count', 1)
        self.model_statuses["document-processor"] = corrupt_model
        
        # Scenario 5: Configuration error
        config_model = ModelLoadingStatus(
            model_name="search-index",
            priority="essential",
            status="failed",
            started_at=datetime.now() - timedelta(seconds=30),
            error_message="Model path not found: /models/search-index-v2.bin",
            size_mb=256.0,
            estimated_load_time_seconds=15.0
        )
        setattr(config_model, 'retry_count', 0)
        self.model_statuses["search-index"] = config_model
        
        # Scenario 6: Successfully loaded models (for context)
        success_model = ModelLoadingStatus(
            model_name="text-classifier",
            priority="standard",
            status="loaded",
            started_at=datetime.now() - timedelta(seconds=45),
            completed_at=datetime.now() - timedelta(seconds=25),
            duration_seconds=20.0,
            size_mb=128.0
        )
        self.model_statuses["text-classifier"] = success_model
    
    def get_current_status(self):
        """Return demo status."""
        class DemoStatus:
            def __init__(self, manager):
                self.current_phase = manager.current_phase
                self.phase_start_time = manager.phase_start_time
                self.model_statuses = manager.model_statuses
                self.phase_transitions = manager.phase_transitions
        
        return DemoStatus(self)


class DemoMetricsCollector:
    """Demo metrics collector with realistic failure metrics."""
    
    def get_phase_completion_metrics(self, phase):
        return {"sample_count": 3, "success_rate": 0.67}
    
    def get_model_loading_metrics(self):
        return {
            "sample_count": 6,
            "success_rate": 0.33,  # Low success rate due to failures
            "loading_stats": {"mean_duration_seconds": 85.0}
        }
    
    def get_user_wait_time_metrics(self):
        return {
            "wait_time_stats": {"mean_seconds": 45.0, "p95_seconds": 120.0},
            "success_rate": 0.7,
            "fallback_usage_rate": 0.6
        }
    
    def get_cache_performance_metrics(self):
        return {
            "cache_hit_rate": 0.4,  # Low hit rate
            "cache_effectiveness": "poor",
            "total_model_loads": 15,
            "cache_speedup_factor": 2.1
        }
    
    def get_active_user_requests(self):
        return {
            "req_1": {"is_overdue": True, "wait_time": 60},
            "req_2": {"is_overdue": False, "wait_time": 15},
            "req_3": {"is_overdue": True, "wait_time": 90}
        }


async def demo_enhanced_notifications():
    """Demonstrate enhanced model loading failure notifications."""
    logger.info("🚀 Starting Enhanced Model Loading Failure Notifications Demo")
    logger.info("=" * 70)
    
    # Create demo components
    phase_manager = DemoPhaseManager()
    metrics_collector = DemoMetricsCollector()
    
    # Create alerts service with notification handler
    alerts_service = StartupAlertsService(phase_manager, metrics_collector)
    
    # Add a custom notification handler for demo
    def demo_notification_handler(alert: Alert):
        print(f"\n🚨 ALERT NOTIFICATION 🚨")
        print(f"Type: {alert.alert_type.value}")
        print(f"Severity: {alert.severity.value.upper()}")
        print(f"Title: {alert.title}")
        print(f"Description: {alert.description}")
        print(f"Affected Resources: {', '.join(alert.affected_resources)}")
        print(f"Remediation Steps:")
        for i, step in enumerate(alert.remediation_steps[:3], 1):  # Show first 3 steps
            print(f"  {i}. {step}")
        if len(alert.remediation_steps) > 3:
            print(f"  ... and {len(alert.remediation_steps) - 3} more steps")
        print("-" * 50)
    
    alerts_service.add_notification_handler(demo_notification_handler)
    alerts_service.add_notification_handler(create_log_notification_handler())
    
    # Start monitoring
    await alerts_service.start_monitoring()
    
    logger.info("📊 Current Model Status Summary:")
    summary = alerts_service.get_model_failure_summary()
    print(f"  Total Models: {summary['total_models']}")
    print(f"  Failed Models: {summary['failed_count']}")
    print(f"  Essential Failures: {summary['essential_failed_count']}")
    print(f"  Repeated Failures: {summary['repeated_failures_count']}")
    print(f"  Current Phase: {summary['current_phase']}")
    print()
    
    logger.info("🔍 Detailed Failure Analysis:")
    for model_name, details in summary['failure_details'].items():
        print(f"  {model_name}:")
        print(f"    Priority: {details['priority']}")
        print(f"    Error Type: {details['error_type']}")
        print(f"    Retry Count: {details['retry_count']}")
        print(f"    Error: {details['error_message']}")
        print()
    
    # Wait for alerts to be processed
    logger.info("⏳ Processing alerts (waiting 3 seconds)...")
    await asyncio.sleep(3.0)
    
    # Show active alerts
    active_alerts = alerts_service.get_active_alerts()
    logger.info(f"📋 Active Alerts: {len(active_alerts)}")
    
    for alert in active_alerts:
        print(f"\n  Alert ID: {alert.alert_id}")
        print(f"  Type: {alert.alert_type.value}")
        print(f"  Severity: {alert.severity.value}")
        print(f"  Title: {alert.title}")
        print(f"  Context: {json.dumps(alert.context, indent=2, default=str)}")
    
    # Demonstrate immediate alert recording
    logger.info("\n🔥 Demonstrating Immediate Alert Recording...")
    await alerts_service.record_model_loading_failure(
        "critical-new-model",
        "Essential model failed during startup - application cannot function",
        priority="essential",
        retry_count=0,
        context={"deployment_id": "demo-123", "node_id": "worker-01"}
    )
    
    # Wait for immediate alert to be processed
    await asyncio.sleep(1.0)
    
    # Show updated active alerts
    updated_alerts = alerts_service.get_active_alerts()
    logger.info(f"📋 Updated Active Alerts: {len(updated_alerts)}")
    
    # Show alert summary
    logger.info("\n📈 Alert Summary:")
    alert_summary = alerts_service.get_alert_summary()
    print(f"  Active Alerts: {alert_summary['active_alerts']}")
    print(f"  Alerts (24h): {alert_summary['alerts_last_24h']}")
    print(f"  Severity Breakdown: {alert_summary['severity_breakdown']}")
    print(f"  Type Breakdown: {alert_summary['type_breakdown']}")
    print(f"  Monitoring Active: {alert_summary['monitoring_active']}")
    print(f"  Rules Enabled: {alert_summary['rules_enabled']}/{alert_summary['total_rules']}")
    
    # Demonstrate error classification
    logger.info("\n🏷️  Error Classification Examples:")
    test_errors = [
        "CUDA out of memory: tried to allocate 2.5GB",
        "Network timeout: failed to download from S3",
        "Disk space full: cannot write to /tmp/models",
        "Model file corrupted: checksum mismatch",
        "Configuration error: model path not found"
    ]
    
    for error in test_errors:
        error_type = alerts_service._classify_model_error(error)
        print(f"  '{error}' → {error_type}")
    
    # Stop monitoring
    await alerts_service.stop_monitoring()
    
    logger.info("\n✅ Demo completed successfully!")
    logger.info("=" * 70)


if __name__ == "__main__":
    asyncio.run(demo_enhanced_notifications())