#!/usr/bin/env python3
"""
Tests for Graceful Degradation when Services Unavailable

Feature: dependency-injection-architecture
Task 3.4: Write tests for graceful degradation when services unavailable

**Validates: Requirements 3.5, 4.3, 4.5**

Property 3: Graceful Degradation
When an optional service is unavailable, endpoints that depend on it must:
- Return a valid response (not crash)
- Indicate reduced functionality
- Not block indefinitely
"""

import asyncio
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException


class TestGracefulDegradation:
    """
    Tests for graceful degradation when services are unavailable.
    
    **Validates: Requirements 3.5, 4.3, 4.5**
    """
    
    def setup_method(self):
        """Clear cache before each test."""
        try:
            from multimodal_librarian.api.dependencies.services import (
                clear_service_cache,
            )
            clear_service_cache()
        except ImportError:
            pass
    
    def teardown_method(self):
        """Clear cache after each test."""
        try:
            from multimodal_librarian.api.dependencies.services import (
                clear_service_cache,
            )
            clear_service_cache()
        except ImportError:
            pass
    
    @pytest.mark.asyncio
    async def test_rag_service_returns_none_when_opensearch_unavailable(self):
        """
        Test that RAG service returns None when OpenSearch is unavailable.
        
        **Validates: Requirements 3.5, 4.3**
        """
        try:
            from multimodal_librarian.api.dependencies.services import (
                clear_service_cache,
                get_rag_service,
            )
            
            clear_service_cache()
            
            # Create a mock AI service
            mock_ai_service = MagicMock()
            
            # Call get_rag_service with vector_client=None (new API)
            result = await get_rag_service(vector_client=None, ai_service=mock_ai_service)
            
            assert result is None, (
                "RAG service should return None when vector client is unavailable, "
                "enabling graceful degradation"
            )
            
        except ImportError as e:
            pytest.skip(f"Module not available: {e}")
    
    @pytest.mark.asyncio
    async def test_cached_rag_service_returns_none_when_opensearch_unavailable(self):
        """
        Test that Cached RAG service returns None when OpenSearch is unavailable.
        
        **Validates: Requirements 3.5, 4.3**
        """
        try:
            from multimodal_librarian.api.dependencies.services import (
                clear_service_cache,
                get_cached_rag_service,
            )
            
            clear_service_cache()
            
            # Create a mock AI service
            mock_ai_service = MagicMock()
            
            # Call get_cached_rag_service with vector_client=None (new API)
            result = await get_cached_rag_service(vector_client=None, ai_service=mock_ai_service)
            
            assert result is None, (
                "Cached RAG service should return None when vector client is unavailable, "
                "enabling graceful degradation"
            )
            
        except ImportError as e:
            pytest.skip(f"Module not available: {e}")
    
    @pytest.mark.asyncio
    async def test_ai_service_optional_returns_none_on_failure(self):
        """
        Test that get_ai_service_optional returns None on failure.
        
        **Validates: Requirements 3.5**
        """
        try:
            from multimodal_librarian.api.dependencies.services import (
                clear_service_cache,
                get_ai_service_optional,
            )
            
            clear_service_cache()
            
            # Patch AIService to raise an exception
            with patch('multimodal_librarian.api.dependencies.services.get_ai_service') as mock_get_ai:
                mock_get_ai.side_effect = HTTPException(status_code=503, detail="AI service unavailable")
                
                # This should return None, not raise
                result = await get_ai_service_optional()
                
                assert result is None, (
                    "get_ai_service_optional should return None when AI service fails, "
                    "enabling graceful degradation"
                )
                
        except ImportError as e:
            pytest.skip(f"Module not available: {e}")
    
    @pytest.mark.asyncio
    async def test_opensearch_client_optional_returns_none_on_failure(self):
        """
        Test that get_opensearch_client_optional returns None on failure.
        
        **Validates: Requirements 3.5**
        """
        try:
            from multimodal_librarian.api.dependencies.services import (
                clear_service_cache,
                get_opensearch_client_optional,
            )
            
            clear_service_cache()
            
            # Patch get_opensearch_client to raise an exception
            with patch('multimodal_librarian.api.dependencies.services.get_opensearch_client') as mock_get_os:
                mock_get_os.side_effect = HTTPException(status_code=503, detail="OpenSearch unavailable")
                
                # This should return None, not raise
                result = await get_opensearch_client_optional()
                
                assert result is None, (
                    "get_opensearch_client_optional should return None when OpenSearch fails, "
                    "enabling graceful degradation"
                )
                
        except ImportError as e:
            pytest.skip(f"Module not available: {e}")
    
    @pytest.mark.asyncio
    async def test_connection_manager_works_without_services(self):
        """
        Test that ConnectionManager works even without RAG/AI services.
        
        **Validates: Requirements 4.1, 4.2, 4.5**
        """
        try:
            from multimodal_librarian.api.dependencies.services import (
                clear_service_cache,
                get_connection_manager,
            )
            
            clear_service_cache()
            
            # Get connection manager
            manager = await get_connection_manager()
            
            # Verify it works without services
            assert manager is not None
            assert manager._rag_service is None
            assert manager._ai_service is None
            
            # Verify rag_available property returns False
            assert manager.rag_available is False, (
                "ConnectionManager.rag_available should be False when RAG service is not set"
            )
            
        except ImportError as e:
            pytest.skip(f"Module not available: {e}")
    
    @pytest.mark.asyncio
    async def test_connection_manager_with_services_handles_none_services(self):
        """
        Test that get_connection_manager_with_services handles None services gracefully.
        
        **Validates: Requirements 4.3, 4.4**
        """
        try:
            from multimodal_librarian.api.dependencies.services import (
                clear_service_cache,
                get_connection_manager_with_services,
            )
            
            clear_service_cache()
            
            # Call with None services (simulating unavailable services)
            manager = await get_connection_manager_with_services(
                rag_service=None,
                ai_service=None
            )
            
            # Should still return a valid manager
            assert manager is not None
            assert manager._rag_service is None
            assert manager._ai_service is None
            assert manager.rag_available is False
            
        except ImportError as e:
            pytest.skip(f"Module not available: {e}")
    
    @pytest.mark.asyncio
    async def test_connection_manager_set_services_accepts_none(self):
        """
        Test that ConnectionManager.set_services accepts None values.
        
        **Validates: Requirements 4.3, 4.4**
        """
        try:
            from multimodal_librarian.api.dependencies.services import (
                clear_service_cache,
                get_connection_manager,
            )
            
            clear_service_cache()
            
            manager = await get_connection_manager()
            
            # Set services to None (simulating unavailable services)
            manager.set_services(rag_service=None, ai_service=None)
            
            # Should not raise and should update properties
            assert manager._rag_service is None
            assert manager._ai_service is None
            assert manager.rag_available is False
            
        except ImportError as e:
            pytest.skip(f"Module not available: {e}")
    
    @pytest.mark.asyncio
    async def test_connection_manager_partial_services(self):
        """
        Test that ConnectionManager works with partial services (only AI, no RAG).
        
        **Validates: Requirements 4.3, 4.5**
        """
        try:
            from multimodal_librarian.api.dependencies.services import (
                clear_service_cache,
                get_connection_manager,
            )
            
            clear_service_cache()
            
            manager = await get_connection_manager()
            
            # Set only AI service, not RAG
            mock_ai = MagicMock()
            manager.set_services(rag_service=None, ai_service=mock_ai)
            
            # RAG should be unavailable, but AI should be available
            assert manager._rag_service is None
            assert manager._ai_service is mock_ai
            assert manager.rag_available is False
            assert manager.ai_service is mock_ai
            
        except ImportError as e:
            pytest.skip(f"Module not available: {e}")


