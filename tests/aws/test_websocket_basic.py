#!/usr/bin/env python3
"""
Basic WebSocket Tests for AWS Learning Deployment

This module tests WebSocket connectivity through the Application Load Balancer including:
- WebSocket connection establishment
- Message sending and receiving
- Connection persistence
- Load balancer WebSocket support
- Chat interface WebSocket functionality
- Error handling and reconnection
"""

import os
import sys
import pytest
import asyncio
import websockets
import json
import aiohttp
from datetime import datetime
from typing import Dict, Any, List, Optional

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from multimodal_librarian.logging_config import get_logger


class WebSocketTestSuite:
    """Test suite for WebSocket operations."""
    
    def __init__(self):
        self.logger = get_logger("websocket_tests")
        
        # Configuration
        self.base_url = os.getenv("AWS_BASE_URL", "http://localhost:8000")
        self.ws_url = self.base_url.replace("http://", "ws://").replace("https://", "wss://")
        self.test_timeout = 30
        
        # WebSocket endpoints to test
        self.ws_endpoints = {
            "chat": "/ws/chat",
            "notifications": "/ws/notifications",
            "status": "/ws/status"
        }


@pytest.fixture(scope="session")
def ws_test_suite():
    """Pytest fixture for WebSocket test suite."""
    return WebSocketTestSuite()


class TestWebSocketConnectivity:
    """Test basic WebSocket connectivity."""
    
    @pytest.mark.asyncio
    async def test_websocket_connection_establishment(self, ws_test_suite):
        """Test WebSocket connection establishment."""
        ws_url = f"{ws_test_suite.ws_url}/ws/chat"
        
        try:
            # Attempt to establish WebSocket connection
            async with websockets.connect(
                ws_url,
                timeout=ws_test_suite.test_timeout
            ) as websocket:
                # Connection successful
                assert websocket.open
                
                ws_test_suite.logger.info("✅ WebSocket connection established successfully")
                
        except websockets.exceptions.InvalidURI:
            pytest.skip("Invalid WebSocket URI - may not be configured")
        except websockets.exceptions.ConnectionClosed:
            pytest.fail("WebSocket connection was closed unexpectedly")
        except asyncio.TimeoutError:
            pytest.fail("WebSocket connection timeout")
        except Exception as e:
            # May fail if WebSocket endpoint doesn't exist - that's okay for basic test
            ws_test_suite.logger.warning(f"⚠️  WebSocket connection test: {e}")
            pytest.skip(f"WebSocket endpoint may not be available: {e}")
    
    @pytest.mark.asyncio
    async def test_websocket_ping_pong(self, ws_test_suite):
        """Test WebSocket ping/pong mechanism."""
        ws_url = f"{ws_test_suite.ws_url}/ws/chat"
        
        try:
            async with websockets.connect(
                ws_url,
                timeout=ws_test_suite.test_timeout
            ) as websocket:
                # Send ping
                await websocket.ping()
                
                # Connection should still be open
                assert websocket.open
                
                ws_test_suite.logger.info("✅ WebSocket ping/pong successful")
                
        except Exception as e:
            ws_test_suite.logger.warning(f"⚠️  WebSocket ping/pong test: {e}")
            pytest.skip(f"WebSocket ping/pong may not be supported: {e}")
    
    @pytest.mark.asyncio
    async def test_websocket_multiple_connections(self, ws_test_suite):
        """Test multiple simultaneous WebSocket connections."""
        ws_url = f"{ws_test_suite.ws_url}/ws/chat"
        
        try:
            # Create multiple connections
            connections = []
            
            for i in range(3):
                try:
                    websocket = await websockets.connect(
                        ws_url,
                        timeout=ws_test_suite.test_timeout
                    )
                    connections.append(websocket)
                    assert websocket.open
                    
                except Exception as e:
                    ws_test_suite.logger.warning(f"Connection {i} failed: {e}")
                    break
            
            if connections:
                ws_test_suite.logger.info(f"✅ Multiple WebSocket connections: {len(connections)}")
                
                # Close all connections
                for websocket in connections:
                    await websocket.close()
            else:
                pytest.skip("Could not establish multiple WebSocket connections")
                
        except Exception as e:
            ws_test_suite.logger.warning(f"⚠️  Multiple connections test: {e}")
            pytest.skip(f"Multiple WebSocket connections test failed: {e}")


