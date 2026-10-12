"""Document request and response contracts."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.db.models import DocumentStatus


class DocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    knowledge_area_id: UUID
    uploaded_by: UUID
    original_filename: str
    content_type: str
    byte_size: int
    page_count: int
    status: DocumentStatus
    created_at: datetime
    updated_at: datetime
