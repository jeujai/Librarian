#!/usr/bin/env python3
"""
Test script for Document Management UI
Tests the document upload and management functionality
"""

import asyncio
import aiohttp
import json
from pathlib import Path

async def test_document_ui():
    """Test the document management UI functionality"""
    
    print("🧪 Testing Document Management UI...")
    
    # Test API endpoints
    base_url = "http://localhost:8000"
    
    async with aiohttp.ClientSession() as session:
        try:
            # Test document list endpoint
            print("\n📋 Testing document list endpoint...")
            async with session.get(f"{base_url}/api/documents/") as response:
                if response.status == 200:
                    data = await response.json()
                    print(f"✅ Document list endpoint working - found {len(data.get('documents', []))} documents")
                else:
                    print(f"❌ Document list endpoint failed: {response.status}")
            
            # Test health endpoint
            print("\n🏥 Testing health endpoint...")
            async with session.get(f"{base_url}/api/documents/health") as response:
                if response.status == 200:
                    data = await response.json()
                    print(f"✅ Health endpoint working - status: {data.get('status', 'unknown')}")
                else:
                    print(f"❌ Health endpoint failed: {response.status}")
            
            # Test statistics endpoint
            print("\n📊 Testing statistics endpoint...")
            async with session.get(f"{base_url}/api/documents/stats/summary") as response:
                if response.status == 200:
                    data = await response.json()
                    print(f"✅ Statistics endpoint working")
                    print(f"   - Active jobs: {data.get('active_jobs', 0)}")
                    if 'processing_service' in data:
                        stats = data['processing_service']
                        print(f"   - Total jobs: {stats.get('total_jobs', 0)}")
                        print(f"   - Success rate: {stats.get('success_rate', 0):.1f}%")
                else:
                    print(f"❌ Statistics endpoint failed: {response.status}")
            
        except aiohttp.ClientConnectorError:
            print("❌ Could not connect to server. Make sure the application is running on localhost:8000")
            return False
        except Exception as e:
            print(f"❌ Error testing API: {e}")
            return False
    
    # Test static files
    print("\n📁 Testing static files...")
    
    static_files = [
        "src/multimodal_librarian/static/js/document_upload.js",
        "src/multimodal_librarian/static/css/document_manager.css",
        "src/multimodal_librarian/templates/documents.html"
    ]
    
    for file_path in static_files:
        if Path(file_path).exists():
            print(f"✅ {file_path} exists")
        else:
            print(f"❌ {file_path} missing")
    
    # Check if main HTML includes new files
    print("\n🔗 Checking HTML integration...")
    index_path = Path("src/multimodal_librarian/static/index.html")
    if index_path.exists():
        content = index_path.read_text()
        if "document_manager.css" in content:
            print("✅ Document manager CSS included in index.html")
        else:
            print("❌ Document manager CSS not included in index.html")
        
        if "document_upload.js" in content:
            print("✅ Document upload JS included in index.html")
        else:
            print("❌ Document upload JS not included in index.html")
    else:
        print("❌ index.html not found")
    
    print("\n🎉 Document Management UI test completed!")
    return True

if __name__ == "__main__":
    asyncio.run(test_document_ui())