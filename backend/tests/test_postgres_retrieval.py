"""Real PostgreSQL/pgvector/FTS retrieval integration tests."""

import json
import os
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, delete, inspect
from sqlalchemy.orm import Session
from test_search import FakeProvider

from app.core.config import Settings
from app.db.models import (
    Document,
    DocumentChunk,
    DocumentStatus,
    KnowledgeArea,
    MembershipRole,
    User,
    Workspace,
    WorkspaceMembership,
)
from app.embeddings.provider import EmbeddingSet
from app.search.evidence import select_evidence
from app.search.schemas import SearchRequest
from app.search.service import retrieve

RETRIEVAL_EVAL = json.loads(
    (Path(__file__).parent / "fixtures" / "retrieval_eval.json").read_text()
)


class EvaluationProvider(FakeProvider):
    """Deterministic query vectors so each fixture query ranks its expected row first."""

    def embed(self, texts, *, purpose, progress=None):
        if purpose != "query":
            return super().embed(texts, purpose=purpose, progress=progress)
        query = texts[0].lower()
        if "remote" in query:
            vector = [0.9, 0.1] + [0.0] * 382
        elif "security" in query or "incident" in query:
            vector = [0.6, 0.4] + [0.0] * 382
        elif "probation" in query:
            vector = [0.8, 0.2] + [0.0] * 382
        elif "carry" in query or "unused" in query:
            vector = [0.9, 0.1] + [0.0] * 382
        elif "vacation" in query:
            vector = [1.0, 0.0] + [0.0] * 382
        elif "parental" in query:
            vector = [0.5, 0.5] + [0.0] * 382
        else:
            vector = [1.0, 0.0] + [0.0] * 382
        return EmbeddingSet(
            "intfloat/e5-small-v2@ffb93f3bd4047442299a41ebb6fa998a38507c52",
            "v1",
            self.dimensions,
            [vector],
        )


