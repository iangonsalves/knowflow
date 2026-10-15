"""Workspace-scoped PDF upload, metadata, content and deletion API."""

from collections.abc import Iterator
from typing import Annotated
from urllib.parse import quote
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
    status,
)
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_session
from app.documents.schemas import DocumentResponse
from app.documents.service import (
    get_document,
    get_document_record,
    list_documents,
    mark_document_deleted,
    retry_document_processing,
    upload_document,
)
from app.documents.storage import (
    ObjectStorage,
    ObjectStorageError,
    StoredObjectNotFound,
    get_object_storage,
)
from app.documents.validation import validate_declared_request_size, validate_pdf_upload
from app.identity.dependencies import CurrentUser
from app.jobs.worker import wake_in_process_worker
from app.tenancy.policies import require_owner, require_workspace_access

router = APIRouter(prefix="/workspaces/{workspace_id}/documents", tags=["documents"])
SessionDep = Annotated[Session, Depends(get_session)]
StorageDep = Annotated[ObjectStorage, Depends(get_object_storage)]


@router.get("", response_model=list[DocumentResponse])
def read_documents(
    workspace_id: UUID,
    current_user: CurrentUser,
    session: SessionDep,
    knowledge_area_id: Annotated[UUID | None, Query()] = None,
) -> list[DocumentResponse]:
    access = require_workspace_access(session, current_user, workspace_id)
    return list_documents(session, access, knowledge_area_id)


@router.post("", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
def post_document(
    workspace_id: UUID,
    request: Request,
    current_user: CurrentUser,
    session: SessionDep,
    storage: StorageDep,
    knowledge_area_id: Annotated[UUID, Form()],
    file: Annotated[UploadFile, File()],
) -> DocumentResponse:
    access = require_workspace_access(session, current_user, workspace_id)
    require_owner(access)
    settings = get_settings()
    validate_declared_request_size(request.headers.get("content-length"), settings)
    validated_pdf = validate_pdf_upload(file, settings)
    response = upload_document(session, access, knowledge_area_id, file, validated_pdf, storage)
    wake_in_process_worker()
    return response


@router.get("/{document_id}", response_model=DocumentResponse)
def read_document(
    workspace_id: UUID,
    document_id: UUID,
    current_user: CurrentUser,
    session: SessionDep,
) -> DocumentResponse:
    access = require_workspace_access(session, current_user, workspace_id)
    return get_document(session, access, document_id)


@router.post("/{document_id}/retry", response_model=DocumentResponse)
def post_document_retry(
    workspace_id: UUID,
    document_id: UUID,
    current_user: CurrentUser,
    session: SessionDep,
) -> DocumentResponse:
    access = require_workspace_access(session, current_user, workspace_id)
    response = retry_document_processing(session, access, document_id)
    wake_in_process_worker()
    return response


@router.get("/{document_id}/content")
def read_document_content(
    workspace_id: UUID,
    document_id: UUID,
    current_user: CurrentUser,
    session: SessionDep,
    storage: StorageDep,
    download: bool = Query(default=False),
) -> StreamingResponse:
    access = require_workspace_access(session, current_user, workspace_id)
    document = get_document_record(session, access, document_id)
    try:
        body, content_length = storage.get_file(document.storage_key)
    except (StoredObjectNotFound, ObjectStorageError) as error:
        raise storage_unavailable() from error

    def stream() -> Iterator[bytes]:
        try:
            while chunk := body.read(64 * 1024):
                yield chunk
        finally:
            body.close()

    disposition = "attachment" if download else "inline"
    encoded_filename = quote(document.original_filename.encode("utf-8"), safe="!#$&+-.^_`|~")
    fallback_filename = document.original_filename.encode("ascii", "ignore").decode("ascii")
    if not fallback_filename or any(character in fallback_filename for character in '"\\\r\n'):
        fallback_filename = "document.pdf"
    headers = {
        "Content-Length": str(content_length),
        "Content-Disposition": (
            f"{disposition}; filename=\"{fallback_filename}\"; filename*=UTF-8''{encoded_filename}"
        ),
        "Cache-Control": "private, no-store",
        "X-Content-Type-Options": "nosniff",
    }
    return StreamingResponse(stream(), media_type="application/pdf", headers=headers)


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(
    workspace_id: UUID,
    document_id: UUID,
    current_user: CurrentUser,
    session: SessionDep,
    storage: StorageDep,
) -> Response:
    access = require_workspace_access(session, current_user, workspace_id)
    mark_document_deleted(session, access, document_id, storage)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def storage_unavailable() -> HTTPException:
    return HTTPException(
        status_code=503,
        detail={
            "code": "document_storage_unavailable",
            "message": "The document is temporarily unavailable",
        },
    )
