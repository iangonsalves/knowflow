from datetime import UTC, datetime, timedelta
from io import BytesIO
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import Settings
from app.db.models import Document, DocumentStatus, ProcessingJob, ProcessingJobStatus
from app.documents.router import get_object_storage
from app.main import app

OWNER_HEADERS = {"Authorization": "Bearer workos_owner_sub"}
MEMBER_HEADERS = {"Authorization": "Bearer workos_member_sub"}
OUTSIDER_HEADERS = {"Authorization": "Bearer workos_outsider_sub"}


class FakeObjectStorage:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.fail_put = False
        self.fail_delete = False
        self.put_calls: list[tuple[str, int, str, str]] = []
        self.deleted_keys: list[str] = []

    def put_file(self, key: str, stream, size: int, checksum: str, content_type: str) -> None:
        if self.fail_put:
            from app.documents.storage import ObjectStorageError

            raise ObjectStorageError("fake storage failure")
        data = stream.read()
        assert len(data) == size
        self.objects[key] = data
        self.put_calls.append((key, size, checksum, content_type))

    def get_file(self, key: str):
        from app.documents.storage import StoredObjectNotFound

        if key not in self.objects:
            raise StoredObjectNotFound("fake object missing")
        data = self.objects[key]
        return BytesIO(data), len(data)

    def delete_file(self, key: str) -> None:
        from app.documents.storage import ObjectStorageError

        self.deleted_keys.append(key)
        if self.fail_delete:
            raise ObjectStorageError("fake delete failure")
        self.objects.pop(key, None)


def make_text_pdf(page_count: int = 1) -> bytes:
    """Create a small standards-readable PDF with selectable text on each page."""
    page_object_ids = [3 + index * 2 for index in range(page_count)]
    font_object_id = 3 + page_count * 2
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        (
            f"<< /Type /Pages /Kids [{' '.join(f'{page_id} 0 R' for page_id in page_object_ids)}] "
            f"/Count {page_count} >>"
        ).encode(),
    ]
    for index, page_id in enumerate(page_object_ids):
        content_id = page_id + 1
        stream_data = f"BT /F1 12 Tf 20 80 Td (KnowFlow page {index + 1}) Tj ET\n".encode()
        objects.extend(
            [
                (
                    f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 144] "
                    f"/Resources << /Font << /F1 {font_object_id} 0 R >> >> "
                    f"/Contents {content_id} 0 R >>"
                ).encode(),
                f"<< /Length {len(stream_data)} >>\nstream\n".encode() + stream_data + b"endstream",
            ]
        )
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

    pdf = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for object_number, body in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf.extend(f"{object_number} 0 obj\n".encode() + body + b"\nendobj\n")
    xref_offset = len(pdf)
    pdf.extend(f"xref\n0 {len(objects) + 1}\n".encode())
    pdf.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        pdf.extend(f"{offset:010d} 00000 n \n".encode())
    pdf.extend(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_offset}\n%%EOF\n".encode()
    )
    return bytes(pdf)


def register_storage(fake_storage: FakeObjectStorage) -> None:
    app.dependency_overrides[get_object_storage] = lambda: fake_storage


