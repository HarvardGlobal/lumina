"""Archive catalogue models.

PostgreSQL holds metadata, provenance, and lineage. Object and Parquet bytes
are deliberately kept outside these tables by the storage backends.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


JSON_TYPE = JSON().with_variant(JSONB, "postgresql")


class IngestionBatch(Base):
    __tablename__ = "ingestion_batch"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    source_system: Mapped[str] = mapped_column(String(255), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="received")
    record_count: Mapped[int] = mapped_column(Integer, default=0)
    source_cursor: Mapped[str | None] = mapped_column(Text, nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    pipeline_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_summary: Mapped[str | None] = mapped_column(Text, nullable=True)


class ArchiveObject(Base):
    __tablename__ = "archive_object"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    storage_uri: Mapped[str] = mapped_column(Text, unique=True)
    content_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    original_filename: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    size_bytes: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    compression: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_format: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    storage_backend: Mapped[str] = mapped_column(String(64), default="filesystem")
    encryption_metadata: Mapped[dict[str, Any] | None] = mapped_column(JSON_TYPE, nullable=True)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON_TYPE, nullable=True)


class ArchiveDataset(Base):
    __tablename__ = "archive_dataset"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    lumina_person_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    source_subject_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    source_system: Mapped[str] = mapped_column(String(255), index=True)
    modality: Mapped[str] = mapped_column(String(128), index=True)
    dataset_type: Mapped[str] = mapped_column(String(128))
    metric: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    start_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    end_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    row_count: Mapped[int] = mapped_column(Integer)
    storage_uri: Mapped[str] = mapped_column(Text, unique=True)
    schema_name: Mapped[str] = mapped_column(String(255))
    schema_version: Mapped[str] = mapped_column(String(64))
    mapping_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    quality_status: Mapped[str | None] = mapped_column(String(64), nullable=True)
    sha256: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    ingestion_batch_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("ingestion_batch.id"), nullable=True)


class ArchiveRecord(Base):
    __tablename__ = "archive_record"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    # patient_id is retained for legacy clients. It maps to source_subject_id;
    # it is not a resolved LUMINA identity.
    patient_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    lumina_person_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    source_subject_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    identity_status: Mapped[str] = mapped_column(String(32), default="unresolved")
    source_system: Mapped[str] = mapped_column(String(255), index=True)
    source_record_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    record_type: Mapped[str] = mapped_column(String(255))
    storage_type: Mapped[str] = mapped_column(String(32), default="inline_json")
    content_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    format: Mapped[str | None] = mapped_column(String(128), nullable=True)
    observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    raw_payload: Mapped[dict[str, Any] | None] = mapped_column(JSON_TYPE, nullable=True)
    normalized_payload: Mapped[dict[str, Any] | None] = mapped_column(JSON_TYPE, nullable=True)
    schema_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    mapping_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    quality_status: Mapped[str | None] = mapped_column(String(64), nullable=True)
    object_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("archive_object.id"), nullable=True)
    dataset_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("archive_dataset.id"), nullable=True)
    content_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    supersedes_record_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("archive_record.id"), nullable=True)
    ingestion_batch_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("ingestion_batch.id"), nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="received")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class ArchiveProvenanceEvent(Base):
    __tablename__ = "archive_provenance_event"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    archive_record_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("archive_record.id"), nullable=True, index=True)
    archive_object_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("archive_object.id"), nullable=True, index=True)
    archive_dataset_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("archive_dataset.id"), nullable=True, index=True)
    event_type: Mapped[str] = mapped_column(String(64), index=True)
    actor_service: Mapped[str] = mapped_column(String(128), default="lumina-archive")
    source_system: Mapped[str | None] = mapped_column(String(255), nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    pipeline_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    pipeline_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    mapping_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    details: Mapped[dict[str, Any] | None] = mapped_column(JSON_TYPE, nullable=True)


class ArchivePromotion(Base):
    __tablename__ = "archive_promotion"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    archive_record_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("archive_record.id"), nullable=True, index=True)
    archive_dataset_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("archive_dataset.id"), nullable=True, index=True)
    target_system: Mapped[str] = mapped_column(String(64), default="promop")
    target_domain: Mapped[str | None] = mapped_column(String(128), nullable=True)
    target_table: Mapped[str | None] = mapped_column(String(128), nullable=True)
    target_record_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    mapping_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    transform_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    promoted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="pending")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
