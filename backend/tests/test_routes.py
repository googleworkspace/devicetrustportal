# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import pytest
import base64
import json
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from backend.main import app
from backend.routes.chaining import PAIRING_CODE_CACHE
from backend.routes.admin import get_current_user_email
from backend.services.config_service import TenantConfig

client = TestClient(app)

@pytest.fixture(autouse=True)
def mock_services():
    with patch("backend.services.directory_service.DirectoryService.verify_user_is_admin") as mock_admin, \
         patch("backend.services.directory_service.DirectoryService.get_user_chaining_policy") as mock_chain, \
         patch("backend.services.cloud_identity.CloudIdentityService.lookup_device_user") as mock_lookup, \
         patch("backend.services.cloud_identity.CloudIdentityService.parse_endpoint_verification_header") as mock_ev, \
         patch("backend.services.cloud_identity.CloudIdentityService.approve_device_user") as mock_app, \
         patch("backend.services.cloud_identity.CloudIdentityService.list_inactive_devices") as mock_inact, \
         patch("backend.services.cloud_identity.CloudIdentityService.revoke_device_user") as mock_rev, \
         patch("backend.services.config_service.ConfigService.get_tenant_config") as mock_conf, \
         patch("backend.services.cloud_identity.cloud_identity_service.service") as mock_service:
        
        mock_admin.side_effect = lambda *args, **kwargs: "admin" in (kwargs.get("user_email") or args[0])
        mock_chain.side_effect = lambda *args, **kwargs: "allowed" in (kwargs.get("user_email") or args[0])
        
        mock_conf.return_value = TenantConfig(
            customer_id="customers/my_customer",
            inactivity_threshold_days=90,
            trusted_ip_ranges=["127.0.0.1/32"],
            chaining_allowed_groups=["trust-chaining-allowed@example.com"],
            chaining_allowed_ous=["/Staff"]
        )
        
        mock_ev.return_value = "devices/dev-1/deviceUsers/du-1"
        mock_lookup.return_value = "devices/dev-1/deviceUsers/du-1"
        mock_app.return_value = {"done": True, "response": {"status": "APPROVED"}}
        mock_inact.return_value = [{"name": "devices/dev-1/deviceUsers/du-1"}]
        mock_rev.return_value = {"status": "REVOKED"}
        
        mock_service.devices().create().execute.return_value = {"name": "devices/dev-99"}
        mock_service.devices().list().execute.return_value = {"devices": [{"name": "devices/dev-1", "deviceType": "CHROME_OS", "model": "Chromebook", "osVersion": "Chrome 120", "serialNumber": "1234"}]}
        mock_service.devices().deviceUsers().list().execute.return_value = {
            "deviceUsers": [{"name": "devices/dev-1/deviceUsers/du-1", "userEmail": "student@example.com", "approvalState": "APPROVED"}]
        }
        
        yield
        app.dependency_overrides.clear()

def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "OK"}

def test_admin_config_access_denied():
    app.dependency_overrides[get_current_user_email] = lambda: "student@example.com"
    response = client.get("/api/admin/config")
    assert response.status_code == 403

def test_admin_config_success():
    app.dependency_overrides[get_current_user_email] = lambda: "admin@example.com"
    response = client.get("/api/admin/config")
    assert response.status_code == 200
    data = response.json()
    assert data["customer_id"] == "customers/my_customer"

def test_chaining_generate_access_denied():
    app.dependency_overrides[get_current_user_email] = lambda: "student@example.com"
    response = client.post("/api/chaining/generate")
    assert response.status_code == 403

def test_chaining_generate_and_verify_success():
    app.dependency_overrides[get_current_user_email] = lambda: "trust-chaining-allowed@example.com"
    response = client.post("/api/chaining/generate")
    assert response.status_code == 200
    data = response.json()
    assert "pairing_code" in data
    code = data["pairing_code"]
    
    assert code in PAIRING_CODE_CACHE

    verify_resp = client.post(
        "/api/chaining/verify", 
        json={"pairing_code": code, "raw_device_id": "pixel-phone99"}
    )
    assert verify_resp.status_code == 200
    assert verify_resp.json()["status"] == "SUCCESS"
    assert code not in PAIRING_CODE_CACHE

def test_network_approval_success():
    app.dependency_overrides[get_current_user_email] = lambda: "student@example.com"
    response = client.post(
        "/api/network/approve",
        headers={"X-Forwarded-For": "127.0.0.1"},
        json={"raw_device_id": "pixel-phone99"}
    )
    assert response.status_code == 200
    assert response.json()["status"] == "SUCCESS"

def test_network_approval_forbidden():
    app.dependency_overrides[get_current_user_email] = lambda: "student@example.com"
    response = client.post(
        "/api/network/approve",
        headers={"X-Forwarded-For": "192.168.1.100"},
        json={"raw_device_id": "pixel-phone99"}
    )
    assert response.status_code == 403

def test_cron_cleanup_forbidden():
    response = client.post("/api/cron/cleanup")
    assert response.status_code == 403

def test_cron_cleanup_success():
    response = client.post("/api/cron/cleanup", headers={"X-Cloudscheduler": "true"})
    assert response.status_code == 200
    assert response.json()["status"] == "SUCCESS"

def test_webhook_enrollment_success():
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

def test_get_my_devices():
    app.dependency_overrides[get_current_user_email] = lambda: "student@example.com"
    response = client.get("/api/devices/my-devices")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["approval_state"] == "APPROVED"

def test_get_public_config():
    response = client.get("/api/config/public")
    assert response.status_code == 200
    assert "google_client_id" in response.json()
