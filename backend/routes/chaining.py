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

import random
import datetime
from typing import Optional, Dict, Any
from pydantic import BaseModel
from fastapi import APIRouter, HTTPException, Depends, Request
from backend.services.config_service import config_service
from backend.services.directory_service import directory_service
from backend.services.cloud_identity import cloud_identity_service
from backend.routes.session_watch import session_guard
from backend.routes.devices import crawl_devices_for_user, sync_time_sort_key
from backend.routes.admin import get_current_user_email

try:
    from google.cloud import firestore
    db = firestore.Client()
except Exception as e:
    print(f"INFO [chaining.py]: Firestore client not available ({e}). Using in-memory PAIRING_CODE_CACHE.")
    db = None

router = APIRouter(prefix="/api/chaining", tags=["Chaining"])

# 6-digit pairing codes are valid for 24 hours (86,400 seconds) and single-use upon device approval
PAIRING_CODE_TTL_SECONDS = 24 * 60 * 60

# Lightweight in-memory cache for pairing codes (code -> {user_email, expires_at})
PAIRING_CODE_CACHE: Dict[str, Dict[str, Any]] = {}


def _infer_caller_os_family(request: Optional[Request]) -> str:
    """Infers the OS family from the caller's HTTP User-Agent / Sec-CH-UA-Platform."""
    if not request:
        return "UNKNOWN"
    ch_platform = (request.headers.get("sec-ch-ua-platform") or "").strip().strip('"').upper()
    ua = (request.headers.get("user-agent") or "").upper()
    if "CROS" in ua or "CHROME OS" in ch_platform or "CHROMEOS" in ch_platform:
        return "CHROME_OS"
    if "IPHONE" in ua or "IPAD" in ua or "IOS" in ch_platform:
        return "IOS"
    if "ANDROID" in ua or "ANDROID" in ch_platform:
        return "ANDROID"
    if "MACINTOSH" in ua or "MAC OS" in ua or "MACOS" in ch_platform or "MAC" in ch_platform:
        return "MAC_OS"
    if "WINDOWS" in ua or "WIN" in ch_platform:
        return "WINDOWS"
    if "LINUX" in ua or "LINUX" in ch_platform:
        return "LINUX"
    return "UNKNOWN"


class GenerateResponse(BaseModel):
    pairing_code: str
    expires_in_seconds: int


class VerifyRequest(BaseModel):
    pairing_code: str
    raw_device_id: Optional[str] = None
    ev_header: Optional[str] = None


def store_pairing_code(code: str, user_email: str, expires_at: datetime.datetime):
    norm_code = (code or "").strip()
    if db:
        try:
            db.collection("pairing_codes").document(norm_code).set({
                "user_email": user_email,
                "expires_at": expires_at.isoformat()
            })
            return
        except Exception as e:
            print(f"WARNING [chaining.py]: Firestore write failed ({e}). Falling back to in-memory cache.")

    PAIRING_CODE_CACHE[norm_code] = {
        "user_email": user_email,
        "expires_at": expires_at
    }


def peek_pairing_code(code: str) -> str:
    """Validates a 6-digit pairing code and returns user_email without deleting it yet."""
    norm_code = (code or "").strip()
    if db:
        try:
            doc_ref = db.collection("pairing_codes").document(norm_code)
            snapshot = doc_ref.get()
            if not snapshot.exists:
                raise HTTPException(status_code=400, detail="Invalid or expired pairing code")
            data = snapshot.to_dict() or {}
            expires_str = data.get("expires_at")
            expires_at = (
                datetime.datetime.fromisoformat(expires_str)
                if isinstance(expires_str, str)
                else data.get("expires_at")
            )
            if expires_at and expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=datetime.timezone.utc)
            if expires_at and datetime.datetime.now(datetime.timezone.utc) > expires_at:
                doc_ref.delete()
                raise HTTPException(status_code=400, detail="Pairing code has expired")
            return data["user_email"]
        except HTTPException:
            raise
        except Exception as e:
            print(f"WARNING [chaining.py]: Firestore read failed ({e}). Checking in-memory cache.")

    code_data = PAIRING_CODE_CACHE.get(norm_code)
    if not code_data:
        raise HTTPException(status_code=400, detail="Invalid or expired pairing code")

    now = datetime.datetime.now(datetime.timezone.utc)
    exp = code_data["expires_at"]
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=datetime.timezone.utc)
    if now > exp:
        PAIRING_CODE_CACHE.pop(norm_code, None)
        raise HTTPException(status_code=400, detail="Pairing code has expired")

    return code_data["user_email"]


def delete_pairing_code(code: str) -> None:
    """Deletes a pairing code once it has been consumed to approve a device."""
    norm_code = (code or "").strip()
    if db:
        try:
            db.collection("pairing_codes").document(norm_code).delete()
        except Exception as e:
            print(f"WARNING [chaining.py]: Firestore delete failed ({e}).")
    PAIRING_CODE_CACHE.pop(norm_code, None)


