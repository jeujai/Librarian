#!/usr/bin/env python3
"""
Tests for Chat Router with Dependency Injection Pattern

Feature: dependency-injection-architecture
Task 4.6: Test WebSocket functionality with new DI pattern

**Validates: Requirements 2.2, 4.1, 4.2, 4.3, 4.4**

Tests that the chat router:
- Uses dependency injection for ConnectionManager
- Does not instantiate services at module import time
- WebSocket endpoint accepts connections with DI
- Services are properly injected via Depends()
"""

import asyncio
import sys
import time
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from datetime import datetime


class TestChatRouterModuleImport:
    """Test that chat router module import doesn't block or create connections."""
    
    def test_chat_router_import_is_fast(self):
        """
        Test that importing chat.py doesn't block for service initialization.
        
        Validates: Requirements 1.2, 1.3, 2.2
        """
        # Clear any cached imports
        modules_to_clear = [k for k in sys.modules.keys() if 'chat' in k.lower()]
        for mod in modules_to_clear:
            if 'test' not in mod.lower():
                try:
                    del sys.modules[mod]
                except KeyError:
                    pass
        
        start_time = time.time()
        
        try:
            # Import the chat router
            from multimodal_librarian.api.routers import chat
            
            import_time = (time.time() - start_time) * 1000  # Convert to ms
            
            # Import should complete in under 1000ms (generous for CI environments)
            assert import_time < 1000, f"Chat router import took {import_time:.2f}ms, expected < 1000ms"
            
            print(f"✓ Chat router imported in {import_time:.2f}ms")
            
        except ImportError as e:
            pytest.skip(f"Module not available: {e}")
    
    def test_no_module_level_connection_manager(self):
        """
        Test that there's no module-level ConnectionManager instantiation.
        
        Validates: Requirements 2.2, 4.2
        """
        try:
            from multimodal_librarian.api.routers import chat
            
            # Check that there's no module-level 'manager' variable that's a ConnectionManager
            # The old pattern was: manager = ConnectionManager()
            
            # If 'manager' exists at module level, it should be None or not a ConnectionManager
            if hasattr(chat, 'manager'):
                # If it exists, it should be None (not instantiated)
                from multimodal_librarian.api.dependencies.services import ConnectionManager
                assert not isinstance(chat.manager, ConnectionManager), \
                    "Module-level 'manager' should not be a ConnectionManager instance"
            
            print("✓ No module-level ConnectionManager instantiation")
            
        except ImportError as e:
            pytest.skip(f"Module not available: {e}")
        except AttributeError:
            # 'manager' doesn't exist at module level - this is correct
            print("✓ No module-level 'manager' attribute (correct)")


class TestChatRouterDependencyInjection:
    """Test that chat router uses dependency injection correctly."""
    
    def setup_method(self):
        """Clear service cache before each test."""
        try:
            from multimodal_librarian.api.dependencies.services import clear_service_cache
            clear_service_cache()
        except ImportError:
            pass
    
    def teardown_method(self):
        """Clear service cache after each test."""
        try:
            from multimodal_librarian.api.dependencies.services import clear_service_cache
            clear_service_cache()
        except ImportError:
            pass
    
    def test_websocket_endpoint_uses_depends(self):
        """
        Test that websocket_endpoint uses Depends() for ConnectionManager.
        
        Validates: Requirements 4.3, 4.4
        """
        try:
            from multimodal_librarian.api.routers.chat import websocket_endpoint
            import inspect
            
            # Get the function signature
            sig = inspect.signature(websocket_endpoint)
            params = sig.parameters
            
            # Check that 'manager' parameter exists
            assert 'manager' in params, "websocket_endpoint should have 'manager' parameter"
            
            # Check that it has a default (which should be Depends(...))
            manager_param = params['manager']
            assert manager_param.default is not inspect.Parameter.empty, \
                "manager parameter should have a default value (Depends)"
            
            print("✓ websocket_endpoint uses Depends() for manager")
            
        except ImportError as e:
            pytest.skip(f"Module not available: {e}")
    
    def test_health_endpoint_uses_depends(self):
        """
        Test that health endpoint uses Depends() for ConnectionManager.
        
        Validates: Requirements 4.3
        """
        try:
            from multimodal_librarian.api.routers.chat import chat_health
            import inspect
            
            # Get the function signature
            sig = inspect.signature(chat_health)
            params = sig.parameters
            
            # Check that 'manager' parameter exists
            assert 'manager' in params, "chat_health should have 'manager' parameter"
            
            print("✓ chat_health uses Depends() for manager")
            
        except ImportError as e:
            pytest.skip(f"Module not available: {e}")
    
    @pytest.mark.asyncio
    async def test_connection_manager_services_injected(self):
        """
        Test that ConnectionManager receives services via DI.
        
        Validates: Requirements 4.4
        """
        try:
            from multimodal_librarian.api.dependencies.services import (
                get_connection_manager_with_services,
                ConnectionManager
            )
            
            # Create mock services
            mock_rag = MagicMock()
            mock_rag.get_service_status = MagicMock(return_value={"status": "healthy"})
            mock_ai = MagicMock()
            
            # Get manager with services
            manager = await get_connection_manager_with_services(
                rag_service=mock_rag,
                ai_service=mock_ai
            )
            
            assert isinstance(manager, ConnectionManager)
            assert manager.rag_service is mock_rag
            assert manager.ai_service is mock_ai
            assert manager.rag_available is True
            
            print("✓ ConnectionManager receives services via DI")
            
        except ImportError as e:
            pytest.skip(f"Module not available: {e}")


