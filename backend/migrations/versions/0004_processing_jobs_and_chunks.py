"""Add durable processing jobs, extracted pages, and deterministic chunks."""

import sqlalchemy as sa
from alembic import op

revision = "0004_processing_jobs_chunks"
down_revision = "0003_areas_documents"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("documents", sa.Column("processing_error_code", sa.String(64), nullable=True))
    op.add_column("documents", sa.Column("processing_error_message", sa.String(500), nullable=True))
    op.create_check_constraint(
        "ck_documents_processing_error_code",
        "documents",
        "processing_error_code IS NULL OR length(processing_error_code) > 0",
    )

    op.create_table(
        "processing_jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("job_type", sa.String(32), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column(
            "available_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("locked_by", sa.String(128), nullable=True),
        sa.Column("lease_token", sa.Uuid(), nullable=True),
        sa.Column("last_error_code", sa.String(64), nullable=True),
        sa.Column("last_error_message", sa.String(500), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("attempt_count >= 0", name="ck_jobs_attempt_count_nonnegative"),
        sa.CheckConstraint("max_attempts > 0", name="ck_jobs_max_attempts_positive"),
        sa.CheckConstraint(
            "status IN ('QUEUED', 'RUNNING', 'RETRYABLE_FAILURE', 'PERMANENT_FAILURE', "
            "'SUCCEEDED', 'CANCELLED')",
            name="ck_jobs_status",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "document_id"],
            ["documents.workspace_id", "documents.id"],
            name="fk_jobs_workspace_document",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_processing_jobs")),
        sa.UniqueConstraint("workspace_id", "document_id", name="uq_job_per_document"),
    )
    op.create_index("ix_jobs_claim", "processing_jobs", ["status", "available_at", "created_at"])
    op.create_index("ix_jobs_lease", "processing_jobs", ["status", "locked_at"])

    # M3 documents already exist without a processing job; enqueue eligible originals on upgrade.
    op.execute(
        """
        INSERT INTO processing_jobs (
            id, workspace_id, document_id, job_type, status, attempt_count, max_attempts,
            available_at, created_at, updated_at
        )
        SELECT gen_random_uuid(), workspace_id, id, 'PROCESS_DOCUMENT', 'QUEUED', 0, 4,
               now(), now(), now()
        FROM documents
        WHERE deleted_at IS NULL AND status = 'UPLOADED'
        """
    )

    op.create_table(
        "document_pages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("page_number > 0", name="ck_pages_page_number_positive"),
        sa.ForeignKeyConstraint(
            ["workspace_id", "document_id"],
            ["documents.workspace_id", "documents.id"],
            name="fk_pages_workspace_document",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_document_pages")),
        sa.UniqueConstraint("document_id", "page_number", name="uq_pages_document_page"),
    )
    op.create_index(
        "ix_pages_workspace_document",
        "document_pages",
        ["workspace_id", "document_id", "page_number"],
    )

    op.create_table(
        "document_chunks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("page_start", sa.Integer(), nullable=False),
        sa.Column("page_end", sa.Integer(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=True),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("chunk_index >= 0", name="ck_chunks_index_nonnegative"),
        sa.CheckConstraint("page_start > 0", name="ck_chunks_page_start_positive"),
        sa.CheckConstraint("page_end >= page_start", name="ck_chunks_page_range"),
        sa.CheckConstraint("token_count IS NULL OR token_count >= 0", name="ck_chunks_token_count"),
        sa.ForeignKeyConstraint(
            ["workspace_id", "document_id"],
            ["documents.workspace_id", "documents.id"],
            name="fk_chunks_workspace_document",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_document_chunks")),
        sa.UniqueConstraint("workspace_id", "document_id", "chunk_index", name="uq_chunks_order"),
    )
    op.create_index(
        "ix_chunks_workspace_document_order",
        "document_chunks",
        ["workspace_id", "document_id", "chunk_index"],
    )


def downgrade() -> None:
    op.drop_index("ix_chunks_workspace_document_order", table_name="document_chunks")
    op.drop_table("document_chunks")
    op.drop_index("ix_pages_workspace_document", table_name="document_pages")
    op.drop_table("document_pages")
    op.drop_index("ix_jobs_lease", table_name="processing_jobs")
    op.drop_index("ix_jobs_claim", table_name="processing_jobs")
    op.drop_table("processing_jobs")
    op.drop_constraint("ck_documents_processing_error_code", "documents", type_="check")
    op.drop_column("documents", "processing_error_message")
    op.drop_column("documents", "processing_error_code")
