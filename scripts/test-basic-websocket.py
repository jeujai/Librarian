#!/usr/bin/env python3
"""
Basic WebSocket Connection Test

Test the basic WebSocket functionality with the current deployment.
"""

import asyncio
import json
import websockets
import sys

async def test_basic_websocket():
    """Test basic WebSocket connection."""
    
    ws_url = "ws://multimodal-librarian-learning-659419827.us-east-1.elb.amazonaws.com/ws/chat"
    
    print(f"🔗 Testing WebSocket connection to: {ws_url}")
    
    try:
        async with websockets.connect(ws_url) as websocket:
            print("✅ WebSocket connection established!")
            
            # Send a test message
            test_message = {
                "type": "user_message",
                "content": "Hello! This is a connection test with sticky sessions.",
                "timestamp": "2026-01-02T20:20:00Z"
            }
            
            await websocket.send(json.dumps(test_message))
            print("📤 Sent test message")
            
            # Listen for responses
            message_count = 0
            timeout_count = 0
            max_timeout = 3
            
            while message_count < 5 and timeout_count < max_timeout:
                try:
                    # Wait for a message with timeout
                    message = await asyncio.wait_for(websocket.recv(), timeout=10.0)
                    message_data = json.loads(message)
                    message_count += 1
                    
                    print(f"📥 Received message {message_count}: {message_data.get('type', 'unknown')} - {message_data.get('content', '')[:100]}...")
                    
                    # Send another message after receiving some responses
                    if message_count == 2:
                        follow_up = {
                            "type": "user_message", 
                            "content": "How is the WebSocket connection working?",
                            "timestamp": "2026-01-02T20:21:00Z"
                        }
                        await websocket.send(json.dumps(follow_up))
                        print("📤 Sent follow-up message")
                
                except asyncio.TimeoutError:
                    timeout_count += 1
                    print(f"⏰ Timeout {timeout_count}/{max_timeout} - no message received")
                    
                    if timeout_count < max_timeout:
                        # Send a ping message
                        ping_message = {
                            "type": "user_message",
                            "content": "ping",
                            "timestamp": "2026-01-02T20:22:00Z"
                        }
                        await websocket.send(json.dumps(ping_message))
                        print("📤 Sent ping message")
            
            print(f"🎉 Test completed! Received {message_count} messages")
            
            if message_count > 0:
                print("✅ WebSocket connection is working with sticky sessions!")
                return True
            else:
                print("❌ No messages received - connection may have issues")
                return False
                
    except Exception as e:
        print(f"❌ WebSocket connection failed: {e}")
        return False

async def main():
    """Main test function."""
    print("🧪 Basic WebSocket Connection Test")
    print("==================================")
    
    success = await test_basic_websocket()
    
    if success:
        print("\n🎯 RESULT: WebSocket connection is working!")
        print("✅ Sticky sessions appear to be helping with connection stability")
        sys.exit(0)
    else:
        print("\n💥 RESULT: WebSocket connection failed")
        print("❌ May need additional fixes beyond sticky sessions")
        sys.exit(1)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Test interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n💥 Unexpected error: {e}")
        sys.exit(1)