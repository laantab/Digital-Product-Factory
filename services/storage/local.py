"""Local filesystem storage driver — Upgrade 0, Phase 0B-3A.

The Factory must keep running on exactly the infrastructure it has today
while the storage boundary is introduced, so the first driver writes to
the same persistent disk everything already uses. Nothing external is
required, nothing is provisioned, and no existing file is touched.

Writes are atomic: bytes go to a temporary file in the same directory and
are renamed into place only after being flushed and verified, so an
interrupted put can never leave a truncated object readable at its key.
That property is what lets the later migration trust a copy before it
removes anything.
"""
from __future__ import annotations

import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from services.storage.base import (
    StorageDriver,
    StorageError,
    StorageKeyNotFound,
    StorageStat,
    sha256_hex,
)
from services.storage.keys import is_valid_key


def default_storage_root() -> Path:
    """Where local objects live.

    Defaults to an `_assets` folder beside the existing exports tree, so
    it lands on the same persistent disk as everything else and cannot
    collide with an existing `exports/<package_id>/` directory. Override
    with FACTORY_STORAGE_DIR; nothing in production sets it today.
    """
    configured = str(os.environ.get("FACTORY_STORAGE_DIR") or "").strip()
    if configured:
        return Path(configured)

    exports = (
        str(os.environ.get("FACTORY_EXPORTS_DIR") or "").strip()
        or str(os.environ.get("FLASK_EXPORTS_DIR") or "").strip()
    )
    if exports:
        return Path(exports) / "_assets"
    return Path(__file__).resolve().parents[2] / "exports" / "_assets"


class LocalFilesystemDriver(StorageDriver):
    """StorageDriver backed by a directory tree."""

    name = "local"

    def __init__(self, root: str | os.PathLike[str] | None = None):
        self.root = Path(root) if root is not None else default_storage_root()

    # -- internals --------------------------------------------------------

    def _path(self, key: str) -> Path:
        if not is_valid_key(key):
            raise StorageError(f"invalid storage key: {key!r}")
        path = (self.root / key).resolve()
        root = self.root.resolve()
        # Defence in depth: is_valid_key already rejects traversal, but a
        # storage layer should never be one bug away from writing outside
        # its own root.
        if root != path and root not in path.parents:
            raise StorageError(f"storage key escapes root: {key!r}")
        return path

    # -- StorageDriver ----------------------------------------------------

    def put(
        self,
        key: str,
        data: bytes,
        *,
        content_type: str = "application/octet-stream",
    ) -> StorageStat:
        if not isinstance(data, (bytes, bytearray)):
            raise StorageError("storage put requires bytes")
        payload = bytes(data)
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)

        tmp_name = None
        try:
            fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), suffix=".part")
            with os.fdopen(fd, "wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_name, path)
            tmp_name = None
        except OSError as exc:
            raise StorageError(f"could not store {key!r}: {exc}") from exc
        finally:
            if tmp_name and os.path.exists(tmp_name):
                try:
                    os.unlink(tmp_name)
                except OSError:
                    pass

        stat = self.stat(key)
        if stat is None or stat.size != len(payload):
            raise StorageError(f"stored object {key!r} did not verify after write")
        return StorageStat(
            key=key,
            size=stat.size,
            checksum=stat.checksum,
            content_type=content_type,
            modified_at=stat.modified_at,
        )

    def get(self, key: str) -> bytes:
        path = self._path(key)
        try:
            return path.read_bytes()
        except FileNotFoundError as exc:
            raise StorageKeyNotFound(f"no object at {key!r}") from exc
        except OSError as exc:
            raise StorageError(f"could not read {key!r}: {exc}") from exc

    def exists(self, key: str) -> bool:
        try:
            return self._path(key).is_file()
        except StorageError:
            return False

    def delete(self, key: str) -> bool:
        path = self._path(key)
        try:
            path.unlink()
            return True
        except FileNotFoundError:
            return False
        except OSError as exc:
            raise StorageError(f"could not delete {key!r}: {exc}") from exc

    def stat(self, key: str) -> StorageStat | None:
        try:
            path = self._path(key)
        except StorageError:
            return None
        if not path.is_file():
            return None
        try:
            raw = path.read_bytes()
            modified = datetime.fromtimestamp(
                path.stat().st_mtime, tz=timezone.utc
            ).isoformat()
        except OSError:
            return None
        return StorageStat(
            key=key,
            size=len(raw),
            checksum=sha256_hex(raw),
            modified_at=modified,
        )
