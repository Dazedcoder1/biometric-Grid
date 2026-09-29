from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import logging
import os

from app.mqtt.client import mqtt_manager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting GridSphere IoT Core...")
    mqtt_manager.start()

    # Background reconcile for GitHub-mirrored tasks. Webhooks are the fast
    # path; this catches deliveries that never arrived.
    import asyncio
    from app.services.github_service import reconcile_loop
    github_task = asyncio.create_task(reconcile_loop())

    # Marks expired shares and writes "access expired" to the audit log.
    # It does NOT enforce expiry — every access query already filters on
    # expires_at, so a dead sweeper means late log entries, not leaked access.
    from app.services.share_sweeper import expiry_loop
    share_task = asyncio.create_task(expiry_loop())

    yield

    logger.info("Shutting down...")
    for task in (github_task, share_task):
        task.cancel()
    for task in (github_task, share_task):
        try:
            await task
        except asyncio.CancelledError:
            pass
    mqtt_manager.stop()


app = FastAPI(title="GridSphere Multi-Tenant API", lifespan=lifespan)

# ─── CORS (allow Vite dev server + production origin) ────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Static frontend (old HTML) ───────────────────────────────────────────────
base_dir     = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
frontend_dir = os.path.join(base_dir, "frontend")

if os.path.exists(frontend_dir):
    app.mount("/ui", StaticFiles(directory=frontend_dir, html=True), name="frontend")
else:
    logger.warning("Legacy frontend directory not found — skipping.")


@app.get("/", tags=["UI"])
async def serve_root():
    return RedirectResponse(url="/ui/")


# ─── Auth ─────────────────────────────────────────────────────────────────────
from app.api.routes.auth import router as auth_router
app.include_router(auth_router, prefix="/api/auth", tags=["Auth"])

# ─── Device-level attendance (called from fingerprint scanner) ────────────────
from app.api.routes.attendance import router as attendance_router
app.include_router(attendance_router, prefix="/api/attendance", tags=["Device Attendance"])

# ─── Super Admin ──────────────────────────────────────────────────────────────
from app.api.routes.super_admin.tenants import router as super_tenants_router
app.include_router(super_tenants_router, prefix="/api/super", tags=["Super Admin"])

# ─── Tenant Admin (uses X-API-Key header) ─────────────────────────────────────
from app.api.routes.tenant.dashboard    import router as tenant_dash_router
from app.api.routes.tenant.departments  import router as tenant_dept_router
from app.api.routes.tenant.org_admins   import router as tenant_orgadmin_router
from app.api.routes.tenant.employees    import router as tenant_emp_router
from app.api.routes.tenant.attendance   import router as tenant_att_router
from app.api.routes.tenant.leaves       import router as tenant_leave_router
from app.api.routes.tenant.holidays     import router as tenant_holiday_router
from app.api.routes.tenant.devices      import router as tenant_device_router
from app.api.routes.tenant.settings     import router as tenant_settings_router
from app.api.routes.tenant.reports      import router as tenant_reports_router

TENANT_PREFIX = "/api/tenant"
app.include_router(tenant_dash_router,     prefix=TENANT_PREFIX, tags=["Tenant Admin"])
app.include_router(tenant_dept_router,     prefix=TENANT_PREFIX, tags=["Tenant Admin"])
app.include_router(tenant_orgadmin_router, prefix=TENANT_PREFIX, tags=["Tenant Admin"])
app.include_router(tenant_emp_router,      prefix=TENANT_PREFIX, tags=["Tenant Admin"])
app.include_router(tenant_att_router,      prefix=TENANT_PREFIX, tags=["Tenant Admin"])
app.include_router(tenant_leave_router,    prefix=TENANT_PREFIX, tags=["Tenant Admin"])
app.include_router(tenant_holiday_router,  prefix=TENANT_PREFIX, tags=["Tenant Admin"])
app.include_router(tenant_device_router,   prefix=TENANT_PREFIX, tags=["Tenant Admin"])
app.include_router(tenant_settings_router, prefix=TENANT_PREFIX, tags=["Tenant Admin"])
app.include_router(tenant_reports_router,  prefix=TENANT_PREFIX, tags=["Tenant Admin"])

# ─── Org Admin (uses JWT Bearer) ──────────────────────────────────────────────
from app.api.routes.org_admin.dashboard  import router as org_dash_router
from app.api.routes.org_admin.employees  import router as org_emp_router
from app.api.routes.org_admin.attendance import router as org_att_router
from app.api.routes.org_admin.leaves     import router as org_leave_router
from app.api.routes.org_admin.holidays   import router as org_holiday_router
from app.api.routes.org_admin.devices    import router as org_devices_router
from app.api.routes.org_admin.activity   import router as org_activity_router

