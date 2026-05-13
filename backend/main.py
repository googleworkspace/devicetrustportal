import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from backend.routes import admin, chaining, network_auth, cron, webhook

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

@app.get("/health")
def health_check():
    return {"status": "OK"}

# Serve React static frontend build files
if os.path.exists("frontend/build"):
    app.mount("/", StaticFiles(directory="frontend/build", html=True), name="frontend")
elif os.path.exists("../frontend/build"):
    app.mount("/", StaticFiles(directory="../frontend/build", html=True), name="frontend")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8080, reload=True)
