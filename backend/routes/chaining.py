import random
import datetime
from typing import Optional, Dict, Any
from pydantic import BaseModel
from fastapi import APIRouter, Header, HTTPException, Depends
from backend.services.config_service import config_service
from backend.services.directory_service import directory_service
from backend.services.cloud_identity import cloud_identity_service
from backend.routes.admin import get_current_user_email

router = APIRouter(prefix="/api/chaining", tags=["Chaining"])

# Lightweight in-memory cache for pairing codes (code -> {user_email, expires_at})
PAIRING_CODE_CACHE: Dict[str, Dict[str, Any]] = {}

class GenerateResponse(BaseModel):
    pairing_code: str
    expires_in_seconds: int

class VerifyRequest(BaseModel):
    pairing_code: str
    raw_device_id: Optional[str] = None
    ev_header: Optional[str] = None

@router.post("/generate", response_model=GenerateResponse)
def generate_pairing_code(user_email: str = Depends(get_current_user_email)):
    """Generates a temporary pairing code if caller is permitted to chain trust."""
    config = config_service.get_tenant_config()
    
    # Verify user chaining policy (Group overriding OU)
    is_allowed = directory_service.get_user_chaining_policy(
        user_email=user_email,
        allowed_groups=config.chaining_allowed_groups,
        allowed_ous=config.chaining_allowed_ous
    )
    
    if not is_allowed:
        raise HTTPException(
            status_code=403, 
            detail="Access denied: You are not authorized to perform device trust chaining."
        )

    # Generate 6-digit numeric code
    code = f"{random.randint(100000, 999999)}"
    expires_at = datetime.datetime.utcnow() + datetime.timedelta(minutes=10)
    
    PAIRING_CODE_CACHE[code] = {
        "user_email": user_email,
        "expires_at": expires_at
    }
    
    return GenerateResponse(pairing_code=code, expires_in_seconds=600)

@router.post("/verify")
def verify_pairing_code(request: VerifyRequest):
    """Verifies pairing code and approves target device."""
    code_data = PAIRING_CODE_CACHE.get(request.pairing_code)
    if not code_data:
        raise HTTPException(status_code=400, detail="Invalid or expired pairing code")
    
    if datetime.datetime.utcnow() > code_data["expires_at"]:
        del PAIRING_CODE_CACHE[request.pairing_code]
        raise HTTPException(status_code=400, detail="Pairing code has expired")
    
    user_email = code_data["user_email"]
    config = config_service.get_tenant_config()
    
    # Resolve device user resource name (Option A vs Option B)
    device_user_name = None
    if request.ev_header:
        device_user_name = cloud_identity_service.parse_endpoint_verification_header(request.ev_header)
    
    if not device_user_name and request.raw_device_id:
        device_user_name = cloud_identity_service.lookup_device_user(
            user_email=user_email, 
            raw_device_id=request.raw_device_id, 
            customer_id=config.customer_id
        )
        
    if not device_user_name:
        raise HTTPException(status_code=404, detail="Target device user could not be identified")

    # Execute Cloud Identity Approval
    try:
        operation = cloud_identity_service.approve_device_user(
            device_user_name=device_user_name, 
            customer_id=config.customer_id
        )
        # Invalidate used code
        del PAIRING_CODE_CACHE[request.pairing_code]
        return {"status": "SUCCESS", "operation": operation}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
