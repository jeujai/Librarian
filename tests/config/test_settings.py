"""
Test Configuration

This module provides configuration for testing in the development environment.
"""

import os
from pathlib import Path

# Test environment settings
TEST_ENV = {
    'ML_ENVIRONMENT': 'local',
    'DATABASE_TYPE': 'local',
    'DEBUG': 'true',
    'LOG_LEVEL': 'WARNING',  # Reduce log noise in tests
    'TEST_MODE': 'true',
    'DISABLE_TELEMETRY': 'true',
    'DISABLE_ANALYTICS': 'true'
}

# Test database settings
TEST_DB_SETTINGS = {
    'TEST_DB_FAST_SETUP': 'true',
    'TEST_DB_IN_MEMORY': 'true',
    'POSTGRES_POOL_SIZE': '2',  # Smaller pool for tests
    'POSTGRES_MAX_CONNECTIONS': '10'
}

# Performance test settings
PERFORMANCE_TEST_SETTINGS = {
    'PERFORMANCE_TEST_DURATION': '10',  # Shorter for development
    'PERFORMANCE_TEST_CONCURRENT_USERS': '5',
    'PERFORMANCE_TEST_TIMEOUT': '30'
}

def setup_test_environment():
    """Set up the test environment."""
    # Apply test environment variables
    for key, value in TEST_ENV.items():
        os.environ[key] = value
    
    for key, value in TEST_DB_SETTINGS.items():
        os.environ[key] = value
    
    # Create test directories
    test_dirs = [
        Path('/app/test_data'),
        Path('/app/test_uploads'),
        Path('/app/test_exports')
    ]
    
    for test_dir in test_dirs:
        test_dir.mkdir(exist_ok=True)

def cleanup_test_environment():
    """Clean up the test environment."""
    import shutil
    
    # Clean up test directories
    test_dirs = [
        Path('/app/test_data'),
        Path('/app/test_uploads'),
        Path('/app/test_exports')
    ]
    
    for test_dir in test_dirs:
        if test_dir.exists():
            shutil.rmtree(test_dir, ignore_errors=True)