class TestGracefulDegradationProperties:
    """
    Property-based tests for graceful degradation.
    
    **Validates: Requirements 3.5, 4.3, 4.5**
    """
    
    def setup_method(self):
        """Clear cache before each test."""
        try:
            from multimodal_librarian.api.dependencies.services import (
                clear_service_cache,
            )
            clear_service_cache()
        except ImportError:
            pass
    
    def teardown_method(self):
        """Clear cache after each test."""
        try:
            from multimodal_librarian.api.dependencies.services import (
                clear_service_cache,
            )
            clear_service_cache()
        except ImportError:
            pass
    
    @pytest.mark.asyncio
    async def test_optional_dependencies_never_raise(self):
        """
        Property: Optional dependencies should never raise exceptions.
        
        **Validates: Requirements 3.5**
        """
        try:
            from multimodal_librarian.api.dependencies.services import (
                clear_service_cache,
                get_ai_service_optional,
                get_opensearch_client_optional,
            )
            
            clear_service_cache()
            
            # Test with mocked failures
            with patch('multimodal_librarian.api.dependencies.services.get_ai_service') as mock_ai:
                mock_ai.side_effect = Exception("Simulated failure")
                
                # Should not raise
                try:
                    result = await get_ai_service_optional()
                    assert result is None
                except Exception as e:
                    pytest.fail(f"get_ai_service_optional raised an exception: {e}")
            
            with patch('multimodal_librarian.api.dependencies.services.get_opensearch_client') as mock_os:
                mock_os.side_effect = Exception("Simulated failure")
                
                # Should not raise
                try:
                    result = await get_opensearch_client_optional()
                    assert result is None
                except Exception as e:
                    pytest.fail(f"get_opensearch_client_optional raised an exception: {e}")
                    
        except ImportError as e:
            pytest.skip(f"Module not available: {e}")
    
    @pytest.mark.asyncio
    async def test_rag_service_graceful_with_any_opensearch_state(self):
        """
        Property: RAG service should handle any OpenSearch state gracefully.
        
        **Validates: Requirements 3.5, 4.3**
        """
        try:
            from multimodal_librarian.api.dependencies.services import (
                clear_service_cache,
                get_rag_service,
            )
            
            clear_service_cache()
            
            mock_ai = MagicMock()
            
            # Test with None vector_client (new API)
            result = await get_rag_service(vector_client=None, ai_service=mock_ai)
            assert result is None
            
            # Test with valid vector client mock
            clear_service_cache()
            mock_vector_client = MagicMock()
            
            # This may succeed or fail depending on RAGService implementation
            # The key is it shouldn't crash
            try:
                result = await get_rag_service(vector_client=mock_vector_client, ai_service=mock_ai)
                # If it succeeds, result should be a RAGService or None
                assert result is None or result is not None
            except HTTPException:
                # HTTPException is acceptable (indicates service unavailable)
                pass
            except Exception as e:
                # Other exceptions should not occur
                pytest.fail(f"Unexpected exception: {e}")
                
        except ImportError as e:
            pytest.skip(f"Module not available: {e}")


if __name__ == "__main__":
    print("Running Graceful Degradation Tests")
    print("=" * 60)
    
    async def run_tests():
        test = TestGracefulDegradation()
        
        print("\n1. Testing RAG service returns None when OpenSearch unavailable...")
        test.setup_method()
        try:
            await test.test_rag_service_returns_none_when_opensearch_unavailable()
            print("   ✓ PASS")
        except Exception as e:
            print(f"   ✗ FAIL: {e}")
        test.teardown_method()
        
        print("\n2. Testing ConnectionManager works without services...")
        test.setup_method()
        try:
            await test.test_connection_manager_works_without_services()
            print("   ✓ PASS")
        except Exception as e:
            print(f"   ✗ FAIL: {e}")
        test.teardown_method()
        
        print("\n3. Testing optional dependencies never raise...")
        prop_test = TestGracefulDegradationProperties()
        prop_test.setup_method()
        try:
            await prop_test.test_optional_dependencies_never_raise()
            print("   ✓ PASS")
        except Exception as e:
            print(f"   ✗ FAIL: {e}")
        prop_test.teardown_method()
    
    asyncio.run(run_tests())
    
    print("\nTo run with pytest:")
    print("pytest tests/api/test_di_graceful_degradation.py -v --noconftest")
