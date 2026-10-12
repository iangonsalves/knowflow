"""Atomic replacement of page text/chunks and document/job readiness."""

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import (
    Document,
    DocumentChunk,
    DocumentPage,
    DocumentStatus,
    ProcessingJob,
    ProcessingJobStatus,
)
from app.jobs.service import ClaimedJob
from app.processing.chunking import PreparedChunk
from app.processing.extraction import ExtractedPage, LeaseLost


def persist_processed_output(
    session_factory: sessionmaker[Session],
    claim: ClaimedJob,
    pages: list[ExtractedPage],
    chunks: list[PreparedChunk],
) -> bool:
    """Persist all derived output and READY/SUCCEEDED in one transaction."""
    with session_factory() as session, session.begin():
        job = session.scalar(
            select(ProcessingJob)
            .where(
                ProcessingJob.id == claim.job_id,
                ProcessingJob.workspace_id == claim.workspace_id,
                ProcessingJob.document_id == claim.document_id,
                ProcessingJob.lease_token == claim.lease_token,
                ProcessingJob.status == ProcessingJobStatus.RUNNING.value,
            )
            .with_for_update()
        )
        if job is None:
            raise LeaseLost
        document = session.scalar(
            select(Document)
            .where(
                Document.workspace_id == claim.workspace_id,
                Document.id == claim.document_id,
            )
            .with_for_update()
        )
        if document is None or document.deleted_at is not None:
            job.status = ProcessingJobStatus.CANCELLED.value
            job.finished_at = datetime.now(UTC)
            job.locked_at = None
            job.locked_by = None
            job.lease_token = None
            return False

        session.execute(
            delete(DocumentChunk).where(
                DocumentChunk.workspace_id == claim.workspace_id,
                DocumentChunk.document_id == claim.document_id,
            )
        )
        session.execute(
            delete(DocumentPage).where(
                DocumentPage.workspace_id == claim.workspace_id,
                DocumentPage.document_id == claim.document_id,
            )
        )
        session.add_all(
            [
                DocumentPage(
                    id=uuid4(),
                    workspace_id=claim.workspace_id,
                    document_id=claim.document_id,
                    page_number=page.page_number,
                    text=page.text,
                    content_hash=page.content_hash,
                )
                for page in pages
            ]
        )
        session.add_all(
            [
                DocumentChunk(
                    id=uuid4(),
                    workspace_id=claim.workspace_id,
                    document_id=claim.document_id,
                    chunk_index=chunk.chunk_index,
                    text=chunk.text,
                    page_start=chunk.page_start,
                    page_end=chunk.page_end,
                    content_hash=chunk.content_hash,
                )
                for chunk in chunks
            ]
        )
        document.status = DocumentStatus.READY.value
        document.processing_error_code = None
        document.processing_error_message = None
        job.status = ProcessingJobStatus.SUCCEEDED.value
        job.last_error_code = None
        job.last_error_message = None
        job.finished_at = datetime.now(UTC)
        job.locked_at = None
        job.locked_by = None
        job.lease_token = None
    return True
