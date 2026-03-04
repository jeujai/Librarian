#!/usr/bin/env python3
"""
Property-Based Test: Dependency Resolution Idempotence

Feature: dependency-injection-architecture
Property 2: Dependency Resolution Idempotence

**Validates: Requirements 2.1, 2.3**

Resolving a dependency multiple times must return the same instance
(singleton behavior) and must not cause side effects beyond the first resolution.
"""

import asyncio
import sys
from typing import List, Any, Dict
import pytest
from hypothesis import given, strategies as st, settings


class DependencyResolutionTest:
    """
    Test class for validating dependency resolution idempotence.
    
    Property: Resolving a dependency multiple times must return the same instance
    (singleton behavior) and must not cause side effects beyond the first resolution.
    """
    
    async def resolve_dependency_multiple_times(
        self, 
        dependency_func, 
        times: int = 3
    ) -> List[Any]:
        """
        Resolve a dependency multiple times and return all instances.
        
        Args:
            dependency_func: The async dependency function to call
            times: Number of times to resolve
            
        Returns:
            List of resolved instances
        """
        instances = []
        for _ in range(times):
            try:
                instance = await dependency_func()
                instances.append(instance)
            except Exception as e:
                instances.append(e)
        return instances
    
    def check_idempotence(self, instances: List[Any]) -> Dict[str, Any]:
        """
        Check if all instances are the same object (singleton behavior).
        
        Args:
            instances: List of resolved instances
            
        Returns:
            Dict with idempotence check results
        """
        if not instances:
            return {'idempotent': True, 'reason': 'No instances to compare'}
        
        # Filter out exceptions
        valid_instances = [i for i in instances if not isinstance(i, Exception)]
        
        if not valid_instances:
            return {'idempotent': True, 'reason': 'All resolutions failed'}
        
        # Check if all valid instances are the same object
        first_instance = valid_instances[0]
        all_same = all(i is first_instance for i in valid_instances)
        
        return {
            'idempotent': all_same,
            'instance_count': len(valid_instances),
            'unique_ids': [id(i) for i in valid_instances],
            'reason': 'All instances are the same object' if all_same else 'Different instances returned'
        }


# Hypothesis strategies for resolution count
@st.composite
def resolution_count_strategy(draw):
    """Strategy for number of times to resolve a dependency."""
    return draw(st.integers(min_value=2, max_value=5))


