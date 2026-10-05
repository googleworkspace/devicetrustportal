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
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
from pydantic import BaseModel
from fastapi import APIRouter, HTTPException, Depends, Request
from backend.services.config_service import config_service
from backend.services.cloud_identity import cloud_identity_service, normalize_customer_id
from backend.services.directory_service import directory_service
from backend.services.session_guard import DeviceRecord
from backend.routes.session_watch import session_guard
from backend.routes.admin import get_current_user_email

router = APIRouter(prefix="/api/devices", tags=["Devices"])

def verify_device_user_ownership(device_user_name: str, user_email: str, customer_id: str, is_admin: bool):
    if is_admin:
        return
    norm_user = user_email.lower().strip()
    if device_user_name.startswith("directory/"):
        if f"/deviceusers/{norm_user}" in device_user_name.lower():
            return
        raise HTTPException(status_code=403, detail="Access denied: You can only modify your own device bindings.")
    du_info = cloud_identity_service.get_device_user(device_user_name, customer_id)
    if not du_info:
        raise HTTPException(status_code=404, detail=f"Target device binding '{device_user_name}' not found.")
    owner_email = du_info.get("userEmail", "").lower().strip()
    if owner_email != norm_user:
        raise HTTPException(status_code=403, detail="Access denied: You can only modify your own device bindings.")

class DeviceUserItem(BaseModel):
    device_user_name: str
    device_type: str
    model: str
    os_version: str
    serial_number: str
    approval_state: str
    owner_type: str
    last_sync_time: str
    annotated_user: Optional[str] = ""

class DeviceActionRequest(BaseModel):
    device_user_name: str

class BulkRevokeRequest(BaseModel):
    device_user_names: List[str]

INVALID_SERIALS = frozenset({
    "N/A", "NONE", "UNKNOWN", "NULL", "NOT AVAILABLE", "[NOT SPECIFIED]",
    "UNDEFINED", "[UNKNOWN]", "[N/A]", "-"
})

def is_valid_serial(s: Any) -> bool:
    if s is None:
        return False
    cleaned = str(s).strip().upper()
    return bool(cleaned and cleaned not in INVALID_SERIALS)

def normalize_sync_time(t: Any) -> str:
    cleaned = str(t or "").strip()
    if not cleaned or cleaned.upper() in ("N/A", "NONE", "NULL", "UNKNOWN"):
        return "N/A"
    return cleaned

def sync_time_sort_key(t: Any) -> float:
    norm = normalize_sync_time(t)
    if norm == "N/A":
        return -1.0
    try:
        cleaned = norm
        if cleaned.endswith("Z") or cleaned.endswith("z"):
            cleaned = cleaned[:-1] + "+00:00"
        dt = datetime.fromisoformat(cleaned)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except Exception:
        return 0.0

def extract_field(d: Dict[str, Any], *keys: str, default: str = "") -> str:
    for k in keys:
        val = d.get(k)
        if val is not None:
            s = str(val).strip()
            if s:
                return s
    return default

def normalize_approval_state(*raw_states: Any) -> str:
    """Normalizes Cloud Identity DeviceUser and Device managementState/approvalState values."""
    cleaned_states: List[str] = []
    for raw in raw_states:
        val = str(raw or "").strip().upper()
        if val and val not in ("MANAGEMENT_STATE_UNSPECIFIED", "APPROVAL_STATE_UNSPECIFIED", "UNSPECIFIED"):
            cleaned_states.append(val)

    for val in cleaned_states:
        if val == "BLOCKED":
            return "BLOCKED"
        if val == "APPROVED":
            return "APPROVED"
        if val in ("PENDING_APPROVAL", "PENDING"):
            return "PENDING_APPROVAL"
        if val in ("WIPED", "WIPING", "ACCOUNT_WIPED", "ACCOUNT_WIPING"):
            return "WIPED"

    return cleaned_states[0] if cleaned_states else "UNKNOWN_STATE"

