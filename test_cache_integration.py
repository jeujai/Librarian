#!/usr/bin/env python3
"""
Test Cache Integration

This script tests the cache integration functionality to ensure all components
are working correctly with the new caching layers.
"""

import asyncio
import sys
import time
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

async def test_cache_service():
    """Test basic cache service functionality."""
    print("🔧 Testing Cache Service...")
    
    try:
        from multimodal_librarian.services.cache_service import get_cache_service, CacheType
        
        # Get cache service
        cache_service = await get_cache_service()
        
        # Test connection
        health = await cache_service.health_check()
        print(f"   Cache Health: {health['status']}")
        
        if health['status'] == 'healthy':
            # Test basic operations
            test_key = "test_key"
            test_value = {"message": "Hello Cache!", "timestamp": time.time()}
            
            # Set value
            success = await cache_service.set(CacheType.AI_RESPONSE, test_key, test_value, ttl=60)
            print(f"   Cache Set: {'✅' if success else '❌'}")
            
            # Get value
            retrieved = await cache_service.get(CacheType.AI_RESPONSE, test_key)
            print(f"   Cache Get: {'✅' if retrieved == test_value else '❌'}")
            
            # Delete value
            deleted = await cache_service.delete(CacheType.AI_RESPONSE, test_key)
            print(f"   Cache Delete: {'✅' if deleted else '❌'}")
            
            # Get stats
            stats = await cache_service.get_stats()
            print(f"   Cache Stats: {stats.total_entries} entries, {stats.memory_usage_mb:.1f}MB")
            
        return health['status'] == 'healthy'
        
    except Exception as e:
        print(f"   ❌ Cache Service Error: {e}")
        return False

async def test_cached_ai_service():
    """Test cached AI service functionality."""
    print("🤖 Testing Cached AI Service...")
    
    try:
        from multimodal_librarian.services.ai_service_cached import get_cached_ai_service
        
        # Get cached AI service
        ai_service = get_cached_ai_service()
        
        # Test embedding caching
        test_texts = ["Hello world", "This is a test"]
        
        # First call (should miss cache)
        start_time = time.time()
        embeddings1 = await ai_service.generate_embeddings(test_texts)
        first_call_time = time.time() - start_time
        
        # Second call (should hit cache)
        start_time = time.time()
        embeddings2 = await ai_service.generate_embeddings(test_texts)
        second_call_time = time.time() - start_time
        
        # Verify embeddings are the same
        embeddings_match = embeddings1 == embeddings2
        cache_faster = second_call_time < first_call_time
        
        print(f"   Embeddings Match: {'✅' if embeddings_match else '❌'}")
        print(f"   Cache Faster: {'✅' if cache_faster else '❌'} ({first_call_time:.3f}s vs {second_call_time:.3f}s)")
        
        # Test response caching
        messages = [{"role": "user", "content": "Say hello"}]
        
        # First call
        start_time = time.time()
        response1 = await ai_service.generate_response(messages, temperature=0.0)
        first_response_time = time.time() - start_time
        
        # Second call (should hit cache)
        start_time = time.time()
        response2 = await ai_service.generate_response(messages, temperature=0.0)
        second_response_time = time.time() - start_time
        
        responses_match = response1.content == response2.content
        response_cache_faster = second_response_time < first_response_time
        
        print(f"   Response Match: {'✅' if responses_match else '❌'}")
        print(f"   Response Cache Faster: {'✅' if response_cache_faster else '❌'} ({first_response_time:.3f}s vs {second_response_time:.3f}s)")
        
        # Get cache stats
        cache_stats = ai_service.get_cache_stats()
        print(f"   AI Cache Stats: {cache_stats['performance']['total_cache_hits']} hits, {cache_stats['performance']['overall_hit_rate']:.2f} hit rate")
        
        return embeddings_match and responses_match
        
    except Exception as e:
        print(f"   ❌ Cached AI Service Error: {e}")
        return False

