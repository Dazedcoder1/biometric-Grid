from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from app.models.domain import User


# =========================
# ENROLL USER (FIXED ✅)
# =========================

async def enroll_user(
    tenant_id: int,
    finger_id: int,
    name: str,
    employee_code: str,
    db: AsyncSession
):
    # =========================
    # CHECK: employee_code unique per tenant
    # =========================
    existing = await db.execute(
        select(User).where(
            User.tenant_id == tenant_id,
            User.employee_code == employee_code
        )
    )
    if existing.scalars().first():
        raise HTTPException(
            status_code=400,
            detail="Employee code already exists for this tenant."
        )

    # =========================
    # CHECK: finger_id unique per tenant
    # =========================
    existing_finger = await db.execute(
        select(User).where(
            User.tenant_id == tenant_id,
            User.finger_id == finger_id
        )
    )
    if existing_finger.scalars().first():
        raise HTTPException(
            status_code=400,
            detail="Finger ID already assigned for this tenant."
        )

    # =========================
    # CREATE USER
    # =========================
    user = User(
        tenant_id=tenant_id,
        finger_id=finger_id,
        name=name,
        employee_code=employee_code
    )

    db.add(user)
    await db.commit()
    await db.refresh(user)

    return user


# =========================
# DELETE USER
# =========================

async def delete_user(
    tenant_id: int,
    finger_id: int,
    db: AsyncSession
):
    result = await db.execute(
        select(User).where(
            User.tenant_id == tenant_id,
            User.finger_id == finger_id
        )
    )
    user = result.scalars().first()

    if not user:
        raise HTTPException(
            status_code=404,
            detail="User not found."
        )

    await db.delete(user)
    await db.commit()

    return {"message": "User deleted successfully"}