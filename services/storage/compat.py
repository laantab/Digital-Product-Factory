"""Legacy-compatible artifact reads — Upgrade 0, Phases 0B-3A / 0B-3B1.

The Factory keeps customer binaries in two legacy places: base64 inside
`projects.data` (e.g. `pdf_bytes`) and files on disk under EXPORTS_DIR.
0B-3B1 converts the READERS to prefer a new stored asset while keeping
both legacy sources authoritative as fallback. No bytes have moved, so
with zero asset rows every function here behaves exactly as it did
before: a no-op for every existing customer.

THE ONE RULE
------------
A broken new asset must NEVER hide a valid legacy artifact.

An asset is usable only when ALL of these hold:

  * an `assets` metadata row exists for the key
  * the object exists in storage
  * the byte count matches the recorded size
  * the SHA-256 matches the recorded checksum

If the new copy is missing, unreadable, corrupt, the wrong size, the
wrong checksum, or unavailable because storage is down, the legacy source
is used whenever one exists. Every storage failure is swallowed in favour
of the legacy path -- an outage must degrade to the old copy, never to an
error the customer can see.
"""
from __future__ import annotations

import base64
import binascii
from pathlib import Path

from services.storage import StorageError, get_storage, sha256_hex
from services.storage.keys import (
    InvalidStorageKey,
    KIND_PDF,
    embedded_key,
    export_object_key,
)


def decode_embedded(value: object) -> bytes | None:
    """Decode a base64 field from `projects.data`, tolerating junk.

    Returns None rather than raising: a malformed legacy field is a fact
    to report during migration planning, not a crash during a read.
    """
    if isinstance(value, (bytes, bytearray)):
        return bytes(value)
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return base64.b64decode(text, validate=False)
    except (binascii.Error, ValueError):
        return None


def _asset_record(storage_key: str) -> dict | None:
    try:
        import database

        return database.get_asset_by_key(storage_key)
    except Exception:
        # A database hiccup must not stop the legacy read either.
        return None


def verified_asset_bytes(storage_key: str) -> bytes | None:
    """Bytes for `storage_key`, but ONLY if they pass full verification.

    Returns None for every failure mode -- no record, no object, wrong
    size, wrong checksum, storage down, corrupt payload. None means
    "fall back", never "the artifact is gone".
    """
    key = str(storage_key or "")
    if not key:
        return None

    record = _asset_record(key)
    if not record:
        return None

    expected_size = int(record.get("byte_size") or 0)
    expected_sum = str(record.get("checksum") or "")
    if expected_size <= 0 or not expected_sum:
        # An asset row that cannot prove its own contents is not usable.
        return None

    try:
        storage = get_storage()
        stat = storage.stat(key)
        if stat is None or int(stat.size) != expected_size:
            return None
        payload = storage.get(key)
    except (StorageError, ValueError, OSError):
        return None
    except Exception:
        # Any unexpected backend failure behaves the same way: fall back.
        return None

    if payload is None or len(payload) != expected_size:
        return None
    if sha256_hex(payload) != expected_sum:
        return None
    return payload


def read_asset_or_legacy(
    project_id: int,
    data: dict | None,
    *,
    field: str = "pdf_bytes",
    kind: str = KIND_PDF,
) -> bytes | None:
    """Artifact bytes for an embedded binary: verified asset, else legacy.

    Order is deliberate:
      1. the new asset, but only when fully verified
      2. the legacy embedded base64 field
      3. None
    """
    pid = int(project_id or 0)
    if pid > 0:
        try:
            payload = verified_asset_bytes(embedded_key(pid, field, kind))
        except (InvalidStorageKey, ValueError):
            payload = None
        if payload is not None:
            return payload

    return decode_embedded((data or {}).get(field))


def read_export_or_legacy(
    project_id: int,
    relative_path: str,
    legacy_path: str | Path | None = None,
) -> bytes | None:
    """Bytes for an export file: verified asset, else the file on disk.

    `relative_path` is the artifact's path relative to the exports root --
    the canonical key input. `package_id` is never used to build the key,
    because it does not reliably name the directory the file lives in.
    """
    pid = int(project_id or 0)
    if pid > 0 and relative_path:
        try:
            payload = verified_asset_bytes(export_object_key(pid, relative_path))
        except (InvalidStorageKey, ValueError):
            payload = None
        if payload is not None:
            return payload

    if legacy_path:
        try:
            path = Path(legacy_path)
            if path.is_file():
                return path.read_bytes()
        except OSError:
            return None
    return None


def export_asset_is_available(project_id: int, relative_path: str) -> bool:
    """True when a verified asset could serve this export file.

    Used by Saved Projects so an asset-backed product stays visible even
    if its disk copy is gone. Verification is full, not a key lookup: an
    unverifiable asset must not make a product appear downloadable.
    """
    pid = int(project_id or 0)
    if pid <= 0 or not relative_path:
        return False
    try:
        return verified_asset_bytes(export_object_key(pid, relative_path)) is not None
    except (InvalidStorageKey, ValueError):
        return False


def legacy_embedded_fields(data: dict | None) -> dict[str, int]:
    """Map every embedded binary field present to its decoded byte size.

    Used by migration planning and by tests that assert the legacy
    representation was left completely untouched.
    """
    found: dict[str, int] = {}
    for field in ("pdf_bytes", "zip_bytes", "cover_preview_b64", "sample_preview_b64"):
        raw = decode_embedded((data or {}).get(field))
        if raw:
            found[field] = len(raw)
    return found
