"""
Circuit Breaker Pattern Demonstration.

This script demonstrates the circuit breaker pattern implementation including:
- Failure threshold detection
- Automatic service isolation
- Recovery testing
- State transitions
"""

import asyncio
import time
import random
from datetime import datetime
from typing import Dict, Any

from src.multimodal_librarian.monitoring.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerManager,
    CircuitBreakerConfig,
    CircuitState,
    CircuitBreakerError,
    circuit_breaker,
    get_circuit_breaker_manager
)
from src.multimodal_librarian.monitoring.service_health_monitor_enhanced import (
    EnhancedServiceHealthMonitor,
    get_enhanced_service_health_monitor
)


class MockService:
    """Mock service for demonstration purposes."""
    
    def __init__(self, name: str, failure_rate: float = 0.0):
        """
        Initialize mock service.
        
        Args:
            name: Service name
            failure_rate: Probability of failure (0.0-1.0)
        """
        self.name = name
        self.failure_rate = failure_rate
        self.call_count = 0
        self.is_healthy = True
        
    async def process_request(self, request_id: str) -> Dict[str, Any]:
        """Process a request with potential failure."""
        self.call_count += 1
        
        # Simulate processing time
        await asyncio.sleep(0.1)
        
        # Simulate failure based on failure rate
        if not self.is_healthy or random.random() < self.failure_rate:
            raise Exception(f"Service {self.name} failed to process request {request_id}")
        
        return {
            "service": self.name,
            "request_id": request_id,
            "result": f"Processed by {self.name}",
            "call_count": self.call_count,
            "timestamp": datetime.now().isoformat()
        }
    
    def health_check(self) -> bool:
        """Check if service is healthy."""
        return self.is_healthy
    
    def set_healthy(self, healthy: bool) -> None:
        """Set service health status."""
        self.is_healthy = healthy
        print(f"🔧 Service {self.name} health set to: {'healthy' if healthy else 'unhealthy'}")
    
    async def restart(self) -> bool:
        """Restart the service."""
        print(f"🔄 Restarting service {self.name}...")
        await asyncio.sleep(1)  # Simulate restart time
        self.is_healthy = True
        self.call_count = 0
        print(f"✅ Service {self.name} restarted successfully")
        return True


async def demonstrate_basic_circuit_breaker():
    """Demonstrate basic circuit breaker functionality."""
    print("\n" + "="*60)
    print("🔌 BASIC CIRCUIT BREAKER DEMONSTRATION")
    print("="*60)
    
    # Create configuration
    config = CircuitBreakerConfig(
        failure_threshold=3,
        failure_rate_threshold=0.6,
        timeout_seconds=2,
        success_threshold=2,
        health_check_interval=1
    )
    
    # Create mock service
    service = MockService("payment_service", failure_rate=0.8)
    
    # Create circuit breaker with recovery function
    circuit_breaker = CircuitBreaker(
        "payment_circuit",
        config,
        recovery_function=service.health_check
    )
    
    print(f"📊 Initial circuit state: {circuit_breaker.get_state().value}")
    
    # Phase 1: Normal operation with failures
    print("\n🔥 Phase 1: Triggering failures to open circuit...")
    for i in range(5):
        try:
            result = await circuit_breaker.call(service.process_request, f"req_{i}")
            print(f"✅ Request {i}: Success - {result['result']}")
        except CircuitBreakerError as e:
            print(f"🚫 Request {i}: Circuit breaker blocked - {e}")
            break
        except Exception as e:
            print(f"❌ Request {i}: Service failed - {e}")
        
        # Show current state
        state = circuit_breaker.get_state()
        metrics = circuit_breaker.get_metrics()
        print(f"   State: {state.value}, Failures: {metrics.consecutive_failures}")
        
        await asyncio.sleep(0.5)
    
    # Phase 2: Circuit is open, calls are blocked
    print(f"\n🔒 Phase 2: Circuit is {circuit_breaker.get_state().value}")
    print("Attempting calls while circuit is open...")
    
    for i in range(3):
        try:
            await circuit_breaker.call(service.process_request, f"blocked_{i}")
        except CircuitBreakerError as e:
            print(f"🚫 Blocked call {i}: {e}")
        await asyncio.sleep(0.5)
    
    # Phase 3: Service recovery
    print(f"\n🏥 Phase 3: Service recovery after {config.timeout_seconds} seconds...")
    service.set_healthy(True)
    
    # Wait for timeout
    print(f"⏳ Waiting {config.timeout_seconds} seconds for circuit timeout...")
    await asyncio.sleep(config.timeout_seconds + 0.5)
    
    # Phase 4: Half-open testing
    print("\n🔄 Phase 4: Testing recovery (half-open state)...")
    for i in range(config.success_threshold + 1):
        try:
            result = await circuit_breaker.call(service.process_request, f"recovery_{i}")
            print(f"✅ Recovery test {i}: Success - {result['result']}")
            print(f"   State: {circuit_breaker.get_state().value}")
        except Exception as e:
            print(f"❌ Recovery test {i}: Failed - {e}")
        
        await asyncio.sleep(0.5)
    
    # Final status
    final_status = circuit_breaker.get_status()
    print(f"\n📈 Final Status:")
    print(f"   State: {final_status['state']}")
    print(f"   Total requests: {final_status['metrics']['total_requests']}")
    print(f"   Success rate: {final_status['metrics']['success_rate']:.1%}")
    print(f"   State changes: {final_status['metrics']['state_changes']}")
    
    await circuit_breaker.shutdown()


