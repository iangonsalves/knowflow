"""Authenticated workspace search API."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.rate_limits import process_rate_limiter
from app.db.session import get_session
from app.embeddings.factory import get_embedding_provider
from app.embeddings.provider import EmbeddingConfigurationError, EmbeddingError, EmbeddingProvider
from app.identity.dependencies import CurrentUser
from app.search.evidence import select_evidence
from app.search.schemas import AskResponse, SearchRequest, SearchResponse
from app.search.service import retrieve
from app.tenancy.policies import require_workspace_access

router = APIRouter(tags=["search"])


def _retrieve_for_workspace(
    workspace_id: UUID,
    payload: SearchRequest,
    session: Session,
    settings: Settings,
    user_id: str,
):
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
    retry_after = process_rate_limiter.consume_question(
        user_id,
        per_minute=settings.rate_limit_questions_per_minute,
        burst=settings.rate_limit_question_burst,
    )
    if retry_after is not None:
        raise HTTPException(
            status_code=429,
            detail={
                "code": "question_rate_limit",
                "message": "Too many questions. Try again shortly.",
            },
            headers={"Retry-After": str(retry_after)},
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
    return results


@router.post("/workspaces/{workspace_id}/search", response_model=SearchResponse)
def search_workspace(
    workspace_id: UUID,
    payload: SearchRequest,
    current_user: CurrentUser,
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> SearchResponse:
    require_workspace_access(session, current_user, workspace_id)
    results = _retrieve_for_workspace(
        workspace_id, payload, session, settings, str(current_user.id)
    )
    return SearchResponse(query=payload.query, results=results)


@router.post("/workspaces/{workspace_id}/ask", response_model=AskResponse)
def ask_workspace(
    workspace_id: UUID,
    payload: SearchRequest,
    current_user: CurrentUser,
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AskResponse:
    """Return selected source evidence; this endpoint does not generate answers."""
    require_workspace_access(session, current_user, workspace_id)
    results = _retrieve_for_workspace(
        workspace_id, payload, session, settings, str(current_user.id)
    )
    selected = select_evidence(
        results,
        question=payload.query,
        workspace_id=str(workspace_id),
        settings=settings,
    )
    messages = {
        "evidence_found": (
            "Found substantive source passages relevant to your question. Review the sources."
        ),
        "weak_evidence": (
            "No strong evidence was found. These passages may be related to your question; "
            "review the sources."
        ),
        "no_evidence": (
            "No relevant source evidence was found in ready documents in this workspace."
        ),
    }
    return AskResponse(
        question=payload.query,
        evidence_state=selected.state,
        message=messages[selected.state],
        best_evidence=selected.best,
        supporting_evidence=selected.supporting,
        related_evidence=selected.related,
    )
