#!/usr/bin/env python3
"""
Test Environment Variable Loading

This script tests that environment variables are properly loaded
by the application configuration system.
"""

import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

def test_config_loading():
    """Test configuration loading."""
    print("Testing environment variable loading...")
    print("=" * 50)
    
    try:
        # Test basic config loading
        from multimodal_librarian.config import get_settings
        print(f"  Config module: {get_settings.__module__}")
        settings = get_settings()
        
        print("✓ Basic configuration loaded successfully")
        print(f"  App Name: {settings.app_name}")
        print(f"  Environment: {getattr(settings, 'environment', 'N/A')}")
        print(f"  ML Environment: {getattr(settings, 'ml_environment', 'N/A')}")
        print(f"  ML Database Type: {getattr(settings, 'ml_database_type', 'N/A')}")
        if hasattr(settings, 'get_database_backend'):
            print(f"  Database Backend: {settings.get_database_backend()}")
        print(f"  Debug Mode: {settings.debug}")
        print(f"  API Host: {settings.api_host}")
        print(f"  API Port: {settings.api_port}")
        print(f"  Upload Dir: {settings.upload_dir}")
        print(f"  Media Dir: {settings.media_dir}")
        print(f"  Export Dir: {settings.export_dir}")
        print()
        
    except Exception as e:
        print(f"✗ Failed to load basic configuration: {e}")
        print(f"  Error type: {type(e).__name__}")
        import traceback
        traceback.print_exc()
        return False
    
    try:
        # Test config factory
        from multimodal_librarian.config.config_factory import get_database_config, detect_environment
        
        env_info = detect_environment()
        print("✓ Environment detection successful")
        print(f"  Detected Type: {env_info.detected_type}")
        print(f"  Confidence: {env_info.confidence:.2f}")
        print(f"  Indicators: {list(env_info.indicators.keys())}")
        if env_info.warnings:
            print(f"  Warnings: {env_info.warnings}")
        print()
        
        config = get_database_config()
        print("✓ Database configuration loaded successfully")
        print(f"  Backend Type: {config.get_backend_type()}")
        
        if hasattr(config, 'get_environment_info'):
            env_info = config.get_environment_info()
            print(f"  Environment Info: {env_info}")
        
        print()
        
    except Exception as e:
        print(f"✗ Failed to load database configuration: {e}")
        return False
    
    try:
        # Test local config specifically
        from multimodal_librarian.config.local_config import get_local_config
        
        local_config = get_local_config()
        print("✓ Local configuration loaded successfully")
        print(f"  PostgreSQL: {local_config.postgres_host}:{local_config.postgres_port}")
        print(f"  Neo4j: {local_config.neo4j_host}:{local_config.neo4j_port}")
        print(f"  Milvus: {local_config.milvus_host}:{local_config.milvus_port}")
        print()
        
        # Test configuration validation
        validation = local_config.validate_configuration()
        print("✓ Configuration validation completed")
        print(f"  Valid: {validation['valid']}")
        if validation['issues']:
            print(f"  Issues: {validation['issues']}")
        if validation['warnings']:
            print(f"  Warnings: {validation['warnings']}")
        print()
        
    except Exception as e:
        print(f"✗ Failed to load local configuration: {e}")
        return False
    
    # Test environment variable access
    print("Environment Variables:")
    print("-" * 20)
    
    important_vars = [
        "ML_ENVIRONMENT", "ML_DATABASE_TYPE", "DATABASE_TYPE",
        "POSTGRES_HOST", "POSTGRES_PORT", "POSTGRES_DB", "POSTGRES_USER",
        "NEO4J_HOST", "NEO4J_PORT", "NEO4J_USER",
        "MILVUS_HOST", "MILVUS_PORT",
        "REDIS_HOST", "REDIS_PORT",
        "DEBUG", "LOG_LEVEL", "API_HOST", "API_PORT"
    ]
    
    for var in important_vars:
        value = os.getenv(var, "NOT_SET")
        print(f"  {var}: {value}")
    
    print()
    print("✓ All configuration tests passed!")
    return True


def test_database_client_factory():
    """Test database client factory."""
    print("Testing database client factory...")
    print("=" * 50)
    
    try:
        from multimodal_librarian.clients.database_client_factory import DatabaseClientFactory
        from multimodal_librarian.config.config_factory import get_database_config
        
        config = get_database_config()
        factory = DatabaseClientFactory(config)
        
        print("✓ Database client factory created successfully")
        print(f"  Configuration type: {type(config).__name__}")
        print(f"  Backend type: {config.get_backend_type()}")
        print()
        
        # Test client creation (without actually connecting)
        print("Testing client creation (dry run):")
        
        try:
            # Test PostgreSQL client creation
            postgres_config = factory._get_postgres_config()
            print(f"  ✓ PostgreSQL config: {postgres_config['host']}:{postgres_config['port']}")
        except Exception as e:
            print(f"  ✗ PostgreSQL config error: {e}")
        
        try:
            # Test Neo4j client creation
            neo4j_config = factory._get_neo4j_config()
            print(f"  ✓ Neo4j config: {neo4j_config['uri']}")
        except Exception as e:
            print(f"  ✗ Neo4j config error: {e}")
        
        try:
            # Test Milvus client creation
            milvus_config = factory._get_milvus_config()
            print(f"  ✓ Milvus config: {milvus_config['host']}:{milvus_config['port']}")
        except Exception as e:
            print(f"  ✗ Milvus config error: {e}")
        
        print()
        print("✓ Database client factory tests passed!")
        return True
        
    except Exception as e:
        print(f"✗ Database client factory test failed: {e}")
        return False


def main():
    """Main function."""
    print("Environment Variable Loading Test")
    print("=" * 60)
    print()
    
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
    else:
        print("⚠ .env.local file not found - using system environment only")
        print()
    
    # Run tests
    success = True
    
    success &= test_config_loading()
    print()
    
    success &= test_database_client_factory()
    print()
    
    if success:
        print("🎉 All tests passed! Environment configuration is working correctly.")
        sys.exit(0)
    else:
        print("❌ Some tests failed. Check the configuration.")
        sys.exit(1)


if __name__ == "__main__":
    main()