from pydantic import BaseModel, Field
from typing import List, Optional
import datetime
from app.models.domain import CommandStatus


# =========================
# USERS
# =========================

class UserEnrollRequest(BaseModel):
    finger_id: int = Field(..., ge=1, le=127)
    name: str
    employee_code: str
    password: Optional[str] = None  # ✅ NEW
    target_tenant_id: Optional[int] = None

class UserDeleteRequest(BaseModel):
    finger_id: int = Field(..., ge=1, le=127)
    target_tenant_id: Optional[int] = None


# =========================
# DEVICES
# =========================

class DeviceRegisterRequest(BaseModel):
    device_id: str
    secret_key: str


class DeviceResponse(BaseModel):
    device_id: str
    status: str
    last_seen: Optional[datetime.datetime]


# =========================
# ATTENDANCE
# =========================

class SyncItem(BaseModel):
    finger_id: int
    timestamp: datetime.datetime


class BulkAttendanceRequest(BaseModel):
    logs: List[SyncItem]


class AttendanceLogResponse(BaseModel):
    timestamp: datetime.datetime
    finger_id: int
    device_id: str
    record_type: str
    user_id: Optional[int] = None
    employee_code: Optional[str] = None
    user_name: Optional[str] = "Unknown"
    
    # ✅ NEW FIELDS
    hours_worked: Optional[float] = None
    met_min_hours: Optional[bool] = None
    working_hours_status: Optional[str] = None
    is_late: Optional[bool] = None
    late_status_message: Optional[str] = None
# =========================
# COMMANDS
# =========================

class CommandRequest(BaseModel):
    device_id: str
    command: str
    target_id: Optional[int] = None

class HolidayCreate(BaseModel):
    name: str
    holiday_date: datetime.date
    description: Optional[str] = None


class HolidayResponse(BaseModel):
    holiday_id: int
    name: str
    holiday_date: datetime.date
    description: Optional[str] = None

class LeaveApplyRequest(BaseModel):
    leave_type: str
    start_date: datetime.date
    end_date: datetime.date
    reason: Optional[str] = None


class LeaveResponse(BaseModel):
    leave_id: int
    employee_id: int
    employee_name: str
    leave_type: str
    start_date: datetime.date
    end_date: datetime.date
    reason: Optional[str]
    status: str
    created_at: datetime.datetime

class NotificationResponse(BaseModel):
    notification_id: int
    title: str
    message: str
    type: str
    is_read: bool
    created_at: datetime.datetime


class SettingsResponse(BaseModel):
    office_start_time: str
    office_end_time: str
    late_threshold_minutes: int
    working_days: str
    min_working_hours: int  # ✅ NEW

class SettingsUpdateRequest(BaseModel):
    office_start_time: Optional[str] = "09:00:00"
    office_end_time: Optional[str] = "18:00:00"
    late_threshold_minutes: Optional[int] = 15
    working_days: Optional[str] = "1,2,3,4,5"
    min_working_hours: Optional[int] = 9  # ✅ NEW