from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from app.models.domain import User

# REMOVED: from app.services.user_service import enroll_user, delete_user (This was the circular import)

async def enroll_user(tenant_id: int, finger_id: int, name: str, db: AsyncSession):
    result = await db.execute(select(User).where(User.tenant_id == tenant_id, User.finger_id == finger_id))
    if result.scalars().first():
        raise HTTPException(status_code=400, detail="Finger ID already exists for this tenant.")
        
    user = User(tenant_id=tenant_id, finger_id=finger_id, name=name)
    db.add(user)
    await db.commit()
    return user

async def delete_user(tenant_id: int, finger_id: int, db: AsyncSession):
    result = await db.execute(select(User).where(User.tenant_id == tenant_id, User.finger_id == finger_id))
    user = result.scalars().first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
        
    await db.delete(user)
    await db.commit()