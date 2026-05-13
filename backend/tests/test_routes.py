import pytest
import base64
import json
from fastapi.testclient import TestClient
from backend.main import app
from backend.routes.chaining import PAIRING_CODE_CACHE

client = TestClient(app)

def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "OK"}

def test_admin_config_access_denied():
    response = client.get("/api/admin/config", headers={"X-User-Email": "student@example.com"})
    assert response.status_code == 403

def test_admin_config_success():
    response = client.get("/api/admin/config", headers={"X-User-Email": "admin@example.com"})
    assert response.status_code == 200
    data = response.json()
    assert data["customer_id"] == "customers/my_customer"

def test_chaining_generate_access_denied():
    response = client.post("/api/chaining/generate", headers={"X-User-Email": "student@example.com"})
    assert response.status_code == 403

def test_chaining_generate_and_verify_success():
    response = client.post("/api/chaining/generate", headers={"X-User-Email": "trust-chaining-allowed@example.com"})
    assert response.status_code == 200
    data = response.json()
    assert "pairing_code" in data
    code = data["pairing_code"]
    
    assert code in PAIRING_CODE_CACHE

    verify_resp = client.post(
        "/api/chaining/verify", 
        headers={"X-User-Email": "trust-chaining-allowed@example.com"},
        json={"pairing_code": code, "raw_device_id": "pixel-phone99"}
    )
    assert verify_resp.status_code == 200
    assert verify_resp.json()["status"] == "SUCCESS"
    assert code not in PAIRING_CODE_CACHE

def test_network_approval_success():
    response = client.post(
        "/api/network/approve",
        headers={"X-Forwarded-For": "127.0.0.1", "X-User-Email": "student@example.com"},
        json={"raw_device_id": "pixel-phone99"}
    )
    assert response.status_code == 200
    assert response.json()["status"] == "SUCCESS"

def test_network_approval_forbidden():
    response = client.post(
        "/api/network/approve",
        headers={"X-Forwarded-For": "192.168.1.100", "X-User-Email": "student@example.com"},
        json={"raw_device_id": "pixel-phone99"}
    )
    assert response.status_code == 403

def test_cron_cleanup_forbidden():
    response = client.post("/api/cron/cleanup")
    assert response.status_code == 403

def test_cron_cleanup_success():
    response = client.post("/api/cron/cleanup", headers={"X-Mock-Cron": "true"})
    assert response.status_code == 200
    assert response.json()["status"] == "SUCCESS"

def test_webhook_enrollment_success():
    # Create mock Reports API payload
    mock_payload = {
        "events": [
            {
                "name": "ENTERPRISE_ENROLLMENT",
                "parameters": [{"name": "SERIAL_NUMBER", "value": "CHROME-9999"}]
            }
        ]
    }
    encoded_data = base64.b64encode(json.dumps(mock_payload).encode("utf-8")).decode("utf-8")
    
    push_body = {
        "message": {"data": encoded_data},
        "subscription": "projects/my-proj/subscriptions/chrome-enroll-sub"
    }
    
    response = client.post("/api/webhook/chrome-enrollment", json=push_body)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "SUCCESS"
    assert data["processed_count"] == 1
    assert "CHROME-9999" in data["anchored_serials"]

def test_webhook_ignore_irrelevant_event():
    mock_payload = {
        "events": [
            {
                "name": "USER_LOGIN",
                "parameters": [{"name": "user", "value": "student@example.com"}]
            }
        ]
    }
    encoded_data = base64.b64encode(json.dumps(mock_payload).encode("utf-8")).decode("utf-8")
    
    push_body = {
        "message": {"data": encoded_data},
        "subscription": "projects/my-proj/subscriptions/chrome-enroll-sub"
    }
    
    response = client.post("/api/webhook/chrome-enrollment", json=push_body)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "SUCCESS"
    assert data["processed_count"] == 0
