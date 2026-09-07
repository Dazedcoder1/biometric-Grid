from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func, text, insert
from sqlalchemy.future import select
from pydantic import BaseModel
from typing import Optional
import secrets
import string
from app.db.session import get_db
from app.api.dependencies import get_current_user, require_role
from app.models.domain import User, Notification
from app.core.security import hash_password

router = APIRouter()


def generate_strong_password(length: int = 10) -> str:
    """Generate a strong random password"""
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
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


# =========================
# BACKGROUND TASKS
# =========================

async def notify_other_admins_bg(
    tenant_id: int,
    dept_id: int,
    actor_id: int,
    actor_name: str,
    employee_id: int,
    employee_name: str,
    db: AsyncSession
):
    """Background task: Notify OTHER org admins about new employee"""
    
    # Get other org admins in this department
    org_admins = await db.execute(text("""
        SELECT id FROM users
        WHERE tenant_id = :tenant_id
        AND dept_id = :dept_id
        AND role = 'org_admin'
        AND is_active = true
        AND id != :actor_id
    """), {
        "tenant_id": tenant_id,
        "dept_id": dept_id,
        "actor_id": actor_id
    })
    admin_ids = [row[0] for row in org_admins.all()]
    
    if not admin_ids:
        return
    
    notification_values = []
    for admin_id in admin_ids:
        notification_values.append({
            "tenant_id": tenant_id,
            "actor_id": actor_id,
            "actor_name": actor_name,
            "recipient_id": admin_id,
            "event_type": "employee_added",
            "entity_type": "User",
            "entity_id": employee_id,
            "entity_name": employee_name,
            "title": "New Employee Added",
            "message": f"{employee_name} was added to your department",
            "is_read": False
        })
    
    await db.execute(insert(Notification).values(notification_values))
    await db.commit()


async def notify_employee_deactivated_bg(
    tenant_id: int,
    dept_id: int,
    actor_id: int,
    actor_name: str,
    employee_id: int,
    employee_name: str,
    db: AsyncSession
):
    """Background task: Notify OTHER org admins about employee deactivation"""
    
    org_admins = await db.execute(text("""
        SELECT id FROM users
        WHERE tenant_id = :tenant_id
        AND dept_id = :dept_id
        AND role = 'org_admin'
        AND is_active = true
        AND id != :actor_id
    """), {
        "tenant_id": tenant_id,
        "dept_id": dept_id,
        "actor_id": actor_id
    })
    admin_ids = [row[0] for row in org_admins.all()]
    
    if not admin_ids:
        return
    
    notification_values = []
    for admin_id in admin_ids:
        notification_values.append({
            "tenant_id": tenant_id,
            "actor_id": actor_id,
            "actor_name": actor_name,
            "recipient_id": admin_id,
            "event_type": "employee_deactivated",
            "entity_type": "User",
            "entity_id": employee_id,
            "entity_name": employee_name,
            "title": "Employee Deactivated",
            "message": f"{employee_name} has been deactivated",
            "is_read": False
        })
    
    await db.execute(insert(Notification).values(notification_values))
    await db.commit()


async def notify_fingerprint_enrolled_bg(
    tenant_id: int,
    actor_id: int,
    employee_id: int,
    employee_name: str,
    finger_id: int,
    db: AsyncSession
):
    """Background task: Notify employee about fingerprint enrollment"""
    
    await db.execute(insert(Notification).values([{
        "tenant_id": tenant_id,
        "actor_id": actor_id,
        "actor_name": "System",
        "recipient_id": employee_id,
        "event_type": "fingerprint_enrolled",
        "entity_type": "User",
        "entity_id": employee_id,
        "entity_name": employee_name,
        "title": "Fingerprint Enrolled",
        "message": f"Your fingerprint has been successfully registered (Slot {finger_id})",
        "is_read": False
    }]))
    await db.commit()


# =========================
# ROUTES
# =========================

