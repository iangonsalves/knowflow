from dataclasses import dataclass
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateIndex

from app.db.models import Document, DocumentChunk, DocumentStatus
from app.embeddings.provider import EmbeddingSet
from app.search.schemas import SearchRequest
from app.search.service import RankedChunk, fuse_rankings
from app.tenancy.policies import require_workspace_access


def test_fts_index_expression_compiles_as_postgresql_literal_sql() -> None:
    index = next(
        index
        for index in DocumentChunk.__table__.indexes
        if index.name == "ix_chunks_search_vector"
    )

    compiled = str(CreateIndex(index).compile(dialect=postgresql.dialect()))

    assert "to_tsvector('english', text)" in compiled


@dataclass
class FakeProvider:
    dimensions: int = 384

    def embed(self, texts, *, purpose, progress=None):
        vector = [0.0] * self.dimensions
        vector[0] = 1.0
        return EmbeddingSet(
            "intfloat/e5-small-v2@ffb93f3bd4047442299a41ebb6fa998a38507c52",
            "v1",
            self.dimensions,
            [vector for _ in texts],
        )


def test_rrf_combines_and_deduplicates_with_stable_order(db_session, identities) -> None:
    document = Document(
        workspace_id=identities.workspace.id,
        knowledge_area_id=uuid4(),
        uploaded_by=identities.owner.id,
        original_filename="test.pdf",
        storage_key="rrf-test",
        content_type="application/pdf",
        byte_size=1,
        page_count=1,
        sha256="a" * 64,
        status=DocumentStatus.READY.value,
    )
    first = DocumentChunk(
        id=uuid4(),
        workspace_id=identities.workspace.id,
        document=document,
        chunk_index=0,
        text="First",
        page_start=1,
        page_end=1,
        content_hash="b" * 64,
    )
    second = DocumentChunk(
        id=uuid4(),
        workspace_id=identities.workspace.id,
        document=document,
        chunk_index=1,
        text="Second",
        page_start=1,
        page_end=1,
        content_hash="c" * 64,
    )
    third = DocumentChunk(
        id=uuid4(),
        workspace_id=identities.workspace.id,
        document=document,
        chunk_index=2,
        text="Third",
        page_start=1,
        page_end=1,
        content_hash="d" * 64,
    )
    keyword = [RankedChunk(first, document, 1), RankedChunk(second, document, 2)]
    vector = [RankedChunk(second, document, 1), RankedChunk(third, document, 2)]

    fused = fuse_rankings(keyword, vector, rrf_k=60)

    assert [item.chunk.id for item in fused] == [second.id, first.id, third.id]
    assert fused[0].keyword_rank == 2 and fused[0].vector_rank == 1
    assert len({item.chunk.id for item in fused}) == 3


def test_search_request_rejects_blank_and_oversized_query() -> None:
    with pytest.raises(ValueError):
        SearchRequest(query="  ")
    with pytest.raises(ValueError):
        SearchRequest(query="x" * 10_001)


def test_search_requires_workspace_membership(client, identities, db_session) -> None:
    assert require_workspace_access(db_session, identities.owner, identities.workspace.id)
    with pytest.raises(HTTPException) as error:
        require_workspace_access(db_session, identities.outsider, identities.workspace.id)
    assert error.value.status_code == 404


def test_owner_and_member_can_call_search_but_foreign_workspace_is_hidden(
    client, identities, monkeypatch
) -> None:

    # Workspace membership is tested at the route boundary; PostgreSQL-specific retrieval is
    # covered by test_postgres_retrieval.py.
    async def fake_provider(_settings):
        return FakeProvider()

    # The provider factory is synchronous; use a tiny deterministic query result override.
    monkeypatch.setattr(
        "app.search.router.get_embedding_provider", lambda _settings: FakeProvider()
    )
    monkeypatch.setattr("app.search.router.retrieve", lambda *_args, **_kwargs: [])
    request = {"query": "annual leave"}
    url = f"/api/v1/workspaces/{identities.workspace.id}/search"
    assert (
        client.post(
            url, headers={"Authorization": "Bearer workos_owner_sub"}, json=request
        ).status_code
        == 200
    )
    assert (
        client.post(
            url, headers={"Authorization": "Bearer workos_member_sub"}, json=request
        ).status_code
        == 200
    )
    foreign = f"/api/v1/workspaces/{identities.other.id}/search"
    assert (
        client.post(
            foreign, headers={"Authorization": "Bearer workos_member_sub"}, json=request
        ).status_code
        == 404
    )
