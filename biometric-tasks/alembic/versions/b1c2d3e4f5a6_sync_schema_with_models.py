"""sync schema with models (departments, leaves, holidays, notifications, settings, refresh_tokens, user columns)

The migration chain had fallen a long way behind app/models/domain.py:

  * migrated tables : tenants, users, devices, attendance_logs, commands, admin_users
  * model tables    : the above plus departments, refresh_tokens, holidays,
                      leaves, notifications, settings
  * users           : migrated with 4 columns, the model declares 11

Schema was evidently being created by some other means (see scratch/sync_db.py),
so nothing depended on the chain being correct until a migration finally
referenced departments.department_id with a foreign key.

This migration reconciles the two by inspecting the live database and creating
only what is actually missing, which makes it safe on a fresh database and on
one already built by hand. Task-manager tables are excluded — the next
migration owns those.

Revision ID: b1c2d3e4f5a6
Revises: 90405d9757e0
Create Date: 2026-09-07

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import context, op


revision: str = 'b1c2d3e4f5a6'
down_revision: Union[str, Sequence[str], None] = '90405d9757e0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Owned by the following migration, so skipped here.
TASK_TABLES = {"tasks", "task_comments", "github_repos"}

# Created in dependency order — departments before anything referencing it.
ORDERED_TABLES = [
    "tenants",
    "departments",
    "users",
    "devices",
    "attendance_logs",
    "commands",
    "refresh_tokens",
    "holidays",
    "leaves",
    "notifications",
    "settings",
]


def upgrade() -> None:
    from app.models.domain import Base

    if context.is_offline_mode():
        raise RuntimeError(
            "b1c2d3e4f5a6 reconciles drift by inspecting the live database, so it "
            "cannot generate offline SQL (--sql). Run it online against the target "
            "database instead."
        )

    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_tables = set(inspector.get_table_names())

    metadata = Base.metadata

    # ─── 1. Create whole tables that are missing ──────────────────────────────
    for name in ORDERED_TABLES:
        if name in TASK_TABLES or name in existing_tables:
            continue
        table = metadata.tables.get(name)
        if table is None:
            continue
        table.create(bind=conn)
        print(f"  created table: {name}")

    # ─── 2. Add columns missing from tables that already exist ────────────────
    inspector = sa.inspect(conn)  # refresh after the creates above
    for name in ORDERED_TABLES:
        if name in TASK_TABLES or name not in set(inspector.get_table_names()):
            continue
        table = metadata.tables.get(name)
        if table is None:
            continue

        present = {c["name"] for c in inspector.get_columns(name)}
        for column in table.columns:
            if column.name in present:
                continue

            # Added nullable regardless of the model, because existing rows
            # have no value for them. The model still enforces its own
            # constraints at the application layer.
            new_col = sa.Column(
                column.name,
                column.type,
                nullable=True,
                server_default=column.server_default,
            )
            op.add_column(name, new_col)
            print(f"  added column: {name}.{column.name}")

    # ─── 3. Relax NOT NULL where the model says the column is optional ────────
    #
    # The old migrations declared several columns NOT NULL that the models
    # since made optional — users.finger_id is the one that bites immediately,
    # because an employee created through the admin UI has no fingerprint
    # enrolled yet, so the INSERT fails outright.
    inspector = sa.inspect(conn)
    for name in ORDERED_TABLES:
        if name in TASK_TABLES or name not in set(inspector.get_table_names()):
            continue
        table = metadata.tables.get(name)
        if table is None:
            continue

        pk_cols = set(inspector.get_pk_constraint(name).get("constrained_columns") or [])
        db_cols = {c["name"]: c for c in inspector.get_columns(name)}

        for column in table.columns:
            db_col = db_cols.get(column.name)
            if db_col is None or column.name in pk_cols:
                continue
            # DB enforces NOT NULL but the model allows null -> relax it.
            if not db_col["nullable"] and column.nullable:
                with op.batch_alter_table(name) as batch:
                    batch.alter_column(
                        column.name,
                        existing_type=column.type,
                        nullable=True,
                    )
                print(f"  relaxed NOT NULL: {name}.{column.name}")


def downgrade() -> None:
    # Intentionally not reversible. This migration reconciles drift rather than
    # making a single deliberate change, so dropping the tables it created
    # could destroy data the chain never knew about.
    raise NotImplementedError(
        "b1c2d3e4f5a6 reconciles pre-existing schema drift and cannot be "
        "safely reversed. Restore from a backup instead."
    )
