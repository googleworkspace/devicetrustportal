# Context-Aware Access (CAA) & Zero-Trust Architecture

The **Device Trust Gateway** is engineered to serve as the secure registration bridge for Google Workspace and Cloud Identity enterprise customers transitioning to a strict Zero-Trust access model. 

By leveraging **Google Workspace Context-Aware Access (CAA)** and **Google Cloud Identity-Aware Proxy (IAP)**, organizations can establish a military-grade security perimeter that protects both core enterprise resources (Gmail, Drive, SSO apps) and the Gateway portal itself.

---

## 🏛️ 1. The Core Whitepaper Blueprint: Context-Aware Access (CAA)

Google Workspace Context-Aware Access allows administrators to gate application access based on identity, device security posture, IP address, and geographic location.

### The Enterprise Challenge
Many organizations want to restrict access to "Approved Devices Only" to prevent data exfiltration from unmanaged, compromised hardware. However, enforcing intrusive Mobile Device Management (MDM) profiles on employee-owned personal hardware (BYOD) creates massive friction, privacy concerns, and support overhead.

### The Gateway Solution
Our Gateway decouples device approval from MDM enrollment. Employees install the lightweight, privacy-preserving **Endpoint Verification** browser extension. The device reports its certificate and security posture to Cloud Identity as "Unmanaged". 
When the employee successfully authorizes their device on our Gateway, our backend executes a secure API call (`service.devices().deviceUsers().approve`), setting the binding's `managementState` to `APPROVED`.

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

### Gating Workspace Applications (The CAA Policy Rule)
To enforce this across your tenant, navigate to **Google Workspace Admin Console > Security > Access and data control > Context-Aware Access** (`https://admin.google.com/ac/security/contextaware`) and create a Custom Access Level using this exact Common Expression Language (CEL) rule:

```text
device.is_corp_owned == true || device.is_admin_approved == true
```
* **`device.is_corp_owned == true`:** Automatically permits access from corporate hardware trust anchors (e.g., zero-touch Chromebooks, company-owned Macs).
* **`device.is_admin_approved == true`:** Automatically permits access from personal BYOD hardware that has been vetted and approved via our Gateway portal!

---

## 🔒 2. Gating the Gateway Portal at the Edge (Google Cloud IAP)

While CAA protects your Workspace applications, how do you protect the Gateway portal itself from being accessed by unauthorized external attackers? 
You can restrict access to the Gateway UI so that it can **only** be reached from company-owned hardware or trusted corporate IP ranges by placing Cloud Run behind **Identity-Aware Proxy (IAP)**.

```
+-----------------------------------------------------------------------------------+
|                           External Public Internet                                |
|                    (Attacker attempts access from coffee shop)                    |
+-----------------------------------------+-----------------------------------------+
                                          |
                                          v
+-----------------------------------------------------------------------------------+
|                   Google Cloud External HTTP(S) Load Balancer                     |
+-----------------------------------------+-----------------------------------------+
                                          |
                                          v
+-----------------------------------------------------------------------------------+
|                     Identity-Aware Proxy (IAP) Edge Gating                        |
|                                                                                   |
|  [ ACCESS LEVEL: ip_subnetworks: ["10.0.0.0/8"] OR device.is_corp_owned ]         |
|  [ RESULT: Blocks external attacker with 403 Access Denied at edge ]              |
+-----------------------------------------+-----------------------------------------+
                                          |
                                          v
+-----------------------------------------------------------------------------------+
|                      Cloud Run Container (Gateway Backend)                        |
+-----------------------------------------------------------------------------------+
```

### Step-by-Step IAP Configuration Blueprint:
1. **Remove Public Access:** Ensure your Cloud Run service does not allow unauthenticated access (`gcloud run services remove-iam-policy-binding device-trust-gateway --member="allUsers" --role="roles/run.invoker"`).
2. **Deploy External Load Balancer:** Configure a GCP External HTTP(S) Load Balancer with a Serverless Network Endpoint Group (NEG) pointing to your Cloud Run service.
3. **Enable IAP:** In the GCP Console (**Security > Identity-Aware Proxy**), enable IAP on your Load Balancer backend service.
4. **Configure Access Context Manager:** Open **Security > Access Context Manager** and create an Access Level that establishes your mandatory edge guardrails:
   - **IP Subnets:** Add your corporate CIDR ranges (e.g., `10.0.0.0/8`, `192.168.1.0/24`).
   - **Device Posture:** Require `Company Owned` device posture.
5. **Bind Access Level to IAP:** In the IAP console, bind this Access Level to your Gateway resource. If an unmanaged device outside your corporate network attempts to hit your portal URL, IAP instantly blocks them at the edge with a `403 Access Denied` screen!

---

## 🔄 3. System Lifecycle Management

To maintain an immaculate Zero-Trust posture, approved BYOD hardware should not retain permanent access indefinitely.

Our Gateway backend exposes a secure automated lifecycle endpoint (`/api/cron/cleanup`). When invoked by a background **Google Cloud Scheduler** cron job, the backend crawls Cloud Identity for all BYOD hardware whose `lastSyncTime` exceeds your configured inactivity threshold (e.g., 90 days). 
The backend automatically executes `service.devices().deviceUsers().delete(...)` to revoke their approval. The next time that stale device attempts to access Gmail, Context-Aware Access instantly blocks them, requiring them to re-register through the Gateway!
