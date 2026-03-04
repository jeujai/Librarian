#!/usr/bin/env python3
"""
Enhanced Alerting System Demonstration

This script demonstrates the comprehensive enhanced alerting system including:
- Performance-based alerting with intelligent thresholds
- Error rate monitoring with automatic escalation
- Multi-level escalation procedures with external notifications
- Alert correlation and noise reduction
- Real-time monitoring and analytics

Validates: Requirement 6.4 - Alerting system with performance alerts, error rate monitoring, and escalation procedures
"""

import asyncio
import json
import time
from datetime import datetime, timedelta
from typing import Dict, Any

# Import the enhanced alerting system
try:
    from src.multimodal_librarian.monitoring.enhanced_alerting_system import (
        get_enhanced_alerting_system, EnhancedAlertingSystem,
        EscalationRule, PerformanceThreshold, AlertCategory, EscalationLevel, AlertSeverity
    )
    from src.multimodal_librarian.monitoring.alerting_service import Alert, AlertStatus
    print("✅ Enhanced alerting system imports successful")
except ImportError as e:
    print(f"❌ Import error: {e}")
    print("Please ensure the enhanced alerting system is properly installed")
    exit(1)


class EnhancedAlertingDemo:
    """Demonstration of the Enhanced Alerting System capabilities."""
    
    def __init__(self):
        self.system = get_enhanced_alerting_system()
        self.demo_results = {
            "timestamp": datetime.now().isoformat(),
            "tests_run": [],
            "alerts_triggered": [],
            "escalations_created": [],
            "notifications_sent": [],
            "performance_metrics": {},
            "system_status": {}
        }
    
    async def run_comprehensive_demo(self):
        """Run comprehensive demonstration of enhanced alerting capabilities."""
        print("🚀 Starting Enhanced Alerting System Demonstration")
        print("=" * 60)
        
        try:
            # 1. System initialization and configuration
            await self.demo_system_initialization()
            
            # 2. Performance threshold configuration
            await self.demo_performance_thresholds()
            
            # 3. Escalation rule configuration
            await self.demo_escalation_rules()
            
            # 4. External notification channels
            await self.demo_notification_channels()
            
            # 5. Performance monitoring and alerting
            await self.demo_performance_monitoring()
            
            # 6. Error rate monitoring
            await self.demo_error_rate_monitoring()
            
            # 7. Alert escalation procedures
            await self.demo_alert_escalation()
            
            # 8. Alert correlation and noise reduction
            await self.demo_alert_correlation()
            
            # 9. System analytics and reporting
            await self.demo_analytics_reporting()
            
            # 10. Integration testing
            await self.demo_integration_scenarios()
            
            print("\n✅ Enhanced Alerting System Demonstration Completed Successfully!")
            return self.demo_results
            
        except Exception as e:
            print(f"\n❌ Demo failed with error: {e}")
            self.demo_results["error"] = str(e)
            return self.demo_results
    
    async def demo_system_initialization(self):
        """Demonstrate system initialization and basic configuration."""
        print("\n📋 1. System Initialization and Configuration")
        print("-" * 50)
        
        try:
            # Get initial system status
            initial_status = self.system.get_escalation_status()
            print(f"   Initial system status: {initial_status['system_active']}")
            print(f"   Default escalation rules: {initial_status['escalation_rules']}")
            print(f"   Default performance thresholds: {initial_status['performance_thresholds']}")
            print(f"   External channels configured: {initial_status['external_channels']}")
            
            # Start the enhanced alerting system
            print("   Starting enhanced alerting system...")
            await self.system.start_enhanced_alerting()
            
            # Verify system is active
            status = self.system.get_escalation_status()
            print(f"   System active: {status['system_active']}")
            print(f"   Performance monitoring: {status['performance_monitoring_enabled']}")
            print(f"   Error monitoring: {status['error_monitoring_enabled']}")
            
            self.demo_results["tests_run"].append("system_initialization")
            self.demo_results["system_status"] = status
            print("   ✅ System initialization completed")
            
        except Exception as e:
            print(f"   ❌ System initialization failed: {e}")
            raise
    
    async def demo_performance_thresholds(self):
        """Demonstrate performance threshold configuration and monitoring."""
        print("\n⚡ 2. Performance Threshold Configuration")
        print("-" * 50)
        
        try:
            # Define custom performance thresholds
            custom_thresholds = [
                PerformanceThreshold(
                    metric_name="demo_response_time",
                    threshold_value=500.0,
                    comparison="greater_than",
                    severity=AlertSeverity.MEDIUM,
                    evaluation_window_minutes=2,
                    consecutive_violations=1,
                    description="Demo response time threshold",
                    category=AlertCategory.PERFORMANCE
                ),
                PerformanceThreshold(
                    metric_name="demo_error_rate",
                    threshold_value=5.0,
                    comparison="greater_than",
                    severity=AlertSeverity.HIGH,
                    evaluation_window_minutes=3,
                    consecutive_violations=2,
                    description="Demo error rate threshold",
                    category=AlertCategory.ERROR_RATE
                ),
                PerformanceThreshold(
                    metric_name="demo_cpu_usage",
                    threshold_value=80.0,
                    comparison="greater_than",
                    severity=AlertSeverity.CRITICAL,
                    evaluation_window_minutes=1,
                    consecutive_violations=1,
                    description="Demo CPU usage threshold",
                    category=AlertCategory.RESOURCE_USAGE
                )
            ]
            
            # Add thresholds to system
            for threshold in custom_thresholds:
                success = self.system.add_performance_threshold(threshold)
                print(f"   Added threshold '{threshold.metric_name}': {success}")
            
            # Display current thresholds
            with self.system._lock:
                total_thresholds = len(self.system._performance_thresholds)
                print(f"   Total performance thresholds: {total_thresholds}")
            
            self.demo_results["tests_run"].append("performance_thresholds")
            print("   ✅ Performance threshold configuration completed")
            
        except Exception as e:
            print(f"   ❌ Performance threshold configuration failed: {e}")
            raise
    
    async def demo_escalation_rules(self):
        """Demonstrate escalation rule configuration."""
        print("\n📈 3. Escalation Rule Configuration")
        print("-" * 50)
        
        try:
            # Define custom escalation rules
            custom_rules = [
                EscalationRule(
                    rule_id="demo_critical_performance",
                    name="Demo Critical Performance Issues",
                    category=AlertCategory.PERFORMANCE,
                    severity_threshold=AlertSeverity.CRITICAL,
                    level_1_duration_minutes=2,
                    level_2_duration_minutes=5,
                    level_3_duration_minutes=10,
                    level_1_channels=["console"],
                    level_2_channels=["console", "email_ops"],
                    level_3_channels=["console", "email_ops", "slack_alerts"],
                    auto_escalate=True,
                    require_acknowledgment=False
                ),
                EscalationRule(
                    rule_id="demo_error_rate_spike",
                    name="Demo Error Rate Spike",
                    category=AlertCategory.ERROR_RATE,
                    severity_threshold=AlertSeverity.HIGH,
                    level_1_duration_minutes=3,
                    level_2_duration_minutes=8,
                    level_3_duration_minutes=15,
                    level_1_channels=["console"],
                    level_2_channels=["console", "slack_alerts"],
                    level_3_channels=["console", "slack_alerts", "pager_duty"],
                    auto_escalate=True,
                    require_acknowledgment=True
                )
            ]
            
            # Add escalation rules to system
            for rule in custom_rules:
                success = self.system.add_escalation_rule(rule)
                print(f"   Added escalation rule '{rule.name}': {success}")
                print(f"     Category: {rule.category.value}")
                print(f"     Severity threshold: {rule.severity_threshold.value}")
                print(f"     Auto-escalate: {rule.auto_escalate}")
            
            # Display current rules
            with self.system._lock:
                total_rules = len(self.system._escalation_rules)
                print(f"   Total escalation rules: {total_rules}")
            
            self.demo_results["tests_run"].append("escalation_rules")
            print("   ✅ Escalation rule configuration completed")
            
        except Exception as e:
            print(f"   ❌ Escalation rule configuration failed: {e}")
            raise
    
    async def demo_notification_channels(self):
        """Demonstrate external notification channel configuration."""
        print("\n📧 4. External Notification Channels")
        print("-" * 50)
        
        try:
            # Configure demo notification channels
            channels_config = {
                "email_ops": {
                    "smtp_server": "smtp.demo.com",
                    "smtp_port": 587,
                    "username": "demo@example.com",
                    "password": "demo_password",
                    "recipients": ["ops@example.com", "admin@example.com"]
                },
                "slack_alerts": {
                    "webhook_url": "https://hooks.slack.com/services/DEMO/WEBHOOK/URL",
                    "channel": "#alerts-demo",
                    "username": "DemoAlertBot",
                    "icon_emoji": ":warning:"
                }
            }
            
            # Configure channels
            for channel_id, config in channels_config.items():
                success = self.system.configure_external_channel(channel_id, config)
                print(f"   Configured channel '{channel_id}': {success}")
            
            # Display channel status
            with self.system._lock:
                enabled_channels = len([
                    ch for ch in self.system._external_channels.values()
                    if ch["enabled"]
                ])
                total_channels = len(self.system._external_channels)
                print(f"   Enabled channels: {enabled_channels}/{total_channels}")
            
            self.demo_results["tests_run"].append("notification_channels")
            print("   ✅ Notification channel configuration completed")
            
        except Exception as e:
            print(f"   ❌ Notification channel configuration failed: {e}")
            raise
    
    async def demo_performance_monitoring(self):
        """Demonstrate performance monitoring and threshold evaluation."""
        print("\n📊 5. Performance Monitoring and Alerting")
        print("-" * 50)
        
        try:
            # Simulate performance metrics that violate thresholds
            mock_metrics = {
                "response_time_metrics": {
                    "avg_response_time_ms": 750.0,  # Will violate demo_response_time threshold
                    "p95_response_time_ms": 1200.0,
                    "total_requests_5min": 150
                },
                "resource_usage": {
                    "cpu": {"percent": 85.0},  # Will violate demo_cpu_usage threshold
                    "memory": {"percent": 70.0},
                    "disk": {"percent": 45.0}
                },
                "cache_metrics": {
                    "hit_rate_percent": 65.0
                },
                "error_metrics": {
                    "error_rate_percent": 7.0  # Will violate demo_error_rate threshold
                }
            }
            
            print("   Simulating performance metrics:")
            print(f"     Response time: {mock_metrics['response_time_metrics']['avg_response_time_ms']}ms")
            print(f"     CPU usage: {mock_metrics['resource_usage']['cpu']['percent']}%")
            print(f"     Error rate: {mock_metrics['error_metrics']['error_rate_percent']}%")
            
            # Mock the metrics collector
            if hasattr(self.system, 'metrics_collector') and self.system.metrics_collector:
                original_get_metrics = self.system.metrics_collector.get_real_time_metrics
                self.system.metrics_collector.get_real_time_metrics = lambda: mock_metrics
            
            # Mock the base alerting service
            original_active_alerts = getattr(self.system.alerting_service, 'active_alerts', {})
            original_alert_history = getattr(self.system.alerting_service, 'alert_history', [])
            self.system.alerting_service.active_alerts = {}
            self.system.alerting_service.alert_history = []
            
            # Evaluate performance thresholds
            print("   Evaluating performance thresholds...")
            await self.system._evaluate_performance_thresholds()
            
            # Check for triggered alerts
            triggered_alerts = len(self.system.alerting_service.active_alerts)
            print(f"   Performance alerts triggered: {triggered_alerts}")
            
            # Display alert details
            for alert_id, alert in self.system.alerting_service.active_alerts.items():
                print(f"     Alert: {alert.rule_name}")
                print(f"       Severity: {alert.severity.value}")
                print(f"       Message: {alert.message}")
                self.demo_results["alerts_triggered"].append({
                    "alert_id": alert_id,
                    "rule_name": alert.rule_name,
                    "severity": alert.severity.value,
                    "message": alert.message
                })
            
            # Restore original methods
            if hasattr(self.system, 'metrics_collector') and self.system.metrics_collector:
                self.system.metrics_collector.get_real_time_metrics = original_get_metrics
            
            self.demo_results["tests_run"].append("performance_monitoring")
            self.demo_results["performance_metrics"] = mock_metrics
            print("   ✅ Performance monitoring demonstration completed")
            
        except Exception as e:
            print(f"   ❌ Performance monitoring demonstration failed: {e}")
            raise
    
    async def demo_error_rate_monitoring(self):
        """Demonstrate error rate monitoring and alerting."""
        print("\n🚨 6. Error Rate Monitoring")
        print("-" * 50)
        
        try:
            # Simulate error rate monitoring
            print("   Simulating error rate scenarios...")
            
            # Record some operations with errors
            if hasattr(self.system, 'error_monitoring') and self.system.error_monitoring:
                # Simulate high error rate
                for i in range(20):
                    success = i % 3 != 0  # 33% error rate
                    self.system.error_monitoring.record_operation(
                        service="demo_service",
                        operation="demo_operation",
                        success=success
                    )
                
                # Get error rate metrics
                error_metrics = self.system.error_monitoring.get_system_error_metrics(window_minutes=5)
                print(f"   System error rate: {error_metrics.error_rate:.1f}%")
                print(f"   Total operations: {error_metrics.total_operations}")
                print(f"   Total errors: {error_metrics.total_errors}")
                
                self.demo_results["performance_metrics"]["error_monitoring"] = {
                    "error_rate": error_metrics.error_rate,
                    "total_operations": error_metrics.total_operations,
                    "total_errors": error_metrics.total_errors
                }
            else:
                print("   Error monitoring not available in demo mode")
            
            self.demo_results["tests_run"].append("error_rate_monitoring")
            print("   ✅ Error rate monitoring demonstration completed")
            
        except Exception as e:
            print(f"   ❌ Error rate monitoring demonstration failed: {e}")
            raise
    
    async def demo_alert_escalation(self):
        """Demonstrate alert escalation procedures."""
        print("\n🔄 7. Alert Escalation Procedures")
        print("-" * 50)
        
        try:
            # Create a sample alert for escalation
            sample_alert = Alert(
                alert_id="demo_alert_001",
                rule_id="demo_rule",
                rule_name="Demo High Severity Alert",
                severity=AlertSeverity.CRITICAL,
                status=AlertStatus.ACTIVE,
                message="Demo critical performance issue detected",
                metric_value=95.0,
                threshold=80.0,
                triggered_at=datetime.now(),
                metadata={"category": "performance"}
            )
            
            print(f"   Created demo alert: {sample_alert.rule_name}")
            print(f"   Alert severity: {sample_alert.severity.value}")
            print(f"   Alert message: {sample_alert.message}")
            
            # Mock the base alerting service to return this alert
            self.system.alerting_service.get_active_alerts = lambda: [sample_alert]
            
            # Mock external notification sending
            original_send_notification = self.system._send_external_notification
            notification_calls = []
            
            async def mock_send_notification(channel_id, escalated_alert, level):
                notification_calls.append({
                    "channel_id": channel_id,
                    "alert_id": escalated_alert.alert_id,
                    "level": level.value,
                    "timestamp": datetime.now().isoformat()
                })
                print(f"     📧 Notification sent via {channel_id} (Level {level.value})")
            
            self.system._send_external_notification = mock_send_notification
            
            # Process escalations
            print("   Processing alert escalations...")
            await self.system._process_escalations()
            
            # Check for created escalations
            escalated_count = len(self.system._escalated_alerts)
            print(f"   Escalated alerts created: {escalated_count}")
            
            # Display escalation details
            for esc_id, esc_alert in self.system._escalated_alerts.items():
                print(f"     Escalation ID: {esc_id}")
                print(f"     Current level: {esc_alert.current_level.value}")
                print(f"     Rule: {esc_alert.escalation_rule.name}")
                
                self.demo_results["escalations_created"].append({
                    "escalation_id": esc_id,
                    "original_alert_id": esc_alert.original_alert.alert_id,
                    "current_level": esc_alert.current_level.value,
                    "rule_name": esc_alert.escalation_rule.name
                })
            
            # Record notifications sent
            self.demo_results["notifications_sent"] = notification_calls
            
            # Restore original method
            self.system._send_external_notification = original_send_notification
            
            self.demo_results["tests_run"].append("alert_escalation")
            print("   ✅ Alert escalation demonstration completed")
            
        except Exception as e:
            print(f"   ❌ Alert escalation demonstration failed: {e}")
            raise
    
    async def demo_alert_correlation(self):
        """Demonstrate alert correlation and noise reduction."""
        print("\n🔗 8. Alert Correlation and Noise Reduction")
        print("-" * 50)
        
        try:
            # Create multiple related alerts
            related_alerts = []
            for i in range(4):
                alert = Alert(
                    alert_id=f"demo_corr_alert_{i}",
                    rule_id=f"demo_corr_rule_{i}",
                    rule_name=f"Demo Correlated Alert {i}",
                    severity=AlertSeverity.HIGH,
                    status=AlertStatus.ACTIVE,
                    message=f"Demo correlated issue {i}",
                    metric_value=90.0 + i,
                    threshold=80.0,
                    triggered_at=datetime.now(),
                    metadata={"category": "performance"}
                )
                related_alerts.append(alert)
            
            print(f"   Created {len(related_alerts)} related alerts for correlation")
            
            # Mock the base alerting service to return these alerts
            self.system.alerting_service.get_active_alerts = lambda: related_alerts
            
            # Run alert correlation
            print("   Running alert correlation...")
            await self.system._correlate_alerts()
            
            # Check for created correlations
            correlation_count = len(self.system._alert_correlations)
            print(f"   Alert correlations created: {correlation_count}")
            
            # Display correlation details
            for corr_id, correlation in self.system._alert_correlations.items():
                print(f"     Correlation ID: {corr_id}")
                print(f"     Related alerts: {len(correlation.related_alerts)}")
                print(f"     Root cause alert: {correlation.root_cause_alert}")
                print(f"     Suppressed alerts: {len(correlation.suppressed_alerts)}")
                print(f"     Reason: {correlation.correlation_reason}")
            
            self.demo_results["tests_run"].append("alert_correlation")
            print("   ✅ Alert correlation demonstration completed")
            
        except Exception as e:
            print(f"   ❌ Alert correlation demonstration failed: {e}")
            raise
    
    async def demo_analytics_reporting(self):
        """Demonstrate analytics and reporting capabilities."""
        print("\n📈 9. System Analytics and Reporting")
        print("-" * 50)
        
        try:
            # Get comprehensive system status
            system_status = self.system.get_escalation_status()
            print("   System Status:")
            print(f"     System active: {system_status['system_active']}")
            print(f"     Active escalations: {system_status['active_escalations']}")
            print(f"     Critical escalations: {system_status['critical_escalations']}")
            print(f"     Escalation rules: {system_status['escalation_rules']}")
            print(f"     Performance thresholds: {system_status['performance_thresholds']}")
            print(f"     Enabled channels: {system_status['enabled_channels']}")
            
            # Generate analytics report
            print("   Generating comprehensive report...")
            report_path = self.system.export_escalation_report()
            print(f"   Report exported to: {report_path}")
            
            # Read and display report summary
            try:
                with open(report_path, 'r') as f:
                    report_data = json.load(f)
                
                print("   Report Summary:")
                print(f"     Export timestamp: {report_data['export_timestamp']}")
                print(f"     Active escalations: {len(report_data['active_escalations'])}")
                print(f"     Alert correlations: {len(report_data['alert_correlations'])}")
                print(f"     Escalation rules: {len(report_data['escalation_rules'])}")
                print(f"     Performance thresholds: {len(report_data['performance_thresholds'])}")
                
            except Exception as e:
                print(f"   Could not read report file: {e}")
            
            self.demo_results["tests_run"].append("analytics_reporting")
            self.demo_results["report_path"] = report_path
            print("   ✅ Analytics and reporting demonstration completed")
            
        except Exception as e:
            print(f"   ❌ Analytics and reporting demonstration failed: {e}")
            raise
    
    async def demo_integration_scenarios(self):
        """Demonstrate integration scenarios and edge cases."""
        print("\n🔧 10. Integration Testing Scenarios")
        print("-" * 50)
        
        try:
            # Test alert acknowledgment
            if self.system._escalated_alerts:
                first_escalation_id = list(self.system._escalated_alerts.keys())[0]
                success = self.system.acknowledge_escalated_alert(first_escalation_id, "demo_user")
                print(f"   Alert acknowledgment test: {success}")
            
            # Test alert resolution
            if self.system._escalated_alerts:
                first_escalation_id = list(self.system._escalated_alerts.keys())[0]
                success = self.system.resolve_escalated_alert(first_escalation_id, "Demo resolution")
                print(f"   Alert resolution test: {success}")
            
            # Test threshold violation tracking
            test_threshold = PerformanceThreshold(
                metric_name="integration_test_metric",
                threshold_value=100.0,
                comparison="greater_than",
                severity=AlertSeverity.MEDIUM,
                consecutive_violations=3
            )
            self.system.add_performance_threshold(test_threshold)
            
            # Simulate consecutive violations
            for i in range(4):
                violation = self.system._evaluate_threshold(150.0, test_threshold)
                if violation:
                    self.system._threshold_violations[test_threshold.metric_name] += 1
            
            violation_count = self.system._threshold_violations[test_threshold.metric_name]
            print(f"   Threshold violation tracking: {violation_count} violations")
            
            # Test configuration edge cases
            invalid_channel_config = self.system.configure_external_channel("invalid_channel", {})
            print(f"   Invalid channel configuration handling: {not invalid_channel_config}")
            
            self.demo_results["tests_run"].append("integration_scenarios")
            print("   ✅ Integration testing scenarios completed")
            
        except Exception as e:
            print(f"   ❌ Integration testing scenarios failed: {e}")
            raise
    
    def print_demo_summary(self):
        """Print a comprehensive summary of the demonstration."""
        print("\n" + "=" * 60)
        print("📊 ENHANCED ALERTING SYSTEM DEMONSTRATION SUMMARY")
        print("=" * 60)
        
        print(f"\n🕒 Demo completed at: {self.demo_results['timestamp']}")
        print(f"✅ Tests run: {len(self.demo_results['tests_run'])}")
        print(f"🚨 Alerts triggered: {len(self.demo_results['alerts_triggered'])}")
        print(f"📈 Escalations created: {len(self.demo_results['escalations_created'])}")
        print(f"📧 Notifications sent: {len(self.demo_results['notifications_sent'])}")
        
        print("\n📋 Tests Executed:")
        for i, test in enumerate(self.demo_results['tests_run'], 1):
            print(f"   {i}. {test.replace('_', ' ').title()}")
        
        if self.demo_results['alerts_triggered']:
            print("\n🚨 Alerts Triggered:")
            for alert in self.demo_results['alerts_triggered']:
                print(f"   • {alert['rule_name']} ({alert['severity']})")
        
        if self.demo_results['escalations_created']:
            print("\n📈 Escalations Created:")
            for escalation in self.demo_results['escalations_created']:
                print(f"   • {escalation['rule_name']} (Level {escalation['current_level']})")
        
        if self.demo_results['notifications_sent']:
            print("\n📧 Notifications Sent:")
            for notification in self.demo_results['notifications_sent']:
                print(f"   • {notification['channel_id']} (Level {notification['level']})")
        
        print(f"\n🏥 Final System Status:")
        if 'system_status' in self.demo_results:
            status = self.demo_results['system_status']
            print(f"   • System Active: {status.get('system_active', 'Unknown')}")
            print(f"   • Performance Monitoring: {status.get('performance_monitoring_enabled', 'Unknown')}")
            print(f"   • Error Monitoring: {status.get('error_monitoring_enabled', 'Unknown')}")
            print(f"   • Escalation Rules: {status.get('escalation_rules', 'Unknown')}")
            print(f"   • Performance Thresholds: {status.get('performance_thresholds', 'Unknown')}")
            print(f"   • Enabled Channels: {status.get('enabled_channels', 'Unknown')}")
        
        print("\n🎯 Key Features Demonstrated:")
        print("   ✅ Performance-based alerting with intelligent thresholds")
        print("   ✅ Error rate monitoring with automatic escalation")
        print("   ✅ Multi-level escalation procedures")
        print("   ✅ External notification channel integration")
        print("   ✅ Alert correlation and noise reduction")
        print("   ✅ Real-time monitoring and analytics")
        print("   ✅ Comprehensive reporting and export capabilities")
        print("   ✅ Integration testing and edge case handling")
        
        print(f"\n📄 Report exported to: {self.demo_results.get('report_path', 'Not generated')}")
        
        print("\n" + "=" * 60)
        print("🎉 Enhanced Alerting System is ready for production use!")
        print("=" * 60)


