# Device Trust Gateway & Approval Portal

The **Device Trust Gateway** is a secure bridge application designed for organizations (specifically Google Workspace and Cloud Identity customers) to enforce strict "Approved Devices Only" access policies via Context-Aware Access (CAA), while providing a seamless, low-friction self-service workflow for end-users to approve their personal BYOD devices.

---

## 📋 Table of Contents
1. [Architecture & Zero-Trust Overview](#-architecture--zero-trust-overview)
2. [Prerequisites & Billing Check](#-prerequisites--billing-check)
3. [⚡ Automated Interactive Deployer (Recommended)](#-automated-interactive-deployer-recommended)
4. [Chromebook Fleet Seeding Tool](#-chromebook-fleet-seeding-tool)
5. [Manual Setup: Local Development](#-manual-setup-local-development)
6. [Manual Setup: Docker (On-Premise)](#-manual-setup-docker-on-premise)
7. [Manual Setup: Google Cloud (GCP Cloud Run)](#-manual-setup-google-cloud-gcp-cloud-run)
8. [Configuration & Admin UI](#-configuration--admin-ui)
9. [Firewall, Network Allowlist & Anti-Spoofing](#-firewall-network-allowlist--anti-spoofing)

---

## 🏛 Architecture & Zero-Trust Overview

The Gateway leverages Google Workspace Context-Aware Access (CAA) to establish a zero-trust access perimeter. 

For a comprehensive whitepaper detailing how Context-Aware Access Custom Access Levels, Company-Owned inventory anchors, and Cloud Identity device approvals interact across the tenant, please read our dedicated enterprise guide:
👉 **[docs/caa_architecture_overview.md](docs/caa_architecture_overview.md)**

### Key Architectural Principles:
* **Unmanaged BYOD Hardware:** Personal devices do **not** require intrusive Mobile Device Management (MDM) enrollment or profiles. Users install the lightweight Endpoint Verification browser extension, registering the device as "Unmanaged" while still allowing our backend to approve them (`devices.deviceUsers.approve`), satisfying CAA policy rules while preserving user privacy.
* **Trust Anchor:** Automatically trusts company-owned inventory (e.g. ChromeOS zero-touch devices).
* **Trust Chaining Portal:** Users generate a temporary pairing code on an approved device (like a school Chromebook) and enter it on their unapproved phone to register it.
* **Network-Gated Portal:** One-click device approval when connected to campus Wi-Fi / trusted IP ranges.
* **Automated Lifecycle Management:** A secure cron endpoint (`/api/cron/cleanup`) automatically revokes access for inactive BYOD devices older than X days.

---

## 🛠 Prerequisites & Billing Check

- **Google Cloud Project** with an **Active Billing Account** linked. *(Google Cloud Run, Cloud Build, Cloud Scheduler, and Secret Manager require billing to be enabled before APIs can be activated).*
- **Google Workspace / Cloud Identity** tenant with Context-Aware Access (CAA) enabled.
- **Service Account Credentials** with Domain-Wide Delegation (DWD) or appropriate OAuth scopes (`https://www.googleapis.com/auth/cloud-identity.devices`, `https://www.googleapis.com/auth/admin.directory.device.chromeos.readonly`).
- **Node.js (v18+)** and **Python (3.11+)** installed for local development.

> [!IMPORTANT]
> **Pre-Deployment Billing Verification:** The automated `./deploy.sh` script actively inspects your GCP project's billing status before initiating setup. If billing is missing, it will provide direct links to the Google Cloud Billing Console (`https://console.cloud.google.com/billing`) so you can link an account and proceed without encountering API precondition failures.

---

## ⚡ Automated Interactive Deployer (Recommended)

We have included a robust interactive deployment script (`deploy.sh`) that streamlines setup across all target environments.

To launch the deployer from your terminal, run:
```bash
./deploy.sh
```

You will be presented with a simplified interactive menu:
```text
Please select your desired deployment target:
  1) Google Cloud (GCP Cloud Run + Secret Manager)
  2) On-Premise (Docker Compose + Local .env)
  3) Exit
```

### Three-Phase Cloud Run Deployment Workflow:
When deploying to Google Cloud, the script seamlessly solves the OAuth origin "chicken-and-egg" problem:
1. **Phase 1 (Baseline Service):** Executes an initial container build and Cloud Run deployment to establish your unique live HTTPS service URL (`https://device-trust-gateway-HASH-uc.a.run.app`).
2. **Phase 2 (Interactive Setup):** Displays explicit instructions prompting you to authorize this newly generated live URL as an Authorized JavaScript Origin in the Google Cloud Console, pausing to collect your resulting Client ID string.
3. **Phase 3 (Final Revision):** Re-executes Cloud Build forwarding the authorized Client ID, permanently baking it into the compiled Webpack React static bundle and deploying the final revision.

### Domain-Wide Delegation (DWD) Setup Wizard:
When configuring live API execution or Chromebook fleet seeding, the script launches an interactive DWD Setup Wizard:
1. Automatically verifies or creates a dedicated Google Cloud Service Account (`device-trust-gateway-sa`).
2. Generates and downloads a private JSON key (`dwd_key.json`).
3. Extracts your exact Service Account Client ID.
4. Displays explicit instructions to authorize the Client ID and required scopes in the Google Workspace Admin Console (`https://admin.google.com/ac/owl/domainwidedelegation`), pausing execution until you confirm authorization.
5. Prompts for your Super Administrator email and exports credentials for flawless impersonation.

---

## 💻 Chromebook Fleet Seeding Tool

For organizations with tens of thousands or hundreds of thousands of active ChromeOS devices, we provide an automated inventory seeding tool (`seed_company_inventory.py`) and real-time webhook endpoints (`/api/webhook/chrome-enrollment`).

This tool is seamlessly integrated into `./deploy.sh` and supports four execution frequencies:
1. **One-Time Execution:** Runs the crawl immediately from your terminal, paginating through the Directory API and executing batch registration requests against Cloud Identity.
2. **Daily Recurring Schedule:** Configures a Google Cloud Scheduler cron job to run daily at 2:00 AM.
3. **Weekly Recurring Schedule:** Configures a Google Cloud Scheduler cron job to run every Sunday at 3:00 AM.
4. **Event-Driven Real-Time Webhook (Pub/Sub Push) + Weekly Safety Net:** Establishes a real-time Google Cloud Pub/Sub push subscription listening for Google Workspace Reports API enrollment events (`ENTERPRISE_ENROLLMENT`), anchoring newly enrolled Chromebooks instantly while maintaining a weekly recurring sync as a reliable safety net.

---

## 🚀 Manual Setup: Local Development

If you prefer setting up the environment manually without the script:

### 1. Start the Backend (FastAPI)
Navigate to the root directory and install Python dependencies:
```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn backend.main:app --host 127.0.0.1 --port 8080 --reload
```
*Interactive API documentation will be available at `http://127.0.0.1:8080/docs`.*

### 2. Start the Frontend (React)
In a new terminal, start the React server:
```bash
cd frontend
npm install
npm start
```
*The frontend UI will automatically open at `http://localhost:3000`.*

---

## 🐳 Manual Setup: Docker (On-Premise)

1. Create a local `.env` file at the root directory:
```env
USE_SECRET_MANAGER=false
TENANT_CUSTOMER_ID=customers/my_customer
TENANT_INACTIVITY_THRESHOLD=90
TENANT_TRUSTED_IPS=["127.0.0.1/32", "10.0.0.0/8"]
TENANT_CHAINING_GROUPS=["trust-chaining-allowed@example.com"]
TENANT_CHAINING_OUS=["/Staff", "/Faculty"]
```

2. Build and start the container:
```bash
docker-compose -f deploy/docker-compose.yml up --build -d
```

---

## ☁️ Manual Setup: Google Cloud (GCP Cloud Run)

1. Enable required Google Cloud APIs:
```bash
gcloud services enable run.googleapis.com secretmanager.googleapis.com cloudidentity.googleapis.com cloudscheduler.googleapis.com pubsub.googleapis.com
```

2. Create a Secret Manager secret to hold dynamic tenant configurations:
```bash
gcloud secrets create device_trust_gateway_config --replication-policy="automatic"
```

3. Build and deploy the container to Cloud Run:
```bash
gcloud builds submit --tag gcr.io/YOUR_PROJECT_ID/device-trust-gateway deploy/
gcloud run deploy device-trust-gateway --image gcr.io/YOUR_PROJECT_ID/device-trust-gateway --platform managed --region us-central1 --set-env-vars="USE_SECRET_MANAGER=true,SECRET_NAME=device_trust_gateway_config"
```

---

## ⚙️ Configuration & Admin UI

Once the application is running, Workspace Administrators can dynamically update tenant configurations directly via the UI.

1. Access the portal and navigate to **Admin Configurations** (or visit `#/admin`).
2. Ensure your active user profile has administrator privileges (in local simulation mode, set your active email to `admin@example.com`).
3. Update settings such as **Inactivity Threshold (Days)**, **Campus Trusted IP CIDR Blocks**, and **Chaining Allowed Groups/OUs**.
4. Click **Save Configurations**. Changes will instantly persist to Secret Manager (GCP mode) or your local `.env` file (on-premise mode).

---

## 🔐 Firewall, Network Allowlist & Anti-Spoofing

If you are deploying the Gateway on-premise (Docker Compose) inside an enterprise network, explicit firewall rules are required for both incoming user traffic and outgoing Google API communication, alongside strict reverse proxy anti-spoofing security measures.

For the complete, detailed specification covering exact ports, protocols, reverse proxy header stripping, and Uvicorn trust configurations, please refer to our dedicated enterprise guide:
👉 **[docs/network_requirements.md](docs/network_requirements.md)**

### Summary of Anti-Spoofing Security Tiers:
* **🛡️ Upstream Proxy Stripping:** Enterprise reverse proxies (Nginx, F5, Cloudflare) must actively strip forged `X-Forwarded-For` headers arriving from external internet interfaces, overwriting them with authentic TCP socket client IPs.
* **🔒 Uvicorn Trust Gating (`--forwarded-allow-ips`):** Configure Uvicorn to only accept forwarded IP headers if they arrive directly from the known internal IP address of your reverse proxy host.
* **🔑 Session Binding:** Network IP trust alone cannot grant device approval. Requesting clients must also present a valid, authenticated Google Workspace OIDC Bearer token session for the target user.
