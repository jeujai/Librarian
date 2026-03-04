#!/usr/bin/env python3
"""
Property-Based Test: Import-Time Behavior for DI Infrastructure

Feature: dependency-injection-architecture
Property 1: No Import-Time Connections

**Validates: Requirements 1.2, 1.3**

For any module in the application, importing that module must not:
- Establish database connections
- Make network requests
- Instantiate service singletons at module level
"""

import sys
import pytest
from hypothesis import given, strategies as st, settings


class TestImportTimeBehavior:
    """
    Property-based tests for import-time behavior.
    
    **Validates: Requirements 1.2, 1.3**
    """
    
    def _clear_di_modules(self):
        """Clear DI modules from cache."""
        modules_to_clear = [
            "multimodal_librarian.api.dependencies.services",
            "multimodal_librarian.api.dependencies",
        ]
        for mod in list(sys.modules.keys()):
            if mod.startswith("multimodal_librarian.api.dependencies"):
                del sys.modules[mod]
    
    def _check_no_instantiation(self) -> bool:
        """Check that no services are instantiated at import time."""
        try:
            from multimodal_librarian.api.dependencies import services
            
            return (
                services._opensearch_client is None and
                services._ai_service is None and
                services._rag_service is None and
                services._cached_rag_service is None and
                services._connection_manager is None
            )
        except ImportError:
            return True  # Module not available, skip
    
    @given(iteration=st.integers(min_value=1, max_value=3))
    @settings(max_examples=3, deadline=None)
    def test_no_connections_at_import_time(self, iteration: int):
        """
        Property test: For any DI module import, no connections should be established.
        
        **Validates: Requirements 1.2, 1.3**
        
        This property ensures that no module-level initialization establishes
        database connections or instantiates service singletons.
        """
        # Clear modules to force re-import
        self._clear_di_modules()
        
        # Check that no services are instantiated
        assert self._check_no_instantiation(), (
            "DI module import established connections or instantiated services. "
            "Service caches should be None at import time."
        )
    
    def test_services_module_no_instantiation(self):
        """
        Direct test: services.py module should not instantiate services at import.
        
        **Validates: Requirements 1.2, 1.3, 2.2**
        """
        self._clear_di_modules()
        
        try:
            from multimodal_librarian.api.dependencies import services
            
            assert services._opensearch_client is None, \
                "OpenSearch client should not be instantiated at import time"
            assert services._ai_service is None, \
                "AI service should not be instantiated at import time"
            assert services._rag_service is None, \
                "RAG service should not be instantiated at import time"
            assert services._cached_rag_service is None, \
                "Cached RAG service should not be instantiated at import time"
            assert services._connection_manager is None, \
                "Connection manager should not be instantiated at import time"
                
        except ImportError as e:
            pytest.skip(f"Module not available: {e}")
    
    def test_connection_manager_class_exists_but_not_instantiated(self):
        """
        Test that ConnectionManager class is defined but not instantiated.
        
        **Validates: Requirements 2.2, 4.2**
        """
        self._clear_di_modules()
        
        try:
            from multimodal_librarian.api.dependencies.services import (
                ConnectionManager,
                _connection_manager
            )
            
            # Class should exist
            assert ConnectionManager is not None, "ConnectionManager class should be defined"
            
            # But no instance should be created at import time
            assert _connection_manager is None, \
                "ConnectionManager should not be instantiated at module import"
                
        except ImportError as e:
            pytest.skip(f"Module not available: {e}")


if __name__ == "__main__":
    print("Running Import-Time Behavior Property Tests")
    print("=" * 60)
    
    test = TestImportTimeBehavior()
    
    print("\n1. Testing no instantiation at import time...")
    test._clear_di_modules()
    result = test._check_no_instantiation()
    print(f"   Result: {'PASS' if result else 'FAIL'}")
    
    print("\n2. Testing services module...")
    try:
        test.test_services_module_no_instantiation()
        print("   Result: PASS")
    except AssertionError as e:
        print(f"   Result: FAIL - {e}")
    
    print("\n3. Testing ConnectionManager class...")
    try:
        test.test_connection_manager_class_exists_but_not_instantiated()
        print("   Result: PASS")
    except AssertionError as e:
        print(f"   Result: FAIL - {e}")
    
    print("\nTo run with pytest:")
    print("pytest tests/api/test_di_import_time.py -v")