def consume_pairing_code(code: str) -> str:
    norm_code = (code or "").strip()
    if db:
        try:
            doc_ref = db.collection("pairing_codes").document(norm_code)

            @firestore.transactional
            def atomic_consume(transaction, ref):
                snapshot = ref.get(transaction=transaction)
                if not snapshot.exists:
                    return None
                data = snapshot.to_dict()
                transaction.delete(ref)
                return data

            data = atomic_consume(db.transaction(), doc_ref)
            if not data:
                raise HTTPException(status_code=400, detail="Invalid or expired pairing code")

            expires_str = data.get("expires_at")
            expires_at = datetime.datetime.fromisoformat(expires_str) if isinstance(expires_str, str) else data.get("expires_at")
            if expires_at and expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=datetime.timezone.utc)
            if expires_at and datetime.datetime.now(datetime.timezone.utc) > expires_at:
                raise HTTPException(status_code=400, detail="Pairing code has expired")

            return data["user_email"]
        except HTTPException:
            raise
        except Exception as e:
            print(f"WARNING [chaining.py]: Firestore transaction failed ({e}). Checking in-memory cache.")

    user_email = peek_pairing_code(norm_code)
    PAIRING_CODE_CACHE.pop(norm_code, None)
    return user_email


@router.post("/generate", response_model=GenerateResponse)
def generate_pairing_code(user_email: str = Depends(get_current_user_email)):
    """Generates a 24-hour 6-digit pairing code if caller is permitted to chain trust.

    Note: Generating the code does NOT open a 24-hour users.signOut bypass window.
    Instead, the 15-minute Onboarding Grace Lease is triggered when the 6-digit code
    is redeemed on the secondary device via POST /api/chaining/verify.
    """
    config = config_service.get_tenant_config()

    # Master Admin Switch check
    if not config.enable_trust_chaining:
        raise HTTPException(
            status_code=403,
            detail="Device trust chaining is disabled by domain policy."
        )

    # Verify user chaining policy (Group overriding OU, hierarchical matching, negative deny lists)
    is_allowed = directory_service.get_user_chaining_policy(
        user_email=user_email,
        allowed_groups=config.chaining_allowed_groups,
        allowed_ous=config.chaining_allowed_ous,
        denied_groups=config.chaining_denied_groups,
        denied_ous=config.chaining_denied_ous,
        feature_enabled=config.enable_trust_chaining,
    )

    if not is_allowed:
        raise HTTPException(
            status_code=403,
            detail="Access denied: You are not authorized to perform device trust chaining."
        )

    # Generate 6-digit numeric code valid for 24 hours (86,400 seconds)
    code = f"{random.randint(100000, 999999)}"
    expires_at = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(
        seconds=PAIRING_CODE_TTL_SECONDS
    )

    store_pairing_code(code, user_email, expires_at)

    return GenerateResponse(
        pairing_code=code,
        expires_in_seconds=PAIRING_CODE_TTL_SECONDS,
    )


