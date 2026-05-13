import pytest
from backend.services.config_service import config_service, TenantConfig
from backend.services.directory_service import directory_service
from backend.services.cloud_identity import cloud_identity_service

def test_tenant_config_defaults():
    config = config_service.get_tenant_config()
    assert config.customer_id == "customers/my_customer"
    assert config.inactivity_threshold_days == 90
    assert "127.0.0.1/32" in config.trusted_ip_ranges

def test_directory_admin_verification():
    # Test mock admin verification
    assert directory_service.verify_user_is_admin("admin@example.com") == True
    assert directory_service.verify_user_is_admin("student@example.com") == False

def test_directory_hierarchical_chaining_policy():
    allowed_groups = ["trust-chaining-allowed@example.com"]
    allowed_ous = ["/Staff", "/Faculty"]

    # User in allowed group should be approved (Group override)
    assert directory_service.get_user_chaining_policy(
        "trust-chaining-allowed@example.com", allowed_groups, allowed_ous
    ) == True

    # User not in allowed group or OU
    assert directory_service.get_user_chaining_policy(
        "student@example.com", allowed_groups, allowed_ous
    ) == False

def test_cloud_identity_approve_mock():
    res = cloud_identity_service.approve_device_user("devices/dev-1/deviceUsers/du-1", "customers/my_customer")
    assert res["done"] == True
    assert res["response"]["status"] == "APPROVED"

def test_cloud_identity_lookup_mock():
    res = cloud_identity_service.lookup_device_user("user@example.com", "pixel-99", "customers/my_customer")
    assert res == "devices/mock-device-pixel-99/deviceUsers/mock-user-user-example.com"

def test_cloud_identity_parse_ev_header():
    ev_header = "some-metadata devices/pixel-123/deviceUsers/du-99 some-other-data"
    parsed = cloud_identity_service.parse_endpoint_verification_header(ev_header)
    assert parsed == "devices/pixel-123/deviceUsers/du-99"
