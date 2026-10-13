"""Add chunk vectors and FTS index; requeue existing documents for embedding."""

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

revision = "0005_embeddings_retrieval"
down_revision = "0004_processing_jobs_chunks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("document_chunks", sa.Column("embedding", Vector(384), nullable=True))
    op.add_column("document_chunks", sa.Column("embedding_model", sa.String(100), nullable=True))
    op.add_column("document_chunks", sa.Column("embedding_version", sa.String(32), nullable=True))
    op.add_column("document_chunks", sa.Column("embedding_dimensions", sa.Integer(), nullable=True))
    op.add_column(
        "document_chunks", sa.Column("embedded_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_check_constraint(
        "ck_chunks_embedding_metadata_consistent",
        "document_chunks",
        "(embedding IS NULL AND embedding_model IS NULL AND embedding_version IS NULL "
        "AND embedding_dimensions IS NULL AND embedded_at IS NULL) OR "
        "(embedding IS NOT NULL AND embedding_model IS NOT NULL AND embedding_version IS NOT NULL "
        "AND embedding_dimensions = 384 AND embedded_at IS NOT NULL)",
    )
    op.create_index(
        "ix_chunks_search_vector",
        "document_chunks",
        [sa.text("to_tsvector('english', text)")],
        postgresql_using="gin",
    )

    # Existing READY rows have M4 text but no embedding. Reuse each document's
    # durable job row and the normal worker pipeline; no provider call runs in DDL.
    op.execute(
        """
        UPDATE documents
        SET status = 'UPLOADED', processing_error_code = NULL, processing_error_message = NULL,
            updated_at = now()
        WHERE deleted_at IS NULL AND status IN ('READY', 'PROCESSING', 'UPLOADED')
        """
    )
    op.execute(
        """
        UPDATE processing_jobs AS jobs
        SET status = 'QUEUED', attempt_count = 0, available_at = now(), locked_at = NULL,
            locked_by = NULL, lease_token = NULL, last_error_code = NULL, last_error_message = NULL,
            finished_at = NULL, updated_at = now()
        FROM documents AS documents
        WHERE jobs.workspace_id = documents.workspace_id
          AND jobs.document_id = documents.id
          AND documents.deleted_at IS NULL
          AND documents.status = 'UPLOADED'
          AND jobs.job_type = 'PROCESS_DOCUMENT'
        """
    )


def downgrade() -> None:
    # Never mark documents READY during rollback: their M5 vector data is removed.
    op.drop_index("ix_chunks_search_vector", table_name="document_chunks")
    op.drop_constraint("ck_chunks_embedding_metadata_consistent", "document_chunks", type_="check")
    op.drop_column("document_chunks", "embedded_at")
    op.drop_column("document_chunks", "embedding_dimensions")
    op.drop_column("document_chunks", "embedding_version")
    op.drop_column("document_chunks", "embedding_model")
    op.drop_column("document_chunks", "embedding")
