"""Identity endpoints for the authenticated user profile."""

from fastapi import APIRouter

from app.identity.dependencies import CurrentUser
from app.identity.schemas import UserResponse

router = APIRouter(prefix="/me", tags=["identity"])


@router.get("", response_model=UserResponse)
def get_me(current_user: CurrentUser) -> UserResponse:
    return UserResponse.model_validate(current_user)
