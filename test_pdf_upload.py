#!/usr/bin/env python3
"""
Simple test script for PDF upload functionality.

This script tests the basic PDF upload endpoints and functionality
to ensure Phase 1 implementation is working correctly.
"""

import asyncio
import json
import requests
import time
from pathlib import Path

# Test configuration
BASE_URL = "http://multimodal-librarian-learning-659419827.us-east-1.elb.amazonaws.com"
TEST_PDF_PATH = "test_document.pdf"

def create_test_pdf():
    """Create a simple test PDF file."""
    try:
        from reportlab.pdfgen import canvas
        from reportlab.lib.pagesizes import letter
        
        # Create a simple PDF
        c = canvas.Canvas(TEST_PDF_PATH, pagesize=letter)
        c.drawString(100, 750, "Test Document for The Librarian")
        c.drawString(100, 730, "This is a test PDF document for upload testing.")
        c.drawString(100, 710, "Created by the PDF upload test script.")
        c.drawString(100, 690, f"Generated at: {time.strftime('%Y-%m-%d %H:%M:%S')}")
        c.showPage()
        c.save()
        
        print(f"✅ Created test PDF: {TEST_PDF_PATH}")
        return True
        
    except ImportError:
        print("⚠️  reportlab not available, creating dummy PDF")
        # Create a minimal PDF header for testing
        with open(TEST_PDF_PATH, 'wb') as f:
            f.write(b'%PDF-1.4\n')
            f.write(b'1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n')
            f.write(b'2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n')
            f.write(b'3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] >>\nendobj\n')
            f.write(b'xref\n0 4\n0000000000 65535 f \n0000000009 00000 n \n0000000058 00000 n \n0000000115 00000 n \n')
            f.write(b'trailer\n<< /Size 4 /Root 1 0 R >>\nstartxref\n178\n%%EOF\n')
        
        print(f"✅ Created minimal test PDF: {TEST_PDF_PATH}")
        return True

def test_health_check():
    """Test basic health check endpoint."""
    try:
        response = requests.get(f"{BASE_URL}/health")
        if response.status_code == 200:
            data = response.json()
            print("✅ Health check passed")
            print(f"   Status: {data.get('overall_status')}")
            print(f"   AI Available: {data.get('services', {}).get('ai', {}).get('status')}")
            return True
        else:
            print(f"❌ Health check failed: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Health check error: {e}")
        return False

def test_features_endpoint():
    """Test features endpoint to check PDF upload availability."""
    try:
        response = requests.get(f"{BASE_URL}/features")
        if response.status_code == 200:
            data = response.json()
            features = data.get('features', {})
            print("✅ Features endpoint accessible")
            print(f"   PDF Processing: {features.get('pdf_processing')}")
            print(f"   Document Upload: {features.get('document_upload')}")
            print(f"   Document Management: {features.get('document_management')}")
            return True
        else:
            print(f"❌ Features endpoint failed: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Features endpoint error: {e}")
        return False

def test_document_upload():
    """Test document upload endpoint."""
    if not Path(TEST_PDF_PATH).exists():
        print(f"❌ Test PDF not found: {TEST_PDF_PATH}")
        return False
    
    try:
        with open(TEST_PDF_PATH, 'rb') as f:
            files = {'file': (TEST_PDF_PATH, f, 'application/pdf')}
            data = {
                'title': 'Test Document Upload',
                'description': 'Test document for upload functionality'
            }
            
            response = requests.post(f"{BASE_URL}/api/documents/upload", files=files, data=data)
            
        if response.status_code == 200:
            result = response.json()
            print("✅ Document upload successful")
            print(f"   Document ID: {result.get('document_id')}")
            print(f"   Title: {result.get('title')}")
            print(f"   Status: {result.get('status')}")
            print(f"   File Size: {result.get('file_size')} bytes")
            return result.get('document_id')
        else:
            print(f"❌ Document upload failed: {response.status_code}")
            try:
                error_data = response.json()
                print(f"   Error: {error_data.get('detail', 'Unknown error')}")
            except:
                print(f"   Response: {response.text}")
            return None
            
    except Exception as e:
        print(f"❌ Document upload error: {e}")
        return None

