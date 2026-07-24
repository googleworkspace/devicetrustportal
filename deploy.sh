#!/usr/bin/env bash
# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# Enforce UTF-8 character encoding stability across international deployment environments
export LANG=C.UTF-8
export LC_ALL=C.UTF-8

# Device Trust Gateway - Automated Deployment & Setup Script

set -e

GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Helper function for interactive Domain-Wide Delegation (DWD) Setup
setup_domain_wide_delegation() {
    echo -e "\n${YELLOW}===================================================================================================${NC}"
    echo -e "${YELLOW}      Google Workspace Domain-Wide Delegation (DWD) Setup Wizard                                  ${NC}"
    echo -e "${YELLOW}===================================================================================================${NC}"
    echo -e "Live API calls to Google Workspace Admin Directory and Cloud Identity require a Service Account"
    echo -e "configured with Domain-Wide Delegation (DWD) and a designated Super Administrator email to impersonate."
    echo ""
    
    if [ -z "$GCP_PROJECT" ]; then
        read -p "Enter your Google Cloud Project ID: " GCP_PROJECT
    fi
    
    SA_NAME="device-trust-gateway-sa"
    SA_EMAIL="${SA_NAME}@${GCP_PROJECT}.iam.gserviceaccount.com"
    
    echo -e "\n${BLUE}[1/5] Verifying Service Account '$SA_EMAIL'...${NC}"
    if ! gcloud iam service-accounts describe "$SA_EMAIL" --project="$GCP_PROJECT" &>/dev/null; then
        echo "Creating new Service Account '$SA_NAME'..."
        gcloud iam service-accounts create "$SA_NAME" \
            --display-name="Device Trust Gateway Service Account for DWD" \
            --project="$GCP_PROJECT" --quiet
    else
        echo -e "${GREEN}✔ Service Account exists.${NC}"
    fi
    
    echo -e "\n${BLUE}[2/5] Generating JSON Private Key...${NC}"
    KEY_FILE="dwd_key.json"
    if [ ! -f "$KEY_FILE" ]; then
        gcloud iam service-accounts keys create "$KEY_FILE" \
            --iam-account="$SA_EMAIL" \
            --project="$GCP_PROJECT" --quiet
        echo -e "${GREEN}✔ JSON key downloaded to '$(pwd)/$KEY_FILE'.${NC}"
    else
        echo -e "${GREEN}✔ Existing key file '$KEY_FILE' detected.${NC}"
    fi
    
    echo -e "\n${BLUE}[3/5] Securing DWD Private Key in Secret Manager...${NC}"
    KEY_SECRET_NAME="device_trust_gateway_dwd_key"
    if ! gcloud secrets describe "$KEY_SECRET_NAME" --project="$GCP_PROJECT" &>/dev/null; then
        echo "Creating Secret Manager secret '$KEY_SECRET_NAME'..."
        gcloud secrets create "$KEY_SECRET_NAME" --replication-policy="automatic" --project="$GCP_PROJECT" --quiet
        gcloud secrets versions add "$KEY_SECRET_NAME" --data-file="$KEY_FILE" --project="$GCP_PROJECT" --quiet
    else
        echo -e "${GREEN}✔ Secret '$KEY_SECRET_NAME' already securely stored.${NC}"
    fi
    
    # Explicitly grant Secret Manager Accessor permissions to our dedicated DWD service account for DWD Key
    echo "Granting Secret Accessor IAM binding to '$SA_EMAIL' for DWD Key..."
    gcloud secrets add-iam-policy-binding "$KEY_SECRET_NAME" \
        --member="serviceAccount:$SA_EMAIL" \
        --role="roles/secretmanager.secretAccessor" \
        --project="$GCP_PROJECT" --quiet > /dev/null 2>&1 || echo "IAM binding already configured."
        
    echo -e "\n${BLUE}[4/5] Retrieving Service Account Client ID...${NC}"
    CLIENT_ID=$(gcloud iam service-accounts describe "$SA_EMAIL" --project="$GCP_PROJECT" --format="value(oauth2ClientId)" 2>/dev/null || gcloud iam service-accounts describe "$SA_EMAIL" --project="$GCP_PROJECT" --format="value(uniqueId)")
    
    echo -e "\n${RED}===================================================================================================${NC}"
    echo -e "${YELLOW}🔑 REQUIRED WORKSPACE ADMIN CONSOLE ACTION:${NC}"
    echo -e "To authorize this Service Account to read Chromebook fleets and approve BYOD devices:"
    echo -e "  1. Open the Google Workspace Admin Console: https://admin.google.com/ac/owl/domainwidedelegation"
    echo -e "  2. Click ${YELLOW}'Add new'${NC}."
    echo -e "  3. In the ${YELLOW}'Client ID'${NC} field, copy and paste this exact numeric ID:"
    echo -e "     ${GREEN}${CLIENT_ID}${NC}"
    echo -e "  4. In the ${YELLOW}'OAuth Scopes'${NC} field, copy and paste this exact comma-separated string:"
    echo -e "     ${GREEN}https://www.googleapis.com/auth/cloud-identity.devices,https://www.googleapis.com/auth/admin.directory.user.readonly,https://www.googleapis.com/auth/admin.directory.group.member.readonly,https://www.googleapis.com/auth/admin.directory.device.chromeos.readonly${NC}"
    echo -e "  5. Click ${YELLOW}'Authorize'${NC}."
    echo -e "${RED}===================================================================================================${NC}\n"
    
    read -p "Press [ENTER] when Domain-Wide Delegation has been successfully authorized in the Workspace Admin console..."
    
    echo ""
    CURRENT_EMAIL=$(gcloud config get-value account 2>/dev/null || true)
    if [ -n "$CURRENT_EMAIL" ] && [[ "$CURRENT_EMAIL" != *"gserviceaccount.com"* ]]; then
        read -p "Enter the email address of a Workspace Super Administrator to impersonate [${CURRENT_EMAIL}]: " ADMIN_EMAIL
        ADMIN_EMAIL=${ADMIN_EMAIL:-$CURRENT_EMAIL}
    else
        read -p "Enter the email address of a Workspace Super Administrator to impersonate (e.g., admin@yourdomain.com): " ADMIN_EMAIL
    fi
    
    export GOOGLE_APPLICATION_CREDENTIALS="$(pwd)/$KEY_FILE"
    export WORKSPACE_ADMIN_EMAIL="$ADMIN_EMAIL"
    export DWD_SA_EMAIL="$SA_EMAIL"
    
    echo -e "\n${GREEN}✔ DWD Setup Complete! Credentials exported for live API execution.${NC}"
}

