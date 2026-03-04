#!/usr/bin/env python3
"""
Test AI Integration

This script tests the AI service integration to ensure all providers
are working correctly.
"""

import asyncio
import sys
import os
import json
from typing import Dict, Any

# Add the src directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

async def test_ai_service():
    """Test the AI service functionality."""
    try:
        from multimodal_librarian.services.ai_service import get_ai_service
        from multimodal_librarian.config import get_settings
        
        print("🤖 Testing AI Service Integration")
        print("=" * 50)
        
        # Get AI service
        ai_service = get_ai_service()
        
        # Check available providers
        providers = ai_service.get_available_providers()
        provider_status = ai_service.get_provider_status()
        
        print(f"📋 Available providers: {providers}")
        print(f"🔍 Provider status:")
        for provider, status in provider_status.items():
            status_icon = "✅" if status["available"] else "❌"
            print(f"  {status_icon} {provider}: {status['model']} (Primary: {status['is_primary']})")
        
        if not providers:
            print("❌ No AI providers available. Please check your API keys.")
            return False
        
        # Test message generation
        print(f"\n💬 Testing message generation...")
        test_messages = [
            {"role": "user", "content": "Hello! Please respond with a brief greeting to confirm you're working."}
        ]
        
        try:
            response = await ai_service.generate_response(
                messages=test_messages,
                temperature=0.7
            )
            
            print(f"✅ Response generated successfully!")
            print(f"   Provider: {response.provider}")
            print(f"   Model: {response.model}")
            print(f"   Tokens: {response.tokens_used}")
            print(f"   Time: {response.processing_time_ms}ms")
            print(f"   Response: {response.content[:100]}...")
            
        except Exception as e:
            print(f"❌ Failed to generate response: {e}")
            return False
        
        # Test embeddings if available
        print(f"\n🔢 Testing embedding generation...")
        try:
            embeddings = await ai_service.generate_embeddings(
                texts=["This is a test sentence for embedding generation."]
            )
            
            if embeddings and len(embeddings) > 0:
                print(f"✅ Embeddings generated successfully!")
                print(f"   Dimensions: {len(embeddings[0])}")
                print(f"   Sample values: {embeddings[0][:5]}...")
            else:
                print(f"❌ No embeddings generated")
                
        except Exception as e:
            print(f"⚠️  Embedding generation failed: {e}")
            print("   (This is expected if no embedding-capable providers are available)")
        
        print(f"\n🎉 AI service test completed successfully!")
        return True
        
    except ImportError as e:
        print(f"❌ Failed to import AI service: {e}")
        print("   Make sure you're running from the correct directory")
        return False
    except Exception as e:
        print(f"❌ AI service test failed: {e}")
        return False

async def test_chat_service():
    """Test the chat service functionality."""
    try:
        from multimodal_librarian.services.chat_service import get_chat_service
        
        print("\n💬 Testing Chat Service Integration")
        print("=" * 50)
        
        # Get chat service
        chat_service = get_chat_service()
        
        # Get chat status
        status = chat_service.get_chat_status()
        
        print(f"📊 Chat service status:")
        print(f"   Status: {status['status']}")
        print(f"   Active connections: {status['active_connections']}")
        print(f"   Active users: {status['active_users']}")
        print(f"   AI providers: {status['ai_providers']}")
        print(f"   Features: {list(status['features'].keys())}")
        
        print(f"\n✅ Chat service test completed successfully!")
        return True
        
    except ImportError as e:
        print(f"❌ Failed to import chat service: {e}")
        return False
    except Exception as e:
        print(f"❌ Chat service test failed: {e}")
        return False

async def test_database_migration():
    """Test if the chat messages table exists."""
    try:
        from multimodal_librarian.database.migrations.add_chat_messages import check_migration_status
        
        print("\n🗄️  Testing Database Migration")
        print("=" * 50)
        
        migration_applied = await check_migration_status()
        
        if migration_applied:
            print("✅ Chat messages table exists")
        else:
            print("❌ Chat messages table not found")
            print("   Run: python src/multimodal_librarian/database/migrations/add_chat_messages.py")
        
        return migration_applied
        
    except ImportError as e:
        print(f"❌ Failed to import migration check: {e}")
        return False
    except Exception as e:
        print(f"❌ Database migration test failed: {e}")
        return False

async def test_configuration():
    """Test configuration loading."""
    try:
        from multimodal_librarian.config import get_settings
        
        print("\n⚙️  Testing Configuration")
        print("=" * 50)
        
        settings = get_settings()
        
        # Check AI API keys
        ai_keys = {
            "Gemini": settings.gemini_api_key or settings.google_api_key,
            "OpenAI": settings.openai_api_key,
            "Anthropic": settings.anthropic_api_key
        }
        
        print("🔑 AI API Keys:")
        for provider, key in ai_keys.items():
            if key:
                print(f"   ✅ {provider}: {key[:10]}...")
            else:
                print(f"   ❌ {provider}: Not set")
        
        # Check database settings
        print(f"\n🗄️  Database Settings:")
        print(f"   Host: {settings.postgres_host}")
        print(f"   Port: {settings.postgres_port}")
        print(f"   Database: {settings.postgres_db}")
        print(f"   User: {settings.postgres_user}")
        
        return True
        
    except Exception as e:
        print(f"❌ Configuration test failed: {e}")
        return False

async def main():
    """Run all tests."""
    print("🧪 AI Integration Test Suite")
    print("=" * 60)
    
    tests = [
        ("Configuration", test_configuration),
        ("Database Migration", test_database_migration),
        ("AI Service", test_ai_service),
        ("Chat Service", test_chat_service)
    ]
    
    results = {}
    
    for test_name, test_func in tests:
        try:
            result = await test_func()
            results[test_name] = result
        except Exception as e:
            print(f"❌ {test_name} test crashed: {e}")
            results[test_name] = False
    
    # Summary
    print(f"\n📊 Test Results Summary")
    print("=" * 30)
    
    passed = 0
    total = len(results)
    
    for test_name, result in results.items():
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} {test_name}")
        if result:
            passed += 1
    
    print(f"\n🎯 Overall: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed! AI integration is ready.")
        return True
    else:
        print("⚠️  Some tests failed. Please check the configuration.")
        return False

if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)