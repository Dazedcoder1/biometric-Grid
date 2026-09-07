"""add default repo + default assignee (github_repos.is_default, default_assignee_id)

Lets a tenant nominate one repository that new tasks are pushed to
automatically, so nobody has to pick a repo on every task, plus a fallback
assignee for issues opened from tasks that have nobody assigned.

Revision ID: d3e4f5a6b7c8
Revises: c2d3e4f5a6b7
Create Date: 2026-09-07

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import context, op


revision: str = 'd3e4f5a6b7c8'
down_revision: Union[str, Sequence[str], None] = 'c2d3e4f5a6b7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()

    # Offline (--sql) has no connection to inspect, so emit the DDL
    # unconditionally there and keep the idempotent path for live runs.
    offline = context.is_offline_mode()
    cols = set() if offline else {
        c["name"] for c in sa.inspect(conn).get_columns("github_repos")
    }

    if "is_default" not in cols:
        op.add_column(
            "github_repos",
            sa.Column("is_default", sa.Boolean(), nullable=False,
                      server_default=sa.false()),
        )
    if "default_assignee_id" not in cols:
        op.add_column(
            "github_repos", sa.Column("default_assignee_id", sa.Integer(), nullable=True)
        )
        # SQLite can't add a foreign key to an existing table; Postgres can, and
        # Postgres is what this project runs on.
        if offline or conn.dialect.name != "sqlite":
            op.create_foreign_key(
                "fk_github_repos_default_assignee",
                "github_repos", "users",
                ["default_assignee_id"], ["id"],
                ondelete="SET NULL",
            )


def downgrade() -> None:
    conn = op.get_bind()
    if conn.dialect.name != "sqlite":
        op.drop_constraint("fk_github_repos_default_assignee", "github_repos",
                           type_="foreignkey")
    op.drop_column("github_repos", "default_assignee_id")
    op.drop_column("github_repos", "is_default")
