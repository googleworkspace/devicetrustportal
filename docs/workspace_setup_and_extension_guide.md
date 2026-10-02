# Google Workspace Configuration & Extension Guide for Zero-Trust Device Approvals

This document outlines the mandatory Google Workspace Admin Console settings, extension force-install procedures, and baseline revocation commands required to enforce a strict **"Approved Devices Only"** Zero-Trust security model using the **Device Trust Gateway**.

---

## 📑 Table of Contents
1. [Executive Summary](#-executive-summary)
2. [Google Workspace Admin Console Settings](#-google-workspace-admin-console-settings)
3. [Endpoint Verification Extension Force-Installation](#-endpoint-verification-extension-force-installation)
4. [Mobile vs Desktop Approval Behavior](#-mobile-vs-desktop-approval-behavior)
5. [Context-Aware Access (CAA) Rule Setup](#-context-aware-access-caa-rule-setup)
6. [Establishing the Zero-Trust Baseline Sweep](#-establishing-the-zero-trust-baseline-sweep)
7. [Troubleshooting Auto-Approval Leakage](#-troubleshooting-auto-approval-leakage)

---

## 🏛 Executive Summary

In Google Workspace:
* **Mobile Devices (Android / iOS):** Require **Advanced Mobile Management** + **Require Admin Approval** to automatically enter a `PENDING_APPROVAL` / `BLOCKED` state upon enrollment.
* **Computers (macOS / Windows / Linux):**
  - Personal BYOD laptops do **not** require Chrome Browser Cloud Management (CBCM) machine enrollment (`CloudReportingEnabled` is ignored on unenrolled BYOD machines).
  - When **Profile reporting** (`CloudProfileReportingEnabled`), **Chrome signals sharing** (`UserSecuritySignalsReporting` & `UserSecurityAuthenticatedReporting`), **Universal Device signals**, and **Require admin approval** are enabled together, newly signed-in managed Chrome profiles register directly in **Pending approval** (`Device.managementState = PENDING`, `DeviceUser.managementState = PENDING_APPROVAL`).
  - If desktop devices signed in *before* these policies were enabled (or via legacy unauthenticated sync), they may have initialized as `APPROVED`; administrators can run the **Mass BYOD Revocation Sweep** (`backend/scripts/mass_revoke_byod_approvals.py`) to reset pre-existing BYOD assets to `BLOCKED` until authorized via the **Device Trust Portal**.

---

## ⚙️ Google Workspace Admin Console Settings

Navigate to **[admin.google.com](https://admin.google.com)** and verify the following settings across all target Organizational Units (OUs), including sub-OUs such as `/Admin`, `/Staff`, and `/Students`:

### 1. Enable ChromeOS Device Reporting (Mandatory for Chromebook CAA Recognition)
> [!IMPORTANT]
> **Why Enterprise-Enrollment is Not Enough for CAA:**
> For Context-Aware Access (CAA) to recognize a Chromebook as a "Company-owned device" (`device.is_corp_owned_device == true`), simply enterprise-enrolling it is not enough. CAA relies on Endpoint Verification, which requires specific ChromeOS reporting and telemetry settings to be actively broadcasting the device's hardware identity to the Google Admin console.

* **Path:** `Devices > Chrome > Settings > Device settings` (`https://admin.google.com/ac/chrome/settings/device`)
* **Section:** Scroll down to the **User and device reporting** section.
* **Mandatory Settings (Turn all 4 ON):**
  1. **Report device OS information** → Set to **Enable OS information reporting**.
  2. **Report device hardware information** → Set to **Enable hardware information reporting**.
  3. **Report device telemetry** → Set to **Enable telemetry reporting**.
  4. **Report device user tracking** → Set to **Enable user tracking / recent users reporting**.

### 2. Enable Endpoint Verification Globally (Universal Settings)
Activates device signal collection across your entire organization.
* **Path:** `Devices > Mobile & endpoints > Settings > Universal > Data access` *(labeled **Universal** or **Universal settings**)*
* **Setting:** Expand **Device signals** *(or **Endpoint verification**)*.
* **Configuration:** Check **both** boxes:
  1. **Collect device signals from Chrome browser**
  2. **Collect device signals using endpoint verification** *(or **Monitor which devices access organization data**)*

### 3. Enable Device Approvals (Security)
* **Path:** `Devices > Mobile & endpoints > Settings > Universal settings > Security`
* **Direct Link:** `https://admin.google.com/ac/appsettings/724141353720?vid=EMM_UNIVERSAL_SETTINGS_VIEW`
* **Setting:** Expand **Device approvals**.
* **Configuration:** Select **Require admin approval**.
* **Email Notifications:** Enter the admin email address (e.g., `admin@yourdomain.com`) to receive enrollment alerts.
* ⚠️ **Important:** Verify that sub-OUs (like `/Admin`, `/Staff`, `/Students`) inherit this setting or explicitly have **Require admin approval** selected.

### 4. Enable Advanced Mobile Management (Mobile Devices)
* **Path:** `Devices > Mobile & endpoints > Settings > Universal settings > General`
* **Setting:** Expand **Mobile management**.
* **Configuration:** Set Android and iOS to **Advanced**.
* **Purpose:** Forces new Android and iOS logins into a `PENDING_APPROVAL` state upon initial account sign-in.

### 5. Enable Managed Chrome Profile Reporting, Signals Sharing & Sign-in Restrictions
To enable zero-enrollment BYOD telemetry reporting and prevent employees/students from signing into corporate Workspace accounts inside unmanaged personal Chrome profiles:
* **Path:** `Devices > Chrome > Settings > Users & browsers` (`https://admin.google.com/ac/chrome/settings/user`)
* **Setting 1 (Profile Reporting):** Find **Profile reporting** (`CloudProfileReportingEnabled`) and set to **Enable profile reporting**.
* **Setting 2 (Chrome Signals Sharing):** Find **Chrome signals sharing** (`UserSecuritySignalsReporting` & `UserSecurityAuthenticatedReporting`) and set to **Enable signals sharing**.
* **Setting 3 (Enterprise Hardware Platform API):** Find **Enterprise Hardware Platform API** (`EnterpriseHardwarePlatformAPIEnabled`) and set to **Allow extensions to see hardware platform information**.
* **Setting 4 (Browser Sign-in):** Find **Browser sign-in** and set to **Force users to sign in to use the browser**.
* **Setting 5 (Managed Account Restriction):** Find **Managed accounts sign-in restriction** (`ManagedAccountsSigninRestriction`) and set to **Block users from signing into secondary accounts** (`primary_account_strict`).
* **Purpose:** Ensures that all enterprise data access originates from an authenticated, policy-managed Google Workspace Chrome profile that reports hardware and OS signals directly to Cloud Identity without requiring CBCM machine enrollment.
* *(Note on `chrome://policy` Precedence Warnings: Machine-scoped precedence policies like `CloudPolicyOverridesPlatformPolicy` and `CloudUserPolicyOverridesCloudMachinePolicy` are `per_profile: false`. If configured at the user/profile scope on an unenrolled BYOD laptop, `chrome://policy` will display a benign "Ignored because the policy is not set at the machine scope" notice. You can leave Policy Precedence at default; `Cloud user` profile policies apply automatically).*

---

## 🔌 Endpoint Verification Extension Force-Installation

To ensure all Mac, Windows, Linux, and ChromeOS devices report accurate telemetry to Cloud Identity without relying on voluntary user installation, force-push the extension from the Admin Console.

### Extension Parameters
| Parameter | Value |
| :--- | :--- |
| **Extension Name** | Google Endpoint Verification |
| **Extension ID** | `callobklhcbilhphinckomhgkigmfocg` |
| **Target Platforms** | macOS, Windows, Linux, ChromeOS |
| **Store Source** | Chrome Web Store |

### Force-Install Procedure
1. Log into **Google Admin Console** (`admin.google.com`).
2. Navigate to **Devices > Chrome > Apps & extensions > Users & browsers** (`https://admin.google.com/ac/chrome/apps/user`).
3. In the left-hand **Organizational Units** panel, select your top-level domain or target OU (`/Students`, `/Staff`, `/Admin`).
4. Click the yellow **`+`** button in the bottom right corner and select **Add Chrome app or extension by ID**.
5. Paste the Extension ID:
   ```text
   callobklhcbilhphinckomhgkigmfocg
   ```
6. Leave **From the Chrome Web Store** selected and click **Save**.
7. **Locate the Right-Hand App Options Panel:**
   * Once you click **Save**, a configuration side panel automatically opens on the right side of the screen. *(If closed, simply click on the `Endpoint Verification` row in the extensions table to open it).*
   * Under **Installation policy**, select **Force install + pin to browser toolbar**.
   * Scroll down inside the right-hand panel to the **Certificate management** section:
     * Next to **Allow access to keys** (`KeyPermissions`), click **Turn on**.
     * Next to **Allow enterprise challenge** (`AttestationExtensionAllowlist`), click **Turn on**.
   * *(Platform Note: In Chromium's policy engine, `KeyPermissions` and `AttestationExtensionAllowlist` are ChromeOS-only policies (`supported_on: ["chrome_os"]`) for Verified Access hardware TPM attestation. They will not appear in `chrome://policy` on Windows or macOS laptops—this is normal. Windows and macOS BYOD devices register via the Profile Reporting and Chrome Signals Sharing policies configured in Section 5).*
8. Click **Save** at the top right of the page.

---

## 📊 Mobile vs Desktop Approval Behavior

Understanding how Google Cloud Identity treats different platform registrations:

```
+-------------------+---------------------------------------------+-------------------------------------------------+
| Platform Category | Required Management & Policy Settings       | Initial State in Cloud Identity                 |
+-------------------+---------------------------------------------+-------------------------------------------------+
| Android & iOS     | Advanced Mobile Management + Require Approv | PENDING_APPROVAL / BLOCKED                      |
+-------------------+---------------------------------------------+-------------------------------------------------+
| macOS & Windows   | Profile Reporting + Chrome Signals Sharing  | PENDING (Device) / PENDING_APPROVAL (DeviceUser)|
| (Managed Profile) | + Require Admin Approval                    |                                                 |
+-------------------+---------------------------------------------+-------------------------------------------------+
| macOS & Windows   | Legacy Endpoint Verification Sync without   | APPROVED by default upon initial sync           |
| (Pre-Policy Sync) | Profile Signals Sharing / Require Approval  | (Reset via mass_revoke_byod_approvals.py)       |
+-------------------+---------------------------------------------+-------------------------------------------------+
```

---

## 🏢 Registering & Seeding Company-Owned Inventory

Context-Aware Access rules permit access if `device.is_corp_owned_device == true || device.is_admin_approved_device == true`.

To ensure your corporate hardware assets are recognized as **Company-Owned** (`is_corp_owned_device == true`) without requiring manual user self-service approval:

### 1. Enterprise Chromebooks (Automated Seeding)
If you skipped seeding during deployment or enrolled new Chromebooks:
```bash
WORKSPACE_ADMIN_EMAIL=admin@yourdomain.com \
GOOGLE_APPLICATION_CREDENTIALS=dwd_key.json \
backend/venv/bin/python backend/scripts/seed_company_inventory.py
```
*Queries the Directory API and batch-anchors all managed ChromeOS devices in Cloud Identity under `ownerType: COMPANY`.*

### 2. Company-Owned Macs, Windows PCs & Mobile (Admin Console CSV Import)
For district-issued MacBooks, Windows PCs, and mobile devices:
1. Navigate to **Devices > Mobile & endpoints > Company-owned inventory** (`https://admin.google.com/ac/devices/companyowned`).
2. Click **Import company-owned devices** (`+`).
3. Select **Company-owned computers** or **Company-owned mobile devices**.
4. Download the CSV template and populate hardware **Serial Numbers** and **Asset Tags**.
5. Upload the CSV and click **Import**.
6. When users sign in with the Endpoint Verification extension on these computers, Google automatically matches the hardware serial number and applies `is_corp_owned_device == true`.

---

## 🛡 Context-Aware Access (CAA) Rule Setup

To transform `APPROVED` tags into mandatory access gatekeepers for Google Workspace apps:

1. Open **Security > Access and data control > Context-Aware Access** (`https://admin.google.com/ac/security/contextaware`).
2. Click **Create Access Level**.
3. Name the level: `Approved Devices Only`.
4. Select **Advanced mode** and enter the following exact Common Expression Language (CEL) rule:
   ```text
   device.is_corp_owned_device == true || device.is_admin_approved_device == true
   ```
5. Click **Save**.
6. Navigate to **Assign to apps** to configure policy enforcement:
   * ⚠️ **Critical: Target Organizational Unit (OU) Selection:** In the left Organizational Unit tree, **do NOT leave this policy assigned to the Root Organizational Unit (`/`)**. The Admin Console defaults to the Root OU, which will immediately apply the access level domain-wide to all user accounts (including Super Admins, faculty, and IT staff). If left at the Root OU without widespread pre-approval, administrators and staff can be locked out. Instead, explicitly select a specific target OU (such as **`Students` OU** or a dedicated **`Test / Pilot OU`**) to isolate policy enforcement.
   * **App Assignment:** Assign this level to the Workspace Apps of your choice (eg. Gmail, Drive…).
   * **Enforcement Policy:** Set policies to **Block** when policies / access levels are not met.
   * **Desktop & Mobile Apps:** Ensure policy is set to Enable for **Apply to Google desktop and mobile apps** (to enforce policy across native clients like Gmail mobile and Google Drive for Desktop in addition to web browsers).

---

## 🧹 Establishing the Zero-Trust Baseline Sweep

Because newly signed-in desktop Chrome profiles are assigned `managementState: APPROVED` by default before revocation, administrators must execute the baseline revocation sweep to reset unapproved BYOD assets.

### Execute Baseline Revocation via Terminal
Run the mass revocation script from the workspace directory:

```bash
WORKSPACE_ADMIN_EMAIL=claycodes@gwfe.org backend/venv/bin/python backend/scripts/mass_revoke_byod_approvals.py
```

### What the Sweep Script Does:
1. Paginate through all hardware assets registered in your Cloud Identity tenant (`gwfe.org`).
2. Identifies devices with `ownerType: BYOD` and `managementState: APPROVED`.
3. Preserves corporate hardware trust anchors (such as zero-touch enterprise Chromebooks).
4. Executes `service.devices().deviceUsers().delete(...)` or `.block(...)`, shifting personal BYOD devices (including Macs & PCs) to **`BLOCKED`**.

Once executed:
* Any unapproved Mac or PC attempting to open Gmail/Drive is instantly blocked by Context-Aware Access with a **403 Access Denied** screen.
* The user opens the **Device Trust Portal**, authenticates, and completes device approval (via Trust Chaining or Network Auth).
* The portal backend invokes `approve_device_user()`, updating `managementState` to `APPROVED` and restoring access.

---

## 🖥 Understanding Multiple Device Listings in the Portal

When inspecting your devices in the Device Trust Portal, you may observe multiple entries for a single physical computer (e.g., multiple Mac entries):

```text
+-------------------+--------------------+----------------------------+-------------------+
| Hardware Model    | Operating System   | Identifier                 | Approval State    |
+-------------------+--------------------+----------------------------+-------------------+
| MacBook Pro       | MacOS 15.6.1       | Serial/IMEI: C02F30BV0KPF  | PENDING APPROVAL  |
| MacBookPro17,1    | MacOS 15.6.1       | Virtual Asset / EV Cert    | PENDING APPROVAL  |
| Mac OS            | macOS 10.15.7      | Virtual Asset / EV Cert    | APPROVED          |
+-------------------+--------------------+----------------------------+-------------------+
```

### Why Multiple Listings Exist:
1. **Hardware Serial Binding (`MacBook Pro` with `Serial/IMEI`):** Created when Google Workspace captures the physical hardware serial number (`C02F30BV0KPF`). Approving this entry authorizes the physical computer hardware asset.
2. **Virtual Extension Certificate (`MacBookPro17,1` with `Virtual Asset / EV Cert`):** Created by the Endpoint Verification Chrome extension using a virtual certificate binding. Approving this entry authorizes the extension profile session.
3. **Legacy / Prior Browser Profile Syncs (`Mac OS` macOS 10.15.7):** Represents prior Chrome profile registrations from earlier sign-ins or legacy sessions.

### Recommended Approval Action:
To fully authorize your Mac, click **`[✓ Approve]`** on the row displaying your **physical Serial Number / IMEI** (`MacBook Pro` with `Serial/IMEI: C02F30BV0KPF`). If using Endpoint Verification extension challenges, click **`[✓ Approve]`** on both pending rows.

---

## 🔍 Troubleshooting Auto-Approval Leakage

| Symptom | Cause | Solution |
| :--- | :--- | :--- |
| **Mac auto-approves upon sign-in** | User belongs to a sub-OU (e.g., `/Admin`) that overrides root settings | Check `Devices > Universal settings > Security` for the `/Admin` OU specifically and set to **Require admin approval**. |
| **Mac bypasses CAA block** | Context-Aware Access policy is not assigned to Workspace apps | Open `Security > Context-Aware Access > Assign to apps` and bind the `Approved Devices Only` access level to Gmail/Drive. |
| **Endpoint Verification not reporting** | Extension is missing or blocked | Force-install Extension ID `callobklhcbilhphinckomhgkigmfocg` in Chrome Policy. |
| **Stale Mac retains access** | Mass revocation sweep has not run since device initial sync | Execute `backend/scripts/mass_revoke_byod_approvals.py` or trigger the `/api/cron/cleanup` endpoint. |
