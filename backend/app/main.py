"""FastAPI application entry point for the KnowFlow modular monolith."""

import logging
import threading
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError

from app.api.health import router as health_router
from app.core.config import get_settings
from app.core.errors import http_exception_handler, validation_exception_handler
from app.documents.router import router as documents_router
from app.documents.storage import get_object_storage
from app.embeddings.factory import (
    clear_shared_embedding_provider,
    initialize_shared_embedding_provider,
)
from app.identity.router import router as identity_router
from app.jobs.worker import register_in_process_wakeup, run_worker
from app.knowledge_areas.router import router as knowledge_areas_router
from app.search.router import router as search_router
from app.tenancy.router import router as tenancy_router

settings = get_settings()
logger = logging.getLogger("knowflow.api")


@asynccontextmanager
async def lifespan(application: FastAPI):
    """Optionally run the durable worker loop inside the API process."""
    worker_thread: threading.Thread | None = None
    stop_event: threading.Event | None = None
    wakeup_event: threading.Event | None = None
    application.state.embedding_provider_ready = not settings.run_worker_in_api
    application.state.embedding_provider = None
    application.state.worker_thread = None

    try:
        if settings.run_worker_in_api:
            # Initialize before accepting traffic. API search/Ask and the worker receive
            # the exact same provider object and ONNX session.
            embedding_provider = initialize_shared_embedding_provider(settings)
            application.state.embedding_provider = embedding_provider
            application.state.embedding_provider_ready = True
            stop_event = threading.Event()
            wakeup_event = threading.Event()
            register_in_process_wakeup(wakeup_event)
            worker_thread = threading.Thread(
                target=run_worker,
                kwargs={
                    "settings": settings,
                    "storage": get_object_storage(),
                    "stop_event": stop_event,
                    "embedding_provider": embedding_provider,
                    "wakeup_event": wakeup_event,
                },
                name="knowflow-document-worker",
                daemon=True,
            )
            application.state.worker_thread = worker_thread
            worker_thread.start()
            logger.info(
                "In-process durable worker started (poll_interval_seconds=%s)",
                settings.worker_poll_interval_seconds,
            )
        yield
    finally:
        if stop_event is not None:
            stop_event.set()
        if wakeup_event is not None:
            wakeup_event.set()
        if worker_thread is not None:
            worker_thread.join(timeout=settings.worker_shutdown_timeout_seconds)
            if worker_thread.is_alive():
                logger.warning(
                    "Worker did not stop within %s seconds; active lease will recover after expiry",
                    settings.worker_shutdown_timeout_seconds,
                )
            else:
                logger.info("In-process durable worker stopped")
        if settings.run_worker_in_api:
            register_in_process_wakeup(None)
            clear_shared_embedding_provider()

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="KnowFlow identity, workspace, document, hybrid retrieval, and evidence APIs.",
    lifespan=lifespan,
)
app.include_router(health_router)
app.include_router(identity_router, prefix="/api/v1")
app.include_router(tenancy_router, prefix="/api/v1")
app.include_router(knowledge_areas_router, prefix="/api/v1")
app.include_router(documents_router, prefix="/api/v1")
app.include_router(search_router, prefix="/api/v1")
app.add_exception_handler(HTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)


@app.middleware("http")
async def add_request_id(request: Request, call_next):
    request.state.request_id = str(uuid4())
    response = await call_next(request)
    response.headers["X-Request-ID"] = request.state.request_id
    return response
