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

By default in Google Workspace:
* **Mobile Devices (Android / iOS):** Require **Advanced Mobile Management** + **Require Admin Approval** to automatically enter a `PENDING_APPROVAL` / `BLOCKED` state upon enrollment.
* **Computers (macOS / Windows / Linux):** Chrome Browser Profile Sync (*Chrome Signals Sharing / Fundamental Management*) registers computers with Cloud Identity as `APPROVED` upon initial Google sign-in.
* **Solution:** To enforce strict gated access for desktop computers (Macs & PCs), administrators must **force-install the Endpoint Verification Chrome extension**, enforce **Context-Aware Access (CAA)** policies, and run the **Mass BYOD Revocation Sweep** (`backend/scripts/mass_revoke_byod_approvals.py`) to reset auto-approved desktop assets to `BLOCKED` until authorized via the **Device Trust Portal**.

---

## ⚙️ Google Workspace Admin Console Settings

Navigate to **[admin.google.com](https://admin.google.com)** and verify the following settings across all target Organizational Units (OUs), including sub-OUs such as `/Admin`, `/Staff`, and `/Students`:

### 1. Enable Device Approvals (Security)
* **Path:** `Devices > Mobile & endpoints > Settings > Universal settings > Security`
* **Direct Link:** `https://admin.google.com/ac/appsettings/724141353720?vid=EMM_UNIVERSAL_SETTINGS_VIEW`
* **Setting:** Expand **Device approvals**.
* **Configuration:** Select **Require admin approval**.
* **Email Notifications:** Enter the admin email address (e.g., `claycodes@gwfe.org`) to receive enrollment alerts.
* ⚠️ **Important:** Verify that sub-OUs (like `/Admin`) inherit this setting or explicitly have **Require admin approval** selected.

### 2. Enable Advanced Mobile Management (Mobile Devices)
* **Path:** `Devices > Mobile & endpoints > Settings > Universal settings > General`
* **Setting:** Expand **Mobile management**.
* **Configuration:** Set Android and iOS to **Advanced**.
* **Purpose:** Forces new Android and iOS logins into a `PENDING_APPROVAL` state upon initial account sign-in.

### 3. Enable Endpoint Verification Signal Collection
* **Path:** `Devices > Mobile & endpoints > Settings > Universal settings > Data access`
* **Setting:** Expand **Endpoint verification**.
* **Configuration:** Check **Collect Device signals using endpoint verification**.

### 4. Force Managed Chrome Profile Sign-in (Chrome Browser Settings)
To prevent employees from signing into corporate Workspace accounts inside unmanaged personal Chrome profiles:
* **Path:** `Devices > Chrome > Settings > Users & browsers` *(or `Chrome browser > Settings > Users & browsers`)*
* **Setting 1 (Browser Sign-in):** Find **Browser sign-in** and set to **Force users to sign in to use the browser**.
* **Setting 2 (Managed Account Restriction):** Find **Managed accounts sign-in restriction** (`ManagedAccountsSigninRestriction`) and set to **Block users from signing into secondary accounts** (`primary_account_strict`).
* **Purpose:** Ensures that all enterprise data access originates exclusively from an authenticated, policy-managed Google Workspace Chrome profile where the Endpoint Verification extension is forced.

---

## 🔌 Endpoint Verification Extension Force-Installation

To ensure all Mac, Windows, and Linux devices report accurate telemetry and cryptographic challenges to Cloud Identity without relying on voluntary user installation, force-push the extension from the Admin Console.

### Extension Parameters
| Parameter | Value |
| :--- | :--- |
| **Extension Name** | Google Endpoint Verification |
| **Extension ID** | `callobklhcbilhphinckomhgkigmfocg` |
| **Target Platforms** | macOS, Windows, Linux, ChromeOS |
| **Store Source** | Chrome Web Store |

### Force-Install Procedure
1. Log into **Google Admin Console** (`admin.google.com`).
2. Navigate to **Devices > Chrome > Apps & extensions > Users & browsers** *(or `Chrome browser > Apps & extensions > Users & browsers`)*.
3. In the left-hand **Organizational Units** panel, select your top-level domain (`gwfe.org`) or target OU (`/Staff`, `/Admin`).
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
     * Next to **Allow access to keys**, click **Turn on** (allows extension to access OS Keychain/TPM client certificates to sign telemetry).
     * Next to **Allow enterprise challenge**, click **Turn on** (allows extension to respond to Context-Aware Access real-time attestation challenges).
8. Click **Save** at the top right of the page.

---

## 📊 Mobile vs Desktop Approval Behavior

Understanding how Google Cloud Identity treats different platform registrations:

```
+-------------------+--------------------------------+-------------------------------------------------+
| Platform Category | Required Management Type       | Default Initial State in Cloud Identity         |
+-------------------+--------------------------------+-------------------------------------------------+
| Android & iOS     | Advanced Mobile Management     | PENDING_APPROVAL / BLOCKED                      |
+-------------------+--------------------------------+-------------------------------------------------+
| macOS & Windows   | Endpoint Verification + CAA    | APPROVED by default upon initial Chrome sync    |
+-------------------+--------------------------------+-------------------------------------------------+
```

### Why Desktop Computers Auto-Approve by Default
When a user signs into Chrome browser on macOS or Windows without an active Context-Aware Access enforcement block, Chrome Profile Reporting registers the computer in Cloud Identity under **Fundamental Management**. Cloud Identity initializes `managementState` to `APPROVED` at `createTime`.

---

## 🛡 Context-Aware Access (CAA) Rule Setup

To transform `APPROVED` tags into mandatory access gatekeepers for Google Workspace apps:

1. Open **Security > Access and data control > Context-Aware Access** (`https://admin.google.com/ac/security/contextaware`).
2. Click **Create Access Level**.
3. Name the level: `Approved Devices Only`.
4. Select **Advanced mode** and enter the following Common Expression Language (CEL) rule:
   ```text
   device.is_corp_owned == true || device.is_admin_approved == true
   ```
5. Click **Save**.
6. Click **Assign to apps** and bind this Access Level to **Google Workspace** (Gmail, Google Drive, Google Calendar, Admin Console).

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
