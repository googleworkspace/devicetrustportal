#!/usr/bin/env bash
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
    echo -e "     ${GREEN}https://www.googleapis.com/auth/admin.directory.device.chromeos.readonly,https://www.googleapis.com/auth/cloud-identity.devices${NC}"
    echo -e "  5. Click ${YELLOW}'Authorize'${NC}."
    echo -e "${RED}===================================================================================================${NC}\n"
    
    read -p "Press [ENTER] when Domain-Wide Delegation has been successfully authorized in the Workspace Admin console..."
    
    echo ""
    read -p "Enter the email address of a Workspace Super Administrator to impersonate (e.g., admin@yourdomain.com): " ADMIN_EMAIL
    
    export GOOGLE_APPLICATION_CREDENTIALS="$(pwd)/$KEY_FILE"
    export WORKSPACE_ADMIN_EMAIL="$ADMIN_EMAIL"
    
    echo -e "\n${GREEN}✔ DWD Setup Complete! Credentials exported for live API execution.${NC}"
}

# Helper function for Chromebook fleet inventory seeding
configure_inventory_seeding() {
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
                --uri="https://device-trust-gateway-HASH-uc.a.run.app/api/cron/cleanup" \
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
                --uri="https://device-trust-gateway-HASH-uc.a.run.app/api/cron/cleanup" \
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
            
            SUB_NAME="chrome-enrollment-webhook-sub"
            WEBHOOK_URI="https://device-trust-gateway-HASH-uc.a.run.app/api/webhook/chrome-enrollment"
            
            echo "Creating Pub/Sub Push Subscription targeting '$WEBHOOK_URI'..."
            gcloud pubsub subscriptions create "$SUB_NAME" \
                --topic="$TOPIC_NAME" \
                --push-endpoint="$WEBHOOK_URI" \
                --ack-deadline=60 \
                --project="$GCP_PROJECT" --quiet 2>/dev/null || echo "Subscription already configured."
                
            echo "Configuring Weekly Cloud Scheduler safety net..."
            gcloud scheduler jobs create http seed-chromebook-inventory-weekly \
                --schedule="0 3 * * 0" \
                --uri="https://device-trust-gateway-HASH-uc.a.run.app/api/cron/cleanup" \
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

# Helper function for printing final completion summary banner
print_final_summary() {
    local PORTAL_URL="$1"
    echo -e "\n${GREEN}===================================================================================================${NC}"
    echo -e "${GREEN}🎉 DEVICE TRUST GATEWAY FULLY DEPLOYED & CONFIGURED!                                              ${NC}"
    echo -e "${GREEN}===================================================================================================${NC}"
    echo -e "Access your live self-service portals and admin configuration dashboards below:"
    echo ""
    echo -e "  🌐 ${YELLOW}Main Gateway Dashboard:${NC}     ${PORTAL_URL}/#/"
    echo -e "  🔗 ${YELLOW}Trust Chaining Portal:${NC}      ${PORTAL_URL}/#/chaining"
    echo -e "  📶 ${YELLOW}Campus Wi-Fi Approval:${NC}      ${PORTAL_URL}/#/network"
    echo -e "  ⚙️ ${YELLOW}Admin Config UI:${NC}            ${PORTAL_URL}/#/admin"
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
    gcloud services enable run.googleapis.com secretmanager.googleapis.com cloudidentity.googleapis.com cloudbuild.googleapis.com cloudscheduler.googleapis.com pubsub.googleapis.com admin.googleapis.com --quiet
    
    echo -e "\n${BLUE}[4/7] Initializing Secret Manager for dynamic admin configuration...${NC}"
    SECRET_NAME="device_trust_gateway_config"
    if ! gcloud secrets describe "$SECRET_NAME" --project="$GCP_PROJECT" &>/dev/null; then
        echo "Creating new Secret Manager secret: $SECRET_NAME"
        gcloud secrets create "$SECRET_NAME" --replication-policy="automatic" --project="$GCP_PROJECT" --quiet
        
        DEFAULT_CONFIG='{"customer_id": "customers/my_customer", "inactivity_threshold_days": 90, "trusted_ip_ranges": ["127.0.0.1/32", "10.0.0.0/8"], "chaining_allowed_groups": ["trust-chaining-allowed@example.com"], "chaining_allowed_ous": ["/Staff", "/Faculty"]}'
        echo -n "$DEFAULT_CONFIG" | gcloud secrets versions add "$SECRET_NAME" --data-file=- --project="$GCP_PROJECT" --quiet
    else
        echo -e "${GREEN}Secret '$SECRET_NAME' already exists in project.${NC}"
    fi
    
    # Ensure DWD credentials and Admin Email are established before deploying container
    if [ -z "$WORKSPACE_ADMIN_EMAIL" ]; then
        setup_domain_wide_delegation
    fi
    
    echo -e "\n${BLUE}[5/7] Phase 1: Executing baseline container build to establish live Cloud Run URL...${NC}"
    IMAGE_TAG="gcr.io/$GCP_PROJECT/device-trust-gateway"
    
    gcloud builds submit --config cloudbuild.yaml . --project="$GCP_PROJECT" --substitutions=_GOOGLE_CLIENT_ID="INITIAL_DEPLOY_PENDING" --suppress-logs
    
    SERVICE_URL=$(gcloud run deploy device-trust-gateway \
        --image "$IMAGE_TAG" \
        --platform managed \
        --region "$GCP_REGION" \
        --project "$GCP_PROJECT" \
        --allow-unauthenticated \
        --format="value(status.url)" \
        --quiet \
        --set-secrets="/secrets/dwd_key.json=device_trust_gateway_dwd_key:latest" \
        --set-env-vars="USE_SECRET_MANAGER=true,SECRET_NAME=$SECRET_NAME,GOOGLE_CLOUD_PROJECT=$GCP_PROJECT,WORKSPACE_ADMIN_EMAIL=$WORKSPACE_ADMIN_EMAIL,GOOGLE_APPLICATION_CREDENTIALS=/secrets/dwd_key.json" 2>/dev/null || echo "https://device-trust-gateway-${GCP_PROJECT}.us-central1.run.app")
        
    echo -e "${GREEN}✔ Baseline service established at: ${SERVICE_URL}${NC}"
    
    echo -e "\n${BLUE}[6/7] Phase 2: Interactive Google OAuth 2.0 Client ID Origin Authorization...${NC}"
    echo -e "\n${YELLOW}===================================================================================================${NC}"
    echo -e "${YELLOW}🔑 REQUIRED OAUTH 2.0 CLIENT ID SETUP:${NC}"
    echo -e "Now that your live Cloud Run URL is established, authorize Google Sign-In for your portal frontend:"
    echo -e "  1. Open Google Cloud Console: https://console.cloud.google.com/apis/credentials?project=${GCP_PROJECT}"
    echo -e "  2. Click ${YELLOW}'Create Credentials' > 'OAuth client ID'${NC}."
    echo -e "  3. Select Application Type: ${YELLOW}'Web application'${NC}."
    echo -e "  4. Under ${YELLOW}'Authorized JavaScript origins'${NC}, copy and paste this exact live URL:"
    echo -e "     ${GREEN}${SERVICE_URL}${NC}"
    echo -e "  5. Click ${YELLOW}'Create'${NC} and copy the resulting Client ID string."
    echo -e "${YELLOW}===================================================================================================${NC}\n"
    read -p "Enter your authorized Google OAuth 2.0 Client ID: " GOOGLE_CLIENT_ID
    
    echo -e "\n${BLUE}[7/7] Phase 3: Rebuilding container with authorized OAuth Client ID and deploying final revision...${NC}"
    gcloud builds submit --config cloudbuild.yaml . --project="$GCP_PROJECT" --substitutions=_GOOGLE_CLIENT_ID="$GOOGLE_CLIENT_ID" --suppress-logs
    
    gcloud run deploy device-trust-gateway \
        --image "$IMAGE_TAG" \
        --platform managed \
        --region "$GCP_REGION" \
        --project "$GCP_PROJECT" \
        --allow-unauthenticated \
        --quiet \
        --set-secrets="/secrets/dwd_key.json=device_trust_gateway_dwd_key:latest" \
        --set-env-vars="USE_SECRET_MANAGER=true,SECRET_NAME=$SECRET_NAME,GOOGLE_CLOUD_PROJECT=$GCP_PROJECT,WORKSPACE_ADMIN_EMAIL=$WORKSPACE_ADMIN_EMAIL,GOOGLE_APPLICATION_CREDENTIALS=/secrets/dwd_key.json"
        
    echo -e "\n${GREEN}=========================================================${NC}"
    echo -e "${GREEN}✔ GCP Deployment & OAuth Authorization Complete!${NC}"
    echo -e "${GREEN}=========================================================${NC}"
    
    configure_inventory_seeding
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
TENANT_TRUSTED_IPS=["127.0.0.1/32", "10.0.0.0/8"]
TENANT_CHAINING_GROUPS=["trust-chaining-allowed@example.com"]
TENANT_CHAINING_OUS=["/Staff", "/Faculty"]
EOF
    else
        echo -e "${GREEN}Existing .env file detected.${NC}"
    fi
    
    echo -e "\n${BLUE}Building and launching Docker containers in background...${NC}"
    docker-compose -f deploy/docker-compose.yml up --build -d
    
    echo -e "\n${GREEN}=========================================================${NC}"
    echo -e "${GREEN}✔ On-Premise Deployment Complete! Backend running on port 8080.${NC}"
    echo -e "${GREEN}=========================================================${NC}"
    
    configure_inventory_seeding
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