@router.get("/employees/available-finger-slots")
async def available_finger_slots(
    current_user: User = Depends(require_role("org_admin")),
    db: AsyncSession = Depends(get_db)
):
    tenant_id = current_user.tenant_id
    result = await db.execute(
        select(User.finger_id).where(User.tenant_id == tenant_id, User.finger_id.isnot(None))
    )
    used = set(result.scalars().all())
    available = [i for i in range(1, 128) if i not in used]
    return {"used": list(used), "available": available, "total": 127, "free_count": len(available)}


@router.get("/employees")
async def list_employees(
    current_user: User = Depends(require_role("org_admin")),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(User).where(
            User.tenant_id == current_user.tenant_id,
            User.dept_id == current_user.dept_id,
            User.role == "employee"
        ).order_by(User.name)
    )
    return result.scalars().all()


@router.post("/employees")
async def create_employee(
    data: EmployeeCreate,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(require_role("org_admin")),
    db: AsyncSession = Depends(get_db)
):
    tenant_id = current_user.tenant_id
    dept_id = current_user.dept_id
    
    auto_generated = {"employee_code": False, "finger_id": False, "password": False}
    
    # AUTO-GENERATE employee_code
    if not data.employee_code:
        count_result = await db.execute(
            select(func.count()).select_from(User).where(
                User.tenant_id == tenant_id,
                User.role == "employee"
            )
        )
        emp_count = count_result.scalar() or 0
        data.employee_code = f"EMP{tenant_id}{emp_count + 1:03d}"
        auto_generated["employee_code"] = True
    
    # Check employee_code unique
    existing = await db.execute(
        select(User).where(
            User.tenant_id == tenant_id,
            User.employee_code == data.employee_code
        )
    )
    if existing.scalars().first():
        raise HTTPException(400, "Employee code already exists")
    
    # AUTO-GENERATE password
    original_password = data.password
    if not data.password:
        original_password = generate_strong_password(10)
        auto_generated["password"] = True
    
    # AUTO-ASSIGN finger_id
    if data.finger_id is None:
        used_result = await db.execute(
            select(User.finger_id).where(
                User.tenant_id == tenant_id,
                User.finger_id.isnot(None)
            )
        )
        used = set(used_result.scalars().all())
        for i in range(1, 128):
            if i not in used:
                data.finger_id = i
                break
        
        if data.finger_id is None:
            raise HTTPException(400, "No available fingerprint slots (1-127 all used)")
        auto_generated["finger_id"] = True
    else:
        finger_check = await db.execute(
            select(User).where(
                User.tenant_id == tenant_id,
                User.finger_id == data.finger_id
            )
        )
        if finger_check.scalars().first():
            raise HTTPException(400, f"Finger ID {data.finger_id} already assigned")
    
    # Create employee
    user = User(
        tenant_id=tenant_id,
        employee_code=data.employee_code,
        name=data.name,
        email=None,
        dept_id=dept_id,
        finger_id=data.finger_id,
        role="employee",
        password_hash=hash_password(original_password)
    )
    
    db.add(user)
    await db.commit()
    await db.refresh(user)
    
    # Schedule notification in BACKGROUND
    background_tasks.add_task(
        notify_other_admins_bg,
        tenant_id=tenant_id,
        dept_id=dept_id,
        actor_id=current_user.id,
        actor_name=current_user.name,
        employee_id=user.id,
        employee_name=user.name,
        db=db
    )
    
    return {
        "message": "Employee created successfully",
        "credentials": {
            "name": user.name,
            "employee_code": user.employee_code,
            "password": original_password,
            "finger_id": user.finger_id
        },
        "auto_generated": auto_generated,
        "instructions": "Share these credentials with the employee. They should change password on first login."
    }


