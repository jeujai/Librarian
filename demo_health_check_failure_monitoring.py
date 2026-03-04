#!/usr/bin/env python3
"""
Health Check Failure Monitoring Demo

This demo shows the health check failure monitoring system in action,
including failure detection, alerting, and integration with health endpoints.
"""

import asyncio
import time
from datetime import datetime
from unittest.mock import Mock

async def demo_health_check_failure_monitoring():
    """Demonstrate the health check failure monitoring system."""
    
    print("🏥 Health Check Failure Monitoring Demo")
    print("=" * 50)
    
    # Import required modules
    from src.multimodal_librarian.monitoring.startup_alerts import StartupAlertsService, create_log_notification_handler
    from src.multimodal_librarian.startup.phase_manager import StartupPhaseManager
    from src.multimodal_librarian.monitoring.startup_metrics import StartupMetricsCollector
    from src.multimodal_librarian.api.routers.health import set_startup_alerts_service
    
    # Create mock dependencies
    print("📋 Setting up monitoring system...")
    phase_manager = Mock(spec=StartupPhaseManager)
    metrics_collector = Mock(spec=StartupMetricsCollector)
    
    # Initialize the alerts service
    alerts_service = StartupAlertsService(phase_manager, metrics_collector)
    
    # Add a notification handler to see alerts
    log_handler = create_log_notification_handler()
    alerts_service.add_notification_handler(log_handler)
    
    # Set up health endpoint integration
    set_startup_alerts_service(alerts_service)
    
    # Start monitoring
    await alerts_service.start_monitoring()
    print("✅ Monitoring system started")
    
    print("\n🔍 Demonstrating Health Check Monitoring...")
    
    # 1. Show successful health checks
    print("\n1️⃣ Recording successful health checks...")
    for i in range(3):
        await alerts_service.record_health_check_result(True, 100.0 + i * 10)
        print(f"   ✅ Health check {i+1}: SUCCESS (response time: {100 + i * 10}ms)")
        await asyncio.sleep(0.1)
    
    print(f"   📊 Consecutive failures: {alerts_service._consecutive_health_failures}")
    
    # 2. Show health check failures building up
    print("\n2️⃣ Recording health check failures...")
    threshold = int(alerts_service.default_thresholds["health_check_failure_threshold"].threshold_value)
    
    for i in range(threshold + 1):
        await alerts_service.record_health_check_result(False, 5000.0 + i * 1000)
        print(f"   ❌ Health check failure {i+1}: FAILED (response time: {5000 + i * 1000}ms)")
        print(f"   📊 Consecutive failures: {alerts_service._consecutive_health_failures}")
        
        if alerts_service._consecutive_health_failures >= threshold:
            print("   🚨 ALERT THRESHOLD REACHED!")
        
        await asyncio.sleep(0.2)
    
    # 3. Show alert status
    print("\n3️⃣ Checking alert status...")
    active_alerts = alerts_service.get_active_alerts()
    print(f"   📊 Active alerts: {len(active_alerts)}")
    
    for alert in active_alerts:
        if alert.alert_type.value == "health_check_failure":
            print(f"   🚨 Health Check Alert: {alert.title}")
            print(f"      Severity: {alert.severity.value}")
            print(f"      Description: {alert.description}")
            print(f"      Remediation steps: {len(alert.remediation_steps)} steps")
    
    # 4. Show health check summary
    print("\n4️⃣ Health Check Status Summary...")
    summary = alerts_service.get_alert_summary()
    print(f"   📊 Total active alerts: {summary['active_alerts']}")
    print(f"   📊 Alerts in last 24h: {summary['alerts_last_24h']}")
    print(f"   📊 Monitoring active: {summary['monitoring_active']}")
    print(f"   📊 Rules enabled: {summary['rules_enabled']}/{summary['total_rules']}")
    
    # 5. Show recovery
    print("\n5️⃣ Demonstrating recovery...")
    print("   Recording successful health check to reset failures...")
    await alerts_service.record_health_check_result(True, 150.0)
    print(f"   ✅ Health check: SUCCESS (response time: 150ms)")
    print(f"   📊 Consecutive failures reset to: {alerts_service._consecutive_health_failures}")
    
    # 6. Show health check performance tracking
    print("\n6️⃣ Health Check Performance Tracking...")
    print("   Recording various response times...")
    
    response_times = [50, 100, 200, 500, 1000, 2000, 5000]
    for rt in response_times:
        success = rt < 3000  # Consider anything over 3s as failure
        await alerts_service.record_health_check_result(success, rt)
        status = "SUCCESS" if success else "TIMEOUT"
        print(f"   {'✅' if success else '⏰'} Health check: {status} (response time: {rt}ms)")
        await asyncio.sleep(0.1)
    
    print(f"   📊 Final consecutive failures: {alerts_service._consecutive_health_failures}")
    
    # 7. Show remediation recommendations
    print("\n7️⃣ Remediation Recommendations...")
    threshold_config = alerts_service.default_thresholds["health_check_failure_threshold"]
    print("   When health checks fail, the system recommends:")
    for i, step in enumerate(threshold_config.remediation_steps, 1):
        print(f"   {i}. {step}")
    
    # Stop monitoring
    await alerts_service.stop_monitoring()
    print("\n✅ Monitoring system stopped")
    
    print("\n" + "=" * 50)
    print("🎯 Demo Summary:")
    print("  • Health check results are tracked and monitored")
    print("  • Consecutive failures trigger alerts when threshold is reached")
    print("  • Response times are recorded for performance analysis")
    print("  • Successful checks reset the failure counter")
    print("  • Alerts include detailed remediation steps")
    print("  • Integration with health endpoints provides monitoring data")


