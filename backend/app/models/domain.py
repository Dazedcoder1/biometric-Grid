from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Index, Enum, UniqueConstraint, Boolean, Text, Float
from sqlalchemy.orm import declarative_base
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
    # GitHub login, for mirroring task assignment onto the issue. GitHub has no
    # way to resolve our users, so this mapping has to be entered by hand.
    github_username = Column(String, nullable=True)
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
    # The minimum a day must contain to count as worked. Every attendance
    # screen already displayed this and every compliance figure was computed
    # against it, but the column did not exist — so the UI silently used its
    # own hardcoded 9.0 and the Settings page had nowhere to save a change.
    # Float rather than Integer: half-day and 7.5-hour arrangements are common.
    min_working_hours = Column(Float, nullable=False, server_default="9.0")
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

# =========================
# TASK MANAGEMENT
# Ported from the standalone task-manager app.
# 'teams' there maps onto this project's existing Department.
# =========================

class TaskStatus(str, enum.Enum):
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    IN_REVIEW = "in_review"
    DONE = "done"


class TaskPriority(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class TaskSource(str, enum.Enum):
    MANUAL = "manual"
    GITHUB = "github"


class GitHubRepo(Base):
    """A GitHub repository a tenant mirrors issues from."""
    __tablename__ = "github_repos"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)

    # "owner/name" exactly as GitHub reports it in webhook payloads
    full_name = Column(String, nullable=False)

    # Personal access token, Fernet-encrypted at rest. Never returned by the API.
    token_encrypted = Column(Text, nullable=True)
    # Shared secret for validating webhook signatures, also encrypted.
    webhook_secret_encrypted = Column(Text, nullable=True)

    is_active = Column(Boolean, default=True, nullable=False)
    # Only issues with this label are mirrored, when set.
    label_filter = Column(String, nullable=True)

    # At most one default per tenant — new tasks push here without anyone
    # choosing a repo. Enforced in the route, not by a constraint, because
    # a partial unique index is Postgres-specific.
    is_default = Column(Boolean, default=False, nullable=False)
    # Applied to issues opened from tasks that have no assignee of their own.
    default_assignee_id = Column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    last_synced_at = Column(DateTime(timezone=True), nullable=True)
    last_sync_error = Column(String, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("tenant_id", "full_name", name="uix_tenant_github_repo"),
    )


class Task(Base):
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)

    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)

    source = Column(String, nullable=False, default=TaskSource.MANUAL.value)
    status = Column(String, nullable=False, default=TaskStatus.TODO.value)
    priority = Column(String, nullable=False, default=TaskPriority.MEDIUM.value)

    # --- GitHub mirror fields (null for manually created tasks) ---
    github_repo_id = Column(Integer, ForeignKey("github_repos.id", ondelete="SET NULL"), nullable=True)
    github_repo = Column(String, nullable=True)
    github_issue_number = Column(Integer, nullable=True)
    github_url = Column(String, nullable=True)
    github_state = Column(String, nullable=True)       # open / closed, as GitHub sees it
    github_labels = Column(String, nullable=True)      # comma-separated
    github_updated_at = Column(DateTime(timezone=True), nullable=True)

    # --- Assignment ---
    dept_id = Column(Integer, ForeignKey("departments.department_id", ondelete="SET NULL"), nullable=True)
    assigned_to = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    created_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    due_date = Column(DateTime, nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        # Makes webhook delivery idempotent: the same issue upserts instead of duplicating.
        UniqueConstraint("tenant_id", "github_repo", "github_issue_number",
                         name="uix_tenant_repo_issue"),
        Index("ix_task_tenant_status", "tenant_id", "status"),
    )


class TaskComment(Base):
    __tablename__ = "task_comments"

    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(Integer, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    author_name = Column(String, nullable=True)   # snapshot, survives user deletion
    body = Column(Text, nullable=False)
    # Set once the comment has been mirrored onto the GitHub issue. Also marks
    # the comment as ours, so an inbound issue_comment event can be ignored
    # instead of being re-imported as a duplicate.
    github_comment_id = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


# Legacy compat alias
AdminUser = User