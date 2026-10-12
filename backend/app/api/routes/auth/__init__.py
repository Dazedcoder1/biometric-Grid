from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import text, or_
from app.db.session import get_db
from app.models.domain import User, RefreshToken, Tenant
from app.api.dependencies import get_current_user
from app.core import activity
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


class LoginRequest(BaseModel):
    identifier: str
    password: str
    tenant_id: int | None = None


class TenantLoginRequest(BaseModel):
    api_key: str


class RefreshRequest(BaseModel):
    refresh_token: str


class ChangePasswordRequest(BaseModel):
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


def _create_auth_response(user: User, db_session: AsyncSession = None) -> dict:
    payload = {
        "user_id": user.id,
        "role": user.role,
        "tenant_id": user.tenant_id,
        "dept_id": user.dept_id,
        # Lets the client go straight to the change-password screen. A hint
        # only: the server enforces it from the database row on every request
        # (dependencies.get_current_user), not from this claim.
        "must_change_password": bool(getattr(user, "must_change_password", False)),
        # Which screens to draw. The server never trusts this claim — payroll
        # routes check permissions resolved from the database on every call.
        "is_hr": bool(getattr(user, "is_hr", False)),
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


async def _failed_sign_in(db: AsyncSession, request: Request, *, reason: str,
                          user: User | None = None) -> None:
    """
    Record a refused sign-in and commit it on its own — the route is about to
    raise, and nothing else in this request will commit.

    The typed identifier is recorded only when it matched a real account.
    When it matched nothing it may well be a password typed into the wrong
    box, and the audit log must never hold one.
    """
    await activity.log(
        db, request, action="auth.sign_in_failed", result="denied", reason=reason,
        tenant_id=user.tenant_id if user else None,
        target_type="user" if user else None,
        target_id=user.id if user else None,
        details={"account": user.email or user.employee_code} if user else None,
        anonymous="unknown",
    )
    await db.commit()


@router.post("/login")
async def login(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db)
):
    try:
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
                await _failed_sign_in(db, request, reason="wrong password", user=user)
                raise HTTPException(401, "Invalid credentials")
            if not user.is_active:
                await _failed_sign_in(db, request, reason="account deactivated", user=user)
                raise HTTPException(403, "Account is deactivated")

            logger.info(f"User login: {user.email or user.employee_code} ({user.role})")
            response = _create_auth_response(user, db)
            await activity.log(
                db, request, action="auth.signed_in", tenant_id=user.tenant_id,
                target_type="user", target_id=user.id, actor=user,
                details={"method": "password"},
            )
            await db.commit()
            return response

        # Try API Key (Tenant Manager)
        result = await db.execute(
            select(Tenant).where(Tenant.api_key == form_data.password)
        )
        tenant = result.scalars().first()

        if tenant:
            payload = {
                "user_id": tenant.id,
                "role": "tenant_admin",
                "tenant_id": tenant.id,
                "dept_id": None
            }
            access_token = create_access_token(payload)
            refresh_token, jti = create_refresh_token(payload)
            logger.info(f"Tenant login via API key: {tenant.name}")
            await activity.log(
                db, request, action="auth.signed_in", tenant_id=tenant.id,
                details={"method": "api_key"}, anonymous="api_key",
            )
            await db.commit()
            return {
                "access_token": access_token,
                "refresh_token": refresh_token,
                "token_type": "bearer"
            }

        logger.warning(f"Failed login: {form_data.username}")
        await _failed_sign_in(db, request, reason="unknown account")
        raise HTTPException(401, "Invalid credentials")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Login error: {str(e)}")
        await db.rollback()
        raise HTTPException(500, "Internal server error")


class TenantLoginRequest(BaseModel):
    api_key: str


