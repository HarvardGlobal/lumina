import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ArchiveRecordCreate(BaseModel):
    """Compatibility request for small inline JSON records."""

    model_config = ConfigDict(extra="forbid")

    patient_id: str = Field(min_length=1, max_length=255)
    source_system: str = Field(min_length=1, max_length=255)
    source_record_id: str | None = Field(default=None, max_length=255)
    record_type: str = Field(min_length=1, max_length=255)
    raw_payload: dict[str, Any]
    observed_at: datetime | None = None
    normalized_payload: dict[str, Any] | None = None
    schema_version: str = Field(default="0.1.0", min_length=1, max_length=64)
    mapping_version: str | None = Field(default=None, max_length=64)
    quality_status: str | None = Field(default=None, max_length=64)
    lumina_person_id: uuid.UUID | None = None
    source_subject_id: str | None = Field(default=None, max_length=255)
    identity_status: str = Field(default="unresolved", pattern="^(unresolved|linked|verified|disputed)$")
    supersedes_record_id: uuid.UUID | None = None
    ingestion_batch_id: uuid.UUID | None = None


class ArchiveRecordRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    patient_id: str | None
    lumina_person_id: uuid.UUID | None
    source_subject_id: str | None
    identity_status: str
    source_system: str
    source_record_id: str | None
    record_type: str
    storage_type: str
    content_type: str | None
    format: str | None
    observed_at: datetime | None
    received_at: datetime
    raw_payload: dict[str, Any] | None
    normalized_payload: dict[str, Any] | None
    schema_version: str | None
    mapping_version: str | None
    quality_status: str | None
    object_id: uuid.UUID | None
    dataset_id: uuid.UUID | None
    content_sha256: str | None
    supersedes_record_id: uuid.UUID | None
    ingestion_batch_id: uuid.UUID | None
    status: str
    created_at: datetime


class ObjectMetadataRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    content_type: str | None
    original_filename: str | None
    size_bytes: int
    sha256: str
    compression: str | None
    source_format: str | None
    created_at: datetime
    storage_backend: str
    metadata_json: dict[str, Any] | None


class ObjectIngestRead(BaseModel):
    record_id: uuid.UUID
    object: ObjectMetadataRead
    duplicate: bool = False


class WearableObservation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lumina_person_id: uuid.UUID | None = None
    source_subject_id: str | None = None
    provider: str = Field(min_length=1)
    device_id: str | None = None
    metric: str = Field(min_length=1)
    source_metric: str | None = None
    timestamp: datetime
    value: float
    unit: str | None = None
    source_unit: str | None = None
    quality_status: str | None = None
    source_record_id: str | None = None
    schema_version: str = "1.0.0"
    mapping_version: str | None = None


class WearableDatasetCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_system: str = Field(min_length=1, max_length=255)
    modality: str = "wearable"
    dataset_type: str = "time_series"
    metric: str | None = None
    lumina_person_id: uuid.UUID | None = None
    source_subject_id: str | None = None
    schema_name: str = "lumina.wearable.observations"
    schema_version: str = "1.0.0"
    mapping_version: str | None = None
    quality_status: str | None = None
    ingestion_batch_id: uuid.UUID | None = None
    observations: list[WearableObservation] = Field(min_length=1)


class DatasetRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    lumina_person_id: uuid.UUID | None
    source_subject_id: str | None
    source_system: str
    modality: str
    dataset_type: str
    metric: str | None
    start_time: datetime | None
    end_time: datetime | None
    row_count: int
    schema_name: str
    schema_version: str
    mapping_version: str | None
    quality_status: str | None
    sha256: str
    created_at: datetime
    ingestion_batch_id: uuid.UUID | None


class DatasetIngestRead(BaseModel):
    record_id: uuid.UUID
    raw_object: ObjectMetadataRead
    dataset: DatasetRead
    duplicate: bool = False
