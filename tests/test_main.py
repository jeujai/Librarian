"""
Tests for the main FastAPI application.
"""

import pytest
from fastapi.testclient import TestClient


def test_root_endpoint(client: TestClient):
    """Test the root endpoint returns correct response."""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["message"] == "Multimodal Librarian API"
    assert data["version"] == "0.1.0"


def test_health_check_endpoint(client: TestClient):
    """Test the health check endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    # The endpoint returns either ServiceHealthResponse or basic fallback
    if "overall_status" in data:
        # ServiceHealthResponse format
        assert data["overall_status"] == "healthy"
        assert "services" in data
        assert "uptime_seconds" in data
    else:
        # Basic fallback format
        assert data["status"] == "healthy"
        assert "service" in data


def test_app_creation():
    """Test that the FastAPI app can be created successfully."""
    from multimodal_librarian.main import create_app
    
    app = create_app()
    assert app is not None
    assert app.title == "Multimodal Librarian"