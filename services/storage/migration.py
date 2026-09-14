"""Migration planning — DRY RUN ONLY in Phase 0B-3A.

This module inspects what a future migration WOULD do. It performs no
writes of any kind: it does not store objects, does not record assets,
does not touch `projects.data`, and does not move a single file. Phase
0B-3A explicitly forbids migrating a customer binary.

THE SAFETY CONTRACT THE REAL MIGRATION MUST FOLLOW (0B-3B)
-----------------------------------------------------------
    COPY -> VERIFY CHECKSUM/BYTE COUNT -> RECORD ASSET
         -> VERIFY READBACK -> ONLY THEN REMOVE LEGACY BINARY

Never MOVE -> DELETE -> HOPE. A failure at any step must leave the
original customer artifact exactly as it was. The plan produced here
carries everything needed to execute that sequence and to verify it:
deterministic key, checksum, byte count, source field, and the target
asset record.

Restartability comes from two properties, both established in 0B-3A:
deterministic keys (services/storage/keys.py) and a UNIQUE storage_key on
`assets` (database.record_asset). Running a migration twice therefore
re-records one asset rather than creating a duplicate.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field as dc_field

from services.storage.base import sha256_hex
from services.storage.compat import decode_embedded
from services.storage.keys import (
    KIND_COVER,
    KIND_EXPORT_FILE,
    KIND_PDF,
    KIND_PREVIEW,
    KIND_ZIP,
    embedded_key,
)

#: Embedded fields a migration would move, and the kind each becomes.
EMBEDDED_FIELDS: dict[str, str] = {
    "pdf_bytes": KIND_PDF,
    "zip_bytes": KIND_ZIP,
    "cover_preview_b64": KIND_COVER,
    "sample_preview_b64": KIND_PREVIEW,
}

_CONTENT_TYPES = {
    KIND_PDF: "application/pdf",
    KIND_ZIP: "application/zip",
    KIND_COVER: "image/png",
    KIND_PREVIEW: "image/png",
}

#: Export files are whatever the product engines wrote, so the kind comes
#: from the real filename rather than from an assumed layout.
_KIND_BY_SUFFIX = {
    ".pdf": KIND_PDF,
    ".zip": KIND_ZIP,
    ".png": KIND_PREVIEW,
    ".jpg": KIND_PREVIEW,
    ".jpeg": KIND_PREVIEW,
}


@dataclass
class PlannedMove:
    """One embedded binary a migration would relocate."""

    project_id: int
    project_name: str
    source_field: str
    kind: str
    storage_key: str
    content_type: str
    byte_size: int
    checksum: str
    #: What would be removed from projects.data AFTER the copy is verified
    #: and read back -- never before.
    would_delete_field: str

    def as_asset_record(self) -> dict:
        """The exact `assets` row this move would create."""
        return {
            "project_id": self.project_id,
            "kind": self.kind,
            "storage_key": self.storage_key,
            "content_type": self.content_type,
            "byte_size": self.byte_size,
            "checksum": self.checksum,
        }


@dataclass
class MigrationProblem:
    project_id: int
    source_field: str
    problem: str


@dataclass
class MigrationPlan:
    moves: list[PlannedMove] = dc_field(default_factory=list)
    problems: list[MigrationProblem] = dc_field(default_factory=list)
    projects_scanned: int = 0

    @property
    def total_bytes(self) -> int:
        return sum(m.byte_size for m in self.moves)

    @property
    def projects_affected(self) -> int:
        return len({m.project_id for m in self.moves})

    def summary(self) -> dict:
        by_field: dict[str, dict] = {}
        for move in self.moves:
            entry = by_field.setdefault(move.source_field, {"count": 0, "bytes": 0})
            entry["count"] += 1
            entry["bytes"] += move.byte_size
        return {
            "projects_scanned": self.projects_scanned,
            "projects_affected": self.projects_affected,
            "binaries_to_move": len(self.moves),
            "total_bytes": self.total_bytes,
            "by_field": by_field,
            "problems": len(self.problems),
            "largest_bytes": max((m.byte_size for m in self.moves), default=0),
        }

    def as_dict(self) -> dict:
        return {
            "summary": self.summary(),
            "moves": [asdict(m) for m in self.moves],
            "problems": [asdict(p) for p in self.problems],
        }


def plan_project(project: dict) -> tuple[list[PlannedMove], list[MigrationProblem]]:
    """Plan one project. Pure: reads the dict, changes nothing."""
    moves: list[PlannedMove] = []
    problems: list[MigrationProblem] = []

    pid = int(project.get("id") or 0)
    name = str(project.get("name") or "")
    data = project.get("data") if isinstance(project.get("data"), dict) else {}

    if pid <= 0:
        problems.append(MigrationProblem(pid, "-", "project has no usable id"))
        return moves, problems

    for source_field, kind in EMBEDDED_FIELDS.items():
        if source_field not in data:
            continue
        raw_value = data.get(source_field)
        if raw_value in (None, "", b""):
            problems.append(
                MigrationProblem(pid, source_field, "field present but empty")
            )
            continue

        decoded = decode_embedded(raw_value)
        if decoded is None:
            problems.append(
                MigrationProblem(pid, source_field, "field is not decodable base64")
            )
            continue
        if not decoded:
            problems.append(
                MigrationProblem(pid, source_field, "field decoded to zero bytes")
            )
            continue

        try:
            key = embedded_key(pid, source_field, kind)
        except ValueError as exc:
            problems.append(MigrationProblem(pid, source_field, f"unusable key: {exc}"))
            continue

        moves.append(
            PlannedMove(
                project_id=pid,
                project_name=name,
                source_field=source_field,
                kind=kind,
                storage_key=key,
                content_type=_CONTENT_TYPES.get(kind, "application/octet-stream"),
                byte_size=len(decoded),
                checksum=sha256_hex(decoded),
                would_delete_field=source_field,
            )
        )

    return moves, problems


def plan_exports(projects: list[dict] | None = None) -> MigrationPlan:
    """Dry-run plan for artifacts that live on disk under EXPORTS_DIR.

    Keys come from the artifact's REAL stored path, never from
    `package_id` -- 38 of 114 local projects disagree about that, and a
    package-id key would map back to no file at all. Every key is proved
    to invert to the exact existing file before it enters the plan
    (services/storage/resolve.py does that check per artifact).

    Writes nothing. This is a plan, not a migration.
    """
    from services.storage.resolve import audit_projects

    report = audit_projects(projects)
    plan = MigrationPlan()
    plan.projects_scanned = report.projects_scanned

    for artifact in report.artifacts:
        kind = _KIND_BY_SUFFIX.get(
            artifact.absolute_path.suffix.lower(), KIND_EXPORT_FILE
        )
        plan.moves.append(
            PlannedMove(
                project_id=artifact.project_id,
                project_name=artifact.project_name,
                source_field=f"exports/{artifact.relative_path}",
                kind=kind,
                storage_key=artifact.storage_key,
                content_type=_CONTENT_TYPES.get(kind, "application/octet-stream"),
                byte_size=artifact.byte_size,
                checksum="",  # hashing 1.8 GB is 0B-3B2 work, not planning
                would_delete_field="",  # nothing is ever deleted in 0B-3B1
            )
        )

    for pid, declared, dirs in report.package_id_mismatches:
        plan.problems.append(
            MigrationProblem(
                pid,
                "package_id",
                f"declared package_id {declared!r} is not the directory the "
                f"files live in ({', '.join(dirs[:3])}) — key taken from the real path",
            )
        )
    for pid, declared, has_embedded in report.missing_path_pointers:
        plan.problems.append(
            MigrationProblem(
                pid,
                "path pointer",
                "no resolvable artifact path"
                + (" (embedded pdf_bytes still present)" if has_embedded else ""),
            )
        )
    for pid, where, why in report.unresolved:
        plan.problems.append(MigrationProblem(pid, str(where), why))
    for key, first, second in report.collisions:
        plan.problems.append(
            MigrationProblem(second, key, f"storage key collides with project {first}")
        )

    return plan


def plan_migration(projects: list[dict] | None = None) -> MigrationPlan:
    """Build a full dry-run plan. Makes zero persistent mutations.

    Reads projects through the ordinary listing API when none are
    supplied, so the plan reflects exactly what the Factory can see.
    """
    if projects is None:
        import database

        projects = database.list_projects(include_system=True)

    plan = MigrationPlan()
    for project in projects or []:
        plan.projects_scanned += 1
        moves, problems = plan_project(project)
        plan.moves.extend(moves)
        plan.problems.extend(problems)

    # Deterministic keys mean two projects can never collide, but a
    # duplicate here would silently overwrite a customer artifact, so it
    # is checked rather than assumed.
    seen: dict[str, int] = {}
    for move in plan.moves:
        if move.storage_key in seen:
            plan.problems.append(
                MigrationProblem(
                    move.project_id,
                    move.source_field,
                    f"storage key collides with project {seen[move.storage_key]}",
                )
            )
        seen[move.storage_key] = move.project_id

    return plan


def format_plan(plan: MigrationPlan) -> str:
    """Human-readable dry-run report."""
    s = plan.summary()
    lines = [
        "=" * 66,
        "  EMBEDDED BINARY MIGRATION — DRY RUN (no changes made)",
        "=" * 66,
        f"  projects scanned   : {s['projects_scanned']}",
        f"  projects affected  : {s['projects_affected']}",
        f"  binaries to move   : {s['binaries_to_move']}",
        f"  total bytes        : {s['total_bytes']:,} ({s['total_bytes'] / 1048576:.2f} MB)",
        f"  largest single     : {s['largest_bytes']:,} ({s['largest_bytes'] / 1048576:.2f} MB)",
        "",
        "  by source field:",
    ]
    for field_name, entry in sorted(s["by_field"].items()):
        lines.append(
            f"    {field_name:20} {entry['count']:5} objects  "
            f"{entry['bytes'] / 1048576:9.2f} MB"
        )
    lines.append("")
    lines.append(f"  problems / malformed : {s['problems']}")
    for problem in plan.problems[:20]:
        lines.append(f"    project {problem.project_id}: {problem.source_field} — {problem.problem}")
    if len(plan.problems) > 20:
        lines.append(f"    … and {len(plan.problems) - 20} more")
    lines.append("")
    lines.append("  sample of proposed moves:")
    for move in plan.moves[:5]:
        lines.append(
            f"    project {move.project_id:6} {move.source_field:16} "
            f"{move.byte_size / 1048576:8.2f} MB  -> {move.storage_key}"
        )
        lines.append(f"      checksum {move.checksum[:16]}…  would then clear data['{move.would_delete_field}']")
    lines.append("")
    lines.append("  NOTHING WAS MIGRATED. Phase 0B-3A is foundation only.")
    lines.append("=" * 66)
    return "\n".join(lines)
