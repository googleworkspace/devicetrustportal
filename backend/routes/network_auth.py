import ipaddress
from typing import Optional
from pydantic import BaseModel
from fastapi import APIRouter, Header, HTTPException, Depends, Request
from backend.services.config_service import config_service
from backend.services.cloud_identity import cloud_identity_service
from backend.routes.admin import get_current_user_email

router = APIRouter(prefix="/api/network", tags=["Network Approval"])

class NetworkApprovalRequest(BaseModel):
    raw_device_id: Optional[str] = None
    ev_header: Optional[str] = None

def verify_client_ip_is_trusted(request: Request) -> str:
    """Validates if the request originates from a configured trusted IP CIDR range."""
    config = config_service.get_tenant_config()
    
    # Get client IP from X-Forwarded-For or raw client host
    client_ip_str = request.headers.get("X-Forwarded-For")
    if not client_ip_str and request.client:
        client_ip_str = request.client.host
        
    if not client_ip_str:
        raise HTTPException(status_code=400, detail="Unable to determine client IP address")
        
    # If multiple IPs in X-Forwarded-For, take the first (origin)
    client_ip_str = client_ip_str.split(",")[0].strip()
    
    try:
        client_ip = ipaddress.ip_address(client_ip_str)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid client IP address format")

    is_trusted = False
    for cidr_str in config.trusted_ip_ranges:
        try:
            trusted_network = ipaddress.ip_network(cidr_str, strict=False)
            if client_ip in trusted_network:
                is_trusted = True
                break
        except ValueError:
            continue # Ignore malformed CIDR in config
            
    if not is_trusted:
        raise HTTPException(
            status_code=403, 
            detail=f"Access denied: Client IP {client_ip_str} is not within campus trusted networks."
        )
        
    return client_ip_str

@router.post("/approve")
def network_gated_approval(
    body: NetworkApprovalRequest,
    request: Request,
    user_email: str = Depends(get_current_user_email)
):
    """Executes self-service device approval if caller is connected to a trusted network."""
    # Validate IP
    verify_client_ip_is_trusted(request)
    
    config = config_service.get_tenant_config()
    
    # Resolve device user resource name
    device_user_name = None
    if body.ev_header:
        device_user_name = cloud_identity_service.parse_endpoint_verification_header(body.ev_header)
        
    if not device_user_name and body.raw_device_id:
        device_user_name = cloud_identity_service.lookup_device_user(
            user_email=user_email,
            raw_device_id=body.raw_device_id,
            customer_id=config.customer_id
        )
        
    if not device_user_name:
        raise HTTPException(status_code=404, detail="Target device user could not be identified")
        
    # Execute approval
    try:
        operation = cloud_identity_service.approve_device_user(
            device_user_name=device_user_name,
            customer_id=config.customer_id
        )
        return {"status": "SUCCESS", "operation": operation}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
