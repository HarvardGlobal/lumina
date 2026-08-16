"""Storage abstraction for immutable Archive bytes.

The local backend is private filesystem storage mounted into the Archive
container. The business layer only handles opaque URIs, so an S3/MinIO backend
can be added without changing catalogue or API semantics.
"""

from __future__ import annotations

import os
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
        self.root = Path(root or os.getenv("ARCHIVE_OBJECT_STORE_ROOT", "/tmp/lumina-archive-objects")).resolve()
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


def make_object_store(root: str | Path | None = None) -> ObjectStore:
    backend = os.getenv("ARCHIVE_OBJECT_STORE_BACKEND", "filesystem")
    if backend != "filesystem":
        raise RuntimeError(f"Unsupported Archive object store backend: {backend}")
    return FilesystemObjectStore(root)
