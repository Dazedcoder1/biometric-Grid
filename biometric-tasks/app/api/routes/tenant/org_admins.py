from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import text
from pydantic import BaseModel
from typing import Optional
from app.db.session import get_db
from app.api.dependencies import verify_tenant_api_key
from app.models.domain import Tenant, Department, User
from app.core.security import hash_password

router = APIRouter()

class OrgAdminCreate(BaseModel):
    name: str
    email: str
    password: str
    dept_id: int

class OrgAdminUpdate(BaseModel):
    name: Optional[str] = None
    dept_id: Optional[int] = None
    is_active: Optional[bool] = None

@router.get('/org-admins')
async def list_org_admins(tenant: Tenant = Depends(verify_tenant_api_key), db: AsyncSession = Depends(get_db)):
    result = await db.execute(text("""
        SELECT u.id, u.name, u.email, u.dept_id, d.department_name, u.is_active, u.created_at,
               COUNT(e.id) FILTER (WHERE e.role = 'employee') as employee_count
        FROM users u JOIN departments d ON u.dept_id = d.department_id
        LEFT JOIN users e ON e.dept_id = u.dept_id AND e.role = 'employee'
        WHERE u.tenant_id = :tenant_id AND u.role = 'org_admin'
        GROUP BY u.id, d.department_name ORDER BY u.name
    """), {"tenant_id": tenant.id})
    return result.mappings().all()

@router.post('/org-admins')
async def create_org_admin(data: OrgAdminCreate, tenant: Tenant = Depends(verify_tenant_api_key), db: AsyncSession = Depends(get_db)):
    dept_result = await db.execute(select(Department).where(Department.department_id == data.dept_id, Department.tenant_id == tenant.id, Department.is_active == True))
    if not dept_result.scalars().first():
        raise HTTPException(400, "Invalid or inactive department")
    existing = await db.execute(select(User).where(User.email == data.email))
    if existing.scalars().first():
        raise HTTPException(400, "Email already exists")
    org_admin = User(tenant_id=tenant.id, name=data.name, email=data.email, password_hash=hash_password(data.password), dept_id=data.dept_id, role="org_admin", employee_code=None)
    db.add(org_admin)
    await db.commit()
    await db.refresh(org_admin)
    return {"message": "Org admin created", "org_admin": {"id": org_admin.id, "name": org_admin.name, "email": org_admin.email, "dept_id": org_admin.dept_id, "role": org_admin.role}}

@router.put('/org-admins/{admin_id}')
async def update_org_admin(admin_id: int, data: OrgAdminUpdate, tenant: Tenant = Depends(verify_tenant_api_key), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.id == admin_id, User.tenant_id == tenant.id, User.role == "org_admin"))
    org_admin = result.scalars().first()
    if not org_admin:
        raise HTTPException(404, "Org admin not found")
    if data.name is not None: org_admin.name = data.name
    if data.dept_id is not None:
        dept_result = await db.execute(select(Department).where(Department.department_id == data.dept_id, Department.tenant_id == tenant.id))
        if not dept_result.scalars().first():
            raise HTTPException(400, "Invalid department")
        org_admin.dept_id = data.dept_id
    if data.is_active is not None: org_admin.is_active = data.is_active
    await db.commit()
    return {"message": "Org admin updated"}

@router.delete('/org-admins/{admin_id}')
async def delete_org_admin(admin_id: int, tenant: Tenant = Depends(verify_tenant_api_key), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.id == admin_id, User.tenant_id == tenant.id, User.role == "org_admin"))
    org_admin = result.scalars().first()
    if not org_admin:
        raise HTTPException(404, "Org admin not found")
    org_admin.is_active = False
    await db.commit()
    return {"message": "Org admin deactivated"}