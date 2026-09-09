from fastapi import Header, HTTPException, Depends
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
import datetime
import logging

from app.db.session import get_db
from app.models.domain import Device, User, Tenant
from app.core.security import decode_token

logger = logging.getLogger(__name__)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db)
) -> User:
    payload = decode_token(token)
    if not payload or payload.get("type") != "access":
        raise HTTPException(401, "Invalid or expired token")

    user_id = payload.get("user_id")
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalars().first()

    if not user or not user.is_active:
        raise HTTPException(401, "User not found or inactive")

    return user


def require_role(*allowed_roles: str):
    async def checker(current_user: User = Depends(get_current_user)):
        if current_user.role not in allowed_roles:
            raise HTTPException(403, f"Requires one of: {allowed_roles}")
        return current_user
    return checker


async def require_super_admin(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != "super_admin":
        raise HTTPException(403, "Only super admin can access this")
    return current_user


async def require_org_admin(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != "org_admin":
        raise HTTPException(403, "Only org admin can access this")
    return current_user


async def require_employee(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != "employee":
        raise HTTPException(403, "Only employees can access this")
    return current_user


async def verify_tenant_api_key(
    x_api_key: str = Header(..., alias="X-API-Key"),
    db: AsyncSession = Depends(get_db)
) -> Tenant:
    result = await db.execute(select(Tenant).where(Tenant.api_key == x_api_key))
    tenant = result.scalars().first()
    if not tenant:
        raise HTTPException(401, "Invalid API key")
    return tenant


async def verify_device(
    x_device_id: str = Header(..., alias="x-device-id"),
    x_secret_key: str = Header(..., alias="x-secret-key"),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(Device).where(
            Device.device_id == x_device_id,
            Device.secret_key == x_secret_key
        )
    )
    device = result.scalars().first()
    if not device:
        raise HTTPException(401, "Invalid Device Credentials")
    device.last_seen = datetime.datetime.utcnow()
    device.status = "online"
    await db.commit()
    return device