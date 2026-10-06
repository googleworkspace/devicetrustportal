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
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field

from backend.routes.admin import get_current_user_email
from backend.services.cloud_identity import cloud_identity_service, normalize_customer_id
from backend.services.config_service import config_service
from backend.services.directory_service import directory_service
from backend.services.session_guard import (
    DeviceRecord,
    LoginAuditEvent,
    SessionGuardService,
    TokenAuditEvent,
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


class OnboardingLeaseRequest(BaseModel):
    user_email: Optional[str] = Field(default=None, description="Signed-in Google Workspace user email")
    minutes: Optional[int] = Field(
        default=None,
        description="Optional override for onboarding grace window in minutes",
    )
    duration_minutes: Optional[int] = Field(
        default=None,
        description="Optional override for onboarding grace window in minutes (defaults to tenant config)",
    )


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
        default=60,
        description="Lookback window in minutes for Admin SDK Reports API activities.list(applicationName='login')",
    )
    persist_all_allowed: bool = Field(
        default=True,
        description="Whether to record ALLOW_ATTESTED decisions in the enforcement log table",
    )
    force: bool = Field(
        default=False,
        description="Allow manual admin execution from Admin Configurations even when background scheduler is disabled",
    )
    sub_poll_cycles: Optional[int] = Field(
        default=None,
        description="Number of sub-minute polling passes to run within a single Cloud Scheduler invocation",
    )
    sub_poll_interval_sec: float = Field(
        default=10.0,
        description="Seconds between sub-minute polling passes when triggered by Cloud Scheduler",
    )


_cold_start_baselined: bool = False


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
            with cloud_identity_service._lock:
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


@router.post("/onboarding-lease")
async def start_onboarding_grace_lease(
    request: Request,
    body: Optional[OnboardingLeaseRequest] = None,
) -> Dict[str, Any]:
    """Grants a temporary onboarding grace lease (default 15m) so a user adding/approving a personal
    BYOD device is never signed out by the background Session Watch sweep mid-enrollment.
    """
    import datetime

    req_body = body or OnboardingLeaseRequest()
    target_email = (req_body.user_email or "").strip().lower()
    if not target_email:
        auth_header = request.headers.get("Authorization")
        if auth_header:
            target_email = get_current_user_email(authorization=auth_header).strip().lower()
    if not target_email:
        raise HTTPException(status_code=400, detail="user_email or Authorization bearer token is required")

    config = config_service.get_tenant_config()
    requested_min = req_body.minutes or req_body.duration_minutes
    minutes = (
        requested_min
        if requested_min and requested_min > 0
        else getattr(config, "session_watch_onboarding_grace_minutes", 15)
    )
    duration_sec = max(60, int(minutes) * 60)
    now = time.time()
    expires_at = session_guard.grant_onboarding_lease(
        user_email=target_email,
        duration_sec=duration_sec,
        now_epoch=now,
        reason="PORTAL_ADD_PERSONAL_DEVICE",
    )
    expires_iso = datetime.datetime.fromtimestamp(
        expires_at, tz=datetime.timezone.utc
    ).isoformat()
    return {
        "status": "LEASE_ACTIVE",
        "user_email": target_email,
        "minutes": int(minutes),
        "duration_minutes": int(minutes),
        "remaining_seconds": int(round(expires_at - now)),
        "expires_at_iso": expires_iso,
        "message": (
            f"15-Minute Personal Device Onboarding Pass Active for {target_email} "
            f"(until {expires_iso}). Background users.signOut is paused while you sign in and approve your personal device."
        ),
    }


