"""Storage abstraction for immutable Archive bytes.

The local backend is private filesystem storage mounted into the Archive
container. The business layer only handles opaque URIs, so an S3/MinIO backend
can be added without changing catalogue or API semantics.
"""

from __future__ import annotations

import os
import tempfile
from abc import ABC, abstractmethod
from pathlib import Path
from uuid import UUID


class ObjectStore(ABC):
    backend_name: str

    @abstractmethod
    def put(self, object_id: UUID, data: bytes, *, namespace: str, suffix: str = "") -> str: ...

    @abstractmethod
    def get(self, storage_uri: str) -> bytes: ...

    @abstractmethod
    def exists(self, storage_uri: str) -> bool: ...

    @abstractmethod
    def delete(self, storage_uri: str) -> None:
        """Reserved for governed lifecycle operations; never exposed publicly."""


class FilesystemObjectStore(ObjectStore):
    backend_name = "filesystem"

    def __init__(self, root: str | Path | None = None):
        configured_root = root or os.getenv("ARCHIVE_OBJECT_STORE_ROOT")
        # Compose supplies a persistent development volume and production
        # requires S3. A unique directory is safe for ad-hoc local/test use;
        # a shared predictable /tmp path could be pre-created or substituted.
        self.root = (
            Path(configured_root).resolve()
            if configured_root
            else Path(tempfile.mkdtemp(prefix="lumina-archive-objects-")).resolve()
        )
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, storage_uri: str) -> Path:
        if not storage_uri.startswith("file://"):
            raise ValueError("Filesystem storage URI must use file://")
        path = Path(storage_uri.removeprefix("file://")).resolve()
        if self.root not in path.parents and path != self.root:
            raise ValueError("Storage URI escapes configured Archive object root")
        return path

    def put(self, object_id: UUID, data: bytes, *, namespace: str, suffix: str = "") -> str:
        if namespace not in {"raw", "datasets"}:
            raise ValueError("Unsupported Archive storage namespace")
        relative = Path("archive") / namespace / str(object_id)[:2] / f"{object_id}{suffix}"
        destination = self.root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            raise FileExistsError("Archive objects are immutable and cannot be overwritten")
        temporary = destination.with_suffix(destination.suffix + ".partial")
        try:
            with temporary.open("xb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            temporary.replace(destination)
        finally:
            if temporary.exists():
                temporary.unlink()
        return f"file://{destination}"

    def get(self, storage_uri: str) -> bytes:
        return self._path(storage_uri).read_bytes()

    def exists(self, storage_uri: str) -> bool:
        return self._path(storage_uri).is_file()

    def delete(self, storage_uri: str) -> None:
        # No caller in this application path invokes this. Retained solely for
        # a future governed retention/lifecycle worker.
        self._path(storage_uri).unlink()


class S3ObjectStore(ObjectStore):
    """Private S3-compatible object storage with immutable Archive keys.

    Credentials are intentionally obtained through the standard AWS provider
    chain (for example, a workload identity), not from Archive payloads or the
    database.  Production configuration is validated before this backend is
    allowed to start.
    """

    backend_name = "s3"

    def __init__(self):
        try:
            import boto3
        except ImportError as error:  # pragma: no cover - guarded by dependencies
            raise RuntimeError("S3 Archive storage requires boto3") from error

        self.bucket = os.getenv("ARCHIVE_S3_BUCKET", "")
        self.prefix = os.getenv("ARCHIVE_S3_PREFIX", "lumina-archive").strip("/")
        if not self.bucket:
            raise RuntimeError("ARCHIVE_S3_BUCKET is required for the S3 Archive object store")
        client_options: dict[str, str] = {}
        if endpoint_url := os.getenv("ARCHIVE_S3_ENDPOINT_URL"):
            client_options["endpoint_url"] = endpoint_url
        if region_name := os.getenv("AWS_REGION"):
            client_options["region_name"] = region_name
        self.client = boto3.client("s3", **client_options)
        self.sse = os.getenv("ARCHIVE_S3_SSE", "")
        self.kms_key_id = os.getenv("ARCHIVE_S3_KMS_KEY_ID", "")

    def _key(self, object_id: UUID, *, namespace: str, suffix: str = "") -> str:
        if namespace not in {"raw", "datasets"}:
            raise ValueError("Unsupported Archive storage namespace")
        key = f"archive/{namespace}/{str(object_id)[:2]}/{object_id}{suffix}"
        return f"{self.prefix}/{key}" if self.prefix else key

    def _parse_uri(self, storage_uri: str) -> str:
        expected_prefix = f"s3://{self.bucket}/"
        if not storage_uri.startswith(expected_prefix):
            raise ValueError("Storage URI does not belong to the configured Archive bucket")
        return storage_uri.removeprefix(expected_prefix)

    def put(self, object_id: UUID, data: bytes, *, namespace: str, suffix: str = "") -> str:
        key = self._key(object_id, namespace=namespace, suffix=suffix)
        options: dict[str, str | bytes] = {"Bucket": self.bucket, "Key": key, "Body": data}
        if self.sse:
            options["ServerSideEncryption"] = self.sse
        if self.kms_key_id:
            options["SSEKMSKeyId"] = self.kms_key_id
        self.client.put_object(**options)
        return f"s3://{self.bucket}/{key}"

    def get(self, storage_uri: str) -> bytes:
        return self.client.get_object(Bucket=self.bucket, Key=self._parse_uri(storage_uri))["Body"].read()

    def exists(self, storage_uri: str) -> bool:
        try:
            self.client.head_object(Bucket=self.bucket, Key=self._parse_uri(storage_uri))
        except self.client.exceptions.ClientError as error:
            if error.response.get("Error", {}).get("Code") in {"404", "NoSuchKey", "NotFound"}:
                return False
            raise
        return True

    def delete(self, storage_uri: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=self._parse_uri(storage_uri))


def make_object_store(root: str | Path | None = None) -> ObjectStore:
    backend = os.getenv("ARCHIVE_OBJECT_STORE_BACKEND", "filesystem")
    if backend == "filesystem":
        return FilesystemObjectStore(root)
    if backend == "s3":
        return S3ObjectStore()
    raise RuntimeError(f"Unsupported Archive object store backend: {backend}")