def extract_device_metadata(d: Dict[str, Any]) -> Dict[str, str]:
    device_type = extract_field(d, "deviceType", default="UNKNOWN_TYPE").upper()
    model = extract_field(d, "model", default="Unknown Model")
    os_version = extract_field(d, "osVersion", "os", default="Unknown OS")
    owner_type = extract_field(d, "ownerType", default="BYOD").upper()
    raw_serial = extract_field(d, "serialNumber", "deviceSerialNumber", "imei", "meid", default="")
    serial_number = raw_serial if is_valid_serial(raw_serial) else "N/A"
    dev_last_sync = normalize_sync_time(d.get("lastSyncTime"))
    dev_mgmt_state = extract_field(d, "managementState", "approvalState", default="")
    return {
        "device_type": device_type,
        "model": model,
        "os_version": os_version,
        "owner_type": owner_type,
        "serial_number": serial_number,
        "last_sync_time": dev_last_sync,
        "management_state": dev_mgmt_state,
    }

def crawl_devices_for_user(
    customer_id: str,
    target_email: str,
    query_filter: Optional[str] = None
) -> tuple[List[DeviceUserItem], int]:
    """Crawls Cloud Identity devices (filtered or unfiltered) and extracts device-user bindings matching target_email."""
    if not cloud_identity_service.service:
        return [], 0

    norm_email = (target_email or "").lower().strip()
    if not norm_email:
        return [], 0

    cid = normalize_customer_id(customer_id)

    matched_items: List[DeviceUserItem] = []
    total_devices_scanned = 0
    seen_dus = set()
    device_map: Dict[str, Dict[str, Any]] = {}
    devices_with_matched_du = set()
    du_errors: List[str] = []

    next_page_token = None
    seen_page_tokens = set()

    # Step 1: List matching Device resources
    while True:
        list_kwargs: Dict[str, Any] = {
            "customer": cid,
            "pageSize": 100,
        }
        if next_page_token:
            list_kwargs["pageToken"] = next_page_token
        if query_filter:
            list_kwargs["filter"] = query_filter

        try:
            with cloud_identity_service._lock:
                request = cloud_identity_service.service.devices().list(**list_kwargs)
                response = request.execute() or {}
        except Exception as list_err:
            print(f"WARNING [devices.py]: Failed to fetch page of devices: {list_err}")
            if not next_page_token:
                raise
            break

        devices = response.get("devices") or []
        if not isinstance(devices, list):
            devices = []
        total_devices_scanned += len(devices)

        for d in devices:
            if not d or not isinstance(d, dict):
                continue
            device_name = extract_field(d, "name", "id", "deviceId", default="")
            if not device_name:
                continue
            if not device_name.startswith("devices/"):
                device_name = f"devices/{device_name}"
            device_map[device_name] = d

        raw_next = str(response.get("nextPageToken") or "").strip()
        next_page_token = raw_next if raw_next else None
        if not next_page_token or next_page_token in seen_page_tokens:
            break
        seen_page_tokens.add(next_page_token)

    # Step 2: Query deviceUsers(parent='devices/-') directly with email filter when performing filtered lookup
    if query_filter:
        try:
            du_wildcard_token = None
            seen_wildcard_tokens = set()
            while True:
                du_w_kwargs: Dict[str, Any] = {
                    "parent": "devices/-",
                    "customer": cid,
                    "pageSize": 20,
                    "filter": query_filter,
                }
                if du_wildcard_token:
                    du_w_kwargs["pageToken"] = du_wildcard_token
                with cloud_identity_service._lock:
                    du_w_req = cloud_identity_service.service.devices().deviceUsers().list(**du_w_kwargs)
                    du_w_resp = du_w_req.execute() or {}
                du_w_list = du_w_resp.get("deviceUsers") or []
                if not isinstance(du_w_list, list):
                    du_w_list = []

                for du in du_w_list:
                    if not du or not isinstance(du, dict):
                        continue
                    du_email = str(du.get("userEmail") or "").lower().strip()
                    if du_email and du_email == norm_email:
                        du_name = str(du.get("name") or "").strip()
                        if not du_name or "/deviceUsers/" not in du_name:
                            continue
                        parent_dev_name = du_name.split("/deviceUsers/")[0]
                        if parent_dev_name not in device_map:
                            try:
                                with cloud_identity_service._lock:
                                    fetched_dev = cloud_identity_service.service.devices().get(
                                        name=parent_dev_name, customer=cid
                                    ).execute() or {}
                                if isinstance(fetched_dev, dict) and isinstance(fetched_dev.get("name"), str) and fetched_dev.get("name"):
                                    device_map[parent_dev_name] = fetched_dev
                                    total_devices_scanned += 1
                                else:
                                    continue
                            except Exception as get_err:
                                print(f"WARNING [devices.py]: Could not fetch parent device '{parent_dev_name}': {get_err}")
                                continue

                        if du_name not in seen_dus:
                            seen_dus.add(du_name)
                            devices_with_matched_du.add(parent_dev_name)
                            meta = extract_device_metadata(device_map.get(parent_dev_name, {}))
                            state = normalize_approval_state(
                                du.get("managementState"),
                                du.get("approvalState"),
                                meta["management_state"],
                            )
                            du_sync = normalize_sync_time(du.get("lastSyncTime"))
                            effective_sync = du_sync if du_sync != "N/A" else meta["last_sync_time"]
                            matched_items.append(
                                DeviceUserItem(
                                    device_user_name=du_name,
                                    device_type=meta["device_type"],
                                    model=meta["model"],
                                    os_version=meta["os_version"],
                                    serial_number=meta["serial_number"],
                                    approval_state=state,
                                    owner_type=meta["owner_type"],
                                    last_sync_time=effective_sync,
                                    annotated_user=norm_email,
                                )
                            )

                raw_w_next = str(du_w_resp.get("nextPageToken") or "").strip()
                du_wildcard_token = raw_w_next if raw_w_next else None
                if not du_wildcard_token or du_wildcard_token in seen_wildcard_tokens:
                    break
                seen_wildcard_tokens.add(du_wildcard_token)
        except Exception as w_err:
            print(f"WARNING [devices.py]: Wildcard deviceUsers.list(parent='devices/-', filter='{query_filter}') notice: {w_err}")

    # Step 3: For any discovered Device not yet matched via 'devices/-', inspect its deviceUsers directly
    for device_name, d in device_map.items():
        if device_name in devices_with_matched_du:
            continue
        meta = extract_device_metadata(d)
        try:
            du_page_token = None
            seen_du_tokens = set()
            while True:
                du_kwargs: Dict[str, Any] = {
                    "parent": device_name,
                    "customer": cid,
                }
                if du_page_token:
                    du_kwargs["pageToken"] = du_page_token
                with cloud_identity_service._lock:
                    du_req = cloud_identity_service.service.devices().deviceUsers().list(**du_kwargs)
                    du_resp = du_req.execute() or {}

                du_list = du_resp.get("deviceUsers") or []
                if not isinstance(du_list, list):
                    du_list = []

                for du in du_list:
                    if not du or not isinstance(du, dict):
                        continue
                    du_email = str(du.get("userEmail") or "").lower().strip()
                    if du_email and du_email == norm_email:
                        du_name = str(du.get("name") or f"{device_name}/deviceUsers/{norm_email}").strip()
                        if du_name and du_name not in seen_dus:
                            seen_dus.add(du_name)
                            devices_with_matched_du.add(device_name)
                            state = normalize_approval_state(
                                du.get("managementState"),
                                du.get("approvalState"),
                                meta["management_state"],
                            )
                            du_sync = normalize_sync_time(du.get("lastSyncTime"))
                            effective_sync = du_sync if du_sync != "N/A" else meta["last_sync_time"]

                            matched_items.append(
                                DeviceUserItem(
                                    device_user_name=du_name,
                                    device_type=meta["device_type"],
                                    model=meta["model"],
                                    os_version=meta["os_version"],
                                    serial_number=meta["serial_number"],
                                    approval_state=state,
                                    owner_type=meta["owner_type"],
                                    last_sync_time=effective_sync,
                                    annotated_user=norm_email,
                                )
                            )

                raw_du_next = str(du_resp.get("nextPageToken") or "").strip()
                du_page_token = raw_du_next if raw_du_next else None
                if not du_page_token or du_page_token in seen_du_tokens:
                    break
                seen_du_tokens.add(du_page_token)
        except Exception as du_err:
            du_errors.append(f"{device_name}: {du_err}")
            print(f"WARNING [devices.py]: Failed to list device users for '{device_name}': {du_err}")

    if not matched_items and du_errors and len(du_errors) == len(device_map):
        raise RuntimeError(f"Failed to list deviceUsers for discovered devices ({du_errors[0]})")

    return matched_items, total_devices_scanned

