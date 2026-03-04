#!/usr/bin/env python3
"""
Comprehensive test suite for Task 13.1 - Comprehensive Logging Implementation.

This test validates:
- Structured logging across all services
- Distributed tracing for requests
- Performance monitoring
- Business metrics tracking
- Error tracking and alerting
- Logging API endpoints
- Integration with existing services
"""

import asyncio
import json
import time
import requests
from datetime import datetime
from typing import Dict, Any, List

# Test configuration
BASE_URL = "http://localhost:8001"
TEST_RESULTS = {
    "test_name": "Task 13.1 - Comprehensive Logging Implementation",
    "timestamp": datetime.now().isoformat(),
    "tests": {}
}


def log_test_result(test_name: str, success: bool, details: Dict[str, Any], error: str = None):
    """Log test result."""
    TEST_RESULTS["tests"][test_name] = {
        "success": success,
        "details": details,
        "error": error,
        "timestamp": datetime.now().isoformat()
    }
    
    status = "✅ PASS" if success else "❌ FAIL"
    print(f"{status} {test_name}")
    if error:
        print(f"   Error: {error}")
    if details:
        print(f"   Details: {json.dumps(details, indent=2)}")


def test_logging_service_health():
    """Test logging service health endpoint."""
    try:
        response = requests.get(f"{BASE_URL}/api/logging/health", timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            
            # Validate response structure
            required_fields = ["status", "service", "components", "recent_activity"]
            missing_fields = [field for field in required_fields if field not in data]
            
            if missing_fields:
                log_test_result(
                    "logging_service_health",
                    False,
                    {"status_code": response.status_code, "response": data},
                    f"Missing required fields: {missing_fields}"
                )
                return False
            
            # Check if service is healthy
            is_healthy = data.get("status") == "healthy"
            components_ok = all(
                comp == "ok" for comp in data.get("components", {}).values()
            )
            
            log_test_result(
                "logging_service_health",
                is_healthy and components_ok,
                {
                    "status": data.get("status"),
                    "components": data.get("components"),
                    "recent_activity": data.get("recent_activity")
                }
            )
            return is_healthy and components_ok
            
        else:
            log_test_result(
                "logging_service_health",
                False,
                {"status_code": response.status_code, "response": response.text},
                f"HTTP {response.status_code}"
            )
            return False
            
    except Exception as e:
        log_test_result(
            "logging_service_health",
            False,
            {},
            str(e)
        )
        return False


def test_structured_logging_api():
    """Test structured logging API endpoint."""
    try:
        # Test logging a structured entry
        log_data = {
            "level": "INFO",
            "service": "test_service",
            "operation": "test_operation",
            "message": "Test log message for comprehensive logging validation",
            "metadata": {
                "test_type": "structured_logging",
                "test_timestamp": datetime.now().isoformat()
            }
        }
        
        response = requests.post(
            f"{BASE_URL}/api/logging/log",
            params=log_data,
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            
            # Validate response
            success = (
                data.get("success", False) and
                data.get("details", {}).get("service") == "test_service" and
                data.get("details", {}).get("operation") == "test_operation"
            )
            
            log_test_result(
                "structured_logging_api",
                success,
                {
                    "log_data": log_data,
                    "response": data
                }
            )
            return success
            
        else:
            log_test_result(
                "structured_logging_api",
                False,
                {"status_code": response.status_code, "response": response.text},
                f"HTTP {response.status_code}"
            )
            return False
            
    except Exception as e:
        log_test_result(
            "structured_logging_api",
            False,
            {},
            str(e)
        )
        return False


def test_distributed_tracing():
    """Test distributed tracing functionality."""
    try:
        # Start a trace
        trace_data = {
            "service": "test_service",
            "operation": "test_distributed_tracing"
        }
        
        start_response = requests.post(
            f"{BASE_URL}/api/logging/trace/start",
            params=trace_data,
            timeout=10
        )
        
        if start_response.status_code != 200:
            log_test_result(
                "distributed_tracing",
                False,
                {"start_response": start_response.text},
                f"Failed to start trace: HTTP {start_response.status_code}"
            )
            return False
        
        start_data = start_response.json()
        trace_id = start_data.get("details", {}).get("trace_id")
        
        if not trace_id:
            log_test_result(
                "distributed_tracing",
                False,
                {"start_response": start_data},
                "No trace_id returned"
            )
            return False
        
        # Simulate some work
        time.sleep(0.1)
        
        # Finish the trace
        finish_response = requests.post(
            f"{BASE_URL}/api/logging/trace/{trace_id}/finish",
            params={"error": False},
            timeout=10
        )
        
        if finish_response.status_code != 200:
            log_test_result(
                "distributed_tracing",
                False,
                {"finish_response": finish_response.text},
                f"Failed to finish trace: HTTP {finish_response.status_code}"
            )
            return False
        
        # Get trace details
        trace_response = requests.get(
            f"{BASE_URL}/api/logging/traces",
            params={"trace_id": trace_id},
            timeout=10
        )
        
        if trace_response.status_code == 200:
            trace_details = trace_response.json()
            
            success = (
                "trace_data" in trace_details and
                trace_details["trace_data"].get("trace", {}).get("trace_id") == trace_id
            )
            
            log_test_result(
                "distributed_tracing",
                success,
                {
                    "trace_id": trace_id,
                    "trace_details": trace_details.get("trace_data", {})
                }
            )
            return success
        else:
            log_test_result(
                "distributed_tracing",
                False,
                {"trace_response": trace_response.text},
                f"Failed to get trace details: HTTP {trace_response.status_code}"
            )
            return False
            
    except Exception as e:
        log_test_result(
            "distributed_tracing",
            False,
            {},
            str(e)
        )
        return False


def test_performance_monitoring():
    """Test performance monitoring functionality."""
    try:
        # Make some requests to generate performance data
        test_endpoints = [
            "/health",
            "/features",
            "/api/logging/health"
        ]
        
        for endpoint in test_endpoints:
            requests.get(f"{BASE_URL}{endpoint}", timeout=5)
        
        # Wait a moment for metrics to be processed
        time.sleep(1)
        
        # Get performance metrics
        response = requests.get(
            f"{BASE_URL}/api/logging/performance",
            params={"hours": 1},
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            
            # Check if performance metrics are available
            perf_metrics = data.get("performance_metrics", {})
            
            success = (
                "error" not in perf_metrics and
                "total_operations" in perf_metrics and
                "performance" in perf_metrics
            )
            
            log_test_result(
                "performance_monitoring",
                success,
                {
                    "metrics_available": success,
                    "total_operations": perf_metrics.get("total_operations", 0),
                    "performance_data": perf_metrics.get("performance", {})
                }
            )
            return success
            
        else:
            log_test_result(
                "performance_monitoring",
                False,
                {"status_code": response.status_code, "response": response.text},
                f"HTTP {response.status_code}"
            )
            return False
            
    except Exception as e:
        log_test_result(
            "performance_monitoring",
            False,
            {},
            str(e)
        )
        return False


def test_business_metrics():
    """Test business metrics functionality."""
    try:
        # Log a business metric
        metric_data = {
            "metric_name": "test_metric",
            "metric_value": 42.5,
            "metric_type": "gauge",
            "tags": {"test_type": "comprehensive_logging", "environment": "test"}
        }
        
        response = requests.post(
            f"{BASE_URL}/api/logging/business-metric",
            params=metric_data,
            timeout=10
        )
        
        if response.status_code != 200:
            log_test_result(
                "business_metrics",
                False,
                {"status_code": response.status_code, "response": response.text},
                f"Failed to log business metric: HTTP {response.status_code}"
            )
            return False
        
        # Wait for metric to be processed
        time.sleep(1)
        
        # Get business metrics
        metrics_response = requests.get(
            f"{BASE_URL}/api/logging/business-metrics",
            params={"metric_name": "test_metric", "hours": 1},
            timeout=10
        )
        
        if metrics_response.status_code == 200:
            metrics_data = metrics_response.json()
            
            business_metrics = metrics_data.get("business_metrics", {})
            
            success = (
                "error" not in business_metrics and
                "metrics" in business_metrics and
                "test_metric" in business_metrics.get("metrics", {})
            )
            
            log_test_result(
                "business_metrics",
                success,
                {
                    "metric_logged": response.json(),
                    "metrics_retrieved": business_metrics.get("metrics", {}).get("test_metric", {})
                }
            )
            return success
            
        else:
            log_test_result(
                "business_metrics",
                False,
                {"metrics_response": metrics_response.text},
                f"Failed to get business metrics: HTTP {metrics_response.status_code}"
            )
            return False
            
    except Exception as e:
        log_test_result(
            "business_metrics",
            False,
            {},
            str(e)
        )
        return False


def test_error_tracking():
    """Test error tracking functionality."""
    try:
        # Get error summary
        response = requests.get(
            f"{BASE_URL}/api/logging/errors",
            params={"hours": 24},
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            
            error_summary = data.get("error_summary", {})
            
            # Check if error tracking is working
            success = (
                "total_error_patterns" in error_summary and
                "recent_errors_count" in error_summary and
                "error_rate_per_hour" in error_summary
            )
            
            log_test_result(
                "error_tracking",
                success,
                {
                    "error_patterns": error_summary.get("total_error_patterns", 0),
                    "recent_errors": error_summary.get("recent_errors_count", 0),
                    "error_rate": error_summary.get("error_rate_per_hour", 0)
                }
            )
            return success
            
        else:
            log_test_result(
                "error_tracking",
                False,
                {"status_code": response.status_code, "response": response.text},
                f"HTTP {response.status_code}"
            )
            return False
            
    except Exception as e:
        log_test_result(
            "error_tracking",
            False,
            {},
            str(e)
        )
        return False


def test_operation_statistics():
    """Test operation statistics functionality."""
    try:
        response = requests.get(
            f"{BASE_URL}/api/logging/operations",
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            
            operation_stats = data.get("operation_stats", {})
            
            success = (
                "operations" in operation_stats and
                "total_operations" in operation_stats
            )
            
            log_test_result(
                "operation_statistics",
                success,
                {
                    "total_operations": operation_stats.get("total_operations", 0),
                    "sample_operations": list(operation_stats.get("operations", {}).keys())[:5]
                }
            )
            return success
            
        else:
            log_test_result(
                "operation_statistics",
                False,
                {"status_code": response.status_code, "response": response.text},
                f"HTTP {response.status_code}"
            )
            return False
            
    except Exception as e:
        log_test_result(
            "operation_statistics",
            False,
            {},
            str(e)
        )
        return False


def test_logging_dashboard():
    """Test comprehensive logging dashboard."""
    try:
        response = requests.get(
            f"{BASE_URL}/api/logging/dashboard",
            timeout=15
        )
        
        if response.status_code == 200:
            data = response.json()
            
            dashboard_data = data.get("dashboard_data", {})
            summary = data.get("summary", {})
            
            # Check if all dashboard components are present
            required_components = [
                "recent_logs", "performance", "business_metrics",
                "error_summary", "trace_summary", "operation_stats"
            ]
            
            missing_components = [
                comp for comp in required_components
                if comp not in dashboard_data
            ]
            
            success = len(missing_components) == 0
            
            log_test_result(
                "logging_dashboard",
                success,
                {
                    "components_present": len(required_components) - len(missing_components),
                    "total_components": len(required_components),
                    "missing_components": missing_components,
                    "summary": summary
                }
            )
            return success
            
        else:
            log_test_result(
                "logging_dashboard",
                False,
                {"status_code": response.status_code, "response": response.text},
                f"HTTP {response.status_code}"
            )
            return False
            
    except Exception as e:
        log_test_result(
            "logging_dashboard",
            False,
            {},
            str(e)
        )
        return False


def test_log_export():
    """Test log export functionality."""
    try:
        response = requests.post(
            f"{BASE_URL}/api/logging/export",
            params={"hours": 1, "format": "json"},
            timeout=15
        )
        
        if response.status_code == 200:
            data = response.json()
            
            success = (
                data.get("success", False) and
                "filepath" in data.get("details", {})
            )
            
            log_test_result(
                "log_export",
                success,
                {
                    "export_successful": success,
                    "filepath": data.get("details", {}).get("filepath"),
                    "hours": data.get("details", {}).get("hours")
                }
            )
            return success
            
        else:
            log_test_result(
                "log_export",
                False,
                {"status_code": response.status_code, "response": response.text},
                f"HTTP {response.status_code}"
            )
            return False
            
    except Exception as e:
        log_test_result(
            "log_export",
            False,
            {},
            str(e)
        )
        return False


def test_middleware_integration():
    """Test logging middleware integration."""
    try:
        # Make a request that should be logged by middleware
        response = requests.get(f"{BASE_URL}/features", timeout=10)
        
        if response.status_code == 200:
            # Check if correlation and trace headers are present
            correlation_id = response.headers.get("X-Correlation-ID")
            trace_id = response.headers.get("X-Trace-ID")
            
            success = correlation_id is not None and trace_id is not None
            
            log_test_result(
                "middleware_integration",
                success,
                {
                    "correlation_id_present": correlation_id is not None,
                    "trace_id_present": trace_id is not None,
                    "correlation_id": correlation_id,
                    "trace_id": trace_id
                }
            )
            return success
            
        else:
            log_test_result(
                "middleware_integration",
                False,
                {"status_code": response.status_code},
                f"HTTP {response.status_code}"
            )
            return False
            
    except Exception as e:
        log_test_result(
            "middleware_integration",
            False,
            {},
            str(e)
        )
        return False


def run_comprehensive_logging_tests():
    """Run all comprehensive logging tests."""
    print("🚀 Starting Task 13.1 - Comprehensive Logging Implementation Tests")
    print("=" * 80)
    
    # Test functions to run
    tests = [
        ("Logging Service Health", test_logging_service_health),
        ("Structured Logging API", test_structured_logging_api),
        ("Distributed Tracing", test_distributed_tracing),
        ("Performance Monitoring", test_performance_monitoring),
        ("Business Metrics", test_business_metrics),
        ("Error Tracking", test_error_tracking),
        ("Operation Statistics", test_operation_statistics),
        ("Logging Dashboard", test_logging_dashboard),
        ("Log Export", test_log_export),
        ("Middleware Integration", test_middleware_integration)
    ]
    
    # Run tests
    results = []
    for test_name, test_func in tests:
        print(f"\n📋 Running: {test_name}")
        try:
            result = test_func()
            results.append(result)
        except Exception as e:
            print(f"❌ FAIL {test_name}: {e}")
            results.append(False)
    
    # Calculate summary
    passed = sum(results)
    total = len(results)
    success_rate = (passed / total) * 100
    
    print("\n" + "=" * 80)
    print("📊 COMPREHENSIVE LOGGING TEST SUMMARY")
    print("=" * 80)
    print(f"✅ Passed: {passed}/{total} ({success_rate:.1f}%)")
    print(f"❌ Failed: {total - passed}/{total}")
    
    # Overall assessment
    if success_rate >= 90:
        print("🎉 EXCELLENT: Comprehensive logging system is working excellently!")
    elif success_rate >= 75:
        print("✅ GOOD: Comprehensive logging system is working well with minor issues.")
    elif success_rate >= 50:
        print("⚠️  PARTIAL: Comprehensive logging system has significant issues.")
    else:
        print("❌ CRITICAL: Comprehensive logging system has major problems.")
    
    # Save detailed results
    TEST_RESULTS["summary"] = {
        "total_tests": total,
        "passed_tests": passed,
        "failed_tests": total - passed,
        "success_rate": success_rate,
        "overall_status": "excellent" if success_rate >= 90 else "good" if success_rate >= 75 else "partial" if success_rate >= 50 else "critical"
    }
    
    # Save results to file
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    results_file = f"comprehensive-logging-test-results-{timestamp}.json"
    
    with open(results_file, 'w') as f:
        json.dump(TEST_RESULTS, f, indent=2, default=str)
    
    print(f"\n📄 Detailed results saved to: {results_file}")
    
    return success_rate >= 75


if __name__ == "__main__":
    success = run_comprehensive_logging_tests()
    exit(0 if success else 1)