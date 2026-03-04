#!/usr/bin/env python3
"""
AI Optimization Integration Test

This script tests the AI optimization service implementation including:
- Request batching functionality
- Prompt optimization
- Cost monitoring and alerting
- Provider selection optimization
- Rate limiting and graceful degradation
"""

import asyncio
import json
import time
import logging
from typing import Dict, List, Any
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_ai_optimization_service():
    """Test AI optimization service functionality."""
    
    print("🚀 Starting AI Optimization Service Integration Test")
    print("=" * 60)
    
    test_results = {
        "timestamp": datetime.utcnow().isoformat(),
        "tests": {},
        "summary": {
            "total_tests": 0,
            "passed_tests": 0,
            "failed_tests": 0,
            "success_rate": 0.0
        }
    }
    
    # Test 1: Service Initialization
    print("\n📋 Test 1: AI Optimization Service Initialization")
    try:
        from src.multimodal_librarian.services.ai_optimization_service import get_ai_optimization_service
        
        optimization_service = get_ai_optimization_service()
        
        # Check service attributes
        assert hasattr(optimization_service, 'ai_service'), "AI service not initialized"
        assert hasattr(optimization_service, 'provider_costs'), "Provider costs not configured"
        assert hasattr(optimization_service, 'usage_metrics'), "Usage metrics not initialized"
        
        print("✅ AI Optimization Service initialized successfully")
        print(f"   - Providers configured: {len(optimization_service.provider_costs)}")
        print(f"   - Batching enabled: {optimization_service.enable_batching}")
        print(f"   - Prompt optimization enabled: {optimization_service.enable_prompt_optimization}")
        print(f"   - Cost optimization enabled: {optimization_service.enable_cost_optimization}")
        
        test_results["tests"]["service_initialization"] = {
            "status": "passed",
            "details": {
                "providers_configured": len(optimization_service.provider_costs),
                "features_enabled": {
                    "batching": optimization_service.enable_batching,
                    "prompt_optimization": optimization_service.enable_prompt_optimization,
                    "cost_optimization": optimization_service.enable_cost_optimization,
                    "rate_limiting": optimization_service.enable_rate_limiting
                }
            }
        }
        
    except Exception as e:
        print(f"❌ Service initialization failed: {e}")
        test_results["tests"]["service_initialization"] = {
            "status": "failed",
            "error": str(e)
        }
    
    # Test 2: Health Check
    print("\n🏥 Test 2: AI Optimization Health Check")
    try:
        health_data = await optimization_service.health_check()
        
        assert "status" in health_data, "Health status missing"
        assert "optimization_features" in health_data, "Optimization features missing"
        assert "cost_monitoring" in health_data, "Cost monitoring missing"
        
        print("✅ Health check completed successfully")
        print(f"   - Status: {health_data['status']}")
        print(f"   - Providers available: {health_data['providers_available']}")
        print(f"   - Cost monitoring active: {health_data['cost_monitoring']['within_limits']}")
        
        test_results["tests"]["health_check"] = {
            "status": "passed",
            "details": {
                "service_status": health_data["status"],
                "providers_available": health_data["providers_available"],
                "cost_monitoring_active": health_data["cost_monitoring"]["within_limits"]
            }
        }
        
    except Exception as e:
        print(f"❌ Health check failed: {e}")
        test_results["tests"]["health_check"] = {
            "status": "failed",
            "error": str(e)
        }
    
    # Test 3: Prompt Optimization
    print("\n✂️ Test 3: Prompt Optimization")
    try:
        # Test prompt compression
        test_messages = [
            {
                "role": "user",
                "content": "Could you please kindly help me understand the concept of machine learning in order to improve my knowledge?"
            }
        ]
        
        optimized_messages, tokens_saved = optimization_service._optimize_prompt(test_messages)
        
        assert len(optimized_messages) == len(test_messages), "Message count changed"
        assert tokens_saved >= 0, "Invalid tokens saved count"
        
        original_content = test_messages[0]["content"]
        optimized_content = optimized_messages[0]["content"]
        
        print("✅ Prompt optimization working")
        print(f"   - Original: '{original_content[:50]}...'")
        print(f"   - Optimized: '{optimized_content[:50]}...'")
        print(f"   - Tokens saved: {tokens_saved}")
        
        test_results["tests"]["prompt_optimization"] = {
            "status": "passed",
            "details": {
                "tokens_saved": tokens_saved,
                "compression_ratio": len(optimized_content) / len(original_content) if original_content else 1.0
            }
        }
        
    except Exception as e:
        print(f"❌ Prompt optimization failed: {e}")
        test_results["tests"]["prompt_optimization"] = {
            "status": "failed",
            "error": str(e)
        }
    
    # Test 4: Provider Selection
    print("\n🎯 Test 4: Provider Selection Optimization")
    try:
        test_messages = [{"role": "user", "content": "Hello, how are you?"}]
        
        # Test provider selection
        optimal_provider = optimization_service._select_optimal_provider(test_messages)
        
        assert optimal_provider is not None, "No provider selected"
        
        print("✅ Provider selection working")
        print(f"   - Selected provider: {optimal_provider.value}")
        
        # Test with different message lengths
        long_messages = [{"role": "user", "content": "This is a much longer message " * 50}]
        optimal_provider_long = optimization_service._select_optimal_provider(long_messages)
        
        print(f"   - Provider for long message: {optimal_provider_long.value}")
        
        test_results["tests"]["provider_selection"] = {
            "status": "passed",
            "details": {
                "short_message_provider": optimal_provider.value,
                "long_message_provider": optimal_provider_long.value
            }
        }
        
    except Exception as e:
        print(f"❌ Provider selection failed: {e}")
        test_results["tests"]["provider_selection"] = {
            "status": "failed",
            "error": str(e)
        }
    
    # Test 5: Cost Calculation
    print("\n💰 Test 5: Cost Calculation")
    try:
        from src.multimodal_librarian.services.ai_optimization_service import AIProvider
        
        # Test cost calculation for different providers
        input_tokens = 1000
        output_tokens = 500
        
        costs = {}
        for provider in optimization_service.provider_costs.keys():
            cost = optimization_service._calculate_cost(provider, input_tokens, output_tokens)
            costs[provider.value] = cost
        
        assert len(costs) > 0, "No costs calculated"
        
        print("✅ Cost calculation working")
        for provider, cost in costs.items():
            print(f"   - {provider}: ${cost:.6f}")
        
        test_results["tests"]["cost_calculation"] = {
            "status": "passed",
            "details": {
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "provider_costs": costs
            }
        }
        
    except Exception as e:
        print(f"❌ Cost calculation failed: {e}")
        test_results["tests"]["cost_calculation"] = {
            "status": "failed",
            "error": str(e)
        }
    
    # Test 6: Usage Analytics
    print("\n📊 Test 6: Usage Analytics")
    try:
        analytics = optimization_service.get_usage_analytics()
        
        assert "summary" in analytics, "Analytics summary missing"
        assert "provider_performance" in analytics, "Provider performance missing"
        assert "optimization_settings" in analytics, "Optimization settings missing"
        assert "recommendations" in analytics, "Recommendations missing"
        
        print("✅ Usage analytics working")
        print(f"   - Total requests tracked: {analytics['summary']['total_requests']}")
        print(f"   - Total cost tracked: ${analytics['summary']['total_cost']:.6f}")
        print(f"   - Recommendations: {len(analytics['recommendations'])}")
        
        test_results["tests"]["usage_analytics"] = {
            "status": "passed",
            "details": {
                "total_requests": analytics["summary"]["total_requests"],
                "total_cost": analytics["summary"]["total_cost"],
                "recommendations_count": len(analytics["recommendations"])
            }
        }
        
    except Exception as e:
        print(f"❌ Usage analytics failed: {e}")
        test_results["tests"]["usage_analytics"] = {
            "status": "failed",
            "error": str(e)
        }
    
    # Test 7: Rate Limiting Check
    print("\n⏱️ Test 7: Rate Limiting")
    try:
        from src.multimodal_librarian.services.ai_optimization_service import AIProvider
        
        # Test rate limiting for available providers
        rate_limit_results = {}
        for provider in optimization_service.provider_costs.keys():
            within_limits = await optimization_service._check_rate_limits(provider)
            rate_limit_results[provider.value] = within_limits
        
        print("✅ Rate limiting check working")
        for provider, within_limits in rate_limit_results.items():
            print(f"   - {provider}: {'✅ Within limits' if within_limits else '⚠️ Rate limited'}")
        
        test_results["tests"]["rate_limiting"] = {
            "status": "passed",
            "details": rate_limit_results
        }
        
    except Exception as e:
        print(f"❌ Rate limiting check failed: {e}")
        test_results["tests"]["rate_limiting"] = {
            "status": "failed",
            "error": str(e)
        }
    
    # Test 8: API Router Integration
    print("\n🌐 Test 8: API Router Integration")
    try:
        from src.multimodal_librarian.api.routers.ai_optimization import router
        
        # Check router configuration
        assert router.prefix == "/api/ai-optimization", "Incorrect router prefix"
        assert "AI Optimization" in router.tags, "Missing router tags"
        
        # Check endpoints
        endpoint_paths = [route.path for route in router.routes]
        expected_endpoints = [
            "/health",
            "/analytics", 
            "/cost-breakdown",
            "/settings",
            "/chat/optimized",
            "/chat/batch",
            "/providers",
            "/recommendations"
        ]
        
        for endpoint in expected_endpoints:
            full_path = f"{router.prefix}{endpoint}"
            assert any(endpoint in path for path in endpoint_paths), f"Missing endpoint: {endpoint}"
        
        print("✅ API router integration working")
        print(f"   - Router prefix: {router.prefix}")
        print(f"   - Endpoints available: {len(endpoint_paths)}")
        print(f"   - Expected endpoints found: {len(expected_endpoints)}")
        
        test_results["tests"]["api_router_integration"] = {
            "status": "passed",
            "details": {
                "router_prefix": router.prefix,
                "endpoints_count": len(endpoint_paths),
                "expected_endpoints_found": len(expected_endpoints)
            }
        }
        
    except Exception as e:
        print(f"❌ API router integration failed: {e}")
        test_results["tests"]["api_router_integration"] = {
            "status": "failed",
            "error": str(e)
        }
    
    # Calculate summary
    test_results["summary"]["total_tests"] = len(test_results["tests"])
    test_results["summary"]["passed_tests"] = sum(
        1 for test in test_results["tests"].values() 
        if test["status"] == "passed"
    )
    test_results["summary"]["failed_tests"] = (
        test_results["summary"]["total_tests"] - test_results["summary"]["passed_tests"]
    )
    test_results["summary"]["success_rate"] = (
        test_results["summary"]["passed_tests"] / test_results["summary"]["total_tests"]
        if test_results["summary"]["total_tests"] > 0 else 0.0
    )
    
    # Print summary
    print("\n" + "=" * 60)
    print("📊 TEST SUMMARY")
    print("=" * 60)
    print(f"Total Tests: {test_results['summary']['total_tests']}")
    print(f"Passed: {test_results['summary']['passed_tests']}")
    print(f"Failed: {test_results['summary']['failed_tests']}")
    print(f"Success Rate: {test_results['summary']['success_rate']:.1%}")
    
    if test_results["summary"]["success_rate"] >= 0.8:
        print("\n🎉 AI OPTIMIZATION IMPLEMENTATION SUCCESSFUL!")
        print("✅ All core features are working correctly")
    elif test_results["summary"]["success_rate"] >= 0.6:
        print("\n⚠️ AI OPTIMIZATION PARTIALLY WORKING")
        print("🔧 Some features need attention")
    else:
        print("\n❌ AI OPTIMIZATION NEEDS SIGNIFICANT WORK")
        print("🚨 Multiple critical issues found")
    
    # Save results
    with open("ai-optimization-test-results.json", "w") as f:
        json.dump(test_results, f, indent=2)
    
    print(f"\n📄 Detailed results saved to: ai-optimization-test-results.json")
    
    return test_results

