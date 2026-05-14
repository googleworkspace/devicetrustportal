import os
from typing import List, Dict, Any
import google.auth
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

class DirectoryService:
    def __init__(self):
        self.scopes = [
            "https://www.googleapis.com/auth/admin.directory.user.readonly",
            "https://www.googleapis.com/auth/admin.directory.group.readonly",
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
            print(f"Error initializing Admin Directory service: {e}")
            self.service = None

    def verify_user_is_admin(self, user_email: str) -> bool:
        if not self.service:
            raise Exception("Directory service not initialized with valid credentials")

        try:
            user = self.service.users().get(userKey=user_email).execute()
            return user.get("isAdmin", False) or user.get("isDelegatedAdmin", False)
        except HttpError as e:
            print(f"Directory API error during admin check: {e}")
            return False

    def get_user_chaining_policy(self, user_email: str, allowed_groups: List[str], allowed_ous: List[str]) -> bool:
        if not self.service:
            raise Exception("Directory service not initialized with valid credentials")

        try:
            # 1. Evaluate Group Membership
            for group_email in allowed_groups:
                try:
                    member = self.service.members().get(groupKey=group_email, memberKey=user_email).execute()
                    if member and member.get("status") == "ACTIVE":
                        return True
                except HttpError as e:
                    # Gracefully ignore 404 (group not found) and 403 (foreign domain/permission denied)
                    if e.resp.status in [404, 403]:
                        continue
                    print(f"Warning: Error checking group membership for {group_email}: {e}")

            # 2. Evaluate Organizational Unit (OU) Placement
            user = self.service.users().get(userKey=user_email).execute()
            user_org_unit = user.get("orgUnitPath", "/")

            for allowed_ou in allowed_ous:
                if user_org_unit == allowed_ou or user_org_unit.startswith(f"{allowed_ou}/"):
                    return True

            return False
        except HttpError as e:
            print(f"Directory API error during chaining policy evaluation: {e}")
            return False

directory_service = DirectoryService()
