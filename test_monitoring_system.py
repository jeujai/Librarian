#!/usr/bin/env python3
"""
Comprehensive Monitoring System Test Suite

Tests the complete monitoring system implementation including:
- Alerting service functionality
- Dashboard service capabilities  
- Monitoring API endpoints
- Background alert evaluation
- Real-time dashboard data
- Integration with main application

This validates Task 13.2: Set up alerting and dashboards
"""

import asyncio
import json
import time
import requests
from datetime import datetime, timedelta
from typing import Dict, List, Any

class MonitoringSystemTester:
    """Comprehensive monitoring system test suite."""
    
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
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
    
    async def test_alerting_service_health(self):
        """Test alerting service health and availability."""
        category = "Alerting Service Health"
        
        try:
            # Test monitoring health endpoint
            response = requests.get(f"{self.base_url}/api/monitoring/health", timeout=10)
            
            if response.status_code == 200:
                health_data = response.json()
                
                # Check overall monitoring status
                if health_data.get("status") in ["healthy", "degraded"]:
                    self.log_test(category, "Monitoring Service Status", True, 
                                f"Status: {health_data.get('status')}", health_data)
                else:
                    self.log_test(category, "Monitoring Service Status", False, 
                                f"Unexpected status: {health_data.get('status')}")
                
                # Check alerting component
                alerting_status = health_data.get("components", {}).get("alerting", {})
                if alerting_status.get("status") == "active":
                    self.log_test(category, "Alerting Component Status", True, 
                                "Alerting service is active", alerting_status)
                else:
                    self.log_test(category, "Alerting Component Status", False, 
                                f"Alerting status: {alerting_status.get('status')}")
                
                # Check alerting features
                features = alerting_status.get("features", {})
                expected_features = ["alert_rules", "notification_channels", "metric_recording", 
                                   "alert_evaluation", "alert_management", "statistics"]
                
                feature_success = all(features.get(feature, False) for feature in expected_features)
                if feature_success:
                    self.log_test(category, "Alerting Features Available", True, 
                                f"All {len(expected_features)} features enabled", features)
                else:
                    missing_features = [f for f in expected_features if not features.get(f, False)]
                    self.log_test(category, "Alerting Features Available", False, 
                                f"Missing features: {missing_features}")
                
            else:
                self.log_test(category, "Monitoring Health Endpoint", False, 
                            f"HTTP {response.status_code}: {response.text}")
                
        except Exception as e:
            self.log_test(category, "Alerting Service Health Check", False, f"Error: {str(e)}")
    
    async def test_dashboard_service_health(self):
        """Test dashboard service health and availability."""
        category = "Dashboard Service Health"
        
        try:
            # Test monitoring health endpoint for dashboard component
            response = requests.get(f"{self.base_url}/api/monitoring/health", timeout=10)
            
            if response.status_code == 200:
                health_data = response.json()
                
                # Check dashboard component
                dashboard_status = health_data.get("components", {}).get("dashboard", {})
                if dashboard_status.get("status") == "active":
                    self.log_test(category, "Dashboard Component Status", True, 
                                "Dashboard service is active", dashboard_status)
                else:
                    self.log_test(category, "Dashboard Component Status", False, 
                                f"Dashboard status: {dashboard_status.get('status')}")
                
                # Check dashboard features
                features = dashboard_status.get("features", {})
                expected_features = ["real_time_dashboards", "custom_widgets", "multiple_data_sources", 
                                   "auto_refresh", "responsive_design"]
                
                feature_success = all(features.get(feature, False) for feature in expected_features)
                if feature_success:
                    self.log_test(category, "Dashboard Features Available", True, 
                                f"All {len(expected_features)} features enabled", features)
                else:
                    missing_features = [f for f in expected_features if not features.get(f, False)]
                    self.log_test(category, "Dashboard Features Available", False, 
                                f"Missing features: {missing_features}")
                
                # Check dashboard statistics
                stats = dashboard_status.get("statistics", {})
                if stats.get("total_dashboards", 0) > 0:
                    self.log_test(category, "Default Dashboards Available", True, 
                                f"{stats.get('total_dashboards')} dashboards with {stats.get('total_widgets')} widgets", stats)
                else:
                    self.log_test(category, "Default Dashboards Available", False, 
                                "No dashboards found")
                
            else:
                self.log_test(category, "Dashboard Health Check", False, 
                            f"HTTP {response.status_code}: {response.text}")
                
        except Exception as e:
            self.log_test(category, "Dashboard Service Health Check", False, f"Error: {str(e)}")
    
    async def test_alert_management_api(self):
        """Test alert management API endpoints."""
        category = "Alert Management API"
        
        try:
            # Test active alerts endpoint
            response = requests.get(f"{self.base_url}/api/monitoring/alerts/active", timeout=10)
            
            if response.status_code == 200:
                alerts_data = response.json()
                self.log_test(category, "Active Alerts Endpoint", True, 
                            f"Retrieved {alerts_data.get('total_count', 0)} active alerts", alerts_data)
                
                # Test severity filtering
                response = requests.get(f"{self.base_url}/api/monitoring/alerts/active?severity=high", timeout=10)
                if response.status_code == 200:
                    filtered_data = response.json()
                    self.log_test(category, "Alert Severity Filtering", True, 
                                f"Filtered alerts by severity: {filtered_data.get('severity_filter')}")
                else:
                    self.log_test(category, "Alert Severity Filtering", False, 
                                f"HTTP {response.status_code}")
            else:
                self.log_test(category, "Active Alerts Endpoint", False, 
                            f"HTTP {response.status_code}: {response.text}")
            
            # Test alert history endpoint
            response = requests.get(f"{self.base_url}/api/monitoring/alerts/history?limit=10", timeout=10)
            
            if response.status_code == 200:
                history_data = response.json()
                self.log_test(category, "Alert History Endpoint", True, 
                            f"Retrieved {history_data.get('total_count', 0)} historical alerts", history_data)
            else:
                self.log_test(category, "Alert History Endpoint", False, 
                            f"HTTP {response.status_code}: {response.text}")
            
            # Test alert statistics endpoint
            response = requests.get(f"{self.base_url}/api/monitoring/alerts/statistics", timeout=10)
            
            if response.status_code == 200:
                stats_data = response.json()
                stats = stats_data.get("statistics", {})
                
                # Check key statistics
                key_stats = ["active_alerts", "total_rules", "enabled_rules", "alerts_last_24h"]
                if all(stat in stats for stat in key_stats):
                    self.log_test(category, "Alert Statistics", True, 
                                f"Statistics available: {len(stats)} metrics", stats)
                else:
                    missing_stats = [stat for stat in key_stats if stat not in stats]
                    self.log_test(category, "Alert Statistics", False, 
                                f"Missing statistics: {missing_stats}")
            else:
                self.log_test(category, "Alert Statistics Endpoint", False, 
                            f"HTTP {response.status_code}: {response.text}")
                
        except Exception as e:
            self.log_test(category, "Alert Management API", False, f"Error: {str(e)}")
    
    async def test_dashboard_api(self):
        """Test dashboard API endpoints."""
        category = "Dashboard API"
        
        try:
            # Test available dashboards endpoint
            response = requests.get(f"{self.base_url}/api/monitoring/dashboards", timeout=10)
            
            if response.status_code == 200:
                dashboards_data = response.json()
                dashboard_count = dashboards_data.get("total_count", 0)
                
                if dashboard_count > 0:
                    self.log_test(category, "Available Dashboards", True, 
                                f"Found {dashboard_count} dashboards", dashboards_data)
                    
                    # Test individual dashboard data
                    dashboards = dashboards_data.get("dashboards", [])
                    if dashboards:
                        first_dashboard = dashboards[0]
                        dashboard_id = first_dashboard["dashboard_id"]
                        
                        response = requests.get(f"{self.base_url}/api/monitoring/dashboards/{dashboard_id}", timeout=15)
                        
                        if response.status_code == 200:
                            dashboard_data = response.json()
                            
                            # Check dashboard structure
                            required_fields = ["dashboard", "widget_data", "last_updated"]
                            if all(field in dashboard_data for field in required_fields):
                                widget_count = len(dashboard_data.get("widget_data", {}))
                                self.log_test(category, "Dashboard Data Retrieval", True, 
                                            f"Dashboard '{first_dashboard['name']}' with {widget_count} widgets")
                            else:
                                missing_fields = [f for f in required_fields if f not in dashboard_data]
                                self.log_test(category, "Dashboard Data Retrieval", False, 
                                            f"Missing fields: {missing_fields}")
                        else:
                            self.log_test(category, "Dashboard Data Retrieval", False, 
                                        f"HTTP {response.status_code}")
                else:
                    self.log_test(category, "Available Dashboards", False, "No dashboards found")
            else:
                self.log_test(category, "Available Dashboards", False, 
                            f"HTTP {response.status_code}: {response.text}")
                
        except Exception as e:
            self.log_test(category, "Dashboard API", False, f"Error: {str(e)}")
    
    async def test_metric_recording(self):
        """Test metric recording functionality."""
        category = "Metric Recording"
        
        try:
            # Test metric recording endpoint
            test_metric = {
                "metric_name": "test_metric",
                "value": 42.5,
                "timestamp": datetime.now().isoformat(),
                "metadata": {"source": "test_suite", "category": "validation"}
            }
            
            response = requests.post(
                f"{self.base_url}/api/monitoring/metrics/record",
                json=test_metric,
                timeout=10
            )
            
            if response.status_code == 200:
                record_data = response.json()
                self.log_test(category, "Metric Recording", True, 
                            f"Recorded metric: {test_metric['metric_name']} = {test_metric['value']}", record_data)
                
                # Test invalid metric recording
                invalid_metric = {"metric_name": "test_invalid"}  # Missing value
                
                response = requests.post(
                    f"{self.base_url}/api/monitoring/metrics/record",
                    json=invalid_metric,
                    timeout=10
                )
                
                if response.status_code == 400:
                    self.log_test(category, "Invalid Metric Validation", True, 
                                "Properly rejected invalid metric data")
                else:
                    self.log_test(category, "Invalid Metric Validation", False, 
                                f"Expected 400, got {response.status_code}")
            else:
                self.log_test(category, "Metric Recording", False, 
                            f"HTTP {response.status_code}: {response.text}")
                
        except Exception as e:
            self.log_test(category, "Metric Recording", False, f"Error: {str(e)}")
    
    async def test_monitoring_dashboard_ui(self):
        """Test monitoring dashboard web interface."""
        category = "Dashboard Web Interface"
        
        try:
            # Test monitoring dashboard route
            response = requests.get(f"{self.base_url}/monitoring", timeout=10)
            
            if response.status_code == 200:
                html_content = response.text
                
                # Check for key dashboard elements
                required_elements = [
                    "Monitoring Dashboard",
                    "Active Alerts",
                    "System Health", 
                    "Performance Monitoring",
                    "Cost Monitoring",
                    "dashboard-grid",
                    "loadMonitoringData"
                ]
                
                missing_elements = []
                for element in required_elements:
                    if element not in html_content:
                        missing_elements.append(element)
                
                if not missing_elements:
                    self.log_test(category, "Dashboard HTML Content", True, 
                                f"All {len(required_elements)} required elements present")
                else:
                    self.log_test(category, "Dashboard HTML Content", False, 
                                f"Missing elements: {missing_elements}")
                
                # Check for JavaScript functionality
                if "loadMonitoringData" in html_content and "setInterval" in html_content:
                    self.log_test(category, "Dashboard JavaScript", True, 
                                "Auto-refresh and data loading functionality present")
                else:
                    self.log_test(category, "Dashboard JavaScript", False, 
                                "Missing JavaScript functionality")
                    
            else:
                self.log_test(category, "Dashboard Web Interface", False, 
                            f"HTTP {response.status_code}: {response.text}")
            
            # Test API dashboard endpoint
            response = requests.get(f"{self.base_url}/api/monitoring/dashboard", timeout=10)
            
            if response.status_code == 200:
                self.log_test(category, "API Dashboard Endpoint", True, 
                            "API dashboard endpoint accessible")
            else:
                self.log_test(category, "API Dashboard Endpoint", False, 
                            f"HTTP {response.status_code}")
                
        except Exception as e:
            self.log_test(category, "Dashboard Web Interface", False, f"Error: {str(e)}")
    
    async def test_main_app_integration(self):
        """Test integration with main application."""
        category = "Main Application Integration"
        
        try:
            # Test that monitoring features are enabled in main app
            response = requests.get(f"{self.base_url}/features", timeout=10)
            
            if response.status_code == 200:
                features_data = response.json()
                features = features_data.get("features", {})
                
                # Check monitoring-related features
                monitoring_features = [
                    "alerting_system",
                    "dashboard_monitoring", 
                    "real_time_alerts",
                    "system_dashboards",
                    "cost_alerts",
                    "performance_dashboards"
                ]
                
                enabled_features = [f for f in monitoring_features if features.get(f, False)]
                
                if len(enabled_features) == len(monitoring_features):
                    self.log_test(category, "Monitoring Features Enabled", True, 
                                f"All {len(monitoring_features)} monitoring features enabled", enabled_features)
                else:
                    disabled_features = [f for f in monitoring_features if not features.get(f, False)]
                    self.log_test(category, "Monitoring Features Enabled", False, 
                                f"Disabled features: {disabled_features}")
            else:
                self.log_test(category, "Features Endpoint", False, 
                            f"HTTP {response.status_code}")
            
            # Test navigation integration (check if monitoring link is in chat interface)
            response = requests.get(f"{self.base_url}/chat", timeout=10)
            
            if response.status_code == 200:
                chat_html = response.text
                if "/monitoring" in chat_html and "🔍 Monitoring" in chat_html:
                    self.log_test(category, "Navigation Integration", True, 
                                "Monitoring link present in chat interface navigation")
                else:
                    self.log_test(category, "Navigation Integration", False, 
                                "Monitoring link missing from navigation")
            else:
                self.log_test(category, "Chat Interface Check", False, 
                            f"HTTP {response.status_code}")
                
        except Exception as e:
            self.log_test(category, "Main Application Integration", False, f"Error: {str(e)}")
    
    async def test_background_alert_evaluation(self):
        """Test background alert evaluation system."""
        category = "Background Alert Evaluation"
        
        try:
            # Record some test metrics to trigger potential alerts
            test_metrics = [
                {"metric_name": "error_rate", "value": 0.02},  # Below threshold
                {"metric_name": "avg_response_time", "value": 1500},  # Below threshold
                {"metric_name": "daily_ai_cost", "value": 25.0}  # Below threshold
            ]
            
            for metric in test_metrics:
                response = requests.post(
                    f"{self.base_url}/api/monitoring/metrics/record",
                    json=metric,
                    timeout=10
                )
                
                if response.status_code != 200:
                    self.log_test(category, "Test Metric Recording", False, 
                                f"Failed to record {metric['metric_name']}")
                    return
            
            self.log_test(category, "Test Metrics Recorded", True, 
                        f"Recorded {len(test_metrics)} test metrics")
            
            # Wait a moment for potential alert evaluation
            await asyncio.sleep(2)
            
            # Check alert statistics to see if evaluation is working
            response = requests.get(f"{self.base_url}/api/monitoring/alerts/statistics", timeout=10)
            
            if response.status_code == 200:
                stats_data = response.json()
                stats = stats_data.get("statistics", {})
                
                # Check if we have alert rules configured
                if stats.get("total_rules", 0) > 0:
                    self.log_test(category, "Alert Rules Configured", True, 
                                f"{stats.get('total_rules')} alert rules, {stats.get('enabled_rules')} enabled")
                    
                    # Check if metrics are being tracked
                    if stats.get("metrics_tracked", 0) > 0:
                        self.log_test(category, "Metrics Tracking", True, 
                                    f"{stats.get('metrics_tracked')} metrics being tracked")
                    else:
                        self.log_test(category, "Metrics Tracking", False, 
                                    "No metrics being tracked")
                else:
                    self.log_test(category, "Alert Rules Configured", False, 
                                "No alert rules found")
            else:
                self.log_test(category, "Alert Statistics Check", False, 
                            f"HTTP {response.status_code}")
                
        except Exception as e:
            self.log_test(category, "Background Alert Evaluation", False, f"Error: {str(e)}")
    
    async def run_all_tests(self):
        """Run all monitoring system tests."""
        print("🔍 Starting Comprehensive Monitoring System Test Suite")
        print("=" * 60)
        
        test_methods = [
            self.test_alerting_service_health,
            self.test_dashboard_service_health,
            self.test_alert_management_api,
            self.test_dashboard_api,
            self.test_metric_recording,
            self.test_monitoring_dashboard_ui,
            self.test_main_app_integration,
            self.test_background_alert_evaluation
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
        print("📊 MONITORING SYSTEM TEST RESULTS")
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
            print(f"\n🎉 ALL TESTS PASSED! Monitoring system is fully functional.")
        else:
            print(f"\n⚠️  Some tests failed. Check the details above.")
        
        # Save detailed results
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        results_file = f"monitoring-system-test-results-{timestamp}.json"
        
        with open(results_file, 'w') as f:
            json.dump(self.results, f, indent=2)
        
        print(f"\n📄 Detailed results saved to: {results_file}")
        
        return self.results

async def main():
    """Run the monitoring system test suite."""
    tester = MonitoringSystemTester()
    results = await tester.run_all_tests()
    
    # Return appropriate exit code
    return 0 if results["overall_success"] else 1

if __name__ == "__main__":
    import sys
    exit_code = asyncio.run(main())
    sys.exit(exit_code)