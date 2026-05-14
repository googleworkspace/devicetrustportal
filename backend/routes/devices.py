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
    """Fetches the authentic list of approved devices assigned to the requesting user."""
    if not cloud_identity_service.service:
        # If running locally without credentials or in mock mode, return mock device list
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

    try:
        # List all devices in the tenant (or search by user if supported)
        request = cloud_identity_service.service.devices().list(customer=config.customer_id)
        response = request.execute()
        devices = response.get("devices", [])

        for d in devices:
            device_name = d["name"]
            device_type = d.get("deviceType", "UNKNOWN_TYPE")
            
            # List device users for this device
            du_req = cloud_identity_service.service.devices().deviceUsers().list(parent=device_name, customer=config.customer_id)
            du_resp = du_req.execute()
            
            for du in du_resp.get("deviceUsers", []):
                if du.get("userEmail") == user_email and du.get("approvalState") == "APPROVED":
                    my_devices.append(
                        DeviceUserItem(
                            device_user_name=du["name"],
                            device_type=device_type,
                            approval_state=du.get("approvalState", "APPROVED"),
                            last_sync_time=d.get("lastSyncTime", "N/A")
                        )
                    )
                    
        return my_devices
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch user devices from Cloud Identity: {e}")
