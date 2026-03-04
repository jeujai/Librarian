#!/usr/bin/env python3
"""
Demonstration script for comprehensive metrics collection system.

This script demonstrates the comprehensive metrics collection capabilities including:
- Response time tracking
- Resource usage monitoring  
- User session metrics
- Search performance tracking
- Document processing metrics
- Real-time analytics and reporting
"""

import asyncio
import time
import random
import json
from datetime import datetime, timedelta
from typing import List, Dict, Any

# Import the comprehensive metrics system
from src.multimodal_librarian.monitoring.comprehensive_metrics_collector import ComprehensiveMetricsCollector
from src.multimodal_librarian.monitoring.metrics_integration import (
    initialize_metrics_integration,
    track_response_time,
    track_search_performance,
    track_document_processing,
    MetricsContext,
    SearchMetricsHelper,
    DocumentMetricsHelper,
    record_cache_hit,
    record_cache_miss
)


class MetricsDemo:
    """Demonstration of comprehensive metrics collection."""
    
    def __init__(self):
        self.collector = ComprehensiveMetricsCollector()
        initialize_metrics_integration(self.collector)
        self.demo_users = ["user1", "user2", "user3", "user4", "user5"]
        self.demo_queries = [
            "machine learning algorithms",
            "data science techniques",
            "artificial intelligence",
            "neural networks",
            "deep learning",
            "natural language processing",
            "computer vision",
            "reinforcement learning"
        ]
        self.demo_documents = [
            {"id": "doc1", "size_mb": 1.2, "name": "ML_Research_Paper.pdf"},
            {"id": "doc2", "size_mb": 2.8, "name": "AI_Handbook.pdf"},
            {"id": "doc3", "size_mb": 0.5, "name": "Quick_Guide.pdf"},
            {"id": "doc4", "size_mb": 4.1, "name": "Comprehensive_Study.pdf"},
            {"id": "doc5", "size_mb": 1.8, "name": "Technical_Manual.pdf"}
        ]
    
    async def simulate_api_requests(self, num_requests: int = 50):
        """Simulate various API requests with response time tracking."""
        print(f"🌐 Simulating {num_requests} API requests...")
        
        endpoints = [
            ("/api/search", "POST"),
            ("/api/documents", "GET"),
            ("/api/documents/upload", "POST"),
            ("/api/chat", "POST"),
            ("/api/users/profile", "GET"),
            ("/api/analytics", "GET")
        ]
        
        for i in range(num_requests):
            endpoint, method = random.choice(endpoints)
            user_id = random.choice(self.demo_users)
            
            # Simulate varying response times
            base_time = random.uniform(50, 300)  # 50-300ms base
            if "search" in endpoint:
                base_time += random.uniform(100, 500)  # Search takes longer
            elif "upload" in endpoint:
                base_time += random.uniform(500, 2000)  # Upload takes much longer
            
            # Simulate occasional errors
            status_code = 200
            if random.random() < 0.05:  # 5% error rate
                status_code = random.choice([400, 404, 500])
                base_time *= 0.5  # Errors typically fail faster
            
            # Record the metric
            self.collector.record_response_time(
                endpoint=endpoint,
                method=method,
                response_time_ms=base_time,
                status_code=status_code,
                user_id=user_id,
                user_agent=f"DemoClient/1.0 ({user_id})"
            )
            
            # Record user session activity
            session_id = f"session_{user_id}_{i // 10}"  # Group requests into sessions
            self.collector.record_user_session_activity(
                session_id=session_id,
                user_id=user_id,
                endpoint=endpoint,
                response_time_ms=base_time,
                user_agent=f"DemoClient/1.0 ({user_id})",
                ip_address=f"192.168.1.{random.randint(1, 100)}"
            )
            
            # Small delay to spread out requests
            await asyncio.sleep(0.01)
        
        print(f"✅ Completed {num_requests} API request simulations")
    
    async def simulate_search_operations(self, num_searches: int = 30):
        """Simulate search operations with performance tracking."""
        print(f"🔍 Simulating {num_searches} search operations...")
        
        search_types = ["vector", "hybrid", "simple"]
        
        for i in range(num_searches):
            query = random.choice(self.demo_queries)
            search_type = random.choice(search_types)
            user_id = random.choice(self.demo_users)
            
            # Simulate search performance based on type
            if search_type == "vector":
                response_time = random.uniform(200, 800)
                results_count = random.randint(5, 25)
            elif search_type == "hybrid":
                response_time = random.uniform(300, 1200)
                results_count = random.randint(8, 35)
            else:  # simple
                response_time = random.uniform(50, 200)
                results_count = random.randint(3, 15)
            
            # Simulate cache hits (30% chance)
            cache_hit = random.random() < 0.3
            if cache_hit:
                response_time *= 0.1  # Cache hits are much faster
            
            # Record search performance
            self.collector.record_search_performance(
                query_text=query,
                search_type=search_type,
                response_time_ms=response_time,
                results_count=results_count,
                cache_hit=cache_hit,
                user_id=user_id,
                query_complexity_score=len(query.split()) / 10.0  # Simple complexity score
            )
            
            # Record cache events
            if cache_hit:
                record_cache_hit()
            else:
                record_cache_miss()
            
            await asyncio.sleep(0.02)
        
        print(f"✅ Completed {num_searches} search operation simulations")
    
    async def simulate_document_processing(self, num_documents: int = 15):
        """Simulate document processing operations."""
        print(f"📄 Simulating {num_documents} document processing operations...")
        
        processing_stages = ["upload", "extract", "chunk", "embed", "index"]
        
        for i in range(num_documents):
            doc = random.choice(self.demo_documents)
            
            for stage in processing_stages:
                # Simulate processing time based on document size and stage
                base_time = doc["size_mb"] * 1000  # 1 second per MB base
                
                if stage == "upload":
                    processing_time = base_time * random.uniform(0.5, 1.5)
                elif stage == "extract":
                    processing_time = base_time * random.uniform(2.0, 4.0)
                elif stage == "chunk":
                    processing_time = base_time * random.uniform(1.0, 2.0)
                elif stage == "embed":
                    processing_time = base_time * random.uniform(3.0, 6.0)  # Most expensive
                else:  # index
                    processing_time = base_time * random.uniform(0.5, 1.0)
                
                # Simulate occasional failures (5% chance)
                success = random.random() > 0.05
                error_message = None
                if not success:
                    error_message = f"Processing failed at {stage} stage"
                    processing_time *= 0.3  # Failures happen faster
                
                # Record document processing
                self.collector.record_document_processing(
                    document_id=f"{doc['id']}_{i}",
                    document_size_mb=doc["size_mb"],
                    processing_time_ms=processing_time,
                    processing_stage=stage,
                    success=success,
                    error_message=error_message
                )
                
                await asyncio.sleep(0.01)
        
        print(f"✅ Completed {num_documents} document processing simulations")
    
    @track_response_time("/api/demo/decorated", "GET")
    async def decorated_function_demo(self):
        """Demonstrate decorator-based metrics collection."""
        print("🎯 Demonstrating decorator-based metrics collection...")
        await asyncio.sleep(0.1)  # Simulate work
        return {"result": "success", "data": [1, 2, 3]}
    
    @track_search_performance("vector")
    async def decorated_search_demo(self, query: str):
        """Demonstrate search performance decorator."""
        print(f"🔍 Demonstrating search decorator with query: '{query}'")
        await asyncio.sleep(0.2)  # Simulate search work
        return {
            "results": [{"id": i, "score": random.random()} for i in range(10)],
            "cache_hit": False
        }
    
    @track_document_processing("extract")
    async def decorated_processing_demo(self, document_id: str, document_size_mb: float):
        """Demonstrate document processing decorator."""
        print(f"📄 Demonstrating processing decorator for doc: {document_id}")
        await asyncio.sleep(document_size_mb * 0.1)  # Simulate processing time
        return f"Processed document {document_id}"
    
    async def demonstrate_context_manager(self):
        """Demonstrate manual metrics collection with context manager."""
        print("📊 Demonstrating context manager metrics collection...")
        
        async with MetricsContext("custom_operation", "DEMO") as ctx:
            # Simulate some work
            await asyncio.sleep(0.15)
            
            # Set additional context
            ctx.set_result_info(items_processed=42, cache_used=True)
        
        print("✅ Context manager demonstration completed")
    
    def demonstrate_manual_helpers(self):
        """Demonstrate manual metrics collection helpers."""
        print("🛠️ Demonstrating manual metrics helpers...")
        
        # Manual search metrics
        SearchMetricsHelper.record_search(
            query="manual search query",
            search_type="hybrid",
            response_time_ms=350.0,
            results_count=12,
            cache_hit=True,
            user_id="demo_user"
        )
        
        # Manual document processing metrics
        DocumentMetricsHelper.record_processing(
            document_id="manual_doc_123",
            document_size_mb=3.2,
            processing_time_ms=4500.0,
            processing_stage="embed",
            success=True
        )
        
        print("✅ Manual helpers demonstration completed")
    
    def display_real_time_metrics(self):
        """Display current real-time metrics."""
        print("\n" + "="*60)
        print("📊 REAL-TIME METRICS DASHBOARD")
        print("="*60)
        
        metrics = self.collector.get_real_time_metrics()
        
        # System overview
        print(f"🕐 System Uptime: {metrics['system_uptime_hours']:.2f} hours")
        
        # Response time metrics
        response_metrics = metrics['response_time_metrics']
        print(f"\n⚡ Response Time Metrics (Last 5 minutes):")
        print(f"   • Total Requests: {response_metrics['total_requests_5min']}")
        print(f"   • Average Response Time: {response_metrics['avg_response_time_ms']:.2f}ms")
        print(f"   • 95th Percentile: {response_metrics['p95_response_time_ms']:.2f}ms")
        print(f"   • 99th Percentile: {response_metrics['p99_response_time_ms']:.2f}ms")
        
        # Resource usage
        if 'resource_usage' in metrics and 'error' not in metrics['resource_usage']:
            resource_usage = metrics['resource_usage']
            print(f"\n💻 Resource Usage:")
            print(f"   • CPU: {resource_usage['cpu']['percent']:.1f}%")
            print(f"   • Memory: {resource_usage['memory']['percent']:.1f}% ({resource_usage['memory']['used_gb']:.2f}GB used)")
            print(f"   • Disk: {resource_usage['disk']['percent']:.1f}% ({resource_usage['disk']['free_gb']:.2f}GB free)")
        
        # User session metrics
        session_metrics = metrics['user_session_metrics']
        print(f"\n👥 User Session Metrics:")
        print(f"   • Active Sessions: {session_metrics['active_sessions']}")
        print(f"   • Total Sessions: {session_metrics['total_sessions']}")
        print(f"   • Concurrent Requests: {session_metrics['concurrent_requests']}")
        print(f"   • Peak Concurrent: {session_metrics['peak_concurrent_requests']}")
        print(f"   • Unique Active Users: {session_metrics['unique_users_active']}")
        
        # Search performance
        if metrics['search_performance']:
            search_perf = metrics['search_performance']
            print(f"\n🔍 Search Performance (Last 5 minutes):")
            print(f"   • Total Searches: {search_perf['total_searches']}")
            print(f"   • Average Search Time: {search_perf['avg_search_time_ms']:.2f}ms")
            print(f"   • Cache Hit Rate: {search_perf['cache_hit_rate']:.1f}%")
        
        # Cache metrics
        cache_metrics = metrics['cache_metrics']
        print(f"\n🗄️ Cache Metrics:")
        print(f"   • Hit Rate: {cache_metrics['hit_rate_percent']:.1f}%")
        print(f"   • Total Hits: {cache_metrics['total_hits']}")
        print(f"   • Total Misses: {cache_metrics['total_misses']}")
        print(f"   • Cache Size: {cache_metrics['cache_size_mb']:.2f}MB")
    
    def display_performance_trends(self, hours: int = 2):
        """Display performance trends."""
        print(f"\n📈 PERFORMANCE TRENDS (Last {hours} hours)")
        print("="*60)
        
        trends = self.collector.get_performance_trends(hours)
        
        # Summary
        summary = trends['summary']
        print(f"📊 Summary:")
        print(f"   • Total Requests: {summary['total_requests']}")
        print(f"   • Total Searches: {summary['total_searches']}")
        print(f"   • Documents Processed: {summary['total_documents_processed']}")
        print(f"   • Average Response Time: {summary['avg_response_time_ms']:.2f}ms")
        print(f"   • Error Rate: {summary['error_rate_percent']:.2f}%")
        
        # Hourly breakdown (show last 3 hours)
        if trends['hourly_trends']:
            print(f"\n⏰ Hourly Breakdown:")
            for hour_data in trends['hourly_trends'][-3:]:  # Last 3 hours
                print(f"   {hour_data['hour']}:")
                print(f"      Requests: {hour_data['requests']}, "
                      f"Avg Response: {hour_data.get('avg_response_time', 0):.1f}ms, "
                      f"Errors: {hour_data['errors']}, "
                      f"Searches: {hour_data['searches']}")
    
    def display_user_session_analytics(self):
        """Display user session analytics."""
        print(f"\n👥 USER SESSION ANALYTICS")
        print("="*60)
        
        analytics = self.collector.get_user_session_analytics()
        
        print(f"📊 Session Overview:")
        print(f"   • Active Sessions: {analytics['active_sessions']}")
        print(f"   • Total Sessions: {analytics['total_sessions']}")
        
        session_stats = analytics['session_analytics']
        print(f"\n📈 Session Statistics:")
        print(f"   • Average Session Duration: {session_stats['avg_session_duration_minutes']:.1f} minutes")
        print(f"   • Median Session Duration: {session_stats['median_session_duration_minutes']:.1f} minutes")
        print(f"   • Average Requests per Session: {session_stats['avg_requests_per_session']:.1f}")
        print(f"   • Total Requests: {session_stats['total_requests']}")
        
        engagement = analytics['user_engagement']
        print(f"\n🎯 User Engagement:")
        print(f"   • Unique Users: {engagement['unique_users']}")
        print(f"   • Returning Users: {engagement['returning_users']}")
        
        if engagement['top_endpoints']:
            print(f"\n🔥 Top Endpoints:")
            for endpoint_data in engagement['top_endpoints'][:5]:
                print(f"   • {endpoint_data['endpoint']}: {endpoint_data['usage_count']} requests")
    
    async def run_comprehensive_demo(self):
        """Run the complete comprehensive metrics demonstration."""
        print("🚀 Starting Comprehensive Metrics Collection Demo")
        print("="*60)
        
        # Phase 1: Simulate various operations
        print("\n📊 Phase 1: Simulating System Activity")
        await self.simulate_api_requests(75)
        await self.simulate_search_operations(40)
        await self.simulate_document_processing(20)
        
        # Phase 2: Demonstrate decorators and helpers
        print("\n🎯 Phase 2: Demonstrating Integration Features")
        await self.decorated_function_demo()
        await self.decorated_search_demo("machine learning optimization")
        await self.decorated_processing_demo("demo_doc_456", 2.1)
        await self.demonstrate_context_manager()
        self.demonstrate_manual_helpers()
        
        # Phase 3: Display comprehensive analytics
        print("\n📈 Phase 3: Analytics and Reporting")
        self.display_real_time_metrics()
        self.display_performance_trends()
        self.display_user_session_analytics()
        
        # Phase 4: Export comprehensive report
        print(f"\n💾 Phase 4: Exporting Comprehensive Report")
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        report_path = f"comprehensive_metrics_demo_report_{timestamp}.json"
        
        try:
            exported_path = self.collector.export_comprehensive_report(report_path)
            print(f"✅ Comprehensive report exported to: {exported_path}")
        except Exception as e:
            print(f"❌ Failed to export report: {e}")
        
        print(f"\n🎉 Comprehensive Metrics Demo Completed!")
        print("="*60)
        
        # Final summary
        final_metrics = self.collector.get_real_time_metrics()
        print(f"\n📊 Final Statistics:")
        print(f"   • Total API Requests Tracked: {final_metrics['response_time_metrics']['total_requests_5min']}")
        print(f"   • Total User Sessions: {final_metrics['user_session_metrics']['total_sessions']}")
        print(f"   • Cache Hit Rate: {final_metrics['cache_metrics']['hit_rate_percent']:.1f}%")
        print(f"   • System Uptime: {final_metrics['system_uptime_hours']:.2f} hours")


async def main():
    """Main demonstration function."""
    print("🔧 Initializing Comprehensive Metrics Collection Demo...")
    
    demo = MetricsDemo()
    
    try:
        await demo.run_comprehensive_demo()
    except KeyboardInterrupt:
        print("\n⚠️ Demo interrupted by user")
    except Exception as e:
        print(f"\n❌ Demo failed with error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Stop background collection
        demo.collector.stop_collection()
        print("\n🛑 Metrics collection stopped")


if __name__ == "__main__":
    asyncio.run(main())