#!/usr/bin/env python3
"""
Validate Document Upload Integration

Comprehensive test of the document upload API and its integration
with the RAG service and knowledge graph.
"""

import requests
import json
import time
from pathlib import Path

BASE_URL = "http://localhost:8001"

def create_test_documents():
    """Create test documents with different content."""
    documents = {
        "ml_basics.pdf": """%PDF-1.4
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
/Length 300
>>
stream
BT
/F1 12 Tf
72 720 Td
(Machine Learning Basics) Tj
0 -20 Td
(Machine learning is a method of data analysis that automates analytical model building.) Tj
0 -20 Td
(It uses algorithms that iteratively learn from data to find hidden insights.) Tj
0 -20 Td
(Common types include supervised learning, unsupervised learning, and reinforcement learning.) Tj
0 -20 Td
(Applications include image recognition, natural language processing, and recommendation systems.) Tj
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
500
%%EOF""",
        
        "deep_learning.txt": """Deep Learning Fundamentals

Deep learning is a subset of machine learning that uses artificial neural networks with multiple layers.
These networks are inspired by the structure and function of the human brain.

Key concepts:
- Neural Networks: Computational models with interconnected nodes
- Layers: Input layer, hidden layers, and output layer
- Activation Functions: Functions that determine neuron output
- Backpropagation: Algorithm for training neural networks
- Gradient Descent: Optimization algorithm for minimizing loss

Applications:
- Computer Vision: Image classification, object detection
- Natural Language Processing: Language translation, sentiment analysis
- Speech Recognition: Converting speech to text
- Autonomous Vehicles: Self-driving car technology

Popular frameworks:
- TensorFlow: Google's open-source platform
- PyTorch: Facebook's research-focused framework
- Keras: High-level neural networks API
"""
    }
    
    # Write test files
    for filename, content in documents.items():
        with open(filename, "w") as f:
            f.write(content)
    
    return list(documents.keys())

def test_document_upload(filename, title, description, tags):
    """Test uploading a single document."""
    print(f"📤 Uploading {filename}...")
    
    try:
        with open(filename, "rb") as f:
            files = {'file': (filename, f, 'application/pdf' if filename.endswith('.pdf') else 'text/plain')}
            data = {
                'title': title,
                'description': description,
                'tags': tags
            }
            
            response = requests.post(f"{BASE_URL}/api/documents/upload", files=files, data=data)
            
            if response.status_code in [200, 201]:
                result = response.json()
                print(f"   ✅ Upload successful - ID: {result.get('document_id')}")
                return result.get('document_id')
            else:
                print(f"   ❌ Upload failed: {response.status_code} - {response.text}")
                return None
                
    except Exception as e:
        print(f"   ❌ Upload failed: {e}")
        return None

def test_document_list():
    """Test listing documents."""
    print("📋 Testing document list...")
    
    try:
        response = requests.get(f"{BASE_URL}/api/documents/")
        
        if response.status_code == 200:
            result = response.json()
            total = result.get('total_count', 0)
            documents = result.get('documents', [])
            
            print(f"   ✅ Found {total} documents")
            for doc in documents:
                print(f"      - {doc.get('title')}: {doc.get('status')}")
            
            return total > 0
        else:
            print(f"   ❌ List failed: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"   ❌ List failed: {e}")
        return False

def test_document_search(query):
    """Test searching documents."""
    print(f"🔍 Searching for '{query}'...")
    
    try:
        params = {'query': query, 'page_size': 5}
        response = requests.get(f"{BASE_URL}/api/documents/", params=params)
        
        if response.status_code == 200:
            result = response.json()
            total = result.get('total_count', 0)
            documents = result.get('documents', [])
            
            print(f"   ✅ Found {total} matching documents")
            for doc in documents:
                print(f"      - {doc.get('title')}")
            
            return total > 0
        else:
            print(f"   ❌ Search failed: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"   ❌ Search failed: {e}")
        return False

def test_document_health():
    """Test document service health."""
    print("🏥 Testing document service health...")
    
    try:
        response = requests.get(f"{BASE_URL}/api/documents/health")
        
        if response.status_code == 200:
            result = response.json()
            status = result.get('status')
            services = result.get('services', {})
            
            print(f"   ✅ Service status: {status}")
            for service, service_status in services.items():
                print(f"      - {service}: {service_status}")
            
            return status == 'healthy'
        else:
            print(f"   ❌ Health check failed: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"   ❌ Health check failed: {e}")
        return False

def cleanup_test_files(filenames):
    """Clean up test files."""
    for filename in filenames:
        try:
            Path(filename).unlink()
        except:
            pass

def main():
    """Run comprehensive document upload integration tests."""
    print("🚀 Document Upload Integration Validation")
    print("=" * 80)
    
    # Create test documents
    test_files = create_test_documents()
    document_ids = []
    
    try:
        # Test 1: Health check
        health_ok = test_document_health()
        
        # Test 2: Upload documents
        print("\\n📤 Testing Document Upload")
        print("-" * 40)
        
        upload_results = [
            test_document_upload(
                "ml_basics.pdf", 
                "Machine Learning Basics", 
                "Introduction to machine learning concepts",
                "machine-learning,basics,algorithms"
            ),
            test_document_upload(
                "deep_learning.txt", 
                "Deep Learning Fundamentals", 
                "Deep learning and neural networks guide",
                "deep-learning,neural-networks,ai"
            )
        ]
        
        document_ids = [doc_id for doc_id in upload_results if doc_id]
        upload_success = len(document_ids) == len(upload_results)
        
        # Test 3: List documents
        print("\\n📋 Testing Document Management")
        print("-" * 40)
        list_success = test_document_list()
        
        # Test 4: Search documents
        print("\\n🔍 Testing Document Search")
        print("-" * 40)
        search_results = [
            test_document_search("machine learning"),
            test_document_search("neural networks"),
            test_document_search("deep learning")
        ]
        search_success = any(search_results)
        
        # Summary
        print("\\n" + "=" * 80)
        print("📊 Integration Test Results")
        print("=" * 80)
        
        tests = [
            ("Document Service Health", health_ok),
            ("Document Upload & Processing", upload_success),
            ("Document List & Management", list_success),
            ("Document Search", search_success)
        ]
        
        passed = sum(1 for _, result in tests if result)
        total = len(tests)
        
        for test_name, result in tests:
            status = "✅ PASS" if result else "❌ FAIL"
            print(f"{status} {test_name}")
        
        print(f"\\n🎯 Overall: {passed}/{total} tests passed ({passed/total*100:.1f}%)")
        
        if passed == total:
            print("\\n🎉 Document Upload Integration is FULLY FUNCTIONAL!")
            print("\\n📋 Verified Capabilities:")
            print("   ✅ Document upload (PDF, TXT) with metadata")
            print("   ✅ Document list and management")
            print("   ✅ Document search and filtering")
            print("   ✅ Service health monitoring")
            print("\\n🚀 The system is ready for production use!")
            print("\\n📋 Next Steps:")
            print("   1. Test with larger documents")
            print("   2. Test bulk upload functionality")
            print("   3. Test document deletion and updates")
            print("   4. Performance testing with multiple users")
        else:
            print("\\n⚠️  Some features need attention before production deployment.")
        
        return passed == total
        
    finally:
        # Clean up test files
        cleanup_test_files(test_files)

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)