from types import SimpleNamespace
from pathlib import Path
import tempfile
from uuid import UUID

import httpx
import pytest

from app.promop import PromopClient, PromopPromotionError
from app.storage import FilesystemObjectStore, S3ObjectStore, make_object_store


class FakeS3Error(Exception):
    def __init__(self, code):
        self.response = {"Error": {"Code": code}}


class FakeS3:
    def __init__(self):
        self.calls = []
        self.objects = {}
        self.exceptions = SimpleNamespace(ClientError=FakeS3Error)

    def put_object(self, **kwargs):
        self.calls.append(("put", kwargs))
        self.objects[kwargs["Key"]] = kwargs["Body"]

    def get_object(self, **kwargs):
        return {"Body": SimpleNamespace(read=lambda: self.objects[kwargs["Key"]])}

    def head_object(self, **kwargs):
        if kwargs["Key"] not in self.objects:
            raise FakeS3Error("404")

    def delete_object(self, **kwargs):
        self.calls.append(("delete", kwargs))
        self.objects.pop(kwargs["Key"], None)


def test_filesystem_store_is_immutable_and_confined(tmp_path):
    store = FilesystemObjectStore(tmp_path)
    object_id = UUID("00000000-0000-0000-0000-000000000001")
    uri = store.put(object_id, b"source", namespace="raw")
    assert store.get(uri) == b"source"
    assert store.exists(uri)
    with pytest.raises(FileExistsError):
        store.put(object_id, b"replacement", namespace="raw")
    with pytest.raises(ValueError):
        store.get("file:///tmp/not-an-archive-object")
    with pytest.raises(ValueError):
        store.put(object_id, b"x", namespace="unsupported")


def test_filesystem_store_uses_unique_temporary_root_when_unconfigured(monkeypatch):
    monkeypatch.delenv("ARCHIVE_OBJECT_STORE_ROOT", raising=False)
    first = FilesystemObjectStore()
    second = FilesystemObjectStore()
    assert first.root != second.root
    assert first.root.parent == Path(tempfile.gettempdir()).resolve()
    assert second.root.parent == Path(tempfile.gettempdir()).resolve()


def test_s3_store_uses_configured_kms_and_private_bucket(monkeypatch):
    import boto3

    client = FakeS3()
    monkeypatch.setattr(boto3, "client", lambda service, **options: client)
    monkeypatch.setenv("ARCHIVE_S3_BUCKET", "lumina-private")
    monkeypatch.setenv("ARCHIVE_S3_PREFIX", "patient-data")
    monkeypatch.setenv("ARCHIVE_S3_SSE", "aws:kms")
    monkeypatch.setenv("ARCHIVE_S3_KMS_KEY_ID", "alias/lumina")
    monkeypatch.setenv("ARCHIVE_OBJECT_STORE_BACKEND", "s3")
    store = make_object_store()
    assert isinstance(store, S3ObjectStore)
    object_id = UUID("00000000-0000-0000-0000-000000000002")
    uri = store.put(object_id, b"source", namespace="datasets", suffix=".parquet")
    assert uri == "s3://lumina-private/patient-data/archive/datasets/00/00000000-0000-0000-0000-000000000002.parquet"
    assert client.calls[0][1]["ServerSideEncryption"] == "aws:kms"
    assert client.calls[0][1]["SSEKMSKeyId"] == "alias/lumina"
    assert store.get(uri) == b"source"
    assert store.exists(uri)
    store.delete(uri)
    assert not store.exists(uri)
    with pytest.raises(ValueError):
        store.get("s3://other-bucket/object")


class FakeResponse:
    def __init__(self, status_code=201, body=None, json_error=False):
        self.status_code = status_code
        self.body = body if body is not None else {"person_id": 42}
        self.json_error = json_error

    def json(self):
        if self.json_error:
            raise ValueError("not JSON")
        return self.body


def test_promop_client_requires_service_credential_and_sends_contract_headers(monkeypatch):
    with pytest.raises(PromopPromotionError, match="not configured"):
        PromopClient(service_token="").promote_fhir(archive_record_id="archive-1", person_id=42, bundle={})

    captured = {}
    monkeypatch.setattr(
        "app.promop.httpx.post",
        lambda url, **kwargs: captured.update(url=url, **kwargs) or FakeResponse(body={"person_id": 42}),
    )
    result = PromopClient(base_url="https://promop.example/", service_token="secret", timeout_seconds=4).promote_fhir(
        archive_record_id="archive-1", person_id=42, bundle={"resourceType": "Bundle"}, fhir_version="R4"
    )
    assert result == {"person_id": 42}
    assert captured["url"] == "https://promop.example/api/v1/fhir/sync/"
    assert captured["headers"]["Authorization"] == "Bearer secret"
    assert captured["headers"]["FHIR-Version"] == "R4"


@pytest.mark.parametrize(
    "response, expected",
    [
        (FakeResponse(status_code=422), "HTTP 422"),
        (FakeResponse(json_error=True), "invalid promotion response"),
        (FakeResponse(body=[]), "invalid promotion response"),
    ],
)
def test_promop_client_rejects_bad_responses(monkeypatch, response, expected):
    monkeypatch.setattr("app.promop.httpx.post", lambda *args, **kwargs: response)
    with pytest.raises(PromopPromotionError, match=expected):
        PromopClient(service_token="secret").promote_fhir(archive_record_id="archive-1", person_id=42, bundle={})


def test_promop_client_hides_transport_failure(monkeypatch):
    monkeypatch.setattr("app.promop.httpx.post", lambda *args, **kwargs: (_ for _ in ()).throw(httpx.ConnectError("offline")))
    with pytest.raises(PromopPromotionError, match="could not be completed"):
        PromopClient(service_token="secret").promote_fhir(archive_record_id="archive-1", person_id=42, bundle={})
