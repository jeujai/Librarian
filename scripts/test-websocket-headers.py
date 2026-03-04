#!/usr/bin/env python3
"""
WebSocket Headers Test

Test WebSocket connection with detailed header inspection.
"""

import asyncio
import websockets
import sys

async def test_websocket_with_headers():
    """Test WebSocket connection with header inspection."""
    
    ws_url = "ws://multimodal-librarian-learning-659419827.us-east-1.elb.amazonaws.com/ws/chat"
    
    print(f"🔗 Testing WebSocket connection to: {ws_url}")
    print("📋 Connection details:")
    
    # Custom headers for WebSocket connection
    extra_headers = {
        "User-Agent": "WebSocket-Test-Client/1.0",
        "Origin": "http://multimodal-librarian-learning-659419827.us-east-1.elb.amazonaws.com"
    }
    
    try:
        # Try to connect with detailed error handling
        async with websockets.connect(
            ws_url, 
            extra_headers=extra_headers,
            ping_interval=None,  # Disable ping for testing
            ping_timeout=None,
            close_timeout=10
        ) as websocket:
            print("✅ WebSocket connection established!")
            print(f"📊 Connection state: {websocket.state}")
            
            # Send a simple message
            await websocket.send('{"type": "test", "message": "Hello WebSocket!"}')
            print("📤 Sent test message")
            
            # Try to receive a response
            try:
                response = await asyncio.wait_for(websocket.recv(), timeout=10.0)
                print(f"📥 Received response: {response[:100]}...")
                return True
            except asyncio.TimeoutError:
                print("⏰ No response received within 10 seconds")
                return True  # Connection worked, just no response
                
    except websockets.exceptions.InvalidStatusCode as e:
        print(f"❌ WebSocket connection rejected with status code: {e.status_code}")
        print(f"📋 Response headers: {e.headers}")
        return False
        
    except websockets.exceptions.InvalidHandshake as e:
        print(f"❌ WebSocket handshake failed: {e}")
        return False
        
    except Exception as e:
        print(f"❌ WebSocket connection failed: {e}")
        print(f"📋 Error type: {type(e).__name__}")
        return False

async def test_http_first():
    """Test HTTP connection first to verify basic connectivity."""
    import aiohttp
    
    base_url = "http://multimodal-librarian-learning-659419827.us-east-1.elb.amazonaws.com"
    
    print(f"🌐 Testing HTTP connection to: {base_url}")
    
    try:
        async with aiohttp.ClientSession() as session:
            # Test health endpoint
            async with session.get(f"{base_url}/health") as response:
                if response.status == 200:
                    print("✅ HTTP health endpoint working")
                else:
                    print(f"⚠️ HTTP health endpoint returned {response.status}")
            
            # Test WebSocket endpoint via HTTP (should return 404 or 405)
            async with session.get(f"{base_url}/ws/chat") as response:
                print(f"📋 WebSocket endpoint via HTTP returned: {response.status}")
                if response.status in [404, 405]:
                    print("✅ WebSocket endpoint exists (returns expected error for HTTP)")
                    return True
                else:
                    print("❌ WebSocket endpoint may not exist")
                    return False
                    
    except Exception as e:
        print(f"❌ HTTP connection failed: {e}")
        return False

async def main():
    """Main test function."""
    print("🧪 WebSocket Headers Test")
    print("=========================")
    
    # Test HTTP first
    http_ok = await test_http_first()
    print()
    
    if not http_ok:
        print("❌ HTTP connection failed, skipping WebSocket test")
        sys.exit(1)
    
    # Test WebSocket
    ws_ok = await test_websocket_with_headers()
    
    if ws_ok:
        print("\n🎯 RESULT: WebSocket connection successful!")
        sys.exit(0)
    else:
        print("\n💥 RESULT: WebSocket connection failed")
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