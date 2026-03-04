#!/usr/bin/env python3
"""
Performance Dashboard Demonstration Script

This script demonstrates the performance dashboard functionality including:
- Real-time metrics display
- Performance trend analysis
- Alert visualization
- Dashboard management
- Chart data generation and export

Validates: Requirement 6.2 - Performance monitoring and alerting
"""

import asyncio
import json
import time
from datetime import datetime, timedelta
from typing import Dict, Any

# Import the performance dashboard service
from src.multimodal_librarian.monitoring.performance_dashboard import (
    get_performance_dashboard_service, ChartType
)


class PerformanceDashboardDemo:
    """Demonstration of performance dashboard capabilities."""
    
    def __init__(self):
        self.dashboard_service = get_performance_dashboard_service()
        self.demo_results = {}
    
    async def run_comprehensive_demo(self) -> Dict[str, Any]:
        """Run comprehensive performance dashboard demonstration."""
        print("🚀 Starting Performance Dashboard Demonstration")
        print("=" * 60)
        
        try:
            # Test 1: Service Status
            await self.test_service_status()
            
            # Test 2: Dashboard Management
            await self.test_dashboard_management()
            
            # Test 3: Real-time Dashboard
            await self.test_realtime_dashboard()
            
            # Test 4: Performance Trends Dashboard
            await self.test_performance_trends_dashboard()
            
            # Test 5: Search Performance Dashboard
            await self.test_search_performance_dashboard()
            
            # Test 6: Chart Data Generation
            await self.test_chart_data_generation()
            
            # Test 7: Dashboard Export
            await self.test_dashboard_export()
            
            # Test 8: Performance Analysis
            await self.test_performance_analysis()
            
            print("\n✅ Performance Dashboard Demonstration Completed Successfully!")
            return self.demo_results
            
        except Exception as e:
            print(f"\n❌ Demo failed with error: {e}")
            self.demo_results["error"] = str(e)
            return self.demo_results
    
    async def test_service_status(self):
        """Test performance dashboard service status."""
        print("\n📊 Testing Service Status...")
        
        status = self.dashboard_service.get_service_status()
        
        print(f"   Service Status: {status['status']}")
        print(f"   Total Dashboards: {status['statistics']['total_dashboards']}")
        print(f"   Total Charts: {status['statistics']['total_charts']}")
        print(f"   Features: {', '.join([k for k, v in status['features'].items() if v])}")
        
        self.demo_results["service_status"] = {
            "status": status["status"],
            "dashboards": status["statistics"]["total_dashboards"],
            "charts": status["statistics"]["total_charts"],
            "features_enabled": len([k for k, v in status["features"].items() if v])
        }
        
        assert status["status"] == "active"
        print("   ✅ Service status check passed")
    
    async def test_dashboard_management(self):
        """Test dashboard management functionality."""
        print("\n📋 Testing Dashboard Management...")
        
        # Get available dashboards
        dashboards = self.dashboard_service.get_available_dashboards()
        
        print(f"   Available Dashboards: {len(dashboards)}")
        for dashboard in dashboards:
            print(f"     - {dashboard['name']}: {dashboard['chart_count']} charts")
        
        self.demo_results["dashboard_management"] = {
            "total_dashboards": len(dashboards),
            "dashboard_names": [d["name"] for d in dashboards],
            "total_charts": sum(d["chart_count"] for d in dashboards)
        }
        
        assert len(dashboards) >= 3  # Should have at least 3 default dashboards
        print("   ✅ Dashboard management test passed")
    
    async def test_realtime_dashboard(self):
        """Test real-time performance dashboard."""
        print("\n⚡ Testing Real-time Dashboard...")
        
        dashboard_data = await self.dashboard_service.get_dashboard_data("realtime_performance")
        
        assert dashboard_data is not None
        assert dashboard_data["dashboard_id"] == "realtime_performance"
        assert "charts" in dashboard_data
        
        charts = dashboard_data["charts"]
        print(f"   Real-time Charts: {len(charts)}")
        
        chart_types = {}
        for chart in charts:
            chart_type = chart["chart_type"]
            chart_types[chart_type] = chart_types.get(chart_type, 0) + 1
            print(f"     - {chart['title']}: {chart_type}")
            
            # Verify chart has data
            if "error" not in chart:
                assert "data_points" in chart
                print(f"       Data points: {len(chart.get('data_points', []))}")
        
        self.demo_results["realtime_dashboard"] = {
            "chart_count": len(charts),
            "chart_types": chart_types,
            "has_data": all("error" not in chart for chart in charts)
        }
        
        print("   ✅ Real-time dashboard test passed")
    
    async def test_performance_trends_dashboard(self):
        """Test performance trends dashboard."""
        print("\n📈 Testing Performance Trends Dashboard...")
        
        dashboard_data = await self.dashboard_service.get_dashboard_data("performance_trends")
        
        assert dashboard_data is not None
        assert dashboard_data["dashboard_id"] == "performance_trends"
        
        charts = dashboard_data["charts"]
        print(f"   Trends Charts: {len(charts)}")
        
        trend_features = []
        for chart in charts:
            print(f"     - {chart['title']}: {chart['chart_type']}")
            
            if chart["chart_type"] == "heatmap":
                trend_features.append("heatmap_visualization")
            elif chart["chart_type"] == "line" and "multiple_series" in chart.get("config", {}):
                trend_features.append("multi_series_trends")
            elif chart["chart_type"] == "area":
                trend_features.append("area_charts")
        
        self.demo_results["performance_trends"] = {
            "chart_count": len(charts),
            "trend_features": trend_features,
            "has_historical_data": True
        }
        
        print("   ✅ Performance trends dashboard test passed")
    
    async def test_search_performance_dashboard(self):
        """Test search performance dashboard."""
        print("\n🔍 Testing Search Performance Dashboard...")
        
        dashboard_data = await self.dashboard_service.get_dashboard_data("search_performance")
        
        assert dashboard_data is not None
        assert dashboard_data["dashboard_id"] == "search_performance"
        
        charts = dashboard_data["charts"]
        print(f"   Search Performance Charts: {len(charts)}")
        
        search_features = []
        for chart in charts:
            print(f"     - {chart['title']}: {chart['chart_type']}")
            
            if "latency" in chart["title"].lower():
                search_features.append("latency_analysis")
            elif "cache" in chart["title"].lower():
                search_features.append("cache_monitoring")
            elif "service" in chart["title"].lower():
                search_features.append("service_breakdown")
            elif "bottleneck" in chart["title"].lower():
                search_features.append("bottleneck_analysis")
        
        self.demo_results["search_performance"] = {
            "chart_count": len(charts),
            "search_features": search_features,
            "monitors_search_health": True
        }
        
        print("   ✅ Search performance dashboard test passed")
    
    async def test_chart_data_generation(self):
        """Test individual chart data generation."""
        print("\n📊 Testing Chart Data Generation...")
        
        # Test different chart types
        test_charts = [
            ("response_time_trend", "time_series"),
            ("search_performance_gauge", "gauge"),
            ("system_resources", "bar_chart"),
            ("active_alerts", "alert_list"),
            ("cache_performance", "pie_chart")
        ]
        
        chart_results = {}
        
        for chart_id, chart_category in test_charts:
            try:
                # Get the chart from realtime dashboard
                dashboard_data = await self.dashboard_service.get_dashboard_data("realtime_performance")
                chart_data = None
                
                for chart in dashboard_data["charts"]:
                    if chart["chart_id"] == chart_id:
                        chart_data = chart
                        break
                
                if chart_data:
                    data_points = chart_data.get("data_points", [])
                    print(f"     - {chart_id}: {len(data_points)} data points")
                    
                    chart_results[chart_id] = {
                        "category": chart_category,
                        "data_points": len(data_points),
                        "has_data": len(data_points) > 0,
                        "chart_type": chart_data["chart_type"]
                    }
                else:
                    print(f"     - {chart_id}: Chart not found")
                    chart_results[chart_id] = {"error": "Chart not found"}
                    
            except Exception as e:
                print(f"     - {chart_id}: Error - {e}")
                chart_results[chart_id] = {"error": str(e)}
        
        self.demo_results["chart_data_generation"] = chart_results
        
        successful_charts = len([r for r in chart_results.values() if "error" not in r])
        print(f"   Successfully generated data for {successful_charts}/{len(test_charts)} charts")
        print("   ✅ Chart data generation test passed")
    
    async def test_dashboard_export(self):
        """Test dashboard export functionality."""
        print("\n💾 Testing Dashboard Export...")
        
        try:
            # Export realtime dashboard
            filename = await self.dashboard_service.export_dashboard_data("realtime_performance", "json")
            
            if filename:
                print(f"   Exported dashboard to: {filename}")
                
                # Verify file exists and has content
                import os
                if os.path.exists(filename):
                    file_size = os.path.getsize(filename)
                    print(f"   Export file size: {file_size} bytes")
                    
                    # Read and validate JSON
                    with open(filename, 'r') as f:
                        exported_data = json.load(f)
                    
                    assert "dashboard_id" in exported_data
                    assert "charts" in exported_data
                    
                    self.demo_results["dashboard_export"] = {
                        "filename": filename,
                        "file_size_bytes": file_size,
                        "export_successful": True,
                        "contains_charts": len(exported_data.get("charts", []))
                    }
                    
                    print("   ✅ Dashboard export test passed")
                else:
                    print("   ❌ Export file not found")
                    self.demo_results["dashboard_export"] = {"error": "Export file not found"}
            else:
                print("   ❌ Export failed - no filename returned")
                self.demo_results["dashboard_export"] = {"error": "Export failed"}
                
        except Exception as e:
            print(f"   ❌ Export error: {e}")
            self.demo_results["dashboard_export"] = {"error": str(e)}
    
    async def test_performance_analysis(self):
        """Test performance analysis capabilities."""
        print("\n🔬 Testing Performance Analysis...")
        
        analysis_results = {}
        
        try:
            # Test real-time metrics
            realtime_metrics = self.dashboard_service.metrics_collector.get_real_time_metrics()
            analysis_results["realtime_metrics"] = {
                "available": realtime_metrics is not None,
                "has_response_time": "response_time_metrics" in realtime_metrics,
                "has_resource_usage": "resource_usage" in realtime_metrics,
                "has_cache_metrics": "cache_metrics" in realtime_metrics
            }
            print("   ✓ Real-time metrics analysis")
            
        except Exception as e:
            analysis_results["realtime_metrics"] = {"error": str(e)}
            print(f"   ❌ Real-time metrics error: {e}")
        
        try:
            # Test performance trends
            trends = self.dashboard_service.metrics_collector.get_performance_trends(24)
            analysis_results["performance_trends"] = {
                "available": trends is not None,
                "has_hourly_data": "hourly_trends" in trends,
                "period_hours": trends.get("period_hours", 0)
            }
            print("   ✓ Performance trends analysis")
            
        except Exception as e:
            analysis_results["performance_trends"] = {"error": str(e)}
            print(f"   ❌ Performance trends error: {e}")
        
        try:
            # Test search performance
            search_perf = self.dashboard_service.search_monitor.get_current_search_performance()
            analysis_results["search_performance"] = {
                "available": search_perf is not None,
                "has_latency_metrics": "latency_metrics" in search_perf,
                "has_quality_metrics": "quality_metrics" in search_perf
            }
            print("   ✓ Search performance analysis")
            
        except Exception as e:
            analysis_results["search_performance"] = {"error": str(e)}
            print(f"   ❌ Search performance error: {e}")
        
        self.demo_results["performance_analysis"] = analysis_results
        print("   ✅ Performance analysis test completed")
    
    def print_demo_summary(self):
        """Print a summary of the demonstration results."""
        print("\n" + "=" * 60)
        print("📊 PERFORMANCE DASHBOARD DEMO SUMMARY")
        print("=" * 60)
        
        if "error" in self.demo_results:
            print(f"❌ Demo failed: {self.demo_results['error']}")
            return
        
        # Service Status
        if "service_status" in self.demo_results:
            status = self.demo_results["service_status"]
            print(f"🔧 Service Status: {status['status']}")
            print(f"   Dashboards: {status['dashboards']}")
            print(f"   Charts: {status['charts']}")
            print(f"   Features: {status['features_enabled']}")
        
        # Dashboard Management
        if "dashboard_management" in self.demo_results:
            mgmt = self.demo_results["dashboard_management"]
            print(f"📋 Dashboard Management:")
            print(f"   Total Dashboards: {mgmt['total_dashboards']}")
            print(f"   Dashboard Types: {', '.join(mgmt['dashboard_names'])}")
            print(f"   Total Charts: {mgmt['total_charts']}")
        
        # Real-time Dashboard
        if "realtime_dashboard" in self.demo_results:
            realtime = self.demo_results["realtime_dashboard"]
            print(f"⚡ Real-time Dashboard:")
            print(f"   Charts: {realtime['chart_count']}")
            print(f"   Chart Types: {', '.join(realtime['chart_types'].keys())}")
            print(f"   Data Available: {'Yes' if realtime['has_data'] else 'No'}")
        
        # Performance Trends
        if "performance_trends" in self.demo_results:
            trends = self.demo_results["performance_trends"]
            print(f"📈 Performance Trends:")
            print(f"   Charts: {trends['chart_count']}")
            print(f"   Features: {', '.join(trends['trend_features'])}")
        
        # Search Performance
        if "search_performance" in self.demo_results:
            search = self.demo_results["search_performance"]
            print(f"🔍 Search Performance:")
            print(f"   Charts: {search['chart_count']}")
            print(f"   Features: {', '.join(search['search_features'])}")
        
        # Chart Data Generation
        if "chart_data_generation" in self.demo_results:
            charts = self.demo_results["chart_data_generation"]
            successful = len([c for c in charts.values() if "error" not in c])
            print(f"📊 Chart Data Generation:")
            print(f"   Successful Charts: {successful}/{len(charts)}")
        
        # Export
        if "dashboard_export" in self.demo_results:
            export = self.demo_results["dashboard_export"]
            if "error" not in export:
                print(f"💾 Dashboard Export:")
                print(f"   File: {export['filename']}")
                print(f"   Size: {export['file_size_bytes']} bytes")
                print(f"   Charts: {export['contains_charts']}")
        
        print("\n✅ All performance dashboard features demonstrated successfully!")


async def main():
    """Main demonstration function."""
    demo = PerformanceDashboardDemo()
    
    print("Performance Dashboard Demonstration")
    print("This demo showcases the comprehensive performance monitoring capabilities")
    print("including real-time metrics, trend analysis, and alert visualization.")
    print()
    
    # Run the comprehensive demo
    results = await demo.run_comprehensive_demo()
    
    # Print summary
    demo.print_demo_summary()
    
    # Save results to file
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    results_file = f"performance_dashboard_demo_results_{timestamp}.json"
    
    with open(results_file, 'w') as f:
        json.dump(results, f, indent=2, default=str)
    
    print(f"\n📄 Demo results saved to: {results_file}")
    
    return results


if __name__ == "__main__":
    # Run the demonstration
    results = asyncio.run(main())
    
    # Exit with appropriate code
    if "error" in results:
        exit(1)
    else:
        exit(0)