@router.get("/my-devices", response_model=List[DeviceUserItem])
def get_my_approved_devices(user_email: str = Depends(get_current_user_email)):
    """Fetches the authentic list of devices assigned to the requesting user using server-side email filtering with adaptive fallback."""
    target_email = (user_email or "").lower().strip()
    if not target_email:
        return []

    if not cloud_identity_service.service:
        err_detail = getattr(cloud_identity_service, "init_error", None) or "Missing or invalid Domain-Wide Delegation credentials."
        raise HTTPException(
            status_code=500,
            detail=(
                f"Cloud Identity API service is not initialized ({err_detail}). "
                "Verify that /secrets/dwd_key.json is mounted, WORKSPACE_ADMIN_EMAIL is set to an active "
                "Google Workspace Super Admin, and Domain-Wide Delegation scopes are authorized."
            )
        )

    config = config_service.get_tenant_config()
    cid = normalize_customer_id(config.customer_id)
    my_devices: List[DeviceUserItem] = []
    is_admin = directory_service.verify_user_is_admin(target_email, portal_admins=config.portal_admins)

    query_filter = f"email:{target_email}"
    dwd_subject = getattr(cloud_identity_service, "admin_email", "") or os.getenv("WORKSPACE_ADMIN_EMAIL", "")
    print(
        f"INFO [devices.py]: Executing Cloud Identity lookup for user='{target_email}', "
        f"customer='{cid}', dwd_subject='{dwd_subject}', is_admin={is_admin}..."
    )

    total_devices_matched = 0
    crawl_error: Optional[str] = None

    # 1. Fast path: server-side filtered search
    try:
        fast_path_devices, fast_path_count = crawl_devices_for_user(
            customer_id=cid,
            target_email=target_email,
            query_filter=query_filter
        )
        total_devices_matched += fast_path_count
        my_devices.extend(fast_path_devices)
    except Exception as e:
        crawl_error = str(e)
        print(f"WARNING [devices.py]: Cloud Identity API filtered crawl encountered notice: {e}")

    # 2. Adaptive Fallback: If fast-path yields zero device bindings for user,
    # automatically crawl across tenant devices unfiltered to discover unindexed or secondary user bindings.
    if not my_devices:
        print(f"INFO [devices.py]: Fast-path filter yielded 0 device bindings for '{target_email}'. Initiating unfiltered fallback crawl across tenant devices...")
        try:
            fallback_devices, fallback_count = crawl_devices_for_user(
                customer_id=cid,
                target_email=target_email,
                query_filter=None
            )
            total_devices_matched += fallback_count
            my_devices.extend(fallback_devices)
            crawl_error = None
            if not my_devices:
                print(
                    f"WARNING [devices.py]: Unfiltered fallback scanned {fallback_count} total device(s) in customer '{cid}' "
                    f"(impersonating WORKSPACE_ADMIN_EMAIL='{dwd_subject}') and found 0 bindings for '{target_email}'."
                )
        except Exception as e:
            crawl_error = str(e)
            print(f"WARNING [devices.py]: Cloud Identity API unfiltered fallback crawl encountered notice: {e}")
            raise HTTPException(
                status_code=500,
                detail=(
                    f"Cloud Identity API device lookup failed ({crawl_error}). "
                    "Verify WORKSPACE_ADMIN_EMAIL and Domain-Wide Delegation scope "
                    "(https://www.googleapis.com/auth/cloud-identity.devices)."
                )
            )

    # Fetch enterprise-enrolled ChromeOS devices from Admin SDK Directory API
    directory_cbs = []
    try:
        directory_cbs = directory_service.get_user_chromeos_devices(
            user_email=target_email,
            customer_id=config.customer_id,
            is_admin=is_admin
        ) or []
        for cb in directory_cbs:
            raw_cb_serial = extract_field(cb, "serial_number", "deviceId", default="")
            cb_serial = raw_cb_serial if is_valid_serial(raw_cb_serial) else "N/A"
            cb_model = extract_field(cb, "model", default="Google Chromebook")
            cb_os = extract_field(cb, "os_version", default="ChromeOS")
            cb_sync = normalize_sync_time(cb.get("last_sync_time"))
            cb_du_name = str(cb.get("device_user_name") or f"directory/devices/{cb_serial}/deviceUsers/{target_email}").strip()
            cb_annotated_user = extract_field(cb, "annotated_user", default="").lower()

            # Check if this physical hardware serial is already in my_devices (case-insensitive)
            existing_match = None
            if is_valid_serial(cb_serial):
                existing_match = next((d for d in my_devices if is_valid_serial(d.serial_number) and d.serial_number.strip().upper() == cb_serial.upper()), None)

            if existing_match:
                existing_match.owner_type = "COMPANY"
                existing_match.approval_state = "APPROVED"
                if cb_annotated_user:
                    existing_match.annotated_user = cb_annotated_user
                cb_time_key = sync_time_sort_key(cb_sync)
                ex_time_key = sync_time_sort_key(existing_match.last_sync_time)
                if cb_time_key > 0 and (ex_time_key < 0 or cb_time_key > ex_time_key):
                    existing_match.last_sync_time = cb_sync
                    if cb_model and cb_model not in ("Google Chromebook", "Chromebook", "Unknown Model", ""):
                        existing_match.model = cb_model
                    if cb_os and cb_os not in ("ChromeOS", "Unknown OS", ""):
                        existing_match.os_version = cb_os
                else:
                    if existing_match.model in ("Unknown Model", "Google Chromebook", "Chromebook", "") and cb_model:
                        existing_match.model = cb_model
                    if existing_match.os_version in ("Unknown OS", "ChromeOS", "") and cb_os:
                        existing_match.os_version = cb_os
            else:
                my_devices.append(
                    DeviceUserItem(
                        device_user_name=cb_du_name,
                        device_type="CHROME_OS",
                        model=cb_model,
                        os_version=cb_os,
                        serial_number=cb_serial,
                        approval_state=extract_field(cb, "approval_state", default="APPROVED").upper(),
                        owner_type=extract_field(cb, "owner_type", default="COMPANY").upper(),
                        last_sync_time=cb_sync,
                        annotated_user=cb_annotated_user,
                    )
                )
    except Exception as e:
        print(f"WARNING [devices.py]: Failed to retrieve Directory ChromeOS devices for '{target_email}': {e}")

    # Deduplicate device entries by platform & prioritize physical hardware serial assets over virtual duplicates
    grouped: Dict[str, List[DeviceUserItem]] = {}
    for dev_item in my_devices:
        dev_type = str(dev_item.device_type or "UNKNOWN_TYPE").strip().upper()
        dev_item.device_type = dev_type
        if dev_type not in grouped:
            grouped[dev_type] = []
        grouped[dev_type].append(dev_item)

    deduped_devices: List[DeviceUserItem] = []
    for dev_type, items in grouped.items():
        serial_items = [i for i in items if is_valid_serial(i.serial_number)]
        virtual_items = [i for i in items if not is_valid_serial(i.serial_number)]
        for v in virtual_items:
            v.serial_number = "N/A"

        unique_serial_list: List[DeviceUserItem] = []
        if serial_items:
            # If physical hardware serial items exist for this platform, deduplicate by hardware serial
            unique_serials: Dict[str, DeviceUserItem] = {}
            for s_item in serial_items:
                serial_key = s_item.serial_number.strip().upper()
                if serial_key not in unique_serials:
                    unique_serials[serial_key] = s_item
                else:
                    existing = unique_serials[serial_key]
                    s_owner = str(s_item.owner_type or "").strip().upper()
                    e_owner = str(existing.owner_type or "").strip().upper()
                    s_state = str(s_item.approval_state or "").strip().upper()
                    e_state = str(existing.approval_state or "").strip().upper()

                    # If duplicate exists, prefer COMPANY owned and APPROVED state
                    if s_owner == "COMPANY" and e_owner != "COMPANY":
                        existing.owner_type = "COMPANY"
                        existing.approval_state = "APPROVED"
                        existing.device_user_name = s_item.device_user_name
                    elif s_state == "APPROVED" and e_state != "APPROVED":
                        existing.approval_state = "APPROVED"
                        if e_owner != "COMPANY" or s_owner == "COMPANY":
                            existing.device_user_name = s_item.device_user_name

                    if not existing.annotated_user and s_item.annotated_user:
                        existing.annotated_user = s_item.annotated_user

                    s_time_key = sync_time_sort_key(s_item.last_sync_time)
                    e_time_key = sync_time_sort_key(existing.last_sync_time)
                    if s_time_key > 0 and (e_time_key < 0 or s_time_key > e_time_key):
                        existing.last_sync_time = normalize_sync_time(s_item.last_sync_time)
                        if s_item.model and s_item.model not in ("Unknown Model", ""):
                            existing.model = s_item.model
                        if s_item.os_version and s_item.os_version not in ("Unknown OS", ""):
                            existing.os_version = s_item.os_version
                        if (e_owner == s_owner and e_state == s_state) or (s_owner == "COMPANY" and s_state == "APPROVED"):
                            existing.device_user_name = s_item.device_user_name
                    else:
                        existing.last_sync_time = normalize_sync_time(existing.last_sync_time)
                        if existing.model in ("Unknown Model", "") and s_item.model not in ("Unknown Model", ""):
                            existing.model = s_item.model
                        if existing.os_version in ("Unknown OS", "") and s_item.os_version not in ("Unknown OS", ""):
                            existing.os_version = s_item.os_version
            unique_serial_list = list(unique_serials.values())
            for u_item in unique_serial_list:
                if dev_type == "CHROME_OS" and u_item.model in ("Unknown Model", ""):
                    u_item.model = "Chromebook"
            deduped_devices.extend(unique_serial_list)

        if virtual_items:
            # Sort virtual (serial="N/A") items chronologically so the most recently synced asset is primary
            virtual_items.sort(key=lambda x: sync_time_sort_key(x.last_sync_time), reverse=True)
            primary = virtual_items[0]
            primary.last_sync_time = normalize_sync_time(primary.last_sync_time)
            for other in virtual_items[1:]:
                o_owner = str(other.owner_type or "").strip().upper()
                p_owner = str(primary.owner_type or "").strip().upper()
                o_state = str(other.approval_state or "").strip().upper()
                p_state = str(primary.approval_state or "").strip().upper()

                if o_owner == "COMPANY" and p_owner != "COMPANY":
                    primary.owner_type = "COMPANY"
                    primary.approval_state = "APPROVED"
                    primary.device_user_name = other.device_user_name
                elif o_state == "APPROVED" and p_state != "APPROVED":
                    primary.approval_state = "APPROVED"
                    if p_owner != "COMPANY" or o_owner == "COMPANY":
                        primary.device_user_name = other.device_user_name

                if primary.model in ("Unknown Model", "") and other.model not in ("Unknown Model", ""):
                    primary.model = other.model
                if primary.os_version in ("Unknown OS", "") and other.os_version not in ("Unknown OS", ""):
                    primary.os_version = other.os_version

            if dev_type == "CHROME_OS" and primary.model in ("Unknown Model", ""):
                primary.model = "Chromebook"

            if not unique_serial_list:
                deduped_devices.append(primary)
            elif primary.approval_state == "PENDING_APPROVAL" or (
                dev_type == "CHROME_OS"
                and str(primary.owner_type or "BYOD").strip().upper() == "BYOD"
                and not any(
                    str(s.owner_type or "").strip().upper() == "BYOD"
                    and sync_time_sort_key(s.last_sync_time) >= sync_time_sort_key(primary.last_sync_time)
                    for s in unique_serial_list
                )
            ):
                deduped_devices.append(primary)

    # Sort so PENDING_APPROVAL devices appear first, followed by most recently synced devices at the top
    deduped_devices.sort(
        key=lambda d: (
            1 if d.approval_state == "PENDING_APPROVAL" else 0,
            sync_time_sort_key(d.last_sync_time),
        ),
        reverse=True,
    )

    # Warm SessionGuard approved serial cache and register any PENDING_APPROVAL BYOD devices
    # Note: Onboarding grace leases are NEVER auto-granted here; the user must explicitly click
    # "+ Add Personal Device (15m Grace Pass)" or generate a Trust Chaining code.
    warm_records: List[DeviceRecord] = []
    session_guard.clear_unapproved_devices_for_user(target_email)
    for d in deduped_devices:
        if d.owner_type == "COMPANY" or d.approval_state == "APPROVED":
            effective_serial = (
                d.serial_number.strip().upper()
                if is_valid_serial(d.serial_number)
                else d.device_user_name.strip().upper()
            )
            if effective_serial:
                warm_records.append(
                    DeviceRecord(
                        device_id=d.device_user_name,
                        serial_number=effective_serial,
                        device_type="CHROMEOS"
                        if (d.owner_type == "COMPANY" or "CHROME" in (d.device_type or "").upper())
                        else "CLOUD_IDENTITY_APPROVED",
                        status="APPROVED",
                        assigned_user=target_email,
                    )
                )
        elif d.owner_type != "COMPANY" and d.approval_state == "PENDING_APPROVAL":
            session_guard.record_unapproved_device(
                user_email=target_email,
                device_user_name=d.device_user_name,
                model=d.model,
                device_type=d.device_type,
                serial_number=d.serial_number,
                approval_state=d.approval_state,
            )

    if warm_records:
        session_guard.load_device_inventory(warm_records)

    print(f"INFO [devices.py]: Matched {total_devices_matched} Cloud Identity assets and {len(directory_cbs)} Directory Chromebooks. Deduplicated {len(my_devices)} down to {len(deduped_devices)} primary device bindings.")
    return deduped_devices

