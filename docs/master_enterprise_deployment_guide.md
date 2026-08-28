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
| [ RULE: device.is_corp_owned_device == true || device.is_admin_approved_device == true ] |
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

* **Company-Owned Devices:** Managed hardware (such as Chromebooks enrolled via zero-touch or manual CSV upload) are automatically trusted as Company-Owned (`is_corp_owned_device == true`).
* **Personal BYOD Devices:** Employees install the privacy-preserving **Google Endpoint Verification** extension. Devices report telemetry without MDM control. When a user approves a personal device via the self-service Gateway portal, the backend updates its state to `APPROVED` in Cloud Identity (`is_admin_approved_device == true`), satisfying CAA rules and granting access.

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
   device.is_corp_owned_device == true || device.is_admin_approved_device == true
   ```
4. Because the personal device is unapproved (`is_admin_approved_device == false`) and not company inventory (`is_corp_owned_device == false`), Context-Aware Access blocks the request and displays a **403 Access Denied** screen with a link to your Device Trust Gateway portal.

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
2. Context-Aware Access re-evaluates the device posture. Because `device.is_admin_approved_device` is now `true`, access is instantly granted.

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
4. Switch to **Advanced mode** and paste this exact CEL expression:
   ```text
   device.is_corp_owned_device == true || device.is_admin_approved_device == true
   ```
5. Click **Save**.
6. Navigate to **Assign to apps** to configure policy enforcement:
   * ⚠️ **Critical: Target Organizational Unit (OU) Selection:** In the left Organizational Unit tree, **do NOT leave this policy assigned to the Root Organizational Unit (`/`)**. The Admin Console defaults to the Root OU, which will immediately apply the access level domain-wide to all user accounts (including Super Admins, faculty, and IT staff). If left at the Root OU without widespread pre-approval, administrators and staff can be locked out. Instead, explicitly select a specific target OU (such as **`Students` OU** or a dedicated **`Test / Pilot OU`**) to isolate policy enforcement.
   * **App Assignment:** Assign this level to the Workspace Apps of your choice (eg. Gmail, Drive…).
   * **Enforcement Policy:** Set policies to **Block** when policies / access levels are not met.
   * **Desktop & Mobile Apps:** Ensure policy is set to Enable for **Apply to Google desktop and mobile apps** (to enforce policy across native clients like Gmail mobile and Google Drive for Desktop in addition to web browsers).

### Step 7: Execute the Zero-Trust Baseline Revocation Sweep
Because initial Chrome browser profile sign-ins tag new desktop assets as `APPROVED` by default before revocation, execute the mass revocation script to reset unapproved BYOD hardware to `BLOCKED`:

```bash
WORKSPACE_ADMIN_EMAIL=claycodes@gwfe.org backend/venv/bin/python backend/scripts/mass_revoke_byod_approvals.py
```

---

## 5. Deployment Walkthrough

### Target 1: Automated Interactive Deployer (`./deploy.sh`) — Recommended

The repository includes an interactive deployment script (`deploy.sh`) that automates setup:

```bash
# Standard interactive deployment
./deploy.sh

# Verbose mode with real-time build streaming and detailed CLI command traces
./deploy.sh --verbose

