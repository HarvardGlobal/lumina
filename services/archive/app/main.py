import hashlib
import json
import os
import secrets
import uuid
from collections.abc import Generator
from datetime import datetime
from typing import Annotated

import pyarrow.parquet as pq
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, Response, status
from pydantic import ValidationError
from sqlalchemy import or_, text
from sqlalchemy.orm import Session

from .database import make_engine, make_session_factory
from .models import ArchiveDataset, ArchiveObject, ArchivePromotion, ArchiveProvenanceEvent, ArchiveRecord, IngestionBatch
from .schemas import (
    ArchiveRecordCreate,
    ArchiveRecordRead,
    DatasetIngestRead,
    DatasetRead,
    ObjectIngestRead,
    ObjectMetadataRead,
    WearableDatasetCreate,
)
from .services import add_event, fhir_metadata, sha256, store_original, wearable_parquet_bytes
from .storage import make_object_store


def get_session(request: Request) -> Generator[Session, None, None]:
    session = request.app.state.session_factory()
    try:
        yield session
    finally:
        session.close()


def require_protected_access(request: Request) -> None:
    """Local/POC auth hook; an empty configured token leaves development open."""
    token = request.app.state.bearer_token
    if not token:
        return
    presented = request.headers.get("Authorization", "")
    if not secrets.compare_digest(presented, f"Bearer {token}"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Archive authorization is required")


def canonical_json_sha256(payload: object) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def duplicate_record(
    session: Session,
    *,
    source_system: str,
    source_record_id: str | None = None,
    idempotency_key: str | None = None,
    content_sha256: str | None = None,
) -> ArchiveRecord | None:
    if idempotency_key:
        record = (
            session.query(ArchiveRecord)
            .filter(ArchiveRecord.source_system == source_system, ArchiveRecord.idempotency_key == idempotency_key)
            .first()
        )
        if record is not None:
            return record
    if source_record_id:
        record = (
            session.query(ArchiveRecord)
            .filter(ArchiveRecord.source_system == source_system, ArchiveRecord.source_record_id == source_record_id)
            .first()
        )
        if record is not None:
            return record
    if content_sha256:
        return (
            session.query(ArchiveRecord)
            .filter(ArchiveRecord.source_system == source_system, ArchiveRecord.content_sha256 == content_sha256)
            .first()
        )
    return None


def complete_record(session: Session, record: ArchiveRecord, *, source_system: str, event: str = "received") -> ArchiveRecord:
    session.add(record)
    session.flush()
    if record.ingestion_batch_id:
        batch = session.get(IngestionBatch, record.ingestion_batch_id)
        if batch is not None:
            batch.record_count += 1
    add_event(session, event, record=record, source_system=source_system)
    if record.supersedes_record_id:
        add_event(
            session,
            "superseded",
            record=record,
            source_system=source_system,
            details={"supersedes_record_id": str(record.supersedes_record_id)},
        )
    session.commit()
    session.refresh(record)
    return record


def create_app(
    database_url: str | None = None,
    object_store_root: str | None = None,
    bearer_token: str | None = None,
) -> FastAPI:
    app = FastAPI(title="LUMINA Archive", version="0.2.0")
    app.state.engine = make_engine(database_url)
    app.state.session_factory = make_session_factory(database_url)
    app.state.object_store = make_object_store(object_store_root)
    app.state.bearer_token = bearer_token if bearer_token is not None else os.getenv("ARCHIVE_BEARER_TOKEN", "")

    @app.get("/health")
    def health(request: Request):
        try:
            with request.app.state.engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            return {"status": "healthy", "service": "lumina-archive", "database": "connected", "object_store": "configured"}
        except Exception:
            raise HTTPException(status_code=503, detail="Archive database is unavailable")

    @app.post(
        "/api/v1/archive/records",
        response_model=ArchiveRecordRead,
        status_code=status.HTTP_201_CREATED,
    )
    def create_record(
        payload: ArchiveRecordCreate,
        response: Response,
        request: Request,
        idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
        session: Session = Depends(get_session),
    ):
        content_digest = canonical_json_sha256(payload.raw_payload)
        existing = duplicate_record(
            session,
            source_system=payload.source_system,
            source_record_id=payload.source_record_id,
            idempotency_key=idempotency_key,
        )
        if existing is not None:
            if existing.content_sha256 and existing.content_sha256 != content_digest:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Source record already exists with different content; create a correcting record with supersedes_record_id",
                )
            response.status_code = status.HTTP_200_OK
            return existing
        if payload.supersedes_record_id and session.get(ArchiveRecord, payload.supersedes_record_id) is None:
            raise HTTPException(status_code=404, detail="Superseded Archive record not found")
        values = payload.model_dump()
        values["source_subject_id"] = values["source_subject_id"] or payload.patient_id
        values["storage_type"] = "inline_json"
        values["content_type"] = "application/json"
        values["format"] = "json"
        values["content_sha256"] = content_digest
        values["idempotency_key"] = idempotency_key
        record = complete_record(session, ArchiveRecord(**values), source_system=payload.source_system)
        return record

    @app.get("/api/v1/archive/records/{record_id}", response_model=ArchiveRecordRead)
    def get_record(record_id: uuid.UUID, session: Session = Depends(get_session)):
        record = session.get(ArchiveRecord, record_id)
        if record is None:
            raise HTTPException(status_code=404, detail="Archive record not found")
        return record

    @app.get("/api/v1/archive/patients/{patient_id}/records", response_model=list[ArchiveRecordRead])
    def patient_records(
        patient_id: str,
        source_system: str | None = None,
        limit: int = Query(default=100, ge=1, le=500),
        session: Session = Depends(get_session),
    ):
        query = session.query(ArchiveRecord).filter(ArchiveRecord.patient_id == patient_id)
        if source_system:
            query = query.filter(ArchiveRecord.source_system == source_system)
        return query.order_by(ArchiveRecord.received_at.desc()).limit(limit).all()

    @app.post("/api/v1/archive/batches", status_code=status.HTTP_201_CREATED)
    def create_batch(source_system: str, request_id: str | None = None, pipeline_version: str | None = None, session: Session = Depends(get_session)):
        batch = IngestionBatch(source_system=source_system, request_id=request_id, pipeline_version=pipeline_version, status="running")
        session.add(batch)
        session.commit()
        session.refresh(batch)
        return {"id": batch.id, "status": batch.status, "source_system": batch.source_system}

    @app.post("/api/v1/archive/objects", response_model=ObjectIngestRead, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_protected_access)])
    async def ingest_object(
        request: Request,
        response: Response,
        source_system: str,
        record_type: str = "source_object",
        source_record_id: str | None = None,
        patient_id: str | None = None,
        source_subject_id: str | None = None,
        original_filename: str | None = None,
        source_format: str | None = None,
        ingestion_batch_id: uuid.UUID | None = None,
        idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
        session: Session = Depends(get_session),
    ):
        data = await request.body()
        if not data:
            raise HTTPException(status_code=422, detail="Archive object body must not be empty")
        digest = sha256(data)
        existing = duplicate_record(
            session,
            source_system=source_system,
            source_record_id=source_record_id,
            idempotency_key=idempotency_key,
            content_sha256=digest,
        )
        if existing is not None:
            if existing.content_sha256 and existing.content_sha256 != digest:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Source record already exists with different content; create a correcting record with supersedes_record_id",
                )
            archive_object = session.get(ArchiveObject, existing.object_id) if existing.object_id else None
            if archive_object is None:
                raise HTTPException(status_code=409, detail="Existing source record is not an object record")
            response.status_code = status.HTTP_200_OK
            return ObjectIngestRead(record_id=existing.id, object=archive_object, duplicate=True)
        if ingestion_batch_id and session.get(IngestionBatch, ingestion_batch_id) is None:
            raise HTTPException(status_code=404, detail="Ingestion batch not found")
        archive_object = store_original(
            session,
            request.app.state.object_store,
            data,
            content_type=request.headers.get("content-type"),
            original_filename=original_filename,
            source_format=source_format,
        )
        record = ArchiveRecord(
            patient_id=patient_id or source_subject_id,
            source_subject_id=source_subject_id or patient_id,
            source_system=source_system,
            source_record_id=source_record_id,
            record_type=record_type,
            storage_type="object",
            content_type=archive_object.content_type,
            format=source_format,
            object_id=archive_object.id,
            content_sha256=archive_object.sha256,
            ingestion_batch_id=ingestion_batch_id,
            idempotency_key=idempotency_key,
            status="archived",
        )
        record = complete_record(session, record, source_system=source_system)
        return ObjectIngestRead(record_id=record.id, object=archive_object)

    @app.post("/api/v1/archive/fhir", response_model=ObjectIngestRead, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_protected_access)])
    async def ingest_fhir(
        request: Request,
        response: Response,
        source_system: str = "fhir",
        source_record_id: str | None = None,
        fhir_version: Annotated[str | None, Header(alias="FHIR-Version")] = None,
        idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
        session: Session = Depends(get_session),
    ):
        data = await request.body()
        try:
            metadata, source_subject_id = fhir_metadata(data, fhir_version)
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise HTTPException(status_code=422, detail="FHIR ingestion requires a valid JSON resource or Bundle")
        digest = sha256(data)
        existing = duplicate_record(session, source_system=source_system, source_record_id=source_record_id, idempotency_key=idempotency_key, content_sha256=digest)
        if existing is not None and existing.object_id:
            if existing.content_sha256 and existing.content_sha256 != digest:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Source record already exists with different content; create a correcting record with supersedes_record_id",
                )
            response.status_code = status.HTTP_200_OK
            return ObjectIngestRead(record_id=existing.id, object=session.get(ArchiveObject, existing.object_id), duplicate=True)
        archive_object = store_original(
            session,
            request.app.state.object_store,
            data,
            content_type=request.headers.get("content-type", "application/fhir+json"),
            source_format="fhir-json",
            metadata_json=metadata,
        )
        record = ArchiveRecord(
            patient_id=source_subject_id,
            source_subject_id=source_subject_id,
            source_system=source_system,
            source_record_id=source_record_id,
            record_type="fhir_bundle" if metadata["bundle_type"] else "fhir_resource",
            storage_type="object",
            content_type=archive_object.content_type,
            format="fhir-json",
            object_id=archive_object.id,
            content_sha256=archive_object.sha256,
            normalized_payload=metadata,
            idempotency_key=idempotency_key,
            status="archived",
        )
        record = complete_record(session, record, source_system=source_system)
        add_event(session, "validated", record=record, archive_object=archive_object, source_system=source_system, details=metadata)
        session.commit()
        return ObjectIngestRead(record_id=record.id, object=archive_object)

    @app.get("/api/v1/archive/objects/{object_id}/metadata", response_model=ObjectMetadataRead)
    def object_metadata(object_id: uuid.UUID, session: Session = Depends(get_session)):
        archive_object = session.get(ArchiveObject, object_id)
        if archive_object is None:
            raise HTTPException(status_code=404, detail="Archive object not found")
        return archive_object

    @app.get("/api/v1/archive/objects/{object_id}/content", dependencies=[Depends(require_protected_access)])
    def object_content(object_id: uuid.UUID, request: Request, session: Session = Depends(get_session)):
        archive_object = session.get(ArchiveObject, object_id)
        if archive_object is None:
            raise HTTPException(status_code=404, detail="Archive object not found")
        try:
            content = request.app.state.object_store.get(archive_object.storage_uri)
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail="Archive object content is unavailable")
        add_event(session, "exported", archive_object=archive_object, details={"bytes": len(content)})
        session.commit()
        headers = {"Content-Disposition": f'attachment; filename="archive-object-{object_id}"'}
        return Response(content=content, media_type=archive_object.content_type or "application/octet-stream", headers=headers)

    @app.post("/api/v1/archive/datasets/wearables", response_model=DatasetIngestRead, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_protected_access)])
    async def ingest_wearable_dataset(
        request: Request,
        response: Response,
        idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
        session: Session = Depends(get_session),
    ):
        raw_source = await request.body()
        try:
            payload = WearableDatasetCreate.model_validate_json(raw_source)
        except ValidationError as error:
            raise HTTPException(status_code=422, detail=error.errors())
        source_digest = sha256(raw_source)
        existing = duplicate_record(session, source_system=payload.source_system, idempotency_key=idempotency_key, content_sha256=source_digest)
        if existing is not None and existing.object_id and existing.dataset_id:
            if existing.content_sha256 and existing.content_sha256 != source_digest:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Idempotency key already belongs to different source content")
            response.status_code = status.HTTP_200_OK
            return DatasetIngestRead(
                record_id=existing.id,
                raw_object=session.get(ArchiveObject, existing.object_id),
                dataset=session.get(ArchiveDataset, existing.dataset_id),
                duplicate=True,
            )
        if payload.ingestion_batch_id and session.get(IngestionBatch, payload.ingestion_batch_id) is None:
            raise HTTPException(status_code=404, detail="Ingestion batch not found")
        raw_object = store_original(
            session,
            request.app.state.object_store,
            raw_source,
            content_type=request.headers.get("content-type", "application/json"),
            source_format="wearable-json",
            metadata_json={"kind": "wearable_source_payload", "observation_count": len(payload.observations)},
        )
        parquet_bytes, start_time, end_time = wearable_parquet_bytes(payload)
        dataset_id = uuid.uuid4()
        storage_uri = request.app.state.object_store.put(dataset_id, parquet_bytes, namespace="datasets", suffix=".parquet")
        metric = payload.metric or (payload.observations[0].metric if len({row.metric for row in payload.observations}) == 1 else None)
        dataset = ArchiveDataset(
            id=dataset_id,
            lumina_person_id=payload.lumina_person_id,
            source_subject_id=payload.source_subject_id,
            source_system=payload.source_system,
            modality=payload.modality,
            dataset_type=payload.dataset_type,
            metric=metric,
            start_time=start_time,
            end_time=end_time,
            row_count=len(payload.observations),
            storage_uri=storage_uri,
            schema_name=payload.schema_name,
            schema_version=payload.schema_version,
            mapping_version=payload.mapping_version,
            quality_status=payload.quality_status,
            sha256=sha256(parquet_bytes),
            ingestion_batch_id=payload.ingestion_batch_id,
        )
        session.add(dataset)
        session.flush()
        record = ArchiveRecord(
            patient_id=payload.source_subject_id,
            lumina_person_id=payload.lumina_person_id,
            source_subject_id=payload.source_subject_id,
            source_system=payload.source_system,
            record_type="wearable_time_series",
            storage_type="parquet",
            content_type="application/vnd.apache.parquet",
            format="parquet",
            raw_payload={"observation_count": len(payload.observations), "schema_name": payload.schema_name},
            schema_version=payload.schema_version,
            mapping_version=payload.mapping_version,
            quality_status=payload.quality_status,
            object_id=raw_object.id,
            dataset_id=dataset.id,
            content_sha256=source_digest,
            ingestion_batch_id=payload.ingestion_batch_id,
            idempotency_key=idempotency_key,
            status="archived",
        )
        record = complete_record(session, record, source_system=payload.source_system)
        add_event(session, "normalized", record=record, archive_object=raw_object, dataset=dataset, source_system=payload.source_system, details={"rows": dataset.row_count})
        session.commit()
        session.refresh(dataset)
        return DatasetIngestRead(record_id=record.id, raw_object=raw_object, dataset=dataset)

    @app.get("/api/v1/archive/datasets", response_model=list[DatasetRead])
    def list_datasets(
        lumina_person_id: uuid.UUID | None = None,
        source_system: str | None = None,
        modality: str | None = None,
        metric: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        session: Session = Depends(get_session),
    ):
        query = session.query(ArchiveDataset)
        for column, value in ((ArchiveDataset.lumina_person_id, lumina_person_id), (ArchiveDataset.source_system, source_system), (ArchiveDataset.modality, modality), (ArchiveDataset.metric, metric)):
            if value is not None:
                query = query.filter(column == value)
        if start_time is not None:
            query = query.filter(ArchiveDataset.end_time >= start_time)
        if end_time is not None:
            query = query.filter(ArchiveDataset.start_time <= end_time)
        return query.order_by(ArchiveDataset.created_at.desc()).all()

    @app.get("/api/v1/archive/datasets/{dataset_id}", response_model=DatasetRead)
    def get_dataset(dataset_id: uuid.UUID, session: Session = Depends(get_session)):
        dataset = session.get(ArchiveDataset, dataset_id)
        if dataset is None:
            raise HTTPException(status_code=404, detail="Archive dataset not found")
        return dataset

    @app.get("/api/v1/archive/datasets/{dataset_id}/rows", dependencies=[Depends(require_protected_access)])
    def dataset_rows(dataset_id: uuid.UUID, request: Request, session: Session = Depends(get_session)):
        dataset = session.get(ArchiveDataset, dataset_id)
        if dataset is None:
            raise HTTPException(status_code=404, detail="Archive dataset not found")
        try:
            table = pq.read_table(__import__("io").BytesIO(request.app.state.object_store.get(dataset.storage_uri)))
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail="Archive dataset content is unavailable")
        add_event(session, "exported", dataset=dataset, source_system=dataset.source_system, details={"rows": dataset.row_count})
        session.commit()
        return {"dataset_id": dataset.id, "row_count": dataset.row_count, "rows": table.to_pylist()}

    @app.get("/api/v1/archive/records/{record_id}/lineage")
    def record_lineage(record_id: uuid.UUID, session: Session = Depends(get_session)):
        record = session.get(ArchiveRecord, record_id)
        if record is None:
            raise HTTPException(status_code=404, detail="Archive record not found")
        archive_object = session.get(ArchiveObject, record.object_id) if record.object_id else None
        dataset = session.get(ArchiveDataset, record.dataset_id) if record.dataset_id else None
        event_filters = [ArchiveProvenanceEvent.archive_record_id == record_id]
        promotion_filters = [ArchivePromotion.archive_record_id == record_id]
        if record.object_id:
            event_filters.append(ArchiveProvenanceEvent.archive_object_id == record.object_id)
        if record.dataset_id:
            event_filters.append(ArchiveProvenanceEvent.archive_dataset_id == record.dataset_id)
            promotion_filters.append(ArchivePromotion.archive_dataset_id == record.dataset_id)
        events = session.query(ArchiveProvenanceEvent).filter(or_(*event_filters)).order_by(ArchiveProvenanceEvent.occurred_at).all()
        promotions = session.query(ArchivePromotion).filter(or_(*promotion_filters)).all()
        return {
            "record": ArchiveRecordRead.model_validate(record).model_dump(mode="json"),
            "object": ObjectMetadataRead.model_validate(archive_object).model_dump(mode="json") if archive_object else None,
            "dataset": DatasetRead.model_validate(dataset).model_dump(mode="json") if dataset else None,
            "events": [{"event_type": event.event_type, "occurred_at": event.occurred_at, "details": event.details} for event in events],
            "promotions": [{"target_system": item.target_system, "status": item.status, "target_table": item.target_table, "target_record_id": item.target_record_id} for item in promotions],
        }

    return app


app = create_app()
