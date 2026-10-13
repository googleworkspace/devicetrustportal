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
import ssl
import datetime
import threading
from typing import List, Dict, Any, Optional, Callable
try:
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
    from googleapiclient.http import BatchHttpRequest
except ImportError:
    service_account = None
    build = None
    class HttpError(Exception):
        pass
    BatchHttpRequest = None


def is_transient_socket_error(exc: Exception) -> bool:
    """Returns True if exc is a stale keep-alive socket / BrokenPipe / TLS EOF error from httplib2."""
    if isinstance(exc, HttpError):
        return False
    if isinstance(exc, (BrokenPipeError, ConnectionError, TimeoutError, ssl.SSLError)):
        return True
    msg = str(exc).lower()
    markers = (
        "broken pipe",
        "errno 32",
        "errno 104",
        "connection reset",
        "unexpected_eof_while_reading",
        "eof occurred in violation of protocol",
        "remotedisconnected",
        "remote end closed connection",
        "badstatusline",
        "timed out",
    )
    return any(m in msg for m in markers)

def resolve_dwd_key_path() -> Optional[str]:
    """Resolves the DWD service account key file path, recovering from MSYS2/Windows path mangling."""
    env_path = (os.getenv("GOOGLE_APPLICATION_CREDENTIALS") or "").strip()
    candidates = []
    if env_path:
        candidates.append(env_path)
        if not env_path.startswith("/"):
            candidates.append(f"/{env_path}")
    candidates.extend(["/secrets/dwd_key.json", "dwd_key.json"])
    for candidate in candidates:
        if candidate and os.path.exists(candidate):
            if env_path and candidate != env_path:
                print(
                    f"INFO [cloud_identity.py]: Configured GOOGLE_APPLICATION_CREDENTIALS='{env_path}' not found; "
                    f"recovered mounted DWD key at '{candidate}'."
                )
                os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = candidate
            return candidate
    return None

def normalize_customer_id(customer_id: Optional[str]) -> str:
    """Ensures customer_id is formatted as 'customers/<id>' as required by Cloud Identity API."""
    cid = (customer_id or "my_customer").strip()
    if not cid:
        cid = "my_customer"
    if not cid.startswith("customers/"):
        cid = f"customers/{cid}"
    return cid

