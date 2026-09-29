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
    x_api_key: str | None = Header(None, alias="X-API-Key"),
    x_acting_tenant_id: int | None = Header(None, alias="X-Acting-Tenant-Id"),
    authorization: str | None = Header(None),
    db: AsyncSession = Depends(get_db)
) -> Tenant:
    """
    Resolve the tenant for a Tenant Admin route, by API key OR by bearer token.

    The API key is the primary credential and is unchanged. The bearer fallback
    exists because a tenant_admin or super_admin who signed in with email and
    password holds a JWT and no API key, and previously could not reach any of
    these routes at all — the header was declared required, so FastAPI rejected
    the request as 422 Unprocessable Entity before this function even ran. A
    422 reads as "your request body is malformed", which sent everyone looking
    at the wrong thing; the real meaning was "no credential supplied".

    X-Acting-Tenant-Id exists for Super Admins, who have `tenant_id = NULL` by
    design — they belong to the platform, not to an organisation. Every route
    behind this dependency is tenant-scoped, so without a tenant to name there
    is nothing for them to administer, and the whole Tenant Admin UI answered
    them with "This admin is not attached to an organisation." The header says
    which organisation they are acting within.

    It is honoured ONLY for super_admin. A tenant_admin who sends it is
    refused rather than ignored: silently using their own tenant would let a
    client believe it was acting on another organisation while quietly writing
    to its own, which is the more dangerous failure. Their scope is fixed by
    their account and is not theirs to choose.

    Both paths end at the same Tenant, so route handlers are unaffected.
    """
    if x_api_key:
        result = await db.execute(select(Tenant).where(Tenant.api_key == x_api_key))
        tenant = result.scalars().first()
        if not tenant:
            raise HTTPException(401, "Invalid API key")
        return tenant

    # No API key — try a bearer token belonging to an admin of some tenant.
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()
        payload = decode_token(token)
        if not payload or payload.get("type") != "access":
            raise HTTPException(401, "Invalid or expired token")

        user = (
            await db.execute(select(User).where(User.id == payload.get("user_id")))
        ).scalars().first()
        if not user or not user.is_active:
            raise HTTPException(401, "User not found or inactive")

        if user.role not in ("tenant_admin", "super_admin"):
            raise HTTPException(
                403,
                "This area is for Tenant Admins. Sign in with the tenant API key, "
                f"or as a tenant admin — you are signed in as '{user.role}'.",
            )

        if user.role == "super_admin":
            if x_acting_tenant_id is None:
                # 409, not 403: nothing is forbidden here, the request is simply
                # missing the one thing it needs. The client turns this into the
                # organisation chooser rather than an error page.
                raise HTTPException(
                    409,
                    "Choose an organisation first. A Super Admin belongs to the "
                    "platform rather than to one organisation, so this request "
                    "needs an X-Acting-Tenant-Id header naming which to act on.",
                )
            tenant = (
                await db.execute(select(Tenant).where(Tenant.id == x_acting_tenant_id))
            ).scalars().first()
            if not tenant:
                raise HTTPException(404, "That organisation does not exist.")
            return tenant

        # tenant_admin from here down.
        if x_acting_tenant_id is not None and x_acting_tenant_id != user.tenant_id:
            raise HTTPException(
                403,
                "You can only administer your own organisation.",
            )
        if not user.tenant_id:
            raise HTTPException(403, "This admin is not attached to an organisation.")

        tenant = (
            await db.execute(select(Tenant).where(Tenant.id == user.tenant_id))
        ).scalars().first()
        if not tenant:
            raise HTTPException(401, "The organisation on this account no longer exists.")
        return tenant

    raise HTTPException(
        401,
        "No credentials supplied. Tenant Admin routes need the X-API-Key header, "
        "or a bearer token for a tenant admin.",
    )


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