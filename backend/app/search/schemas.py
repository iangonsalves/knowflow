"""Search request and citation-ready result contracts."""

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


class SearchResponse(BaseModel):
    query: str
    results: list[SearchResult]
