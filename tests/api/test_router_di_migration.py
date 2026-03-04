#!/usr/bin/env python3
"""
Tests for Router DI Migration

Feature: dependency-injection-architecture
Task 5.3: Test each migrated router

**Validates: Requirements 2.1, 2.3, 2.4**

Tests that the migrated routers:
- Use DI dependencies instead of direct imports
- Handle graceful degradation when services unavailable
- Don't block on import
"""

import asyncio
import time
import pytest
from unittest.mock import MagicMock, AsyncMock, patch


class TestRouterImportTime:
    """Test that router imports don't block or establish connections."""
    
    def test_rag_chat_router_import_is_fast(self):
        """Test that rag_chat router imports quickly without blocking."""
        start_time = time.time()
        
        try:
            # Import the router module
            from multimodal_librarian.api.routers import rag_chat
            
            import_time = time.time() - start_time
            
            # First import may take longer due to dependency loading (ML models, etc.)
            # The key is that it doesn't block on network connections
            # We use a generous 10 second limit for first import
            assert import_time < 10.0, f"rag_chat import took {import_time:.2f}s, expected < 10.0s"
            
            # Verify router exists
            assert hasattr(rag_chat, 'router')
            
        except ImportError as e:
            pytest.skip(f"Module not available: {e}")
    
    def test_cache_management_router_import_is_fast(self):
        """Test that cache_management router imports quickly without blocking."""
        start_time = time.time()
        
        try:
            # Import the router module
            from multimodal_librarian.api.routers import cache_management
            
            import_time = time.time() - start_time
            
            # Import should complete in under 1 second (modules already cached)
            assert import_time < 1.0, f"cache_management import took {import_time:.2f}s, expected < 1.0s"
            
            # Verify router exists
            assert hasattr(cache_management, 'router')
            
        except ImportError as e:
            pytest.skip(f"Module not available: {e}")
    
    def test_chat_ai_router_import_is_fast(self):
        """Test that chat_ai router imports quickly without blocking."""
        start_time = time.time()
        
        try:
            # Import the router module
            from multimodal_librarian.api.routers import chat_ai
            
            import_time = time.time() - start_time
            
            # Import should complete in under 1 second
            assert import_time < 1.0, f"chat_ai import took {import_time:.2f}s, expected < 1.0s"
            
            # Verify router exists
            assert hasattr(chat_ai, 'router')
            
        except ImportError as e:
            pytest.skip(f"Module not available: {e}")


class TestRouterDIUsage:
    """Test that routers use DI dependencies correctly."""
    
    def test_rag_chat_uses_di_dependencies(self):
        """Test that rag_chat router imports from dependencies module."""
        try:
            import inspect
            from multimodal_librarian.api.routers import rag_chat
            
            # Get the source code
            source = inspect.getsource(rag_chat)
            
            # Should import from dependencies, not directly from services
            assert "from ..dependencies import" in source or "from ...api.dependencies import" in source, \
                "rag_chat should import from dependencies module"
            
            # Should NOT import get_cached_rag_service from services module
            assert "from ...services.rag_service_cached import get_cached_rag_service" not in source, \
                "rag_chat should not import get_cached_rag_service from services module"
            
        except ImportError as e:
            pytest.skip(f"Module not available: {e}")
    
    def test_cache_management_uses_di_dependencies(self):
        """Test that cache_management router imports from dependencies module."""
        try:
            import inspect
            from multimodal_librarian.api.routers import cache_management
            
            # Get the source code
            source = inspect.getsource(cache_management)
            
            # Should import from dependencies
            assert "from ..dependencies import" in source or "from ...api.dependencies import" in source, \
                "cache_management should import from dependencies module"
            
            # Should NOT import directly from services
            assert "from ...services.ai_service_cached import get_cached_ai_service" not in source, \
                "cache_management should not import get_cached_ai_service from services module"
            assert "from ...services.rag_service_cached import get_cached_rag_service" not in source, \
                "cache_management should not import get_cached_rag_service from services module"
            
        except ImportError as e:
            pytest.skip(f"Module not available: {e}")
    
    def test_chat_ai_uses_di_dependencies(self):
        """Test that chat_ai router imports from dependencies module."""
        try:
            import inspect
            from multimodal_librarian.api.routers import chat_ai
            
            # Get the source code
            source = inspect.getsource(chat_ai)
            
            # Should import from dependencies
            assert "from ..dependencies import" in source or "from ...api.dependencies import" in source, \
                "chat_ai should import from dependencies module"
            
            # Should NOT import get_cached_ai_service from services module
            assert "from ...services.ai_service_cached import get_cached_ai_service" not in source, \
                "chat_ai should not import get_cached_ai_service from services module"
            
        except ImportError as e:
            pytest.skip(f"Module not available: {e}")


