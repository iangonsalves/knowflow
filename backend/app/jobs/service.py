"""PostgreSQL-backed job claiming, leasing, retry scheduling, and terminal states."""

import random
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import and_, or_, select, update
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.models import (
    Document,
    DocumentStatus,
    ProcessingJob,
    ProcessingJobStatus,
)
from app.processing.extraction import LeaseLost, ProcessingError


@dataclass(frozen=True)
class ClaimedJob:
    job_id: UUID
    workspace_id: UUID
    document_id: UUID
    lease_token: UUID
    attempt_count: int


def claim_next_job(
    session: Session,
    worker_id: str,
    settings: Settings,
    now: datetime | None = None,
) -> ClaimedJob | None:
    """Claim the oldest eligible row; concurrent PostgreSQL workers skip held rows."""
    now = now or datetime.now(UTC)
    job = lock_next_eligible_job(session, settings, now)
    if job is None:
        session.rollback()
        return None

    document = session.scalar(
        select(Document).where(
            Document.workspace_id == job.workspace_id,
            Document.id == job.document_id,
        )
    )
    if document is None or document.deleted_at:
        _cancel_job(job, now)
        session.commit()
        return None

    if job.attempt_count >= job.max_attempts:
        job.status = ProcessingJobStatus.PERMANENT_FAILURE.value
        job.last_error_code = "worker_lease_expired"
        job.last_error_message = (
            "The worker stopped before processing completed. Retry the document."
        )
        job.finished_at = now
        job.locked_at = None
        job.locked_by = None
        job.lease_token = None
        document.status = DocumentStatus.FAILED.value
        document.processing_error_code = job.last_error_code
        document.processing_error_message = job.last_error_message
        session.commit()
        return None

    token = uuid4()
    job.status = ProcessingJobStatus.RUNNING.value
    job.attempt_count += 1
    job.locked_at = now
    job.locked_by = worker_id
    job.lease_token = token
    job.last_error_code = None
    job.last_error_message = None
    job.finished_at = None
    document.status = DocumentStatus.PROCESSING.value
    document.processing_error_code = None
    document.processing_error_message = None
    session.commit()
    return ClaimedJob(job.id, job.workspace_id, job.document_id, token, job.attempt_count)


def lock_next_eligible_job(
    session: Session,
    settings: Settings,
    now: datetime | None = None,
    workspace_id: UUID | None = None,
) -> ProcessingJob | None:
    """Lock one eligible row without committing; peer workers skip it in PostgreSQL."""
    now = now or datetime.now(UTC)
    lease_expired_before = now - timedelta(seconds=settings.job_lease_seconds)
    eligible = or_(
        and_(
            ProcessingJob.status.in_(
                [ProcessingJobStatus.QUEUED.value, ProcessingJobStatus.RETRYABLE_FAILURE.value]
            ),
            ProcessingJob.available_at <= now,
        ),
        and_(
            ProcessingJob.status == ProcessingJobStatus.RUNNING.value,
            ProcessingJob.locked_at.is_not(None),
            ProcessingJob.locked_at <= lease_expired_before,
        ),
    )
    statement = (
        select(ProcessingJob)
        .join(
            Document,
            and_(
                Document.workspace_id == ProcessingJob.workspace_id,
                Document.id == ProcessingJob.document_id,
            ),
        )
        .where(
            eligible,
            Document.deleted_at.is_(None),
            Document.status.in_([DocumentStatus.UPLOADED.value, DocumentStatus.PROCESSING.value]),
            ProcessingJob.job_type == "PROCESS_DOCUMENT",
        )
        .order_by(ProcessingJob.available_at, ProcessingJob.created_at, ProcessingJob.id)
    )
    if workspace_id is not None:
        statement = statement.where(ProcessingJob.workspace_id == workspace_id)
    return session.scalar(statement.with_for_update(of=ProcessingJob, skip_locked=True).limit(1))


def renew_lease(session: Session, claim: ClaimedJob, now: datetime | None = None) -> None:
    now = now or datetime.now(UTC)
    result = session.execute(
        update(ProcessingJob)
        .where(
            ProcessingJob.id == claim.job_id,
            ProcessingJob.lease_token == claim.lease_token,
            ProcessingJob.status == ProcessingJobStatus.RUNNING.value,
        )
        .values(locked_at=now, updated_at=now)
    )
    session.commit()
    if result.rowcount != 1:
        raise LeaseLost


def record_failure(
    session: Session,
    claim: ClaimedJob,
    error: ProcessingError,
    settings: Settings,
    now: datetime | None = None,
) -> None:
    now = now or datetime.now(UTC)
    job = session.scalar(
        select(ProcessingJob)
        .where(
            ProcessingJob.id == claim.job_id,
            ProcessingJob.lease_token == claim.lease_token,
            ProcessingJob.status == ProcessingJobStatus.RUNNING.value,
        )
        .with_for_update()
    )
    if job is None:
        session.rollback()
        return
    document = session.scalar(
        select(Document).where(
            Document.workspace_id == claim.workspace_id,
            Document.id == claim.document_id,
        )
    )
    if document is None or document.deleted_at is not None:
        _cancel_job(job, now)
    else:
        job.last_error_code = error.code
        job.last_error_message = error.safe_message
        job.locked_at = None
        job.locked_by = None
        job.lease_token = None
        document.processing_error_code = error.code
        document.processing_error_message = error.safe_message
        backoffs = settings.worker_retry_backoff_seconds
        if error.retryable and job.attempt_count < job.max_attempts:
            base_delay = backoffs[min(job.attempt_count - 1, len(backoffs) - 1)]
            delay = max(1, int(base_delay * random.uniform(0.9, 1.1)))
            job.status = ProcessingJobStatus.RETRYABLE_FAILURE.value
            job.available_at = now + timedelta(seconds=delay)
            document.status = DocumentStatus.PROCESSING.value
            job.finished_at = None
        else:
            job.status = ProcessingJobStatus.PERMANENT_FAILURE.value
            document.status = DocumentStatus.FAILED.value
            job.finished_at = now
    session.commit()


def _cancel_job(job: ProcessingJob, now: datetime) -> None:
    job.status = ProcessingJobStatus.CANCELLED.value
    job.locked_at = None
    job.locked_by = None
    job.lease_token = None
    job.finished_at = now
