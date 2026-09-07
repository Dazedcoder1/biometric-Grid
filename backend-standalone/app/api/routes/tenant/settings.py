from fastapi import APIRouter, Depends, HTTPException, Header, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from sqlalchemy.future import select
from pydantic import BaseModel, field_validator
from typing import Optional
import re
import logging
from datetime import datetime

from app.db.session import get_db
from app.api.dependencies import verify_tenant_api_key, oauth2_scheme_optional
from app.models.domain import Tenant
from app.core.security import decode_token

router = APIRouter()
logger = logging.getLogger(__name__)


# =========================
# SCHEMAS
# =========================

class SettingsUpdate(BaseModel):
    office_start_time: str = "09:00:00"
    office_end_time: str = "18:00:00"
    late_threshold_minutes: int = 15
    working_days: str = "1,2,3,4,5"
    min_working_hours: float = 9.0  # ✅ NEW - Minimum working hours per day

    @field_validator('office_start_time', 'office_end_time')
    @classmethod
    def validate_time_format(cls, v: str) -> str:
        """Validate time format HH:MM:SS"""
        pattern = r'^([0-1][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9]$'
        if not re.match(pattern, v):
            raise ValueError(f'Invalid time format: {v}. Use HH:MM:SS')
        return v

    @field_validator('late_threshold_minutes')
    @classmethod
    def validate_threshold(cls, v: int) -> int:
        if v < 0 or v > 120:
            raise ValueError('Late threshold must be between 0 and 120 minutes')
        return v

    @field_validator('min_working_hours')
    @classmethod
    def validate_min_hours(cls, v: float) -> float:
        if v < 0.5 or v > 24:
            raise ValueError('Minimum working hours must be between 0.5 and 24 hours')
        return v

    @field_validator('working_days')
    @classmethod
    def validate_working_days(cls, v: str) -> str:
        """Validate working days format: comma-separated numbers 1-7"""
        if not v:
            return "1,2,3,4,5"
        days = v.split(',')
        for day in days:
            if not day.strip().isdigit() or int(day) < 1 or int(day) > 7:
                raise ValueError(f'Invalid working day: {day}. Must be 1-7')
        return v


