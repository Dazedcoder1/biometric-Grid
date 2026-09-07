from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, HTMLResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import logging
import os

from app.api.routes import auth, attendance
from app.api.routes import tracker
from app.api.routes.super_admin import tenants
from app.api.routes.tenant import (
    dashboard as tenant_dashboard, departments as tenant_departments, org_admins as tenant_org_admins,
    employees as tenant_employees, attendance as tenant_attendance, reports as tenant_reports,
    devices as tenant_devices, settings as tenant_settings, holidays as tenant_holidays, leaves as tenant_leaves
)
from app.api.routes.org_admin import (
    dashboard as org_dashboard, employees as org_employees, attendance as org_attendance,
    leaves as org_leaves, holidays as org_holidays , devices as org_devices
)
from app.api.routes.employee import (
    dashboard as emp_dashboard, attendance as emp_attendance, profile as emp_profile,
    leaves as emp_leaves, holidays as emp_holidays, notifications as emp_notifications
)
from app.mqtt.client import mqtt_manager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting GridSphere IoT Core...")
    mqtt_manager.start()
    yield
    logger.info("Shutting down...")
    mqtt_manager.stop()


app = FastAPI(title="GridSphere Multi-Tenant API", version="2.0.0", lifespan=lifespan)

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


@app.get("/", response_class=HTMLResponse, tags=["UI"])
async def serve_dashboard():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    file_path = os.path.join(base_dir, "index.html")
    if os.path.exists(file_path):
        return FileResponse(file_path)
    return HTMLResponse(content=f"<h1>GridSphere IoT Core</h1><p>API Server is running. Visit <a href='/docs'>/docs</a> for documentation.</p>", status_code=200)


app.include_router(auth.router, prefix="/api/auth", tags=["Auth"])
app.include_router(tenants.router, prefix="/api/super-admin", tags=["Super Admin"])

app.include_router(tenant_dashboard.router, prefix="/api/tenant", tags=["Tenant"])
app.include_router(tenant_departments.router, prefix="/api/tenant", tags=["Tenant"])
app.include_router(tenant_org_admins.router, prefix="/api/tenant", tags=["Tenant"])
app.include_router(tenant_employees.router, prefix="/api/tenant", tags=["Tenant"])
app.include_router(tenant_attendance.router, prefix="/api/tenant", tags=["Tenant"])
app.include_router(tenant_reports.router, prefix="/api/tenant", tags=["Tenant"])
app.include_router(tenant_devices.router, prefix="/api/tenant", tags=["Tenant"])
app.include_router(tenant_settings.router, prefix="/api/tenant", tags=["Tenant"])
app.include_router(tenant_holidays.router, prefix="/api/tenant", tags=["Tenant"])
app.include_router(tenant_leaves.router, prefix="/api/tenant", tags=["Tenant"])

app.include_router(org_dashboard.router, prefix="/api/org-admin", tags=["Org Admin"])
app.include_router(org_employees.router, prefix="/api/org-admin", tags=["Org Admin"])
app.include_router(org_attendance.router, prefix="/api/org-admin", tags=["Org Admin"])
app.include_router(org_leaves.router, prefix="/api/org-admin", tags=["Org Admin"])
app.include_router(org_holidays.router, prefix="/api/org-admin", tags=["Org Admin"])
app.include_router(org_devices.router, prefix="/api/org-admin", tags=["Org Admin"])

app.include_router(emp_dashboard.router, prefix="/api/employee", tags=["Employee"])
app.include_router(emp_attendance.router, prefix="/api/employee", tags=["Employee"])
app.include_router(emp_profile.router, prefix="/api/employee", tags=["Employee"])
app.include_router(emp_leaves.router, prefix="/api/employee", tags=["Employee"])
app.include_router(emp_holidays.router, prefix="/api/employee", tags=["Employee"])
app.include_router(emp_notifications.router, prefix="/api/employee", tags=["Employee"])
app.include_router(tracker.router, prefix="/api", tags=["Tracker"])

app.include_router(attendance.router, prefix="/api/device", tags=["Device"])


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Error: {exc}")
    return JSONResponse(status_code=500, content={"detail": str(exc)})