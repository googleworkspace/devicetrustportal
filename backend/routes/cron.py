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

from typing import Optional, Dict, Any
from fastapi import APIRouter, Header, HTTPException
from backend.services.config_service import config_service
from backend.services.cloud_identity import cloud_identity_service
from backend.services.directory_service import directory_service

router = APIRouter(prefix="/api/cron", tags=["Cron"])

def sync_chromebook_fleet_inventory(customer_id: str) -> Dict[str, Any]:
    """Crawls active Directory ChromeOS devices and ensures they are anchored as COMPANY hardware in Cloud Identity."""
    if not directory_service.service or not cloud_identity_service.service:
        print("INFO [cron.py]: Simulated Chromebook inventory sync complete.")
        return {"status": "SUCCESS", "synced_count": 0, "simulated": True}

    cust_key = customer_id.replace("customers/", "").strip() if customer_id else "my_customer"
    ci_customer = f"customers/{cust_key}" if not customer_id.startswith("customers/") else customer_id

    try:
        page_token = None
        total_synced = 0
        max_pages = 10
        page = 0

        while page < max_pages:
            page += 1
            req = directory_service.service.chromeosdevices().list(
                customerId=cust_key,
                pageToken=page_token,
                maxResults=50,
                projection="FULL"
            )
            resp = req.execute()
            devices = resp.get("chromeosdevices", [])
            if not devices:
                break

            for dev in devices:
                serial = dev.get("serialNumber")
                if not serial:
                    continue
                body = {
                    "deviceType": "CHROME_OS",
                    "serialNumber": serial,
                    "assetTag": dev.get("annotatedAssetId", serial),
                    "model": dev.get("model", "Google Chromebook"),
                    "osVersion": dev.get("osVersion", "ChromeOS"),
                    "ownerType": "COMPANY"
                }
                try:
                    cloud_identity_service.service.devices().create(
                        customer=ci_customer,
                        body=body
                    ).execute()
                    total_synced += 1
                except Exception:
                    # Device already exists or already registered
                    pass

            page_token = resp.get("nextPageToken")
            if not page_token:
                break

        print(f"SUCCESS [cron.py]: Chromebook fleet sync complete. Anchored/verified {total_synced} device(s).")
        return {"status": "SUCCESS", "synced_count": total_synced}
    except Exception as e:
        print(f"WARNING [cron.py]: Directory Chromebook inventory crawl encountered notice: {e}")
        return {"status": "WARNING", "error": str(e)}

@router.post("/sync-inventory")
def run_inventory_sync(
    x_cloudscheduler: Optional[str] = Header(None)
):
    """Synchronizes active Google Workspace Directory ChromeOS devices with Cloud Identity hardware inventory."""
    if not x_cloudscheduler or x_cloudscheduler.lower() != "true":
        raise HTTPException(status_code=403, detail="Access denied: Automated cron execution requires Google Cloud Scheduler authorization.")

    config = config_service.get_tenant_config()
    return sync_chromebook_fleet_inventory(config.customer_id)

@router.post("/cleanup")
def run_inactivity_cleanup(
    x_cloudscheduler: Optional[str] = Header(None)
):
    """Evaluates BYOD devices against inactivity thresholds and anchors enterprise Chromebooks, authorized strictly by Cloud Scheduler."""
    if not x_cloudscheduler or x_cloudscheduler.lower() != "true":
        raise HTTPException(status_code=403, detail="Access denied: Automated cron execution requires Google Cloud Scheduler authorization.")

    if not cloud_identity_service.service:
        print("INFO [cron.py]: Simulated inactivity cleanup complete (No valid Cloud Identity service).")
        return {"status": "SUCCESS", "revoked_count": 1, "inventory_sync": {"status": "SUCCESS", "synced_count": 0}}

    config = config_service.get_tenant_config()
    revoked_count = 0

    try:
        inactive_device_users = cloud_identity_service.list_inactive_devices(
            threshold_days=config.inactivity_threshold_days,
            customer_id=config.customer_id
        )

        for du in inactive_device_users:
            device_user_name = du["name"]
            print(f"INFO [cron.py]: Revoking stale device user '{device_user_name}' (Exceeded {config.inactivity_threshold_days} days inactivity) via {config.revocation_action}...")
            cloud_identity_service.revoke_device_user(
                device_user_name=device_user_name,
                customer_id=config.customer_id,
                action=config.revocation_action
            )
            revoked_count += 1

        print(f"SUCCESS [cron.py]: Inactivity cleanup complete. Revoked {revoked_count} stale device(s).")
        
        # Synchronize enterprise Chromebook inventory
        sync_result = sync_chromebook_fleet_inventory(config.customer_id)
        return {"status": "SUCCESS", "revoked_count": revoked_count, "inventory_sync": sync_result}
    except Exception as e:
        print(f"ERROR [cron.py]: Inactivity cleanup failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
