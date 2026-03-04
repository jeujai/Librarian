#!/usr/bin/env python3
"""
Analytics Functionality Test Script

This script tests the complete analytics system including:
- Analytics API endpoints
- Dashboard functionality
- Data generation and visualization
- Integration with document system
"""

import asyncio
import json
import time
import requests
from datetime import datetime
from typing import Dict, Any, List

class AnalyticsTestSuite:
    """Comprehensive test suite for analytics functionality."""
    
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url.rstrip('/')
        self.test_results = []
        self.start_time = time.time()
        
    def log_test(self, test_name: str, success: bool, details: str = "", response_time: float = 0):
        """Log test result."""
        result = {
            "test_name": test_name,
            "success": success,
            "details": details,
            "response_time_ms": round(response_time * 1000, 2),
            "timestamp": datetime.utcnow().isoformat()
        }
        self.test_results.append(result)
        
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status} {test_name}")
        if details:
            print(f"    {details}")
        if response_time > 0:
            print(f"    Response time: {result['response_time_ms']}ms")
        print()
    
    def test_analytics_health(self) -> bool:
        """Test analytics service health endpoint."""
        try:
            start_time = time.time()
            response = requests.get(f"{self.base_url}/api/analytics/health", timeout=10)
            response_time = time.time() - start_time
            
            if response.status_code == 200:
                data = response.json()
                if data.get("status") == "healthy":
                    self.log_test(
                        "Analytics Health Check",
                        True,
                        f"Service healthy with capabilities: {list(data.get('capabilities', {}).keys())}",
                        response_time
                    )
                    return True
                else:
                    self.log_test(
                        "Analytics Health Check",
                        False,
                        f"Service unhealthy: {data.get('status')}",
                        response_time
                    )
                    return False
            else:
                self.log_test(
                    "Analytics Health Check",
                    False,
                    f"HTTP {response.status_code}: {response.text[:100]}",
                    response_time
                )
                return False
                
        except Exception as e:
            self.log_test("Analytics Health Check", False, f"Request failed: {str(e)}")
            return False
    
    def test_document_statistics(self) -> bool:
        """Test document statistics endpoint."""
        try:
            start_time = time.time()
            response = requests.get(f"{self.base_url}/api/analytics/documents/statistics", timeout=15)
            response_time = time.time() - start_time
            
            if response.status_code == 200:
                data = response.json()
                if data.get("success"):
                    analytics_data = data.get("data", {})
                    overview = analytics_data.get("overview", {})
                    
                    self.log_test(
                        "Document Statistics",
                        True,
                        f"Retrieved stats for {overview.get('total_documents', 0)} documents, {overview.get('total_size_mb', 0)}MB total",
                        response_time
                    )
                    return True
                else:
                    self.log_test(
                        "Document Statistics",
                        False,
                        f"API returned error: {data.get('message')}",
                        response_time
                    )
                    return False
            else:
                self.log_test(
                    "Document Statistics",
                    False,
                    f"HTTP {response.status_code}: {response.text[:100]}",
                    response_time
                )
                return False
                
        except Exception as e:
            self.log_test("Document Statistics", False, f"Request failed: {str(e)}")
            return False
    
    def test_content_insights(self) -> bool:
        """Test content insights endpoint."""
        try:
            start_time = time.time()
            response = requests.get(f"{self.base_url}/api/analytics/content/insights", timeout=15)
            response_time = time.time() - start_time
            
            if response.status_code == 200:
                data = response.json()
                if data.get("success"):
                    insights_data = data.get("data", {})
                    content_overview = insights_data.get("content_overview", {})
                    keywords = insights_data.get("top_keywords", {})
                    
                    self.log_test(
                        "Content Insights",
                        True,
                        f"Generated insights for {content_overview.get('total_documents', 0)} documents with {len(keywords.get('titles', []))} title keywords",
                        response_time
                    )
                    return True
                else:
                    self.log_test(
                        "Content Insights",
                        False,
                        f"API returned error: {data.get('message')}",
                        response_time
                    )
                    return False
            else:
                self.log_test(
                    "Content Insights",
                    False,
                    f"HTTP {response.status_code}: {response.text[:100]}",
                    response_time
                )
                return False
                
        except Exception as e:
            self.log_test("Content Insights", False, f"Request failed: {str(e)}")
            return False
    
    def test_similarity_analysis(self) -> bool:
        """Test similarity analysis endpoint."""
        try:
            start_time = time.time()
            response = requests.get(f"{self.base_url}/api/analytics/similarity/analysis", timeout=15)
            response_time = time.time() - start_time
            
            if response.status_code == 200:
                data = response.json()
                if data.get("success"):
                    similarity_data = data.get("data", {})
                    overview = similarity_data.get("similarity_overview", {})
                    
                    self.log_test(
                        "Similarity Analysis",
                        True,
                        f"Found {overview.get('similar_pairs_found', 0)} similar pairs in {overview.get('total_documents', 0)} documents",
                        response_time
                    )
                    return True
                else:
                    self.log_test(
                        "Similarity Analysis",
                        False,
                        f"API returned error: {data.get('message')}",
                        response_time
                    )
                    return False
            else:
                self.log_test(
                    "Similarity Analysis",
                    False,
                    f"HTTP {response.status_code}: {response.text[:100]}",
                    response_time
                )
                return False
                
        except Exception as e:
            self.log_test("Similarity Analysis", False, f"Request failed: {str(e)}")
            return False
    
    def test_usage_analytics(self) -> bool:
        """Test usage analytics endpoint."""
        try:
            start_time = time.time()
            response = requests.get(f"{self.base_url}/api/analytics/usage/patterns", timeout=15)
            response_time = time.time() - start_time
            
            if response.status_code == 200:
                data = response.json()
                if data.get("success"):
                    usage_data = data.get("data", {})
                    overview = usage_data.get("usage_overview", {})
                    
                    self.log_test(
                        "Usage Analytics",
                        True,
                        f"Retrieved usage data: {overview.get('total_chat_sessions', 0)} chat sessions, {overview.get('total_document_views', 0)} document views",
                        response_time
                    )
                    return True
                else:
                    self.log_test(
                        "Usage Analytics",
                        False,
                        f"API returned error: {data.get('message')}",
                        response_time
                    )
                    return False
            else:
                self.log_test(
                    "Usage Analytics",
                    False,
                    f"HTTP {response.status_code}: {response.text[:100]}",
                    response_time
                )
                return False
                
        except Exception as e:
            self.log_test("Usage Analytics", False, f"Request failed: {str(e)}")
            return False
    
    def test_dashboard_summary(self) -> bool:
        """Test analytics dashboard summary endpoint."""
        try:
            start_time = time.time()
            response = requests.get(f"{self.base_url}/api/analytics/dashboard/summary", timeout=20)
            response_time = time.time() - start_time
            
            if response.status_code == 200:
                data = response.json()
                if data.get("success"):
                    dashboard_data = data.get("data", {})
                    overview = dashboard_data.get("overview", {})
                    charts_data = dashboard_data.get("charts_data", {})
                    
                    self.log_test(
                        "Dashboard Summary",
                        True,
                        f"Dashboard data includes {len(charts_data)} chart datasets and {len(overview)} overview metrics",
                        response_time
                    )
                    return True
                else:
                    self.log_test(
                        "Dashboard Summary",
                        False,
                        f"API returned error: {data.get('message')}",
                        response_time
                    )
                    return False
            else:
                self.log_test(
                    "Dashboard Summary",
                    False,
                    f"HTTP {response.status_code}: {response.text[:100]}",
                    response_time
                )
                return False
                
        except Exception as e:
            self.log_test("Dashboard Summary", False, f"Request failed: {str(e)}")
            return False
    
    def test_analytics_dashboard_page(self) -> bool:
        """Test analytics dashboard HTML page."""
        try:
            start_time = time.time()
            response = requests.get(f"{self.base_url}/analytics", timeout=10)
            response_time = time.time() - start_time
            
            if response.status_code == 200:
                html_content = response.text
                
                # Check for key dashboard elements
                required_elements = [
                    "Analytics Dashboard",
                    "chart.js",
                    "analytics_dashboard.js",
                    "analytics_dashboard.css",
                    "dashboard-container"
                ]
                
                missing_elements = [elem for elem in required_elements if elem not in html_content]
                
                if not missing_elements:
                    self.log_test(
                        "Analytics Dashboard Page",
                        True,
                        f"Dashboard HTML loaded successfully ({len(html_content)} chars)",
                        response_time
                    )
                    return True
                else:
                    self.log_test(
                        "Analytics Dashboard Page",
                        False,
                        f"Missing elements: {missing_elements}",
                        response_time
                    )
                    return False
            else:
                self.log_test(
                    "Analytics Dashboard Page",
                    False,
                    f"HTTP {response.status_code}: {response.text[:100]}",
                    response_time
                )
                return False
                
        except Exception as e:
            self.log_test("Analytics Dashboard Page", False, f"Request failed: {str(e)}")
            return False
    
    def test_static_assets(self) -> bool:
        """Test analytics static assets (CSS and JS)."""
        assets_to_test = [
            ("/static/css/analytics_dashboard.css", "CSS"),
            ("/static/js/analytics_dashboard.js", "JavaScript")
        ]
        
        all_assets_loaded = True
        
        for asset_path, asset_type in assets_to_test:
            try:
                start_time = time.time()
                response = requests.get(f"{self.base_url}{asset_path}", timeout=10)
                response_time = time.time() - start_time
                
                if response.status_code == 200:
                    content_length = len(response.text)
                    self.log_test(
                        f"Analytics {asset_type} Asset",
                        True,
                        f"Asset loaded successfully ({content_length} chars)",
                        response_time
                    )
                else:
                    self.log_test(
                        f"Analytics {asset_type} Asset",
                        False,
                        f"HTTP {response.status_code}: Asset not found",
                        response_time
                    )
                    all_assets_loaded = False
                    
            except Exception as e:
                self.log_test(f"Analytics {asset_type} Asset", False, f"Request failed: {str(e)}")
                all_assets_loaded = False
        
        return all_assets_loaded
    
    def test_integration_with_documents(self) -> bool:
        """Test analytics integration with document system."""
        try:
            # First check if document system is available
            doc_response = requests.get(f"{self.base_url}/api/documents/health", timeout=10)
            
            if doc_response.status_code != 200:
                self.log_test(
                    "Analytics-Document Integration",
                    False,
                    "Document system not available for integration test"
                )
                return False
            
            # Test analytics with document data
            start_time = time.time()
            analytics_response = requests.get(f"{self.base_url}/api/analytics/documents/statistics", timeout=15)
            response_time = time.time() - start_time
            
            if analytics_response.status_code == 200:
                data = analytics_response.json()
                if data.get("success"):
                    self.log_test(
                        "Analytics-Document Integration",
                        True,
                        "Analytics successfully integrated with document system",
                        response_time
                    )
                    return True
                else:
                    self.log_test(
                        "Analytics-Document Integration",
                        False,
                        f"Analytics integration failed: {data.get('message')}",
                        response_time
                    )
                    return False
            else:
                self.log_test(
                    "Analytics-Document Integration",
                    False,
                    f"Integration test failed: HTTP {analytics_response.status_code}",
                    response_time
                )
                return False
                
        except Exception as e:
            self.log_test("Analytics-Document Integration", False, f"Integration test failed: {str(e)}")
            return False
    
    def run_all_tests(self) -> Dict[str, Any]:
        """Run all analytics tests."""
        print("🚀 Starting Analytics Functionality Test Suite")
        print("=" * 60)
        print()
        
        # Test sequence
        tests = [
            ("Analytics Health Check", self.test_analytics_health),
            ("Document Statistics API", self.test_document_statistics),
            ("Content Insights API", self.test_content_insights),
            ("Similarity Analysis API", self.test_similarity_analysis),
            ("Usage Analytics API", self.test_usage_analytics),
            ("Dashboard Summary API", self.test_dashboard_summary),
            ("Analytics Dashboard Page", self.test_analytics_dashboard_page),
            ("Static Assets Loading", self.test_static_assets),
            ("Document System Integration", self.test_integration_with_documents)
        ]
        
        passed_tests = 0
        total_tests = len(tests)
        
        for test_name, test_func in tests:
            try:
                if test_func():
                    passed_tests += 1
            except Exception as e:
                self.log_test(test_name, False, f"Test execution failed: {str(e)}")
        
        # Calculate results
        success_rate = (passed_tests / total_tests) * 100
        total_time = time.time() - self.start_time
        
        # Generate summary
        summary = {
            "test_suite": "Analytics Functionality",
            "timestamp": datetime.utcnow().isoformat(),
            "total_tests": total_tests,
            "passed_tests": passed_tests,
            "failed_tests": total_tests - passed_tests,
            "success_rate": round(success_rate, 1),
            "total_time_seconds": round(total_time, 2),
            "test_results": self.test_results
        }
        
        # Print summary
        print("=" * 60)
        print("📊 ANALYTICS FUNCTIONALITY TEST RESULTS")
        print("=" * 60)
        print(f"✅ Passed: {passed_tests}/{total_tests} tests ({success_rate:.1f}%)")
        print(f"⏱️  Total time: {total_time:.2f} seconds")
        print(f"🎯 Status: {'SUCCESS' if success_rate >= 80 else 'NEEDS ATTENTION'}")
        print()
        
        if success_rate >= 80:
            print("🎉 Analytics system is working correctly!")
            print("📊 Dashboard available at: /analytics")
            print("🔗 API endpoints available at: /api/analytics/*")
        else:
            print("⚠️  Some analytics features need attention.")
            print("📋 Check individual test results above for details.")
        
        print()
        print("🔗 Quick Links:")
        print(f"   • Analytics Dashboard: {self.base_url}/analytics")
        print(f"   • API Documentation: {self.base_url}/docs")
        print(f"   • Health Check: {self.base_url}/api/analytics/health")
        
        return summary

def main():
    """Main test execution."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Test Analytics Functionality")
    parser.add_argument("--url", default="http://localhost:8000", help="Base URL for testing")
    parser.add_argument("--output", help="Output file for test results (JSON)")
    
    args = parser.parse_args()
    
    # Run tests
    test_suite = AnalyticsTestSuite(args.url)
    results = test_suite.run_all_tests()
    
    # Save results if requested
    if args.output:
        with open(args.output, 'w') as f:
            json.dump(results, f, indent=2)
        print(f"\n💾 Test results saved to: {args.output}")

if __name__ == "__main__":
    main()