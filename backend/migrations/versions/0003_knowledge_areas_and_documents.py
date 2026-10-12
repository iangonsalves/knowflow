"""Add workspace-scoped knowledge areas and PDF document metadata."""

import sqlalchemy as sa
from alembic import op

revision = "0003_areas_documents"
down_revision = "0002_identity_and_tenancy"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "knowledge_areas",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("normalized_name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("length(trim(name)) > 0", name="ck_knowledge_areas_name_nonempty"),
        sa.CheckConstraint(
            "normalized_name = lower(trim(name))", name="ck_knowledge_areas_normalized_name"
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_knowledge_areas_created_by_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_knowledge_areas_workspace_id_workspaces"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_knowledge_areas")),
        sa.UniqueConstraint("workspace_id", "id", name="uq_knowledge_areas_workspace_id_id"),
        sa.UniqueConstraint(
            "workspace_id", "normalized_name", name="uq_knowledge_areas_workspace_name"
        ),
    )
    op.create_index(
        "ix_knowledge_areas_workspace_name", "knowledge_areas", ["workspace_id", "name"]
    )

    op.create_table(
        "documents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("knowledge_area_id", sa.Uuid(), nullable=False),
        sa.Column("uploaded_by", sa.Uuid(), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("storage_key", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=100), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("page_count", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cleanup_completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cleanup_error_code", sa.String(length=64), nullable=True),
        sa.Column("purge_after", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "content_type = 'application/pdf'", name="ck_documents_content_type_pdf"
        ),
        sa.CheckConstraint("byte_size > 0", name="ck_documents_byte_size_positive"),
        sa.CheckConstraint("page_count > 0", name="ck_documents_page_count_positive"),
        sa.CheckConstraint(
            "status IN ('UPLOADED', 'PROCESSING', 'READY', 'FAILED', 'DELETING')",
            name="ck_documents_status",
        ),
        sa.CheckConstraint("length(sha256) = 64", name="ck_documents_sha256_length"),
        sa.CheckConstraint(
            "purge_after IS NULL OR cleanup_completed_at IS NOT NULL",
            name="ck_documents_purge_after_cleanup",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_documents_workspace_id_workspaces"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["uploaded_by"],
            ["users.id"],
            name=op.f("fk_documents_uploaded_by_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "knowledge_area_id"],
            ["knowledge_areas.workspace_id", "knowledge_areas.id"],
            name="fk_documents_workspace_area",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_documents")),
        sa.UniqueConstraint("storage_key", name="uq_documents_storage_key"),
        sa.UniqueConstraint("workspace_id", "id", name="uq_documents_workspace_id_id"),
    )
    op.create_index(
        "ix_documents_workspace_area_created",
        "documents",
        ["workspace_id", "knowledge_area_id", "created_at"],
    )
    op.create_index("ix_documents_workspace_created", "documents", ["workspace_id", "created_at"])
    op.create_index("ix_documents_purge_after", "documents", ["purge_after"])


def downgrade() -> None:
    op.drop_index("ix_documents_purge_after", table_name="documents")
    op.drop_index("ix_documents_workspace_created", table_name="documents")
    op.drop_index("ix_documents_workspace_area_created", table_name="documents")
    op.drop_table("documents")
    op.drop_index("ix_knowledge_areas_workspace_name", table_name="knowledge_areas")
    op.drop_table("knowledge_areas")
