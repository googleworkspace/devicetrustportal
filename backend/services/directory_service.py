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

import os
import time
from typing import List, Dict, Any, Optional, Tuple
try:
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
except ImportError:
    service_account = None
    build = None
    class HttpError(Exception):
        pass

from backend.services.cloud_identity import resolve_dwd_key_path

class DirectoryService:
    def __init__(self):
        self.scopes = [
            "https://www.googleapis.com/auth/admin.directory.user.readonly",
            "https://www.googleapis.com/auth/admin.directory.group.member.readonly",
            "https://www.googleapis.com/auth/admin.directory.device.chromeos.readonly",
            "https://www.googleapis.com/auth/admin.directory.user.security",
        ]
        self.init_error: Optional[str] = None
        self.key_path = resolve_dwd_key_path()
        self.admin_email = (os.getenv("WORKSPACE_ADMIN_EMAIL") or "").strip()

        if not self.key_path:
            raw_env_cred = (os.getenv("GOOGLE_APPLICATION_CREDENTIALS") or "").strip()
            self.init_error = (
                f"DWD service account key file not found (GOOGLE_APPLICATION_CREDENTIALS='{raw_env_cred}', "
                "checked '/secrets/dwd_key.json' and 'dwd_key.json')."
            )
            print(f"ERROR [directory_service.py]: {self.init_error}")
            self.service = None
            return

        if not self.admin_email:
            self.init_error = "WORKSPACE_ADMIN_EMAIL environment variable is not set for Domain-Wide Delegation."
            print(f"ERROR [directory_service.py]: {self.init_error}")
            self.service = None
            return

        try:
            credentials = service_account.Credentials.from_service_account_file(
                self.key_path, scopes=self.scopes, subject=self.admin_email
            )
            self.service = build("admin", "directory_v1", credentials=credentials)
            print(
                f"INFO [directory_service.py]: Initialized Admin SDK Directory v1 client with DWD key '{self.key_path}' "
                f"and subject '{self.admin_email}'."
            )
        except Exception as e:
            self.init_error = str(e)
            print(f"Error initializing Directory service: {e}")
            self.service = None

    def verify_user_is_admin(self, user_email: str, portal_admins: List[str] = None) -> bool:
        target_email = user_email.lower().strip()
        
        if portal_admins and target_email in [a.lower().strip() for a in portal_admins]:
            print(f"SUCCESS [directory_service.py]: User '{target_email}' verified via portal_admins delegation list.")
            return True

        env_admin = os.getenv("WORKSPACE_ADMIN_EMAIL", "").lower().strip()
        if env_admin and target_email == env_admin:
            print(f"SUCCESS [directory_service.py]: User '{target_email}' verified via WORKSPACE_ADMIN_EMAIL environment variable.")
            return True

        if not self.service:
            print(f"ERROR [directory_service.py]: Directory API service is not initialized; cannot verify admin status for '{target_email}'.")
            return False

        self._user_cache: Dict[str, Dict[str, Any]] = {}
        self._group_cache: Dict[str, Dict[str, Any]] = {}

    def get_user_details(self, user_email: str) -> Dict[str, Any]:
        """Fetches basic user metadata (orgUnitPath, isAdmin) with a 300s RAM cache to protect Directory API quota."""
        target_email = user_email.lower().strip()
        now = time.time()
        cached = self._user_cache.get(target_email)
        if cached and (now - cached.get("_cached_at", 0)) < 300:
            return cached

        default_info = {"orgUnitPath": "/", "isAdmin": False, "_cached_at": now}
        if not self.service:
            return default_info

        try:
            req = self.service.users().get(userKey=target_email, projection="full")
            res = req.execute()
            info = {
                "orgUnitPath": res.get("orgUnitPath", "/"),
                "isAdmin": res.get("isAdmin", False),
                "_cached_at": now,
            }
            self._user_cache[target_email] = info
            return info
        except HttpError as e:
            print(f"Directory API error fetching user details for '{target_email}': {e}")
            return default_info

    def is_user_in_group(self, user_email: str, group_email: str) -> bool:
        """Verifies group membership with a 300s RAM cache."""
        target_email = user_email.lower().strip()
        target_group = group_email.lower().strip()
        cache_key = f"{target_email}::{target_group}"
        now = time.time()
        cached = self._group_cache.get(cache_key)
        if cached and (now - cached.get("_cached_at", 0)) < 300:
            return cached.get("is_member", False)

        if not self.service:
            return False

        try:
            member_check = self.service.members().hasMember(
                groupKey=target_group,
                memberKey=target_email
            ).execute()
            is_member = member_check.get("isMember", False)
            self._group_cache[cache_key] = {"is_member": is_member, "_cached_at": now}
            return is_member
        except HttpError as e:
            print(f"Warning: Failed to check membership in group '{target_group}' for '{target_email}': {e}")
            return False

    def is_ou_matching(self, user_ou: str, target_ou: str) -> bool:
        """Hierarchical OU matching with boundary awareness.
        
        e.g., '/Staff' matches '/Staff' and '/Staff/HighSchool', but not '/Staff-Temp' or '/Students'.
        Root '/' matches everything.
        """
        if not user_ou or not target_ou:
            return False
        u = "/" + user_ou.strip().strip("/")
        t = "/" + target_ou.strip().strip("/")
        if t == "/":
            return True
        u_lower = u.lower()
        t_lower = t.lower()
        return u_lower == t_lower or u_lower.startswith(t_lower + "/")

    def evaluate_feature_authorization(
        self,
        user_email: str,
        feature_name: str,
        feature_enabled: bool,
        allowed_ous: List[str],
        allowed_groups: List[str],
        denied_ous: Optional[List[str]] = None,
        denied_groups: Optional[List[str]] = None,
        require_explicit_allowlist: bool = False,
    ) -> Tuple[bool, str]:
        """Evaluates whether a user is authorized for a feature under an admin switch and OU/Group scopes.
        
        Returns (is_authorized, reason).
        """
        if not feature_enabled:
            return False, f"Feature '{feature_name}' is disabled by domain policy."

        target_email = user_email.lower().strip()
        denied_ous = denied_ous or []
        denied_groups = denied_groups or []
        allowed_ous = allowed_ous or []
        allowed_groups = allowed_groups or []

        user_info = self.get_user_details(target_email)
        user_ou = user_info.get("orgUnitPath", "/")

        # 1. Deny-list OU checks (Precedence: explicit deny overrides any allow)
        for dou in denied_ous:
            if self.is_ou_matching(user_ou, dou):
                return False, f"Access denied: User OU '{user_ou}' is explicitly denied by policy."

        # 2. Deny-list Group checks
        for dgroup in denied_groups:
            if self.is_user_in_group(target_email, dgroup):
                return False, f"Access denied: User is a member of explicitly denied Group '{dgroup}'."

        # 3. Allow-list OU checks (Hierarchical prefix match)
        for aou in allowed_ous:
            if self.is_ou_matching(user_ou, aou):
                return True, f"Authorized for '{feature_name}' via OU '{user_ou}' (matched rule '{aou}')."

        # 4. Allow-list Group checks
        for agroup in allowed_groups:
            if self.is_user_in_group(target_email, agroup):
                return True, f"Authorized for '{feature_name}' via Group '{agroup}'."

        # 5. If allowlists were configured but user matched neither
        if allowed_ous or allowed_groups:
            return False, f"Access denied: User '{target_email}' (OU: '{user_ou}') is not in authorized OUs or Groups."

        # 6. If no allowlists were configured
        if require_explicit_allowlist:
            return False, f"Access denied: Feature '{feature_name}' requires an explicit OU or Group allowlist."

        return True, f"Authorized for '{feature_name}' (domain-wide policy)."

    def get_user_chaining_policy(
        self,
        user_email: str,
        allowed_groups: List[str],
        allowed_ous: List[str],
        denied_groups: Optional[List[str]] = None,
        denied_ous: Optional[List[str]] = None,
        feature_enabled: bool = True,
    ) -> bool:
        """Verifies if user is allowed to chain trust based on admin switch, groups, and hierarchical OUs."""
        is_allowed, reason = self.evaluate_feature_authorization(
            user_email=user_email,
            feature_name="Trust Chaining",
            feature_enabled=feature_enabled,
            allowed_ous=allowed_ous,
            allowed_groups=allowed_groups,
            denied_ous=denied_ous,
            denied_groups=denied_groups,
            require_explicit_allowlist=True,
        )
        print(f"INFO [directory_service.py]: Chaining check for '{user_email}': {reason}")
        return is_allowed

    def get_user_chromeos_devices(self, user_email: str, customer_id: str = "my_customer", is_admin: bool = False) -> List[Dict[str, Any]]:
        """Queries Admin SDK Directory API for enterprise-enrolled ChromeOS devices associated with the user."""
        target_email = user_email.lower().strip()
        
        if not self.service:
            print(f"WARNING [directory_service.py]: Directory API service is not initialized; skipping ChromeOS device lookup for '{target_email}'.")
            return []

        cust_key = customer_id.replace("customers/", "").strip() if customer_id else "my_customer"
        if not cust_key:
            cust_key = "my_customer"

        matched_devices = []
        try:
            page_token = None
            max_pages = 5
            page = 0
            while page < max_pages:
                page += 1
                request = self.service.chromeosdevices().list(
                    customerId=cust_key,
                    pageToken=page_token,
                    maxResults=100,
                    projection="FULL"
                )
                response = request.execute()
                devices = response.get("chromeosdevices", [])
                if not devices:
                    break

                for dev in devices:
                    annotated_user = dev.get("annotatedUser", "").lower().strip()
                    recent_users = [u.get("email", "").lower().strip() for u in dev.get("recentUsers", []) if isinstance(u, dict)]
                    
                    is_match = is_admin or (annotated_user == target_email) or (target_email in recent_users)
                    if is_match:
                        serial = dev.get("serialNumber") or dev.get("deviceId") or "N/A"
                        model = dev.get("model") or "Google Chromebook"
                        os_version = dev.get("osVersion") or "ChromeOS"
                        last_sync = dev.get("lastSync", "N/A")
                        
                        matched_devices.append({
                            "device_user_name": f"directory/devices/{dev.get('deviceId', serial)}/deviceUsers/{target_email}",
                            "device_type": "CHROME_OS",
                            "model": model,
                            "os_version": os_version,
                            "serial_number": serial,
                            "approval_state": "APPROVED",
                            "owner_type": "COMPANY",
                            "last_sync_time": last_sync,
                            "annotated_user": annotated_user,
                            "asset_tag": dev.get("annotatedAssetId", "")
                        })

                page_token = response.get("nextPageToken")
                if not page_token:
                    break

            print(f"INFO [directory_service.py]: Found {len(matched_devices)} company-owned ChromeOS device(s) matching '{target_email}' (is_admin={is_admin}).")
            return matched_devices
        except HttpError as e:
            print(f"Directory API error fetching ChromeOS devices for {target_email}: {e}")
            return []
        except Exception as e:
            print(f"Unexpected error fetching ChromeOS devices for {target_email}: {e}")
            return []

    def sign_out_user(self, user_email: str) -> bool:
        """Immediately invalidates all active login sessions and OAuth tokens for userKey."""
        target_email = user_email.lower().strip()
        if not self.service:
            print(f"ERROR [directory_service.py]: Directory API service not initialized; cannot sign out '{target_email}'.")
            return False
        try:
            self.service.users().signOut(userKey=target_email).execute()
            print(f"SUCCESS [directory_service.py]: Revoked all active sessions for '{target_email}' via users.signOut.")
            return True
        except HttpError as e:
            print(f"ERROR [directory_service.py]: Failed users.signOut for '{target_email}': {e}")
            return False
        except Exception as e:
            print(f"ERROR [directory_service.py]: Unexpected error in users.signOut for '{target_email}': {e}")
            return False

directory_service = DirectoryService()
