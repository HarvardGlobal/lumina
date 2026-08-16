import uuid
from collections.abc import Generator

from fastapi import Depends, FastAPI, HTTPException, Query, Request, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from .database import make_engine, make_session_factory
from .models import ArchiveRecord
from .schemas import ArchiveRecordCreate, ArchiveRecordRead


def get_session(request: Request) -> Generator[Session, None, None]:
    session = request.app.state.session_factory()
    try:
        yield session
    finally:
        session.close()


def create_app(database_url: str | None = None) -> FastAPI:
    app = FastAPI(title="LUMINA Archive", version="0.1.0")
    app.state.engine = make_engine(database_url)
    app.state.session_factory = make_session_factory(database_url)

    @app.get("/health")
    def health(request: Request):
        try:
            with request.app.state.engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            return {"status": "healthy", "service": "lumina-archive", "database": "connected"}
        except Exception:
            raise HTTPException(status_code=503, detail="Archive database is unavailable")

    @app.post(
        "/api/v1/archive/records",
        response_model=ArchiveRecordRead,
        status_code=status.HTTP_201_CREATED,
    )
    def create_record(payload: ArchiveRecordCreate, session: Session = Depends(get_session)):
        record = ArchiveRecord(**payload.model_dump())
        session.add(record)
        session.commit()
        session.refresh(record)
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

    return app


app = create_app()
