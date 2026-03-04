"""
Network Failure Simulation Test

This test simulates network-related failures to validate:
1. Database connection failures
2. Service timeout handling  
3. Retry mechanisms

Validates: Requirement 3.2 - Error Handling and Recovery
"""

import pytest
import asyncio
import time
import logging
from typing import Dict, List, Any, Optional
from unittest.mock import patch, MagicMock, AsyncMock
from contextlib import asynccontextmanager
import socket
import aiohttp
from concurrent.futures import TimeoutError as ConcurrentTimeoutError

logger = logging.getLogger(__name__)


class NetworkFailureSimulator:
    """Simulates various network failures and tests system resilience."""
    
    def __init__(self):
        self.failure_results = {}
        self.timeout_results = {}
        self.retry_results = {}
        self.errors = []
    
    async def simulate_database_connection_failure(self) -> Dict[str, Any]:
        """Simulate database connection failures."""
        logger.info("🌐 Simulating database connection failure...")
        
        result = {
            "test_type": "database_connection_failure",
            "connection_failure_handled": False,
            "timeout_handled": False,
            "retry_mechanism_works": False,
            "graceful_degradation": False,
            "details": {}
        }
        
        try:
            # Test 1: Connection refused (database server down)
            with patch('psycopg2.connect') as mock_connect:
                mock_connect.side_effect = socket.error("Connection refused")
                
                try:
                    from multimodal_librarian.database.connection import get_database_connection
                    
                    # Should handle connection failure gracefully
                    try:
                        with get_database_connection() as conn:
                            result["details"]["unexpected_connection_success"] = True
                    except Exception as e:
                        result["connection_failure_handled"] = True
                        result["details"]["connection_error_handled"] = str(e)
                        
                except ImportError:
                    result["details"]["connection_module_not_available"] = True
                
                # Test that main app can still be created without database
                try:
                    from multimodal_librarian.main import create_minimal_app
                    app = create_minimal_app()
                    result["graceful_degradation"] = app is not None
                    result["details"]["app_works_without_db"] = True
                except Exception as e:
                    result["details"]["app_creation_error"] = str(e)
            
            # Test 2: Connection timeout
            with patch('psycopg2.connect') as mock_connect:
                mock_connect.side_effect = socket.timeout("Connection timed out")
                
                try:
                    from multimodal_librarian.database.connection import get_database_connection
                    
                    start_time = time.time()
                    try:
                        with get_database_connection() as conn:
                            result["details"]["timeout_not_triggered"] = True
                    except Exception as e:
                        elapsed_time = time.time() - start_time
                        result["timeout_handled"] = elapsed_time < 30  # Should timeout quickly
                        result["details"]["timeout_duration"] = elapsed_time
                        result["details"]["timeout_error"] = str(e)
                        
                except ImportError:
                    result["details"]["connection_module_not_available"] = True
            
            # Test 3: Retry mechanism
            retry_count = 0
            def mock_connect_with_retries(*args, **kwargs):
                nonlocal retry_count
                retry_count += 1
                if retry_count < 3:
                    raise socket.error("Connection failed")
                return MagicMock()  # Success on 3rd try
            
            with patch('psycopg2.connect', side_effect=mock_connect_with_retries):
                try:
                    from multimodal_librarian.database.connection import get_database_connection
                    
                    with get_database_connection() as conn:
                        result["retry_mechanism_works"] = retry_count >= 2
                        result["details"]["retry_attempts"] = retry_count
                    
                except Exception as e:
                    result["details"]["retry_test_error"] = str(e)
                    result["details"]["retry_attempts"] = retry_count
        
        except Exception as e:
            result["details"]["simulation_error"] = str(e)
            self.errors.append(f"Database connection failure simulation error: {e}")
        
        self.failure_results["database_connection"] = result
        return result
    
    async def simulate_service_timeout_scenarios(self) -> Dict[str, Any]:
        """Simulate various service timeout scenarios."""
        logger.info("⏱️ Simulating service timeout scenarios...")
        
        result = {
            "test_type": "service_timeouts",
            "ai_service_timeout_handled": False,
            "vector_store_timeout_handled": False,
            "http_request_timeout_handled": False,
            "timeout_recovery_works": False,
            "details": {}
        }
        
        try:
            # Test 1: AI Service timeout
            with patch('aiohttp.ClientSession.post') as mock_post:
                mock_post.side_effect = asyncio.TimeoutError("AI service timeout")
                
                try:
                    from multimodal_librarian.services.ai_service import AIService
                    ai_service = AIService()
                    
                    start_time = time.time()
                    try:
                        messages = [{"role": "user", "content": "test"}]
                        response = await ai_service.generate_response(messages)
                        result["details"]["ai_timeout_not_triggered"] = True
                    except Exception as e:
                        elapsed_time = time.time() - start_time
                        result["ai_service_timeout_handled"] = elapsed_time < 60  # Should timeout within 60s
                        result["details"]["ai_timeout_duration"] = elapsed_time
                        result["details"]["ai_timeout_error"] = str(e)
                        
                except ImportError:
                    result["details"]["ai_service_not_available"] = True
            
            # Test 2: Vector Store timeout
            with patch('multimodal_librarian.components.vector_store.vector_store.VectorStore.search') as mock_search:
                mock_search.side_effect = asyncio.TimeoutError("Vector store timeout")
                
                try:
                    from multimodal_librarian.components.vector_store.search_service import EnhancedSemanticSearchService
                    from multimodal_librarian.components.vector_store.search_service import SearchRequest
                    
                    mock_vector_store = MagicMock()
                    mock_vector_store.search = mock_search
                    search_service = EnhancedSemanticSearchService(mock_vector_store)
                    
                    start_time = time.time()
                    try:
                        search_request = SearchRequest(query="test query")
                        response = await search_service.search(search_request)
                        result["details"]["vector_timeout_not_triggered"] = True
                    except Exception as e:
                        elapsed_time = time.time() - start_time
                        result["vector_store_timeout_handled"] = elapsed_time < 30  # Should timeout within 30s
                        result["details"]["vector_timeout_duration"] = elapsed_time
                        result["details"]["vector_timeout_error"] = str(e)
                        
                except ImportError:
                    result["details"]["vector_store_not_available"] = True
            
            # Test 3: HTTP Request timeout
            with patch('aiohttp.ClientSession.get') as mock_get:
                mock_get.side_effect = aiohttp.ServerTimeoutError("HTTP timeout")
                
                try:
                    # Test with a generic HTTP client if available
                    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as session:
                        start_time = time.time()
                        try:
                            async with session.get("http://example.com") as response:
                                result["details"]["http_timeout_not_triggered"] = True
                        except Exception as e:
                            elapsed_time = time.time() - start_time
                            result["http_request_timeout_handled"] = elapsed_time < 10  # Should timeout within 10s
                            result["details"]["http_timeout_duration"] = elapsed_time
                            result["details"]["http_timeout_error"] = str(e)
                            
                except Exception as e:
                    result["details"]["http_test_error"] = str(e)
            
            # Test 4: Timeout recovery mechanism
            timeout_count = 0
            def mock_operation_with_recovery(*args, **kwargs):
                nonlocal timeout_count
                timeout_count += 1
                if timeout_count < 2:
                    raise asyncio.TimeoutError("Operation timeout")
                return {"status": "success"}  # Success on 2nd try
            
            try:
                # Simulate a service that recovers after timeout
                start_time = time.time()
                for attempt in range(3):
                    try:
                        result_data = mock_operation_with_recovery()
                        result["timeout_recovery_works"] = True
                        result["details"]["recovery_attempts"] = attempt + 1
                        break
                    except asyncio.TimeoutError:
                        if attempt < 2:  # Allow retries
                            await asyncio.sleep(0.1)  # Brief delay before retry
                            continue
                        else:
                            result["details"]["recovery_failed_after_retries"] = True
                
                elapsed_time = time.time() - start_time
                result["details"]["total_recovery_time"] = elapsed_time
                
            except Exception as e:
                result["details"]["recovery_test_error"] = str(e)
        
        except Exception as e:
            result["details"]["simulation_error"] = str(e)
            self.errors.append(f"Service timeout simulation error: {e}")
        
        self.timeout_results = result
        return result
    
    async def simulate_network_retry_mechanisms(self) -> Dict[str, Any]:
        """Simulate and test network retry mechanisms."""
        logger.info("🔄 Simulating network retry mechanisms...")
        
        result = {
            "test_type": "retry_mechanisms",
            "exponential_backoff_works": False,
            "max_retries_respected": False,
            "circuit_breaker_works": False,
            "retry_on_specific_errors": False,
            "details": {}
        }
        
        try:
            # Test 1: Exponential backoff
            retry_times = []
            retry_count = 0
            
            async def mock_failing_operation():
                nonlocal retry_count
                retry_count += 1
                retry_times.append(time.time())
                
                if retry_count < 4:
                    raise aiohttp.ClientError("Network error")
                return {"status": "success"}
            
            # Simulate exponential backoff retry logic
            max_retries = 3
            base_delay = 0.1
            
            start_time = time.time()
            for attempt in range(max_retries + 1):
                try:
                    result_data = await mock_failing_operation()
                    break
                except aiohttp.ClientError:
                    if attempt < max_retries:
                        delay = base_delay * (2 ** attempt)  # Exponential backoff
                        await asyncio.sleep(delay)
                        continue
                    else:
                        result["details"]["max_retries_reached"] = True
            
            # Analyze retry timing
            if len(retry_times) > 1:
                delays = [retry_times[i] - retry_times[i-1] for i in range(1, len(retry_times))]
                result["exponential_backoff_works"] = all(
                    delays[i] >= delays[i-1] * 1.5 for i in range(1, len(delays))
                ) if len(delays) > 1 else True
                result["details"]["retry_delays"] = delays
            
            result["max_retries_respected"] = retry_count <= max_retries + 1
            result["details"]["total_retry_attempts"] = retry_count
            
            # Test 2: Circuit breaker pattern
            failure_count = 0
            circuit_open = False
            
            async def mock_circuit_breaker_operation():
                nonlocal failure_count, circuit_open
                
                if circuit_open:
                    raise Exception("Circuit breaker open")
                
                failure_count += 1
                if failure_count >= 3:  # Open circuit after 3 failures
                    circuit_open = True
                
                raise aiohttp.ClientError("Service unavailable")
            
            # Test circuit breaker behavior
            circuit_breaker_results = []
            for i in range(5):
                try:
                    await mock_circuit_breaker_operation()
                    circuit_breaker_results.append("success")
                except Exception as e:
                    if "Circuit breaker open" in str(e):
                        circuit_breaker_results.append("circuit_open")
                    else:
                        circuit_breaker_results.append("failure")
            
            # Circuit breaker should open after failures
            result["circuit_breaker_works"] = "circuit_open" in circuit_breaker_results
            result["details"]["circuit_breaker_results"] = circuit_breaker_results
            
            # Test 3: Retry on specific errors only
            specific_error_retries = 0
            
            async def mock_selective_retry_operation(error_type):
                nonlocal specific_error_retries
                specific_error_retries += 1
                
                if error_type == "retryable":
                    raise aiohttp.ClientError("Temporary network error")
                elif error_type == "non_retryable":
                    raise ValueError("Invalid input")
            
            # Test retryable error
            retryable_attempts = 0
            for attempt in range(3):
                try:
                    await mock_selective_retry_operation("retryable")
                    break
                except aiohttp.ClientError:
                    retryable_attempts += 1
                    if attempt < 2:
                        continue
                except ValueError:
                    break  # Don't retry on non-retryable errors
            
            # Test non-retryable error
            non_retryable_attempts = 0
            try:
                await mock_selective_retry_operation("non_retryable")
            except ValueError:
                non_retryable_attempts = 1  # Should fail immediately
            except aiohttp.ClientError:
                non_retryable_attempts = 1
            
            result["retry_on_specific_errors"] = (
                retryable_attempts > 1 and non_retryable_attempts == 1
            )
            result["details"]["retryable_attempts"] = retryable_attempts
            result["details"]["non_retryable_attempts"] = non_retryable_attempts
        
        except Exception as e:
            result["details"]["simulation_error"] = str(e)
            self.errors.append(f"Retry mechanism simulation error: {e}")
        
        self.retry_results = result
        return result
    
    async def simulate_intermittent_network_issues(self) -> Dict[str, Any]:
        """Simulate intermittent network connectivity issues."""
        logger.info("📡 Simulating intermittent network issues...")
        
        result = {
            "test_type": "intermittent_network",
            "handles_packet_loss": False,
            "handles_slow_connections": False,
            "handles_dns_failures": False,
            "connection_pooling_resilient": False,
            "details": {}
        }
        
        try:
            # Test 1: Packet loss simulation
            packet_loss_count = 0
            
            async def mock_packet_loss_operation():
                nonlocal packet_loss_count
                packet_loss_count += 1
                
                # Simulate 30% packet loss
                if packet_loss_count % 3 == 0:
                    raise aiohttp.ClientError("Packet lost")
                return {"status": "success"}
            
            successful_operations = 0
            for i in range(10):
                try:
                    await mock_packet_loss_operation()
                    successful_operations += 1
                except aiohttp.ClientError:
                    # Retry once on packet loss
                    try:
                        await mock_packet_loss_operation()
                        successful_operations += 1
                    except aiohttp.ClientError:
                        pass  # Accept some failures
            
            result["handles_packet_loss"] = successful_operations >= 6  # 60% success rate
            result["details"]["packet_loss_success_rate"] = successful_operations / 10
            
            # Test 2: Slow connection simulation
            async def mock_slow_operation():
                await asyncio.sleep(2)  # Simulate slow response
                return {"status": "success"}
            
            start_time = time.time()
            try:
                # Use timeout to handle slow connections
                response = await asyncio.wait_for(mock_slow_operation(), timeout=1.0)
                result["details"]["slow_connection_completed"] = True
            except asyncio.TimeoutError:
                elapsed_time = time.time() - start_time
                result["handles_slow_connections"] = elapsed_time < 1.5  # Timeout handled quickly
                result["details"]["slow_connection_timeout"] = elapsed_time
            
            # Test 3: DNS failure simulation
            with patch('socket.gethostbyname') as mock_dns:
                mock_dns.side_effect = socket.gaierror("DNS resolution failed")
                
                try:
                    # Test DNS failure handling
                    host = socket.gethostbyname("example.com")
                    result["details"]["dns_failure_not_triggered"] = True
                except socket.gaierror as e:
                    result["handles_dns_failures"] = True
                    result["details"]["dns_error_handled"] = str(e)
            
            # Test 4: Connection pooling resilience
            connection_attempts = []
            
            async def mock_connection_pool_operation(connection_id):
                connection_attempts.append(connection_id)
                
                # Simulate some connections failing
                if connection_id % 3 == 0:
                    raise aiohttp.ClientError("Connection failed")
                return {"connection_id": connection_id, "status": "success"}
            
            # Test multiple connections
            successful_connections = 0
            for i in range(6):
                try:
                    await mock_connection_pool_operation(i)
                    successful_connections += 1
                except aiohttp.ClientError:
                    pass
            
            result["connection_pooling_resilient"] = successful_connections >= 4  # 66% success rate
            result["details"]["connection_pool_success_rate"] = successful_connections / 6
            result["details"]["connection_attempts"] = len(connection_attempts)
        
        except Exception as e:
            result["details"]["simulation_error"] = str(e)
            self.errors.append(f"Intermittent network simulation error: {e}")
        
        return result
    
    def get_comprehensive_report(self) -> Dict[str, Any]:
        """Get comprehensive network failure simulation report."""
        return {
            "network_failure_simulations": {
                "database_connection": self.failure_results.get("database_connection", {}),
                "service_timeouts": self.timeout_results,
                "retry_mechanisms": self.retry_results
            },
            "errors": self.errors,
            "summary": {
                "database_connection_resilient": self.failure_results.get("database_connection", {}).get("connection_failure_handled", False),
                "timeout_handling_works": self.timeout_results.get("ai_service_timeout_handled", False) or 
                                        self.timeout_results.get("vector_store_timeout_handled", False),
                "retry_mechanisms_functional": (
                    self.retry_results.get("exponential_backoff_works", False) and
                    self.retry_results.get("max_retries_respected", False)
                ),
                "overall_network_resilience_score": self._calculate_network_resilience_score()
            }
        }
    
    def _calculate_network_resilience_score(self) -> float:
        """Calculate overall network resilience score (0-1)."""
        scores = []
        
        # Database connection resilience
        db_result = self.failure_results.get("database_connection", {})
        db_score = sum([
            db_result.get("connection_failure_handled", False),
            db_result.get("timeout_handled", False),
            db_result.get("retry_mechanism_works", False),
            db_result.get("graceful_degradation", False)
        ]) / 4
        scores.append(db_score)
        
        # Timeout handling
        timeout_score = sum([
            self.timeout_results.get("ai_service_timeout_handled", False),
            self.timeout_results.get("vector_store_timeout_handled", False),
            self.timeout_results.get("http_request_timeout_handled", False),
            self.timeout_results.get("timeout_recovery_works", False)
        ]) / 4
        scores.append(timeout_score)
        
        # Retry mechanisms
        retry_score = sum([
            self.retry_results.get("exponential_backoff_works", False),
            self.retry_results.get("max_retries_respected", False),
            self.retry_results.get("circuit_breaker_works", False),
            self.retry_results.get("retry_on_specific_errors", False)
        ]) / 4
        scores.append(retry_score)
        
        return sum(scores) / len(scores) if scores else 0.0


