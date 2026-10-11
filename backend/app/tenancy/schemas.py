"""Workspace and membership request/response schemas."""

import re
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class RoleName(StrEnum):
    OWNER = "OWNER"
    MEMBER = "MEMBER"


class WorkspaceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)

    @field_validator("name")
    @classmethod
    def trim_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Workspace name cannot be empty")
        return value


class WorkspaceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    slug: str
    role: RoleName
    created_at: datetime


class MemberAdd(BaseModel):
    email: str = Field(min_length=3, max_length=320)

    @field_validator("email")
    @classmethod
    def normalize_and_validate_email(cls, value: str) -> str:
        value = value.strip().lower()
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value):
            raise ValueError("Enter a valid email address")
        return value


class MembershipRoleUpdate(BaseModel):
    role: RoleName


class MemberResponse(BaseModel):
    user_id: UUID
    email: str
    display_name: str | None
    role: RoleName
    created_at: datetime
