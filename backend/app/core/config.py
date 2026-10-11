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

    max_upload_bytes: int = Field(default=20 * 1024 * 1024, gt=0)
    max_pdf_pages: int = Field(default=250, gt=0)
    max_question_chars: int = Field(default=2_000, gt=0)
    keyword_candidates: int = Field(default=30, gt=0)
    vector_candidates: int = Field(default=30, gt=0)
    retrieval_top_k: int = Field(default=6, gt=0)
    max_context_tokens: int = Field(default=6_000, gt=0)

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
        return self


@lru_cache
def get_settings() -> Settings:
    """Return one validated settings object per process."""
    return Settings()
