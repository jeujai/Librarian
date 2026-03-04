#!/usr/bin/env python3
"""
Fallback Detection System Demonstration.

This script demonstrates the enhanced fallback detection capabilities including:
- Health monitoring and automatic fallback triggers
- Service switching and recovery
- Performance monitoring and notifications
- Real-time status reporting
"""

import asyncio
import logging
import json
import time
from datetime import datetime, timedelta
from typing import Dict, Any, List
from unittest.mock import Mock

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Import fallback detection components
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.multimodal_librarian.components.vector_store.fallback_manager import (
    FallbackManager, FallbackConfig, FallbackEvent, ServiceStatus
)
from src.multimodal_librarian.components.vector_store.search_service_enhanced import (
    SearchServiceWithFallback
)
from src.multimodal_librarian.components.vector_store.search_service import SearchRequest


class DemoService:
    """Demo service with configurable behavior for testing fallback detection."""
    
    def __init__(self, name: str, base_latency_ms: float = 50.0):
        self.name = name
        self.base_latency_ms = base_latency_ms
        self.is_healthy = True
        self.should_be_slow = False
        self.failure_mode = False
        self.call_count = 0
        
        logger.info(f"Demo service '{name}' initialized with {base_latency_ms}ms base latency")
    
    async def health_check(self) -> bool:
        """Demo health check with configurable behavior."""
        self.call_count += 1
        
        # Simulate latency
        latency = self.base_latency_ms
        if self.should_be_slow:
            latency *= 10  # Make it 10x slower
        
        await asyncio.sleep(latency / 1000.0)
        
        if self.failure_mode:
            raise Exception(f"Demo service {self.name} is in failure mode")
        
        return self.is_healthy
    
    async def search(self, request):
        """Demo search method."""
        await asyncio.sleep(self.base_latency_ms / 1000.0)
        self.call_count += 1
        
        if self.failure_mode:
            raise Exception(f"Demo service {self.name} search failed")
        
        from src.multimodal_librarian.components.vector_store.search_service_simple import SimpleSearchResponse
        return SimpleSearchResponse(
            results=[],
            search_time_ms=self.base_latency_ms,
            session_id=getattr(request, 'session_id', 'demo')
        )
    
    def get_performance_stats(self) -> Dict[str, Any]:
        """Get demo performance stats."""
        return {
            'call_count': self.call_count,
            'is_healthy': self.is_healthy,
            'should_be_slow': self.should_be_slow,
            'failure_mode': self.failure_mode
        }
    
    def set_healthy(self, healthy: bool):
        """Set health status."""
        self.is_healthy = healthy
        logger.info(f"Demo service '{self.name}' health set to: {healthy}")
    
    def set_slow(self, slow: bool):
        """Set slow response mode."""
        self.should_be_slow = slow
        logger.info(f"Demo service '{self.name}' slow mode set to: {slow}")
    
    def set_failure_mode(self, failure: bool):
        """Set failure mode."""
        self.failure_mode = failure
        logger.info(f"Demo service '{self.name}' failure mode set to: {failure}")


