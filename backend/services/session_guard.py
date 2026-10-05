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

"""CAA-Free Session Watch & Circuit Breaker for Education Fundamentals.

Enforces approved / district-inventory devices without Context-Aware Access (CAA)
by combining:
1. O(1) in-memory + SQLite device inventory cache (synced from Admin SDK
   `chromeosdevices.list` and Cloud Identity `devices.list`).
2. Real-time Chrome extension session attestation (`POST /api/session-watch/attest`).
3. Windowed Admin SDK Reports `login` activity sweep (`activities.list`) or
   push webhook (`activities.watch`).
4. Automated session revocation via `admin.directory_v1.users.signOut` when an
   unattested or unapproved device establishes a Workspace session.
"""

from __future__ import annotations

import dataclasses
import datetime
import json
import sqlite3
import threading
import time
from typing import Any, Callable, Dict, Iterable, List, Optional, Set, Tuple


@dataclasses.dataclass(frozen=True)
class DeviceRecord:
    """Normalized device inventory record across ChromeOS and Cloud Identity."""

    device_id: str
    serial_number: str
    device_type: str  # "CHROMEOS", "CLOUD_IDENTITY_APPROVED", "BYOD_TOKEN"
    status: str  # "ACTIVE", "APPROVED", "DISABLED", "BLOCKED"
    assigned_user: Optional[str] = None
    org_unit_path: str = "/"


@dataclasses.dataclass
class SessionAttestation:
    """Real-time attestation heartbeat sent by the managed Chrome extension."""

    user_email: str
    serial_number: str
    ip_address: str
    attested_at_epoch: float
    user_agent: str = ""
    session_id: str = ""


@dataclasses.dataclass
class LoginAuditEvent:
    """Normalized Admin SDK Reports API `login` activity event."""

    event_id: str
    user_email: str
    ip_address: str
    timestamp_epoch: float
    login_type: str = "exchange"
    is_suspicious: bool = False


@dataclasses.dataclass
class EnforcementAction:
    """Audit record of a session evaluation and circuit-breaker decision."""

    event_id: str
    user_email: str
    ip_address: str
    decision: str  # "ALLOW_ATTESTED", "ALLOW_CAMPUS_GRACE", "REVOKE_SIGN_OUT", "SKIP_COOLDOWN"
    reason: str
    matched_serial: Optional[str]
    detection_latency_sec: float
    timestamp_iso: str