# Bypass billing verification check if billing is managed centrally
./deploy.sh --skip-billing-check
```

**CLI Flags & Environment Variables:**
* `-v`, `--verbose` (`VERBOSE=true`): Enables real-time Cloud Build streaming, Cloud Run deployment outputs, and verbose CLI command tracing.
* `--skip-billing-check` (`SKIP_BILLING_CHECK=true`): Bypasses the pre-flight billing verification step if the deploying user lacks `roles/billing.viewer` IAM rights on the billing account object.
* `--project <ID>` (`GCP_PROJECT=<ID>`): Pre-specifies target Google Cloud Project ID.
* `--region <REGION>` (`GCP_REGION=<REGION>`): Pre-specifies target Cloud Run and Cloud Scheduler region (default: `us-central1`).
* `--target <1|2>` (`DEPLOY_TARGET=<1|2>`): Pre-selects deployment target (`1` for Cloud Run, `2` for Docker Compose).

**Automated Deployment Phases:**
1. **Pre-flight Billing Check & Diagnostics:** Verifies GCP billing enablement before creating resources. If verification fails (e.g. missing IAM permissions or disabled Cloud Billing API), the script prints the exact `gcloud` error message and diagnostic remedies directly to the console.
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

> [!IMPORTANT]
> **Architectural Decision Guide: Education & Hybrid Work vs. Strict On-Premise Enterprise**
>
> When configuring portal access, organizations must choose between two distinct security architectures:
>
> 1. **Standard Mode (Recommended for K-12, Higher Ed, and Hybrid Workplaces — Default):**
>    - **How it Works:** The Gateway portal is hosted directly on Cloud Run over public HTTPS, protected by **Google Workspace OAuth 2.0 Sign-In** and **Trust Chaining (6-digit pairing code)**.
>    - **The Student/Homework Workflow:** A student at home working on a personal PC/Mac opens the portal on their school-issued Chromebook, clicks **Generate Pairing Code**, and enters the code on their home PC to approve it.
>    - **User Impact:** **Zero friction.** Students can approve home computers in the evening to complete homework and assignments without IT helpdesk intervention.
>
> 2. **Strict IAP Edge Defense Mode (Strict Corporate / On-Premise Only):**
>    - **How it Works:** Places Cloud Run behind Google Cloud **Identity-Aware Proxy (IAP)** and an External HTTP(S) Load Balancer, restricting traffic strictly to corporate egress IP subnets or company-owned hardware.
>    - **User Impact:** **External Access Blocked.** Students or staff at home attempting to access the portal from a personal device are blocked at the edge with a `403 Forbidden` screen. Personal devices **cannot** be approved while off-campus unless the user connects through an enterprise VPN.
>    - **When to Use:** Only enable IAP Edge Defense if district/organization policy mandates that BYOD device approvals must occur exclusively while physically present on campus Wi-Fi or inside an administrative office.

```
+---------------------------------------------------------------------------------------------------+
| STANDARD MODE (Recommended for Schools)   | STRICT IAP MODE (On-Premise / Strict Corporate)      |
+-------------------------------------------+-------------------------------------------------------+
| • Public Cloud Run URL over HTTPS         | • Ingress restricted to Load Balancer + IAP Gating    |
| • Protected by Google OAuth 2.0           | • Restricted to Campus IP CIDRs or Corp Hardware      |
| • Remote self-service via Pairing Codes   | • No access from home internet without VPN            |
| • Students can do homework on home PCs    | • Blocks student home approvals (locks until on-site) |
+---------------------------------------------------------------------------------------------------+
```

#### Step-by-Step IAP Setup (If Mandated by Organization Policy):
If your security policy mandates strict on-campus-only gating:
1. **Restrict Cloud Run Ingress:** Set Cloud Run ingress control to **Internal and Cloud Load Balancing only**.
2. **Deploy HTTPS Load Balancer:** Create a GCP Load Balancer with a Serverless Network Endpoint Group (NEG) pointing to Cloud Run.
3. **Enable IAP:** In **GCP Console > Security > Identity-Aware Proxy**, enable IAP on the backend service.
4. **Configure Access Level:** In **Access Context Manager**, create an Access Level requiring corporate IP subnets (`10.0.0.0/8`) or corporate device posture. External users attempting to reach the portal from home internet will be blocked at the edge.

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

### Finding & Retrieving Your Live Portal URL
If you misplaced your unique Cloud Run portal URL after deployment:
1. **Google Cloud Console UI:** Open [Google Cloud Console > Cloud Run](https://console.cloud.google.com/run) and click on **`device-trust-gateway`**. The live HTTPS service URL is displayed at the top of the service page.
2. **Terminal (CLI Command):** Run the following command to print your active service URL:
   ```bash
   gcloud run services describe device-trust-gateway --region us-central1 --format='value(status.url)'
   ```
3. **Admin Configuration Dashboard:** Append `/#/admin` to the portal URL (e.g., `https://device-trust-gateway-xyz-uc.a.run.app/#/admin`).

### Common Issues & Remedies

| Issue | Cause | Fix |
| :--- | :--- | :--- |
| **Misplaced or forgot unique Cloud Run Portal URL** | Portal URL was lost in terminal scrollback or between testing sessions | View it in [Cloud Run Console](https://console.cloud.google.com/run) > `device-trust-gateway` (at top of page), or run `gcloud run services describe device-trust-gateway --region <REGION> --format='value(status.url)'`. Append `/#/admin` for Admin UI. |
| **Deployment stuck at billing check or fails with permission error** | Deploying account lacks `roles/billing.viewer` or `cloudbilling.googleapis.com` is disabled | Run with `./deploy.sh --verbose` to view exact CLI error details. If billing is managed centrally, run with `./deploy.sh --skip-billing-check` to bypass the verification. |
| **Cloud Build or Cloud Run deployment failure during script run** | Container build error, IAM role shortage, or service quota issue | Run `./deploy.sh --verbose` (or `-v`) to stream real-time container build logs and Cloud Run service revision error messages. |
| **New Mac auto-approves upon sign-in** | User is in a sub-OU (e.g. `/Admin`) with inherited auto-approval | Open `Devices > Universal settings > Security`, select the `/Admin` OU on the left, and check **Require admin approval**. |
| **User sees duplicate Mac entries in Portal** | Hardware serial asset vs. Extension virtual cert vs. Legacy browser profile | The portal backend automatically deduplicates rows, prioritizing physical serial assets (`Serial: C02F30BV0KPF`). Instruct users to approve the physical serial row. |
| **Context-Aware Access not blocking unapproved devices** | CAA Access Level is not assigned to apps, or policy is not set to Block | Go to `Security > Access and data control > Context-Aware Access > Assign to apps`. Select your target OU (e.g. `Students`), assign `Approved Devices Only` to the Workspace Apps of your choice (eg. Gmail, Drive…), set policy enforcement to **Block**, and enable **Apply to Google desktop and mobile apps**. |
| **Endpoint Verification telemetry missing** | Extension lacks key/challenge permissions | Ensure **Allow access to keys** and **Allow enterprise challenge** are set to **ON** in extension policy. |