async def demonstrate_circuit_breaker_decorator():
    """Demonstrate circuit breaker decorator functionality."""
    print("\n" + "="*60)
    print("🎭 CIRCUIT BREAKER DECORATOR DEMONSTRATION")
    print("="*60)
    
    # Configuration for decorator
    config = CircuitBreakerConfig(
        failure_threshold=2,
        timeout_seconds=1,
        success_threshold=1
    )
    
    # Mock service state
    service_healthy = False
    call_count = 0
    
    @circuit_breaker("decorated_service", config)
    async def decorated_service_call(request_id: str) -> str:
        nonlocal call_count
        call_count += 1
        
        await asyncio.sleep(0.1)  # Simulate processing
        
        if not service_healthy:
            raise Exception(f"Decorated service failed for request {request_id}")
        
        return f"Decorated service processed {request_id} (call #{call_count})"
    
    # Phase 1: Trigger failures
    print("🔥 Phase 1: Triggering failures...")
    for i in range(4):
        try:
            result = await decorated_service_call(f"req_{i}")
            print(f"✅ Request {i}: {result}")
        except CircuitBreakerError as e:
            print(f"🚫 Request {i}: Circuit breaker blocked")
            break
        except Exception as e:
            print(f"❌ Request {i}: Service failed")
        
        await asyncio.sleep(0.3)
    
    # Phase 2: Service recovery
    print(f"\n🏥 Phase 2: Service recovery...")
    service_healthy = True
    
    # Wait for timeout
    await asyncio.sleep(config.timeout_seconds + 0.5)
    
    # Test recovery
    try:
        result = await decorated_service_call("recovery_test")
        print(f"✅ Recovery test: {result}")
    except Exception as e:
        print(f"❌ Recovery test failed: {e}")


async def demonstrate_enhanced_service_monitor():
    """Demonstrate enhanced service monitor with circuit breakers."""
    print("\n" + "="*60)
    print("🔍 ENHANCED SERVICE MONITOR DEMONSTRATION")
    print("="*60)
    
    # Create enhanced monitor
    monitor = EnhancedServiceHealthMonitor()
    
    # Create mock services
    database_service = MockService("database", failure_rate=0.7)
    api_service = MockService("api", failure_rate=0.3)
    cache_service = MockService("cache", failure_rate=0.1)
    
    # Register services with circuit breaker protection
    services = {
        "database": database_service,
        "api": api_service,
        "cache": cache_service
    }
    
    for name, service in services.items():
        config = CircuitBreakerConfig(
            failure_threshold=2,
            timeout_seconds=2,
            success_threshold=1
        )
        
        monitor.register_service_with_circuit_breaker(
            name,
            service,
            config,
            recovery_function=service.health_check
        )
    
    # Start monitoring
    monitor.start_monitoring()
    
    print("📊 Registered services with circuit breaker protection:")
    for name in services.keys():
        print(f"   - {name}")
    
    # Phase 1: Make requests to services
    print("\n🔄 Phase 1: Making requests to services...")
    
    for round_num in range(3):
        print(f"\n--- Round {round_num + 1} ---")
        
        for service_name, service in services.items():
            try:
                result = await monitor.call_service_with_protection(
                    service_name,
                    service.process_request,
                    f"round_{round_num}_req"
                )
                print(f"✅ {service_name}: {result['result']}")
                
            except CircuitBreakerError:
                print(f"🚫 {service_name}: Circuit breaker blocked")
            except Exception as e:
                print(f"❌ {service_name}: Service failed")
        
        await asyncio.sleep(1)
    
    # Phase 2: Check service health
    print("\n📈 Phase 2: Service health status...")
    
    health_info = monitor.get_all_services_health_with_circuit_breakers()
    
    print(f"Overall status: {health_info['overall_status']}")
    print(f"Circuit breaker summary: {health_info['circuit_breaker_summary']}")
    
    for service_name in services.keys():
        service_health = health_info['services'].get(service_name, {})
        circuit_info = service_health.get('circuit_breaker', {})
        
        print(f"\n{service_name.upper()} SERVICE:")
        print(f"   Health status: {service_health.get('status', 'unknown')}")
        print(f"   Circuit state: {circuit_info.get('state', 'unknown')}")
        print(f"   Success rate: {service_health.get('statistics', {}).get('success_rate', 0):.1f}%")
        print(f"   Isolated: {service_health.get('isolated', False)}")
    
    # Phase 3: Force recovery
    print("\n🏥 Phase 3: Forcing service recovery...")
    
    for service_name, service in services.items():
        if monitor.is_service_isolated(service_name):
            print(f"🔧 Forcing recovery of {service_name}...")
            service.set_healthy(True)
            recovery_success = await monitor.force_service_recovery(service_name)
            print(f"   Recovery {'successful' if recovery_success else 'failed'}")
    
    # Final status
    print("\n📊 Final circuit breaker statistics:")
    stats = monitor.get_circuit_breaker_statistics()
    print(f"   Total circuit breakers: {stats['total_circuit_breakers']}")
    print(f"   Isolated services: {stats['isolated_services']}")
    print(f"   Circuit breaker states: {stats['circuit_breaker_states']}")
    
    # Cleanup
    await monitor.shutdown_enhanced_monitoring()


