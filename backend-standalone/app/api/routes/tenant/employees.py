from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from typing import Optional
from app.db.session import get_db
from app.api.dependencies import verify_tenant_api_key
from app.models.domain import Tenant

router = APIRouter()


@router.get("/employees")
async def list_all_employees(
    dept_id: Optional[int] = None,
    tenant: Tenant = Depends(verify_tenant_api_key),
    db: AsyncSession = Depends(get_db)
):
    """Tenant Manager: List all employees across all departments"""
    
    query = """
        SELECT 
            u.id,
            u.name,
            u.employee_code,
            u.email,
            u.finger_id,
            u.is_active,
            u.created_at,
            d.department_id,
            d.department_name
        FROM users u
        LEFT JOIN departments d ON u.dept_id = d.department_id
        WHERE u.tenant_id = :tenant_id
        AND u.role = 'employee'
    """
    
    params = {"tenant_id": tenant.id}
    
    if dept_id:
        query += " AND u.dept_id = :dept_id"
        params["dept_id"] = dept_id
    
    query += " ORDER BY u.name"
    
    result = await db.execute(text(query), params)
    return result.mappings().all()


@router.get("/employees/{employee_id}")
async def get_employee_detail(
    employee_id: int,
    tenant: Tenant = Depends(verify_tenant_api_key),
    db: AsyncSession = Depends(get_db)
):
    """Tenant Manager: Get detailed employee information"""
    
    result = await db.execute(text("""
        SELECT 
            u.id,
            u.name,
            u.employee_code,
            u.email,
            u.finger_id,
            u.is_active,
            u.created_at,
            d.department_id,
            d.department_name,
            COUNT(a.id) as total_attendance,
            MAX(a.timestamp) as last_attendance
        FROM users u
        LEFT JOIN departments d ON u.dept_id = d.department_id
        LEFT JOIN attendance_logs a ON u.id = a.user_id
        WHERE u.id = :employee_id
        AND u.tenant_id = :tenant_id
        AND u.role = 'employee'
        GROUP BY u.id, d.department_id
    """), {
        "employee_id": employee_id,
        "tenant_id": tenant.id
    })
    
    employee = result.mappings().first()
    
    if not employee:
        raise HTTPException(404, "Employee not found")
    
    return employee


@router.get("/employees/{employee_id}/attendance")
async def get_employee_attendance(
    employee_id: int,
    month: Optional[int] = None,
    year: Optional[int] = None,
    tenant: Tenant = Depends(verify_tenant_api_key),
    db: AsyncSession = Depends(get_db)
):
    """Tenant Manager: View employee's attendance history"""
    
    query = """
        SELECT 
            DATE(timestamp) as date,
            MIN(timestamp) FILTER (WHERE record_type = 'IN') as check_in,
            MAX(timestamp) FILTER (WHERE record_type = 'OUT') as check_out,
            CASE 
                WHEN MIN(timestamp) FILTER (WHERE record_type = 'IN') IS NOT NULL 
                THEN 'present' 
                ELSE 'absent' 
            END as status
        FROM attendance_logs
        WHERE user_id = :employee_id
        AND tenant_id = :tenant_id
    """
    
    params = {
        "employee_id": employee_id,
        "tenant_id": tenant.id
    }
    
    if month and year:
        query += " AND EXTRACT(MONTH FROM timestamp) = :month AND EXTRACT(YEAR FROM timestamp) = :year"
        params["month"] = month
        params["year"] = year
    
    query += " GROUP BY DATE(timestamp) ORDER BY date DESC"
    
    result = await db.execute(text(query), params)
    return result.mappings().all()


@router.get("/employees/fingerprint/{finger_id}")
async def find_employee_by_fingerprint(
    finger_id: int,
    tenant: Tenant = Depends(verify_tenant_api_key),
    db: AsyncSession = Depends(get_db)
):
    """Tenant Manager: Find employee by fingerprint ID"""
    
    result = await db.execute(text("""
        SELECT 
            u.id,
            u.name,
            u.employee_code,
            u.finger_id,
            d.department_name
        FROM users u
        LEFT JOIN departments d ON u.dept_id = d.department_id
        WHERE u.tenant_id = :tenant_id
        AND u.finger_id = :finger_id
        AND u.role = 'employee'
    """), {
        "tenant_id": tenant.id,
        "finger_id": finger_id
    })
    
    employee = result.mappings().first()
    
    if not employee:
        raise HTTPException(404, "No employee found with this fingerprint ID")
    
    return employee