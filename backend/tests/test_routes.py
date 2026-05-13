import pytest
from fastapi.testclient import TestClient
from backend.main import app
from backend.routes.chaining import PAIRING_CODE_CACHE

client = TestClient(app)

def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "OK"}

def test_admin_config_access_denied():
    # Non-admin user header
    response = client.get("/api/admin/config", headers={"X-User-Email": "student@example.com"})
    assert response.status_code == 403

def test_admin_config_success():
    # Admin user header
    response = client.get("/api/admin/config", headers={"X-User-Email": "admin@example.com"})
    assert response.status_code == 200
    data = response.json()
    assert data["customer_id"] == "customers/my_customer"

def test_chaining_generate_access_denied():
    response = client.post("/api/chaining/generate", headers={"X-User-Email": "student@example.com"})
    assert response.status_code == 403

def test_chaining_generate_and_verify_success():
    # User authorized for chaining
    response = client.post("/api/chaining/generate", headers={"X-User-Email": "trust-chaining-allowed@example.com"})
    assert response.status_code == 200
    data = response.json()
    assert "pairing_code" in data
    code = data["pairing_code"]
    
    assert code in PAIRING_CODE_CACHE

    # Verify pairing code
    verify_resp = client.post(
        "/api/chaining/verify", 
        headers={"X-User-Email": "trust-chaining-allowed@example.com"},
        json={"pairing_code": code, "raw_device_id": "pixel-phone99"}
    )
    assert verify_resp.status_code == 200
    assert verify_resp.json()["status"] == "SUCCESS"
    assert code not in PAIRING_CODE_CACHE # Cache invalidated

def test_network_approval_success():
    # Pass X-Forwarded-For matching trusted IP range '127.0.0.1/32'
    response = client.post(
        "/api/network/approve",
        headers={"X-Forwarded-For": "127.0.0.1", "X-User-Email": "student@example.com"},
        json={"raw_device_id": "pixel-phone99"}
    )
    assert response.status_code == 200
    assert response.json()["status"] == "SUCCESS"

def test_network_approval_forbidden():
    # Pass untrusted IP
    response = client.post(
        "/api/network/approve",
        headers={"X-Forwarded-For": "192.168.1.100", "X-User-Email": "student@example.com"},
        json={"raw_device_id": "pixel-phone99"}
    )
    assert response.status_code == 403

def test_cron_cleanup_forbidden():
    # Missing cron headers
    response = client.post("/api/cron/cleanup")
    assert response.status_code == 403

def test_cron_cleanup_success():
    # Valid mock cron header
    response = client.post("/api/cron/cleanup", headers={"X-Mock-Cron": "true"})
    assert response.status_code == 200
    assert response.json()["status"] == "SUCCESS"