@router.post("/tenant-login")
async def tenant_login(
    data: TenantLoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    Tenant-admin sign-in by API key.

    The React client has always called this path; it simply didn't exist on the
    server, so tenant login failed. The generic /login route can also accept an
    API key as the password, but the client expects the tenant object back —
    which that route doesn't return.
    """
    result = await db.execute(select(Tenant).where(Tenant.api_key == data.api_key))
    tenant = result.scalars().first()

    if not tenant:
        logger.warning("Failed tenant login attempt")
        await _failed_sign_in(db, request, reason="unknown API key")
        raise HTTPException(401, "Invalid API Key")

    payload = {
        "user_id": tenant.id,
        "role": "tenant_admin",
        "tenant_id": tenant.id,
        "dept_id": None,
    }
    access_token = create_access_token(payload)
    refresh, _jti = create_refresh_token(payload)

    logger.info(f"Tenant login: {tenant.name}")
    await activity.log(
        db, request, action="auth.signed_in", tenant_id=tenant.id,
        details={"method": "api_key"}, anonymous="api_key",
    )
    await db.commit()
    return {
        "access_token": access_token,
        "refresh_token": refresh,
        "token_type": "bearer",
        "tenant": {"id": tenant.id, "name": tenant.name},
    }


@router.post("/refresh")
async def refresh_token(
    data: RefreshRequest,
    db: AsyncSession = Depends(get_db)
):
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

        # HR access can be granted or withdrawn between sign-ins; read it fresh
        # so a refreshed session shows the right screens.
        holder = (await db.execute(select(User).where(User.id == user_id))).scalars().first()
        new_payload = {
            "user_id": user_id,
            "role": payload.get("role"),
            "tenant_id": payload.get("tenant_id"),
            "dept_id": payload.get("dept_id"),
            "must_change_password": bool(payload.get("must_change_password", False)),
            "is_hr": bool(getattr(holder, "is_hr", False)),
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


@router.post("/logout")
async def logout(
    refresh_token: str,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    try:
        payload = decode_token(refresh_token)
        if payload and payload.get("jti"):
            await db.execute(
                text("UPDATE refresh_tokens SET is_revoked = TRUE WHERE token_jti = :jti"),
                {"jti": payload["jti"]}
            )
            # The refresh token names the person; an API-key session's names
            # an organisation instead, and resolves to nobody here.
            person = (
                await db.execute(select(User).where(User.id == payload.get("user_id")))
            ).scalars().first()
            if person and person.tenant_id == payload.get("tenant_id"):
                await activity.log(
                    db, request, action="auth.signed_out", tenant_id=person.tenant_id,
                    target_type="user", target_id=person.id, actor=person,
                )
            await db.commit()
        return {"message": "Logged out"}
    except Exception as e:
        logger.error(f"Logout error: {str(e)}")
        await db.rollback()
        raise HTTPException(500, "Internal server error")


@router.post("/setup/super-admin")
async def create_super_admin(
    data: CreateSuperAdminRequest,
    db: AsyncSession = Depends(get_db)
):
    try:
        result = await db.execute(select(User).where(User.role == "super_admin"))
        if result.scalars().first():
            raise HTTPException(400, "Super admin already exists")

        email_check = await db.execute(select(User).where(User.email == data.email))
        if email_check.scalars().first():
            raise HTTPException(400, "Email already in use")

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
        return {"message": "Super admin created", "user_id": user.id, "email": user.email}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Super admin error: {str(e)}")
        await db.rollback()
        raise HTTPException(500, "Internal server error")


@router.post("/change-password")
async def change_password(
    data: ChangePasswordRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Change your own password. Also how a temporary password from an admin gets
    replaced — this route stays open while must_change_password is set.

    Every other session for the account is signed out, and fresh tokens come
    back in the response: the old ones carry must_change_password=true, and a
    password change is exactly when a session opened by someone else should
    end.
    """
    try:
        if not current_user.password_hash:
            raise HTTPException(400, "No password set")
        if not verify_password(data.old_password, current_user.password_hash):
            # Someone at an unlocked laptop guessing the current password is
            # exactly what this record is for.
            await activity.log(
                db, request, action="auth.password_change_failed", result="denied",
                reason="current password wrong", tenant_id=current_user.tenant_id,
                target_type="user", target_id=current_user.id, actor=current_user,
            )
            await db.commit()
            raise HTTPException(401, "Incorrect current password")
        if data.old_password == data.new_password:
            raise HTTPException(400, "The new password must be different from the current one.")

        was_temporary = bool(current_user.must_change_password)
        current_user.password_hash = hash_password(data.new_password)
        current_user.must_change_password = False

        await db.execute(
            text("UPDATE refresh_tokens SET is_revoked = TRUE "
                 "WHERE user_id = :u AND is_revoked = FALSE"),
            {"u": current_user.id},
        )
        tokens = _create_auth_response(current_user, db)
        await activity.log(
            db, request, action="auth.password_changed", tenant_id=current_user.tenant_id,
            target_type="user", target_id=current_user.id, actor=current_user,
            details={"replaced_temporary": was_temporary},
        )
        await db.commit()
        return {"message": "Password changed", **tokens}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Change password error: {str(e)}")
        await db.rollback()
        raise HTTPException(500, "Internal server error")


# /set-password used to live here. It let any Org Admin set ANY user's password
# in ANY organisation — a Super Admin's included — with no scope check at all.
# Removed; the replacement is POST /api/accounts/{user_id}/reset-password
# (routes/common/accounts.py), scoped to the people the caller administers,
# audited, and forcing the person to choose their own password at next sign-in.
