import os

import pytest
from pydantic import ValidationError

from app.core.config import Settings


@pytest.fixture(autouse=True)
def isolate_settings_from_process_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep config unit tests independent from CI and developer .env overrides."""
    workos_aliases = {
        "WORKOS_CLIENT_ID",
        "WORKOS_API_KEY",
        "WORKOS_ISSUER",
        "WORKOS_TOKEN_AUDIENCE",
    }
    for name in tuple(os.environ):
        normalized_name = name.upper()
        if normalized_name.startswith("KNOWFLOW_") or normalized_name in workos_aliases:
            monkeypatch.delenv(name)


def test_approved_operating_defaults_are_loaded() -> None:
    settings = Settings(_env_file=None)

    assert settings.max_upload_bytes == 20 * 1024 * 1024
    assert settings.max_pdf_pages == 250
    assert settings.max_question_chars == 2_000
    assert settings.keyword_candidates == 30
    assert settings.vector_candidates == 30
    assert settings.retrieval_top_k == 6
    assert settings.worker_max_attempts == 4
    assert settings.worker_retry_backoff_seconds == [30, 120, 600]
    assert settings.job_lease_seconds == 90
    assert settings.job_heartbeat_seconds == 30


def test_invalid_limits_fail_validation() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, max_upload_bytes=0)


def test_worker_lease_must_exceed_heartbeat() -> None:
    with pytest.raises(ValidationError, match="heartbeat must be shorter"):
        Settings(_env_file=None, job_lease_seconds=30, job_heartbeat_seconds=30)


def test_retry_schedule_must_match_attempt_count() -> None:
    with pytest.raises(ValidationError, match="one delay per retry"):
        Settings(_env_file=None, worker_max_attempts=3)


def test_production_rejects_development_database_credentials() -> None:
    with pytest.raises(ValidationError, match="production must use a non-development"):
        Settings(
            _env_file=None,
            app_env="production",
            database_url="postgresql+psycopg://knowflow:local_only@db/knowflow",
            allowed_origins=["https://knowflow.example"],
        )


def test_production_rejects_local_allowed_origins() -> None:
    with pytest.raises(
        ValidationError, match="production allowed origins cannot point to localhost"
    ):
        Settings(
            _env_file=None,
            app_env="production",
            database_url="postgresql+psycopg://knowflow:secure-password@db/knowflow",
            allowed_origins=["http://localhost:3000"],
        )
