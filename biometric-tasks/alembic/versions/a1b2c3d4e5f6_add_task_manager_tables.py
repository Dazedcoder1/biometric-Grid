"""add task manager tables (tasks, task_comments, github_repos)

Ports the standalone task-manager schema into the multi-tenant model:
  - its `teams` become this project's existing `departments`
  - its `users` become this project's existing `users`
  - task/comment tables gain a tenant_id and are scoped accordingly

Revision ID: a1b2c3d4e5f6
Revises: b1c2d3e4f5a6
Create Date: 2026-09-07

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = 'b1c2d3e4f5a6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ─── github_repos ─────────────────────────────────────────────────────────
    op.create_table(
        'github_repos',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=False),
        sa.Column('full_name', sa.String(), nullable=False),
        sa.Column('token_encrypted', sa.Text(), nullable=True),
        sa.Column('webhook_secret_encrypted', sa.Text(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('label_filter', sa.String(), nullable=True),
        sa.Column('last_synced_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_sync_error', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tenant_id', 'full_name', name='uix_tenant_github_repo'),
    )
    op.create_index(op.f('ix_github_repos_id'), 'github_repos', ['id'])
    op.create_index(op.f('ix_github_repos_tenant_id'), 'github_repos', ['tenant_id'])

    # ─── tasks ────────────────────────────────────────────────────────────────
    op.create_table(
        'tasks',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('source', sa.String(), nullable=False, server_default='manual'),
        sa.Column('status', sa.String(), nullable=False, server_default='todo'),
        sa.Column('priority', sa.String(), nullable=False, server_default='medium'),
        sa.Column('github_repo_id', sa.Integer(), nullable=True),
        sa.Column('github_repo', sa.String(), nullable=True),
        sa.Column('github_issue_number', sa.Integer(), nullable=True),
        sa.Column('github_url', sa.String(), nullable=True),
        sa.Column('github_state', sa.String(), nullable=True),
        sa.Column('github_labels', sa.String(), nullable=True),
        sa.Column('github_updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('dept_id', sa.Integer(), nullable=True),
        sa.Column('assigned_to', sa.Integer(), nullable=True),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.Column('due_date', sa.DateTime(), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['github_repo_id'], ['github_repos.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['dept_id'], ['departments.department_id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['assigned_to'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        # Makes webhook delivery idempotent — a redelivered event updates
        # rather than duplicating the task.
        sa.UniqueConstraint('tenant_id', 'github_repo', 'github_issue_number',
                            name='uix_tenant_repo_issue'),
    )
    op.create_index(op.f('ix_tasks_id'), 'tasks', ['id'])
    op.create_index(op.f('ix_tasks_tenant_id'), 'tasks', ['tenant_id'])
    op.create_index(op.f('ix_tasks_assigned_to'), 'tasks', ['assigned_to'])
    op.create_index('ix_task_tenant_status', 'tasks', ['tenant_id', 'status'])

    # ─── task_comments ────────────────────────────────────────────────────────
    op.create_table(
        'task_comments',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('task_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('author_name', sa.String(), nullable=True),
        sa.Column('body', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['task_id'], ['tasks.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_task_comments_id'), 'task_comments', ['id'])
    op.create_index(op.f('ix_task_comments_task_id'), 'task_comments', ['task_id'])


def downgrade() -> None:
    op.drop_index(op.f('ix_task_comments_task_id'), table_name='task_comments')
    op.drop_index(op.f('ix_task_comments_id'), table_name='task_comments')
    op.drop_table('task_comments')

    op.drop_index('ix_task_tenant_status', table_name='tasks')
    op.drop_index(op.f('ix_tasks_assigned_to'), table_name='tasks')
    op.drop_index(op.f('ix_tasks_tenant_id'), table_name='tasks')
    op.drop_index(op.f('ix_tasks_id'), table_name='tasks')
    op.drop_table('tasks')

    op.drop_index(op.f('ix_github_repos_tenant_id'), table_name='github_repos')
    op.drop_index(op.f('ix_github_repos_id'), table_name='github_repos')
    op.drop_table('github_repos')
