from hashlib import sha256
from io import BytesIO
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pdf_helpers import make_text_pdf
from pypdf import PdfReader, PdfWriter
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.db.models import (
    Document,
    DocumentChunk,
    DocumentPage,
    DocumentStatus,
    KnowledgeArea,
    ProcessingJob,
    ProcessingJobStatus,
)
from app.documents.storage import ObjectStorageError, StoredObjectNotFound
from app.embeddings.provider import EmbeddingSet, EmbeddingTransientError
from app.jobs.service import claim_next_job, record_failure
from app.jobs.worker import process_claim
from app.processing.chunking import PreparedChunk, chunk_pages
from app.processing.extraction import (
    EncryptedSourcePDF,
    ExtractedPage,
    InvalidSourcePDF,
    MissingSourceObject,
    NoExtractableText,
    SourceIntegrityError,
    TransientProcessingError,
    extract_pdf_pages,
    normalize_page_text,
)
from app.processing.persistence import EmbeddedChunk, persist_processed_output


class MemoryStorage:
    def __init__(self, objects: dict[str, bytes] | None = None) -> None:
        self.objects = objects or {}

    def get_file(self, key: str):
        if key not in self.objects:
            raise StoredObjectNotFound(key)
        body = self.objects[key]
        return BytesIO(body), len(body)

    def put_file(self, *_args, **_kwargs) -> None:
        raise NotImplementedError

    def delete_file(self, *_args, **_kwargs) -> None:
        raise NotImplementedError


class DeterministicEmbeddingProvider:
    def __init__(self, dimensions: int = 384) -> None:
        self.dimensions = dimensions

    def embed(self, texts: list[str], *, purpose: str, progress=None) -> EmbeddingSet:
        base = [0.0] * self.dimensions
        if texts:
            base[0] = 1.0 if purpose == "query" else 0.8
        return EmbeddingSet(
            "intfloat/e5-small-v2@ffb93f3bd4047442299a41ebb6fa998a38507c52",
            "v1",
            self.dimensions,
            [base[:] for _ in texts],
        )


def source_document(pdf: bytes, *, page_count: int = 1):
    return SimpleNamespace(
        storage_key="source.pdf",
        byte_size=len(pdf),
        sha256=sha256(pdf).hexdigest(),
        page_count=page_count,
    )


def test_extracts_each_page_normalizes_text_and_preserves_page_numbers() -> None:
    pdf = make_text_pdf(
        page_texts=["HR leave policy\n\nCarry forward up to 5 days.", "IT security policy"]
    )
    pages = extract_pdf_pages(
        source_document(pdf, page_count=2), MemoryStorage({"source.pdf": pdf})
    )

    assert [page.page_number for page in pages] == [1, 2]
    assert pages[0].text == "HR leave policy\n\nCarry forward up to 5 days."
    assert pages[1].text == "IT security policy"
    assert all(len(page.content_hash) == 64 for page in pages)


def test_normalization_is_stable_and_preserves_paragraphs() -> None:
    value = "  Alpha\t beta  \r\n\r\n\r\n Gamma\u00ad  "
    assert normalize_page_text(value) == "Alpha beta\n\nGamma"


def test_extraction_rejects_no_text_malformed_missing_and_corrupt_sources() -> None:
    empty_pdf = make_text_pdf(page_texts=[""])
    with pytest.raises(NoExtractableText):
        extract_pdf_pages(source_document(empty_pdf), MemoryStorage({"source.pdf": empty_pdf}))

    malformed = b"%PDF-1.7 not a valid PDF"
    with pytest.raises(InvalidSourcePDF):
        extract_pdf_pages(source_document(malformed), MemoryStorage({"source.pdf": malformed}))

    valid = make_text_pdf()
    writer = PdfWriter()
    writer.append(PdfReader(BytesIO(valid)))
    writer.encrypt("test-password")
    encrypted_stream = BytesIO()
    writer.write(encrypted_stream)
    encrypted = encrypted_stream.getvalue()
    with pytest.raises(EncryptedSourcePDF):
        extract_pdf_pages(source_document(encrypted), MemoryStorage({"source.pdf": encrypted}))

    with pytest.raises(MissingSourceObject):
        extract_pdf_pages(source_document(valid), MemoryStorage())

    with pytest.raises(SourceIntegrityError):
        extract_pdf_pages(
            SimpleNamespace(
                storage_key="source.pdf",
                byte_size=len(valid),
                sha256="0" * 64,
                page_count=1,
            ),
            MemoryStorage({"source.pdf": valid}),
        )


def test_storage_transport_error_is_classified_as_retryable() -> None:
    class UnavailableStorage(MemoryStorage):
        def get_file(self, _key: str):
            raise ObjectStorageError("network unavailable")

    pdf = make_text_pdf()

    with pytest.raises(TransientProcessingError):
        extract_pdf_pages(source_document(pdf), UnavailableStorage())