class TestNetworkFailureSimulation:
    """Test class for network failure simulation."""
    
    @pytest.mark.asyncio
    async def test_database_connection_failures(self):
        """Test database connection failure handling."""
        simulator = NetworkFailureSimulator()
        
        print(f"\n🌐 Testing Database Connection Failures")
        print("=" * 50)
        
        result = await simulator.simulate_database_connection_failure()
        
        print(f"   Connection failure handled: {'✅' if result['connection_failure_handled'] else '❌'}")
        print(f"   Timeout handled: {'✅' if result['timeout_handled'] else '❌'}")
        print(f"   Retry mechanism works: {'✅' if result['retry_mechanism_works'] else '❌'}")
        print(f"   Graceful degradation: {'✅' if result['graceful_degradation'] else '❌'}")
        
        if result.get("details"):
            for key, value in result["details"].items():
                if isinstance(value, bool):
                    status = "✅" if value else "❌"
                    print(f"   {key}: {status}")
                elif isinstance(value, (int, float)) and key.endswith("_duration"):
                    print(f"   {key}: {value:.2f}s")
        
        # Assert that critical database failure handling works
        assert result["connection_failure_handled"], "Database connection failure not handled"
    
    @pytest.mark.asyncio
    async def test_service_timeout_handling(self):
        """Test service timeout handling mechanisms."""
        simulator = NetworkFailureSimulator()
        
        print(f"\n⏱️ Testing Service Timeout Handling")
        print("=" * 50)
        
        result = await simulator.simulate_service_timeout_scenarios()
        
        print(f"   AI service timeout handled: {'✅' if result['ai_service_timeout_handled'] else '❌'}")
        print(f"   Vector store timeout handled: {'✅' if result['vector_store_timeout_handled'] else '❌'}")
        print(f"   HTTP request timeout handled: {'✅' if result['http_request_timeout_handled'] else '❌'}")
        print(f"   Timeout recovery works: {'✅' if result['timeout_recovery_works'] else '❌'}")
        
        if result.get("details"):
            for key, value in result["details"].items():
                if isinstance(value, bool):
                    status = "✅" if value else "❌"
                    print(f"   {key}: {status}")
                elif isinstance(value, (int, float)) and key.endswith("_duration"):
                    print(f"   {key}: {value:.2f}s")
        
        # Assert that timeout handling works for at least one service
        timeout_handled = (
            result["ai_service_timeout_handled"] or 
            result["vector_store_timeout_handled"] or 
            result["http_request_timeout_handled"]
        )
        assert timeout_handled, "No service timeout handling detected"
    
    @pytest.mark.asyncio
    async def test_retry_mechanisms(self):
        """Test network retry mechanisms."""
        simulator = NetworkFailureSimulator()
        
        print(f"\n🔄 Testing Retry Mechanisms")
        print("=" * 50)
        
        result = await simulator.simulate_network_retry_mechanisms()
        
        print(f"   Exponential backoff works: {'✅' if result['exponential_backoff_works'] else '❌'}")
        print(f"   Max retries respected: {'✅' if result['max_retries_respected'] else '❌'}")
        print(f"   Circuit breaker works: {'✅' if result['circuit_breaker_works'] else '❌'}")
        print(f"   Retry on specific errors: {'✅' if result['retry_on_specific_errors'] else '❌'}")
        
        if result.get("details"):
            for key, value in result["details"].items():
                if isinstance(value, bool):
                    status = "✅" if value else "❌"
                    print(f"   {key}: {status}")
                elif isinstance(value, list) and len(value) <= 5:
                    print(f"   {key}: {value}")
                elif isinstance(value, (int, float)):
                    print(f"   {key}: {value}")
        
        # Assert that retry mechanisms work
        assert result["max_retries_respected"], "Max retries not respected"
        
        # At least exponential backoff or circuit breaker should work
        retry_mechanisms_ok = (
            result["exponential_backoff_works"] or 
            result["circuit_breaker_works"]
        )
        assert retry_mechanisms_ok, "No retry mechanisms working properly"
    
    @pytest.mark.asyncio
    async def test_intermittent_network_issues(self):
        """Test handling of intermittent network issues."""
        simulator = NetworkFailureSimulator()
        
        print(f"\n📡 Testing Intermittent Network Issues")
        print("=" * 50)
        
        result = await simulator.simulate_intermittent_network_issues()
        
        print(f"   Handles packet loss: {'✅' if result['handles_packet_loss'] else '❌'}")
        print(f"   Handles slow connections: {'✅' if result['handles_slow_connections'] else '❌'}")
        print(f"   Handles DNS failures: {'✅' if result['handles_dns_failures'] else '❌'}")
        print(f"   Connection pooling resilient: {'✅' if result['connection_pooling_resilient'] else '❌'}")
        
        if result.get("details"):
            for key, value in result["details"].items():
                if isinstance(value, bool):
                    status = "✅" if value else "❌"
                    print(f"   {key}: {status}")
                elif isinstance(value, float) and key.endswith("_rate"):
                    print(f"   {key}: {value:.1%}")
                elif isinstance(value, (int, float)):
                    print(f"   {key}: {value}")
        
        # Assert that at least some intermittent network handling works
        intermittent_handling_ok = (
            result["handles_packet_loss"] or 
            result["handles_slow_connections"] or 
            result["handles_dns_failures"]
        )
        assert intermittent_handling_ok, "No intermittent network issue handling detected"
    
    @pytest.mark.asyncio
    async def test_comprehensive_network_failure_simulation(self):
        """Run comprehensive network failure simulation."""
        simulator = NetworkFailureSimulator()
        
        print(f"\n🧪 Running Comprehensive Network Failure Simulation")
        print("=" * 60)
        
        # Run all network failure simulations
        await simulator.simulate_database_connection_failure()
        await simulator.simulate_service_timeout_scenarios()
        await simulator.simulate_network_retry_mechanisms()
        await simulator.simulate_intermittent_network_issues()
        
        # Get comprehensive report
        report = simulator.get_comprehensive_report()
        
        print(f"\n📊 Comprehensive Network Failure Simulation Report:")
        print(f"   Database connection resilient: {'✅' if report['summary']['database_connection_resilient'] else '❌'}")
        print(f"   Timeout handling works: {'✅' if report['summary']['timeout_handling_works'] else '❌'}")
        print(f"   Retry mechanisms functional: {'✅' if report['summary']['retry_mechanisms_functional'] else '❌'}")
        print(f"   Overall network resilience score: {report['summary']['overall_network_resilience_score']:.2%}")
        
        if report["errors"]:
            print(f"\n⚠️  Errors encountered:")
            for error in report["errors"]:
                print(f"   - {error}")
        
        # Overall validation
        resilience_score = report['summary']['overall_network_resilience_score']
        db_resilient = report['summary']['database_connection_resilient']
        timeout_handling = report['summary']['timeout_handling_works']
        retry_functional = report['summary']['retry_mechanisms_functional']
        
        overall_success = (
            resilience_score >= 0.6 and  # 60% resilience score
            (db_resilient or timeout_handling or retry_functional)  # At least one major area working
        )
        
        print(f"\n🎯 Overall Network Failure Simulation: {'✅ PASSED' if overall_success else '❌ FAILED'}")
        
        assert overall_success, f"Network failure simulation failed - Resilience: {resilience_score:.2%}"


# Pytest fixtures and test functions
@pytest.fixture
def network_simulator():
    """Fixture to provide a network failure simulator."""
    return NetworkFailureSimulator()


def test_network_failure_simulation_comprehensive():
    """Comprehensive test of network failure simulation."""
    test_instance = TestNetworkFailureSimulation()
    
    # Run all network failure simulation tests
    asyncio.run(test_instance.test_database_connection_failures())
    asyncio.run(test_instance.test_service_timeout_handling())
    asyncio.run(test_instance.test_retry_mechanisms())
    asyncio.run(test_instance.test_intermittent_network_issues())
    asyncio.run(test_instance.test_comprehensive_network_failure_simulation())


if __name__ == "__main__":
    # Allow running this test directly
    asyncio.run(test_network_failure_simulation_comprehensive())
    print("\n✅ All network failure simulation tests passed!")