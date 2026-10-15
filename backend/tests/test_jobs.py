import threading
from contextlib import nullcontext
from datetime import UTC, datetime, timedelta
from io import BytesIO
from types import SimpleNamespace
from uuid import uuid4

from app.core.config import Settings
from app.db.models import (
    Document,
    DocumentStatus,
    KnowledgeArea,
    ProcessingJob,
    ProcessingJobStatus,
)
from app.jobs import worker as worker_module
from app.jobs.service import claim_next_job, record_failure
from app.jobs.worker import process_claim, run_worker
from app.processing.extraction import InvalidSourcePDF, TransientProcessingError

OWNER_HEADERS = {"Authorization": "Bearer workos_owner_sub"}
MEMBER_HEADERS = {"Authorization": "Bearer workos_member_sub"}


def create_processing_document(db_session, identities, *, max_attempts: int = 4):
    area_id = uuid4()
    document_id = uuid4()
    area = KnowledgeArea(
        id=area_id,
        workspace_id=identities.workspace.id,
        name=f"area-{area_id}",
        normalized_name=f"area-{area_id}",
        created_by=identities.owner.id,
    )
    document = Document(
        id=document_id,
        workspace_id=identities.workspace.id,
        knowledge_area_id=area_id,
        uploaded_by=identities.owner.id,
        original_filename="job-test.pdf",
        storage_key=f"documents/{document_id}.pdf",
        content_type="application/pdf",
        byte_size=120,
        page_count=1,
        sha256="a" * 64,
        status=DocumentStatus.UPLOADED.value,
    )
    now = datetime.now(UTC)
    job = ProcessingJob(
        id=uuid4(),
        workspace_id=identities.workspace.id,
        document_id=document_id,
        job_type="PROCESS_DOCUMENT",
        status=ProcessingJobStatus.QUEUED.value,
        attempt_count=0,
        max_attempts=max_attempts,
        available_at=now - timedelta(seconds=1),
    )
    db_session.add_all([area, document, job])
    db_session.commit()
    return document, job


def test_claim_sets_processing_state_and_only_one_worker_gets_the_job(
    db_session, identities
) -> None:
    document, job = create_processing_document(db_session, identities)
    settings = Settings(_env_file=None, app_env="test")
    now = datetime.now(UTC)

    claim = claim_next_job(db_session, "worker-a", settings, now)

    assert claim is not None
    assert claim.job_id == job.id
    assert claim.attempt_count == 1
    assert db_session.get(ProcessingJob, job.id).status == ProcessingJobStatus.RUNNING
    assert db_session.get(Document, document.id).status == DocumentStatus.PROCESSING
    assert claim.lease_token == db_session.get(ProcessingJob, job.id).lease_token
    assert claim_next_job(db_session, "worker-b", settings, now) is None


def test_expired_lease_is_reclaimed_with_new_token_and_attempt(db_session, identities) -> None:
    document, job = create_processing_document(db_session, identities)
    settings = Settings(_env_file=None, app_env="test")
    now = datetime.now(UTC)
    first = claim_next_job(db_session, "crashed-worker", settings, now)
    assert first is not None

    job = db_session.get(ProcessingJob, job.id)
    job.locked_at = now - timedelta(seconds=settings.job_lease_seconds + 1)
    db_session.commit()
    second = claim_next_job(db_session, "recovery-worker", settings, now)

    assert second is not None
    assert second.attempt_count == 2
    assert second.lease_token != first.lease_token
    assert db_session.get(Document, document.id).status == DocumentStatus.PROCESSING


def test_shutdown_during_processing_leaves_job_for_expired_lease_recovery(
    db_session, identities
) -> None:
    document, job = create_processing_document(db_session, identities)
    settings = Settings(_env_file=None, app_env="test")
    now = datetime.now(UTC)
    claim = claim_next_job(db_session, "api-worker", settings, now)
    assert claim is not None
    stop_event = threading.Event()

    class ShutdownStream(BytesIO):
        def read(self, *args):
            block = super().read(*args)
            if block:
                stop_event.set()
            return block

    class Storage:
        def get_file(self, _key):
            return ShutdownStream(b"pdf-data"), 8

    process_claim(
        lambda: db_session,
        Storage(),
        settings,
        claim,
        embedding_provider=object(),
        stop_event=stop_event,
    )

    job = db_session.get(ProcessingJob, job.id)
    document = db_session.get(Document, document.id)
    assert job.status == ProcessingJobStatus.RUNNING
    assert job.lease_token == claim.lease_token
    assert document.status == DocumentStatus.PROCESSING

    job.locked_at = now - timedelta(seconds=settings.job_lease_seconds + 1)
    db_session.commit()
    recovered = claim_next_job(db_session, "restarted-api-worker", settings, now)
    assert recovered is not None
    assert recovered.job_id == claim.job_id
    assert recovered.lease_token != claim.lease_token
    assert recovered.attempt_count == 2


