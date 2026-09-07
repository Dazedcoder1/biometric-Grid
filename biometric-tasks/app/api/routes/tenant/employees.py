from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from typing import Optional
from app.db.session import get_db
from app.api.dependencies import verify_tenant_api_key
from app.models.domain import Tenant

router = APIRouter()

@router.get('/employees')
async def list_all_employees(dept_id: Optional[int] = None, tenant: Tenant = Depends(verify_tenant_api_key), db: AsyncSession = Depends(get_db)):
    query = """
        SELECT u.id, u.name, u.employee_code, u.email, u.finger_id, u.is_active, u.created_at,
               d.department_id, d.department_name
        FROM users u LEFT JOIN departments d ON u.dept_id = d.department_id
        WHERE u.tenant_id = :tenant_id AND u.role = 'employee'
    """
    params = {"tenant_id": tenant.id}
    if dept_id:
        query += " AND u.dept_id = :dept_id"
        params["dept_id"] = dept_id
    query += " ORDER BY u.name"
    result = await db.execute(text(query), params)
    return result.mappings().all()