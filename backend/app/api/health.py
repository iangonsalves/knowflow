"""Liveness and database readiness endpoints for local operation and deployment."""

from fastapi import APIRouter, HTTPException
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.db.session import engine

router = APIRouter(tags=["health"])


@router.get("/health/live", summary="Check that the API process is running")
def liveness() -> dict[str, str]:
    return {"status": "alive"}


@router.get("/health/ready", summary="Check database and pgvector readiness")
def readiness() -> dict[str, str]:
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

    return {"status": "ready", "database": "ready", "vector_extension": "ready"}
