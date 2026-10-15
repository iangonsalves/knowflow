"""Liveness and database readiness endpoints for local operation and deployment."""

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import get_settings
from app.db.session import engine

router = APIRouter(tags=["health"])


@router.get("/health/live", summary="Check that the API process is running")
def liveness() -> dict[str, str]:
    return {"status": "alive"}


@router.get("/health/ready", summary="Check database, pgvector, and required runtime readiness")
def readiness(request: Request) -> dict[str, str]:
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
            vector_extension = connection.execute(
                text("SELECT extname FROM pg_extension WHERE extname = 'vector'")
            ).scalar_one_or_none()
    except SQLAlchemyError as error:
        raise HTTPException(status_code=503, detail="Database is not ready") from error

    if vector_extension is None:
        raise HTTPException(status_code=503, detail="Database migrations are not applied")

    result = {"status": "ready", "database": "ready", "vector_extension": "ready"}
    settings = get_settings()
    if settings.run_worker_in_api:
        provider_ready = bool(getattr(request.app.state, "embedding_provider_ready", False))
        worker_thread = getattr(request.app.state, "worker_thread", None)
        worker_ready = worker_thread is not None and worker_thread.is_alive()
        if not provider_ready or not worker_ready:
            raise HTTPException(status_code=503, detail="Backend processing runtime is not ready")
        result["embedding_provider"] = "ready"
        result["worker"] = "ready"

    return result
