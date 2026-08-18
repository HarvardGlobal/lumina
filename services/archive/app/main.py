import hashlib
import json
import os
import secrets
import uuid
from collections import defaultdict, deque
from collections.abc import Generator
from datetime import UTC, datetime
from threading import Lock
from time import monotonic
from typing import Annotated

import pyarrow.parquet as pq
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, Response, status
from pydantic import ValidationError
from sqlalchemy import or_, text
from sqlalchemy.orm import Session
from starlette.responses import JSONResponse

from .database import make_engine, make_session_factory
from .models import ArchiveDataset, ArchiveObject, ArchivePromotion, ArchiveProvenanceEvent, ArchiveRecord, IngestionBatch
from .schemas import (
    ArchiveRecordCreate,
    ArchiveRecordRead,
    DatasetIngestRead,
    DatasetRead,
    ObjectIngestRead,
    ObjectMetadataRead,
    PromopPromotionRequest,
    PromotionRead,
    WearableDatasetCreate,
)
from .promop import PromopClient, PromopPromotionError
from .services import add_event, fhir_metadata, sha256, store_original, wearable_parquet_bytes
from .storage import make_object_store


def get_session(request: Request) -> Generator[Session, None, None]:
    session = request.app.state.session_factory()
    try:
        yield session
    finally:
        session.close()


