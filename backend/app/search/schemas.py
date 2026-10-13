"""Hybrid-search and source-evidence response contracts."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=10_000)
    knowledge_area_id: UUID | None = None
    limit: int | None = Field(default=None, ge=1)

    @field_validator("query")
    @classmethod
    def nonblank_query(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Search query cannot be blank")
        return value.strip()


class SearchResult(BaseModel):
    chunk_id: UUID
    document_id: UUID
    document_filename: str
    chunk_index: int
    text: str
    page_start: int
    page_end: int
    rank: int
    rrf_score: float
    keyword_rank: int | None
    vector_rank: int | None
    # Internal evidence-assessment signals. Excluded from the public M5 response.
    keyword_score: float | None = Field(default=None, exclude=True)
    vector_similarity: float | None = Field(default=None, exclude=True)


class SearchResponse(BaseModel):
    query: str
    results: list[SearchResult]


class EvidenceItem(BaseModel):
    chunk_id: UUID
    document_id: UUID
    document_title: str
    text: str
    page_start: int
    page_end: int
    source_path: str
    retrieval_rank: int


class AskResponse(BaseModel):
    question: str
    evidence_state: Literal["evidence_found", "weak_evidence", "no_evidence"]
    message: str
    best_evidence: EvidenceItem | None
    supporting_evidence: list[EvidenceItem]
    related_evidence: list[EvidenceItem]
