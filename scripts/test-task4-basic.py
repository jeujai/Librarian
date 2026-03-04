#!/usr/bin/env python3

"""
Basic test script for Task 4: Document Processing Pipeline Implementation.

This script validates the core Celery integration without importing problematic models.
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

def test_celery_import():
    """Test Celery service import."""
    try:
        from multimodal_librarian.services.celery_service import celery_app, CeleryService
        print("✅ Celery service imported successfully")
        return True
    except Exception as e:
        print(f"❌ Celery service import failed: {e}")
        return False

def test_processing_service_import():
    """Test Processing service import."""
    try:
        from multimodal_librarian.services.processing_service import ProcessingService
        print("✅ Processing service imported successfully")
        return True
    except Exception as e:
        print(f"❌ Processing service import failed: {e}")
        return False

def test_redis_connection():
    """Test Redis connection."""
    try:
        import redis
        redis_client = redis.Redis.from_url("redis://localhost:6379/0")
        redis_client.ping()
        print("✅ Redis connection successful")
        return True
    except Exception as e:
        print(f"❌ Redis connection failed: {e}")
        return False

def test_celery_configuration():
    """Test Celery configuration."""
    try:
        from multimodal_librarian.services.celery_service import celery_app
        
        # Check broker URL
        broker_url = celery_app.conf.broker_url
        if "redis://" not in broker_url:
            print(f"❌ Invalid broker URL: {broker_url}")
            return False
        
        # Check task routes
        task_routes = celery_app.conf.task_routes
        expected_tasks = [
            'process_document_task',
            'extract_pdf_content_task',
            'generate_chunks_task',
            'store_embeddings_task',
            'update_knowledge_graph_task'
        ]
        
        for task in expected_tasks:
            if task not in task_routes:
                print(f"❌ Missing task route: {task}")
                return False
        
        print("✅ Celery configuration valid")
        return True
        
    except Exception as e:
        print(f"❌ Celery configuration test failed: {e}")
        return False

def test_celery_service_init():
    """Test CeleryService initialization."""
    try:
        from multimodal_librarian.services.celery_service import CeleryService
        
        service = CeleryService()
        health = service.health_check()
        
        if health['status'] in ['healthy', 'degraded']:
            print(f"✅ Celery service initialized (status: {health['status']})")
            return True
        else:
            print(f"❌ Celery service unhealthy: {health}")
            return False
            
    except Exception as e:
        print(f"❌ Celery service initialization failed: {e}")
        return False

def test_processing_service_init():
    """Test ProcessingService initialization."""
    try:
        from multimodal_librarian.services.processing_service import ProcessingService
        
        service = ProcessingService()
        stats = service.get_processing_statistics()
        
        if isinstance(stats, dict):
            print("✅ Processing service initialized successfully")
            return True
        else:
            print("❌ Processing service statistics invalid")
            return False
            
    except Exception as e:
        print(f"❌ Processing service initialization failed: {e}")
        return False

def main():
    """Run basic tests."""
    print("🧪 Starting Task 4: Basic Integration Tests")
    print("=" * 50)
    
    tests = [
        ("Celery Import", test_celery_import),
        ("Processing Service Import", test_processing_service_import),
        ("Redis Connection", test_redis_connection),
        ("Celery Configuration", test_celery_configuration),
        ("Celery Service Init", test_celery_service_init),
        ("Processing Service Init", test_processing_service_init),
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        print(f"\n🔍 Testing: {test_name}")
        if test_func():
            passed += 1
        else:
            print(f"   ⚠️  {test_name} failed")
    
    print(f"\n{'='*50}")
    print(f"Test Results: {passed}/{total} tests passed")
    print(f"{'='*50}")
    
    if passed == total:
        print("🎉 All basic tests passed! Task 4 core integration is working.")
        print("\nNext steps:")
        print("1. Fix SQLAlchemy model metadata conflict")
        print("2. Run full deployment script: ./scripts/deploy-task4-document-processing.sh")
        print("3. Start Celery worker and test document processing")
        return True
    else:
        print("⚠️  Some tests failed. Please check the implementation.")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)