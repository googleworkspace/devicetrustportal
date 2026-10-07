# `devicetrustportal` — Dual Enforcement Architecture: CAA-Free Session Management & Context-Aware Access (`poc/fundamentals-session-watch`)

## 1. Executive Summary
**Google Workspace for Education Fundamentals** domains do not have Context-Aware Access (CAA) to block unapproved devices inline at the Google login screen, while **Education Standard / Plus** domains use CAA to block Workspace apps (`Gmail`, `Drive`, `Docs`) at the edge—yet `accounts.google.com` itself still permits initial sign-in so Chrome Profile Reporting can register the hardware in Cloud Identity.

To solve both scenarios—either independently or simultaneously—the **Device Trust Gateway** implements a **Dual Enforcement Architecture** powered by:
1. **Chrome Enterprise Policy & Profile Reporting** (`CloudProfileReportingEnabled`, `UserSecuritySignalsReporting`, `callobklhcbilhphinckomhgkigmfocg` Endpoint Verification extension, and `chrome.enterprise.deviceAttributes` for ChromeOS).
2. **Cloud Identity Devices API (`cloudidentity.v1.devices` & `deviceUsers`)**: Real-time `lastSyncTime` telemetry (~1.7s latency on Chrome profile sign-in) and `PENDING_APPROVAL` / `BLOCKED` / `APPROVED` state management.
3. **Admin SDK Directory API (`admin.directory_v1`)**: Hardware inventory (`chromeosdevices.list`, strictly filtered by `recentUsers` per user on `#/`), the session circuit-breaker (`users.signOut`), and OAuth token revocation (`tokens.delete`).
4. **Admin SDK Reports API (`admin.reports_v1`)**: Domain-wide `login` audit streams (`activities.list` and `activities.watch`).

### Safe New-Install Default (`DISABLED` Standby Mode)
On any fresh installation (`./deploy.sh`, Docker Compose, or a newly created Secret Manager secret), **both** enforcement engines start **disabled by default**:
- `session_watch_enabled: false` (Session Management for Education Fundamentals)
- `caa_enforcement_enabled: false` (Context-Aware Access Integration for Education Standard & Plus)
- `enforcement_mode: "DISABLED"`

This guarantees zero unexpected lockouts during initial deployment. Once ready, the administrator navigates to `#/admin` to enable **Session Management**, **Context-Aware Access Integration**, or **Both** (`"BOTH"`).

---

## 2. How Quickly Can We Stop an Unapproved Device? (3-Layer Sub-10s Pipeline)

| Layer & Scenario | Enforcement Mechanism | Time to Terminate | What Happens |
| :--- | :--- | :--- | :--- |
| **Layer 1: User opens the Device Trust Portal or active browser tab on an unapproved / `BLOCKED` device** | **Inline Portal Verification & 8s Heartbeat** (`GET /api/session-watch/session-status` + JWT `iat` validation) | **< 0.5 seconds (Immediate) / ≤ 8s on open tabs** | On login/mount and every 8 seconds, the portal verifies the browser OS against Cloud Identity & the approved serial cache. If unapproved or `BLOCKED` (without an active 15m onboarding lease), the backend immediately calls `users.signOut` + OAuth grant revocation (`tokens.delete`) and returns `401 SESSION_REVOKED_UNAPPROVED_DEVICE`. Any JWT issued before `last_signout_epoch` is immediately rejected with `HTTP 401`. |
| **Layer 2: User signs into Chrome / Google on an unapproved BYOD Mac/PC (including re-login on an already-`BLOCKED` device)** | **Sub-Minute Cloud Identity `lastSyncTime` Sub-Polling** (`POST /api/session-watch/live-sweep` — 5x 10s sub-polls per minute) | **~2 – 10 seconds** | Chrome Profile Reporting updates `DeviceUser.lastSyncTime` in Cloud Identity within ~1.7s of sign-in—even when `managementState` remains `BLOCKED` from an earlier block or when Admin SDK `login` logs lag by 15–60m. Our 1-minute Cloud Scheduler job executes 5 sub-polls spaced 10s apart (`t=0s, 10s, 20s, 30s, 40s`), detects any `PENDING_APPROVAL` or `BLOCKED` BYOD `lastSyncTime` newer than the user's last sign-out, transitions pending/stale records to `BLOCKED`, and fires `users.signOut` + `tokens.delete`. |
| **Layer 3: External Attacker logs in from an unmanaged browser with *no* Chrome profile sync** | **Admin SDK `login` Audit Sweep + Circuit Breaker** (`activities.list(userKey='all', applicationName='login')` + `users.signOut`) | **15 – 60 seconds** (after Google audit log emission) | Sweeps domain login events using a 15s grace window, prioritizes unapproved device detection over shared NAT Wi-Fi Chromebook IPs, and revokes all Google session cookies and OAuth grants. |

