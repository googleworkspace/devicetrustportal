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
from fastapi import APIRouter, HTTPException, Depends
from backend.services.config_service import config_service
from backend.services.cloud_identity import cloud_identity_service
from backend.services.directory_service import directory_service
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

    cid = (customer_id or "my_customer").strip() or "my_customer"

    matched_items: List[DeviceUserItem] = []
    total_devices_scanned = 0
    seen_dus = set()
    next_page_token = None
    seen_page_tokens = set()

    while True:
        list_kwargs: Dict[str, Any] = {
            "customer": cid,
        }
        if next_page_token:
            list_kwargs["pageToken"] = next_page_token
        if query_filter:
            list_kwargs["filter"] = query_filter

        try:
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

            device_type = extract_field(d, "deviceType", default="UNKNOWN_TYPE").upper()
            model = extract_field(d, "model", default="Unknown Model")
            os_version = extract_field(d, "osVersion", "os", default="Unknown OS")
            owner_type = extract_field(d, "ownerType", default="BYOD").upper()
            raw_serial = extract_field(d, "serialNumber", "deviceSerialNumber", "imei", "meid", default="")
            serial_number = raw_serial if is_valid_serial(raw_serial) else "N/A"
            dev_last_sync = normalize_sync_time(d.get("lastSyncTime"))

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
                                m_state = str(du.get("managementState") or "").strip().upper()
                                a_state = str(du.get("approvalState") or "").strip().upper()
                                if m_state in ("MANAGEMENT_STATE_UNSPECIFIED", "UNSPECIFIED"):
                                    m_state = ""
                                if a_state in ("APPROVAL_STATE_UNSPECIFIED", "UNSPECIFIED"):
                                    a_state = ""

                                if m_state == "BLOCKED" or a_state == "BLOCKED":
                                    state = "BLOCKED"
                                elif m_state == "APPROVED" or a_state == "APPROVED":
                                    state = "APPROVED"
                                elif m_state == "PENDING_APPROVAL" or a_state == "PENDING_APPROVAL":
                                    state = "PENDING_APPROVAL"
                                elif m_state in ("WIPED", "WIPING") or a_state in ("WIPED", "WIPING"):
                                    state = "WIPED"
                                else:
                                    state = m_state or a_state or "UNKNOWN_STATE"

                                du_sync = normalize_sync_time(du.get("lastSyncTime"))
                                effective_sync = du_sync if du_sync != "N/A" else dev_last_sync

                                matched_items.append(
                                    DeviceUserItem(
                                        device_user_name=du_name,
                                        device_type=device_type,
                                        model=model,
                                        os_version=os_version,
                                        serial_number=serial_number,
                                        approval_state=state,
                                        owner_type=owner_type,
                                        last_sync_time=effective_sync
                                    )
                                )

                    raw_du_next = str(du_resp.get("nextPageToken") or "").strip()
                    du_page_token = raw_du_next if raw_du_next else None
                    if not du_page_token or du_page_token in seen_du_tokens:
                        break
                    seen_du_tokens.add(du_page_token)
            except Exception as du_err:
                print(f"WARNING [devices.py]: Failed to list device users for '{device_name}': {du_err}")

        raw_next = str(response.get("nextPageToken") or "").strip()
        next_page_token = raw_next if raw_next else None
        if not next_page_token or next_page_token in seen_page_tokens:
            break
        seen_page_tokens.add(next_page_token)

    return matched_items, total_devices_scanned

