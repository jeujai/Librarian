"""
Tests for configuration management.
"""

import os
import tempfile
from pathlib import Path

import pytest

from multimodal_librarian.config import Settings, get_settings


def test_settings_defaults():
    """Test that settings have correct default values."""
    # Create settings without loading from .env file by temporarily setting env_file to None
    import os
    from unittest.mock import patch
    
    # Mock environment to not have DEBUG set
    with patch.dict(os.environ, {}, clear=True):
        # Create settings with no env file
        class TestSettings(Settings):
            model_config = Settings.model_config.copy()
            model_config.update({"env_file": None})
        
        settings = TestSettings()
    
    assert settings.app_name == "Multimodal Librarian"
    assert settings.debug is False
    assert settings.log_level == "INFO"
    assert settings.api_host == "0.0.0.0"
    assert settings.api_port == 8000
    assert settings.postgres_host == "localhost"
    assert settings.postgres_port == 5432
    assert settings.milvus_host == "localhost"
    assert settings.milvus_port == 19530


def test_postgres_url_generation():
    """Test PostgreSQL URL generation."""
    settings = Settings(
        postgres_user="testuser",
        postgres_password="testpass",
        postgres_host="testhost",
        postgres_port=5433,
        postgres_db="testdb"
    )
    
    expected_url = "postgresql://testuser:testpass@testhost:5433/testdb"
    assert settings.postgres_url == expected_url


def test_directory_creation():
    """Test that necessary directories are created."""
    with tempfile.TemporaryDirectory() as temp_dir:
        upload_dir = os.path.join(temp_dir, "test_uploads")
        media_dir = os.path.join(temp_dir, "test_media")
        export_dir = os.path.join(temp_dir, "test_exports")
        
        settings = Settings(
            upload_dir=upload_dir,
            media_dir=media_dir,
            export_dir=export_dir
        )
        
        assert Path(upload_dir).exists()
        assert Path(media_dir).exists()
        assert Path(export_dir).exists()


def test_get_settings_caching():
    """Test that get_settings returns cached instance."""
    # Clear cache first
    get_settings.cache_clear()
    
    settings1 = get_settings()
    settings2 = get_settings()
    
    # Should be the same instance due to caching
    assert settings1 is settings2