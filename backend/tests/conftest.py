"""Shared isolated database and authenticated test-client fixtures."""

from collections.abc import Generator
from dataclasses import dataclass
from typing import Annotated

import pytest
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.models import Base, MembershipRole, User, Workspace, WorkspaceMembership
from app.db.session import get_session
from app.identity.dependencies import bearer_scheme, get_current_user
from app.main import app


@dataclass(frozen=True)
class TestIdentities:
    owner: User
    member: User
    outsider: User
    workspace: Workspace
    other: Workspace


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def enable_sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    session = session_factory()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


@pytest.fixture
def identities(db_session: Session) -> TestIdentities:
    owner = User(
        auth_subject="workos_owner_sub",
        email="owner@example.com",
        email_verified=True,
        display_name="Owner User",
    )
    member = User(
        auth_subject="workos_member_sub",
        email="member@example.com",
        email_verified=True,
        display_name="Member User",
    )
    outsider = User(
        auth_subject="workos_outsider_sub",
        email="outsider@example.com",
        email_verified=True,
        display_name="Outsider User",
    )
    db_session.add_all([owner, member, outsider])
    db_session.flush()
    workspace = Workspace(name="Owner workspace", slug="owner-workspace", created_by=owner.id)
    other_workspace = Workspace(
        name="Other workspace", slug="other-workspace", created_by=outsider.id
    )
    db_session.add_all([workspace, other_workspace])
    db_session.flush()
    db_session.add_all(
        [
            WorkspaceMembership(
                workspace_id=workspace.id,
                user_id=owner.id,
                role=MembershipRole.OWNER.value,
                created_by=owner.id,
            ),
            WorkspaceMembership(
                workspace_id=workspace.id,
                user_id=member.id,
                role=MembershipRole.MEMBER.value,
                created_by=owner.id,
            ),
            WorkspaceMembership(
                workspace_id=other_workspace.id,
                user_id=outsider.id,
                role=MembershipRole.OWNER.value,
                created_by=outsider.id,
            ),
        ]
    )
    db_session.commit()
    return TestIdentities(owner, member, outsider, workspace, other_workspace)


@pytest.fixture
def client(db_session: Session) -> Generator[TestClient, None, None]:
    def override_session() -> Generator[Session, None, None]:
        yield db_session

    def override_current_user(
        credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    ) -> User:
        # Only test requests accept the subject selector; production dependency verifies JWTs.
        if credentials is None:
            raise HTTPException(status_code=401, detail="Not authenticated")
        user = db_session.scalar(select(User).where(User.auth_subject == credentials.credentials))
        if user is None:
            raise HTTPException(status_code=401, detail="Invalid test identity")
        return user

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_current_user] = override_current_user
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()
