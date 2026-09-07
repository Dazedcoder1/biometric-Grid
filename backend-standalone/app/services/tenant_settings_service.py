"""
Tenant Settings Service - Core service for managing and caching tenant settings
"""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from datetime import datetime, time, date, timezone, timedelta
from typing import Optional, Dict, Any
import pytz
import logging

logger = logging.getLogger(__name__)

# Define IST timezone
IST = pytz.timezone('Asia/Kolkata')

# In-memory cache with TTL
_settings_cache: Dict[int, Dict[str, Any]] = {}
_cache_timestamps: Dict[int, datetime] = {}
CACHE_TTL_SECONDS = 300  # 5 minutes


def _utc_now() -> datetime:
    """Get current UTC datetime with timezone"""
    return datetime.now(timezone.utc)


def ensure_timezone_aware(dt: Optional[datetime]) -> Optional[datetime]:
    """Convert naive datetime to timezone-aware UTC datetime"""
    if dt is None:
        return None
    if dt.tzinfo is None:
        # Assume naive datetime is UTC
        return dt.replace(tzinfo=timezone.utc)
    return dt


def convert_to_ist(dt: datetime) -> datetime:
    """Convert any datetime to IST timezone"""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(IST)


async def get_tenant_settings(
    tenant_id: int,
    db: AsyncSession,
    force_refresh: bool = False
) -> Dict[str, Any]:
    """
    Get tenant settings from database with caching.
    Returns dict with all settings including parsed time objects.
    """
    # Check cache
    if not force_refresh and tenant_id in _settings_cache:
        cached_time = _cache_timestamps.get(tenant_id)
        if cached_time:
            # Ensure cached_time is timezone-aware
            if cached_time.tzinfo is None:
                cached_time = cached_time.replace(tzinfo=timezone.utc)
            now_utc = _utc_now()
            if (now_utc - cached_time).total_seconds() < CACHE_TTL_SECONDS:
                logger.debug(f"Returning cached settings for tenant {tenant_id}")
                return _settings_cache[tenant_id].copy()
    
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
    
    row = result.mappings().first()
    
    # Default settings if none found
    if not row:
        settings = {
            "office_start_time": "10:00:00",  # Changed to 10:00 AM IST
            "office_end_time": "17:00:00",    # Changed to 5:00 PM IST
            "late_threshold_minutes": 15,
            "working_days": "1,2,3,4,5",
            "min_working_hours": 6.0,         # Changed from 9.0 to 6.0 for 6-hour workday
            "updated_at": None
        }
    else:
        settings = dict(row)
        if settings.get("min_working_hours") is None:
            settings["min_working_hours"] = 6.0  # Changed default
    
    # Parse time strings to time objects
    # These times are stored as IST times in database
    settings["office_start"] = datetime.strptime(
        settings["office_start_time"], "%H:%M:%S"
    ).time()
    settings["office_end"] = datetime.strptime(
        settings["office_end_time"], "%H:%M:%S"
    ).time()
    
    # Parse working days
    settings["working_days_list"] = [
        int(d.strip()) for d in settings["working_days"].split(",") if d.strip()
    ]
    
    # Cache the result - use UTC time with timezone
    _settings_cache[tenant_id] = settings.copy()
    _cache_timestamps[tenant_id] = _utc_now()
    
    logger.debug(f"Cached settings for tenant {tenant_id} with IST office hours {settings['office_start_time']} to {settings['office_end_time']}")
    return settings


def invalidate_tenant_settings_cache(tenant_id: int):
    """Invalidate cached settings for a tenant"""
    if tenant_id in _settings_cache:
        del _settings_cache[tenant_id]
    if tenant_id in _cache_timestamps:
        del _cache_timestamps[tenant_id]
    logger.info(f"Invalidated settings cache for tenant {tenant_id}")


