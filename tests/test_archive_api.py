from fastapi.testclient import TestClient

from app.database import Base
from app.main import create_app


def test_archive_create_retrieve_and_patient_filter(tmp_path):
    app = create_app(f"sqlite:///{tmp_path / 'archive.db'}")
    Base.metadata.create_all(app.state.engine)
    client = TestClient(app)

    payload = {
        "patient_id": "patient-1",
        "source_system": "synthetic",
        "source_record_id": "source-1",
        "record_type": "observation",
        "raw_payload": {"value": 42, "nested": {"source_field": "preserved"}},
        "schema_version": "0.1.0",
    }
    created = client.post("/api/v1/archive/records", json=payload)
    assert created.status_code == 201
    record = created.json()
    assert record["raw_payload"] == payload["raw_payload"]

    fetched = client.get(f"/api/v1/archive/records/{record['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["source_record_id"] == "source-1"

    by_patient = client.get("/api/v1/archive/patients/patient-1/records?source_system=synthetic")
    assert by_patient.status_code == 200
    assert len(by_patient.json()) == 1


def test_archive_rejects_undeclared_archive_fields(tmp_path):
    app = create_app(f"sqlite:///{tmp_path / 'archive.db'}")
    Base.metadata.create_all(app.state.engine)
    client = TestClient(app)
    response = client.post(
        "/api/v1/archive/records",
        json={
            "patient_id": "patient-1",
            "source_system": "synthetic",
            "record_type": "observation",
            "raw_payload": {"value": 42},
            "unknown_field": "not silently accepted",
        },
    )
    assert response.status_code == 422