def require_protected_access(request: Request) -> None:
    """Require the configured Archive service credential when one is set."""
    token = request.app.state.bearer_token
    if not token:
        return
    presented = request.headers.get("Authorization", "")
    if not secrets.compare_digest(presented, f"Bearer {token}"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Archive authorization is required")


def configured_positive_int(value: str | None, *, name: str, default: int) -> int:
    if value is None or value == "":
        return default
    try:
        parsed = int(value)
    except ValueError as error:
        raise RuntimeError(f"{name} must be a positive integer") from error
    if parsed < 1:
        raise RuntimeError(f"{name} must be a positive integer")
    return parsed


def configured_nonnegative_int(value: str | None, *, name: str, default: int) -> int:
    if value is None or value == "":
        return default
    try:
        parsed = int(value)
    except ValueError as error:
        raise RuntimeError(f"{name} must be zero or a positive integer") from error
    if parsed < 0:
        raise RuntimeError(f"{name} must be zero or a positive integer")
    return parsed


def validate_production_archive_settings(*, bearer_token: str, max_request_bytes: int, rate_limit_per_minute: int) -> None:
    """Refuse an accidentally insecure Archive production process.

    This validates controls the service can observe.  The deployment runbook
    separately covers identity, network, backup, and organization controls.
    """
    errors: list[str] = []
    if len(bearer_token) < 32 or bearer_token in {"archive-test-token", "change-me"}:
        errors.append("ARCHIVE_BEARER_TOKEN must be a unique secret of at least 32 characters")
    if os.getenv("ARCHIVE_OBJECT_STORE_BACKEND", "filesystem") != "s3":
        errors.append("ARCHIVE_OBJECT_STORE_BACKEND must be s3 in production; the local filesystem backend is not a production control")
    if not os.getenv("ARCHIVE_S3_BUCKET"):
        errors.append("ARCHIVE_S3_BUCKET is required in production")
    if os.getenv("ARCHIVE_S3_SSE") != "aws:kms" or not os.getenv("ARCHIVE_S3_KMS_KEY_ID"):
        errors.append("ARCHIVE_S3_SSE=aws:kms and ARCHIVE_S3_KMS_KEY_ID are required in production")
    if max_request_bytes > 100 * 1024 * 1024:
        errors.append("ARCHIVE_MAX_REQUEST_BYTES must not exceed 104857600 in production")
    if rate_limit_per_minute < 1:
        errors.append("ARCHIVE_RATE_LIMIT_REQUESTS_PER_MINUTE must be enabled in production")
    if errors:
        raise RuntimeError("Invalid production Archive configuration: " + "; ".join(errors))


class SlidingWindowRateLimiter:
    """Small per-process backstop; the ingress must also enforce global limits."""

    def __init__(self, limit_per_minute: int):
        self.limit_per_minute = limit_per_minute
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def allow(self, key: str) -> bool:
        if self.limit_per_minute < 1:
            return True
        now = monotonic()
        with self._lock:
            window = self._hits[key]
            while window and window[0] <= now - 60:
                window.popleft()
            if len(window) >= self.limit_per_minute:
                return False
            window.append(now)
            return True


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
    promop_client: PromopClient | None = None,
    environment: str | None = None,
    max_request_bytes: int | None = None,
    rate_limit_per_minute: int | None = None,
) -> FastAPI:
    archive_environment = (environment or os.getenv("LUMINA_ENV", "development")).lower()
    if archive_environment not in {"development", "test", "staging", "production"}:
        raise RuntimeError("LUMINA_ENV must be development, test, staging, or production")
    configured_token = bearer_token if bearer_token is not None else os.getenv("ARCHIVE_BEARER_TOKEN", "")
    request_limit = max_request_bytes or configured_positive_int(
        os.getenv("ARCHIVE_MAX_REQUEST_BYTES"), name="ARCHIVE_MAX_REQUEST_BYTES", default=25 * 1024 * 1024
    )
    request_rate_limit = rate_limit_per_minute if rate_limit_per_minute is not None else configured_nonnegative_int(
        os.getenv("ARCHIVE_RATE_LIMIT_REQUESTS_PER_MINUTE"),
        name="ARCHIVE_RATE_LIMIT_REQUESTS_PER_MINUTE",
        default=0,
    )
    if archive_environment == "production":
        validate_production_archive_settings(
            bearer_token=configured_token,
            max_request_bytes=request_limit,
            rate_limit_per_minute=request_rate_limit,
        )
    app = FastAPI(
        title="LUMINA Archive",
        version="1.0.0",
        docs_url=None if archive_environment == "production" else "/docs",
        redoc_url=None if archive_environment == "production" else "/redoc",
        openapi_url=None if archive_environment == "production" else "/openapi.json",
    )
    app.state.engine = make_engine(database_url)
    app.state.session_factory = make_session_factory(database_url)
    app.state.object_store = make_object_store(object_store_root)
    app.state.bearer_token = configured_token
    app.state.environment = archive_environment
    app.state.max_request_bytes = request_limit
    app.state.rate_limiter = SlidingWindowRateLimiter(request_rate_limit)
    app.state.promop_client = promop_client or PromopClient()

    @app.middleware("http")
    async def protect_archive_api(request: Request, call_next):
        """Make every Archive API route private when a token is configured.

        This avoids endpoint-by-endpoint omissions for metadata, catalogue, and
        lineage responses, all of which can contain protected health data.
        """
        is_archive_api = request.url.path.startswith("/api/v1/archive")
        if is_archive_api:
            content_length = request.headers.get("content-length")
            if content_length:
                try:
                    if int(content_length) > request.app.state.max_request_bytes:
                        return JSONResponse(status_code=413, content={"detail": "Archive request exceeds the configured size limit"})
                except ValueError:
                    return JSONResponse(status_code=400, content={"detail": "Invalid Content-Length header"})
            token = request.app.state.bearer_token
            presented = request.headers.get("Authorization", "")
            if token and not secrets.compare_digest(presented, f"Bearer {token}"):
                return JSONResponse(status_code=401, content={"detail": "Archive authorization is required"})
            if token and not request.app.state.rate_limiter.allow(hashlib.sha256(presented.encode()).hexdigest()):
                return JSONResponse(
                    status_code=429,
                    content={"detail": "Archive request rate limit exceeded"},
                    headers={"Retry-After": "60"},
                )
        response = await call_next(request)
        if is_archive_api:
            response.headers.setdefault("Cache-Control", "no-store")
            response.headers.setdefault("Pragma", "no-cache")
            response.headers.setdefault("X-Content-Type-Options", "nosniff")
            response.headers.setdefault("Referrer-Policy", "no-referrer")
        return response

    async def read_limited_body(request: Request) -> bytes:
        """Read a request incrementally so chunked uploads obey the same cap."""
        chunks: list[bytes] = []
        received = 0
        async for chunk in request.stream():
            received += len(chunk)
            if received > request.app.state.max_request_bytes:
                raise HTTPException(status_code=413, detail="Archive request exceeds the configured size limit")
            chunks.append(chunk)
        return b"".join(chunks)

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
    async def create_record(
        request: Request,
        response: Response,
        idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
        session: Session = Depends(get_session),
    ):
        try:
            payload = ArchiveRecordCreate.model_validate_json(await read_limited_body(request))
        except ValidationError as error:
            raise HTTPException(status_code=422, detail=error.errors())
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
        data = await read_limited_body(request)
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
        data = await read_limited_body(request)
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
        raw_source = await read_limited_body(request)
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

    @app.post(
        "/api/v1/archive/records/{record_id}/promote/promop",
        response_model=PromotionRead,
        status_code=status.HTTP_201_CREATED,
        dependencies=[Depends(require_protected_access)],
    )
    def promote_fhir_record(
        record_id: uuid.UUID,
        payload: PromopPromotionRequest,
        request: Request,
        response: Response,
        session: Session = Depends(get_session),
    ):
        """Promote a preserved FHIR Bundle through PRomop's own FHIR importer.

        This is intentionally the only automatic promotion path: Archive never
        maps generic JSON or minute-level wearable values into OMOP itself.
        """
        record = session.get(ArchiveRecord, record_id)
        if record is None:
            raise HTTPException(status_code=404, detail="Archive record not found")
        if record.format != "fhir-json" or record.object_id is None:
            raise HTTPException(
                status_code=422,
                detail="Only preserved FHIR Archive records can be promoted to PRomop",
            )
        existing = (
            session.query(ArchivePromotion)
            .filter(
                ArchivePromotion.archive_record_id == record.id,
                ArchivePromotion.target_system == "promop",
                ArchivePromotion.target_record_id == str(payload.promop_person_id),
                ArchivePromotion.mapping_version == payload.mapping_version,
                ArchivePromotion.transform_version == payload.transform_version,
                ArchivePromotion.status == "succeeded",
            )
            .first()
        )
        if existing is not None:
            response.status_code = status.HTTP_200_OK
            return existing
        archive_object = session.get(ArchiveObject, record.object_id)
        if archive_object is None:
            raise HTTPException(status_code=409, detail="FHIR Archive object catalogue entry is unavailable")
        try:
            raw_bundle = request.app.state.object_store.get(archive_object.storage_uri)
            bundle = json.loads(raw_bundle)
        except (FileNotFoundError, UnicodeDecodeError, json.JSONDecodeError):
            raise HTTPException(status_code=409, detail="Preserved FHIR content is unavailable or invalid")
        if not isinstance(bundle, dict) or bundle.get("resourceType") != "Bundle":
            raise HTTPException(status_code=422, detail="Only a preserved FHIR Bundle can be promoted")

        promotion = ArchivePromotion(
            archive_record_id=record.id,
            target_system="promop",
            target_domain="FHIR",
            target_table="fhir_sync",
            target_record_id=str(payload.promop_person_id),
            mapping_version=payload.mapping_version,
            transform_version=payload.transform_version,
            status="pending",
        )
        session.add(promotion)
        session.commit()
        session.refresh(promotion)

        fhir_version = (archive_object.metadata_json or {}).get("fhir_version")
        try:
            result = request.app.state.promop_client.promote_fhir(
                archive_record_id=str(record.id),
                person_id=payload.promop_person_id,
                bundle=bundle,
                fhir_version=fhir_version,
            )
        except PromopPromotionError as error:
            promotion.status = "failed"
            promotion.error = str(error)
            session.add(promotion)
            add_event(
                session,
                "promotion_failed",
                record=record,
                archive_object=archive_object,
                source_system=record.source_system,
                details={"target_system": "promop", "promotion_id": str(promotion.id)},
            )
            session.commit()
            raise HTTPException(status_code=502, detail="PRomop promotion failed; Archive source data remains preserved")
        if result.get("person_id") != payload.promop_person_id:
            promotion.status = "failed"
            promotion.error = "PRomop returned a mismatched person identifier"
            session.add(promotion)
            session.commit()
            raise HTTPException(status_code=502, detail="PRomop returned an invalid promotion response")
        promotion.status = "succeeded"
        promotion.target_details = result
        promotion.promoted_at = datetime.now(UTC)
        session.add(promotion)
        add_event(
            session,
            "promoted",
            record=record,
            archive_object=archive_object,
            source_system=record.source_system,
            details={"target_system": "promop", "promotion_id": str(promotion.id), "person_id": payload.promop_person_id},
        )
        session.commit()
        session.refresh(promotion)
        return promotion

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
            "promotions": [PromotionRead.model_validate(item).model_dump(mode="json") for item in promotions],
        }

    return app


app = create_app()
