from fastapi.testclient import TestClient
import pytest

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
        "schema_version": "1.0.0",
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


def test_configured_archive_credential_protects_every_patient_data_route(tmp_path):
    app = create_app(f"sqlite:///{tmp_path / 'archive.db'}", bearer_token="a" * 32)
    Base.metadata.create_all(app.state.engine)
    client = TestClient(app)
    auth = {"Authorization": f"Bearer {'a' * 32}"}
    payload = {
        "patient_id": "patient-1",
        "source_system": "synthetic",
        "source_record_id": "source-1",
        "record_type": "observation",
        "raw_payload": {"value": 42},
    }

    created = client.post("/api/v1/archive/records", json=payload, headers=auth)
    assert created.status_code == 201
    record_id = created.json()["id"]

    protected_requests = [
        ("post", "/api/v1/archive/records", {"json": payload}),
        ("get", f"/api/v1/archive/records/{record_id}", {}),
        ("get", "/api/v1/archive/patients/patient-1/records", {}),
        ("post", "/api/v1/archive/batches?source_system=synthetic", {}),
        ("post", "/api/v1/archive/objects?source_system=synthetic", {"content": b"x"}),
        ("post", "/api/v1/archive/fhir", {"content": b'{"resourceType":"Bundle","type":"collection","entry":[]}'}),
        ("get", "/api/v1/archive/objects/00000000-0000-0000-0000-000000000000/metadata", {}),
        ("get", "/api/v1/archive/objects/00000000-0000-0000-0000-000000000000/content", {}),
        ("post", "/api/v1/archive/datasets/wearables", {"content": b"{}"}),
        ("get", "/api/v1/archive/datasets", {}),
        ("get", "/api/v1/archive/datasets/00000000-0000-0000-0000-000000000000", {}),
        ("get", "/api/v1/archive/datasets/00000000-0000-0000-0000-000000000000/rows", {}),
        ("post", f"/api/v1/archive/records/{record_id}/promote/promop", {"json": {"promop_person_id": 1}}),
        ("get", f"/api/v1/archive/records/{record_id}/lineage", {}),
    ]
    for method, path, kwargs in protected_requests:
        response = getattr(client, method)(path, **kwargs)
        assert response.status_code == 401, f"{method.upper()} {path} was not protected"

    retrieved = client.get(f"/api/v1/archive/records/{record_id}", headers=auth)
    assert retrieved.status_code == 200
    assert retrieved.headers["cache-control"] == "no-store"


def test_archive_rejects_oversized_chunked_upload_before_persistence(tmp_path):
    app = create_app(
        f"sqlite:///{tmp_path / 'archive.db'}",
        bearer_token="b" * 32,
        max_request_bytes=4,
    )
    Base.metadata.create_all(app.state.engine)
    client = TestClient(app)
    response = client.post(
        "/api/v1/archive/objects?source_system=synthetic",
        content=b"12345",
        headers={"Authorization": f"Bearer {'b' * 32}"},
    )
    assert response.status_code == 413


def test_archive_refuses_local_storage_for_production_patient_data(tmp_path, monkeypatch):
    monkeypatch.setenv("ARCHIVE_OBJECT_STORE_BACKEND", "filesystem")
    with pytest.raises(RuntimeError, match="local filesystem backend"):
        create_app(
            f"sqlite:///{tmp_path / 'archive.db'}",
            bearer_token="p" * 32,
            environment="production",
            rate_limit_per_minute=60,
        )
