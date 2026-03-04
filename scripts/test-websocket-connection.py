#!/usr/bin/env python3
"""
WebSocket Connection Test Script

This script tests the enhanced WebSocket implementation to validate
that the connection fixes are working properly.
"""

import asyncio
import json
import time
import sys
import argparse
from typing import Optional
import websockets
import requests

class WebSocketTester:
    """Test WebSocket connections with comprehensive validation."""
    
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip('/')
        self.ws_url = base_url.replace('http://', 'ws://').replace('https://', 'wss://') + '/ws/chat'
        self.results = {
            'http_health': False,
            'chat_status': False,
            'websocket_connect': False,
            'message_exchange': False,
            'heartbeat': False,
            'diagnostics': False,
            'connection_duration': 0,
            'messages_sent': 0,
            'messages_received': 0,
            'errors': []
        }
    
    def test_http_endpoints(self) -> bool:
        """Test HTTP endpoints before WebSocket testing."""
        print("🔍 Testing HTTP endpoints...")
        
        try:
            # Test health endpoint
            response = requests.get(f"{self.base_url}/health", timeout=10)
            if response.status_code == 200:
                print("✅ Health endpoint responding")
                self.results['http_health'] = True
            else:
                print(f"❌ Health endpoint returned {response.status_code}")
                self.results['errors'].append(f"Health endpoint: {response.status_code}")
        except Exception as e:
            print(f"❌ Health endpoint error: {e}")
            self.results['errors'].append(f"Health endpoint: {e}")
        
        try:
            # Test chat status endpoint
            response = requests.get(f"{self.base_url}/chat/status", timeout=10)
            if response.status_code == 200:
                print("✅ Chat status endpoint responding")
                self.results['chat_status'] = True
                
                # Print status info
                status_data = response.json()
                print(f"   Active connections: {status_data.get('connection_stats', {}).get('active_connections', 'N/A')}")
                print(f"   Features: {', '.join(status_data.get('features', {}).keys())}")
            else:
                print(f"❌ Chat status endpoint returned {response.status_code}")
                self.results['errors'].append(f"Chat status: {response.status_code}")
        except Exception as e:
            print(f"❌ Chat status endpoint error: {e}")
            self.results['errors'].append(f"Chat status: {e}")
        
        try:
            # Test diagnostics endpoint
            response = requests.get(f"{self.base_url}/diagnostics", timeout=10)
            if response.status_code == 200:
                print("✅ Diagnostics endpoint responding")
                self.results['diagnostics'] = True
                
                # Print diagnostic info
                diag_data = response.json()
                print(f"   System health: {diag_data.get('health_indicators', {})}")
            else:
                print(f"❌ Diagnostics endpoint returned {response.status_code}")
        except Exception as e:
            print(f"❌ Diagnostics endpoint error: {e}")
        
        return self.results['http_health'] and self.results['chat_status']
    
    async def test_websocket_connection(self, duration: int = 60) -> bool:
        """Test WebSocket connection with message exchange."""
        print(f"🔗 Testing WebSocket connection for {duration} seconds...")
        
        try:
            start_time = time.time()
            
            async with websockets.connect(self.ws_url) as websocket:
                print("✅ WebSocket connection established")
                self.results['websocket_connect'] = True
                
                # Send initial message
                test_message = {
                    "type": "user_message",
                    "content": "Hello! This is a connection test.",
                    "timestamp": time.time()
                }
                
                await websocket.send(json.dumps(test_message))
                self.results['messages_sent'] += 1
                print("📤 Sent test message")
                
                # Listen for messages
                message_count = 0
                heartbeat_received = False
                
                try:
                    while time.time() - start_time < duration:
                        # Set a timeout for receiving messages
                        try:
                            message = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                            message_data = json.loads(message)
                            message_count += 1
                            self.results['messages_received'] += 1
                            
                            print(f"📥 Received message ({message_count}): {message_data.get('type', 'unknown')}")
                            
                            # Check for heartbeat/pong messages
                            if message_data.get('type') == 'pong':
                                heartbeat_received = True
                                self.results['heartbeat'] = True
                                print("💓 Heartbeat pong received")
                            
                            # Send ping every 30 seconds
                            if time.time() - start_time > 30 and not heartbeat_received:
                                ping_message = {
                                    "type": "ping",
                                    "timestamp": time.time()
                                }
                                await websocket.send(json.dumps(ping_message))
                                print("💓 Sent heartbeat ping")
                        
                        except asyncio.TimeoutError:
                            # No message received, continue
                            continue
                        
                        # Send additional test messages
                        if message_count == 2:  # After receiving welcome messages
                            test_messages = [
                                "Can you tell me about the system status?",
                                "What are your enhanced WebSocket features?",
                                "ping"  # Test connection
                            ]
                            
                            for msg in test_messages:
                                await asyncio.sleep(2)
                                test_msg = {
                                    "type": "user_message",
                                    "content": msg,
                                    "timestamp": time.time()
                                }
                                await websocket.send(json.dumps(test_msg))
                                self.results['messages_sent'] += 1
                                print(f"📤 Sent: {msg}")
                
                except Exception as e:
                    print(f"⚠️ Error during message exchange: {e}")
                    self.results['errors'].append(f"Message exchange: {e}")
                
                self.results['connection_duration'] = time.time() - start_time
                
                if message_count > 0:
                    self.results['message_exchange'] = True
                    print(f"✅ Message exchange successful ({message_count} messages received)")
                else:
                    print("❌ No messages received")
                
                return True
                
        except Exception as e:
            print(f"❌ WebSocket connection failed: {e}")
            self.results['errors'].append(f"WebSocket connection: {e}")
            return False
    
    async def test_reconnection(self) -> bool:
        """Test WebSocket reconnection capability."""
        print("🔄 Testing reconnection capability...")
        
        try:
            # First connection
            async with websockets.connect(self.ws_url) as websocket1:
                print("✅ First connection established")
                
                # Send a message
                await websocket1.send(json.dumps({
                    "type": "user_message",
                    "content": "First connection test",
                    "timestamp": time.time()
                }))
                
                # Receive response
                response = await asyncio.wait_for(websocket1.recv(), timeout=10)
                print("📥 Received response on first connection")
            
            print("🔌 First connection closed")
            
            # Wait a moment
            await asyncio.sleep(2)
            
            # Second connection (reconnection)
            async with websockets.connect(self.ws_url) as websocket2:
                print("✅ Reconnection successful")
                
                # Send a message
                await websocket2.send(json.dumps({
                    "type": "user_message",
                    "content": "Reconnection test",
                    "timestamp": time.time()
                }))
                
                # Receive response
                response = await asyncio.wait_for(websocket2.recv(), timeout=10)
                print("📥 Received response on reconnection")
                
                return True
                
        except Exception as e:
            print(f"❌ Reconnection test failed: {e}")
            self.results['errors'].append(f"Reconnection: {e}")
            return False
    
    def print_results(self):
        """Print comprehensive test results."""
        print("\n" + "="*50)
        print("📊 WebSocket Connection Test Results")
        print("="*50)
        
        # Overall status
        overall_success = (
            self.results['http_health'] and
            self.results['websocket_connect'] and
            self.results['message_exchange']
        )
        
        status_emoji = "✅" if overall_success else "❌"
        print(f"{status_emoji} Overall Status: {'PASS' if overall_success else 'FAIL'}")
        print()
        
        # Detailed results
        print("📋 Detailed Results:")
        print(f"   HTTP Health Endpoint: {'✅' if self.results['http_health'] else '❌'}")
        print(f"   Chat Status Endpoint: {'✅' if self.results['chat_status'] else '❌'}")
        print(f"   Diagnostics Endpoint: {'✅' if self.results['diagnostics'] else '❌'}")
        print(f"   WebSocket Connection: {'✅' if self.results['websocket_connect'] else '❌'}")
        print(f"   Message Exchange: {'✅' if self.results['message_exchange'] else '❌'}")
        print(f"   Heartbeat/Ping-Pong: {'✅' if self.results['heartbeat'] else '❌'}")
        print()
        
        # Statistics
        print("📈 Statistics:")
        print(f"   Connection Duration: {self.results['connection_duration']:.1f} seconds")
        print(f"   Messages Sent: {self.results['messages_sent']}")
        print(f"   Messages Received: {self.results['messages_received']}")
        print()
        
        # Errors
        if self.results['errors']:
            print("❌ Errors:")
            for error in self.results['errors']:
                print(f"   - {error}")
        else:
            print("✅ No errors detected")
        
        print("="*50)
        
        return overall_success

async def main():
    """Main test function."""
    parser = argparse.ArgumentParser(description='Test WebSocket connection')
    parser.add_argument('url', help='Base URL of the service (e.g., http://localhost:8000)')
    parser.add_argument('--duration', type=int, default=60, help='Test duration in seconds (default: 60)')
    parser.add_argument('--skip-reconnection', action='store_true', help='Skip reconnection test')
    
    args = parser.parse_args()
    
    print("🧪 WebSocket Connection Tester")
    print("==============================")
    print(f"Target URL: {args.url}")
    print(f"Test Duration: {args.duration} seconds")
    print()
    
    tester = WebSocketTester(args.url)
    
    # Test HTTP endpoints first
    if not tester.test_http_endpoints():
        print("❌ HTTP endpoints failed, skipping WebSocket tests")
        tester.print_results()
        sys.exit(1)
    
    print()
    
    # Test WebSocket connection
    ws_success = await tester.test_websocket_connection(args.duration)
    
    if ws_success and not args.skip_reconnection:
        print()
        await tester.test_reconnection()
    
    # Print final results
    success = tester.print_results()
    
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Test interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n💥 Unexpected error: {e}")
        sys.exit(1)