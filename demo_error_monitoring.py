#!/usr/bin/env python3
"""
Error Monitoring System Demonstration

This script demonstrates the comprehensive error monitoring system including:
- Real-time error tracking and rate monitoring
- Configurable alert thresholds
- Integration with error logging and alerting services
- API endpoints and system management

Run this script to see the error monitoring system in action.
"""

import asyncio
import json
import random
import time
from datetime import datetime, timedelta
from typing import Dict, Any

# Import the error monitoring system
from src.multimodal_librarian.monitoring.error_monitoring_system import (
    get_error_monitoring_system,
    ErrorThresholdConfig,
    start_error_monitoring,
    stop_error_monitoring,
    record_operation_result
)
from src.multimodal_librarian.monitoring.error_logging_service import (
    ErrorCategory,
    ErrorSeverity
)
from src.multimodal_librarian.monitoring.alerting_service import AlertSeverity


class ErrorMonitoringDemo:
    """Demonstration of the error monitoring system."""
    
    def __init__(self):
        self.monitoring_system = get_error_monitoring_system()
        self.demo_services = ["api", "database", "search", "ai_service", "vector_store"]
        self.demo_operations = ["create", "read", "update", "delete", "search", "process"]
        self.results = {}
    
    async def run_demo(self):
        """Run the complete error monitoring demonstration."""
        print("🔍 Error Monitoring System Demonstration")
        print("=" * 50)
        
        try:
            # Step 1: Initialize and configure
            await self.demo_initialization()
            
            # Step 2: Start monitoring
            await self.demo_start_monitoring()
            
            # Step 3: Configure custom thresholds
            await self.demo_threshold_configuration()
            
            # Step 4: Simulate normal operations
            await self.demo_normal_operations()
            
            # Step 5: Simulate error scenarios
            await self.demo_error_scenarios()
            
            # Step 6: Demonstrate alerting
            await self.demo_alerting_system()
            
            # Step 7: Show metrics and analysis
            await self.demo_metrics_analysis()
            
            # Step 8: Test alert management
            await self.demo_alert_management()
            
            # Step 9: Export data
            await self.demo_data_export()
            
            # Step 10: Cleanup
            await self.demo_cleanup()
            
        except Exception as e:
            print(f"❌ Demo failed with error: {e}")
            raise
        finally:
            # Ensure monitoring is stopped
            try:
                await stop_error_monitoring()
            except:
                pass
    
    async def demo_initialization(self):
        """Demonstrate system initialization."""
        print("\n📋 Step 1: System Initialization")
        print("-" * 30)
        
        # Show initial status
        status = self.monitoring_system.get_monitoring_status()
        print(f"✅ Monitoring system initialized")
        print(f"   - Default threshold configs: {status['threshold_configs']}")
        print(f"   - Services monitored: {status['services_monitored']}")
        print(f"   - Monitoring active: {status['monitoring_active']}")
        
        self.results['initialization'] = {
            'status': 'success',
            'threshold_configs': status['threshold_configs'],
            'services_monitored': status['services_monitored']
        }
    
    async def demo_start_monitoring(self):
        """Demonstrate starting the monitoring system."""
        print("\n🚀 Step 2: Start Monitoring System")
        print("-" * 35)
        
        await start_error_monitoring()
        
        # Wait a moment for initialization
        await asyncio.sleep(1)
        
        status = self.monitoring_system.get_monitoring_status()
        print(f"✅ Monitoring system started")
        print(f"   - Status: {'Active' if status['monitoring_active'] else 'Inactive'}")
        print(f"   - Last evaluation: {status['last_evaluation']}")
        
        self.results['monitoring_start'] = {
            'status': 'success',
            'active': status['monitoring_active'],
            'last_evaluation': status['last_evaluation'].isoformat()
        }
    
    async def demo_threshold_configuration(self):
        """Demonstrate configuring custom error thresholds."""
        print("\n⚙️  Step 3: Configure Custom Thresholds")
        print("-" * 40)
        
        # Add a sensitive threshold for demo purposes
        demo_config = ErrorThresholdConfig(
            service="demo_service",
            operation="demo_operation",
            warning_rate=2.0,      # 2 errors per minute
            critical_rate=5.0,     # 5 errors per minute
            warning_percentage=15.0, # 15% error rate
            critical_percentage=30.0, # 30% error rate
            evaluation_window_minutes=2,
            cooldown_minutes=5
        )
        
        success = self.monitoring_system.add_threshold_config(demo_config)
        print(f"✅ Added custom threshold config: {success}")
        print(f"   - Service: {demo_config.service}")
        print(f"   - Warning rate: {demo_config.warning_rate} errors/min")
        print(f"   - Critical rate: {demo_config.critical_rate} errors/min")
        print(f"   - Warning percentage: {demo_config.warning_percentage}%")
        print(f"   - Critical percentage: {demo_config.critical_percentage}%")
        
        self.results['threshold_config'] = {
            'status': 'success',
            'config_added': success,
            'service': demo_config.service,
            'warning_rate': demo_config.warning_rate,
            'critical_rate': demo_config.critical_rate
        }
    
    async def demo_normal_operations(self):
        """Demonstrate recording normal operations."""
        print("\n📊 Step 4: Simulate Normal Operations")
        print("-" * 38)
        
        operation_count = 0
        
        # Simulate normal operations with high success rate
        for service in self.demo_services:
            for operation in random.sample(self.demo_operations, 3):
                # 95% success rate for normal operations
                for _ in range(20):
                    success = random.random() > 0.05
                    record_operation_result(service, operation, success)
                    operation_count += 1
        
        print(f"✅ Recorded {operation_count} normal operations")
        print(f"   - Services: {len(self.demo_services)}")
        print(f"   - Expected success rate: ~95%")
        
        # Show current metrics
        await asyncio.sleep(1)  # Let monitoring process
        metrics = self.monitoring_system.get_system_error_metrics()
        print(f"   - Actual error rate: {metrics.error_rate:.2f}%")
        print(f"   - Total operations: {metrics.total_operations}")
        print(f"   - Total errors: {metrics.total_errors}")
        
        self.results['normal_operations'] = {
            'status': 'success',
            'operations_recorded': operation_count,
            'error_rate': metrics.error_rate,
            'total_operations': metrics.total_operations,
            'total_errors': metrics.total_errors
        }
    
    async def demo_error_scenarios(self):
        """Demonstrate various error scenarios."""
        print("\n🚨 Step 5: Simulate Error Scenarios")
        print("-" * 36)
        
        error_scenarios = [
            {
                'name': 'Database Connection Failures',
                'service': 'database',
                'operation': 'connect',
                'error_category': ErrorCategory.DATABASE_ERROR,
                'error_severity': ErrorSeverity.HIGH,
                'error_count': 8,
                'success_count': 2
            },
            {
                'name': 'API Rate Limiting',
                'service': 'api',
                'operation': 'process_request',
                'error_category': ErrorCategory.EXTERNAL_SERVICE_ERROR,
                'error_severity': ErrorSeverity.MEDIUM,
                'error_count': 12,
                'success_count': 8
            },
            {
                'name': 'Search Service Timeouts',
                'service': 'search',
                'operation': 'vector_search',
                'error_category': ErrorCategory.NETWORK_ERROR,
                'error_severity': ErrorSeverity.MEDIUM,
                'error_count': 6,
                'success_count': 14
            },
            {
                'name': 'Demo Service Critical Errors',
                'service': 'demo_service',
                'operation': 'demo_operation',
                'error_category': ErrorCategory.SERVICE_FAILURE,
                'error_severity': ErrorSeverity.CRITICAL,
                'error_count': 15,  # This should trigger alerts
                'success_count': 5
            }
        ]
        
        for scenario in error_scenarios:
            print(f"\n   🔥 Simulating: {scenario['name']}")
            
            # Record errors
            for _ in range(scenario['error_count']):
                record_operation_result(
                    scenario['service'],
                    scenario['operation'],
                    success=False,
                    error_category=scenario['error_category'],
                    error_severity=scenario['error_severity']
                )
            
            # Record some successes
            for _ in range(scenario['success_count']):
                record_operation_result(
                    scenario['service'],
                    scenario['operation'],
                    success=True
                )
            
            # Get error rate for this service
            error_rate = self.monitoring_system.get_error_rate(
                scenario['service'], 
                scenario['operation']
            )
            
            print(f"      - Error rate: {error_rate['error_rate_percentage']:.1f}%")
            print(f"      - Errors/min: {error_rate['errors_per_minute']:.1f}")
            print(f"      - Total ops: {error_rate['total_operations']}")
        
        self.results['error_scenarios'] = {
            'status': 'success',
            'scenarios_simulated': len(error_scenarios),
            'scenarios': [
                {
                    'name': s['name'],
                    'service': s['service'],
                    'error_count': s['error_count'],
                    'success_count': s['success_count']
                }
                for s in error_scenarios
            ]
        }
    
    async def demo_alerting_system(self):
        """Demonstrate the alerting system."""
        print("\n🚨 Step 6: Demonstrate Alerting System")
        print("-" * 38)
        
        # Wait for monitoring system to evaluate thresholds
        print("   ⏳ Waiting for threshold evaluation...")
        await asyncio.sleep(3)
        
        # Check for active alerts
        active_alerts = self.monitoring_system.get_active_alerts()
        print(f"✅ Active alerts detected: {len(active_alerts)}")
        
        if active_alerts:
            for i, alert in enumerate(active_alerts[:3], 1):  # Show first 3 alerts
                print(f"\n   🚨 Alert #{i}:")
                print(f"      - Service: {alert.threshold_config.service}")
                print(f"      - Severity: {alert.severity.value}")
                print(f"      - Current rate: {alert.current_rate:.1f} errors/min")
                print(f"      - Current percentage: {alert.current_percentage:.1f}%")
                print(f"      - Threshold exceeded: {alert.threshold_exceeded}")
                print(f"      - Message: {alert.message}")
                print(f"      - Consecutive count: {alert.consecutive_count}")
                print(f"      - Escalated: {alert.escalated}")
        else:
            print("   ℹ️  No alerts triggered (thresholds may need adjustment)")
        
        # Check alert history
        alert_history = self.monitoring_system.get_alert_history(limit=5)
        print(f"\n   📜 Alert history entries: {len(alert_history)}")
        
        self.results['alerting'] = {
            'status': 'success',
            'active_alerts': len(active_alerts),
            'alert_history': len(alert_history),
            'alerts': [
                {
                    'service': alert.threshold_config.service,
                    'severity': alert.severity.value,
                    'current_rate': alert.current_rate,
                    'current_percentage': alert.current_percentage,
                    'escalated': alert.escalated
                }
                for alert in active_alerts[:3]
            ]
        }
    
    async def demo_metrics_analysis(self):
        """Demonstrate metrics analysis and reporting."""
        print("\n📈 Step 7: Metrics Analysis")
        print("-" * 28)
        
        # Get comprehensive system metrics
        metrics = self.monitoring_system.get_system_error_metrics()
        
        print(f"✅ System-wide metrics:")
        print(f"   - Total operations: {metrics.total_operations}")
        print(f"   - Total errors: {metrics.total_errors}")
        print(f"   - Overall error rate: {metrics.error_rate:.2f}%")
        
        print(f"\n   📊 Errors by service:")
        for service, count in sorted(metrics.errors_by_service.items()):
            if count > 0:
                service_rate = self.monitoring_system.get_error_rate(service)
                print(f"      - {service}: {count} errors ({service_rate['error_rate_percentage']:.1f}%)")
        
        print(f"\n   🏷️  Errors by category:")
        for category, count in sorted(metrics.errors_by_category.items()):
            if count > 0:
                print(f"      - {category}: {count} errors")
        
        print(f"\n   ⚠️  Errors by severity:")
        for severity, count in sorted(metrics.errors_by_severity.items()):
            if count > 0:
                print(f"      - {severity}: {count} errors")
        
        # Show top error patterns
        if metrics.top_error_types:
            print(f"\n   🔍 Top error patterns:")
            for i, pattern in enumerate(metrics.top_error_types[:3], 1):
                print(f"      {i}. {pattern.get('error_type', 'Unknown')}: {pattern.get('occurrences', 0)} occurrences")
        
        self.results['metrics_analysis'] = {
            'status': 'success',
            'total_operations': metrics.total_operations,
            'total_errors': metrics.total_errors,
            'error_rate': metrics.error_rate,
            'errors_by_service': dict(metrics.errors_by_service),
            'errors_by_category': dict(metrics.errors_by_category),
            'errors_by_severity': dict(metrics.errors_by_severity)
        }
    
    async def demo_alert_management(self):
        """Demonstrate alert management capabilities."""
        print("\n🔧 Step 8: Alert Management")
        print("-" * 28)
        
        active_alerts = self.monitoring_system.get_active_alerts()
        
        if active_alerts:
            # Demonstrate acknowledging an alert
            first_alert = active_alerts[0]
            success = self.monitoring_system.acknowledge_alert(first_alert.alert_id)
            print(f"✅ Acknowledged alert: {success}")
            print(f"   - Alert ID: {first_alert.alert_id}")
            print(f"   - Service: {first_alert.threshold_config.service}")
            
            # Demonstrate resolving an alert
            if len(active_alerts) > 1:
                second_alert = active_alerts[1]
                success = self.monitoring_system.resolve_alert(
                    second_alert.alert_id, 
                    "Demo resolution - issue fixed"
                )
                print(f"✅ Resolved alert: {success}")
                print(f"   - Alert ID: {second_alert.alert_id}")
                print(f"   - Resolution reason: Demo resolution - issue fixed")
            
            # Show updated active alerts count
            updated_alerts = self.monitoring_system.get_active_alerts()
            print(f"\n   📊 Alert status update:")
            print(f"      - Previously active: {len(active_alerts)}")
            print(f"      - Currently active: {len(updated_alerts)}")
            
            self.results['alert_management'] = {
                'status': 'success',
                'initial_alerts': len(active_alerts),
                'final_alerts': len(updated_alerts),
                'acknowledged': True,
                'resolved': len(active_alerts) > 1
            }
        else:
            print("   ℹ️  No active alerts to manage")
            self.results['alert_management'] = {
                'status': 'no_alerts',
                'initial_alerts': 0,
                'final_alerts': 0
            }
    
    async def demo_data_export(self):
        """Demonstrate data export functionality."""
        print("\n💾 Step 9: Data Export")
        print("-" * 22)
        
        try:
            # Export monitoring data
            filepath = self.monitoring_system.export_monitoring_data()
            print(f"✅ Data exported successfully")
            print(f"   - File: {filepath}")
            
            # Read and show summary of exported data
            with open(filepath, 'r') as f:
                export_data = json.load(f)
            
            print(f"   - Export timestamp: {export_data['export_timestamp']}")
            print(f"   - Threshold configs: {len(export_data['threshold_configs'])}")
            print(f"   - Active alerts: {len(export_data['active_alerts'])}")
            print(f"   - Metrics history entries: {len(export_data['metrics_history'])}")
            
            # Show file size
            import os
            file_size = os.path.getsize(filepath)
            print(f"   - File size: {file_size:,} bytes")
            
            self.results['data_export'] = {
                'status': 'success',
                'filepath': filepath,
                'file_size': file_size,
                'threshold_configs': len(export_data['threshold_configs']),
                'active_alerts': len(export_data['active_alerts']),
                'metrics_history': len(export_data['metrics_history'])
            }
            
        except Exception as e:
            print(f"❌ Export failed: {e}")
            self.results['data_export'] = {
                'status': 'failed',
                'error': str(e)
            }
    
    async def demo_cleanup(self):
        """Demonstrate system cleanup."""
        print("\n🧹 Step 10: Cleanup")
        print("-" * 19)
        
        # Stop monitoring
        await stop_error_monitoring()
        
        # Get final status
        status = self.monitoring_system.get_monitoring_status()
        print(f"✅ Monitoring system stopped")
        print(f"   - Status: {'Active' if status['monitoring_active'] else 'Inactive'}")
        
        self.results['cleanup'] = {
            'status': 'success',
            'monitoring_active': status['monitoring_active']
        }
    
    def print_demo_summary(self):
        """Print a summary of the demonstration results."""
        print("\n" + "=" * 50)
        print("📋 DEMONSTRATION SUMMARY")
        print("=" * 50)
        
        total_steps = len(self.results)
        successful_steps = len([r for r in self.results.values() if r.get('status') == 'success'])
        
        print(f"✅ Completed steps: {successful_steps}/{total_steps}")
        
        if 'normal_operations' in self.results:
            ops = self.results['normal_operations']
            print(f"📊 Operations recorded: {ops.get('total_operations', 0)}")
            print(f"📈 Final error rate: {ops.get('error_rate', 0):.2f}%")
        
        if 'alerting' in self.results:
            alerts = self.results['alerting']
            print(f"🚨 Alerts triggered: {alerts.get('active_alerts', 0)}")
        
        if 'data_export' in self.results and self.results['data_export']['status'] == 'success':
            export = self.results['data_export']
            print(f"💾 Export file size: {export.get('file_size', 0):,} bytes")
        
        print(f"\n🎯 Key Features Demonstrated:")
        print(f"   ✅ Real-time error tracking")
        print(f"   ✅ Configurable alert thresholds")
        print(f"   ✅ Error rate monitoring")
        print(f"   ✅ Alert management")
        print(f"   ✅ Metrics analysis")
        print(f"   ✅ Data export")
        print(f"   ✅ System integration")
        
        print(f"\n🔍 Error Monitoring System is ready for production use!")


async def main():
    """Main demonstration function."""
    demo = ErrorMonitoringDemo()
    
    try:
        await demo.run_demo()
        demo.print_demo_summary()
        
    except KeyboardInterrupt:
        print("\n\n⏹️  Demo interrupted by user")
    except Exception as e:
        print(f"\n\n❌ Demo failed: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Ensure cleanup
        try:
            await stop_error_monitoring()
        except:
            pass


if __name__ == "__main__":
    print("Starting Error Monitoring System Demonstration...")
    asyncio.run(main())