@router.get("/session-status")
async def verify_active_session_status(
    request: Request,
    user_email: str = Depends(get_current_user_email),
) -> Dict[str, Any]:
    """Real-time session guard check for active portal sessions.

    1. `get_current_user_email` automatically rejects any Google ID token issued prior to
       the user's most recent `users.signOut` timestamp with HTTP 401.
    2. When `session_watch_enabled` is True, if the browser User-Agent is a personal/BYOD OS
       (Mac, Windows, Android, iOS) and the user has no APPROVED device matching that OS in
       Cloud Identity (and no active 15m Onboarding Grace Pass), immediately executes
       `users.signOut` inline (<0.5s) and returns HTTP 401 to terminate the session.
    """
    norm_user = (user_email or "").strip().lower()
    config = config_service.get_tenant_config()
    sw_enabled = bool(getattr(config, "session_watch_enabled", False)) or getattr(
        config, "enforcement_mode", "DISABLED"
    ) in ("SESSION_WATCH", "BOTH")

    if not sw_enabled:
        return {"status": "OK", "session_watch_enabled": False}

    has_lease, rem_sec = session_guard.has_active_onboarding_lease(norm_user)
    if has_lease:
        return {
            "status": "OK",
            "session_watch_enabled": True,
            "onboarding_grace_active": True,
            "remaining_seconds": int(rem_sec),
        }

    in_scope, scope_reason = directory_service.is_user_in_session_watch_scope(
        user_email=norm_user,
        target_ous=getattr(config, "session_watch_target_ous", []),
        target_groups=getattr(config, "session_watch_target_groups", []),
        exempt_admins=getattr(config, "session_watch_exempt_admins", False),
        portal_admins=getattr(config, "portal_admins", []),
    )
    if not in_scope:
        return {"status": "OK", "session_watch_enabled": True, "exempt": True, "reason": scope_reason}

    ua = (request.headers.get("user-agent") or "").lower()
    sec_ch_platform = (request.headers.get("sec-ch-ua-platform") or "").lower()
    is_cros = "cros" in ua or "chrome os" in sec_ch_platform or "chromeos" in sec_ch_platform
    if is_cros:
        return {"status": "OK", "session_watch_enabled": True, "platform": "CHROME_OS"}

    os_family = None
    if "macintosh" in ua or "mac os x" in ua:
        os_family = "MAC"
    elif "windows" in ua:
        os_family = "WINDOWS"
    elif "android" in ua:
        os_family = "ANDROID"
    elif "iphone" in ua or "ipad" in ua:
        os_family = "IOS"

    if os_family and cloud_identity_service.service:
        cid = normalize_customer_id(config.customer_id or "customers/my_customer")
        try:
            from backend.routes.devices import crawl_devices_for_user, sync_time_sort_key

            now = time.time()
            user_items, _ = crawl_devices_for_user(
                customer_id=cid,
                target_email=norm_user,
                query_filter=f"email:{norm_user}",
            )

            def _parse_item_sync_epoch(sync_str: str) -> float:
                ts = sync_time_sort_key(sync_str)
                return ts if ts > 0 else 0.0

            # If an APPROVED ChromeOS or Company device synced within the last 120s, the user is on
            # their approved Chromebook (e.g. using Chrome DevTools Mobile Emulation) — do not sign out.
            recent_approved_cros_sync = any(
                (it.owner_type == "COMPANY" or "CHROME" in (it.device_type or "").upper())
                and it.approval_state == "APPROVED"
                and (now - _parse_item_sync_epoch(it.last_sync_time)) <= 120.0
                for it in user_items
            )
            if recent_approved_cros_sync:
                return {
                    "status": "OK",
                    "session_watch_enabled": True,
                    "platform": "CHROME_OS_DEVTOOLS_OR_RECENT_SYNC",
                }

            matching_os_items = [
                it
                for it in user_items
                if os_family in (it.device_type or "").upper()
                or os_family in (it.os_version or "").upper()
            ]
            has_approved_matching_os = any(
                it.approval_state == "APPROVED" for it in matching_os_items
            )

            # Identify if there is a recently-synced (within 15m) unapproved device for this OS
            active_unapproved_items = []
            for it in matching_os_items:
                if it.owner_type == "COMPANY" or it.approval_state == "APPROVED":
                    continue
                sync_ep = _parse_item_sync_epoch(it.last_sync_time)
                age_sec = (now - sync_ep) if sync_ep > 0 else 999999.0
                if it.approval_state == "PENDING_APPROVAL" and age_sec <= 900.0:
                    active_unapproved_items.append((it, sync_ep))
                elif (
                    not has_approved_matching_os
                    and it.approval_state in ("BLOCKED", "UNAPPROVED")
                    and age_sec <= 900.0
                ):
                    active_unapproved_items.append((it, sync_ep))

            if active_unapproved_items:
                is_dry_run = getattr(config, "session_watch_dry_run", False)
                for it, sync_ep in active_unapproved_items:
                    if not is_dry_run and it.owner_type != "COMPANY" and it.approval_state == "PENDING_APPROVAL":
                        try:
                            cloud_identity_service.revoke_device_user(
                                device_user_name=it.device_user_name,
                                customer_id=cid,
                                action="BLOCK",
                            )
                        except Exception:
                            pass
                    if sync_ep > 0:
                        session_guard.mark_device_sync_enforced(
                            it.device_user_name, norm_user, sync_ep, now_epoch=now
                        )
                action = session_guard.execute_immediate_signout(
                    user_email=norm_user,
                    event_id=f"inline-session-guard:{norm_user}:{os_family}:{int(now)}",
                    reason=f"Immediate inline revocation: Unapproved {os_family} device accessed portal without an active 15m Onboarding Grace Pass.",
                    ip_address=_extract_client_ip(request),
                    dry_run=is_dry_run,
                )
                print(session_guard.format_cloud_logging_entry(action), flush=True)
                if not is_dry_run:
                    raise HTTPException(
                        status_code=401,
                        detail=f"Unapproved {os_family} device detected. Your Google Workspace session has been terminated.",
                    )
        except HTTPException:
            raise
        except Exception as e:
            print(f"WARNING [session_watch.py]: verify_active_session_status check notice: {e}")

    return {"status": "OK", "session_watch_enabled": True}