---

## 3. Exact Google APIs & Scopes in Use (6 Required DWD Scopes)

| API & Method | OAuth Scope (Domain-Wide Delegation) | Role in Architecture | Official Quota Limit |
| :--- | :--- | :--- | :--- |
| **`cloudidentity.v1.devices.list` / `deviceUsers.list` / `approve` / `block`** | `https://www.googleapis.com/auth/cloud-identity.devices` | Queries personal BYOD & corp endpoints, detects ~1.7s `lastSyncTime` updates on `PENDING_APPROVAL` and `BLOCKED` BYOD devices, and approves/blocks bindings. | **600 – 1,200 queries / minute** |
| **`admin.directory_v1.chromeosdevices.list`** (`projection='FULL'`) | `https://www.googleapis.com/auth/admin.directory.device.chromeos.readonly` | Pre-warms the district's ChromeOS serial inventory into SQLite/RAM and filters `#/` Company-Owned Devices strictly to `email in recentUsers`. | **2,400 queries / minute (QPM)** |
| **`admin.directory_v1.users.get`** | `https://www.googleapis.com/auth/admin.directory.user.readonly` | Resolves user `orgUnitPath` and Super Admin status (`isAdmin`) for OU scoping and admin authorization. | **2,400 queries / minute (QPM)** |
| **`admin.directory_v1.members.hasMember`** | `https://www.googleapis.com/auth/admin.directory.group.member.readonly` | Evaluates Google Group membership scoping (`session_watch_target_groups`) and portal admin delegation. | **2,400 queries / minute (QPM)** |
| **`admin.reports_v1.activities.list` & `activities.watch`** | `https://www.googleapis.com/auth/admin.reports.audit.readonly` | Pulls domain `login` audit events in paginated batches of 1,000 events per call. | **240 queries / minute (QPM)** |
| **`admin.directory_v1.users.signOut` & `tokens.list` / `tokens.delete`** | `https://www.googleapis.com/auth/admin.directory.user.security` | **The Circuit Breaker**: Immediately invalidates all active Google login cookies (`users.signOut`) and revokes OAuth token grants (`tokens.delete`). | **2,400 queries / minute (QPM)** |

---

## 4. Key Edge Cases Solved in Production (`gwfe.org` Live Verification)

1. **Why CAA Blocks Gmail/Drive While `accounts.google.com` Stays Signed In**:
   - Context-Aware Access blocks Workspace applications at the app edge (`403 Access Denied`), but Google allows `accounts.google.com` authentication so Endpoint Verification / Chrome Profile Reporting can register the device. By enabling **Session Management** alongside **CAA** (`enforcement_mode: "BOTH"`), the gateway immediately revokes the underlying Google account session (`users.signOut`) and OAuth grants whenever an unapproved device signs in.
2. **Re-Logging In on an Already-`BLOCKED` Mac or Windows Device**:
   - When an unapproved Mac in `PENDING_APPROVAL` is caught and transitioned to `BLOCKED`, subsequent sign-ins on that Mac update `DeviceUser.lastSyncTime` in **~1.7 seconds**, but Cloud Identity keeps `managementState: "BLOCKED"` (it does not revert to `PENDING_APPROVAL`).
   - `SessionGuardService` persists `enforced_device_syncs (device_user_name, last_enforced_sync_epoch)` in SQLite, baselines historical `BLOCKED` syncs (>15m old) on cold start, and triggers immediate `users.signOut` + OAuth revocation whenever `lastSyncTime` advances on a `BLOCKED` or `PENDING_APPROVAL` BYOD device.
