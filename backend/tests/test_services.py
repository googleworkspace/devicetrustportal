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
    assert config.revocation_action == "DELETE"
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
    assert res_del == {}

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
