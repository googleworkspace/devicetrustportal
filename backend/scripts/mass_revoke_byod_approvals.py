import os
import time
import google.auth
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

def execute_mass_byod_revocation():
    print("\n===================================================================================================")
    print("      Starting Live Mass BYOD Approval Revocation Crawl (Pristine Zero-Trust Baseline)            ")
    print("===================================================================================================")
    print("This enterprise crawl actively paginates through all Cloud Identity hardware assets in your tenant.")
    print("It permanently revokes approval for all personal (BYOD) devices while preserving company anchors.\n")

    scopes = [
        "https://www.googleapis.com/auth/cloud-identity.devices",
        "https://www.googleapis.com/auth/cloud-identity"
    ]
    key_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "dwd_key.json")
    admin_email = os.getenv("WORKSPACE_ADMIN_EMAIL")

    if not admin_email:
        print("ERROR: WORKSPACE_ADMIN_EMAIL environment variable is required for DWD impersonation.")
        return

    try:
        if key_path and os.path.exists(key_path):
            credentials = service_account.Credentials.from_service_account_file(
                key_path, scopes=scopes, subject=admin_email
            )
        else:
            credentials, _ = google.auth.default(scopes=scopes)

        service = build("cloudidentity", "v1", credentials=credentials)
    except Exception as e:
        print(f"ERROR: Failed to initialize Cloud Identity service: {e}")
        return

    customer_id = "customers/my_customer"
    next_page_token = None
    page_count = 0
    total_devices_inspected = 0
    total_revoked = 0
    total_skipped_company = 0
    total_errors = 0

    start_time = time.time()

    while True:
        page_count += 1
        print(f"INFO: Fetching Cloud Identity devices.list [Page {page_count}]...")

        try:
            request = service.devices().list(
                customer=customer_id,
                pageToken=next_page_token
            )
            response = request.execute()
            devices = response.get("devices", [])
            total_devices_inspected += len(devices)

            for d in devices:
                device_name = d["name"]
                owner_type = d.get("ownerType", "BYOD")
                model = d.get("model", "Unknown Model")

                # Safety Check: Preserve Company-Owned Trust Anchors
                if owner_type == "COMPANY":
                    total_skipped_company += 1
                    continue

                # Paginate through deviceUsers bindings for personal BYOD hardware
                du_page_token = None
                while True:
                    try:
                        du_req = service.devices().deviceUsers().list(
                            parent=device_name,
                            customer=customer_id,
                            pageToken=du_page_token
                        )
                        du_resp = du_req.execute()

                        for du in du_resp.get("deviceUsers", []):
                            state = du.get("managementState") or du.get("approvalState", "UNKNOWN_STATE")
                            if state == "APPROVED":
                                du_name = du["name"]
                                user_email = du.get("userEmail", "Unknown User")
                                print(f"REVOKING: Unapproving BYOD binding '{du_name}' ({model}) for '{user_email}'...")
                                
                                del_req = service.devices().deviceUsers().delete(
                                    name=du_name,
                                    customer=customer_id
                                )
                                del_req.execute()
                                total_revoked += 1
                                
                        du_page_token = du_resp.get("nextPageToken")
                        if not du_page_token:
                            break
                    except HttpError as e:
                        print(f"WARNING: API error inspecting deviceUsers for '{device_name}': {e}")
                        total_errors += 1
                        break
                    except Exception as e:
                        print(f"WARNING: Unexpected error inspecting deviceUsers for '{device_name}': {e}")
                        total_errors += 1
                        break

            next_page_token = response.get("nextPageToken")
            if not next_page_token:
                break

        except HttpError as e:
            print(f"ERROR: Cloud Identity API pagination error on Page {page_count}: {e}")
            total_errors += 1
            time.sleep(5)  # Exponential backoff pause before retrying/breaking
            break
        except Exception as e:
            print(f"ERROR: Unexpected pagination error on Page {page_count}: {e}")
            total_errors += 1
            break

    elapsed = time.time() - start_time
    print("\n===================================================================================================")
    print("      Mass BYOD Approval Revocation Sweep Complete!                                               ")
    print("===================================================================================================")
    print(f"⏱️ Elapsed Time:             {elapsed:.2f} seconds")
    print(f"📦 Total Devices Inspected:  {total_devices_inspected}")
    print(f"🏢 Company Anchors Skipped:  {total_skipped_company}")
    print(f"✕ Personal BYODs Revoked:    {total_revoked}")
    print(f"⚠️ Total API Errors:         {total_errors}")
    print("===================================================================================================\n")

if __name__ == "__main__":
    execute_mass_byod_revocation()
