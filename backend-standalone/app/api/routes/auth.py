from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import text, or_
from app.db.session import get_db
from app.models.domain import User, RefreshToken, Tenant
from app.api.dependencies import get_current_user
from pydantic import BaseModel, EmailStr, field_validator
from app.core.security import (
    verify_password,
    hash_password,
    create_access_token,
    create_refresh_token,
    decode_token
)
from datetime import datetime, timedelta
import secrets
import re
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


# =========================
# SCHEMAS
# =========================

class LoginRequest(BaseModel):
    """JSON login - accepts employee_code OR email"""
    identifier: str
    password: str
    tenant_id: int | None = None


class TenantLoginRequest(BaseModel):
    """Tenant manager login using API key"""
    api_key: str


class RefreshRequest(BaseModel):
    refresh_token: str


class SetPasswordRequest(BaseModel):
    user_id: int
    new_password: str
    
    @field_validator('new_password')
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError('Password must be at least 8 characters')
        if not re.search(r'[A-Z]', v):
            raise ValueError('Password must contain at least one uppercase letter')
        if not re.search(r'[a-z]', v):
            raise ValueError('Password must contain at least one lowercase letter')
        if not re.search(r'[0-9]', v):
            raise ValueError('Password must contain at least one number')
        return v


class ChangePasswordRequest(BaseModel):
    """Change own password"""
    old_password: str
    new_password: str
    
    @field_validator('new_password')
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError('Password must be at least 8 characters')
        if not re.search(r'[A-Z]', v):
            raise ValueError('Password must contain at least one uppercase letter')
        if not re.search(r'[a-z]', v):
            raise ValueError('Password must contain at least one lowercase letter')
        if not re.search(r'[0-9]', v):
            raise ValueError('Password must contain at least one number')
        return v


class CreateSuperAdminRequest(BaseModel):
    name: str
    email: EmailStr
    password: str
    
    @field_validator('password')
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError('Password must be at least 8 characters')
        if not re.search(r'[A-Z]', v):
            raise ValueError('Password must contain at least one uppercase letter')
        if not re.search(r'[a-z]', v):
            raise ValueError('Password must contain at least one lowercase letter')
        if not re.search(r'[0-9]', v):
            raise ValueError('Password must contain at least one number')
        return v


# =========================
# HELPER FUNCTIONS
# =========================

def _create_auth_response(user: User, db_session: AsyncSession = None) -> dict:
    """Helper to create consistent auth response"""
    payload = {
        "user_id": user.id,
        "role": user.role,
        "tenant_id": user.tenant_id,
        "dept_id": user.dept_id
    }
    
    access_token = create_access_token(payload)
    refresh_token, jti = create_refresh_token(payload)
    
    if db_session:
        expires_at = datetime.utcnow() + timedelta(days=7)
        token_record = RefreshToken(
            user_id=user.id,
            token_jti=jti,
            expires_at=expires_at
        )
        db_session.add(token_record)
    
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer"
    }


# =========================
# UNIFIED OAUTH2 LOGIN
# =========================

@router.post("/login")
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db)
):
    """Unified login for ALL users (Super Admin, Org Admin, Employee, Tenant)"""
    
    try:
        # 1. Try Users table (Super Admin, Org Admin, Employee)
        query = select(User).where(
            or_(
                User.employee_code == form_data.username,
                User.email == form_data.username
            )
        )
        result = await db.execute(query)
        user = result.scalars().first()
        
        if user and user.password_hash:
            if not verify_password(form_data.password, user.password_hash):
                raise HTTPException(401, "Invalid credentials")
            
            if not user.is_active:
                raise HTTPException(403, "Account is deactivated")
            
            logger.info(f"User login: {user.email or user.employee_code} ({user.role})")
            return _create_auth_response(user, db)
        
        # 2. Try API Key (Tenant Manager)
        result = await db.execute(
            select(Tenant).where(Tenant.api_key == form_data.password)
        )
        tenant = result.scalars().first()
        
        if tenant:
            payload = {
                "user_id": tenant.id,
                "role": "tenant_admin",
                "tenant_id": tenant.id
            }
            
            access_token = create_access_token(payload)
            refresh_token, jti = create_refresh_token(payload)
            
            logger.info(f"Tenant login via API key: {tenant.name}")
            
            return {
                "access_token": access_token,
                "refresh_token": refresh_token,
                "token_type": "bearer"
            }
        
        logger.warning(f"Failed login: {form_data.username}")
        raise HTTPException(401, "Invalid credentials")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Login error: {str(e)}")
        await db.rollback()
        raise HTTPException(500, "Internal server error")


# =========================
# TENANT LOGIN (API Key)
# =========================

@router.post("/tenant-login")
async def tenant_login(
    data: TenantLoginRequest,
    db: AsyncSession = Depends(get_db)
):
    """Dedicated login for tenant managers using API key"""
    
    try:
        result = await db.execute(
            select(Tenant).where(Tenant.api_key == data.api_key)
        )
        tenant = result.scalars().first()
        
        if not tenant:
            raise HTTPException(401, "Invalid API key")
        
        payload = {
            "user_id": tenant.id,
            "role": "tenant_admin",
            "tenant_id": tenant.id
        }
        
        access_token = create_access_token(payload)
        refresh_token, jti = create_refresh_token(payload)
        
        logger.info(f"Tenant login: {tenant.name}")
        
        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "tenant": {"id": tenant.id, "name": tenant.name}
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Tenant login error: {str(e)}")
        raise HTTPException(500, "Internal server error")


