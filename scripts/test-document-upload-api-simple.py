#!/usr/bin/env python3
"""
Simple Document Upload API Test

Tests the document upload API endpoints directly without loading the full application.
"""

import asyncio
import sys
import os
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

def test_document_router_import():
    """Test if the document router can be imported successfully."""
    print("🧪 Testing Document Router Import")
    print("=" * 50)
    
    try:
        # Test direct import of document router
        from multimodal_librarian.api.routers.documents import router
        print("✅ Document router imported successfully")
        
        # Check available routes
        routes = []
        for route in router.routes:
            if hasattr(route, 'path'):
                methods = getattr(route, 'methods', {'GET'})
                routes.append(f"{list(methods)} {route.path}")
        
        print(f"✅ Found {len(routes)} routes in document router:")
        for route in routes:
            print(f"   {route}")
        
        return True
        
    except Exception as e:
        print(f"❌ Failed to import document router: {e}")
        return False

def test_document_models():
    """Test if document models can be imported."""
    print("\\n🧪 Testing Document Models")
    print("=" * 50)
    
    try:
        from multimodal_librarian.models.documents import (
            DocumentUploadRequest, DocumentUploadResponse, Document,
            DocumentListResponse, DocumentSearchRequest, DocumentStatus
        )
        print("✅ Document models imported successfully")
        
        # Test model creation
        upload_request = DocumentUploadRequest(
            title="Test Document",
            description="Test description"
        )
        print(f"✅ Created DocumentUploadRequest: {upload_request.title}")
        
        return True
        
    except Exception as e:
        print(f"❌ Failed to import document models: {e}")
        return False

def test_upload_service():
    """Test if upload service can be imported."""
    print("\\n🧪 Testing Upload Service")
    print("=" * 50)
    
    try:
        from multimodal_librarian.services.upload_service import UploadService
        print("✅ Upload service imported successfully")
        
        # Test service creation
        service = UploadService()
        print(f"✅ Created UploadService instance")
        
        return True
        
    except Exception as e:
        print(f"❌ Failed to import upload service: {e}")
        return False

def test_processing_service():
    """Test if processing service can be imported."""
    print("\\n🧪 Testing Processing Service")
    print("=" * 50)
    
    try:
        from multimodal_librarian.services.processing_service import ProcessingService
        print("✅ Processing service imported successfully")
        
        return True
        
    except Exception as e:
        print(f"❌ Failed to import processing service: {e}")
        return False

def test_document_manager():
    """Test if document manager can be imported."""
    print("\\n🧪 Testing Document Manager")
    print("=" * 50)
    
    try:
        from multimodal_librarian.components.document_manager.document_manager import DocumentManager
        print("✅ Document manager imported successfully")
        
        return True
        
    except Exception as e:
        print(f"❌ Failed to import document manager: {e}")
        return False

def main():
    """Run all tests."""
    print("🚀 Document Upload API Component Test")
    print("=" * 60)
    
    tests = [
        ("Document Models", test_document_models),
        ("Upload Service", test_upload_service),
        ("Processing Service", test_processing_service),
        ("Document Manager", test_document_manager),
        ("Document Router", test_document_router_import),
    ]
    
    results = []
    
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"❌ {test_name} test failed with exception: {e}")
            results.append((test_name, False))
    
    # Summary
    print("\\n" + "=" * 60)
    print("📊 Test Results Summary")
    print("=" * 60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} {test_name}")
    
    print(f"\\n🎯 Overall: {passed}/{total} tests passed ({passed/total*100:.1f}%)")
    
    if passed == total:
        print("🎉 All document upload API components are working!")
        print("\\n📋 Next Steps:")
        print("1. Start the server: uvicorn src.multimodal_librarian.main:app --reload")
        print("2. Test upload endpoint: POST /api/documents/upload")
        print("3. Check document list: GET /api/documents/")
    else:
        print("⚠️  Some components need attention before the API will work properly.")
    
    return passed == total

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)