"""Production embedded-PDF migration, driven over HTTP — Phase 0B-3E.

WHY THIS EXISTS
---------------
The embedded-PDF migration was completed against the local database. The
production Factory runs on a Render persistent disk with its OWN SQLite
file, which no other machine can reach — a disk "is accessible by only a
single service instance". The Render plan in use has no Shell tab, so
there is no way to run the proven executor against production data.

This module is that missing hand. It exposes the SAME executor and the
SAME safety contract as the local migration, callable through one
token-gated admin route, so production can be migrated without a shell,
a new service, or a second implementation.

WHAT IT WILL NOT DO
-------------------
It never deletes or rewrites `pdf_bytes`. It never rewrites a project's
data blob or bumps a project version. It never regenerates a product. It
has no code path that removes a legacy artifact — the same rule the
executor already enforces:

    COPY -> VERIFY SIZE -> VERIFY SHA-256 -> RECORD -> READ BACK
         -> VERIFY READBACK -> MARK VERIFIED -> KEEP LEGACY

Every function here returns plain data with no secret in it.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import os
import shutil
import sqlite3
from datetime import datetime, timezone

from services.storage.keys import KIND_PDF, embedded_key

#: Only this many projects may be migrated in one request. Bounded work
#: per HTTP request is the same discipline that fixed the worker-timeout
#: defect in v1.7.10 -- a migration must never become a long request.
MAX_BATCH = 25


def _decode(value: object) -> bytes | None:
    if isinstance(value, (bytes, bytearray)):
        return bytes(value)
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return base64.b64decode(text, validate=False)
    except (binascii.Error, ValueError):
        return None


def database_path() -> str:
    import database

    return database.DB_PATH


def _rows():
    """Read every project id + data blob. Read-only connection."""
    import database

    conn = database.get_conn()
    try:
        return conn.execute("SELECT id, name, data FROM projects ORDER BY id").fetchall()
    finally:
        conn.close()


def _scan() -> dict:
    """Full scan. Returns the COMPLETE pending list, never truncated.

    `inventory()` trims the list for its HTTP response; `migrate()` must
    not work from a trimmed list, or a database with more eligible
    projects than the display cap would leave the tail unreachable.
    """
    import database

    path = database_path()
    existing = {a["storage_key"] for a in _all_assets()}

    scanned = eligible = already = 0
    problems: list[dict] = []
    pending: list[dict] = []
    total_bytes = 0

    for row in _rows():
        scanned += 1
        pid = int(row["id"])
        try:
            data = database._json_loads_safe(row["data"]) if hasattr(
                database, "_json_loads_safe") else __import__("json").loads(row["data"] or "{}")
        except Exception:
            problems.append({"project_id": pid, "problem": "unparseable data"})
            continue
        if not isinstance(data, dict) or not data.get("pdf_bytes"):
            continue

        decoded = _decode(data.get("pdf_bytes"))
        if decoded is None:
            problems.append({"project_id": pid, "problem": "undecodable base64"})
            continue
        if not decoded:
            problems.append({"project_id": pid, "problem": "zero bytes"})
            continue
        if decoded[:4] != b"%PDF":
            problems.append({"project_id": pid, "problem": "not a PDF signature"})
            continue

        eligible += 1
        key = embedded_key(pid, "pdf_bytes", KIND_PDF)
        if key in existing:
            already += 1
            continue
        total_bytes += len(decoded)
        pending.append({
            "project_id": pid,
            "bytes": len(decoded),
            "sha256": hashlib.sha256(decoded).hexdigest(),
            "storage_key": key,
            "product_type": str(data.get("product_type") or ""),
        })

    return {
        "database_path": path,
        "database_bytes": os.path.getsize(path) if os.path.exists(path) else 0,
        "projects_scanned": scanned,
        "projects_with_pdf_bytes": eligible,
        "already_migrated": already,
        "pending_migration": len(pending),
        "pending_bytes": total_bytes,
        "existing_asset_rows": len(existing),
        "problems": problems,
        "pending": pending,
    }


def inventory() -> dict:
    """DRY RUN. What a production migration would do. Writes nothing.

    The pending list is trimmed for the response; the totals above it are
    complete.
    """
    result = _scan()
    return {**result, "pending": result["pending"][:200],
            "pending_listed": min(len(result["pending"]), 200)}


#: R2 settings the driver requires. Reported by PRESENCE only -- a value
#: must never reach a shell, a log, or a report.
_R2_REQUIRED = (
    "FACTORY_R2_ACCOUNT_ID",
    "FACTORY_R2_BUCKET",
    "FACTORY_R2_ACCESS_KEY_ID",
    "FACTORY_R2_SECRET_ACCESS_KEY",
)


def environment() -> dict:
    """Configuration facts, with NO secret value in the output.

    Reports whether each required R2 setting is present, never what it
    contains. `storage_driver` is the thing that decides whether reads
    come from object storage at all, and on production it is expected to
    be unset until the migration is verified.
    """
    driver = str(os.environ.get("FACTORY_STORAGE_DRIVER") or "").strip()
    exports = ""
    exports_files = None
    try:
        import database

        exports = str(database._exports_root())
        if os.path.isdir(exports):
            exports_files = sum(len(f) for _, _, f in os.walk(exports))
    except Exception:
        pass

    return {
        "storage_driver": driver or "(unset -> local)",
        "r2_reads_enabled": driver.lower() == "r2",
        "r2_config_present": {name: bool(str(os.environ.get(name) or "").strip())
                              for name in _R2_REQUIRED},
        "r2_config_complete": all(
            str(os.environ.get(n) or "").strip() for n in _R2_REQUIRED),
        "exports_path": exports,
        "exports_files": exports_files,
    }


def _all_assets() -> list[dict]:
    import database

    conn = database.get_conn()
    try:
        rows = conn.execute("SELECT * FROM assets").fetchall()
    except sqlite3.Error:
        return []
    finally:
        conn.close()
    return [database._asset_row_to_dict(r) for r in rows]


def _sha_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def backup(label: str = "PRE-0B3E-PRODUCTION-MIGRATION") -> dict:
    """Timestamped byte-for-byte copy beside the production database.

    Additive: it never overwrites an earlier backup (the filename carries
    a timestamp) and never touches the source. Written next to the
    database, which on production means the persistent disk.
    """
    import database

    src = database_path()
    if not os.path.exists(src):
        return {"ok": False, "error": "database file not found"}

    # Checkpoint so the .db file is self-contained before it is copied.
    try:
        conn = database.get_conn()
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchall()
        conn.close()
    except sqlite3.Error:
        pass

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    dest = f"{src}.{label}-{stamp}.bak"
    # Never overwrite an earlier backup. Two runs inside the same second
    # get a suffix rather than a refusal -- a legitimate retry must not be
    # blocked by clock resolution, and an existing backup must not be lost.
    suffix = 1
    while os.path.exists(dest):
        suffix += 1
        dest = f"{src}.{label}-{stamp}-{suffix}.bak"
        if suffix > 50:
            return {"ok": False, "error": "too many backups this second"}

    shutil.copy2(src, dest)
    src_sha, dest_sha = _sha_file(src), _sha_file(dest)
    return {
        "ok": src_sha == dest_sha,
        "source_path": src,
        "backup_path": dest,
        "source_bytes": os.path.getsize(src),
        "backup_bytes": os.path.getsize(dest),
        "source_sha256": src_sha,
        "backup_sha256": dest_sha,
        "identical": src_sha == dest_sha,
    }


def migrate(limit: int = 10, project_ids: list[int] | None = None) -> dict:
    """Migrate up to `limit` eligible projects. Bounded and idempotent.

    Stops at the first failed verification rather than continuing, so a
    problem is isolated to one project instead of a whole batch.
    """
    import database
    from services.storage import get_storage
    from services.storage.executor import migrate_artifact

    limit = max(1, min(int(limit or 1), MAX_BATCH))
    plan = _scan()                      # full list, never the display cap
    pending = plan["pending"]
    if project_ids:
        wanted = {int(p) for p in project_ids}
        pending = [p for p in pending if p["project_id"] in wanted]
    pending = pending[:limit]

    # The migration writes to R2 explicitly, regardless of which driver the
    # app serves reads from. FACTORY_STORAGE_DRIVER stays whatever it is.
    from services.storage.r2 import R2Driver

    storage = R2Driver()

    migrated, failed, skipped = [], [], []
    moved_bytes = 0
    for item in pending:
        pid = item["project_id"]
        project = database.get_project(pid)
        data = (project or {}).get("data") or {}
        decoded = _decode(data.get("pdf_bytes"))
        if not decoded:
            skipped.append({"project_id": pid, "reason": "pdf_bytes unreadable at migrate time"})
            continue
        sha = hashlib.sha256(decoded).hexdigest()
        key = item["storage_key"]

        outcome = migrate_artifact(
            project_id=pid, storage_key=key, source_bytes=decoded, kind=KIND_PDF,
            content_type="application/pdf", enable_customer_migration=True,
            storage=storage,
        )
        if not outcome.ok:
            failed.append({"project_id": pid, "step": outcome.step_reached,
                           "error": outcome.error})
            break

        check = verify_one(pid, storage=storage)
        if not check.get("ok"):
            failed.append({"project_id": pid, "step": "verification", "error": check})
            break

        migrated.append(pid)
        moved_bytes += len(decoded)

    after = _scan()
    return {
        "migrated": migrated,
        "migrated_count": len(migrated),
        "bytes_migrated": moved_bytes,
        "skipped": skipped,
        "failed": failed,
        "remaining_after": after["pending_migration"],
        "asset_rows_after": after["existing_asset_rows"],
    }


def verify_one(project_id: int, storage=None) -> dict:
    """Re-verify one migrated project against its retained legacy blob."""
    import database

    if storage is None:
        from services.storage.r2 import R2Driver

        storage = R2Driver()

    pid = int(project_id)
    project = database.get_project(pid)
    if not project:
        return {"ok": False, "project_id": pid, "error": "no such project"}
    data = project.get("data") or {}
    legacy = _decode(data.get("pdf_bytes"))
    key = embedded_key(pid, "pdf_bytes", KIND_PDF)
    record = database.get_asset_by_key(key)

    if legacy is None:
        return {"ok": False, "project_id": pid, "error": "legacy pdf_bytes missing"}
    if not record:
        return {"ok": False, "project_id": pid, "error": "no asset row"}

    try:
        obj = storage.get(key)
    except Exception as exc:
        return {"ok": False, "project_id": pid, "error": f"cannot read object: {type(exc).__name__}"}

    checks = {
        "object_exists": True,
        "bytes_match_legacy": obj == legacy,
        "byte_count": len(obj) == len(legacy) == int(record["byte_size"]),
        "sha256": hashlib.sha256(obj).hexdigest() == record["checksum"]
        == hashlib.sha256(legacy).hexdigest(),
        "approved": bool(record["approved"]),
        "legacy_present": bool(data.get("pdf_bytes")),
    }
    return {
        "ok": all(checks.values()),
        "project_id": pid,
        "storage_key": key,
        "bytes": len(obj),
        "checks": checks,
    }


def verify_all(sample: int = 0, project_ids: list[int] | None = None) -> dict:
    """Verify migrated assets: all of them, a random sample, or named ones.

    `project_ids` narrows the check to specific projects, which is how a
    spot-check after a batch is done without re-reading every object.
    """
    import random

    from services.storage.r2 import R2Driver

    storage = R2Driver()
    assets = _all_assets()
    targets = assets
    if project_ids:
        wanted = {int(p) for p in project_ids}
        targets = [a for a in assets if a["project_id"] in wanted]
    elif sample and sample < len(assets):
        targets = random.sample(assets, sample)

    results = [verify_one(a["project_id"], storage=storage) for a in targets]
    bad = [r for r in results if not r.get("ok")]
    return {
        "asset_rows": len(assets),
        "verified": len(results),
        "passed": len(results) - len(bad),
        "failed": len(bad),
        "failures": bad[:20],
        "all_ok": not bad,
    }


def read_check(fallback_probe: bool = True) -> dict:
    """READ ONLY. Which source the REAL packaging reader actually chooses.

    `verify` proves the stored objects are intact. This proves something
    different and, after enabling R2 reads, more important: that the
    function the six packaging read sites actually call
    (`services.packaging._verified_embedded_pdf`) selects R2 rather than
    the legacy blob -- and that the bytes it returns are identical to the
    legacy copy.

    It deliberately does NOT call `build_product_export`, which would
    write export files. It only reads.

    With `fallback_probe`, it then proves the fallback on real production
    data by substituting a broken storage driver IN THIS PROCESS ONLY.
    No production object is touched, moved, corrupted or deleted.
    """
    import database
    from services.packaging import _verified_embedded_pdf

    env = environment()
    results = []
    for asset in _all_assets():
        pid = asset["project_id"]
        project = database.get_project(pid)
        if not project:
            results.append({"project_id": pid, "error": "project missing"})
            continue
        data = project.get("data") or {}
        legacy = _decode(data.get("pdf_bytes"))
        served = _verified_embedded_pdf(project, data)
        source = "R2" if served is not None else "LEGACY"
        used = served if served is not None else legacy
        results.append({
            "project_id": pid,
            "source": source,
            "bytes": len(used) if used else 0,
            "matches_legacy": bool(used and legacy and used == legacy),
            "sha256_ok": bool(
                used and hashlib.sha256(used).hexdigest() == asset["checksum"]),
            "valid_pdf": bool(used and used[:4] == b"%PDF"),
            "legacy_present": bool(data.get("pdf_bytes")),
        })

    report = {
        "storage_driver": env["storage_driver"],
        "r2_reads_enabled": env["r2_reads_enabled"],
        "assets_checked": len(results),
        "served_from_r2": sum(1 for r in results if r.get("source") == "R2"),
        "served_from_legacy": sum(1 for r in results if r.get("source") == "LEGACY"),
        "per_project": results,
    }

    if fallback_probe and results:
        report["fallback_probe"] = _fallback_probe(results[0]["project_id"])

    ok = bool(results) and all(
        r.get("matches_legacy") and r.get("sha256_ok") and r.get("valid_pdf")
        and r.get("legacy_present") for r in results)
    if env["r2_reads_enabled"]:
        ok = ok and report["served_from_r2"] == len(results)
    probe = report.get("fallback_probe") or {}
    if fallback_probe:
        ok = ok and probe.get("all_fell_back_to_legacy", False)
    report["ok"] = ok
    report["result"] = "PASS" if ok else "FAIL"
    return report


def _fallback_probe(project_id: int) -> dict:
    """Prove the fallback on real data without touching a real object.

    Each failure mode is simulated by replacing the storage driver for the
    duration of one in-process call. Production R2 objects are never
    written to, deleted, or modified.
    """
    import database
    from services.packaging import _verified_embedded_pdf
    from services.storage.base import StorageStat
    import services.storage.compat as compat

    project = database.get_project(int(project_id))
    data = (project or {}).get("data") or {}
    legacy = _decode(data.get("pdf_bytes"))
    if not legacy:
        return {"error": "no legacy copy to fall back to"}

    size, digest = len(legacy), hashlib.sha256(legacy).hexdigest()

    class _Outage:
        def stat(self, key): raise RuntimeError("simulated R2 outage")
        def get(self, key): raise RuntimeError("simulated R2 outage")

    class _Missing:
        def stat(self, key): return None
        def get(self, key): raise RuntimeError("no object")

    class _Corrupt:
        def stat(self, key): return StorageStat(key=key, size=size, checksum="0" * 64)
        def get(self, key): return b"not-the-real-pdf"

    class _WrongSize:
        def stat(self, key): return StorageStat(key=key, size=size + 999, checksum=digest)
        def get(self, key): return legacy

    real = compat.get_storage
    outcomes = {}
    try:
        for label, fake in (("r2_unavailable", _Outage()), ("object_missing", _Missing()),
                            ("checksum_mismatch", _Corrupt()), ("wrong_size", _WrongSize())):
            compat.get_storage = lambda f=fake: f
            served = _verified_embedded_pdf(project, data)
            used = served if served is not None else legacy
            outcomes[label] = {
                "used_legacy": served is None,
                "bytes": len(used),
                "sha256_ok": hashlib.sha256(used).hexdigest() == digest,
            }
    finally:
        compat.get_storage = real

    return {
        "project_id": int(project_id),
        "modes": outcomes,
        "all_fell_back_to_legacy": all(
            o["used_legacy"] and o["sha256_ok"] for o in outcomes.values()),
        "production_objects_touched": 0,
    }


#: Where a database has to live to count as "on the persistent disk".
#: Tests monkeypatch this; production never changes it.
PERSISTENT_DISK_PREFIXES = ("/var/data",)


def run_production_migration() -> dict:
    """The whole approved production sequence, as ONE guarded operation.

    SAFETY CHECK -> BACKUP (verified) -> RE-INVENTORY -> MIGRATE PENDING
    -> PER-PROJECT VERIFY -> POST-VERIFY -> FINAL INVENTORY

    Every gate is fail-closed: the migration does not start unless the
    database is on the persistent disk, R2 is fully configured, the
    storage driver is still unset, and the inventory reports no malformed
    records. It does not start unless a backup has been taken AND proven
    byte-identical. It stops at the first failure rather than continuing.

    It never deletes or rewrites `pdf_bytes`, never touches exports, never
    rewrites a project blob, never bumps a project version, and never
    changes any environment variable.
    """
    report: dict = {"ok": False, "aborted_at": None}

    # ---- 1. SAFETY CHECK ------------------------------------------------
    env = environment()
    before = _scan()
    path = str(before.get("database_path") or "")
    safety = {
        "on_persistent_disk": path.startswith(PERSISTENT_DISK_PREFIXES),
        "r2_config_complete": bool(env["r2_config_complete"]),
        "storage_driver_unset": not env["r2_reads_enabled"],
        "no_inventory_problems": not before["problems"],
        "something_to_migrate": before["pending_migration"] > 0,
    }
    report["database_path"] = path
    report["safety_check"] = safety
    report["storage_driver"] = env["storage_driver"]
    report["r2_reads_enabled"] = env["r2_reads_enabled"]
    if not all(safety.values()):
        report["aborted_at"] = "safety_check"
        report["reason"] = [k for k, v in safety.items() if not v]
        return report

    # ---- 2. BACKUP, VERIFIED --------------------------------------------
    saved = backup(label="PRE-R2-MIGRATION")
    report["backup"] = {
        "path": saved.get("backup_path"),
        "source_bytes": saved.get("source_bytes"),
        "backup_bytes": saved.get("backup_bytes"),
        "source_sha256": saved.get("source_sha256"),
        "backup_sha256": saved.get("backup_sha256"),
        "identical": bool(saved.get("identical")),
    }
    if not saved.get("ok") or not saved.get("identical"):
        report["aborted_at"] = "backup"
        report["reason"] = saved.get("error") or "backup did not verify byte-identical"
        return report

    # ---- 3. RE-INVENTORY ------------------------------------------------
    # Compared against the scan taken moments ago rather than hardcoded
    # figures: the live site may legitimately have gained a project, but
    # the numbers must not move underneath the migration.
    again = _scan()
    drift = {
        "projects_scanned": (before["projects_scanned"], again["projects_scanned"]),
        "projects_with_pdf_bytes": (before["projects_with_pdf_bytes"],
                                    again["projects_with_pdf_bytes"]),
        "pending_migration": (before["pending_migration"], again["pending_migration"]),
        "existing_asset_rows": (before["existing_asset_rows"],
                                again["existing_asset_rows"]),
    }
    report["inventory_before"] = {k: v[0] for k, v in drift.items()}
    changed = [k for k, (a, b) in drift.items() if a != b]
    if changed:
        report["aborted_at"] = "re_inventory"
        report["reason"] = f"state changed between scans: {changed}"
        report["drift"] = drift
        return report

    # ---- 4-5. MIGRATE THE PENDING SET, VERIFYING EACH -------------------
    pending_ids = [p["project_id"] for p in again["pending"]]
    outcome = migrate(limit=min(len(pending_ids), MAX_BATCH),
                      project_ids=pending_ids)
    report["migrated"] = outcome["migrated"]
    report["migrated_count"] = outcome["migrated_count"]
    report["bytes_migrated"] = outcome["bytes_migrated"]
    report["skipped"] = outcome["skipped"]
    report["failed"] = outcome["failed"]
    if outcome["failed"]:
        report["aborted_at"] = "migrate"
        report["reason"] = outcome["failed"]
        report["legacy_retained"] = True      # nothing is ever deleted
        return report

    # ---- 7. POST-MIGRATION VERIFY ---------------------------------------
    checked = verify_all(project_ids=outcome["migrated"])
    report["verification"] = {
        "verified": checked["verified"],
        "passed": checked["passed"],
        "failed": checked["failed"],
        "failures": checked["failures"],
        "per_project": [
            {"project_id": r["project_id"], "bytes": r.get("bytes"),
             "checks": r.get("checks")}
            for r in [verify_one(pid) for pid in outcome["migrated"]]
        ],
    }
    if not checked["all_ok"]:
        report["aborted_at"] = "post_verify"
        report["reason"] = checked["failures"]
        return report

    # ---- 8. FINAL INVENTORY ---------------------------------------------
    final = _scan()
    final_env = environment()
    report["inventory_after"] = {
        "projects_scanned": final["projects_scanned"],
        "projects_with_pdf_bytes": final["projects_with_pdf_bytes"],
        "already_migrated": final["already_migrated"],
        "pending_migration": final["pending_migration"],
        "existing_asset_rows": final["existing_asset_rows"],
    }
    report["legacy_pdf_bytes_retained"] = (
        final["projects_with_pdf_bytes"] == before["projects_with_pdf_bytes"]
    )
    report["storage_driver_after"] = final_env["storage_driver"]
    report["r2_reads_enabled_after"] = final_env["r2_reads_enabled"]
    report["ok"] = (
        not outcome["failed"]
        and checked["all_ok"]
        and final["pending_migration"] == 0
        and report["legacy_pdf_bytes_retained"]
        and not final_env["r2_reads_enabled"]
    )
    report["result"] = "PASS" if report["ok"] else "FAIL"
    return report


# ---------------------------------------------------------------------------
# Command line
#
# Render's Web Shell mangles pasted multi-line input (it injects bracketed
# paste markers), so the production migration has to be driveable by a few
# typed words. Run from the project root:
#
#     python pmig.py                 inventory  (READ ONLY -- the default)
#     python pmig.py backup          timestamped verified copy
#     python pmig.py migrate 10      migrate up to 10, bounded
#     python pmig.py verify          re-verify every migrated asset
#     python pmig.py verify 5        re-verify a random sample of 5
#
# The default does nothing but read. `migrate` is the only action that
# writes an object, and it never deletes or rewrites pdf_bytes.
# ---------------------------------------------------------------------------
def main(argv: list[str] | None = None) -> int:
    import json as _json

    args = list(argv if argv is not None else __import__("sys").argv[1:])
    action = (args[0] if args else "inventory").strip().lower()
    number = int(args[1]) if len(args) > 1 and str(args[1]).isdigit() else 0

    if action in ("inventory", "", "status"):
        report = inventory()
        report.pop("pending", None)
        report["problems_count"] = len(report.pop("problems", []))
        report["on_persistent_disk"] = str(
            report.get("database_path", "")).startswith("/var/data")
        report["environment"] = environment()
        result = report
    elif action == "backup":
        result = backup()
    elif action == "migrate":
        # Bare `migrate` runs the full guarded production sequence:
        # safety check -> verified backup -> re-inventory -> migrate ->
        # verify each -> post-verify -> final inventory. `migrate N` stays
        # the raw bounded batch for local work.
        result = migrate(limit=number) if number else run_production_migration()
    elif action == "verify":
        result = verify_all(sample=number)
    elif action in ("readcheck", "reads"):
        result = read_check()
    else:
        print(f"unknown action: {action!r}")
        return 2

    print(_json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised via pmig.py
    raise SystemExit(main())