def test_postgres_hybrid_search_uses_fts_vector_ready_filter_and_page_provenance() -> None:
    database_url = os.getenv("KNOWFLOW_DATABASE_URL")
    if not database_url or not database_url.startswith("postgresql"):
        pytest.skip("PostgreSQL retrieval test requires KNOWFLOW_DATABASE_URL")
    engine = create_engine(database_url)
    inspector = inspect(engine)
    if not inspector.has_table("document_chunks"):
        engine.dispose()
        pytest.skip("Apply migrations before running PostgreSQL retrieval tests")
    if "embedding" not in {column["name"] for column in inspector.get_columns("document_chunks")}:
        engine.dispose()
        pytest.skip("Upgrade to the M5 migration before running PostgreSQL retrieval tests")

    user_id, workspace_id, area_id, doc_id = uuid4(), uuid4(), uuid4(), uuid4()
    deleted_doc_id, processing_doc_id = uuid4(), uuid4()
    other_workspace_id, other_area_id, other_doc_id = uuid4(), uuid4(), uuid4()
    try:
        with Session(engine) as session:
            user = User(
                id=user_id,
                auth_subject=f"search-{user_id}",
                email=f"search-{user_id}@example.test",
                email_verified=True,
            )
            workspace = Workspace(
                id=workspace_id,
                name="Search tenant",
                slug=f"search-{workspace_id}",
                created_by=user_id,
            )
            other_workspace = Workspace(
                id=other_workspace_id,
                name="Other tenant",
                slug=f"other-search-{other_workspace_id}",
                created_by=user_id,
            )
            session.add_all([user, workspace, other_workspace])
            session.flush()
            session.add_all(
                [
                    WorkspaceMembership(
                        workspace_id=workspace_id,
                        user_id=user_id,
                        role=MembershipRole.OWNER.value,
                        created_by=user_id,
                    ),
                    KnowledgeArea(
                        id=area_id,
                        workspace_id=workspace_id,
                        name="HR",
                        normalized_name="hr",
                        created_by=user_id,
                    ),
                    KnowledgeArea(
                        id=other_area_id,
                        workspace_id=other_workspace_id,
                        name="Other",
                        normalized_name="other",
                        created_by=user_id,
                    ),
                ]
            )
            session.flush()
            documents = [
                Document(
                    id=doc_id,
                    workspace_id=workspace_id,
                    knowledge_area_id=area_id,
                    uploaded_by=user_id,
                    original_filename="Annual Leave Policy.pdf",
                    storage_key=f"search/{doc_id}",
                    content_type="application/pdf",
                    byte_size=100,
                    page_count=6,
                    sha256="a" * 64,
                    status=DocumentStatus.READY.value,
                ),
                Document(
                    id=deleted_doc_id,
                    workspace_id=workspace_id,
                    knowledge_area_id=area_id,
                    uploaded_by=user_id,
                    original_filename="Deleted Policy.pdf",
                    storage_key=f"search/deleted-{doc_id}",
                    content_type="application/pdf",
                    byte_size=100,
                    page_count=1,
                    sha256="b" * 64,
                    status=DocumentStatus.READY.value,
                    deleted_at=__import__("datetime").datetime.now(__import__("datetime").UTC),
                ),
                Document(
                    id=processing_doc_id,
                    workspace_id=workspace_id,
                    knowledge_area_id=area_id,
                    uploaded_by=user_id,
                    original_filename="Not Ready.pdf",
                    storage_key=f"search/not-ready-{doc_id}",
                    content_type="application/pdf",
                    byte_size=100,
                    page_count=1,
                    sha256="c" * 64,
                    status=DocumentStatus.PROCESSING.value,
                ),
                Document(
                    id=other_doc_id,
                    workspace_id=other_workspace_id,
                    knowledge_area_id=other_area_id,
                    uploaded_by=user_id,
                    original_filename="Other tenant.pdf",
                    storage_key=f"search/{other_doc_id}",
                    content_type="application/pdf",
                    byte_size=100,
                    page_count=2,
                    sha256="d" * 64,
                    status=DocumentStatus.READY.value,
                ),
            ]
            session.add_all(documents)
            session.flush()
            session.add_all(
                [
                    DocumentChunk(
                        workspace_id=workspace_id,
                        document_id=doc_id,
                        chunk_index=0,
                        text=(
                            "Full time employees receive 25 working days of paid annual leave "
                            "each year."
                        ),
                        page_start=2,
                        page_end=2,
                        content_hash="e" * 64,
                        embedding=[1.0] + [0.0] * 383,
                        embedding_model="intfloat/e5-small-v2@ffb93f3bd4047442299a41ebb6fa998a38507c52",
                        embedding_version="v1",
                        embedding_dimensions=384,
                        embedded_at=__import__("datetime").datetime.now(__import__("datetime").UTC),
                    ),
                    DocumentChunk(
                        workspace_id=workspace_id,
                        document_id=doc_id,
                        chunk_index=1,
                        text=(
                            "Employees may carry forward up to 5 unused annual leave days into "
                            "the next calendar year."
                        ),
                        page_start=2,
                        page_end=2,
                        content_hash="1" * 64,
                        embedding=[0.9, 0.1] + [0.0] * 382,
                        embedding_model="intfloat/e5-small-v2@ffb93f3bd4047442299a41ebb6fa998a38507c52",
                        embedding_version="v1",
                        embedding_dimensions=384,
                        embedded_at=__import__("datetime").datetime.now(__import__("datetime").UTC),
                    ),
                    DocumentChunk(
                        workspace_id=workspace_id,
                        document_id=doc_id,
                        chunk_index=2,
                        text="The standard probation period is six months.",
                        page_start=3,
                        page_end=3,
                        content_hash="2" * 64,
                        embedding=[0.8, 0.2] + [0.0] * 382,
                        embedding_model="intfloat/e5-small-v2@ffb93f3bd4047442299a41ebb6fa998a38507c52",
                        embedding_version="v1",
                        embedding_dimensions=384,
                        embedded_at=__import__("datetime").datetime.now(__import__("datetime").UTC),
                    ),
                    DocumentChunk(
                        workspace_id=workspace_id,
                        document_id=doc_id,
                        chunk_index=3,
                        text=(
                            "Eligible employees may work remotely for up to two days per week, "
                            "subject to line-manager approval and business requirements."
                        ),
                        page_start=3,
                        page_end=3,
                        content_hash="5" * 64,
                        embedding=[0.7, 0.3] + [0.0] * 382,
                        embedding_model="intfloat/e5-small-v2@ffb93f3bd4047442299a41ebb6fa998a38507c52",
                        embedding_version="v1",
                        embedding_dimensions=384,
                        embedded_at=__import__("datetime").datetime.now(__import__("datetime").UTC),
                    ),
                    DocumentChunk(
                        workspace_id=workspace_id,
                        document_id=doc_id,
                        chunk_index=4,
                        text=(
                            "Suspected information-security incidents must be reported to IT "
                            "Security within one hour of discovery."
                        ),
                        page_start=4,
                        page_end=4,
                        content_hash="6" * 64,
                        embedding=[0.6, 0.4] + [0.0] * 382,
                        embedding_model="intfloat/e5-small-v2@ffb93f3bd4047442299a41ebb6fa998a38507c52",
                        embedding_version="v1",
                        embedding_dimensions=384,
                        embedded_at=__import__("datetime").datetime.now(__import__("datetime").UTC),
                    ),
                    DocumentChunk(
                        workspace_id=workspace_id,
                        document_id=doc_id,
                        chunk_index=5,
                        text=(
                            "Quick Reference for Testing. Question: How many remote-working "
                            "days are allowed?"
                        ),
                        page_start=6,
                        page_end=6,
                        content_hash="7" * 64,
                        embedding=[1.0] + [0.0] * 383,
                        embedding_model="intfloat/e5-small-v2@ffb93f3bd4047442299a41ebb6fa998a38507c52",
                        embedding_version="v1",
                        embedding_dimensions=384,
                        embedded_at=__import__("datetime").datetime.now(__import__("datetime").UTC),
                    ),
                    DocumentChunk(
                        workspace_id=other_workspace_id,
                        document_id=other_doc_id,
                        chunk_index=0,
                        text="Other tenant secret about annual leave.",
                        page_start=1,
                        page_end=1,
                        content_hash="f" * 64,
                        embedding=[1.0] + [0.0] * 383,
                        embedding_model="intfloat/e5-small-v2@ffb93f3bd4047442299a41ebb6fa998a38507c52",
                        embedding_version="v1",
                        embedding_dimensions=384,
                        embedded_at=__import__("datetime").datetime.now(__import__("datetime").UTC),
                    ),
                    DocumentChunk(
                        workspace_id=workspace_id,
                        document_id=deleted_doc_id,
                        chunk_index=0,
                        text=(
                            "Full time employees receive 25 working days of paid annual leave "
                            "each year."
                        ),
                        page_start=2,
                        page_end=2,
                        content_hash="3" * 64,
                        embedding=[1.0] + [0.0] * 383,
                        embedding_model="intfloat/e5-small-v2@ffb93f3bd4047442299a41ebb6fa998a38507c52",
                        embedding_version="v1",
                        embedding_dimensions=384,
                        embedded_at=__import__("datetime").datetime.now(__import__("datetime").UTC),
                    ),
                    DocumentChunk(
                        workspace_id=workspace_id,
                        document_id=processing_doc_id,
                        chunk_index=0,
                        text=(
                            "Full time employees receive 25 working days of paid annual leave "
                            "each year."
                        ),
                        page_start=2,
                        page_end=2,
                        content_hash="4" * 64,
                        embedding=[1.0] + [0.0] * 383,
                        embedding_model="intfloat/e5-small-v2@ffb93f3bd4047442299a41ebb6fa998a38507c52",
                        embedding_version="v1",
                        embedding_dimensions=384,
                        embedded_at=__import__("datetime").datetime.now(__import__("datetime").UTC),
                    ),
                ]
            )
            session.commit()

        with Session(engine) as session:
            results = retrieve(
                session,
                workspace_id=workspace_id,
                request=SearchRequest(query=RETRIEVAL_EVAL[0]["query"], limit=6),
                settings=Settings(_env_file=None, app_env="test"),
                embedding_provider=EvaluationProvider(),
            )
            assert results
            # M5 returns relevance-ranked candidates, not evidence-quality-ranked
            # answers. Synthetic vectors can tie a reference/question chunk with
            # the policy passage, so assert retrieval inclusion here; M6's
            # selection below owns the best-evidence expectation.
            annual_leave_candidate = next(
                (
                    result
                    for result in results
                    if result.document_filename == "Annual Leave Policy.pdf"
                    and "25 working days" in result.text
                    and result.page_start == result.page_end == 2
                ),
                None,
            )
            assert annual_leave_candidate is not None
            assert annual_leave_candidate.vector_rank is not None
            assert annual_leave_candidate.vector_similarity is not None
            assert annual_leave_candidate.vector_similarity > Settings(
                _env_file=None, app_env="test"
            ).evidence_minimum_vector_similarity
            assert all(result.document_id == doc_id for result in results)
            selected = select_evidence(
                results,
                question=RETRIEVAL_EVAL[0]["query"],
                workspace_id=str(workspace_id),
                settings=Settings(_env_file=None, app_env="test"),
            )
            assert selected.best is not None
            assert "25 working days" in selected.best.text
            assert selected.best.document_id == doc_id
            assert selected.best.page_start == 2

            # Validate the lexical path with an explicit term query separately.
            # The natural-language evaluation query is primarily checking the
            # semantic path; RRF does not guarantee that the top hybrid result
            # is rank 1 in both independent candidate lists.
            lexical_results = retrieve(
                session,
                workspace_id=workspace_id,
                request=SearchRequest(query="employees receive", limit=6),
                settings=Settings(_env_file=None, app_env="test"),
                embedding_provider=EvaluationProvider(),
            )
            assert any(
                item.document_id == doc_id
                and item.keyword_rank is not None
                and "25 working days" in item.text
                for item in lexical_results
            )

            for evaluation in RETRIEVAL_EVAL:
                evaluated = retrieve(
                    session,
                    workspace_id=workspace_id,
                    request=SearchRequest(query=evaluation["query"], limit=6),
                    settings=Settings(_env_file=None, app_env="test"),
                    embedding_provider=EvaluationProvider(),
                )
                assert any(evaluation["expected_text"] in item.text for item in evaluated)
                assert any(item.page_start == evaluation["page"] for item in evaluated)
                if "remote" in evaluation["query"].lower():
                    # The fixture deliberately includes a question-like quick
                    # reference candidate. It may rank highly in M5, but M6
                    # must prefer the declarative policy passage below.
                    assert any(
                        "Question: How many remote-working days are allowed?" in item.text
                        for item in evaluated
                    )
                evidence = select_evidence(
                    evaluated,
                    question=evaluation["query"],
                    workspace_id=str(workspace_id),
                    settings=Settings(_env_file=None, app_env="test"),
                )
                assert evidence.best is not None
                assert evaluation["expected_text"] in evidence.best.text
                assert evidence.best.page_start == evaluation["page"]

            unsupported_question = "What is the maternity leave entitlement?"
            unsupported_results = retrieve(
                session,
                workspace_id=workspace_id,
                request=SearchRequest(query=unsupported_question, limit=6),
                settings=Settings(_env_file=None, app_env="test"),
                embedding_provider=EvaluationProvider(),
            )
            unsupported = select_evidence(
                unsupported_results,
                question=unsupported_question,
                workspace_id=str(workspace_id),
                settings=Settings(_env_file=None, app_env="test"),
            )
            assert unsupported.state in {"weak_evidence", "no_evidence"}
            assert unsupported.best is None
            assert unsupported.supporting == []
            if unsupported.state == "no_evidence":
                assert unsupported.related == []

            with pytest.raises(HTTPException) as inaccessible_area:
                retrieve(
                    session,
                    workspace_id=workspace_id,
                    request=SearchRequest(
                        query="annual leave", knowledge_area_id=other_area_id, limit=6
                    ),
                    settings=Settings(_env_file=None, app_env="test"),
                    embedding_provider=EvaluationProvider(),
                )
            assert inaccessible_area.value.status_code == 404
    finally:
        with Session(engine) as session:
            session.execute(
                delete(DocumentChunk).where(
                    DocumentChunk.workspace_id.in_([workspace_id, other_workspace_id])
                )
            )
            session.execute(
                delete(Document).where(
                    Document.workspace_id.in_([workspace_id, other_workspace_id])
                )
            )
            session.execute(
                delete(WorkspaceMembership).where(
                    WorkspaceMembership.workspace_id.in_([workspace_id, other_workspace_id])
                )
            )
            session.execute(
                delete(KnowledgeArea).where(
                    KnowledgeArea.workspace_id.in_([workspace_id, other_workspace_id])
                )
            )
            session.execute(
                delete(Workspace).where(Workspace.id.in_([workspace_id, other_workspace_id]))
            )
            session.execute(delete(User).where(User.id == user_id))
            session.commit()
        engine.dispose()