class TokenEventPayload(BaseModel):
    event_id: str
    user_email: str
    ip_address: str
    timestamp_epoch: Optional[float] = None
    app_name: str = ""
    client_id: str = ""
    asn: Optional[str] = None
    is_suspicious: bool = False


class TokenSweepRequest(BaseModel):
    events: List[TokenEventPayload] = Field(
        default_factory=list,
        description="Batch of token events fetched from Admin SDK Reports API activities.list(applicationName='token')",
    )


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
    """Evaluates a 1-to-5 minute window of domain login events and revokes unattested sessions."""
    config = config_service.get_tenant_config()
    sw_enabled = bool(
        getattr(config, "session_watch_enabled", False)
        or getattr(config, "enable_session_guard", False)
    )
    session_guard.enabled = sw_enabled

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
    simulated = [a for a in actions if a.decision == "WOULD_REVOKE_DISABLED"]
    return {
        "session_guard_enabled": sw_enabled,
        "dry_run": not sw_enabled,
        "evaluated_count": len(audit_events),
        "revoked_count": len(revoked),
        "simulated_count": len(simulated),
        "revoked_users": [a.user_email for a in revoked],
        "simulated_users": [a.user_email for a in simulated],
        "metrics": session_guard.metrics,
    }


@router.post("/sweep-tokens")
async def evaluate_token_sweep(body: TokenSweepRequest) -> Dict[str, object]:
    """Evaluates a batch of token audit events to detect cloud hosting ASNs and foreign IP pivots."""
    config = config_service.get_tenant_config()
    cookie_sentinel_active = bool(
        getattr(config, "cookie_threat_detection_enabled", False)
        or getattr(config, "enable_session_guard", False)
        or getattr(config, "session_watch_enabled", False)
    )
    is_dry_run = bool(getattr(config, "session_watch_dry_run", False)) or (not cookie_sentinel_active)
    session_guard.enabled = not is_dry_run

    now = time.time()
    audit_events = [
        TokenAuditEvent(
            event_id=e.event_id,
            user_email=e.user_email,
            ip_address=e.ip_address,
            timestamp_epoch=e.timestamp_epoch or (now - 60.0),
            app_name=e.app_name,
            client_id=e.client_id,
            asn=e.asn,
            is_suspicious=e.is_suspicious,
        )
        for e in body.events
    ]
    actions = session_guard.evaluate_token_batch(
        audit_events,
        now_epoch=now,
        dry_run=is_dry_run,
    )
    revoked = [a for a in actions if a.decision == "REVOKE_SIGN_OUT"]
    simulated = [
        a for a in actions if a.decision.startswith("WOULD_REVOKE_")
    ]
    return {
        "session_guard_enabled": not is_dry_run,
        "session_watch_enabled": bool(getattr(config, "session_watch_enabled", False)),
        "cookie_threat_detection_enabled": bool(getattr(config, "cookie_threat_detection_enabled", False)),
        "dry_run": is_dry_run,
        "evaluated_count": len(audit_events),
        "revoked_count": len(revoked),
        "simulated_count": len(simulated),
        "flagged_actions": [
            {
                "event_id": a.event_id,
                "user_email": a.user_email,
                "ip_address": a.ip_address,
                "decision": a.decision,
                "reason": a.reason,
            }
            for a in (revoked + simulated)
        ],
        "metrics": session_guard.metrics,
    }


