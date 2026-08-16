"""Archive ingestion helpers shared by the HTTP endpoints."""

from __future__ import annotations

import hashlib
import io
import json
import uuid
from datetime import UTC
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq
from sqlalchemy.orm import Session

from .models import ArchiveDataset, ArchiveObject, ArchiveProvenanceEvent, ArchiveRecord
from .schemas import WearableDatasetCreate
from .storage import ObjectStore


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def add_event(
    session: Session,
    event_type: str,
    *,
    record: ArchiveRecord | None = None,
    archive_object: ArchiveObject | None = None,
    dataset: ArchiveDataset | None = None,
    source_system: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    session.add(
        ArchiveProvenanceEvent(
            archive_record_id=record.id if record else None,
            archive_object_id=archive_object.id if archive_object else None,
            archive_dataset_id=dataset.id if dataset else None,
            event_type=event_type,
            source_system=source_system,
            details=details,
        )
    )


def store_original(
    session: Session,
    store: ObjectStore,
    data: bytes,
    *,
    content_type: str | None,
    original_filename: str | None = None,
    source_format: str | None = None,
    metadata_json: dict[str, Any] | None = None,
) -> ArchiveObject:
    digest = sha256(data)
    existing = session.query(ArchiveObject).filter(ArchiveObject.sha256 == digest).first()
    if existing is not None and store.exists(existing.storage_uri):
        return existing
    object_id = uuid.uuid4()
    storage_uri = store.put(object_id, data, namespace="raw")
    archive_object = ArchiveObject(
        id=object_id,
        storage_uri=storage_uri,
        content_type=content_type,
        original_filename=original_filename,
        size_bytes=len(data),
        sha256=digest,
        source_format=source_format,
        storage_backend=store.backend_name,
        metadata_json=metadata_json,
    )
    session.add(archive_object)
    session.flush()
    add_event(session, "stored", archive_object=archive_object, details={"bytes": len(data)})
    return archive_object


def fhir_metadata(data: bytes, fhir_version: str | None = None) -> tuple[dict[str, Any], str | None]:
    """Extract catalogue facts while retaining the exact original FHIR bytes."""
    payload = json.loads(data)
    resource_types: set[str] = set()
    profiles: set[str] = set()
    source_subject_id: str | None = None

    def inspect(resource: Any) -> None:
        nonlocal source_subject_id
        if not isinstance(resource, dict):
            return
        resource_type = resource.get("resourceType")
        if isinstance(resource_type, str):
            resource_types.add(resource_type)
        meta = resource.get("meta")
        if isinstance(meta, dict):
            for profile in meta.get("profile", []):
                if isinstance(profile, str):
                    profiles.add(profile)
        if resource_type == "Patient" and source_subject_id is None and isinstance(resource.get("id"), str):
            source_subject_id = resource["id"]

    inspect(payload)
    if isinstance(payload, dict) and payload.get("resourceType") == "Bundle":
        for entry in payload.get("entry", []):
            if isinstance(entry, dict):
                inspect(entry.get("resource"))
    metadata = {
        "fhir_version": fhir_version,
        "bundle_type": payload.get("type") if isinstance(payload, dict) and payload.get("resourceType") == "Bundle" else None,
        "resource_types": sorted(resource_types),
        "profiles": sorted(profiles),
    }
    return metadata, source_subject_id


def wearable_parquet_bytes(payload: WearableDatasetCreate) -> tuple[bytes, Any, Any]:
    rows: list[dict[str, Any]] = []
    for observation in payload.observations:
        timestamp = observation.timestamp
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=UTC)
        rows.append(
            {
                "lumina_person_id": str(observation.lumina_person_id or payload.lumina_person_id) if (observation.lumina_person_id or payload.lumina_person_id) else None,
                "source_subject_id": observation.source_subject_id or payload.source_subject_id,
                "provider": observation.provider,
                "device_id": observation.device_id,
                "metric": observation.metric,
                "source_metric": observation.source_metric,
                "timestamp": timestamp.astimezone(UTC),
                "value": observation.value,
                "unit": observation.unit,
                "source_unit": observation.source_unit,
                "quality_status": observation.quality_status,
                "source_record_id": observation.source_record_id,
                "schema_version": observation.schema_version,
                "mapping_version": observation.mapping_version,
            }
        )
    schema = pa.schema(
        [
            pa.field("lumina_person_id", pa.string()),
            pa.field("source_subject_id", pa.string()),
            pa.field("provider", pa.string()),
            pa.field("device_id", pa.string()),
            pa.field("metric", pa.string()),
            pa.field("source_metric", pa.string()),
            pa.field("timestamp", pa.timestamp("us", tz="UTC")),
            pa.field("value", pa.float64()),
            pa.field("unit", pa.string()),
            pa.field("source_unit", pa.string()),
            pa.field("quality_status", pa.string()),
            pa.field("source_record_id", pa.string()),
            pa.field("schema_version", pa.string()),
            pa.field("mapping_version", pa.string()),
        ]
    )
    table = pa.Table.from_pylist(rows, schema=schema)
    output = io.BytesIO()
    pq.write_table(table, output, compression="zstd")
    timestamps = [row["timestamp"] for row in rows]
    return output.getvalue(), min(timestamps), max(timestamps)
