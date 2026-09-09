from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel, Field, field_validator


def _coerce_optional_int(v):
    """HTML selects submit '' for "no selection"; treat that as null."""
    if v == "":
        return None
    return v


def _coerce_date_only(v):
    """
    Accept a plain 'YYYY-MM-DD' from <input type="date">.

    The field is a datetime, and Pydantic rejects a bare date for one, so a
    task with a due date failed validation with a 422 before this.
    """
    if isinstance(v, str):
        v = v.strip()
        if not v:
            return None
        if len(v) == 10 and v.count("-") == 2:
            return f"{v}T00:00:00"
    return v


# ─── Tasks ────────────────────────────────────────────────────────────────────

class TaskCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=500)
    description: Optional[str] = None
    priority: str = "medium"
    status: str = "todo"
    dept_id: Optional[int] = None
    assigned_to: Optional[int] = None
    due_date: Optional[datetime] = None
    # Where to open the issue. Omit and the tenant's default repo is used;
    # set keep_local to opt out of that default entirely.
    github_repo_id: Optional[int] = None
    keep_local: bool = False

    _due = field_validator("due_date", mode="before")(_coerce_date_only)
    _ints = field_validator("dept_id", "assigned_to", "github_repo_id",
                            mode="before")(_coerce_optional_int)


class TaskUpdate(BaseModel):
    """All optional — only supplied fields are changed."""
    title: Optional[str] = Field(None, min_length=1, max_length=500)
    description: Optional[str] = None
    priority: Optional[str] = None
    status: Optional[str] = None
    dept_id: Optional[int] = None
    assigned_to: Optional[int] = None
    due_date: Optional[datetime] = None

    _due = field_validator("due_date", mode="before")(_coerce_date_only)
    _ints = field_validator("dept_id", "assigned_to",
                            mode="before")(_coerce_optional_int)


class TaskStatusUpdate(BaseModel):
    """What an employee is allowed to change on their own task."""
    status: str


class TaskOut(BaseModel):
    id: int
    title: str
    description: Optional[str] = None
    source: str
    status: str
    priority: str

    github_repo: Optional[str] = None
    github_issue_number: Optional[int] = None
    github_url: Optional[str] = None
    github_state: Optional[str] = None
    github_labels: Optional[str] = None

    dept_id: Optional[int] = None
    dept_name: Optional[str] = None
    assigned_to: Optional[int] = None
    assignee_name: Optional[str] = None
    created_by: Optional[int] = None

    due_date: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


# ─── Comments ─────────────────────────────────────────────────────────────────

class CommentCreate(BaseModel):
    body: str = Field(..., min_length=1, max_length=5000)


class CommentOut(BaseModel):
    id: int
    task_id: int
    user_id: Optional[int] = None
    author_name: Optional[str] = None
    body: str
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


# ─── GitHub repo config ───────────────────────────────────────────────────────

class GitHubRepoCreate(BaseModel):
    full_name: str = Field(..., description="owner/repo, e.g. gridsphere/biometric")
    token: Optional[str] = Field(None, description="PAT with read+write access. Stored encrypted.")
    webhook_secret: Optional[str] = Field(None, description="Shared secret for webhook signatures.")
    label_filter: Optional[str] = Field(None, description="Comma-separated; only these labels sync.")
    is_default: bool = Field(False, description="Send every new task here unless told otherwise.")
    default_assignee_id: Optional[int] = Field(
        None, description="Assigned on issues whose task has no assignee.")


class TaskPushRequest(BaseModel):
    """Push an already-created local task to GitHub."""
    github_repo_id: Optional[int] = Field(
        None, description="Target repo. Omitted means the tenant's default.")


class GitHubUsernameUpdate(BaseModel):
    """Maps an app user onto a GitHub login so assignment can be mirrored."""
    github_username: Optional[str] = Field(None, max_length=100)


class GitHubRepoUpdate(BaseModel):
    token: Optional[str] = None
    webhook_secret: Optional[str] = None
    label_filter: Optional[str] = None
    is_active: Optional[bool] = None
    is_default: Optional[bool] = None
    default_assignee_id: Optional[int] = None


class GitHubRepoOut(BaseModel):
    """Deliberately has no token field — secrets never travel back to a client."""
    id: int
    full_name: str
    is_active: bool
    label_filter: Optional[str] = None
    is_default: bool = False
    default_assignee_id: Optional[int] = None
    default_assignee_name: Optional[str] = None
    has_token: bool = False
    has_webhook_secret: bool = False
    last_synced_at: Optional[datetime] = None
    last_sync_error: Optional[str] = None
    task_count: int = 0
    created_at: Optional[datetime] = None