ORG_PREFIX = "/api/org"
app.include_router(org_dash_router,     prefix=ORG_PREFIX, tags=["Org Admin"])
app.include_router(org_emp_router,      prefix=ORG_PREFIX, tags=["Org Admin"])
app.include_router(org_att_router,      prefix=ORG_PREFIX, tags=["Org Admin"])
app.include_router(org_leave_router,    prefix=ORG_PREFIX, tags=["Org Admin"])
app.include_router(org_holiday_router,  prefix=ORG_PREFIX, tags=["Org Admin"])
app.include_router(org_devices_router,  prefix=ORG_PREFIX, tags=["Org Admin"])
app.include_router(org_activity_router, prefix=ORG_PREFIX, tags=["Org Admin"])

# ─── Shared by every signed-in role ───────────────────────────────────────────
# Office hours are one tenant-wide fact that attendance screens for all three
# roles need. It used to live only under /api/tenant, which rejects anyone who
# is not a Tenant Admin — so org and employee pages silently fell back to
# hardcoded defaults. See routes/common/settings.py.
from app.api.routes.common.settings import router as common_settings_router

app.include_router(common_settings_router, prefix="/api", tags=["Shared"])

# ─── Employee (uses JWT Bearer) ───────────────────────────────────────────────
from app.api.routes.employee.dashboard      import router as emp_dash_router
from app.api.routes.employee.profile        import router as emp_profile_router
from app.api.routes.employee.attendance     import router as emp_att_router
from app.api.routes.employee.leaves         import router as emp_leave_router
from app.api.routes.employee.holidays       import router as emp_holiday_router
from app.api.routes.employee.notifications  import router as emp_notif_router

EMP_PREFIX = "/api/employee"
app.include_router(emp_dash_router,    prefix=EMP_PREFIX, tags=["Employee"])
app.include_router(emp_profile_router, prefix=EMP_PREFIX, tags=["Employee"])
app.include_router(emp_att_router,     prefix=EMP_PREFIX, tags=["Employee"])
# These three declare bare paths ("", "/balance", "/{id}/read") rather than
# carrying their own segment, so they need a sub-prefix. Mounted flat they all
# collapsed onto /api/employee — "/api/employee/{id}/read" and
# "/api/employee/{leave_id}/cancel" even shadowed each other, and every call
# the client made to /api/employee/leaves/... returned 404.
app.include_router(emp_leave_router,   prefix=f"{EMP_PREFIX}/leaves",        tags=["Employee"])
app.include_router(emp_holiday_router, prefix=f"{EMP_PREFIX}/holidays",      tags=["Employee"])
app.include_router(emp_notif_router,   prefix=f"{EMP_PREFIX}/notifications", tags=["Employee"])

# ─── Task manager (ported from the standalone task-manager app) ───────────────
from app.api.routes.tenant.tasks         import router as tenant_tasks_router
from app.api.routes.tenant.github_repos  import router as tenant_github_router
from app.api.routes.org_admin.tasks      import router as org_tasks_router
from app.api.routes.employee.tasks       import router as emp_tasks_router
from app.api.routes.webhooks.github      import router as github_webhook_router

app.include_router(tenant_tasks_router,  prefix=TENANT_PREFIX, tags=["Tasks - Tenant Admin"])
app.include_router(tenant_github_router, prefix=TENANT_PREFIX, tags=["Tasks - GitHub Config"])
app.include_router(org_tasks_router,     prefix=ORG_PREFIX,    tags=["Tasks - Org Admin"])
app.include_router(emp_tasks_router,     prefix=EMP_PREFIX,    tags=["Tasks - Employee"])

# Unauthenticated by necessity — every request is HMAC-verified inside.
app.include_router(github_webhook_router, prefix="/api/webhooks", tags=["Webhooks"])

# ─── Credential vault ─────────────────────────────────────────────────────────
# Authorisation is per-route via app/api/deps_security.py, not a blanket
# dependency here: reveal needs step-up, the rest do not, and burying that
# distinction in a router-level guard would hide it.
from app.api.routes.vault.activity import router as vault_activity_router
from app.api.routes.vault.credentials import router as vault_credentials_router
from app.api.routes.vault.dependencies import router as vault_dependencies_router
from app.api.routes.vault.mfa import router as vault_mfa_router
from app.api.routes.vault.security import router as vault_security_router
from app.api.routes.vault.shares import router as vault_shares_router

VAULT_PREFIX = "/api/vault"
app.include_router(vault_mfa_router, prefix=VAULT_PREFIX, tags=["Vault - MFA"])
app.include_router(vault_credentials_router, prefix=VAULT_PREFIX, tags=["Vault - Credentials"])
app.include_router(vault_shares_router, prefix=VAULT_PREFIX, tags=["Vault - Sharing"])
app.include_router(vault_activity_router, prefix=VAULT_PREFIX, tags=["Vault - Activity & Audit"])
app.include_router(vault_security_router, prefix=VAULT_PREFIX, tags=["Vault - Security & Rotation"])
app.include_router(vault_dependencies_router, prefix=VAULT_PREFIX, tags=["Vault - Dependencies"])


# ─── Global error handler ─────────────────────────────────────────────────────
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled error: {exc}", exc_info=True)
    return JSONResponse(status_code=500, content={"detail": "Internal Server Error"})