# Helper function for executing mass BYOD revocation sweep
execute_mass_revocation_prompt() {
    echo -e "\n${YELLOW}--- Mass BYOD Approval Revocation (Pristine Zero-Trust Baseline) ---${NC}"
    echo "Would you like to execute a mass revocation sweep across Cloud Identity, unapproving all personal BYOD devices to establish a pristine Zero-Trust baseline?"
    echo "Note: This operation preserves company-owned hardware and ChromeOS assets but revokes all personal device approvals across your entire tenant catalog."
    read -p "Execute Mass Revocation Sweep? (y/n): " DO_MASS_REVOKE
    
    if [[ "$DO_MASS_REVOKE" =~ ^[Yy]$ ]]; then
        if [ -z "$WORKSPACE_ADMIN_EMAIL" ]; then
            setup_domain_wide_delegation
        fi
        
        echo -e "\n${BLUE}Launching live mass revocation script...${NC}"
        if [ -d "backend/venv" ]; then
            source backend/venv/bin/activate
        elif [ -d "venv" ]; then
            source venv/bin/activate
        else
            python3 -m venv backend/venv && source backend/venv/bin/activate
            pip install --quiet -r backend/requirements.txt --index-url https://pypi.org/simple
        fi
        python3 backend/scripts/mass_revoke_byod_approvals.py
    else
        echo -e "${BLUE}Skipping mass revocation sweep.${NC}"
    fi
}

