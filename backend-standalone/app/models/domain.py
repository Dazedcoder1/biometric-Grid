from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Index, Enum, UniqueConstraint, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func
import enum

Base = declarative_base()


# =========================
# ENUMS
# =========================

class CommandStatus(str, enum.Enum):
    PENDING = "PENDING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


class UserRole(str, enum.Enum):
    SUPER_ADMIN = "super_admin"
    ORG_ADMIN = "org_admin"
    DEPT_ADMIN = "dept_admin"
    EMPLOYEE = "employee"


# =========================
# TENANT
# =========================

class Tenant(Base):
    __tablename__ = "tenants"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    api_key = Column(String, unique=True, index=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


# =========================
# DEPARTMENT
# =========================

class Department(Base):
    __tablename__ = "departments"

    department_id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False)
    department_name = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint('tenant_id', 'department_name', name='uix_tenant_dept_name'),
    )


# =========================
# DEVICE
# =========================

class Device(Base):
    __tablename__ = "devices"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False)
    device_id = Column(String, index=True, nullable=False)
    secret_key = Column(String, nullable=False)
    status = Column(String, default="offline")
    last_seen = Column(DateTime(timezone=True))

    __table_args__ = (
        Index('ix_tenant_device', 'tenant_id', 'device_id', unique=True),
    )


# =========================
# USER
# =========================

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=True)
    employee_code = Column(String, nullable=True, index=True)
    finger_id = Column(Integer, nullable=True)

    name = Column(String, nullable=False)
    email = Column(String, nullable=True)
    password_hash = Column(String, nullable=True)
    dept_id = Column(Integer, ForeignKey("departments.department_id"), nullable=True)
    role = Column(String, default="employee")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index('ix_tenant_finger', 'tenant_id', 'finger_id', unique=True, postgresql_where=(finger_id.isnot(None))),
        Index('ix_tenant_employee_code', 'tenant_id', 'employee_code', unique=True),
    )


# =========================
# ATTENDANCE LOG
# =========================

class AttendanceLog(Base):
    __tablename__ = "attendance_logs"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False)
    device_id = Column(String, nullable=False)

    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    finger_id = Column(Integer, nullable=False)

    record_type = Column(String, nullable=False, default="IN")
    timestamp = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index('ix_tenant_timestamp', 'tenant_id', 'timestamp'),
        UniqueConstraint('tenant_id', 'device_id', 'finger_id', 'timestamp', name='uix_attendance_record')
    )


# =========================
# COMMAND
# =========================

class Command(Base):
    __tablename__ = "commands"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False)
    device_id = Column(String, nullable=False)
    command = Column(String, nullable=False)
    target_id = Column(Integer, nullable=True)
    status = Column(Enum(CommandStatus, name="commandstatus", values_callable=lambda x: [e.value for e in x]), default=CommandStatus.PENDING)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


# =========================
# REFRESH TOKEN
# =========================

class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    token_jti = Column(String, unique=True, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    is_revoked = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


# =========================
# HOLIDAYS
# =========================

class Holiday(Base):
    __tablename__ = "holidays"

    holiday_id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False)
    name = Column(String, nullable=False)
    holiday_date = Column(DateTime, nullable=False)
    description = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (UniqueConstraint('tenant_id', 'holiday_date', name='uix_tenant_holiday_date'),)


# =========================
# LEAVES
# =========================

class Leave(Base):
    __tablename__ = "leaves"

    leave_id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False)
    employee_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    leave_type = Column(String, nullable=False)
    start_date = Column(DateTime, nullable=False)
    end_date = Column(DateTime, nullable=False)
    reason = Column(String, nullable=True)
    status = Column(String, default="pending")
    dept_approved_at = Column(DateTime(timezone=True), nullable=True)
    dept_approved_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    approved_by = Column(Integer, nullable=True)
    rejected_at = Column(DateTime(timezone=True), nullable=True)
    rejection_reason = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


# =========================
# SETTINGS
# =========================

class Settings(Base):
    __tablename__ = "settings"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, unique=True)
    office_start_time = Column(String, default="09:00:00")
    office_end_time = Column(String, default="18:00:00")
    late_threshold_minutes = Column(Integer, default=15)
    working_days = Column(String, default="1,2,3,4,5")
    min_working_hours = Column(Integer, default=9)  # ✅ NEW - Minimum hours required per day
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


# =========================
# NOTIFICATIONS
# =========================

class Notification(Base):
    __tablename__ = "notifications"

    notification_id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False)
    
    # Who did it
    actor_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    actor_name = Column(String, nullable=True)
    
    # Who receives it
    recipient_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    
    # What happened
    event_type = Column(String, nullable=False)
    entity_type = Column(String, nullable=True)
    entity_id = Column(Integer, nullable=True)
    entity_name = Column(String, nullable=True)
    
    # The message
    title = Column(String, nullable=False)
    message = Column(String, nullable=False)
    
    # Read status
    is_read = Column(Boolean, default=False)
    read_at = Column(DateTime(timezone=True), nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())


# =========================
# LEAVE BALANCES (ADD THESE)
# =========================

class LeaveBalance(Base):
    __tablename__ = "leave_balances"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    leave_type = Column(String, nullable=False)  # 'sick', 'casual', 'earned'
    total_quota = Column(Integer, default=0)
    used_quota = Column(Integer, default=0)
    remaining_quota = Column(Integer, default=0)
    year = Column(Integer, nullable=False)
    last_updated = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    updated_by = Column(Integer, ForeignKey("users.id"), nullable=True)

    __table_args__ = (
        UniqueConstraint('tenant_id', 'user_id', 'leave_type', 'year', name='uix_user_leave_balance_year'),
        Index('ix_tenant_user_balance', 'tenant_id', 'user_id', 'year'),
    )


class LeaveSettings(Base):
    __tablename__ = "leave_settings"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, unique=True)
    sick_leave_quota = Column(Integer, default=12)
    casual_leave_quota = Column(Integer, default=12)
    earned_leave_quota = Column(Integer, default=15)
    reset_frequency = Column(String, default="yearly")  # 'yearly', 'monthly', 'never'
    carry_forward_limit = Column(Integer, default=0)
    auto_approve_limit = Column(Integer, default=0)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    updated_by = Column(Integer, ForeignKey("users.id"), nullable=True)


class LeaveBalanceHistory(Base):
    __tablename__ = "leave_balance_history"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    leave_type = Column(String, nullable=False)
    previous_balance = Column(Integer, default=0)
    new_balance = Column(Integer, default=0)
    adjustment = Column(Integer, default=0)
    reason = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)