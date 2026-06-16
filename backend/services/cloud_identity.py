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
import datetime
from typing import List, Dict, Any, Optional
import google.auth
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import BatchHttpRequest

class CloudIdentityService:
    def __init__(self):
        self.scopes = [
            "https://www.googleapis.com/auth/cloud-identity.devices",
            "https://www.googleapis.com/auth/cloud-identity"
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

            self.service = build("cloudidentity", "v1", credentials=credentials)
        except Exception as e:
            print(f"Error initializing Cloud Identity service: {e}")
            self.service = None

    def approve_device_user(self, device_user_name: str, customer_id: str) -> Dict[str, Any]:
        if not self.service:
            raise Exception("Cloud Identity service not initialized with valid credentials")

        try:
            body = {"customer": customer_id}
            request = self.service.devices().deviceUsers().approve(name=device_user_name, body=body)
            operation = request.execute()
            return operation
        except HttpError as e:
            raise Exception(f"Cloud Identity API error during approve: {e}")

    def lookup_device_user(self, user_email: str, raw_device_id: str, customer_id: str) -> Optional[str]:
        if not self.service:
            raise Exception("Cloud Identity service not initialized with valid credentials")

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
        if "devices/" in ev_header and "/deviceUsers/" in ev_header:
            parts = ev_header.split("devices/")
            if len(parts) > 1:
                subpart = parts[1].split(" ")[0]
                return f"devices/{subpart}"
        return None

    def list_inactive_devices(self, threshold_days: int, customer_id: str) -> List[Dict[str, Any]]:
        if not self.service:
            raise Exception("Cloud Identity service not initialized with valid credentials")

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
        if not self.service:
            raise Exception("Cloud Identity service not initialized with valid credentials")

        try:
            request = self.service.devices().deviceUsers().delete(name=device_user_name, customer=customer_id)
            response = request.execute()
            return response
        except HttpError as e:
            raise Exception(f"Cloud Identity API error during revocation: {e}")

    def revoke_device_users_bulk(self, device_user_names: List[str], customer_id: str) -> Dict[str, Any]:
        if not self.service:
            raise Exception("Cloud Identity service not initialized with valid credentials")

        print(f"INFO [cloud_identity.py]: Executing BatchHttpRequest for {len(device_user_names)} device revocation(s)...")
        batch = self.service.new_batch_http_request()
        
        errors = []
        def callback(request_id, response, exception):
            if exception:
                errors.append(exception)

        for du_name in device_user_names:
            # Add individual delete call to multipart batch
            req = self.service.devices().deviceUsers().delete(name=du_name, customer=customer_id)
            batch.add(req, callback=callback)

        batch.execute()
        if errors:
            raise Exception(f"Batch revocation encountered {len(errors)} error(s). First error: {errors[0]}")
            
        return {"status": "SUCCESS", "revoked_count": len(device_user_names)}

cloud_identity_service = CloudIdentityService()