def calculate_late_status(
    check_in_time: datetime,
    settings: Dict[str, Any]
) -> tuple[bool, str]:
    """
    Calculate if a check-in time is considered late.
    Uses IST timezone for comparison.
    """
    if not check_in_time:
        return False, "No check-in time"
    
    # Ensure check_in_time is timezone-aware and convert to IST
    check_in_time = ensure_timezone_aware(check_in_time)
    check_in_ist = check_in_time.astimezone(IST)
    check_time = check_in_ist.time()
    
    office_start = settings["office_start"]
    late_threshold = settings.get("late_threshold_minutes", 15)
    
    # Calculate threshold time (office start + late threshold)
    total_minutes = office_start.hour * 60 + office_start.minute + late_threshold
    threshold_hour = total_minutes // 60
    threshold_minute = total_minutes % 60
    threshold_time = time(threshold_hour, threshold_minute)
    
    # Create threshold datetime for comparison
    threshold_dt = check_in_ist.replace(
        hour=threshold_hour, minute=threshold_minute, second=0, microsecond=0
    )
    
    if check_in_ist > threshold_dt:
        late_minutes = int((check_in_ist - threshold_dt).total_seconds() / 60) + late_threshold
        return True, f"Late by {late_minutes} minutes (after {office_start.strftime('%H:%M')})"
    
    return False, f"On time (before {threshold_time.strftime('%H:%M')})"


def calculate_valid_working_hours(
    check_in_time: Optional[datetime],
    check_out_time: Optional[datetime],
    settings: Dict[str, Any]
) -> tuple[float, float, float, bool, str]:
    """
    Calculate working hours WITHIN official office hours only.
    Uses IST timezone for office hour boundaries.
    
    Returns:
        (valid_hours, actual_duration, lost_hours, met_min_hours, status_message)
    """
    if not check_in_time or not check_out_time:
        return 0.0, 0.0, 0.0, False, "Incomplete attendance"
    
    # Ensure both are timezone-aware and convert to IST
    check_in_time = ensure_timezone_aware(check_in_time)
    check_out_time = ensure_timezone_aware(check_out_time)
    
    # Convert to IST for office hour comparison
    check_in_ist = check_in_time.astimezone(IST)
    check_out_ist = check_out_time.astimezone(IST)
    
    # Get the date for office hours (use check-in date in IST)
    work_date = check_in_ist.date()
    
    office_start = settings["office_start"]
    office_end = settings["office_end"]
    min_hours = settings.get("min_working_hours", 6.0)
    
    # Create office boundary datetimes in IST
    office_start_dt = IST.localize(datetime.combine(work_date, office_start))
    office_end_dt = IST.localize(datetime.combine(work_date, office_end))
    
    # If check-out is after midnight, adjust office end date
    if check_out_ist.date() > work_date:
        office_end_dt = IST.localize(datetime.combine(check_out_ist.date(), office_end))
    
    # Calculate actual duration (total time between check-in and check-out)
    actual_duration = (check_out_ist - check_in_ist).total_seconds() / 3600
    
    # Valid working hours = only time within office hours
    valid_start = max(check_in_ist, office_start_dt)
    valid_end = min(check_out_ist, office_end_dt)
    
    if valid_end > valid_start:
        valid_hours = (valid_end - valid_start).total_seconds() / 3600
    else:
        valid_hours = 0
    
    # Calculate lost hours (time outside office hours)
    lost_hours = max(0, actual_duration - valid_hours)
    
    # Check if met minimum working hours requirement
    met_min_hours = valid_hours >= min_hours
    
    # Create status message with better details
    if lost_hours > 0.1:  # More than 0.1 hour (6 minutes) lost
        status_msg = f"{valid_hours:.1f}h worked within office hours ({lost_hours:.1f}h outside office)"
    else:
        status_msg = f"{valid_hours:.1f}h worked within office hours"
    
    # Add extra info if minimum not met
    if not met_min_hours and valid_hours > 0:
        hours_needed = min_hours - valid_hours
        status_msg += f" (needs {hours_needed:.1f}h more to meet minimum)"
    
    return valid_hours, actual_duration, lost_hours, met_min_hours, status_msg


def is_working_day(check_date: date, settings: Dict[str, Any]) -> bool:
    """Check if a given date is a working day (Monday=1, Sunday=7)."""
    python_weekday = check_date.weekday()
    our_weekday = python_weekday + 1  # Convert to Monday=1 format
    working_days = settings.get("working_days_list", [1, 2, 3, 4, 5])  # Monday to Friday
    return our_weekday in working_days