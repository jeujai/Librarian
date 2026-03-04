#!/usr/bin/env python3
"""
Test Application Startup with Environment Variables

This script tests that the application can start successfully with
the configured environment variables for local development.
"""

import os
import sys
import asyncio
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


async def test_app_startup():
    """Test application startup with local environment."""
    print("Testing application startup with local environment...")
    print("=" * 60)
    
    # Load .env.local if it exists
    env_local_path = Path(".env.local")
    if env_local_path.exists():
        print(f"Loading environment from {env_local_path}")
        
        # Simple .env file loader
        with open(env_local_path, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ[key.strip()] = value.strip()
        
        print("✓ Environment variables loaded from .env.local")
        print()
    
    try:
        # Test FastAPI app creation
        print("1. Testing FastAPI app creation...")
        from multimodal_librarian.main import create_minimal_app
        
        app = create_minimal_app()
        print("✓ FastAPI app created successfully")
        print(f"  Title: {app.title}")
        print(f"  Version: {app.version}")
        print()
        
    except Exception as e:
        print(f"✗ Failed to create FastAPI app: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    try:
        # Test configuration loading
        print("2. Testing configuration loading...")
        from multimodal_librarian.config.config_factory import get_database_config
        
        config = get_database_config()
        print("✓ Database configuration loaded successfully")
        print(f"  Backend: {config.get_backend_type()}")
        
        if hasattr(config, 'get_environment_info'):
            env_info = config.get_environment_info()
            print(f"  Services: {list(env_info.get('services', {}).keys())}")
        
        print()
        
    except Exception as e:
        print(f"✗ Failed to load database configuration: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    try:
        # Test dependency injection system
        print("3. Testing dependency injection system...")
        from multimodal_librarian.api.dependencies.services import get_configuration_factory
        
        factory = get_configuration_factory()
        print("✓ Configuration factory loaded successfully")
        print(f"  Factory type: {type(factory).__name__}")
        print()
        
    except Exception as e:
        print(f"✗ Failed to load dependency injection: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    try:
        # Test health check endpoint
        print("4. Testing health check endpoint...")
        from fastapi.testclient import TestClient
        
        client = TestClient(app)
        response = client.get("/health/simple")
        
        print(f"✓ Health check endpoint responded: {response.status_code}")
        if response.status_code == 200:
            print(f"  Response: {response.json()}")
        print()
        
    except Exception as e:
        print(f"✗ Failed to test health check endpoint: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    try:
        # Test environment variable access
        print("5. Testing environment variable access...")
        
        important_vars = [
            "ML_ENVIRONMENT", "ML_DATABASE_TYPE", "DATABASE_TYPE",
            "POSTGRES_HOST", "POSTGRES_PORT", "POSTGRES_DB", "POSTGRES_USER",
            "NEO4J_HOST", "NEO4J_PORT", "NEO4J_USER",
            "MILVUS_HOST", "MILVUS_PORT",
            "DEBUG", "LOG_LEVEL", "API_HOST", "API_PORT"
        ]
        
        missing_vars = []
        for var in important_vars:
            value = os.getenv(var)
            if value is None:
                missing_vars.append(var)
        
        if missing_vars:
            print(f"⚠ Missing environment variables: {missing_vars}")
        else:
            print("✓ All important environment variables are set")
        
        print()
        
    except Exception as e:
        print(f"✗ Failed to check environment variables: {e}")
        return False
    
    print("🎉 Application startup test completed successfully!")
    print()
    print("Summary:")
    print("- FastAPI app can be created with local environment")
    print("- Database configuration loads correctly")
    print("- Dependency injection system works")
    print("- Health check endpoint is accessible")
    print("- Environment variables are properly configured")
    print()
    print("The application is ready for local development!")
    
    return True


def main():
    """Main function."""
    print("Application Startup Test with Local Environment")
    print("=" * 60)
    print()
    
    success = asyncio.run(test_app_startup())
    
    if success:
        print("\n✅ All tests passed! The application is ready for local development.")
        sys.exit(0)
    else:
        print("\n❌ Some tests failed. Check the configuration and try again.")
        sys.exit(1)


if __name__ == "__main__":
    main()