# Helper function for Chromebook fleet inventory seeding
configure_inventory_seeding() {
    local GATEWAY_URL="$1"
    
    echo -e "\n${YELLOW}--- Chromebook Fleet Inventory Seeding Configuration ---${NC}"
    echo "Would you like to configure automated Chromebook Fleet Inventory Seeding to anchor enterprise devices in Cloud Identity?"
    read -p "Configure Seeding? (y/n): " DO_SEED
    
    if [[ "$DO_SEED" =~ ^[Yy]$ ]]; then
        echo ""
        echo "Select scheduling frequency for synchronizing active Directory Chromebooks with Cloud Identity:"
        echo "  1) One-Time Execution (Run Crawl Now)"
        echo "  2) Daily Recurring Schedule (GCP Cloud Scheduler Cron)"
        echo "  3) Weekly Recurring Schedule (GCP Cloud Scheduler Cron)"
        echo "  4) Event-Driven Real-Time Webhook (Pub/Sub Push) + Weekly Safety Net"
        echo ""
        read -p "Enter option [1-4]: " SEED_OPTION
        
        # For options that require a public gateway URL, ensure we have one
        if [[ "$SEED_OPTION" =~ ^[234]$ ]]; then
            if [ -z "$GATEWAY_URL" ] || [[ "$GATEWAY_URL" == *"localhost"* ]] || [[ "$GATEWAY_URL" == *"127.0.0.1"* ]]; then
                echo -e "${YELLOW}Warning: GCP Cloud Scheduler and Pub/Sub Push require a publicly accessible HTTPS URL.${NC}"
                read -p "Enter your public Gateway URL (e.g., https://yourgateway.com): " CUSTOM_URL
                GATEWAY_URL="$CUSTOM_URL"
            fi
            if [ -z "$GATEWAY_URL" ]; then
                echo -e "${RED}Error: Public Gateway URL is required for this option. Skipping seeding configuration.${NC}"
                return
            fi
            # Remove trailing slash if present
            GATEWAY_URL="${GATEWAY_URL%/}"
        fi
        
        case $SEED_OPTION in
          1)
            if [ -z "$WORKSPACE_ADMIN_EMAIL" ]; then
                setup_domain_wide_delegation
            fi
            
            echo -e "\n${BLUE}Launching live inventory seeding script...${NC}"
            if [ -d "backend/venv" ]; then
                source backend/venv/bin/activate
            elif [ -d "venv" ]; then
                source venv/bin/activate
            else
                python3 -m venv backend/venv && source backend/venv/bin/activate
                pip install --quiet -r backend/requirements.txt --index-url https://pypi.org/simple
            fi
            python3 backend/scripts/seed_company_inventory.py
            ;;
          2)
            echo -e "\n${BLUE}Configuring Daily GCP Cloud Scheduler Job...${NC}"
            if [ -z "$GCP_PROJECT" ]; then
                read -p "Enter your Google Cloud Project ID: " GCP_PROJECT
            fi
            read -p "Enter target Cloud Scheduler region [us-central1]: " GCP_REGION
            GCP_REGION=${GCP_REGION:-us-central1}
            
            gcloud scheduler jobs create http seed-chromebook-inventory-daily \
                --schedule="0 2 * * *" \
                --uri="${GATEWAY_URL}/api/cron/cleanup" \
                --http-method=POST \
                --headers="X-Cloudscheduler=true" \
                --location="$GCP_REGION" \
                --project="$GCP_PROJECT" \
                --description="Daily crawl of active Chromebooks for Cloud Identity anchoring" --quiet 2>/dev/null || echo "Scheduler job already configured."
                
            echo -e "${GREEN}✔ Daily Cloud Scheduler Job configured successfully! (Runs at 2:00 AM daily)${NC}"
            ;;
          3)
            echo -e "\n${BLUE}Configuring Weekly GCP Cloud Scheduler Job...${NC}"
            if [ -z "$GCP_PROJECT" ]; then
                read -p "Enter your Google Cloud Project ID: " GCP_PROJECT
            fi
            read -p "Enter target Cloud Scheduler region [us-central1]: " GCP_REGION
            GCP_REGION=${GCP_REGION:-us-central1}
            
            gcloud scheduler jobs create http seed-chromebook-inventory-weekly \
                --schedule="0 3 * * 0" \
                --uri="${GATEWAY_URL}/api/cron/cleanup" \
                --http-method=POST \
                --headers="X-Cloudscheduler=true" \
                --location="$GCP_REGION" \
                --project="$GCP_PROJECT" \
                --description="Weekly crawl of active Chromebooks for Cloud Identity anchoring" --quiet 2>/dev/null || echo "Scheduler job already configured."
                
            echo -e "${GREEN}✔ Weekly Cloud Scheduler Job configured successfully! (Runs at 3:00 AM every Sunday)${NC}"
            ;;
          4)
            echo -e "\n${BLUE}Configuring Event-Driven Pub/Sub Push Webhook & Weekly Cron Safety Net...${NC}"
            if [ -z "$GCP_PROJECT" ]; then
                read -p "Enter your Google Cloud Project ID: " GCP_PROJECT
            fi
            read -p "Enter target GCP region [us-central1]: " GCP_REGION
            GCP_REGION=${GCP_REGION:-us-central1}
            
            TOPIC_NAME="chrome-enrollment-events"
            echo "Verifying Pub/Sub topic '$TOPIC_NAME'..."
            gcloud pubsub topics create "$TOPIC_NAME" --project="$GCP_PROJECT" --quiet 2>/dev/null || echo "Topic already exists."
            
            SA_NAME="device-trust-gateway-sa"
            SA_EMAIL="${SA_NAME}@${GCP_PROJECT}.iam.gserviceaccount.com"
            if ! gcloud iam service-accounts describe "$SA_EMAIL" --project="$GCP_PROJECT" &>/dev/null; then
                gcloud iam service-accounts create "$SA_NAME" --display-name="Device Trust Gateway Service Account" --project="$GCP_PROJECT" --quiet 2>/dev/null || true
            fi

            echo "Granting Cloud Run Invoker role to '$SA_EMAIL' for push authentication..."
            gcloud run services add-iam-policy-binding device-trust-gateway \
                --region="$GCP_REGION" \
                --member="serviceAccount:$SA_EMAIL" \
                --role="roles/run.invoker" \
                --project="$GCP_PROJECT" --quiet 2>/dev/null || true
            
            SUB_NAME="chrome-enrollment-webhook-sub"
            WEBHOOK_URI="${GATEWAY_URL}/api/webhook/chrome-enrollment"
            
            echo "Creating Pub/Sub Push Subscription with OIDC authentication targeting '$WEBHOOK_URI'..."
            gcloud pubsub subscriptions create "$SUB_NAME" \
                --topic="$TOPIC_NAME" \
                --push-endpoint="$WEBHOOK_URI" \
                --push-auth-service-account="$SA_EMAIL" \
                --push-auth-token-audience="$GATEWAY_URL" \
                --ack-deadline=60 \
                --project="$GCP_PROJECT" --quiet 2>/dev/null || \
            gcloud pubsub subscriptions update "$SUB_NAME" \
                --push-endpoint="$WEBHOOK_URI" \
                --push-auth-service-account="$SA_EMAIL" \
                --push-auth-token-audience="$GATEWAY_URL" \
                --project="$GCP_PROJECT" --quiet 2>/dev/null || echo "Subscription configured."
                
            echo "Configuring Weekly Cloud Scheduler safety net..."
            gcloud scheduler jobs create http seed-chromebook-inventory-weekly \
                --schedule="0 3 * * 0" \
                --uri="${GATEWAY_URL}/api/cron/cleanup" \
                --http-method=POST \
                --headers="X-Cloudscheduler=true" \
                --location="$GCP_REGION" \
                --project="$GCP_PROJECT" \
                --description="Weekly safety net crawl of active Chromebooks for Cloud Identity anchoring" --quiet 2>/dev/null || echo "Weekly cron already configured."
                
            echo -e "${GREEN}✔ Real-Time Event-Driven Seeding configured successfully!${NC}"
            ;;
          *)
            echo -e "${RED}Invalid scheduling option. Skipping seeding configuration.${NC}"
            ;;
        esac
    else
        echo -e "${BLUE}Skipping inventory seeding configuration.${NC}"
    fi
}