# =========================
# REFRESH TOKEN
# =========================

@router.post("/refresh")
async def refresh_token(
    data: RefreshRequest,
    db: AsyncSession = Depends(get_db)
):
    """Refresh access token"""
    
    try:
        payload = decode_token(data.refresh_token)
        if not payload or payload.get("type") != "refresh":
            raise HTTPException(401, "Invalid refresh token")
        
        jti = payload.get("jti")
        user_id = payload.get("user_id")
        
        result = await db.execute(
            select(RefreshToken).where(
                RefreshToken.token_jti == jti,
                RefreshToken.user_id == user_id
            )
        )
        token_record = result.scalars().first()
        
        if not token_record or token_record.is_revoked:
            raise HTTPException(401, "Token revoked or not found")
        
        if token_record.expires_at < datetime.utcnow():
            raise HTTPException(401, "Token expired")
        
        token_record.is_revoked = True
        
        new_payload = {
            "user_id": user_id,
            "role": payload.get("role"),
            "tenant_id": payload.get("tenant_id"),
            "dept_id": payload.get("dept_id")
        }
        
        new_access = create_access_token(new_payload)
        new_refresh, new_jti = create_refresh_token(new_payload)
        
        expires_at = datetime.utcnow() + timedelta(days=7)
        new_token = RefreshToken(
            user_id=user_id,
            token_jti=new_jti,
            expires_at=expires_at
        )
        db.add(new_token)
        await db.commit()
        
        return {
            "access_token": new_access,
            "refresh_token": new_refresh,
            "token_type": "bearer"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Refresh error: {str(e)}")
        await db.rollback()
        raise HTTPException(500, "Internal server error")


# =========================
# LOGOUT
# =========================

@router.post("/logout")
async def logout(
    refresh_token: str,
    db: AsyncSession = Depends(get_db)
):
    """Revoke refresh token"""
    
    try:
        payload = decode_token(refresh_token)
        if payload and payload.get("jti"):
            await db.execute(
                text("UPDATE refresh_tokens SET is_revoked = TRUE WHERE token_jti = :jti"),
                {"jti": payload["jti"]}
            )
            await db.commit()
        
        return {"message": "Logged out"}
        
    except Exception as e:
        logger.error(f"Logout error: {str(e)}")
        await db.rollback()
        raise HTTPException(500, "Internal server error")


# =========================
# CREATE SUPER ADMIN
# =========================

@router.post("/setup/super-admin")
async def create_super_admin(
    data: CreateSuperAdminRequest,
    db: AsyncSession = Depends(get_db)
):
    """One-time setup - creates first super admin"""
    
    try:
        # Check if super admin already exists
        result = await db.execute(
            select(User).where(User.role == "super_admin")
        )
        if result.scalars().first():
            raise HTTPException(400, "Super admin already exists")
        
        # Check email
        email_check = await db.execute(
            select(User).where(User.email == data.email)
        )
        if email_check.scalars().first():
            raise HTTPException(400, "Email already in use")
        
        # Create super admin
        user = User(
            tenant_id=None,
            email=data.email,
            name=data.name,
            employee_code=None,
            finger_id=None,
            password_hash=hash_password(data.password),
            role="super_admin",
            is_active=True
        )
        
        db.add(user)
        await db.commit()
        await db.refresh(user)
        
        logger.info(f"Super admin created: {data.email}")
        
        return {
            "message": "Super admin created",
            "user_id": user.id,
            "email": user.email
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Super admin error: {str(e)}")
        await db.rollback()
        raise HTTPException(500, "Internal server error")


# =========================
# CHANGE PASSWORD
# =========================

@router.post("/change-password")
async def change_password(
    data: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """User changes own password"""
    
    try:
        if not current_user.password_hash:
            raise HTTPException(400, "No password set")
        
        if not verify_password(data.old_password, current_user.password_hash):
            raise HTTPException(401, "Incorrect current password")
        
        current_user.password_hash = hash_password(data.new_password)
        await db.commit()
        
        logger.info(f"Password changed for user: {current_user.id}")
        return {"message": "Password changed"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Change password error: {str(e)}")
        await db.rollback()
        raise HTTPException(500, "Internal server error")


# =========================
# SET PASSWORD (Admin only)
# =========================

@router.post("/set-password")
async def set_password(
    data: SetPasswordRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Admin sets password for a user"""
    
    if current_user.role not in ["super_admin", "org_admin"]:
        raise HTTPException(403, "Admin access required")
    
    try:
        result = await db.execute(select(User).where(User.id == data.user_id))
        user = result.scalars().first()
        
        if not user:
            raise HTTPException(404, "User not found")
        
        user.password_hash = hash_password(data.new_password)
        await db.commit()
        
        return {"message": "Password set successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Set password error: {str(e)}")
        await db.rollback()
        raise HTTPException(500, "Internal server error")