from typing import List, Dict, Any
from pydantic import BaseModel
from fastapi import APIRouter, HTTPException, Depends
from backend.services.config_service import config_service
from backend.services.cloud_identity import cloud_identity_service
from backend.routes.admin import get_current_user_email

router = APIRouter(prefix="/api/devices", tags=["Devices"])

class DeviceUserItem(BaseModel):
    device_user_name: str
    device_type: str
    approval_state: str
    last_sync_time: str

@router.get("/my-devices", response_model=List[DeviceUserItem])
def get_my_approved_devices(user_email: str = Depends(get_current_user_email)):
    """Fetches the authentic list of devices assigned to the requesting user across all Cloud Identity pages, logging execution."""
    if not cloud_identity_service.service:
        print(f"INFO [devices.py]: Running without Cloud Identity service credentials. Returning mock assets for '{user_email}'.")
        return [
            DeviceUserItem(
                device_user_name="devices/mock-cb123/deviceUsers/du-1",
                device_type="CHROME_OS (Trust Anchor)",
                approval_state="APPROVED",
                last_sync_time="2026-05-14T10:00:00Z"
            ),
            DeviceUserItem(
                device_user_name="devices/mock-pixel99/deviceUsers/du-2",
                device_type="ANDROID Smartphone",
                approval_state="APPROVED",
                last_sync_time="2026-05-14T10:05:00Z"
            )
        ]

    config = config_service.get_tenant_config()
    my_devices = []
    target_email = user_email.lower().strip()

    print(f"INFO [devices.py]: Initiating Cloud Identity devices.list crawl for customer '{config.customer_id}' targeting user '{target_email}'...")

    try:
        # 1. Paginate through all devices in the tenant
        next_page_token = None
        page_count = 0
        total_devices_crawled = 0
        
        while True:
            page_count += 1
            print(f"INFO [devices.py]: Executing service.devices().list(pageToken={next_page_token}) [Page {page_count}]...")
            request = cloud_identity_service.service.devices().list(
                customer=config.customer_id,
                pageToken=next_page_token
            )
            response = request.execute()
            devices = response.get("devices", [])
            total_devices_crawled += len(devices)

            print(f"INFO [devices.py]: Discovered {len(devices)} hardware assets on Page {page_count}. Inspecting deviceUsers bindings...")

            for d in devices:
                device_name = d["name"]
                device_type = d.get("deviceType", "UNKNOWN_TYPE")
                
                # 2. Paginate through all device users for this hardware
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
                            state = du.get("approvalState", "UNKNOWN_STATE")
                            print(f"SUCCESS [devices.py]: Found matching binding '{du['name']}' for '{target_email}' (Type: {device_type}, State: {state})")
                            my_devices.append(
                                DeviceUserItem(
                                    device_user_name=du["name"],
                                    device_type=device_type,
                                    approval_state=state,
                                    last_sync_time=d.get("lastSyncTime", "N/A")
                                )
                            )
                            
                    du_page_token = du_resp.get("nextPageToken")
                    if not du_page_token:
                        break
                        
            next_page_token = response.get("nextPageToken")
            if not next_page_token:
                break
                
        print(f"INFO [devices.py]: Crawl complete. Crawled {total_devices_crawled} total hardware assets across {page_count} pages. Returning {len(my_devices)} matching devices.")
        return my_devices
    except Exception as e:
        print(f"ERROR [devices.py]: Cloud Identity API crawl failed: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch user devices from Cloud Identity: {e}")
