import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ArchiveRecordCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    patient_id: str = Field(min_length=1, max_length=255)
    source_system: str = Field(min_length=1, max_length=255)
    source_record_id: str | None = Field(default=None, max_length=255)
    record_type: str = Field(min_length=1, max_length=255)
    observed_at: datetime | None = None
    raw_payload: dict[str, Any]
    normalized_payload: dict[str, Any] | None = None
    schema_version: str = Field(default="0.1.0", min_length=1, max_length=64)
    mapping_version: str | None = Field(default=None, max_length=64)
    quality_status: str | None = Field(default=None, max_length=64)


class ArchiveRecordRead(ArchiveRecordCreate):
    id: uuid.UUID
    received_at: datetime
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
