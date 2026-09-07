from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func
from sqlalchemy.future import select
from pydantic import BaseModel
from typing import Optional
import secrets, string
from app.db.session import get_db
from app.api.dependencies import require_role
from app.models.domain import User
from app.core.security import hash_password
from app.services.notification_service import notify_single_user

router = APIRouter()

def generate_strong_password(length: int = 10) -> str:
    alphabet = string.ascii_letters + string.digits + '!@#$%^&*'
    return ''.join(secrets.choice(alphabet) for _ in range(length))

class EmployeeCreate(BaseModel):
    name: str
    employee_code: Optional[str] = None
    password: Optional[str] = None
    finger_id: Optional[int] = None

class EmployeeUpdate(BaseModel):
    name: Optional[str] = None
    finger_id: Optional[int] = None
    is_active: Optional[bool] = None

class AssignFingerprintRequest(BaseModel):
    finger_id: int

@router.get('/employees/available-finger-slots')
async def available_finger_slots(current_user: User = Depends(require_role('org_admin')), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User.finger_id).where(User.tenant_id == current_user.tenant_id, User.finger_id.isnot(None)))
    used = set(result.scalars().all())
    available = [i for i in range(1, 128) if i not in used]
    return {"used": list(used), "available": available, "total": 127, "free_count": len(available)}

@router.get('/employees')
async def list_employees(current_user: User = Depends(require_role('org_admin')), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.tenant_id == current_user.tenant_id, User.dept_id == current_user.dept_id, User.role == 'employee').order_by(User.name))
    return result.scalars().all()

@router.post('/employees')
async def create_employee(data: EmployeeCreate, current_user: User = Depends(require_role('org_admin')), db: AsyncSession = Depends(get_db)):
    tenant_id = current_user.tenant_id
    dept_id   = current_user.dept_id
    auto_generated = {"employee_code": False, "finger_id": False, "password": False}
    if not data.employee_code:
        count_result = await db.execute(select(func.count()).select_from(User).where(User.tenant_id == tenant_id, User.role == 'employee'))
        emp_count = count_result.scalar() or 0
        data.employee_code = f"EMP{tenant_id}{emp_count + 1:03d}"
        auto_generated["employee_code"] = True
    existing = await db.execute(select(User).where(User.tenant_id == tenant_id, User.employee_code == data.employee_code))
    if existing.scalars().first():
        raise HTTPException(400, "Employee code already exists")
    original_password = data.password
    if not data.password:
        original_password = generate_strong_password(10)
        auto_generated["password"] = True
    if data.finger_id is None:
        used_result = await db.execute(select(User.finger_id).where(User.tenant_id == tenant_id, User.finger_id.isnot(None)))
        used = set(used_result.scalars().all())
        for i in range(1, 128):
            if i not in used:
                data.finger_id = i
                break
        if data.finger_id is None:
            raise HTTPException(400, "No available fingerprint slots")
        auto_generated["finger_id"] = True
    else:
        finger_check = await db.execute(select(User).where(User.tenant_id == tenant_id, User.finger_id == data.finger_id))
        if finger_check.scalars().first():
            raise HTTPException(400, f"Finger ID {data.finger_id} already assigned")
    user = User(tenant_id=tenant_id, employee_code=data.employee_code, name=data.name, email=None, dept_id=dept_id, finger_id=data.finger_id, role='employee', password_hash=hash_password(original_password))
    db.add(user)
    await db.commit()
    await db.refresh(user)
    await notify_single_user(db, tenant_id, current_user.id, current_user.id, "employee_added", "New Employee Added", f"{user.name} ({user.employee_code}) added to your department")
    return {"message": "Employee created", "credentials": {"name": user.name, "employee_code": user.employee_code, "password": original_password, "finger_id": user.finger_id}, "auto_generated": auto_generated}

@router.put('/employees/{employee_id}')
async def update_employee(employee_id: int, data: EmployeeUpdate, current_user: User = Depends(require_role('org_admin')), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.id == employee_id, User.tenant_id == current_user.tenant_id, User.dept_id == current_user.dept_id, User.role == 'employee'))
    employee = result.scalars().first()
    if not employee: raise HTTPException(404, "Employee not found")
    if data.name is not None: employee.name = data.name
    if data.finger_id is not None: employee.finger_id = data.finger_id
    if data.is_active is not None:
        employee.is_active = data.is_active
        if not data.is_active: employee.finger_id = None
    await db.commit()
    return {"message": "Employee updated"}

@router.delete('/employees/{employee_id}')
async def delete_employee(employee_id: int, current_user: User = Depends(require_role('org_admin')), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.id == employee_id, User.tenant_id == current_user.tenant_id, User.dept_id == current_user.dept_id, User.role == 'employee'))
    employee = result.scalars().first()
    if not employee: raise HTTPException(404, "Employee not found")
    employee.is_active = False
    employee.finger_id = None
    await db.commit()
    return {"message": "Employee deactivated"}

@router.get('/employees/{employee_id}')
async def get_employee(employee_id: int, current_user: User = Depends(require_role('org_admin')), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.id == employee_id, User.tenant_id == current_user.tenant_id, User.dept_id == current_user.dept_id, User.role == 'employee'))
    employee = result.scalars().first()
    if not employee: raise HTTPException(404, "Employee not found")
    return {"id": employee.id, "name": employee.name, "employee_code": employee.employee_code, "finger_id": employee.finger_id, "is_active": employee.is_active}