async def demo_health_endpoint_integration():
    """Demonstrate health endpoint integration with failure monitoring."""
    
    print("\n🌐 Health Endpoint Integration Demo")
    print("=" * 50)
    
    from fastapi.testclient import TestClient
    from src.multimodal_librarian.api.routers.health import router
    from src.multimodal_librarian.api.routers.health import set_startup_alerts_service
    from src.multimodal_librarian.monitoring.startup_alerts import StartupAlertsService
    from src.multimodal_librarian.startup.phase_manager import StartupPhaseManager
    from src.multimodal_librarian.monitoring.startup_metrics import StartupMetricsCollector
    from fastapi import FastAPI
    from unittest.mock import Mock
    
    # Create test app
    app = FastAPI()
    app.include_router(router)
    
    # Create mock dependencies
    phase_manager = Mock(spec=StartupPhaseManager)
    metrics_collector = Mock(spec=StartupMetricsCollector)
    
    # Initialize the alerts service
    alerts_service = StartupAlertsService(phase_manager, metrics_collector)
    set_startup_alerts_service(alerts_service)
    
    # Create test client
    client = TestClient(app)
    
    print("📋 Testing health endpoint integration...")
    
    # 1. Test alerts endpoint
    print("\n1️⃣ Testing /api/health/alerts endpoint...")
    response = client.get("/api/health/alerts")
    print(f"   Status: {response.status_code}")
    
    if response.status_code == 200:
        data = response.json()
        print(f"   ✅ Health check status available")
        print(f"   📊 Consecutive failures: {data['health_check_status']['consecutive_failures']}")
        print(f"   📊 Failure threshold: {data['health_check_status']['failure_threshold']}")
        print(f"   📊 Monitoring active: {data['health_check_status']['monitoring_active']}")
    
    # 2. Test alerts summary endpoint
    print("\n2️⃣ Testing /api/health/alerts/summary endpoint...")
    response = client.get("/api/health/alerts/summary")
    print(f"   Status: {response.status_code}")
    
    if response.status_code == 200:
        data = response.json()
        print(f"   ✅ Health summary available")
        print(f"   📊 Health score: {data['health_score']}")
        print(f"   📊 Health grade: {data['health_grade']}")
        print(f"   📊 Trend: {data['trend']}")
    
    # 3. Test failure simulation
    print("\n3️⃣ Testing health check failure simulation...")
    response = client.post("/api/health/alerts/test")
    print(f"   Status: {response.status_code}")
    
    if response.status_code == 200:
        data = response.json()
        print(f"   ✅ Test failure recorded")
        print(f"   📊 Consecutive failures: {data['consecutive_failures']}")
        print(f"   📊 Alert triggered: {data['alert_triggered']}")
    
    # 4. Test failure reset
    print("\n4️⃣ Testing health check failure reset...")
    response = client.post("/api/health/alerts/reset")
    print(f"   Status: {response.status_code}")
    
    if response.status_code == 200:
        data = response.json()
        print(f"   ✅ Failures reset")
        print(f"   📊 Consecutive failures: {data['consecutive_failures']}")
    
    print("\n✅ Health endpoint integration demo completed")


async def main():
    """Run the complete health check failure monitoring demo."""
    
    print("🚀 Starting Health Check Failure Monitoring Demo")
    print("=" * 60)
    
    try:
        await demo_health_check_failure_monitoring()
        await demo_health_endpoint_integration()
        
        print("\n" + "=" * 60)
        print("🎉 Health Check Failure Monitoring Demo Completed Successfully!")
        print("\n📋 Key Features Demonstrated:")
        print("  ✅ Health check result tracking and monitoring")
        print("  ✅ Consecutive failure counting and threshold detection")
        print("  ✅ Alert triggering when failure thresholds are exceeded")
        print("  ✅ Response time tracking for performance analysis")
        print("  ✅ Automatic failure counter reset on successful checks")
        print("  ✅ Detailed remediation steps for troubleshooting")
        print("  ✅ Integration with health API endpoints")
        print("  ✅ Real-time monitoring and alerting capabilities")
        
        return True
        
    except Exception as e:
        print(f"❌ Demo failed: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    # Run the demo
    success = asyncio.run(main())
    exit(0 if success else 1)