class ChangeApiKeyRequest(BaseModel):
    """Change API key request - password-like validation"""
    api_key: str
    
    @field_validator('api_key')
    @classmethod
    def validate_api_key(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError('API key must be at least 8 characters')
        if not re.search(r'[A-Z]', v):
            raise ValueError('API key must contain at least one uppercase letter')
        if not re.search(r'[a-z]', v):
            raise ValueError('API key must contain at least one lowercase letter')
        if not re.search(r'[0-9]', v):
            raise ValueError('API key must contain at least one number')
        return v


class SettingsResponse(BaseModel):
    office_start_time: str
    office_end_time: str
    late_threshold_minutes: int
    working_days: str
    min_working_hours: float
    updated_at: Optional[datetime] = None


# =========================
# CACHE FOR SETTINGS (In-memory with TTL)
# =========================

_settings_cache = {}
_cache_ttl = 300  # 5 minutes cache


def get_cached_settings(tenant_id: int) -> Optional[dict]:
    """Get settings from cache if not expired"""
    cache_key = f"tenant_settings_{tenant_id}"
    if cache_key in _settings_cache:
        cached_data, timestamp = _settings_cache[cache_key]
        if (datetime.now() - timestamp).seconds < _cache_ttl:
            return cached_data
        # Cache expired, remove it
        del _settings_cache[cache_key]
    return None


def set_cached_settings(tenant_id: int, settings: dict):
    """Store settings in cache"""
    cache_key = f"tenant_settings_{tenant_id}"
    _settings_cache[cache_key] = (settings.copy(), datetime.now())


def invalidate_settings_cache(tenant_id: int):
    """Invalidate cache for a tenant"""
    cache_key = f"tenant_settings_{tenant_id}"
    if cache_key in _settings_cache:
        del _settings_cache[cache_key]
        logger.info(f"Cache invalidated for tenant {tenant_id}")


# =========================
# CORE SETTINGS FUNCTIONS
# =========================

async def get_tenant_settings_from_db(
    tenant_id: int, 
    db: AsyncSession,
    force_refresh: bool = False
) -> dict:
    """
    Get tenant settings from database with caching
    """
    # Check cache first
    if not force_refresh:
        cached = get_cached_settings(tenant_id)
        if cached:
            return cached
    
    # Fetch from database
    result = await db.execute(text("""
        SELECT 
            office_start_time, 
            office_end_time, 
            late_threshold_minutes, 
            working_days,
            min_working_hours,
            updated_at
        FROM settings
        WHERE tenant_id = :tenant_id
        LIMIT 1
    """), {"tenant_id": tenant_id})
    
    settings = result.mappings().first()
    
    if not settings:
        # Return defaults if no settings found
        settings = {
            "office_start_time": "09:00:00",
            "office_end_time": "18:00:00",
            "late_threshold_minutes": 15,
            "working_days": "1,2,3,4,5",
            "min_working_hours": 9.0,
            "updated_at": None
        }
    else:
        # Convert to dict
        settings = dict(settings)
        # Ensure min_working_hours exists (for backward compatibility)
        if settings.get("min_working_hours") is None:
            settings["min_working_hours"] = 9.0
    
    # Parse times for convenience
    settings["office_start"] = datetime.strptime(
        settings["office_start_time"], "%H:%M:%S"
    ).time()
    settings["office_end"] = datetime.strptime(
        settings["office_end_time"], "%H:%M:%S"
    ).time()
    
    # Store in cache
    set_cached_settings(tenant_id, settings)
    
    return settings


# =========================
# EXISTING ENDPOINTS (UPDATED)
# =========================

@router.get("/settings", response_model=SettingsResponse)
async def get_settings(
    tenant: Tenant = Depends(verify_tenant_api_key),
    db: AsyncSession = Depends(get_db)
):
    """Tenant Manager: Get organization settings"""
    
    settings = await get_tenant_settings_from_db(tenant.id, db)
    
    return SettingsResponse(
        office_start_time=settings["office_start_time"],
        office_end_time=settings["office_end_time"],
        late_threshold_minutes=settings["late_threshold_minutes"],
        working_days=settings["working_days"],
        min_working_hours=settings["min_working_hours"],
        updated_at=settings.get("updated_at")
    )


@router.put("/settings")
async def update_settings(
    data: SettingsUpdate,
    tenant: Tenant = Depends(verify_tenant_api_key),
    db: AsyncSession = Depends(get_db)
):
    """Tenant Manager: Update organization settings"""
    
    try:
        # Update settings in database
        await db.execute(text("""
            INSERT INTO settings (
                tenant_id, 
                office_start_time, 
                office_end_time, 
                late_threshold_minutes, 
                working_days,
                min_working_hours,
                updated_at
            )
            VALUES (
                :tenant_id, 
                :office_start_time, 
                :office_end_time, 
                :late_threshold_minutes, 
                :working_days,
                :min_working_hours,
                NOW()
            )
            ON CONFLICT (tenant_id) DO UPDATE SET
                office_start_time = EXCLUDED.office_start_time,
                office_end_time = EXCLUDED.office_end_time,
                late_threshold_minutes = EXCLUDED.late_threshold_minutes,
                working_days = EXCLUDED.working_days,
                min_working_hours = EXCLUDED.min_working_hours,
                updated_at = EXCLUDED.updated_at
        """), {
            "tenant_id": tenant.id,
            "office_start_time": data.office_start_time,
            "office_end_time": data.office_end_time,
            "late_threshold_minutes": data.late_threshold_minutes,
            "working_days": data.working_days,
            "min_working_hours": data.min_working_hours
        })
        
        await db.commit()
        
        # Invalidate cache
        invalidate_settings_cache(tenant.id)
        
        logger.info(f"Settings updated for tenant {tenant.id}: min_working_hours={data.min_working_hours}")
        
        return {
            "message": "Settings updated successfully",
            "settings": {
                "office_start_time": data.office_start_time,
                "office_end_time": data.office_end_time,
                "late_threshold_minutes": data.late_threshold_minutes,
                "working_days": data.working_days,
                "min_working_hours": data.min_working_hours
            }
        }
        
    except Exception as e:
        logger.error(f"Failed to update settings for tenant {tenant.id}: {e}")
        await db.rollback()
        raise HTTPException(500, f"Failed to update settings: {str(e)}")


@router.get("/profile")
async def get_tenant_profile(
    tenant: Tenant = Depends(verify_tenant_api_key),
    db: AsyncSession = Depends(get_db)
):
    """Tenant Manager: Get own profile"""
    
    # Get settings as well
    settings = await get_tenant_settings_from_db(tenant.id, db)
    
    return {
        "id": tenant.id,
        "name": tenant.name,
        "api_key": tenant.api_key,
        "created_at": tenant.created_at,
        "settings": {
            "office_start_time": settings["office_start_time"],
            "office_end_time": settings["office_end_time"],
            "late_threshold_minutes": settings["late_threshold_minutes"],
            "working_days": settings["working_days"],
            "min_working_hours": settings["min_working_hours"]
        }
    }


# =========================
# PUBLIC SETTINGS ENDPOINT (No Auth Required)
# =========================

@router.get("/settings/public")
async def get_public_settings(
    tenant_id: int = Query(..., description="Tenant ID to fetch settings for"),
    db: AsyncSession = Depends(get_db)
):
    """
    Public endpoint for frontend to fetch settings without authentication.
    Used by Org Admin and Employee dashboards to get attendance rules.
    """
    try:
        settings = await get_tenant_settings_from_db(tenant_id, db)
        
        # Return only non-sensitive information
        return {
            "office_start_time": settings["office_start_time"],
            "office_end_time": settings["office_end_time"],
            "late_threshold_minutes": settings["late_threshold_minutes"],
            "min_working_hours": settings["min_working_hours"],
            "working_days": settings["working_days"],
            "office_start": settings["office_start"].strftime("%H:%M"),
            "office_end": settings["office_end"].strftime("%H:%M")
        }
    except Exception as e:
        logger.error(f"Failed to fetch public settings for tenant {tenant_id}: {e}")
        # Return defaults instead of failing
        return {
            "office_start_time": "09:00:00",
            "office_end_time": "18:00:00",
            "late_threshold_minutes": 15,
            "min_working_hours": 9.0,
            "working_days": "1,2,3,4,5",
            "office_start": "09:00",
            "office_end": "18:00"
        }


# =========================
# BULK SETTINGS ENDPOINT (For multiple tenants - Super Admin only)
# =========================

@router.get("/settings/bulk")
async def get_bulk_settings(
    tenant_ids: str = Query(..., description="Comma-separated tenant IDs"),
    db: AsyncSession = Depends(get_db),
    tenant: Tenant = Depends(verify_tenant_api_key)  # Requires tenant admin access
):
    """Get settings for multiple tenants (useful for super admin dashboards)"""
    
    ids = [int(id.strip()) for id in tenant_ids.split(',')]
    
    result = await db.execute(text("""
        SELECT 
            tenant_id,
            office_start_time,
            office_end_time,
            late_threshold_minutes,
            working_days,
            min_working_hours
        FROM settings
        WHERE tenant_id = ANY(:tenant_ids)
    """), {"tenant_ids": ids})
    
    settings_list = result.mappings().all()
    
    # Create a map for easy lookup
    settings_map = {}
    for setting in settings_list:
        settings_map[setting["tenant_id"]] = dict(setting)
    
    # Fill in defaults for tenants without settings
    for tenant_id in ids:
        if tenant_id not in settings_map:
            settings_map[tenant_id] = {
                "tenant_id": tenant_id,
                "office_start_time": "09:00:00",
                "office_end_time": "18:00:00",
                "late_threshold_minutes": 15,
                "working_days": "1,2,3,4,5",
                "min_working_hours": 9.0
            }
    
    return list(settings_map.values())


# =========================
# SETTINGS VALIDATION ENDPOINT
# =========================

@router.post("/settings/validate")
async def validate_settings(
    data: SettingsUpdate,
    tenant: Tenant = Depends(verify_tenant_api_key)
):
    """Validate settings without saving them"""
    
    # All validation is done by Pydantic
    return {
        "valid": True,
        "message": "Settings are valid",
        "settings": {
            "office_start_time": data.office_start_time,
            "office_end_time": data.office_end_time,
            "late_threshold_minutes": data.late_threshold_minutes,
            "working_days": data.working_days,
            "min_working_hours": data.min_working_hours
        }
    }


# =========================
# UPDATED CHANGE API KEY ENDPOINT
# =========================

@router.post("/change-api-key")
async def change_api_key(
    data: ChangeApiKeyRequest,
    x_api_key: str = Header(None, alias="X-API-Key"),
    token: str = Depends(oauth2_scheme_optional),
    db: AsyncSession = Depends(get_db)
):
    """
    Tenant changes own API key.
    Accepts BOTH:
    - API Key authentication (X-API-Key header) - for existing API key users
    - JWT Bearer token authentication - for users logged in via /tenant-login
    
    This allows tenants to change their API key regardless of how they authenticated.
    """
    
    try:
        tenant = None
        
        # Method 1: Try API Key from header (X-API-Key)
        if x_api_key:
            result = await db.execute(
                select(Tenant).where(Tenant.api_key == x_api_key)
            )
            tenant = result.scalars().first()
            if tenant:
                logger.info(f"Tenant authenticated via API key: {tenant.id} ({tenant.name})")
        
        # Method 2: Try JWT Bearer token
        if not tenant and token:
            payload = decode_token(token)
            if payload and payload.get("type") == "access":
                # Verify this is a tenant token
                if payload.get("role") == "tenant_admin":
                    tenant_id = payload.get("tenant_id")
                    if tenant_id:
                        result = await db.execute(
                            select(Tenant).where(Tenant.id == tenant_id)
                        )
                        tenant = result.scalars().first()
                        if tenant:
                            logger.info(f"Tenant authenticated via JWT: {tenant.id} ({tenant.name})")
        
        # No valid authentication found
        if not tenant:
            logger.warning("Change API key attempt - no valid authentication")
            raise HTTPException(401, "Unauthorized - Valid API key or JWT token required")
        
        # Store old key for logging
        old_key_preview = tenant.api_key[:8] + "..." if tenant.api_key else "None"
        
        # Update API key with the provided value
        tenant.api_key = data.api_key
        await db.commit()
        
        logger.info(f"API key changed for tenant: {tenant.id} ({tenant.name})")
        logger.warning(f"Old key: {old_key_preview}, New key: {data.api_key[:8]}...")
        
        # Invalidate settings cache (though API key change doesn't affect settings)
        invalidate_settings_cache(tenant.id)
        
        return {
            "message": "API key changed successfully",
            "tenant_id": tenant.id,
            "tenant_name": tenant.name
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Change API key error: {str(e)}")
        await db.rollback()
        raise HTTPException(500, "Internal server error")


# =========================
# UTILITY ENDPOINT - Clear Settings Cache (for debugging)
# =========================

@router.post("/settings/clear-cache")
async def clear_settings_cache(
    tenant: Tenant = Depends(verify_tenant_api_key)
):
    """Clear cached settings for this tenant (useful for debugging)"""
    invalidate_settings_cache(tenant.id)
    return {"message": f"Cache cleared for tenant {tenant.id}"}


# =========================
# SETTINGS HISTORY (Optional - if you want to track changes)
# =========================

@router.get("/settings/history")
async def get_settings_history(
    limit: int = 10,
    tenant: Tenant = Depends(verify_tenant_api_key),
    db: AsyncSession = Depends(get_db)
):
    """
    Get settings change history (requires a settings_history table)
    This is a placeholder - implement if you want to track changes over time
    """
    # Note: You'd need to create a settings_history table first
    # For now, return a message
    return {
        "message": "Settings history feature requires additional database table",
        "suggestion": "Create settings_history table to track changes"
    }


@router.get("/settings/public")
async def get_public_settings(
    tenant_id: int = Query(..., description="Tenant ID"),
    db: AsyncSession = Depends(get_db)
):
    """
    PUBLIC ENDPOINT - No authentication required.
    Get tenant settings by tenant_id.
    Anyone from the same company can access this.
    """
    try:
        from app.services.tenant_settings_service import get_tenant_settings
        settings = await get_tenant_settings(tenant_id, db)
        
        return {
            "office_start_time": settings["office_start_time"],
            "office_end_time": settings["office_end_time"],
            "late_threshold_minutes": settings["late_threshold_minutes"],
            "min_working_hours": settings["min_working_hours"],
            "working_days": settings["working_days"]
        }
    except Exception as e:
        logger.error(f"Failed to fetch public settings: {e}")
        return {
            "office_start_time": "09:00:00",
            "office_end_time": "18:00:00",
            "late_threshold_minutes": 15,
            "min_working_hours": 9.0,
            "working_days": "1,2,3,4,5"
        }