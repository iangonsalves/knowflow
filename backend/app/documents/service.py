"""Document metadata use cases and lifecycle transitions."""

import logging
from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi import HTTPException, UploadFile
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import (
    Document,
    DocumentChunk,
    DocumentPage,
    DocumentStatus,
    KnowledgeArea,
    ProcessingJob,
    ProcessingJobStatus,
)
from app.documents.lifecycle import (
    cleanup_retry_expired,
    mark_cleanup_complete,
    purge_expired_tombstones,
)
from app.documents.schemas import DocumentResponse
from app.documents.storage import ObjectStorage, ObjectStorageError
from app.documents.validation import ValidatedPDF
from app.tenancy.policies import WorkspaceAccess, require_owner

logger = logging.getLogger(__name__)


def list_documents(
    session: Session,
    access: WorkspaceAccess,
    knowledge_area_id: UUID | None = None,
) -> list[DocumentResponse]:
    purge_expired_tombstones(session, access.workspace.id)
    statement = select(Document).where(
        Document.workspace_id == access.workspace.id,
        Document.deleted_at.is_(None),
    )
    if knowledge_area_id is not None:
        area = session.scalar(
            select(KnowledgeArea.id).where(
                KnowledgeArea.workspace_id == access.workspace.id,
                KnowledgeArea.id == knowledge_area_id,
            )
        )
        if area is None:
            raise knowledge_area_not_found()
        statement = statement.where(Document.knowledge_area_id == knowledge_area_id)
    statement = statement.order_by(Document.created_at.desc(), Document.id)
    return [DocumentResponse.model_validate(row) for row in session.scalars(statement).all()]


def get_document(session: Session, access: WorkspaceAccess, document_id: UUID) -> DocumentResponse:
    document = get_document_record(session, access, document_id)
    return DocumentResponse.model_validate(document)


def get_document_record(session: Session, access: WorkspaceAccess, document_id: UUID) -> Document:
    return _find_active_document(session, access.workspace.id, document_id)


def retry_document_processing(
    session: Session, access: WorkspaceAccess, document_id: UUID
) -> DocumentResponse:
    require_owner(access)
    document = _find_active_document(session, access.workspace.id, document_id)
    if document.status != DocumentStatus.FAILED.value:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "document_not_failed",
                "message": "Only failed document processing can be retried",
            },
        )
    job = session.scalar(
        select(ProcessingJob).where(
            ProcessingJob.workspace_id == access.workspace.id,
            ProcessingJob.document_id == document.id,
        )
    )
    if job is None or job.status not in {
        ProcessingJobStatus.PERMANENT_FAILURE.value,
        ProcessingJobStatus.RETRYABLE_FAILURE.value,
    }:
        raise HTTPException(
            status_code=409,
            detail={"code": "processing_job_unavailable", "message": "The job cannot be retried"},
        )

    session.execute(
        delete(DocumentChunk).where(
            DocumentChunk.workspace_id == access.workspace.id,
            DocumentChunk.document_id == document.id,
        )
    )
    session.execute(
        delete(DocumentPage).where(
            DocumentPage.workspace_id == access.workspace.id,
            DocumentPage.document_id == document.id,
        )
    )
    now = datetime.now(UTC)
    job.status = ProcessingJobStatus.QUEUED.value
    job.attempt_count = 0
    job.max_attempts = get_settings().worker_max_attempts
    job.available_at = now
    job.locked_at = None
    job.locked_by = None
    job.lease_token = None
    job.last_error_code = None
    job.last_error_message = None
    job.finished_at = None
    document.status = DocumentStatus.UPLOADED.value
    document.processing_error_code = None
    document.processing_error_message = None
    session.commit()
    session.refresh(document)
    return DocumentResponse.model_validate(document)


