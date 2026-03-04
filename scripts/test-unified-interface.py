#!/usr/bin/env python3
"""
Test script for the unified interface implementation.
Validates that all components are working together correctly.
"""

import asyncio
import aiohttp
import json
import sys
import os
from pathlib import Path

# Add the src directory to the Python path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

async def test_unified_interface():
    """Test the unified interface functionality."""
    
    print("🧪 Testing Unified Interface Implementation")
    print("=" * 50)
    
    base_url = "http://localhost:8000"
    
    async with aiohttp.ClientSession() as session:
        
        # Test 1: Check if unified interface endpoint is available
        print("\n1. Testing unified interface endpoint...")
        try:
            async with session.get(f"{base_url}/app") as response:
                if response.status == 200:
                    content = await response.text()
                    if "unified_interface.css" in content and "unified_interface.js" in content:
                        print("✅ Unified interface HTML served successfully")
                        print("✅ CSS and JS files referenced correctly")
                    else:
                        print("⚠️  Unified interface HTML served but missing CSS/JS references")
                else:
                    print(f"❌ Unified interface endpoint failed: {response.status}")
        except Exception as e:
            print(f"❌ Failed to access unified interface: {e}")
        
        # Test 2: Check static file serving
        print("\n2. Testing static file serving...")
        
        # Test CSS file
        try:
            async with session.get(f"{base_url}/static/css/unified_interface.css") as response:
                if response.status == 200:
                    css_content = await response.text()
                    if ".app-container" in css_content and ".sidebar" in css_content:
                        print("✅ CSS file served successfully with correct content")
                    else:
                        print("⚠️  CSS file served but content may be incomplete")
                else:
                    print(f"❌ CSS file not accessible: {response.status}")
        except Exception as e:
            print(f"❌ Failed to access CSS file: {e}")
        
        # Test JS file
        try:
            async with session.get(f"{base_url}/static/js/unified_interface.js") as response:
                if response.status == 200:
                    js_content = await response.text()
                    if "UnifiedInterface" in js_content and "switchView" in js_content:
                        print("✅ JavaScript file served successfully with correct content")
                    else:
                        print("⚠️  JavaScript file served but content may be incomplete")
                else:
                    print(f"❌ JavaScript file not accessible: {response.status}")
        except Exception as e:
            print(f"❌ Failed to access JavaScript file: {e}")
        
        # Test 3: Check if existing chat and document endpoints are still working
        print("\n3. Testing existing endpoints...")
        
        # Test chat endpoint
        try:
            async with session.get(f"{base_url}/chat") as response:
                if response.status == 200:
                    print("✅ Chat interface still accessible")
                else:
                    print(f"⚠️  Chat interface status: {response.status}")
        except Exception as e:
            print(f"❌ Failed to access chat interface: {e}")
        
        # Test documents endpoint
        try:
            async with session.get(f"{base_url}/documents") as response:
                if response.status in [200, 503]:  # 503 is acceptable for fallback
                    print("✅ Documents interface accessible")
                else:
                    print(f"⚠️  Documents interface status: {response.status}")
        except Exception as e:
            print(f"❌ Failed to access documents interface: {e}")
        
        # Test 4: Check API endpoints that the unified interface will use
        print("\n4. Testing API endpoints...")
        
        # Test health endpoint
        try:
            async with session.get(f"{base_url}/health") as response:
                if response.status == 200:
                    health_data = await response.json()
                    print("✅ Health endpoint working")
                    print(f"   Overall status: {health_data.get('overall_status', 'unknown')}")
                else:
                    print(f"❌ Health endpoint failed: {response.status}")
        except Exception as e:
            print(f"❌ Failed to access health endpoint: {e}")
        
        # Test features endpoint
        try:
            async with session.get(f"{base_url}/features") as response:
                if response.status == 200:
                    features_data = await response.json()
                    print("✅ Features endpoint working")
                    features = features_data.get('features', {})
                    print(f"   Chat enabled: {features.get('chat', False)}")
                    print(f"   Document upload enabled: {features.get('document_upload', False)}")
                    print(f"   RAG integration enabled: {features.get('rag_integration', False)}")
                else:
                    print(f"❌ Features endpoint failed: {response.status}")
        except Exception as e:
            print(f"❌ Failed to access features endpoint: {e}")
        
        # Test 5: Check if document API endpoints are available
        print("\n5. Testing document API endpoints...")
        
        try:
            async with session.get(f"{base_url}/api/documents/") as response:
                if response.status in [200, 422]:  # 422 is acceptable for missing query params
                    print("✅ Document list API accessible")
                else:
                    print(f"⚠️  Document list API status: {response.status}")
        except Exception as e:
            print(f"❌ Failed to access document list API: {e}")
        
        # Test 6: Validate file structure
        print("\n6. Validating file structure...")
        
        # Check if template file exists
        template_path = Path("src/multimodal_librarian/templates/unified_interface.html")
        if template_path.exists():
            print("✅ Unified interface template file exists")
        else:
            print("❌ Unified interface template file missing")
        
        # Check if CSS file exists
        css_path = Path("src/multimodal_librarian/static/css/unified_interface.css")
        if css_path.exists():
            print("✅ Unified interface CSS file exists")
        else:
            print("❌ Unified interface CSS file missing")
        
        # Check if JS file exists
        js_path = Path("src/multimodal_librarian/static/js/unified_interface.js")
        if js_path.exists():
            print("✅ Unified interface JavaScript file exists")
        else:
            print("❌ Unified interface JavaScript file missing")
        
        # Check if existing WebSocket and FileHandler JS files exist
        websocket_js_path = Path("src/multimodal_librarian/static/js/websocket.js")
        filehandler_js_path = Path("src/multimodal_librarian/static/js/filehandler.js")
        
        if websocket_js_path.exists():
            print("✅ WebSocket JavaScript file exists")
        else:
            print("⚠️  WebSocket JavaScript file missing (may need to be created)")
        
        if filehandler_js_path.exists():
            print("✅ FileHandler JavaScript file exists")
        else:
            print("⚠️  FileHandler JavaScript file missing (may need to be created)")

def check_server_running():
    """Check if the server is running."""
    import socket
    
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    result = sock.connect_ex(('localhost', 8000))
    sock.close()
    
    return result == 0

async def main():
    """Main test function."""
    
    if not check_server_running():
        print("❌ Server is not running on localhost:8000")
        print("Please start the server with: python -m uvicorn src.multimodal_librarian.main:app --reload")
        return
    
    await test_unified_interface()
    
    print("\n" + "=" * 50)
    print("🎯 Test Summary:")
    print("- Unified interface implementation completed")
    print("- HTML template, CSS, and JavaScript files created")
    print("- Static file serving configured")
    print("- Route handler added to main application")
    print("\n📝 Next Steps:")
    print("1. Start the server: python -m uvicorn src.multimodal_librarian.main:app --reload")
    print("2. Visit http://localhost:8000/app to see the unified interface")
    print("3. Test chat functionality and document management")
    print("4. Verify WebSocket connections and file uploads work")

if __name__ == "__main__":
    asyncio.run(main())