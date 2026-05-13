# High-Level Architecture: Context-Aware Access (CAA), Device Approvals & Company-Owned Inventory

This document provides a high-level architectural overview of how the **Device Trust Gateway** interacts with Google Workspace Context-Aware Access (CAA), Cloud Identity Device Approvals, and Company-Owned hardware inventory to establish a zero-trust access model without compromising end-user privacy or introducing deployment friction.

---

## 🌐 1. The Zero-Trust Access Architecture

In a traditional security perimeter, access is gated purely by network location or valid user credentials. In a modern Zero-Trust architecture, Google Workspace Context-Aware Access (CAA) continuously evaluates dynamic user and device signals before granting access to core applications (Gmail, Drive, Calendar, etc.).

```
+-------------------------------------------------------------------------------+
|                        Context-Aware Access (CAA) Engine                      |
|                                                                               |
|   [ Access Level Policy: (device.is_corp_owned OR device.is_admin_approved) ] |
+---------------------------------------+---------------------------------------+
                                        |
                    +-------------------+-------------------+
                    | (Evaluates Client Signals)            |
                    v                                       v
    +-------------------------------+       +-------------------------------+
    |  Company-Owned Trust Anchor   |       |    BYOD Personal Hardware     |
    |  (ChromeOS Zero-Touch Fleet)  |       |  (Unmanaged + Endpoint Verif.)|
    +-------------------------------+       +-------------------------------+
                    |                                       |
                    | (Pre-Approved)                        | (Requires Approval)
                    v                                       v
    +-------------------------------+       +-------------------------------+
    |    Immediate Resource Access  |       |  Device Trust Gateway Portal  |
    +-------------------------------+       +-------------------------------+
```

---

## 🛡️ 2. Component Breakdown & Interplay

### A. Context-Aware Access (CAA) Access Levels
CAA acts as the policy enforcement engine. Administrators configure Custom Access Levels in the Google Cloud Console that define required device attributes. For our portal, the target access level policy expression is:
```cel
device.is_corp_owned == true || device.is_admin_approved == true
```
*This rule dictates that to access Google Workspace, the requesting session must originate from either a company-owned hardware asset OR an unmanaged personal device that has received explicit administrator approval.*

### B. Company-Owned Inventory (The Trust Anchor)
Company-owned devices represent the baseline of trust anchors.
- **ChromeOS Devices:** Automatically added to company inventory upon enterprise enrollment (or via zero-touch enrollment).
- **Automated Seeding:** For organizations with large existing fleets, our backend automation script (`seed_company_inventory.py`) paginates through the Google Workspace Admin SDK to batch register and anchor available hardware directly in Cloud Identity.

### C. Device Approvals (`devices.deviceUsers.approve`)
For personal BYOD hardware (smartphones, home desktops, personal laptops), blocking access entirely creates extreme friction, while allowing unverified access exposes the organization to compromised credential attacks. 
Our Gateway backend utilizes the Google Cloud Identity REST API to execute `devices.deviceUsers.approve`. This elevates the device's approval state to `APPROVED`, satisfying the CAA `device.is_admin_approved == true` signal.

---

## 📱 3. Unmanaged vs. Managed Hardware: The BYOD Privacy Advantage

A critical advantage of this architecture is that **personal BYOD devices do NOT require Mobile Device Management (MDM) enrollment or restrictive profiles.**

```
+---------------------------------------------------------------------------+
|                           Cloud Identity Management Tiers                 |
+------------------------------------+--------------------------------------+
|      Full MDM Enrollment           |    Endpoint Verification (Unmanaged) |
|  (Company Hardware / Advanced MDM) |     (Personal BYOD Laptops & Phones) |
+------------------------------------+--------------------------------------+
| - Intrusive device control         | - Lightweight browser extension      |
| - Remote wipe capability           | - Collects device cert & basic OS info|
| - Enforces password policies       | - Zero control over personal apps    |
| - High friction for personal hardware| - Low friction, privacy-preserving   |
+------------------------------------+--------------------------------------+
```

### How Unmanaged Approval Works:
1. **Registration:** The user installs the lightweight **Endpoint Verification** Chrome extension (or Google Workspace mobile app).
2. **Signal Collection:** Endpoint Verification securely generates a device certificate and reports basic identifying metadata (OS version, device ID) to Cloud Identity. The device is classified as **Unmanaged**.
3. **Gateway Elevation:** The user logs into our Device Trust Gateway portal. Upon verifying a pairing code or campus network connection, the backend executes `devices.deviceUsers.approve`.
4. **Access Granted:** The unmanaged personal device retains total user privacy (no MDM control) while successfully satisfying the enterprise CAA access level.

---

## 📋 4. Step-by-Step Setup Guide for Workspace Admins

To enable this workflow in your Google Workspace / Cloud Identity tenant:

1. **Enable Endpoint Verification:** In the Google Workspace Admin console, navigate to *Devices > Mobile & endpoints > Settings > Universal settings > Endpoint Verification* and check "Enable Endpoint Verification".
2. **Enable Approved Device Management:** Navigate to *Devices > Mobile & endpoints > Settings > Universal settings > Security* and ensure **Device Approvals** is set to "Requires Admin Approval" (so devices do not bypass gating automatically).
3. **Create Custom Access Level:** Open the Google Cloud Console, navigate to *Security > Access Context Manager*, and create an access level using the Custom CEL expression: `device.is_corp_owned == true || device.is_admin_approved == true`.
4. **Assign CAA Policy:** In the Workspace Admin console, navigate to *Security > Access and data control > Context-Aware Access*, select your target applications (e.g. Google Drive, Gmail), and assign the newly created Access Level.
