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

from typing import List, Dict, Any, Optional
from pydantic import BaseModel
from fastapi import APIRouter, HTTPException, Depends
from backend.services.config_service import config_service
from backend.services.cloud_identity import cloud_identity_service
from backend.routes.admin import get_current_user_email

router = APIRouter(prefix="/api/devices", tags=["Devices"])

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

@router.get("/my-devices", response_model=List[DeviceUserItem])
def get_my_approved_devices(user_email: str = Depends(get_current_user_email)):
    """Fetches the authentic list of devices assigned to the requesting user using server-side email filtering."""
    if not cloud_identity_service.service:
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
    my_devices = []
    target_email = user_email.lower().strip()

    query_filter = f"email:{target_email}"
    print(f"INFO [devices.py]: Executing Cloud Identity devices.list(filter='{query_filter}') for customer '{config.customer_id}'...")

    try:
        next_page_token = None
        page_count = 0
        total_devices_matched = 0
        
        while True:
            page_count += 1
            request = cloud_identity_service.service.devices().list(
                customer=config.customer_id,
                filter=query_filter,
                pageToken=next_page_token
            )
            response = request.execute()
            devices = response.get("devices", [])
            total_devices_matched += len(devices)

            for d in devices:
                device_name = d["name"]
                device_type = d.get("deviceType", "UNKNOWN_TYPE")
                model = d.get("model", "Unknown Model")
                os_version = d.get("osVersion", d.get("os", "Unknown OS"))
                owner_type = d.get("ownerType", "BYOD")
                serial_number = d.get("serialNumber") or d.get("deviceSerialNumber") or d.get("imei") or d.get("meid") or "N/A"
                
                du_page_token = None
                while True:
                    du_req = cloud_identity_service.service.devices().deviceUsers().list(
                        parent=device_name,
                        customer=config.customer_id,
                        pageToken=du_page_token
                    )
                    du_resp = du_req.execute()
                    
                    for du in du_resp.get("deviceUsers", []):
                        du_email = du.get("userEmail", "").lower().strip()
                        if du_email == target_email:
                            state = du.get("managementState") or du.get("approvalState", "UNKNOWN_STATE")
                            my_devices.append(
                                DeviceUserItem(
                                    device_user_name=du["name"],
                                    device_type=device_type,
                                    model=model,
                                    os_version=os_version,
                                    serial_number=serial_number,
                                    approval_state=state,
                                    owner_type=owner_type,
                                    last_sync_time=d.get("lastSyncTime", "N/A")
                                )
                            )
                            
                    du_page_token = du_resp.get("nextPageToken")
                    if not du_page_token:
                        break
                        
            next_page_token = response.get("nextPageToken")
            if not next_page_token:
                break
                
        # Deduplicate device entries by platform & prioritize physical hardware serial assets over virtual duplicates
        grouped: Dict[str, List[DeviceUserItem]] = {}
        for dev_item in my_devices:
            dev_type = dev_item.device_type
            if dev_type not in grouped:
                grouped[dev_type] = []
            grouped[dev_type].append(dev_item)

        deduped_devices: List[DeviceUserItem] = []
        for dev_type, items in grouped.items():
            serial_items = [i for i in items if i.serial_number != "N/A"]
            virtual_items = [i for i in items if i.serial_number == "N/A"]

            if serial_items:
                # If physical hardware serial items exist for this platform, return unique hardware serial assets
                unique_serials: Dict[str, DeviceUserItem] = {}
                for s_item in serial_items:
                    if s_item.serial_number not in unique_serials:
                        unique_serials[s_item.serial_number] = s_item
                deduped_devices.extend(list(unique_serials.values()))
            else:
                # If only virtual extension assets exist, keep the single most recently synced asset for that platform
                virtual_items.sort(key=lambda x: x.last_sync_time, reverse=True)
                if virtual_items:
                    deduped_devices.extend(virtual_items[:1])

        print(f"INFO [devices.py]: Matched {total_devices_matched} total hardware assets across {page_count} pages. Deduplicated {len(my_devices)} down to {len(deduped_devices)} primary device bindings.")
        return deduped_devices
    except Exception as e:
        print(f"ERROR [devices.py]: Cloud Identity API filtered crawl failed: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch user devices from Cloud Identity: {e}")

@router.post("/approve")
def approve_device(request: DeviceActionRequest, user_email: str = Depends(get_current_user_email)):
    if not cloud_identity_service.service:
        return {"status": "SUCCESS", "message": "Simulated device approval complete."}

    config = config_service.get_tenant_config()
    try:
        operation = cloud_identity_service.approve_device_user(
            device_user_name=request.device_user_name,
            customer_id=config.customer_id
        )
        return {"status": "SUCCESS", "operation": operation}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/revoke")
def revoke_device(request: DeviceActionRequest, user_email: str = Depends(get_current_user_email)):
    if not cloud_identity_service.service:
        return {"status": "SUCCESS", "message": "Simulated device revocation complete."}

    config = config_service.get_tenant_config()
    try:
        parent_device = request.device_user_name.split("/deviceUsers/")[0]
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
    try:
        # Filter out company anchors before batch execution
        bulk_targets = []
        for du_name in request.device_user_names:
            parent_dev = du_name.split("/deviceUsers/")[0]
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
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