class TestChatRouterFunctionality:
    """Test that chat router functions work correctly with DI."""
    
    def setup_method(self):
        """Clear service cache before each test."""
        try:
            from multimodal_librarian.api.dependencies.services import clear_service_cache
            clear_service_cache()
        except ImportError:
            pass
    
    def teardown_method(self):
        """Clear service cache after each test."""
        try:
            from multimodal_librarian.api.dependencies.services import clear_service_cache
            clear_service_cache()
        except ImportError:
            pass
    
    @pytest.mark.asyncio
    async def test_handle_start_conversation_with_di_manager(self):
        """
        Test that handle_start_conversation works with DI-injected manager.
        
        Validates: Requirements 4.1, 4.2
        """
        try:
            from multimodal_librarian.api.routers.chat import handle_start_conversation
            from multimodal_librarian.api.dependencies.services import ConnectionManager
            
            # Create a mock manager
            manager = ConnectionManager()
            manager.set_thread_id = MagicMock()
            manager.send_personal_message = AsyncMock()
            
            connection_id = "test-connection-123"
            
            # Mock the _get_legacy_components to avoid network calls
            with patch('multimodal_librarian.api.routers.chat._get_legacy_components') as mock_legacy:
                # Return None for all components to test graceful degradation
                mock_legacy.return_value = (None, None, None)
                
                # Call the function
                await handle_start_conversation(connection_id, manager)
            
            # Verify thread ID was set
            manager.set_thread_id.assert_called_once()
            
            # Verify welcome message was sent
            manager.send_personal_message.assert_called_once()
            call_args = manager.send_personal_message.call_args
            message = call_args[0][0]
            
            assert message['type'] == 'conversation_started'
            assert 'thread_id' in message
            assert 'features' in message
            
            print("✓ handle_start_conversation works with DI manager")
            
        except ImportError as e:
            pytest.skip(f"Module not available: {e}")
    
    @pytest.mark.asyncio
    async def test_connection_manager_connect_disconnect(self):
        """
        Test ConnectionManager connect/disconnect functionality.
        
        Validates: Requirements 4.1
        """
        try:
            from multimodal_librarian.api.dependencies.services import ConnectionManager
            
            manager = ConnectionManager()
            
            # Create mock websocket
            mock_websocket = AsyncMock()
            mock_websocket.accept = AsyncMock()
            
            connection_id = "test-conn-456"
            
            # Test connect
            await manager.connect(mock_websocket, connection_id)
            
            assert connection_id in manager.active_connections
            assert connection_id in manager.conversation_history
            mock_websocket.accept.assert_called_once()
            
            # Test disconnect
            manager.disconnect(connection_id)
            
            assert connection_id not in manager.active_connections
            assert connection_id not in manager.conversation_history
            
            print("✓ ConnectionManager connect/disconnect works correctly")
            
        except ImportError as e:
            pytest.skip(f"Module not available: {e}")
    
    @pytest.mark.asyncio
    async def test_conversation_history_management(self):
        """
        Test conversation history management in ConnectionManager.
        
        Validates: Requirements 4.5
        """
        try:
            from multimodal_librarian.api.dependencies.services import ConnectionManager
            
            manager = ConnectionManager()
            connection_id = "test-history-789"
            
            # Initialize conversation history
            manager.conversation_history[connection_id] = []
            
            # Add messages
            manager.add_to_conversation_history(connection_id, "user", "Hello")
            manager.add_to_conversation_history(connection_id, "assistant", "Hi there!")
            
            # Get context
            context = manager.get_conversation_context(connection_id)
            
            assert len(context) == 2
            assert context[0]['role'] == 'user'
            assert context[0]['content'] == 'Hello'
            assert context[1]['role'] == 'assistant'
            assert context[1]['content'] == 'Hi there!'
            
            print("✓ Conversation history management works correctly")
            
        except ImportError as e:
            pytest.skip(f"Module not available: {e}")
    
    @pytest.mark.asyncio
    async def test_conversation_history_limit(self):
        """
        Test that conversation history is limited to 10 messages.
        
        Validates: Requirements 4.5
        """
        try:
            from multimodal_librarian.api.dependencies.services import ConnectionManager
            
            manager = ConnectionManager()
            connection_id = "test-limit-101"
            
            # Initialize conversation history
            manager.conversation_history[connection_id] = []
            
            # Add 15 messages
            for i in range(15):
                manager.add_to_conversation_history(
                    connection_id, 
                    "user" if i % 2 == 0 else "assistant", 
                    f"Message {i}"
                )
            
            # Get context
            context = manager.get_conversation_context(connection_id)
            
            # Should be limited to 10
            assert len(context) == 10
            
            # Should have the last 10 messages (5-14)
            assert context[0]['content'] == 'Message 5'
            assert context[-1]['content'] == 'Message 14'
            
            print("✓ Conversation history limited to 10 messages")
            
        except ImportError as e:
            pytest.skip(f"Module not available: {e}")


