"""Legacy-compatible artifact reads — Upgrade 0, Phase 0B-3A.

The Factory keeps customer binaries in two legacy places: base64 inside
`projects.data` (e.g. `pdf_bytes`) and files on disk under EXPORTS_DIR.
Phase 0B-3A introduces the storage layer beside them without moving
anything, so every read must still work exactly as it does today.

These helpers read an artifact by preferring a recorded asset and falling
back to the legacy representation. Nothing here writes, deletes, or
changes existing behaviour: the customer download path is untouched in
0B-3A and still reads its legacy locations directly. This is the plumbing
0B-3B will switch over, proven in place first.

THE FALLBACK IS PERMANENT UNTIL A COPY IS VERIFIED
--------------------------------------------------
A missing asset means "read the legacy copy", never "the artifact is
gone". A storage outage must degrade to the legacy copy, not to an error,
which is why storage failures here are swallowed in favour of the legacy
path rather than raised.
"""
from __future__ import annotations

import base64
import binascii

from services.storage import StorageError, get_storage
from services.storage.keys import KIND_PDF, embedded_key


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


def read_asset_or_legacy(
    project_id: int,
    data: dict | None,
    *,
    field: str = "pdf_bytes",
    kind: str = KIND_PDF,
) -> bytes | None:
    """Return artifact bytes, preferring stored assets over the legacy blob.

    Order is deliberate:
      1. the storage layer, when an object exists at the deterministic key
      2. the legacy embedded base64 field
      3. None

    During 0B-3A step 1 never finds anything, because nothing has been
    migrated. The path exists, is tested, and stays dormant until 0B-3B.
    """
    pid = int(project_id or 0)
    if pid > 0:
        try:
            key = embedded_key(pid, field, kind)
            storage = get_storage()
            if storage.exists(key):
                return storage.get(key)
        except (StorageError, ValueError):
            # Never let a storage problem hide a perfectly good legacy copy.
            pass

    return decode_embedded((data or {}).get(field))


def legacy_embedded_fields(data: dict | None) -> dict[str, int]:
    """Map every embedded binary field present to its decoded byte size.

    Used by migration planning and by tests that assert 0B-3A left the
    legacy representation completely untouched.
    """
    found: dict[str, int] = {}
    for field in ("pdf_bytes", "zip_bytes", "cover_preview_b64", "sample_preview_b64"):
        raw = decode_embedded((data or {}).get(field))
        if raw:
            found[field] = len(raw)
    return found
