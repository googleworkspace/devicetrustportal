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
from typing import List, Dict, Any, Optional
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from backend.services.cloud_identity import resolve_dwd_key_path

class DirectoryService:
    def __init__(self):
        self.scopes = [
            "https://www.googleapis.com/auth/admin.directory.user.readonly",
            "https://www.googleapis.com/auth/admin.directory.group.member.readonly",
            "https://www.googleapis.com/auth/admin.directory.device.chromeos.readonly"
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
            request = self.service.users().get(userKey=target_email, projection="full")
            response = request.execute()
            is_admin = response.get("isAdmin", False)
            if is_admin:
                print(f"SUCCESS [directory_service.py]: User '{target_email}' verified as Workspace Super Administrator.")
            return is_admin
        except HttpError as e:
            print(f"Directory API error checking admin status for {target_email}: {e}")
            return False

    def get_user_chaining_policy(self, user_email: str, allowed_groups: List[str], allowed_ous: List[str]) -> bool:
        """Verifies if user is allowed to chain trust based on groups and OUs."""
        target_email = user_email.lower().strip()
        
        if not allowed_groups and not allowed_ous:
            return False

        if not self.service:
            print(f"ERROR [directory_service.py]: Directory API service is not initialized; cannot verify chaining policy for '{target_email}'.")
            return False

        try:
            # 1. Check Org Unit (OU)
            request = self.service.users().get(userKey=target_email, projection="basic")
            user_res = request.execute()
            user_ou = user_res.get("orgUnitPath", "")
            
            if user_ou and any(user_ou.lower().strip() == ou.lower().strip() for ou in allowed_ous):
                print(f"SUCCESS [directory_service.py]: User '{target_email}' authorized via OU '{user_ou}'.")
                return True

            # 2. Check Groups
            for group in allowed_groups:
                try:
                    member_check = self.service.members().hasMember(
                        groupKey=group.strip(),
                        memberKey=target_email
                    ).execute()
                    
                    if member_check.get("isMember", False):
                        print(f"SUCCESS [directory_service.py]: User '{target_email}' authorized via Group '{group}'.")
                        return True
                except HttpError as e:
                    print(f"Warning: Failed to check membership in group '{group}': {e}")
                    continue

            return False
        except HttpError as e:
            print(f"Directory API error checking chaining policy for {target_email}: {e}")
            return False

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

        creds = service_account.Credentials.from_service_account_file(
            self.key_path,
            scopes=["https://www.googleapis.com/auth/admin.reports.audit.readonly"],
            subject=self.admin_email,
        )
        reports_service = build("admin", "reports_v1", credentials=creds)
        start_dt = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(
            minutes=max(1, lookback_minutes)
        )
        start_time_iso = start_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

        resp = (
            reports_service.activities()
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

    def sign_out_user(self, user_email: str) -> bool:
        """Executes `admin.directory_v1.users.signOut` circuit breaker to revoke active Workspace cookies/tokens.

        Requires Domain-Wide Delegation scope:
        `https://www.googleapis.com/auth/admin.directory.user.security`
        """
        target_email = user_email.strip().lower()
        if not self.key_path or not self.admin_email:
            raise RuntimeError(
                self.init_error or "DWD service account key or WORKSPACE_ADMIN_EMAIL is not configured."
            )

        creds = service_account.Credentials.from_service_account_file(
            self.key_path,
            scopes=["https://www.googleapis.com/auth/admin.directory.user.security"],
            subject=self.admin_email,
        )
        security_dir_service = build("admin", "directory_v1", credentials=creds)
        security_dir_service.users().signOut(userKey=target_email).execute()
        print(
            f"WARNING [directory_service.py]: Executed users.signOut circuit breaker for '{target_email}'."
        )
        return True


directory_service = DirectoryService()