async def demonstrate_circuit_breaker_manager():
    """Demonstrate circuit breaker manager functionality."""
    print("\n" + "="*60)
    print("🎛️  CIRCUIT BREAKER MANAGER DEMONSTRATION")
    print("="*60)
    
    # Get global manager
    manager = get_circuit_breaker_manager()
    
    # Create multiple circuit breakers
    services = ["user_service", "order_service", "inventory_service"]
    
    for service_name in services:
        config = CircuitBreakerConfig(
            failure_threshold=2,
            timeout_seconds=1
        )
        
        cb = manager.create_circuit_breaker(service_name, config)
        print(f"✅ Created circuit breaker for {service_name}")
    
    # Get summary
    print("\n📊 Circuit breaker summary:")
    summary = manager.get_summary()
    print(f"   Total: {summary['total_circuit_breakers']}")
    print(f"   Closed: {summary['closed_breakers']}")
    print(f"   Open: {summary['open_breakers']}")
    print(f"   Health: {summary['health_percentage']:.1f}%")
    
    # Force one circuit breaker open
    print(f"\n🔒 Forcing user_service circuit breaker open...")
    user_cb = manager.get_circuit_breaker("user_service")
    if user_cb:
        user_cb.force_open()
    
    # Updated summary
    print("\n📊 Updated summary after forcing one open:")
    summary = manager.get_summary()
    print(f"   Closed: {summary['closed_breakers']}")
    print(f"   Open: {summary['open_breakers']}")
    print(f"   Health: {summary['health_percentage']:.1f}%")
    
    # Get detailed status
    print("\n📋 Detailed status of all circuit breakers:")
    all_status = manager.get_all_status()
    
    for cb_name, status in all_status.items():
        print(f"\n{cb_name.upper()}:")
        print(f"   State: {status['state']}")
        print(f"   Total requests: {status['metrics']['total_requests']}")
        print(f"   State changes: {status['metrics']['state_changes']}")
    
    # Cleanup
    await manager.shutdown_all()


async def main():
    """Run all demonstrations."""
    print("🚀 CIRCUIT BREAKER PATTERN DEMONSTRATION")
    print("This demo shows the circuit breaker pattern in action")
    print("with failure detection, service isolation, and recovery testing.")
    
    try:
        # Run demonstrations
        await demonstrate_basic_circuit_breaker()
        await demonstrate_circuit_breaker_decorator()
        await demonstrate_enhanced_service_monitor()
        await demonstrate_circuit_breaker_manager()
        
        print("\n" + "="*60)
        print("✅ ALL DEMONSTRATIONS COMPLETED SUCCESSFULLY")
        print("="*60)
        
        print("\n📝 Summary of demonstrated features:")
        print("   ✅ Failure threshold detection")
        print("   ✅ Automatic service isolation")
        print("   ✅ Recovery testing")
        print("   ✅ State transitions (CLOSED → OPEN → HALF_OPEN → CLOSED)")
        print("   ✅ Circuit breaker decorator")
        print("   ✅ Enhanced service health monitoring")
        print("   ✅ Circuit breaker manager")
        print("   ✅ Manual reset and force open operations")
        
    except Exception as e:
        print(f"\n❌ Demonstration failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())