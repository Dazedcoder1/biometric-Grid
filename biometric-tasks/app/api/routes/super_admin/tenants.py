from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from pydantic import BaseModel
import secrets

from app.db.session import get_db
from app.api.dependencies import require_super_admin
from app.models.domain import User, Tenant

router = APIRouter()


class TenantCreate(BaseModel):
    organization_name: str
    manager_email: str
    manager_password: str


@router.get("/tenants")
async def list_tenants(
    current_user: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(Tenant).order_by(Tenant.name))
    tenants = result.scalars().all()
    return [
        {"id": t.id, "name": t.name, "api_key": t.api_key, "created_at": t.created_at}
        for t in tenants
    ]


@router.post("/tenants")
async def create_tenant(
    data: TenantCreate,
    current_user: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db)
):
    existing = await db.execute(select(Tenant).where(Tenant.name == data.organization_name))
    if existing.scalars().first():
        raise HTTPException(400, "Organization name already exists")

    api_key = secrets.token_hex(16)
    tenant = Tenant(name=data.organization_name, api_key=api_key)
    db.add(tenant)
    await db.commit()
    await db.refresh(tenant)

    return {
        "message": "Tenant created successfully",
        "tenant": {"id": tenant.id, "name": tenant.name, "api_key": tenant.api_key}
    }


@router.get("/tenants/{tenant_id}")
async def get_tenant(
    tenant_id: int,
    current_user: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db)
):
    from sqlalchemy import text
    result = await db.execute(select(Tenant).where(Tenant.id == tenant_id))
    tenant = result.scalars().first()
    if not tenant:
        raise HTTPException(404, "Tenant not found")

    stats = await db.execute(text("""
        SELECT
            COUNT(DISTINCT d.department_id) as department_count,
            COUNT(DISTINCT u.id) FILTER (WHERE u.role = 'org_admin') as org_admin_count,
            COUNT(DISTINCT u.id) FILTER (WHERE u.role = 'employee') as employee_count
        FROM tenants t
        LEFT JOIN departments d ON t.id = d.tenant_id
        LEFT JOIN users u ON t.id = u.tenant_id
        WHERE t.id = :tenant_id
        GROUP BY t.id
    """), {"tenant_id": tenant_id})
    stats_data = stats.mappings().first()

    return {
        "id": tenant.id, "name": tenant.name,
        "api_key": tenant.api_key, "created_at": tenant.created_at,
        "stats": {
            "departments": stats_data["department_count"] if stats_data else 0,
            "org_admins":  stats_data["org_admin_count"]  if stats_data else 0,
            "employees":   stats_data["employee_count"]   if stats_data else 0,
        }
    }


@router.patch("/tenants/{tenant_id}/reset-api-key")
async def reset_tenant_api_key(
    tenant_id: int,
    current_user: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(Tenant).where(Tenant.id == tenant_id))
    tenant = result.scalars().first()
    if not tenant:
        raise HTTPException(404, "Tenant not found")

    tenant.api_key = secrets.token_hex(16)
    await db.commit()
    return {"message": "API key reset successfully", "new_api_key": tenant.api_key}


@router.delete("/tenants/{tenant_id}")
async def delete_tenant(
    tenant_id: int,
    current_user: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(Tenant).where(Tenant.id == tenant_id))
    tenant = result.scalars().first()
    if not tenant:
        raise HTTPException(404, "Tenant not found")

    await db.delete(tenant)
    await db.commit()
    return {"message": "Tenant deleted successfully"}
