"""Health endpoint tests."""
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    """Create test client."""
    from server import app
    return TestClient(app)


def test_health_live(client):
    """Test liveness probe endpoint."""
    response = client.get("/api/health/live")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "live"


def test_health_ready(client):
    """Test readiness probe endpoint."""
    response = client.get("/api/health/ready")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ready"


def test_root_endpoint(client):
    """Test root API endpoint."""
    response = client.get("/api/")
    assert response.status_code == 200
    data = response.json()
    assert "message" in data