def _execute_single_live_sweep_pass(
    req_body: LiveSweepRequest,
    config: Any,
    include_reports_api: bool = True,
    run_login_sweep: bool = True,
    run_token_sweep: bool = False,
) -> Dict[str, Any]:
    """Executes a single pass of Admin SDK Reports API + Cloud Identity unapproved/blocked BYOD sync detection
    and/or Stolen Cookie & Token Threat Detection (`token` audit stream)."""
    global _cold_start_baselined
    import datetime

    now = time.time()
    cid = normalize_customer_id(config.customer_id or "customers/my_customer")
    is_dry_run = getattr(config, "session_watch_dry_run", False)

    def _scope_checker(email: str) -> tuple[bool, str]:
        return directory_service.is_user_in_session_watch_scope(
            user_email=email,
            target_ous=getattr(config, "session_watch_target_ous", []),
            target_groups=getattr(config, "session_watch_target_groups", []),
            exempt_admins=getattr(config, "session_watch_exempt_admins", False),
            portal_admins=getattr(config, "portal_admins", []),
        )

    raw_events: List[Dict[str, Any]] = []
    if run_login_sweep and include_reports_api:
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

    audit_log_events_count = len(raw_events)
    unapproved_ci_byod_events_count = 0
    auto_blocked_byod_count = 0
    actions: List[Any] = []
    evaluated_count = 0

    if run_login_sweep:
        # Scan Cloud Identity Devices API for real-time PENDING_APPROVAL and recently-synced BLOCKED BYOD devices!
        # Chrome Profile Reporting updates `lastSyncTime` in ~1.7 seconds on sign-in, even when Admin SDK
        # Reports API `login` logs lag by 15-60m or when the device was already in `BLOCKED` state.
        users_with_ci_events: set[str] = set()
        raw_ci_byod_records_by_user: Dict[str, List[Dict[str, Any]]] = {}
        if cloud_identity_service.service:
            try:
                with cloud_identity_service._lock:
                    devs_resp = (
                        cloud_identity_service.service.devices()
                        .list(customer=cid, pageSize=100)
                        .execute()
                    )
                    dus_resp = (
                        cloud_identity_service.service.devices()
                        .deviceUsers()
                        .list(parent="devices/-", customer=cid, pageSize=100)
                        .execute()
                    )
                devs_by_name = {
                    d.get("name", ""): d for d in (devs_resp.get("devices", []) or []) if d.get("name")
                }
                for du in dus_resp.get("deviceUsers", []) or []:
                    du_name = du.get("name", "")
                    du_email = (du.get("userEmail") or "").strip().lower()
                    if not du_name or not du_email:
                        continue
                    parent_name = "/".join(du_name.split("/")[:2])
                    parent_dev = devs_by_name.get(parent_name, {})
                    owner_type = (parent_dev.get("ownerType") or "BYOD").upper()
                    if owner_type in ("COMPANY", "CUSTOMER"):
                        continue
                    raw_state = (
                        du.get("managementState")
                        or du.get("approvalState")
                        or parent_dev.get("managementState")
                        or ""
                    ).upper()
                    model = parent_dev.get("model") or "Personal BYOD Device"
                    dtype = (parent_dev.get("deviceType") or "BYOD").upper()
                    serial = (parent_dev.get("serialNumber") or "N/A").strip() or "N/A"
                    last_sync_str = (
                        du.get("lastSyncTime")
                        or parent_dev.get("lastSyncTime")
                        or du.get("createTime")
                        or ""
                    )
                    try:
                        sync_epoch = datetime.datetime.fromisoformat(
                            last_sync_str.replace("Z", "+00:00")
                        ).timestamp()
                    except Exception:
                        sync_epoch = now - 30.0

                    norm_state = "PENDING_APPROVAL" if raw_state in ("PENDING", "PENDING_APPROVAL") else raw_state
                    raw_ci_byod_records_by_user.setdefault(du_email, []).append(
                        {
                            "device_user_name": du_name,
                            "model": model,
                            "device_type": dtype,
                            "serial_number": serial,
                            "approval_state": norm_state,
                            "sync_epoch": sync_epoch,
                            "last_sync_str": last_sync_str,
                        }
                    )

                    is_pending = norm_state == "PENDING_APPROVAL"
                    is_blocked_or_unapproved = norm_state in ("BLOCKED", "UNAPPROVED")
                    age_since_sync = max(0.0, now - sync_epoch)

                    # On cold start, baseline historical BLOCKED devices that synced >15 minutes ago
                    # so old blocked devices from hours/days/months ago never trigger false sign-outs.
                    if is_blocked_or_unapproved and not _cold_start_baselined and age_since_sync > 900.0:
                        session_guard.mark_device_sync_enforced(du_name, du_email, sync_epoch, now_epoch=now)
                        continue

                    already_enforced = session_guard.is_device_sync_already_enforced(du_name, sync_epoch)
                    last_user_signout = session_guard.get_last_signout_epoch(du_email)

                    should_trigger_unapproved_sync = False
                    if is_pending and not already_enforced:
                        should_trigger_unapproved_sync = True
                    elif (
                        is_blocked_or_unapproved
                        and not already_enforced
                        and age_since_sync <= (req_body.lookback_minutes * 60.0)
                        and sync_epoch > (last_user_signout + 1.0)
                    ):
                        should_trigger_unapproved_sync = True

                    if should_trigger_unapproved_sync:
                        effective_epoch = min(sync_epoch, now - 60.0)
                        session_guard.record_unapproved_device(
                            user_email=du_email,
                            device_user_name=du_name,
                            model=model,
                            device_type=dtype,
                            serial_number=serial,
                            approval_state=norm_state,
                            last_sync_epoch=sync_epoch,
                        )
                        if du_email not in users_with_ci_events:
                            users_with_ci_events.add(du_email)
                            unapproved_ci_byod_events_count += 1
                            raw_events.append(
                                {
                                    "event_id": f"ci-pending:{du_name}:{last_sync_str or int(now)}",
                                    "user_email": du_email,
                                    "ip_address": "cloud-identity-sync",
                                    "timestamp_epoch": effective_epoch,
                                    "timestamp_iso": last_sync_str,
                                    "login_type": "cloud_identity_device_sync",
                                    "is_suspicious": False,
                                }
                            )
                _cold_start_baselined = True
            except Exception as ci_scan_err:
                print(f"WARNING [session_watch.py]: Cloud Identity pending sync scan notice: {ci_scan_err}")

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
        evaluated_count += len(audit_events)

        checked_unapproved_by_user: Dict[str, Optional[Dict[str, Any]]] = {}

        def _unapproved_device_checker(email: str, _login_epoch: float) -> Optional[Dict[str, Any]]:
            nonlocal auto_blocked_byod_count
            norm_user = email.strip().lower()
            if norm_user in checked_unapproved_by_user:
                return checked_unapproved_by_user[norm_user]

            found_dev: Optional[Dict[str, Any]] = None
            if cloud_identity_service.service:
                try:
                    raw_records = raw_ci_byod_records_by_user.get(norm_user)
                    if raw_records is None:
                        from backend.routes.devices import crawl_devices_for_user

                        user_items, _ = crawl_devices_for_user(
                            customer_id=cid,
                            target_email=norm_user,
                            query_filter=f"email:{norm_user}",
                        )
                        raw_records = [
                            {
                                "device_user_name": it.device_user_name,
                                "model": it.model,
                                "device_type": it.device_type,
                                "serial_number": it.serial_number,
                                "approval_state": it.approval_state,
                                "sync_epoch": now - 30.0,
                            }
                            for it in user_items
                            if it.owner_type != "COMPANY"
                        ]

                    for rec in raw_records:
                        rec_state = rec["approval_state"]
                        rec_sync_ep = float(rec.get("sync_epoch") or (now - 30.0))
                        is_active_unapproved = rec_state == "PENDING_APPROVAL" or (
                            rec_state in ("BLOCKED", "UNAPPROVED")
                            and not session_guard.is_device_sync_already_enforced(
                                rec["device_user_name"], rec_sync_ep
                            )
                            and (now - rec_sync_ep) <= (req_body.lookback_minutes * 60.0)
                        )
                        if is_active_unapproved:
                            found_dev = rec
                            if not is_dry_run:
                                try:
                                    if rec_state == "PENDING_APPROVAL":
                                        cloud_identity_service.revoke_device_user(
                                            device_user_name=rec["device_user_name"],
                                            customer_id=cid,
                                            action="BLOCK",
                                        )
                                        auto_blocked_byod_count += 1
                                    # Also block any stale serial-less APPROVED duplicate records of the same OS type for this user
                                    for dup in raw_records:
                                        if (
                                            dup["device_user_name"] != rec["device_user_name"]
                                            and dup["device_type"] == rec["device_type"]
                                            and dup["approval_state"] == "APPROVED"
                                            and (not dup["serial_number"] or dup["serial_number"] == "N/A")
                                        ):
                                            try:
                                                cloud_identity_service.revoke_device_user(
                                                    device_user_name=dup["device_user_name"],
                                                    customer_id=cid,
                                                    action="BLOCK",
                                                )
                                                auto_blocked_byod_count += 1
                                            except Exception:
                                                pass
                                except Exception as blk_err:
                                    print(
                                        f"WARNING [session_watch.py]: Could not auto-block pending device '{rec['device_user_name']}': {blk_err}"
                                    )
                            session_guard.mark_device_sync_enforced(
                                rec["device_user_name"],
                                norm_user,
                                rec_sync_ep,
                                now_epoch=now,
                            )
                            session_guard.clear_unapproved_devices_for_user(
                                norm_user, device_user_name=rec["device_user_name"]
                            )
                            break

                    if found_dev is None:
                        # If no unapproved device is active and Cloud Identity shows an APPROVED device
                        # that synced within the last 180 seconds, auto-attest the user's login session
                        # so logging into an approved Chromebook/BYOD device isn't signed out before opening the portal.
                        for rec in raw_records:
                            rec_sync_ep = float(rec.get("sync_epoch") or 0.0)
                            if (
                                rec.get("approval_state") == "APPROVED"
                                and rec.get("last_sync_str")
                                and 0.0 <= (now - rec_sync_ep) <= 180.0
                            ):
                                eff_serial = (
                                    rec["serial_number"].strip().upper()
                                    if rec.get("serial_number") and rec["serial_number"] != "N/A"
                                    else rec["device_user_name"].strip().upper()
                                )
                                dtype_tag = (
                                    "CHROMEOS"
                                    if "CHROME" in str(rec.get("device_type") or "").upper()
                                    else "CLOUD_IDENTITY_APPROVED"
                                )
                                for ev_item in audit_events:
                                    if ev_item.user_email.strip().lower() == norm_user:
                                        session_guard.promote_approved_device(
                                            user_email=norm_user,
                                            serial_number=eff_serial,
                                            device_type=dtype_tag,
                                            ip_address=ev_item.ip_address,
                                            now_epoch=now,
                                        )
                                break
                except Exception as ci_err:
                    print(
                        f"WARNING [session_watch.py]: Unapproved device check notice for '{norm_user}': {ci_err}"
                    )

            checked_unapproved_by_user[norm_user] = found_dev
            return found_dev

        try:
            login_actions = session_guard.evaluate_login_batch(
                audit_events,
                now_epoch=now,
                persist_all_allowed=req_body.persist_all_allowed,
                scope_checker=_scope_checker,
                unapproved_device_checker=_unapproved_device_checker,
                dry_run=is_dry_run,
            )
            actions.extend(login_actions)
        except Exception as eval_err:
            raise HTTPException(
                status_code=500,
                detail=f"Error executing users.signOut circuit breaker during sweep: {eval_err}",
            )

    # Pathway 3: Stolen Cookie & Token Threat Detection (Cloud Hosting ASN & Foreign IP Pivot Sentinel)
    token_log_events_count = 0
    if run_token_sweep and include_reports_api:
        try:
            raw_token_events = directory_service.list_recent_token_events(
                lookback_minutes=req_body.lookback_minutes
            )
            token_log_events_count = len(raw_token_events)
            if raw_token_events:
                token_audit_events = [
                    TokenAuditEvent(
                        event_id=tev["event_id"],
                        user_email=tev["user_email"],
                        ip_address=tev["ip_address"],
                        timestamp_epoch=tev["timestamp_epoch"],
                        app_name=tev.get("app_name", "Google Workspace Web/OAuth"),
                        asn=tev.get("asn"),
                    )
                    for tev in raw_token_events
                ]
                evaluated_count += len(token_audit_events)
                token_actions = session_guard.evaluate_token_batch(
                    token_audit_events,
                    now_epoch=now,
                    dry_run=is_dry_run,
                    persist_all_allowed=req_body.persist_all_allowed,
                    scope_checker=_scope_checker,
                )
                actions.extend(token_actions)
        except Exception as tok_err:
            if not run_login_sweep:
                err_str = str(tok_err)
                if "unauthorized_client" in err_str.lower() or "access_denied" in err_str.lower() or "403" in err_str:
                    raise HTTPException(
                        status_code=500,
                        detail=(
                            "Admin SDK Reports API authorization error during token threat sweep. Ensure Domain-Wide "
                            "Delegation includes https://www.googleapis.com/auth/admin.reports.audit.readonly and "
                            f"https://www.googleapis.com/auth/admin.directory.user.security. Raw error: {err_str}"
                        ),
                    )
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to query Admin SDK Reports API token events: {err_str}",
                )
            print(f"WARNING [session_watch.py]: Token audit stream sweep notice: {tok_err}")

    for action in actions:
        print(session_guard.format_cloud_logging_entry(action), flush=True)

    return {
        "audit_log_events_count": audit_log_events_count,
        "token_log_events_count": token_log_events_count,
        "unapproved_ci_byod_events_count": unapproved_ci_byod_events_count,
        "evaluated_count": evaluated_count,
        "auto_blocked_byod_count": auto_blocked_byod_count,
        "actions": actions,
        "is_dry_run": is_dry_run,
    }