class TestRouterNoModuleLevelInstantiation:
    """Test that routers don't have module-level service instantiation."""
    
    def test_rag_chat_no_module_level_service_calls(self):
        """Test that rag_chat doesn't call service functions at module level."""
        try:
            import inspect
            from multimodal_librarian.api.routers import rag_chat
            
            source = inspect.getsource(rag_chat)
            
            # Check for module-level service instantiation patterns
            # These patterns indicate direct calls outside of functions
            lines = source.split('\n')
            
            for i, line in enumerate(lines):
                # Skip lines inside functions/classes (indented)
                if line.startswith('    ') or line.startswith('\t'):
                    continue
                # Skip comments and empty lines
                if line.strip().startswith('#') or not line.strip():
                    continue
                # Skip imports, class/function definitions
                if any(line.strip().startswith(kw) for kw in ['from ', 'import ', 'def ', 'class ', 'async def ', '@']):
                    continue
                    
                # Check for problematic patterns at module level
                if 'get_cached_rag_service()' in line or 'get_cached_ai_service()' in line:
                    pytest.fail(f"Found module-level service call at line {i+1}: {line.strip()}")
            
        except ImportError as e:
            pytest.skip(f"Module not available: {e}")
    
    def test_chat_ai_no_module_level_ai_service_call(self):
        """Test that chat_ai doesn't instantiate ai_service at module level."""
        try:
            import inspect
            from multimodal_librarian.api.routers import chat_ai
            
            source = inspect.getsource(chat_ai)
            
            # Should NOT have module-level ai_service = get_cached_ai_service()
            # This pattern was removed in the migration
            assert "ai_service = get_cached_ai_service()" not in source, \
                "chat_ai should not have module-level ai_service instantiation"
            
        except ImportError as e:
            pytest.skip(f"Module not available: {e}")


class TestCachedAIServiceDI:
    """Test the new get_cached_ai_service_di dependency."""
    
    def setup_method(self):
        """Clear cache before each test."""
        try:
            from multimodal_librarian.api.dependencies.services import clear_service_cache
            clear_service_cache()
        except ImportError:
            pass
    
    def teardown_method(self):
        """Clear cache after each test."""
        try:
            from multimodal_librarian.api.dependencies.services import clear_service_cache
            clear_service_cache()
        except ImportError:
            pass
    
    @pytest.mark.asyncio
    async def test_get_cached_ai_service_di_exists(self):
        """Test that get_cached_ai_service_di dependency exists."""
        try:
            from multimodal_librarian.api.dependencies import get_cached_ai_service_di
            
            assert callable(get_cached_ai_service_di)
            
        except ImportError as e:
            pytest.skip(f"Module not available: {e}")
    
    @pytest.mark.asyncio
    async def test_get_cached_ai_service_optional_exists(self):
        """Test that get_cached_ai_service_optional dependency exists."""
        try:
            from multimodal_librarian.api.dependencies import get_cached_ai_service_optional
            
            assert callable(get_cached_ai_service_optional)
            
        except ImportError as e:
            pytest.skip(f"Module not available: {e}")
    
    @pytest.mark.asyncio
    async def test_get_cached_ai_service_di_returns_instance(self):
        """Test that get_cached_ai_service_di returns a CachedAIService instance."""
        try:
            from multimodal_librarian.api.dependencies.services import get_cached_ai_service_di
            from multimodal_librarian.services.ai_service_cached import CachedAIService
            
            service = await get_cached_ai_service_di()
            
            assert service is not None
            assert isinstance(service, CachedAIService)
            
        except ImportError as e:
            pytest.skip(f"Module not available: {e}")
        except Exception as e:
            if "unavailable" in str(e).lower():
                pytest.skip(f"AI service not available: {e}")
            raise


