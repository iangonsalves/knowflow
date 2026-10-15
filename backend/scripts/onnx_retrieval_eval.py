"""Seed sample PDFs and inspect PostgreSQL M5/M6 retrieval for an embedding provider."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from pypdf import PdfReader
from sqlalchemy import create_engine, delete
from sqlalchemy.orm import sessionmaker

from app.core.config import Settings
from app.db.models import (
    Document,
    DocumentChunk,
    DocumentPage,
    DocumentStatus,
    KnowledgeArea,
    MembershipRole,
    User,
    Workspace,
    WorkspaceMembership,
)
from app.embeddings.factory import get_embedding_provider
from app.embeddings.provider import EmbeddingProvider
from app.embeddings.sentence_transformers import SentenceTransformerEmbeddingProvider
from app.processing.chunking import chunk_pages
from app.processing.extraction import ExtractedPage, normalize_page_text
from app.search.evidence import select_evidence
from app.search.schemas import SearchRequest
from app.search.service import retrieve


def _provider_for_evaluation(settings: Settings, reference_model: Path) -> EmbeddingProvider:
    if settings.embedding_backend == "onnx":
        return get_embedding_provider(settings)

    # The compare image contains the pinned snapshot at this path so the
    # PyTorch baseline is evaluated offline against the exact same revision.
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer(str(reference_model), device="cpu", local_files_only=True)
    return SentenceTransformerEmbeddingProvider(
        model_name=settings.embedding_model,
        revision=settings.embedding_revision,
        dimensions=settings.embedding_dimensions,
        version=settings.embedding_version,
        cache_dir=settings.embedding_cache_dir,
        device="cpu",
        batch_size=settings.embedding_batch_size,
        model_loader=lambda *_args: model,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--backend",
        choices=("onnx", "sentence_transformers"),
        default="onnx",
    )
    parser.add_argument(
        "--reference-model",
        type=Path,
        default=Path("/opt/reference-e5"),
        help="Pinned local E5 snapshot path used by the Sentence Transformers baseline",
    )
    parser.add_argument(
        "--backup-diagnostic",
        action="store_true",
        help="Print full M5 candidates and M6 evidence selection for the backup question only",
    )
    args = parser.parse_args()
    database_url = os.environ.get("KNOWFLOW_DATABASE_URL")
    if not database_url:
        raise SystemExit("KNOWFLOW_DATABASE_URL is required")
    if not database_url.startswith("postgresql"):
        raise SystemExit("This evaluation requires PostgreSQL with pgvector and FTS")
    samples = Path(os.environ.get("KNOWFLOW_EVAL_SAMPLES", "/samples"))
    settings = Settings(
        _env_file=None, app_env="test", embedding_backend=args.backend
    )
    provider = _provider_for_evaluation(settings, args.reference_model)
    engine = create_engine(database_url, pool_pre_ping=True)
    Session = sessionmaker(engine, expire_on_commit=False)
    workspace_id, user_id = uuid4(), uuid4()
    now = datetime.now(UTC)
    evidence_records: list[dict] = []
    seeded_document_ids = []

    try:
        with Session.begin() as session:
            user = User(
                id=user_id,
                auth_subject=f"m8-1-eval-{user_id}",
                email=f"m8-1-eval-{user_id}@example.invalid",
                email_verified=True,
                display_name="M8.1 Retrieval Evaluation",
            )
            session.add(user)
            session.flush()
            workspace = Workspace(
                id=workspace_id,
                name="M8.1 Evaluation",
                slug=f"m8-1-eval-{workspace_id.hex[:12]}",
                created_by=user_id,
            )
            session.add(workspace)
            session.add(
                WorkspaceMembership(
                    workspace_id=workspace_id,
                    user_id=user_id,
                    role=MembershipRole.OWNER.value,
                    created_by=user_id,
                )
            )
            for filename in sorted(samples.glob("*.pdf")):
                pdf_bytes = filename.read_bytes()
                pages = [
                    ExtractedPage(
                        page_number=index,
                        text=normalize_page_text(page.extract_text() or ""),
                        content_hash=hashlib.sha256(
                            normalize_page_text(page.extract_text() or "").encode("utf-8")
                        ).hexdigest(),
                    )
                    for index, page in enumerate(PdfReader(str(filename)).pages, start=1)
                ]
                chunks = chunk_pages(
                    pages,
                    chunk_size_chars=settings.chunk_size_chars,
                    overlap_chars=settings.chunk_overlap_chars,
                )
                vectors = provider.embed([chunk.text for chunk in chunks], purpose="document")
                area_id, document_id = uuid4(), uuid4()
                area = KnowledgeArea(
                    id=area_id,
                    workspace_id=workspace_id,
                    name=filename.stem.replace("_", " ")[:120],
                    normalized_name=filename.stem.replace("_", " ").lower()[:120],
                    created_by=user_id,
                )
                session.add(area)
                session.flush()
                document = Document(
                    id=document_id,
                    workspace_id=workspace_id,
                    knowledge_area_id=area_id,
                    uploaded_by=user_id,
                    original_filename=filename.name,
                    storage_key=f"m8-1-eval/{document_id}.pdf",
                    content_type="application/pdf",
                    byte_size=len(pdf_bytes),
                    page_count=len(pages),
                    sha256=hashlib.sha256(pdf_bytes).hexdigest(),
                    status=DocumentStatus.READY.value,
                )
                session.add(document)
                session.flush()
                session.add_all(
                    [
                        DocumentPage(
                            workspace_id=workspace_id,
                            document_id=document_id,
                            page_number=page.page_number,
                            text=page.text,
                            content_hash=page.content_hash,
                        )
                        for page in pages
                    ]
                )
                session.add_all(
                    [
                        DocumentChunk(
                            workspace_id=workspace_id,
                            document_id=document_id,
                            chunk_index=chunk.chunk_index,
                            text=chunk.text,
                            page_start=chunk.page_start,
                            page_end=chunk.page_end,
                            content_hash=chunk.content_hash,
                            embedding=vector,
                            embedding_model=vectors.model,
                            embedding_version=vectors.version,
                            embedding_dimensions=vectors.dimensions,
                            embedded_at=now,
                        )
                        for chunk, vector in zip(chunks, vectors.vectors, strict=True)
                    ]
                )
                seeded_document_ids.append(document_id)

        questions = [
            ("How much vacation time do staff get?", "25 working days", True),
            ("What is the maternity leave entitlement?", "25 working days", False),
            ("How many days can employees work remotely?", "up to two days per week", True),
            ("How quickly must a security incident be reported?", "security incident", True),
            ("How often are backups performed?", "backed up at least daily", True),
        ]
        if args.backup_diagnostic:
            questions = [("How often are backups performed?", "", False)]
        annual_leave_results = None
        with Session() as session:
            for question, expected_text, must_be_strong in questions:
                results = retrieve(
                    session,
                    workspace_id=workspace_id,
                    request=SearchRequest(query=question),
                    settings=settings,
                    embedding_provider=provider,
                )
                selected = select_evidence(
                    results,
                    question=question,
                    workspace_id=str(workspace_id),
                    settings=settings,
                )
                all_items = [selected.best, *selected.supporting, *selected.related]
                snippets = [item.text for item in all_items if item is not None]
                retrieval_details = [
                    {
                        "retrieval_rank": result.rank,
                        "chunk_id": str(result.chunk_id),
                        "document_id": str(result.document_id),
                        "filename": result.document_filename,
                        "page_start": result.page_start,
                        "page_end": result.page_end,
                        "keyword_rank": result.keyword_rank,
                        "keyword_score": result.keyword_score,
                        "vector_rank": result.vector_rank,
                        "vector_similarity": result.vector_similarity,
                        "rrf_score": result.rrf_score,
                        "text": result.text,
                    }
                    for result in results
                ]
                output = {
                    "provider": settings.embedding_backend,
                    "question": question,
                    "state": selected.state,
                    "best_evidence": selected.best.model_dump(mode="json")
                    if selected.best
                    else None,
                    "supporting_count": len(selected.supporting),
                    "related_count": len(selected.related),
                    "supporting_evidence": [
                        item.model_dump(mode="json") for item in selected.supporting
                    ],
                    "related_evidence": [
                        item.model_dump(mode="json") for item in selected.related
                    ],
                    "retrieved_results": retrieval_details,
                    "daily_backup_chunks": [
                        item for item in retrieval_details
                        if "backed up at least daily" in item["text"].casefold()
                    ],
                    "quarterly_restoration_chunks": [
                        item for item in retrieval_details
                        if "quarterly" in item["text"].casefold()
                        and "restor" in item["text"].casefold()
                    ],
                    "expected_text_observed": any(
                        expected_text.casefold() in s.casefold() for s in snippets
                    ),
                }
                evidence_records.append(output)
                print(json.dumps(output, indent=2, default=str))
                if not args.backup_diagnostic and must_be_strong and (
                    selected.state != "evidence_found"
                    or selected.best is None
                    or expected_text.casefold() not in selected.best.text.casefold()
                ):
                    raise AssertionError(f"Expected strong passage not selected for: {question}")
                if (
                    not args.backup_diagnostic
                    and not must_be_strong
                    and selected.state == "evidence_found"
                ):
                    raise AssertionError(f"Unsupported question classified as strong: {question}")
            if not args.backup_diagnostic:
                annual_leave_results = retrieve(
                    session,
                    workspace_id=workspace_id,
                    request=SearchRequest(query="How much annual leave do employees receive?"),
                    settings=settings,
                    embedding_provider=provider,
                )

        if args.backup_diagnostic:
            print(
                json.dumps(
                    {
                        "diagnostic_complete": True,
                        "provider": settings.embedding_backend,
                        "model": settings.embedding_model_identifier,
                        "embedding_version": settings.embedding_storage_version,
                        "dimension": settings.embedding_dimensions,
                    },
                    indent=2,
                )
            )
            return

        vacation = evidence_records[0]
        if not vacation["best_evidence"] or vacation["best_evidence"]["page_start"] != 2:
            raise AssertionError("Vacation-time evidence did not preserve expected PDF page 2")
        if not vacation["best_evidence"]["source_path"].endswith("?page=2"):
            raise AssertionError("The evidence source link did not preserve page provenance")
        if not annual_leave_results or not any(
            result.keyword_rank is not None for result in annual_leave_results
        ):
            raise AssertionError("The exact annual-leave query produced no PostgreSQL FTS results")
        if not any(result.vector_rank is not None for result in annual_leave_results):
            raise AssertionError("The annual-leave query produced no pgvector results")
        if not any(
            result.keyword_rank is not None and result.vector_rank is not None
            for result in annual_leave_results
        ):
            raise AssertionError("No candidate was fused from both PostgreSQL FTS and pgvector")
        print(
            json.dumps(
                {
                    "overall": "PASS",
                    "workspace_id": str(workspace_id),
                    "model": settings.embedding_model_identifier,
                    "provider": settings.embedding_backend,
                    "dimension": settings.embedding_dimensions,
                    "keyword_vector_rrf_fields_present": bool(vacation["top_retrieval"])
                    and any(item["vector_rank"] for item in vacation["top_retrieval"])
                    and any(
                        result.keyword_rank is not None and result.vector_rank is not None
                        for result in annual_leave_results
                    ),
                    "provenance_page": vacation["best_evidence"]["page_start"],
                },
                indent=2,
            )
        )
    finally:
        with Session.begin() as session:
            for document_id in seeded_document_ids:
                session.execute(
                    delete(DocumentChunk).where(DocumentChunk.document_id == document_id)
                )
                session.execute(delete(DocumentPage).where(DocumentPage.document_id == document_id))
                session.execute(delete(Document).where(Document.id == document_id))
            session.execute(delete(KnowledgeArea).where(KnowledgeArea.workspace_id == workspace_id))
            session.execute(
                delete(WorkspaceMembership).where(WorkspaceMembership.workspace_id == workspace_id)
            )
            session.execute(delete(Workspace).where(Workspace.id == workspace_id))
            session.execute(delete(User).where(User.id == user_id))
        engine.dispose()


if __name__ == "__main__":
    main()
