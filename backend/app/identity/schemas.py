"""Public identity response models."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    email_verified: bool
    display_name: str | None
    created_at: datetime
