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
from typing import Optional
from pydantic import BaseModel
from fastapi import APIRouter, HTTPException, Header, Request
from google.oauth2 import id_token
from google.auth.transport import requests
from backend.services.config_service import config_service
from backend.services.cloud_identity import cloud_identity_service, normalize_customer_id
from backend.services.directory_service import directory_service
from backend.routes.session_watch import session_guard, _is_mobile_byod_device
from backend.routes.devices import crawl_devices_for_user, is_newly_enrolled_basic_mobile_device

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
    cid = normalize_customer_id(config.customer_id)

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
                            "assetTag": serial_num,
                            "ownerType": "COMPANY"
                        }
                        cloud_identity_service.service.devices().create(
                            customer=cid,
                            body=ci_body
                        ).execute()
                    except Exception as e:
                        print(f"Error: Cloud Identity anchoring failed for {serial_num}: {e}")

    return {
        "status": "SUCCESS",
        "processed_count": len(enrolled_serials),
        "anchored_serials": enrolled_serials
    }


@router.post("/mobile-audit")
async def mobile_audit_webhook(
    body: PubSubPushRequest,
    request: Request,
    authorization: Optional[str] = Header(None),
):
    """Event-driven ($0.00/mo) webhook listening for Google Workspace Admin Reports `mobile` / `login`
    activity (`activities.watch`).

    - When `basic_mobile_auto_quarantine_enabled` is False (Advanced Mobile Management mode), returns
      `SKIPPED_DISABLED` immediately with 0 API calls.
    - When `basic_mobile_auto_quarantine_enabled` is True, checks if the user is in the configured
      Ordered Google Group Hierarchy (`basic_mobile_target_groups`) or OU Tree (`basic_mobile_target_ous`),
      and immediately flips any unverified Basic Android/iOS BYOD device from `APPROVED` -> `BLOCKED`
      in Cloud Identity.
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

    config = config_service.get_tenant_config()
    if not getattr(config, "basic_mobile_auto_quarantine_enabled", False):
        return {
            "status": "SKIPPED_DISABLED",
            "basic_mobile_auto_quarantine_enabled": False,
            "quarantined_devices": 0,
            "message": "Basic Mobile Auto-Quarantine is OFF (Advanced Mobile Management mode active); skipping.",
        }

    try:
        decoded_data = base64.b64decode(body.message.data).decode("utf-8")
        audit_payload = json.loads(decoded_data)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid Pub/Sub message payload: {e}")

    cid = normalize_customer_id(config.customer_id or "customers/my_customer")
    is_dry_run = getattr(config, "session_watch_dry_run", False)

    actor_email = (
        (audit_payload.get("actor") or {}).get("email")
        or audit_payload.get("user_email")
        or ""
    ).strip().lower()

    candidate_emails = set()
    if actor_email:
        candidate_emails.add(actor_email)

    for event in audit_payload.get("events", []) or []:
        for param in event.get("parameters", []) or []:
            if param.get("name") in ("USER_EMAIL", "user_email", "ACCOUNT_NAME"):
                val = (param.get("value") or "").strip().lower()
                if val and "@" in val:
                    candidate_emails.add(val)

    quarantined = []
    for email in sorted(candidate_emails):
        in_scope, scope_reason = directory_service.is_user_in_session_watch_scope(
            user_email=email,
            target_ous=getattr(config, "basic_mobile_target_ous", []),
            target_groups=getattr(config, "basic_mobile_target_groups", []),
            exempt_admins=getattr(config, "session_watch_exempt_admins", False),
            portal_admins=getattr(config, "portal_admins", []),
            exempt_ous=getattr(config, "session_guard_exempt_ous", []),
            exempt_groups=getattr(config, "session_guard_exempt_groups", []),
            require_explicit_target_scope=True,
        )
        if not in_scope:
            continue

        has_grace, _ = session_guard.has_active_onboarding_lease(email)
        if has_grace:
            continue

        user_items, _ = crawl_devices_for_user(
            customer_id=cid,
            target_email=email,
            query_filter=f"email:{email}",
        )
        for item in user_items:
            if (
                (item.owner_type or "").upper() not in ("COMPANY", "CUSTOMER")
                and (item.approval_state or "").upper() == "APPROVED"
                and _is_mobile_byod_device(
                    item.device_type,
                    item.os_version,
                    item.model,
                    getattr(item, "ownership_privilege", "") or "",
                )
                and not session_guard.is_portal_approved_device(item.device_user_name, item.serial_number)
            ):
                if not is_newly_enrolled_basic_mobile_device(
                    getattr(item, "create_time", ""), item.last_sync_time
                ):
                    session_guard.record_portal_approved_device(
                        device_user_name=item.device_user_name,
                        user_email=email,
                        serial_number=item.serial_number,
                    )
                    continue
                if not is_dry_run:
                    cloud_identity_service.revoke_device_user(
                        device_user_name=item.device_user_name,
                        customer_id=cid,
                        action="BLOCK",
                    )
                    session_guard.metrics["basic_mobile_auto_quarantined"] = (
                        session_guard.metrics.get("basic_mobile_auto_quarantined", 0) + 1
                    )
                quarantined.append(
                    {
                        "user_email": email,
                        "device_user_name": item.device_user_name,
                        "model": item.model,
                        "serial_number": item.serial_number,
                        "scope_reason": scope_reason,
                    }
                )

    return {
        "status": "SUCCESS",
        "basic_mobile_auto_quarantine_enabled": True,
        "quarantined_devices": len(quarantined),
        "devices": quarantined,
    }