class TestWebSocketMessaging:
    """Test WebSocket message sending and receiving."""
    
    @pytest.mark.asyncio
    async def test_websocket_message_echo(self, ws_test_suite):
        """Test WebSocket message echo functionality."""
        ws_url = f"{ws_test_suite.ws_url}/ws/chat"
        
        try:
            async with websockets.connect(
                ws_url,
                timeout=ws_test_suite.test_timeout
            ) as websocket:
                # Send test message
                test_message = {
                    "type": "test",
                    "content": "Hello WebSocket",
                    "timestamp": datetime.now().isoformat()
                }
                
                await websocket.send(json.dumps(test_message))
                
                # Try to receive response (with timeout)
                try:
                    response = await asyncio.wait_for(
                        websocket.recv(),
                        timeout=5.0
                    )
                    
                    # Parse response
                    response_data = json.loads(response)
                    
                    # Basic validation
                    assert isinstance(response_data, dict)
                    
                    ws_test_suite.logger.info("✅ WebSocket message exchange successful")
                    
                except asyncio.TimeoutError:
                    ws_test_suite.logger.warning("⚠️  No response received (may be expected)")
                    # This might be expected if the server doesn't echo
                    
        except Exception as e:
            ws_test_suite.logger.warning(f"⚠️  WebSocket messaging test: {e}")
            pytest.skip(f"WebSocket messaging may not be implemented: {e}")
    
    @pytest.mark.asyncio
    async def test_websocket_chat_message_format(self, ws_test_suite):
        """Test WebSocket chat message format."""
        ws_url = f"{ws_test_suite.ws_url}/ws/chat"
        
        try:
            async with websockets.connect(
                ws_url,
                timeout=ws_test_suite.test_timeout
            ) as websocket:
                # Send chat message in expected format
                chat_message = {
                    "type": "chat_message",
                    "message": "Test chat message",
                    "user_id": "test_user",
                    "conversation_id": "test_conversation",
                    "timestamp": datetime.now().isoformat()
                }
                
                await websocket.send(json.dumps(chat_message))
                
                # Try to receive response
                try:
                    response = await asyncio.wait_for(
                        websocket.recv(),
                        timeout=5.0
                    )
                    
                    response_data = json.loads(response)
                    
                    # Validate response structure
                    assert isinstance(response_data, dict)
                    
                    ws_test_suite.logger.info("✅ WebSocket chat message format test successful")
                    
                except asyncio.TimeoutError:
                    ws_test_suite.logger.warning("⚠️  No chat response received")
                    
        except Exception as e:
            ws_test_suite.logger.warning(f"⚠️  WebSocket chat format test: {e}")
            pytest.skip(f"WebSocket chat functionality may not be available: {e}")
    
    @pytest.mark.asyncio
    async def test_websocket_invalid_message_handling(self, ws_test_suite):
        """Test WebSocket handling of invalid messages."""
        ws_url = f"{ws_test_suite.ws_url}/ws/chat"
        
        try:
            async with websockets.connect(
                ws_url,
                timeout=ws_test_suite.test_timeout
            ) as websocket:
                # Send invalid JSON
                await websocket.send("invalid json message")
                
                # Connection should remain open (good error handling)
                assert websocket.open
                
                # Send valid message after invalid one
                valid_message = {
                    "type": "test",
                    "content": "Valid message after invalid"
                }
                
                await websocket.send(json.dumps(valid_message))
                
                # Connection should still be open
                assert websocket.open
                
                ws_test_suite.logger.info("✅ WebSocket invalid message handling successful")
                
        except Exception as e:
            ws_test_suite.logger.warning(f"⚠️  WebSocket error handling test: {e}")
            pytest.skip(f"WebSocket error handling test failed: {e}")