3. **Shared NAT Wi-Fi IP Protection (Chromebook + Unapproved Mac on Same Home/School Wi-Fi)**:
   - If a user has an approved Chromebook attested on `76.143.82.10` and signs into an unapproved Mac on the same Wi-Fi IP, `evaluate_login_batch()` checks `_unapproved_device_checker` first so the shared IP never masks the unapproved Mac. Furthermore, `record_extension_attestation()` validates the browser `User-Agent` OS family so a macOS/Windows browser can never spoof a `CHROMEOS` hardware serial.
4. **Explicit-Only 15-Minute Onboarding Grace Pass**:
   - Visiting `#/` (`GET /api/devices/my-devices`) never silently grants a grace window. A 15-minute `ONBOARDING_GRACE` lease is created **only** when the user explicitly clicks **`⏱️ + Add Personal Device (15m Grace Pass)`** (`POST /api/session-watch/onboarding-lease`) or generates a 6-digit Trust Chaining pairing code (`POST /api/chaining/generate`).

---

## 5. 40,000-Student District Scale & Quota Math (The 8:00 AM Morning Bell Surge)

In a district of **40,000 students + 5,000 staff**:
- **Daily Login Volume**: ~90,000 to 120,000 logins/day.
- **Peak 30-Minute Surge (7:45 AM – 8:15 AM)**: **~32,500 logins** (~1,080 logins/minute).

### How Our SQLite/RAM Cached Architecture Scales
1. **RAM & SQLite Footprint**: 43,000 device serial records in Python/SQLite (`/tmp/session_guard_cache.db`) = **~4.2 MB of RAM**.
2. **Zero Directory API Calls for Normal Logins**: All 32,500 morning logins are matched in **< 65 milliseconds** in RAM against `_approved_serials` and `_active_attestations`.
3. **Reports API Calls (`activities.list`)**: Paginated at `maxResults=1000` per page, staying well within the **240 QPM** quota limit.
4. **Directory API Calls (`users.signOut`)**: Executed *only* when an unapproved device or unattested login is detected, using `BatchHttpRequest` (up to 50 sign-outs per HTTP call) and thread-safe `threading.RLock()` wrappers around `googleapiclient`.

---

## 6. Live Testing Configuration (`gwfe.org`) vs. New Installation Defaults

| Parameter | New Install Default (`./deploy.sh` / `TenantConfig`) | Live `gwfe.org` Test Deployment (`devicetrustportal`) |
| :--- | :--- | :--- |
| **`session_watch_enabled`** | `false` (Admin must enable in `#/admin`) | **`true` (Active)** |
| **`caa_enforcement_enabled`** | `false` (Admin must enable in `#/admin`) | **`true` (Active)** |
| **`enforcement_mode`** | `"DISABLED"` | **`"BOTH"`** |
| **Cloud Scheduler (`session-watch-login-sweep`)** | `* * * * *` (Every 1 min; skips while disabled) | **`* * * * *` (Active: 5x 10s sub-polls per minute)** |
| **Portal UI (`#/`)** | Unified device list for all users + `⚙️ ENFORCEMENT STANDBY` badge for admins | Unified device list for all users + `🛡️ CAA + SESSION MANAGEMENT ACTIVE` badge |
| **Admin Portal (`#/admin`)** | Toggle switches, OU/Group scope, Inventory Sync, Live Sweep & Recent Events | Active with 20 cached approved serials & live enforcement feed |
| **Automated Test Coverage** | **75 backend `pytest` tests + 10 frontend `Vitest` tests** | Verified passing prior to Cloud Run deployment |

---

## 7. 3-Tier Logging Architecture & Monthly GCP Cost Estimate (1,000 to 40,000 Students)

Because `devicetrustportal` evaluates domain login and Cloud Identity sync events in batched sweeps rather than per-student background workers, **a 1,000-student district and a 40,000-student district have nearly identical GCP compute costs**. Monthly cost depends almost entirely on which deployment target and polling cadence the district selects:

### Summary by Deployment & Enforcement Mode