def create_area(client: TestClient, workspace_id: UUID, headers=OWNER_HEADERS) -> str:
    response = client.post(
        f"/api/v1/workspaces/{workspace_id}/knowledge-areas",
        json={"name": "HR"},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def upload_pdf(
    client: TestClient,
    workspace_id: UUID,
    area_id: str,
    *,
    headers=OWNER_HEADERS,
    contents: bytes | None = None,
    filename: str = "leave-policy.pdf",
    content_type: str = "application/pdf",
):
    return client.post(
        f"/api/v1/workspaces/{workspace_id}/documents",
        data={"knowledge_area_id": area_id},
        files={
            "file": (filename, contents if contents is not None else make_text_pdf(), content_type)
        },
        headers=headers,
    )


def test_owner_uploads_member_reads_and_downloads_then_delete_revokes_access(
    client, identities, db_session
) -> None:
    storage = FakeObjectStorage()
    register_storage(storage)
    area_id = create_area(client, identities.workspace.id)
    contents = make_text_pdf()
    uploaded = upload_pdf(client, identities.workspace.id, area_id, contents=contents)
    assert uploaded.status_code == 201, uploaded.text
    document = uploaded.json()
    assert document["original_filename"] == "leave-policy.pdf"
    assert document["status"] == DocumentStatus.UPLOADED
    assert document["page_count"] == 1
    assert document["byte_size"] == len(contents)
    assert len(storage.objects) == 1
    job = db_session.scalar(
        select(ProcessingJob).where(ProcessingJob.document_id == UUID(document["id"]))
    )
    assert job is not None
    assert job.status == ProcessingJobStatus.QUEUED
    assert job.attempt_count == 0
    assert job.max_attempts == 4
    storage_key, stored_size, stored_digest, stored_type = storage.put_calls[0]
    assert storage_key.startswith("documents/") and "leave-policy" not in storage_key
    assert stored_size == len(contents)
    assert len(stored_digest) == 64
    assert stored_type == "application/pdf"

    workspace_documents = f"/api/v1/workspaces/{identities.workspace.id}/documents"
    document_path = f"{workspace_documents}/{document['id']}"
    assert client.get(workspace_documents, headers=MEMBER_HEADERS).json()[0]["id"] == document["id"]
    assert client.get(document_path, headers=MEMBER_HEADERS).status_code == 200
    preview = client.get(f"{document_path}/content", headers=MEMBER_HEADERS)
    assert preview.status_code == 200
    assert preview.content == contents
    assert preview.headers["content-type"].startswith("application/pdf")
    assert preview.headers["content-disposition"].startswith("inline;")
    download = client.get(f"{document_path}/content?download=true", headers=OWNER_HEADERS)
    assert download.headers["content-disposition"].startswith("attachment;")

    assert (
        upload_pdf(
            client,
            identities.workspace.id,
            area_id,
            headers=MEMBER_HEADERS,
        ).status_code
        == 403
    )
    assert client.delete(document_path, headers=MEMBER_HEADERS).status_code == 403
    area_path = f"/api/v1/workspaces/{identities.workspace.id}/knowledge-areas/{area_id}"
    assert client.delete(area_path, headers=OWNER_HEADERS).status_code == 409

    assert client.delete(document_path, headers=OWNER_HEADERS).status_code == 204
    assert client.delete(document_path, headers=OWNER_HEADERS).status_code == 204
    assert storage_key not in storage.objects
    assert client.get(document_path, headers=OWNER_HEADERS).status_code == 404
    assert client.get(f"{document_path}/content", headers=OWNER_HEADERS).status_code == 404
    tombstone = db_session.get(Document, UUID(document["id"]))
    assert tombstone is not None
    assert job.status == ProcessingJobStatus.CANCELLED
    assert tombstone.status == DocumentStatus.DELETING
    assert tombstone.deleted_at is not None
    assert tombstone.cleanup_completed_at is not None
    assert tombstone.purge_after is not None
    purge_after = tombstone.purge_after
    if purge_after.tzinfo is None:
        purge_after = purge_after.replace(tzinfo=UTC)
    assert purge_after > datetime.now(UTC) + timedelta(days=6)
    assert client.delete(area_path, headers=OWNER_HEADERS).status_code == 409

    tombstone.purge_after = datetime.now(UTC) - timedelta(seconds=1)
    db_session.commit()
    assert client.delete(area_path, headers=OWNER_HEADERS).status_code == 204
    assert db_session.get(Document, UUID(document["id"])) is None


def test_document_metadata_content_and_mutations_are_workspace_scoped(client, identities) -> None:
    storage = FakeObjectStorage()
    register_storage(storage)
    area_one = create_area(client, identities.workspace.id)
    area_two = create_area(client, identities.other.id, headers=OUTSIDER_HEADERS)
    doc_one = upload_pdf(client, identities.workspace.id, area_one).json()
    doc_two = upload_pdf(client, identities.other.id, area_two, headers=OUTSIDER_HEADERS).json()

    workspace_one_path = f"/api/v1/workspaces/{identities.workspace.id}/documents"
    workspace_two_path = f"/api/v1/workspaces/{identities.other.id}/documents"
    assert client.get(workspace_one_path, headers=OUTSIDER_HEADERS).status_code == 404
    assert client.get(workspace_two_path, headers=OWNER_HEADERS).status_code == 404

    # Valid workspace membership does not allow substituting another tenant's document ID.
    for path, headers in (
        (f"{workspace_one_path}/{doc_two['id']}", OWNER_HEADERS),
        (f"{workspace_one_path}/{doc_two['id']}/content", OWNER_HEADERS),
        (f"{workspace_two_path}/{doc_one['id']}", OUTSIDER_HEADERS),
        (f"{workspace_two_path}/{doc_one['id']}/content", OUTSIDER_HEADERS),
    ):
        assert client.get(path, headers=headers).status_code == 404
    assert (
        client.delete(f"{workspace_one_path}/{doc_two['id']}", headers=OWNER_HEADERS).status_code
        == 404
    )
    assert (
        client.delete(f"{workspace_two_path}/{doc_one['id']}", headers=OUTSIDER_HEADERS).status_code
        == 404
    )
    assert len(storage.objects) == 2


@pytest.mark.parametrize(
    ("filename", "content_type", "contents", "expected_status", "expected_code"),
    [
        ("readme.txt", "text/plain", b"ordinary text", 415, "pdf_required"),
        ("not-really.pdf", "application/pdf", b"%PDF- this is malformed", 422, "invalid_pdf"),
    ],
)
def test_invalid_pdf_uploads_are_rejected_without_storing_objects(
    client,
    identities,
    filename,
    content_type,
    contents,
    expected_status,
    expected_code,
) -> None:
    storage = FakeObjectStorage()
    register_storage(storage)
    area_id = create_area(client, identities.workspace.id)

    response = upload_pdf(
        client,
        identities.workspace.id,
        area_id,
        contents=contents,
        filename=filename,
        content_type=content_type,
    )
    assert response.status_code == expected_status
    assert response.json()["error"]["code"] == expected_code
    assert storage.objects == {}


def test_size_and_page_limits_are_enforced_at_upload_boundary(
    client, identities, monkeypatch: pytest.MonkeyPatch
) -> None:
    import app.documents.router as router_module

    storage = FakeObjectStorage()
    register_storage(storage)
    area_id = create_area(client, identities.workspace.id)
    monkeypatch.setattr(
        router_module,
        "get_settings",
        lambda: Settings(_env_file=None, max_upload_bytes=32),
    )
    oversize = upload_pdf(
        client,
        identities.workspace.id,
        area_id,
        contents=b"%PDF-" + (b"x" * 64),
    )
    assert oversize.status_code == 413
    assert oversize.json()["error"]["code"] == "upload_too_large"
    assert storage.objects == {}

    monkeypatch.setattr(
        router_module,
        "get_settings",
        lambda: Settings(_env_file=None, max_pdf_pages=2),
    )
    too_many_pages = upload_pdf(
        client,
        identities.workspace.id,
        area_id,
        contents=make_text_pdf(page_count=3),
    )
    assert too_many_pages.status_code == 413
    assert too_many_pages.json()["error"]["code"] == "pdf_page_limit_exceeded"
    assert storage.objects == {}


def test_storage_failures_do_not_publish_documents_and_delete_failure_keeps_tombstone(
    client, identities, db_session
) -> None:
    storage = FakeObjectStorage()
    register_storage(storage)
    area_id = create_area(client, identities.workspace.id)
    storage.fail_put = True
    failed_upload = upload_pdf(client, identities.workspace.id, area_id)
    assert failed_upload.status_code == 503
    assert storage.objects == {}
    assert (
        client.get(
            f"/api/v1/workspaces/{identities.workspace.id}/documents", headers=OWNER_HEADERS
        ).json()
        == []
    )

    storage.fail_put = False
    document = upload_pdf(client, identities.workspace.id, area_id).json()
    document_path = f"/api/v1/workspaces/{identities.workspace.id}/documents/{document['id']}"
    storage.fail_delete = True
    failed_delete = client.delete(document_path, headers=OWNER_HEADERS)
    assert failed_delete.status_code == 503
    assert failed_delete.json()["error"]["code"] == "document_cleanup_pending"
    assert client.get(document_path, headers=OWNER_HEADERS).status_code == 404
    tombstone = db_session.get(Document, UUID(document["id"]))
    assert tombstone is not None and tombstone.deleted_at is not None
    assert tombstone.cleanup_completed_at is None

    storage.fail_delete = False
    assert client.delete(document_path, headers=OWNER_HEADERS).status_code == 204
    tombstone = db_session.get(Document, UUID(document["id"]))
    assert tombstone is not None and tombstone.cleanup_completed_at is not None