class FallbackDetectionDemo:
    """Main demonstration class for fallback detection system."""
    
    def __init__(self):
        """Initialize the demonstration."""
        # Create demo configuration
        self.config = FallbackConfig(
            health_check_interval_seconds=2,  # Check every 2 seconds
            health_check_timeout_seconds=3,
            max_response_time_ms=200.0,  # 200ms threshold
            max_error_rate=0.1,  # 10% error rate threshold
            consecutive_failures_threshold=2,
            consecutive_successes_threshold=3,
            enable_notifications=True,
            notification_cooldown_minutes=0  # No cooldown for demo
        )
        
        # Create fallback manager
        self.fallback_manager = FallbackManager(self.config)
        
        # Create demo services
        self.primary_service = DemoService("Primary Search Service", base_latency_ms=30.0)
        self.fallback_service = DemoService("Fallback Search Service", base_latency_ms=50.0)
        self.backup_service = DemoService("Backup Search Service", base_latency_ms=80.0)
        
        # Register services
        self.fallback_manager.register_service("primary", self.primary_service, is_primary=True)
        self.fallback_manager.register_service("fallback", self.fallback_service)
        self.fallback_manager.register_service("backup", self.backup_service)
        
        # Track events
        self.events = []
        self.fallback_manager.add_notification_callback(self._handle_fallback_event)
        
        # Create mock vector store for enhanced search service
        self.mock_vector_store = Mock()
        self.mock_vector_store.health_check.return_value = True
        
        # Create enhanced search service
        self.search_service = SearchServiceWithFallback(
            self.mock_vector_store,
            fallback_config=self.config
        )
        
        logger.info("Fallback detection demonstration initialized")
    
    def _handle_fallback_event(self, event: FallbackEvent):
        """Handle fallback events for demonstration."""
        self.events.append(event)
        
        if event.resolved:
            logger.info(f"🟢 SERVICE RECOVERED: {event.service_name}")
            logger.info(f"   Recovery time: {(event.resolved_at - event.timestamp).total_seconds():.1f}s")
        else:
            logger.warning(f"🔴 FALLBACK ACTIVATED: {event.service_name}")
            logger.warning(f"   Reason: {event.reason.value}")
            logger.warning(f"   Message: {event.message}")
            logger.warning(f"   Fallback service: {event.fallback_service}")
    
    async def demonstrate_basic_monitoring(self):
        """Demonstrate basic health monitoring."""
        print("\n" + "="*60)
        print("DEMONSTRATION 1: Basic Health Monitoring")
        print("="*60)
        
        logger.info("Starting health monitoring...")
        await self.fallback_manager.start_monitoring()
        
        # Let monitoring run for a bit
        logger.info("Monitoring healthy services for 10 seconds...")
        await asyncio.sleep(10)
        
        # Show status
        self._print_service_status()
        
        await self.fallback_manager.stop_monitoring()
        logger.info("Basic monitoring demonstration completed")
    
    async def demonstrate_response_time_fallback(self):
        """Demonstrate fallback due to response time threshold."""
        print("\n" + "="*60)
        print("DEMONSTRATION 2: Response Time Fallback")
        print("="*60)
        
        logger.info("Starting monitoring...")
        await self.fallback_manager.start_monitoring()
        
        # Make primary service slow
        logger.info("Making primary service slow (10x latency)...")
        self.primary_service.set_slow(True)
        
        # Wait for fallback detection
        logger.info("Waiting for fallback detection...")
        await asyncio.sleep(15)
        
        # Show results
        self._print_service_status()
        self._print_fallback_events()
        
        # Restore primary service
        logger.info("Restoring primary service performance...")
        self.primary_service.set_slow(False)
        
        # Wait for recovery
        logger.info("Waiting for service recovery...")
        await asyncio.sleep(15)
        
        self._print_service_status()
        
        await self.fallback_manager.stop_monitoring()
        logger.info("Response time fallback demonstration completed")
    
    async def demonstrate_failure_fallback(self):
        """Demonstrate fallback due to service failures."""
        print("\n" + "="*60)
        print("DEMONSTRATION 3: Service Failure Fallback")
        print("="*60)
        
        logger.info("Starting monitoring...")
        await self.fallback_manager.start_monitoring()
        
        # Make primary service fail
        logger.info("Enabling failure mode on primary service...")
        self.primary_service.set_failure_mode(True)
        
        # Wait for fallback detection
        logger.info("Waiting for fallback detection...")
        await asyncio.sleep(10)
        
        # Show results
        self._print_service_status()
        self._print_fallback_events()
        
        # Restore primary service
        logger.info("Disabling failure mode on primary service...")
        self.primary_service.set_failure_mode(False)
        
        # Wait for recovery
        logger.info("Waiting for service recovery...")
        await asyncio.sleep(15)
        
        self._print_service_status()
        
        await self.fallback_manager.stop_monitoring()
        logger.info("Service failure fallback demonstration completed")
    
    async def demonstrate_cascading_failures(self):
        """Demonstrate cascading failures and multiple fallbacks."""
        print("\n" + "="*60)
        print("DEMONSTRATION 4: Cascading Failures")
        print("="*60)
        
        logger.info("Starting monitoring...")
        await self.fallback_manager.start_monitoring()
        
        # Initial state
        await asyncio.sleep(5)
        logger.info("All services healthy initially")
        self._print_service_status()
        
        # Primary service fails
        logger.info("Primary service failing...")
        self.primary_service.set_failure_mode(True)
        await asyncio.sleep(8)
        
        logger.info("After primary failure:")
        self._print_service_status()
        
        # Fallback service also fails
        logger.info("Fallback service also failing...")
        self.fallback_service.set_failure_mode(True)
        await asyncio.sleep(8)
        
        logger.info("After cascading failure:")
        self._print_service_status()
        
        # Gradual recovery
        logger.info("Starting gradual recovery...")
        
        # Restore fallback service first
        logger.info("Restoring fallback service...")
        self.fallback_service.set_failure_mode(False)
        await asyncio.sleep(10)
        
        logger.info("After fallback recovery:")
        self._print_service_status()
        
        # Restore primary service
        logger.info("Restoring primary service...")
        self.primary_service.set_failure_mode(False)
        await asyncio.sleep(15)
        
        logger.info("After full recovery:")
        self._print_service_status()
        
        await self.fallback_manager.stop_monitoring()
        logger.info("Cascading failures demonstration completed")
    
    async def demonstrate_search_service_integration(self):
        """Demonstrate integration with enhanced search service."""
        print("\n" + "="*60)
        print("DEMONSTRATION 5: Search Service Integration")
        print("="*60)
        
        # Start the enhanced search service
        await self.search_service.start()
        
        try:
            # Perform some searches
            logger.info("Performing searches with healthy services...")
            for i in range(5):
                request = SearchRequest(query=f"test query {i}")
                response = await self.search_service.search(request)
                logger.info(f"Search {i+1}: {len(response.results)} results in {response.search_time_ms:.1f}ms")
            
            # Show initial stats
            stats = self.search_service.get_performance_stats()
            logger.info(f"Initial stats: {stats}")
            
            # Trigger fallback
            logger.info("Triggering manual fallback...")
            await self.search_service.manual_fallback("Demonstration fallback")
            
            # Perform searches with fallback
            logger.info("Performing searches with fallback service...")
            for i in range(5):
                request = SearchRequest(query=f"fallback query {i}")
                response = await self.search_service.search(request)
                logger.info(f"Fallback search {i+1}: {len(response.results)} results in {response.search_time_ms:.1f}ms")
            
            # Show updated stats
            stats = self.search_service.get_performance_stats()
            logger.info(f"Updated stats: {stats}")
            
            # Get comprehensive analytics
            analytics = await self.search_service.get_search_analytics()
            logger.info("Comprehensive analytics:")
            logger.info(f"  Current service: {analytics['current_service']}")
            logger.info(f"  Service switches: {analytics['performance_stats']['service_switches']}")
            logger.info(f"  Active fallbacks: {len(analytics['active_fallbacks'])}")
            
            # Trigger recovery
            logger.info("Triggering manual recovery...")
            await self.search_service.manual_recovery()
            
            # Final searches
            logger.info("Performing searches after recovery...")
            for i in range(3):
                request = SearchRequest(query=f"recovery query {i}")
                response = await self.search_service.search(request)
                logger.info(f"Recovery search {i+1}: {len(response.results)} results in {response.search_time_ms:.1f}ms")
            
            # Final stats
            final_stats = self.search_service.get_performance_stats()
            logger.info(f"Final stats: {final_stats}")
            
        finally:
            await self.search_service.stop()
        
        logger.info("Search service integration demonstration completed")
    
    async def demonstrate_manual_operations(self):
        """Demonstrate manual fallback and recovery operations."""
        print("\n" + "="*60)
        print("DEMONSTRATION 6: Manual Operations")
        print("="*60)
        
        logger.info("Starting monitoring...")
        await self.fallback_manager.start_monitoring()
        
        # Wait for initial health checks
        await asyncio.sleep(5)
        
        logger.info("Initial service status:")
        self._print_service_status()
        
        # Manual fallback
        logger.info("Triggering manual fallback for primary service...")
        success = await self.fallback_manager.manual_fallback("primary", "Manual demonstration")
        logger.info(f"Manual fallback result: {success}")
        
        await asyncio.sleep(3)
        self._print_service_status()
        
        # Manual recovery
        logger.info("Triggering manual recovery for primary service...")
        success = await self.fallback_manager.manual_recovery("primary")
        logger.info(f"Manual recovery result: {success}")
        
        await asyncio.sleep(3)
        self._print_service_status()
        
        await self.fallback_manager.stop_monitoring()
        logger.info("Manual operations demonstration completed")
    
    def _print_service_status(self):
        """Print current service status."""
        print("\n📊 SERVICE STATUS:")
        print("-" * 40)
        
        all_status = self.fallback_manager.get_all_service_status()
        for name, metrics in all_status.items():
            status_emoji = {
                ServiceStatus.HEALTHY: "🟢",
                ServiceStatus.DEGRADED: "🟡",
                ServiceStatus.FAILED: "🔴",
                ServiceStatus.UNKNOWN: "⚪"
            }.get(metrics.status, "❓")
            
            print(f"{status_emoji} {name}:")
            print(f"   Status: {metrics.status.value}")
            print(f"   Response time: {metrics.response_time_ms:.1f}ms")
            print(f"   Error rate: {metrics.error_rate:.1%}")
            print(f"   Total requests: {metrics.total_requests}")
            
            # Check if in fallback
            if self.fallback_manager.is_service_in_fallback(name):
                print(f"   ⚠️  Currently in fallback mode")
        
        # Show active fallbacks
        active_fallbacks = self.fallback_manager.get_active_fallbacks()
        if active_fallbacks:
            print(f"\n🔄 ACTIVE FALLBACKS: {len(active_fallbacks)}")
            for service_name, event in active_fallbacks.items():
                print(f"   {service_name}: {event.reason.value}")
    
    def _print_fallback_events(self):
        """Print recent fallback events."""
        if not self.events:
            return
        
        print("\n📋 RECENT FALLBACK EVENTS:")
        print("-" * 40)
        
        for event in self.events[-5:]:  # Show last 5 events
            event_emoji = "🟢" if event.resolved else "🔴"
            event_type = "RECOVERY" if event.resolved else "FALLBACK"
            
            print(f"{event_emoji} {event_type}: {event.service_name}")
            print(f"   Time: {event.timestamp.strftime('%H:%M:%S')}")
            print(f"   Reason: {event.reason.value}")
            print(f"   Message: {event.message}")
            
            if event.resolved:
                duration = (event.resolved_at - event.timestamp).total_seconds()
                print(f"   Duration: {duration:.1f}s")
    
    def _print_statistics(self):
        """Print comprehensive statistics."""
        stats = self.fallback_manager.get_fallback_statistics()
        
        print("\n📈 FALLBACK STATISTICS:")
        print("-" * 40)
        print(f"Total fallback events: {stats['total_fallback_events']}")
        print(f"Active fallbacks: {stats['active_fallbacks']}")
        print(f"Registered services: {stats['registered_services']}")
        print(f"Healthy services: {stats['healthy_services']}")
        
        if stats['average_recovery_time_minutes']:
            print(f"Average recovery time: {stats['average_recovery_time_minutes']:.1f} minutes")
        
        if stats['reason_statistics']:
            print("\nFailure reasons:")
            for reason, counts in stats['reason_statistics'].items():
                print(f"  {reason}: {counts['count']} total, {counts['resolved']} resolved")


