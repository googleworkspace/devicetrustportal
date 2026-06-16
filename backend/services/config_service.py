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

import os
import json
from typing import Dict, Any, List
from pydantic import BaseModel, Field
from dotenv import load_dotenv, set_key

load_dotenv()

class TenantConfig(BaseModel):
    customer_id: str = Field(default="customers/my_customer", description="Google Workspace Customer Resource Name")
    inactivity_threshold_days: int = Field(default=90, description="Days of inactivity before automated revocation")
    portal_admins: List[str] = Field(default=[], description="List of user emails authorized to access Admin Config UI")
    trusted_ip_ranges: List[str] = Field(default=[], description="Deprecated")
    chaining_allowed_groups: List[str] = Field(default=[], description="Deprecated")
    chaining_allowed_ous: List[str] = Field(default=[], description="Deprecated")

class ConfigService:
    def __init__(self):
        self.project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
        self.secret_name = os.getenv("SECRET_NAME", "device_trust_gateway_config")
        self.use_secret_manager = os.getenv("USE_SECRET_MANAGER", "false").lower() == "true"
        
        if self.use_secret_manager:
            try:
                from google.cloud import secretmanager
                self.sm_client = secretmanager.SecretManagerServiceClient()
            except Exception as e:
                print(f"Warning: Failed to initialize Secret Manager client: {e}. Falling back to .env")
                self.use_secret_manager = False

    def get_tenant_config(self) -> TenantConfig:
        if self.use_secret_manager and self.project_id:
            try:
                name = f"projects/{self.project_id}/secrets/{self.secret_name}/versions/latest"
                response = self.sm_client.access_secret_version(request={"name": name})
                payload = response.payload.data.decode("UTF-8")
                data = json.loads(payload)
                return TenantConfig(**data)
            except Exception as e:
                print(f"Error reading from Secret Manager: {e}. Falling back to local config.")

        return TenantConfig(
            customer_id=os.getenv("TENANT_CUSTOMER_ID", "customers/my_customer"),
            inactivity_threshold_days=int(os.getenv("TENANT_INACTIVITY_THRESHOLD", 90)),
            portal_admins=json.loads(os.getenv("TENANT_PORTAL_ADMINS", '[]')),
            trusted_ip_ranges=json.loads(os.getenv("TENANT_TRUSTED_IPS", '[]')),
            chaining_allowed_groups=json.loads(os.getenv("TENANT_CHAINING_GROUPS", '[]')),
            chaining_allowed_ous=json.loads(os.getenv("TENANT_CHAINING_OUS", '[]'))
        )

    def update_tenant_config(self, config: TenantConfig) -> bool:
        config_dict = config.model_dump()
        config_json = json.dumps(config_dict)

        if self.use_secret_manager and self.project_id:
            try:
                parent = f"projects/{self.project_id}/secrets/{self.secret_name}"
                self.sm_client.add_secret_version(
                    request={"parent": parent, "payload": {"data": config_json.encode("UTF-8")}}
                )
                return True
            except Exception as e:
                print(f"Error updating Secret Manager: {e}. Falling back to local .env update.")

        dotenv_path = os.path.join(os.getcwd(), ".env")
        if not os.path.exists(dotenv_path):
            with open(dotenv_path, "w") as f:
                f.write("# Device Trust Gateway Configuration\n")

        set_key(dotenv_path, "TENANT_CUSTOMER_ID", config.customer_id)
        set_key(dotenv_path, "TENANT_INACTIVITY_THRESHOLD", str(config.inactivity_threshold_days))
        set_key(dotenv_path, "TENANT_PORTAL_ADMINS", json.dumps(config.portal_admins))
        set_key(dotenv_path, "TENANT_TRUSTED_IPS", json.dumps(config.trusted_ip_ranges))
        set_key(dotenv_path, "TENANT_CHAINING_GROUPS", json.dumps(config.chaining_allowed_groups))
        set_key(dotenv_path, "TENANT_CHAINING_OUS", json.dumps(config.chaining_allowed_ous))
        
        load_dotenv(dotenv_path, override=True)
        return True

config_service = ConfigService()
