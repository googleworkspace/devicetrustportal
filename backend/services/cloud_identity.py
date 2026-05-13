import os
import datetime
from typing import List, Dict, Any, Optional
import google.auth
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

class CloudIdentityService:
    def __init__(self):
        self.scopes = [
            "https://www.googleapis.com/auth/cloud-identity.devices",
            "https://www.googleapis.com/auth/cloud-identity"
        ]
        self.mock_mode = os.getenv("MOCK_MODE", "false").lower() == "true"
        
        if self.mock_mode:
            self.service = None
        else:
            try:
                credentials, _ = google.auth.default(scopes=self.scopes)
                self.service = build("cloudidentity", "v1", credentials=credentials)
            except Exception as e:
                print(f"Warning: Failed to initialize Cloud Identity service: {e}. Mocking API mode.")
                self.service = None

    def approve_device_user(self, device_user_name: str, customer_id: str) -> Dict[str, Any]:
        """Approves a device user to access organizational data."""
        if not self.service:
            return {"name": f"operations/mock-approve-{device_user_name}", "done": True, "response": {"status": "APPROVED"}}

        try:
            body = {"customer": customer_id}
            request = self.service.devices().deviceUsers().approve(name=device_user_name, body=body)
            operation = request.execute()
            return operation
        except HttpError as e:
            raise Exception(f"Cloud Identity API error during approve: {e}")

    def lookup_device_user(self, user_email: str, raw_device_id: str, customer_id: str) -> Optional[str]:
        """Option A: Lookup fully qualified device user resource name."""
        if not self.service:
            return f"devices/mock-device-{raw_device_id}/deviceUsers/mock-user-{user_email.replace('@', '-')}"

        try:
            query = f"id=='{raw_device_id}'" if not raw_device_id.startswith("devices/") else ""
            if not query and raw_device_id.startswith("devices/"):
                device_name = raw_device_id
            else:
                request = self.service.devices().list(customer=customer_id, filter=query)
                response = request.execute()
                devices = response.get("devices", [])
                if not devices:
                    return None
                device_name = devices[0]["name"]

            users_request = self.service.devices().deviceUsers().list(parent=device_name, customer=customer_id)
            users_response = users_request.execute()
            device_users = users_response.get("deviceUsers", [])
            
            for du in device_users:
                if du.get("userEmail") == user_email:
                    return du["name"]
            
            return None
        except HttpError as e:
            raise Exception(f"Cloud Identity API error during lookup: {e}")

    def parse_endpoint_verification_header(self, ev_header: str) -> Optional[str]:
        """Option B: Parse device resource name directly from Endpoint Verification / CAA headers."""
        if "devices/" in ev_header and "/deviceUsers/" in ev_header:
            parts = ev_header.split("devices/")
            if len(parts) > 1:
                subpart = parts[1].split(" ")[0]
                return f"devices/{subpart}"
        return None

    def list_inactive_devices(self, threshold_days: int, customer_id: str) -> List[Dict[str, Any]]:
        """Finds devices whose last sync time exceeds the threshold."""
        if not self.service:
            return [{"name": "devices/mock-stale-dev/deviceUsers/mock-stale-user", "lastSyncTime": "2025-01-01T00:00:00Z"}]

        try:
            cutoff_date = datetime.datetime.utcnow() - datetime.timedelta(days=threshold_days)
            cutoff_str = cutoff_date.strftime("%Y-%m-%dT%H:%M:%SZ")
            
            query = f"lastSyncTime < '{cutoff_str}'"
            request = self.service.devices().list(customer=customer_id, filter=query)
            response = request.execute()
            devices = response.get("devices", [])
            
            inactive_device_users = []
            for d in devices:
                du_req = self.service.devices().deviceUsers().list(parent=d["name"], customer=customer_id)
                du_resp = du_req.execute()
                for du in du_resp.get("deviceUsers", []):
                    if du.get("approvalState") == "APPROVED":
                        inactive_device_users.append(du)
                        
            return inactive_device_users
        except HttpError as e:
            raise Exception(f"Cloud Identity API error during inactive list: {e}")

    def revoke_device_user(self, device_user_name: str, customer_id: str) -> Dict[str, Any]:
        """Revokes approved status by deleting or blocking the device user."""
        if not self.service:
            return {"status": "REVOKED", "name": device_user_name}

        try:
            request = self.service.devices().deviceUsers().delete(name=device_user_name, customer=customer_id)
            response = request.execute()
            return response
        except HttpError as e:
            raise Exception(f"Cloud Identity API error during revocation: {e}")

cloud_identity_service = CloudIdentityService()
