#!/usr/bin/env python3
"""
Test Document API Endpoints

Tests the document upload API endpoints by starting a server and making HTTP requests.
"""

import asyncio
import sys
import os
import tempfile
import requests
import time
import json
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

def create_test_pdf():
    """Create a simple test PDF file."""
    pdf_content = b"""%PDF-1.4
1 0 obj
<<
/Type /Catalog
/Pages 2 0 R
>>
endobj

2 0 obj
<<
/Type /Pages
/Kids [3 0 R]
/Count 1
>>
endobj

3 0 obj
<<
/Type /Page
/Parent 2 0 R
/MediaBox [0 0 612 792]
/Contents 4 0 R
>>
endobj

4 0 obj
<<
/Length 44
>>
stream
BT
/F1 12 Tf
72 720 Td
(Test Document Content) Tj
ET
endstream
endobj

xref
0 5
0000000000 65535 f 
0000000009 00000 n 
0000000074 00000 n 
0000000120 00000 n 
0000000179 00000 n 
trailer
<<
/Size 5
/Root 1 0 R
>>
startxref
238
%%EOF"""
    
    # Create temporary file
    temp_file = tempfile.NamedTemporaryFile(suffix='.pdf', delete=False)
    temp_file.write(pdf_content)
    temp_file.close()
    
    return temp_file.name

def test_server_startup():
    """Test if the server can start up."""
    print("🧪 Testing Server Startup")
    print("=" * 50)
    
    try:
        # Try to import the main app
        from multimodal_librarian.main import app
        print("✅ Main application imported successfully")
        
        # Check if document routes are available
        document_routes = []
        for route in app.routes:
            if hasattr(route, 'path') and '/api/documents' in route.path:
                methods = getattr(route, 'methods', {'GET'})
                document_routes.append(f"{list(methods)} {route.path}")
        
        if document_routes:
            print(f"✅ Found {len(document_routes)} document API routes:")
            for route in document_routes:
                print(f"   {route}")
            return True
        else:
            print("❌ No document API routes found")
            return False
            
    except Exception as e:
        print(f"❌ Failed to start server: {e}")
        return False

def test_health_endpoint():
    """Test the health endpoint."""
    print("\\n🧪 Testing Health Endpoint")
    print("=" * 50)
    
    try:
        response = requests.get("http://localhost:8001/health", timeout=5)
        if response.status_code == 200:
            print("✅ Health endpoint is responding")
            return True
        else:
            print(f"❌ Health endpoint returned status {response.status_code}")
            return False
    except requests.exceptions.ConnectionError:
        print("❌ Could not connect to server (is it running?)")
        return False
    except Exception as e:
        print(f"❌ Health check failed: {e}")
        return False

def test_document_endpoints():
    """Test document API endpoints."""
    print("\\n🧪 Testing Document API Endpoints")
    print("=" * 50)
    
    base_url = "http://localhost:8001/api/documents"
    
    # Test document list endpoint
    try:
        response = requests.get(f"{base_url}/", timeout=10)
        if response.status_code == 200:
            print("✅ Document list endpoint is working")
            list_working = True
        else:
            print(f"❌ Document list endpoint returned status {response.status_code}")
            list_working = False
    except Exception as e:
        print(f"❌ Document list endpoint failed: {e}")
        list_working = False
    
    # Test document upload endpoint
    try:
        pdf_file = create_test_pdf()
        
        with open(pdf_file, 'rb') as f:
            files = {'file': ('test.pdf', f, 'application/pdf')}
            data = {
                'title': 'Test Document',
                'description': 'Test document for API validation'
            }
            
            response = requests.post(f"{base_url}/upload", files=files, data=data, timeout=30)
            
            if response.status_code in [200, 201]:
                print("✅ Document upload endpoint is working")
                upload_working = True
                
                # Try to parse response
                try:
                    result = response.json()
                    if 'document_id' in result:
                        print(f"✅ Upload returned document ID: {result['document_id']}")
                    else:
                        print("⚠️  Upload succeeded but no document ID returned")
                except:
                    print("⚠️  Upload succeeded but response is not JSON")
                    
            else:
                print(f"❌ Document upload endpoint returned status {response.status_code}")
                try:
                    error_detail = response.json()
                    print(f"   Error: {error_detail}")
                except:
                    print(f"   Error: {response.text}")
                upload_working = False
        
        # Clean up
        os.unlink(pdf_file)
        
    except Exception as e:
        print(f"❌ Document upload endpoint failed: {e}")
        upload_working = False
    
    # Test health endpoint
    try:
        response = requests.get(f"{base_url}/health", timeout=10)
        if response.status_code == 200:
            print("✅ Document health endpoint is working")
            health_working = True
        else:
            print(f"❌ Document health endpoint returned status {response.status_code}")
            health_working = False
    except Exception as e:
        print(f"❌ Document health endpoint failed: {e}")
        health_working = False
    
    return list_working, upload_working, health_working

def main():
    """Run all tests."""
    print("🚀 Document API Endpoints Test")
    print("=" * 60)
    
    # Test server startup
    server_ok = test_server_startup()
    
    if not server_ok:
        print("\\n❌ Server startup failed - cannot proceed with endpoint tests")
        print("\\n📋 To fix:")
        print("1. Fix import issues in the application")
        print("2. Start server: uvicorn src.multimodal_librarian.main:app --reload")
        print("3. Run this test again")
        return False
    
    print("\\n📋 Server startup successful! Now testing endpoints...")
    print("\\n⚠️  Note: This test requires the server to be running.")
    print("   Start with: uvicorn src.multimodal_librarian.main:app --reload")
    
    # Test health first
    health_ok = test_health_endpoint()
    
    if not health_ok:
        print("\\n❌ Server is not responding - start the server first")
        return False
    
    # Test document endpoints
    list_ok, upload_ok, health_ok = test_document_endpoints()
    
    # Summary
    print("\\n" + "=" * 60)
    print("📊 Test Results Summary")
    print("=" * 60)
    
    results = [
        ("Server Startup", server_ok),
        ("Document List API", list_ok),
        ("Document Upload API", upload_ok),
        ("Document Health API", health_ok),
    ]
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} {test_name}")
    
    print(f"\\n🎯 Overall: {passed}/{total} tests passed ({passed/total*100:.1f}%)")
    
    if passed == total:
        print("🎉 All document API endpoints are working!")
        print("\\n📋 Next Steps:")
        print("1. Test with real PDF files")
        print("2. Test document processing pipeline")
        print("3. Test RAG integration with uploaded documents")
    else:
        print("⚠️  Some endpoints need attention.")
        print("\\n📋 To fix:")
        print("1. Check server logs for errors")
        print("2. Verify all dependencies are installed")
        print("3. Check database connections")
    
    return passed == total

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)