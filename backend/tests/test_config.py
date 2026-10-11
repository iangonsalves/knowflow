import pytest
from pydantic import ValidationError

from app.core.config import Settings


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
        Settings(_env_file=None, app_env="production")