class SessionGuardService:
    """High-throughput session evaluator and `users.signOut` circuit breaker.

    Designed for 40,000+ student districts to operate well inside Google Admin SDK
    quotas (Reports API: 240 QPM; Directory API: 2,400 QPM).
    """

    # Official Google Admin SDK quotas (queries per minute)
    REPORTS_API_QPM_LIMIT = 240
    DIRECTORY_API_QPM_LIMIT = 2400
    REPORTS_PAGE_SIZE = 1000
    DIRECTORY_BATCH_SIZE = 50

    def __init__(
        self,
        sqlite_path: str = ":memory:",
        attestation_ttl_sec: int = 14400,  # 4 hours per school block
        grace_window_sec: int = 45,  # Wait up to 45s for extension heartbeat
        signout_cooldown_sec: int = 300,  # Prevent duplicate signOut loops
        campus_egress_ips: Optional[Set[str]] = None,
        signout_callback: Optional[Callable[[str], bool]] = None,
    ) -> None:
        self.sqlite_path = sqlite_path
        self.attestation_ttl_sec = attestation_ttl_sec
        self.grace_window_sec = grace_window_sec
        self.signout_cooldown_sec = signout_cooldown_sec
        self.campus_egress_ips: Set[str] = campus_egress_ips or set()
        self.signout_callback = signout_callback

        self._lock = threading.RLock()
        # O(1) RAM cache for 40,000+ devices (~4 MB memory footprint)
        self._approved_serials: Dict[str, DeviceRecord] = {}
        # Active attested sessions indexed by lowercase user_email
        self._active_attestations: Dict[str, List[SessionAttestation]] = {}
        # Temporary personal-device onboarding grace leases (email -> expires_at_epoch)
        self._onboarding_leases: Dict[str, float] = {}
        self._onboarding_lease_reasons: Dict[str, str] = {}
        # Active unapproved BYOD devices indexed by lowercase user_email -> {device_user_name -> metadata}
        self._unapproved_devices: Dict[str, Dict[str, Dict[str, Any]]] = {}
        # Recent signOut timestamps indexed by user_email to avoid API storms
        self._recent_signouts: Dict[str, float] = {}

        # Telemetry counters for scale/quota verification
        self.metrics: Dict[str, int] = {
            "inventory_devices_cached": 0,
            "attestations_received": 0,
            "onboarding_leases_granted": 0,
            "login_events_evaluated": 0,
            "allowed_attested": 0,
            "allowed_onboarding_grace": 0,
            "skipped_out_of_scope": 0,
            "deferred_grace_window": 0,
            "audit_would_signout": 0,
            "signouts_executed": 0,
            "reports_api_calls": 0,
            "directory_api_calls": 0,
            "directory_batch_http_calls": 0,
        }

        self._conn = sqlite3.connect(self.sqlite_path, check_same_thread=False)
        self._init_sqlite_schema()

    def _init_sqlite_schema(self) -> None:
        with self._conn:
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS session_enforcement_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id TEXT NOT NULL,
                    user_email TEXT NOT NULL,
                    ip_address TEXT NOT NULL,
                    decision TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    matched_serial TEXT,
                    detection_latency_sec REAL NOT NULL,
                    timestamp_iso TEXT NOT NULL
                )
                """
            )
            self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_user_email ON session_enforcement_log(user_email)"
            )
            self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_decision ON session_enforcement_log(decision)"
            )

    def load_device_inventory(self, devices: Iterable[DeviceRecord]) -> int:
        """Populates the O(1) in-memory inventory map from ChromeOS + Cloud Identity sync."""
        count = 0
        with self._lock:
            for dev in devices:
                serial_key = dev.serial_number.strip().upper()
                if serial_key and dev.status.upper() in ("ACTIVE", "APPROVED", "PROVISIONED"):
                    self._approved_serials[serial_key] = dev
                    count += 1
            self.metrics["inventory_devices_cached"] = len(self._approved_serials)
        return count

    def record_unapproved_device(
        self,
        user_email: str,
        device_user_name: str,
        model: str = "Personal Device",
        device_type: str = "BYOD",
        serial_number: str = "",
        approval_state: str = "PENDING_APPROVAL",
        last_sync_epoch: Optional[float] = None,
    ) -> None:
        """Tracks an unapproved (PENDING_APPROVAL or recently synced BLOCKED) BYOD device for a user
        so same-IP Chromebook attestations cannot mask an unapproved personal device login.
        """
        email_key = user_email.strip().lower()
        du_key = (device_user_name or serial_number or model).strip()
        if not email_key or not du_key:
            return
        with self._lock:
            user_map = self._unapproved_devices.setdefault(email_key, {})
            user_map[du_key] = {
                "device_user_name": du_key,
                "model": model or "Personal Device",
                "device_type": (device_type or "BYOD").upper(),
                "serial_number": (serial_number or "").strip().upper(),
                "approval_state": (approval_state or "PENDING_APPROVAL").upper(),
                "last_sync_epoch": last_sync_epoch if last_sync_epoch is not None else time.time(),
            }

    def clear_unapproved_devices_for_user(
        self, user_email: str, device_user_name: str = "", serial_number: str = ""
    ) -> None:
        """Clears unapproved device tracking when a user's personal device is approved."""
        email_key = user_email.strip().lower()
        clean_serial = (serial_number or "").strip().upper()
        with self._lock:
            user_map = self._unapproved_devices.get(email_key)
            if not user_map:
                return
            if not device_user_name and not clean_serial:
                self._unapproved_devices.pop(email_key, None)
                return
            keys_to_remove = [
                k
                for k, v in user_map.items()
                if k == device_user_name
                or (clean_serial and v.get("serial_number") == clean_serial)
            ]
            for k in keys_to_remove:
                user_map.pop(k, None)
            if not user_map:
                self._unapproved_devices.pop(email_key, None)

    def get_unapproved_devices(self, user_email: str) -> List[Dict[str, Any]]:
        """Returns tracked unapproved BYOD devices for a user."""
        email_key = user_email.strip().lower()
        with self._lock:
            user_map = self._unapproved_devices.get(email_key, {})
            return list(user_map.values())

    def promote_approved_device(
        self,
        device_id: str = "",
        serial_number: str = "",
        user_email: str = "",
        ip_address: Optional[str] = None,
        now_epoch: Optional[float] = None,
    ) -> str:
        """Immediately promotes a newly approved personal or corporate device into the O(1) cache
        and optionally attests the user's current browser session IP so they are never signed out.
        """
        now = now_epoch if now_epoch is not None else time.time()
        email_key = user_email.strip().lower()
        clean_serial = (serial_number or "").strip().upper()
        if not clean_serial or clean_serial in ("N/A", "NONE", "UNKNOWN"):
            clean_serial = (device_id or "").strip().upper()
        if not clean_serial:
            return ""

        rec = DeviceRecord(
            device_id=device_id or clean_serial,
            serial_number=clean_serial,
            device_type="CLOUD_IDENTITY_APPROVED",
            status="APPROVED",
            assigned_user=email_key,
        )
        with self._lock:
            self._approved_serials[clean_serial] = rec
            self.metrics["inventory_devices_cached"] = len(self._approved_serials)
            self._onboarding_leases.pop(email_key, None)
            self._onboarding_lease_reasons.pop(email_key, None)
        self.clear_unapproved_devices_for_user(
            user_email=email_key, device_user_name=device_id, serial_number=clean_serial
        )

        if ip_address and ip_address.strip():
            self.record_extension_attestation(
                user_email=email_key,
                serial_number=clean_serial,
                ip_address=ip_address.strip(),
                now_epoch=now,
                session_id="portal-instant-approval",
            )
        return clean_serial

    def grant_onboarding_lease(
        self,
        user_email: str,
        duration_sec: int = 900,
        now_epoch: Optional[float] = None,
        minutes: Optional[int] = None,
        reason: str = "PORTAL_ONBOARDING_PASS",
    ) -> float:
        """Grants a temporary onboarding grace lease (e.g., 15 minutes) so a user adding or
        approving a personal BYOD device is not signed out by the background sweep mid-flow.
        """
        now = now_epoch if now_epoch is not None else time.time()
        email_key = user_email.strip().lower()
        effective_sec = int(minutes) * 60 if minutes is not None and minutes > 0 else duration_sec
        expires_at = now + max(60, effective_sec)
        with self._lock:
            self._onboarding_leases[email_key] = expires_at
            self._onboarding_lease_reasons[email_key] = reason
            self.metrics["onboarding_leases_granted"] += 1
        return expires_at

    def has_active_onboarding_lease(
        self, user_email: str, now_epoch: Optional[float] = None
    ) -> Tuple[bool, float]:
        """Checks if the user has an active personal-device onboarding grace lease."""
        now = now_epoch if now_epoch is not None else time.time()
        email_key = user_email.strip().lower()
        with self._lock:
            expires_at = self._onboarding_leases.get(email_key, 0.0)
            if expires_at > now:
                return True, expires_at - now
            if email_key in self._onboarding_leases:
                del self._onboarding_leases[email_key]
                self._onboarding_lease_reasons.pop(email_key, None)
        return False, 0.0

    def get_active_onboarding_leases(
        self, now_epoch: Optional[float] = None
    ) -> List[Dict[str, Any]]:
        """Returns all active non-expired personal-device onboarding grace leases."""
        now = now_epoch if now_epoch is not None else time.time()
        active: List[Dict[str, Any]] = []
        expired_keys: List[str] = []
        with self._lock:
            for email_key, exp in self._onboarding_leases.items():
                if exp > now:
                    active.append(
                        {
                            "user_email": email_key,
                            "expires_at_iso": datetime.datetime.fromtimestamp(
                                exp, tz=datetime.timezone.utc
                            ).isoformat(),
                            "remaining_seconds": int(round(exp - now)),
                            "reason": self._onboarding_lease_reasons.get(
                                email_key, "PORTAL_ONBOARDING_PASS"
                            ),
                        }
                    )
                else:
                    expired_keys.append(email_key)
            for k in expired_keys:
                self._onboarding_leases.pop(k, None)
                self._onboarding_lease_reasons.pop(k, None)
        return active

    def record_extension_attestation(
        self,
        user_email: str,
        serial_number: str,
        ip_address: str,
        now_epoch: Optional[float] = None,
        user_agent: str = "",
        session_id: str = "",
    ) -> Tuple[bool, str]:
        """Registers a live heartbeat from the district Chrome extension.

        Returns (is_approved_device, status_reason).
        """
        now = now_epoch if now_epoch is not None else time.time()
        email_key = user_email.strip().lower()
        serial_key = serial_number.strip().upper()
        self.metrics["attestations_received"] += 1

        device = self._approved_serials.get(serial_key)
        if not device:
            return False, f"Serial '{serial_key}' is not in approved district inventory."

        # Prevent a non-ChromeOS browser (e.g. Mac/Windows/Mobile) from spoofing attestation using a ChromeOS serial
        ua_upper = (user_agent or "").upper()
        if (
            device.device_type.upper() == "CHROMEOS"
            and ua_upper
            and "CROS" not in ua_upper
            and any(os_token in ua_upper for os_token in ("MACINTOSH", "MAC OS X", "WINDOWS NT", "IPHONE", "IPAD", "ANDROID"))
        ):
            return (
                False,
                f"OS platform mismatch: cannot attest a non-ChromeOS browser session using ChromeOS serial '{serial_key}'.",
            )

        attestation = SessionAttestation(
            user_email=email_key,
            serial_number=serial_key,
            ip_address=ip_address.strip(),
            attested_at_epoch=now,
            user_agent=user_agent,
            session_id=session_id,
        )
        existing = self._active_attestations.get(email_key, [])
        # Prune expired attestations for this user
        cutoff = now - self.attestation_ttl_sec
        fresh = [a for a in existing if a.attested_at_epoch >= cutoff]
        fresh.append(attestation)
        self._active_attestations[email_key] = fresh
        return True, f"Verified {device.device_type} device '{serial_key}'."

    def _find_matching_attestation(
        self, user_email: str, ip_address: str, login_epoch: float
    ) -> Optional[SessionAttestation]:
        """Checks if the user has a valid device attestation matching the session."""
        email_key = user_email.strip().lower()
        attestations = self._active_attestations.get(email_key)
        if not attestations:
            return None

        cutoff = login_epoch - self.attestation_ttl_sec
        for att in reversed(attestations):
            if att.attested_at_epoch < cutoff:
                continue
            # The attestation must originate from the same IP address as the login event
            # (or both must originate from verified campus NAT egress IPs within 120s).
            same_ip = att.ip_address == ip_address
            both_campus_nat = (
                bool(self.campus_egress_ips)
                and att.ip_address in self.campus_egress_ips
                and ip_address in self.campus_egress_ips
                and abs(att.attested_at_epoch - login_epoch) <= 120
            )
            if same_ip or both_campus_nat:
                if att.serial_number in self._approved_serials:
                    return att
        return None

    def evaluate_login_batch(
        self,
        events: List[LoginAuditEvent],
        now_epoch: Optional[float] = None,
        persist_all_allowed: bool = False,
        scope_checker: Optional[Callable[[str], Tuple[bool, str]]] = None,
        unapproved_device_checker: Optional[Callable[[str, float], Optional[Dict[str, Any]]]] = None,
        dry_run: bool = False,
    ) -> List[EnforcementAction]:
        """Evaluates a window of Admin SDK Reports `login` events and executes batched signOuts.

        Uses O(1) hash lookups for inventory/attestation matching, respects explicit personal-device
        onboarding grace leases and OU/Group rollout scopes, detects unapproved BYOD devices even on
        shared Wi-Fi/NAT IPs, and batches `users.signOut` calls (`BatchHttpRequest` up to 50 calls/request)
        to stay well within the 2,400 QPM Directory API quota.
        """
        now = now_epoch if now_epoch is not None else time.time()
        now_iso = datetime.datetime.fromtimestamp(now, tz=datetime.timezone.utc).isoformat()

        # Count paginated Reports API calls required to fetch `len(events)`
        if events:
            pages = (len(events) + self.REPORTS_PAGE_SIZE - 1) // self.REPORTS_PAGE_SIZE
            self.metrics["reports_api_calls"] += pages

        actions: List[EnforcementAction] = []
        pending_signouts: List[EnforcementAction] = []

        for ev in events:
            self.metrics["login_events_evaluated"] += 1
            email_key = ev.user_email.strip().lower()
            age_sec = max(0.0, now - ev.timestamp_epoch)

            # 1. Check for explicit active personal-device onboarding grace lease first
            has_lease, rem_sec = self.has_active_onboarding_lease(email_key, now_epoch=now)
            if has_lease:
                self.metrics["allowed_onboarding_grace"] += 1
                if persist_all_allowed:
                    actions.append(
                        EnforcementAction(
                            event_id=ev.event_id,
                            user_email=email_key,
                            ip_address=ev.ip_address,
                            decision="ALLOW_ONBOARDING_GRACE",
                            reason=f"Active personal device onboarding grace lease ({int(rem_sec)}s remaining)",
                            matched_serial=None,
                            detection_latency_sec=age_sec,
                            timestamp_iso=now_iso,
                        )
                    )
                continue

            # 2. Check OU / Group rollout scope and Admin Safe-Harbor exemption
            if scope_checker is not None:
                in_scope, scope_reason = scope_checker(email_key)
                if not in_scope:
                    self.metrics["skipped_out_of_scope"] += 1
                    if persist_all_allowed:
                        actions.append(
                            EnforcementAction(
                                event_id=ev.event_id,
                                user_email=email_key,
                                ip_address=ev.ip_address,
                                decision="SKIP_OUT_OF_SCOPE",
                                reason=scope_reason,
                                matched_serial=None,
                                detection_latency_sec=age_sec,
                                timestamp_iso=now_iso,
                            )
                        )
                    continue

            # 3. Check if the user has an unapproved BYOD device (PENDING_APPROVAL or recently synced BLOCKED).
            # Even if the user also has an attested Chromebook on the same Wi-Fi IP, an unapproved BYOD device
            # without an active Onboarding Grace Lease must not be masked by same-IP attestation.
            unapproved_dev: Optional[Dict[str, Any]] = None
            tracked_unapproved = self.get_unapproved_devices(email_key)
            if tracked_unapproved:
                unapproved_dev = tracked_unapproved[0]
            if unapproved_device_checker is not None:
                checked_dev = unapproved_device_checker(email_key, ev.timestamp_epoch)
                if checked_dev is not None:
                    unapproved_dev = checked_dev

            if unapproved_dev is None:
                # 4. Check for matching verified device attestation in RAM
                matched_att = self._find_matching_attestation(
                    email_key, ev.ip_address, ev.timestamp_epoch
                )
                if matched_att is not None:
                    self.metrics["allowed_attested"] += 1
                    if persist_all_allowed:
                        actions.append(
                            EnforcementAction(
                                event_id=ev.event_id,
                                user_email=email_key,
                                ip_address=ev.ip_address,
                                decision="ALLOW_ATTESTED",
                                reason=f"Verified district device {matched_att.serial_number}",
                                matched_serial=matched_att.serial_number,
                                detection_latency_sec=age_sec,
                                timestamp_iso=now_iso,
                            )
                        )
                    continue

                # 5. If event just occurred (< grace_window_sec), defer so extension heartbeat can arrive
                if age_sec < self.grace_window_sec and not ev.is_suspicious:
                    self.metrics["deferred_grace_window"] += 1
                    continue

            # 6. Check signOut cooldown so we don't repeatedly call signOut for the same event
            last_signout = self._recent_signouts.get(email_key, 0.0)
            if (now - last_signout) < self.signout_cooldown_sec:
                continue

            unapproved_desc = (
                f"Unapproved BYOD device '{unapproved_dev.get('model', 'Personal Device')}' "
                f"({unapproved_dev.get('device_type', 'BYOD')}, state={unapproved_dev.get('approval_state', 'PENDING_APPROVAL')}) "
                f"detected on IP {ev.ip_address}"
                if unapproved_dev
                else f"Login session has no matching district device attestation (IP {ev.ip_address}, login_type={ev.login_type})"
            )

            # 7. Audit Dry-Run Mode vs. Active Circuit-Breaker Enforcement
            if dry_run:
                self.metrics["audit_would_signout"] += 1
                actions.append(
                    EnforcementAction(
                        event_id=ev.event_id,
                        user_email=email_key,
                        ip_address=ev.ip_address,
                        decision="AUDIT_WOULD_SIGN_OUT",
                        reason=f"[Audit Dry-Run] {unapproved_desc}; signOut skipped in dry-run mode.",
                        matched_serial=None,
                        detection_latency_sec=age_sec,
                        timestamp_iso=now_iso,
                    )
                )
                continue

            # 8. Unattested / unapproved device session detected -> Queue `users.signOut`
            self._recent_signouts[email_key] = now
            action = EnforcementAction(
                event_id=ev.event_id,
                user_email=email_key,
                ip_address=ev.ip_address,
                decision="REVOKE_SIGN_OUT",
                reason=f"{unapproved_desc}.",
                matched_serial=None,
                detection_latency_sec=age_sec,
                timestamp_iso=now_iso,
            )
            actions.append(action)
            pending_signouts.append(action)

        # Execute `admin.directory_v1.users.signOut` in batches
        if pending_signouts:
            self._execute_batched_signouts(pending_signouts)

        # Persist enforcement actions to SQLite / structured log
        if actions:
            self._persist_actions(actions)

        return actions

    def _execute_batched_signouts(self, signout_actions: List[EnforcementAction]) -> None:
        """Executes `users.signOut` calls and tracks Directory API quota consumption."""
        count = len(signout_actions)
        self.metrics["signouts_executed"] += count
        self.metrics["directory_api_calls"] += count
        self.metrics["directory_batch_http_calls"] += (
            count + self.DIRECTORY_BATCH_SIZE - 1
        ) // self.DIRECTORY_BATCH_SIZE

        if self.signout_callback is not None:
            for action in signout_actions:
                self.signout_callback(action.user_email)

    def _persist_actions(self, actions: List[EnforcementAction]) -> None:
        with self._conn:
            self._conn.executemany(
                """
                INSERT INTO session_enforcement_log (
                    event_id, user_email, ip_address, decision, reason,
                    matched_serial, detection_latency_sec, timestamp_iso
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        a.event_id,
                        a.user_email,
                        a.ip_address,
                        a.decision,
                        a.reason,
                        a.matched_serial,
                        a.detection_latency_sec,
                        a.timestamp_iso,
                    )
                    for a in actions
                ],
            )

    def format_cloud_logging_entry(self, action: EnforcementAction) -> str:
        """Formats an enforcement decision as a single-line Cloud Logging JSON payload."""
        payload = {
            "severity": "WARNING" if action.decision in ("REVOKE_SIGN_OUT", "AUDIT_WOULD_SIGN_OUT") else "INFO",
            "component": "devicetrustportal.session_guard",
            "event_id": action.event_id,
            "user_email": action.user_email,
            "ip_address": action.ip_address,
            "decision": action.decision,
            "reason": action.reason,
            "matched_serial": action.matched_serial,
            "detection_latency_sec": round(action.detection_latency_sec, 2),
            "timestamp": action.timestamp_iso,
        }
        return json.dumps(payload, sort_keys=True)

    def get_recent_actions(self, limit: int = 25) -> List[Dict[str, Any]]:
        """Returns the most recent session enforcement decisions from the SQLite audit log."""
        cur = self._conn.cursor()
        cur.execute(
            """
            SELECT event_id, user_email, ip_address, decision, reason,
                   matched_serial, detection_latency_sec, timestamp_iso
            FROM session_enforcement_log
            ORDER BY id DESC
            LIMIT ?
            """,
            (max(1, min(200, limit)),),
        )
        rows = cur.fetchall()
        return [
            {
                "event_id": r[0],
                "user_email": r[1],
                "ip_address": r[2],
                "decision": r[3],
                "reason": r[4],
                "matched_serial": r[5],
                "detection_latency_sec": round(float(r[6]), 2),
                "timestamp_iso": r[7],
            }
            for r in rows
        ]

    def get_active_attestations(self, now_epoch: Optional[float] = None) -> List[Dict[str, Any]]:
        """Returns active non-expired browser attestations in memory."""
        now = now_epoch if now_epoch is not None else time.time()
        cutoff = now - self.attestation_ttl_sec
        result: List[Dict[str, Any]] = []
        for email_key, att_list in self._active_attestations.items():
            for att in att_list:
                if att.attested_at_epoch >= cutoff:
                    result.append(
                        {
                            "user_email": att.user_email,
                            "serial_number": att.serial_number,
                            "ip_address": att.ip_address,
                            "attested_at_iso": datetime.datetime.fromtimestamp(
                                att.attested_at_epoch, tz=datetime.timezone.utc
                            ).isoformat(),
                            "session_id": att.session_id,
                        }
                    )
        return result