async def test_cached_rag_service():
    """Test cached RAG service functionality."""
    print("📚 Testing Cached RAG Service...")
    
    try:
        from multimodal_librarian.services.rag_service_cached import get_cached_rag_service
        
        # Get cached RAG service
        rag_service = get_cached_rag_service()
        
        # Test service status
        status = await rag_service.get_enhanced_service_status()
        print(f"   RAG Service Status: {status.get('status', 'unknown')}")
        
        # Test knowledge graph insights caching
        test_query = "What is artificial intelligence?"
        
        # First call
        start_time = time.time()
        insights1 = await rag_service.get_knowledge_graph_insights(test_query)
        first_kg_time = time.time() - start_time
        
        # Second call (should hit cache)
        start_time = time.time()
        insights2 = await rag_service.get_knowledge_graph_insights(test_query)
        second_kg_time = time.time() - start_time
        
        kg_cache_faster = second_kg_time < first_kg_time
        print(f"   KG Cache Faster: {'✅' if kg_cache_faster else '❌'} ({first_kg_time:.3f}s vs {second_kg_time:.3f}s)")
        
        # Get cache stats
        cache_stats = rag_service.get_cache_stats()
        print(f"   RAG Cache Stats: {cache_stats['overall_performance']['overall_hit_rate']:.2f} hit rate")
        
        return True
        
    except Exception as e:
        print(f"   ❌ Cached RAG Service Error: {e}")
        return False

async def test_conversation_cache_service():
    """Test conversation cache service functionality."""
    print("💬 Testing Conversation Cache Service...")
    
    try:
        from multimodal_librarian.services.conversation_cache_service import get_conversation_cache_service
        
        # Get conversation cache service
        conv_service = get_conversation_cache_service()
        
        # Test health check
        health = await conv_service.health_check()
        print(f"   Conversation Cache Health: {health['status']}")
        
        # Test session data caching
        test_user_id = "test_user_123"
        test_session_data = {
            "preferences": {"theme": "dark", "language": "en"},
            "last_activity": time.time()
        }
        
        # Set session data
        success = await conv_service.set_session_data(test_user_id, test_session_data)
        print(f"   Session Data Set: {'✅' if success else '❌'}")
        
        # Get session data
        retrieved_data = await conv_service.get_session_data(test_user_id)
        data_matches = retrieved_data and retrieved_data["preferences"] == test_session_data["preferences"]
        print(f"   Session Data Retrieved: {'✅' if data_matches else '❌'}")
        
        # Get cache stats
        cache_stats = conv_service.get_cache_stats()
        print(f"   Conversation Cache Stats: {cache_stats['performance']['overall_hit_rate']:.2f} hit rate")
        
        return success and data_matches
        
    except Exception as e:
        print(f"   ❌ Conversation Cache Service Error: {e}")
        return False

async def test_cache_management_api():
    """Test cache management API endpoints."""
    print("🔧 Testing Cache Management API...")
    
    try:
        # Import the router to ensure it loads correctly
        from multimodal_librarian.api.routers.cache_management import router
        print(f"   Cache Management Router: ✅ Loaded with {len(router.routes)} routes")
        
        # Test that the router has expected endpoints
        route_paths = [route.path for route in router.routes]
        expected_paths = ["/health", "/stats", "/clear", "/warm", "/performance", "/config", "/optimize"]
        
        missing_paths = [path for path in expected_paths if not any(path in route_path for route_path in route_paths)]
        
        if not missing_paths:
            print("   All Expected Endpoints: ✅")
            return True
        else:
            print(f"   Missing Endpoints: ❌ {missing_paths}")
            return False
        
    except Exception as e:
        print(f"   ❌ Cache Management API Error: {e}")
        return False

async def main():
    """Run all cache integration tests."""
    print("🚀 Starting Cache Integration Tests\n")
    
    tests = [
        ("Cache Service", test_cache_service),
        ("Cached AI Service", test_cached_ai_service),
        ("Cached RAG Service", test_cached_rag_service),
        ("Conversation Cache Service", test_conversation_cache_service),
        ("Cache Management API", test_cache_management_api),
    ]
    
    results = []
    
    for test_name, test_func in tests:
        try:
            result = await test_func()
            results.append((test_name, result))
            print()
        except Exception as e:
            print(f"   ❌ {test_name} failed with error: {e}\n")
            results.append((test_name, False))
    
    # Summary
    print("📊 Test Results Summary:")
    print("=" * 50)
    
    passed = 0
    total = len(results)
    
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{test_name:.<30} {status}")
        if result:
            passed += 1
    
    print("=" * 50)
    print(f"Overall: {passed}/{total} tests passed ({passed/total*100:.1f}%)")
    
    if passed == total:
        print("🎉 All cache integration tests passed!")
        return 0
    else:
        print("⚠️  Some cache integration tests failed.")
        return 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)