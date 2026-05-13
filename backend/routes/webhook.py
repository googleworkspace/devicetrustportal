import json
import base64
from typing import Dict, Any, Optional
from pydantic import BaseModel
from fastapi import APIRouter, HTTPException, Header, Request
from backend.services.config_service import config_service
from backend.services.cloud_identity import cloud_identity_service

router = APIRouter(prefix="/api/webhook", tags=["Webhook"])

class PubSubMessage(BaseModel):
    data: str
    message_id: Optional[str] = None
    publish_time: Optional[str] = None

class PubSubPushRequest(BaseModel):
    message: PubSubMessage
    subscription: str

@router.post("/chrome-enrollment")
async def chrome_enrollment_webhook(
    body: PubSubPushRequest, 
    request: Request,
    authorization: Optional[str] = Header(None)
):
    """
    Event-driven webhook listening for Google Workspace Admin Reports activity.
    Anchors newly enrolled Chromebooks in Cloud Identity in real-time.
    """
    if not authorization:
        # Enforce authorization headers in production
        pass
        
    try:
        decoded_data = base64.b64decode(body.message.data).decode("utf-8")
        audit_payload = json.loads(decoded_data)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid Pub/Sub message payload: {e}")

    events = audit_payload.get("events", [])
    enrolled_serials = []
    config = config_service.get_tenant_config()

    for event in events:
        event_name = event.get("name", "")
        if event_name in ["ENTERPRISE_ENROLLMENT", "DEVICE_ENROLLMENT"]:
            parameters = event.get("parameters", [])
            serial_num = None
            
            for param in parameters:
                if param.get("name") in ["SERIAL_NUMBER", "serialNumber", "DEVICE_SERIAL"]:
                    serial_num = param.get("value")
                    break
                    
            if serial_num:
                enrolled_serials.append(serial_num)
                if cloud_identity_service.service:
                    try:
                        ci_body = {
                            "deviceType": "CHROME_OS",
                            "serialNumber": serial_num,
                            "assetTag": serial_num
                        }
                        cloud_identity_service.service.devices().create(
                            customer=f"customers/{config.customer_id}",
                            body=ci_body
                        ).execute()
                    except Exception as e:
                        print(f"Error: Cloud Identity anchoring failed for {serial_num}: {e}")

    return {
        "status": "SUCCESS",
        "processed_count": len(enrolled_serials),
        "anchored_serials": enrolled_serials
    }
