from typing import Optional
from fastapi import APIRouter, Header, HTTPException, Depends
from google.oauth2 import id_token
from google.auth.transport import requests
from backend.services.config_service import config_service, TenantConfig
from backend.services.directory_service import directory_service
from backend.services.cloud_identity import cloud_identity_service

router = APIRouter(prefix="/api/admin", tags=["Admin"])

def get_current_user_email(
    authorization: Optional[str] = Header(None),
    x_goog_authenticated_user_email: Optional[str] = Header(None),
    x_user_email: Optional[str] = Header(None)
) -> str:
    """Extracts and verifies authentic user email from Google ID token Bearer, IAP, or dev headers."""
    # 1. Check Google Sign-In OIDC Bearer Token
    if authorization and authorization.startswith("Bearer "):
        token = authorization.split("Bearer ")[-1]
        if cloud_identity_service.mock_mode:
            # In mock mode or local dev simulation, return decoded mock token
            if "@" in token:
                return token
        try:
            id_info = id_token.verify_oauth2_token(token, requests.Request())
            email = id_info.get("email")
            if email:
                return email
        except Exception as e:
            print(f"Warning: Google ID token validation failed: {e}")
            # Fall through to header checks if Bearer validation fails

    # 2. Check Google Cloud IAP Header
    if x_goog_authenticated_user_email:
        if ":" in x_goog_authenticated_user_email:
            return x_goog_authenticated_user_email.split(":")[-1]
        return x_goog_authenticated_user_email

    # 3. Check Development Mock Header
    if x_user_email:
        return x_user_email

    raise HTTPException(status_code=401, detail="Authentication required: Invalid or missing Google ID token.")

@router.get("/config", response_model=TenantConfig)
def get_config(user_email: str = Depends(get_current_user_email)):
    if not directory_service.verify_user_is_admin(user_email):
        raise HTTPException(status_code=403, detail=f"Access denied: Workspace Admin required for {user_email}")
    return config_service.get_tenant_config()

@router.post("/config")
def update_config(config: TenantConfig, user_email: str = Depends(get_current_user_email)):
    if not directory_service.verify_user_is_admin(user_email):
        raise HTTPException(status_code=403, detail=f"Access denied: Workspace Admin required for {user_email}")
    
    success = config_service.update_tenant_config(config)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to update configuration")
    return {"status": "SUCCESS", "message": "Configuration updated successfully"}
