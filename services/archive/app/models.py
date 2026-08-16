import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, JSON, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


class ArchiveRecord(Base):
    __tablename__ = "archive_record"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    patient_id: Mapped[str] = mapped_column(String(255), index=True)
    source_system: Mapped[str] = mapped_column(String(255), index=True)
    source_record_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    record_type: Mapped[str] = mapped_column(String(255))
    observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    normalized_payload: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    schema_version: Mapped[str] = mapped_column(String(64), nullable=False)
    mapping_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    quality_status: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
