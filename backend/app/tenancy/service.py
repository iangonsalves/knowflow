"""Workspace and membership use cases with explicit tenant scope."""

import re
from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import MembershipRole, User, Workspace, WorkspaceMembership
from app.identity.service import provision_registered_user, raise_profile_http_error
from app.identity.workos import (
    WorkOSConfigurationError,
    WorkOSDirectoryClient,
    WorkOSDirectoryError,
)
from app.tenancy.policies import WorkspaceAccess, require_last_owner_preserved, require_owner
from app.tenancy.schemas import (
    MemberAdd,
    MemberResponse,
    RoleName,
    WorkspaceCreate,
    WorkspaceResponse,
)


def list_user_workspaces(session: Session, user: User) -> list[WorkspaceResponse]:
    rows = session.execute(
        select(Workspace, WorkspaceMembership.role)
        .join(WorkspaceMembership, WorkspaceMembership.workspace_id == Workspace.id)
        .where(WorkspaceMembership.user_id == user.id)
        .order_by(Workspace.created_at, Workspace.id)
    ).all()
    return [
        WorkspaceResponse(
            id=workspace.id,
            name=workspace.name,
            slug=workspace.slug,
            role=role,
            created_at=workspace.created_at,
        )
        for workspace, role in rows
    ]


def create_workspace(session: Session, user: User, payload: WorkspaceCreate) -> WorkspaceResponse:
    base_slug = re.sub(r"[^a-z0-9]+", "-", payload.name.casefold()).strip("-")[:100] or "workspace"
    workspace = Workspace(
        name=payload.name,
        slug=f"{base_slug}-{uuid4().hex[:8]}",
        created_by=user.id,
    )
    session.add(workspace)
    session.flush()
    session.add(
        WorkspaceMembership(
            workspace_id=workspace.id,
            user_id=user.id,
            role=MembershipRole.OWNER.value,
            created_by=user.id,
        )
    )
    session.commit()
    session.refresh(workspace)
    return WorkspaceResponse(
        id=workspace.id,
        name=workspace.name,
        slug=workspace.slug,
        role=RoleName.OWNER,
        created_at=workspace.created_at,
    )


def get_workspace(access: WorkspaceAccess) -> WorkspaceResponse:
    return WorkspaceResponse(
        id=access.workspace.id,
        name=access.workspace.name,
        slug=access.workspace.slug,
        role=access.role,
        created_at=access.workspace.created_at,
    )


def list_members(session: Session, access: WorkspaceAccess) -> list[MemberResponse]:
    rows = session.execute(
        select(WorkspaceMembership, User)
        .join(User, User.id == WorkspaceMembership.user_id)
        .where(WorkspaceMembership.workspace_id == access.workspace.id)
        .order_by(WorkspaceMembership.created_at, User.email)
    ).all()
    return [
        MemberResponse(
            user_id=user.id,
            email=user.email,
            display_name=user.display_name,
            role=membership.role,
            created_at=membership.created_at,
        )
        for membership, user in rows
    ]


def add_member(session: Session, access: WorkspaceAccess, payload: MemberAdd) -> MemberResponse:
    require_owner(access)
    try:
        profile = WorkOSDirectoryClient().find_verified_user_by_email(payload.email)
    except (WorkOSConfigurationError, WorkOSDirectoryError) as error:
        raise_profile_http_error(error)
    if profile is None:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "registered_user_not_found",
                "message": "No registered user has that email",
            },
        )
    user = provision_registered_user(session, profile)
    existing = session.get(WorkspaceMembership, (access.workspace.id, user.id))
    if existing is not None:
        return MemberResponse(
            user_id=user.id,
            email=user.email,
            display_name=user.display_name,
            role=existing.role,
            created_at=existing.created_at,
        )

    membership = WorkspaceMembership(
        workspace_id=access.workspace.id,
        user_id=user.id,
        role=MembershipRole.MEMBER.value,
        created_by=access.actor_user_id,
    )
    session.add(membership)
    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        existing = session.get(WorkspaceMembership, (access.workspace.id, user.id))
        if existing is None:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "membership_conflict",
                    "message": "Membership could not be created",
                },
            ) from error
        membership = existing
    session.refresh(membership)
    return MemberResponse(
        user_id=user.id,
        email=user.email,
        display_name=user.display_name,
        role=MembershipRole.MEMBER.value,
        created_at=membership.created_at,
    )


def update_member_role(
    session: Session,
    access: WorkspaceAccess,
    user_id: UUID,
    new_role: RoleName,
) -> MemberResponse:
    require_owner(access)
    # Serialize Owner-count changes per workspace on PostgreSQL.
    session.execute(select(Workspace).where(Workspace.id == access.workspace.id).with_for_update())
    membership = session.get(WorkspaceMembership, (access.workspace.id, user_id))
    if membership is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "membership_not_found", "message": "Workspace member not found"},
        )
    if membership.role == MembershipRole.OWNER.value and new_role is RoleName.MEMBER:
        require_last_owner_preserved(session, access.workspace.id, user_id)
    membership.role = new_role.value
    session.commit()
    session.refresh(membership)
    user = session.get(User, user_id)
    return MemberResponse(
        user_id=user.id,
        email=user.email,
        display_name=user.display_name,
        role=membership.role,
        created_at=membership.created_at,
    )


def remove_member(session: Session, access: WorkspaceAccess, user_id: UUID) -> None:
    require_owner(access)
    session.execute(select(Workspace).where(Workspace.id == access.workspace.id).with_for_update())
    membership = session.get(WorkspaceMembership, (access.workspace.id, user_id))
    if membership is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "membership_not_found", "message": "Workspace member not found"},
        )
    if membership.role == MembershipRole.OWNER.value:
        require_last_owner_preserved(session, access.workspace.id, user_id)
    session.delete(membership)
    session.commit()