@router.get("/my-devices", response_model=List[DeviceUserItem])
def get_my_approved_devices(user_email: str = Depends(get_current_user_email)):
    """Fetches the authentic list of devices assigned to the requesting user using server-side email filtering with adaptive fallback."""
    target_email = (user_email or "").lower().strip()
    if not target_email:
        return []

    is_production = os.getenv("USE_SECRET_MANAGER", "false").lower() == "true"

    if not cloud_identity_service.service:
        if is_production:
            err_detail = getattr(cloud_identity_service, "init_error", None) or "Missing or invalid Domain-Wide Delegation credentials."
            raise HTTPException(
                status_code=500,
                detail=(
                    f"Cloud Identity API service is not initialized ({err_detail}). "
                    "Verify that /secrets/dwd_key.json is mounted, WORKSPACE_ADMIN_EMAIL is set to an active "
                    "Google Workspace Super Admin, and Domain-Wide Delegation scopes are authorized."
                )
            )
        print(f"INFO [devices.py]: Running without Cloud Identity service credentials. Returning mock assets for '{user_email}'.")
        return [
            DeviceUserItem(
                device_user_name="devices/mock-cb123/deviceUsers/du-1",
                device_type="CHROME_OS",
                model="Enterprise Chromebook Pixel",
                os_version="ChromeOS 120.0",
                serial_number="PF2ABC99",
                approval_state="APPROVED",
                owner_type="COMPANY",
                last_sync_time="2026-05-14T10:00:00Z"
            ),
            DeviceUserItem(
                device_user_name="devices/mock-pixel99/deviceUsers/du-2",
                device_type="ANDROID",
                model="Google Pixel 7 Pro",
                os_version="Android 14.0",
                serial_number="35991234567890",
                approval_state="PENDING_APPROVAL",
                owner_type="BYOD",
                last_sync_time="2026-05-14T10:05:00Z"
            )
        ]

    config = config_service.get_tenant_config()
    my_devices: List[DeviceUserItem] = []
    is_admin = directory_service.verify_user_is_admin(target_email, portal_admins=config.portal_admins)

    query_filter = f"email:{target_email}"
    print(f"INFO [devices.py]: Executing Cloud Identity devices.list(filter='{query_filter}') for customer '{config.customer_id}' (is_admin={is_admin})...")

    total_devices_matched = 0
    crawl_error: Optional[str] = None

    # 1. Fast path: server-side filtered search
    try:
        fast_path_devices, fast_path_count = crawl_devices_for_user(
            customer_id=config.customer_id,
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
                customer_id=config.customer_id,
                target_email=target_email,
                query_filter=None
            )
            total_devices_matched += fallback_count
            my_devices.extend(fallback_devices)
            crawl_error = None
        except Exception as e:
            crawl_error = str(e)
            print(f"WARNING [devices.py]: Cloud Identity API unfiltered fallback crawl encountered notice: {e}")
            if is_production:
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

            # Check if this physical hardware serial is already in my_devices (case-insensitive)
            existing_match = None
            if is_valid_serial(cb_serial):
                existing_match = next((d for d in my_devices if is_valid_serial(d.serial_number) and d.serial_number.strip().upper() == cb_serial.upper()), None)

            if existing_match:
                existing_match.owner_type = "COMPANY"
                existing_match.approval_state = "APPROVED"
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
                        last_sync_time=cb_sync
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

        if serial_items:
            # If physical hardware serial items exist for this platform, return unique hardware serial assets
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
            deduped_devices.extend(list(unique_serials.values()))
        else:
            # If only virtual extension assets exist, keep the single most recently synced asset for that platform
            # Note: filter out "N/A" so it sorts chronologically and doesn't precede real ISO timestamps
            virtual_items.sort(key=lambda x: sync_time_sort_key(x.last_sync_time), reverse=True)
            if virtual_items:
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
                deduped_devices.append(primary)

    print(f"INFO [devices.py]: Matched {total_devices_matched} Cloud Identity assets and {len(directory_cbs)} Directory Chromebooks. Deduplicated {len(my_devices)} down to {len(deduped_devices)} primary device bindings.")
    return deduped_devices

@router.post("/approve")
def approve_device(request: DeviceActionRequest, user_email: str = Depends(get_current_user_email)):
    if not cloud_identity_service.service:
        return {"status": "SUCCESS", "message": "Simulated device approval complete."}

    config = config_service.get_tenant_config()
    is_admin = directory_service.verify_user_is_admin(user_email, portal_admins=config.portal_admins)
    verify_device_user_ownership(request.device_user_name, user_email, config.customer_id, is_admin)
    try:
        operation = cloud_identity_service.approve_device_user(
            device_user_name=request.device_user_name,
            customer_id=config.customer_id
        )
        return {"status": "SUCCESS", "operation": operation}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/revoke")
def revoke_device(request: DeviceActionRequest, user_email: str = Depends(get_current_user_email)):
    if not cloud_identity_service.service:
        return {"status": "SUCCESS", "message": "Simulated device revocation complete."}

    config = config_service.get_tenant_config()
    is_admin = directory_service.verify_user_is_admin(user_email, portal_admins=config.portal_admins)
    verify_device_user_ownership(request.device_user_name, user_email, config.customer_id, is_admin)
    try:
        parent_device = request.device_user_name.split("/deviceUsers/")[0]
        if parent_device.startswith("directory/"):
            raise HTTPException(status_code=403, detail="Access Denied: Company-owned trust anchors cannot be revoked.")
        dev_req = cloud_identity_service.service.devices().get(name=parent_device, customer=config.customer_id)
        dev_resp = dev_req.execute()
        if dev_resp.get("ownerType") == "COMPANY":
            raise HTTPException(status_code=403, detail="Access Denied: Company-owned trust anchors cannot be revoked.")

        cloud_identity_service.revoke_device_user(
            device_user_name=request.device_user_name,
            customer_id=config.customer_id,
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
        return {"status": "SUCCESS", "revoked_count": len(request.device_user_names)}

    config = config_service.get_tenant_config()
    is_admin = directory_service.verify_user_is_admin(user_email, portal_admins=config.portal_admins)
    for du_name in request.device_user_names:
        verify_device_user_ownership(du_name, user_email, config.customer_id, is_admin)
    try:
        # Filter out company anchors before batch execution
        bulk_targets = []
        for du_name in request.device_user_names:
            parent_dev = du_name.split("/deviceUsers/")[0]
            if parent_dev.startswith("directory/"):
                continue
            dev_req = cloud_identity_service.service.devices().get(name=parent_dev, customer=config.customer_id)
            dev_resp = dev_req.execute()
            if dev_resp.get("ownerType") != "COMPANY":
                bulk_targets.append(du_name)

        if not bulk_targets:
            return {"status": "SUCCESS", "revoked_count": 0, "message": "No eligible BYOD devices to revoke."}

        res = cloud_identity_service.revoke_device_users_bulk(
            device_user_names=bulk_targets,
            customer_id=config.customer_id,
            action=config.revocation_action
        )
        return res
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