def test_chunking_is_deterministic_ordered_and_keeps_page_provenance() -> None:
    pages = [
        ExtractedPage(1, "First sentence. Second sentence.\n\nThird paragraph here.", "a" * 64),
        ExtractedPage(2, "Fourth page has another passage for context.", "b" * 64),
    ]
    first_run = chunk_pages(pages, chunk_size_chars=32, overlap_chars=7)
    second_run = chunk_pages(pages, chunk_size_chars=32, overlap_chars=7)

    assert first_run == second_run
    assert [chunk.chunk_index for chunk in first_run] == list(range(len(first_run)))
    assert first_run[0].page_start == first_run[0].page_end == 1
    assert first_run[-1].page_start == first_run[-1].page_end == 2
    assert all(len(chunk.content_hash) == 64 for chunk in first_run)
    assert all(len(chunk.text) <= 32 for chunk in first_run)
    assert any("Second sentence" in chunk.text for chunk in first_run)
    assert any("Third paragraph" in chunk.text for chunk in first_run)


def test_chunking_rejects_invalid_size_and_overlap() -> None:
    page = [ExtractedPage(1, "Some source text", "a" * 64)]
    with pytest.raises(ValueError):
        chunk_pages(page, chunk_size_chars=0, overlap_chars=0)
    with pytest.raises(ValueError):
        chunk_pages(page, chunk_size_chars=10, overlap_chars=10)


def test_worker_persists_ordered_page_chunks_and_ready_atomically(db_session, identities) -> None:
    pdf = make_text_pdf(
        page_texts=[
            "Page one includes the annual leave policy and carry forward details.",
            "Page two describes manager approval and the request process.",
        ]
    )
    storage = MemoryStorage({"documents/worker-test.pdf": pdf})
    area_id = uuid4()
    document_id = uuid4()
    area = KnowledgeArea(
        id=area_id,
        workspace_id=identities.workspace.id,
        name="Processing",
        normalized_name="processing",
        created_by=identities.owner.id,
    )
    document = Document(
        id=document_id,
        workspace_id=identities.workspace.id,
        knowledge_area_id=area_id,
        uploaded_by=identities.owner.id,
        original_filename="worker-test.pdf",
        storage_key="documents/worker-test.pdf",
        content_type="application/pdf",
        byte_size=len(pdf),
        page_count=2,
        sha256=sha256(pdf).hexdigest(),
        status=DocumentStatus.UPLOADED.value,
    )
    job = ProcessingJob(
        workspace_id=identities.workspace.id,
        document_id=document_id,
        job_type="PROCESS_DOCUMENT",
        status=ProcessingJobStatus.QUEUED.value,
        attempt_count=0,
        max_attempts=4,
    )
    db_session.add_all([area, document, job])
    db_session.commit()

    settings = SimpleNamespace(
        processing_job_timeout_seconds=600,
        job_heartbeat_seconds=30,
        job_lease_seconds=90,
        worker_max_attempts=4,
        worker_retry_backoff_seconds=[30, 120, 600],
        chunk_size_chars=32,
        chunk_overlap_chars=6,
        embedding_model_identifier="intfloat/e5-small-v2@ffb93f3bd4047442299a41ebb6fa998a38507c52",
        embedding_version="v1",
        embedding_dimensions=384,
    )
    claim = claim_next_job(db_session, "test-worker", settings)
    assert claim is not None
    session_factory = sessionmaker(bind=db_session.get_bind(), expire_on_commit=False)

    process_claim(session_factory, storage, settings, claim, DeterministicEmbeddingProvider())
    db_session.expire_all()

    assert db_session.get(Document, document_id).status == DocumentStatus.READY
    assert db_session.get(ProcessingJob, job.id).status == ProcessingJobStatus.SUCCEEDED
    pages = db_session.scalars(
        select(DocumentPage)
        .where(DocumentPage.document_id == document_id)
        .order_by(DocumentPage.page_number)
    ).all()
    chunks = db_session.scalars(
        select(DocumentChunk)
        .where(DocumentChunk.document_id == document_id)
        .order_by(DocumentChunk.chunk_index)
    ).all()
    assert [page.page_number for page in pages] == [1, 2]
    assert "annual leave policy" in pages[0].text
    assert chunks
    assert [chunk.chunk_index for chunk in chunks] == list(range(len(chunks)))
    assert all(chunk.workspace_id == identities.workspace.id for chunk in chunks)
    assert all(chunk.page_start <= chunk.page_end for chunk in chunks)
    assert all(len(chunk.embedding) == 384 for chunk in chunks)
    assert all(
        chunk.embedding_model
        == "intfloat/e5-small-v2@ffb93f3bd4047442299a41ebb6fa998a38507c52"
        for chunk in chunks
    )
    assert all(chunk.embedding_version == "v1" for chunk in chunks)
    assert all(chunk.embedded_at is not None for chunk in chunks)

    # A stale duplicate delivery cannot replace completed data or duplicate rows.
    page_count = len(pages)
    chunk_count = len(chunks)
    process_claim(session_factory, storage, settings, claim, DeterministicEmbeddingProvider())
    assert (
        len(
            db_session.scalars(
                select(DocumentPage).where(DocumentPage.document_id == document_id)
            ).all()
        )
        == page_count
    )
    assert (
        len(
            db_session.scalars(
                select(DocumentChunk).where(DocumentChunk.document_id == document_id)
            ).all()
        )
        == chunk_count
    )


