from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Index, Enum, UniqueConstraint, Boolean, Text, Float, Numeric, Date, JSON, LargeBinary
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
    # Set when an administrator issues a temporary password. Until the person
    # chooses their own, every authenticated route except changing it refuses
    # them — see dependencies.get_current_user. Migration c8d9e0f1a2b3.
    must_change_password = Column(Boolean, nullable=False, default=False, server_default="false")
    # HR access on top of the person's own role: an employee or Org Admin who
    # also runs payroll. Granted by a Tenant Admin or Super Admin; adds the
    # "hr" system role's permissions (deps_security.load_permissions).
    is_hr = Column(Boolean, nullable=False, default=False, server_default="false")
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
    # NULL for a web sign-in: there is no finger, the person is identified by
    # user_id from their session.
    finger_id = Column(Integer, nullable=True)

    record_type = Column(String, nullable=False, default="IN")
    timestamp = Column(DateTime(timezone=True), server_default=func.now())

    # "device" (fingerprint scanner) or "web" (the Sign In button). Both feed
    # the same day: a web sign-in can be closed at the scanner and vice versa.
    source = Column(String(16), nullable=False, default="device", server_default="device")
    # Where a web punch came from, for admins reviewing remote sign-ins.
    source_ip = Column(String(64), nullable=True)

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



# =========================
# PAYROLL
# Indian payroll: monthly salary and stipend, structured as components the
# organisation defines itself (nothing statutory is preloaded — PF, ESI,
# Professional Tax, LWF and TDS are added as components with their own
# rates, ceilings and slabs). See app/services/payroll_service.py.
# =========================

