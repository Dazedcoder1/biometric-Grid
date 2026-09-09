from pydantic import BaseModel, Field, EmailStr
from typing import List, Optional
import datetime

# =========================
# COMMON
# =========================

class MessageResponse(BaseModel):
    message: str


# =========================
# AUTH
# =========================

class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class LoginRequest(BaseModel):
    identifier: str
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


# =========================
# USER / PROFILE
# =========================

class UserResponse(BaseModel):
    id: int
    email: Optional[str]
    name: str
    employee_code: Optional[str]
    role: str
    is_active: bool
    dept_id: Optional[int]
    tenant_id: Optional[int]

    class Config:
        from_attributes = True


class ProfileUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[EmailStr] = None


# =========================
# ATTENDANCE
# =========================

class AttendanceLogResponse(BaseModel):
    timestamp: datetime.datetime
    finger_id: int
    device_id: str
    record_type: str
    user_name: Optional[str] = "Unknown"

    class Config:
        from_attributes = True


class AttendanceStats(BaseModel):
    total_present_days: int
    total_late_days: int
    total_hours_worked: float
    average_hours_per_day: float


class MonthlyStats(BaseModel):
    month: int
    year: int
    attendance_percentage: float
    present_days: int
    absent_days: int
    late_days: int


class SyncItem(BaseModel):
    finger_id: int
    timestamp: datetime.datetime


class BulkAttendanceRequest(BaseModel):
    logs: List[SyncItem]


# =========================
# LEAVES
# =========================

class LeaveCreate(BaseModel):
    leave_type: str
    start_date: datetime.date
    end_date: datetime.date
    reason: Optional[str] = None


class LeaveResponse(BaseModel):
    leave_id: int
    leave_type: str
    start_date: datetime.datetime
    end_date: datetime.datetime
    reason: Optional[str]
    status: str
    created_at: datetime.datetime

    class Config:
        from_attributes = True


# =========================
# HOLIDAYS
# =========================

class HolidayResponse(BaseModel):
    holiday_id: int
    name: str
    holiday_date: datetime.datetime
    description: Optional[str]

    class Config:
        from_attributes = True


# =========================
# NOTIFICATIONS
# =========================

class NotificationResponse(BaseModel):
    notification_id: int
    title: str
    message: str
    event_type: str
    is_read: bool
    created_at: datetime.datetime

    class Config:
        from_attributes = True


# =========================
# DASHBOARD
# =========================

class EmployeeDashboardResponse(BaseModel):
    today_status: str  # present / absent
    check_in: Optional[datetime.datetime]
    check_out: Optional[datetime.datetime]
    working_hours: float
    
    monthly_attendance_pct: float
    present_days_count: int
    absent_days_count: int
    late_days_count: int
    
    upcoming_holiday: Optional[HolidayResponse]
    pending_leaves_count: int
    last_check_in: Optional[datetime.datetime]
    
    attendance_trend: List[float] # Last 4 weeks


# =========================
# DEVICE / ADMIN (From previous version)
# =========================

class DeviceRegisterRequest(BaseModel):
    device_id: str
    secret_key: str


class DeviceResponse(BaseModel):
    device_id: str
    status: str
    last_seen: Optional[datetime.datetime]


class CommandRequest(BaseModel):
    device_id: str
    command: str
    target_id: Optional[int] = None