"""Knowledge-area use cases with explicit workspace scope."""

from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import Document, KnowledgeArea
from app.documents.lifecycle import purge_expired_tombstones
from app.knowledge_areas.schemas import (
    KnowledgeAreaCreate,
    KnowledgeAreaResponse,
    KnowledgeAreaUpdate,
)
from app.tenancy.policies import WorkspaceAccess, require_owner


def _area_response(area: KnowledgeArea, document_count: int) -> KnowledgeAreaResponse:
    return KnowledgeAreaResponse(
        id=area.id,
        workspace_id=area.workspace_id,
        name=area.name,
        description=area.description,
        document_count=document_count,
        created_at=area.created_at,
        updated_at=area.updated_at,
    )


def _document_count(session: Session, workspace_id: UUID, area_id: UUID) -> int:
    return int(
        session.scalar(
            select(func.count())
            .select_from(Document)
            .where(
                Document.workspace_id == workspace_id,
                Document.knowledge_area_id == area_id,
            )
        )
        or 0
    )


def list_knowledge_areas(session: Session, access: WorkspaceAccess) -> list[KnowledgeAreaResponse]:
    purge_expired_tombstones(session, access.workspace.id)
    rows = session.execute(
        select(KnowledgeArea, func.count(Document.id))
        .outerjoin(
            Document,
            (Document.workspace_id == KnowledgeArea.workspace_id)
            & (Document.knowledge_area_id == KnowledgeArea.id)
            & Document.deleted_at.is_(None),
        )
        .where(KnowledgeArea.workspace_id == access.workspace.id)
        .group_by(KnowledgeArea.id)
        .order_by(KnowledgeArea.name, KnowledgeArea.id)
    ).all()
    return [_area_response(area, int(count)) for area, count in rows]


def get_knowledge_area(
    session: Session, access: WorkspaceAccess, area_id: UUID
) -> KnowledgeAreaResponse:
    area = session.scalar(
        select(KnowledgeArea).where(
            KnowledgeArea.workspace_id == access.workspace.id,
            KnowledgeArea.id == area_id,
        )
    )
    if area is None:
        raise area_not_found()
    return _area_response(area, _document_count(session, access.workspace.id, area.id))


def create_knowledge_area(
    session: Session, access: WorkspaceAccess, payload: KnowledgeAreaCreate
) -> KnowledgeAreaResponse:
    require_owner(access)
    area = KnowledgeArea(
        id=uuid4(),
        workspace_id=access.workspace.id,
        name=payload.name,
        normalized_name=payload.name.lower(),
        description=payload.description,
        created_by=access.actor_user_id,
    )
    session.add(area)
    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise duplicate_area_name() from error
    session.refresh(area)
    return _area_response(area, 0)


def update_knowledge_area(
    session: Session,
    access: WorkspaceAccess,
    area_id: UUID,
    payload: KnowledgeAreaUpdate,
) -> KnowledgeAreaResponse:
    require_owner(access)
    if not payload.model_fields_set:
        raise HTTPException(
            status_code=422,
            detail={"code": "empty_update", "message": "Provide a name or description to update"},
        )
    area = session.scalar(
        select(KnowledgeArea).where(
            KnowledgeArea.workspace_id == access.workspace.id,
            KnowledgeArea.id == area_id,
        )
    )
    if area is None:
        raise area_not_found()
    if "name" in payload.model_fields_set:
        if payload.name is None:
            raise HTTPException(
                status_code=422,
                detail={"code": "invalid_name", "message": "Knowledge-area name cannot be empty"},
            )
        area.name = payload.name
        area.normalized_name = payload.name.lower()
    if "description" in payload.model_fields_set:
        area.description = payload.description
    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise duplicate_area_name() from error
    session.refresh(area)
    return _area_response(area, _document_count(session, access.workspace.id, area.id))


def delete_knowledge_area(session: Session, access: WorkspaceAccess, area_id: UUID) -> None:
    require_owner(access)
    purge_expired_tombstones(session, access.workspace.id)
    area = session.scalar(
        select(KnowledgeArea).where(
            KnowledgeArea.workspace_id == access.workspace.id,
            KnowledgeArea.id == area_id,
        )
    )
    if area is None:
        raise area_not_found()
    if _document_count(session, access.workspace.id, area.id) > 0:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "knowledge_area_not_empty",
                "message": "The area still contains documents or retained deletion records",
            },
        )
    session.delete(area)
    session.commit()


def area_not_found() -> HTTPException:
    return HTTPException(
        status_code=404,
        detail={"code": "knowledge_area_not_found", "message": "Knowledge area not found"},
    )


def duplicate_area_name() -> HTTPException:
    return HTTPException(
        status_code=409,
        detail={
            "code": "knowledge_area_name_conflict",
            "message": "A knowledge area with that name already exists in this workspace",
        },
    )
