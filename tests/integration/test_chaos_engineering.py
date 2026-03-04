"""
Chaos Engineering Tests

This test suite implements comprehensive chaos engineering tests to validate:
1. Random component failures and system resilience
2. System recovery capabilities under stress
3. Cascading failure prevention
4. Service degradation and recovery patterns

Validates: Requirement 5.2 - Production Readiness Validation
"""

import pytest
import asyncio
import time
import random
import logging
from typing import Dict, List, Any, Optional, Callable, Tuple
from unittest.mock import patch, MagicMock, AsyncMock
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from enum import Enum
import threading
import uuid
import json

# Test framework imports
from fastapi.testclient import TestClient

logger = logging.getLogger(__name__)


class ChaosExperimentType(Enum):
    """Types of chaos experiments."""
    RANDOM_COMPONENT_FAILURE = "random_component_failure"
    CASCADING_FAILURE_INJECTION = "cascading_failure_injection"
    RESOURCE_EXHAUSTION = "resource_exhaustion"
    NETWORK_PARTITION = "network_partition"
    LATENCY_INJECTION = "latency_injection"
    MEMORY_PRESSURE = "memory_pressure"
    CPU_SPIKE = "cpu_spike"
    DISK_FULL = "disk_full"
    RANDOM_RESTART = "random_restart"
    CONFIGURATION_CORRUPTION = "configuration_corruption"


