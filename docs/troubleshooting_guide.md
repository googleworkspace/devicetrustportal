# 🛠️ Device Trust Gateway: Troubleshooting & AI Diagnostics Guide

This guide compiles real-world troubleshooting playbooks, root-cause explanations, and verification commands for the **Device Trust Gateway & Approval Portal**. It also includes ready-to-use workflows for **troubleshooting with Gemini** using server telemetry, Chrome policy exports, and Google Workspace audit logs.

---

## 📋 Table of Contents
1. [🤖 Troubleshooting with Gemini (AI-Assisted Diagnostics)](#-1-troubleshooting-with-gemini-ai-assisted-diagnostics)
2. [🔍 End-to-End Client & Server Log Telemetry](#-2-end-to-end-client--server-log-telemetry)
3. [💻 Personal Windows & macOS BYOD Devices Not Appearing or Stuck](#-3-personal-windows--macos-byod-devices-not-appearing-or-stuck)
4. [⚠️ Understanding `chrome://policy` Warnings & Missing Policies](#-4-understanding-chromepolicy-warnings--missing-policies)
5. [🪟 Windows Git Bash (`MINGW64`) Path Conversion & `gcloud.py` Errors](#-5-windows-git-bash-mingw64-path-conversion--gcloudpy-errors)
6. [🔐 Domain-Wide Delegation (DWD) & Cloud Identity API Errors](#-6-domain-wide-delegation-dwd--cloud-identity-api-errors)
7. [🚫 Google Sign-In OAuth Errors (`redirect_uri_mismatch` / `App is blocked`)](#-7-google-sign-in-oauth-errors-redirect_uri_mismatch--app-is-blocked)
8. [🏢 Context-Aware Access (CAA) Lockouts & Policy Assignment Pitfalls](#-8-context-aware-access-caa-lockouts--policy-assignment-pitfalls)
9. [📱 Unexpected Devices or Auto-Approved Desktop BYOD Devices](#-9-unexpected-devices-or-auto-approved-desktop-byod-devices)
10. [🔄 Updating an Existing Deployment to the Latest Release](#-10-updating-an-existing-deployment-to-the-latest-release)

---

## 🤖 1. Troubleshooting with Gemini (AI-Assisted Diagnostics)

Because the Device Trust Gateway spans **Google Cloud Run**, **Cloud Identity Devices API**, **Google Workspace Admin Console policies**, and **Chrome Browser Profile Reporting**, the fastest way to isolate any issue is to collect your diagnostic bundle and ask **Gemini** (in Google Cloud Console, Gemini CLI / Code Assist, or Google Workspace) to analyze the logs alongside this repository.

### Step A: Collect Your 3-Part Diagnostic Bundle

#### 1. Export Cloud Run Server + Client Telemetry Logs (`cloud_run_logs.json`)
The portal automatically forwards browser-side events (`[CLIENT_LOG]`) to the Cloud Run server logs alongside backend API traces (`[devices.py]`, `[cloud_identity.py]`, `[config_service.py]`). Run this command in your terminal to export the last 150 log entries:

```bash
gcloud logging read \
  'resource.type="cloud_run_revision" AND resource.labels.service_name="device-trust-gateway"' \
  --project=YOUR_GCP_PROJECT_ID \
  --limit=150 \
  --format=json > cloud_run_logs.json
```

#### 2. Export Chrome Policies from the Test Device (`policies.json`)
On the personal Windows, macOS, or ChromeOS device you are testing:
1. Open Chrome and sign into the Chrome profile with your managed Google Workspace account (`user@yourdomain.com`).
2. Navigate to **`chrome://policy`**.
3. Click **Reload policies** in the top-left corner.
4. Click **Export to JSON** (or **Save as JSON**) and save the file as `policies.json`.

#### 3. (Optional) Export Google Admin Console Device Audit Logs or Run the CLI Inspector
* **From Admin Console:** Go to **Reporting > Audit and investigation > Device log events**, filter by your test user, and click **Export** (CSV).
* **From Terminal:** Run the included domain diagnostic script to inspect raw Cloud Identity and Directory API records:
  ```bash
  WORKSPACE_ADMIN_EMAIL=admin@yourdomain.com \
  GOOGLE_APPLICATION_CREDENTIALS=dwd_key.json \
  ./backend/venv/bin/python backend/scripts/pull_domain_device_logs.py
  ```

---

### Step B: Copy-Paste Prompt for Gemini

Attach `cloud_run_logs.json` and `policies.json` (plus any Admin Console screenshots or CSV exports) to your Gemini chat and paste the following prompt:

```markdown
I am troubleshooting our deployment of the Google Workspace Device Trust Gateway (`devicetrustportal`) on Cloud Run.

Here is my environment context:
- Google Workspace Domain: <YOUR_DOMAIN>
- GCP Project ID: <YOUR_GCP_PROJECT_ID>
- Test User Email: <TEST_USER_EMAIL>
- Test Device OS & Browser: <e.g., Windows 11 / macOS Sequoia, Chrome signed into managed profile>
- Symptom we are seeing: <Describe what happens in the portal or when opening Gmail/Drive>

I have attached:
1. `cloud_run_logs.json` (Cloud Run stdout/stderr including `[CLIENT_LOG]` frontend telemetry and `[devices.py]` Cloud Identity lookups)
2. `policies.json` (exported from `chrome://policy` on the test device)

Please check:
1. Are the Domain-Wide Delegation credentials (`/secrets/dwd_key.json` and `WORKSPACE_ADMIN_EMAIL`) initializing cleanly in `cloud_run_logs.json`, or are there `403 PERMISSION_DENIED` / `DefaultCredentialsError` failures?
2. What does `[CLIENT_LOG]` show for `OAUTH_SIGNIN_SUCCESS` and `LOAD_DEVICES_*`, and how many devices did `crawl_devices_for_user` scan in Cloud Identity?
3. In `policies.json`, are `CloudProfileReportingEnabled`, `UserSecuritySignalsReporting`, `UserSecurityAuthenticatedReporting`, and `EnterpriseHardwarePlatformAPIEnabled` active under the signed-in Chrome user profile, and is the Endpoint Verification extension (`callobklhcbilhphinckomhgkigmfocg`) force-installed?
4. What exact Google Admin Console setting or `gcloud` command should I run to fix this?
```

---

## 🔍 2. End-to-End Client & Server Log Telemetry

To make debugging effortless without needing browser DevTools on student or employee machines, the frontend automatically sends structured telemetry to `POST /api/client-logs`, which prints to Cloud Run `stdout` under the `[CLIENT_LOG]` prefix.

| Log Event Tag | Meaning & What to Check |
| :--- | :--- |
| `OAUTH_CLIENT_ID_MISSING` | The frontend did not receive a `google_client_id` from `/api/config/public` or `REACT_APP_GOOGLE_CLIENT_ID`. Complete Phase 2/3 of `./deploy.sh` or set the Client ID in `#/admin`. |
| `OAUTH_SIGNIN_SUCCESS` | Confirms the user authenticated via Google Sign-In and logs their `email` and hosted domain (`hd`). |
| `LOAD_DEVICES_START` | The browser requested `GET /api/devices/my-devices`. Look immediately below this line for `INFO [devices.py]: Executing Cloud Identity lookup...`. |
| `LOAD_DEVICES_EMPTY` | The backend returned `0` devices for the signed-in user. Check whether the user's device has registered in Cloud Identity (`Admin Console > Devices > Mobile & endpoints > Devices`). |
| `LOAD_DEVICES_SUCCESS` | Logs the exact count, `device_user_name`, `model`, `approval_state`, and `owner_type` rendered in the UI. |
| `LOAD_DEVICES_ERROR` | The backend returned an HTTP error (such as `500` due to missing DWD scopes or invalid `WORKSPACE_ADMIN_EMAIL`). |
| `APPROVE_DEVICE_SUCCESS` / `ERROR` | Logs the outcome of clicking **✓ Approve** on a personal BYOD device (`devices.deviceUsers.approve`). |
| `REVOKE_DEVICE_SUCCESS` / `ERROR` | Logs the outcome of revoking device access (`devices.deviceUsers.block`). |

---

## 💻 3. Personal Windows & macOS BYOD Devices Not Appearing or Stuck

### Symptom
* A user signs into Chrome on a personal Windows or macOS laptop, installs the Endpoint Verification extension, and logs into the Device Trust Portal, but the portal says **"No Registered Hardware Assets Discovered"**—or `chrome://policy` shows:
  * `CloudReportingEnabled: Ignored because machine is not enrolled`.

### Root Cause
Personal BYOD computers are **not** enrolled in machine-level Chrome Browser Cloud Management (CBCM). `CloudReportingEnabled` is a machine-level CBCM policy and is always ignored on unenrolled BYOD laptops.

Instead, personal Windows and macOS laptops register in Cloud Identity as `PENDING_APPROVAL` (`ClientType.EVERY_DEVICE_SECURE`) when **Managed Chrome Profile Reporting** and **Chrome Signals Sharing** are enabled for the user's Organizational Unit!

### Resolution
1. **Do NOT enroll personal BYOD machines in CBCM.**
2. Open **[Google Admin Console > Devices > Chrome > Settings > Users & browsers](https://admin.google.com/ac/chrome/settings/user)**, select your target OU, and configure these **5 user/browser settings**:
   * **Profile reporting** (`CloudProfileReportingEnabled`) → **Enable profile reporting**
   * **Chrome signals sharing** (`UserSecuritySignalsReporting` & `UserSecurityAuthenticatedReporting`) → **Enable signals sharing**
   * **Enterprise Hardware Platform API** (`EnterpriseHardwarePlatformAPIEnabled`) → **Allow extensions to see hardware platform information**
   * **Browser sign-in** → **Force users to sign in to use the browser**
   * **Managed accounts sign-in restriction** (`ManagedAccountsSigninRestriction`) → **Block users from signing into secondary accounts** (`primary_account_strict`)
3. Open **[Devices > Mobile & endpoints > Settings > Universal > Data access](https://admin.google.com/ac/appsettings/724141353720?vid=EMM_UNIVERSAL_SETTINGS_VIEW)** → **Device signals** and enable:
   * **Collect device signals from Chrome browser**
   * **Collect device signals using endpoint verification**
4. Open **[Devices > Mobile & endpoints > Settings > Universal > Security](https://admin.google.com/ac/appsettings/724141353720?vid=EMM_UNIVERSAL_SETTINGS_VIEW)** → **Device approvals** and enable:
   * **Require admin approval**
5. On the personal laptop, open `chrome://policy`, click **Reload policies**, click the Endpoint Verification extension icon (`callobklhcbilhphinckomhgkigmfocg`) → **Sync now**, and click **Refresh Devices** in the portal.

---

## ⚠️ 4. Understanding `chrome://policy` Warnings & Missing Policies

When inspecting `chrome://policy` on a personal Windows or macOS laptop, two common observations often look like errors but are actually expected Chromium behavior:

### Observation A: "Conflict" or "Ignored because the policy is not set at the machine scope"
* **Policies affected:** `CloudPolicyOverridesPlatformPolicy`, `CloudUserPolicyOverridesCloudMachinePolicy`.
* **Why it happens:** In Chromium's policy engine, Policy Precedence metapolicies are **machine-scoped** (`per_profile: false`). For security reasons, a signed-in user profile is not allowed to alter machine-wide policy precedence on an unenrolled computer, so Chrome displays *"Ignored because the policy is not set at the machine scope"*.
* **What to do:** This notice is **completely benign** and does not block device registration. You can return **Policy precedence** in the Admin Console back to its default setting; on unenrolled BYOD laptops with no local Windows Group Policy (GPO) or MDM profile, `Cloud user` policies already take effect automatically.

### Observation B: "Allow access to keys" (`KeyPermissions`) and "Allow enterprise challenge" (`AttestationExtensionAllowlist`) Do Not Appear in `chrome://policy` on Windows/Mac
* **Why it happens:** Even when you turn ON **Allow access to keys** and **Allow enterprise challenge** under `Devices > Chrome > Apps & extensions > Users & browsers > Endpoint Verification`, Chromium's policy engine defines both policies as **ChromeOS-only** (`supported_on: ["chrome_os"]`) because they control ChromeOS Verified Access hardware TPM attestation.
* **What to do:** Nothing—this is expected. On Windows and macOS, check `chrome://policy` for these policies instead:
  * `CloudProfileReportingEnabled`: `true`
  * `UserSecuritySignalsReporting`: `true`
  * `UserSecurityAuthenticatedReporting`: `true`
  * `EnterpriseHardwarePlatformAPIEnabled`: `true`
  * `ExtensionInstallForcelist`: contains `callobklhcbilhphinckomhgkigmfocg`

---

## 🪟 5. Windows Git Bash (`MINGW64`) Path Conversion & `gcloud.py` Errors

When deploying from a Windows machine using **Git Bash (`MINGW64`)**, MSYS2 automatically translates POSIX-style arguments (starting with `/`) into Windows filesystem paths (`C:/Program Files/Git/...`). This can cause two distinct issues if not handled properly:

### Issue A: `DefaultCredentialsError: File C:/Program Files/Git/secrets/dwd_key.json was not found`
* **Cause:** Git Bash translated `--set-env-vars="GOOGLE_APPLICATION_CREDENTIALS=/secrets/dwd_key.json"` into `C:/Program Files/Git/secrets/dwd_key.json` before passing it to Cloud Run.
* **How it is prevented automatically:**
  1. `./deploy.sh` sets `MSYS2_ARG_CONV_EXCL="--set-secrets;--set-env-vars;--update-env-vars;GOOGLE_APPLICATION_CREDENTIALS"` so container paths are never converted.
  2. The backend's `resolve_dwd_key_path()` helper automatically detects mangled Windows paths inside the Linux container and repairs `GOOGLE_APPLICATION_CREDENTIALS` to `/secrets/dwd_key.json` at startup.

### Issue B: `python.exe: can't open file 'C:\c\Program Files (x86)\Google\Cloud SDK\...\gcloud.py': [Errno 2] No such file or directory`
* **Cause:** Running `MSYS_NO_PATHCONV=1` or `MSYS2_ARG_CONV_EXCL="*"` globally in Git Bash disables path translation for *every* argument—including `gcloud`'s own bash wrapper script when it passes `/c/Program Files (x86)/Google/Cloud SDK/.../gcloud.py` to native Windows `python.exe`.
* **Fix:** **Never set `MSYS_NO_PATHCONV=1` or `MSYS2_ARG_CONV_EXCL="*"` globally** when running `gcloud` on Windows Git Bash. Instead, run:
  ```bash
  unset MSYS_NO_PATHCONV
  MSYS2_ARG_CONV_EXCL="--set-secrets;--set-env-vars;--update-env-vars;GOOGLE_APPLICATION_CREDENTIALS" \
    gcloud run services update device-trust-gateway \
    --region=us-central1 \
    --project=YOUR_PROJECT_ID \
    --update-env-vars="GOOGLE_APPLICATION_CREDENTIALS=/secrets/dwd_key.json"
  ```

---

## 🔐 6. Domain-Wide Delegation (DWD) & Cloud Identity API Errors

### Symptom
The portal displays a red alert banner:
* `Failed to load approved devices: {"detail":"Cloud Identity API service is not initialized..."}`
* `Failed to load approved devices: {"detail":"Cloud Identity API device lookup failed (HttpError 403 ... Request had insufficient authentication scopes / unauthorized_client)..."}`

### Resolution Checklist
1. **Verify the 6 Exact OAuth Scopes in Google Workspace Admin Console:**
   Open [Security > Access and data control > API controls > Domain-wide Delegation](https://admin.google.com/ac/owl/domainwidedelegation) and confirm your Service Account's **Numeric Client ID** has all six comma-separated scopes:
   ```text
   https://www.googleapis.com/auth/cloud-identity.devices,https://www.googleapis.com/auth/admin.directory.user.readonly,https://www.googleapis.com/auth/admin.directory.group.member.readonly,https://www.googleapis.com/auth/admin.directory.device.chromeos.readonly,https://www.googleapis.com/auth/admin.reports.audit.readonly,https://www.googleapis.com/auth/admin.directory.user.security
   ```
2. **Verify `WORKSPACE_ADMIN_EMAIL` Is an Active Super Administrator:**
   Domain-Wide Delegation requires impersonating a Google Workspace user who holds privileges to query Cloud Identity Devices and Directory APIs. Check the configured email on Cloud Run:
   ```bash
   gcloud run services describe device-trust-gateway \
     --region=us-central1 \
     --project=YOUR_PROJECT_ID \
     --format="yaml(spec.template.spec.containers[0].env)"
   ```
3. **Verify Required Google Cloud APIs Are Enabled:**
   ```bash
   gcloud services enable \
     cloudidentity.googleapis.com \
     admin.googleapis.com \
     secretmanager.googleapis.com \
     run.googleapis.com \
     --project=YOUR_PROJECT_ID
   ```

---

## 🚫 7. Google Sign-In OAuth Errors (`redirect_uri_mismatch` / `App is blocked`)

### Error A: `Error 400: origin_mismatch` or `redirect_uri_mismatch`
* **Cause:** Your live Cloud Run HTTPS URL (`https://device-trust-gateway-xyz-uc.a.run.app`) is missing from your OAuth 2.0 Web Client ID's **Authorized JavaScript origins**.
* **Fix:**
  1. Open [Google Cloud Console > APIs & Services > Credentials](https://console.cloud.google.com/apis/credentials).
  2. Click your Web Application OAuth 2.0 Client ID.
  3. Add your exact Cloud Run URL (with `https://` and no trailing slash) under **Authorized JavaScript origins** and **Authorized redirect URIs**, then click **Save**.

### Error B: `Access blocked: Your institution's admin needs to review this app`
* **Cause:** Student or restricted Organizational Units often block unreviewed OAuth Client IDs by default.
* **Fix:**
  1. Open [Google Admin Console > Security > Access and data control > API controls > App access control](https://admin.google.com/ac/owl/appaccess).
  2. Click **Add app > OAuth app name or Client ID**, paste your OAuth 2.0 Web Client ID, and set access to **Trusted** for your target OUs.

---

## 🏢 8. Context-Aware Access (CAA) Lockouts & Policy Assignment Pitfalls

### Symptom
* After assigning the `Approved Devices Only` Context-Aware Access level, administrators or staff are immediately blocked from Gmail/Drive, or the Device Trust Portal itself returns `403 Forbidden`.

### Resolution
1. **Never Assign CAA Policies to the Root OU (`/`) First:**
   In `Security > Access and data control > Context-Aware Access > Assign to apps`, the left-hand tree defaults to the Root OU (`/`). Always select a dedicated **Pilot OU** or **`/Students` OU** so Super Administrators in `/Admin` cannot lock themselves out.
2. **Keep the Device Trust Portal Accessible from Unapproved Home Devices (Standard Mode):**
   When `./deploy.sh` asks *"Enable IAP Edge Defense & Corporate Network Gating? (y/N)"*, choose **`N`** (Standard Mode) for K-12, Higher Ed, or hybrid workforces so users on unapproved home laptops can open the portal and approve their device.

---

## 📱 9. Unexpected Devices or Auto-Approved Desktop BYOD Devices

### Issue A: Seeing Sample Devices (e.g., "Pixel 7", "MacBook Pro") Not Present in Admin Console
* **Cause:** Deployments running a container built prior to commit `2562135` fell back to sample demonstration data when Domain-Wide Delegation credentials failed to load (`GOOGLE_APPLICATION_CREDENTIALS` path mangling).
* **Fix:** Update your repository checkout (`git fetch origin && git reset --hard origin/main`) and re-run `./deploy.sh`. All mock and simulation fallbacks have been completely removed from the codebase; the portal exclusively serves live Cloud Identity and Directory API records.

### Issue B: Personal Windows/Mac Laptops Automatically Register as `APPROVED` Instead of `PENDING_APPROVAL`
* **Cause:**
  1. Devices that synced *before* **Require admin approval** (`Universal > Security > Device approvals`) and **Profile reporting** (`CloudProfileReportingEnabled`) were enabled may already hold `APPROVED` state in Cloud Identity.
  2. Or a child Organizational Unit overrides **Device approvals** with *Do not require admin approval*.
* **Fix:**
  1. Verify **Require admin approval** is inherited across all target OUs.
  2. Run the one-time baseline mass revocation script to reset existing BYOD bindings to `BLOCKED`:
     ```bash
     WORKSPACE_ADMIN_EMAIL=admin@yourdomain.com \
     GOOGLE_APPLICATION_CREDENTIALS=dwd_key.json \
     ./backend/venv/bin/python backend/scripts/mass_revoke_byod_approvals.py --force
     ```

---

## ⚡ 10. Unapproved Mac/PC Sessions Staying Signed In After Login (3-Layer Session Termination)

### Symptom
* Context-Aware Access (CAA) blocks Gmail and Google Drive (`403 Access Denied`), **or** you are testing on an Education Fundamentals domain without CAA, and a user who logs into an unapproved personal Mac or Windows laptop remains signed into `accounts.google.com` or the browser profile.

### Why This Happens in Google Workspace
1. **New Installs Start Disabled by Default (`enforcement_mode: "DISABLED"`):** On a fresh installation (`./deploy.sh`), both **Session Management** (`session_watch_enabled: false`) and **CAA Integration** (`caa_enforcement_enabled: false`) start disabled until enabled by an administrator in `#/admin`.
2. **CAA Blocks Apps at the Edge, Not `accounts.google.com`:** Even when CAA is active, Google permits initial `accounts.google.com` authentication so Chrome Profile Reporting and Endpoint Verification can register the device in Cloud Identity (`PENDING_APPROVAL`).
3. **Re-Logins on Previously `BLOCKED` Devices:** Once an unapproved Mac is transitioned from `PENDING_APPROVAL` to `BLOCKED`, signing in again updates `DeviceUser.lastSyncTime` in **~1.7 seconds**, while `managementState` stays `BLOCKED` (and Admin SDK `login` audit logs can lag 15–60 minutes).

### Resolution: Enable Session Management in `#/admin`
1. Open the Admin Portal (`#/admin`) and enable **Session Management (Education Fundamentals)** (either alone or alongside **Context-Aware Access Integration** as `BOTH`).
2. Click **💾 Save Configurations**, then click **🔄 Sync Inventory Cache** to load your approved ChromeOS and BYOD serials into the SQLite/RAM cache.
3. If testing with an administrator account, ensure **Exempt Super Admins & Portal Admins (`session_watch_exempt_admins`)** is **unchecked** (`false`).
4. Once enabled, the **3-Layer Immediate Enforcement Pipeline** terminates unapproved device sessions automatically:
   * **Layer 1 (`< 0.5s` Inline Portal Check + `8s` Heartbeat):** Opening the portal on an unapproved or `BLOCKED` device (without an active 15-minute onboarding lease) immediately fires `users.signOut` + OAuth grant revocation and signs the browser out with `401 SESSION_REVOKED_UNAPPROVED_DEVICE`.
   * **Layer 2 (`~2–10s` Cloud Identity `lastSyncTime` Sub-Polling):** The 1-minute Cloud Scheduler job (`session-watch-login-sweep`) runs 5 sub-polls spaced 10s apart (`t=0s, 10s, 20s, 30s, 40s`), detecting any `PENDING_APPROVAL` or re-authenticated `BLOCKED` BYOD `lastSyncTime` newer than the user's last sign-out and immediately executing `users.signOut` + `directory.tokens.delete`.
   * **Layer 3 (Admin SDK Reports API Sweep):** Catches external unmanaged browser logins that do not report via Chrome Profile Reporting.

---

## 🔄 11. Updating an Existing Deployment to the Latest Release

Whenever new fixes or UI improvements are pushed to the repository, update your local checkout and redeploy with:

```bash
cd ~/devicetrustportal
git fetch origin
git reset --hard origin/main
./deploy.sh
```

*(Note: `./deploy.sh` also checks `origin/main` automatically at startup and fast-forwards your checkout before building the container, while preserving your existing Secret Manager `device_trust_gateway_config` settings).*

