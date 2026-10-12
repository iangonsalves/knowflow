"""Small document lifecycle helpers shared by areas and documents."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import Document


def purge_expired_tombstones(session: Session, workspace_id: UUID) -> int:
    """Purge completed cleanup tombstones after their configured retention period."""
    now = datetime.now(UTC)
    expired_ids = session.scalars(
        select(Document.id).where(
            Document.workspace_id == workspace_id,
            Document.deleted_at.is_not(None),
            Document.cleanup_completed_at.is_not(None),
            Document.purge_after <= now,
        )
    ).all()
    if not expired_ids:
        return 0
    session.execute(delete(Document).where(Document.id.in_(expired_ids)))
    session.commit()
    return len(expired_ids)


def mark_cleanup_complete(document: Document) -> None:
    now = datetime.now(UTC)
    document.cleanup_completed_at = now
    document.cleanup_error_code = None
    document.purge_after = now + timedelta(days=get_settings().tombstone_retention_days)


def cleanup_retry_expired(document: Document) -> bool:
    if document.deleted_at is None:
        return False
    retry_seconds = get_settings().cleanup_retry_window_hours * 60 * 60
    deleted_at = document.deleted_at
    if deleted_at.tzinfo is None:
        deleted_at = deleted_at.replace(tzinfo=UTC)
    return datetime.now(UTC) - deleted_at >= timedelta(seconds=retry_seconds)
