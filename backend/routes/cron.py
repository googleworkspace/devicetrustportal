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
from fastapi import APIRouter, Header, HTTPException
from backend.services.config_service import config_service
from backend.services.cloud_identity import cloud_identity_service

router = APIRouter(prefix="/api/cron", tags=["Cron"])

@router.post("/cleanup")
def run_inactivity_cleanup(
    x_cloudscheduler: Optional[str] = Header(None)
):
    """Evaluates BYOD devices against inactivity thresholds, revoking stale hardware, authorized strictly by Cloud Scheduler."""
    if not x_cloudscheduler or x_cloudscheduler.lower() != "true":
        raise HTTPException(status_code=403, detail="Access denied: Automated cron execution requires Google Cloud Scheduler authorization.")

    if not cloud_identity_service.service:
        print("INFO [cron.py]: Simulated inactivity cleanup complete (No valid Cloud Identity service).")
        return {"status": "SUCCESS", "revoked_count": 1}

    config = config_service.get_tenant_config()
    revoked_count = 0

    try:
        inactive_device_users = cloud_identity_service.list_inactive_devices(
            threshold_days=config.inactivity_threshold_days,
            customer_id=config.customer_id
        )

        for du in inactive_device_users:
            device_user_name = du["name"]
            print(f"INFO [cron.py]: Revoking stale device user '{device_user_name}' (Exceeded {config.inactivity_threshold_days} days inactivity)...")
            cloud_identity_service.revoke_device_user(
                device_user_name=device_user_name,
                customer_id=config.customer_id
            )
            revoked_count += 1

        print(f"SUCCESS [cron.py]: Inactivity cleanup complete. Revoked {revoked_count} stale device(s).")
        return {"status": "SUCCESS", "revoked_count": revoked_count}
    except Exception as e:
        print(f"ERROR [cron.py]: Inactivity cleanup failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
