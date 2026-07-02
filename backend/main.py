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
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from backend.routes import admin, chaining, network_auth, cron, webhook, devices
from backend.services.config_service import config_service

app = FastAPI(
    title="Device Trust Gateway API",
    description="Secure gateway bridge for managing Google Workspace / Cloud Identity device approvals.",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include REST routers
app.include_router(admin.router)
app.include_router(chaining.router)
app.include_router(network_auth.router)
app.include_router(cron.router)
app.include_router(webhook.router)
app.include_router(devices.router)

@app.get("/health")
def health_check():
    return {"status": "OK"}

@app.get("/api/config/public")
def get_public_config():
    config = config_service.get_tenant_config()
    return {
        "google_client_id": getattr(config, "google_client_id", "") or "1234567890-mockclient.apps.googleusercontent.com"
    }

# Serve React static frontend build files
if os.path.exists("frontend/build"):
    app.mount("/", StaticFiles(directory="frontend/build", html=True), name="frontend")
elif os.path.exists("../frontend/build"):
    app.mount("/", StaticFiles(directory="../frontend/build", html=True), name="frontend")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8080, reload=True)
