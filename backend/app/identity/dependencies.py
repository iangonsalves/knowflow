"""FastAPI dependency for WorkOS bearer authentication and user mapping."""

from typing import Annotated

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt.exceptions import PyJWKClientConnectionError
from sqlalchemy.orm import Session

from app.db.models import User
from app.db.session import get_session
from app.identity.service import resolve_authenticated_user
from app.identity.workos import (
    WorkOSConfigurationError,
    verify_workos_access_token,
)

bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    session: Annotated[Session, Depends(get_session)],
) -> User:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=401,
            detail={"code": "authentication_required", "message": "Sign in to continue"},
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        claims = verify_workos_access_token(credentials.credentials)
    except WorkOSConfigurationError as error:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "identity_provider_not_configured",
                "message": "Identity service is not configured",
            },
        ) from error
    except PyJWKClientConnectionError as error:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "identity_provider_unavailable",
                "message": "Identity service is temporarily unavailable",
            },
        ) from error
    except jwt.PyJWTError as error:
        raise HTTPException(
            status_code=401,
            detail={
                "code": "invalid_access_token",
                "message": "Access token is invalid or expired",
            },
            headers={"WWW-Authenticate": "Bearer"},
        ) from error
    return resolve_authenticated_user(session, claims["sub"])


CurrentUser = Annotated[User, Depends(get_current_user)]
