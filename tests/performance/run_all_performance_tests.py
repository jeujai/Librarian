#!/usr/bin/env python3
"""
Comprehensive Performance Test Runner for AWS Learning Deployment

This script orchestrates all performance tests including basic load testing,
chat interface testing, and ML training performance testing. It provides
comprehensive reporting and analysis suitable for learning environments.

Features:
- Automated test execution with configurable parameters
- Comprehensive result aggregation and analysis
- Performance trend analysis and recommendations
- Cost optimization insights
- Integration with CloudWatch metrics
"""

import os
import sys
import asyncio
import json
import time
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
import argparse

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from multimodal_librarian.logging_config import get_logger

# Import test modules
from basic_load_test import run_basic_load_test
from chat_basic_load_test import run_chat_load_test
from ml_training_basic_test import run_ml_performance_test


@dataclass
class PerformanceTestSuite:
    """Configuration for performance test suite."""
    base_url: str
    websocket_url: str
    concurrent_users: int
    test_duration: int
    output_directory: str
    run_basic_tests: bool = True
    run_chat_tests: bool = True
    run_ml_tests: bool = True
    save_individual_results: bool = True
    generate_summary_report: bool = True


class ComprehensivePerformanceTester:
    """Comprehensive performance test orchestrator."""
    
    def __init__(self, config: PerformanceTestSuite):
        self.config = config
        self.logger = get_logger("comprehensive_performance_tester")
        
        # Ensure output directory exists
        os.makedirs(config.output_directory, exist_ok=True)
        
        # Test results storage
        self.test_results = {
            "suite_start_time": None,
            "suite_end_time": None,
            "suite_duration_seconds": 0,
            "configuration": asdict(config),
            "basic_load_results": None,
            "chat_performance_results": None,
            "ml_performance_results": None,
            "suite_summary": {},
            "recommendations": [],
            "cost_analysis": {},
            "performance_trends": {}
        }
        
        self.logger.info(f"Initialized comprehensive performance tester")
        self.logger.info(f"Target URL: {config.base_url}")
        self.logger.info(f"Output directory: {config.output_directory}")
    
    async def run_comprehensive_tests(self) -> Dict[str, Any]:
        """Run comprehensive performance test suite."""
        self.logger.info("🚀 Starting comprehensive performance test suite")
        
        self.test_results["suite_start_time"] = datetime.now()
        
        print("=" * 100)
        print("🚀 COMPREHENSIVE PERFORMANCE TEST SUITE")
        print("=" * 100)
        print(f"📅 Started: {self.test_results['suite_start_time'].isoformat()}")
        print(f"🎯 Target: {self.config.base_url}")
        print(f"👥 Concurrent Users: {self.config.concurrent_users}")
        print(f"⏱️  Test Duration: {self.config.test_duration}s")
        print(f"📁 Output Directory: {self.config.output_directory}")
        print()
        
        # Run test suites
        if self.config.run_basic_tests:
            await self._run_basic_load_tests()
        
        if self.config.run_chat_tests:
            await self._run_chat_performance_tests()
        
        if self.config.run_ml_tests:
            await self._run_ml_performance_tests()
        
        # Calculate suite summary
        self.test_results["suite_end_time"] = datetime.now()
        self.test_results["suite_duration_seconds"] = (
            self.test_results["suite_end_time"] - self.test_results["suite_start_time"]
        ).total_seconds()
        
        # Generate comprehensive analysis
        self._generate_suite_summary()
        self._generate_recommendations()
        self._analyze_cost_performance()
        
        # Save comprehensive report
        if self.config.generate_summary_report:
            await self._save_comprehensive_report()
        
        # Print final summary
        self._print_comprehensive_summary()
        
        return self.test_results
    
    async def _run_basic_load_tests(self):
        """Run basic load testing suite."""
        print("📋 [1/3] BASIC LOAD TESTING")
        print("   Testing API endpoints and general system performance")
        print("-" * 80)
        
        try:
            # Configure output file
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_file = None
            if self.config.save_individual_results:
                output_file = os.path.join(
                    self.config.output_directory, 
                    f"basic_load_test_{timestamp}.json"
                )
            
            # Run basic load tests
            results = await run_basic_load_test(
                base_url=self.config.base_url,
                concurrent_users=self.config.concurrent_users,
                test_duration=self.config.test_duration,
                output_file=output_file
            )
            
            self.test_results["basic_load_results"] = results
            
            # Print summary
            summary = results.get("summary", {})
            success_rate = summary.get("overall_success_rate", 0)
            avg_response_time = summary.get("average_response_time_ms", 0)
            
            status_icon = "✅" if success_rate >= 95 else "⚠️" if success_rate >= 85 else "❌"
            print(f"{status_icon} Basic Load Tests Completed")
            print(f"   Success Rate: {success_rate:.1f}%")
            print(f"   Avg Response Time: {avg_response_time:.1f}ms")
            print(f"   Total Requests: {summary.get('total_requests', 0)}")
            
        except Exception as e:
            self.logger.error(f"Error in basic load tests: {e}")
            print(f"❌ Basic Load Tests Failed: {e}")
            self.test_results["basic_load_results"] = {"error": str(e)}
        
        print()
    
    async def _run_chat_performance_tests(self):
        """Run chat interface performance testing."""
        print("📋 [2/3] CHAT PERFORMANCE TESTING")
        print("   Testing WebSocket connections and real-time messaging")
        print("-" * 80)
        
        try:
            # Configure output file
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_file = None
            if self.config.save_individual_results:
                output_file = os.path.join(
                    self.config.output_directory, 
                    f"chat_performance_{timestamp}.json"
                )
            
            # Run chat performance tests
            results = await run_chat_load_test(
                base_url=self.config.base_url,
                websocket_url=self.config.websocket_url,
                concurrent_users=self.config.concurrent_users,
                test_duration=self.config.test_duration,
                messages_per_user=10,
                output_file=output_file
            )
            
            self.test_results["chat_performance_results"] = results
            
            # Print summary
            summary = results.get("summary", {})
            connection_success = summary.get("overall_connection_success_rate", 0)
            message_delivery = summary.get("overall_message_delivery_rate", 0)
            avg_latency = summary.get("average_message_latency_ms", 0)
            
            status_icon = "✅" if connection_success >= 90 and message_delivery >= 90 else "⚠️" if connection_success >= 80 else "❌"
            print(f"{status_icon} Chat Performance Tests Completed")
            print(f"   Connection Success: {connection_success:.1f}%")
            print(f"   Message Delivery: {message_delivery:.1f}%")
            print(f"   Avg Latency: {avg_latency:.1f}ms")
            print(f"   Total Messages: {summary.get('total_messages_sent', 0)}")
            
        except Exception as e:
            self.logger.error(f"Error in chat performance tests: {e}")
            print(f"❌ Chat Performance Tests Failed: {e}")
            self.test_results["chat_performance_results"] = {"error": str(e)}
        
        print()
    
    async def _run_ml_performance_tests(self):
        """Run ML training performance testing."""
        print("📋 [3/3] ML TRAINING PERFORMANCE TESTING")
        print("   Testing ML APIs and processing pipelines")
        print("-" * 80)
        
        try:
            # Configure output file
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_file = None
            if self.config.save_individual_results:
                output_file = os.path.join(
                    self.config.output_directory, 
                    f"ml_performance_{timestamp}.json"
                )
            
            # Run ML performance tests (reduced concurrency for learning environment)
            concurrent_ops = min(5, self.config.concurrent_users // 2)
            results = await run_ml_performance_test(
                base_url=self.config.base_url,
                concurrent_operations=concurrent_ops,
                operations_per_test=8,
                test_duration=self.config.test_duration,
                output_file=output_file
            )
            
            self.test_results["ml_performance_results"] = results
            
            # Print summary
            summary = results.get("summary", {})
            success_rate = summary.get("overall_success_rate", 0)
            avg_processing_time = summary.get("average_processing_time_ms", 0)
            throughput = summary.get("average_throughput_ops_per_sec", 0)
            
            status_icon = "✅" if success_rate >= 85 else "⚠️" if success_rate >= 75 else "❌"
            print(f"{status_icon} ML Performance Tests Completed")
            print(f"   Success Rate: {success_rate:.1f}%")
            print(f"   Avg Processing Time: {avg_processing_time:.1f}ms")
            print(f"   Throughput: {throughput:.1f} ops/sec")
            print(f"   Total Operations: {summary.get('total_operations', 0)}")
            
        except Exception as e:
            self.logger.error(f"Error in ML performance tests: {e}")
            print(f"❌ ML Performance Tests Failed: {e}")
            self.test_results["ml_performance_results"] = {"error": str(e)}
        
        print()
    
    def _generate_suite_summary(self):
        """Generate comprehensive suite summary."""
        summary = {
            "overall_status": "unknown",
            "total_test_suites": 0,
            "successful_test_suites": 0,
            "failed_test_suites": 0,
            "overall_performance_score": 0,
            "key_metrics": {},
            "performance_categories": {}
        }
        
        # Count test suites
        test_suites = ["basic_load_results", "chat_performance_results", "ml_performance_results"]
        
        for suite_name in test_suites:
            suite_results = self.test_results.get(suite_name)
            if suite_results and "error" not in suite_results:
                summary["total_test_suites"] += 1
                
                # Determine if suite was successful
                if suite_name == "basic_load_results":
                    suite_summary = suite_results.get("summary", {})
                    success_rate = suite_summary.get("overall_success_rate", 0)
                    if success_rate >= 85:
                        summary["successful_test_suites"] += 1
                    else:
                        summary["failed_test_suites"] += 1
                
                elif suite_name == "chat_performance_results":
                    suite_summary = suite_results.get("summary", {})
                    connection_success = suite_summary.get("overall_connection_success_rate", 0)
                    message_delivery = suite_summary.get("overall_message_delivery_rate", 0)
                    if connection_success >= 80 and message_delivery >= 80:
                        summary["successful_test_suites"] += 1
                    else:
                        summary["failed_test_suites"] += 1
                
                elif suite_name == "ml_performance_results":
                    suite_summary = suite_results.get("summary", {})
                    success_rate = suite_summary.get("overall_success_rate", 0)
                    if success_rate >= 75:
                        summary["successful_test_suites"] += 1
                    else:
                        summary["failed_test_suites"] += 1
            else:
                summary["total_test_suites"] += 1
                summary["failed_test_suites"] += 1
        
        # Calculate overall status
        if summary["failed_test_suites"] == 0:
            summary["overall_status"] = "excellent"
        elif summary["successful_test_suites"] > summary["failed_test_suites"]:
            summary["overall_status"] = "good"
        elif summary["successful_test_suites"] > 0:
            summary["overall_status"] = "acceptable"
        else:
            summary["overall_status"] = "poor"
        
        # Calculate performance score (0-100)
        if summary["total_test_suites"] > 0:
            summary["overall_performance_score"] = (
                summary["successful_test_suites"] / summary["total_test_suites"]
            ) * 100
        
        # Extract key metrics
        self._extract_key_metrics(summary)
        
        self.test_results["suite_summary"] = summary
    
    def _extract_key_metrics(self, summary: Dict[str, Any]):
        """Extract key performance metrics from all test results."""
        key_metrics = {}
        
        # Basic load test metrics
        basic_results = self.test_results.get("basic_load_results")
        if basic_results and "error" not in basic_results:
            basic_summary = basic_results.get("summary", {})
            key_metrics.update({
                "api_success_rate_percent": basic_summary.get("overall_success_rate", 0),
                "api_avg_response_time_ms": basic_summary.get("average_response_time_ms", 0),
                "api_requests_per_second": basic_summary.get("average_requests_per_second", 0),
                "api_total_requests": basic_summary.get("total_requests", 0)
            })
        
        # Chat performance metrics
        chat_results = self.test_results.get("chat_performance_results")
        if chat_results and "error" not in chat_results:
            chat_summary = chat_results.get("summary", {})
            key_metrics.update({
                "chat_connection_success_rate_percent": chat_summary.get("overall_connection_success_rate", 0),
                "chat_message_delivery_rate_percent": chat_summary.get("overall_message_delivery_rate", 0),
                "chat_avg_latency_ms": chat_summary.get("average_message_latency_ms", 0),
                "chat_total_messages": chat_summary.get("total_messages_sent", 0)
            })
        
        # ML performance metrics
        ml_results = self.test_results.get("ml_performance_results")
        if ml_results and "error" not in ml_results:
            ml_summary = ml_results.get("summary", {})
            key_metrics.update({
                "ml_success_rate_percent": ml_summary.get("overall_success_rate", 0),
                "ml_avg_processing_time_ms": ml_summary.get("average_processing_time_ms", 0),
                "ml_throughput_ops_per_sec": ml_summary.get("average_throughput_ops_per_sec", 0),
                "ml_total_operations": ml_summary.get("total_operations", 0)
            })
        
        summary["key_metrics"] = key_metrics
        
        # Categorize performance
        performance_categories = {
            "api_performance": self._categorize_performance(
                key_metrics.get("api_success_rate_percent", 0),
                key_metrics.get("api_avg_response_time_ms", 0),
                success_threshold=90, response_time_threshold=500
            ),
            "chat_performance": self._categorize_performance(
                key_metrics.get("chat_connection_success_rate_percent", 0),
                key_metrics.get("chat_avg_latency_ms", 0),
                success_threshold=85, response_time_threshold=300
            ),
            "ml_performance": self._categorize_performance(
                key_metrics.get("ml_success_rate_percent", 0),
                key_metrics.get("ml_avg_processing_time_ms", 0),
                success_threshold=80, response_time_threshold=5000
            )
        }
        
        summary["performance_categories"] = performance_categories
    
    def _categorize_performance(self, success_rate: float, response_time: float, 
                              success_threshold: float, response_time_threshold: float) -> str:
        """Categorize performance based on success rate and response time."""
        if success_rate >= success_threshold and response_time <= response_time_threshold:
            return "excellent"
        elif success_rate >= success_threshold * 0.9 and response_time <= response_time_threshold * 1.5:
            return "good"
        elif success_rate >= success_threshold * 0.8 and response_time <= response_time_threshold * 2:
            return "acceptable"
        else:
            return "poor"
    
    def _generate_recommendations(self):
        """Generate performance optimization recommendations."""
        recommendations = []
        
        # Analyze basic load test results
        basic_results = self.test_results.get("basic_load_results")
        if basic_results and "error" not in basic_results:
            basic_summary = basic_results.get("summary", {})
            
            if basic_summary.get("overall_success_rate", 0) < 90:
                recommendations.append({
                    "category": "API Performance",
                    "priority": "high",
                    "issue": "Low API success rate",
                    "recommendation": "Review error logs and optimize API endpoints",
                    "expected_improvement": "Increase success rate to >95%"
                })
            
            if basic_summary.get("average_response_time_ms", 0) > 500:
                recommendations.append({
                    "category": "API Performance",
                    "priority": "medium",
                    "issue": "High API response times",
                    "recommendation": "Implement caching and optimize database queries",
                    "expected_improvement": "Reduce response times to <300ms"
                })
        
        # Analyze chat performance results
        chat_results = self.test_results.get("chat_performance_results")
        if chat_results and "error" not in chat_results:
            chat_summary = chat_results.get("summary", {})
            
            if chat_summary.get("overall_connection_success_rate", 0) < 85:
                recommendations.append({
                    "category": "Chat Performance",
                    "priority": "high",
                    "issue": "WebSocket connection failures",
                    "recommendation": "Review load balancer WebSocket configuration and connection limits",
                    "expected_improvement": "Increase connection success rate to >90%"
                })
            
            if chat_summary.get("average_message_latency_ms", 0) > 300:
                recommendations.append({
                    "category": "Chat Performance",
                    "priority": "medium",
                    "issue": "High message latency",
                    "recommendation": "Optimize WebSocket message processing and reduce network overhead",
                    "expected_improvement": "Reduce message latency to <200ms"
                })
        
        # Analyze ML performance results
        ml_results = self.test_results.get("ml_performance_results")
        if ml_results and "error" not in ml_results:
            ml_summary = ml_results.get("summary", {})
            
            if ml_summary.get("overall_success_rate", 0) < 80:
                recommendations.append({
                    "category": "ML Performance",
                    "priority": "high",
                    "issue": "ML operation failures",
                    "recommendation": "Review ML pipeline error handling and resource allocation",
                    "expected_improvement": "Increase ML success rate to >85%"
                })
            
            if ml_summary.get("average_processing_time_ms", 0) > 8000:
                recommendations.append({
                    "category": "ML Performance",
                    "priority": "medium",
                    "issue": "Slow ML processing",
                    "recommendation": "Optimize ML algorithms and consider GPU acceleration",
                    "expected_improvement": "Reduce processing times to <5000ms"
                })
        
        # General recommendations
        if not recommendations:
            recommendations.append({
                "category": "General",
                "priority": "low",
                "issue": "No critical issues detected",
                "recommendation": "Continue monitoring and consider advanced optimizations",
                "expected_improvement": "Maintain current performance levels"
            })
        
        self.test_results["recommendations"] = recommendations
    
    def _analyze_cost_performance(self):
        """Analyze cost vs performance trade-offs."""
        cost_analysis = {
            "estimated_hourly_cost_usd": 0.15,  # Learning environment estimate
            "performance_per_dollar": {},
            "cost_optimization_opportunities": [],
            "scaling_recommendations": []
        }
        
        # Calculate performance per dollar metrics
        key_metrics = self.test_results["suite_summary"].get("key_metrics", {})
        
        if key_metrics.get("api_requests_per_second", 0) > 0:
            cost_analysis["performance_per_dollar"]["requests_per_dollar_per_hour"] = (
                key_metrics["api_requests_per_second"] * 3600 / cost_analysis["estimated_hourly_cost_usd"]
            )
        
        if key_metrics.get("ml_throughput_ops_per_sec", 0) > 0:
            cost_analysis["performance_per_dollar"]["ml_ops_per_dollar_per_hour"] = (
                key_metrics["ml_throughput_ops_per_sec"] * 3600 / cost_analysis["estimated_hourly_cost_usd"]
            )
        
        # Cost optimization opportunities
        if key_metrics.get("api_success_rate_percent", 0) < 95:
            cost_analysis["cost_optimization_opportunities"].append(
                "Improve API reliability to reduce retry costs and user frustration"
            )
        
        if key_metrics.get("api_avg_response_time_ms", 0) > 500:
            cost_analysis["cost_optimization_opportunities"].append(
                "Implement caching to reduce compute costs and improve response times"
            )
        
        # Scaling recommendations
        performance_score = self.test_results["suite_summary"].get("overall_performance_score", 0)
        
        if performance_score >= 90:
            cost_analysis["scaling_recommendations"].append(
                "System performing well - consider cost optimization through right-sizing"
            )
        elif performance_score >= 75:
            cost_analysis["scaling_recommendations"].append(
                "Good performance - monitor for scaling opportunities"
            )
        else:
            cost_analysis["scaling_recommendations"].append(
                "Performance issues detected - address before scaling"
            )
        
        self.test_results["cost_analysis"] = cost_analysis
    
    async def _save_comprehensive_report(self):
        """Save comprehensive performance test report."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_file = os.path.join(
            self.config.output_directory,
            f"comprehensive_performance_report_{timestamp}.json"
        )
        
        try:
            # Convert datetime objects to strings for JSON serialization
            report_data = json.loads(json.dumps(self.test_results, default=str))
            
            with open(report_file, 'w') as f:
                json.dump(report_data, f, indent=2)
            
            print(f"📄 Comprehensive report saved to: {report_file}")
            
        except Exception as e:
            self.logger.error(f"Could not save comprehensive report: {e}")
            print(f"⚠️  Could not save comprehensive report: {e}")
    
    def _print_comprehensive_summary(self):
        """Print comprehensive test suite summary."""
        summary = self.test_results["suite_summary"]
        key_metrics = summary.get("key_metrics", {})
        
        print("=" * 100)
        print("📊 COMPREHENSIVE PERFORMANCE TEST SUMMARY")
        print("=" * 100)
        print(f"⏱️  Total Duration: {self.test_results['suite_duration_seconds']:.1f} seconds")
        print(f"🎯 Overall Status: {summary.get('overall_status', 'unknown').upper()}")
        print(f"📈 Performance Score: {summary.get('overall_performance_score', 0):.1f}/100")
        print()
        
        print("📋 Test Suite Results:")
        print(f"   Total Suites: {summary.get('total_test_suites', 0)}")
        print(f"   ✅ Successful: {summary.get('successful_test_suites', 0)}")
        print(f"   ❌ Failed: {summary.get('failed_test_suites', 0)}")
        print()
        
        print("🔍 Key Performance Metrics:")
        if key_metrics.get("api_success_rate_percent") is not None:
            print(f"   API Success Rate: {key_metrics['api_success_rate_percent']:.1f}%")
            print(f"   API Response Time: {key_metrics['api_avg_response_time_ms']:.1f}ms")
            print(f"   API Throughput: {key_metrics['api_requests_per_second']:.1f} RPS")
        
        if key_metrics.get("chat_connection_success_rate_percent") is not None:
            print(f"   Chat Connection Success: {key_metrics['chat_connection_success_rate_percent']:.1f}%")
            print(f"   Chat Message Latency: {key_metrics['chat_avg_latency_ms']:.1f}ms")
        
        if key_metrics.get("ml_success_rate_percent") is not None:
            print(f"   ML Success Rate: {key_metrics['ml_success_rate_percent']:.1f}%")
            print(f"   ML Processing Time: {key_metrics['ml_avg_processing_time_ms']:.1f}ms")
        print()
        
        print("💡 Top Recommendations:")
        recommendations = self.test_results.get("recommendations", [])
        for i, rec in enumerate(recommendations[:3], 1):
            priority_icon = "🔴" if rec["priority"] == "high" else "🟡" if rec["priority"] == "medium" else "🟢"
            print(f"   {i}. {priority_icon} {rec['category']}: {rec['recommendation']}")
        print()
        
        print("💰 Cost Analysis:")
        cost_analysis = self.test_results.get("cost_analysis", {})
        print(f"   Estimated Hourly Cost: ${cost_analysis.get('estimated_hourly_cost_usd', 0):.2f}")
        
        perf_per_dollar = cost_analysis.get("performance_per_dollar", {})
        if perf_per_dollar.get("requests_per_dollar_per_hour"):
            print(f"   Requests per $/hour: {perf_per_dollar['requests_per_dollar_per_hour']:.0f}")
        print()
        
        # Overall assessment
        performance_score = summary.get("overall_performance_score", 0)
        if performance_score >= 90:
            print("🎉 EXCELLENT OVERALL PERFORMANCE - System is performing very well!")
        elif performance_score >= 75:
            print("✅ GOOD OVERALL PERFORMANCE - System is performing well with minor issues")
        elif performance_score >= 60:
            print("⚠️  ACCEPTABLE PERFORMANCE - System has some performance issues to address")
        else:
            print("❌ POOR PERFORMANCE - System has significant performance issues")
        
        print("=" * 100)


async def main():
    """Main performance test runner function."""
    parser = argparse.ArgumentParser(description='Run Comprehensive Performance Tests')
    parser.add_argument('--url', type=str, default='http://localhost:8000',
                       help='Base HTTP URL for testing')
    parser.add_argument('--ws-url', type=str, default='ws://localhost:8000',
                       help='WebSocket URL for testing')
    parser.add_argument('--users', type=int, default=10,
                       help='Number of concurrent users')
    parser.add_argument('--duration', type=int, default=60,
                       help='Test duration in seconds')
    parser.add_argument('--output-dir', type=str, 
                       default='monitoring/performance-reports-basic',
                       help='Output directory for test results')
    parser.add_argument('--skip-basic', action='store_true',
                       help='Skip basic load tests')
    parser.add_argument('--skip-chat', action='store_true',
                       help='Skip chat performance tests')
    parser.add_argument('--skip-ml', action='store_true',
                       help='Skip ML performance tests')
    parser.add_argument('--no-individual-results', action='store_true',
                       help='Do not save individual test results')
    parser.add_argument('--no-summary', action='store_true',
                       help='Do not generate summary report')
    
    args = parser.parse_args()
    
    # Create test configuration
    config = PerformanceTestSuite(
        base_url=args.url,
        websocket_url=args.ws_url,
        concurrent_users=args.users,
        test_duration=args.duration,
        output_directory=args.output_dir,
        run_basic_tests=not args.skip_basic,
        run_chat_tests=not args.skip_chat,
        run_ml_tests=not args.skip_ml,
        save_individual_results=not args.no_individual_results,
        generate_summary_report=not args.no_summary
    )
    
    # Run comprehensive tests
    tester = ComprehensivePerformanceTester(config)
    results = await tester.run_comprehensive_tests()
    
    # Exit with appropriate code based on overall performance
    performance_score = results["suite_summary"].get("overall_performance_score", 0)
    
    if performance_score >= 85:
        exit(0)  # Excellent performance
    elif performance_score >= 70:
        exit(1)  # Good performance with warnings
    elif performance_score >= 50:
        exit(2)  # Acceptable performance with issues
    else:
        exit(3)  # Poor performance


if __name__ == "__main__":
    asyncio.run(main())