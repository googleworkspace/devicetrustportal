from fastapi import APIRouter, Header, HTTPException, Depends
from typing import Optional
from backend.services.config_service import config_service, TenantConfig
from backend.services.directory_service import directory_service

router = APIRouter(prefix="/api/admin", tags=["Admin"])

def get_current_user_email(
    x_goog_authenticated_user_email: Optional[str] = Header(None),
    x_user_email: Optional[str] = Header(None)
) -> str:
    """Extracts authenticated user email from IAP or dev headers."""
    email_header = x_goog_authenticated_user_email or x_user_email
    if not email_header:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    # IAP headers typically look like 'accounts.google.com:user@example.com'
    if ":" in email_header:
        return email_header.split(":")[-1]
    return email_header

@router.get("/config", response_model=TenantConfig)
def get_config(user_email: str = Depends(get_current_user_email)):
    """Retrieves tenant configuration if caller is a Workspace Admin."""
    if not directory_service.verify_user_is_admin(user_email):
        raise HTTPException(status_code=403, detail="Access denied: Workspace Admin required")
    
    return config_service.get_tenant_config()

@router.post("/config")
def update_config(config: TenantConfig, user_email: str = Depends(get_current_user_email)):
    """Updates tenant configuration if caller is a Workspace Admin."""
    if not directory_service.verify_user_is_admin(user_email):
        raise HTTPException(status_code=403, detail="Access denied: Workspace Admin required")
    
    success = config_service.update_tenant_config(config)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to update configuration")
    
    return {"status": "SUCCESS", "message": "Configuration updated successfully"}
