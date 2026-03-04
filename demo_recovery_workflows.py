#!/usr/bin/env python3
"""
Recovery Workflows Demonstration Script

This script demonstrates the recovery workflow system including:
- Automatic service restoration
- Recovery validation
- Recovery notifications
"""

import asyncio
import json
from datetime import datetime
from typing import Dict, Any

from src.multimodal_librarian.monitoring.recovery_workflow_manager import (
    get_recovery_workflow_manager,
    RecoveryPriority
)
from src.multimodal_librarian.monitoring.recovery_notification_service import (
    get_recovery_notification_service,
    RecoveryNotificationType,
    RecoveryNotificationPriority
)
from src.multimodal_librarian.monitoring.recovery_integration import (
    get_recovery_integration_service,
    trigger_manual_recovery
)
from src.multimodal_librarian.monitoring.service_health_monitor import HealthStatus
from src.multimodal_librarian.monitoring.error_logging_service import ErrorCategory


async def demonstrate_recovery_workflows():
    """Demonstrate the complete recovery workflow system."""
    
    print("=" * 80)
    print("RECOVERY WORKFLOWS DEMONSTRATION")
    print("=" * 80)
    print()
    
    # Initialize services
    print("1. Initializing Recovery Services...")
    recovery_manager = get_recovery_workflow_manager()
    notification_service = get_recovery_notification_service()
    integration_service = get_recovery_integration_service()
    
    print(f"   ✓ Recovery Manager: {len(recovery_manager._workflows)} workflows registered")
    print(f"   ✓ Notification Service: {len(notification_service._notification_rules)} rules configured")
    print(f"   ✓ Integration Service: {len(integration_service._trigger_conditions)} triggers active")
    print()
    
    # Demonstrate manual recovery trigger
    print("2. Demonstrating Manual Recovery Trigger...")
    print("   Triggering recovery for 'database' service...")
    
    attempt_ids = await trigger_manual_recovery(
        service_name="database",
        reason="Demonstration of manual recovery trigger",
        priority=RecoveryPriority.HIGH
    )
    
    if attempt_ids:
        print(f"   ✓ Recovery triggered successfully: {len(attempt_ids)} attempts started")
        for attempt_id in attempt_ids:
            print(f"     - Attempt ID: {attempt_id}")
    else:
        print("   ⚠ No recovery workflows were triggered")
    
    print()
    
    # Wait for recovery to complete
    print("3. Waiting for Recovery Completion...")
    await asyncio.sleep(2)  # Give time for recovery to complete
    
    # Check recovery statistics
    print("4. Recovery Statistics:")
    stats = recovery_manager.get_recovery_statistics()
    
    overall_stats = stats.get("overall_statistics", {})
    print(f"   Total Attempts: {overall_stats.get('total_attempts', 0)}")
    print(f"   Successful Attempts: {overall_stats.get('successful_attempts', 0)}")
    print(f"   Success Rate: {overall_stats.get('success_rate', 0):.1f}%")
    print(f"   Active Workflows: {overall_stats.get('active_workflows', 0)}")
    print()
    
    # Show workflow details
    print("5. Available Recovery Workflows:")
    for workflow_id in recovery_manager._workflows.keys():
        workflow_details = recovery_manager.get_workflow_details(workflow_id)
        if workflow_details:
            print(f"   • {workflow_details['name']}")
            print(f"     Service: {workflow_details['service_name']}")
            print(f"     Priority: {workflow_details['priority']}")
            print(f"     Actions: {len(workflow_details['actions'])}")
    print()
    
    # Demonstrate notification system
    print("6. Demonstrating Recovery Notifications...")
    
    # Send test notifications
    notification_id = await notification_service.send_recovery_notification(
        notification_type=RecoveryNotificationType.RECOVERY_SUCCESS,
        service_name="database",
        workflow_id="demo_workflow",
        attempt_id="demo_attempt",
        title="Demo Recovery Completed",
        message="This is a demonstration of the recovery notification system",
        priority=RecoveryNotificationPriority.MEDIUM
    )
    
    print(f"   ✓ Notification sent: {notification_id}")
    
    # Show notification statistics
    notification_stats = notification_service.get_notification_statistics()
    print(f"   Total Notifications: {notification_stats.get('total_notifications', 0)}")
    print(f"   Active Notifications: {notification_stats.get('active_notifications', 0)}")
    print()
    
    # Show integration status
    print("7. Integration Service Status:")
    integration_status = integration_service.get_integration_status()
    print(f"   Integration Active: {integration_status.get('integration_active', False)}")
    print(f"   Registered Triggers: {integration_status.get('registered_triggers', 0)}")
    print(f"   Active Cooldowns: {integration_status.get('active_cooldowns', 0)}")
    print()
    
    # Show recovery history
    print("8. Recent Recovery History:")
    history = recovery_manager.get_recovery_history(hours=1)
    
    if history:
        for attempt in history[:3]:  # Show last 3 attempts
            print(f"   • Attempt: {attempt['attempt_id'][:8]}...")
            print(f"     Service: {attempt['service_name']}")
            print(f"     Status: {attempt['status']}")
            print(f"     Duration: {attempt.get('duration_seconds', 0):.1f}s")
            print(f"     Actions: {attempt['actions_executed']}")
    else:
        print("   No recent recovery attempts found")
    
    print()
    
    # Demonstrate health status integration
    print("9. Health Status Integration:")
    print("   Simulating health status change...")
    
    # This would normally be triggered by the health monitoring system
    await integration_service._handle_health_status_change("search_service", HealthStatus.DEGRADED)
    print("   ✓ Health status change processed")
    print()
    
    # Show comprehensive metrics
    print("10. Comprehensive Recovery Metrics:")
    metrics = integration_service.get_recovery_metrics()
    
    # Recovery workflows metrics
    recovery_metrics = metrics.get("recovery_workflows", {})
    overall = recovery_metrics.get("overall_statistics", {})
    print(f"    Recovery Success Rate: {overall.get('success_rate', 0):.1f}%")
    
    # Notification metrics
    notification_metrics = metrics.get("recovery_notifications", {})
    ack_stats = notification_metrics.get("acknowledgment_statistics", {})
    print(f"    Notification Acknowledgment Rate: {ack_stats.get('acknowledgment_rate', 0):.1f}%")
    
    # Integration metrics
    integration_metrics = metrics.get("integration_status", {})
    print(f"    Integration Triggers: {integration_metrics.get('registered_triggers', 0)}")
    print()
    
    print("=" * 80)
    print("RECOVERY WORKFLOWS DEMONSTRATION COMPLETED")
    print("=" * 80)
    print()
    print("Key Features Demonstrated:")
    print("✓ Automatic service restoration workflows")
    print("✓ Recovery validation and verification")
    print("✓ Recovery notifications and alerting")
    print("✓ Integration with health monitoring")
    print("✓ Manual recovery triggering")
    print("✓ Comprehensive metrics and statistics")
    print("✓ Recovery attempt tracking and history")
    print()


def save_demo_results():
    """Save demonstration results to file."""
    
    # Get current state of all services
    recovery_manager = get_recovery_workflow_manager()
    notification_service = get_recovery_notification_service()
    integration_service = get_recovery_integration_service()
    
    demo_results = {
        "timestamp": datetime.now().isoformat(),
        "recovery_statistics": recovery_manager.get_recovery_statistics(),
        "notification_statistics": notification_service.get_notification_statistics(),
        "integration_status": integration_service.get_integration_status(),
        "recovery_history": recovery_manager.get_recovery_history(hours=1),
        "notification_history": notification_service.get_notification_history(hours=1),
        "available_workflows": [
            recovery_manager.get_workflow_details(workflow_id)
            for workflow_id in recovery_manager._workflows.keys()
        ]
    }
    
    filename = f"recovery_workflows_demo_results_{int(datetime.now().timestamp())}.json"
    
    with open(filename, 'w') as f:
        json.dump(demo_results, f, indent=2, default=str)
    
    print(f"Demo results saved to: {filename}")
    return filename


async def main():
    """Main demonstration function."""
    try:
        await demonstrate_recovery_workflows()
        save_demo_results()
        
    except Exception as e:
        print(f"Error during demonstration: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())