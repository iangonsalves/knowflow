"""Polling worker entrypoint for the modular-monolith backend image."""

import logging
import signal
import socket
import threading
import time
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings, get_settings
from app.db.models import Document
from app.db.session import SessionLocal
from app.documents.storage import ObjectStorage, get_object_storage
from app.embeddings.factory import get_embedding_provider
from app.embeddings.provider import (
    EmbeddingConfigurationError,
    EmbeddingError,
    EmbeddingProvider,
    EmbeddingTransientError,
)
from app.jobs.service import ClaimedJob, claim_next_job, record_failure, renew_lease
from app.processing.chunking import chunk_pages
from app.processing.extraction import (
    EmbeddingProcessingFailure,
    LeaseLost,
    ProcessingError,
    ProcessingTimedOut,
    TransientProcessingError,
    extract_pdf_pages,
)
from app.processing.persistence import EmbeddedChunk, persist_processed_output

logger = logging.getLogger("knowflow.worker")
POLL_INTERVAL_SECONDS = 2


def process_claim(
    session_factory: sessionmaker[Session],
    storage: ObjectStorage,
    settings: Settings,
    claim: ClaimedJob,
    embedding_provider: EmbeddingProvider | None = None,
) -> None:
    started = time.monotonic()
    last_heartbeat = started

    def heartbeat_if_due(force: bool = False) -> None:
        nonlocal last_heartbeat
        now = time.monotonic()
        if now - started >= settings.processing_job_timeout_seconds:
            raise ProcessingTimedOut
        if force or now - last_heartbeat >= settings.job_heartbeat_seconds:
            with session_factory() as heartbeat_session:
                renew_lease(heartbeat_session, claim)
            last_heartbeat = now

    try:
        with session_factory() as session:
            document = session.scalar(
                select(Document).where(
                    Document.workspace_id == claim.workspace_id,
                    Document.id == claim.document_id,
                    Document.deleted_at.is_(None),
                )
            )
        if document is None:
            return

        pages = extract_pdf_pages(document, storage, heartbeat=heartbeat_if_due)
        chunks = chunk_pages(
            pages,
            chunk_size_chars=settings.chunk_size_chars,
            overlap_chars=settings.chunk_overlap_chars,
            progress=heartbeat_if_due,
        )
        embedding_provider = embedding_provider or get_embedding_provider(settings)
        embeddings = embedding_provider.embed(
            [chunk.text for chunk in chunks],
            purpose="document",
            progress=heartbeat_if_due,
        )
        if len(embeddings.vectors) != len(chunks):
            raise EmbeddingProcessingFailure(
                "invalid_embedding_response",
                "The embedding provider returned an invalid response.",
                False,
            )
        if (
            embeddings.model != settings.embedding_model_identifier
            or embeddings.dimensions != settings.embedding_dimensions
        ):
            raise EmbeddingProcessingFailure(
                "embedding_configuration_mismatch",
                "Embedding configuration does not match the database schema.",
                False,
            )
        embedded_chunks = [
            EmbeddedChunk(
                chunk, vector, embeddings.model, embeddings.version, embeddings.dimensions
            )
            for chunk, vector in zip(chunks, embeddings.vectors, strict=True)
        ]
        heartbeat_if_due()
        persist_processed_output(session_factory, claim, pages, embedded_chunks)
    except LeaseLost:
        logger.info("Worker lease was lost for job %s", claim.job_id)
    except ProcessingError as error:
        _record_failure_safely(session_factory, claim, error, settings)
    except EmbeddingError as error:
        _record_failure_safely(
            session_factory,
            claim,
            EmbeddingProcessingFailure(error.code, error.safe_message, error.retryable),
            settings,
        )
    except Exception as error:
        logger.error(
            "Unexpected processing error for job %s (error_type=%s)",
            claim.job_id,
            type(error).__name__,
        )
        _record_failure_safely(
            session_factory,
            claim,
            TransientProcessingError(),
            settings,
            log_error_type=type(error).__name__,
        )


def _record_failure_safely(
    session_factory: sessionmaker[Session],
    claim: ClaimedJob,
    error: ProcessingError,
    settings: Settings,
    log_error_type: str | None = None,
) -> None:
    try:
        with session_factory() as session:
            record_failure(session, claim, error, settings)
    except Exception as error:
        logger.error(
            "Could not persist failure for job %s; lease recovery will retry (error_type=%s)",
            claim.job_id,
            log_error_type or type(error).__name__,
        )


def run_worker(
    session_factory: sessionmaker[Session] = SessionLocal,
    storage: ObjectStorage | None = None,
    settings: Settings | None = None,
    stop_event: threading.Event | None = None,
    worker_id: str | None = None,
) -> None:
    settings = settings or get_settings()
    storage = storage or get_object_storage()
    stop_event = stop_event or threading.Event()
    worker_id = worker_id or f"{socket.gethostname()}:{uuid4()}"
    logger.info("Document worker started (worker_id=%s)", worker_id)
    embedding_provider: EmbeddingProvider | None = None

    while not stop_event.is_set():
        if embedding_provider is None:
            try:
                # Load/download before claiming work; cold-start model setup must not
                # consume a job lease or cause another worker to reclaim the job.
                embedding_provider = get_embedding_provider(settings)
            except EmbeddingTransientError as error:
                logger.warning("Local embedding model is not ready (error=%s)", error.code)
                stop_event.wait(POLL_INTERVAL_SECONDS)
                continue
            except EmbeddingConfigurationError:
                logger.exception("Local embedding model configuration is invalid")
                raise
        try:
            with session_factory() as session:
                claim = claim_next_job(session, worker_id, settings)
            if claim is None:
                stop_event.wait(POLL_INTERVAL_SECONDS)
                continue
            logger.info("Processing job %s (attempt=%s)", claim.job_id, claim.attempt_count)
            process_claim(session_factory, storage, settings, claim, embedding_provider)
        except Exception as error:
            logger.error("Worker loop encountered an error (error_type=%s)", type(error).__name__)
            stop_event.wait(POLL_INTERVAL_SECONDS)

    logger.info("Document worker stopped (worker_id=%s)", worker_id)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    stop_event = threading.Event()
    signal.signal(signal.SIGTERM, lambda _signum, _frame: stop_event.set())
    signal.signal(signal.SIGINT, lambda _signum, _frame: stop_event.set())
    run_worker(stop_event=stop_event)


if __name__ == "__main__":
    main()