def test_no_text_pdf_fails_cleanly_without_page_or_chunk_output(db_session, identities) -> None:
    pdf = make_text_pdf(page_texts=[""])
    storage = MemoryStorage({"documents/no-text.pdf": pdf})
    area = KnowledgeArea(
        workspace_id=identities.workspace.id,
        name="No text",
        normalized_name="no text",
        created_by=identities.owner.id,
    )
    document = Document(
        workspace_id=identities.workspace.id,
        knowledge_area=area,
        uploaded_by=identities.owner.id,
        original_filename="no-text.pdf",
        storage_key="documents/no-text.pdf",
        content_type="application/pdf",
        byte_size=len(pdf),
        page_count=1,
        sha256=sha256(pdf).hexdigest(),
        status=DocumentStatus.UPLOADED.value,
    )
    job = ProcessingJob(
        workspace_id=identities.workspace.id,
        document=document,
        job_type="PROCESS_DOCUMENT",
        status=ProcessingJobStatus.QUEUED.value,
        attempt_count=0,
        max_attempts=4,
    )
    db_session.add_all([area, document, job])
    db_session.commit()
    settings = SimpleNamespace(
        processing_job_timeout_seconds=600,
        job_heartbeat_seconds=30,
        job_lease_seconds=90,
        worker_max_attempts=4,
        worker_retry_backoff_seconds=[30, 120, 600],
        chunk_size_chars=100,
        chunk_overlap_chars=10,
        embedding_model_identifier="intfloat/e5-small-v2@ffb93f3bd4047442299a41ebb6fa998a38507c52",
        embedding_version="v1",
        embedding_dimensions=384,
    )
    claim = claim_next_job(db_session, "test-worker", settings)
    session_factory = sessionmaker(bind=db_session.get_bind(), expire_on_commit=False)

    process_claim(session_factory, storage, settings, claim, DeterministicEmbeddingProvider())
    db_session.expire_all()

    assert db_session.get(Document, document.id).status == DocumentStatus.FAILED
    assert db_session.get(Document, document.id).processing_error_code == "no_extractable_text"
    assert db_session.get(ProcessingJob, job.id).status == ProcessingJobStatus.PERMANENT_FAILURE
    assert (
        db_session.scalars(
            select(DocumentPage).where(DocumentPage.document_id == document.id)
        ).all()
        == []
    )
    assert (
        db_session.scalars(
            select(DocumentChunk).where(DocumentChunk.document_id == document.id)
        ).all()
        == []
    )


def test_embedding_provider_failure_never_marks_document_ready(db_session, identities) -> None:
    pdf = make_text_pdf(page_texts=["Annual leave entitlement is 25 days."])
    storage = MemoryStorage({"documents/provider-error.pdf": pdf})
    area = KnowledgeArea(
        workspace_id=identities.workspace.id,
        name="Provider error",
        normalized_name="provider error",
        created_by=identities.owner.id,
    )
    document = Document(
        workspace_id=identities.workspace.id,
        knowledge_area=area,
        uploaded_by=identities.owner.id,
        original_filename="provider-error.pdf",
        storage_key="documents/provider-error.pdf",
        content_type="application/pdf",
        byte_size=len(pdf),
        page_count=1,
        sha256=sha256(pdf).hexdigest(),
        status=DocumentStatus.UPLOADED.value,
    )
    job = ProcessingJob(
        workspace_id=identities.workspace.id,
        document=document,
        job_type="PROCESS_DOCUMENT",
        status=ProcessingJobStatus.QUEUED.value,
        attempt_count=0,
        max_attempts=4,
    )
    db_session.add_all([area, document, job])
    db_session.commit()
    settings = SimpleNamespace(
        processing_job_timeout_seconds=600,
        job_heartbeat_seconds=30,
        job_lease_seconds=90,
        worker_max_attempts=4,
        worker_retry_backoff_seconds=[30, 120, 600],
        chunk_size_chars=1800,
        chunk_overlap_chars=240,
    )
    claim = claim_next_job(db_session, "test-worker", settings)
    assert claim is not None

    class FailingProvider:
        def embed(self, _texts, *, purpose, progress=None):
            raise EmbeddingTransientError

    session_factory = sessionmaker(bind=db_session.get_bind(), expire_on_commit=False)
    process_claim(session_factory, storage, settings, claim, FailingProvider())
    db_session.expire_all()

    assert db_session.get(Document, document.id).status == DocumentStatus.PROCESSING
    assert db_session.get(ProcessingJob, job.id).status == ProcessingJobStatus.RETRYABLE_FAILURE
    assert (
        db_session.scalars(
            select(DocumentChunk).where(DocumentChunk.document_id == document.id)
        ).all()
        == []
    )


