from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException

from app.core.config import Settings
from app.db.models import User
from app.identity.service import resolve_authenticated_user
from app.identity.workos import verify_workos_access_token

TOKEN_AUDIENCE = "https://api.knowflow.example"


class FakeJwksClient:
    def __init__(self, public_key) -> None:
        self.public_key = public_key

    def get_signing_key_from_jwt(self, _token: str) -> SimpleNamespace:
        return SimpleNamespace(key=self.public_key)


def make_token(private_key, **overrides: object) -> str:
    now = datetime.now(UTC)
    claims = {
        "sub": "user_workos_123",
        "iss": "https://api.workos.com/user_management/client_test_123",
        "aud": TOKEN_AUDIENCE,
        "iat": now,
        "exp": now + timedelta(minutes=10),
        "sid": "session_123",
    }
    claims.update(overrides)
    return jwt.encode(claims, private_key, algorithm="RS256", headers={"kid": "test-key"})


def test_workos_token_requires_valid_signature_issuer_audience_and_expiry() -> None:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    settings = Settings(workos_client_id="client_test_123")
    jwks = FakeJwksClient(private_key.public_key())

    claims = verify_workos_access_token(make_token(private_key), settings, jwks_client=jwks)
    assert claims["sub"] == "user_workos_123"

    with pytest.raises(jwt.InvalidIssuerError):
        verify_workos_access_token(
            make_token(private_key, iss="https://attacker.example"), settings, jwks_client=jwks
        )
    with pytest.raises(jwt.InvalidAudienceError):
        verify_workos_access_token(
            make_token(private_key, aud="https://other-api.example"), settings, jwks_client=jwks
        )
    with pytest.raises(jwt.ExpiredSignatureError):
        verify_workos_access_token(
            make_token(private_key, exp=datetime.now(UTC) - timedelta(seconds=60)),
            settings,
            jwks_client=jwks,
        )


def test_access_token_with_non_user_subject_is_rejected() -> None:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    settings = Settings(workos_client_id="client_test_123")
    jwks = FakeJwksClient(private_key.public_key())
    token = make_token(private_key, sub_profile="ai_agent")

    with pytest.raises(jwt.InvalidTokenError, match="agent token"):
        verify_workos_access_token(token, settings, jwks_client=jwks)


def test_authenticated_user_is_created_from_trusted_workos_profile(db_session, monkeypatch) -> None:
    class FakeDirectory:
        def get_user(self, subject: str) -> dict[str, object]:
            assert subject == "user_workos_123"
            return {
                "id": subject,
                "email": "Person@Example.com",
                "email_verified": True,
                "first_name": "Ada",
                "last_name": "Lovelace",
            }

    monkeypatch.setattr("app.identity.service.WorkOSDirectoryClient", FakeDirectory)
    user = resolve_authenticated_user(db_session, "user_workos_123")

    assert user.auth_subject == "user_workos_123"
    assert user.email == "person@example.com"
    assert user.display_name == "Ada Lovelace"
    assert user.email_verified is True
    assert db_session.query(User).count() == 1


def test_email_collision_does_not_merge_distinct_workos_subjects(db_session, monkeypatch) -> None:
    db_session.add(
        User(
            auth_subject="different_workos_subject",
            email="person@example.com",
            email_verified=True,
        )
    )
    db_session.commit()

    class FakeDirectory:
        def get_user(self, subject: str) -> dict[str, object]:
            return {"id": subject, "email": "Person@Example.com", "email_verified": True}

    monkeypatch.setattr("app.identity.service.WorkOSDirectoryClient", FakeDirectory)
    with pytest.raises(HTTPException) as error:
        resolve_authenticated_user(db_session, "another_workos_subject")

    assert error.value.status_code == 409
    assert db_session.query(User).count() == 1


def test_authenticated_api_without_bearer_is_rejected(client) -> None:
    response = client.get("/api/v1/workspaces")

    assert response.status_code == 401