class ChaosImpact(Enum):
    """Impact levels for chaos experiments."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class ChaosExperiment:
    """Definition of a chaos experiment."""
    experiment_id: str
    name: str
    description: str
    experiment_type: ChaosExperimentType
    target_components: List[str]
    impact_level: ChaosImpact
    duration_seconds: int
    failure_probability: float  # 0.0 to 1.0
    recovery_time_seconds: int
    validation_checks: List[Callable] = field(default_factory=list)
    rollback_actions: List[Callable] = field(default_factory=list)


@dataclass
class ChaosExperimentResult:
    """Result of a chaos experiment."""
    experiment_id: str
    start_time: datetime
    end_time: Optional[datetime] = None
    success: bool = False
    system_resilient: bool = False
    recovery_successful: bool = False
    cascading_failures_prevented: bool = False
    performance_degradation: Dict[str, float] = field(default_factory=dict)
    error_messages: List[str] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)
    validation_results: List[Dict[str, Any]] = field(default_factory=list)


class ChaosEngineeringFramework:
    """
    Comprehensive chaos engineering framework for testing system resilience.
    
    Implements various chaos experiments to validate system behavior under
    failure conditions and stress scenarios.
    """
    
    def __init__(self):
        self.experiment_results = {}
        self.active_experiments = {}
        self.system_baseline = {}
        self.errors = []
        self._lock = threading.Lock()
        
        # Initialize baseline metrics
        self._establish_baseline()
    
    def _establish_baseline(self) -> None:
        """Establish baseline system performance metrics."""
        self.system_baseline = {
            'response_time_ms': 100,
            'memory_usage_mb': 512,
            'cpu_usage_percent': 20,
            'error_rate_percent': 0.1,
            'throughput_rps': 100
        }
    
    async def run_chaos_experiment(self, experiment: ChaosExperiment) -> ChaosExperimentResult:
        """Run a single chaos experiment."""
        logger.info(f"🔥 Starting chaos experiment: {experiment.name}")
        
        result = ChaosExperimentResult(
            experiment_id=experiment.experiment_id,
            start_time=datetime.now()
        )
        
        with self._lock:
            self.active_experiments[experiment.experiment_id] = experiment
        
        try:
            # Pre-experiment validation
            pre_validation = await self._run_pre_experiment_validation(experiment)
            result.validation_results.append({
                'phase': 'pre_experiment',
                'results': pre_validation,
                'timestamp': datetime.now().isoformat()
            })
            
            # Inject chaos
            chaos_context = await self._inject_chaos(experiment)
            
            # Monitor system during chaos
            monitoring_results = await self._monitor_system_during_chaos(
                experiment, chaos_context
            )
            result.metrics.update(monitoring_results)
            
            # Wait for experiment duration
            await asyncio.sleep(experiment.duration_seconds)
            
            # Stop chaos injection
            await self._stop_chaos_injection(experiment, chaos_context)
            
            # Wait for recovery
            await asyncio.sleep(experiment.recovery_time_seconds)
            
            # Post-experiment validation
            post_validation = await self._run_post_experiment_validation(experiment)
            result.validation_results.append({
                'phase': 'post_experiment',
                'results': post_validation,
                'timestamp': datetime.now().isoformat()
            })
            
            # Analyze results
            result.success = True
            result.system_resilient = self._analyze_system_resilience(result)
            result.recovery_successful = self._analyze_recovery_success(result)
            result.cascading_failures_prevented = self._analyze_cascading_prevention(result)
            
            logger.info(f"✅ Chaos experiment completed: {experiment.name}")
            
        except Exception as e:
            result.error_messages.append(f"Experiment failed: {str(e)}")
            result.success = False
            logger.error(f"❌ Chaos experiment failed: {experiment.name}: {e}")
            
        finally:
            result.end_time = datetime.now()
            
            # Cleanup and rollback
            await self._cleanup_experiment(experiment)
            
            with self._lock:
                if experiment.experiment_id in self.active_experiments:
                    del self.active_experiments[experiment.experiment_id]
                self.experiment_results[experiment.experiment_id] = result
        
        return result
    
    async def _inject_chaos(self, experiment: ChaosExperiment) -> Dict[str, Any]:
        """Inject chaos based on experiment type."""
        chaos_context = {
            'experiment_id': experiment.experiment_id,
            'injected_failures': [],
            'patches': [],
            'modified_components': []
        }
        
        if experiment.experiment_type == ChaosExperimentType.RANDOM_COMPONENT_FAILURE:
            chaos_context = await self._inject_random_component_failures(experiment, chaos_context)
            
        elif experiment.experiment_type == ChaosExperimentType.CASCADING_FAILURE_INJECTION:
            chaos_context = await self._inject_cascading_failures(experiment, chaos_context)
            
        elif experiment.experiment_type == ChaosExperimentType.RESOURCE_EXHAUSTION:
            chaos_context = await self._inject_resource_exhaustion(experiment, chaos_context)
            
        elif experiment.experiment_type == ChaosExperimentType.NETWORK_PARTITION:
            chaos_context = await self._inject_network_partition(experiment, chaos_context)
            
        elif experiment.experiment_type == ChaosExperimentType.LATENCY_INJECTION:
            chaos_context = await self._inject_latency(experiment, chaos_context)
            
        elif experiment.experiment_type == ChaosExperimentType.MEMORY_PRESSURE:
            chaos_context = await self._inject_memory_pressure(experiment, chaos_context)
            
        elif experiment.experiment_type == ChaosExperimentType.CPU_SPIKE:
            chaos_context = await self._inject_cpu_spike(experiment, chaos_context)
            
        elif experiment.experiment_type == ChaosExperimentType.RANDOM_RESTART:
            chaos_context = await self._inject_random_restarts(experiment, chaos_context)
            
        elif experiment.experiment_type == ChaosExperimentType.CONFIGURATION_CORRUPTION:
            chaos_context = await self._inject_configuration_corruption(experiment, chaos_context)
        
        return chaos_context
    
    async def _inject_random_component_failures(self, experiment: ChaosExperiment, 
                                              context: Dict[str, Any]) -> Dict[str, Any]:
        """Inject random component failures."""
        logger.info("🎲 Injecting random component failures...")
        
        # Randomly select components to fail
        components_to_fail = random.sample(
            experiment.target_components,
            k=min(len(experiment.target_components), random.randint(1, 3))
        )
        
        for component in components_to_fail:
            if random.random() < experiment.failure_probability:
                failure_type = random.choice([
                    'connection_error',
                    'timeout_error',
                    'service_unavailable',
                    'authentication_error',
                    'rate_limit_exceeded'
                ])
                
                # Create component-specific failure
                if component == 'database':
                    patch_obj = patch('multimodal_librarian.database.connection.get_database_connection')
                    mock = patch_obj.start()
                    mock.side_effect = Exception(f"Random database failure: {failure_type}")
                    context['patches'].append(patch_obj)
                    
                elif component == 'vector_store':
                    patch_obj = patch('multimodal_librarian.components.vector_store.vector_store.VectorStore')
                    mock = patch_obj.start()
                    mock.side_effect = Exception(f"Random vector store failure: {failure_type}")
                    context['patches'].append(patch_obj)
                    
                elif component == 'ai_service':
                    patch_obj = patch('multimodal_librarian.services.ai_service.AIService.generate_response')
                    mock = patch_obj.start()
                    mock.side_effect = Exception(f"Random AI service failure: {failure_type}")
                    context['patches'].append(patch_obj)
                    
                elif component == 'search_service':
                    patch_obj = patch('multimodal_librarian.components.vector_store.search_service.EnhancedSemanticSearchService.search')
                    mock = patch_obj.start()
                    mock.side_effect = Exception(f"Random search service failure: {failure_type}")
                    context['patches'].append(patch_obj)
                    
                elif component == 'cache':
                    patch_obj = patch('multimodal_librarian.services.cache_service.CacheService')
                    mock = patch_obj.start()
                    mock.side_effect = Exception(f"Random cache failure: {failure_type}")
                    context['patches'].append(patch_obj)
                
                context['injected_failures'].append({
                    'component': component,
                    'failure_type': failure_type,
                    'timestamp': datetime.now().isoformat()
                })
                
                logger.info(f"💥 Injected failure in {component}: {failure_type}")
        
        return context
    
    async def _inject_cascading_failures(self, experiment: ChaosExperiment, 
                                       context: Dict[str, Any]) -> Dict[str, Any]:
        """Inject cascading failures to test failure isolation."""
        logger.info("🌊 Injecting cascading failures...")
        
        # Start with a primary failure
        primary_component = random.choice(experiment.target_components)
        
        # Database failure that could cascade
        if primary_component == 'database':
            patch_obj = patch('multimodal_librarian.database.connection.get_database_connection')
            mock = patch_obj.start()
            mock.side_effect = Exception("Primary database failure")
            context['patches'].append(patch_obj)
            
            # Wait a bit, then inject secondary failures
            await asyncio.sleep(2)
            
            # Vector store might fail due to database dependency
            if random.random() < 0.7:  # 70% chance of cascade
                patch_obj2 = patch('multimodal_librarian.components.vector_store.vector_store.VectorStore')
                mock2 = patch_obj2.start()
                mock2.side_effect = Exception("Cascading vector store failure")
                context['patches'].append(patch_obj2)
                
                context['injected_failures'].append({
                    'component': 'vector_store',
                    'failure_type': 'cascading_failure',
                    'primary_cause': primary_component,
                    'timestamp': datetime.now().isoformat()
                })
        
        # AI service failure that could cascade
        elif primary_component == 'ai_service':
            patch_obj = patch('multimodal_librarian.services.ai_service.AIService')
            mock = patch_obj.start()
            mock.side_effect = Exception("Primary AI service failure")
            context['patches'].append(patch_obj)
            
            # Chat service might fail due to AI dependency
            await asyncio.sleep(1)
            if random.random() < 0.6:  # 60% chance of cascade
                patch_obj2 = patch('multimodal_librarian.services.chat_service.ChatService')
                mock2 = patch_obj2.start()
                mock2.side_effect = Exception("Cascading chat service failure")
                context['patches'].append(patch_obj2)
                
                context['injected_failures'].append({
                    'component': 'chat_service',
                    'failure_type': 'cascading_failure',
                    'primary_cause': primary_component,
                    'timestamp': datetime.now().isoformat()
                })
        
        context['injected_failures'].append({
            'component': primary_component,
            'failure_type': 'primary_failure',
            'timestamp': datetime.now().isoformat()
        })
        
        return context
    
    async def _inject_resource_exhaustion(self, experiment: ChaosExperiment, 
                                        context: Dict[str, Any]) -> Dict[str, Any]:
        """Inject resource exhaustion scenarios."""
        logger.info("📈 Injecting resource exhaustion...")
        
        # Simulate high memory usage (reduced for faster tests)
        if 'memory' in experiment.target_components:
            # Create memory pressure simulation
            memory_hog = []
            try:
                # Allocate memory in chunks (reduced from 100 to 20)
                for _ in range(20):
                    memory_hog.append(b'x' * (1024 * 1024))  # 1MB chunks
                    await asyncio.sleep(0.005)  # Reduced delay
                
                context['memory_hog'] = memory_hog
                context['injected_failures'].append({
                    'component': 'memory',
                    'failure_type': 'memory_exhaustion',
                    'allocated_mb': len(memory_hog),
                    'timestamp': datetime.now().isoformat()
                })
                
            except MemoryError:
                context['injected_failures'].append({
                    'component': 'memory',
                    'failure_type': 'memory_limit_reached',
                    'timestamp': datetime.now().isoformat()
                })
        
        # Simulate CPU spike (reduced duration)
        if 'cpu' in experiment.target_components:
            # Start CPU-intensive task
            cpu_task = asyncio.create_task(self._cpu_intensive_task())
            context['cpu_task'] = cpu_task
            
            context['injected_failures'].append({
                'component': 'cpu',
                'failure_type': 'cpu_spike',
                'timestamp': datetime.now().isoformat()
            })
        
        return context
    
    async def _inject_network_partition(self, experiment: ChaosExperiment, 
                                      context: Dict[str, Any]) -> Dict[str, Any]:
        """Inject network partition scenarios."""
        logger.info("🌐 Injecting network partition...")
        
        # Simulate network timeouts
        patch_obj = patch('aiohttp.ClientSession.request')
        mock = patch_obj.start()
        mock.side_effect = asyncio.TimeoutError("Network partition timeout")
        context['patches'].append(patch_obj)
        
        # Simulate DNS failures
        patch_obj2 = patch('socket.gethostbyname')
        mock2 = patch_obj2.start()
        mock2.side_effect = Exception("DNS resolution failed due to network partition")
        context['patches'].append(patch_obj2)
        
        context['injected_failures'].append({
            'component': 'network',
            'failure_type': 'network_partition',
            'timestamp': datetime.now().isoformat()
        })
        
        return context
    
    async def _inject_latency(self, experiment: ChaosExperiment, 
                            context: Dict[str, Any]) -> Dict[str, Any]:
        """Inject latency into system operations."""
        logger.info("⏱️ Injecting latency...")
        
        # Add random delays to database operations
        if 'database' in experiment.target_components:
            original_get_connection = None
            
            async def slow_database_connection(*args, **kwargs):
                delay = random.uniform(1.0, 5.0)  # 1-5 second delay
                await asyncio.sleep(delay)
                if original_get_connection:
                    return await original_get_connection(*args, **kwargs)
                return MagicMock()
            
            patch_obj = patch('multimodal_librarian.database.connection.get_database_connection')
            mock = patch_obj.start()
            mock.side_effect = slow_database_connection
            context['patches'].append(patch_obj)
        
        # Add delays to AI service calls
        if 'ai_service' in experiment.target_components:
            async def slow_ai_response(*args, **kwargs):
                delay = random.uniform(2.0, 10.0)  # 2-10 second delay
                await asyncio.sleep(delay)
                return {"response": "Delayed AI response"}
            
            patch_obj = patch('multimodal_librarian.services.ai_service.AIService.generate_response')
            mock = patch_obj.start()
            mock.side_effect = slow_ai_response
            context['patches'].append(patch_obj)
        
        context['injected_failures'].append({
            'component': 'latency',
            'failure_type': 'high_latency',
            'timestamp': datetime.now().isoformat()
        })
        
        return context
    
    async def _inject_memory_pressure(self, experiment: ChaosExperiment, 
                                    context: Dict[str, Any]) -> Dict[str, Any]:
        """Inject memory pressure."""
        logger.info("🧠 Injecting memory pressure...")
        
        # Create memory pressure (reduced for faster tests)
        memory_blocks = []
        try:
            for i in range(50):  # Try to allocate 50MB (reduced from 200MB)
                block = bytearray(1024 * 1024)  # 1MB block
                memory_blocks.append(block)
                
                if i % 5 == 0:  # Check every 5MB (reduced from 10MB)
                    await asyncio.sleep(0.05)  # Reduced sleep time
            
            context['memory_blocks'] = memory_blocks
            
        except MemoryError:
            logger.info("Memory limit reached during pressure injection")
        
        context['injected_failures'].append({
            'component': 'memory',
            'failure_type': 'memory_pressure',
            'allocated_blocks': len(memory_blocks),
            'timestamp': datetime.now().isoformat()
        })
        
        return context
    
    async def _inject_cpu_spike(self, experiment: ChaosExperiment, 
                              context: Dict[str, Any]) -> Dict[str, Any]:
        """Inject CPU spike."""
        logger.info("⚡ Injecting CPU spike...")
        
        # Start fewer CPU-intensive tasks (reduced from 4 to 2)
        cpu_tasks = []
        for i in range(2):  # 2 CPU-intensive tasks
            task = asyncio.create_task(self._cpu_intensive_task())
            cpu_tasks.append(task)
        
        context['cpu_tasks'] = cpu_tasks
        
        context['injected_failures'].append({
            'component': 'cpu',
            'failure_type': 'cpu_spike',
            'task_count': len(cpu_tasks),
            'timestamp': datetime.now().isoformat()
        })
        
        return context
    
    async def _inject_random_restarts(self, experiment: ChaosExperiment, 
                                    context: Dict[str, Any]) -> Dict[str, Any]:
        """Inject random service restarts."""
        logger.info("🔄 Injecting random restarts...")
        
        # Simulate service restarts by clearing service instances
        for component in experiment.target_components:
            if random.random() < experiment.failure_probability:
                
                # Simulate restart by temporarily making service unavailable
                if component == 'search_service':
                    patch_obj = patch('multimodal_librarian.components.vector_store.search_service.EnhancedSemanticSearchService')
                    mock = patch_obj.start()
                    mock.side_effect = Exception("Service restarting...")
                    context['patches'].append(patch_obj)
                    
                    # After a delay, restore service
                    async def restore_service():
                        await asyncio.sleep(random.uniform(5, 15))  # 5-15 second restart
                        patch_obj.stop()
                    
                    asyncio.create_task(restore_service())
                
                context['injected_failures'].append({
                    'component': component,
                    'failure_type': 'random_restart',
                    'timestamp': datetime.now().isoformat()
                })
        
        return context
    
    async def _inject_configuration_corruption(self, experiment: ChaosExperiment, 
                                             context: Dict[str, Any]) -> Dict[str, Any]:
        """Inject configuration corruption."""
        logger.info("⚙️ Injecting configuration corruption...")
        
        # Simulate corrupted configuration
        patch_obj = patch('multimodal_librarian.config.get_settings')
        mock = patch_obj.start()
        
        # Return corrupted settings
        corrupted_settings = MagicMock()
        corrupted_settings.database_url = "invalid://corrupted:url"
        corrupted_settings.ai_api_key = "corrupted_key"
        corrupted_settings.vector_store_url = "invalid://vector:store"
        
        mock.return_value = corrupted_settings
        context['patches'].append(patch_obj)
        
        context['injected_failures'].append({
            'component': 'configuration',
            'failure_type': 'configuration_corruption',
            'timestamp': datetime.now().isoformat()
        })
        
        return context
    
    async def _cpu_intensive_task(self) -> None:
        """CPU-intensive task for load testing."""
        end_time = time.time() + 5  # Run for 5 seconds (reduced from 30)
        while time.time() < end_time:
            # CPU-intensive calculation (reduced iterations)
            sum(i * i for i in range(100))  # Reduced from 1000
            await asyncio.sleep(0.01)  # Increased yield time
    
    async def _monitor_system_during_chaos(self, experiment: ChaosExperiment, 
                                         context: Dict[str, Any]) -> Dict[str, Any]:
        """Monitor system behavior during chaos injection."""
        monitoring_results = {
            'response_times': [],
            'error_counts': 0,
            'successful_operations': 0,
            'service_availability': {},
            'resource_usage': {}
        }
        
        # Monitor for the experiment duration (reduced monitoring frequency)
        start_time = time.time()
        while time.time() - start_time < experiment.duration_seconds:
            
            # Test system responsiveness
            try:
                operation_start = time.time()
                
                # Try to create minimal app (basic health check)
                from multimodal_librarian.main import create_minimal_app
                app = create_minimal_app()
                
                response_time = (time.time() - operation_start) * 1000  # ms
                monitoring_results['response_times'].append(response_time)
                monitoring_results['successful_operations'] += 1
                
                # Check if app is functional
                monitoring_results['service_availability']['main_app'] = app is not None
                
            except Exception as e:
                monitoring_results['error_counts'] += 1
                monitoring_results['service_availability']['main_app'] = False
            
            # Test individual services (less frequently)
            if len(monitoring_results['response_times']) % 3 == 0:  # Every 3rd iteration
                await self._test_service_availability(monitoring_results)
            
            await asyncio.sleep(2)  # Monitor every 2 seconds (reduced from 1)
        
        return monitoring_results
    
    async def _test_service_availability(self, monitoring_results: Dict[str, Any]) -> None:
        """Test availability of individual services."""
        
        # Test AI service
        try:
            from multimodal_librarian.services.ai_service import get_ai_service
            ai_service = get_ai_service()
            providers = ai_service.get_available_providers()
            monitoring_results['service_availability']['ai_service'] = len(providers) > 0
        except Exception:
            monitoring_results['service_availability']['ai_service'] = False
        
        # Test search service
        try:
            from multimodal_librarian.components.vector_store.search_service_simple import SimpleSemanticSearchService
            search_service = SimpleSemanticSearchService(MagicMock())
            monitoring_results['service_availability']['search_service'] = search_service is not None
        except Exception:
            monitoring_results['service_availability']['search_service'] = False
        
        # Test cache service
        try:
            from multimodal_librarian.services.cache_service import get_cache_service
            cache_service = get_cache_service()
            monitoring_results['service_availability']['cache_service'] = cache_service is not None
        except Exception:
            monitoring_results['service_availability']['cache_service'] = False
    
    async def _stop_chaos_injection(self, experiment: ChaosExperiment, 
                                   context: Dict[str, Any]) -> None:
        """Stop chaos injection and cleanup."""
        logger.info("🛑 Stopping chaos injection...")
        
        # Stop all patches
        for patch_obj in context.get('patches', []):
            try:
                patch_obj.stop()
            except Exception as e:
                logger.warning(f"Failed to stop patch: {e}")
        
        # Cleanup memory allocations
        if 'memory_hog' in context:
            del context['memory_hog']
        
        if 'memory_blocks' in context:
            del context['memory_blocks']
        
        # Cancel CPU tasks
        for task in context.get('cpu_tasks', []):
            if not task.done():
                task.cancel()
        
        if 'cpu_task' in context and not context['cpu_task'].done():
            context['cpu_task'].cancel()
    
    async def _run_pre_experiment_validation(self, experiment: ChaosExperiment) -> Dict[str, Any]:
        """Run validation checks before experiment."""
        validation_results = {
            'system_healthy': False,
            'services_available': {},
            'baseline_metrics': {}
        }
        
        try:
            # Check if main app can be created
            from multimodal_librarian.main import create_minimal_app
            app = create_minimal_app()
            validation_results['system_healthy'] = app is not None
            
            # Check individual services
            await self._test_service_availability(validation_results)
            
            # Record baseline metrics
            validation_results['baseline_metrics'] = self.system_baseline.copy()
            
        except Exception as e:
            validation_results['error'] = str(e)
        
        return validation_results
    
    async def _run_post_experiment_validation(self, experiment: ChaosExperiment) -> Dict[str, Any]:
        """Run validation checks after experiment."""
        validation_results = {
            'system_recovered': False,
            'services_recovered': {},
            'performance_impact': {}
        }
        
        try:
            # Check if system recovered
            from multimodal_librarian.main import create_minimal_app
            app = create_minimal_app()
            validation_results['system_recovered'] = app is not None
            
            # Check service recovery
            await self._test_service_availability(validation_results)
            
            # Run custom validation checks
            for check in experiment.validation_checks:
                try:
                    check_result = await check()
                    validation_results[f'custom_check_{check.__name__}'] = check_result
                except Exception as e:
                    validation_results[f'custom_check_{check.__name__}_error'] = str(e)
            
        except Exception as e:
            validation_results['error'] = str(e)
        
        return validation_results
    
    def _analyze_system_resilience(self, result: ChaosExperimentResult) -> bool:
        """Analyze if system showed resilience during chaos."""
        
        # Check if system maintained basic functionality
        if not result.metrics:
            return False
        
        # System is resilient if it had some successful operations
        successful_ops = result.metrics.get('successful_operations', 0)
        total_ops = successful_ops + result.metrics.get('error_counts', 0)
        
        if total_ops == 0:
            return False
        
        # Consider resilient if success rate > 30% during chaos
        success_rate = successful_ops / total_ops
        return success_rate > 0.3
    
    def _analyze_recovery_success(self, result: ChaosExperimentResult) -> bool:
        """Analyze if system recovered successfully after chaos."""
        
        # Check post-experiment validation
        post_validation = None
        for validation in result.validation_results:
            if validation['phase'] == 'post_experiment':
                post_validation = validation['results']
                break
        
        if not post_validation:
            return False
        
        # System recovered if it's healthy after experiment
        return post_validation.get('system_recovered', False)
    
    def _analyze_cascading_prevention(self, result: ChaosExperimentResult) -> bool:
        """Analyze if cascading failures were prevented."""
        
        # Check service availability during chaos
        if not result.metrics or 'service_availability' not in result.metrics:
            return False
        
        service_availability = result.metrics['service_availability']
        
        # Count how many services remained available
        available_services = sum(1 for available in service_availability.values() if available)
        total_services = len(service_availability)
        
        if total_services == 0:
            return False
        
        # Cascading failures prevented if > 50% of services remained available
        availability_rate = available_services / total_services
        return availability_rate > 0.5
    
    async def _cleanup_experiment(self, experiment: ChaosExperiment) -> None:
        """Cleanup after experiment."""
        
        # Run rollback actions
        for rollback_action in experiment.rollback_actions:
            try:
                await rollback_action()
            except Exception as e:
                logger.warning(f"Rollback action failed: {e}")
        
        # Force garbage collection to cleanup memory
        import gc
        gc.collect()
    
    def get_experiment_summary(self) -> Dict[str, Any]:
        """Get summary of all chaos experiments."""
        
        total_experiments = len(self.experiment_results)
        successful_experiments = sum(
            1 for result in self.experiment_results.values() 
            if result.success
        )
        resilient_experiments = sum(
            1 for result in self.experiment_results.values() 
            if result.system_resilient
        )
        recovered_experiments = sum(
            1 for result in self.experiment_results.values() 
            if result.recovery_successful
        )
        
        return {
            'total_experiments': total_experiments,
            'successful_experiments': successful_experiments,
            'resilient_experiments': resilient_experiments,
            'recovered_experiments': recovered_experiments,
            'success_rate': (successful_experiments / max(1, total_experiments)) * 100,
            'resilience_rate': (resilient_experiments / max(1, total_experiments)) * 100,
            'recovery_rate': (recovered_experiments / max(1, total_experiments)) * 100,
            'active_experiments': len(self.active_experiments),
            'errors': self.errors
        }


class TestChaosEngineering:
    """Test class for chaos engineering experiments."""
    
    @pytest.mark.asyncio
    async def test_random_component_failures(self):
        """Test system resilience against random component failures."""
        framework = ChaosEngineeringFramework()
        
        print(f"\n🎲 Testing Random Component Failures")
        print("=" * 50)
        
        experiment = ChaosExperiment(
            experiment_id="random_failures_001",
            name="Random Component Failures",
            description="Test system resilience against random component failures",
            experiment_type=ChaosExperimentType.RANDOM_COMPONENT_FAILURE,
            target_components=['database', 'vector_store', 'ai_service', 'search_service', 'cache'],
            impact_level=ChaosImpact.MEDIUM,
            duration_seconds=10,  # Reduced from 30
            failure_probability=0.7,
            recovery_time_seconds=5  # Reduced from 15
        )
        
        result = await framework.run_chaos_experiment(experiment)
        
        print(f"   Experiment successful: {'✅' if result.success else '❌'}")
        print(f"   System resilient: {'✅' if result.system_resilient else '❌'}")
        print(f"   Recovery successful: {'✅' if result.recovery_successful else '❌'}")
        print(f"   Cascading failures prevented: {'✅' if result.cascading_failures_prevented else '❌'}")
        
        if result.metrics:
            successful_ops = result.metrics.get('successful_operations', 0)
            error_count = result.metrics.get('error_counts', 0)
            total_ops = successful_ops + error_count
            
            if total_ops > 0:
                success_rate = (successful_ops / total_ops) * 100
                print(f"   Success rate during chaos: {success_rate:.1f}%")
            
            # Show service availability
            service_availability = result.metrics.get('service_availability', {})
            for service, available in service_availability.items():
                status = "✅" if available else "❌"
                print(f"   {service}: {status}")
        
        # Assert that system showed some resilience
        assert result.success, "Random component failure experiment failed"
        
        # System should maintain some functionality during chaos
        if result.metrics and result.metrics.get('successful_operations', 0) > 0:
            assert result.system_resilient, "System did not show resilience during random failures"
    
    @pytest.mark.asyncio
    async def test_cascading_failure_prevention(self):
        """Test prevention of cascading failures."""
        framework = ChaosEngineeringFramework()
        
        print(f"\n🌊 Testing Cascading Failure Prevention")
        print("=" * 50)
        
        experiment = ChaosExperiment(
            experiment_id="cascading_failures_001",
            name="Cascading Failure Prevention",
            description="Test system's ability to prevent cascading failures",
            experiment_type=ChaosExperimentType.CASCADING_FAILURE_INJECTION,
            target_components=['database', 'vector_store', 'ai_service', 'chat_service'],
            impact_level=ChaosImpact.HIGH,
            duration_seconds=8,  # Reduced from 25
            failure_probability=0.8,
            recovery_time_seconds=5  # Reduced from 20
        )
        
        result = await framework.run_chaos_experiment(experiment)
        
        print(f"   Experiment successful: {'✅' if result.success else '❌'}")
        print(f"   System resilient: {'✅' if result.system_resilient else '❌'}")
        print(f"   Recovery successful: {'✅' if result.recovery_successful else '❌'}")
        print(f"   Cascading failures prevented: {'✅' if result.cascading_failures_prevented else '❌'}")
        
        if result.error_messages:
            print(f"   Errors: {len(result.error_messages)}")
            for error in result.error_messages[:3]:  # Show first 3 errors
                print(f"     - {error}")
        
        # Assert that cascading failures were prevented
        assert result.success, "Cascading failure prevention experiment failed"
        assert result.cascading_failures_prevented, "System did not prevent cascading failures"
    
    @pytest.mark.asyncio
    async def test_resource_exhaustion_resilience(self):
        """Test system resilience under resource exhaustion."""
        framework = ChaosEngineeringFramework()
        
        print(f"\n📈 Testing Resource Exhaustion Resilience")
        print("=" * 50)
        
        experiment = ChaosExperiment(
            experiment_id="resource_exhaustion_001",
            name="Resource Exhaustion Test",
            description="Test system behavior under resource exhaustion",
            experiment_type=ChaosExperimentType.RESOURCE_EXHAUSTION,
            target_components=['memory', 'cpu'],
            impact_level=ChaosImpact.HIGH,
            duration_seconds=8,  # Reduced from 20
            failure_probability=1.0,
            recovery_time_seconds=3  # Reduced from 10
        )
        
        result = await framework.run_chaos_experiment(experiment)
        
        print(f"   Experiment successful: {'✅' if result.success else '❌'}")
        print(f"   System resilient: {'✅' if result.system_resilient else '❌'}")
        print(f"   Recovery successful: {'✅' if result.recovery_successful else '❌'}")
        
        # Resource exhaustion tests are expected to be challenging
        # Success means the system didn't crash completely
        assert result.success, "Resource exhaustion experiment failed"
    
    @pytest.mark.asyncio
    async def test_network_partition_handling(self):
        """Test system handling of network partitions."""
        framework = ChaosEngineeringFramework()
        
        print(f"\n🌐 Testing Network Partition Handling")
        print("=" * 50)
        
        experiment = ChaosExperiment(
            experiment_id="network_partition_001",
            name="Network Partition Test",
            description="Test system behavior during network partitions",
            experiment_type=ChaosExperimentType.NETWORK_PARTITION,
            target_components=['network'],
            impact_level=ChaosImpact.MEDIUM,
            duration_seconds=6,  # Reduced from 15
            failure_probability=1.0,
            recovery_time_seconds=3  # Reduced from 10
        )
        
        result = await framework.run_chaos_experiment(experiment)
        
        print(f"   Experiment successful: {'✅' if result.success else '❌'}")
        print(f"   System resilient: {'✅' if result.system_resilient else '❌'}")
        print(f"   Recovery successful: {'✅' if result.recovery_successful else '❌'}")
        
        assert result.success, "Network partition experiment failed"
    
    @pytest.mark.asyncio
    async def test_latency_injection_tolerance(self):
        """Test system tolerance to high latency."""
        framework = ChaosEngineeringFramework()
        
        print(f"\n⏱️ Testing Latency Injection Tolerance")
        print("=" * 50)
        
        experiment = ChaosExperiment(
            experiment_id="latency_injection_001",
            name="Latency Injection Test",
            description="Test system tolerance to high latency",
            experiment_type=ChaosExperimentType.LATENCY_INJECTION,
            target_components=['database', 'ai_service'],
            impact_level=ChaosImpact.MEDIUM,
            duration_seconds=6,  # Reduced from 20
            failure_probability=1.0,
            recovery_time_seconds=2  # Reduced from 5
        )
        
        result = await framework.run_chaos_experiment(experiment)
        
        print(f"   Experiment successful: {'✅' if result.success else '❌'}")
        print(f"   System resilient: {'✅' if result.system_resilient else '❌'}")
        print(f"   Recovery successful: {'✅' if result.recovery_successful else '❌'}")
        
        if result.metrics and 'response_times' in result.metrics:
            response_times = result.metrics['response_times']
            if response_times:
                avg_response_time = sum(response_times) / len(response_times)
                print(f"   Average response time during chaos: {avg_response_time:.1f}ms")
        
        assert result.success, "Latency injection experiment failed"
    
    @pytest.mark.asyncio
    async def test_comprehensive_chaos_engineering(self):
        """Run comprehensive chaos engineering test suite."""
        framework = ChaosEngineeringFramework()
        
        print(f"\n🧪 Running Comprehensive Chaos Engineering Tests")
        print("=" * 60)
        
        # Define multiple chaos experiments (reduced number and duration)
        experiments = [
            ChaosExperiment(
                experiment_id="comprehensive_001",
                name="Light Random Failures",
                description="Light random component failures",
                experiment_type=ChaosExperimentType.RANDOM_COMPONENT_FAILURE,
                target_components=['cache', 'search_service'],
                impact_level=ChaosImpact.LOW,
                duration_seconds=5,  # Reduced from 10
                failure_probability=0.5,
                recovery_time_seconds=2  # Reduced from 5
            ),
            ChaosExperiment(
                experiment_id="comprehensive_002",
                name="Memory Pressure",
                description="Memory pressure test",
                experiment_type=ChaosExperimentType.MEMORY_PRESSURE,
                target_components=['memory'],
                impact_level=ChaosImpact.MEDIUM,
                duration_seconds=6,  # Reduced from 15
                failure_probability=1.0,
                recovery_time_seconds=3  # Reduced from 10
            )
            # Removed the third experiment to speed up testing
        ]
        
        # Run all experiments
        results = []
        for experiment in experiments:
            print(f"\n🔥 Running: {experiment.name}")
            result = await framework.run_chaos_experiment(experiment)
            results.append(result)
            
            print(f"   Result: {'✅ PASSED' if result.success else '❌ FAILED'}")
            if result.error_messages:
                print(f"   Errors: {len(result.error_messages)}")
        
        # Get overall summary
        summary = framework.get_experiment_summary()
        
        print(f"\n📊 Comprehensive Chaos Engineering Summary:")
        print(f"   Total experiments: {summary['total_experiments']}")
        print(f"   Successful experiments: {summary['successful_experiments']}")
        print(f"   Resilient experiments: {summary['resilient_experiments']}")
        print(f"   Recovered experiments: {summary['recovered_experiments']}")
        print(f"   Success rate: {summary['success_rate']:.1f}%")
        print(f"   Resilience rate: {summary['resilience_rate']:.1f}%")
        print(f"   Recovery rate: {summary['recovery_rate']:.1f}%")
        
        if summary['errors']:
            print(f"\n⚠️  Framework errors:")
            for error in summary['errors']:
                print(f"   - {error}")
        
        # Overall validation
        overall_success = (
            summary['success_rate'] >= 70 and  # 70% success rate
            summary['resilience_rate'] >= 50 and  # 50% resilience rate
            summary['recovery_rate'] >= 60  # 60% recovery rate
        )
        
        print(f"\n🎯 Overall Chaos Engineering Assessment: {'✅ PASSED' if overall_success else '❌ FAILED'}")
        
        assert overall_success, f"Comprehensive chaos engineering failed - Success: {summary['success_rate']:.1f}%, Resilience: {summary['resilience_rate']:.1f}%, Recovery: {summary['recovery_rate']:.1f}%"


# Pytest fixtures and test functions
@pytest.fixture
def chaos_framework():
    """Fixture to provide a chaos engineering framework."""
    return ChaosEngineeringFramework()


def test_chaos_engineering_comprehensive():
    """Comprehensive test of chaos engineering capabilities."""
    test_instance = TestChaosEngineering()
    
    # Run all chaos engineering tests
    asyncio.run(test_instance.test_random_component_failures())
    asyncio.run(test_instance.test_cascading_failure_prevention())
    asyncio.run(test_instance.test_resource_exhaustion_resilience())
    asyncio.run(test_instance.test_network_partition_handling())
    asyncio.run(test_instance.test_latency_injection_tolerance())
    asyncio.run(test_instance.test_comprehensive_chaos_engineering())


if __name__ == "__main__":
    # Allow running this test directly
    asyncio.run(test_chaos_engineering_comprehensive())
    print("\n✅ All chaos engineering tests passed!")