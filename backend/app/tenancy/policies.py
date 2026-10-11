"""Central workspace membership and role policy checks."""

from dataclasses import dataclass
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import MembershipRole, User, Workspace, WorkspaceMembership


@dataclass(frozen=True)
class WorkspaceAccess:
    workspace: Workspace
    role: MembershipRole
    actor_user_id: UUID


def require_workspace_access(session: Session, user: User, workspace_id: UUID) -> WorkspaceAccess:
    """Load a workspace only when the caller has an active membership."""
    row = session.execute(
        select(Workspace, WorkspaceMembership.role)
        .join(WorkspaceMembership, WorkspaceMembership.workspace_id == Workspace.id)
        .where(
            Workspace.id == workspace_id,
            WorkspaceMembership.user_id == user.id,
        )
    ).one_or_none()
    if row is None:
        # 404 avoids revealing whether an inaccessible workspace exists.
        raise HTTPException(
            status_code=404,
            detail={"code": "workspace_not_found", "message": "Workspace not found"},
        )
    workspace, role_value = row
    return WorkspaceAccess(
        workspace=workspace,
        role=MembershipRole(role_value),
        actor_user_id=user.id,
    )


def require_owner(access: WorkspaceAccess) -> None:
    if access.role is not MembershipRole.OWNER:
        raise HTTPException(
            status_code=403,
            detail={"code": "owner_required", "message": "Workspace Owner permission is required"},
        )


def require_last_owner_preserved(
    session: Session, workspace_id: UUID, target_user_id: UUID
) -> None:
    target = session.scalar(
        select(WorkspaceMembership).where(
            WorkspaceMembership.workspace_id == workspace_id,
            WorkspaceMembership.user_id == target_user_id,
        )
    )
    if target is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "membership_not_found", "message": "Workspace member not found"},
        )
    if target.role != MembershipRole.OWNER.value:
        return
    # Count in SQL so a workspace cannot accidentally lose its final Owner.
    owner_count = session.scalar(
        select(func.count())
        .select_from(WorkspaceMembership)
        .where(
            WorkspaceMembership.workspace_id == workspace_id,
            WorkspaceMembership.role == MembershipRole.OWNER.value,
        )
    )
    if owner_count <= 1:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "final_owner_required",
                "message": "A workspace must retain at least one Owner",
            },
        )
