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

"""FastAPI routes for CAA-Free Session Watch on Education Fundamentals."""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, Field

from backend.services.cloud_identity import cloud_identity_service, normalize_customer_id
from backend.services.config_service import config_service
from backend.services.directory_service import directory_service
from backend.services.session_guard import (
    DeviceRecord,
    LoginAuditEvent,
    SessionGuardService,
)

router = APIRouter(prefix="/api/session-watch", tags=["Session Watch (CAA-Free)"])


def _live_signout_callback(user_email: str) -> bool:
    """Executes real Admin SDK Directory users.signOut circuit breaker."""
    return directory_service.sign_out_user(user_email)


# Singleton guard service for runtime enforcement
session_guard = SessionGuardService(signout_callback=_live_signout_callback)


class ExtensionAttestRequest(BaseModel):
    user_email: str = Field(..., description="Signed-in Google Workspace user email")
    serial_number: str = Field(
        ...,
        description="Hardware serial from chrome.enterprise.deviceAttributes or signed BYOD token",
    )
    session_id: Optional[str] = Field(default="", description="Browser session nonce")


class LoginEventPayload(BaseModel):
    event_id: str
    user_email: str
    ip_address: str
    timestamp_epoch: Optional[float] = None
    login_type: str = "exchange"
    is_suspicious: bool = False


class SweepRequest(BaseModel):
    events: List[LoginEventPayload] = Field(
        default_factory=list,
        description="Batch of login events fetched from Admin SDK Reports API activities.list",
    )


class LiveSweepRequest(BaseModel):
    lookback_minutes: int = Field(
        default=15,
        description="Lookback window in minutes for Admin SDK Reports API activities.list(applicationName='login')",
    )
    persist_all_allowed: bool = Field(
        default=True,
        description="Whether to record ALLOW_ATTESTED decisions in the enforcement log table",
    )


def _extract_client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "0.0.0.0"


def _sync_live_inventory() -> Dict[str, Any]:
    """Loads live ChromeOS Directory devices and Cloud Identity approved devices into SessionGuardService."""
    config = config_service.get_tenant_config()
    customer_id = config.customer_id or "customers/my_customer"
    records: List[DeviceRecord] = []
    errors: List[str] = []

    # 1. Load ChromeOS fleet from Admin SDK Directory API
    try:
        cros_list = directory_service.list_all_chromeos_inventory(customer_id=customer_id)
        for item in cros_list:
            records.append(
                DeviceRecord(
                    device_id=item["device_id"],
                    serial_number=item["serial_number"],
                    device_type="CHROMEOS",
                    status=item["status"],
                    assigned_user=item.get("assigned_user"),
                    org_unit_path=item.get("org_unit_path", "/"),
                )
            )
    except Exception as e:
        errors.append(f"Directory ChromeOS sync error: {e}")

    # 2. Load Company & Admin-Approved BYOD devices from Cloud Identity Devices API
    if cloud_identity_service.service:
        ci_customer = normalize_customer_id(customer_id)
        try:
            resp = (
                cloud_identity_service.service.devices()
                .list(customer=ci_customer, pageSize=200)
                .execute()
            )
            for dev in resp.get("devices", []) or []:
                serial = (dev.get("serialNumber") or "").strip().upper()
                dev_name = dev.get("name", "")
                device_id = dev_name.split("/")[-1] if dev_name else serial
                owner_type = (dev.get("ownerType") or "").upper()
                mgmt_state = (dev.get("managementState") or "APPROVED").upper()
                if serial and (
                    owner_type in ("COMPANY", "CUSTOMER")
                    or mgmt_state == "APPROVED"
                ):
                    records.append(
                        DeviceRecord(
                            device_id=device_id,
                            serial_number=serial,
                            device_type="CLOUD_IDENTITY_APPROVED",
                            status="APPROVED",
                        )
                    )
                elif device_id and mgmt_state == "APPROVED":
                    records.append(
                        DeviceRecord(
                            device_id=device_id,
                            serial_number=device_id.upper(),
                            device_type="CLOUD_IDENTITY_APPROVED",
                            status="APPROVED",
                        )
                    )
        except Exception as e:
            errors.append(f"Cloud Identity devices sync error: {e}")
    else:
        errors.append(
            cloud_identity_service.init_error
            or "Cloud Identity API service is not initialized."
        )

    if not records and errors:
        raise HTTPException(
            status_code=500,
            detail="Failed to synchronize live device inventory: " + "; ".join(errors),
        )

    loaded_count = session_guard.load_device_inventory(records)
    return {
        "status": "SYNCED",
        "loaded_count": loaded_count,
        "inventory_devices_cached": session_guard.metrics["inventory_devices_cached"],
        "warnings": errors,
    }


@router.post("/sync-inventory")
async def sync_session_watch_inventory() -> Dict[str, Any]:
    """Synchronizes the in-memory O(1) device inventory cache from live Directory & Cloud Identity APIs."""
    return _sync_live_inventory()


@router.post("/attest")
async def attest_device_session(
    body: ExtensionAttestRequest,
    request: Request,
) -> Dict[str, object]:
    """Receives a real-time device attestation heartbeat from the managed Chrome extension or portal."""
    if session_guard.metrics["inventory_devices_cached"] == 0:
        try:
            _sync_live_inventory()
        except Exception as sync_err:
            print(f"WARNING [session_watch.py]: Auto-sync before attest noticed: {sync_err}")

    client_ip = _extract_client_ip(request)
    user_agent = request.headers.get("user-agent", "")
    approved, message = session_guard.record_extension_attestation(
        user_email=body.user_email,
        serial_number=body.serial_number,
        ip_address=client_ip,
        user_agent=user_agent,
        session_id=body.session_id or "",
    )
    if not approved:
        raise HTTPException(status_code=403, detail=message)
    return {
        "status": "ATTESTED",
        "user_email": body.user_email.lower(),
        "serial_number": body.serial_number.upper(),
        "client_ip": client_ip,
        "message": message,
    }