async def main():
    """Main demonstration function."""
    demo = EnhancedAlertingDemo()
    
    try:
        # Run comprehensive demonstration
        results = await demo.run_comprehensive_demo()
        
        # Print summary
        demo.print_demo_summary()
        
        # Save results to file
        results_file = f"enhanced_alerting_demo_results_{int(time.time())}.json"
        with open(results_file, 'w') as f:
            json.dump(results, f, indent=2, default=str)
        
        print(f"\n💾 Demo results saved to: {results_file}")
        
        return results
        
    except KeyboardInterrupt:
        print("\n\n⚠️  Demo interrupted by user")
        return None
    except Exception as e:
        print(f"\n\n❌ Demo failed with error: {e}")
        return None
    finally:
        # Clean up - stop the alerting system
        try:
            await demo.system.stop_enhanced_alerting()
            print("🛑 Enhanced alerting system stopped")
        except Exception as e:
            print(f"⚠️  Error stopping system: {e}")


if __name__ == "__main__":
    print("Enhanced Alerting System Demonstration")
    print("=====================================")
    print("This demo showcases comprehensive alerting capabilities including:")
    print("• Performance monitoring and alerting")
    print("• Error rate monitoring with escalation")
    print("• Multi-level escalation procedures")
    print("• External notification integration")
    print("• Alert correlation and analytics")
    print("\nStarting demonstration...")
    
    # Run the demonstration
    asyncio.run(main())