class CloudIdentityService:
    def __init__(self):
        self._lock = threading.RLock()
        self.scopes = [
            "https://www.googleapis.com/auth/cloud-identity.devices"
        ]
        self.init_error: Optional[str] = None
        self.key_path = resolve_dwd_key_path()
        self.admin_email = (os.getenv("WORKSPACE_ADMIN_EMAIL") or "").strip()

        if not self.key_path:
            raw_env_cred = (os.getenv("GOOGLE_APPLICATION_CREDENTIALS") or "").strip()
            self.init_error = (
                f"DWD service account key file not found (GOOGLE_APPLICATION_CREDENTIALS='{raw_env_cred}', "
                "checked '/secrets/dwd_key.json' and 'dwd_key.json')."
            )
            print(f"ERROR [cloud_identity.py]: {self.init_error}")
            self.service = None
            return

        if not self.admin_email:
            self.init_error = "WORKSPACE_ADMIN_EMAIL environment variable is not set for Domain-Wide Delegation."
            print(f"ERROR [cloud_identity.py]: {self.init_error}")
            self.service = None
            return

        try:
            credentials = service_account.Credentials.from_service_account_file(
                self.key_path, scopes=self.scopes, subject=self.admin_email
            )
            self.service = build("cloudidentity", "v1", credentials=credentials)
            print(
                f"INFO [cloud_identity.py]: Initialized Cloud Identity v1 client with DWD key '{self.key_path}' "
                f"and subject '{self.admin_email}'."
            )
        except Exception as e:
            self.init_error = str(e)
            print(f"Error initializing Cloud Identity service: {e}")
            self.service = None

    def _rebuild_service(self) -> None:
        """Rebuilds the Cloud Identity client when httplib2's keep-alive socket breaks."""
        current = getattr(self, "service", None)
        if current is not None and hasattr(current, "_mock_name"):
            return
        key_path = getattr(self, "key_path", None)
        admin_email = getattr(self, "admin_email", None)
        if not key_path or not admin_email or not service_account or not build:
            return
        try:
            credentials = service_account.Credentials.from_service_account_file(
                key_path, scopes=self.scopes, subject=admin_email
            )
            self.service = build("cloudidentity", "v1", credentials=credentials)
            print("INFO [cloud_identity.py]: Rebuilt Cloud Identity v1 client after transient socket reset.")
        except Exception as rebuild_err:
            print(f"WARNING [cloud_identity.py]: Failed to rebuild Cloud Identity client: {rebuild_err}")

    def execute_with_retry(self, op: Callable[[], Any], max_attempts: int = 3) -> Any:
        """Executes a Cloud Identity request under lock, rebuilding the client on broken pipe / TLS EOF."""
        lock = getattr(self, "_lock", None)
        last_err: Optional[Exception] = None
        for attempt in range(max_attempts):
            try:
                if lock:
                    with lock:
                        return op()
                return op()
            except Exception as exc:
                last_err = exc
                if not is_transient_socket_error(exc) or attempt + 1 >= max_attempts:
                    raise
                print(
                    f"WARNING [cloud_identity.py]: Transient socket error "
                    f"(attempt {attempt + 1}/{max_attempts}): {exc}; resetting connection pool."
                )
                if lock:
                    with lock:
                        self._rebuild_service()
                else:
                    self._rebuild_service()
        if last_err:
            raise last_err
        return None

    def get_device_user(self, device_user_name: str, customer_id: str) -> Optional[Dict[str, Any]]:
        if not self.service:
            raise Exception("Cloud Identity service not initialized with valid credentials")

        cid = normalize_customer_id(customer_id)
        try:
            return self.execute_with_retry(
                lambda: self.service.devices().deviceUsers().get(name=device_user_name, customer=cid).execute()
            )
        except HttpError as e:
            print(f"Cloud Identity API error during get_device_user: {e}")
            return None

    def approve_device_user(self, device_user_name: str, customer_id: str) -> Dict[str, Any]:
        if not self.service:
            raise Exception("Cloud Identity service not initialized with valid credentials")

        cid = normalize_customer_id(customer_id)
        try:
            body = {"customer": cid}
            return self.execute_with_retry(
                lambda: self.service.devices().deviceUsers().approve(name=device_user_name, body=body).execute()
            )
        except HttpError as e:
            raise Exception(f"Cloud Identity API error during approve: {e}")

    def lookup_device_user(self, user_email: str, raw_device_id: str, customer_id: str) -> Optional[str]:
        if not self.service:
            raise Exception("Cloud Identity service not initialized with valid credentials")

        cid = normalize_customer_id(customer_id)
        try:
            query = f"id=='{raw_device_id}'" if not raw_device_id.startswith("devices/") else ""
            if not query and raw_device_id.startswith("devices/"):
                device_name = raw_device_id
            else:
                response = self.execute_with_retry(
                    lambda: self.service.devices().list(customer=cid, filter=query).execute()
                )
                devices = response.get("devices", [])
                if not devices:
                    return None
                device_name = devices[0]["name"]

            users_response = self.execute_with_retry(
                lambda: self.service.devices().deviceUsers().list(parent=device_name, customer=cid).execute()
            )
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

        cid = normalize_customer_id(customer_id)
        try:
            cutoff_date = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=threshold_days)
            cutoff_str = cutoff_date.strftime("%Y-%m-%dT%H:%M:%SZ")
            
            query = f"lastSyncTime < '{cutoff_str}'"
            try:
                response = self.execute_with_retry(
                    lambda: self.service.devices().list(customer=cid, filter=query).execute()
                )
                devices = response.get("devices", [])
            except HttpError as filter_err:
                if getattr(filter_err, "resp", None) and getattr(filter_err.resp, "status", None) == 400:
                    all_resp = self.execute_with_retry(
                        lambda: self.service.devices().list(customer=cid).execute()
                    )
                    devices = [
                        d
                        for d in (all_resp.get("devices", []) or [])
                        if (d.get("lastSyncTime") or "") and d.get("lastSyncTime") < cutoff_str
                    ]
                else:
                    raise
            
            inactive_device_users = []
            for d in devices:
                du_resp = self.execute_with_retry(
                    lambda d_name=d["name"]: self.service.devices().deviceUsers().list(parent=d_name, customer=cid).execute()
                )
                for du in du_resp.get("deviceUsers", []):
                    state = (du.get("managementState") or du.get("approvalState") or "").upper()
                    if state == "APPROVED":
                        inactive_device_users.append(du)
                        
            return inactive_device_users
        except HttpError as e:
            raise Exception(f"Cloud Identity API error during inactive list: {e}")

    def revoke_device_user(self, device_user_name: str, customer_id: str, action: str = "BLOCK") -> Dict[str, Any]:
        if not self.service:
            raise Exception("Cloud Identity service not initialized with valid credentials")

        cid = normalize_customer_id(customer_id)
        try:
            # Strictly enforce BLOCK method to ensure revoked devices remain explicitly BLOCKED
            body = {"customer": cid}
            return self.execute_with_retry(
                lambda: self.service.devices().deviceUsers().block(name=device_user_name, body=body).execute()
            )
        except HttpError as e:
            raise Exception(f"Cloud Identity API error during revocation: {e}")

    def revoke_device_users_bulk(self, device_user_names: List[str], customer_id: str, action: str = "BLOCK") -> Dict[str, Any]:
        if not self.service:
            raise Exception("Cloud Identity service not initialized with valid credentials")

        cid = normalize_customer_id(customer_id)
        print(f"INFO [cloud_identity.py]: Executing BatchHttpRequest for {len(device_user_names)} device revocation(s) using BLOCK method...")
        errors: List[Any] = []

        def _run_batch():
            errors.clear()
            batch = self.service.new_batch_http_request()

            def callback(request_id, response, exception):
                if exception:
                    errors.append(exception)

            body = {"customer": cid}
            for du_name in device_user_names:
                req = self.service.devices().deviceUsers().block(name=du_name, body=body)
                batch.add(req, callback=callback)

            batch.execute()

        self.execute_with_retry(_run_batch)
        if errors:
            raise Exception(f"Batch revocation encountered {len(errors)} error(s). First error: {errors[0]}")
            
        return {"status": "SUCCESS", "revoked_count": len(device_user_names)}

cloud_identity_service = CloudIdentityService()
