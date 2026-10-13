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
from unittest.mock import MagicMock, patch
from backend.services.config_service import config_service, TenantConfig
from backend.services.directory_service import directory_service
from backend.services.cloud_identity import cloud_identity_service

def test_tenant_config_defaults():
    config = config_service.get_tenant_config()
    assert config.customer_id == "customers/my_customer"
    assert config.inactivity_threshold_days == 90
    assert config.trusted_ip_ranges == []
    assert config.revocation_action == "BLOCK"
    assert config.google_client_id == ""
    assert config.default_locale == "en"
    assert config.chaining_allowed_groups == []
    assert config.chaining_allowed_ous == []

@patch("backend.services.directory_service.DirectoryService")
def test_directory_admin_verification(mock_dir, monkeypatch):
    mock_service = MagicMock()
    mock_service.users().get().execute.return_value = {"isAdmin": True}
    directory_service.service = mock_service

    assert directory_service.verify_user_is_admin("admin@example.com") == True

    monkeypatch.setenv("WORKSPACE_ADMIN_EMAIL", "deployer@example.com")
    assert directory_service.verify_user_is_admin("deployer@example.com") == True

@patch("backend.services.directory_service.DirectoryService")
def test_directory_hierarchical_chaining_policy_group_match(mock_dir):
    mock_service = MagicMock()
    # Mock OU check to not match
    mock_service.users().get().execute.return_value = {"orgUnitPath": "/Other"}
    # Mock Group check to match
    mock_service.members().hasMember().execute.return_value = {"isMember": True}
    directory_service.service = mock_service

    allowed_groups = ["trust-chaining-allowed@example.com"]
    allowed_ous = ["/Staff", "/Faculty"]

    assert directory_service.get_user_chaining_policy(
        "user@example.com", allowed_groups, allowed_ous
    ) == True

@patch("backend.services.directory_service.DirectoryService")
def test_directory_hierarchical_chaining_policy_ou_match(mock_dir):
    mock_service = MagicMock()
    # Mock OU check to match
    mock_service.users().get().execute.return_value = {"orgUnitPath": "/Staff"}
    directory_service.service = mock_service

    allowed_groups = ["trust-chaining-allowed@example.com"]
    allowed_ous = ["/Staff", "/Faculty"]

    assert directory_service.get_user_chaining_policy(
        "user@example.com", allowed_groups, allowed_ous
    ) == True

@patch("backend.services.directory_service.DirectoryService")
def test_directory_hierarchical_chaining_policy_no_match(mock_dir):
    mock_service = MagicMock()
    # Mock OU check to not match
    mock_service.users().get().execute.return_value = {"orgUnitPath": "/Other"}
    # Mock Group check to not match
    mock_service.members().hasMember().execute.return_value = {"isMember": False}
    directory_service.service = mock_service

    allowed_groups = ["trust-chaining-allowed@example.com"]
    allowed_ous = ["/Staff", "/Faculty"]

    assert directory_service.get_user_chaining_policy(
        "user@example.com", allowed_groups, allowed_ous
    ) == False

@patch("backend.services.cloud_identity.CloudIdentityService")
def test_cloud_identity_approve(mock_ci):
    mock_service = MagicMock()
    mock_service.devices().deviceUsers().approve().execute.return_value = {"done": True, "response": {"status": "APPROVED"}}
    cloud_identity_service.service = mock_service

    res = cloud_identity_service.approve_device_user("devices/dev-1/deviceUsers/du-1", "customers/my_customer")
    assert res["done"] == True
    assert res["response"]["status"] == "APPROVED"

@patch("backend.services.cloud_identity.CloudIdentityService")
def test_cloud_identity_revoke_actions(mock_ci):
    mock_service = MagicMock()
    mock_service.devices().deviceUsers().block().execute.return_value = {"done": True, "response": {"status": "BLOCKED"}}
    mock_service.devices().deviceUsers().delete().execute.return_value = {}
    cloud_identity_service.service = mock_service

    res_block = cloud_identity_service.revoke_device_user("devices/dev-1/deviceUsers/du-1", "customers/my_customer", action="BLOCK")
    assert res_block["response"]["status"] == "BLOCKED"

    res_del = cloud_identity_service.revoke_device_user("devices/dev-1/deviceUsers/du-1", "customers/my_customer", action="DELETE")
    assert res_del["response"]["status"] == "BLOCKED"