@router.post("/approve")
def approve_device(
    request: DeviceActionRequest,
    http_request: Request = None,
    user_email: str = Depends(get_current_user_email)
):
    if not cloud_identity_service.service:
        err_detail = getattr(cloud_identity_service, "init_error", None) or "Missing or invalid Domain-Wide Delegation credentials."
        raise HTTPException(status_code=500, detail=f"Cloud Identity API service is not initialized ({err_detail}).")

    config = config_service.get_tenant_config()
    cid = normalize_customer_id(config.customer_id)
    is_admin = directory_service.verify_user_is_admin(user_email, portal_admins=config.portal_admins)
    verify_device_user_ownership(request.device_user_name, user_email, cid, is_admin)
    try:
        operation = cloud_identity_service.approve_device_user(
            device_user_name=request.device_user_name,
            customer_id=cid
        )
        # Immediately promote device in SessionGuard so active sessions are not terminated by login sweep
        serial_num = ""
        target_owner_email = user_email
        try:
            parent_dev = request.device_user_name.split("/deviceUsers/")[0]
            if not parent_dev.startswith("directory/"):
                with cloud_identity_service._lock:
                    dev_resp = cloud_identity_service.service.devices().get(name=parent_dev, customer=cid).execute() or {}
                serial_num = extract_field(dev_resp, "serialNumber", "deviceSerialNumber", default="")
        except Exception:
            pass
        client_ip = None
        if http_request is not None:
            forwarded = http_request.headers.get("x-forwarded-for", "")
            client_ip = forwarded.split(",")[0].strip() if forwarded else (http_request.client.host if http_request.client else None)
        session_guard.promote_approved_device(
            user_email=target_owner_email,
            device_id=request.device_user_name,
            serial_number=serial_num,
            ip_address=client_ip,
        )
        return {"status": "SUCCESS", "operation": operation}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/revoke")