class PayComponent(Base):
    """One line that can appear on a payslip: Basic, HRA, PF, PT, ..."""
    __tablename__ = "pay_components"

    id = Column(Integer, primary_key=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    code = Column(String(32), nullable=False)            # BASIC, HRA, PF, PT ...
    name = Column(String(80), nullable=False)
    kind = Column(String(16), nullable=False)            # earning | deduction
    # fixed    the monthly amount comes from the person's salary structure
    # percent  rate% of the earnings named in base_codes (or GROSS)
    # slab     a flat amount picked by gross pay — Professional Tax
    calc = Column(String(16), nullable=False, default="fixed")
    rate = Column(Numeric(7, 4), nullable=True)           # employee %, for percent
    employer_rate = Column(Numeric(7, 4), nullable=True)  # employer % (shown, not deducted)
    base_codes = Column(String(255), nullable=True)       # "BASIC,DA" or "GROSS"
    wage_ceiling = Column(Numeric(12, 2), nullable=True)  # base is capped here (PF 15,000)
    gross_limit = Column(Numeric(12, 2), nullable=True)   # applies only up to this gross (ESI 21,000)
    slabs = Column(JSON, nullable=True)                   # [{"upto": 15000, "amount": 0}, {"upto": null, "amount": 200}]
    prorate = Column(Boolean, nullable=False, default=True, server_default="true")
    applies_to = Column(String(16), nullable=False, default="all", server_default="all")  # all | salary | stipend
    is_statutory = Column(Boolean, nullable=False, default=False, server_default="false")
    active = Column(Boolean, nullable=False, default=True, server_default="true")
    sort_order = Column(Integer, nullable=False, default=100, server_default="100")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (UniqueConstraint("tenant_id", "code", name="uq_pay_component_code"),)


class EmployeePayProfile(Base):
    """Pay type and the compliance fields a payslip and register need."""
    __tablename__ = "employee_pay_profiles"

    id = Column(Integer, primary_key=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True)
    pay_type = Column(String(16), nullable=False, default="salary", server_default="salary")  # salary | stipend
    designation = Column(String(80), nullable=True)
    date_of_joining = Column(Date, nullable=True)
    pan = Column(String(10), nullable=True)
    uan = Column(String(12), nullable=True)
    pf_number = Column(String(32), nullable=True)
    esic_number = Column(String(17), nullable=True)
    pt_state = Column(String(40), nullable=True)
    bank_name = Column(String(80), nullable=True)
    bank_account = Column(String(34), nullable=True)
    bank_ifsc = Column(String(11), nullable=True)
    # Components that do not apply to this person, e.g. "PF" for an
    # employee who has opted out, comma separated.
    exempt_codes = Column(String(255), nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class SalaryRevision(Base):
    """
    A salary structure from a date onwards. Append-only: the history of
    revisions IS the salary revision history, and the structure for a month
    is the latest revision effective on or before that month's last day.
    """
    __tablename__ = "salary_revisions"

    id = Column(Integer, primary_key=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    effective_from = Column(Date, nullable=False)
    annual_ctc = Column(Numeric(14, 2), nullable=False)
    lines = Column(JSON, nullable=False)                 # {"BASIC": 25000, "HRA": 10000, ...} monthly
    reason = Column(String(255), nullable=True)
    created_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (Index("ix_salary_rev_user_from", "tenant_id", "user_id", "effective_from"),)


class Reimbursement(Base):
    """An expense claim. Approved claims are paid with the next payroll."""
    __tablename__ = "reimbursements"

    id = Column(Integer, primary_key=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    category = Column(String(40), nullable=False)
    description = Column(String(500), nullable=True)
    amount = Column(Numeric(12, 2), nullable=False)
    expense_date = Column(Date, nullable=False)
    reference = Column(String(120), nullable=True)        # bill / invoice number
    status = Column(String(16), nullable=False, default="pending", server_default="pending")  # pending|approved|rejected|paid
    decided_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    decided_at = Column(DateTime(timezone=True), nullable=True)
    decision_note = Column(String(255), nullable=True)
    payroll_run_id = Column(Integer, ForeignKey("payroll_runs.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (Index("ix_reimb_tenant_status", "tenant_id", "status"),)


class PayrollRun(Base):
    """
    One organisation, one month. draft -> submitted -> closed.

    Maker-checker: the person who submits a month cannot approve it. Closing
    is approval; a closed month is never recalculated — corrections go into a
    later month as an adjustment.
    """
    __tablename__ = "payroll_runs"

    id = Column(Integer, primary_key=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    period = Column(Date, nullable=False)                 # first day of the month
    status = Column(String(16), nullable=False, default="draft", server_default="draft")
    prepared_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    prepared_at = Column(DateTime(timezone=True), nullable=True)
    submitted_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    submitted_at = Column(DateTime(timezone=True), nullable=True)
    approved_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    returned_note = Column(String(500), nullable=True)
    totals = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (UniqueConstraint("tenant_id", "period", name="uq_payroll_run_period"),)


class PayrollEntry(Base):
    """One person's pay for one run — the payslip, frozen when the run closes."""
    __tablename__ = "payroll_entries"

    id = Column(Integer, primary_key=True)
    run_id = Column(Integer, ForeignKey("payroll_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    data = Column(JSON, nullable=False)                   # the computed payslip
    lop_override = Column(Numeric(5, 2), nullable=True)   # admin's LOP days, replacing the computed figure
    override_note = Column(String(255), nullable=True)
    adjustments = Column(JSON, nullable=True)             # [{"kind": "earning", "label": "Bonus", "amount": 5000}]
    gross = Column(Numeric(14, 2), nullable=False, default=0)
    net_pay = Column(Numeric(14, 2), nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (UniqueConstraint("run_id", "user_id", name="uq_payroll_entry_person"),)


# =========================
# HR DOCUMENTS & LETTERS
# Letters are generated from the organisation's templates and frozen when
# issued; policies and the handbook are versioned and acknowledged per
# version; employee documents carry expiry dates. Files live in the database
# (stored_files) — see app/services/hr_documents.py.
# =========================

class StoredFile(Base):
    """An uploaded file's bytes. Referenced by document versions; never edited."""
    __tablename__ = "stored_files"

    id = Column(Integer, primary_key=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    file_name = Column(String(255), nullable=False)
    content_type = Column(String(100), nullable=False)
    size = Column(Integer, nullable=False)
    sha256 = Column(String(64), nullable=False)
    data = Column(LargeBinary, nullable=False)
    uploaded_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class HrSettings(Base):
    """Letterhead: what every generated letter says at the top and bottom."""
    __tablename__ = "hr_settings"

    id = Column(Integer, primary_key=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, unique=True)
    company_name = Column(String(160), nullable=True)
    address = Column(Text, nullable=True)
    contact_line = Column(String(255), nullable=True)      # phone · email · website
    cin = Column(String(32), nullable=True)                 # company identification number
    signatory_name = Column(String(120), nullable=True)
    signatory_title = Column(String(120), nullable=True)
    footer = Column(String(255), nullable=True)
    reference_prefix = Column(String(20), nullable=True)    # e.g. NWT -> NWT/OFFER/2026/0007
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class LetterTemplate(Base):
    __tablename__ = "letter_templates"

    id = Column(Integer, primary_key=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    kind = Column(String(32), nullable=False)       # offer, appointment, internship, confirmation, ...
    name = Column(String(120), nullable=False)
    subject = Column(String(200), nullable=False)
    body = Column(Text, nullable=False)              # paragraphs with {{placeholders}}
    version = Column(Integer, nullable=False, default=1, server_default="1")
    active = Column(Boolean, nullable=False, default=True, server_default="true")
    updated_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class LetterTemplateVersion(Base):
    """Every saved wording of a template, newest last."""
    __tablename__ = "letter_template_versions"

    id = Column(Integer, primary_key=True)
    template_id = Column(Integer, ForeignKey("letter_templates.id", ondelete="CASCADE"), nullable=False, index=True)
    version = Column(Integer, nullable=False)
    subject = Column(String(200), nullable=False)
    body = Column(Text, nullable=False)
    note = Column(String(255), nullable=True)
    created_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (UniqueConstraint("template_id", "version", name="uq_letter_template_version"),)


class Letter(Base):
    """
    A letter to one person. Draft while HR edits it; frozen when issued —
    the PDF is always rebuilt from the issued text, so it never changes.
    A wrong letter is revoked and a new one issued.
    """
    __tablename__ = "letters"

    id = Column(Integer, primary_key=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    template_id = Column(Integer, ForeignKey("letter_templates.id", ondelete="SET NULL"), nullable=True)
    template_version = Column(Integer, nullable=True)
    kind = Column(String(32), nullable=False)
    subject = Column(String(200), nullable=False)
    body = Column(Text, nullable=False)              # rendered text
    fields = Column(JSON, nullable=True)             # values used to fill it
    letterhead = Column(JSON, nullable=True)         # snapshot when issued
    letter_date = Column(Date, nullable=False)
    reference_no = Column(String(60), nullable=True)
    status = Column(String(16), nullable=False, default="draft", server_default="draft")   # draft|issued|revoked
    created_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    issued_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    issued_at = Column(DateTime(timezone=True), nullable=True)
    acknowledged_at = Column(DateTime(timezone=True), nullable=True)   # the person accepted / received it
    revoked_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    revoke_reason = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class HrDocument(Base):
    """A policy, the handbook, or any document published to employees."""
    __tablename__ = "hr_documents"

    id = Column(Integer, primary_key=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    category = Column(String(32), nullable=False)    # leave_policy, attendance_policy, handbook, policy, other
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    requires_ack = Column(Boolean, nullable=False, default=True, server_default="true")
    audience = Column(JSON, nullable=True)           # null = everyone; {"departments": [ids]}
    review_by = Column(Date, nullable=True)          # when it must be reviewed — reminders before
    status = Column(String(16), nullable=False, default="active", server_default="active")  # active|archived
    current_version = Column(Integer, nullable=False, default=0, server_default="0")
    last_reminded_on = Column(Date, nullable=True)
    created_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class HrDocumentVersion(Base):
    __tablename__ = "hr_document_versions"

    id = Column(Integer, primary_key=True)
    document_id = Column(Integer, ForeignKey("hr_documents.id", ondelete="CASCADE"), nullable=False, index=True)
    version = Column(Integer, nullable=False)
    file_id = Column(Integer, ForeignKey("stored_files.id", ondelete="SET NULL"), nullable=True)
    body = Column(Text, nullable=True)               # written in the app instead of uploaded
    change_note = Column(String(255), nullable=True)
    published_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    published_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (UniqueConstraint("document_id", "version", name="uq_hr_document_version"),)


class HrDocumentAck(Base):
    """'I have read and acknowledge' — per person, per version."""
    __tablename__ = "hr_document_acks"

    id = Column(Integer, primary_key=True)
    document_id = Column(Integer, ForeignKey("hr_documents.id", ondelete="CASCADE"), nullable=False)
    version_id = Column(Integer, ForeignKey("hr_document_versions.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    acknowledged_at = Column(DateTime(timezone=True), server_default=func.now())
    source_ip = Column(String(64), nullable=True)

    __table_args__ = (
        UniqueConstraint("version_id", "user_id", name="uq_hr_document_ack"),
        Index("ix_hr_document_ack_doc", "document_id", "user_id"),
    )


class EmployeeDocument(Base):
    """A document in a person's file: ID proof, contract, visa, certificate…"""
    __tablename__ = "employee_documents"

    id = Column(Integer, primary_key=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    doc_type = Column(String(32), nullable=False)
    title = Column(String(200), nullable=False)
    number = Column(String(80), nullable=True)
    issued_on = Column(Date, nullable=True)
    expires_on = Column(Date, nullable=True)
    current_version = Column(Integer, nullable=False, default=1, server_default="1")
    file_id = Column(Integer, ForeignKey("stored_files.id", ondelete="SET NULL"), nullable=True)
    notes = Column(String(500), nullable=True)
    reminder_stage = Column(Integer, nullable=True)   # smallest days-left threshold already reminded
    uploaded_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (Index("ix_employee_documents_expiry", "tenant_id", "expires_on"),)


class EmployeeDocumentVersion(Base):
    __tablename__ = "employee_document_versions"

    id = Column(Integer, primary_key=True)
    document_id = Column(Integer, ForeignKey("employee_documents.id", ondelete="CASCADE"), nullable=False, index=True)
    version = Column(Integer, nullable=False)
    file_id = Column(Integer, ForeignKey("stored_files.id", ondelete="SET NULL"), nullable=True)
    number = Column(String(80), nullable=True)
    issued_on = Column(Date, nullable=True)
    expires_on = Column(Date, nullable=True)
    note = Column(String(255), nullable=True)
    created_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

# Legacy compat alias
AdminUser = User