@patch("backend.services.cloud_identity.CloudIdentityService")
def test_cloud_identity_lookup(mock_ci):
    mock_service = MagicMock()
    mock_service.devices().list().execute.return_value = {"devices": [{"name": "devices/dev-1"}]}
    mock_service.devices().deviceUsers().list().execute.return_value = {
        "deviceUsers": [{"name": "devices/dev-1/deviceUsers/du-1", "userEmail": "user@example.com"}]
    }
    cloud_identity_service.service = mock_service

    res = cloud_identity_service.lookup_device_user("user@example.com", "pixel-99", "customers/my_customer")
    assert res == "devices/dev-1/deviceUsers/du-1"

def test_cloud_identity_parse_ev_header():
    ev_header = "some-metadata devices/pixel-123/deviceUsers/du-99 some-other-data"
    parsed = cloud_identity_service.parse_endpoint_verification_header(ev_header)
    assert parsed == "devices/pixel-123/deviceUsers/du-99"

@patch("backend.services.directory_service.DirectoryService")
def test_directory_get_user_chromeos_devices(mock_dir):
    mock_service = MagicMock()
    mock_service.chromeosdevices().list().execute.return_value = {
        "chromeosdevices": [
            {
                "deviceId": "dev-cb-101",
                "serialNumber": "CB-SERIAL-101",
                "model": "HP Chromebook 14",
                "osVersion": "ChromeOS 120.0",
                "annotatedUser": "student@example.com",
                "recentUsers": [{"email": "student@example.com"}],
                "lastSync": "2026-08-31T10:00:00Z"
            },
            {
                "deviceId": "dev-cb-102",
                "serialNumber": "CB-SERIAL-102",
                "model": "Dell Chromebook 3100",
                "osVersion": "ChromeOS 120.0",
                "annotatedUser": "other@example.com",
                "recentUsers": [{"email": "other@example.com"}],
                "lastSync": "2026-08-31T10:00:00Z"
            }
        ]
    }
    directory_service.service = mock_service

    # Query for student@example.com
    devices = directory_service.get_user_chromeos_devices("student@example.com", "customers/my_customer", is_admin=False)
    assert len(devices) == 1
    assert devices[0]["serial_number"] == "CB-SERIAL-101"
    assert devices[0]["owner_type"] == "COMPANY"
    assert devices[0]["approval_state"] == "APPROVED"

    # Admin query also returns only devices actually accessed by that admin (in recentUsers)
    admin_devices = directory_service.get_user_chromeos_devices("admin@example.com", "customers/my_customer", is_admin=True)
    assert len(admin_devices) == 0


def test_directory_chromeos_broken_pipe_retry_and_cache():
    mock_service = MagicMock()
    chromeos_payload = {
        "chromeosdevices": [
            {
                "deviceId": "cb-retry-1",
                "serialNumber": "CB-RETRY-101",
                "model": "Lenovo 10e Chromebook Tablet",
                "osVersion": "ChromeOS 151.0",
                "annotatedUser": "",
                "recentUsers": [{"email": "claycodes@gwfe.org"}],
                "lastSync": "2026-10-12T16:03:00Z",
            },
            {
                "deviceId": "cb-retry-2",
                "serialNumber": "CB-RETRY-102",
                "model": "Google Pixelbook Go",
                "osVersion": "ChromeOS 151.0",
                "annotatedUser": "claycodes@gwfe.org",
                "recentUsers": [],
                "lastSync": "2026-10-12T16:04:00Z",
            },
        ]
    }
    # First .execute() raises [Errno 32] Broken pipe (idle httplib2 socket), second succeeds
    mock_service.chromeosdevices().list().execute.side_effect = [
        BrokenPipeError(32, "Broken pipe"),
        chromeos_payload,
    ]
    directory_service.service = mock_service

    devices = directory_service.get_user_chromeos_devices("claycodes@gwfe.org", "customers/my_customer")
    assert len(devices) == 2
    assert {d["serial_number"] for d in devices} == {"CB-RETRY-101", "CB-RETRY-102"}

    # If a later call fails all retries on the same service instance, fallback cache returns the 2 devices
    mock_service.chromeosdevices().list().execute.side_effect = RuntimeError("Upstream unavailable")
    cached_devices = directory_service.get_user_chromeos_devices("claycodes@gwfe.org", "customers/my_customer")
    assert len(cached_devices) == 2


