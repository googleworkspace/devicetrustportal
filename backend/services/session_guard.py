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


# Known cloud hosting / proxy ASNs frequently weaponized for token theft or proxy pivots
KNOWN_HOSTING_ASNS: Set[str] = {
    "AS13335",   # Cloudflare
    "AS396356",  # Latitude.sh
    "AS16509",   # Amazon AWS
    "AS14618",   # Amazon AWS
    "AS14061",   # DigitalOcean
    "AS24940",   # Hetzner
    "AS63949",   # Linode / Akamai
    "AS8075",    # Microsoft Azure
    "AS20473",   # AS-CHOOPA / Vultr
    "AS16276",   # OVH
}


@dataclasses.dataclass
class TokenAuditEvent:
    """Normalized Admin SDK Reports API `token` activity event (OAuth grant/refresh)."""

    event_id: str
    user_email: str
    ip_address: str
    timestamp_epoch: float
    app_name: str = ""
    client_id: str = ""
    asn: Optional[str] = None
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
        enabled: bool = False,  # Off by default in Admin Config
    ) -> None:
        self.sqlite_path = sqlite_path
        self.attestation_ttl_sec = attestation_ttl_sec
        self.grace_window_sec = grace_window_sec
        self.signout_cooldown_sec = signout_cooldown_sec
        self.campus_egress_ips: Set[str] = campus_egress_ips or set()
        self.signout_callback = signout_callback
        self.enabled = enabled

        # O(1) RAM cache for 40,000+ devices (~4 MB memory footprint)
        self._approved_serials: Dict[str, DeviceRecord] = {}
        # Active attested sessions indexed by lowercase user_email
        self._active_attestations: Dict[str, List[SessionAttestation]] = {}
        # Recent signOut timestamps indexed by user_email to avoid API storms
        self._recent_signouts: Dict[str, float] = {}

        # Telemetry counters for scale/quota verification
        self.metrics: Dict[str, int] = {
            "inventory_devices_cached": 0,
            "attestations_received": 0,
            "login_events_evaluated": 0,
            "token_events_evaluated": 0,
            "allowed_attested": 0,
            "deferred_grace_window": 0,
            "signouts_executed": 0,
            "signouts_simulated": 0,
            "tokens_flagged_hosting_asn": 0,
            "tokens_flagged_ip_mismatch": 0,
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
        for dev in devices:
            serial_key = dev.serial_number.strip().upper()
            if serial_key and dev.status.upper() in ("ACTIVE", "APPROVED", "PROVISIONED"):
                self._approved_serials[serial_key] = dev
                count += 1
        self.metrics["inventory_devices_cached"] = len(self._approved_serials)
        return count

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
        dry_run: Optional[bool] = None,
        persist_all_allowed: bool = False,
    ) -> List[EnforcementAction]:
        """Evaluates a window of Admin SDK Reports `login` events and executes batched signOuts.

        Uses O(1) hash lookups for inventory/attestation matching and batches
        `users.signOut` calls (`BatchHttpRequest` up to 50 calls/request) to stay
        well within the 2,400 QPM Directory API quota.
        """
        now = now_epoch if now_epoch is not None else time.time()
        now_iso = datetime.datetime.fromtimestamp(now, tz=datetime.timezone.utc).isoformat()
        is_dry_run = dry_run if dry_run is not None else (not self.enabled)

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

            # 1. Check for matching verified device attestation in RAM
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

            # 2. If event just occurred (< grace_window_sec), defer so extension heartbeat can arrive
            if age_sec < self.grace_window_sec and not ev.is_suspicious:
                self.metrics["deferred_grace_window"] += 1
                continue

            # 3. Check signOut cooldown so we don't repeatedly call signOut for the same event
            last_signout = self._recent_signouts.get(email_key, 0.0)
            if (now - last_signout) < self.signout_cooldown_sec:
                continue

            # 4. Unattested / unapproved device session detected
            self._recent_signouts[email_key] = now
            if is_dry_run:
                self.metrics["signouts_simulated"] += 1
                action = EnforcementAction(
                    event_id=ev.event_id,
                    user_email=email_key,
                    ip_address=ev.ip_address,
                    decision="WOULD_REVOKE_DISABLED",
                    reason=(
                        "Login session has no matching district device attestation "
                        f"(IP {ev.ip_address}, login_type={ev.login_type}) [Session Guard Disabled/Dry-Run]."
                    ),
                    matched_serial=None,
                    detection_latency_sec=age_sec,
                    timestamp_iso=now_iso,
                )
                actions.append(action)
            else:
                action = EnforcementAction(
                    event_id=ev.event_id,
                    user_email=email_key,
                    ip_address=ev.ip_address,
                    decision="REVOKE_SIGN_OUT",
                    reason=(
                        "Login session has no matching district device attestation "
                        f"(IP {ev.ip_address}, login_type={ev.login_type})."
                    ),
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

    def evaluate_token_batch(
        self,
        events: List[TokenAuditEvent],
        now_epoch: Optional[float] = None,
        dry_run: Optional[bool] = None,
        persist_all_allowed: bool = False,
    ) -> List[EnforcementAction]:
        """Evaluates Admin SDK Reports `token` events for hosting ASN or foreign IP pivots."""
        now = now_epoch if now_epoch is not None else time.time()
        now_iso = datetime.datetime.fromtimestamp(now, tz=datetime.timezone.utc).isoformat()
        is_dry_run = dry_run if dry_run is not None else (not self.enabled)

        if events:
            pages = (len(events) + self.REPORTS_PAGE_SIZE - 1) // self.REPORTS_PAGE_SIZE
            self.metrics["reports_api_calls"] += pages

        actions: List[EnforcementAction] = []
        pending_signouts: List[EnforcementAction] = []

        for ev in events:
            self.metrics["token_events_evaluated"] += 1
            email_key = ev.user_email.strip().lower()
            age_sec = max(0.0, now - ev.timestamp_epoch)
            asn_norm = (ev.asn or "").strip().upper()

            # Pathway 3 Check A: Datacenter / Cloud Hosting ASN Sentinel
            if asn_norm in KNOWN_HOSTING_ASNS:
                self.metrics["tokens_flagged_hosting_asn"] += 1
                decision = "WOULD_REVOKE_HOSTING_ASN" if is_dry_run else "REVOKE_SIGN_OUT"
                action = EnforcementAction(
                    event_id=ev.event_id,
                    user_email=email_key,
                    ip_address=ev.ip_address,
                    decision=decision,
                    reason=f"Token activity from cloud hosting ASN '{asn_norm}' (IP {ev.ip_address}, app={ev.app_name}).",
                    matched_serial=None,
                    detection_latency_sec=age_sec,
                    timestamp_iso=now_iso,
                )
                actions.append(action)
                if is_dry_run:
                    self.metrics["signouts_simulated"] += 1
                else:
                    pending_signouts.append(action)
                continue

            # Pathway 3 Check B: Foreign IP Divergence From Active Attested Sessions
            active_att = self._active_attestations.get(email_key, [])
            cutoff = now - self.attestation_ttl_sec
            fresh_att = [a for a in active_att if a.attested_at_epoch >= cutoff]
            if fresh_att:
                known_ips = {a.ip_address for a in fresh_att}
                if self.campus_egress_ips:
                    known_ips.update(self.campus_egress_ips)
                if ev.ip_address not in known_ips:
                    self.metrics["tokens_flagged_ip_mismatch"] += 1
                    decision = "WOULD_REVOKE_TOKEN_IP_MISMATCH" if is_dry_run else "REVOKE_SIGN_OUT"
                    action = EnforcementAction(
                        event_id=ev.event_id,
                        user_email=email_key,
                        ip_address=ev.ip_address,
                        decision=decision,
                        reason=(
                            f"Token activity on foreign IP '{ev.ip_address}' diverging from "
                            f"attested session IPs {sorted(known_ips)} (app={ev.app_name})."
                        ),
                        matched_serial=None,
                        detection_latency_sec=age_sec,
                        timestamp_iso=now_iso,
                    )
                    actions.append(action)
                    if is_dry_run:
                        self.metrics["signouts_simulated"] += 1
                    else:
                        pending_signouts.append(action)
                    continue

            # Legitimate token activity
            if persist_all_allowed:
                actions.append(
                    EnforcementAction(
                        event_id=ev.event_id,
                        user_email=email_key,
                        ip_address=ev.ip_address,
                        decision="ALLOW_TOKEN_ACTIVITY",
                        reason=f"Token activity on verified network (app={ev.app_name})",
                        matched_serial=None,
                        detection_latency_sec=age_sec,
                        timestamp_iso=now_iso,
                    )
                )

        if pending_signouts:
            self._execute_batched_signouts(pending_signouts)

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
            "severity": "WARNING" if action.decision == "REVOKE_SIGN_OUT" else "INFO",
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
