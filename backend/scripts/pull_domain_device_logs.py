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
import sys
import json
import google.auth
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

def pull_device_audit_logs():
    """
    Queries Google Workspace Admin Audit Logs (Reports API) and Cloud Identity API
    to inspect recent device registrations, approvals, and sync events.
    """
    print("\n==================================================================================")
    print("           Google Workspace Domain Device Audit Log Investigator                   ")
    print("==================================================================================")

    key_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "dwd_key.json")
    admin_email = os.getenv("WORKSPACE_ADMIN_EMAIL")

    if not admin_email:
        print("INFO: WORKSPACE_ADMIN_EMAIL environment variable not set.")
        print("Usage: WORKSPACE_ADMIN_EMAIL=admin@yourdomain.com python backend/scripts/pull_domain_device_logs.py\n")

    scopes = [
        "https://www.googleapis.com/auth/admin.reports.audit.readonly",
        "https://www.googleapis.com/auth/cloud-identity.devices",
        "https://www.googleapis.com/auth/cloud-identity"
    ]

    try:
        if key_path and os.path.exists(key_path) and admin_email:
            credentials = service_account.Credentials.from_service_account_file(
                key_path, scopes=scopes, subject=admin_email
            )
            print(f"INFO: Authenticated via Service Account using DWD subject '{admin_email}'.")
        else:
            credentials, _ = google.auth.default(scopes=scopes)
            print("INFO: Authenticated via Application Default Credentials.")

        ci_service = build("cloudidentity", "v1", credentials=credentials)
        reports_service = build("admin", "reports_v1", credentials=credentials) if admin_email else None
    except Exception as e:
        print(f"ERROR: Failed to initialize Google API clients: {e}")
        return

    customer_id = os.getenv("TENANT_CUSTOMER_ID", "customers/my_customer")

    # 1. Query Cloud Identity Devices API
    print(f"\n--- 1. Querying Current Cloud Identity Registered Devices ({customer_id}) ---")
    try:
        req = ci_service.devices().list(customer=customer_id)
        res = req.execute()
        devices = res.get("devices", [])
        print(f"Found {len(devices)} registered device(s) in Cloud Identity.\n")

        for dev in devices:
            dev_name = dev.get("name")
            dev_type = dev.get("deviceType", "UNKNOWN")
            model = dev.get("model", "Unknown Model")
            owner_type = dev.get("ownerType", "BYOD")
            last_sync = dev.get("lastSyncTime", "N/A")
            serial = dev.get("serialNumber") or dev.get("deviceSerialNumber") or "N/A"

            print(f"• Device: {model} ({dev_type})")
            print(f"  Resource Name: {dev_name}")
            print(f"  Owner Type:    {owner_type}")
            print(f"  Serial Number: {serial}")
            print(f"  Last Sync:     {last_sync}")

            # Fetch device users for this device
            try:
                du_req = ci_service.devices().deviceUsers().list(parent=dev_name, customer=customer_id)
                du_res = du_req.execute()
                for du in du_res.get("deviceUsers", []):
                    user_email = du.get("userEmail", "N/A")
                    mgmt_state = du.get("managementState") or du.get("approvalState", "UNKNOWN")
                    first_sync = du.get("firstSyncTime", "N/A")
                    print(f"  └─ User: {user_email} | Approval/Mgmt State: {mgmt_state} | First Sync: {first_sync}")
            except Exception as du_err:
                print(f"  └─ Warning fetching device users: {du_err}")
            print()

    except HttpError as e:
        print(f"API Error listing Cloud Identity devices: {e}")
    except Exception as e:
        print(f"Unexpected error: {e}")

    # 2. Query Admin Audit Reports API for Device Events (if Reports API available)
    if reports_service:
        print("\n--- 2. Querying Google Workspace Admin Audit Logs (Device Activity) ---")
        try:
            activities_req = reports_service.activities().list(
                userKey="all",
                applicationName="admin",
                eventName="REGISTER_DEVICE,APPROVE_DEVICE,BLOCK_DEVICE,DELETE_DEVICE"
            )
            activities_res = activities_req.execute()
            items = activities_res.get("items", [])
            print(f"Found {len(items)} matching device audit log event(s).\n")

            for item in items[:10]: # Print latest 10
                actor = item.get("actor", {}).get("email", "System")
                time_str = item.get("id", {}).get("time", "N/A")
                events = item.get("events", [])
                for ev in events:
                    ev_name = ev.get("name")
                    params = {p.get("name"): p.get("value") for p in ev.get("parameters", [])}
                    print(f"[{time_str}] Event: {ev_name} | Actor: {actor} | Params: {params}")

        except HttpError as e:
            print(f"Note: Could not query Admin Reports API ({e}). Ensure Admin Audit Reports API scope is enabled.")
        except Exception as e:
            print(f"Unexpected error querying Reports API: {e}")

if __name__ == "__main__":
    pull_device_audit_logs()
