"""Add settings.min_working_hours.

Revision ID: b7c8d9e0f1a2
Revises: a6b7c8d9e0f1

Every attendance screen displayed "minimum hours required" and every
compliance figure was calculated against it, but no such column existed. The
frontend filled the gap with its own hardcoded 9.0, so the number looked real,
agreed with itself everywhere, and could not be changed — the Settings page had
nowhere to save it.

server_default 9.0 matches the value the UI was already assuming, so existing
tenants see no behavioural change on upgrade; they simply gain the ability to
set it.
"""

from alembic import op
import sqlalchemy as sa

revision = "b7c8d9e0f1a2"
down_revision = "a6b7c8d9e0f1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "settings",
        sa.Column(
            "min_working_hours",
            sa.Float(),
            nullable=False,
            server_default="9.0",
        ),
    )


def downgrade() -> None:
    op.drop_column("settings", "min_working_hours")
