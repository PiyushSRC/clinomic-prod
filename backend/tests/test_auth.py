"""Authentication tests."""
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    """Create test client."""
    from server import app
    return TestClient(app)


def test_login_success(client):
    """Test successful login with demo credentials."""
    response = client.post("/api/auth/login", json={
        "username": "admin",
        "password": "admin"
    })
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "role" in data
    assert data["role"] == "ADMIN"


def test_login_invalid_credentials(client):
    """Test login with invalid credentials."""
    response = client.post("/api/auth/login", json={
        "username": "invalid",
        "password": "invalid"
    })
    assert response.status_code == 401


def test_login_wrong_password(client):
    """Test login with wrong password."""
    response = client.post("/api/auth/login", json={
        "username": "admin",
        "password": "wrong"
    })
    assert response.status_code == 401


def test_protected_endpoint_unauthorized(client):
    """Test accessing protected endpoint without token."""
    response = client.get("/api/auth/me")
    assert response.status_code == 401


def test_protected_endpoint_authorized(client):
    """Test accessing protected endpoint with valid token."""
    # First login
    login_response = client.post("/api/auth/login", json={
        "username": "admin",
        "password": "admin"
    })
    token = login_response.json()["access_token"]
    
    # Access protected endpoint
    response = client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == "admin"
    assert data["role"] == "ADMIN"