@router.patch("/employees/{employee_id}/assign-fingerprint")
async def assign_fingerprint(
    employee_id: int,
    data: AssignFingerprintRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(require_role("org_admin")),
    db: AsyncSession = Depends(get_db)
):
    tenant_id, dept_id = current_user.tenant_id, current_user.dept_id
    result = await db.execute(
        select(User).where(
            User.id == employee_id,
            User.tenant_id == tenant_id,
            User.dept_id == dept_id,
            User.role == "employee"
        )
    )
    employee = result.scalars().first()
    if not employee:
        raise HTTPException(404, "Employee not found in your department")
    
    finger_check = await db.execute(
        select(User).where(
            User.tenant_id == tenant_id,
            User.finger_id == data.finger_id,
            User.id != employee_id
        )
    )
    if finger_check.scalars().first():
        raise HTTPException(400, f"Finger ID {data.finger_id} already in use")
    
    employee.finger_id = data.finger_id
    await db.commit()
    
    # Schedule notification in BACKGROUND
    background_tasks.add_task(
        notify_fingerprint_enrolled_bg,
        tenant_id=tenant_id,
        actor_id=current_user.id,
        employee_id=employee.id,
        employee_name=employee.name,
        finger_id=data.finger_id,
        db=db
    )
    
    return {
        "message": f"Fingerprint slot {data.finger_id} assigned",
        "employee_id": employee.id,
        "finger_id": data.finger_id
    }


@router.put("/employees/{employee_id}")
async def update_employee(
    employee_id: int,
    data: EmployeeUpdate,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(require_role("org_admin")),
    db: AsyncSession = Depends(get_db)
):
    tenant_id, dept_id = current_user.tenant_id, current_user.dept_id
    result = await db.execute(
        select(User).where(
            User.id == employee_id,
            User.tenant_id == tenant_id,
            User.dept_id == dept_id,
            User.role == "employee"
        )
    )
    employee = result.scalars().first()
    if not employee:
        raise HTTPException(404, "Employee not found in your department")
    
    was_active = employee.is_active
    
    if data.name is not None:
        employee.name = data.name
    if data.finger_id is not None:
        if data.finger_id != employee.finger_id:
            check = await db.execute(
                select(User).where(
                    User.tenant_id == tenant_id,
                    User.finger_id == data.finger_id,
                    User.id != employee_id
                )
            )
            if check.scalars().first():
                raise HTTPException(400, "Finger ID already in use")
        employee.finger_id = data.finger_id
    if data.is_active is not None:
        employee.is_active = data.is_active
        if not data.is_active:
            employee.finger_id = None
    
    await db.commit()
    
    # Schedule notification in BACKGROUND if deactivated
    if was_active and employee.is_active is False:
        background_tasks.add_task(
            notify_employee_deactivated_bg,
            tenant_id=tenant_id,
            dept_id=dept_id,
            actor_id=current_user.id,
            actor_name=current_user.name,
            employee_id=employee.id,
            employee_name=employee.name,
            db=db
        )
    
    return {"message": "Employee updated successfully"}


@router.delete("/employees/{employee_id}")
async def delete_employee(
    employee_id: int,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(require_role("org_admin")),
    db: AsyncSession = Depends(get_db)
):
    tenant_id, dept_id = current_user.tenant_id, current_user.dept_id
    result = await db.execute(
        select(User).where(
            User.id == employee_id,
            User.tenant_id == tenant_id,
            User.dept_id == dept_id,
            User.role == "employee"
        )
    )
    employee = result.scalars().first()
    if not employee:
        raise HTTPException(404, "Employee not found in your department")
    
    employee.is_active = False
    employee.finger_id = None
    await db.commit()
    
    # Schedule notification in BACKGROUND
    background_tasks.add_task(
        notify_employee_deactivated_bg,
        tenant_id=tenant_id,
        dept_id=dept_id,
        actor_id=current_user.id,
        actor_name=current_user.name,
        employee_id=employee.id,
        employee_name=employee.name,
        db=db
    )
    
    return {"message": "Employee deactivated successfully"}


@router.get("/employees/{employee_id}")
async def get_employee(
    employee_id: int,
    current_user: User = Depends(require_role("org_admin")),
    db: AsyncSession = Depends(get_db)
):
    tenant_id, dept_id = current_user.tenant_id, current_user.dept_id
    result = await db.execute(
        select(User).where(
            User.id == employee_id,
            User.tenant_id == tenant_id,
            User.dept_id == dept_id,
            User.role == "employee"
        )
    )
    employee = result.scalars().first()
    if not employee:
        raise HTTPException(404, "Employee not found in your department")
    return {
        "id": employee.id,
        "name": employee.name,
        "employee_code": employee.employee_code,
        "finger_id": employee.finger_id,
        "is_active": employee.is_active
    }