# Helper function for optional Identity-Aware Proxy (IAP) Edge Defense setup
configure_iap_edge_defense() {
    echo -e "\n${YELLOW}--- Identity-Aware Proxy (IAP) Edge Defense & Access Control Configuration ---${NC}"
    echo "Would you like to enable Identity-Aware Proxy (IAP) Edge Defense to restrict portal access to corporate IP subnets or company-owned devices?"
    read -p "Enable IAP Edge Defense? (y/n): " DO_IAP
    
    if [[ "$DO_IAP" =~ ^[Yy]$ ]]; then
        local SERVICE_NAME="device-trust-gateway"
        if [ -z "$GCP_PROJECT" ]; then
            read -p "Enter your Google Cloud Project ID: " GCP_PROJECT
        fi
        if [ -z "$GCP_REGION" ]; then
            read -p "Enter target Cloud Run region [us-central1]: " GCP_REGION
            GCP_REGION=${GCP_REGION:-us-central1}
        fi
        
        echo -e "\n${BLUE}--- Configured Access Control Parameters ---${NC}"
        echo -e "${YELLOW}Note for GCP Cloud Run / IAP:${NC} IAP inspects the client's ${YELLOW}Public Egress IP address${NC} (or internal RFC1918 CIDR if connecting via Cloud VPN/Interconnect)."
        read -p "Enter corporate Public Egress IP CIDR subnets allowed to access portal (comma-separated, e.g., 203.0.113.0/24, 10.0.0.0/8) [Leave blank to skip]: " USER_IP_INPUT
        
        echo ""
        echo "Select Access Control & Posture restriction mode:"
        echo "  1) IP Subnet Gating AND (Company-Owned OR Admin-Approved BYOD Devices) [Recommended]"
        echo "  2) IP Subnet Gating AND Strictly Company-Owned Devices Only"
        echo "  3) Company-Owned OR Admin-Approved BYOD Devices (Any IP)"
        echo "  4) Strictly Company-Owned Devices Only (Any IP)"
        echo "  5) IP Subnet Gating Only (Any Device)"
        echo ""
        read -p "Enter option [1-5] (default: 1): " POSTURE_OPTION
        POSTURE_OPTION=${POSTURE_OPTION:-1}

        # Format IP array for config update and CEL expression
        IP_ARRAY_JSON="[]"
        CEL_IP_LIST=""
        if [ -n "$USER_IP_INPUT" ]; then
            IFS=',' read -ra ADDR <<< "$USER_IP_INPUT"
            JSON_ELEMENTS=""
            CEL_ELEMENTS=""
            for ip in "${ADDR[@]}"; do
                trimmed=$(echo "$ip" | xargs)
                if [ -n "$trimmed" ]; then
                    if [ -n "$JSON_ELEMENTS" ]; then
                        JSON_ELEMENTS="${JSON_ELEMENTS}, "
                        CEL_ELEMENTS="${CEL_ELEMENTS}, "
                    fi
                    JSON_ELEMENTS="${JSON_ELEMENTS}\"${trimmed}\""
                    CEL_ELEMENTS="${CEL_ELEMENTS}'${trimmed}'"
                fi
            done
            IP_ARRAY_JSON="[${JSON_ELEMENTS}]"
            CEL_IP_LIST="[${CEL_ELEMENTS}]"
        fi

        # Sync trusted IP ranges into Secret Manager config if enabled
        SECRET_NAME="device_trust_gateway_config"
        if gcloud secrets describe "$SECRET_NAME" --project="$GCP_PROJECT" &>/dev/null; then
            echo -e "\n${BLUE}Updating Secret Manager configuration with trusted IP ranges...${NC}"
            EXISTING_PAYLOAD=$(gcloud secrets versions access latest --secret="$SECRET_NAME" --project="$GCP_PROJECT" 2>/dev/null || echo "{}")
            if command -v python3 &>/dev/null; then
                UPDATED_PAYLOAD=$(python3 -c "
import json, sys
data = json.loads('''$EXISTING_PAYLOAD''') if '''$EXISTING_PAYLOAD''' != '{}' else {}
data['trusted_ip_ranges'] = json.loads('''$IP_ARRAY_JSON''')
print(json.dumps(data))
")
                echo -n "$UPDATED_PAYLOAD" | gcloud secrets versions add "$SECRET_NAME" --data-file=- --project="$GCP_PROJECT" --quiet
                echo -e "${GREEN}✔ Secret Manager updated with trusted IP ranges: ${IP_ARRAY_JSON}${NC}"
            fi
        fi

        echo -e "\n${BLUE}[1/5] Enabling IAP and Compute Engine APIs...${NC}"
        gcloud services enable iap.googleapis.com compute.googleapis.com accesscontextmanager.googleapis.com --project="$GCP_PROJECT" --quiet
        
        echo -e "\n${BLUE}[2/5] Restricting Cloud Run service ingress to Load Balancer only...${NC}"
        gcloud run services update "$SERVICE_NAME" \
            --ingress=internal-and-cloud-load-balancing \
            --region="$GCP_REGION" \
            --project="$GCP_PROJECT" --quiet
            
        echo -e "\n${BLUE}[3/5] Creating Serverless Network Endpoint Group (NEG)...${NC}"
        NEG_NAME="dtg-serverless-neg"
        gcloud compute network-endpoint-groups create "$NEG_NAME" \
            --region="$GCP_REGION" \
            --network-endpoint-type=serverless \
            --cloud-run-service="$SERVICE_NAME" \
            --project="$GCP_PROJECT" --quiet 2>/dev/null || echo "Serverless NEG '$NEG_NAME' already exists."
            
        echo -e "\n${BLUE}[4/5] Creating Backend Service and attaching NEG...${NC}"
        BACKEND_NAME="dtg-backend-service"
        gcloud compute backend-services create "$BACKEND_NAME" \
            --global \
            --project="$GCP_PROJECT" --quiet 2>/dev/null || echo "Backend service '$BACKEND_NAME' already exists."
            
        gcloud compute backend-services add-backend "$BACKEND_NAME" \
            --global \
            --network-endpoint-group="$NEG_NAME" \
            --network-endpoint-group-region="$GCP_REGION" \
            --project="$GCP_PROJECT" --quiet 2>/dev/null || echo "Backend NEG already attached."
            
        echo -e "\n${BLUE}[5/5] Enabling Identity-Aware Proxy (IAP) on Backend Service...${NC}"
        gcloud compute backend-services update "$BACKEND_NAME" \
            --global \
            --iap=enabled \
            --project="$GCP_PROJECT" --quiet
            
        # Generate Access Level Spec File based on posture option
        SPEC_FILE="dtg_access_level_spec.yaml"
        CEL_EXPRESSION=""

        case $POSTURE_OPTION in
          1)
            # IP Subnet Gating AND (Company-Owned OR Approved BYOD)
            if [ -n "$CEL_IP_LIST" ]; then
                CEL_EXPRESSION="inSubnetwork(origin.ip, ${CEL_IP_LIST}) && (device.is_corp_owned == true || device.is_admin_approved == true)"
            else
                CEL_EXPRESSION="device.is_corp_owned == true || device.is_admin_approved == true"
            fi
            cat <<EOF > "$SPEC_FILE"
# Access Context Manager Access Level Spec (IP Subnets AND [Company-Owned OR Approved BYOD])
title: Device Trust Gateway Access Policy
expression: "$CEL_EXPRESSION"
EOF
            ;;
          2)
            # IP Subnet Gating AND Strictly Company-Owned Devices Only
            cat <<EOF > "$SPEC_FILE"