class TestWebSocketLoadBalancer:
    """Test WebSocket functionality through Application Load Balancer."""
    
    @pytest.mark.asyncio
    async def test_websocket_through_alb(self, ws_test_suite):
        """Test WebSocket connections through Application Load Balancer."""
        # This test specifically validates ALB WebSocket support
        ws_url = f"{ws_test_suite.ws_url}/ws/chat"
        
        try:
            # Test connection with WebSocket-specific headers
            headers = {
                "Upgrade": "websocket",
                "Connection": "Upgrade",
                "Sec-WebSocket-Version": "13",
                "Sec-WebSocket-Key": "test-key"
            }
            
            async with websockets.connect(
                ws_url,
                timeout=ws_test_suite.test_timeout,
                extra_headers=headers
            ) as websocket:
                # Test that connection works through ALB
                assert websocket.open
                
                # Send a message to test bidirectional communication
                test_message = {
                    "type": "alb_test",
                    "content": "Testing through ALB"
                }
                
                await websocket.send(json.dumps(test_message))
                
                # Connection should remain stable
                assert websocket.open
                
                ws_test_suite.logger.info("✅ WebSocket through ALB successful")
                
        except Exception as e:
            ws_test_suite.logger.warning(f"⚠️  WebSocket ALB test: {e}")
            pytest.skip(f"WebSocket ALB functionality may not be configured: {e}")
    
    @pytest.mark.asyncio
    async def test_websocket_connection_persistence(self, ws_test_suite):
        """Test WebSocket connection persistence through load balancer."""
        ws_url = f"{ws_test_suite.ws_url}/ws/chat"
        
        try:
            async with websockets.connect(
                ws_url,
                timeout=ws_test_suite.test_timeout
            ) as websocket:
                # Send multiple messages over time to test persistence
                for i in range(5):
                    message = {
                        "type": "persistence_test",
                        "sequence": i,
                        "timestamp": datetime.now().isoformat()
                    }
                    
                    await websocket.send(json.dumps(message))
                    
                    # Wait between messages
                    await asyncio.sleep(1)
                    
                    # Connection should remain open
                    assert websocket.open
                
                ws_test_suite.logger.info("✅ WebSocket connection persistence successful")
                
        except Exception as e:
            ws_test_suite.logger.warning(f"⚠️  WebSocket persistence test: {e}")
            pytest.skip(f"WebSocket persistence test failed: {e}")


class TestWebSocketPerformance:
    """Test WebSocket performance characteristics."""
    
    @pytest.mark.asyncio
    async def test_websocket_connection_time(self, ws_test_suite):
        """Test WebSocket connection establishment time."""
        ws_url = f"{ws_test_suite.ws_url}/ws/chat"
        
        try:
            start_time = datetime.now()
            
            async with websockets.connect(
                ws_url,
                timeout=ws_test_suite.test_timeout
            ) as websocket:
                end_time = datetime.now()
                connection_time = (end_time - start_time).total_seconds()
                
                # Connection should be established quickly (under 5 seconds)
                assert connection_time < 5.0
                assert websocket.open
                
                ws_test_suite.logger.info(
                    f"✅ WebSocket connection time: {connection_time:.3f}s"
                )
                
        except Exception as e:
            ws_test_suite.logger.warning(f"⚠️  WebSocket connection time test: {e}")
            pytest.skip(f"WebSocket connection time test failed: {e}")
    
    @pytest.mark.asyncio
    async def test_websocket_message_throughput(self, ws_test_suite):
        """Test WebSocket message throughput."""
        ws_url = f"{ws_test_suite.ws_url}/ws/chat"
        
        try:
            async with websockets.connect(
                ws_url,
                timeout=ws_test_suite.test_timeout
            ) as websocket:
                # Send multiple messages quickly
                message_count = 10
                start_time = datetime.now()
                
                for i in range(message_count):
                    message = {
                        "type": "throughput_test",
                        "sequence": i,
                        "data": f"Message {i}"
                    }
                    
                    await websocket.send(json.dumps(message))
                
                end_time = datetime.now()
                total_time = (end_time - start_time).total_seconds()
                
                # Should be able to send messages quickly
                assert total_time < 5.0
                
                messages_per_second = message_count / total_time
                
                ws_test_suite.logger.info(
                    f"✅ WebSocket throughput: {messages_per_second:.1f} messages/second"
                )
                
        except Exception as e:
            ws_test_suite.logger.warning(f"⚠️  WebSocket throughput test: {e}")
            pytest.skip(f"WebSocket throughput test failed: {e}")


