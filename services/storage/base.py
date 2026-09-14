"""Storage driver contract — Upgrade 0, Phase 0B-3A.

WHY THIS EXISTS
---------------
Customer artifacts live in two incompatible places today: files on the
web service's local disk under EXPORTS_DIR, and base64 binaries embedded
directly inside `projects.data` (73 of 114 local rows, largest ~56 MB).
Neither can be reached by a second process, because a Render persistent
disk is accessible by exactly one service instance and a 56 MB row is
rewritten in full on every checkpoint.

This module defines the one boundary every artifact will eventually pass
through, so the 30+ modules that write artifacts today keep their call
semantics while what sits behind them changes from local disk to shared
object storage.

SCOPE OF 0B-3A
--------------
The interface and a local filesystem driver exist and are proven. No
customer binary is migrated, no `pdf_bytes` is removed, no existing file
is moved, and the download path still reads legacy locations. The S3
driver is a written contract only — nothing is provisioned.
"""
from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from dataclasses import dataclass


class StorageError(RuntimeError):
    """Any storage failure. Never let one destroy a legacy copy."""


class StorageKeyNotFound(StorageError):
    """The requested key does not exist in this backend."""


@dataclass(frozen=True)
class StorageStat:
    """What a backend can say about a stored object without reading it."""

    key: str
    size: int
    checksum: str  # sha256 hex of the stored bytes
    content_type: str = "application/octet-stream"
    modified_at: str | None = None


def sha256_hex(data: bytes) -> str:
    """The one checksum function for the whole storage layer.

    Used both to verify a put round-tripped and, later, to prove a
    migrated binary is byte-identical to the legacy copy before that
    legacy copy is ever removed.
    """
    return hashlib.sha256(data).hexdigest()


class StorageDriver(ABC):
    """put / get / exists / delete / stat over opaque byte payloads.

    Deliberately small. Drivers deal in bytes and keys and know nothing
    about products, projects, QA or approval; that meaning lives in the
    `assets` table. A driver that can honour these five operations can be
    swapped in without any caller changing.
    """

    #: Short identifier for logs and health checks ("local", "s3").
    name: str = "base"

    @abstractmethod
    def put(
        self,
        key: str,
        data: bytes,
        *,
        content_type: str = "application/octet-stream",
    ) -> StorageStat:
        """Store `data` at `key`, overwriting any existing object.

        Must be atomic enough that a failure never leaves a truncated
        object readable at `key`, and must verify what it wrote before
        reporting success.
        """

    @abstractmethod
    def get(self, key: str) -> bytes:
        """Return the stored bytes. Raise StorageKeyNotFound if absent."""

    @abstractmethod
    def exists(self, key: str) -> bool:
        """True when an object is stored at `key`."""

    @abstractmethod
    def delete(self, key: str) -> bool:
        """Remove `key`. Returns False when it was already absent.

        Never called by 0B-3A against a customer artifact. Present so the
        contract is complete and testable.
        """

    @abstractmethod
    def stat(self, key: str) -> StorageStat | None:
        """Metadata for `key`, or None when absent."""

    # -- convenience shared by every driver -------------------------------

    def verify(self, key: str, *, expected_checksum: str, expected_size: int) -> bool:
        """Read back and confirm a stored object matches what was written.

        This is the VERIFY READBACK step of the migration safety contract:
        COPY -> VERIFY CHECKSUM/BYTE COUNT -> RECORD ASSET -> VERIFY
        READBACK -> ONLY THEN REMOVE LEGACY BINARY.
        """
        stat = self.stat(key)
        if stat is None:
            return False
        if int(stat.size) != int(expected_size):
            return False
        if stat.checksum != expected_checksum:
            return False
        # Full read-back: stat alone can be satisfied by metadata that no
        # longer matches the bytes.
        try:
            return sha256_hex(self.get(key)) == expected_checksum
        except StorageError:
            return False