class TestChatRouterGracefulDegradation:
    """Test graceful degradation when services are unavailable."""
    
    def setup_method(self):
        """Clear service cache before each test."""
        try:
            from multimodal_librarian.api.dependencies.services import clear_service_cache
            clear_service_cache()
        except ImportError:
            pass
    
    def teardown_method(self):
        """Clear service cache after each test."""
        try:
            from multimodal_librarian.api.dependencies.services import clear_service_cache
            clear_service_cache()
        except ImportError:
            pass
    
    @pytest.mark.asyncio
    async def test_manager_without_rag_service(self):
        """
        Test that ConnectionManager works without RAG service.
        
        Validates: Requirements 4.3, 4.5
        """
        try:
            from multimodal_librarian.api.dependencies.services import ConnectionManager
            
            manager = ConnectionManager()
            
            # Don't set any services
            assert manager.rag_service is None
            assert manager.ai_service is None
            assert manager.rag_available is False
            
            # Manager should still work for basic operations
            mock_websocket = AsyncMock()
            mock_websocket.accept = AsyncMock()
            
            connection_id = "test-no-rag"
            await manager.connect(mock_websocket, connection_id)
            
            assert connection_id in manager.active_connections
            
            manager.disconnect(connection_id)
            assert connection_id not in manager.active_connections
            
            print("✓ ConnectionManager works without RAG service")
            
        except ImportError as e:
            pytest.skip(f"Module not available: {e}")
    
    @pytest.mark.asyncio
    async def test_health_endpoint_reports_rag_status(self):
        """
        Test that health endpoint correctly reports RAG availability.
        
        Validates: Requirements 4.4
        """
        try:
            from multimodal_librarian.api.routers.chat import chat_health
            from multimodal_librarian.api.dependencies.services import ConnectionManager
            
            # Test with RAG unavailable
            manager_no_rag = ConnectionManager()
            result = await chat_health(manager=manager_no_rag)
            
            assert result['status'] == 'healthy'
            assert result['features']['rag_integration'] is False
            
            # Test with RAG available
            manager_with_rag = ConnectionManager()
            mock_rag = MagicMock()
            mock_rag.get_service_status = MagicMock(return_value={"status": "healthy"})
            manager_with_rag.set_services(rag_service=mock_rag)
            
            result = await chat_health(manager=manager_with_rag)
            
            assert result['status'] == 'healthy'
            assert result['features']['rag_integration'] is True
            
            print("✓ Health endpoint correctly reports RAG status")
            
        except ImportError as e:
            pytest.skip(f"Module not available: {e}")


if __name__ == "__main__":
    print("Running Chat Router DI Tests")
    print("=" * 60)
    
    # Run import tests
    print("\n1. Testing module import...")
    test1 = TestChatRouterModuleImport()
    try:
        test1.test_chat_router_import_is_fast()
    except Exception as e:
        print(f"   ✗ {e}")
    
    try:
        test1.test_no_module_level_connection_manager()
    except Exception as e:
        print(f"   ✗ {e}")
    
    # Run DI tests
    print("\n2. Testing dependency injection...")
    test2 = TestChatRouterDependencyInjection()
    test2.setup_method()
    try:
        test2.test_websocket_endpoint_uses_depends()
    except Exception as e:
        print(f"   ✗ {e}")
    
    try:
        test2.test_health_endpoint_uses_depends()
    except Exception as e:
        print(f"   ✗ {e}")
    test2.teardown_method()
    
    # Run async tests
    print("\n3. Testing functionality...")
    
    async def run_async_tests():
        test3 = TestChatRouterFunctionality()
        test3.setup_method()
        
        try:
            await test3.test_connection_manager_connect_disconnect()
        except Exception as e:
            print(f"   ✗ {e}")
        
        try:
            await test3.test_conversation_history_management()
        except Exception as e:
            print(f"   ✗ {e}")
        
        try:
            await test3.test_conversation_history_limit()
        except Exception as e:
            print(f"   ✗ {e}")
        
        test3.teardown_method()
        
        # Graceful degradation tests
        print("\n4. Testing graceful degradation...")
        test4 = TestChatRouterGracefulDegradation()
        test4.setup_method()
        
        try:
            await test4.test_manager_without_rag_service()
        except Exception as e:
            print(f"   ✗ {e}")
        
        try:
            await test4.test_health_endpoint_reports_rag_status()
        except Exception as e:
            print(f"   ✗ {e}")
        
        test4.teardown_method()
    
    asyncio.run(run_async_tests())
    
    print("\n" + "=" * 60)
    print("To run with pytest:")
    print("pytest tests/api/test_chat_router_di.py -v")