def revoke_device(request: DeviceActionRequest, user_email: str = Depends(get_current_user_email)):
    if not cloud_identity_service.service:
        err_detail = getattr(cloud_identity_service, "init_error", None) or "Missing or invalid Domain-Wide Delegation credentials."
        raise HTTPException(status_code=500, detail=f"Cloud Identity API service is not initialized ({err_detail}).")

    config = config_service.get_tenant_config()
    cid = normalize_customer_id(config.customer_id)
    is_admin = directory_service.verify_user_is_admin(user_email, portal_admins=config.portal_admins)
    verify_device_user_ownership(request.device_user_name, user_email, cid, is_admin)
    try:
        parent_device = request.device_user_name.split("/deviceUsers/")[0]
        if parent_device.startswith("directory/"):
            raise HTTPException(status_code=403, detail="Access Denied: Company-owned trust anchors cannot be revoked.")
        with cloud_identity_service._lock:
            dev_req = cloud_identity_service.service.devices().get(name=parent_device, customer=cid)
            dev_resp = dev_req.execute()
        if dev_resp.get("ownerType") == "COMPANY":
            raise HTTPException(status_code=403, detail="Access Denied: Company-owned trust anchors cannot be revoked.")

        cloud_identity_service.revoke_device_user(
            device_user_name=request.device_user_name,
            customer_id=cid,
            action=config.revocation_action
        )
        return {"status": "SUCCESS", "message": f"Device revoked successfully via {config.revocation_action}."}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/revoke-bulk")
