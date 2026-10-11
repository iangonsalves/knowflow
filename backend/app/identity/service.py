"""Local user provisioning keyed by immutable WorkOS subjects."""

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import User
from app.identity.workos import (
    WorkOSConfigurationError,
    WorkOSDirectoryClient,
    WorkOSDirectoryError,
    map_profile_error_to_http,
    normalize_email,
)


def resolve_authenticated_user(session: Session, subject: str) -> User:
    """Return the existing local user or provision one from a trusted WorkOS profile."""
    user = session.scalar(select(User).where(User.auth_subject == subject))
    if user is not None:
        return user

    # Do not hold a database transaction open while calling the identity provider.
    session.rollback()
    try:
        profile = WorkOSDirectoryClient().get_user(subject)
    except (WorkOSConfigurationError, WorkOSDirectoryError) as error:
        raise_profile_http_error(error)

    if profile.get("email_verified") is not True:
        raise HTTPException(
            status_code=403,
            detail={
                "code": "email_not_verified",
                "message": "Verify your email before using KnowFlow",
            },
        )
    email = normalize_email(str(profile.get("email", "")))
    if not email or "@" not in email:
        raise HTTPException(
            status_code=502,
            detail={
                "code": "identity_profile_invalid",
                "message": "Identity profile is incomplete",
            },
        )
    display_name = (
        " ".join(
            part.strip()
            for part in (profile.get("first_name", ""), profile.get("last_name", ""))
            if isinstance(part, str) and part.strip()
        )
        or None
    )
    conflicting_user = session.scalar(select(User).where(User.email == email))
    if conflicting_user is not None and conflicting_user.auth_subject != subject:
        session.rollback()
        raise HTTPException(
            status_code=409,
            detail={
                "code": "identity_email_conflict",
                "message": "This email is linked to another account",
            },
        )

    user = User(
        auth_subject=subject,
        email=email,
        email_verified=True,
        display_name=display_name,
    )
    session.add(user)
    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        # A simultaneous first request may have created the same subject.
        user = session.scalar(select(User).where(User.auth_subject == subject))
        if user is not None:
            return user
        raise HTTPException(
            status_code=409,
            detail={
                "code": "identity_email_conflict",
                "message": "This email is linked to another account",
            },
        ) from error
    session.refresh(user)
    return user


def provision_registered_user(session: Session, profile: dict[str, object]) -> User:
    """Create or resolve a KnowFlow user from an existing verified WorkOS account."""
    subject = profile.get("id")
    email = normalize_email(str(profile.get("email", "")))
    if not isinstance(subject, str) or not subject or not email:
        raise HTTPException(
            status_code=502,
            detail={
                "code": "identity_profile_invalid",
                "message": "Identity profile is incomplete",
            },
        )
    if profile.get("email_verified") is not True:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "email_not_verified",
                "message": "The registered account email is not verified",
            },
        )

    user = session.scalar(select(User).where(User.auth_subject == subject))
    if user is not None:
        if user.email != email:
            duplicate = session.scalar(select(User).where(User.email == email, User.id != user.id))
            if duplicate is not None:
                raise HTTPException(
                    status_code=409,
                    detail={
                        "code": "identity_email_conflict",
                        "message": "This email is linked to another account",
                    },
                )
            user.email = email
            user.email_verified = True
        session.flush()
        return user

    duplicate = session.scalar(select(User).where(User.email == email))
    if duplicate is not None:
        if duplicate.auth_subject != subject:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "identity_email_conflict",
                    "message": "This email is linked to another account",
                },
            )
        return duplicate

    display_name = (
        " ".join(
            part.strip()
            for part in (profile.get("first_name", ""), profile.get("last_name", ""))
            if isinstance(part, str) and part.strip()
        )
        or None
    )
    user = User(
        auth_subject=subject,
        email=email,
        email_verified=True,
        display_name=display_name,
    )
    session.add(user)
    try:
        session.flush()
    except IntegrityError as error:
        session.rollback()
        resolved = session.scalar(select(User).where(User.auth_subject == subject))
        if resolved is not None:
            return resolved
        raise HTTPException(
            status_code=409,
            detail={
                "code": "identity_email_conflict",
                "message": "This email is linked to another account",
            },
        ) from error
    return user


def raise_profile_http_error(error: Exception) -> None:
    status_code, code, message = map_profile_error_to_http(error)
    raise HTTPException(
        status_code=status_code, detail={"code": code, "message": message}
    ) from error