def test_session_guard_reauth_zero_ip_and_refresh_attestation():
    from backend.services.session_guard import SessionGuardService, LoginAuditEvent

    guard = SessionGuardService(enabled=True, grace_window_sec=15, attestation_ttl_sec=300)
    guard.promote_approved_device(
        device_id="devices/cros-1",
        serial_number="CROS-APPROVED-1",
        user_email="claycodes@gwfe.org",
        ip_address="108.6.43.131",
        now_epoch=1000.0,
        device_type="CHROMEOS",
    )

    # Admin SDK Reports API emits login_type=reauth with ip_address='0.0.0.0' 30s after sign-in
    reauth_event = LoginAuditEvent(
        event_id="claycodes@gwfe.org:reauth-1",
        user_email="claycodes@gwfe.org",
        ip_address="0.0.0.0",
        timestamp_epoch=1030.0,
        login_type="reauth",
    )
    actions = guard.evaluate_login_batch(
        [reauth_event],
        now_epoch=1045.0,
        persist_all_allowed=True,
    )
    assert len(actions) == 1
    assert actions[0].decision == "ALLOW_ATTESTED"
    assert actions[0].matched_serial == "CROS-APPROVED-1"

    # Refreshing attestation at t=1250 keeps the session attested past the original 1300 expiry
    assert guard.refresh_user_attestation("claycodes@gwfe.org", ip_address="108.6.43.131", now_epoch=1250.0) is True
    later_reauth = LoginAuditEvent(
        event_id="claycodes@gwfe.org:reauth-2",
        user_email="claycodes@gwfe.org",
        ip_address="0.0.0.0",
        timestamp_epoch=1400.0,
        login_type="reauth",
    )
    actions2 = guard.evaluate_login_batch(
        [later_reauth],
        now_epoch=1420.0,
        persist_all_allowed=True,
    )
    assert len(actions2) == 1
    assert actions2[0].decision == "ALLOW_ATTESTED"


def test_portal_token_expired_within_24h_accepted_unless_signed_out():
    from unittest.mock import patch
    from fastapi import HTTPException
    import pytest
    from backend.routes.admin import get_current_user_email, PORTAL_SESSION_CLOCK_SKEW_SEC
    from backend.routes.session_watch import session_guard

    def fake_verify(token, request, audience=None, clock_skew_in_seconds=0):
        if clock_skew_in_seconds == 0:
            raise ValueError("Token expired, 1791824630 < 1791824657")
        assert clock_skew_in_seconds == PORTAL_SESSION_CLOCK_SKEW_SEC
        return {"email": "claycodes@gwfe.org", "iat": 1791821030}

    session_guard._recent_signouts.pop("claycodes@gwfe.org", None)
    with patch("backend.routes.admin.id_token.verify_oauth2_token", side_effect=fake_verify):
        email = get_current_user_email(authorization="Bearer expired-60m-jwt")
        assert email == "claycodes@gwfe.org"

        # If Session Guard revokes the user's session after iat, get_current_user_email must reject with 401
        session_guard._recent_signouts["claycodes@gwfe.org"] = 1791822000.0
        with pytest.raises(HTTPException) as exc_info:
            get_current_user_email(authorization="Bearer expired-60m-jwt")
        assert exc_info.value.status_code == 401
    session_guard._recent_signouts.pop("claycodes@gwfe.org", None)