@router.post("/sweep")
async def evaluate_login_sweep(body: SweepRequest) -> Dict[str, object]:
    """Evaluates a batch of domain login events and revokes unattested sessions."""
    now = time.time()
    audit_events = [
        LoginAuditEvent(
            event_id=e.event_id,
            user_email=e.user_email,
            ip_address=e.ip_address,
            timestamp_epoch=e.timestamp_epoch or (now - 60.0),
            login_type=e.login_type,
            is_suspicious=e.is_suspicious,
        )
        for e in body.events
    ]
    actions = session_guard.evaluate_login_batch(
        audit_events, now_epoch=now, persist_all_allowed=True
    )
    for action in actions:
        print(session_guard.format_cloud_logging_entry(action), flush=True)
    revoked = [a for a in actions if a.decision == "REVOKE_SIGN_OUT"]
    return {
        "evaluated_count": len(audit_events),
        "revoked_count": len(revoked),
        "revoked_users": [a.user_email for a in revoked],
        "metrics": session_guard.metrics,
    }


@router.post("/live-sweep")
async def execute_live_reports_sweep(
    body: Optional[LiveSweepRequest] = None,
    x_cloudscheduler: Optional[str] = Header(None),
) -> Dict[str, Any]:
    """Pulls live login events from Admin SDK Reports API (`activities.list`) and executes `users.signOut` on unattested sessions."""
    req_body = body or LiveSweepRequest()
    if session_guard.metrics["inventory_devices_cached"] == 0:
        try:
            _sync_live_inventory()
        except Exception as sync_err:
            print(f"WARNING [session_watch.py]: Auto-sync before live-sweep noticed: {sync_err}")

    try:
        raw_events = directory_service.list_recent_login_events(
            lookback_minutes=req_body.lookback_minutes
        )
    except Exception as e:
        err_str = str(e)
        if "unauthorized_client" in err_str.lower() or "access_denied" in err_str.lower() or "403" in err_str:
            raise HTTPException(
                status_code=500,
                detail=(
                    "Admin SDK Reports API authorization error. Ensure Domain-Wide Delegation in "
                    "Admin Console (https://admin.google.com/ac/owl/domainwidedelegation) includes scopes: "
                    "https://www.googleapis.com/auth/admin.reports.audit.readonly and "
                    f"https://www.googleapis.com/auth/admin.directory.user.security. Raw error: {err_str}"
                ),
            )
        raise HTTPException(
            status_code=500,
            detail=f"Failed to query Admin SDK Reports API login events: {err_str}",
        )

    now = time.time()
    audit_events = [
        LoginAuditEvent(
            event_id=ev["event_id"],
            user_email=ev["user_email"],
            ip_address=ev["ip_address"],
            timestamp_epoch=ev["timestamp_epoch"],
            login_type=ev.get("login_type", "exchange"),
            is_suspicious=ev.get("is_suspicious", False),
        )
        for ev in raw_events
    ]

    try:
        actions = session_guard.evaluate_login_batch(
            audit_events,
            now_epoch=now,
            persist_all_allowed=req_body.persist_all_allowed,
        )
    except Exception as eval_err:
        raise HTTPException(
            status_code=500,
            detail=f"Error executing users.signOut circuit breaker during sweep: {eval_err}",
        )

    for action in actions:
        print(session_guard.format_cloud_logging_entry(action), flush=True)

    revoked = [a for a in actions if a.decision == "REVOKE_SIGN_OUT"]
    return {
        "status": "LIVE_SWEEP_COMPLETE",
        "triggered_by": "cloud_scheduler" if x_cloudscheduler else "portal_api",
        "lookback_minutes": req_body.lookback_minutes,
        "fetched_login_events": len(audit_events),
        "revoked_count": len(revoked),
        "revoked_users": [a.user_email for a in revoked],
        "actions": [
            {
                "event_id": a.event_id,
                "user_email": a.user_email,
                "ip_address": a.ip_address,
                "decision": a.decision,
                "reason": a.reason,
                "matched_serial": a.matched_serial,
                "detection_latency_sec": round(a.detection_latency_sec, 2),
                "timestamp_iso": a.timestamp_iso,
            }
            for a in actions
        ],
        "metrics": session_guard.metrics,
    }


@router.get("/metrics")
async def get_session_watch_metrics() -> Dict[str, object]:
    """Returns live quota utilization and enforcement metrics."""
    config = config_service.get_tenant_config()
    return {
        "enforcement_mode": getattr(config, "enforcement_mode", "SESSION_WATCH"),
        "branch_variation": "poc/fundamentals-session-watch",
        "metrics": session_guard.metrics,
        "quotas": {
            "reports_api_qpm_limit": session_guard.REPORTS_API_QPM_LIMIT,
            "directory_api_qpm_limit": session_guard.DIRECTORY_API_QPM_LIMIT,
        },
        "active_attestations": session_guard.get_active_attestations(),
        "recent_actions": session_guard.get_recent_actions(limit=20),
    }