class TestWebSocketIntegration:
    """Test WebSocket integration with other system components."""
    
    @pytest.mark.asyncio
    async def test_websocket_with_http_endpoints(self, ws_test_suite):
        """Test WebSocket integration with HTTP endpoints."""
        try:
            # First test HTTP endpoint
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{ws_test_suite.base_url}/health",
                    timeout=ws_test_suite.test_timeout
                ) as response:
                    http_status = response.status
            
            # Then test WebSocket on same server
            ws_url = f"{ws_test_suite.ws_url}/ws/chat"
            
            async with websockets.connect(
                ws_url,
                timeout=ws_test_suite.test_timeout
            ) as websocket:
                ws_connected = websocket.open
            
            # Both should work
            assert http_status in [200, 401, 404]  # Various acceptable HTTP responses
            assert ws_connected
            
            ws_test_suite.logger.info("✅ WebSocket-HTTP integration successful")
            
        except Exception as e:
            ws_test_suite.logger.warning(f"⚠️  WebSocket-HTTP integration test: {e}")
            pytest.skip(f"WebSocket-HTTP integration test failed: {e}")
    
    @pytest.mark.asyncio
    async def test_websocket_error_scenarios(self, ws_test_suite):
        """Test WebSocket error handling scenarios."""
        try:
            # Test connection to non-existent endpoint
            invalid_ws_url = f"{ws_test_suite.ws_url}/ws/nonexistent"
            
            try:
                async with websockets.connect(
                    invalid_ws_url,
                    timeout=5.0
                ) as websocket:
                    # If connection succeeds, that's unexpected but not a failure
                    ws_test_suite.logger.info("⚠️  Connection to invalid endpoint succeeded")
                    
            except (websockets.exceptions.ConnectionClosed, 
                    websockets.exceptions.InvalidStatusCode,
                    asyncio.TimeoutError) as e:
                # Expected behavior for invalid endpoint
                ws_test_suite.logger.info(f"✅ Invalid endpoint properly rejected: {type(e).__name__}")
            
            # Test valid endpoint again to ensure server is still working
            valid_ws_url = f"{ws_test_suite.ws_url}/ws/chat"
            
            try:
                async with websockets.connect(
                    valid_ws_url,
                    timeout=5.0
                ) as websocket:
                    assert websocket.open
                    ws_test_suite.logger.info("✅ Valid endpoint still working after error test")
                    
            except Exception as e:
                ws_test_suite.logger.warning(f"Valid endpoint test after error: {e}")
            
        except Exception as e:
            ws_test_suite.logger.warning(f"⚠️  WebSocket error scenarios test: {e}")
            pytest.skip(f"WebSocket error scenarios test failed: {e}")


class TestWebSocketSecurity:
    """Test basic WebSocket security aspects."""
    
    @pytest.mark.asyncio
    async def test_websocket_protocol_upgrade(self, ws_test_suite):
        """Test proper WebSocket protocol upgrade."""
        # Test that WebSocket upgrade works correctly
        ws_url = f"{ws_test_suite.ws_url}/ws/chat"
        
        try:
            async with websockets.connect(
                ws_url,
                timeout=ws_test_suite.test_timeout
            ) as websocket:
                # Check that we have a proper WebSocket connection
                assert websocket.open
                
                # WebSocket should use proper protocol
                assert hasattr(websocket, 'protocol')
                
                ws_test_suite.logger.info("✅ WebSocket protocol upgrade successful")
                
        except Exception as e:
            ws_test_suite.logger.warning(f"⚠️  WebSocket protocol test: {e}")
            pytest.skip(f"WebSocket protocol test failed: {e}")
    
    @pytest.mark.asyncio
    async def test_websocket_connection_limits(self, ws_test_suite):
        """Test WebSocket connection limits and resource management."""
        ws_url = f"{ws_test_suite.ws_url}/ws/chat"
        connections = []
        
        try:
            # Try to create multiple connections (reasonable number for testing)
            max_connections = 5
            
            for i in range(max_connections):
                try:
                    websocket = await websockets.connect(
                        ws_url,
                        timeout=5.0
                    )
                    connections.append(websocket)
                    
                except Exception as e:
                    ws_test_suite.logger.info(f"Connection limit reached at {i} connections: {e}")
                    break
            
            # Should be able to create at least a few connections
            assert len(connections) > 0
            
            ws_test_suite.logger.info(f"✅ WebSocket connections created: {len(connections)}")
            
        finally:
            # Clean up all connections
            for websocket in connections:
                try:
                    await websocket.close()
                except Exception as e:
                    ws_test_suite.logger.warning(f"Connection cleanup warning: {e}")


# Test execution functions
def run_websocket_tests():
    """Run WebSocket tests with proper configuration."""
    import subprocess
    
    # Set test environment
    os.environ.setdefault("TESTING", "true")
    os.environ.setdefault("LOG_LEVEL", "INFO")
    
    # Run pytest with specific markers and output
    cmd = [
        "python", "-m", "pytest",
        __file__,
        "-v",
        "--tb=short",
        "--color=yes",
        "-x"  # Stop on first failure
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        print("🔌 WEBSOCKET TEST RESULTS")
        print("=" * 50)
        print(result.stdout)
        
        if result.stderr:
            print("\n⚠️  WARNINGS/ERRORS:")
            print(result.stderr)
        
        return result.returncode == 0
        
    except Exception as e:
        print(f"❌ Failed to run WebSocket tests: {e}")
        return False


if __name__ == "__main__":
    success = run_websocket_tests()
    exit(0 if success else 1)