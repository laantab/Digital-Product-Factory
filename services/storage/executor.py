"""Migration executor — Upgrade 0, Phase 0B-3B1.

Executes ONE artifact copy under a sequence that cannot lose a customer's
work. Execution against existing customer artifacts is DISABLED in this
phase: `migrate_artifact()` refuses unless explicitly enabled, and the
only thing that enables it is an argument a caller has to pass on
purpose. Nothing in the Factory passes it.

THE SEQUENCE
------------
    COPY
      -> VERIFY BYTE COUNT
      -> VERIFY SHA-256
      -> RECORD/UPDATE ASSET
      -> READ OBJECT BACK
      -> VERIFY READBACK SHA-256
      -> MARK VERIFIED
      -> KEEP LEGACY COPY

There is NO legacy deletion step in 0B-3B1. The source is never touched,
on success or on failure. Deleting a legacy copy is a separate, later,
separately-approved decision.

PROPERTIES
----------
restartable   every step re-derives its inputs from the source; an
              interrupted run resumes by simply running again
idempotent    deterministic keys plus a UNIQUE storage_key mean a second
              run re-records one asset instead of creating a duplicate
deterministic the same artifact always produces the same key and checksum
interruption- no step depends on in-memory state from a previous step, so
safe          a killed process leaves either "not migrated" or "migrated
              and verified", never a half state that reads as success
non-destructive  the executor has no code path that deletes or writes the
              source, so a failure cannot damage it
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from services.storage import StorageError, get_storage, sha256_hex
from services.storage.keys import InvalidStorageKey, is_valid_key

#: Steps, in order, for reporting where a migration stopped.
STEP_COPY = "copy"
STEP_VERIFY_SIZE = "verify_byte_count"
STEP_VERIFY_CHECKSUM = "verify_sha256"
STEP_RECORD = "record_asset"
STEP_READBACK = "read_object_back"
STEP_VERIFY_READBACK = "verify_readback_sha256"
STEP_MARK_VERIFIED = "mark_verified"
STEP_DONE = "done"


class MigrationDisabled(RuntimeError):
    """Execution against existing customer artifacts is not authorized."""


@dataclass
class MigrationOutcome:
    ok: bool
    storage_key: str
    step_reached: str
    byte_size: int = 0
    checksum: str = ""
    already_present: bool = False
    asset_id: int | None = None
    error: str = ""
    #: Always True in 0B-3B1. There is no deletion step.
    legacy_kept: bool = True

    def as_dict(self) -> dict:
        return {
            "ok": self.ok,
            "storage_key": self.storage_key,
            "step_reached": self.step_reached,
            "byte_size": self.byte_size,
            "checksum": self.checksum,
            "already_present": self.already_present,
            "asset_id": self.asset_id,
            "error": self.error,
            "legacy_kept": self.legacy_kept,
        }


def _failure(key: str, step: str, message: str) -> MigrationOutcome:
    # The source was never written to, so it is unchanged by construction.
    return MigrationOutcome(
        ok=False, storage_key=key, step_reached=step, error=message, legacy_kept=True
    )


def migrate_artifact(
    *,
    project_id: int,
    storage_key: str,
    source_bytes: bytes | None = None,
    source_path: str | Path | None = None,
    kind: str,
    content_type: str = "application/octet-stream",
    enable_customer_migration: bool = False,
    storage=None,
) -> MigrationOutcome:
    """Migrate one artifact. Refuses to run unless explicitly enabled.

    Exactly one of `source_bytes` or `source_path` identifies the source.
    The source is read but never written, moved, or deleted -- there is no
    code path here that can modify it.
    """
    if not enable_customer_migration:
        raise MigrationDisabled(
            "Customer artifact migration is disabled in Phase 0B-3B1. "
            "The 73 embedded PDFs and the export files stay where they are "
            "until Phase 0B-3B2 is approved."
        )

    key = str(storage_key or "")
    if not is_valid_key(key):
        return _failure(key, STEP_COPY, f"invalid storage key: {key!r}")
    pid = int(project_id or 0)
    if pid <= 0:
        return _failure(key, STEP_COPY, "invalid project id")

    # ---- read the source (read-only, always) ----------------------------
    if source_bytes is None and source_path is None:
        return _failure(key, STEP_COPY, "no source supplied")
    if source_bytes is not None and source_path is not None:
        return _failure(key, STEP_COPY, "supply exactly one source")
    if source_bytes is None:
        try:
            payload = Path(source_path).read_bytes()
        except OSError as exc:
            return _failure(key, STEP_COPY, f"cannot read source: {exc}")
    else:
        payload = bytes(source_bytes)

    if not payload:
        return _failure(key, STEP_COPY, "source is empty")

    expected_size = len(payload)
    expected_sum = sha256_hex(payload)
    driver = storage if storage is not None else get_storage()

    # ---- idempotence: is a verified copy already there? -----------------
    # Checked before writing so a rerun is cheap and cannot duplicate.
    already = False
    try:
        existing = driver.stat(key)
        if (
            existing is not None
            and int(existing.size) == expected_size
            and existing.checksum == expected_sum
        ):
            already = True
    except (StorageError, InvalidStorageKey):
        existing = None

    # ---- STEP 1: COPY ---------------------------------------------------
    if not already:
        try:
            driver.put(key, payload, content_type=content_type)
        except (StorageError, InvalidStorageKey, OSError) as exc:
            # Upload failed. The source has not been touched.
            return _failure(key, STEP_COPY, f"upload failed: {exc}")

    # ---- STEP 2: VERIFY BYTE COUNT --------------------------------------
    try:
        stored = driver.stat(key)
    except (StorageError, InvalidStorageKey) as exc:
        return _failure(key, STEP_VERIFY_SIZE, f"cannot stat stored object: {exc}")
    if stored is None:
        return _failure(key, STEP_VERIFY_SIZE, "stored object is missing after upload")
    if int(stored.size) != expected_size:
        return _failure(
            key,
            STEP_VERIFY_SIZE,
            f"byte count mismatch: stored {stored.size}, source {expected_size}",
        )

    # ---- STEP 3: VERIFY SHA-256 -----------------------------------------
    if stored.checksum != expected_sum:
        return _failure(
            key, STEP_VERIFY_CHECKSUM, "checksum mismatch between source and stored object"
        )

    # ---- STEP 4: RECORD / UPDATE ASSET ----------------------------------
    # Idempotent on storage_key, so a second run updates one row.
    try:
        import database

        record = database.record_asset(
            pid,
            kind,
            key,
            content_type=content_type,
            byte_size=expected_size,
            checksum=expected_sum,
            approved=False,
        )
    except Exception as exc:
        # Metadata write failed. The object is in storage but no asset row
        # claims it, so every reader still uses the legacy source and the
        # source itself is untouched. Rerunning completes the migration.
        return _failure(key, STEP_RECORD, f"asset record failed: {exc}")

    # ---- STEP 5: READ OBJECT BACK ---------------------------------------
    try:
        readback = driver.get(key)
    except (StorageError, InvalidStorageKey) as exc:
        return _failure(key, STEP_READBACK, f"readback failed: {exc}")

    # ---- STEP 6: VERIFY READBACK SHA-256 --------------------------------
    if readback is None or len(readback) != expected_size:
        return _failure(key, STEP_VERIFY_READBACK, "readback byte count mismatch")
    if sha256_hex(readback) != expected_sum:
        return _failure(key, STEP_VERIFY_READBACK, "readback checksum mismatch")

    # ---- STEP 7: MARK VERIFIED ------------------------------------------
    # Only now is the asset allowed to be preferred over the legacy copy.
    try:
        import database

        record = database.record_asset(
            pid,
            kind,
            key,
            content_type=content_type,
            byte_size=expected_size,
            checksum=expected_sum,
            approved=True,
        )
    except Exception as exc:
        return _failure(key, STEP_MARK_VERIFIED, f"could not mark verified: {exc}")

    # ---- STEP 8: KEEP LEGACY COPY ---------------------------------------
    # Nothing to do, deliberately. There is no deletion step in 0B-3B1.
    return MigrationOutcome(
        ok=True,
        storage_key=key,
        step_reached=STEP_DONE,
        byte_size=expected_size,
        checksum=expected_sum,
        already_present=already,
        asset_id=(record or {}).get("id"),
        legacy_kept=True,
    )
