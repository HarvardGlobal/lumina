import hashlib
import json
import uuid
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from app.database import Base
from app.main import create_app
from app.models import ArchiveRecord
from app.promop import PromopPromotionError


def archive_client(tmp_path, *, bearer_token="archive-test-token", promop_client=None):
    app = create_app(
        f"sqlite:///{tmp_path / 'archive.db'}",
        object_store_root=str(tmp_path / "objects"),
        bearer_token=bearer_token,
        promop_client=promop_client,
    )
    Base.metadata.create_all(app.state.engine)
    return app, TestClient(app), {"Authorization": f"Bearer {bearer_token}"}


class FakePromopClient:
    def __init__(self, *, fail=False):
        self.calls = []
        self.fail = fail

    def promote_fhir(self, **kwargs):
        self.calls.append(kwargs)
        if self.fail:
            raise PromopPromotionError("PRomop rejected the promotion (HTTP 422)")
        return {
            "person_id": kwargs["person_id"],
            "measurement_ids": [101],
            "condition_ids": [],
            "totals": {"measurements": 1},
        }


def test_raw_object_is_byte_exact_and_idempotent(tmp_path):
    app, client, auth = archive_client(tmp_path)
    source_bytes = b"original\x00bytes\nwith exact\xff content"
    headers = {**auth, "Content-Type": "application/octet-stream", "Idempotency-Key": "object-retry-1"}
    first = client.post(
        "/api/v1/archive/objects",
        params={"source_system": "device-api", "source_record_id": "object-1", "original_filename": "source.bin"},
        content=source_bytes,
        headers=headers,
    )
    assert first.status_code == 201
    first_body = first.json()
    assert first_body["object"]["sha256"] == hashlib.sha256(source_bytes).hexdigest()

    denied = client.get(f"/api/v1/archive/objects/{first_body['object']['id']}/content")
    assert denied.status_code == 401
    downloaded = client.get(f"/api/v1/archive/objects/{first_body['object']['id']}/content", headers=auth)
    assert downloaded.status_code == 200
    assert downloaded.content == source_bytes

    retry = client.post(
        "/api/v1/archive/objects",
        params={"source_system": "device-api", "source_record_id": "object-1", "original_filename": "source.bin"},
        content=source_bytes,
        headers=headers,
    )
    assert retry.status_code == 200
    assert retry.json()["duplicate"] is True
    assert retry.json()["record_id"] == first_body["record_id"]
    with app.state.session_factory() as session:
        assert session.query(ArchiveRecord).count() == 1


