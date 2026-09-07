"""add github write-back columns (users.github_username, task_comments.github_comment_id)

Two-way sync needs two things the read-only mirror did not:

  * users.github_username — GitHub cannot resolve our users, so mirroring
    assignment onto an issue requires a hand-entered login per user.
  * task_comments.github_comment_id — records the id GitHub returned, which
    both proves the comment was mirrored and marks it as ours so an inbound
    issue_comment event is never re-imported as a duplicate.

Revision ID: c2d3e4f5a6b7
Revises: a1b2c3d4e5f6
Create Date: 2026-09-07

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import context, op


revision: str = 'c2d3e4f5a6b7'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()

    # Offline (--sql) has no connection to inspect; emit unconditionally there.
    offline = context.is_offline_mode()
    inspector = None if offline else sa.inspect(conn)

    user_cols = set() if offline else {c["name"] for c in inspector.get_columns("users")}
    if "github_username" not in user_cols:
        op.add_column("users", sa.Column("github_username", sa.String(), nullable=True))

    comment_cols = set() if offline else {
        c["name"] for c in inspector.get_columns("task_comments")
    }
    if "github_comment_id" not in comment_cols:
        op.add_column(
            "task_comments", sa.Column("github_comment_id", sa.Integer(), nullable=True)
        )


def downgrade() -> None:
    op.drop_column("task_comments", "github_comment_id")
    op.drop_column("users", "github_username")
