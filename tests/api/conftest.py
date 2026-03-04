"""
Pytest configuration for API dependency injection tests.

This conftest does NOT import the main application to avoid triggering
startup initialization during test collection.
"""

import pytest


@pytest.fixture
def di_test_settings():
    """Minimal test settings for DI tests."""
    return {
        "debug": True,
        "log_level": "DEBUG",
    }


@pytest.fixture(autouse=True)
def clear_di_cache():
    """Clear DI service cache before and after each test."""
    # Clear before test
    try:
        from multimodal_librarian.api.dependencies.services import clear_service_cache
        clear_service_cache()
    except ImportError:
        pass
    
    yield
    
    # Clear after test
    try:
        from multimodal_librarian.api.dependencies.services import clear_service_cache
        clear_service_cache()
    except ImportError:
        pass
