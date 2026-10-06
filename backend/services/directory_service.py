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
import threading
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
        self._lock = threading.RLock()
        self._scope_cache: Dict[str, Tuple[float, bool, str]] = {}
        self._user_cache: Dict[str, Dict[str, Any]] = {}
        self._group_cache: Dict[str, Dict[str, Any]] = {}
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

        try:
            with self._lock:
                request = self.service.users().get(userKey=target_email, projection="full")
                response = request.execute()
            is_admin = response.get("isAdmin", False)
            if is_admin:
                print(f"SUCCESS [directory_service.py]: User '{target_email}' verified as Workspace Super Administrator.")
            return is_admin
        except HttpError as e:
            print(f"Directory API error checking admin status for {target_email}: {e}")
            return False

    def get_user_details(self, user_email: str) -> Dict[str, Any]:
        """Fetches basic user metadata (orgUnitPath, isAdmin) with a 300s RAM cache to protect Directory API quota."""
        target_email = user_email.lower().strip()
        now = time.time()
        if not hasattr(self, "_user_cache"):
            self._user_cache = {}
        cached = self._user_cache.get(target_email)
        if (
            cached
            and (now - cached.get("_cached_at", 0)) < 300
            and ("_service_id" not in cached or cached.get("_service_id") == id(self.service))
        ):
            return cached

        default_info = {"orgUnitPath": "/", "isAdmin": False, "_cached_at": now}
        if not self.service:
            return default_info

        try:
            lock = getattr(self, "_lock", None)
            if lock:
                with lock:
                    req = self.service.users().get(userKey=target_email, projection="full")
                    res = req.execute()
            else:
                req = self.service.users().get(userKey=target_email, projection="full")
                res = req.execute()
            info = {
                "orgUnitPath": res.get("orgUnitPath", "/"),
                "isAdmin": res.get("isAdmin", False),
                "_cached_at": now,
                "_service_id": id(self.service),
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
        if not hasattr(self, "_group_cache"):
            self._group_cache = {}
        cached = self._group_cache.get(cache_key)
        if (
            cached
            and (now - cached.get("_cached_at", 0)) < 300
            and ("_service_id" not in cached or cached.get("_service_id") == id(self.service))
        ):
            return cached.get("is_member", False)

        if not self.service:
            return False

        try:
            lock = getattr(self, "_lock", None)
            if lock:
                with lock:
                    member_check = self.service.members().hasMember(
                        groupKey=target_group,
                        memberKey=target_email
                    ).execute()
            else:
                member_check = self.service.members().hasMember(
                    groupKey=target_group,
                    memberKey=target_email
                ).execute()
            is_member = member_check.get("isMember", False)
            self._group_cache[cache_key] = {
                "is_member": is_member,
                "_cached_at": now,
                "_service_id": id(self.service),
            }
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

        # 2. Deny-list Group checks (Evaluated in comma-separated priority order: 1st = Priority #1)
        ordered_denied_groups: List[str] = []
        for dg in denied_groups:
            dg_clean = (dg or "").strip().lower()
            if dg_clean and dg_clean not in ordered_denied_groups:
                ordered_denied_groups.append(dg_clean)
        for idx, dgroup in enumerate(ordered_denied_groups, start=1):
            if self.is_user_in_group(target_email, dgroup):
                return False, f"Access denied: User is a member of explicitly denied Group '{dgroup}' (Priority #{idx})."

        # 3. Allow-list OU checks (Hierarchical prefix match)
        for aou in allowed_ous:
            if self.is_ou_matching(user_ou, aou):
                return True, f"Authorized for '{feature_name}' via OU '{user_ou}' (matched rule '{aou}')."

        # 4. Allow-list Group checks (Evaluated in comma-separated priority order: 1st = Priority #1)
        ordered_allowed_groups: List[str] = []
        for ag in allowed_groups:
            ag_clean = (ag or "").strip().lower()
            if ag_clean and ag_clean not in ordered_allowed_groups:
                ordered_allowed_groups.append(ag_clean)
        for idx, agroup in enumerate(ordered_allowed_groups, start=1):
            if self.is_user_in_group(target_email, agroup):
                return True, f"Authorized for '{feature_name}' via Group '{agroup}' (Priority #{idx})."

        # 5. If allowlists were configured but user matched neither
        if allowed_ous or ordered_allowed_groups:
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

    def is_user_in_session_watch_scope(
        self,
        user_email: str,
        target_ous: List[str],
        target_groups: List[str],
        exempt_admins: bool = True,
        portal_admins: Optional[List[str]] = None,
        exempt_ous: Optional[List[str]] = None,
        exempt_groups: Optional[List[str]] = None,
    ) -> Tuple[bool, str]:
        """Determines whether a user is in scope for Session Watch enforcement.

        Returns (in_scope: bool, reason: str).
        Uses a 5-minute TTL cache so repeated login events for the same user do not
        consume extra Directory API quota.
        """
        target_email = user_email.lower().strip()
        clean_ous = [o.strip() for o in (target_ous or []) if o and o.strip()]
        clean_groups: List[str] = []
        for g in target_groups or []:
            gc = (g or "").strip().lower()
            if gc and gc not in clean_groups:
                clean_groups.append(gc)
        clean_exempt_ous = [o.strip() for o in (exempt_ous or []) if o and o.strip()]
        clean_exempt_groups: List[str] = []
        for g in exempt_groups or []:
            gc = (g or "").strip().lower()
            if gc and gc not in clean_exempt_groups:
                clean_exempt_groups.append(gc)
        clean_admins = [a.strip().lower() for a in (portal_admins or []) if a and a.strip()]
        env_admin = os.getenv("WORKSPACE_ADMIN_EMAIL", "").lower().strip()
        if env_admin and env_admin not in clean_admins:
            clean_admins.append(env_admin)

        if exempt_admins and target_email in clean_admins:
            return False, f"Exempt administrator ({target_email})"

        cache_key = (
            f"{target_email}|ous={','.join(sorted(clean_ous))}|grps={','.join(clean_groups)}"
            f"|ex={exempt_admins}|ex_ous={','.join(sorted(clean_exempt_ous))}|ex_grps={','.join(clean_exempt_groups)}"
        )
        now = time.time()
        cached = self._scope_cache.get(cache_key)
        if cached and (now - cached[0]) < 300.0:
            return cached[1], cached[2]

        if not self.service:
            if not clean_ous and not clean_groups:
                return True, "Domain-wide scope"
            return False, "Directory service uninitialized; skipping scoped enforcement"

        user_ou = "/"
        is_super_admin = False
        try:
            with self._lock:
                user_res = (
                    self.service.users()
                    .get(userKey=target_email, projection="basic")
                    .execute()
                    or {}
                )
            user_ou = user_res.get("orgUnitPath") or "/"
            is_super_admin = bool(user_res.get("isAdmin", False))
        except Exception as e:
            print(f"WARNING [directory_service.py]: Could not lookup user '{target_email}' for Session Watch scope: {e}")

        if exempt_admins and is_super_admin:
            res = (False, f"Exempt Workspace Super Admin ({target_email})")
            self._scope_cache[cache_key] = (now, res[0], res[1])
            return res

        # Check explicit exempt OUs / Groups (Groups evaluated in comma-separated priority order)
        for eou in clean_exempt_ous:
            if self.is_ou_matching(user_ou, eou):
                res = (False, f"Exempt OU '{user_ou}' (matched rule '{eou}')")
                self._scope_cache[cache_key] = (now, res[0], res[1])
                return res

        for idx, egrp in enumerate(clean_exempt_groups, start=1):
            if self.is_user_in_group(target_email, egrp):
                res = (False, f"Exempt Group '{egrp}' (Priority #{idx})")
                self._scope_cache[cache_key] = (now, res[0], res[1])
                return res

        # If no OUs and no Groups are configured, all non-exempt users are in scope
        if not clean_ous and not clean_groups:
            res = (True, f"Domain-wide scope (OU '{user_ou}')")
            self._scope_cache[cache_key] = (now, res[0], res[1])
            return res

        # 1. Check OU match (exact match or sub-OU hierarchy match, e.g. '/Students' matches '/Students/Grade9')
        for ou in clean_ous:
            if self.is_ou_matching(user_ou, ou):
                res = (True, f"Matched target OU '{ou}' (user OU '{user_ou}')")
                self._scope_cache[cache_key] = (now, res[0], res[1])
                return res

        # 2. Check Group membership match in comma-separated priority order (1st in = Priority #1)
        for idx, group in enumerate(clean_groups, start=1):
            try:
                with self._lock:
                    member_check = (
                        self.service.members()
                        .hasMember(groupKey=group, memberKey=target_email)
                        .execute()
                        or {}
                    )
                if member_check.get("isMember", False):
                    res = (True, f"Matched target Group '{group}' (Priority #{idx})")
                    self._scope_cache[cache_key] = (now, res[0], res[1])
                    return res
            except Exception as e:
                print(f"WARNING [directory_service.py]: Group membership check failed for '{group}': {e}")

        res = (False, f"Outside target OUs/Groups (user OU '{user_ou}')")
        self._scope_cache[cache_key] = (now, res[0], res[1])
        return res

    def get_user_chromeos_devices(self, user_email: str, customer_id: str = "my_customer", is_admin: bool = False) -> List[Dict[str, Any]]:
        """Queries Admin SDK Directory API for enterprise-enrolled ChromeOS devices actually accessed by the user."""
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
                with self._lock:
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
                    
                    # Only include company-owned ChromeOS devices that this user has actually accessed/signed into
                    is_match = target_email in recent_users
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

            print(f"INFO [directory_service.py]: Found {len(matched_devices)} accessed company-owned ChromeOS device(s) for '{target_email}'.")
            return matched_devices
        except HttpError as e:
            print(f"Directory API error fetching ChromeOS devices for {target_email}: {e}")
            return []
        except Exception as e:
            print(f"Unexpected error fetching ChromeOS devices for {target_email}: {e}")
            return []

    def list_all_chromeos_inventory(self, customer_id: str = "my_customer") -> List[Dict[str, Any]]:
        """Fetches active ChromeOS hardware serials across the tenant for SessionGuardService O(1) cache."""
        if not self.service:
            raise RuntimeError(
                self.init_error or "Directory API service is not initialized with valid DWD credentials."
            )

        cust_key = customer_id.replace("customers/", "").strip() if customer_id else "my_customer"
        if not cust_key:
            cust_key = "my_customer"

        inventory: List[Dict[str, Any]] = []
        page_token = None
        max_pages = 20
        page = 0
        while page < max_pages:
            page += 1
            with self._lock:
                request = self.service.chromeosdevices().list(
                    customerId=cust_key,
                    pageToken=page_token,
                    maxResults=200,
                    projection="BASIC",
                )
                response = request.execute()
            devices = response.get("chromeosdevices", [])
            if not devices:
                break
            for dev in devices:
                serial = (dev.get("serialNumber") or "").strip().upper()
                if not serial:
                    continue
                inventory.append(
                    {
                        "device_id": dev.get("deviceId", serial),
                        "serial_number": serial,
                        "device_type": "CHROMEOS",
                        "status": (dev.get("status") or "ACTIVE").upper(),
                        "assigned_user": (dev.get("annotatedUser") or "").strip().lower() or None,
                        "org_unit_path": dev.get("orgUnitPath") or "/",
                    }
                )
            page_token = response.get("nextPageToken")
            if not page_token:
                break
        return inventory

    def list_recent_login_events(
        self, lookback_minutes: int = 15, max_results: int = 250
    ) -> List[Dict[str, Any]]:
        """Queries Admin SDK Reports API (`admin.reports_v1.activities.list`) for domain login events.

        Requires Domain-Wide Delegation scope:
        `https://www.googleapis.com/auth/admin.reports.audit.readonly`
        """
        if not self.key_path or not self.admin_email:
            raise RuntimeError(
                self.init_error or "DWD service account key or WORKSPACE_ADMIN_EMAIL is not configured."
            )

        import datetime

        with self._lock:
            if not getattr(self, "_reports_service", None):
                creds = service_account.Credentials.from_service_account_file(
                    self.key_path,
                    scopes=["https://www.googleapis.com/auth/admin.reports.audit.readonly"],
                    subject=self.admin_email,
                )
                self._reports_service = build("admin", "reports_v1", credentials=creds)
            start_dt = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(
                minutes=max(1, lookback_minutes)
            )
            start_time_iso = start_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

            resp = (
                self._reports_service.activities()
                .list(
                    userKey="all",
                    applicationName="login",
                    startTime=start_time_iso,
                    maxResults=min(1000, max(1, max_results)),
                )
                .execute()
            )
        items = resp.get("items", [])
        events: List[Dict[str, Any]] = []
        for item in items:
            actor_email = (item.get("actor", {}) or {}).get("email", "").strip().lower()
            if not actor_email:
                continue
            ip_address = (item.get("ipAddress") or "0.0.0.0").strip()
            id_block = item.get("id", {}) or {}
            time_str = id_block.get("time") or ""
            unique_qual = str(id_block.get("uniqueQualifier") or time_str or len(events))
            try:
                ts_epoch = datetime.datetime.fromisoformat(
                    time_str.replace("Z", "+00:00")
                ).timestamp()
            except Exception:
                ts_epoch = datetime.datetime.now(datetime.timezone.utc).timestamp()

            raw_events = item.get("events", []) or [{}]
            first_ev = raw_events[0]
            ev_name = first_ev.get("name") or first_ev.get("type") or "login_success"
            if "failure" in ev_name.lower() or "logout" in ev_name.lower():
                continue

            is_suspicious = False
            login_type = ev_name
            for param in first_ev.get("parameters", []) or []:
                p_name = param.get("name", "")
                if p_name == "login_type" and param.get("value"):
                    login_type = param["value"]
                if p_name == "is_suspicious" and param.get("boolValue") is True:
                    is_suspicious = True

            events.append(
                {
                    "event_id": f"{actor_email}:{unique_qual}",
                    "user_email": actor_email,
                    "ip_address": ip_address,
                    "timestamp_epoch": ts_epoch,
                    "timestamp_iso": time_str,
                    "login_type": login_type,
                    "is_suspicious": is_suspicious,
                }
            )
        return events

    def list_recent_token_events(
        self, lookback_minutes: int = 15, max_results: int = 250
    ) -> List[Dict[str, Any]]:
        """Queries Admin SDK Reports API (`admin.reports_v1.activities.list`) for domain OAuth token events.

        Used by Stolen Cookie & Token Threat Detection (Cloud Hosting ASN & Foreign IP Pivot Sentinel)
        even when Unapproved Device Session Management (`session_watch_enabled`) is disabled.

        Requires Domain-Wide Delegation scope:
        `https://www.googleapis.com/auth/admin.reports.audit.readonly`
        """
        if not self.key_path or not self.admin_email:
            raise RuntimeError(
                self.init_error or "DWD service account key or WORKSPACE_ADMIN_EMAIL is not configured."
            )

        import datetime

        with self._lock:
            if not getattr(self, "_reports_service", None):
                creds = service_account.Credentials.from_service_account_file(
                    self.key_path,
                    scopes=["https://www.googleapis.com/auth/admin.reports.audit.readonly"],
                    subject=self.admin_email,
                )
                self._reports_service = build("admin", "reports_v1", credentials=creds)
            start_dt = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(
                minutes=max(1, lookback_minutes)
            )
            start_time_iso = start_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

            resp = (
                self._reports_service.activities()
                .list(
                    userKey="all",
                    applicationName="token",
                    startTime=start_time_iso,
                    maxResults=min(1000, max(1, max_results)),
                )
                .execute()
            )
        items = resp.get("items", [])
        events: List[Dict[str, Any]] = []
        for item in items:
            actor_email = (item.get("actor", {}) or {}).get("email", "").strip().lower()
            if not actor_email:
                continue
            ip_address = (item.get("ipAddress") or "0.0.0.0").strip()
            id_block = item.get("id", {}) or {}
            time_str = id_block.get("time") or ""
            unique_qual = str(id_block.get("uniqueQualifier") or time_str or len(events))
            try:
                ts_epoch = datetime.datetime.fromisoformat(
                    time_str.replace("Z", "+00:00")
                ).timestamp()
            except Exception:
                ts_epoch = datetime.datetime.now(datetime.timezone.utc).timestamp()

            raw_events = item.get("events", []) or [{}]
            first_ev = raw_events[0]
            ev_name = first_ev.get("name") or first_ev.get("type") or "activity"
            if "revoke" in ev_name.lower():
                continue

            net_info = item.get("networkInfo", {}) or {}
            raw_asn = net_info.get("ipAsn")
            asn_str: Optional[str] = None
            if raw_asn is not None:
                if isinstance(raw_asn, list) and raw_asn:
                    asn_str = f"AS{raw_asn[0]}" if not str(raw_asn[0]).upper().startswith("AS") else str(raw_asn[0]).upper()
                else:
                    asn_str = f"AS{raw_asn}" if not str(raw_asn).upper().startswith("AS") else str(raw_asn).upper()

            app_name = "Google Workspace Web/OAuth"
            for param in first_ev.get("parameters", []) or []:
                p_name = param.get("name", "")
                p_val = param.get("value") or (param.get("multiValue") or [None])[0]
                if p_name in ("app_name", "client_id", "api_name") and p_val:
                    app_name = str(p_val)
                elif p_name in ("asn", "ip_asn") and p_val and not asn_str:
                    val_s = str(p_val).strip().upper()
                    asn_str = val_s if val_s.startswith("AS") else f"AS{val_s}"

            events.append(
                {
                    "event_id": f"token:{actor_email}:{unique_qual}",
                    "user_email": actor_email,
                    "ip_address": ip_address,
                    "timestamp_epoch": ts_epoch,
                    "timestamp_iso": time_str,
                    "asn": asn_str,
                    "app_name": app_name,
                }
            )
        return events

    def sign_out_user(self, user_email: str) -> bool:
        """Executes `admin.directory_v1.users.signOut` circuit breaker to revoke active Workspace cookies/tokens.

        Requires Domain-Wide Delegation scope:
        `https://www.googleapis.com/auth/admin.directory.user.security`
        """
        target_email = user_email.strip().lower()
        if not self.key_path or not self.admin_email:
            if self.service:
                try:
                    self.service.users().signOut(userKey=target_email).execute()
                    return True
                except Exception as e:
                    print(f"ERROR [directory_service.py]: Failed users.signOut for '{target_email}': {e}")
                    return False
            raise RuntimeError(
                self.init_error or "DWD service account key or WORKSPACE_ADMIN_EMAIL is not configured."
            )

        with self._lock:
            if not getattr(self, "_security_dir_service", None):
                creds = service_account.Credentials.from_service_account_file(
                    self.key_path,
                    scopes=["https://www.googleapis.com/auth/admin.directory.user.security"],
                    subject=self.admin_email,
                )
                self._security_dir_service = build("admin", "directory_v1", credentials=creds)
            self._security_dir_service.users().signOut(userKey=target_email).execute()
            # Also revoke OAuth 2.0 token grant for the portal client ID if configured
            try:
                from backend.services.config_service import config_service

                cfg = config_service.get_tenant_config()
                if cfg and getattr(cfg, "google_client_id", None):
                    self._security_dir_service.tokens().delete(
                        userKey=target_email, clientId=cfg.google_client_id
                    ).execute()
            except Exception:
                pass
        print(
            f"WARNING [directory_service.py]: Executed users.signOut circuit breaker for '{target_email}'."
        )
        return True

    def list_domain_ous_and_groups(
        self,
        customer_id: str = "my_customer",
        configured_ous: Optional[List[str]] = None,
        configured_groups: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Discovers hierarchical Organizational Units (OUs) in the Workspace tenant and returns configured Groups in priority order.

        Note: Does NOT bulk-import all domain Google Groups; admins specify comma-separated groups
        where earlier entries have higher priority in the hierarchy (1st in = Priority #1).
        """
        cust_key = customer_id.replace("customers/", "").strip() if customer_id else "my_customer"
        if not cust_key:
            cust_key = "my_customer"

        ou_descriptions: Dict[str, str] = {"/": "Root Organization (All OUs)"}
        raw_ou_paths: set[str] = {"/"}
        for raw_ou in configured_ous or []:
            cleaned = "/" + raw_ou.strip().strip("/") if raw_ou and raw_ou.strip() else "/"
            raw_ou_paths.add(cleaned)

        ordered_groups: List[Dict[str, Any]] = []
        seen_groups: set[str] = set()
        for raw_grp in configured_groups or []:
            g_clean = (raw_grp or "").strip().lower()
            if g_clean and g_clean not in seen_groups:
                seen_groups.add(g_clean)
                ordered_groups.append(
                    {
                        "email": g_clean,
                        "name": g_clean.split("@")[0],
                        "priority": len(ordered_groups) + 1,
                        "description": f"Priority #{len(ordered_groups) + 1} Configured Policy Group",
                    }
                )

        now = time.time()
        cached_meta = getattr(self, "_metadata_cache", None)
        if (
            cached_meta
            and (now - cached_meta.get("_cached_at", 0.0)) < 120.0
            and cached_meta.get("_service_id") == id(self.service)
        ):
            for p in cached_meta.get("discovered_ou_paths", []):
                raw_ou_paths.add(p)
            ou_descriptions.update(cached_meta.get("ou_descriptions", {}))
        else:
            discovered_ou_paths: set[str] = set()

            # 1. Try orgunits().list if service or DWD credentials are available
            if self.key_path and self.admin_email and service_account and build:
                try:
                    with self._lock:
                        if not getattr(self, "_orgunit_service", None):
                            ou_creds = service_account.Credentials.from_service_account_file(
                                self.key_path,
                                scopes=["https://www.googleapis.com/auth/admin.directory.orgunit.readonly"],
                                subject=self.admin_email,
                            )
                            self._orgunit_service = build("admin", "directory_v1", credentials=ou_creds)
                        ou_resp = (
                            self._orgunit_service.orgunits()
                            .list(customerId=cust_key, type="all")
                            .execute()
                            or {}
                        )
                    for item in ou_resp.get("organizationUnits", []) or []:
                        p = item.get("orgUnitPath")
                        if p:
                            norm_p = "/" + p.strip().strip("/")
                            discovered_ou_paths.add(norm_p)
                            if item.get("description") or item.get("name"):
                                ou_descriptions[norm_p] = item.get("description") or item.get("name")
                except Exception:
                    pass

            # 2. Harvest orgUnitPath from users().list and chromeosdevices().list (uses existing DWD scopes)
            if self.service:
                try:
                    with self._lock:
                        u_resp = (
                            self.service.users()
                            .list(customer=cust_key, maxResults=200, projection="basic")
                            .execute()
                            or {}
                        )
                    for u in u_resp.get("users", []) or []:
                        upath = u.get("orgUnitPath")
                        if upath:
                            discovered_ou_paths.add("/" + upath.strip().strip("/"))
                except Exception:
                    pass

                try:
                    with self._lock:
                        c_resp = (
                            self.service.chromeosdevices()
                            .list(customerId=cust_key, maxResults=200, projection="BASIC")
                            .execute()
                            or {}
                        )
                    for d in c_resp.get("chromeosdevices", []) or []:
                        dpath = d.get("orgUnitPath")
                        if dpath:
                            discovered_ou_paths.add("/" + dpath.strip().strip("/"))
                except Exception:
                    pass

            for p in discovered_ou_paths:
                raw_ou_paths.add(p)

            self._metadata_cache = {
                "_cached_at": now,
                "_service_id": id(self.service),
                "discovered_ou_paths": list(discovered_ou_paths),
                "ou_descriptions": dict(ou_descriptions),
            }

        # Synthesize all intermediate parent OU paths so the tree is always complete
        all_paths: set[str] = {"/"}
        for path in raw_ou_paths:
            if not path or path == "/":
                continue
            parts = [seg for seg in path.strip("/").split("/") if seg]
            curr = ""
            for seg in parts:
                curr = f"{curr}/{seg}"
                all_paths.add(curr)

        # If only "/" exists (e.g., fresh/empty tenant), provide common Workspace starter OUs
        if len(all_paths) == 1:
            for starter in ("/Students", "/Staff", "/Admins"):
                all_paths.add(starter)

        sorted_paths = sorted(all_paths, key=lambda x: (0 if x == "/" else 1, x.lower()))
        ou_nodes: List[Dict[str, Any]] = []
        for p in sorted_paths:
            if p == "/":
                ou_nodes.append(
                    {
                        "org_unit_path": "/",
                        "name": "Root Organization (/)",
                        "parent_path": "",
                        "depth": 0,
                        "description": ou_descriptions.get("/", "All Organizational Units"),
                    }
                )
            else:
                segs = [s for s in p.strip("/").split("/") if s]
                parent = "/" if len(segs) == 1 else "/" + "/".join(segs[:-1])
                ou_nodes.append(
                    {
                        "org_unit_path": p,
                        "name": segs[-1],
                        "parent_path": parent,
                        "depth": len(segs),
                        "description": ou_descriptions.get(p, ""),
                    }
                )

        return {
            "org_units": ou_nodes,
            "groups": ordered_groups,
        }


directory_service = DirectoryService()
