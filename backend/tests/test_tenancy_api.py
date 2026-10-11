from uuid import UUID

from fastapi import HTTPException

from app.db.models import User, WorkspaceMembership
from app.tenancy.policies import require_workspace_access


def bearer(subject: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {subject}"}


def test_workspace_list_is_scoped_to_membership(client, identities) -> None:
    owner_response = client.get("/api/v1/workspaces", headers=bearer(identities.owner.auth_subject))
    outsider_response = client.get(
        "/api/v1/workspaces", headers=bearer(identities.outsider.auth_subject)
    )

    assert owner_response.status_code == 200
    assert [item["id"] for item in owner_response.json()] == [str(identities.workspace.id)]
    assert outsider_response.status_code == 200
    assert [item["id"] for item in outsider_response.json()] == [str(identities.other.id)]


def test_owner_and_member_read_own_workspace_and_members(client, identities) -> None:
    for actor, role in ((identities.owner, "OWNER"), (identities.member, "MEMBER")):
        workspace_response = client.get(
            f"/api/v1/workspaces/{identities.workspace.id}", headers=bearer(actor.auth_subject)
        )
        members_response = client.get(
            f"/api/v1/workspaces/{identities.workspace.id}/members",
            headers=bearer(actor.auth_subject),
        )
        assert workspace_response.status_code == 200
        assert workspace_response.json()["role"] == role
        assert members_response.status_code == 200
        assert {row["email"] for row in members_response.json()} == {
            "owner@example.com",
            "member@example.com",
        }


def test_cross_tenant_workspace_and_member_access_returns_not_found(client, identities) -> None:
    outsider = bearer(identities.outsider.auth_subject)
    response = client.get(f"/api/v1/workspaces/{identities.workspace.id}", headers=outsider)
    members = client.get(f"/api/v1/workspaces/{identities.workspace.id}/members", headers=outsider)

    assert response.status_code == 404
    assert members.status_code == 404


def test_member_cannot_add_change_or_remove_members(client, identities) -> None:
    headers = bearer(identities.member.auth_subject)
    add = client.post(
        f"/api/v1/workspaces/{identities.workspace.id}/members",
        headers=headers,
        json={"email": "new@example.com"},
    )
    change = client.patch(
        f"/api/v1/workspaces/{identities.workspace.id}/members/{identities.owner.id}",
        headers=headers,
        json={"role": "MEMBER"},
    )
    remove = client.delete(
        f"/api/v1/workspaces/{identities.workspace.id}/members/{identities.owner.id}",
        headers=headers,
    )

    assert (add.status_code, change.status_code, remove.status_code) == (403, 403, 403)


def test_create_workspace_grants_creator_owner_role(client, identities) -> None:
    response = client.post(
        "/api/v1/workspaces",
        headers=bearer(identities.owner.auth_subject),
        json={"name": "  Engineering  "},
    )

    assert response.status_code == 201
    created = response.json()
    assert created["name"] == "Engineering"
    assert created["role"] == "OWNER"


def test_owner_can_add_existing_verified_workos_user(client, identities, monkeypatch) -> None:
    class FakeDirectory:
        def find_verified_user_by_email(self, email: str) -> dict[str, object]:
            assert email == "new.member@example.com"
            return {
                "id": "user_new_member",
                "email": "New.Member@Example.com",
                "email_verified": True,
                "first_name": "New",
                "last_name": "Member",
            }

    monkeypatch.setattr("app.tenancy.service.WorkOSDirectoryClient", FakeDirectory)
    response = client.post(
        f"/api/v1/workspaces/{identities.workspace.id}/members",
        headers=bearer(identities.owner.auth_subject),
        json={"email": " New.Member@Example.com "},
    )

    assert response.status_code == 201
    assert response.json()["email"] == "new.member@example.com"
    assert response.json()["role"] == "MEMBER"
    new_user_id = response.json()["user_id"]
    assert UUID(new_user_id)


def test_only_workspace_owner_can_become_owner_and_final_owner_is_protected(
    client, identities
) -> None:
    headers = bearer(identities.owner.auth_subject)
    promote = client.patch(
        f"/api/v1/workspaces/{identities.workspace.id}/members/{identities.member.id}",
        headers=headers,
        json={"role": "OWNER"},
    )
    new_owner_headers = bearer(identities.member.auth_subject)
    demote_original = client.patch(
        f"/api/v1/workspaces/{identities.workspace.id}/members/{identities.owner.id}",
        headers=new_owner_headers,
        json={"role": "MEMBER"},
    )
    remove_original = client.delete(
        f"/api/v1/workspaces/{identities.workspace.id}/members/{identities.owner.id}",
        headers=new_owner_headers,
    )

    assert promote.status_code == 200
    assert promote.json()["role"] == "OWNER"
    assert demote_original.status_code == 200
    assert demote_original.json()["role"] == "MEMBER"
    assert remove_original.status_code == 204


def test_final_owner_cannot_be_demoted_or_removed(client, identities) -> None:
    headers = bearer(identities.owner.auth_subject)
    demote = client.patch(
        f"/api/v1/workspaces/{identities.workspace.id}/members/{identities.owner.id}",
        headers=headers,
        json={"role": "MEMBER"},
    )
    remove = client.delete(
        f"/api/v1/workspaces/{identities.workspace.id}/members/{identities.owner.id}",
        headers=headers,
    )

    assert demote.status_code == 409
    assert remove.status_code == 409


def test_duplicate_member_add_is_idempotent(client, identities, monkeypatch) -> None:
    class FakeDirectory:
        def find_verified_user_by_email(self, _email: str) -> dict[str, object]:
            return {
                "id": identities.member.auth_subject,
                "email": identities.member.email,
                "email_verified": True,
            }

    monkeypatch.setattr("app.tenancy.service.WorkOSDirectoryClient", FakeDirectory)
    first = client.post(
        f"/api/v1/workspaces/{identities.workspace.id}/members",
        headers=bearer(identities.owner.auth_subject),
        json={"email": identities.member.email},
    )
    second = client.post(
        f"/api/v1/workspaces/{identities.workspace.id}/members",
        headers=bearer(identities.owner.auth_subject),
        json={"email": identities.member.email},
    )

    assert first.status_code == second.status_code == 201
    assert first.json()["user_id"] == second.json()["user_id"]


def test_workspace_access_policy_uses_membership_not_provider_roles(db_session, identities) -> None:
    outsider = db_session.get(User, identities.outsider.id)
    try:
        require_workspace_access(db_session, outsider, identities.workspace.id)
    except HTTPException as error:
        assert error.status_code == 404
    else:
        raise AssertionError("non-member unexpectedly received workspace access")


def test_membership_database_rejects_role_outside_owner_member(db_session, identities) -> None:
    db_session.add(
        WorkspaceMembership(
            workspace_id=identities.workspace.id,
            user_id=identities.outsider.id,
            role="ADMIN",
            created_by=identities.owner.id,
        )
    )
    try:
        db_session.commit()
    except Exception:
        db_session.rollback()
    else:
        raise AssertionError("database accepted an unsupported workspace role")
