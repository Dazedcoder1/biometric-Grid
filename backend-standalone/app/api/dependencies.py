from fastapi import Header, HTTPException, Depends
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from app.db.session import get_db
from app.models.domain import Device, User, Tenant
from app.core.security import decode_token
import datetime
import logging

# Configure logger for authentication tracking
logger = logging.getLogger(__name__)

# Security Schemes
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=True)

# ✅ ADD THIS - Optional version (doesn't raise error automatically)
oauth2_scheme_optional = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)

# =================================================================
# 1. CORE IDENTITY DEPENDENCIES
# =================================================================

async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db)
) -> User:
    """Standard JWT User retrieval"""
    payload = decode_token(token)
    if not payload or payload.get("type") != "access":
        raise HTTPException(401, "Invalid or expired token")
    
    user_id = payload.get("user_id")
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalars().first()
    
    if not user or not user.is_active:
        raise HTTPException(401, "User not found or inactive")
    
    return user

async def get_current_active_identity(
    token: str = Depends(oauth2_scheme),
    x_api_key: str = Header(None, alias="X-API-Key"),
    db: AsyncSession = Depends(get_db)
):
    """
    POLYMORPHIC IDENTITY:
    Allows shared routes (like notifications) to be accessed by either 
    an Employee (via JWT) or a Tenant Admin (via API Key).
    """
    # 1. Check for JWT (Frontend UI Users)
    if token:
        try:
            payload = decode_token(token)
            if payload and payload.get("type") == "access":
                user_id = payload.get("user_id")
                result = await db.execute(select(User).where(User.id == user_id))
                user = result.scalars().first()
                if user and user.is_active:
                    return user
        except Exception as e:
            logger.debug(f"JWT check bypassed/failed: {e}")

    # 2. Check for API Key (Tenant Managers / Direct API hits)
    if x_api_key:
        result = await db.execute(select(Tenant).where(Tenant.api_key == x_api_key))
        tenant = result.scalars().first()
        if tenant:
            return tenant

    # 3. Fallback
    raise HTTPException(
        status_code=401, 
        detail="Valid authentication (JWT or API Key) required for this resource"
    )

# =================================================================
# 2. ROLE-BASED ACCESS CONTROL (RBAC)
# =================================================================

async def get_current_tenant(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db)
) -> Tenant:
    """
    Get current tenant from JWT token.
    Used for tenant endpoints that require JWT auth.
    """
    payload = decode_token(token)
    
    if not payload:
        raise HTTPException(401, "Invalid or expired token")
    
    if payload.get("type") != "access":
        raise HTTPException(401, "Invalid token type")
    
    # Verify this is a tenant token
    if payload.get("role") != "tenant_admin":
        raise HTTPException(403, "Tenant access required")
    
    tenant_id = payload.get("tenant_id")
    
    if not tenant_id:
        raise HTTPException(401, "Invalid token payload")
    
    # Fetch tenant from database
    result = await db.execute(select(Tenant).where(Tenant.id == tenant_id))
    tenant = result.scalars().first()
    
    if not tenant:
        raise HTTPException(401, "Tenant not found")
    
    return tenant

def require_role(*allowed_roles: str):
    """Generic role requirement decorator"""
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

# =================================================================
# 3. TENANT & ORGANIZATION VALIDATION
# =================================================================

async def verify_tenant_api_key(
    x_api_key: str = Header(..., alias="X-API-Key"),
    db: AsyncSession = Depends(get_db)
) -> Tenant:
    """Strictly validates via Header API Key"""
    result = await db.execute(select(Tenant).where(Tenant.api_key == x_api_key))
    tenant = result.scalars().first()
    if not tenant:
        raise HTTPException(401, "Invalid API key")
    return tenant

async def verify_tenant_jwt(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> Tenant:
    """Validates that a logged-in user is a tenant admin and returns the tenant object"""
    if current_user.role != "tenant_admin":
        raise HTTPException(403, "Tenant access required")
    result = await db.execute(select(Tenant).where(Tenant.id == current_user.tenant_id))
    tenant = result.scalars().first()
    if not tenant:
        raise HTTPException(401, "Tenant not found")
    return tenant

# =================================================================
# 4. HARDWARE / DEVICE VALIDATION
# =================================================================

async def verify_device(
    x_device_id: str = Header(..., alias="x-device-id"),
    x_secret_key: str = Header(..., alias="x-secret-key"),
    db: AsyncSession = Depends(get_db)
):
    """Biometric Attendance System: Validates physical hardware devices"""
    result = await db.execute(
        select(Device).where(Device.device_id == x_device_id, Device.secret_key == x_secret_key)
    )
    device = result.scalars().first()
    if not device:
        raise HTTPException(401, "Invalid Device Credentials")
    
    # Update device heartbeat
    device.last_seen = datetime.datetime.utcnow()
    device.status = "online"
    await db.commit()
    return device

# =================================================================
# 5. COMPATIBILITY WRAPPERS
# =================================================================

async def get_admin_data(current_user: User = Depends(require_super_admin)):
    """Legacy compatibility for older frontend structures"""
    class CompatibleAdmin:
        def __init__(self, user):
            self.id = user.id
            self.tenant_id = user.tenant_id
            self.username = user.email or user.name
            self.role = "super_admin"
    return CompatibleAdmin(current_user)