def test_document_list():
    """Test document list endpoint."""
    try:
        response = requests.get(f"{BASE_URL}/api/documents")
        if response.status_code == 200:
            data = response.json()
            documents = data.get('documents', [])
            print("✅ Document list retrieved")
            print(f"   Total documents: {data.get('total_count', 0)}")
            print(f"   Documents in response: {len(documents)}")
            
            for doc in documents[:3]:  # Show first 3 documents
                print(f"   - {doc.get('title')} ({doc.get('status')})")
            
            return True
        else:
            print(f"❌ Document list failed: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Document list error: {e}")
        return False

def test_document_details(document_id):
    """Test document details endpoint."""
    if not document_id:
        print("⚠️  Skipping document details test (no document ID)")
        return False
    
    try:
        response = requests.get(f"{BASE_URL}/api/documents/{document_id}")
        if response.status_code == 200:
            doc = response.json()
            print("✅ Document details retrieved")
            print(f"   ID: {doc.get('id')}")
            print(f"   Title: {doc.get('title')}")
            print(f"   Status: {doc.get('status')}")
            print(f"   File Size: {doc.get('file_size')} bytes")
            print(f"   Upload Time: {doc.get('upload_timestamp')}")
            return True
        else:
            print(f"❌ Document details failed: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Document details error: {e}")
        return False

def test_upload_statistics():
    """Test upload statistics endpoint."""
    try:
        response = requests.get(f"{BASE_URL}/api/documents/statistics")
        if response.status_code == 200:
            stats = response.json()
            print("✅ Upload statistics retrieved")
            print(f"   Total documents: {stats.get('total_documents', 0)}")
            print(f"   Total size: {stats.get('total_size_mb', 0)} MB")
            
            status_counts = stats.get('status_counts', {})
            for status, count in status_counts.items():
                if count > 0:
                    print(f"   {status}: {count}")
            
            storage_status = stats.get('storage_service_status', {})
            print(f"   Storage status: {storage_status.get('status', 'unknown')}")
            
            return True
        else:
            print(f"❌ Upload statistics failed: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Upload statistics error: {e}")
        return False

def cleanup():
    """Clean up test files."""
    try:
        if Path(TEST_PDF_PATH).exists():
            Path(TEST_PDF_PATH).unlink()
            print(f"🧹 Cleaned up test file: {TEST_PDF_PATH}")
    except Exception as e:
        print(f"⚠️  Cleanup error: {e}")

def main():
    """Run all tests."""
    print("🧪 Testing PDF Upload Functionality for The Librarian")
    print("=" * 60)
    
    # Create test PDF
    if not create_test_pdf():
        print("❌ Failed to create test PDF, aborting tests")
        return
    
    # Run tests
    tests_passed = 0
    total_tests = 6
    
    print("\n📋 Running Tests:")
    print("-" * 30)
    
    # Test 1: Health check
    if test_health_check():
        tests_passed += 1
    
    # Test 2: Features endpoint
    if test_features_endpoint():
        tests_passed += 1
    
    # Test 3: Document upload
    document_id = test_document_upload()
    if document_id:
        tests_passed += 1
    
    # Test 4: Document list
    if test_document_list():
        tests_passed += 1
    
    # Test 5: Document details
    if test_document_details(document_id):
        tests_passed += 1
    
    # Test 6: Upload statistics
    if test_upload_statistics():
        tests_passed += 1
    
    # Results
    print("\n📊 Test Results:")
    print("-" * 30)
    print(f"Tests passed: {tests_passed}/{total_tests}")
    
    if tests_passed == total_tests:
        print("🎉 All tests passed! PDF upload functionality is working correctly.")
    elif tests_passed >= total_tests * 0.8:
        print("✅ Most tests passed. PDF upload functionality is mostly working.")
    else:
        print("⚠️  Some tests failed. Check the implementation.")
    
    # Cleanup
    cleanup()
    
    print(f"\n🔗 Access The Librarian at: {BASE_URL}/chat")
    print("📄 Try uploading PDF documents in the Documents tab!")

if __name__ == "__main__":
    main()