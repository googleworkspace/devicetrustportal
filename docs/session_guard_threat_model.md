# Device Trust Portal — Session Guard Threat Model & Stolen-Cookie Defense

This document specifies the threat model, enforcement pathways, and administrative configuration for blocking stolen session cookies and credential hijacking across **Google Workspace for Education Fundamentals** and **Education Standard / Plus**.

---

## 1. Extension Architecture Clarification

* **Education Standard / Plus (Context-Aware Access)**:
  - Uses the official, first-party **Google Endpoint Verification extension** (`callobklhcbilhphinckomhgkigmfocg`) force-installed from the Chrome Web Store via Google Admin Console (`Devices > Chrome > Apps & extensions > Users & browsers`).
  - Collects hardware serial numbers, OS posture, and cryptographic device certificates, syncing them into Google Cloud Identity. Zero custom extension code is required.
* **Education Fundamentals (Zero-CAA Session Watch)**:
  - The server-side session guard (`backend/services/session_guard.py`) operates **100% server-side** using standard Google Admin SDK APIs:
    - **`admin.reports_v1`**: Audit event streams for `login` and `token` (OAuth grants/refreshes).
    - **`admin.directory_v1`**: Hardware inventory (`chromeosdevices.list`) and the session circuit breaker (`users.signOut`).
    - **`cloudidentity.v1`**: Approved desktop/mobile inventory (`devices.list`).
  - **No custom Chrome extension is required.** It cross-references incoming server-side audit events directly against the district's cached approved device inventory.

---

## 2. Admin Configuration Settings (Disabled by Default)

Because automated session termination (`admin.directory_v1.users.signOut`) is a mutating security action, Session Guard and automated cookie revocation must be **disabled by default**. Administrators must explicitly opt in after confirming that their device inventory is pre-warmed.

In `TenantConfig` (`backend/services/config_service.py`):

```python
class TenantConfig(BaseModel):
    # Existing settings...
    customer_id: str = Field(default="customers/my_customer")
    portal_admins: List[str] = Field(default=[])

    # Session Guard & Stolen-Cookie Defense Settings (OFF BY DEFAULT)
    enable_session_guard: bool = Field(
        default=False,
        description="Master switch: Enable automated session monitoring and token revocation for unattested/unapproved devices.",
    )
    session_guard_grace_window_sec: int = Field(
        default=45,
        description="Grace window (seconds) to allow device telemetry/inventory matching before revoking.",
    )
    session_guard_watch_token_stream: bool = Field(
        default=False,
        description="Monitor Admin SDK 'token' audit stream to detect mid-session OAuth pivots on foreign IPs.",
    )
    session_guard_block_hosting_asns: bool = Field(
        default=False,
        description="Automatically trigger users.signOut when sessions originate from datacenter/cloud hosting ASNs (Cloudflare, AWS, etc.).",
    )
```

---

## 3. The Three Stolen-Cookie & Credential Hijacking Pathways

```
                                  STOLEN COOKIE ATTACK VECTORS
                                                │
         ┌──────────────────────────────────────┼──────────────────────────────────────┐
         ▼                                      ▼                                      ▼
   [Pathway 1: AiTM]                   [Pathway 2: Infostealer]              [Pathway 3: Mid-Session]
 Victim phished via proxy             Malware steals cookie from            Active cookie exfiltrated from
 (Evilginx) at login time.            unapproved home PC.                   approved laptop to foreign VPS.
         │                                      │                                      │
   Blocked at Sign-In:                    Blocked at Sign-In:                    Blocked Inline (Plus/CAA) or
   Attacker IP lacks approved             Home PC lacks approved                 via Token/ASN Monitor (Fund.):
   inventory match -> signOut             inventory match -> signOut             foreign IP/ASN -> signOut
```

---

### Pathway 1: Adversary-in-the-Middle (AiTM) / Reverse-Proxy Phishing

#### Attack Mechanism
1. A student or staff member receives a phishing link (e.g., via fake Google Docs share or email) pointing to an AiTM reverse proxy (such as Evilginx).
2. The victim enters their genuine Workspace username, password, and 2-step verification code into the attacker's proxy.
3. The proxy relays these credentials to Google's real authentication servers in real time, completing the login and receiving Google's session cookies (`__Secure-1PSID`, `SID`, `HSID`, `SSID`).
4. The proxy steals the newly minted session cookies and hands them to the threat actor, allowing them to access Workspace without needing the password again.

#### How Device Trust Portal Blocks It
* **Authentication Audit Signal**: The login completed by the proxy triggers a `login_success` event in `admin.reports_v1` (`applicationName='login'`).
* **Enforcement Action**: The login event reveals the attacker's egress IP and browser client. In `devicetrustportal`:
  - **In Standard/Plus (CAA)**: The proxy connection does not originate from an approved device enrolled with Endpoint Verification. CAA blocks access inline.
  - **In Fundamentals (`session_guard.py`)**: The login event has no corresponding approved device record in the district's pre-warmed inventory. After the 45-second grace window, `session_guard.py` calls `admin.directory_v1.users.signOut(userKey=email)`.