def test_cross_workspace_chunk_reference_is_rejected_by_composite_foreign_key(
    db_session, identities
) -> None:
    from sqlalchemy.exc import IntegrityError

    area = KnowledgeArea(
        workspace_id=identities.workspace.id,
        name="Tenant guard",
        normalized_name="tenant guard",
        created_by=identities.owner.id,
    )
    document = Document(
        workspace_id=identities.workspace.id,
        knowledge_area=area,
        uploaded_by=identities.owner.id,
        original_filename="tenant.pdf",
        storage_key="documents/tenant.pdf",
        content_type="application/pdf",
        byte_size=10,
        page_count=1,
        sha256="a" * 64,
        status=DocumentStatus.READY.value,
    )
    db_session.add_all([area, document])
    db_session.commit()
    other_workspace_area = KnowledgeArea(
        workspace_id=identities.other.id,
        name="Other tenant area",
        normalized_name="other tenant area",
        created_by=identities.outsider.id,
    )
    db_session.add(other_workspace_area)
    db_session.flush()
    db_session.add(
        DocumentChunk(
            workspace_id=identities.other.id,
            document_id=document.id,
            chunk_index=0,
            text="A cross-workspace canary",
            page_start=1,
            page_end=1,
            content_hash="b" * 64,
        )
    )
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_chunk_persistence_failure_rolls_back_pages_and_ready_state(db_session, identities) -> None:
    pdf = make_text_pdf()
    area = KnowledgeArea(
        workspace_id=identities.workspace.id,
        name="Atomic output",
        normalized_name="atomic output",
        created_by=identities.owner.id,
    )
    document = Document(
        workspace_id=identities.workspace.id,
        knowledge_area=area,
        uploaded_by=identities.owner.id,
        original_filename="atomic.pdf",
        storage_key="documents/atomic.pdf",
        content_type="application/pdf",
        byte_size=len(pdf),
        page_count=1,
        sha256=sha256(pdf).hexdigest(),
        status=DocumentStatus.UPLOADED.value,
    )
    job = ProcessingJob(
        workspace_id=identities.workspace.id,
        document=document,
        job_type="PROCESS_DOCUMENT",
        status=ProcessingJobStatus.QUEUED.value,
        attempt_count=0,
        max_attempts=4,
    )
    db_session.add_all([area, document, job])
    db_session.commit()
    settings = SimpleNamespace(
        processing_job_timeout_seconds=600,
        job_heartbeat_seconds=30,
        job_lease_seconds=90,
        worker_max_attempts=4,
        worker_retry_backoff_seconds=[30, 120, 600],
    )
    claim = claim_next_job(db_session, "test-worker", settings)
    session_factory = sessionmaker(bind=db_session.get_bind(), expire_on_commit=False)

    with pytest.raises(IntegrityError):
        persist_processed_output(
            session_factory,
            claim,
            [ExtractedPage(1, "Extracted text", "a" * 64)],
            [
                EmbeddedChunk(
                    PreparedChunk(0, "Invalid page range", 2, 1, "b" * 64),
                    [0.0] * 384,
                    "intfloat/e5-small-v2@ffb93f3bd4047442299a41ebb6fa998a38507c52",
                    "v1",
                    384,
                )
            ],
        )
    db_session.expire_all()

    assert db_session.get(Document, document.id).status == DocumentStatus.PROCESSING
    assert db_session.get(ProcessingJob, job.id).status == ProcessingJobStatus.RUNNING
    assert (
        db_session.scalars(
            select(DocumentPage).where(DocumentPage.document_id == document.id)
        ).all()
        == []
    )
    assert (
        db_session.scalars(
            select(DocumentChunk).where(DocumentChunk.document_id == document.id)
        ).all()
        == []
    )
    record_failure(db_session, claim, TransientProcessingError(), settings)
    assert db_session.get(ProcessingJob, job.id).status == ProcessingJobStatus.RETRYABLE_FAILURE
    assert db_session.get(Document, document.id).status == DocumentStatus.PROCESSING
