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
    assert config.chaining_allowed_groups == []
    assert config.chaining_allowed_ous == []

@patch("backend.services.directory_service.DirectoryService")
def test_directory_admin_verification(mock_dir):
    mock_service = MagicMock()
    mock_service.users().get().execute.return_value = {"isAdmin": True}
    directory_service.service = mock_service

    assert directory_service.verify_user_is_admin("admin@example.com") == True

@patch("backend.services.directory_service.DirectoryService")
def test_directory_hierarchical_chaining_policy(mock_dir):
    mock_service = MagicMock()
    # Mock group member exists
    mock_service.members().get().execute.return_value = {"status": "ACTIVE"}
    directory_service.service = mock_service

    allowed_groups = ["trust-chaining-allowed@example.com"]
    allowed_ous = ["/Staff", "/Faculty"]

    assert directory_service.get_user_chaining_policy(
        "trust-chaining-allowed@example.com", allowed_groups, allowed_ous
    ) == True

@patch("backend.services.cloud_identity.CloudIdentityService")
def test_cloud_identity_approve(mock_ci):
    mock_service = MagicMock()
    mock_service.devices().deviceUsers().approve().execute.return_value = {"done": True, "response": {"status": "APPROVED"}}
    cloud_identity_service.service = mock_service

    res = cloud_identity_service.approve_device_user("devices/dev-1/deviceUsers/du-1", "customers/my_customer")
    assert res["done"] == True
    assert res["response"]["status"] == "APPROVED"

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