def test_worker_processes_jobs_serially_in_one_worker_loop(monkeypatch) -> None:
    settings = Settings(_env_file=None, app_env="test", worker_poll_interval_seconds=1)
    stop_event = threading.Event()
    claims = [
        SimpleNamespace(job_id=uuid4(), attempt_count=1),
        SimpleNamespace(job_id=uuid4(), attempt_count=1),
    ]
    call_count = 0
    active = 0
    peak_active = 0

    def next_claim(*_args):
        return claims.pop(0) if claims else None

    def process(*_args, **_kwargs):
        nonlocal call_count, active, peak_active
        active += 1
        peak_active = max(peak_active, active)
        call_count += 1
        active -= 1
        if call_count == 2:
            stop_event.set()

    monkeypatch.setattr(worker_module, "claim_next_job", next_claim)
    monkeypatch.setattr(worker_module, "process_claim", process)
    run_worker(
        session_factory=lambda: nullcontext(),
        storage=object(),
        settings=settings,
        stop_event=stop_event,
        worker_id="single-thread",
        embedding_provider=object(),
    )

    assert call_count == 2
    assert peak_active == 1


def test_retryable_and_permanent_failures_update_job_and_document(
    db_session, identities, monkeypatch
):
    document, job = create_processing_document(db_session, identities)
    settings = Settings(_env_file=None, app_env="test")
    now = datetime.now(UTC)
    monkeypatch.setattr("app.jobs.service.random.uniform", lambda _a, _b: 1.0)
    claim = claim_next_job(db_session, "worker-a", settings, now)
    assert claim is not None

    record_failure(db_session, claim, TransientProcessingError(), settings, now)
    job = db_session.get(ProcessingJob, job.id)
    document = db_session.get(Document, document.id)
    assert job.status == ProcessingJobStatus.RETRYABLE_FAILURE
    assert job.available_at == now + timedelta(seconds=30)
    assert document.status == DocumentStatus.PROCESSING
    assert document.processing_error_code == "processing_temporarily_unavailable"

    claim = claim_next_job(db_session, "worker-a", settings, now + timedelta(seconds=31))
    assert claim is not None and claim.attempt_count == 2
    record_failure(db_session, claim, InvalidSourcePDF(), settings, now + timedelta(seconds=31))
    assert job.status == ProcessingJobStatus.PERMANENT_FAILURE
    assert document.status == DocumentStatus.FAILED
    assert document.processing_error_code == "invalid_source_pdf"


def test_expired_last_lease_fails_document_without_exceeding_attempt_limit(db_session, identities):
    document, job = create_processing_document(db_session, identities, max_attempts=1)
    settings = Settings(_env_file=None, app_env="test")
    now = datetime.now(UTC)
    claim = claim_next_job(db_session, "worker-a", settings, now)
    assert claim is not None
    job = db_session.get(ProcessingJob, job.id)
    job.locked_at = now - timedelta(seconds=settings.job_lease_seconds + 1)
    db_session.commit()

    assert claim_next_job(db_session, "worker-b", settings, now) is None
    assert job.status == ProcessingJobStatus.PERMANENT_FAILURE
    assert db_session.get(Document, document.id).status == DocumentStatus.FAILED
    assert job.attempt_count == 1


def test_only_owner_can_retry_failed_document_processing(client, identities, db_session):
    document, job = create_processing_document(db_session, identities)
    document.status = DocumentStatus.FAILED.value
    job.status = ProcessingJobStatus.PERMANENT_FAILURE.value
    job.finished_at = datetime.now(UTC)
    db_session.commit()
    path = f"/api/v1/workspaces/{identities.workspace.id}/documents/{document.id}/retry"

    assert client.post(path, headers=MEMBER_HEADERS).status_code == 403
    foreign_path = f"/api/v1/workspaces/{identities.other.id}/documents/{document.id}/retry"
    assert (
        client.post(
            foreign_path,
            headers={"Authorization": "Bearer workos_outsider_sub"},
        ).status_code
        == 404
    )
    response = client.post(path, headers=OWNER_HEADERS)

    assert response.status_code == 200
    assert response.json()["status"] == DocumentStatus.UPLOADED
    assert job.status == ProcessingJobStatus.QUEUED
    assert job.attempt_count == 0
    assert job.last_error_code is None
