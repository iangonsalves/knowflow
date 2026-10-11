"""WorkOS access-token verification and trusted profile lookup."""

from functools import lru_cache
from typing import Any
from urllib.parse import quote

import httpx
import jwt
from jwt import PyJWKClient
from jwt.exceptions import PyJWKClientConnectionError

from app.core.config import Settings, get_settings


class WorkOSConfigurationError(RuntimeError):
    """Required WorkOS server configuration is missing."""


class WorkOSDirectoryError(RuntimeError):
    """The WorkOS directory API could not return a verified profile."""


class WorkOSEmailNotVerifiedError(WorkOSDirectoryError):
    """A WorkOS identity has not verified its email address."""


def workos_issuer(settings: Settings) -> str:
    if settings.workos_issuer:
        return settings.workos_issuer.strip().rstrip(",")
    if not settings.workos_client_id:
        raise WorkOSConfigurationError("WorkOS client ID is not configured")
    return f"{settings.workos_api_base_url.rstrip('/')}/user_management/{settings.workos_client_id}"


def workos_jwks_url(settings: Settings) -> str:
    if not settings.workos_client_id:
        raise WorkOSConfigurationError("WorkOS client ID is not configured")
    return f"{settings.workos_api_base_url.rstrip('/')}/sso/jwks/{settings.workos_client_id}"


@lru_cache(maxsize=8)
def _jwks_client(url: str) -> PyJWKClient:
    return PyJWKClient(url, cache_keys=True, timeout=5)


def verify_workos_access_token(
    token: str,
    settings: Settings | None = None,
    *,
    jwks_client: Any | None = None,
) -> dict[str, Any]:
    """Validate signature, algorithm, issuer, audience, expiry and subject."""
    current_settings = settings or get_settings()
    client_id = current_settings.workos_client_id
    if not client_id:
        raise WorkOSConfigurationError("WorkOS client ID is not configured")
    audience = current_settings.workos_token_audience
    if not audience:
        raise WorkOSConfigurationError("WorkOS API token audience is not configured")
    issuer_setting = current_settings.workos_issuer
    issuer: str | list[str]
    if issuer_setting:
        accepted_issuers = [value.strip() for value in issuer_setting.split(",") if value.strip()]
        issuer = accepted_issuers[0] if len(accepted_issuers) == 1 else accepted_issuers
    else:
        issuer = workos_issuer(current_settings)
    client = jwks_client or _jwks_client(workos_jwks_url(current_settings))
    signing_key = client.get_signing_key_from_jwt(token)
    claims = jwt.decode(
        token,
        signing_key.key,
        algorithms=["RS256"],
        issuer=issuer,
        audience=audience,
        options={"require": ["exp", "iat", "iss", "aud", "sub"]},
        leeway=30,
    )
    subject = claims.get("sub")
    if not isinstance(subject, str) or not subject.strip():
        raise jwt.InvalidTokenError("Access token subject is missing")
    if claims.get("sub_profile") == "ai_agent":
        raise jwt.InvalidTokenError("An agent token cannot authenticate a human user")
    return claims


class WorkOSDirectoryClient:
    """Minimal server-side user-management client for trusted profile data."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        if not self.settings.workos_api_key:
            raise WorkOSConfigurationError("WorkOS API key is not configured")
        self.base_url = self.settings.workos_api_base_url.rstrip("/")
        self.headers = {"Authorization": f"Bearer {self.settings.workos_api_key}"}

    def get_user(self, subject: str) -> dict[str, Any]:
        response = self._request("GET", f"/user_management/users/{quote(subject, safe='')}")
        profile = response.json()
        if profile.get("id") != subject:
            raise WorkOSDirectoryError("WorkOS returned a different user identity")
        return profile

    def find_verified_user_by_email(self, email: str) -> dict[str, Any] | None:
        response = self._request("GET", "/user_management/users", params={"email": email})
        results = response.json().get("data", [])
        normalized_email = normalize_email(email)
        for profile in results:
            if normalize_email(profile.get("email", "")) == normalized_email:
                if profile.get("email_verified") is True:
                    return profile
                raise WorkOSEmailNotVerifiedError("The registered account email is not verified")
        return None

    def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        try:
            response = httpx.request(
                method,
                f"{self.base_url}{path}",
                headers=self.headers,
                timeout=5,
                **kwargs,
            )
            response.raise_for_status()
            return response
        except httpx.HTTPStatusError as error:
            raise WorkOSDirectoryError("WorkOS user lookup failed") from error
        except httpx.HTTPError as error:
            raise WorkOSDirectoryError("WorkOS user service is unavailable") from error


def normalize_email(email: str) -> str:
    return email.strip().lower()


def map_profile_error_to_http(error: Exception) -> tuple[int, str, str]:
    if isinstance(error, WorkOSConfigurationError):
        return 503, "identity_provider_not_configured", "Identity service is not configured"
    if isinstance(error, WorkOSEmailNotVerifiedError):
        return 422, "email_not_verified", "The registered account email is not verified"
    if isinstance(error, WorkOSDirectoryError):
        return 503, "identity_provider_unavailable", "Identity service is temporarily unavailable"
    return 503, "identity_provider_unavailable", "Identity service is temporarily unavailable"


def is_jwks_connection_error(error: Exception) -> bool:
    return isinstance(error, PyJWKClientConnectionError)
