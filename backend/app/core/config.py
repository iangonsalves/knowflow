"""Validated application settings loaded from the environment."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration with safe development defaults and bounded values."""

    model_config = SettingsConfigDict(
        env_prefix="KNOWFLOW_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "KnowFlow API"
    app_env: Literal["development", "test", "production"] = "development"
    database_url: str = "postgresql+psycopg://knowflow:knowflow_local_only@db:5432/knowflow"
    allowed_origins: list[str] = ["http://localhost:3000"]
    workos_client_id: str | None = Field(default=None, validation_alias="WORKOS_CLIENT_ID")
    workos_api_key: str | None = Field(default=None, validation_alias="WORKOS_API_KEY")
    workos_issuer: str | None = Field(default=None, validation_alias="WORKOS_ISSUER")
    workos_token_audience: str | None = Field(
        default="https://api.knowflow.example", validation_alias="WORKOS_TOKEN_AUDIENCE"
    )
    workos_api_base_url: str = "https://api.workos.com"

    object_storage_endpoint_url: str = "http://object-store:9000"
    object_storage_access_key: str = "knowflow_local"
    object_storage_secret_key: str = "knowflow_minio_local_only"
    object_storage_bucket: str = "knowflow-documents"
    object_storage_region: str = "us-east-1"

    embedding_model: str = "intfloat/e5-small-v2"
    embedding_revision: str = "ffb93f3bd4047442299a41ebb6fa998a38507c52"
    embedding_dimensions: int = Field(default=384, gt=0)
    embedding_version: Literal["v1"] = "v1"
    embedding_cache_dir: str = "/models"
    embedding_device: Literal["cpu"] = "cpu"
    embedding_batch_size: int = Field(default=16, gt=0, le=128)

    max_upload_bytes: int = Field(default=20 * 1024 * 1024, gt=0)
    max_pdf_pages: int = Field(default=250, gt=0)
    chunk_size_chars: int = Field(default=1_800, gt=0)
    chunk_overlap_chars: int = Field(default=240, ge=0)
    max_question_chars: int = Field(default=2_000, gt=0)
    keyword_candidates: int = Field(default=30, gt=0)
    vector_candidates: int = Field(default=30, gt=0)
    retrieval_top_k: int = Field(default=6, gt=0)
    rrf_k: int = Field(default=60, gt=0)

    processing_job_timeout_seconds: int = Field(default=600, gt=0)
    worker_max_attempts: int = Field(default=4, ge=1)
    worker_retry_backoff_seconds: list[int] = [30, 120, 600]
    cleanup_retry_window_hours: int = Field(default=24, gt=0)
    tombstone_retention_days: int = Field(default=7, gt=0)
    job_lease_seconds: int = Field(default=90, gt=0)
    job_heartbeat_seconds: int = Field(default=30, gt=0)

    rate_limit_questions_per_minute: int = Field(default=20, gt=0)
    rate_limit_question_burst: int = Field(default=5, gt=0)
    rate_limit_uploads_per_hour: int = Field(default=10, gt=0)
    rate_limit_upload_bytes_per_hour: int = Field(default=100 * 1024 * 1024, gt=0)
    rate_limit_auth_failures_per_ip: int = Field(default=10, gt=0)
    rate_limit_auth_window_seconds: int = Field(default=300, gt=0)
    max_search_results: int = Field(default=20, gt=0)
    search_page_size: int = Field(default=10, gt=0)
    evidence_supporting_limit: int = Field(default=3, ge=0, le=5)
    evidence_dedup_jaccard_threshold: float = Field(default=0.72, gt=0.5, le=1.0)
    evidence_minimum_query_term_overlap: int = Field(default=2, ge=1, le=10)
    evidence_minimum_query_coverage: float = Field(default=0.6, gt=0, le=1.0)
    evidence_minimum_vector_similarity: float = Field(default=0.72, ge=-1.0, le=1.0)

    auth_access_token_seconds: int = Field(default=900, gt=0)
    app_session_max_age_seconds: int = Field(default=7 * 24 * 60 * 60, gt=0)
    app_session_idle_timeout_seconds: int = Field(default=12 * 60 * 60, gt=0)

    @model_validator(mode="after")
    def validate_runtime_relationships(self) -> "Settings":
        if self.app_env == "production":
            if "local_only" in self.database_url:
                raise ValueError("production must use a non-development database credential")
            has_local_origin = any(
                "localhost" in origin or "127.0.0.1" in origin for origin in self.allowed_origins
            )
            if has_local_origin:
                raise ValueError("production allowed origins cannot point to localhost")
        if self.job_heartbeat_seconds >= self.job_lease_seconds:
            raise ValueError("job heartbeat must be shorter than the job lease")
        if len(self.worker_retry_backoff_seconds) != self.worker_max_attempts - 1:
            raise ValueError("retry backoff list must contain one delay per retry")
        if any(delay <= 0 for delay in self.worker_retry_backoff_seconds):
            raise ValueError("retry backoff delays must be positive")
        if self.search_page_size > self.max_search_results:
            raise ValueError("search page size cannot exceed max search results")
        if self.retrieval_top_k > self.max_search_results:
            raise ValueError("retrieval top K cannot exceed max search results")
        if self.max_question_chars > 10_000:
            raise ValueError("max question characters cannot exceed 10000")
        if self.chunk_overlap_chars >= self.chunk_size_chars:
            raise ValueError("chunk overlap must be smaller than chunk size")
        if (
            self.embedding_model != "intfloat/e5-small-v2"
            or self.embedding_revision != "ffb93f3bd4047442299a41ebb6fa998a38507c52"
            or self.embedding_dimensions != 384
        ):
            raise ValueError(
                "embedding model/dimensions must match the database vector schema; "
                "changing them requires a migration and re-embedding"
            )
        return self

    @property
    def embedding_model_identifier(self) -> str:
        """Immutable model identity stored with vectors so revisions cannot be mixed."""
        return f"{self.embedding_model}@{self.embedding_revision}"


@lru_cache
def get_settings() -> Settings:
    """Return one validated settings object per process."""
    return Settings()
