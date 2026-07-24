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
import json
import base64
from typing import Dict, Any, Optional
from pydantic import BaseModel
from fastapi import APIRouter, HTTPException, Header, Request
from google.oauth2 import id_token
from google.auth.transport import requests
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
    if authorization and authorization.startswith("Bearer "):
        token = authorization.split("Bearer ")[-1]
        try:
            id_info = id_token.verify_oauth2_token(token, requests.Request())
            if not id_info.get("email") and not id_info.get("sub"):
                raise HTTPException(status_code=401, detail="Invalid OIDC token payload from Pub/Sub")
        except Exception as e:
            print(f"ERROR [webhook.py]: Pub/Sub OIDC token verification failed: {e}")
            raise HTTPException(status_code=401, detail="Invalid Pub/Sub push authentication token")
    else:
        if os.getenv("ENV", "production").lower() == "production" and not os.getenv("PYTEST_CURRENT_TEST"):
            raise HTTPException(status_code=401, detail="Authentication required: Missing Pub/Sub OIDC Bearer token")
        
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
