"""PostgreSQL-only integration test for row-lock/skip behavior used by workers."""

import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, delete, inspect
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.models import (
    Document,
    DocumentStatus,
    KnowledgeArea,
    MembershipRole,
    ProcessingJob,
    ProcessingJobStatus,
    User,
    Workspace,
    WorkspaceMembership,
)
from app.jobs.service import lock_next_eligible_job


def test_concurrent_workers_skip_a_job_locked_by_another_transaction() -> None:
    database_url = os.getenv("KNOWFLOW_DATABASE_URL")
    if not database_url or not database_url.startswith("postgresql"):
        pytest.skip("PostgreSQL concurrency test requires KNOWFLOW_DATABASE_URL")
    engine = create_engine(database_url)
    if not inspect(engine).has_table("processing_jobs"):
        engine.dispose()
        pytest.skip("Apply database migrations before running the PostgreSQL worker test")

    user_id = uuid4()
    workspace_id = uuid4()
    area_id = uuid4()
    document_id = uuid4()
    job_id = uuid4()
    slug = f"worker-lock-{workspace_id}"
    now = datetime.now(UTC)

    try:
        with Session(engine) as setup:
            user = User(
                id=user_id,
                auth_subject=f"worker-lock-{user_id}",
                email=f"worker-{user_id}@example.test",
                email_verified=True,
            )
            workspace = Workspace(
                id=workspace_id, name="Worker lock test", slug=slug, created_by=user_id
            )
            area = KnowledgeArea(
                id=area_id,
                workspace_id=workspace_id,
                name="Test",
                normalized_name="test",
                created_by=user_id,
            )
            document = Document(
                id=document_id,
                workspace_id=workspace_id,
                knowledge_area_id=area_id,
                uploaded_by=user_id,
                original_filename="worker-lock.pdf",
                storage_key=f"documents/{document_id}.pdf",
                content_type="application/pdf",
                byte_size=20,
                page_count=1,
                sha256="a" * 64,
                status=DocumentStatus.UPLOADED.value,
            )
            job = ProcessingJob(
                id=job_id,
                workspace_id=workspace_id,
                document_id=document_id,
                job_type="PROCESS_DOCUMENT",
                status=ProcessingJobStatus.QUEUED.value,
                attempt_count=0,
                max_attempts=4,
                available_at=now - timedelta(seconds=1),
            )
            membership = WorkspaceMembership(
                workspace_id=workspace_id,
                user_id=user_id,
                role=MembershipRole.OWNER.value,
                created_by=user_id,
            )
            setup.add_all([user, workspace, membership, area, document, job])
            setup.commit()

        settings = Settings(_env_file=None, app_env="test")
        with Session(engine) as first_worker, Session(engine) as second_worker:
            first_worker.begin()
            first_claim = lock_next_eligible_job(
                first_worker, settings, now, workspace_id=workspace_id
            )
            assert first_claim is not None and first_claim.id == job_id

            second_worker.begin()
            second_claim = lock_next_eligible_job(
                second_worker, settings, now, workspace_id=workspace_id
            )
            assert second_claim is None
            second_worker.rollback()
            first_worker.rollback()
    finally:
        with Session(engine) as cleanup:
            cleanup.execute(delete(ProcessingJob).where(ProcessingJob.id == job_id))
            cleanup.execute(delete(Document).where(Document.id == document_id))
            cleanup.execute(delete(KnowledgeArea).where(KnowledgeArea.id == area_id))
            cleanup.execute(
                delete(WorkspaceMembership).where(WorkspaceMembership.workspace_id == workspace_id)
            )
            cleanup.execute(delete(Workspace).where(Workspace.id == workspace_id))
            cleanup.execute(delete(User).where(User.id == user_id))
            cleanup.commit()
        engine.dispose()
