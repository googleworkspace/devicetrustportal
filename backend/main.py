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
from typing import Optional, Dict, Any
from pydantic import BaseModel
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from backend.routes import admin, chaining, network_auth, cron, webhook, devices, session_watch
from backend.services.config_service import config_service

app = FastAPI(
    title="Device Trust Gateway API",
    description="Secure gateway bridge for managing Google Workspace / Cloud Identity device approvals and CAA-Free Session Watch.",
    version="1.1.0-session-watch"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ClientLogRequest(BaseModel):
    level: str = "INFO"
    event: str
    message: str
    user_email: Optional[str] = None
    route: Optional[str] = None
    user_agent: Optional[str] = None
    details: Optional[Dict[str, Any]] = None

# Include REST routers
app.include_router(admin.router)
app.include_router(chaining.router)
app.include_router(network_auth.router)
app.include_router(cron.router)
app.include_router(webhook.router)
app.include_router(devices.router)
app.include_router(session_watch.router)

@app.get("/health")
def health_check():
    config = config_service.get_tenant_config()
    return {
        "status": "OK",
        "enforcement_mode": getattr(config, "enforcement_mode", "DISABLED"),
        "session_watch_enabled": bool(getattr(config, "session_watch_enabled", False)),
        "cookie_threat_detection_enabled": bool(
            getattr(config, "cookie_threat_detection_enabled", False)
        ),
        "caa_enforcement_enabled": bool(getattr(config, "caa_enforcement_enabled", False)),
        "branch_variation": "poc/fundamentals-session-watch",
    }

@app.post("/api/client-logs")
def receive_client_log(payload: ClientLogRequest, request: Request):
    lvl = (payload.level or "INFO").strip().upper()
    if lvl not in ("INFO", "WARNING", "ERROR"):
        lvl = "INFO"
    user = (payload.user_email or "anonymous").strip()
    route = (payload.route or "/").strip()
    ua = (payload.user_agent or request.headers.get("user-agent") or "unknown").strip()
    details_str = json.dumps(payload.details or {}, default=str)
    print(
        f"{lvl} [CLIENT_LOG]: event='{payload.event}' user='{user}' route='{route}' "
        f"message='{payload.message}' details={details_str} ua='{ua}'",
        flush=True,
    )
    return {"status": "OK"}

@app.get("/api/config/public")
def get_public_config():
    config = config_service.get_tenant_config()
    return {
        "google_client_id": getattr(config, "google_client_id", "") or "",
        "default_locale": getattr(config, "default_locale", "en"),
        "enforcement_mode": getattr(config, "enforcement_mode", "DISABLED"),
        "session_watch_enabled": bool(getattr(config, "session_watch_enabled", False)),
        "cookie_threat_detection_enabled": bool(
            getattr(config, "cookie_threat_detection_enabled", False)
        ),
        "caa_enforcement_enabled": bool(getattr(config, "caa_enforcement_enabled", False)),
        "enable_trust_chaining": bool(getattr(config, "enable_trust_chaining", False)),
        "branch_variation": "poc/fundamentals-session-watch",
    }

# Serve React static frontend build files
if os.path.exists("frontend/build"):
    app.mount("/", StaticFiles(directory="frontend/build", html=True), name="frontend")
elif os.path.exists("../frontend/build"):
    app.mount("/", StaticFiles(directory="../frontend/build", html=True), name="frontend")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8080, reload=True)
