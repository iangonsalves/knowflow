"""PostgreSQL lexical/vector retrieval with deterministic reciprocal-rank fusion."""

from dataclasses import dataclass
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, literal_column, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.models import Document, DocumentChunk, DocumentStatus, KnowledgeArea
from app.embeddings.provider import EmbeddingProvider, EmbeddingResponseError
from app.search.schemas import SearchRequest, SearchResult


@dataclass(frozen=True)
class RankedChunk:
    chunk: DocumentChunk
    document: Document
    rank: int
    signal: float = 0.0


@dataclass
class FusedChunk:
    chunk: DocumentChunk
    document: Document
    keyword_rank: int | None = None
    vector_rank: int | None = None
    score: float = 0.0
    keyword_score: float | None = None
    vector_similarity: float | None = None


def fuse_rankings(
    keyword: list[RankedChunk], vector: list[RankedChunk], *, rrf_k: int
) -> list[FusedChunk]:
    fused: dict[UUID, FusedChunk] = {}
    for source, ranking in (("keyword_rank", keyword), ("vector_rank", vector)):
        for candidate in ranking:
            item = fused.setdefault(
                candidate.chunk.id, FusedChunk(candidate.chunk, candidate.document)
            )
            setattr(item, source, candidate.rank)
            item.score += 1.0 / (rrf_k + candidate.rank)
            if source == "keyword_rank":
                item.keyword_score = candidate.signal
            else:
                item.vector_similarity = candidate.signal
    return sorted(
        fused.values(),
        key=lambda item: (
            -item.score,
            str(item.chunk.document_id),
            item.chunk.chunk_index,
            str(item.chunk.id),
        ),
    )


def retrieve(
    session: Session,
    *,
    workspace_id: UUID,
    request: SearchRequest,
    settings: Settings,
    embedding_provider: EmbeddingProvider,
) -> list[SearchResult]:
    authorized = (
        select(DocumentChunk, Document)
        .join(
            Document,
            (Document.workspace_id == DocumentChunk.workspace_id)
            & (Document.id == DocumentChunk.document_id),
        )
        .where(
            DocumentChunk.workspace_id == workspace_id,
            Document.workspace_id == workspace_id,
            Document.deleted_at.is_(None),
            Document.status == DocumentStatus.READY.value,
            DocumentChunk.embedding.is_not(None),
            DocumentChunk.embedding_model == settings.embedding_model_identifier,
            DocumentChunk.embedding_version == settings.embedding_version,
            DocumentChunk.embedding_dimensions == settings.embedding_dimensions,
        )
    )
    if request.knowledge_area_id is not None:
        # A cross-workspace area is treated as no matches; it never broadens the search.
        area_exists = session.scalar(
            select(KnowledgeArea.id).where(
                KnowledgeArea.id == request.knowledge_area_id,
                KnowledgeArea.workspace_id == workspace_id,
            )
        )
        if area_exists is None:
            raise HTTPException(
                status_code=404,
                detail={"code": "knowledge_area_not_found", "message": "Knowledge area not found"},
            )
        authorized = authorized.where(Document.knowledge_area_id == request.knowledge_area_id)

    query_embedding = embedding_provider.embed([request.query], purpose="query")
    if (
        len(query_embedding.vectors) != 1
        or query_embedding.model != settings.embedding_model_identifier
        or query_embedding.dimensions != settings.embedding_dimensions
        or len(query_embedding.vectors[0]) != settings.embedding_dimensions
    ):
        raise EmbeddingResponseError

    english_config = literal_column("'english'::regconfig")
    tsquery = func.websearch_to_tsquery(english_config, request.query)
    search_vector = func.to_tsvector(english_config, DocumentChunk.text)
    keyword_score = func.ts_rank_cd(search_vector, tsquery)
    keyword_rows = session.execute(
        authorized.add_columns(keyword_score.label("keyword_score"))
        .where(search_vector.op("@@")(tsquery))
        .order_by(keyword_score.desc(), DocumentChunk.id)
        .limit(settings.keyword_candidates)
    ).all()
    keyword = [
        RankedChunk(row[0], row[1], rank, float(row[2]))
        for rank, row in enumerate(keyword_rows, start=1)
    ]

    vector_column = DocumentChunk.embedding
    vector_distance = vector_column.cosine_distance(query_embedding.vectors[0])
    vector_rows = session.execute(
        authorized.add_columns(vector_distance.label("vector_distance"))
        .order_by(vector_distance, DocumentChunk.id)
        .limit(settings.vector_candidates)
    ).all()
    vector = [
        RankedChunk(row[0], row[1], rank, 1.0 - float(row[2]))
        for rank, row in enumerate(vector_rows, start=1)
    ]

    limit = request.limit or settings.retrieval_top_k
    fused = fuse_rankings(keyword, vector, rrf_k=settings.rrf_k)[:limit]
    return [
        SearchResult(
            chunk_id=item.chunk.id,
            document_id=item.document.id,
            document_filename=item.document.original_filename,
            chunk_index=item.chunk.chunk_index,
            text=item.chunk.text,
            page_start=item.chunk.page_start,
            page_end=item.chunk.page_end,
            rank=rank,
            rrf_score=item.score,
            keyword_rank=item.keyword_rank,
            vector_rank=item.vector_rank,
            keyword_score=item.keyword_score,
            vector_similarity=item.vector_similarity,
        )
        for rank, item in enumerate(fused, start=1)
    ]
