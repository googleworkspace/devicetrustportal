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

from typing import Optional
from pydantic import BaseModel
from fastapi import APIRouter, Header, HTTPException, Depends
from google.oauth2 import id_token
from google.auth.transport import requests
from backend.services.config_service import config_service, TenantConfig
from backend.services.directory_service import directory_service

router = APIRouter(prefix="/api/admin", tags=["Admin"])

class AdminStatusResponse(BaseModel):
    is_admin: bool

def get_current_user_email(
    authorization: Optional[str] = Header(None),
    x_goog_authenticated_user_email: Optional[str] = Header(None)
) -> str:
    if authorization and authorization.startswith("Bearer "):
        token = authorization.split("Bearer ")[-1]
        try:
            id_info = id_token.verify_oauth2_token(token, requests.Request())
            email = id_info.get("email")
            if email:
                return email
        except Exception as e:
            print(f"Google ID token validation failed: {e}")

    if x_goog_authenticated_user_email:
        if ":" in x_goog_authenticated_user_email:
            return x_goog_authenticated_user_email.split(":")[-1]
        return x_goog_authenticated_user_email

    raise HTTPException(status_code=401, detail="Authentication required: Invalid or missing Google ID token.")

@router.get("/status", response_model=AdminStatusResponse)
def check_admin_status(user_email: str = Depends(get_current_user_email)):
    """Returns whether the requesting user holds Workspace Admin privileges or is listed in portal_admins."""
    config = config_service.get_tenant_config()
    is_admin = directory_service.verify_user_is_admin(user_email, portal_admins=config.portal_admins)
    return AdminStatusResponse(is_admin=is_admin)

@router.get("/config", response_model=TenantConfig)
def get_config(user_email: str = Depends(get_current_user_email)):
    config = config_service.get_tenant_config()
    if not directory_service.verify_user_is_admin(user_email, portal_admins=config.portal_admins):
        raise HTTPException(status_code=403, detail=f"Access denied: Workspace Admin privileges required for {user_email}")
    return config

@router.post("/config")
def update_config(config: TenantConfig, user_email: str = Depends(get_current_user_email)):
    current_config = config_service.get_tenant_config()
    if not directory_service.verify_user_is_admin(user_email, portal_admins=current_config.portal_admins):
        raise HTTPException(status_code=403, detail=f"Access denied: Workspace Admin privileges required for {user_email}")
    
    success = config_service.update_tenant_config(config)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to update configuration")
    return {"status": "SUCCESS", "message": "Configuration updated successfully"}
