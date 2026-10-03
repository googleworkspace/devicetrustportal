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

"""Unit & 40,000-Student District Scale Benchmark for CAA-Free Session Watch."""

from __future__ import annotations

import time
import unittest

from backend.services.session_guard import (
    DeviceRecord,
    LoginAuditEvent,
    SessionGuardService,
)


class SessionGuardScaleTest(unittest.TestCase):
    """Verifies accuracy, speed, and Google API quota headroom at 40,000-student scale."""

    def test_40k_student_morning_bell_surge_and_attacker_containment(self) -> None:
        revoked_users = []
        guard = SessionGuardService(
            sqlite_path=":memory:",
            attestation_ttl_sec=14400,
            grace_window_sec=45,
            signout_cooldown_sec=300,
            signout_callback=lambda email: revoked_users.append(email) or True,
        )

        # 1. Load 40,000 district Chromebooks + 3,000 approved staff devices into RAM cache
        t0 = time.perf_counter()
        inventory = [
            DeviceRecord(
                device_id=f"dev-{i}",
                serial_number=f"CROS-SN-{i:06d}",
                device_type="CHROMEOS",
                status="ACTIVE",
                assigned_user=f"student{i}@district.edu",
                org_unit_path="/Students",
            )
            for i in range(40000)
        ] + [
            DeviceRecord(
                device_id=f"staff-dev-{j}",
                serial_number=f"BYOD-TOKEN-{j:05d}",
                device_type="CLOUD_IDENTITY_APPROVED",
                status="APPROVED",
                assigned_user=f"teacher{j}@district.edu",
                org_unit_path="/Staff",
            )
            for j in range(3000)
        ]
        cached_count = guard.load_device_inventory(inventory)
        inventory_load_ms = (time.perf_counter() - t0) * 1000.0
        self.assertEqual(cached_count, 43000)

        # 2. Simulate 30,000 students + 2,500 teachers logging in during the 8:00 AM morning bell
        base_epoch = 1791036000.0  # 2026-10-03T13:00:00Z
        t1 = time.perf_counter()
        login_events = []

        for i in range(30000):
            email = f"student{i}@district.edu"
            serial = f"CROS-SN-{i:06d}"
            campus_ip = f"10.42.{(i // 256) % 256}.{i % 256}"
            # Extension sends attestation within 1-3 seconds of login
            guard.record_extension_attestation(
                user_email=email,
                serial_number=serial,
                ip_address=campus_ip,
                now_epoch=base_epoch + 2.0,
            )
            login_events.append(
                LoginAuditEvent(
                    event_id=f"evt-stu-{i}",
                    user_email=email,
                    ip_address=campus_ip,
                    timestamp_epoch=base_epoch,
                )
            )

        for j in range(2500):
            email = f"teacher{j}@district.edu"
            serial = f"BYOD-TOKEN-{j:05d}"
            campus_ip = f"10.10.{(j // 256) % 256}.{j % 256}"
            guard.record_extension_attestation(
                user_email=email,
                serial_number=serial,
                ip_address=campus_ip,
                now_epoch=base_epoch + 1.0,
            )
            login_events.append(
                LoginAuditEvent(
                    event_id=f"evt-tch-{j}",
                    user_email=email,
                    ip_address=campus_ip,
                    timestamp_epoch=base_epoch,
                )
            )

        # 3. Inject 15 external credential-harvesting phishing logins from unmanaged devices/IPs
        #    (e.g., compromised student/teacher accounts logged in from external attacker IPs)
        expected_revoked = set()
        for k in range(15):
            compromised_email = f"teacher{k}@district.edu" if k < 5 else f"student{k}@district.edu"
            expected_revoked.add(compromised_email)
            login_events.append(
                LoginAuditEvent(
                    event_id=f"evt-phish-attacker-{k}",
                    user_email=compromised_email,
                    ip_address=f"198.51.100.{10 + k}",  # External attacker IP, no extension attestation
                    timestamp_epoch=base_epoch + 5.0,
                    login_type="exchange",
                    is_suspicious=True,
                )
            )

        # 4. Run the 5-minute window sweep at base_epoch + 120s
        t_sweep_start = time.perf_counter()
        actions = guard.evaluate_login_batch(login_events, now_epoch=base_epoch + 120.0)
        sweep_ms = (time.perf_counter() - t_sweep_start) * 1000.0
        total_sim_ms = (time.perf_counter() - t1) * 1000.0

        # Assertions:
        # - All 32,500 legitimate logins are allowed with 0 false-positive signOuts
        self.assertEqual(guard.metrics["allowed_attested"], 32500)
        # - All 15 external phishing attacker sessions are caught and revoked via users.signOut
        self.assertEqual(guard.metrics["signouts_executed"], 15)
        self.assertEqual(set(revoked_users), expected_revoked)
        self.assertEqual(len(actions), 15)

        # - Verify Google API Quota Headroom:
        #   32,515 login events / 1000 per page = 33 Reports API calls (Limit: 240 QPM -> 13.7% of 1-minute quota!)
        self.assertEqual(guard.metrics["reports_api_calls"], 33)
        self.assertLess(guard.metrics["reports_api_calls"], guard.REPORTS_API_QPM_LIMIT)
        #   15 signOut calls = 15 Directory API units in 1 BatchHttpRequest (Limit: 2,400 QPM -> 0.6% of quota!)
        self.assertEqual(guard.metrics["directory_api_calls"], 15)
        self.assertEqual(guard.metrics["directory_batch_http_calls"], 1)

        print(
            "\n=== 40,000-Student District Morning Bell Scale Benchmark ==="
            f"\n- Cached Inventory Devices : {cached_count:,} (loaded in {inventory_load_ms:.1f} ms)"
            f"\n- Morning Surge Logins     : {len(login_events):,} (32,500 legitimate + 15 attacker sessions)"
            f"\n- Sweep Evaluation Time    : {sweep_ms:.1f} ms (Total sim: {total_sim_ms:.1f} ms)"
            f"\n- Legitimate Allowed       : {guard.metrics['allowed_attested']:,} (0 false positives)"
            f"\n- Attacker Sessions Revoked: {guard.metrics['signouts_executed']} via users.signOut"
            f"\n- Reports API Calls Used   : {guard.metrics['reports_api_calls']} / {guard.REPORTS_API_QPM_LIMIT} QPM limit"
            f"\n- Directory API Calls Used : {guard.metrics['directory_api_calls']} / {guard.DIRECTORY_API_QPM_LIMIT} QPM limit "
            f"({guard.metrics['directory_batch_http_calls']} BatchHttpRequest)"
        )


if __name__ == "__main__":
    unittest.main()
