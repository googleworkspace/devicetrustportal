#!/usr/bin/env python3
"""
Automated Chromebook Inventory Seeding Script
Crawls active enterprise ChromeOS devices via Admin SDK Directory API and anchors them in Cloud Identity.
"""

import os
import sys
import time
import random
import google.auth
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import BatchHttpRequest

SCOPES = [
    "https://www.googleapis.com/auth/admin.directory.device.chromeos.readonly",
    "https://www.googleapis.com/auth/cloud-identity.devices"
]

class InventorySeeder:
    def __init__(self):
        self.customer_id = os.getenv("TENANT_CUSTOMER_ID", "my_customer")
        try:
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
        batch_size = 100

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
                    print("Ensure your Google Cloud Service Account or user credentials possess Domain-Wide Delegation (DWD) for Workspace Admin Directory and Cloud Identity Devices.")
                    sys.exit(1)
                
        print("\n=========================================================")
        print(f"✔ Live Inventory Seeding Complete! Processed {total_processed} hardware asset(s).")
        print("=========================================================")

    def _process_device_batch(self, devices):
        def batch_callback(request_id, response, exception):
            if exception:
                if isinstance(exception, HttpError) and exception.resp.status == 409:
                    pass
                else:
                    print(f"Error processing device {request_id}: {exception}")

        batch = self.ci_service.new_batch_http_request(callback=batch_callback)
        
        for device in devices:
            serial = device.get("serialNumber")
            if not serial:
                continue
                
            body = {
                "deviceType": "CHROME_OS",
                "serialNumber": serial,
                "assetTag": device.get("annotatedAssetId", serial)
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

if __name__ == "__main__":
    seeder = InventorySeeder()
    seeder.run()
