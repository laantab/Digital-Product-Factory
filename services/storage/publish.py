"""Publishing a file the builder just made — v1.8.1.

WHY THIS IS NOT MIGRATION
-------------------------
`services/storage/executor.migrate_artifact` moves EXISTING customer
artifacts, and it refuses to run unless customer migration is explicitly
enabled, because moving a customer's only copy of a finished book is an
owner decision (Phase 0B-3B2). None of that applies here.

This publishes a file that has just been created, in this run, by the
builder. There is no legacy copy to endanger and nothing to move: the bytes
are written to storage in addition to the disk they were already written to.
Enabling it changes no existing artifact.

WHY IT IS NEEDED AT ALL
-----------------------
The website and the builder are two Render services with two filesystems.
A cover the builder renders onto its own disk is on a disk the website
cannot read, and the disk disappears when the task ends. The customer would
watch for a cover that is already built and can never be served.

`services/storage/compat.read_export_or_legacy` already reads asset-first
and falls back to the local file, so publishing here is all that is needed
to make a builder-produced file readable by the web process. Inline mode
keeps writing the same local file and keeps reading it from disk, so
nothing about local Windows development changes.

FAILING TO PUBLISH IS NOT FATAL
-------------------------------
Every function here returns a bool and never raises. In inline mode the
local file is authoritative anyway, and in workflow mode a failure to
publish is a cover that does not appear -- bad, and logged loudly -- but not
a reason to throw away a book that has otherwise been built correctly.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

log = logging.getLogger(__name__)

#: Publishing is on whenever the builder owns heavy work, and off otherwise
#: so a local Windows checkout never talks to a storage backend it has no
#: reason to use.
ENV_FORCE = "FACTORY_PUBLISH_EXPORTS"


def publishing_enabled() -> bool:
    """Whether newly created files should also go to storage.

    On in workflow mode, because the two services share no disk. Off inline,
    because the one disk is the one the website reads. `FACTORY_PUBLISH_EXPORTS`
    forces it either way, which is what the tests use.
    """
    forced = str(os.environ.get(ENV_FORCE) or "").strip().lower()
    if forced in ("1", "true", "yes", "on"):
        return True
    if forced in ("0", "false", "no", "off"):
        return False
    try:
        from services.jobs import mode

        return mode.is_workflow_mode()
    except Exception:                                  # noqa: BLE001
        return False


#: Finished files whose earlier version is kept when a book is exported again.
_KEEP_PREVIOUS = ("ebook.pdf", "package.zip")


def previous_relative_path(relative_path: str, old_sha256: str) -> str:
    folder, _, name = str(relative_path).rpartition("/")
    return f"{folder}/previous/{old_sha256[:16]}/{name}" if folder else f"previous/{old_sha256[:16]}/{name}"


def _keep_previous_export(pid: int, relative_path: str, key: str, payload: bytes, driver,
                          content_type: str) -> bool:
    """v1.9.11: before a new PDF or ZIP replaces the stored one, keep the old one.

    Container Gardening for Beginners had to be re-exported twice while its
    only copies lived at the key the export overwrites; nothing recoverable
    was kept. The old bytes are copied to <package>/previous/<sha16>/<name>,
    read back and checksum-verified, and recorded as an approved
    'export_previous' asset. Returns False -- and the caller refuses to
    overwrite -- if an existing different file could not be kept.
    """
    name = relative_path.rpartition("/")[2]
    if name not in _KEEP_PREVIOUS:
        return True
    from services.storage.base import sha256_hex
    from services.storage.keys import export_object_key

    try:
        old = driver.get(key)
    except Exception:  # noqa: BLE001
        old = None
    if not old or sha256_hex(old) == sha256_hex(payload):
        return True
    old_sha = sha256_hex(old)
    prev_rel = previous_relative_path(relative_path, old_sha)
    prev_key = export_object_key(pid, prev_rel)
    try:
        driver.put(prev_key, old, content_type=content_type)
        back = driver.get(prev_key)
        if back is None or sha256_hex(back) != old_sha:
            return False
        import database

        database.record_asset(pid, "export_previous", prev_key, content_type=content_type,
                              byte_size=len(old), checksum=old_sha, approved=True)
        return True
    except Exception:  # noqa: BLE001
        log.exception("could not keep the previous %s", key)
        return False


def publish_export(project_id: int, relative_path: str,
                   payload: bytes | None = None,
                   source_path: str | Path | None = None,
                   *, kind: str = "export_file",
                   content_type: str = "application/octet-stream") -> bool:
    """Put a newly created export file in storage and record it as an asset.

    `relative_path` is the path under the exports root, which is the key the
    website's reader already derives. Returns True when the file is readable
    from storage afterwards.
    """
    if not publishing_enabled():
        return False

    pid = int(project_id or 0)
    if pid <= 0 or not str(relative_path or "").strip():
        return False

    try:
        if payload is None:
            if source_path is None:
                return False
            payload = Path(source_path).read_bytes()
        payload = bytes(payload)
        if not payload:
            return False

        from services.storage import get_storage
        from services.storage.base import sha256_hex
        from services.storage.keys import export_object_key

        key = export_object_key(pid, str(relative_path))
        driver = get_storage()
        if not _keep_previous_export(pid, str(relative_path), key, payload, driver, content_type):
            log.error("refused to overwrite %s: its previous version could not be kept", key)
            return False
        driver.put(key, payload, content_type=content_type)

        # COPY -> VERIFY -> READ BACK -> VERIFY -> RECORD, in that order, and
        # only then marked approved.
        #
        # `approved` is not a formality. `compat.verified_asset_bytes` refuses
        # to serve an asset that is not approved, and it is right to: an asset
        # row is TRUSTED by the reader, which stops falling back to disk the
        # moment one exists. Recording a row before proving the bytes can be
        # read back would turn a servable cover into a missing one, which is
        # worse than never having published it.
        checksum = sha256_hex(payload)
        stat = driver.stat(key)
        if stat is None or int(getattr(stat, "size", 0) or 0) != len(payload):
            log.error("published %s but its size did not verify", key)
            return False

        readback = driver.get(key)
        if readback is None or len(readback) != len(payload):
            log.error("published %s but it did not read back", key)
            return False
        if sha256_hex(readback) != checksum:
            log.error("published %s but the read-back checksum differs", key)
            return False

        import database

        database.record_asset(pid, str(kind), key,
                              content_type=str(content_type),
                              byte_size=len(payload), checksum=checksum,
                              approved=True)
        log.info("published %s (%s bytes)", key, len(payload))
        return True
    except Exception:                                  # noqa: BLE001
        log.exception("could not publish %s for project %s",
                      relative_path, project_id)
        return False


def publish_file(project_id: int, exports_root: str | Path,
                 path: str | Path, *, kind: str = "export_file",
                 content_type: str = "application/octet-stream") -> bool:
    """Publish a file already written to disk, deriving its relative path."""
    if not publishing_enabled():
        return False
    try:
        rel = os.path.relpath(str(path), str(exports_root)).replace(os.sep, "/")
    except Exception:                                  # noqa: BLE001
        return False
    if rel.startswith(".."):
        # Outside the exports root: not an export, and not ours to publish.
        return False
    return publish_export(project_id, rel, source_path=path,
                          kind=kind, content_type=content_type)
