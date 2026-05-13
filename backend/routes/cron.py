from typing import Optional
from fastapi import APIRouter, Header, HTTPException
from backend.services.config_service import config_service
from backend.services.cloud_identity import cloud_identity_service

router = APIRouter(prefix="/api/cron", tags=["Cron"])

@router.post("/cleanup")
def cleanup_inactive_devices(
    x_appengine_cron: Optional[str] = Header(None),
    x_cloudscheduler: Optional[str] = Header(None),
    x_mock_cron: Optional[str] = Header(None)
):
    """Evaluates active BYOD devices against inactivity threshold and revokes stale access."""
    # Validate caller is a secure cron invocation
    if not x_appengine_cron and not x_cloudscheduler and not x_mock_cron:
        raise HTTPException(status_code=403, detail="Access denied: Authorized cron invocation required")
        
    config = config_service.get_tenant_config()
    
    try:
        inactive_devices = cloud_identity_service.list_inactive_devices(
            threshold_days=config.inactivity_threshold_days,
            customer_id=config.customer_id
        )
        
        revoked_count = 0
        revoked_list = []
        for du in inactive_devices:
            device_user_name = du["name"]
            cloud_identity_service.revoke_device_user(device_user_name, config.customer_id)
            revoked_count += 1
            revoked_list.append(device_user_name)
            
        return {
            "status": "SUCCESS",
            "revoked_count": revoked_count,
            "revoked_devices": revoked_list
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
