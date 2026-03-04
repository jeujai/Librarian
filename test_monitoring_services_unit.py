#!/usr/bin/env python3
"""
Monitoring Services Unit Test Suite

Tests the monitoring services directly without requiring a running server:
- Alerting service functionality
- Dashboard service capabilities
- Service integration and configuration

This validates Task 13.2: Set up alerting and dashboards (Unit Tests)
"""

import asyncio
import json
import sys
import os
from datetime import datetime, timedelta
from typing import Dict, List, Any

# Add the src directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

class MonitoringServicesUnitTester:
    """Unit test suite for monitoring services."""
    
    def __init__(self):
        self.results = {
            "timestamp": datetime.now().isoformat(),
            "test_categories": {},
            "overall_success": False,
            "total_tests": 0,
            "passed_tests": 0,
            "failed_tests": 0
        }
    
    def log_test(self, category: str, test_name: str, success: bool, details: str = "", data: Any = None):
        """Log test result."""
        if category not in self.results["test_categories"]:
            self.results["test_categories"][category] = {
                "tests": [],
                "passed": 0,
                "failed": 0,
                "success_rate": 0.0
            }
        
        test_result = {
            "test_name": test_name,
            "success": success,
            "details": details,
            "timestamp": datetime.now().isoformat()
        }
        
        if data:
            test_result["data"] = data
        
        self.results["test_categories"][category]["tests"].append(test_result)
        
        if success:
            self.results["test_categories"][category]["passed"] += 1
            self.results["passed_tests"] += 1
            print(f"✅ {category} - {test_name}: {details}")
        else:
            self.results["test_categories"][category]["failed"] += 1
            self.results["failed_tests"] += 1
            print(f"❌ {category} - {test_name}: {details}")
        
        self.results["total_tests"] += 1
        
        # Update success rate
        total_category_tests = (self.results["test_categories"][category]["passed"] + 
                              self.results["test_categories"][category]["failed"])
        self.results["test_categories"][category]["success_rate"] = (
            self.results["test_categories"][category]["passed"] / total_category_tests * 100
        )
    
    async def test_alerting_service_initialization(self):
        """Test alerting service initialization and basic functionality."""
        category = "Alerting Service Initialization"
        
        try:
            from multimodal_librarian.monitoring.alerting_service import get_alerting_service, AlertSeverity
            
            # Get alerting service instance
            alerting_service = get_alerting_service()
            
            if alerting_service:
                self.log_test(category, "Service Instance Creation", True, 
                            "Alerting service instance created successfully")
            else:
                self.log_test(category, "Service Instance Creation", False, 
                            "Failed to create alerting service instance")
                return
            
            # Test service status
            status = alerting_service.get_service_status()
            
            if status.get("status") == "active":
                self.log_test(category, "Service Status", True, 
                            f"Service active with {len(status.get('features', {}))} features")
            else:
                self.log_test(category, "Service Status", False, 
                            f"Unexpected status: {status.get('status')}")
            
            # Test default alert rules
            if len(alerting_service.alert_rules) > 0:
                self.log_test(category, "Default Alert Rules", True, 
                            f"{len(alerting_service.alert_rules)} default alert rules loaded")
            else:
                self.log_test(category, "Default Alert Rules", False, 
                            "No default alert rules found")
            
            # Test default notification channels
            if len(alerting_service.notification_channels) > 0:
                self.log_test(category, "Default Notification Channels", True, 
                            f"{len(alerting_service.notification_channels)} notification channels configured")
            else:
                self.log_test(category, "Default Notification Channels", False, 
                            "No notification channels found")
            
            # Test alert statistics
            stats = alerting_service.get_alert_statistics()
            
            if isinstance(stats, dict) and "total_rules" in stats:
                self.log_test(category, "Alert Statistics", True, 
                            f"Statistics available: {len(stats)} metrics", stats)
            else:
                self.log_test(category, "Alert Statistics", False, 
                            "Invalid statistics format")
                
        except ImportError as e:
            self.log_test(category, "Import Alerting Service", False, f"Import error: {str(e)}")
        except Exception as e:
            self.log_test(category, "Alerting Service Test", False, f"Error: {str(e)}")
    
    async def test_dashboard_service_initialization(self):
        """Test dashboard service initialization and basic functionality."""
        category = "Dashboard Service Initialization"
        
        try:
            from multimodal_librarian.monitoring.dashboard_service import get_dashboard_service, DashboardType
            
            # Get dashboard service instance
            dashboard_service = get_dashboard_service()
            
            if dashboard_service:
                self.log_test(category, "Service Instance Creation", True, 
                            "Dashboard service instance created successfully")
            else:
                self.log_test(category, "Service Instance Creation", False, 
                            "Failed to create dashboard service instance")
                return
            
            # Test service status
            status = dashboard_service.get_service_status()
            
            if status.get("status") == "active":
                self.log_test(category, "Service Status", True, 
                            f"Service active with {len(status.get('features', {}))} features")
            else:
                self.log_test(category, "Service Status", False, 
                            f"Unexpected status: {status.get('status')}")
            
            # Test default dashboards
            dashboards = dashboard_service.get_available_dashboards()
            
            if len(dashboards) > 0:
                self.log_test(category, "Default Dashboards", True, 
                            f"{len(dashboards)} default dashboards available")
                
                # Test dashboard types
                dashboard_types = set(d["type"] for d in dashboards)
                expected_types = {"system_health", "performance", "cost_monitoring", "user_activity"}
                
                if expected_types.issubset(dashboard_types):
                    self.log_test(category, "Dashboard Types", True, 
                                f"All expected dashboard types present: {dashboard_types}")
                else:
                    missing_types = expected_types - dashboard_types
                    self.log_test(category, "Dashboard Types", False, 
                                f"Missing dashboard types: {missing_types}")
            else:
                self.log_test(category, "Default Dashboards", False, 
                            "No default dashboards found")
            
            # Test data sources
            data_sources = status.get("data_sources", {})
            
            if len(data_sources) > 0:
                self.log_test(category, "Data Sources", True, 
                            f"{len(data_sources)} data sources configured", list(data_sources.keys()))
            else:
                self.log_test(category, "Data Sources", False, 
                            "No data sources configured")
                
        except ImportError as e:
            self.log_test(category, "Import Dashboard Service", False, f"Import error: {str(e)}")
        except Exception as e:
            self.log_test(category, "Dashboard Service Test", False, f"Error: {str(e)}")
    
    async def test_metric_recording_functionality(self):
        """Test metric recording and alert evaluation functionality."""
        category = "Metric Recording & Alert Evaluation"
        
        try:
            from multimodal_librarian.monitoring.alerting_service import get_alerting_service
            
            alerting_service = get_alerting_service()
            
            # Test metric recording
            test_metrics = [
                ("test_metric_1", 10.5),
                ("test_metric_2", 25.0),
                ("error_rate", 0.02),  # Below default threshold
                ("avg_response_time", 1500)  # Below default threshold
            ]
            
            for metric_name, value in test_metrics:
                alerting_service.record_metric(metric_name, value)
            
            # Check if metrics were recorded
            if len(alerting_service.metrics_cache) >= len(test_metrics):
                self.log_test(category, "Metric Recording", True, 
                            f"Recorded {len(test_metrics)} metrics, cache has {len(alerting_service.metrics_cache)} entries")
            else:
                self.log_test(category, "Metric Recording", False, 
                            f"Expected {len(test_metrics)} metrics, found {len(alerting_service.metrics_cache)}")
            
            # Test alert evaluation
            await alerting_service.evaluate_alerts()
            
            # Check active alerts (should be none with our test values)
            active_alerts = alerting_service.get_active_alerts()
            
            self.log_test(category, "Alert Evaluation", True, 
                        f"Alert evaluation completed, {len(active_alerts)} active alerts")
            
            # Test alert statistics after evaluation
            stats = alerting_service.get_alert_statistics()
            
            if stats.get("metrics_tracked", 0) > 0:
                self.log_test(category, "Metrics Tracking", True, 
                            f"{stats.get('metrics_tracked')} metrics being tracked")
            else:
                self.log_test(category, "Metrics Tracking", False, 
                            "No metrics being tracked after recording")
                
        except Exception as e:
            self.log_test(category, "Metric Recording Test", False, f"Error: {str(e)}")
    
    async def test_dashboard_data_generation(self):
        """Test dashboard data generation functionality."""
        category = "Dashboard Data Generation"
        
        try:
            from multimodal_librarian.monitoring.dashboard_service import get_dashboard_service
            
            dashboard_service = get_dashboard_service()
            
            # Get available dashboards
            dashboards = dashboard_service.get_available_dashboards()
            
            if not dashboards:
                self.log_test(category, "Dashboard Data Test", False, "No dashboards available for testing")
                return
            
            # Test data generation for first dashboard
            first_dashboard = dashboards[0]
            dashboard_id = first_dashboard["dashboard_id"]
            
            dashboard_data = await dashboard_service.get_dashboard_data(dashboard_id)
            
            if dashboard_data:
                # Check dashboard data structure
                required_fields = ["dashboard", "widget_data", "last_updated"]
                
                if all(field in dashboard_data for field in required_fields):
                    widget_count = len(dashboard_data.get("widget_data", {}))
                    self.log_test(category, "Dashboard Data Structure", True, 
                                f"Dashboard '{first_dashboard['name']}' data with {widget_count} widgets")
                    
                    # Test widget data
                    widget_data = dashboard_data.get("widget_data", {})
                    successful_widgets = 0
                    
                    for widget_id, data in widget_data.items():
                        if isinstance(data, dict) and not data.get("error"):
                            successful_widgets += 1
                    
                    if successful_widgets > 0:
                        self.log_test(category, "Widget Data Generation", True, 
                                    f"{successful_widgets}/{len(widget_data)} widgets generated data successfully")
                    else:
                        self.log_test(category, "Widget Data Generation", False, 
                                    "No widgets generated data successfully")
                else:
                    missing_fields = [f for f in required_fields if f not in dashboard_data]
                    self.log_test(category, "Dashboard Data Structure", False, 
                                f"Missing required fields: {missing_fields}")
            else:
                self.log_test(category, "Dashboard Data Generation", False, 
                            f"No data returned for dashboard: {dashboard_id}")
                
        except Exception as e:
            self.log_test(category, "Dashboard Data Test", False, f"Error: {str(e)}")
    
    async def test_monitoring_router_import(self):
        """Test monitoring router import and configuration."""
        category = "Monitoring Router Integration"
        
        try:
            from multimodal_librarian.api.routers.monitoring import router
            
            if router:
                self.log_test(category, "Router Import", True, 
                            "Monitoring router imported successfully")
                
                # Check router configuration
                if hasattr(router, 'routes') and len(router.routes) > 0:
                    route_count = len(router.routes)
                    self.log_test(category, "Router Routes", True, 
                                f"{route_count} routes configured in monitoring router")
                    
                    # Check for key endpoints
                    route_paths = [route.path for route in router.routes if hasattr(route, 'path')]
                    expected_paths = [
                        "/api/monitoring/health",
                        "/api/monitoring/alerts/active", 
                        "/api/monitoring/dashboards",
                        "/api/monitoring/metrics/record"
                    ]
                    
                    found_paths = [path for path in expected_paths if any(path in route_path for route_path in route_paths)]
                    
                    if len(found_paths) == len(expected_paths):
                        self.log_test(category, "Key Endpoints", True, 
                                    f"All {len(expected_paths)} key endpoints found")
                    else:
                        missing_paths = set(expected_paths) - set(found_paths)
                        self.log_test(category, "Key Endpoints", False, 
                                    f"Missing endpoints: {missing_paths}")
                else:
                    self.log_test(category, "Router Routes", False, 
                                "No routes found in monitoring router")
            else:
                self.log_test(category, "Router Import", False, 
                            "Failed to import monitoring router")
                
        except ImportError as e:
            self.log_test(category, "Router Import", False, f"Import error: {str(e)}")
        except Exception as e:
            self.log_test(category, "Monitoring Router Test", False, f"Error: {str(e)}")
    
    async def test_service_integration(self):
        """Test integration between alerting and dashboard services."""
        category = "Service Integration"
        
        try:
            from multimodal_librarian.monitoring.alerting_service import get_alerting_service
            from multimodal_librarian.monitoring.dashboard_service import get_dashboard_service
            
            alerting_service = get_alerting_service()
            dashboard_service = get_dashboard_service()
            
            # Test that both services are available
            if alerting_service and dashboard_service:
                self.log_test(category, "Service Availability", True, 
                            "Both alerting and dashboard services available")
            else:
                self.log_test(category, "Service Availability", False, 
                            "One or both services unavailable")
                return
            
            # Test that dashboard can access alerting data
            try:
                # Get a dashboard that uses alerting data
                dashboards = dashboard_service.get_available_dashboards()
                system_health_dashboard = None
                
                for dashboard in dashboards:
                    if dashboard["dashboard_id"] == "system_health":
                        system_health_dashboard = dashboard
                        break
                
                if system_health_dashboard:
                    dashboard_data = await dashboard_service.get_dashboard_data("system_health")
                    
                    # Check if alert widget has data
                    widget_data = dashboard_data.get("widget_data", {})
                    alert_widget_data = widget_data.get("active_alerts")
                    
                    if alert_widget_data and not alert_widget_data.get("error"):
                        self.log_test(category, "Alerting-Dashboard Integration", True, 
                                    "Dashboard successfully accessed alerting service data")
                    else:
                        self.log_test(category, "Alerting-Dashboard Integration", False, 
                                    f"Dashboard failed to access alerting data: {alert_widget_data}")
                else:
                    self.log_test(category, "System Health Dashboard", False, 
                                "System health dashboard not found")
                    
            except Exception as e:
                self.log_test(category, "Integration Test", False, f"Integration error: {str(e)}")
            
            # Test service status consistency
            alerting_status = alerting_service.get_service_status()
            dashboard_status = dashboard_service.get_service_status()
            
            if (alerting_status.get("status") == "active" and 
                dashboard_status.get("status") == "active"):
                self.log_test(category, "Service Status Consistency", True, 
                            "Both services report active status")
            else:
                self.log_test(category, "Service Status Consistency", False, 
                            f"Inconsistent status: alerting={alerting_status.get('status')}, dashboard={dashboard_status.get('status')}")
                
        except Exception as e:
            self.log_test(category, "Service Integration Test", False, f"Error: {str(e)}")
    
    async def run_all_tests(self):
        """Run all monitoring services unit tests."""
        print("🔍 Starting Monitoring Services Unit Test Suite")
        print("=" * 60)
        
        test_methods = [
            self.test_alerting_service_initialization,
            self.test_dashboard_service_initialization,
            self.test_metric_recording_functionality,
            self.test_dashboard_data_generation,
            self.test_monitoring_router_import,
            self.test_service_integration
        ]
        
        for test_method in test_methods:
            try:
                await test_method()
            except Exception as e:
                category = test_method.__name__.replace("test_", "").replace("_", " ").title()
                self.log_test(category, "Test Execution", False, f"Test failed with error: {str(e)}")
        
        # Calculate overall results
        self.results["overall_success"] = self.results["failed_tests"] == 0
        overall_success_rate = (self.results["passed_tests"] / self.results["total_tests"] * 100) if self.results["total_tests"] > 0 else 0
        
        print("\n" + "=" * 60)
        print("📊 MONITORING SERVICES UNIT TEST RESULTS")
        print("=" * 60)
        
        for category, data in self.results["test_categories"].items():
            status = "✅ PASS" if data["failed"] == 0 else "❌ FAIL"
            print(f"{status} {category}: {data['passed']}/{data['passed'] + data['failed']} tests passed ({data['success_rate']:.1f}%)")
        
        print(f"\n🎯 OVERALL RESULTS:")
        print(f"   Total Tests: {self.results['total_tests']}")
        print(f"   Passed: {self.results['passed_tests']}")
        print(f"   Failed: {self.results['failed_tests']}")
        print(f"   Success Rate: {overall_success_rate:.1f}%")
        
        if self.results["overall_success"]:
            print(f"\n🎉 ALL TESTS PASSED! Monitoring services are fully functional.")
        else:
            print(f"\n⚠️  Some tests failed. Check the details above.")
        
        # Save detailed results
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        results_file = f"monitoring-services-unit-test-results-{timestamp}.json"
        
        with open(results_file, 'w') as f:
            json.dump(self.results, f, indent=2)
        
        print(f"\n📄 Detailed results saved to: {results_file}")
        
        return self.results

async def main():
    """Run the monitoring services unit test suite."""
    tester = MonitoringServicesUnitTester()
    results = await tester.run_all_tests()
    
    # Return appropriate exit code
    return 0 if results["overall_success"] else 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)