def test_fhir_bundle_is_preserved_and_catalogued(tmp_path):
    _, client, auth = archive_client(tmp_path)
    bundle = {
        "resourceType": "Bundle",
        "type": "collection",
        "meta": {"profile": ["https://example.test/StructureDefinition/bundle"]},
        "entry": [
            {
                "resource": {
                    "resourceType": "Patient",
                    "id": "external-patient-42",
                    "meta": {"profile": ["https://example.test/StructureDefinition/patient"]},
                }
            },
            {"resource": {"resourceType": "Observation", "id": "obs-1"}},
        ],
    }
    original = json.dumps(bundle, separators=(",", ":")).encode()
    response = client.post(
        "/api/v1/archive/fhir",
        params={"source_system": "ehr"},
        content=original,
        headers={**auth, "Content-Type": "application/fhir+json", "FHIR-Version": "R4"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["object"]["sha256"] == hashlib.sha256(original).hexdigest()
    assert body["object"]["metadata_json"]["bundle_type"] == "collection"
    assert body["object"]["metadata_json"]["resource_types"] == ["Bundle", "Observation", "Patient"]
    restored = client.get(f"/api/v1/archive/objects/{body['object']['id']}/content", headers=auth)
    assert restored.content == original
    record = client.get(f"/api/v1/archive/records/{body['record_id']}", headers=auth).json()
    assert record["source_subject_id"] == "external-patient-42"
    assert record["lumina_person_id"] is None
    assert record["identity_status"] == "unresolved"


def test_wearable_minutes_are_parquet_catalogued_and_losslessly_readable(tmp_path):
    app, client, auth = archive_client(tmp_path)
    person_id = uuid.uuid4()
    start = datetime(2026, 1, 1, tzinfo=UTC)
    observations = [
        {
            "lumina_person_id": str(person_id),
            "source_subject_id": "wearable-subject-1",
            "provider": "synthetic-provider",
            "device_id": "device-1",
            "metric": "heart_rate",
            "source_metric": "hr",
            "timestamp": (start + timedelta(minutes=index)).isoformat(),
            "value": 60.0 + index / 100,
            "unit": "beats/min",
            "source_unit": "bpm",
            "quality_status": "validated",
            "source_record_id": f"minute-{index}",
            "schema_version": "1.0.0",
        }
        for index in range(1440)
    ]
    source_payload = {
        "source_system": "synthetic-wearable",
        "source_subject_id": "wearable-subject-1",
        "lumina_person_id": str(person_id),
        "metric": "heart_rate",
        "observations": observations,
    }
    original_source_bytes = json.dumps(source_payload, separators=(",", ":")).encode()
    response = client.post(
        "/api/v1/archive/datasets/wearables",
        content=original_source_bytes,
        headers={**auth, "Content-Type": "application/json"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["dataset"]["row_count"] == 1440
    assert body["dataset"]["metric"] == "heart_rate"
    assert body["raw_object"]["size_bytes"] > 0
    assert body["raw_object"]["sha256"]
    preserved_source = client.get(f"/api/v1/archive/objects/{body['raw_object']['id']}/content", headers=auth)
    assert preserved_source.content == original_source_bytes

    listed = client.get(f"/api/v1/archive/datasets?lumina_person_id={person_id}&metric=heart_rate", headers=auth)
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()] == [body["dataset"]["id"]]
    rows = client.get(f"/api/v1/archive/datasets/{body['dataset']['id']}/rows", headers=auth)
    assert rows.status_code == 200
    assert rows.json()["row_count"] == 1440
    assert len(rows.json()["rows"]) == 1440
    assert rows.json()["rows"][0]["value"] == 60.0
    assert rows.json()["rows"][-1]["value"] == 74.39

    lineage = client.get(f"/api/v1/archive/records/{body['record_id']}/lineage", headers=auth)
    assert lineage.status_code == 200
    assert lineage.json()["object"]["id"] == body["raw_object"]["id"]
    assert lineage.json()["dataset"]["id"] == body["dataset"]["id"]
    assert any(event["event_type"] == "stored" for event in lineage.json()["events"])
    assert any(event["event_type"] == "normalized" for event in lineage.json()["events"])
    with app.state.session_factory() as session:
        assert session.query(ArchiveRecord).count() == 1


def test_supersession_keeps_original_inline_record(tmp_path):
    _, client, auth = archive_client(tmp_path)
    first = client.post(
        "/api/v1/archive/records",
        json={
            "patient_id": "source-subject-1",
            "source_system": "survey",
            "source_record_id": "survey-v1",
            "record_type": "survey_response",
            "raw_payload": {"answer": "initial"},
        },
        headers=auth,
    )
    assert first.status_code == 201
    correction = client.post(
        "/api/v1/archive/records",
        json={
            "patient_id": "source-subject-1",
            "source_system": "survey",
            "source_record_id": "survey-v2",
            "record_type": "survey_response",
            "raw_payload": {"answer": "corrected"},
            "supersedes_record_id": first.json()["id"],
        },
        headers=auth,
    )
    assert correction.status_code == 201
    assert correction.json()["supersedes_record_id"] == first.json()["id"]
    assert client.get(f"/api/v1/archive/records/{first.json()['id']}", headers=auth).json()["raw_payload"] == {"answer": "initial"}


def test_preserved_fhir_promotes_through_promop_once_and_records_lineage(tmp_path):
    promop = FakePromopClient()
    _, client, auth = archive_client(tmp_path, promop_client=promop)
    bundle = {
        "resourceType": "Bundle",
        "type": "collection",
        "entry": [{"resource": {"resourceType": "Observation", "id": "obs-archive-1"}}],
    }
    archived = client.post(
        "/api/v1/archive/fhir",
        content=json.dumps(bundle, separators=(",", ":")).encode(),
        headers={**auth, "Content-Type": "application/fhir+json", "FHIR-Version": "R4"},
    )
    assert archived.status_code == 201
    record_id = archived.json()["record_id"]
    promotion = client.post(
        f"/api/v1/archive/records/{record_id}/promote/promop",
        json={"promop_person_id": 7001},
        headers=auth,
    )
    assert promotion.status_code == 201
    assert promotion.json()["status"] == "succeeded"
    assert promotion.json()["target_details"]["measurement_ids"] == [101]
    assert len(promop.calls) == 1
    assert promop.calls[0]["bundle"] == bundle
    assert promop.calls[0]["person_id"] == 7001

    retry = client.post(
        f"/api/v1/archive/records/{record_id}/promote/promop",
        json={"promop_person_id": 7001},
        headers=auth,
    )
    assert retry.status_code == 200
    assert len(promop.calls) == 1
    lineage = client.get(f"/api/v1/archive/records/{record_id}/lineage", headers=auth)
    assert lineage.json()["promotions"][0]["target_record_id"] == "7001"
    assert any(event["event_type"] == "promoted" for event in lineage.json()["events"])


def test_failed_promop_promotion_is_retained_as_failed_lineage(tmp_path):
    _, client, auth = archive_client(tmp_path, promop_client=FakePromopClient(fail=True))
    archived = client.post(
        "/api/v1/archive/fhir",
        content=b'{"resourceType":"Bundle","type":"collection","entry":[]}',
        headers={**auth, "Content-Type": "application/fhir+json"},
    )
    failed = client.post(
        f"/api/v1/archive/records/{archived.json()['record_id']}/promote/promop",
        json={"promop_person_id": 7002},
        headers=auth,
    )
    assert failed.status_code == 502
    lineage = client.get(f"/api/v1/archive/records/{archived.json()['record_id']}/lineage", headers=auth)
    assert lineage.json()["promotions"][0]["status"] == "failed"
    assert any(event["event_type"] == "promotion_failed" for event in lineage.json()["events"])