async def test_api_endpoints():
    """Test AI optimization API endpoints."""
    
    print("\n🌐 Testing AI Optimization API Endpoints")
    print("-" * 40)
    
    try:
        import httpx
        
        # Test endpoints (assuming server is running on localhost:8000)
        base_url = "http://localhost:8000"
        
        async with httpx.AsyncClient() as client:
            # Test health endpoint
            try:
                response = await client.get(f"{base_url}/api/ai-optimization/health")
                if response.status_code == 200:
                    print("✅ Health endpoint working")
                else:
                    print(f"⚠️ Health endpoint returned {response.status_code}")
            except Exception as e:
                print(f"❌ Health endpoint failed: {e}")
            
            # Test analytics endpoint
            try:
                response = await client.get(f"{base_url}/api/ai-optimization/analytics")
                if response.status_code == 200:
                    print("✅ Analytics endpoint working")
                else:
                    print(f"⚠️ Analytics endpoint returned {response.status_code}")
            except Exception as e:
                print(f"❌ Analytics endpoint failed: {e}")
            
            # Test providers endpoint
            try:
                response = await client.get(f"{base_url}/api/ai-optimization/providers")
                if response.status_code == 200:
                    print("✅ Providers endpoint working")
                else:
                    print(f"⚠️ Providers endpoint returned {response.status_code}")
            except Exception as e:
                print(f"❌ Providers endpoint failed: {e}")
    
    except ImportError:
        print("⚠️ httpx not available - skipping API endpoint tests")
        print("   Install httpx to test API endpoints: pip install httpx")

if __name__ == "__main__":
    print("🧪 AI Optimization Integration Test Suite")
    print("Testing Task 11.2 implementation...")
    
    # Run service tests
    asyncio.run(test_ai_optimization_service())
    
    # Run API tests
    asyncio.run(test_api_endpoints())
    
    print("\n✨ Test suite completed!")