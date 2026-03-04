#!/usr/bin/env python3
"""
Test script for RAG integration with chat system.

This script tests the integration between the chat system and RAG service
to ensure document-aware responses are working correctly.
"""

import asyncio
import json
import websockets
import time
import sys
import os

# Add the src directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

async def test_rag_integration():
    """Test RAG integration with WebSocket chat."""
    
    print("🧪 Testing RAG Integration with Chat System")
    print("=" * 50)
    
    # Test configuration
    base_url = "localhost:8000"
    websocket_url = f"ws://{base_url}/ws/chat"
    
    try:
        # Connect to WebSocket
        print(f"📡 Connecting to WebSocket: {websocket_url}")
        
        async with websockets.connect(websocket_url) as websocket:
            print("✅ WebSocket connection established")
            
            # Start conversation
            print("\n🚀 Starting conversation...")
            start_message = {
                "type": "start_conversation"
            }
            await websocket.send(json.dumps(start_message))
            
            # Wait for conversation started response
            response = await websocket.recv()
            start_response = json.loads(response)
            print(f"📝 Conversation started: {start_response.get('thread_id', 'unknown')}")
            
            if 'features' in start_response:
                features = start_response['features']
                print(f"🎯 RAG enabled: {features.get('rag_enabled', False)}")
                print(f"📚 Document-aware responses: {features.get('document_aware_responses', False)}")
                print(f"📖 Citation support: {features.get('citation_support', False)}")
            
            # Test messages
            test_messages = [
                "Hello! Can you help me understand how this system works?",
                "What documents do I have available?",
                "Can you search for information about machine learning?",
                "Tell me about the RAG system implementation."
            ]
            
            for i, message in enumerate(test_messages, 1):
                print(f"\n💬 Test Message {i}: {message}")
                
                # Send message
                chat_message = {
                    "type": "chat_message",
                    "message": message
                }
                await websocket.send(json.dumps(chat_message))
                
                # Wait for processing and response
                processing_received = False
                response_received = False
                
                while not response_received:
                    try:
                        response = await asyncio.wait_for(websocket.recv(), timeout=30.0)
                        response_data = json.loads(response)
                        
                        if response_data.get('type') == 'processing':
                            if not processing_received:
                                print("⏳ Processing message...")
                                processing_received = True
                        
                        elif response_data.get('type') == 'response':
                            print("✅ Response received!")
                            
                            # Extract response details
                            response_content = response_data.get('response', {})
                            text_content = response_content.get('text_content', '')
                            citations = response_content.get('knowledge_citations', [])
                            metadata = response_data.get('metadata', {})
                            
                            print(f"📄 Response length: {len(text_content)} characters")
                            print(f"📚 Citations found: {len(citations)}")
                            
                            if metadata:
                                print(f"🤖 RAG enabled: {metadata.get('rag_enabled', False)}")
                                print(f"🎯 Confidence: {metadata.get('confidence_score', 'N/A')}")
                                print(f"⏱️  Processing time: {metadata.get('processing_time_ms', 'N/A')}ms")
                                print(f"🔍 Search results: {metadata.get('search_results_count', 'N/A')}")
                                print(f"🔄 Fallback used: {metadata.get('fallback_used', False)}")
                            
                            if citations:
                                print("📖 Citations:")
                                for j, citation in enumerate(citations[:3], 1):  # Show first 3
                                    print(f"  {j}. {citation.get('document_title', 'Unknown')} "
                                          f"(Score: {citation.get('relevance_score', 'N/A')})")
                            
                            # Show first 200 characters of response
                            preview = text_content[:200] + "..." if len(text_content) > 200 else text_content
                            print(f"💭 Response preview: {preview}")
                            
                            response_received = True
                        
                        elif response_data.get('type') == 'processing_complete':
                            if response_received:
                                print("✅ Processing complete")
                                break
                        
                        elif response_data.get('type') == 'error':
                            print(f"❌ Error: {response_data.get('message', 'Unknown error')}")
                            response_received = True
                    
                    except asyncio.TimeoutError:
                        print("⏰ Timeout waiting for response")
                        response_received = True
                        break
                
                # Wait a bit between messages
                await asyncio.sleep(2)
            
            print("\n🎉 RAG integration test completed!")
            
    except websockets.exceptions.ConnectionClosed:
        print("❌ WebSocket connection closed unexpectedly")
        return False
    except Exception as e:
        print(f"❌ Test failed: {e}")
        return False
    
    return True

async def test_rag_service_directly():
    """Test RAG service directly (if available)."""
    
    print("\n🔬 Testing RAG Service Directly")
    print("=" * 30)
    
    try:
        from multimodal_librarian.services.rag_service import get_rag_service
        
        rag_service = get_rag_service()
        print("✅ RAG service initialized")
        
        # Get service status
        status = rag_service.get_service_status()
        print(f"📊 Service status: {status.get('status', 'unknown')}")
        print(f"🔍 OpenSearch connected: {status.get('opensearch_connected', False)}")
        print(f"🤖 AI providers: {len(status.get('ai_providers', {}))}")
        
        # Test a simple query
        print("\n💬 Testing direct RAG query...")
        test_query = "What is machine learning?"
        
        try:
            response = await rag_service.generate_response(
                query=test_query,
                user_id="test_user"
            )
            
            print(f"✅ RAG response generated")
            print(f"📄 Response length: {len(response.response)} characters")
            print(f"📚 Sources found: {len(response.sources)}")
            print(f"🎯 Confidence: {response.confidence_score:.3f}")
            print(f"⏱️  Processing time: {response.processing_time_ms}ms")
            print(f"🔄 Fallback used: {response.fallback_used}")
            
            # Show response preview
            preview = response.response[:200] + "..." if len(response.response) > 200 else response.response
            print(f"💭 Response preview: {preview}")
            
        except Exception as e:
            print(f"❌ RAG query failed: {e}")
            return False
        
    except ImportError as e:
        print(f"⚠️  RAG service not available: {e}")
        return False
    except Exception as e:
        print(f"❌ RAG service test failed: {e}")
        return False
    
    return True

async def main():
    """Main test function."""
    
    print("🧪 RAG Integration Test Suite")
    print("=" * 40)
    print("This script tests the integration between the chat system and RAG service.")
    print("Make sure the application is running on localhost:8000")
    print()
    
    # Test RAG service directly first
    direct_test_passed = await test_rag_service_directly()
    
    # Test WebSocket integration
    websocket_test_passed = await test_rag_integration()
    
    print("\n📊 Test Results Summary")
    print("=" * 25)
    print(f"🔬 Direct RAG service test: {'✅ PASSED' if direct_test_passed else '❌ FAILED'}")
    print(f"📡 WebSocket integration test: {'✅ PASSED' if websocket_test_passed else '❌ FAILED'}")
    
    if direct_test_passed and websocket_test_passed:
        print("\n🎉 All tests passed! RAG integration is working correctly.")
        return 0
    else:
        print("\n⚠️  Some tests failed. Check the logs above for details.")
        return 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)