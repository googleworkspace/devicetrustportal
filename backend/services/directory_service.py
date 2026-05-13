import os
from typing import List, Dict, Any
import google.auth
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

class DirectoryService:
    def __init__(self):
        self.scopes = [
            "https://www.googleapis.com/auth/admin.directory.user.readonly",
            "https://www.googleapis.com/auth/admin.directory.group.readonly",
            "https://www.googleapis.com/auth/admin.directory.rolemanagement.readonly"
        ]
        self.mock_mode = os.getenv("MOCK_MODE", "false").lower() == "true"
        
        if self.mock_mode:
            self.service = None
        else:
            try:
                credentials, _ = google.auth.default(scopes=self.scopes)
                self.service = build("admin", "directory_v1", credentials=credentials)
            except Exception as e:
                print(f"Warning: Failed to initialize Admin Directory service: {e}. Mocking Directory mode.")
                self.service = None

    def verify_user_is_admin(self, user_email: str) -> bool:
        """Verifies if the given user has Workspace Super Admin or delegated Admin privileges."""
        if not self.service:
            return "admin" in user_email.lower()

        try:
            user = self.service.users().get(userKey=user_email).execute()
            return user.get("isAdmin", False) or user.get("isDelegatedAdmin", False)
        except HttpError as e:
            print(f"Directory API error during admin check: {e}")
            return False

    def get_user_chaining_policy(self, user_email: str, allowed_groups: List[str], allowed_ous: List[str]) -> bool:
        """
        Evaluates whether the user is permitted to perform trust chaining.
        Hierarchical rule: Group membership overrides OU membership.
        """
        if not self.service:
            if any(g in user_email for g in ["chain", "trust", "admin"]):
                return True
            return False

        try:
            for group_email in allowed_groups:
                try:
                    member = self.service.members().get(groupKey=group_email, memberKey=user_email).execute()
                    if member and member.get("status") == "ACTIVE":
                        return True
                except HttpError as e:
                    if e.resp.status == 404:
                        continue
                    print(f"Error checking group membership for {group_email}: {e}")

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
