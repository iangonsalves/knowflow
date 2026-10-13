"""Authenticated workspace search API."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import get_session
from app.embeddings.factory import get_embedding_provider
from app.embeddings.provider import EmbeddingConfigurationError, EmbeddingError, EmbeddingProvider
from app.identity.dependencies import CurrentUser
from app.search.schemas import SearchRequest, SearchResponse
from app.search.service import retrieve
from app.tenancy.policies import require_workspace_access

router = APIRouter(tags=["search"])


@router.post("/workspaces/{workspace_id}/search", response_model=SearchResponse)
def search_workspace(
    workspace_id: UUID,
    payload: SearchRequest,
    current_user: CurrentUser,
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> SearchResponse:
    require_workspace_access(session, current_user, workspace_id)
    if len(payload.query) > settings.max_question_chars:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "query_too_long",
                "message": (
                    f"Search queries must be {settings.max_question_chars} characters or fewer"
                ),
            },
        )
    if payload.limit is not None and payload.limit > settings.max_search_results:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "result_limit_too_high",
                "message": f"Search result limit cannot exceed {settings.max_search_results}",
            },
        )
    try:
        provider: EmbeddingProvider = get_embedding_provider(settings)
        results = retrieve(
            session,
            workspace_id=workspace_id,
            request=payload,
            settings=settings,
            embedding_provider=provider,
        )
    except EmbeddingConfigurationError as error:
        raise HTTPException(
            status_code=503,
            detail={"code": error.code, "message": error.safe_message},
        ) from error
    except EmbeddingError as error:
        raise HTTPException(
            status_code=503 if error.retryable else 502,
            detail={"code": error.code, "message": error.safe_message},
        ) from error
    return SearchResponse(query=payload.query, results=results)
