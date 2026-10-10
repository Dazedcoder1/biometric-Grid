from fastapi import APIRouter, Depends, HTTPException, Request
from app.core import activity
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import text
from pydantic import BaseModel
from app.db.session import get_db
from app.api.dependencies import verify_tenant_api_key
from app.models.domain import Tenant, Department, User

router = APIRouter()

class DepartmentCreate(BaseModel):
    department_name: str

class DepartmentUpdate(BaseModel):
    department_name: str

@router.get('/departments')
async def list_departments(tenant: Tenant = Depends(verify_tenant_api_key), db: AsyncSession = Depends(get_db)):
    result = await db.execute(text("""
        SELECT d.department_id, d.department_name, d.is_active, d.created_at,
               COUNT(u.id) FILTER (WHERE u.role = 'org_admin') as org_admin_count,
               COUNT(u.id) FILTER (WHERE u.role = 'employee' AND u.is_active = true) as employee_count
        FROM departments d LEFT JOIN users u ON d.department_id = u.dept_id
        WHERE d.tenant_id = :tenant_id GROUP BY d.department_id ORDER BY d.department_name
    """), {"tenant_id": tenant.id})
    return result.mappings().all()

@router.post('/departments')
async def create_department(data: DepartmentCreate, request: Request, tenant: Tenant = Depends(verify_tenant_api_key), db: AsyncSession = Depends(get_db)):
    existing = await db.execute(select(Department).where(Department.tenant_id == tenant.id, Department.department_name == data.department_name))
    if existing.scalars().first():
        raise HTTPException(400, "Department already exists")
    dept = Department(tenant_id=tenant.id, department_name=data.department_name, is_active=True)
    db.add(dept)
    await db.flush()
    await activity.log(
        db, request, action="department.created", tenant_id=tenant.id,
        target_type="department", target_id=dept.department_id,
        details={"name": dept.department_name},
    )
    await db.commit()
    await db.refresh(dept)
    return {"message": "Department created", "department": {"department_id": dept.department_id, "department_name": dept.department_name}}

@router.put('/departments/{department_id}')
async def update_department(department_id: int, data: DepartmentUpdate, request: Request, tenant: Tenant = Depends(verify_tenant_api_key), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Department).where(Department.department_id == department_id, Department.tenant_id == tenant.id))
    dept = result.scalars().first()
    if not dept:
        raise HTTPException(404, "Department not found")
    old_name = dept.department_name
    dept.department_name = data.department_name
    if old_name != dept.department_name:
        await activity.log(
            db, request, action="department.renamed", tenant_id=tenant.id,
            target_type="department", target_id=dept.department_id,
            details={"from": old_name, "to": dept.department_name},
        )
    await db.commit()
    return {"message": "Department updated"}

@router.delete('/departments/{department_id}')
async def delete_department(department_id: int, request: Request, tenant: Tenant = Depends(verify_tenant_api_key), db: AsyncSession = Depends(get_db)):
    user_result = await db.execute(select(User).where(User.tenant_id == tenant.id, User.dept_id == department_id))
    if user_result.scalars().first():
        raise HTTPException(400, "Cannot delete department with existing users")
    result = await db.execute(select(Department).where(Department.department_id == department_id, Department.tenant_id == tenant.id))
    dept = result.scalars().first()
    if not dept:
        raise HTTPException(404, "Department not found")
    await activity.log(
        db, request, action="department.deleted", tenant_id=tenant.id,
        target_type="department", target_id=dept.department_id,
        details={"name": dept.department_name},
    )
    await db.delete(dept)
    await db.commit()
    return {"message": "Department deleted"}