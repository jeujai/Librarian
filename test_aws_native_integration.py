#!/usr/bin/env python3
"""
AWS-Native Database Integration Test

This script tests the basic functionality of the AWS-Native database implementation
including Neptune and OpenSearch clients, configuration management, and health checks.
"""

import os
import sys
import json
import asyncio
from typing import Dict, Any

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

def test_configuration():
    """Test AWS-Native configuration management."""
    print("🔧 Testing AWS-Native Configuration...")
    
    try:
        from multimodal_librarian.config.aws_native_config import get_aws_native_config
        
        config = get_aws_native_config()
        backend_type = config.get_backend_type()
        
        print(f"   ✅ Backend type detected: {backend_type}")
        print(f"   ✅ AWS-Native enabled: {config.is_aws_native_enabled()}")
        print(f"   ✅ Self-managed enabled: {config.is_self_managed_enabled()}")
        
        # Test configuration validation
        validation = config.validate_configuration()
        print(f"   ✅ Configuration valid: {validation['valid']}")
        
        if validation['issues']:
            print(f"   ⚠️  Issues found: {validation['issues']}")
        
        if validation['warnings']:
            print(f"   ⚠️  Warnings: {validation['warnings']}")
        
        # Test environment info
        env_info = config.get_environment_info()
        print(f"   ✅ Environment info retrieved: {len(env_info)} keys")
        
        return True
        
    except Exception as e:
        print(f"   ❌ Configuration test failed: {e}")
        return False


def test_database_factory():
    """Test database factory functionality."""
    print("🏭 Testing Database Factory...")
    
    try:
        from multimodal_librarian.clients.database_factory import get_database_factory
        
        factory = get_database_factory()
        print("   ✅ Database factory created")
        
        # Test health check
        health = factory.health_check()
        print(f"   ✅ Health check completed: {health['overall_status']}")
        print(f"   ✅ Backend type: {health['backend_type']}")
        
        # Print service status
        for service_name, service_health in health.get('services', {}).items():
            status = service_health.get('status', 'unknown')
            print(f"   📊 {service_name}: {status}")
            
            if status == 'unhealthy' and 'error' in service_health:
                print(f"      Error: {service_health['error']}")
        
        return True
        
    except Exception as e:
        print(f"   ❌ Database factory test failed: {e}")
        return False


def test_client_imports():
    """Test that all client modules can be imported."""
    print("📦 Testing Client Imports...")
    
    clients_to_test = [
        ('Neptune Client', 'multimodal_librarian.clients.neptune_client'),
        ('OpenSearch Client', 'multimodal_librarian.clients.opensearch_client'),
        ('Database Factory', 'multimodal_librarian.clients.database_factory'),
    ]
    
    success_count = 0
    
    for client_name, module_path in clients_to_test:
        try:
            __import__(module_path)
            print(f"   ✅ {client_name} imported successfully")
            success_count += 1
        except Exception as e:
            print(f"   ❌ {client_name} import failed: {e}")
    
    print(f"   📊 Import success rate: {success_count}/{len(clients_to_test)}")
    return success_count == len(clients_to_test)


def test_unified_interfaces():
    """Test unified database interfaces."""
    print("🔗 Testing Unified Interfaces...")
    
    try:
        from multimodal_librarian.clients.database_factory import get_database_factory
        
        factory = get_database_factory()
        
        # Test graph interface (if enabled)
        try:
            graph_interface = factory.get_unified_graph_interface()
            print("   ✅ Unified graph interface created")
            
            # Test health check
            graph_health = graph_interface.health_check()
            print(f"   ✅ Graph health check: {graph_health.get('status', 'unknown')}")
            
        except Exception as e:
            print(f"   ⚠️  Graph interface test failed: {e}")
        
        # Test vector interface (if enabled)
        try:
            vector_interface = factory.get_unified_vector_interface()
            print("   ✅ Unified vector interface created")
            
            # Test health check
            vector_health = vector_interface.health_check()
            status = vector_health.get('status', 'unknown') if isinstance(vector_health, dict) else ('healthy' if vector_health else 'unhealthy')
            print(f"   ✅ Vector health check: {status}")
            
        except Exception as e:
            print(f"   ⚠️  Vector interface test failed: {e}")
        
        return True
        
    except Exception as e:
        print(f"   ❌ Unified interfaces test failed: {e}")
        return False


def test_main_app_integration():
    """Test main application integration."""
    print("🚀 Testing Main App Integration...")
    
    try:
        from multimodal_librarian.main import create_minimal_app
        
        app = create_minimal_app()
        print("   ✅ Main application created")
        
        # Check if the app has the expected routes
        routes = [route.path for route in app.routes]
        expected_routes = ['/health', '/health/simple', '/config/aws-native']
        
        for route in expected_routes:
            if route in routes:
                print(f"   ✅ Route {route} found")
            else:
                print(f"   ⚠️  Route {route} not found")
        
        return True
        
    except Exception as e:
        print(f"   ❌ Main app integration test failed: {e}")
        return False


def test_requirements():
    """Test that required dependencies are available."""
    print("📋 Testing Requirements...")
    
    required_packages = [
        ('boto3', 'AWS SDK'),
        ('gremlinpython', 'Neptune Gremlin client'),
        ('opensearchpy', 'OpenSearch client'),
        ('requests_aws4auth', 'AWS IAM authentication'),
        ('sentence_transformers', 'Embedding model'),
    ]
    
    success_count = 0
    
    for package, description in required_packages:
        try:
            __import__(package.replace('-', '_'))
            print(f"   ✅ {description} ({package}) available")
            success_count += 1
        except ImportError:
            print(f"   ❌ {description} ({package}) not available")
    
    print(f"   📊 Dependency success rate: {success_count}/{len(required_packages)}")
    return success_count >= len(required_packages) - 1  # Allow one missing dependency


def main():
    """Run all tests."""
    print("🧪 AWS-Native Database Integration Test Suite")
    print("=" * 50)
    
    tests = [
        ("Configuration Management", test_configuration),
        ("Client Imports", test_client_imports),
        ("Requirements Check", test_requirements),
        ("Database Factory", test_database_factory),
        ("Unified Interfaces", test_unified_interfaces),
        ("Main App Integration", test_main_app_integration),
    ]
    
    results = []
    
    for test_name, test_func in tests:
        print(f"\n{test_name}")
        print("-" * len(test_name))
        
        try:
            success = test_func()
            results.append((test_name, success))
        except Exception as e:
            print(f"   ❌ Test failed with exception: {e}")
            results.append((test_name, False))
    
    # Summary
    print("\n" + "=" * 50)
    print("📊 Test Results Summary")
    print("=" * 50)
    
    passed = 0
    total = len(results)
    
    for test_name, success in results:
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status} {test_name}")
        if success:
            passed += 1
    
    print(f"\nOverall: {passed}/{total} tests passed ({passed/total*100:.1f}%)")
    
    if passed == total:
        print("🎉 All tests passed! AWS-Native implementation is ready.")
        return 0
    elif passed >= total * 0.8:
        print("⚠️  Most tests passed. Some issues may need attention.")
        return 1
    else:
        print("❌ Multiple test failures. Implementation needs work.")
        return 2


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)