@router.post("/live-sweep")
async def execute_live_reports_sweep(
    body: Optional[LiveSweepRequest] = None,
    x_cloudscheduler: Optional[str] = Header(None),
) -> Dict[str, Any]:
    """Pulls live login events from Admin SDK Reports API (`activities.list`), real-time Cloud Identity
    `PENDING_APPROVAL` / `BLOCKED` device syncs, and/or OAuth `token` audit events (Stolen Cookie & Token
    Threat Detection), executing `users.signOut` on unapproved or hijacked sessions.

    Session Management (`session_watch_enabled`) and Stolen Cookie & Token Threat Detection
    (`cookie_threat_detection_enabled`) can be enabled independently or together.
    """
    import asyncio

    req_body = body or LiveSweepRequest()
    config = config_service.get_tenant_config()
    sw_enabled = bool(getattr(config, "session_watch_enabled", False)) or getattr(
        config, "enforcement_mode", "DISABLED"
    ) in ("SESSION_WATCH", "BOTH")
    cookie_enabled = bool(getattr(config, "cookie_threat_detection_enabled", False))

    # If both Session Management and Stolen Cookie Threat Detection are disabled and force is not set, skip automatic sweep
    if not sw_enabled and not cookie_enabled and not req_body.force:
        return {
            "status": "SKIPPED_DISABLED",
            "session_watch_enabled": False,
            "cookie_threat_detection_enabled": False,
            "triggered_by": "cloud_scheduler" if x_cloudscheduler else "portal_api",
            "message": "Both Session Management and Stolen Cookie Threat Detection are disabled in Admin Configurations; skipping automatic sweep.",
        }

    run_login_sweep = sw_enabled or req_body.force
    run_token_sweep = cookie_enabled

    if run_login_sweep and session_guard.metrics["inventory_devices_cached"] == 0:
        try:
            _sync_live_inventory()
        except Exception as sync_err:
            print(f"WARNING [session_watch.py]: Auto-sync before live-sweep noticed: {sync_err}")

    if req_body.sub_poll_cycles is not None:
        cycles = max(1, min(10, int(req_body.sub_poll_cycles)))
    else:
        cycles = 5 if (x_cloudscheduler and run_login_sweep) else 1
    interval_sec = max(1.0, min(20.0, float(req_body.sub_poll_interval_sec)))

    total_audit_log_events = 0
    total_token_log_events = 0
    total_ci_byod_events = 0
    total_evaluated = 0
    total_auto_blocked = 0
    all_actions: List[Any] = []
    is_dry_run = getattr(config, "session_watch_dry_run", False)

    for cycle_idx in range(cycles):
        # Query Admin SDK Reports API on cycle 0 and cycle 2; query Cloud Identity on every 10s cycle
        include_reports = (cycle_idx % 2 == 0)
        pass_res = _execute_single_live_sweep_pass(
            req_body=req_body,
            config=config,
            include_reports_api=include_reports,
            run_login_sweep=run_login_sweep,
            run_token_sweep=run_token_sweep,
        )
        if cycle_idx == 0:
            total_audit_log_events = pass_res["audit_log_events_count"]
            total_token_log_events = pass_res.get("token_log_events_count", 0)
        total_ci_byod_events += pass_res["unapproved_ci_byod_events_count"]
        total_evaluated += pass_res["evaluated_count"]
        total_auto_blocked += pass_res["auto_blocked_byod_count"]
        all_actions.extend(pass_res["actions"])
        is_dry_run = pass_res["is_dry_run"]

        if cycle_idx < cycles - 1:
            await asyncio.sleep(interval_sec)

    revoked = [a for a in all_actions if a.decision == "REVOKE_SIGN_OUT"]
    audit_only = [
        a
        for a in all_actions
        if a.decision
        in (
            "AUDIT_WOULD_SIGN_OUT",
            "WOULD_REVOKE_HOSTING_ASN",
            "WOULD_REVOKE_TOKEN_IP_MISMATCH",
        )
    ]
    return {
        "status": "LIVE_SWEEP_COMPLETE",
        "triggered_by": "cloud_scheduler" if x_cloudscheduler else "portal_api",
        "session_watch_enabled": sw_enabled,
        "cookie_threat_detection_enabled": cookie_enabled,
        "sub_poll_cycles": cycles,
        "dry_run": is_dry_run,
        "lookback_minutes": req_body.lookback_minutes,
        "fetched_login_events": total_audit_log_events,
        "fetched_token_events": total_token_log_events,
        "unapproved_cloud_identity_byod_events": total_ci_byod_events,
        "evaluated_count": total_evaluated,
        "revoked_count": len(revoked),
        "auto_blocked_byod_devices": total_auto_blocked,
        "audit_would_signout_count": len(audit_only),
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
            for a in all_actions
        ],
        "metrics": session_guard.metrics,
    }