def upload_document(
    session: Session,
    access: WorkspaceAccess,
    knowledge_area_id: UUID,
    upload: UploadFile,
    validated_pdf: ValidatedPDF,
    storage: ObjectStorage,
) -> DocumentResponse:
    require_owner(access)
    area = session.scalar(
        select(KnowledgeArea.id).where(
            KnowledgeArea.workspace_id == access.workspace.id,
            KnowledgeArea.id == knowledge_area_id,
        )
    )
    if area is None:
        raise knowledge_area_not_found()

    document_id = uuid4()
    storage_key = f"documents/{uuid4().hex}.pdf"
    upload.file.seek(0)
    try:
        storage.put_file(
            storage_key,
            upload.file,
            validated_pdf.byte_size,
            validated_pdf.sha256,
            "application/pdf",
        )
    except ObjectStorageError as error:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "document_storage_unavailable",
                "message": "The document could not be stored; try again shortly",
            },
        ) from error

    document = Document(
        id=document_id,
        workspace_id=access.workspace.id,
        knowledge_area_id=knowledge_area_id,
        uploaded_by=access.actor_user_id,
        original_filename=validated_pdf.filename,
        storage_key=storage_key,
        content_type="application/pdf",
        byte_size=validated_pdf.byte_size,
        page_count=validated_pdf.page_count,
        sha256=validated_pdf.sha256,
        status=DocumentStatus.UPLOADED.value,
    )
    settings = get_settings()
    job = ProcessingJob(
        workspace_id=access.workspace.id,
        document_id=document.id,
        job_type="PROCESS_DOCUMENT",
        status=ProcessingJobStatus.QUEUED.value,
        attempt_count=0,
        max_attempts=settings.worker_max_attempts,
    )
    session.add_all([document, job])
    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        _compensate_storage_write(storage, storage_key)
        raise knowledge_area_not_found() from error
    except Exception:
        session.rollback()
        _compensate_storage_write(storage, storage_key)
        raise
    session.refresh(document)
    return DocumentResponse.model_validate(document)


def mark_document_deleted(
    session: Session,
    access: WorkspaceAccess,
    document_id: UUID,
    storage: ObjectStorage,
) -> None:
    require_owner(access)
    document = session.scalar(
        select(Document).where(
            Document.workspace_id == access.workspace.id,
            Document.id == document_id,
        )
    )
    if document is None:
        raise document_not_found()

    if document.deleted_at is None:
        document.deleted_at = datetime.now(UTC)
        document.status = DocumentStatus.DELETING.value
        document.processing_error_code = None
        document.processing_error_message = None
        job = session.scalar(
            select(ProcessingJob).where(
                ProcessingJob.workspace_id == access.workspace.id,
                ProcessingJob.document_id == document.id,
            )
        )
        if job is not None and job.status not in {
            ProcessingJobStatus.SUCCEEDED.value,
            ProcessingJobStatus.CANCELLED.value,
        }:
            job.status = ProcessingJobStatus.CANCELLED.value
            job.locked_at = None
            job.locked_by = None
            job.lease_token = None
            job.finished_at = datetime.now(UTC)
        session.execute(
            delete(DocumentChunk).where(
                DocumentChunk.workspace_id == access.workspace.id,
                DocumentChunk.document_id == document.id,
            )
        )
        session.execute(
            delete(DocumentPage).where(
                DocumentPage.workspace_id == access.workspace.id,
                DocumentPage.document_id == document.id,
            )
        )
        session.commit()
    elif document.cleanup_completed_at is not None:
        return
    elif cleanup_retry_expired(document):
        raise HTTPException(
            status_code=503,
            detail={
                "code": "document_cleanup_requires_attention",
                "message": "Document access is revoked; storage cleanup needs operator attention",
            },
        )

    try:
        storage.delete_file(document.storage_key)
    except ObjectStorageError as error:
        document.cleanup_error_code = "storage_unavailable"
        session.commit()
        raise HTTPException(
            status_code=503,
            detail={
                "code": "document_cleanup_pending",
                "message": "Document access is revoked; physical cleanup will need to be retried",
            },
        ) from error

    mark_cleanup_complete(document)
    session.commit()


def _find_active_document(session: Session, workspace_id: UUID, document_id: UUID) -> Document:
    document = session.scalar(
        select(Document).where(
            Document.workspace_id == workspace_id,
            Document.id == document_id,
            Document.deleted_at.is_(None),
        )
    )
    if document is None:
        raise document_not_found()
    return document


def _compensate_storage_write(storage: ObjectStorage, storage_key: str) -> None:
    try:
        storage.delete_file(storage_key)
    except ObjectStorageError:
        logger.exception(
            "Document upload compensation failed; opaque object key retained for support"
        )


def document_not_found() -> HTTPException:
    return HTTPException(
        status_code=404,
        detail={"code": "document_not_found", "message": "Document not found"},
    )


def knowledge_area_not_found() -> HTTPException:
    return HTTPException(
        status_code=404,
        detail={"code": "knowledge_area_not_found", "message": "Knowledge area not found"},
    )