| Deployment & Enforcement Mode | Detection Speed | Cloud Run Active Compute | Estimated Monthly Cost (1,000 – 40,000 Students) |
| :--- | :--- | :--- | :--- |
| **1. On-Premise Docker** (`./deploy.sh --target 2`) | **~2 – 10s** | Runs on existing district VM (~60 MB RAM) | **$0.00 / mo** |
| **2. Cloud Run — CAA-Only Mode** (*Education Standard / Plus*, `session_watch_enabled: false`) | **Immediate (Edge 403)** | Scales to zero when idle (~5,000 vCPU-s/mo; **97% inside GCP Free Tier**) | **$0.00 – $0.20 / mo** |
| **3. Cloud Run — Free-Tier 1-Minute Session Sweep** (*Education Fundamentals*, `--sweep-cadence 1min` / `sub_poll_cycles: 1`) | **~30 – 60s** | ~2.5s/min (~110,000 vCPU-s/mo; **fits 100% inside 180k vCPU-s Free Tier**) | **$0.00 – $0.20 / mo** |
| **4. Cloud Run — 24/7 Sub-10s Rapid Polling** (*Education Fundamentals / `BOTH`*, default `--sweep-cadence sub10s` / `sub_poll_cycles: 5`) | **~2 – 10s** | ~43s/min (`5 × 10s` sub-polls ≈ 1.88M vCPU-s/mo at `1 vCPU, 512 MiB` / concurrency `80`) | **~$38.00 – $43.00 / mo** |

### Detailed GCP Line-Item Breakdown

| GCP Component | Monthly Usage (1,000 – 40,000 Students) | GCP Monthly Free Tier Allowance | Estimated Monthly Cost |
| :--- | :--- | :--- | :--- |
| **Google Workspace & Cloud Identity APIs** | Admin SDK Directory, Reports, & Cloud Identity Devices API calls | Included with Google Workspace for Education | **$0.00 / mo** |
| **Cloud Scheduler** | 1 – 2 cron jobs (`session-watch-login-sweep` & inventory cleanup) | First 3 jobs free per billing account | **$0.00 / mo** |
| **Cloud Logging (30-day structured JSON)** | ~0.02 – 0.6 GiB / month (`devicetrustportal.session_guard` & `[CLIENT_LOG]`) | First 50 GiB / month free | **$0.00 / mo** |
| **Firestore (`chaining.py`)** | 6-digit Trust Chaining pairing codes (< 5,000 reads/writes per month) | 50,000 reads & 20,000 writes / day free | **$0.00 / mo** |
| **Cloud Build & Container Storage** | ~200 MB image, ~2 build-minutes per deployment | 120 build-min/day & 0.5 GB storage free | **$0.00 – $0.03 / mo** |
| **Secret Manager (`config` & `dwd_key`)** | 2 active secret versions, ~50,000 – 60,000 reads/mo | 6 versions + 10,000 reads free ($0.03 per 10k after) | **$0.00 – $0.15 / mo** |
| **BigQuery (Optional 1-yr forensic sink)** | ~0.2 – 7 GiB / year | First 10 GiB storage & 1 TiB queries free | **$0.00 – $0.50 / mo** |
| **Cloud Run (`device-trust-gateway`)** | `1 vCPU, 512 MiB RAM`, `--max-instances=1` (keeps `--concurrency=80` for SQLite/RAM state) | First **180,000 vCPU-s** & **360,000 GiB-s** free / month | • **$0.00 / mo** *(CAA-Only or 1-Min Sweep)*<br>• **~$42.25 / mo** *(24/7 Sub-10s Polling)* |

> [!NOTE]
> **Why `1 vCPU` Instead of Fractional CPU (`< 1 vCPU`)?**
> Cloud Run enforces `--concurrency=1` whenever `--cpu < 1` is configured. Keeping the default `1 vCPU` preserves `--concurrency=80` on our single `--max-instances=1` container, ensuring student portal page loads never queue behind an active 43-second `live-sweep` request. Districts on Education Fundamentals that want **$0/mo** Cloud Run compute can select the **Free-Tier 1-Minute Sweep (`--sweep-cadence 1min`)** in `./deploy.sh`.
>
> **Strict IAP Edge Defense Note:** Leave **Strict IAP Edge Defense** at its default **`N`** during `./deploy.sh` (recommended for K-12 & Higher Ed so students can use 6-digit Trust Chaining from home). Enabling Strict IAP provisions a Global External Application Load Balancer forwarding rule, which incurs an ~$18/month base GCP networking fee.


