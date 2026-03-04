#!/usr/bin/env python3
"""
Simple WebSocket Test

Test WebSocket connection with basic websockets library.
"""

import asyncio
import websockets
import json
import sys

async def test_websocket_simple():
    """Test WebSocket connection simply."""
    
    ws_url = "ws://multimodal-librarian-learning-659419827.us-east-1.elb.amazonaws.com/ws/chat"
    
    print(f"🔗 Testing WebSocket connection to: {ws_url}")
    
    try:
        # Simple connection attempt
        websocket = await websockets.connect(ws_url)
        print("✅ WebSocket connection established!")
        
        # Send a test message
        test_message = {
            "type": "user_message",
            "content": "Hello! Testing WebSocket connection.",
            "timestamp": "2026-01-02T20:30:00Z"
        }
        
        await websocket.send(json.dumps(test_message))
        print("📤 Sent test message")
        
        # Try to receive responses
        message_count = 0
        timeout_count = 0
        
        while message_count < 3 and timeout_count < 2:
            try:
                response = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                message_count += 1
                print(f"📥 Received message {message_count}: {response[:100]}...")
                
            except asyncio.TimeoutError:
                timeout_count += 1
                print(f"⏰ Timeout {timeout_count} - no message received")
        
        await websocket.close()
        print("🔌 WebSocket connection closed")
        
        if message_count > 0:
            print(f"🎉 Success! Received {message_count} messages")
            return True
        else:
            print("⚠️ Connection established but no messages received")
            return True  # Still a success - connection worked
            
    except websockets.exceptions.ConnectionClosedError as e:
        print(f"❌ WebSocket connection closed unexpectedly: {e}")
        return False
        
    except websockets.exceptions.WebSocketException as e:
        print(f"❌ WebSocket error: {e}")
        return False
        
    except Exception as e:
        print(f"❌ Connection failed: {e}")
        print(f"📋 Error type: {type(e).__name__}")
        
        # Check if it's a specific HTTP error
        if "403" in str(e):
            print("🔍 HTTP 403 Forbidden - ALB may be rejecting WebSocket upgrade")
        elif "404" in str(e):
            print("🔍 HTTP 404 Not Found - WebSocket endpoint may not exist")
        elif "502" in str(e):
            print("🔍 HTTP 502 Bad Gateway - Backend may be down")
        elif "503" in str(e):
            print("🔍 HTTP 503 Service Unavailable - Backend may be overloaded")
        
        return False

async def main():
    """Main test function."""
    print("🧪 Simple WebSocket Test")
    print("========================")
    
    success = await test_websocket_simple()
    
    if success:
        print("\n🎯 RESULT: WebSocket connection successful!")
        print("✅ The ALB WebSocket configuration is working!")
        sys.exit(0)
    else:
        print("\n💥 RESULT: WebSocket connection failed")
        print("❌ Need to investigate ALB or backend configuration")
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