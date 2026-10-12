"""Workspace-scoped Knowledge Area REST API."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.identity.dependencies import CurrentUser
from app.knowledge_areas.schemas import (
    KnowledgeAreaCreate,
    KnowledgeAreaResponse,
    KnowledgeAreaUpdate,
)
from app.knowledge_areas.service import (
    create_knowledge_area,
    delete_knowledge_area,
    get_knowledge_area,
    list_knowledge_areas,
    update_knowledge_area,
)
from app.tenancy.policies import require_workspace_access

router = APIRouter(prefix="/workspaces/{workspace_id}/knowledge-areas", tags=["knowledge areas"])
SessionDep = Annotated[Session, Depends(get_session)]


@router.get("", response_model=list[KnowledgeAreaResponse])
def read_knowledge_areas(
    workspace_id: UUID, current_user: CurrentUser, session: SessionDep
) -> list[KnowledgeAreaResponse]:
    access = require_workspace_access(session, current_user, workspace_id)
    return list_knowledge_areas(session, access)


@router.post("", response_model=KnowledgeAreaResponse, status_code=status.HTTP_201_CREATED)
def post_knowledge_area(
    workspace_id: UUID,
    payload: KnowledgeAreaCreate,
    current_user: CurrentUser,
    session: SessionDep,
) -> KnowledgeAreaResponse:
    access = require_workspace_access(session, current_user, workspace_id)
    return create_knowledge_area(session, access, payload)


@router.get("/{area_id}", response_model=KnowledgeAreaResponse)
def read_knowledge_area(
    workspace_id: UUID, area_id: UUID, current_user: CurrentUser, session: SessionDep
) -> KnowledgeAreaResponse:
    access = require_workspace_access(session, current_user, workspace_id)
    return get_knowledge_area(session, access, area_id)


@router.patch("/{area_id}", response_model=KnowledgeAreaResponse)
def patch_knowledge_area(
    workspace_id: UUID,
    area_id: UUID,
    payload: KnowledgeAreaUpdate,
    current_user: CurrentUser,
    session: SessionDep,
) -> KnowledgeAreaResponse:
    access = require_workspace_access(session, current_user, workspace_id)
    return update_knowledge_area(session, access, area_id, payload)


@router.delete("/{area_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_knowledge_area(
    workspace_id: UUID, area_id: UUID, current_user: CurrentUser, session: SessionDep
) -> Response:
    access = require_workspace_access(session, current_user, workspace_id)
    delete_knowledge_area(session, access, area_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