@router.get("/metrics")
async def get_session_watch_metrics() -> Dict[str, object]:
    """Returns live quota utilization, rollout scope, onboarding leases, and enforcement metrics."""
    config = config_service.get_tenant_config()
    sw_enabled = bool(
        getattr(config, "session_watch_enabled", False)
        or getattr(config, "enable_session_guard", False)
    )
    cookie_enabled = bool(getattr(config, "cookie_threat_detection_enabled", False))
    return {
        "enforcement_mode": getattr(config, "enforcement_mode", "DISABLED"),
        "session_watch_enabled": sw_enabled,
        "session_guard_enabled": sw_enabled,
        "cookie_threat_detection_enabled": cookie_enabled,
        "caa_enforcement_enabled": bool(getattr(config, "caa_enforcement_enabled", False)),
        "branch_variation": "poc/fundamentals-session-watch",
        "dry_run": getattr(config, "session_watch_dry_run", False),
        "session_watch_dry_run": getattr(config, "session_watch_dry_run", False),
        "exempt_admins": getattr(config, "session_watch_exempt_admins", False),
        "session_watch_exempt_admins": getattr(config, "session_watch_exempt_admins", False),
        "target_ous": getattr(config, "session_watch_target_ous", []),
        "session_watch_target_ous": getattr(config, "session_watch_target_ous", []),
        "target_groups": getattr(config, "session_watch_target_groups", []),
        "session_watch_target_groups": getattr(config, "session_watch_target_groups", []),
        "onboarding_grace_minutes": getattr(config, "session_watch_onboarding_grace_minutes", 15),
        "session_watch_onboarding_grace_minutes": getattr(config, "session_watch_onboarding_grace_minutes", 15),
        "metrics": session_guard.metrics,
        "quotas": {
            "reports_api_qpm_limit": session_guard.REPORTS_API_QPM_LIMIT,
            "directory_api_qpm_limit": session_guard.DIRECTORY_API_QPM_LIMIT,
        },
        "active_attestations": session_guard.get_active_attestations(),
        "active_onboarding_leases": session_guard.get_active_onboarding_leases(),
        "recent_actions": session_guard.get_recent_actions(limit=50),
    }


