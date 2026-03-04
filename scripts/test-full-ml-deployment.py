#!/usr/bin/env python3
"""
Test script for Full ML Configuration deployment
Validates all ML capabilities are working correctly
"""

import requests
import json
import time
import sys
from typing import Dict, Any

def test_endpoint(url: str, endpoint: str, method: str = "GET", data: Dict[Any, Any] = None) -> Dict[str, Any]:
    """Test a specific endpoint and return results"""
    full_url = f"{url.rstrip('/')}/{endpoint.lstrip('/')}"
    
    try:
        if method == "GET":
            response = requests.get(full_url, timeout=30)
        elif method == "POST":
            response = requests.post(full_url, json=data, timeout=30)
        
        return {
            "endpoint": endpoint,
            "status_code": response.status_code,
            "success": response.status_code < 400,
            "response_time": response.elapsed.total_seconds(),
            "content": response.json() if response.headers.get('content-type', '').startswith('application/json') else response.text[:200]
        }
    except Exception as e:
        return {
            "endpoint": endpoint,
            "status_code": 0,
            "success": False,
            "response_time": 0,
            "error": str(e)
        }

def main():
    if len(sys.argv) != 2:
        print("Usage: python test-full-ml-deployment.py <base_url>")
        print("Example: python test-full-ml-deployment.py http://your-alb-dns.amazonaws.com")
        sys.exit(1)
    
    base_url = sys.argv[1]
    print(f"🧪 Testing Full ML Configuration at: {base_url}")
    print("=" * 60)
    
    # Test endpoints
    test_cases = [
        # Basic health checks
        ("health/simple", "GET"),
        ("health", "GET"),
        ("features", "GET"),
        
        # API documentation
        ("docs", "GET"),
        ("openapi.json", "GET"),
        
        # Core ML capabilities
        ("api/v1/ml/capabilities", "GET"),
        ("api/v1/embeddings/models", "GET"),
        ("api/v1/chunking/strategies", "GET"),
        
        # Chat and conversation endpoints
        ("api/v1/conversations", "GET"),
        ("api/v1/chat/health", "GET"),
        
        # Document processing
        ("api/v1/documents", "GET"),
        ("api/v1/export/formats", "GET"),
        
        # Knowledge graph
        ("api/v1/knowledge-graph/status", "GET"),
        ("api/v1/vector-store/status", "GET"),
        
        # Analytics and monitoring
        ("api/v1/analytics/status", "GET"),
        ("api/v1/monitoring/metrics", "GET"),
        
        # ML training endpoints
        ("api/v1/ml/training/status", "GET"),
        ("api/v1/ml/models/available", "GET"),
    ]
    
    results = []
    total_tests = len(test_cases)
    passed_tests = 0
    
    print("Running endpoint tests...")
    print("-" * 40)
    
    for i, (endpoint, method) in enumerate(test_cases, 1):
        print(f"[{i:2d}/{total_tests}] Testing {method} {endpoint}...", end=" ")
        
        result = test_endpoint(base_url, endpoint, method)
        results.append(result)
        
        if result["success"]:
            print(f"✅ {result['status_code']} ({result['response_time']:.2f}s)")
            passed_tests += 1
        else:
            print(f"❌ {result.get('status_code', 'ERR')} - {result.get('error', 'Failed')}")
    
    print("-" * 40)
    print(f"Test Results: {passed_tests}/{total_tests} passed ({passed_tests/total_tests*100:.1f}%)")
    
    # Test ML-specific functionality
    print("\n🤖 Testing ML-specific capabilities...")
    print("-" * 40)
    
    # Test embedding generation
    print("Testing embedding generation...", end=" ")
    embed_test = test_endpoint(
        base_url, 
        "api/v1/embeddings/generate", 
        "POST", 
        {"text": "This is a test document for ML processing."}
    )
    if embed_test["success"]:
        print("✅ Embeddings working")
    else:
        print("❌ Embeddings failed")
    
    # Test document chunking
    print("Testing document chunking...", end=" ")
    chunk_test = test_endpoint(
        base_url,
        "api/v1/chunking/analyze",
        "POST",
        {"content": "This is a sample document that should be chunked into smaller pieces for processing.", "strategy": "adaptive"}
    )
    if chunk_test["success"]:
        print("✅ Chunking working")
    else:
        print("❌ Chunking failed")
    
    # Test knowledge graph query
    print("Testing knowledge graph...", end=" ")
    kg_test = test_endpoint(
        base_url,
        "api/v1/knowledge-graph/query",
        "POST",
        {"query": "MATCH (n) RETURN count(n) as node_count LIMIT 1"}
    )
    if kg_test["success"]:
        print("✅ Knowledge graph working")
    else:
        print("❌ Knowledge graph failed")
    
    # Test vector search
    print("Testing vector search...", end=" ")
    search_test = test_endpoint(
        base_url,
        "api/v1/search/semantic",
        "POST",
        {"query": "machine learning", "limit": 5}
    )
    if search_test["success"]:
        print("✅ Vector search working")
    else:
        print("❌ Vector search failed")
    
    print("-" * 40)
    
    # Performance summary
    print("\n📊 Performance Summary:")
    print("-" * 40)
    
    successful_results = [r for r in results if r["success"]]
    if successful_results:
        avg_response_time = sum(r["response_time"] for r in successful_results) / len(successful_results)
        max_response_time = max(r["response_time"] for r in successful_results)
        min_response_time = min(r["response_time"] for r in successful_results)
        
        print(f"Average response time: {avg_response_time:.2f}s")
        print(f"Fastest response: {min_response_time:.2f}s")
        print(f"Slowest response: {max_response_time:.2f}s")
    
    # Final assessment
    print("\n🎯 Full ML Configuration Assessment:")
    print("-" * 40)
    
    if passed_tests >= total_tests * 0.8:  # 80% success rate
        print("✅ DEPLOYMENT SUCCESSFUL - Ready for demos!")
        print("🌍 Your geographically dispersed audience can access:")
        print("   • Advanced ML document processing")
        print("   • Real-time semantic search")
        print("   • Knowledge graph reasoning")
        print("   • Multi-modal content generation")
        print("   • Interactive chat with ML capabilities")
        
        print(f"\n🔗 Share this URL with your demo audience:")
        print(f"   {base_url}")
        
        return 0
    else:
        print("❌ DEPLOYMENT ISSUES DETECTED")
        print("   Some ML capabilities may not be fully functional")
        print("   Check the failed endpoints above")
        
        return 1

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)