def revoke_device_bulk(request: BulkRevokeRequest, user_email: str = Depends(get_current_user_email)):
    """Executes bulk unapproval via BatchHttpRequest across multiple device user bindings simultaneously."""
    if not cloud_identity_service.service:
        err_detail = getattr(cloud_identity_service, "init_error", None) or "Missing or invalid Domain-Wide Delegation credentials."
        raise HTTPException(status_code=500, detail=f"Cloud Identity API service is not initialized ({err_detail}).")

    config = config_service.get_tenant_config()
    cid = normalize_customer_id(config.customer_id)
    is_admin = directory_service.verify_user_is_admin(user_email, portal_admins=config.portal_admins)
    for du_name in request.device_user_names:
        verify_device_user_ownership(du_name, user_email, cid, is_admin)
    try:
        # Filter out company anchors before batch execution
        bulk_targets = []
        for du_name in request.device_user_names:
            parent_dev = du_name.split("/deviceUsers/")[0]
            if parent_dev.startswith("directory/"):
                continue
            with cloud_identity_service._lock:
                dev_req = cloud_identity_service.service.devices().get(name=parent_dev, customer=cid)
                dev_resp = dev_req.execute()
            if dev_resp.get("ownerType") != "COMPANY":
                bulk_targets.append(du_name)

        if not bulk_targets:
            return {"status": "SUCCESS", "revoked_count": 0, "message": "No eligible BYOD devices to revoke."}

        res = cloud_identity_service.revoke_device_users_bulk(
            device_user_names=bulk_targets,
            customer_id=cid,
            action=config.revocation_action
        )
        return res
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