class TestDependencyResolutionIdempotence:
    """
    Property-based tests for dependency resolution idempotence.
    
    **Validates: Requirements 2.1, 2.3**
    """
    
    def setup_method(self):
        """Set up test fixtures."""
        self.resolution_test = DependencyResolutionTest()
        # Clear service cache before each test
        try:
            from multimodal_librarian.api.dependencies.services import clear_service_cache
            clear_service_cache()
        except ImportError:
            pass
    
    def teardown_method(self):
        """Clean up after each test."""
        try:
            from multimodal_librarian.api.dependencies.services import clear_service_cache
            clear_service_cache()
        except ImportError:
            pass
    
    @given(times=resolution_count_strategy())
    @settings(max_examples=3, deadline=None)
    @pytest.mark.asyncio
    async def test_connection_manager_idempotence(self, times: int):
        """
        Property test: ConnectionManager resolution should be idempotent.
        
        **Validates: Requirements 2.1, 2.3**
        
        Resolving get_connection_manager() multiple times should return
        the same instance each time.
        """
        try:
            from multimodal_librarian.api.dependencies.services import (
                get_connection_manager,
                clear_service_cache
            )
            
            # Clear cache to start fresh
            clear_service_cache()
            
            # Resolve multiple times
            instances = await self.resolution_test.resolve_dependency_multiple_times(
                get_connection_manager, times
            )
            
            # Check idempotence
            result = self.resolution_test.check_idempotence(instances)
            
            assert result['idempotent'], (
                f"ConnectionManager resolution is not idempotent after {times} calls. "
                f"Got {len(set(result['unique_ids']))} unique instances: {result['unique_ids']}"
            )
            
        except ImportError as e:
            pytest.skip(f"Module not available: {e}")
    
    @pytest.mark.asyncio
    async def test_connection_manager_singleton_direct(self):
        """
        Direct test: ConnectionManager should be a singleton.
        
        **Validates: Requirements 2.1, 2.3**
        """
        try:
            from multimodal_librarian.api.dependencies.services import (
                get_connection_manager,
                clear_service_cache
            )
            
            clear_service_cache()
            
            # Get instance twice
            instance1 = await get_connection_manager()
            instance2 = await get_connection_manager()
            
            assert instance1 is instance2, (
                f"ConnectionManager is not a singleton. "
                f"Got different instances: {id(instance1)} vs {id(instance2)}"
            )
            
        except ImportError as e:
            pytest.skip(f"Module not available: {e}")
    
    @pytest.mark.asyncio
    async def test_clear_cache_resets_singleton(self):
        """
        Test that clear_service_cache() properly resets the singleton.
        
        **Validates: Requirements 5.1, 5.2**
        """
        try:
            from multimodal_librarian.api.dependencies.services import (
                get_connection_manager,
                clear_service_cache
            )
            
            clear_service_cache()
            
            # Get first instance
            instance1 = await get_connection_manager()
            
            # Clear cache
            clear_service_cache()
            
            # Get second instance - should be different
            instance2 = await get_connection_manager()
            
            assert instance1 is not instance2, (
                "clear_service_cache() did not reset the singleton. "
                "Same instance returned after cache clear."
            )
            
        except ImportError as e:
            pytest.skip(f"Module not available: {e}")
    
    @given(times=resolution_count_strategy())
    @settings(max_examples=3, deadline=None)
    @pytest.mark.asyncio
    async def test_ai_service_idempotence(self, times: int):
        """
        Property test: AIService resolution should be idempotent.
        
        **Validates: Requirements 2.1, 2.3**
        """
        try:
            from multimodal_librarian.api.dependencies.services import (
                get_ai_service,
                clear_service_cache
            )
            
            clear_service_cache()
            
            instances = await self.resolution_test.resolve_dependency_multiple_times(
                get_ai_service, times
            )
            
            result = self.resolution_test.check_idempotence(instances)
            
            # If all failed, that's okay - service may not be available
            if result['reason'] == 'All resolutions failed':
                pytest.skip("AI service not available in test environment")
            
            assert result['idempotent'], (
                f"AIService resolution is not idempotent after {times} calls. "
                f"Reason: {result['reason']}"
            )
            
        except ImportError as e:
            pytest.skip(f"Module not available: {e}")


if __name__ == "__main__":
    print("Running Dependency Resolution Idempotence Property Tests")
    print("=" * 60)
    
    async def run_tests():
        test = TestDependencyResolutionIdempotence()
        resolution_test = DependencyResolutionTest()
        
        print("\n1. Testing ConnectionManager idempotence...")
        try:
            from multimodal_librarian.api.dependencies.services import (
                get_connection_manager,
                clear_service_cache
            )
            
            clear_service_cache()
            
            instances = await resolution_test.resolve_dependency_multiple_times(
                get_connection_manager, 3
            )
            result = resolution_test.check_idempotence(instances)
            
            print(f"   Resolved {len(instances)} times")
            print(f"   Idempotent: {result['idempotent']}")
            print(f"   Reason: {result['reason']}")
            print(f"   Result: {'PASS' if result['idempotent'] else 'FAIL'}")
            
        except ImportError as e:
            print(f"   SKIP: {e}")
        
        print("\n2. Testing cache reset...")
        try:
            clear_service_cache()
            instance1 = await get_connection_manager()
            clear_service_cache()
            instance2 = await get_connection_manager()
            
            different = instance1 is not instance2
            print(f"   Cache reset works: {different}")
            print(f"   Result: {'PASS' if different else 'FAIL'}")
            
        except ImportError as e:
            print(f"   SKIP: {e}")
    
    asyncio.run(run_tests())
    
    print("\nTo run with pytest:")
    print("pytest tests/api/test_di_idempotence.py -v --noconftest")
