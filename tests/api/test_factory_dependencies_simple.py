"""
Simple test to verify factory-based dependencies work.
"""

import pytest
from unittest.mock import MagicMock, patch

from multimodal_librarian.api.dependencies.services import (
    get_environment_info,
    is_factory_based_environment,
    clear_all_caches,
)

# Configure pytest-asyncio
pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def clear_dependency_cache():
    """Clear dependency cache before and after each test."""
    clear_all_caches()
    yield
    clear_all_caches()


def test_get_environment_info():
    """Test environment information retrieval."""
    info = get_environment_info()
    
    # Should return a dictionary with expected keys
    assert isinstance(info, dict)
    assert "detected_environment" in info
    assert "available_clients" in info
    assert "factory_initialized" in info
    assert "legacy_clients_available" in info
    assert "cached_clients" in info
    
    # Should have reasonable values
    assert info["detected_environment"] in ["local", "aws", "unknown"]
    assert isinstance(info["available_clients"], list)
    assert isinstance(info["factory_initialized"], bool)
    assert isinstance(info["legacy_clients_available"], bool)


@patch('multimodal_librarian.config.config_factory.detect_environment')
def test_is_factory_based_environment_high_confidence(mock_detect_environment):
    """Test factory-based environment detection with high confidence."""
    mock_env_info = MagicMock()
    mock_env_info.confidence = 0.8
    mock_detect_environment.return_value = mock_env_info
    
    result = is_factory_based_environment()
    
    assert result is True


@patch('multimodal_librarian.config.config_factory.detect_environment')
def test_is_factory_based_environment_low_confidence(mock_detect_environment):
    """Test factory-based environment detection with low confidence."""
    mock_env_info = MagicMock()
    mock_env_info.confidence = 0.3
    mock_detect_environment.return_value = mock_env_info
    
    result = is_factory_based_environment()
    
    assert result is False


@patch('multimodal_librarian.config.config_factory.detect_environment')
def test_is_factory_based_environment_exception(mock_detect_environment):
    """Test factory-based environment detection with exception."""
    mock_detect_environment.side_effect = Exception("Detection failed")
    
    result = is_factory_based_environment()
    
    assert result is False


def test_clear_all_caches():
    """Test that cache clearing doesn't raise exceptions."""
    # Should not raise any exceptions
    clear_all_caches()
    
    # Should be idempotent
    clear_all_caches()
    clear_all_caches()


if __name__ == "__main__":
    pytest.main([__file__])