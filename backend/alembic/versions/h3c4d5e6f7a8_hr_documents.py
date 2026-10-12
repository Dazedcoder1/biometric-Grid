"""HR documents and letters.

Revision ID: h3c4d5e6f7a8
Revises: g2b3c4d5e6f7

  stored_files                  uploaded bytes (10 MB cap, enforced in the app)
  hr_settings                   letterhead per organisation
  letter_templates (+versions)  offer, appointment, internship, confirmation,
                                promotion, salary revision, experience,
                                relieving — wording kept for every edit
  letters                       a letter to one person: draft -> issued
                                (frozen) -> revoked
  hr_documents (+versions,      policies and the handbook, versioned;
                acks)           acknowledgement recorded per version
  employee_documents (+versions)  a person's file, with expiry dates

Permissions
  documents.view    read everyone's letters and documents, acknowledgement
                    status and access logs
  documents.manage  templates, letterhead, issuing letters, publishing
                    policies, uploading to a person's file

Granted to tenant_admin and hr. super_admin has everything through
grants_all. Org Admins get neither: letters carry salaries.
"""

from alembic import op
import sqlalchemy as sa

revision = "h3c4d5e6f7a8"
down_revision = "g2b3c4d5e6f7"
branch_labels = None
depends_on = None

PERMISSIONS = [
    ("documents.view", "Read everyone's letters and HR documents, acknowledgements and access logs"),
    ("documents.manage", "Manage letter templates and letterhead, issue letters, publish policies and file documents"),
]
GRANTS = [(role, code) for role in ("tenant_admin", "hr") for code, _ in PERMISSIONS]


def _ts(name):
    return sa.Column(name, sa.DateTime(timezone=True), server_default=sa.func.now())


def _fk_user(name):
    return sa.Column(name, sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"))


def _tenant():
    return sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)


