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
import google.auth
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

class DirectoryService:
    def __init__(self):
        self.scopes = [
            "https://www.googleapis.com/auth/admin.directory.user.readonly",
            "https://www.googleapis.com/auth/admin.directory.group.readonly",
            "https://www.googleapis.com/auth/admin.directory.group.member.readonly",
            "https://www.googleapis.com/auth/admin.directory.rolemanagement.readonly"
        ]
        key_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
        admin_email = os.getenv("WORKSPACE_ADMIN_EMAIL")

        try:
            if key_path and admin_email and os.path.exists(key_path):
                credentials = service_account.Credentials.from_service_account_file(
                    key_path, scopes=self.scopes, subject=admin_email
                )
            else:
                credentials, _ = google.auth.default(scopes=self.scopes)

            self.service = build("admin", "directory_v1", credentials=credentials)
        except Exception as e:
            print(f"Error initializing Directory service: {e}")
            self.service = None

    def verify_user_is_admin(self, user_email: str, portal_admins: List[str] = None) -> bool:
        target_email = user_email.lower().strip()
        
        if portal_admins and target_email in [a.lower().strip() for a in portal_admins]:
            print(f"SUCCESS [directory_service.py]: User '{target_email}' verified via portal_admins delegation list.")
            return True

        if not self.service:
            print(f"INFO [directory_service.py]: Simulated admin check for '{target_email}'")
            return target_email in ["admin@example.com"]

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
            # Simulation mode
            return target_email in [g.lower().strip() for g in allowed_groups] or "/Staff" in allowed_ous

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

directory_service = DirectoryService()
