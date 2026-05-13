# Network & Firewall Requirements: Device Trust Gateway

To successfully deploy the **Device Trust Gateway** in an on-premise containerized environment (Docker Compose) or behind an enterprise firewall, your network security team must configure explicit **Inbound** (Ingress) and **Outbound** (Egress) firewall rules.

Below is the detailed network specification based on the platform's technical architecture.

---

## 📥 1. Inbound Traffic (Ingress: Client to Gateway)

Clients (students, faculty, and IT administrators) must be able to access the frontend web portal and communicate with the backend REST API.

| Source | Destination | Protocol / Port | Architectural Purpose |
| :--- | :--- | :--- | :--- |
| **Campus Trusted Subnets** (e.g., Student/Staff Wi-Fi, LAN CIDR blocks) | Gateway Host / Reverse Proxy | TCP / 80 (HTTP)<br>TCP / 443 (HTTPS) | **Feature 3 (Network-Gated Approval):** Allows on-campus users to access the portal. The backend inspects the client's IP address (via `X-Forwarded-For` headers) to verify they are on a trusted network before granting one-click device approval. |
| **External Internet** (0.0.0.0/0)<br>*(Optional / Policy Dependent)* | Gateway Host / Reverse Proxy | TCP / 80 (HTTP)<br>TCP / 443 (HTTPS) | **Feature 2 (Trust Chaining Portal):** If your organization permits users to approve new personal devices while off-campus (e.g., from home or cellular networks), inbound traffic from the external internet must be permitted. Users must authenticate from an *already approved* device to generate pairing codes. |
| **IT Admin Subnets** / Management VLAN | Gateway Host / Reverse Proxy | TCP / 80 (HTTP)<br>TCP / 443 (HTTPS) | **Admin Configuration UI:** Allows Workspace Administrators to access `#/admin` to dynamically manage security thresholds and access policies. |

> [!IMPORTANT]
> **Reverse Proxy Configuration:** If placing the Gateway behind a load balancer or reverse proxy (e.g., Nginx, Apache, F5), ensure the proxy preserves the original client IP address by forwarding it in the `X-Forwarded-For` header. The backend relies on this header to evaluate trusted campus IP ranges.

---

## 📤 2. Outbound Traffic (Egress: Gateway to Google APIs)

The Gateway backend acts as a secure bridge. When a user successfully authenticates or submits a valid pairing code, the backend makes elevated REST API calls to Google Cloud Identity and Google Workspace Admin SDK on behalf of the organization.

The Gateway server/container host must be permitted outbound access to the following Google API endpoints over **TCP port 443 (HTTPS)**.

### Core Authentication & OAuth
* `oauth2.googleapis.com`: Required to exchange service account credentials and user access tokens.
* `accounts.google.com`: Required for Google Workspace Single Sign-On (SSO) and OpenID Connect authentication flows.
* `www.googleapis.com`: Required for general Google API discovery and client library communications.

### Google Cloud Identity API
* `cloudidentity.googleapis.com`: Core API utilized by the backend to execute device management operations:
  - `POST /v1/{name}:approve`: Approves a device user binding.
  - `GET /v1/devices`: Lists devices to identify inactive/stale BYOD hardware.
  - `DELETE /v1/{name}`: Revokes device approval status during automated cron cleanups.

### Google Workspace Admin SDK (Directory API)
* `admin.googleapis.com`: Utilized by `directory_service.py` to evaluate granular access permissions:
  - **Admin Verification:** Verifies if the logged-in user possesses Workspace Super Admin or delegated Administrator roles.
  - **Chaining Policy Gating:** Inspects user membership in designated Google Groups and Organizational Units (OUs) to verify if they are authorized to perform trust chaining.

### Google Cloud Secret Manager (Optional)
* `secretmanager.googleapis.com`: Required if the backend is configured to sync dynamic admin configurations with Google Cloud Secret Manager (`USE_SECRET_MANAGER=true`). *(Not required if operating in pure local `.env` fallback mode).*