# Access Context Manager Access Level Spec (IP Subnets AND Strictly Company-Owned Devices Only)
- ipSubnetworks:
EOF
            if [ -n "$USER_IP_INPUT" ]; then
                IFS=',' read -ra ADDR <<< "$USER_IP_INPUT"
                for ip in "${ADDR[@]}"; do
                    trimmed=$(echo "$ip" | xargs)
                    if [ -n "$trimmed" ]; then echo "    - $trimmed" >> "$SPEC_FILE"; fi
                done
            else
                echo "    - 0.0.0.0/0" >> "$SPEC_FILE"
            fi
            cat <<EOF >> "$SPEC_FILE"
  devicePolicy:
    allowedDeviceManagementLevels:
      - COMPLETE
    requireCorpOwned: true
EOF
            ;;
          3)
            # Company-Owned OR Admin-Approved BYOD (Any IP)
            CEL_EXPRESSION="device.is_corp_owned == true || device.is_admin_approved == true"
            cat <<EOF > "$SPEC_FILE"
# Access Context Manager Access Level Spec (Company-Owned OR Approved BYOD - Any IP)
title: Device Trust Gateway Access Policy
expression: "$CEL_EXPRESSION"
EOF
            ;;
          4)
            # Strictly Company-Owned Devices Only (Any IP)
            cat <<EOF > "$SPEC_FILE"
# Access Context Manager Access Level Spec (Strictly Company-Owned Devices Only - Any IP)
- ipSubnetworks:
    - 0.0.0.0/0
  devicePolicy:
    allowedDeviceManagementLevels:
      - COMPLETE
    requireCorpOwned: true
EOF
            ;;
          5)
            # IP Subnet Gating Only (Any Device)
            cat <<EOF > "$SPEC_FILE"
