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
        self.customer_id = os.getenv("TENANT_CUSTOMER_ID", "my_customer")
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

    def run(self):
        print("=========================================================")
        print("      Starting Live Chromebook Inventory Seeding Run     ")
        print("=========================================================")
        
        page_token = None
        total_processed = 0
        batch_size = 50

        while True:
            try:
                request = self.admin_service.chromeosdevices().list(
                    customerId=self.customer_id,
                    pageToken=page_token,
                    maxResults=batch_size
                )
                response = request.execute()
                devices = response.get("chromeosdevices", [])

                if not devices:
                    break

                self._process_device_batch(devices)
                total_processed += len(devices)
                print(f"Successfully processed {total_processed} active Chromebook(s)...")

                page_token = response.get("nextPageToken")
                if not page_token:
                    break

            except HttpError as e:
                if e.resp.status in [429, 503]:
                    time.sleep(random.uniform(5, 10))
                    continue
                else:
                    print(f"\n❌ Live API Error during pagination: {e}")
                    sys.exit(1)
                
        print("\n=========================================================")
        print(f"✔ Live Inventory Seeding Complete! Processed {total_processed} hardware asset(s).")
        print("=========================================================")

    def _process_device_batch(self, devices):
        def batch_callback(request_id, response, exception):
            if exception:
                if isinstance(exception, HttpError) and exception.resp.status == 409:
                    # Device already exists, attempt to approve its bindings
                    self._approve_existing_device_users(request_id)
                else:
                    print(f"Error processing device {request_id}: {exception}")
            elif response and "name" in response:
                # Newly created device, attempt to approve its bindings
                self._approve_existing_device_users(response["name"])

        batch = self.ci_service.new_batch_http_request(callback=batch_callback)
        
        for device in devices:
            serial = device.get("serialNumber")
            if not serial:
                continue
                
            body = {
                "deviceType": "CHROME_OS",
                "serialNumber": serial,
                "assetTag": device.get("annotatedAssetId", serial),
                "ownerType": "COMPANY"
            }
            
            ci_req = self.ci_service.devices().create(
                customer=f"customers/{self.customer_id}",
                body=body
            )
            batch.add(ci_req, request_id=serial)

        try:
            batch.execute()
        except HttpError as e:
            if e.resp.status in [429, 503]:
                time.sleep(random.uniform(2, 5))
                batch.execute()

    def _approve_existing_device_users(self, identifier: str):
        """Searches for existing device users on the target hardware and actively approves them."""
        try:
            device_name = identifier
            if not identifier.startswith("devices/"):
                query = f"serialNumber=='{identifier}'"
                req = self.ci_service.devices().list(customer=f"customers/{self.customer_id}", filter=query)
                resp = req.execute()
                devs = resp.get("devices", [])
                if not devs:
                    return
                device_name = devs[0]["name"]

            # List device users
            du_req = self.ci_service.devices().deviceUsers().list(parent=device_name, customer=f"customers/{self.customer_id}")
            du_resp = du_req.execute()

            for du in du_resp.get("deviceUsers", []):
                state = du.get("managementState") or du.get("approvalState", "UNKNOWN_STATE")
                if state != "APPROVED":
                    body = {"customer": f"customers/{self.customer_id}"}
                    app_req = self.ci_service.devices().deviceUsers().approve(name=du["name"], body=body)
                    app_req.execute()
                    print(f"SUCCESS: Approved company-owned binding '{du['name']}' for '{du.get('userEmail')}'")

        except Exception as e:
            print(f"Warning: Failed to approve bindings for '{identifier}': {e}")

if __name__ == "__main__":
    seeder = InventorySeeder()
    seeder.run()
