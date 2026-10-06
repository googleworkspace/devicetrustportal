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
from typing import Dict, List, Optional
from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, Field

from backend.services.config_service import config_service
from backend.services.directory_service import directory_service
from backend.services.session_guard import (
    LoginAuditEvent,
    SessionGuardService,
    TokenAuditEvent,
)

router = APIRouter(prefix="/api/session-watch", tags=["Session Watch (CAA-Free)"])

# Singleton guard service for runtime, hooking real directory_service.sign_out_user by default
session_guard = SessionGuardService(
    signout_callback=directory_service.sign_out_user,
    user_ou_lookup=lambda email: directory_service.get_user_details(email).get("orgUnitPath", "/"),
)

def _sync_guard_config() -> None:
    cfg = config_service.get_tenant_config()
    is_active = cfg.enable_session_guard and cfg.session_guard_mode != "AUDIT_SIMULATION"
    session_guard.enabled = is_active
    session_guard.exempt_ous = cfg.session_guard_exempt_ous
    session_guard.exempt_groups = cfg.session_guard_exempt_groups
    session_guard.campus_egress_ips = set(cfg.trusted_ip_ranges)


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
    """Receives a real-time device attestation heartbeat from the managed Chrome extension."""
    client_ip = request.client.host if request.client else "0.0.0.0"
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
        "message": message,
    }


@router.post("/sweep")
async def evaluate_login_sweep(body: SweepRequest) -> Dict[str, object]:
    """Evaluates a 1-to-5 minute window of domain login events and revokes unattested sessions."""
    _sync_guard_config()
    config = config_service.get_tenant_config()
    is_dry_run = not config.enable_session_guard or config.session_guard_mode == "AUDIT_SIMULATION"

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
    actions = session_guard.evaluate_login_batch(audit_events, now_epoch=now, dry_run=is_dry_run)
    revoked = [a for a in actions if a.decision == "REVOKE_SIGN_OUT"]
    simulated = [a for a in actions if a.decision == "WOULD_REVOKE_DISABLED"]
    exempt = [a for a in actions if a.decision == "ALLOW_EXEMPT"]
    return {
        "session_guard_enabled": config.enable_session_guard,
        "session_guard_mode": config.session_guard_mode,
        "dry_run": is_dry_run,
        "evaluated_count": len(audit_events),
        "revoked_count": len(revoked),
        "simulated_count": len(simulated),
        "exempt_count": len(exempt),
        "revoked_users": [a.user_email for a in revoked],
        "simulated_users": [a.user_email for a in simulated],
        "exempt_users": [a.user_email for a in exempt],
        "metrics": session_guard.metrics,
    }
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
    _sync_guard_config()
    config = config_service.get_tenant_config()
    is_dry_run = not config.enable_session_guard or config.session_guard_mode == "AUDIT_SIMULATION"

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
    actions = session_guard.evaluate_token_batch(audit_events, now_epoch=now, dry_run=is_dry_run)
    revoked = [a for a in actions if a.decision == "REVOKE_SIGN_OUT"]
    simulated = [
        a for a in actions if a.decision.startswith("WOULD_REVOKE_")
    ]
    exempt = [a for a in actions if a.decision == "ALLOW_EXEMPT"]
    return {
        "session_guard_enabled": config.enable_session_guard,
        "session_guard_mode": config.session_guard_mode,
        "dry_run": is_dry_run,
        "evaluated_count": len(audit_events),
        "revoked_count": len(revoked),
        "simulated_count": len(simulated),
        "exempt_count": len(exempt),
        "revoked_users": [a.user_email for a in revoked],
        "simulated_users": [a.user_email for a in simulated],
        "exempt_users": [a.user_email for a in exempt],
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


@router.get("/metrics")
async def get_session_watch_metrics() -> Dict[str, object]:
    """Returns live quota utilization and enforcement metrics."""
    config = config_service.get_tenant_config()
    return {
        "session_guard_enabled": config.enable_session_guard,
        "metrics": session_guard.metrics,
        "quotas": {
            "reports_api_qpm_limit": session_guard.REPORTS_API_QPM_LIMIT,
            "directory_api_qpm_limit": session_guard.DIRECTORY_API_QPM_LIMIT,
        },
    }
