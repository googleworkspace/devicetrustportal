# Master Enterprise Deployment & Operating Guide: Device Trust Gateway

This master guide provides a comprehensive, end-to-end blueprint for deploying, configuring, and operating the **Device Trust Gateway**. It details the core security architecture, required Google Workspace licensing editions, step-by-step end-user workflows, complete Google Admin Console configurations, and deployment procedures.

---

## 📑 Table of Contents
1. [Executive Summary & Core Concept](#1-executive-summary--core-concept)
2. [Google Workspace Edition & Licensing Requirements](#2-google-workspace-edition--licensing-requirements)
3. [End-User Workflow Walkthrough](#3-end-user-workflow-walkthrough)
4. [Complete Google Workspace Configuration Checklist](#4-complete-google-workspace-configuration-checklist)
5. [Deployment Walkthrough](#5-deployment-walkthrough)
6. [Operational Runbook & Troubleshooting](#6-operational-runbook--troubleshooting)

---

## 1. Executive Summary & Core Concept

### The Security Challenge
Educational institutions and corporate enterprises face constant security threats from compromised user credentials (phishing, session hijacking, password reuse). Even with Multi-Factor Authentication (MFA), an attacker with valid credentials will attempt to sign into enterprise systems from an unmanaged, unknown personal device. 

Blocking all personal Bring-Your-Own-Device (BYOD) hardware creates massive friction for employees, students, and IT helpdesks. Conversely, allowing all personal hardware leaves the environment vulnerable to data exfiltration. Deploying full Mobile Device Management (MDM) profiles on personal hardware raises privacy concerns and support overhead.

### The Device Trust Gateway Solution
The **Device Trust Gateway** is a zero-trust bridge application that decouples access approval from intrusive MDM profile enrollment. It leverages **Google Workspace Context-Aware Access (CAA)** and the **Google Cloud Identity Devices API** to enforce a strict **"Approved Devices Only"** access model.

```
+-----------------------------------------------------------------------------------+
|                     Google Workspace Context-Aware Access (CAA)                   |
|                                                                                   |
|   [ RULE: device.is_corp_owned == true || device.is_admin_approved == true ]      |
+-----------------------------------------+-----------------------------------------+
                                          |
                     +--------------------+--------------------+
                     |                                         |
                     v                                         v
+-----------------------------------------+ +-----------------------------------------+
|       Company-Owned Trust Anchor        | |         Personal BYOD Asset             |
|                                         | |                                         |
|  (e.g., Enterprise-Enrolled Chromebook) | |  (Endpoint Verification Extension)      |
|  ownerType: COMPANY                     | |  managementState: APPROVED              |
+-----------------------------------------+ +-----------------------------------------+
```

* **Company-Owned Devices:** Managed hardware (such as Chromebooks enrolled via zero-touch or manual CSV upload) are automatically trusted as Company-Owned (`is_corp_owned == true`).
* **Personal BYOD Devices:** Employees install the privacy-preserving **Google Endpoint Verification** extension. Devices report telemetry without MDM control. When a user approves a personal device via the self-service Gateway portal, the backend updates its state to `APPROVED` in Cloud Identity (`is_admin_approved == true`), satisfying CAA rules and granting access.

---

## 2. Google Workspace Edition & Licensing Requirements

Context-Aware Access (CAA) and advanced Cloud Identity device approval APIs require specific Google Workspace or Cloud Identity editions. 

### Supported Google Workspace & Cloud Identity Editions
To deploy Context-Aware Access policies and integrate with the Devices API, your tenant must hold licenses for at least one of the following editions:

| License Category | Supported Editions |
| :--- | :--- |
| **Education** | • Google Workspace for Education Plus<br>• Google Workspace for Education Standard<br>• Endpoint Education Upgrade |
| **Enterprise** | • Google Workspace Enterprise Plus<br>• Google Workspace Enterprise Standard<br>• Google Workspace Enterprise Essentials / Essentials Plus |
| **Business** | • Google Workspace Business Plus *(Computers/Laptops via Endpoint Verification)* |
| **Frontline** | • Google Workspace Frontline Standard<br>• Google Workspace Frontline Plus |
| **Standalone Identity** | • Cloud Identity Premium |

> [!IMPORTANT]
> **Licensing Verification:** Ensure that target users (especially Super Administrators and staff) have one of the above licenses assigned in **Directory > Users**. Without a supported edition, Context-Aware Access rules will not be evaluated for the user account.

---

## 3. End-User Workflow Walkthrough

Here is the exact step-by-step experience for an end-user connecting from a new personal device.

```
[ Step 1: Login Attempt ] ──> [ Step 2: CAA Block (403) ] ──> [ Step 3: Gateway Portal ] ──> [ Step 4: Access Restored ]
  User signs into Chrome       Context-Aware Access           User completes self-service     CAA re-evaluates & permits
  on new personal laptop       blocks Gmail/Drive             approval via Trust Chaining     access to Workspace apps
```

### Step 1: Initial Sign-In Interception
1. The user signs into Google Chrome or a Workspace application (e.g. Gmail) on a new personal Mac or PC.
2. The force-installed Endpoint Verification extension transmits device telemetry to Google Cloud Identity.
3. Google Workspace Context-Aware Access evaluates the incoming request against your tenant's Access Level rule:
   ```text
   device.is_corp_owned == true || device.is_admin_approved == true
   ```
4. Because the personal device is unapproved (`is_admin_approved == false`) and not company inventory (`is_corp_owned == false`), Context-Aware Access blocks the request and displays a **403 Access Denied** screen with a link to your Device Trust Gateway portal.

### Step 2: Self-Service Device Registration
The user can approve their new personal device using one of two self-service authorization models:

#### Workflow A: Trust Chaining Model (Recommended)
1. The user opens the **Device Trust Gateway Portal** on an **already approved device** (such as their school-issued Chromebook or a previously approved laptop).
2. The user clicks **Generate Pairing Code**. The Gateway backend generates a secure 6-digit numeric pairing code valid for 10 minutes.
3. The user opens the Gateway portal URL on their **new unapproved device** and enters the 6-digit pairing code.
4. The backend verifies the code, identifies the device user binding, and executes:
   ```python
   cloud_identity_service.approve_device_user(device_user_name, customer_id)
   ```
5. Cloud Identity immediately updates the device user `managementState` to `APPROVED`.

#### Workflow B: Network-Gated Model (Campus Wi-Fi)
1. The user connects their personal laptop to the organization's trusted network (e.g. campus Wi-Fi).
2. The user opens the Gateway portal on the new device.
3. The backend inspects the client's IP address against configured corporate CIDR ranges (`trusted_ip_ranges`).
4. Upon IP verification, the user clicks **Register This Device**, and the backend approves the device binding in Cloud Identity.

### Step 3: Access Restored
1. The user reloads Gmail or Google Drive on their personal device.
2. Context-Aware Access re-evaluates the device posture. Because `device.is_admin_approved` is now `true`, access is instantly granted.

---

## 4. Complete Google Workspace Configuration Checklist

Follow this checklist in the **Google Admin Console** (`admin.google.com`) to prepare your tenant for the Gateway.

### Checklist Overview
- [ ] Enable **Require Admin Approval** in Universal Settings across all OUs (including `/Admin`).
- [ ] Set **Mobile Management** to **Advanced** for iOS and Android.
- [ ] Check **Collect Device signals using endpoint verification**.
- [ ] Force-install the **Endpoint Verification Chrome Extension** (`callobklhcbilhphinckomhgkigmfocg`).
- [ ] Turn ON **Allow access to keys** and **Allow enterprise challenge** in Extension Certificate Management.
- [ ] Enforce **Managed Accounts Sign-in Restriction** (`primary_account_strict`).
- [ ] Create and assign the **Context-Aware Access Level** (`Approved Devices Only`).
- [ ] Run the **Mass BYOD Baseline Revocation Sweep**.

---

### Step 1: Universal Security & Device Approval Settings
1. Go to **Devices > Mobile & endpoints > Settings > Universal settings > Security**.
2. Expand **Device approvals**.
3. Select **Require admin approval**.
4. Enter your admin email address to receive enrollment notifications.
5. ⚠️ **Sub-OU Check:** In the left Organizational Units tree, click sub-OUs (such as `/Admin` and `/Staff`) and verify that **Require admin approval** is explicitly selected or inherited.

### Step 2: Advanced Mobile Management Settings
1. Go to **Devices > Mobile & endpoints > Settings > Universal settings > General**.
2. Expand **Mobile management**.
3. Set **Android** and **iOS** management to **Advanced**. *(Forces new mobile device sign-ins into `PENDING_APPROVAL` / `BLOCKED` status).*

### Step 3: Endpoint Verification Signals
1. Go to **Devices > Mobile & endpoints > Settings > Universal settings > Data access**.
2. Expand **Endpoint verification**.
3. Check **Collect Device signals using endpoint verification**.

### Step 4: Force-Install Endpoint Verification Chrome Extension
1. Go to **Devices > Chrome > Apps & extensions > Users & browsers** *(or `Chrome browser > Apps & extensions > Users & browsers`)*.
2. Select your target Organizational Unit (e.g. `gwfe.org` or `/Staff`).
3. Click **Add (+) > Add Chrome app or extension by ID**.
4. Paste Extension ID:
   ```text
   callobklhcbilhphinckomhgkigmfocg
   ```
5. Click **Save**.
6. **In the Right-Hand App Options Panel:**
   * Under **Installation policy**, select **Force install + pin to browser toolbar**.
   * Scroll down to **Certificate management**:
     * Next to **Allow access to keys**, click **Turn on** *(allows extension to sign telemetry with OS Keychain/TPM keys)*.
     * Next to **Allow enterprise challenge**, click **Turn on** *(allows extension to answer Context-Aware Access real-time attestation challenges)*.
7. Click **Save** at the top right of the page.

### Step 5: Force Managed Chrome Profile Sign-in
To prevent data access inside unmanaged personal Chrome browser profiles:
1. Go to **Devices > Chrome > Settings > Users & browsers**.
2. Locate **Browser sign-in** and set to **Force users to sign in to use the browser**.
3. Locate **Managed accounts sign-in restriction** (`ManagedAccountsSigninRestriction`) and set to **Block users from signing into secondary accounts** (`primary_account_strict`).

### Step 6: Create Context-Aware Access Level
1. Go to **Security > Access and data control > Context-Aware Access** (`https://admin.google.com/ac/security/contextaware`).
2. Click **Create Access Level**.
3. Name: `Approved Devices Only`.
4. Switch to **Advanced mode** and paste this CEL expression:
   ```text
   device.is_corp_owned == true || device.is_admin_approved == true
   ```
5. Click **Save**.
6. Click **Assign to apps** and bind this Access Level to **Google Workspace** (Gmail, Google Drive, Google Calendar, Admin Console, etc.).

### Step 7: Execute the Zero-Trust Baseline Revocation Sweep
Because initial Chrome browser profile sign-ins tag new desktop assets as `APPROVED` by default before revocation, execute the mass revocation script to reset unapproved BYOD hardware to `BLOCKED`:

```bash
WORKSPACE_ADMIN_EMAIL=claycodes@gwfe.org backend/venv/bin/python backend/scripts/mass_revoke_byod_approvals.py
```

---

## 5. Deployment Walkthrough

The Device Trust Gateway supports multiple deployment targets.

### Target 1: Automated Interactive Deployer (`./deploy.sh`) — Recommended

The repository includes an interactive deployment script (`deploy.sh`) that automates setup:

```bash
./deploy.sh
```

**Automated Deployment Phases:**
1. **Pre-flight Billing Check:** Verifies GCP billing enablement before creating resources.
2. **Phase 1 (Baseline Container Build):** Deploys the initial FastAPI/React container to Cloud Run to generate your live HTTPS domain (`https://device-trust-gateway-HASH-uc.a.run.app`).
3. **Phase 2 (OAuth Origin Registration):** Prompts you to paste your live Cloud Run URL into Google Cloud Console as an Authorized JavaScript Origin, collecting your Client ID string.
4. **Phase 3 (Final Revision Build):** Re-compiles the React frontend bundle with your Client ID and deploys the final Cloud Run revision.
5. **Phase 4 (Domain-Wide Delegation Setup):** Creates the service account `device-trust-gateway-sa`, exports `dwd_key.json`, and displays client ID authorization links for the Workspace Admin Console.
6. **Phase 5 (Identity-Aware Proxy / IAP Edge Defense):** Prompts to automatically restrict Cloud Run ingress to Internal/Load Balancer traffic, creates the Serverless NEG and Backend Service, and enables Google Cloud IAP.

---

### Target 2: On-Premise Docker Compose

For on-premise virtual machines or internal servers:

1. Create a root `.env` file:
   ```env
   USE_SECRET_MANAGER=false
   TENANT_CUSTOMER_ID=customers/my_customer
   TENANT_INACTIVITY_THRESHOLD=90
   TENANT_PORTAL_ADMINS=["admin@yourdomain.com"]
   WORKSPACE_ADMIN_EMAIL=admin@yourdomain.com
   GOOGLE_APPLICATION_CREDENTIALS=dwd_key.json
   ```
2. Build and launch the container stack:
   ```bash
   docker-compose -f deploy/docker-compose.yml up --build -d
   ```

---

### Target 3: Manual Google Cloud Run Setup

To deploy manually via Google Cloud CLI:

```bash
# 1. Enable required APIs
gcloud services enable run.googleapis.com secretmanager.googleapis.com cloudidentity.googleapis.com cloudscheduler.googleapis.com pubsub.googleapis.com firestore.googleapis.com

# 2. Create Secret Manager secret for configuration
gcloud secrets create device_trust_gateway_config --replication-policy="automatic"

# 3. Build container image via Cloud Build
gcloud builds submit --tag gcr.io/$GOOGLE_CLOUD_PROJECT/device-trust-gateway deploy/

# 4. Deploy service to Cloud Run
gcloud run deploy device-trust-gateway \
  --image gcr.io/$GOOGLE_CLOUD_PROJECT/device-trust-gateway \
  --platform managed \
  --region us-central1 \
  --set-env-vars="USE_SECRET_MANAGER=true,SECRET_NAME=device_trust_gateway_config"
```

---

### Target 4: Optional Portal Edge Defense (Identity-Aware Proxy / IAP)

To protect the Device Trust Gateway portal itself from being scanned or accessed by unauthenticated internet bad actors, place Cloud Run behind Google Cloud **Identity-Aware Proxy (IAP)**:

```
External Internet ──> HTTP(S) Load Balancer ──> IAP Edge Gating ──> Cloud Run (Gateway Backend)
                                                 [Rule: Corporate IP or Corp Device]
```

1. **Restrict Cloud Run Ingress:** Set Cloud Run ingress control to **Internal and Cloud Load Balancing only**.
2. **Deploy HTTPS Load Balancer:** Create a GCP Load Balancer with a Serverless Network Endpoint Group (NEG) pointing to Cloud Run.
3. **Enable IAP:** In **GCP Console > Security > Identity-Aware Proxy**, enable IAP on the backend service.
4. **Configure Access Level:** Bind an Access Level requiring corporate IP subnets (`10.0.0.0/8`) or corporate device posture to the IAP resource. External bad actors attempting to reach the portal URL are blocked at the edge with a 403 screen.

---

## 6. Operational Runbook & Troubleshooting

### Daily/Weekly Operations & Cleanup Cron
The Gateway backend includes an automated cleanup endpoint `/api/cron/cleanup` that revokes BYOD devices inactive for longer than your threshold (default: 90 days).

To configure a recurring Cloud Scheduler job:
```bash
gcloud scheduler jobs create http byod-inactivity-cleanup \
  --schedule="0 2 * * *" \
  --uri="https://YOUR-GATEWAY-URL/api/cron/cleanup" \
  --headers="X-CloudScheduler=true" \
  --http-method=POST
```

### Domain Audit & Troubleshooting Command
To inspect Cloud Identity device bindings, serial numbers, and audit events directly from your terminal:

```bash
WORKSPACE_ADMIN_EMAIL=admin@yourdomain.com backend/venv/bin/python backend/scripts/pull_domain_device_logs.py
```

### Common Issues & Remedies

| Issue | Cause | Fix |
| :--- | :--- | :--- |
| **New Mac auto-approves upon sign-in** | User is in a sub-OU (e.g. `/Admin`) with inherited auto-approval | Open `Devices > Universal settings > Security`, select the `/Admin` OU on the left, and check **Require admin approval**. |
| **User sees duplicate Mac entries in Portal** | Hardware serial asset vs. Extension virtual cert vs. Legacy browser profile | The portal backend automatically deduplicates rows, prioritizing physical serial assets (`Serial: C02F30BV0KPF`). Instruct users to approve the physical serial row. |
| **Context-Aware Access not blocking unapproved devices** | CAA Access Level is not assigned to apps | Go to `Security > Context-Aware Access > Assign to apps` and assign `Approved Devices Only` to Google Workspace. |
| **Endpoint Verification telemetry missing** | Extension lacks key/challenge permissions | Ensure **Allow access to keys** and **Allow enterprise challenge** are set to **ON** in extension policy. |
