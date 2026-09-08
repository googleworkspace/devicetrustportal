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
from fastapi import HTTPException
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
         patch("backend.services.cloud_identity.CloudIdentityService.get_device_user") as mock_get_du, \
         patch("backend.services.config_service.ConfigService.get_tenant_config") as mock_conf, \
         patch("backend.services.cloud_identity.cloud_identity_service.service") as mock_service, \
         patch("backend.services.directory_service.directory_service.service") as mock_dir_service:
        
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
        mock_get_du.side_effect = lambda du_name, cid: {"name": du_name, "userEmail": "ceo@example.com"} if "du-CEO" in du_name else {"name": du_name, "userEmail": "student@example.com"}
        mock_app.return_value = {"done": True, "response": {"status": "APPROVED"}}
        mock_inact.return_value = [{"name": "devices/dev-1/deviceUsers/du-1"}]
        mock_rev.return_value = {"status": "REVOKED"}
        
        mock_service.devices().create().execute.return_value = {"name": "devices/dev-99"}
        mock_service.devices().list().execute.return_value = {"devices": [{"name": "devices/dev-1", "deviceType": "CHROME_OS", "model": "Chromebook", "osVersion": "Chrome 120", "serialNumber": "1234"}]}
        mock_service.devices().deviceUsers().list().execute.return_value = {
            "deviceUsers": [{"name": "devices/dev-1/deviceUsers/du-1", "userEmail": "student@example.com", "approvalState": "APPROVED"}]
        }
        
        mock_dir_service.chromeosdevices().list().execute.return_value = {
            "chromeosdevices": [{"deviceId": "dev-1", "serialNumber": "1234", "model": "Chromebook", "osVersion": "Chrome 120", "annotatedUser": "student@example.com"}]
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

def test_cron_sync_inventory_forbidden():
    response = client.post("/api/cron/sync-inventory")
    assert response.status_code == 403

def test_cron_sync_inventory_success():
    response = client.post("/api/cron/sync-inventory", headers={"X-Cloudscheduler": "true"})
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

def test_get_my_devices_deduplication(mock_services):
    app.dependency_overrides[get_current_user_email] = lambda: "user@example.com"
    
    mock_service = MagicMock()
    mock_devices_resource = MagicMock()
    mock_device_users_resource = MagicMock()
    
    mock_service.devices.return_value = mock_devices_resource
    mock_devices_resource.deviceUsers.return_value = mock_device_users_resource
    
    # Simulate list returns 3 Mac entries (1 serial-backed, 2 virtual duplicates)
    mock_devices_resource.list.return_value.execute.return_value = {
        "devices": [
            {
                "name": "devices/mac-serial",
                "deviceType": "MAC_OS",
                "model": "MacBook Pro",
                "osVersion": "MacOS 15.6.1",
                "serialNumber": "C02F30BV0KPF",
                "ownerType": "BYOD",
                "lastSyncTime": "2026-07-19T17:00:00Z"
            },
            {
                "name": "devices/mac-virtual1",
                "deviceType": "MAC_OS",
                "model": "MacBookPro17,1",
                "osVersion": "MacOS 15.6.1",
                "ownerType": "BYOD",
                "lastSyncTime": "2026-07-19T17:00:00Z"
            },
            {
                "name": "devices/mac-virtual2",
                "deviceType": "MAC_OS",
                "model": "Mac OS",
                "osVersion": "macOS 10.15.7",
                "ownerType": "BYOD",
                "lastSyncTime": "2026-07-19T16:00:00Z"
            }
        ]
    }
    
    def du_list_side_effect(parent, customer, pageToken=None):
        mock_req = MagicMock()
        mock_req.execute.return_value = {
            "deviceUsers": [
                {
                    "name": f"{parent}/deviceUsers/du-1",
                    "userEmail": "user@example.com",
                    "managementState": "APPROVED"
                }
            ]
        }
        return mock_req
        
    mock_device_users_resource.list.side_effect = du_list_side_effect
    
    with patch("backend.routes.devices.cloud_identity_service.service", mock_service):
        response = client.get("/api/devices/my-devices")
        assert response.status_code == 200
        data = response.json()
        # Should deduplicate 3 Mac entries down to 1 physical serial-backed asset
        assert len(data) == 1
        assert data[0]["serial_number"] == "C02F30BV0KPF"
        assert data[0]["model"] == "MacBook Pro"

def test_get_my_devices_with_directory_chromeos():
    app.dependency_overrides[get_current_user_email] = lambda: "student@example.com"
    with patch("backend.routes.devices.directory_service.get_user_chromeos_devices") as mock_dir_cbs:
        mock_dir_cbs.return_value = [
            {
                "device_user_name": "directory/devices/cb-999/deviceUsers/student@example.com",
                "device_type": "CHROME_OS",
                "model": "Acer Chromebook Spin 511",
                "os_version": "ChromeOS 120.0",
                "serial_number": "ACER-CB-999",
                "approval_state": "APPROVED",
                "owner_type": "COMPANY",
                "last_sync_time": "2026-08-31T12:00:00Z",
                "annotated_user": "student@example.com",
                "asset_tag": "ASSET-CB-999"
            }
        ]
        response = client.get("/api/devices/my-devices")
        assert response.status_code == 200
        data = response.json()
        cb_match = next((d for d in data if d["serial_number"] == "ACER-CB-999"), None)
        assert cb_match is not None
        assert cb_match["owner_type"] == "COMPANY"
        assert cb_match["approval_state"] == "APPROVED"
        assert cb_match["model"] == "Acer Chromebook Spin 511"

def test_get_my_devices_fallback_on_zero_filtered_devices():
    app.dependency_overrides[get_current_user_email] = lambda: "unindexed@example.com"

    mock_service = MagicMock()
    mock_devices_resource = MagicMock()
    mock_device_users_resource = MagicMock()

    mock_service.devices.return_value = mock_devices_resource
    mock_devices_resource.deviceUsers.return_value = mock_device_users_resource

    # When filtered by email, returns 0 devices.
    # When unfiltered (no filter kwarg), returns 1 unindexed device.
    def devices_list_side_effect(**kwargs):
        mock_req = MagicMock()
        if kwargs.get("filter"):
            mock_req.execute.return_value = {"devices": []}
        else:
            mock_req.execute.return_value = {
                "devices": [
                    {
                        "name": "devices/unindexed-phone",
                        "deviceType": "ANDROID",
                        "model": "Pixel 8 Pro",
                        "osVersion": "Android 15.0",
                        "serialNumber": "PX8-FALLBACK-001",
                        "ownerType": "BYOD",
                        "lastSyncTime": "2026-09-01T12:00:00Z"
                    }
                ]
            }
        return mock_req

    mock_devices_resource.list.side_effect = devices_list_side_effect

    def du_list_side_effect(parent, customer, pageToken=None):
        mock_req = MagicMock()
        mock_req.execute.return_value = {
            "deviceUsers": [
                {
                    "name": f"{parent}/deviceUsers/du-unindexed",
                    "userEmail": "unindexed@example.com",
                    "managementState": "APPROVED"
                }
            ]
        }
        return mock_req

    mock_device_users_resource.list.side_effect = du_list_side_effect

    with patch("backend.routes.devices.cloud_identity_service.service", mock_service), \
         patch("backend.routes.devices.directory_service.get_user_chromeos_devices", return_value=[]):
        response = client.get("/api/devices/my-devices")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["device_user_name"] == "devices/unindexed-phone/deviceUsers/du-unindexed"
        assert data[0]["serial_number"] == "PX8-FALLBACK-001"
        assert data[0]["model"] == "Pixel 8 Pro"
        assert data[0]["approval_state"] == "APPROVED"

        # Verify fast-path attempted first, then unfiltered fallback
        calls = mock_devices_resource.list.call_args_list
        assert len(calls) == 2
        assert calls[0].kwargs.get("filter") == "email:unindexed@example.com"
        assert "filter" not in calls[1].kwargs or calls[1].kwargs.get("filter") is None

def test_get_my_devices_fallback_on_secondary_session():
    app.dependency_overrides[get_current_user_email] = lambda: "secondary@example.com"

    mock_service = MagicMock()
    mock_devices_resource = MagicMock()
    mock_device_users_resource = MagicMock()

    mock_service.devices.return_value = mock_devices_resource
    mock_devices_resource.deviceUsers.return_value = mock_device_users_resource

    # Fast-path returns a device, but that device only has primary@example.com
    # Fallback unfiltered crawl returns the shared workstation which has secondary@example.com
    def devices_list_side_effect(**kwargs):
        mock_req = MagicMock()
        if kwargs.get("filter"):
            mock_req.execute.return_value = {
                "devices": [
                    {
                        "name": "devices/dev-other-user",
                        "deviceType": "MAC_OS",
                        "model": "MacBook Air",
                        "serialNumber": "MAC-PRIMARY-ONLY",
                        "ownerType": "BYOD",
                        "lastSyncTime": "2026-09-01T10:00:00Z"
                    }
                ]
            }
        else:
            mock_req.execute.return_value = {
                "devices": [
                    {
                        "name": "devices/dev-shared-workstation",
                        "deviceType": "WINDOWS",
                        "model": "Precision 5570",
                        "serialNumber": "DELL-SEC-SESSION",
                        "ownerType": "BYOD",
                        "lastSyncTime": "2026-09-01T11:00:00Z"
                    }
                ]
            }
        return mock_req

    mock_devices_resource.list.side_effect = devices_list_side_effect

    def du_list_side_effect(parent, customer, pageToken=None):
        mock_req = MagicMock()
        if parent == "devices/dev-other-user":
            mock_req.execute.return_value = {
                "deviceUsers": [
                    {
                        "name": "devices/dev-other-user/deviceUsers/du-other",
                        "userEmail": "primary@example.com",
                        "managementState": "APPROVED"
                    }
                ]
            }
        else:
            mock_req.execute.return_value = {
                "deviceUsers": [
                    {
                        "name": "devices/dev-shared-workstation/deviceUsers/du-sec",
                        "userEmail": "secondary@example.com",
                        "managementState": "APPROVED"
                    }
                ]
            }
        return mock_req

    mock_device_users_resource.list.side_effect = du_list_side_effect

    with patch("backend.routes.devices.cloud_identity_service.service", mock_service), \
         patch("backend.routes.devices.directory_service.get_user_chromeos_devices", return_value=[]):
        response = client.get("/api/devices/my-devices")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["device_user_name"] == "devices/dev-shared-workstation/deviceUsers/du-sec"
        assert data[0]["serial_number"] == "DELL-SEC-SESSION"
        assert data[0]["model"] == "Precision 5570"

        # Verify fast path was tried first, then fallback
        assert len(mock_devices_resource.list.call_args_list) == 2

def test_get_my_devices_fast_path_success_skips_fallback():
    app.dependency_overrides[get_current_user_email] = lambda: "direct@example.com"

    mock_service = MagicMock()
    mock_devices_resource = MagicMock()
    mock_device_users_resource = MagicMock()

    mock_service.devices.return_value = mock_devices_resource
    mock_devices_resource.deviceUsers.return_value = mock_device_users_resource

    mock_devices_resource.list.return_value.execute.return_value = {
        "devices": [
            {
                "name": "devices/dev-fast",
                "deviceType": "MAC_OS",
                "model": "MacBook Pro 16",
                "serialNumber": "MAC-FAST-001",
                "ownerType": "BYOD",
                "lastSyncTime": "2026-09-01T10:00:00Z"
            }
        ]
    }

    mock_device_users_resource.list.return_value.execute.return_value = {
        "deviceUsers": [
            {
                "name": "devices/dev-fast/deviceUsers/du-fast",
                "userEmail": "direct@example.com",
                "managementState": "APPROVED"
            }
        ]
    }

    with patch("backend.routes.devices.cloud_identity_service.service", mock_service), \
         patch("backend.routes.devices.directory_service.get_user_chromeos_devices", return_value=[]):
        response = client.get("/api/devices/my-devices")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["serial_number"] == "MAC-FAST-001"
        # Only 1 list call made (fast-path filter)
        assert mock_devices_resource.list.call_count == 1
        assert mock_devices_resource.list.call_args.kwargs.get("filter") == "email:direct@example.com"

def test_get_my_devices_fallback_deduplication():
    app.dependency_overrides[get_current_user_email] = lambda: "user@example.com"

    mock_service = MagicMock()
    mock_devices_resource = MagicMock()
    mock_device_users_resource = MagicMock()

    mock_service.devices.return_value = mock_devices_resource
    mock_devices_resource.deviceUsers.return_value = mock_device_users_resource

    def devices_list_side_effect(**kwargs):
        mock_req = MagicMock()
        if kwargs.get("filter"):
            mock_req.execute.return_value = {"devices": []}
        else:
            mock_req.execute.return_value = {
                "devices": [
                    {
                        "name": "devices/mac-fallback-serial",
                        "deviceType": "MAC_OS",
                        "model": "MacBook Pro",
                        "serialNumber": "MAC-DEDUP-FALLBACK",
                        "ownerType": "BYOD",
                        "lastSyncTime": "2026-09-01T12:00:00Z"
                    },
                    {
                        "name": "devices/mac-fallback-virtual",
                        "deviceType": "MAC_OS",
                        "model": "MacBook Pro",
                        "ownerType": "BYOD",
                        "lastSyncTime": "2026-09-01T11:00:00Z"
                    }
                ]
            }
        return mock_req

    mock_devices_resource.list.side_effect = devices_list_side_effect

    def du_list_side_effect(parent, customer, pageToken=None):
        mock_req = MagicMock()
        mock_req.execute.return_value = {
            "deviceUsers": [
                {
                    "name": f"{parent}/deviceUsers/du-1",
                    "userEmail": "user@example.com",
                    "managementState": "APPROVED"
                }
            ]
        }
        return mock_req

    mock_device_users_resource.list.side_effect = du_list_side_effect

    with patch("backend.routes.devices.cloud_identity_service.service", mock_service), \
         patch("backend.routes.devices.directory_service.get_user_chromeos_devices", return_value=[]):
        response = client.get("/api/devices/my-devices")
        assert response.status_code == 200
        data = response.json()
        # Deduplication retains the physical hardware serial asset and drops virtual duplicate
        assert len(data) == 1
        assert data[0]["serial_number"] == "MAC-DEDUP-FALLBACK"

def test_get_my_devices_fast_path_exception_triggers_fallback():
    app.dependency_overrides[get_current_user_email] = lambda: "user@example.com"

    mock_service = MagicMock()
    mock_devices_resource = MagicMock()
    mock_device_users_resource = MagicMock()

    mock_service.devices.return_value = mock_devices_resource
    mock_devices_resource.deviceUsers.return_value = mock_device_users_resource

    def devices_list_side_effect(**kwargs):
        if kwargs.get("filter"):
            raise Exception("Cloud Identity API filter error: invalid query expression")
        mock_req = MagicMock()
        mock_req.execute.return_value = {
            "devices": [
                {
                    "name": "devices/dev-recovered",
                    "deviceType": "WINDOWS",
                    "model": "ThinkPad X1",
                    "serialNumber": "THINKPAD-RECOVERED",
                    "ownerType": "BYOD",
                    "lastSyncTime": "2026-09-01T12:00:00Z"
                }
            ]
        }
        return mock_req

    mock_devices_resource.list.side_effect = devices_list_side_effect

    def du_list_side_effect(parent, customer, pageToken=None):
        mock_req = MagicMock()
        mock_req.execute.return_value = {
            "deviceUsers": [
                {
                    "name": f"{parent}/deviceUsers/du-rec",
                    "userEmail": "user@example.com",
                    "managementState": "APPROVED"
                }
            ]
        }
        return mock_req

    mock_device_users_resource.list.side_effect = du_list_side_effect

    with patch("backend.routes.devices.cloud_identity_service.service", mock_service), \
         patch("backend.routes.devices.directory_service.get_user_chromeos_devices", return_value=[]):
        response = client.get("/api/devices/my-devices")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["serial_number"] == "THINKPAD-RECOVERED"

def test_get_my_devices_null_api_fields_handled_safely():
    app.dependency_overrides[get_current_user_email] = lambda: "user@example.com"

    mock_service = MagicMock()
    mock_devices_resource = MagicMock()
    mock_device_users_resource = MagicMock()

    mock_service.devices.return_value = mock_devices_resource
    mock_devices_resource.deviceUsers.return_value = mock_device_users_resource

    # API returns device with explicit None fields
    mock_devices_resource.list.return_value.execute.return_value = {
        "devices": [
            {
                "name": "devices/dev-null-test",
                "deviceType": None,
                "model": None,
                "osVersion": None,
                "os": None,
                "ownerType": None,
                "serialNumber": None,
                "lastSyncTime": None
            }
        ]
    }

    # Device users contains one entry with null userEmail and another matching user with null states
    mock_device_users_resource.list.return_value.execute.return_value = {
        "deviceUsers": [
            {
                "name": "devices/dev-null-test/deviceUsers/du-no-email",
                "userEmail": None
            },
            {
                "name": "devices/dev-null-test/deviceUsers/du-valid",
                "userEmail": "user@example.com",
                "managementState": None,
                "approvalState": None,
                "lastSyncTime": None
            }
        ]
    }

    with patch("backend.routes.devices.cloud_identity_service.service", mock_service), \
         patch("backend.routes.devices.directory_service.get_user_chromeos_devices", return_value=[]):
        response = client.get("/api/devices/my-devices")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        dev = data[0]
        assert dev["device_user_name"] == "devices/dev-null-test/deviceUsers/du-valid"
        assert dev["device_type"] == "UNKNOWN_TYPE"
        assert dev["model"] == "Unknown Model"
        assert dev["os_version"] == "Unknown OS"
        assert dev["owner_type"] == "BYOD"
        assert dev["serial_number"] == "N/A"
        assert dev["approval_state"] == "UNKNOWN_STATE"
        assert dev["last_sync_time"] == "N/A"

def test_get_my_devices_virtual_asset_sorting_with_na():
    app.dependency_overrides[get_current_user_email] = lambda: "user@example.com"

    mock_service = MagicMock()
    mock_devices_resource = MagicMock()
    mock_device_users_resource = MagicMock()

    mock_service.devices.return_value = mock_devices_resource
    mock_devices_resource.deviceUsers.return_value = mock_device_users_resource

    # Two virtual extension assets: one with "N/A" sync time and one with real timestamp
    mock_devices_resource.list.return_value.execute.return_value = {
        "devices": [
            {
                "name": "devices/dev-v-na",
                "deviceType": "MAC_OS",
                "model": "MacBook Pro",
                "serialNumber": None,
                "ownerType": "BYOD",
                "lastSyncTime": None
            },
            {
                "name": "devices/dev-v-recent",
                "deviceType": "MAC_OS",
                "model": "MacBook Pro",
                "serialNumber": None,
                "ownerType": "BYOD",
                "lastSyncTime": "2026-09-08T12:00:00Z"
            }
        ]
    }

    def du_side_effect(parent, customer, pageToken=None):
        mock_req = MagicMock()
        if parent == "devices/dev-v-na":
            mock_req.execute.return_value = {
                "deviceUsers": [
                    {
                        "name": "devices/dev-v-na/deviceUsers/du-na",
                        "userEmail": "user@example.com",
                        "approvalState": "APPROVED",
                        "lastSyncTime": None
                    }
                ]
            }
        else:
            mock_req.execute.return_value = {
                "deviceUsers": [
                    {
                        "name": "devices/dev-v-recent/deviceUsers/du-recent",
                        "userEmail": "user@example.com",
                        "approvalState": "APPROVED",
                        "lastSyncTime": "2026-09-08T12:00:00Z"
                    }
                ]
            }
        return mock_req

    mock_device_users_resource.list.side_effect = du_side_effect

    with patch("backend.routes.devices.cloud_identity_service.service", mock_service), \
         patch("backend.routes.devices.directory_service.get_user_chromeos_devices", return_value=[]):
        response = client.get("/api/devices/my-devices")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        # Confirms the recently synced asset is kept instead of the "N/A" entry
        assert data[0]["device_user_name"] == "devices/dev-v-recent/deviceUsers/du-recent"
        assert data[0]["last_sync_time"] == "2026-09-08T12:00:00Z"

def test_get_my_devices_empty_user_email_returns_empty():
    app.dependency_overrides[get_current_user_email] = lambda: ""
    response = client.get("/api/devices/my-devices")
    assert response.status_code == 200
    assert response.json() == []

def test_get_my_devices_case_insensitive_serial_deduplication_and_approval_promotion():
    app.dependency_overrides[get_current_user_email] = lambda: "user@example.com"

    mock_service = MagicMock()
    mock_devices_resource = MagicMock()
    mock_device_users_resource = MagicMock()

    mock_service.devices.return_value = mock_devices_resource
    mock_devices_resource.deviceUsers.return_value = mock_device_users_resource

    # Two entries for same physical serial with differing case:
    # First is lowercase serial with PENDING_APPROVAL. Second is uppercase serial with APPROVED.
    mock_devices_resource.list.return_value.execute.return_value = {
        "devices": [
            {
                "name": "devices/dev-pending",
                "deviceType": "WINDOWS",
                "model": "ThinkPad",
                "serialNumber": "thinkpad-case-123",
                "ownerType": "BYOD",
                "lastSyncTime": "2026-09-01T10:00:00Z"
            },
            {
                "name": "devices/dev-approved",
                "deviceType": "WINDOWS",
                "model": "ThinkPad X1 Carbon",
                "serialNumber": "THINKPAD-CASE-123",
                "ownerType": "BYOD",
                "lastSyncTime": "2026-09-02T10:00:00Z"
            }
        ]
    }

    def du_side_effect(parent, customer, pageToken=None):
        mock_req = MagicMock()
        state = "APPROVED" if "dev-approved" in parent else "PENDING_APPROVAL"
        mock_req.execute.return_value = {
            "deviceUsers": [
                {
                    "name": f"{parent}/deviceUsers/du-1",
                    "userEmail": "user@example.com",
                    "approvalState": state
                }
            ]
        }
        return mock_req

    mock_device_users_resource.list.side_effect = du_side_effect

    with patch("backend.routes.devices.cloud_identity_service.service", mock_service), \
         patch("backend.routes.devices.directory_service.get_user_chromeos_devices", return_value=[]):
        response = client.get("/api/devices/my-devices")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["approval_state"] == "APPROVED"
        assert data[0]["model"] == "ThinkPad X1 Carbon"

def test_get_my_devices_pagination_cycle_protection():
    app.dependency_overrides[get_current_user_email] = lambda: "user@example.com"

    mock_service = MagicMock()
    mock_devices_resource = MagicMock()
    mock_device_users_resource = MagicMock()

    mock_service.devices.return_value = mock_devices_resource
    mock_devices_resource.deviceUsers.return_value = mock_device_users_resource

    # Returns same nextPageToken on every call
    mock_devices_resource.list.return_value.execute.return_value = {
        "devices": [
            {
                "name": "devices/dev-loop",
                "deviceType": "LINUX",
                "model": "Workstation",
                "serialNumber": "LINUX-LOOP-01",
                "ownerType": "BYOD",
                "lastSyncTime": "2026-09-01T10:00:00Z"
            }
        ],
        "nextPageToken": "cyclic-token-123"
    }

    mock_device_users_resource.list.return_value.execute.return_value = {
        "deviceUsers": [
            {
                "name": "devices/dev-loop/deviceUsers/du-loop",
                "userEmail": "user@example.com",
                "approvalState": "APPROVED"
            }
        ]
    }

    with patch("backend.routes.devices.cloud_identity_service.service", mock_service), \
         patch("backend.routes.devices.directory_service.get_user_chromeos_devices", return_value=[]):
        response = client.get("/api/devices/my-devices")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        # Confirms loop terminated on cyclic token rather than hanging indefinitely
        assert mock_devices_resource.list.call_count == 2

def test_get_my_devices_fast_path_null_devices_triggers_fallback():
    app.dependency_overrides[get_current_user_email] = lambda: "user@example.com"

    mock_service = MagicMock()
    mock_devices_resource = MagicMock()
    mock_device_users_resource = MagicMock()

    mock_service.devices.return_value = mock_devices_resource
    mock_devices_resource.deviceUsers.return_value = mock_device_users_resource

    # Fast path returns {"devices": None}; fallback returns valid device
    def devices_list_side_effect(**kwargs):
        mock_req = MagicMock()
        if kwargs.get("filter"):
            mock_req.execute.return_value = {"devices": None}
        else:
            mock_req.execute.return_value = {
                "devices": [
                    {
                        "name": "devices/dev-fallback-null-recovered",
                        "deviceType": "ANDROID",
                        "model": "Pixel 9 Pro",
                        "serialNumber": "PX9-RECOVERED",
                        "ownerType": "BYOD",
                        "lastSyncTime": "2026-09-08T12:00:00Z"
                    }
                ]
            }
        return mock_req

    mock_devices_resource.list.side_effect = devices_list_side_effect

    mock_device_users_resource.list.return_value.execute.return_value = {
        "deviceUsers": [
            {
                "name": "devices/dev-fallback-null-recovered/deviceUsers/du-1",
                "userEmail": "user@example.com",
                "approvalState": "APPROVED"
            }
        ]
    }

    with patch("backend.routes.devices.cloud_identity_service.service", mock_service), \
         patch("backend.routes.devices.directory_service.get_user_chromeos_devices", return_value=[]):
        response = client.get("/api/devices/my-devices")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["serial_number"] == "PX9-RECOVERED"
        assert len(mock_devices_resource.list.call_args_list) == 2

def test_get_my_devices_partial_device_users_failure_continues_discovery():
    app.dependency_overrides[get_current_user_email] = lambda: "user@example.com"

    mock_service = MagicMock()
    mock_devices_resource = MagicMock()
    mock_device_users_resource = MagicMock()

    mock_service.devices.return_value = mock_devices_resource
    mock_devices_resource.deviceUsers.return_value = mock_device_users_resource

    # Fast-path returns 2 devices. First throws exception on deviceUsers().list, second succeeds
    mock_devices_resource.list.return_value.execute.return_value = {
        "devices": [
            {
                "name": "devices/dev-broken",
                "deviceType": "CHROME_OS",
                "model": "Broken Device",
                "serialNumber": "BROKEN-001",
                "ownerType": "COMPANY",
                "lastSyncTime": "2026-09-01T10:00:00Z"
            },
            {
                "name": "devices/dev-healthy",
                "deviceType": "MAC_OS",
                "model": "MacBook Air",
                "serialNumber": "HEALTHY-002",
                "ownerType": "BYOD",
                "lastSyncTime": "2026-09-01T10:00:00Z"
            }
        ]
    }

    def du_side_effect(parent, customer, pageToken=None):
        if parent == "devices/dev-broken":
            raise RuntimeError("Temporary Cloud Identity RPC failure on broken device")
        mock_req = MagicMock()
        mock_req.execute.return_value = {
            "deviceUsers": [
                {
                    "name": "devices/dev-healthy/deviceUsers/du-healthy",
                    "userEmail": "user@example.com",
                    "approvalState": "APPROVED"
                }
            ]
        }
        return mock_req

    mock_device_users_resource.list.side_effect = du_side_effect

    with patch("backend.routes.devices.cloud_identity_service.service", mock_service), \
         patch("backend.routes.devices.directory_service.get_user_chromeos_devices", return_value=[]):
        response = client.get("/api/devices/my-devices")
        assert response.status_code == 200
        data = response.json()
        # Confirms discovery continued and found healthy device despite first device failing
        assert len(data) == 1
        assert data[0]["serial_number"] == "HEALTHY-002"

def test_get_my_devices_email_case_and_whitespace_normalization():
    app.dependency_overrides[get_current_user_email] = lambda: "  User.MixedCase@EXAMPLE.Com  "

    mock_service = MagicMock()
    mock_devices_resource = MagicMock()
    mock_device_users_resource = MagicMock()

    mock_service.devices.return_value = mock_devices_resource
    mock_devices_resource.deviceUsers.return_value = mock_device_users_resource

    mock_devices_resource.list.return_value.execute.return_value = {
        "devices": [
            {
                "name": "devices/dev-normalized",
                "deviceType": "WINDOWS",
                "model": "Surface Pro",
                "serialNumber": "SURFACE-NORM-1",
                "ownerType": "BYOD",
                "lastSyncTime": "2026-09-01T10:00:00Z"
            }
        ]
    }

    mock_device_users_resource.list.return_value.execute.return_value = {
        "deviceUsers": [
            {
                "name": "devices/dev-normalized/deviceUsers/du-norm",
                "userEmail": "user.mixedcase@example.com",
                "approvalState": "APPROVED"
            }
        ]
    }

    with patch("backend.routes.devices.cloud_identity_service.service", mock_service), \
         patch("backend.routes.devices.directory_service.get_user_chromeos_devices", return_value=[]):
        response = client.get("/api/devices/my-devices")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["serial_number"] == "SURFACE-NORM-1"
        # Filter kwarg was normalized
        assert mock_devices_resource.list.call_args.kwargs.get("filter") == "email:user.mixedcase@example.com"

def test_get_public_config():
    response = client.get("/api/config/public")
    assert response.status_code == 200
    assert "google_client_id" in response.json()

def test_approve_device_success_own_device():
    app.dependency_overrides[get_current_user_email] = lambda: "student@example.com"
    response = client.post("/api/devices/approve", json={"device_user_name": "devices/dev-1/deviceUsers/du-1"})
    assert response.status_code == 200
    assert response.json()["status"] == "SUCCESS"

def test_approve_device_forbidden_other_user_device():
    app.dependency_overrides[get_current_user_email] = lambda: "student@example.com"
    response = client.post("/api/devices/approve", json={"device_user_name": "devices/dev-1/deviceUsers/du-CEO"})
    assert response.status_code == 403
    assert "Access denied" in response.json()["detail"]

def test_approve_device_admin_can_approve_any_device():
    app.dependency_overrides[get_current_user_email] = lambda: "admin@example.com"
    response = client.post("/api/devices/approve", json={"device_user_name": "devices/dev-1/deviceUsers/du-CEO"})
    assert response.status_code == 200
    assert response.json()["status"] == "SUCCESS"

def test_get_current_user_email_iap_spoofing_rejected(monkeypatch):
    monkeypatch.delenv("TRUST_IAP_HEADERS", raising=False)
    with pytest.raises(HTTPException) as exc_info:
        get_current_user_email(authorization=None, x_goog_authenticated_user_email="accounts.google.com:attacker@example.com", x_goog_iap_jwt_assertion=None)
    assert exc_info.value.status_code == 401

def test_get_current_user_email_iap_jwt_accepted(monkeypatch):
    monkeypatch.delenv("TRUST_IAP_HEADERS", raising=False)
    email = get_current_user_email(authorization=None, x_goog_authenticated_user_email="accounts.google.com:admin@example.com", x_goog_iap_jwt_assertion="mock.jwt.token")
    assert email == "admin@example.com"

def test_get_current_user_email_trust_iap_env_override(monkeypatch):
    monkeypatch.setenv("TRUST_IAP_HEADERS", "true")
    email = get_current_user_email(authorization=None, x_goog_authenticated_user_email="accounts.google.com:dev@example.com", x_goog_iap_jwt_assertion=None)
    assert email == "dev@example.com"

@patch("backend.routes.admin.id_token.verify_oauth2_token")
def test_get_current_user_email_bearer_token_audience(mock_verify):
    mock_verify.return_value = {"email": "user@example.com"}
    email = get_current_user_email(authorization="Bearer mock_token_123")
    assert email == "user@example.com"
    assert "audience" in mock_verify.call_args.kwargs

def test_webhook_enrollment_invalid_oidc_token_rejected():
    push_body = {
        "message": {"data": "e30="},
        "subscription": "projects/my-proj/subscriptions/chrome-enroll-sub"
    }
    response = client.post("/api/webhook/chrome-enrollment", headers={"Authorization": "Bearer invalid_oidc_token"}, json=push_body)
    assert response.status_code == 401
    assert "Invalid Pub/Sub push authentication token" in response.json()["detail"]

def test_get_my_devices_empty_email_without_service():
    with patch("backend.routes.devices.cloud_identity_service.service", None):
        app.dependency_overrides[get_current_user_email] = lambda: ""
        response = client.get("/api/devices/my-devices")
        assert response.status_code == 200
        assert response.json() == []

def test_get_my_devices_numeric_fields_handled_gracefully():
    app.dependency_overrides[get_current_user_email] = lambda: "user@example.com"

    mock_service = MagicMock()
    mock_devices_resource = MagicMock()
    mock_device_users_resource = MagicMock()
    mock_service.devices.return_value = mock_devices_resource
    mock_devices_resource.deviceUsers.return_value = mock_device_users_resource

    mock_devices_resource.list.return_value.execute.return_value = {
        "devices": [
            {
                "name": "devices/dev-numeric",
                "deviceType": "ANDROID",
                "model": 100,
                "osVersion": 15,
                "serialNumber": 1234567890,
                "ownerType": "BYOD",
                "lastSyncTime": "2026-09-01T10:00:00Z"
            }
        ]
    }
    mock_device_users_resource.list.return_value.execute.return_value = {
        "deviceUsers": [
            {
                "name": "devices/dev-numeric/deviceUsers/du-1",
                "userEmail": "user@example.com",
                "approvalState": "APPROVED"
            }
        ]
    }

    with patch("backend.routes.devices.cloud_identity_service.service", mock_service), \
         patch("backend.routes.devices.directory_service.verify_user_is_admin", return_value=False), \
         patch("backend.routes.devices.directory_service.get_user_chromeos_devices", return_value=[]):
        response = client.get("/api/devices/my-devices")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["serial_number"] == "1234567890"
        assert data[0]["model"] == "100"
        assert data[0]["os_version"] == "15"

def test_get_my_devices_lowercase_na_timestamp_comparison():
    app.dependency_overrides[get_current_user_email] = lambda: "user@example.com"

    mock_service = MagicMock()
    mock_devices_resource = MagicMock()
    mock_device_users_resource = MagicMock()
    mock_service.devices.return_value = mock_devices_resource
    mock_devices_resource.deviceUsers.return_value = mock_device_users_resource

    # Test ordering 1: First duplicate has valid timestamp, second has "n/a"
    mock_devices_resource.list.return_value.execute.return_value = {
        "devices": [
            {
                "name": "devices/dev-1",
                "deviceType": "MAC_OS",
                "model": "MacBook Pro",
                "serialNumber": "SN-TIMESTAMP-TEST",
                "ownerType": "BYOD",
                "lastSyncTime": "2026-09-08T12:00:00Z"
            },
            {
                "name": "devices/dev-2",
                "deviceType": "MAC_OS",
                "model": "MacBook Pro",
                "serialNumber": "SN-TIMESTAMP-TEST",
                "ownerType": "BYOD",
                "lastSyncTime": "n/a"
            }
        ]
    }
    def du_side(parent, customer, pageToken=None):
        mock_req = MagicMock()
        mock_req.execute.return_value = {
            "deviceUsers": [
                {
                    "name": f"{parent}/deviceUsers/du",
                    "userEmail": "user@example.com",
                    "approvalState": "APPROVED"
                }
            ]
        }
        return mock_req

    mock_device_users_resource.list.side_effect = du_side

    with patch("backend.routes.devices.cloud_identity_service.service", mock_service), \
         patch("backend.routes.devices.directory_service.verify_user_is_admin", return_value=False), \
         patch("backend.routes.devices.directory_service.get_user_chromeos_devices", return_value=[]):
        response = client.get("/api/devices/my-devices")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["last_sync_time"] == "2026-09-08T12:00:00Z"

    # Test ordering 2: First duplicate has "n/a", second has valid timestamp
    mock_devices_resource.list.return_value.execute.return_value = {
        "devices": [
            {
                "name": "devices/dev-1",
                "deviceType": "MAC_OS",
                "model": "MacBook Pro",
                "serialNumber": "SN-TIMESTAMP-TEST",
                "ownerType": "BYOD",
                "lastSyncTime": "n/a"
            },
            {
                "name": "devices/dev-2",
                "deviceType": "MAC_OS",
                "model": "MacBook Pro",
                "serialNumber": "SN-TIMESTAMP-TEST",
                "ownerType": "BYOD",
                "lastSyncTime": "2026-09-08T12:00:00Z"
            }
        ]
    }
    with patch("backend.routes.devices.cloud_identity_service.service", mock_service), \
         patch("backend.routes.devices.directory_service.verify_user_is_admin", return_value=False), \
         patch("backend.routes.devices.directory_service.get_user_chromeos_devices", return_value=[]):
        response = client.get("/api/devices/my-devices")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["last_sync_time"] == "2026-09-08T12:00:00Z"

def test_get_my_devices_virtual_asset_approval_and_company_state_promotion():
    app.dependency_overrides[get_current_user_email] = lambda: "user@example.com"

    mock_service = MagicMock()
    mock_devices_resource = MagicMock()
    mock_device_users_resource = MagicMock()
    mock_service.devices.return_value = mock_devices_resource
    mock_devices_resource.deviceUsers.return_value = mock_device_users_resource

    # Virtual item 1 is COMPANY and APPROVED (synced older)
    # Virtual item 2 is BYOD and PENDING_APPROVAL (synced newer)
    mock_devices_resource.list.return_value.execute.return_value = {
        "devices": [
            {
                "name": "devices/dev-v-company-approved",
                "deviceType": "WINDOWS",
                "model": "Surface Laptop",
                "serialNumber": None,
                "ownerType": "COMPANY",
                "lastSyncTime": "2026-09-01T10:00:00Z"
            },
            {
                "name": "devices/dev-v-byod-pending",
                "deviceType": "WINDOWS",
                "model": "Surface Laptop",
                "serialNumber": None,
                "ownerType": "BYOD",
                "lastSyncTime": "2026-09-08T10:00:00Z"
            }
        ]
    }
    def du_side(parent, customer, pageToken=None):
        mock_req = MagicMock()
        state = "APPROVED" if "approved" in parent else "PENDING_APPROVAL"
        mock_req.execute.return_value = {
            "deviceUsers": [
                {
                    "name": f"{parent}/deviceUsers/du",
                    "userEmail": "user@example.com",
                    "approvalState": state
                }
            ]
        }
        return mock_req

    mock_device_users_resource.list.side_effect = du_side

    with patch("backend.routes.devices.cloud_identity_service.service", mock_service), \
         patch("backend.routes.devices.directory_service.verify_user_is_admin", return_value=False), \
         patch("backend.routes.devices.directory_service.get_user_chromeos_devices", return_value=[]):
        response = client.get("/api/devices/my-devices")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["approval_state"] == "APPROVED"
        assert data[0]["owner_type"] == "COMPANY"
        assert data[0]["last_sync_time"] == "2026-09-08T10:00:00Z"
        assert data[0]["device_user_name"] == "devices/dev-v-company-approved/deviceUsers/du"

def test_get_my_devices_virtual_asset_with_na_serial_deduplicates_against_hardware():
    app.dependency_overrides[get_current_user_email] = lambda: "user@example.com"

    mock_service = MagicMock()
    mock_devices_resource = MagicMock()
    mock_device_users_resource = MagicMock()
    mock_service.devices.return_value = mock_devices_resource
    mock_devices_resource.deviceUsers.return_value = mock_device_users_resource

    # Hardware device and a virtual extension reporting "n/a" as serialNumber
    mock_devices_resource.list.return_value.execute.return_value = {
        "devices": [
            {
                "name": "devices/dev-hw",
                "deviceType": "WINDOWS",
                "model": "ThinkPad X1",
                "serialNumber": "THINKPAD-100",
                "ownerType": "COMPANY",
                "lastSyncTime": "2026-09-01T10:00:00Z"
            },
            {
                "name": "devices/dev-virt",
                "deviceType": "WINDOWS",
                "model": "ThinkPad X1",
                "serialNumber": "n/a",
                "ownerType": "BYOD",
                "lastSyncTime": "2026-09-08T10:00:00Z"
            }
        ]
    }
    def du_side(parent, customer, pageToken=None):
        mock_req = MagicMock()
        mock_req.execute.return_value = {
            "deviceUsers": [
                {
                    "name": f"{parent}/deviceUsers/du",
                    "userEmail": "user@example.com",
                    "approvalState": "APPROVED"
                }
            ]
        }
        return mock_req

    mock_device_users_resource.list.side_effect = du_side

    with patch("backend.routes.devices.cloud_identity_service.service", mock_service), \
         patch("backend.routes.devices.directory_service.verify_user_is_admin", return_value=False), \
         patch("backend.routes.devices.directory_service.get_user_chromeos_devices", return_value=[]):
        response = client.get("/api/devices/my-devices")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["serial_number"] == "THINKPAD-100"
        assert data[0]["owner_type"] == "COMPANY"

def test_get_my_devices_case_insensitive_device_type_deduplication():
    app.dependency_overrides[get_current_user_email] = lambda: "user@example.com"

    mock_service = MagicMock()
    mock_devices_resource = MagicMock()
    mock_device_users_resource = MagicMock()
    mock_service.devices.return_value = mock_devices_resource
    mock_devices_resource.deviceUsers.return_value = mock_device_users_resource

    # Hardware device with uppercase "WINDOWS" and virtual extension with lowercase "windows"
    mock_devices_resource.list.return_value.execute.return_value = {
        "devices": [
            {
                "name": "devices/dev-hw",
                "deviceType": "WINDOWS",
                "model": "ThinkPad",
                "serialNumber": "THINKPAD-CASE-TEST",
                "ownerType": "COMPANY",
                "lastSyncTime": "2026-09-01T10:00:00Z"
            },
            {
                "name": "devices/dev-virt",
                "deviceType": "windows",
                "model": "ThinkPad",
                "serialNumber": None,
                "ownerType": "BYOD",
                "lastSyncTime": "2026-09-08T10:00:00Z"
            }
        ]
    }
    def du_side(parent, customer, pageToken=None):
        mock_req = MagicMock()
        mock_req.execute.return_value = {
            "deviceUsers": [
                {
                    "name": f"{parent}/deviceUsers/du",
                    "userEmail": "user@example.com",
                    "approvalState": "APPROVED"
                }
            ]
        }
        return mock_req

    mock_device_users_resource.list.side_effect = du_side

    with patch("backend.routes.devices.cloud_identity_service.service", mock_service), \
         patch("backend.routes.devices.directory_service.verify_user_is_admin", return_value=False), \
         patch("backend.routes.devices.directory_service.get_user_chromeos_devices", return_value=[]):
        response = client.get("/api/devices/my-devices")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["serial_number"] == "THINKPAD-CASE-TEST"
        assert data[0]["device_type"] == "WINDOWS"

def test_get_my_devices_byod_to_company_promotion_updates_device_user_name():
    app.dependency_overrides[get_current_user_email] = lambda: "user@example.com"

    mock_service = MagicMock()
    mock_devices_resource = MagicMock()
    mock_device_users_resource = MagicMock()
    mock_service.devices.return_value = mock_devices_resource
    mock_devices_resource.deviceUsers.return_value = mock_device_users_resource

    # First record is BYOD, second record is COMPANY for the same serial number
    mock_devices_resource.list.return_value.execute.return_value = {
        "devices": [
            {
                "name": "devices/dev-byod-first",
                "deviceType": "MAC_OS",
                "model": "MacBook Pro",
                "serialNumber": "C02XYZ123",
                "ownerType": "BYOD",
                "lastSyncTime": "2026-09-01T10:00:00Z"
            },
            {
                "name": "devices/dev-company-second",
                "deviceType": "MAC_OS",
                "model": "MacBook Pro",
                "serialNumber": "C02XYZ123",
                "ownerType": "COMPANY",
                "lastSyncTime": "2026-09-02T10:00:00Z"
            }
        ]
    }
    def du_side(parent, customer, pageToken=None):
        mock_req = MagicMock()
        mock_req.execute.return_value = {
            "deviceUsers": [
                {
                    "name": f"{parent}/deviceUsers/du",
                    "userEmail": "user@example.com",
                    "approvalState": "APPROVED"
                }
            ]
        }
        return mock_req

    mock_device_users_resource.list.side_effect = du_side

    with patch("backend.routes.devices.cloud_identity_service.service", mock_service), \
         patch("backend.routes.devices.directory_service.verify_user_is_admin", return_value=False), \
         patch("backend.routes.devices.directory_service.get_user_chromeos_devices", return_value=[]):
        response = client.get("/api/devices/my-devices")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["owner_type"] == "COMPANY"
        assert data[0]["device_user_name"] == "devices/dev-company-second/deviceUsers/du"

def test_get_my_devices_multipage_subsequent_page_failure_preserves_page1_devices():
    app.dependency_overrides[get_current_user_email] = lambda: "user@example.com"

    mock_service = MagicMock()
    mock_devices_resource = MagicMock()
    mock_device_users_resource = MagicMock()
    mock_service.devices.return_value = mock_devices_resource
    mock_devices_resource.deviceUsers.return_value = mock_device_users_resource

    call_count = [0]
    def devices_list_side_effect(**kwargs):
        call_count[0] += 1
        mock_req = MagicMock()
        if call_count[0] == 1:
            mock_req.execute.return_value = {
                "devices": [
                    {
                        "name": "devices/dev-page1",
                        "deviceType": "LINUX",
                        "model": "Workstation",
                        "serialNumber": "LINUX-P1-SURVIVOR",
                        "ownerType": "COMPANY",
                        "lastSyncTime": "2026-09-01T10:00:00Z"
                    }
                ],
                "nextPageToken": "page-2-token"
            }
        else:
            raise RuntimeError("Transient network error on page 2")
        return mock_req

    mock_devices_resource.list.side_effect = devices_list_side_effect

    def du_side(parent, customer, pageToken=None):
        mock_req = MagicMock()
        mock_req.execute.return_value = {
            "deviceUsers": [
                {
                    "name": f"{parent}/deviceUsers/du",
                    "userEmail": "user@example.com",
                    "approvalState": "APPROVED"
                }
            ]
        }
        return mock_req

    mock_device_users_resource.list.side_effect = du_side

    with patch("backend.routes.devices.cloud_identity_service.service", mock_service), \
         patch("backend.routes.devices.directory_service.verify_user_is_admin", return_value=False), \
         patch("backend.routes.devices.directory_service.get_user_chromeos_devices", return_value=[]):
        response = client.get("/api/devices/my-devices")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["serial_number"] == "LINUX-P1-SURVIVOR"

def test_get_my_devices_millisecond_timestamp_deduplication():
    app.dependency_overrides[get_current_user_email] = lambda: "user@example.com"

    mock_service = MagicMock()
    mock_devices_resource = MagicMock()
    mock_device_users_resource = MagicMock()
    mock_service.devices.return_value = mock_devices_resource
    mock_devices_resource.deviceUsers.return_value = mock_device_users_resource

    # First record has seconds-only timestamp (12:00:00Z)
    # Second record has milliseconds timestamp (12:00:00.500Z, which is 500ms newer)
    mock_devices_resource.list.return_value.execute.return_value = {
        "devices": [
            {
                "name": "devices/dev-sec",
                "deviceType": "MAC_OS",
                "model": "MacBook Pro",
                "serialNumber": "SN-MS-TEST",
                "ownerType": "BYOD",
                "lastSyncTime": "2026-09-08T12:00:00Z"
            },
            {
                "name": "devices/dev-ms",
                "deviceType": "MAC_OS",
                "model": "MacBook Pro",
                "serialNumber": "SN-MS-TEST",
                "ownerType": "BYOD",
                "lastSyncTime": "2026-09-08T12:00:00.500Z"
            }
        ]
    }
    def du_side(parent, customer, pageToken=None):
        mock_req = MagicMock()
        mock_req.execute.return_value = {
            "deviceUsers": [
                {
                    "name": f"{parent}/deviceUsers/du",
                    "userEmail": "user@example.com",
                    "approvalState": "APPROVED"
                }
            ]
        }
        return mock_req

    mock_device_users_resource.list.side_effect = du_side

    with patch("backend.routes.devices.cloud_identity_service.service", mock_service), \
         patch("backend.routes.devices.directory_service.verify_user_is_admin", return_value=False), \
         patch("backend.routes.devices.directory_service.get_user_chromeos_devices", return_value=[]):
        response = client.get("/api/devices/my-devices")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["last_sync_time"] == "2026-09-08T12:00:00.500Z"
        assert data[0]["device_user_name"] == "devices/dev-ms/deviceUsers/du"

def test_get_my_devices_zero_integer_fields_preserved():
    app.dependency_overrides[get_current_user_email] = lambda: "user@example.com"

    mock_service = MagicMock()
    mock_devices_resource = MagicMock()
    mock_device_users_resource = MagicMock()
    mock_service.devices.return_value = mock_devices_resource
    mock_devices_resource.deviceUsers.return_value = mock_device_users_resource

    # Fields set to integer 0 (falsy in python)
    mock_devices_resource.list.return_value.execute.return_value = {
        "devices": [
            {
                "name": "devices/dev-zero",
                "deviceType": "LINUX",
                "model": 0,
                "osVersion": 0,
                "serialNumber": 0,
                "ownerType": "BYOD",
                "lastSyncTime": "2026-09-08T12:00:00Z"
            }
        ]
    }
    mock_device_users_resource.list.return_value.execute.return_value = {
        "deviceUsers": [
            {
                "name": "devices/dev-zero/deviceUsers/du-1",
                "userEmail": "user@example.com",
                "approvalState": "APPROVED"
            }
        ]
    }

    with patch("backend.routes.devices.cloud_identity_service.service", mock_service), \
         patch("backend.routes.devices.directory_service.verify_user_is_admin", return_value=False), \
         patch("backend.routes.devices.directory_service.get_user_chromeos_devices", return_value=[]):
        response = client.get("/api/devices/my-devices")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["serial_number"] == "0"
        assert data[0]["model"] == "0"
        assert data[0]["os_version"] == "0"

def test_get_my_devices_management_state_unspecified_resolves_to_approval_state():
    app.dependency_overrides[get_current_user_email] = lambda: "user@example.com"

    mock_service = MagicMock()
    mock_devices_resource = MagicMock()
    mock_device_users_resource = MagicMock()
    mock_service.devices.return_value = mock_devices_resource
    mock_devices_resource.deviceUsers.return_value = mock_device_users_resource

    mock_devices_resource.list.return_value.execute.return_value = {
        "devices": [
            {
                "name": "devices/dev-unspecified",
                "deviceType": "WINDOWS",
                "model": "ThinkPad",
                "serialNumber": "SN-UNSPECIFIED-TEST",
                "ownerType": "BYOD",
                "lastSyncTime": "2026-09-08T12:00:00Z"
            }
        ]
    }
    # managementState is MANAGEMENT_STATE_UNSPECIFIED, approvalState is APPROVED
    mock_device_users_resource.list.return_value.execute.return_value = {
        "deviceUsers": [
            {
                "name": "devices/dev-unspecified/deviceUsers/du-1",
                "userEmail": "user@example.com",
                "managementState": "MANAGEMENT_STATE_UNSPECIFIED",
                "approvalState": "APPROVED"
            }
        ]
    }

    with patch("backend.routes.devices.cloud_identity_service.service", mock_service), \
         patch("backend.routes.devices.directory_service.verify_user_is_admin", return_value=False), \
         patch("backend.routes.devices.directory_service.get_user_chromeos_devices", return_value=[]):
        response = client.get("/api/devices/my-devices")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["approval_state"] == "APPROVED"

def test_get_my_devices_company_duplicate_pending_promoted_to_company_approved_binding():
    app.dependency_overrides[get_current_user_email] = lambda: "user@example.com"

    mock_service = MagicMock()
    mock_devices_resource = MagicMock()
    mock_device_users_resource = MagicMock()
    mock_service.devices.return_value = mock_devices_resource
    mock_devices_resource.deviceUsers.return_value = mock_device_users_resource

    # Two COMPANY records for same serial: first is PENDING, second is APPROVED
    mock_devices_resource.list.return_value.execute.return_value = {
        "devices": [
            {
                "name": "devices/dev-comp-pending",
                "deviceType": "MAC_OS",
                "model": "MacBook Pro",
                "serialNumber": "COMP-PROMO-123",
                "ownerType": "COMPANY",
                "lastSyncTime": "2026-09-08T12:00:00Z"
            },
            {
                "name": "devices/dev-comp-approved",
                "deviceType": "MAC_OS",
                "model": "MacBook Pro",
                "serialNumber": "COMP-PROMO-123",
                "ownerType": "COMPANY",
                "lastSyncTime": "2026-09-08T10:00:00Z"
            }
        ]
    }
    def du_side(parent, customer, pageToken=None):
        mock_req = MagicMock()
        state = "PENDING_APPROVAL" if "pending" in parent else "APPROVED"
        mock_req.execute.return_value = {
            "deviceUsers": [
                {
                    "name": f"{parent}/deviceUsers/du",
                    "userEmail": "user@example.com",
                    "approvalState": state
                }
            ]
        }
        return mock_req

    mock_device_users_resource.list.side_effect = du_side

    with patch("backend.routes.devices.cloud_identity_service.service", mock_service), \
         patch("backend.routes.devices.directory_service.verify_user_is_admin", return_value=False), \
         patch("backend.routes.devices.directory_service.get_user_chromeos_devices", return_value=[]):
        response = client.get("/api/devices/my-devices")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["owner_type"] == "COMPANY"
        assert data[0]["approval_state"] == "APPROVED"
        assert data[0]["device_user_name"] == "devices/dev-comp-approved/deviceUsers/du"

def test_get_my_devices_missing_name_on_device_user_synthesizes_name():
    app.dependency_overrides[get_current_user_email] = lambda: "user@example.com"

    mock_service = MagicMock()
    mock_devices_resource = MagicMock()
    mock_device_users_resource = MagicMock()
    mock_service.devices.return_value = mock_devices_resource
    mock_devices_resource.deviceUsers.return_value = mock_device_users_resource

    mock_devices_resource.list.return_value.execute.return_value = {
        "devices": [
            {
                "name": "devices/dev-noname",
                "deviceType": "WINDOWS",
                "model": "Dell XPS",
                "serialNumber": "DELL-SYNTH-1",
                "ownerType": "BYOD",
                "lastSyncTime": "2026-09-08T12:00:00Z"
            }
        ]
    }
    # deviceUser has no "name" attribute
    mock_device_users_resource.list.return_value.execute.return_value = {
        "deviceUsers": [
            {
                "userEmail": "user@example.com",
                "approvalState": "APPROVED"
            }
        ]
    }

    with patch("backend.routes.devices.cloud_identity_service.service", mock_service), \
         patch("backend.routes.devices.directory_service.verify_user_is_admin", return_value=False), \
         patch("backend.routes.devices.directory_service.get_user_chromeos_devices", return_value=[]):
        response = client.get("/api/devices/my-devices")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["device_user_name"] == "devices/dev-noname/deviceUsers/user@example.com"

def test_revoke_directory_chromebook_returns_403_forbidden():
    app.dependency_overrides[get_current_user_email] = lambda: "user@example.com"

    mock_service = MagicMock()
    with patch("backend.routes.devices.cloud_identity_service.service", mock_service), \
         patch("backend.routes.devices.directory_service.verify_user_is_admin", return_value=False):
        response = client.post(
            "/api/devices/revoke",
            json={"device_user_name": "directory/devices/CB-100/deviceUsers/user@example.com"}
        )
        assert response.status_code == 403
        assert "Company-owned trust anchors cannot be revoked" in response.json()["detail"]

def test_revoke_bulk_filters_directory_chromebooks():
    app.dependency_overrides[get_current_user_email] = lambda: "user@example.com"

    mock_service = MagicMock()
    with patch("backend.routes.devices.cloud_identity_service.service", mock_service), \
         patch("backend.routes.devices.directory_service.verify_user_is_admin", return_value=False):
        response = client.post(
            "/api/devices/revoke-bulk",
            json={"device_user_names": ["directory/devices/CB-100/deviceUsers/user@example.com"]}
        )
        assert response.status_code == 200
        assert response.json()["revoked_count"] == 0
        assert "No eligible BYOD devices to revoke" in response.json()["message"]

def test_get_my_devices_directory_chromebook_millisecond_timestamp_enrichment():
    app.dependency_overrides[get_current_user_email] = lambda: "user@example.com"

    mock_service = MagicMock()
    mock_devices_resource = MagicMock()
    mock_device_users_resource = MagicMock()
    mock_service.devices.return_value = mock_devices_resource
    mock_devices_resource.deviceUsers.return_value = mock_device_users_resource

    # Cloud Identity asset with seconds-only timestamp
    mock_devices_resource.list.return_value.execute.return_value = {
        "devices": [
            {
                "name": "devices/dev-cros",
                "deviceType": "CHROME_OS",
                "model": "Chromebook",
                "serialNumber": "CROS-MS-1",
                "ownerType": "COMPANY",
                "lastSyncTime": "2026-09-08T12:00:00Z"
            }
        ]
    }
    mock_device_users_resource.list.return_value.execute.return_value = {
        "deviceUsers": [
            {
                "name": "devices/dev-cros/deviceUsers/du",
                "userEmail": "user@example.com",
                "approvalState": "APPROVED"
            }
        ]
    }

    # Directory Chromebook has same serial but with milliseconds (12:00:00.800Z)
    directory_cbs = [
        {
            "serial_number": "CROS-MS-1",
            "model": "Enterprise Chromebook Pro",
            "os_version": "ChromeOS 124.0",
            "last_sync_time": "2026-09-08T12:00:00.800Z"
        }
    ]

    with patch("backend.routes.devices.cloud_identity_service.service", mock_service), \
         patch("backend.routes.devices.directory_service.verify_user_is_admin", return_value=False), \
         patch("backend.routes.devices.directory_service.get_user_chromeos_devices", return_value=directory_cbs):
        response = client.get("/api/devices/my-devices")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["last_sync_time"] == "2026-09-08T12:00:00.800Z"
        assert data[0]["model"] == "Enterprise Chromebook Pro"

def test_get_my_devices_virtual_timezone_offset_sorting():
    app.dependency_overrides[get_current_user_email] = lambda: "user@example.com"

    mock_service = MagicMock()
    mock_devices_resource = MagicMock()
    mock_device_users_resource = MagicMock()
    mock_service.devices.return_value = mock_devices_resource
    mock_devices_resource.deviceUsers.return_value = mock_device_users_resource

    # Virtual device 1: 07:00:00-05:00 (= 12:00:00 UTC)
    # Virtual device 2: 11:00:00Z (= 11:00:00 UTC, older by 1 hour)
    mock_devices_resource.list.return_value.execute.return_value = {
        "devices": [
            {
                "name": "devices/dev-v-older-utc",
                "deviceType": "MAC_OS",
                "model": "MacBook Air",
                "serialNumber": None,
                "ownerType": "BYOD",
                "lastSyncTime": "2026-09-08T11:00:00Z"
            },
            {
                "name": "devices/dev-v-newer-offset",
                "deviceType": "MAC_OS",
                "model": "MacBook Pro",
                "serialNumber": None,
                "ownerType": "BYOD",
                "lastSyncTime": "2026-09-08T07:00:00-05:00"
            }
        ]
    }
    def du_side(parent, customer, pageToken=None):
        mock_req = MagicMock()
        mock_req.execute.return_value = {
            "deviceUsers": [
                {
                    "name": f"{parent}/deviceUsers/du",
                    "userEmail": "user@example.com",
                    "approvalState": "APPROVED"
                }
            ]
        }
        return mock_req

    mock_device_users_resource.list.side_effect = du_side

    with patch("backend.routes.devices.cloud_identity_service.service", mock_service), \
         patch("backend.routes.devices.directory_service.verify_user_is_admin", return_value=False), \
         patch("backend.routes.devices.directory_service.get_user_chromeos_devices", return_value=[]):
        response = client.get("/api/devices/my-devices")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["device_user_name"] == "devices/dev-v-newer-offset/deviceUsers/du"
        assert data[0]["last_sync_time"] == "2026-09-08T07:00:00-05:00"
