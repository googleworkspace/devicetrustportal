#!/usr/bin/env python3
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

"""
Automated Chromebook Inventory Seeding Script
Crawls active enterprise ChromeOS devices via Admin SDK Directory API and anchors them in Cloud Identity.
"""

import os
import sys
import time
import random
from pathlib import Path
from typing import Optional, Dict, Any, List

# Ensure repository root is always in sys.path
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import google.auth
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

SCOPES = [
    "https://www.googleapis.com/auth/admin.directory.device.chromeos.readonly",
    "https://www.googleapis.com/auth/cloud-identity.devices"
]

class InventorySeeder:
    def __init__(self):
        raw_cust = os.getenv("TENANT_CUSTOMER_ID", "my_customer")
        # Strip customers/ prefix if provided
        self.raw_customer_id = raw_cust.replace("customers/", "").strip() if raw_cust else "my_customer"
        if not self.raw_customer_id:
            self.raw_customer_id = "my_customer"

        key_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
        admin_email = os.getenv("WORKSPACE_ADMIN_EMAIL")

        try:
            if key_path and admin_email and os.path.exists(key_path):
                print(f"Initializing Google API client with DWD impersonation for subject: {admin_email}")
                credentials = service_account.Credentials.from_service_account_file(
                    key_path, scopes=SCOPES, subject=admin_email
                )
            else:
                print("Initializing Google API client using Application Default Credentials (ADC)...")
                credentials, _ = google.auth.default(scopes=SCOPES)

            self.admin_service = build("admin", "directory_v1", credentials=credentials)
            self.ci_service = build("cloudidentity", "v1", credentials=credentials)
        except Exception as e:
            print(f"Error: Failed to initialize Google API credentials: {e}")
            sys.exit(1)

        # Dynamically resolve true Google Workspace Customer ID (e.g., C0xxxxxxx)
        self.resolved_customer_id = self.raw_customer_id
        try:
            cust_res = self.admin_service.customers().get(customerKey="my_customer").execute()
            if cust_res and "id" in cust_res:
                self.resolved_customer_id = cust_res["id"]
                print(f"Successfully resolved Google Workspace Customer ID: {self.resolved_customer_id}")
        except Exception as e:
            print(f"Notice: Using configured customer key '{self.raw_customer_id}' (Dynamic lookup: {e})")

        self.directory_customer_id = self.resolved_customer_id
        self.ci_customer_id = f"customers/{self.resolved_customer_id}"

        # Stats counters
        self.stats = {
            "total_directory_devices": 0,
            "created_in_cloud_identity": 0,
            "already_registered": 0,
            "bindings_approved": 0,
            "errors": 0
        }

    def run(self):
        print("\n=========================================================")
        print("      Starting Live Chromebook Inventory Seeding Run     ")
        print(f"  Directory Customer:     {self.directory_customer_id}")
        print(f"  Cloud Identity Target:  {self.ci_customer_id}")
        print("=========================================================\n")
        
        page_token = None
        batch_size = 50

        while True:
            try:
                request = self.admin_service.chromeosdevices().list(
                    customerId=self.directory_customer_id,
                    pageToken=page_token,
                    maxResults=batch_size,
                    projection="FULL"
                )
                response = request.execute()
                devices = response.get("chromeosdevices", [])

                if not devices:
                    break

                self._process_device_batch(devices)
                self.stats["total_directory_devices"] += len(devices)
                print(f"Processed batch of {len(devices)} device(s) (Total discovered: {self.stats['total_directory_devices']})...")

                page_token = response.get("nextPageToken")
                if not page_token:
                    break

            except HttpError as e:
                if e.resp.status in [429, 503]:
                    time.sleep(random.uniform(5, 10))
                    continue
                else:
                    print(f"\n❌ Live API Error during Directory crawl: {e}")
                    if self.stats["total_directory_devices"] == 0:
                        print("Tip: Verify that Domain-Wide Delegation (DWD) is configured in Google Admin Console with scope:")
                        print("     https://www.googleapis.com/auth/admin.directory.device.chromeos.readonly")
                    sys.exit(1)
            except Exception as e:
                print(f"\n❌ Unexpected error during Directory crawl: {e}")
                sys.exit(1)
                
        print("\n=========================================================")
        print(f"✔ Live Inventory Seeding Run Complete!")
        print(f"  • Total Directory Chromebooks Discovered: {self.stats['total_directory_devices']}")
        print(f"  • Newly Anchored in Cloud Identity:      {self.stats['created_in_cloud_identity']}")
        print(f"  • Already Anchored (Pre-existing):        {self.stats['already_registered']}")
        print(f"  • Device User Bindings Approved:          {self.stats['bindings_approved']}")
        if self.stats["errors"] > 0:
            print(f"  • Errors Encountered:                    {self.stats['errors']}")
        print("=========================================================\n")

        if self.stats["total_directory_devices"] == 0:
            print("Note: No enrolled Chromebooks found in the Directory API.")
            print("If you have enrolled ChromeOS devices in Google Admin Console:")
            print("  1. Verify the service account has Domain-Wide Delegation (DWD) for WORKSPACE_ADMIN_EMAIL.")
            print("  2. Verify devices appear in Google Admin Console under Devices > Chrome > Devices.")

    def _process_device_batch(self, devices: List[Dict[str, Any]]):
        def batch_callback(request_id, response, exception):
            if exception:
                if isinstance(exception, HttpError) and exception.resp.status == 409:
                    # Device already exists in Cloud Identity inventory
                    self.stats["already_registered"] += 1
                    self._approve_existing_device_users(request_id)
                else:
                    self.stats["errors"] += 1
                    print(f"Notice processing device {request_id}: {exception}")
            elif response and "name" in response:
                # Newly created device anchor in Cloud Identity
                self.stats["created_in_cloud_identity"] += 1
                self._approve_existing_device_users(response["name"])

        batch = self.ci_service.new_batch_http_request(callback=batch_callback)
        device_count = 0
        
        for device in devices:
            serial = device.get("serialNumber")
            if not serial:
                continue
                
            body = {
                "deviceType": "CHROME_OS",
                "serialNumber": serial,
                "assetTag": device.get("annotatedAssetId", serial),
                "model": device.get("model", "Google Chromebook"),
                "osVersion": device.get("osVersion", "ChromeOS"),
                "ownerType": "COMPANY"
            }
            
            ci_req = self.ci_service.devices().create(
                customer=self.ci_customer_id,
                body=body
            )
            batch.add(ci_req, request_id=serial)
            device_count += 1

        if device_count > 0:
            try:
                batch.execute()
            except HttpError as e:
                if e.resp.status in [429, 503]:
                    time.sleep(random.uniform(2, 5))
                    batch.execute()
                else:
                    print(f"Warning during batch execution: {e}")

    def _approve_existing_device_users(self, identifier: str):
        """Searches for existing device users on the target hardware and actively approves them."""
        try:
            device_name = identifier
            if not identifier.startswith("devices/"):
                # Try finding device by serial number
                query = f'serial_number = "{identifier}"'
                try:
                    req = self.ci_service.devices().list(customer=self.ci_customer_id, filter=query)
                    resp = req.execute()
                    devs = resp.get("devices", [])
                    if devs:
                        device_name = devs[0]["name"]
                    else:
                        return
                except Exception:
                    return

            # List device users
            du_req = self.ci_service.devices().deviceUsers().list(parent=device_name, customer=self.ci_customer_id)
            du_resp = du_req.execute()

            for du in du_resp.get("deviceUsers", []):
                state = du.get("managementState") or du.get("approvalState", "UNKNOWN_STATE")
                if state != "APPROVED":
                    body = {"customer": self.ci_customer_id}
                    app_req = self.ci_service.devices().deviceUsers().approve(name=du["name"], body=body)
                    app_req.execute()
                    self.stats["bindings_approved"] += 1
                    print(f"SUCCESS: Approved company-owned binding '{du['name']}' for '{du.get('userEmail')}'")

        except Exception as e:
            # Silent warning for non-critical binding approvals
            pass

if __name__ == "__main__":
    seeder = InventorySeeder()
    seeder.run()
