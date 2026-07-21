# **Product Requirements Document (PRD): Device Trust & Approval Portal**

## **1\. Executive Summary**

**Process Name:** Device Trust Gateway (Placeholder)

**Requirements:** Google for Education Plus or Standard with Licensing applied.

**Objective:** To mitigate unauthorized access by bad actors by strictly limiting environment access to approved devices. The solution provides a low-friction, secure workflow for end-users (primarily students and staff) to register their personal devices using a chained-trust or network-gated approval model.

## **2\. Problem Statement**

Organizations, particularly educational institutions, face constant threats from credential compromise (phishing, reused passwords). Even with Multi-Factor Authentication (MFA), bad actors can sometimes bypass protections. If an attacker gains credentials, they typically attempt access from an unmanaged, unknown device. Currently, blocking all personal devices creates too much friction, but allowing all devices leaves the environment vulnerable.

## **3\. Audience**

* **IT Administrators:** Need a scalable way to manage device trust without drowning in helpdesk tickets for device approvals.  
* **End Users (Students & Staff):** Need to access school/work resources (like Gmail, Drive) from personal devices (phones, home laptops) with minimal friction.

## **4\. Goals & Non-Goals**

**Goals:**

* Enforce a strict "Approved Devices Only" access policy using Google Workspace Context-Aware Access (CAA).  
* Provide a self-service mechanism for users to approve their personal devices.  
  * [Cloud Identity API: Devices Approval](https://docs.cloud.google.com/identity/docs/reference/rest/v1/devices.deviceUsers/approve)  
* Automate the lifecycle of device approvals (e.g., auto-revoke after inactivity).

**Non-Goals:**

* Deploying full Mobile Device Management (MDM) profiles to personal devices. (This is about *access approval*, not full device control).  
* Replacing existing company-owned inventory systems (e.g., Chrome Enterprise Upgrade).

## **5\. User Stories**

* **As an IT Admin,** I want to automatically trust all company-owned Chromebooks so that students have immediate access upon receiving their school device.  
* **As a Student,** I want to use my school-issued Chromebook to securely approve my personal smartphone so I can check my school email on the go.  
* **As a Staff Member,** I want to log into a portal while connected to the school's Wi-Fi to register my home desktop for weekend access.  
* **As a Security Lead,** I want inactive personal devices to automatically lose access after 3 months to minimize our attack surface.

## **6\. Proposed Solution & Features**

### **Feature 1: The Trust Anchor (Company-Owned Inventory)**

* **Description:** The baseline of trust. Devices uploaded to the organization's company-owned inventory (e.g., ChromeOS devices via zero-touch or manual CSV upload) are automatically granted an "Approved" status.  
* **Technical:** Relies on Google Admin console's native device management.

### **Feature 2: Trust Chaining Portal**

* **Description:** A web application where users can grant access to *new* devices by authenticating from an *already approved* device.  
* **Flow:**  
  1. User logs into the portal from their school-issued Chromebook.  
  2. User generates a temporary, time-bound pairing code or QR code.  
  3. User opens the portal on their unapproved personal phone and enters the code.  
  4. The backend registers the phone's device ID as "Approved" via the API.

### **Feature 3: Network-Gated Self-Service Portal**

* **Description:** An alternative to chaining. Users can approve a device by logging into a portal, provided they meet specific Context-Aware signals (e.g., coming from the school's trusted IP range).  
* **Flow:**  
  1. User brings their personal laptop to campus.  
  2. Connects to campus Wi-Fi (Trusted IP).  
  3. Logs into the portal and clicks "Register this Device".  
  4. Device is approved.

### **Feature 4: Automated Lifecycle Management**

* **Description:** Scripted backend cleanup to prevent stale devices from retaining access indefinitely.  
* **Flow:** A cron job evaluates the last sync/access time of BYOD devices. If last\_access \> X months, the device's approval status is revoked.

### **Feature 5: Identity-Aware Proxy (IAP) Edge Defense**

* **Description:** Gating the portal container itself at the network edge so that unauthenticated bad actors cannot access or scan the registration interface.
* **Flow:** Google Cloud Run ingress is restricted to Internal and Load Balancer traffic. An External HTTP(S) Load Balancer with Identity-Aware Proxy (IAP) and Access Context Manager enforces corporate IP subnets and/or company-owned device posture rules before traffic reaches the portal.

## **7\. Technical Architecture**

* **Identity & Access:** Google Workspace with Context-Aware Access (requires Cloud Identity Premium or Google Workspace Education Plus/Enterprise).  
* **Core API:** Google Cloud Identity Devices API (devices.create, devices.deviceUsers.approve).  
* **Backend:** A lightweight server/serverless function (e.g., Google Cloud Functions or App Engine) running Node.js or Python. This backend will authenticate users and make the elevated API calls to the Cloud Identity API, acting as the bridge.  
* **Frontend:** A simple, mobile-responsive web app for the self-service portal.

## **8\. Open Questions & Considerations**

* **Edge Case:** What happens if a user loses their only approved device (e.g., loses their Chromebook) and is not on campus? How do they bootstrap access? (e.g., Helpdesk intervention required).  
* **Licensing:** Ensure the target organization has the appropriate Google Workspace tier for advanced Context-Aware Access policies.