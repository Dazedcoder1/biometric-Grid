"""
sync models with db

Revision ID: a25931c81391
Revises: 3486e68d0e91
Create Date: 2026-04-16
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers
revision: str = 'a25931c81391'
down_revision: Union[str, Sequence[str], None] = '3486e68d0e91'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# =========================
# UPGRADE
# =========================

def upgrade() -> None:
    """Upgrade schema safely (NO DATA LOSS)"""

    # =========================
    # ADMIN USERS FIX
    # =========================
    op.alter_column('admin_users', 'username',
        existing_type=sa.TEXT(),
        type_=sa.String(),
        existing_nullable=False
    )

    op.alter_column('admin_users', 'password',
        existing_type=sa.TEXT(),
        type_=sa.String(),
        existing_nullable=False
    )

    op.alter_column('admin_users', 'api_token',
        existing_type=sa.TEXT(),
        type_=sa.String(),
        nullable=False
    )

    op.create_index('ix_admin_users_api_token', 'admin_users', ['api_token'], unique=True)
    op.create_index('ix_admin_users_id', 'admin_users', ['id'])
    op.create_index('ix_admin_users_username', 'admin_users', ['username'], unique=True)

    # =========================
    # ATTENDANCE LOG UPDATE (CRITICAL)
    # =========================
    op.add_column(
        'attendance_logs',
        sa.Column('user_id', sa.Integer(), nullable=True)
    )

    op.create_foreign_key(
        'fk_attendance_user',
        'attendance_logs',
        'users',
        ['user_id'],
        ['id']
    )

    # =========================
    # USERS TABLE INDEX FIX
    # =========================
    op.create_index(
        'ix_tenant_employee_code',
        'users',
        ['tenant_id', 'employee_code'],
        unique=True
    )

    op.create_index(
        'ix_tenant_finger',
        'users',
        ['tenant_id', 'finger_id'],
        unique=True
    )

    op.create_index('ix_users_employee_code', 'users', ['employee_code'])
    op.create_index('ix_users_id', 'users', ['id'])

    # =========================
    # DEVICES INDEX FIX
    # =========================
    op.create_index(
        'ix_tenant_device',
        'devices',
        ['tenant_id', 'device_id'],
        unique=True
    )

    op.create_index('ix_devices_device_id', 'devices', ['device_id'])
    op.create_index('ix_devices_id', 'devices', ['id'])

    # =========================
    # TENANTS INDEX FIX
    # =========================
    op.create_index('ix_tenants_api_key', 'tenants', ['api_key'], unique=True)
    op.create_index('ix_tenants_id', 'tenants', ['id'])

    # =========================
    # COMMANDS INDEX FIX
    # =========================
    op.create_index('ix_commands_id', 'commands', ['id'])


# =========================
# DOWNGRADE
# =========================

def downgrade() -> None:
    """Rollback safely"""

    # Remove indexes
    op.drop_index('ix_commands_id', table_name='commands')

    op.drop_index('ix_tenants_id', table_name='tenants')
    op.drop_index('ix_tenants_api_key', table_name='tenants')

    op.drop_index('ix_devices_id', table_name='devices')
    op.drop_index('ix_devices_device_id', table_name='devices')
    op.drop_index('ix_tenant_device', table_name='devices')

    op.drop_index('ix_users_id', table_name='users')
    op.drop_index('ix_users_employee_code', table_name='users')
    op.drop_index('ix_tenant_finger', table_name='users')
    op.drop_index('ix_tenant_employee_code', table_name='users')

    op.drop_constraint('fk_attendance_user', 'attendance_logs', type_='foreignkey')
    op.drop_column('attendance_logs', 'user_id')

    op.drop_index('ix_admin_users_username', table_name='admin_users')
    op.drop_index('ix_admin_users_id', table_name='admin_users')
    op.drop_index('ix_admin_users_api_token', table_name='admin_users')