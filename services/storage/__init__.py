"""Factory storage layer — Upgrade 0, Phase 0B-3A.

One boundary for every customer artifact. Local filesystem today, shared
object storage later, without any caller changing.

Phase 0B-3A is foundation only: nothing is migrated, no `pdf_bytes` is
removed, no existing export file is moved, and the customer download path
still reads its legacy locations with the legacy fallback intact.
"""
from __future__ import annotations

import os

from services.storage.base import (
    StorageDriver,
    StorageError,
    StorageKeyNotFound,
    StorageStat,
    sha256_hex,
)
from services.storage.keys import (
    KIND_COVER,
    KIND_INTERIOR_IMAGE,
    KIND_MARKETING_IMAGE,
    KIND_PDF,
    KIND_PREVIEW,
    KIND_ZIP,
    KINDS,
    InvalidStorageKey,
    embedded_key,
    export_key,
    is_valid_key,
    project_prefix,
)
from services.storage.local import LocalFilesystemDriver, default_storage_root

__all__ = [
    "StorageDriver",
    "StorageError",
    "StorageKeyNotFound",
    "StorageStat",
    "sha256_hex",
    "LocalFilesystemDriver",
    "default_storage_root",
    "get_storage",
    "reset_storage",
    "embedded_key",
    "export_key",
    "project_prefix",
    "is_valid_key",
    "InvalidStorageKey",
    "KINDS",
    "KIND_PDF",
    "KIND_ZIP",
    "KIND_COVER",
    "KIND_PREVIEW",
    "KIND_INTERIOR_IMAGE",
    "KIND_MARKETING_IMAGE",
]

_driver: StorageDriver | None = None


def get_storage() -> StorageDriver:
    """The active storage driver.

    Local by default, on the disk the Factory already uses, so no
    external infrastructure is required to run. FACTORY_STORAGE_DRIVER
    may select another backend later; nothing in production sets it
    today, and "s3" deliberately raises until a provider is approved.
    """
    global _driver
    if _driver is None:
        choice = str(os.environ.get("FACTORY_STORAGE_DRIVER") or "local").strip().lower()
        if choice in ("", "local", "filesystem"):
            _driver = LocalFilesystemDriver()
        elif choice in ("s3", "r2", "b2"):
            from services.storage.s3 import S3CompatibleDriver

            _driver = S3CompatibleDriver()
        else:
            raise StorageError(f"unknown storage driver: {choice!r}")
    return _driver


def reset_storage() -> None:
    """Drop the cached driver so configuration changes take effect. Tests."""
    global _driver
    _driver = None
