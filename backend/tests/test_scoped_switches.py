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

"""Unit tests for Scoped Admin Switches and Hierarchical OU/Group Policies in devicetrustportal."""

import time
import unittest
from unittest.mock import MagicMock, patch

try:
    from backend.services.config_service import TenantConfig
except ImportError:
    TenantConfig = None
from backend.services.directory_service import DirectoryService
from backend.services.session_guard import (
    DeviceRecord,
    LoginAuditEvent,
    SessionGuardService,
    TokenAuditEvent,
)


class TestScopedAdminSwitches(unittest.TestCase):
    """Test suite covering hierarchical OU matching, negative deny lists, and admin switches."""

    def setUp(self):
        # Create an unauthenticated directory service instance for unit testing
        with patch.object(DirectoryService, "__init__", lambda self: None):
            self.dir_service = DirectoryService()
            self.dir_service.service = None
            self.dir_service._user_cache = {}
            self.dir_service._group_cache = {}

    def test_hierarchical_ou_matching(self):
        """Verifies boundary-safe hierarchical OU matching."""
        # Exact match
        self.assertTrue(self.dir_service.is_ou_matching("/Staff", "/Staff"))
        self.assertTrue(self.dir_service.is_ou_matching("Staff", "/Staff"))
        self.assertTrue(self.dir_service.is_ou_matching("/Staff/HighSchool", "/Staff"))
        self.assertTrue(self.dir_service.is_ou_matching("/Staff/HighSchool/Science", "/Staff"))
        self.assertTrue(self.dir_service.is_ou_matching("/Staff/HighSchool/Science", "/Staff/HighSchool"))

        # Root OU matches all
        self.assertTrue(self.dir_service.is_ou_matching("/Staff", "/"))
        self.assertTrue(self.dir_service.is_ou_matching("/Students/Grade10", "/"))

        # Boundary safety: substring prefix without boundary slash MUST NOT match
        self.assertFalse(self.dir_service.is_ou_matching("/Staff-Temp", "/Staff"))
        self.assertFalse(self.dir_service.is_ou_matching("/StaffContractors", "/Staff"))
        self.assertFalse(self.dir_service.is_ou_matching("/Students", "/Staff"))
        self.assertFalse(self.dir_service.is_ou_matching("", "/Staff"))
        self.assertFalse(self.dir_service.is_ou_matching("/Staff", ""))

    def test_policy_authorization_master_switch_disabled(self):
        """Verifies that if the master admin switch is OFF, access is rejected immediately."""
        is_auth, reason = self.dir_service.evaluate_feature_authorization(
            user_email="teacher@school.edu",
            feature_name="Network-Gated Approval",
            feature_enabled=False,
            allowed_ous=["/Staff"],
            allowed_groups=[],
        )
        self.assertFalse(is_auth)
        self.assertIn("disabled by domain policy", reason)

    def test_policy_authorization_negative_deny_override(self):
        """Verifies that an explicit negative deny rule overrides any allow rule."""
        self.dir_service._user_cache["student_aide@school.edu"] = {
            "orgUnitPath": "/Students/Aides",
            "isAdmin": False,
            "_cached_at": time.time(),
        }

        # User is in group "assistants@school.edu" (allowed) but OU is "/Students" (denied)
        self.dir_service._group_cache["student_aide@school.edu::assistants@school.edu"] = {
            "is_member": True,
            "_cached_at": time.time(),
        }

        is_auth, reason = self.dir_service.evaluate_feature_authorization(
            user_email="student_aide@school.edu",
            feature_name="Trust Chaining",
            feature_enabled=True,
            allowed_ous=[],
            allowed_groups=["assistants@school.edu"],
            denied_ous=["/Students"],
            denied_groups=[],
        )
        self.assertFalse(is_auth)
        self.assertIn("explicitly denied by policy", reason)

    def test_policy_authorization_hierarchical_staff_allow(self):
        """Verifies that a teacher in a nested department OU matches the parent /Staff rule."""
        self.dir_service._user_cache["teacher@school.edu"] = {
            "orgUnitPath": "/Staff/HighSchool/Science",
            "isAdmin": False,
            "_cached_at": time.time(),
        }

        is_auth, reason = self.dir_service.evaluate_feature_authorization(
            user_email="teacher@school.edu",
            feature_name="Network-Gated Approval",
            feature_enabled=True,
            allowed_ous=["/Staff"],
            allowed_groups=[],
        )
        self.assertTrue(is_auth)
        self.assertIn("Authorized for 'Network-Gated Approval' via OU '/Staff/HighSchool/Science'", reason)

    def test_policy_authorization_student_unmatched(self):
        """Verifies that a student is blocked when feature is scoped to /Staff."""
        self.dir_service._user_cache["student@school.edu"] = {
            "orgUnitPath": "/Students/Grade11",
            "isAdmin": False,
            "_cached_at": time.time(),
        }

        is_auth, reason = self.dir_service.evaluate_feature_authorization(
            user_email="student@school.edu",
            feature_name="Network-Gated Approval",
            feature_enabled=True,
            allowed_ous=["/Staff"],
            allowed_groups=["faculty@school.edu"],
        )
        self.assertFalse(is_auth)
        self.assertIn("is not in authorized OUs or Groups", reason)

    def test_session_guard_ou_exemptions(self):
        """Verifies that Session Guard respects OU exemptions and does not sign out exempt admins/staff."""
        user_ous = {
            "superadmin@school.edu": "/Admins/SuperAdmins",
            "principal@school.edu": "/Staff/Leadership",
            "student_rogue@school.edu": "/Students/HighSchool",
        }
        signout_calls = []

        guard = SessionGuardService(
            enabled=True,
            exempt_ous=["/Admins", "/Staff/Leadership"],
            user_ou_lookup=lambda email: user_ous.get(email, "/Students"),
            signout_callback=lambda email: signout_calls.append(email) or True,
        )

        # 1. Unattested login from superadmin in exempt OU -> MUST NOT sign out
        admin_event = LoginAuditEvent(
            event_id="ev_admin",
            user_email="superadmin@school.edu",
            ip_address="198.51.100.1",
            timestamp_epoch=time.time() - 100,  # past grace window
        )
        actions = guard.evaluate_login_batch([admin_event], persist_all_allowed=True)
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0].decision, "ALLOW_EXEMPT")
        self.assertIn("exempt OU '/Admins/SuperAdmins'", actions[0].reason)
        self.assertEqual(len(signout_calls), 0)

        # 2. Unattested login from student in non-exempt OU -> MUST trigger sign out
        student_event = LoginAuditEvent(
            event_id="ev_student",
            user_email="student_rogue@school.edu",
            ip_address="198.51.100.99",
            timestamp_epoch=time.time() - 100,  # past grace window
        )
        actions = guard.evaluate_login_batch([student_event])
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0].decision, "REVOKE_SIGN_OUT")
        self.assertEqual(signout_calls, ["student_rogue@school.edu"])

    @unittest.skipIf(TenantConfig is None, "pydantic not installed in environment")
    def test_tenant_config_scoped_switches_schema(self):
        """Verifies TenantConfig default values and serialization for all 3 switches."""
        cfg = TenantConfig()
        self.assertFalse(cfg.enable_network_approval)
        self.assertEqual(cfg.network_approval_allowed_ous, [])
        self.assertFalse(cfg.enable_trust_chaining)
        self.assertEqual(cfg.chaining_denied_ous, [])
        self.assertFalse(cfg.enable_session_guard)
        self.assertEqual(cfg.session_guard_mode, "DISABLED")
        self.assertEqual(cfg.session_guard_exempt_ous, [])

        custom_cfg = TenantConfig(
            enable_network_approval=True,
            network_approval_allowed_ous=["/Staff"],
            enable_trust_chaining=True,
            chaining_allowed_groups=["faculty@domain.org"],
            chaining_denied_ous=["/Students"],
            enable_session_guard=True,
            session_guard_mode="ENFORCE_ACTIVE",
            session_guard_exempt_ous=["/Admins"],
        )
        dump = custom_cfg.model_dump()
        self.assertTrue(dump["enable_network_approval"])
        self.assertEqual(dump["network_approval_allowed_ous"], ["/Staff"])
        self.assertEqual(dump["session_guard_mode"], "ENFORCE_ACTIVE")


if __name__ == "__main__":
    unittest.main()
