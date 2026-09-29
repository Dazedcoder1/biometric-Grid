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


@router.get('/employees/{employee_id}')
async def get_employee(employee_id: int, tenant: Tenant = Depends(verify_tenant_api_key), db: AsyncSession = Depends(get_db)):
    """One employee. Backs the detail modal on the Tenant Employees page,
    which had no route and so opened onto an error."""
    result = await db.execute(text("""
        SELECT u.id, u.name, u.employee_code, u.email, u.finger_id, u.is_active,
               u.created_at, u.role, d.department_id, d.department_name
          FROM users u LEFT JOIN departments d ON u.dept_id = d.department_id
         WHERE u.id = :employee_id AND u.tenant_id = :tenant_id
    """), {"employee_id": employee_id, "tenant_id": tenant.id})
    employee = result.mappings().first()
    # Scoped to the tenant, so an id belonging to another organisation is
    # reported as absent rather than as forbidden — a 403 would confirm the
    # account exists.
    if not employee:
        raise HTTPException(404, "Employee not found")
    return employee


@router.get('/employees/{employee_id}/attendance')
async def employee_attendance(
    employee_id: int,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 100,
    tenant: Tenant = Depends(verify_tenant_api_key),
    db: AsyncSession = Depends(get_db),
):
    """
    One employee's attendance history, a day per row.

    The existence check runs first and separately: without it, an id from
    another tenant would return an empty list, which reads as "this person has
    never clocked in" rather than "no such person here".
    """
    exists = await db.execute(text(
        "SELECT 1 FROM users WHERE id=:id AND tenant_id=:tenant_id"
    ), {"id": employee_id, "tenant_id": tenant.id})
    if not exists.first():
        raise HTTPException(404, "Employee not found")

    query = """
        SELECT DATE(a.timestamp) AS date,
               MIN(a.timestamp) FILTER (WHERE a.record_type='IN')  AS check_in,
               MAX(a.timestamp) FILTER (WHERE a.record_type='OUT') AS check_out,
               COUNT(*) AS punches
          FROM attendance_logs a
         WHERE a.user_id = :employee_id AND a.tenant_id = :tenant_id
    """
    params = {"employee_id": employee_id, "tenant_id": tenant.id, "limit": min(limit, 500)}
    if start_date:
        query += " AND DATE(a.timestamp) >= CAST(:start_date AS DATE)"
        params["start_date"] = start_date
    if end_date:
        query += " AND DATE(a.timestamp) <= CAST(:end_date AS DATE)"
        params["end_date"] = end_date
    query += " GROUP BY DATE(a.timestamp) ORDER BY DATE(a.timestamp) DESC LIMIT :limit"

    result = await db.execute(text(query), params)
    return result.mappings().all()