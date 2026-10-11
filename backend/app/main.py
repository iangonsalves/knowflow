"""FastAPI application entry point for the KnowFlow modular monolith."""

from fastapi import FastAPI

from app.api.health import router as health_router
from app.core.config import get_settings

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="KnowFlow backend foundation. Product APIs are added in later approved milestones.",
)
app.include_router(health_router)