@router.post("/verify")
def verify_pairing_code(request: VerifyRequest, http_request: Request = None):
    """Verifies a 24-hour 6-digit pairing code on a secondary device.

    Works seamlessly even when Session Management (`users.signOut` Circuit Breaker) is active:
    1. Immediately starts the user's 15-minute Onboarding Grace Lease at redemption time
       so `users.signOut` will not interrupt the secondary device's login/registration.
    2. If `ev_header` or `raw_device_id` is explicitly provided, approves that device and
       consumes the single-use pairing code.
    3. If neither is provided (e.g., user enters the 6-digit code in the portal UI before
       signing in OR after their session was signed out by `users.signOut`), automatically
       checks Cloud Identity for the user's most recently synced unapproved (`PENDING_APPROVAL`
       or `BLOCKED`) BYOD device:
       - If found, immediately approves it in Cloud Identity, promotes it in `SessionGuard`,
         and consumes the pairing code.
       - If not yet registered in Cloud Identity (user entered the code *before* signing into
         Chrome/Google), returns `status: "LEASE_ACTIVATED"` so the user has a protected
         15-minute grace window to sign in and approve the device without getting signed out.
    """
    norm_code = (request.pairing_code or "").strip()
    config = config_service.get_tenant_config()
    grace_minutes = getattr(config, "session_watch_onboarding_grace_minutes", 15) or 15

    # Case 1: Explicit device identifier or Endpoint Verification header supplied
    if request.ev_header or request.raw_device_id:
        user_email = consume_pairing_code(norm_code)
        session_guard.grant_onboarding_lease(
            user_email=user_email,
            minutes=grace_minutes,
            reason="TRUST_CHAINING_PAIRING_CODE_REDEEMED",
        )

        device_user_name = None
        if request.ev_header:
            device_user_name = cloud_identity_service.parse_endpoint_verification_header(
                request.ev_header
            )

        if not device_user_name and request.raw_device_id:
            device_user_name = cloud_identity_service.lookup_device_user(
                user_email=user_email,
                raw_device_id=request.raw_device_id,
                customer_id=config.customer_id,
            )

        if not device_user_name:
            raise HTTPException(status_code=404, detail="Target device user could not be identified")

        try:
            operation = cloud_identity_service.approve_device_user(
                device_user_name=device_user_name,
                customer_id=config.customer_id,
            )
            session_guard.promote_approved_device(
                user_email=user_email,
                device_id=device_user_name,
                serial_number=request.raw_device_id or "",
            )
            return {
                "status": "SUCCESS",
                "mode": "DEVICE_APPROVED",
                "user_email": user_email,
                "device_user_name": device_user_name,
                "onboarding_grace_minutes": grace_minutes,
                "operation": operation,
                "message": f"Secondary device approved for {user_email} via 6-digit pairing code.",
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    # Case 2 & 3: Browser UI 6-digit code redemption (no raw_device_id / ev_header required)
    user_email = peek_pairing_code(norm_code)

    # Activate the 15-minute Onboarding Grace Lease NOW at redemption time
    session_guard.grant_onboarding_lease(
        user_email=user_email,
        minutes=grace_minutes,
        reason="TRUST_CHAINING_PAIRING_CODE_REDEEMED",
    )

    # Attempt to auto-discover an unapproved (PENDING_APPROVAL or BLOCKED) BYOD device for user_email
    discovered_devices = []
    try:
        discovered_devices, _ = crawl_devices_for_user(
            customer_id=config.customer_id,
            target_email=user_email,
            query_filter=f"email:{user_email}",
        )
        if not discovered_devices:
            discovered_devices, _ = crawl_devices_for_user(
                customer_id=config.customer_id,
                target_email=user_email,
                query_filter=None,
            )
    except Exception as crawl_err:
        print(f"WARNING [chaining.py]: Auto-discovery crawl during pairing code redemption failed: {crawl_err}")

    unapproved_byod = [
        d
        for d in discovered_devices
        if (d.owner_type or "").upper() != "COMPANY"
        and (d.approval_state or "").upper() in ("PENDING_APPROVAL", "BLOCKED")
    ]

    if unapproved_byod:
        caller_os = _infer_caller_os_family(http_request)

        def _candidate_sort_key(d):
            dtype = (d.device_type or "").upper()
            os_ver = (d.os_version or "").upper()
            os_match = 0
            if caller_os != "UNKNOWN" and caller_os != "CHROME_OS":
                if caller_os == "MAC_OS" and ("MAC" in dtype or "MAC" in os_ver):
                    os_match = 1
                elif caller_os == "WINDOWS" and ("WINDOWS" in dtype or "WINDOWS" in os_ver):
                    os_match = 1
                elif caller_os == "ANDROID" and ("ANDROID" in dtype or "ANDROID" in os_ver):
                    os_match = 1
                elif caller_os == "IOS" and ("IOS" in dtype or "IOS" in os_ver):
                    os_match = 1
                elif caller_os == "LINUX" and ("LINUX" in dtype or "LINUX" in os_ver):
                    os_match = 1
            is_pending = 1 if (d.approval_state or "").upper() == "PENDING_APPROVAL" else 0
            return (os_match, is_pending, sync_time_sort_key(d.last_sync_time))

        unapproved_byod.sort(key=_candidate_sort_key, reverse=True)
        target_dev = unapproved_byod[0]

        try:
            operation = cloud_identity_service.approve_device_user(
                device_user_name=target_dev.device_user_name,
                customer_id=config.customer_id,
            )
            session_guard.promote_approved_device(
                user_email=user_email,
                device_id=target_dev.device_user_name,
                serial_number=target_dev.serial_number if target_dev.serial_number != "N/A" else "",
            )
            delete_pairing_code(norm_code)
            return {
                "status": "SUCCESS",
                "mode": "DEVICE_APPROVED",
                "user_email": user_email,
                "device_user_name": target_dev.device_user_name,
                "device_model": target_dev.model,
                "onboarding_grace_minutes": grace_minutes,
                "operation": operation,
                "message": (
                    f"Approved {target_dev.model} ({target_dev.device_type}) for {user_email}! "
                    "If your session was previously signed out, sign back in with Google now—your device is permanently authorized."
                ),
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    # Case 3: User redeemed the 6-digit code BEFORE signing into Chrome/Google on the secondary device
    return {
        "status": "LEASE_ACTIVATED",
        "mode": "ONBOARDING_GRACE_STARTED",
        "user_email": user_email,
        "onboarding_grace_minutes": grace_minutes,
        "remaining_seconds": int(grace_minutes) * 60,
        "message": (
            f"Pairing code verified for {user_email}! A {grace_minutes}-minute Onboarding Grace Pass is now active "
            "(Session Management sign-out is paused). Sign in with Google on this device now to register and approve it."
        ),
    }

