# Network & Firewall Requirements: Device Trust Gateway

To successfully deploy the **Device Trust Gateway** in an on-premise containerized environment (Docker Compose) or behind an enterprise firewall, your network security team must configure explicit **Inbound** (Ingress) and **Outbound** (Egress) firewall rules, and establish strict reverse proxy security gating.

Below is the detailed network specification and anti-spoofing architecture.

---

## 📥 1. Inbound Traffic (Ingress: Client to Gateway)

Clients (students, faculty, and IT administrators) must be able to access the frontend web portal and communicate with the backend REST API.

| Source | Destination | Protocol / Port | Architectural Purpose |
| :--- | :--- | :--- | :--- |
| **Campus Trusted Subnets** (e.g., Student/Staff Wi-Fi, LAN CIDR blocks) | Gateway Host / Reverse Proxy | TCP / 80 (HTTP)<br>TCP / 443 (HTTPS) | **Feature 3 (Network-Gated Approval):** Allows on-campus users to access the portal. The backend inspects the client's IP address (via `X-Forwarded-For` headers) to verify they are on a trusted network before granting one-click device approval. |
| **External Internet** (0.0.0.0/0)<br>*(Optional / Policy Dependent)* | Gateway Host / Reverse Proxy | TCP / 80 (HTTP)<br>TCP / 443 (HTTPS) | **Feature 2 (Trust Chaining Portal):** If your organization permits users to approve new personal devices while off-campus (e.g., from home or cellular networks), inbound traffic from the external internet must be permitted. Users must authenticate from an *already approved* device to generate pairing codes. |
| **IT Admin Subnets** / Management VLAN | Gateway Host / Reverse Proxy | TCP / 80 (HTTP)<br>TCP / 443 (HTTPS) | **Admin Configuration UI:** Allows Workspace Administrators to access `#/admin` to dynamically manage security thresholds and access policies. |

---

## 🛡️ 2. Preventing On-Premise Network Spoofing (Anti-Mocking Architecture)

When hosting on-premise, a critical threat vector involves malicious actors attempting to "mock" or spoof the network to bypass campus IP gating (Feature 3). Specifically, an attacker located outside the campus network (e.g., at a coffee shop) might attempt to inject forged HTTP headers (`X-Forwarded-For: 10.0.0.5`) or spoof TCP/IP packets.

To guarantee absolute defense-in-depth, on-premise deployments must enforce the following four security tiers:

```
+-----------------------------------------------------------------------------------+
|                           Untrusted External Internet                             |
|                       (Attacker injects X-Forwarded-For: 10.0.0.5)                |
+-----------------------------------------+-----------------------------------------+
                                          |
                                          v
+-----------------------------------------------------------------------------------+
|                       Enterprise Reverse Proxy / WAF (Nginx / F5)                 |
|                                                                                   |
|  [ RULE: Strip incoming X-Forwarded-For headers from external interfaces ]        |
|  [ RULE: Overwrite with authentic TCP Client IP (e.g., X.X.X.X) ]                 |
+-----------------------------------------+-----------------------------------------+
                                          |
                                          v
+-----------------------------------------------------------------------------------+
|                       Gateway Container Host (Uvicorn / FastAPI)                  |
|                                                                                   |
|  [ RULE: Enforce --forwarded-allow-ips to only trust proxy's internal IP ]        |
+-----------------------------------------+-----------------------------------------+
                                          |
                                          v
+-----------------------------------------------------------------------------------+
|                       Google Sign-In Authentication Validation                    |
|                                                                                   |
|  [ RULE: Bearer JWT required. Network IP alone cannot grant access. ]             |
+-----------------------------------------------------------------------------------+
```

### Tier 1: Upstream Proxy Header Gating (Mandatory)
Never expose the FastAPI container (`port 8080`) directly to the raw internet. Place the Gateway behind an enterprise reverse proxy or Web Application Firewall (WAF) such as **Nginx**, **F5 Big-IP**, **HAProxy**, or **Cloudflare Tunnels**.
Your reverse proxy must be configured with explicit header stripping rules:
* **Strip Forged Headers:** Remove any existing `X-Forwarded-For`, `X-Real-IP`, or `True-Client-IP` headers originating from incoming external internet requests.
* **Append Authentic IP:** Overwrite the header with the actual, authentic TCP socket connection IP address of the client.

*Nginx Example Configuration:*
```nginx
location / {
    # Prevent header forgery by overwriting X-Forwarded-For with actual TCP socket IP
    proxy_set_header X-Forwarded-For $remote_addr;
    proxy_pass http://localhost:8080;
}
```

### Tier 2: Uvicorn Upstream Trust Gating (`--forwarded-allow-ips`)
To prevent direct container access from bypassing the reverse proxy, configure Uvicorn to only accept forwarded IP headers if they arrive directly from the known internal IP address of your reverse proxy host.
In `deploy/docker-compose.yml`, pass the proxy's IP to Uvicorn:
```bash
uvicorn backend.main:app --forwarded-allow-ips="192.168.1.50"
```

### Tier 3: Network Level Gating (802.1X Wi-Fi & mTLS)
To elevate network trust beyond standard IP routing, organizations should enforce **802.1X Wi-Fi Authentication (EAP-TLS)** on campus networks. Alternatively, configure your reverse proxy to enforce **Mutual TLS (mTLS)**, requiring requesting personal devices to present a trusted client certificate before reaching the Gateway portal.

### Tier 4: Session Binding (Defense in Depth)
Even if an elite attacker successfully overcomes IP routing constraints on a local subnet, our Gateway architecture enforces strict **Google Sign-In OpenID Connect (OIDC) Bearer token validation**. An attacker cannot approve an unmanaged device simply by being on the network; they must also possess a valid, authenticated Google Workspace enterprise session for that target user.

---

## 📤 3. Outbound Traffic (Egress: Gateway to Google APIs)

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

### Google Cloud Secret Manager, Pub/Sub & Firestore
* `secretmanager.googleapis.com`: Required if the backend is configured to sync dynamic admin configurations with Google Cloud Secret Manager (`USE_SECRET_MANAGER=true`).
* `pubsub.googleapis.com`: Required for real-time event-driven Chromebook enrollment push webhooks with OIDC Bearer token authentication.
* `firestore.googleapis.com`: Required for distributed, concurrency-safe pairing code caching with atomic transaction validation.
