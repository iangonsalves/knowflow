"""Workspace and membership REST API."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.identity.dependencies import CurrentUser
from app.tenancy.policies import require_workspace_access
from app.tenancy.schemas import (
    MemberAdd,
    MemberResponse,
    MembershipRoleUpdate,
    WorkspaceCreate,
    WorkspaceResponse,
)
from app.tenancy.service import (
    add_member,
    create_workspace,
    get_workspace,
    list_members,
    list_user_workspaces,
    remove_member,
    update_member_role,
)

router = APIRouter(prefix="/workspaces", tags=["workspaces"])
SessionDep = Annotated[Session, Depends(get_session)]


@router.get("", response_model=list[WorkspaceResponse])
def list_workspaces(current_user: CurrentUser, session: SessionDep) -> list[WorkspaceResponse]:
    return list_user_workspaces(session, current_user)


@router.post("", response_model=WorkspaceResponse, status_code=status.HTTP_201_CREATED)
def post_workspace(
    payload: WorkspaceCreate, current_user: CurrentUser, session: SessionDep
) -> WorkspaceResponse:
    return create_workspace(session, current_user, payload)


@router.get("/{workspace_id}", response_model=WorkspaceResponse)
def read_workspace(
    workspace_id: UUID, current_user: CurrentUser, session: SessionDep
) -> WorkspaceResponse:
    access = require_workspace_access(session, current_user, workspace_id)
    return get_workspace(access)


@router.get("/{workspace_id}/members", response_model=list[MemberResponse])
def read_members(
    workspace_id: UUID, current_user: CurrentUser, session: SessionDep
) -> list[MemberResponse]:
    access = require_workspace_access(session, current_user, workspace_id)
    return list_members(session, access)


@router.post(
    "/{workspace_id}/members",
    response_model=MemberResponse,
    status_code=status.HTTP_201_CREATED,
)
def post_member(
    workspace_id: UUID,
    payload: MemberAdd,
    current_user: CurrentUser,
    session: SessionDep,
) -> MemberResponse:
    access = require_workspace_access(session, current_user, workspace_id)
    return add_member(session, access, payload)


@router.patch("/{workspace_id}/members/{user_id}", response_model=MemberResponse)
def patch_member(
    workspace_id: UUID,
    user_id: UUID,
    payload: MembershipRoleUpdate,
    current_user: CurrentUser,
    session: SessionDep,
) -> MemberResponse:
    access = require_workspace_access(session, current_user, workspace_id)
    return update_member_role(session, access, user_id, payload.role)


@router.delete("/{workspace_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_member(
    workspace_id: UUID,
    user_id: UUID,
    current_user: CurrentUser,
    session: SessionDep,
) -> Response:
    access = require_workspace_access(session, current_user, workspace_id)
    remove_member(session, access, user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