* **Outcome**: The newly minted session cookies are revoked across Google Workspace before the attacker can utilize them.

---

### Pathway 2: Infostealer Malware on Unapproved / Personal Devices

#### Attack Mechanism
1. A student or staff member logs into their school Google Workspace account on an unmanaged personal computer (e.g., a home gaming desktop or personal Mac) infected with infostealer malware (Lumma, RedLine, Vidar, Stealc).
2. The malware accesses the browser's local profile directory on disk and decrypts the SQLite cookie database, extracting persistent Google session tokens.
3. The stolen session cookies are exfiltrated to a Telegram bot or command-and-control (C2) server and sold on dark web marketplaces.

#### How Device Trust Portal Blocks It
* **Zero-Trust Baseline**: In an approved-devices-only architecture, personal unapproved computers are never authorized to hold active district sessions.
* **Enforcement Action**:
  - **In Standard/Plus (CAA)**: Context-Aware Access blocks access inline from the personal computer because it lacks the Company-Owned status or Endpoint Verification certificate.
  - **In Fundamentals (`session_guard.py`)**: The sign-in on the unmanaged computer triggers a `login` audit event. `session_guard.py` evaluates the login against the approved hardware inventory (`chromeosdevices.list` + Cloud Identity approved devices). Identifying an unapproved device, it immediately executes `users.signOut`.
* **Outcome**: The session on the compromised home computer is terminated within ~45–90 seconds of login. By the time the infostealer exfiltrates the SQLite cookie file, the session cookies are already invalid and dead at Google's authentication layer.
* *(Note: On managed district Chromebooks, session cookies are protected in hardware by the TPM via ChromeOS `cryptohome` and cannot be harvested by user-space binaries).*

---

### Pathway 3: Mid-Session Cookie Exfiltration & Datacenter / Proxy Replay

#### Attack Mechanism
1. A user is actively working on a **legitimate, approved district device** (e.g., an approved staff Windows laptop).
2. Through a malicious browser extension, local compromise, or physical access, the active session cookie (`__Secure-1PSID`) is extracted *mid-session* (hours after the initial login).
3. The attacker loads the stolen cookie into a headless browser or VPS hosted on a cloud datacenter network (e.g., Cloudflare Workers/WARP, AWS EC2, DigitalOcean, or Latitude.sh in Mexico, as observed in recent district security alerts).
4. Because the session cookie is already authenticated, the attacker accesses `mail.google.com` or `drive.google.com` **without generating a new `login` event**.

#### How Device Trust Portal Blocks It

##### A. In Education Standard / Plus (Context-Aware Access)
* **Status**: **Blocked Inline (Immediate)**.
* **Mechanism**: Context-Aware Access evaluates device posture on **every HTTP request** to Gmail, Drive, and Classroom—not just at login time.
* When the attacker replays the cookie from their foreign server/browser, the request lacks the Google Endpoint Verification certificate and client hardware signature.
* Even though the cookie is technically valid, Google's frontend gateways reject the request with HTTP 403 / Access Denied (`DENIED GMAIL`).

##### B. In Education Fundamentals (Without Context-Aware Access)
* **Status**: Blocked via **Token Stream Monitoring + Datacenter ASN Sentinel**.
* **Mechanism**: Since replaying an existing web cookie does not fire a `login` event, `session_guard.py` monitors the **`admin.reports_v1` `token` audit stream**:
  1. Whenever the hijacked session makes API calls, interacts with Workspace Add-ons, or accesses OAuth-connected clients, Google logs a `token` activity event with the actor's IP address.
  2. `session_guard.py` inspects the autonomous system number (ASN) and IP of the event:
     - **Datacenter/Hosting ASN Check**: If the IP belongs to a known cloud hosting provider (Cloudflare AS13335, Latitude.sh AS396356, AWS, etc.) rather than an educational or residential ISP, it is flagged as high-risk.
     - **Impossible Travel / Geolocation Jump**: If the IP is geolocated thousands of miles away from the user's recent activity within a sub-hour window, it indicates stolen credential replay.
  3. When an anomaly is detected, `session_guard.py` triggers `users.signOut`, revoking the entire session across all devices.

---

## 4. Summary Matrix

| Threat Vector | Attack Method | Standard / Plus (CAA) | Fundamentals (`session_guard.py`) |
| :--- | :--- | :--- | :--- |
| **Pathway 1: AiTM Phishing** | Real-time proxy intercepts password & 2FA to mint session | **Blocked Inline** (Device lacks EV certificate) | **Blocked within 45–90s** (`login` event lacks inventory match -> `users.signOut`) |
| **Pathway 2: Unmanaged PC Infostealer** | Malware scrapes browser cookies from home PC | **Blocked Inline** (Unenrolled / unapproved machine) | **Blocked within 45–90s** (Initial login terminated before cookies can be reused) |
| **Pathway 3: Mid-Session Cookie Replay** | Cookie stolen from approved laptop, replayed from foreign VPS | **Blocked Inline** (CAA checks device cert on every service request) | **Blocked via Token/ASN Monitor** (`token` stream detects hosting ASN/IP jump -> `users.signOut`) |
