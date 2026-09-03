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

### Gating Workspace Applications (The CAA Policy Rule)
To enforce this across your tenant, navigate to **Google Workspace Admin Console > Security > Access and data control > Context-Aware Access** (`https://admin.google.com/ac/security/contextaware`) and create a Custom Access Level using this exact Common Expression Language (CEL) rule:

```text
device.is_corp_owned_device == true || device.is_admin_approved_device == true
```

#### Detailed Breakdown of the CEL Expression:
| Expression Clause | Device Category & Definition | Approval Flow |
| :--- | :--- | :--- |
| **`device.is_corp_owned_device == true`** | **Company-Owned Hardware Trust Anchors:** Hardware serial numbers registered in Google Workspace as enterprise/district inventory (`ownerType: COMPANY`). Includes zero-touch enterprise-enrolled Chromebooks and district laptops imported via CSV. | **Automatic / Direct Access:** Automatically permitted to access Gmail, Drive, Classroom, etc. without needing self-service portal approval. |
| **`device.is_admin_approved_device == true`** | **Admin / Portal Approved BYOD Devices:** Personal employee/student hardware (`ownerType: BYOD`) where the user binding in Cloud Identity has been set to `managementState: APPROVED`. | **Gated / Portal Approval:** Starts in a blocked state. Access is restored once the user approves the device via the Device Trust Portal (using 6-digit Trust Chaining or campus network auth). |

> [!NOTE]
> The logical **`||` (OR)** operator guarantees that enterprise fleet machines (Chromebooks) enjoy frictionless, uninterrupted access, while personal home laptops (Macs & PCs) must be verified and authorized before reaching sensitive Workspace data.
1. **Target Organizational Unit (OU) Selection:** In **Assign to apps**, **do NOT leave this policy assigned to the Root Organizational Unit (`/`)**. The Admin Console defaults to the Root OU, which will immediately enforce the rule domain-wide on all users (including Super Admins and faculty) and can result in severe lockouts. Instead, explicitly select a specific target OU (such as **`Students` OU** or a dedicated **`Test / Pilot OU`**) to isolate policy enforcement.
2. **App Assignment:** Assign this level to the Workspace Apps of your choice (eg. Gmail, Drive…).
3. **Enforcement Policy:** Set policies to **Block** when policies / access levels are not met (ensures access is restricted rather than just audited in Monitor Mode).
4. **Desktop & Mobile Apps:** Ensure policy is set to Enable for **Apply to Google desktop and mobile apps** (ensuring native desktop clients like Google Drive for Desktop and mobile apps like Gmail iOS/Android are evaluated alongside web browsers).

---

## 🔒 2. Gating the Gateway Portal at the Edge: Standard Mode vs. IAP Edge Defense

Organizations can deploy the Gateway in one of two distinct ingress architectures based on their organizational policy and remote access requirements:

### Architectural Comparison:

| Dimension | Standard Mode (Default / Recommended for Schools) | Strict IAP Edge Defense Mode (On-Premise / Corporate) |
| :--- | :--- | :--- |
| **Ingress Point** | Direct Cloud Run HTTPS Service URL | Cloud HTTPS Load Balancer + Identity-Aware Proxy (IAP) |
| **Authentication** | Google Workspace OAuth 2.0 Sign-In + Trust Chaining | Google Cloud Identity-Aware Proxy (IAP) Edge Gating |
| **Remote Access** | Accessible anywhere with valid Google credentials | Restricted to configured corporate IP CIDRs / VPN |
| **BYOD Homework Flow** | **Seamless:** Students at home generate a 6-digit pairing code on their school Chromebook to approve their home PC | **Blocked:** Personal devices at home cannot reach the portal or approve hardware without a district VPN |
| **Ideal For** | K-12 School Districts, Higher Ed, Hybrid Workplaces | Financial Services, Defense, Strict On-Premise Only |

---

### Understanding the School & Homework Trade-Off:
> [!IMPORTANT]
> **Why Schools Default to Standard Mode (No IAP):**
> In K-12 and university environments, students frequently need to access Google Classroom, Drive, and Workspace apps from personal home desktops/laptops in the evening to complete homework.
> 
> * **With Standard Mode:** The student signs into the portal on their managed school Chromebook, clicks **Generate Pairing Code**, and enters the 6-digit code on their home laptop. The home laptop is approved immediately and securely.
> * **With Strict IAP Edge Defense:** Because the home IP address is not part of the school district's campus network, IAP blocks the student at the network edge with a `403 Forbidden` error. The student cannot get their device approved and is locked out of their homework until they return to school the next day.

---

### Step-by-Step IAP Configuration Blueprint (For Strict On-Premise Deployments):
If your security policy mandates that BYOD device approvals must occur exclusively while connected to the campus network or an enterprise VPN:

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
|  [ ACCESS LEVEL: ip_subnetworks: ["10.0.0.0/8"] OR device.is_corp_owned_device ]  |
|  [ RESULT: Blocks external attacker with 403 Access Denied at edge ]              |
+-----------------------------------------+-----------------------------------------+
                                          |
                                          v
+-----------------------------------------------------------------------------------+
|                      Cloud Run Container (Gateway Backend)                        |
+-----------------------------------------------------------------------------------+
```

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