async def main():
    """Run the fallback detection demonstration."""
    print("🚀 FALLBACK DETECTION SYSTEM DEMONSTRATION")
    print("=" * 60)
    
    demo = FallbackDetectionDemo()
    
    try:
        # Run all demonstrations
        await demo.demonstrate_basic_monitoring()
        await demo.demonstrate_response_time_fallback()
        await demo.demonstrate_failure_fallback()
        await demo.demonstrate_cascading_failures()
        await demo.demonstrate_search_service_integration()
        await demo.demonstrate_manual_operations()
        
        # Final statistics
        print("\n" + "="*60)
        print("FINAL STATISTICS")
        print("="*60)
        demo._print_statistics()
        
        # Export results
        results = {
            'demonstration_completed': True,
            'timestamp': datetime.now().isoformat(),
            'total_events': len(demo.events),
            'fallback_statistics': demo.fallback_manager.get_fallback_statistics(),
            'service_status': {
                name: metrics.to_dict() 
                for name, metrics in demo.fallback_manager.get_all_service_status().items()
            },
            'events': [event.to_dict() for event in demo.events]
        }
        
        # Save results
        results_file = f"fallback_detection_demo_results_{int(time.time())}.json"
        with open(results_file, 'w') as f:
            json.dump(results, f, indent=2)
        
        print(f"\n✅ Demonstration completed successfully!")
        print(f"📄 Results saved to: {results_file}")
        
    except Exception as e:
        logger.error(f"Demonstration failed: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())