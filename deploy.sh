#!/usr/bin/env bash
# Device Trust Gateway - Automated Deployment & Setup Script

set -e

GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${BLUE}=========================================================${NC}"
echo -e "${BLUE}      Device Trust Gateway - Interactive Deployer        ${NC}"
echo -e "${BLUE}=========================================================${NC}"
echo ""
echo "Please select your desired deployment target:"
echo "  1) Google Cloud (GCP Cloud Run + Secret Manager)"
echo "  2) On-Premise (Docker Compose + Local .env)"
echo "  3) Local Development Environment (FastAPI + React)"
echo "  4) Seed Company-Owned Chromebook Inventory"
echo "  5) Exit"
echo ""
read -p "Enter option [1-5]: " OPTION

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
    
    echo -e "\n${BLUE}[1/4] Setting active GCP project...${NC}"
    gcloud config set project "$GCP_PROJECT"
    
    echo -e "\n${BLUE}[2/4] Enabling required Google Cloud APIs...${NC}"
    gcloud services enable run.googleapis.com secretmanager.googleapis.com cloudidentity.googleapis.com cloudbuild.googleapis.com cloudscheduler.googleapis.com
    
    echo -e "\n${BLUE}[3/4] Initializing Secret Manager for dynamic admin configuration...${NC}"
    SECRET_NAME="device_trust_gateway_config"
    if ! gcloud secrets describe "$SECRET_NAME" --project="$GCP_PROJECT" &>/dev/null; then
        echo "Creating new Secret Manager secret: $SECRET_NAME"
        gcloud secrets create "$SECRET_NAME" --replication-policy="automatic" --project="$GCP_PROJECT"
        
        DEFAULT_CONFIG='{"customer_id": "customers/my_customer", "inactivity_threshold_days": 90, "trusted_ip_ranges": ["127.0.0.1/32", "10.0.0.0/8"], "chaining_allowed_groups": ["trust-chaining-allowed@example.com"], "chaining_allowed_ous": ["/Staff", "/Faculty"]}'
        echo -n "$DEFAULT_CONFIG" | gcloud secrets versions add "$SECRET_NAME" --data-file=- --project="$GCP_PROJECT"
    else
        echo -e "${GREEN}Secret '$SECRET_NAME' already exists in project.${NC}"
    fi
    
    echo -e "\n${BLUE}[4/4] Building container and deploying to Cloud Run...${NC}"
    IMAGE_TAG="gcr.io/$GCP_PROJECT/device-trust-gateway"
    gcloud builds submit --tag "$IMAGE_TAG" deploy/ --project="$GCP_PROJECT"
    
    gcloud run deploy device-trust-gateway \
        --image "$IMAGE_TAG" \
        --platform managed \
        --region "$GCP_REGION" \
        --project "$GCP_PROJECT" \
        --allow-unauthenticated \
        --set-env-vars="USE_SECRET_MANAGER=true,SECRET_NAME=$SECRET_NAME,GOOGLE_CLOUD_PROJECT=$GCP_PROJECT"
        
    echo -e "\n${GREEN}=========================================================${NC}"
    echo -e "${GREEN}✔ GCP Deployment Complete!${NC}"
    echo -e "${GREEN}=========================================================${NC}"
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
    ;;
    
  3)
    echo -e "\n${YELLOW}--- Setting up Local Development Environment ---${NC}"
    
    echo -e "\n${BLUE}[1/2] Setting up Python virtual environment & backend dependencies...${NC}"
    cd backend
    python3 -m venv venv
    source venv/bin/activate
    pip install --upgrade pip
    pip install -r requirements.txt
    cd ..
    
    echo -e "\n${BLUE}[2/2] Setting up React frontend dependencies...${NC}"
    cd frontend
    npm install
    cd ..
    
    echo -e "\n${GREEN}=========================================================${NC}"
    echo -e "${GREEN}✔ Local Dev Environment Initialized Successfully!${NC}"
    echo -e "To run the backend server: ${YELLOW}cd backend && source venv/bin/activate && uvicorn backend.main:app --reload --port 8080${NC}"
    echo -e "To run the frontend UI:    ${YELLOW}cd frontend && npm start${NC}"
    echo -e "${GREEN}=========================================================${NC}"
    ;;
    
  4)
    echo -e "\n${YELLOW}--- Chromebook Fleet Inventory Seeding Configuration ---${NC}"
    echo "Select scheduling frequency for synchronizing active Directory Chromebooks with Cloud Identity:"
    echo "  1) One-Time Execution (Run Crawl Now)"
    echo "  2) Daily Recurring Schedule (GCP Cloud Scheduler Cron)"
    echo "  3) Weekly Recurring Schedule (GCP Cloud Scheduler Cron)"
    echo ""
    read -p "Enter option [1-3]: " SEED_OPTION
    
    case $SEED_OPTION in
      1)
        echo -e "\n${BLUE}Launching inventory seeding script...${NC}"
        if [ -d "backend/venv" ]; then
            source backend/venv/bin/activate
        fi
        python3 backend/scripts/seed_company_inventory.py
        ;;
      2)
        echo -e "\n${BLUE}Configuring Daily GCP Cloud Scheduler Job...${NC}"
        read -p "Enter your Google Cloud Project ID: " GCP_PROJECT
        read -p "Enter target Cloud Scheduler region [us-central1]: " GCP_REGION
        GCP_REGION=${GCP_REGION:-us-central1}
        
        gcloud scheduler jobs create http seed-chromebook-inventory-daily \
            --schedule="0 2 * * *" \
            --uri="https://device-trust-gateway-HASH-uc.a.run.app/api/cron/cleanup" \
            --http-method=POST \
            --headers="X-Cloudscheduler=true" \
            --location="$GCP_REGION" \
            --project="$GCP_PROJECT" \
            --description="Daily crawl of active Chromebooks for Cloud Identity anchoring"
            
        echo -e "${GREEN}✔ Daily Cloud Scheduler Job configured successfully! (Runs at 2:00 AM daily)${NC}"
        ;;
      3)
        echo -e "\n${BLUE}Configuring Weekly GCP Cloud Scheduler Job...${NC}"
        read -p "Enter your Google Cloud Project ID: " GCP_PROJECT
        read -p "Enter target Cloud Scheduler region [us-central1]: " GCP_REGION
        GCP_REGION=${GCP_REGION:-us-central1}
        
        gcloud scheduler jobs create http seed-chromebook-inventory-weekly \
            --schedule="0 3 * * 0" \
            --uri="https://device-trust-gateway-HASH-uc.a.run.app/api/cron/cleanup" \
            --http-method=POST \
            --headers="X-Cloudscheduler=true" \
            --location="$GCP_REGION" \
            --project="$GCP_PROJECT" \
            --description="Weekly crawl of active Chromebooks for Cloud Identity anchoring"
            
        echo -e "${GREEN}✔ Weekly Cloud Scheduler Job configured successfully! (Runs at 3:00 AM every Sunday)${NC}"
        ;;
      *)
        echo -e "${RED}Invalid scheduling option. Exiting.${NC}"
        exit 1
        ;;
    esac
    ;;
    
  5)
    echo "Exiting."
    exit 0
    ;;
    
  *)
    echo -e "${RED}Invalid option selected. Exiting.${NC}"
    exit 1
    ;;
esac