def upgrade() -> None:
    op.create_table(
        "stored_files",
        sa.Column("id", sa.Integer(), primary_key=True), _tenant(),
        sa.Column("file_name", sa.String(255), nullable=False),
        sa.Column("content_type", sa.String(100), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("data", sa.LargeBinary(), nullable=False),
        _fk_user("uploaded_by"), _ts("created_at"),
    )
    op.create_index("ix_stored_files_tenant_id", "stored_files", ["tenant_id"])

    op.create_table(
        "hr_settings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("company_name", sa.String(160)), sa.Column("address", sa.Text()),
        sa.Column("contact_line", sa.String(255)), sa.Column("cin", sa.String(32)),
        sa.Column("signatory_name", sa.String(120)), sa.Column("signatory_title", sa.String(120)),
        sa.Column("footer", sa.String(255)), sa.Column("reference_prefix", sa.String(20)),
        _ts("updated_at"),
    )

    op.create_table(
        "letter_templates",
        sa.Column("id", sa.Integer(), primary_key=True), _tenant(),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("subject", sa.String(200), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default="true"),
        _fk_user("updated_by"), _ts("created_at"), _ts("updated_at"),
    )
    op.create_index("ix_letter_templates_tenant_id", "letter_templates", ["tenant_id"])

    op.create_table(
        "letter_template_versions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("template_id", sa.Integer(), sa.ForeignKey("letter_templates.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("subject", sa.String(200), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("note", sa.String(255)),
        _fk_user("created_by"), _ts("created_at"),
        sa.UniqueConstraint("template_id", "version", name="uq_letter_template_version"),
    )
    op.create_index("ix_letter_template_versions_template_id", "letter_template_versions", ["template_id"])

    op.create_table(
        "letters",
        sa.Column("id", sa.Integer(), primary_key=True), _tenant(),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("template_id", sa.Integer(), sa.ForeignKey("letter_templates.id", ondelete="SET NULL")),
        sa.Column("template_version", sa.Integer()),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("subject", sa.String(200), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("fields", sa.JSON()), sa.Column("letterhead", sa.JSON()),
        sa.Column("letter_date", sa.Date(), nullable=False),
        sa.Column("reference_no", sa.String(60)),
        sa.Column("status", sa.String(16), nullable=False, server_default="draft"),
        _fk_user("created_by"), _fk_user("issued_by"),
        sa.Column("issued_at", sa.DateTime(timezone=True)),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True)),
        _fk_user("revoked_by"), sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("revoke_reason", sa.String(255)),
        _ts("created_at"), _ts("updated_at"),
    )
    op.create_index("ix_letters_tenant_id", "letters", ["tenant_id"])
    op.create_index("ix_letters_user_id", "letters", ["user_id"])

    op.create_table(
        "hr_documents",
        sa.Column("id", sa.Integer(), primary_key=True), _tenant(),
        sa.Column("category", sa.String(32), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("requires_ack", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("audience", sa.JSON()),
        sa.Column("review_by", sa.Date()),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("current_version", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_reminded_on", sa.Date()),
        _fk_user("created_by"), _ts("created_at"), _ts("updated_at"),
    )
    op.create_index("ix_hr_documents_tenant_id", "hr_documents", ["tenant_id"])

    op.create_table(
        "hr_document_versions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("document_id", sa.Integer(), sa.ForeignKey("hr_documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("file_id", sa.Integer(), sa.ForeignKey("stored_files.id", ondelete="SET NULL")),
        sa.Column("body", sa.Text()),
        sa.Column("change_note", sa.String(255)),
        _fk_user("published_by"), _ts("published_at"),
        sa.UniqueConstraint("document_id", "version", name="uq_hr_document_version"),
    )
    op.create_index("ix_hr_document_versions_document_id", "hr_document_versions", ["document_id"])

    op.create_table(
        "hr_document_acks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("document_id", sa.Integer(), sa.ForeignKey("hr_documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version_id", sa.Integer(), sa.ForeignKey("hr_document_versions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        _ts("acknowledged_at"),
        sa.Column("source_ip", sa.String(64)),
        sa.UniqueConstraint("version_id", "user_id", name="uq_hr_document_ack"),
    )
    op.create_index("ix_hr_document_ack_doc", "hr_document_acks", ["document_id", "user_id"])

    op.create_table(
        "employee_documents",
        sa.Column("id", sa.Integer(), primary_key=True), _tenant(),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("doc_type", sa.String(32), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("number", sa.String(80)),
        sa.Column("issued_on", sa.Date()), sa.Column("expires_on", sa.Date()),
        sa.Column("current_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("file_id", sa.Integer(), sa.ForeignKey("stored_files.id", ondelete="SET NULL")),
        sa.Column("notes", sa.String(500)),
        sa.Column("reminder_stage", sa.Integer()),
        _fk_user("uploaded_by"), _ts("created_at"), _ts("updated_at"),
    )
    op.create_index("ix_employee_documents_tenant_id", "employee_documents", ["tenant_id"])
    op.create_index("ix_employee_documents_user_id", "employee_documents", ["user_id"])
    op.create_index("ix_employee_documents_expiry", "employee_documents", ["tenant_id", "expires_on"])

    op.create_table(
        "employee_document_versions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("document_id", sa.Integer(), sa.ForeignKey("employee_documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("file_id", sa.Integer(), sa.ForeignKey("stored_files.id", ondelete="SET NULL")),
        sa.Column("number", sa.String(80)),
        sa.Column("issued_on", sa.Date()), sa.Column("expires_on", sa.Date()),
        sa.Column("note", sa.String(255)),
        _fk_user("created_by"), _ts("created_at"),
    )
    op.create_index("ix_employee_document_versions_document_id", "employee_document_versions", ["document_id"])

    conn = op.get_bind()
    for code, description in PERMISSIONS:
        conn.execute(
            sa.text(
                "INSERT INTO permissions (code, description, requires_step_up) "
                "VALUES (:c, :d, false) ON CONFLICT (code) DO UPDATE SET description = EXCLUDED.description"
            ),
            {"c": code, "d": description},
        )
    for role, perm in GRANTS:
        conn.execute(
            sa.text(
                """
                INSERT INTO role_permissions (role_id, permission_id)
                SELECT r.id, p.id FROM roles r, permissions p
                 WHERE r.code = :r AND r.tenant_id IS NULL AND p.code = :p
                ON CONFLICT DO NOTHING
                """
            ),
            {"r": role, "p": perm},
        )


def downgrade() -> None:
    conn = op.get_bind()
    for code, _ in PERMISSIONS:
        conn.execute(sa.text(
            "DELETE FROM role_permissions WHERE permission_id = (SELECT id FROM permissions WHERE code = :p)"
        ), {"p": code})
        conn.execute(sa.text("DELETE FROM permissions WHERE code = :c"), {"c": code})
    for table in ("employee_document_versions", "employee_documents", "hr_document_acks",
                  "hr_document_versions", "hr_documents", "letters", "letter_template_versions",
                  "letter_templates", "hr_settings", "stored_files"):
        op.drop_table(table)