# Access Context Manager Access Level Spec (IP Subnet Gating Only - Any Device)
- ipSubnetworks:
EOF
            if [ -n "$USER_IP_INPUT" ]; then
                IFS=',' read -ra ADDR <<< "$USER_IP_INPUT"
                for ip in "${ADDR[@]}"; do
                    trimmed=$(echo "$ip" | xargs)
                    if [ -n "$trimmed" ]; then echo "    - $trimmed" >> "$SPEC_FILE"; fi
                done
            else
                echo "    - 0.0.0.0/0" >> "$SPEC_FILE"
            fi
            ;;
        esac

        echo -e "\n${GREEN}===================================================================================================${NC}"
        echo -e "${GREEN}✔ Identity-Aware Proxy (IAP) & Access Control Parameters Configured!                              ${NC}"
        echo -e "${GREEN}===================================================================================================${NC}"
        echo -e "Generated Access Context Manager Access Level spec file: ${YELLOW}${SPEC_FILE}${NC}"
        if [ -n "$CEL_EXPRESSION" ]; then
            echo -e "CEL Rule Expression: ${GREEN}${CEL_EXPRESSION}${NC}"
        fi
        echo ""
        echo -e "${YELLOW}🔑 ACCESS LEVEL CREATION & IAP BINDING STEPS:${NC}"
        if [ -n "$CEL_EXPRESSION" ]; then
            echo -e "  1. To create the Custom CEL Access Level via gcloud:"
            echo -e "     ${GREEN}gcloud access-context-manager levels create dtg_gateway_access_level \\${NC}"
            echo -e "     ${GREEN}  --title=\"Device Trust Gateway Access Policy\" \\${NC}"
            echo -e "     ${GREEN}  --custom-level-spec=${SPEC_FILE} \\${NC}"
            echo -e "     ${GREEN}  --policy=YOUR_ORGANIZATION_POLICY_ID${NC}"
        else
            echo -e "  1. To create the Basic Access Level via gcloud:"
            echo -e "     ${GREEN}gcloud access-context-manager levels create dtg_gateway_access_level \\${NC}"
            echo -e "     ${GREEN}  --title=\"Device Trust Gateway Access Policy\" \\${NC}"
            echo -e "     ${GREEN}  --basic-level-spec=${SPEC_FILE} \\${NC}"
            echo -e "     ${GREEN}  --policy=YOUR_ORGANIZATION_POLICY_ID${NC}"
        fi
        echo -e "  2. In GCP Console Security > Identity-Aware Proxy (https://console.cloud.google.com/security/iap?project=${GCP_PROJECT}):"
        echo -e "     • Locate ${YELLOW}'dtg-backend-service'${NC}."
        echo -e "     • Select your newly generated Access Level to restrict edge access."
        echo -e "${GREEN}===================================================================================================${NC}\n"
    else
        echo -e "${BLUE}Skipping IAP Edge Defense configuration.${NC}"
    fi
}

# Helper function for printing final completion summary banner
print_final_summary() {
    local PORTAL_URL="$1"
    echo -e "\n${GREEN}===================================================================================================${NC}"
    echo -e "${GREEN}🎉 DEVICE TRUST GATEWAY FULLY DEPLOYED & CONFIGURED!                                              ${NC}"
    echo -e "${GREEN}===================================================================================================${NC}"
    echo -e "Access your live self-service portals and admin configuration dashboards below:"
    echo ""
    echo -e "  🌐 ${YELLOW}Main Gateway Portal:${NC}       ${PORTAL_URL}/#/"
    echo -e "  ⚙️ ${YELLOW}Admin Configuration UI:${NC}    ${PORTAL_URL}/#/admin"
    echo ""
    echo -e "${BLUE}Next Steps & Policy Reminder:${NC}"
    echo -e "Ensure your Google Workspace Context-Aware Access (CAA) Custom Access Level is actively enforcing:"
    echo -e "  ${GREEN}device.is_corp_owned == true || device.is_admin_approved == true${NC}"
    echo -e "${GREEN}===================================================================================================${NC}\n"
}

echo -e "${BLUE}=========================================================${NC}"
echo -e "${BLUE}      Device Trust Gateway - Interactive Deployer        ${NC}"
echo -e "${BLUE}=========================================================${NC}"
echo ""
echo "Please select your desired deployment target:"
echo "  1) Google Cloud (GCP Cloud Run + Secret Manager)"
echo "  2) On-Premise (Docker Compose + Local .env)"
echo "  3) Exit"
echo ""
read -p "Enter option [1-3]: " OPTION

