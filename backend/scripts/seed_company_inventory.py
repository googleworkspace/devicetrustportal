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
from collections import deque
from pathlib import Path
from typing import Optional, Dict, Any, List, Callable, Deque

# Ensure repository root is always in sys.path
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import google.auth
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from backend.services.cloud_identity import (
    resolve_dwd_key_path,
    get_http_error_status,
    is_retryable_http_error,
    is_transient_socket_error,
)

SCOPES = [
    "https://www.googleapis.com/auth/admin.directory.device.chromeos.readonly",
    "https://www.googleapis.com/auth/cloud-identity.devices"
]


def _is_already_exists_error(exc: Exception) -> bool:
    status = get_http_error_status(exc)
    if status == 409:
        return True
    msg = str(exc).lower()
    return "already_exists" in msg or "already exists" in msg


def _is_rate_or_transient_error(exc: Exception) -> bool:
    return is_retryable_http_error(exc) or is_transient_socket_error(exc)


class InventorySeeder:
    def __init__(
        self,
        max_retries: int = 8,
        base_backoff_sec: float = 2.0,
        max_backoff_sec: float = 65.0,
        jitter_sec: float = 1.5,
        write_sub_batch_size: int = 25,
        max_writes_per_minute: int = 150,
    ):
        self.max_retries = max_retries
        self.base_backoff_sec = base_backoff_sec
        self.max_backoff_sec = max_backoff_sec
        self.jitter_sec = jitter_sec
        self.write_sub_batch_size = max(1, write_sub_batch_size)
        self.max_writes_per_minute = max(1, max_writes_per_minute)
        self._write_timestamps: Deque[float] = deque()
        self.existing_devices_by_serial: Dict[str, str] = {}

        raw_cust = os.getenv("TENANT_CUSTOMER_ID", "my_customer")
        # Strip customers/ prefix if provided
        self.raw_customer_id = raw_cust.replace("customers/", "").strip() if raw_cust else "my_customer"
        if not self.raw_customer_id:
            self.raw_customer_id = "my_customer"

        key_path = resolve_dwd_key_path()
        admin_email = (os.getenv("WORKSPACE_ADMIN_EMAIL") or "").strip()

        try:
            if key_path and admin_email:
                print(f"Initializing Google API client with DWD impersonation for subject: {admin_email}")
                credentials = service_account.Credentials.from_service_account_file(
                    key_path, scopes=SCOPES, subject=admin_email
                )
            else:
                raw_env_cred = (os.getenv("GOOGLE_APPLICATION_CREDENTIALS") or "").strip()
                if raw_env_cred and not os.path.exists(raw_env_cred):
                    os.environ.pop("GOOGLE_APPLICATION_CREDENTIALS", None)
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
            cust_res = self._execute_with_backoff(
                lambda: self.admin_service.customers().get(customerKey="my_customer").execute()
            )
            if cust_res and "id" in cust_res:
                self.resolved_customer_id = cust_res["id"]
                print(f"Successfully resolved Google Workspace Customer ID: {self.resolved_customer_id}")
        except Exception:
            pass

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

    def _compute_backoff(self, attempt: int) -> float:
        base = min(self.max_backoff_sec, self.base_backoff_sec * (2 ** attempt))
        jitter = random.uniform(0.0, self.jitter_sec) if self.jitter_sec > 0 else 0.0
        return base + jitter

    def _execute_with_backoff(self, op: Callable[[], Any]) -> Any:
        """Executes a single Google API operation with silent exponential backoff on 429/5xx/socket errors."""
        last_err: Optional[Exception] = None
        for attempt in range(self.max_retries + 1):
            try:
                return op()
            except Exception as exc:
                last_err = exc
                if _is_rate_or_transient_error(exc) and attempt < self.max_retries:
                    sleep_sec = self._compute_backoff(attempt)
                    if sleep_sec > 0:
                        time.sleep(sleep_sec)
                    continue
                raise
        if last_err:
            raise last_err
        return None

    def _pace_write_requests(self, count: int) -> None:
        """Paces Cloud Identity write requests to stay safely under the 180 writes/min project quota."""
        if count <= 0 or self.max_writes_per_minute <= 0:
            return
        now = time.monotonic()
        window_sec = 60.0
        while self._write_timestamps and (now - self._write_timestamps[0]) >= window_sec:
            self._write_timestamps.popleft()

        if len(self._write_timestamps) + count > self.max_writes_per_minute and self._write_timestamps:
            oldest = self._write_timestamps[0]
            wait_sec = max(0.0, window_sec - (now - oldest) + 0.5)
            if wait_sec > 0 and self.base_backoff_sec > 0:
                time.sleep(wait_sec)
            now = time.monotonic()
            while self._write_timestamps and (now - self._write_timestamps[0]) >= window_sec:
                self._write_timestamps.popleft()

        stamp = time.monotonic()
        for _ in range(count):
            self._write_timestamps.append(stamp)

    def _preload_existing_company_devices(self) -> None:
        """Preloads existing Cloud Identity serial numbers via read quota to avoid redundant write calls."""
        page_token: Optional[str] = None
        try:
            while True:
                resp = self._execute_with_backoff(
                    lambda pt=page_token: self.ci_service.devices().list(
                        customer=self.ci_customer_id,
                        pageSize=100,
                        pageToken=pt,
                    ).execute()
                )
                if not isinstance(resp, dict):
                    break
                for dev in resp.get("devices", []) or []:
                    if not isinstance(dev, dict):
                        continue
                    serial = (dev.get("serialNumber") or "").strip()
                    name = (dev.get("name") or "").strip()
                    if serial and name:
                        self.existing_devices_by_serial[serial] = name
                page_token = resp.get("nextPageToken")
                if not page_token:
                    break
        except Exception:
            # Non-fatal: if preloading is unavailable, fallback to batch create + 409 handling
            pass

    def run(self):
        print("\n=========================================================")
        print("      Starting Live Chromebook Inventory Seeding Run     ")
        print(f"  Directory Customer:     {self.directory_customer_id}")
        print(f"  Cloud Identity Target:  {self.ci_customer_id}")
        print("=========================================================\n")

        self._preload_existing_company_devices()

        page_token = None
        batch_size = 50

        while True:
            try:
                response = self._execute_with_backoff(
                    lambda pt=page_token: self.admin_service.chromeosdevices().list(
                        customerId=self.directory_customer_id,
                        pageToken=pt,
                        maxResults=batch_size,
                        projection="FULL"
                    ).execute()
                )
                devices = response.get("chromeosdevices", []) if isinstance(response, dict) else []

                if not devices:
                    break

                self._process_device_batch(devices)
                self.stats["total_directory_devices"] += len(devices)
                print(f"Processed batch of {len(devices)} device(s) (Total discovered: {self.stats['total_directory_devices']})...")

                page_token = response.get("nextPageToken") if isinstance(response, dict) else None
                if not page_token:
                    break

            except HttpError as e:
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
        pending_by_serial: Dict[str, Dict[str, Any]] = {}
        for device in devices:
            serial = (device.get("serialNumber") or "").strip()
            if not serial:
                continue
            if serial in self.existing_devices_by_serial:
                self.stats["already_registered"] += 1
                continue
            pending_by_serial[serial] = device

        if not pending_by_serial:
            return

        serial_items = list(pending_by_serial.items())
        for start_idx in range(0, len(serial_items), self.write_sub_batch_size):
            chunk_map: Dict[str, Dict[str, Any]] = dict(
                serial_items[start_idx : start_idx + self.write_sub_batch_size]
            )
            self._execute_create_sub_batch_with_backoff(chunk_map)

    def _execute_create_sub_batch_with_backoff(self, chunk_map: Dict[str, Dict[str, Any]]) -> None:
        remaining: Dict[str, Dict[str, Any]] = dict(chunk_map)

        for attempt in range(self.max_retries + 1):
            if not remaining:
                break

            rate_limited_serials: List[str] = []
            non_retryable_failed_serials: List[str] = []

            def batch_callback(request_id, response, exception):
                if exception:
                    if _is_already_exists_error(exception):
                        self.stats["already_registered"] += 1
                        self.existing_devices_by_serial[request_id] = request_id
                        self._approve_existing_device_users(request_id)
                    elif _is_rate_or_transient_error(exception):
                        rate_limited_serials.append(request_id)
                    else:
                        non_retryable_failed_serials.append(request_id)
                elif response and "name" in response:
                    self.stats["created_in_cloud_identity"] += 1
                    self.existing_devices_by_serial[request_id] = response["name"]
                    self._approve_existing_device_users(response["name"])

            batch = self.ci_service.new_batch_http_request(callback=batch_callback)
            for serial, device in remaining.items():
                body = {
                    "deviceType": "CHROME_OS",
                    "serialNumber": serial,
                    "assetTag": device.get("annotatedAssetId", serial),
                    "model": device.get("model", "Google Chromebook"),
                    "osVersion": device.get("osVersion", "ChromeOS"),
                    "ownerType": "COMPANY",
                }
                ci_req = self.ci_service.devices().create(
                    customer=self.ci_customer_id,
                    body=body,
                )
                batch.add(ci_req, request_id=serial)

            self._pace_write_requests(len(remaining))

            try:
                batch.execute()
            except Exception as outer_exc:
                if _is_rate_or_transient_error(outer_exc) and attempt < self.max_retries:
                    sleep_sec = self._compute_backoff(attempt)
                    if sleep_sec > 0:
                        time.sleep(sleep_sec)
                    continue
                self.stats["errors"] += len(remaining)
                return

            if non_retryable_failed_serials:
                self.stats["errors"] += len(non_retryable_failed_serials)

            if not rate_limited_serials:
                return

            if attempt >= self.max_retries:
                self.stats["errors"] += len(rate_limited_serials)
                return

            remaining = {
                s: remaining[s]
                for s in rate_limited_serials
                if s in remaining
            }
            sleep_sec = self._compute_backoff(attempt)
            if sleep_sec > 0:
                time.sleep(sleep_sec)

    def _approve_existing_device_users(self, identifier: str):
        """Searches for existing device users on the target hardware and actively approves them."""
        try:
            device_name = identifier
            if not identifier.startswith("devices/"):
                cached_name = self.existing_devices_by_serial.get(identifier, "")
                if cached_name.startswith("devices/"):
                    device_name = cached_name
                else:
                    query = f'serial_number = "{identifier}"'
                    try:
                        resp = self._execute_with_backoff(
                            lambda: self.ci_service.devices().list(customer=self.ci_customer_id, filter=query).execute()
                        )
                        devs = resp.get("devices", []) if isinstance(resp, dict) else []
                        if devs:
                            device_name = devs[0]["name"]
                            self.existing_devices_by_serial[identifier] = device_name
                        else:
                            return
                    except Exception:
                        return

            du_resp = self._execute_with_backoff(
                lambda: self.ci_service.devices().deviceUsers().list(parent=device_name, customer=self.ci_customer_id).execute()
            )

            for du in (du_resp.get("deviceUsers", []) if isinstance(du_resp, dict) else []):
                state = du.get("managementState") or du.get("approvalState", "UNKNOWN_STATE")
                if state != "APPROVED":
                    body = {"customer": self.ci_customer_id}
                    self._execute_with_backoff(
                        lambda du_name=du["name"]: self.ci_service.devices().deviceUsers().approve(name=du_name, body=body).execute()
                    )
                    self.stats["bindings_approved"] += 1
                    print(f"SUCCESS: Approved company-owned binding '{du['name']}' for '{du.get('userEmail')}'")

        except Exception:
            # Silent warning for non-critical binding approvals
            pass

if __name__ == "__main__":
    seeder = InventorySeeder()
    seeder.run()
