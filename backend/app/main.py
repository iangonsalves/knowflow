"""FastAPI application entry point for the KnowFlow modular monolith."""

from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError

from app.api.health import router as health_router
from app.core.config import get_settings
from app.core.errors import http_exception_handler, validation_exception_handler
from app.identity.router import router as identity_router
from app.tenancy.router import router as tenancy_router

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="KnowFlow backend foundation. Product APIs are added in later approved milestones.",
)
app.include_router(health_router)
app.include_router(identity_router, prefix="/api/v1")
app.include_router(tenancy_router, prefix="/api/v1")
app.add_exception_handler(HTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)


@app.middleware("http")
async def add_request_id(request: Request, call_next):
    request.state.request_id = str(uuid4())
    response = await call_next(request)
    response.headers["X-Request-ID"] = request.state.request_id
    return response