case $OPTION in
  1)
    echo -e "\n${YELLOW}--- Starting GCP Cloud Run Deployment ---${NC}"
    
    if ! command -v gcloud &> /dev/null; then
        echo -e "${RED}Error: gcloud CLI could not be found. Please install the Google Cloud SDK.${NC}"
        exit 1
    fi
    
    read -p "Enter your Google Cloud Project ID: " GCP_PROJECT
    read -p "Enter target Cloud Run region [us-central1]: " GCP_REGION
    GCP_REGION=${GCP_REGION:-us-central1}
    
    echo -e "\n${BLUE}[1/7] Setting active GCP project...${NC}"
    gcloud config set project "$GCP_PROJECT" --quiet
    
    echo -e "\n${BLUE}[2/7] Verifying project billing account status...${NC}"
    BILLING_ENABLED=$(gcloud beta billing projects describe "$GCP_PROJECT" --format="value(billingEnabled)" 2>/dev/null || echo "false")
    
    if [ "$BILLING_ENABLED" != "True" ] && [ "$BILLING_ENABLED" != "true" ]; then
        echo -e "\n${RED}===================================================================================================${NC}"
        echo -e "${RED}❌ ERROR: Active billing account not found for project '$GCP_PROJECT'.${NC}"
        echo -e "${RED}Google Cloud Run, Cloud Build, and Secret Manager require an active billing account to be linked.${NC}"
        echo -e "${YELLOW}Instructions:${NC}"
        echo -e "  1. Open the Google Cloud Console: https://console.cloud.google.com/billing"
        echo -e "  2. Link an active billing account to project '$GCP_PROJECT'."
        echo -e "  3. Re-run this deployment script."
        echo -e "${RED}===================================================================================================${NC}\n"
        exit 1
    else
        echo -e "${GREEN}✔ Active billing account verified.${NC}"
    fi
    
    echo -e "\n${BLUE}[3/7] Enabling required Google Cloud APIs...${NC}"
    gcloud services enable run.googleapis.com secretmanager.googleapis.com cloudidentity.googleapis.com cloudbuild.googleapis.com cloudscheduler.googleapis.com pubsub.googleapis.com firestore.googleapis.com admin.googleapis.com --quiet
    
    # Ensure DWD credentials and Admin Email are established before initializing config
    if [ -z "$WORKSPACE_ADMIN_EMAIL" ]; then
        setup_domain_wide_delegation
    fi
    
    echo -e "\n${BLUE}[4/7] Initializing Secret Manager for dynamic admin configuration...${NC}"
    SECRET_NAME="device_trust_gateway_config"
    if ! gcloud secrets describe "$SECRET_NAME" --project="$GCP_PROJECT" &>/dev/null; then
        echo "Creating new Secret Manager secret: $SECRET_NAME"
        gcloud secrets create "$SECRET_NAME" --replication-policy="automatic" --project="$GCP_PROJECT" --quiet
        
        INIT_ADMINS='[]'
        if [ -n "$WORKSPACE_ADMIN_EMAIL" ]; then
            INIT_ADMINS="[\"$WORKSPACE_ADMIN_EMAIL\"]"
        fi
        DEFAULT_CONFIG="{\"customer_id\": \"customers/my_customer\", \"inactivity_threshold_days\": 90, \"revocation_action\": \"DELETE\", \"default_locale\": \"en\", \"portal_admins\": ${INIT_ADMINS}, \"trusted_ip_ranges\": [], \"chaining_allowed_groups\": [], \"chaining_allowed_ous\": []}"
        echo -n "$DEFAULT_CONFIG" | gcloud secrets versions add "$SECRET_NAME" --data-file=- --project="$GCP_PROJECT" --quiet
    else
        echo -e "${GREEN}Secret '$SECRET_NAME' already exists in project.${NC}"
    fi
    
    # Explicitly grant Secret Manager Accessor permissions to our dedicated DWD service account for Admin Config Secret
    echo "Granting Secret Accessor IAM binding to '$DWD_SA_EMAIL' for Admin Config Secret..."
    gcloud secrets add-iam-policy-binding "$SECRET_NAME" \
        --member="serviceAccount:$DWD_SA_EMAIL" \
        --role="roles/secretmanager.secretAccessor" \
        --project="$GCP_PROJECT" --quiet > /dev/null 2>&1 || echo "IAM binding already configured."
    
    echo -e "\n${BLUE}[5/7] Phase 1: Executing baseline container build to establish live Cloud Run URL...${NC}"
    IMAGE_TAG="gcr.io/$GCP_PROJECT/device-trust-gateway"
    
    gcloud builds submit --config cloudbuild.yaml . --project="$GCP_PROJECT" --substitutions=_GOOGLE_CLIENT_ID="" --suppress-logs
    
    SERVICE_URL=$(gcloud run deploy device-trust-gateway \
        --image "$IMAGE_TAG" \
        --platform managed \
        --region "$GCP_REGION" \
        --project "$GCP_PROJECT" \
        --allow-unauthenticated \
        --service-account="$DWD_SA_EMAIL" \
        --format="value(status.url)" \
        --quiet \
        --set-secrets="/secrets/dwd_key.json=device_trust_gateway_dwd_key:latest" \
        --set-env-vars="USE_SECRET_MANAGER=true,SECRET_NAME=$SECRET_NAME,GOOGLE_CLOUD_PROJECT=$GCP_PROJECT,WORKSPACE_ADMIN_EMAIL=$WORKSPACE_ADMIN_EMAIL,GOOGLE_APPLICATION_CREDENTIALS=/secrets/dwd_key.json" 2>/dev/null || echo "https://device-trust-gateway-${GCP_PROJECT}.us-central1.run.app")
        
    echo -e "${GREEN}✔ Baseline service established at: ${SERVICE_URL}${NC}"
    
    echo -e "\n${BLUE}[6/7] Phase 2: Interactive Google OAuth 2.0 Client ID Origin Authorization...${NC}"
    echo -e "\n${YELLOW}===================================================================================================${NC}"
    echo -e "${YELLOW}🔑 REQUIRED OAUTH 2.0 CLIENT ID & CONSENT SCREEN SETUP:${NC}"
    echo -e "Now that your live Cloud Run URL is established, authorize Google Sign-In for your portal frontend:"
    echo ""
    echo -e "  ${BLUE}PART A: OAuth Consent Screen (If using a Custom Domain)${NC}"
    echo -e "  If you plan to use a custom domain (e.g., ${YELLOW}gateway.yourdomain.com${NC}) instead of the default run.app URL:"
    echo -e "    1. Navigate to: https://console.cloud.google.com/apis/credentials/consent?project=${GCP_PROJECT}"
    echo -e "    2. Ensure the User Type is configured (Internal is recommended for Workspace tenants)."
    echo -e "    3. Under ${YELLOW}'Authorized domains'${NC}, add your top-level domain (e.g., ${GREEN}yourdomain.com${NC})."
    echo -e "    4. Save the configurations."
    echo ""
    echo -e "  ${BLUE}PART B: Create OAuth Client ID Credentials${NC}"
    echo -e "    1. Open Google Cloud Credentials: https://console.cloud.google.com/apis/credentials?project=${GCP_PROJECT}"
    echo -e "    2. Click ${YELLOW}'Create Credentials' > 'OAuth client ID'${NC}."
    echo -e "    3. Select Application Type: ${YELLOW}'Web application'${NC}."
    echo -e "    4. In ${YELLOW}'Authorized JavaScript origins'${NC}, add your live service URL:"
    echo -e "       ${GREEN}${SERVICE_URL}${NC}"
    echo -e "    5. In ${YELLOW}'Authorized redirect URIs'${NC}, add your live service URL (required for some redirect flows):"
    echo -e "       ${GREEN}${SERVICE_URL}${NC}"
    echo -e "       ${GREEN}${SERVICE_URL}/${NC}"
    echo -e "    6. Click ${YELLOW}'Create'${NC} and copy the resulting Client ID string."
    echo -e "${YELLOW}===================================================================================================${NC}\n"
    read -p "Enter your authorized Google OAuth 2.0 Client ID: " GOOGLE_CLIENT_ID
    
    echo -e "\n${BLUE}[7/7] Phase 3: Updating Cloud Run configuration with authorized OAuth Client ID (Zero container rebuild required!)...${NC}"
    
    gcloud run deploy device-trust-gateway \
        --image "$IMAGE_TAG" \
        --platform managed \
        --region "$GCP_REGION" \
        --project "$GCP_PROJECT" \
        --allow-unauthenticated \
        --service-account="$DWD_SA_EMAIL" \
        --quiet \
        --set-secrets="/secrets/dwd_key.json=device_trust_gateway_dwd_key:latest" \
        --set-env-vars="USE_SECRET_MANAGER=true,SECRET_NAME=$SECRET_NAME,GOOGLE_CLOUD_PROJECT=$GCP_PROJECT,WORKSPACE_ADMIN_EMAIL=$WORKSPACE_ADMIN_EMAIL,GOOGLE_CLIENT_ID=$GOOGLE_CLIENT_ID,GOOGLE_APPLICATION_CREDENTIALS=/secrets/dwd_key.json"
        
    echo -e "\n${GREEN}=========================================================${NC}"
    echo -e "${GREEN}✔ GCP Deployment & OAuth Authorization Complete!${NC}"
    echo -e "${GREEN}=========================================================${NC}"
    
    execute_mass_revocation_prompt
    configure_inventory_seeding "$SERVICE_URL"
    configure_iap_edge_defense
    print_final_summary "$SERVICE_URL"
    ;;
    
  2)
    echo -e "\n${YELLOW}--- Starting On-Premise Docker Compose Deployment ---${NC}"
    
    if ! command -v docker &> /dev/null; then
        echo -e "${RED}Error: Docker could not be found. Please install Docker and Docker Compose.${NC}"
        exit 1
    fi
    
    if [ ! -f ".env" ]; then
        echo -e "${BLUE}Creating baseline .env configuration file...${NC}"
        cat <<EOF > .env
USE_SECRET_MANAGER=false
TENANT_CUSTOMER_ID=customers/my_customer
TENANT_INACTIVITY_THRESHOLD=90
TENANT_REVOCATION_ACTION=DELETE
TENANT_DEFAULT_LOCALE=en
TENANT_TRUSTED_IPS=[]
TENANT_CHAINING_GROUPS=[]
TENANT_CHAINING_OUS=[]
EOF
    else
        echo -e "${GREEN}Existing .env file detected.${NC}"
    fi
    
    echo -e "\n${BLUE}Building and launching Docker containers in background...${NC}"
    docker-compose -f deploy/docker-compose.yml up --build -d
    
    echo -e "\n${GREEN}=========================================================${NC}"
    echo -e "${GREEN}✔ On-Premise Deployment Complete! Backend running on port 8080.${NC}"
    echo -e "${GREEN}=========================================================${NC}"
    
    execute_mass_revocation_prompt
    configure_inventory_seeding "http://localhost:8080"
    print_final_summary "http://localhost:8080"
    ;;
    
  3)
    echo "Exiting."
    exit 0
    ;;
    
  *)
    echo -e "${RED}Invalid option selected. Exiting.${NC}"
    exit 1
    ;;
esac
