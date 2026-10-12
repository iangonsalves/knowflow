from uuid import UUID

from fastapi.testclient import TestClient

OWNER_HEADERS = {"Authorization": "Bearer workos_owner_sub"}
MEMBER_HEADERS = {"Authorization": "Bearer workos_member_sub"}
OUTSIDER_HEADERS = {"Authorization": "Bearer workos_outsider_sub"}


def create_area(client: TestClient, workspace_id: UUID, headers=OWNER_HEADERS) -> dict:
    response = client.post(
        f"/api/v1/workspaces/{workspace_id}/knowledge-areas",
        json={"name": "Engineering", "description": "Engineering documentation"},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_owner_manages_areas_and_member_has_read_only_access(client, identities) -> None:
    area = create_area(client, identities.workspace.id)
    area_id = area["id"]
    base = f"/api/v1/workspaces/{identities.workspace.id}/knowledge-areas"

    assert client.get(base, headers=MEMBER_HEADERS).json()[0]["id"] == area_id
    assert client.get(f"{base}/{area_id}", headers=MEMBER_HEADERS).status_code == 200
    assert (
        client.patch(f"{base}/{area_id}", json={"name": "Platform"}, headers=OWNER_HEADERS).json()[
            "name"
        ]
        == "Platform"
    )
    assert client.post(base, json={"name": "Product"}, headers=MEMBER_HEADERS).status_code == 403
    assert (
        client.patch(
            f"{base}/{area_id}", json={"name": "Forbidden"}, headers=MEMBER_HEADERS
        ).status_code
        == 403
    )
    assert client.delete(f"{base}/{area_id}", headers=MEMBER_HEADERS).status_code == 403
    assert client.delete(f"{base}/{area_id}", headers=OWNER_HEADERS).status_code == 204
    assert client.get(f"{base}/{area_id}", headers=OWNER_HEADERS).status_code == 404


def test_knowledge_areas_are_scoped_to_workspace(client, identities) -> None:
    area = create_area(client, identities.workspace.id)
    other_base = f"/api/v1/workspaces/{identities.other.id}/knowledge-areas"

    assert client.get(other_base, headers=OWNER_HEADERS).status_code == 404
    assert client.get(f"{other_base}/{area['id']}", headers=OUTSIDER_HEADERS).status_code == 404
    assert (
        client.patch(
            f"{other_base}/{area['id']}",
            json={"name": "Compromised"},
            headers=OUTSIDER_HEADERS,
        ).status_code
        == 404
    )
    assert client.delete(f"{other_base}/{area['id']}", headers=OUTSIDER_HEADERS).status_code == 404


def test_area_names_are_unique_case_insensitively_per_workspace(client, identities) -> None:
    area = create_area(client, identities.workspace.id)
    duplicate = client.post(
        f"/api/v1/workspaces/{identities.workspace.id}/knowledge-areas",
        json={"name": " engineering "},
        headers=OWNER_HEADERS,
    )
    assert duplicate.status_code == 409

    other_area = client.post(
        f"/api/v1/workspaces/{identities.other.id}/knowledge-areas",
        json={"name": "Engineering"},
        headers=OUTSIDER_HEADERS,
    )
    assert other_area.status_code == 201
    assert other_area.json()["id"] != area["id"]