class TestDependencyExports:
    """Test that all new dependencies are properly exported."""
    
    def test_dependencies_init_exports_cached_ai_service_di(self):
        """Test that __init__.py exports get_cached_ai_service_di."""
        try:
            from multimodal_librarian.api.dependencies import get_cached_ai_service_di
            
            assert callable(get_cached_ai_service_di)
            
        except ImportError as e:
            pytest.skip(f"Module not available: {e}")
    
    def test_dependencies_init_exports_cached_ai_service_optional(self):
        """Test that __init__.py exports get_cached_ai_service_optional."""
        try:
            from multimodal_librarian.api.dependencies import get_cached_ai_service_optional
            
            assert callable(get_cached_ai_service_optional)
            
        except ImportError as e:
            pytest.skip(f"Module not available: {e}")
    
    def test_all_exports_in_dependencies_init(self):
        """Test that __all__ includes new dependencies."""
        try:
            from multimodal_librarian.api import dependencies
            
            assert "get_cached_ai_service_di" in dependencies.__all__
            assert "get_cached_ai_service_optional" in dependencies.__all__
            
        except ImportError as e:
            pytest.skip(f"Module not available: {e}")


if __name__ == "__main__":
    print("Running Router DI Migration Tests")
    print("=" * 60)
    
    # Test import times
    print("\n1. Testing router import times...")
    test = TestRouterImportTime()
    
    try:
        test.test_rag_chat_router_import_is_fast()
        print("   ✓ rag_chat imports quickly")
    except Exception as e:
        print(f"   ✗ {e}")
    
    try:
        test.test_cache_management_router_import_is_fast()
        print("   ✓ cache_management imports quickly")
    except Exception as e:
        print(f"   ✗ {e}")
    
    try:
        test.test_chat_ai_router_import_is_fast()
        print("   ✓ chat_ai imports quickly")
    except Exception as e:
        print(f"   ✗ {e}")
    
    # Test DI usage
    print("\n2. Testing DI usage in routers...")
    test2 = TestRouterDIUsage()
    
    try:
        test2.test_rag_chat_uses_di_dependencies()
        print("   ✓ rag_chat uses DI dependencies")
    except Exception as e:
        print(f"   ✗ {e}")
    
    try:
        test2.test_cache_management_uses_di_dependencies()
        print("   ✓ cache_management uses DI dependencies")
    except Exception as e:
        print(f"   ✗ {e}")
    
    try:
        test2.test_chat_ai_uses_di_dependencies()
        print("   ✓ chat_ai uses DI dependencies")
    except Exception as e:
        print(f"   ✗ {e}")
    
    # Test no module-level instantiation
    print("\n3. Testing no module-level service instantiation...")
    test3 = TestRouterNoModuleLevelInstantiation()
    
    try:
        test3.test_rag_chat_no_module_level_service_calls()
        print("   ✓ rag_chat has no module-level service calls")
    except Exception as e:
        print(f"   ✗ {e}")
    
    try:
        test3.test_chat_ai_no_module_level_ai_service_call()
        print("   ✓ chat_ai has no module-level ai_service call")
    except Exception as e:
        print(f"   ✗ {e}")
    
    print("\nTo run with pytest:")
    print("pytest tests/api/test_router_di_migration.py -v --noconftest")
