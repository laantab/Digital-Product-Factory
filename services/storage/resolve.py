"""Artifact resolution — Upgrade 0, Phase 0B-3B1.

WHY THIS MODULE EXISTS
----------------------
The 0B-3A safety checkpoint found that a project's `package_id` field is
NOT reliably the directory its files live in. Locally, 38 of 114 projects
disagree: the record says one id, the customer's PDF sits under another.
The download route works anyway because the browser builds its URL from
the STORED PATH, and the route joins that first URL segment straight onto
EXPORTS_DIR.

So any migration that derived a key from `package_id` would mis-key those
artifacts and produce keys that map back to nothing. This module is the
single place that answers "where does this artifact actually live?", and
every key a migration proposes is derived from that answer.

THE CANONICAL MIGRATION-KEY RULE
--------------------------------
    key = projects/{project_id}/exports/{path relative to the exports root}

The relative path is preserved verbatim, so the key inverts exactly:
`export_key_to_relpath()` returns the original path and the planner
proves, per artifact, that the key maps back to the exact existing file.
`package_id` is never an input.

This module performs no writes of any kind.
"""
from __future__ import annotations

from dataclasses import dataclass, field as dc_field
from pathlib import Path

from services.storage.keys import (
    InvalidStorageKey,
    export_key_to_relpath,
    export_object_key,
)

#: Fields that carry a direct path to a customer artifact. Ordered as
#: `database._existing_customer_output_files` reads them so the two agree.
PATH_FIELDS = ("pdf_path", "zip_path", "package_path", "export_path", "_pdf_path")

#: Fields that name an export DIRECTORY. Kept only to detect disagreement
#: with the real path -- never used to build a key.
PACKAGE_ID_FIELDS = ("package_id", "export_package_id", "artifact_id", "export_package")


@dataclass
class ResolvedArtifact:
    """One customer artifact that exists on disk right now."""

    project_id: int
    project_name: str
    absolute_path: Path
    relative_path: str  # POSIX, relative to the exports root
    byte_size: int
    storage_key: str
    #: How it was found, for the audit trail.
    source: str

    @property
    def filename(self) -> str:
        return self.relative_path.rsplit("/", 1)[-1]

    @property
    def export_directory(self) -> str:
        return self.relative_path.split("/", 1)[0] if "/" in self.relative_path else ""


@dataclass
class ResolutionReport:
    artifacts: list[ResolvedArtifact] = dc_field(default_factory=list)
    #: project_id -> (declared package_id, directories the files really use)
    package_id_mismatches: list[tuple[int, str, list[str]]] = dc_field(default_factory=list)
    #: Projects that look like they have a product but resolve to no file.
    missing_path_pointers: list[tuple[int, str, bool]] = dc_field(default_factory=list)
    #: Keys that two different artifacts both claim.
    collisions: list[tuple[str, int, int]] = dc_field(default_factory=list)
    #: Anything referenced that could not be turned into a usable key.
    unresolved: list[tuple[int, str, str]] = dc_field(default_factory=list)
    projects_scanned: int = 0
    files_examined: int = 0

    def summary(self) -> dict:
        return {
            "projects_scanned": self.projects_scanned,
            "files_examined": self.files_examined,
            "artifacts_resolved": len(self.artifacts),
            "projects_with_artifacts": len({a.project_id for a in self.artifacts}),
            "total_bytes": sum(a.byte_size for a in self.artifacts),
            "package_id_mismatches": len(self.package_id_mismatches),
            "missing_path_pointers": len(self.missing_path_pointers),
            "collisions": len(self.collisions),
            "unresolved": len(self.unresolved),
        }


def exports_root() -> Path:
    """The exports root the Factory is actually configured to use."""
    import database

    return database._exports_root().resolve()


def resolve_project_artifacts(
    project: dict, *, root: Path | None = None
) -> tuple[list[ResolvedArtifact], list[tuple[int, str, str]]]:
    """Every artifact of one project that exists on disk, plus problems.

    Delegates the *finding* to `database._existing_customer_output_files`,
    which is the function Saved Projects already trusts. Reusing it means
    the migration can never disagree with what the customer can see --
    the failure mode that would make a product vanish from their list.
    """
    import database

    base = (root or exports_root()).resolve()
    pid = int(project.get("id") or 0)
    name = str(project.get("name") or "")
    artifacts: list[ResolvedArtifact] = []
    problems: list[tuple[int, str, str]] = []

    if pid <= 0:
        return artifacts, [(pid, "-", "project has no usable id")]

    for path in database._existing_customer_output_files(project):
        try:
            resolved = Path(path).resolve()
            rel = resolved.relative_to(base).as_posix()
        except (OSError, ValueError):
            problems.append((pid, str(path), "artifact resolves outside the exports root"))
            continue
        try:
            key = export_object_key(pid, rel)
            # Reversibility is proved here, per artifact, not assumed.
            if export_key_to_relpath(key) != rel:
                problems.append((pid, rel, "key does not invert to the stored path"))
                continue
        except InvalidStorageKey as exc:
            problems.append((pid, rel, f"unusable key: {exc}"))
            continue
        try:
            size = resolved.stat().st_size
        except OSError as exc:
            problems.append((pid, rel, f"cannot stat artifact: {exc}"))
            continue
        artifacts.append(
            ResolvedArtifact(
                project_id=pid,
                project_name=name,
                absolute_path=resolved,
                relative_path=rel,
                byte_size=size,
                storage_key=key,
                source="customer_output_files",
            )
        )
    return artifacts, problems


def audit_projects(projects: list[dict] | None = None) -> ResolutionReport:
    """Audit every source used to resolve an existing artifact. Read-only."""
    if projects is None:
        import database

        projects = database.list_projects(include_system=True)

    base = exports_root()
    report = ResolutionReport()
    seen_keys: dict[str, int] = {}

    for project in projects or []:
        report.projects_scanned += 1
        pid = int(project.get("id") or 0)
        data = project.get("data") if isinstance(project.get("data"), dict) else {}

        artifacts, problems = resolve_project_artifacts(project, root=base)
        report.files_examined += len(artifacts) + len(problems)
        report.unresolved.extend(problems)

        for artifact in artifacts:
            previous = seen_keys.get(artifact.storage_key)
            if previous is not None and previous != artifact.project_id:
                report.collisions.append(
                    (artifact.storage_key, previous, artifact.project_id)
                )
            seen_keys[artifact.storage_key] = artifact.project_id
            report.artifacts.append(artifact)

        # Does the declared package id agree with where the files really are?
        declared = str(data.get("package_id") or "").strip()
        if declared and artifacts:
            directories = sorted({a.export_directory for a in artifacts if a.export_directory})
            if declared not in directories:
                report.package_id_mismatches.append((pid, declared, directories))

        # A project that clearly has a product but resolves to no file at
        # all. Reported, never guessed at -- guessing is how a migration
        # writes an object that maps to nothing.
        if not artifacts:
            has_embedded = bool(data.get("pdf_bytes"))
            if has_embedded or declared:
                report.missing_path_pointers.append((pid, declared or "-", has_embedded))

    return report


def format_resolution_report(report: ResolutionReport) -> str:
    s = report.summary()
    lines = [
        "=" * 70,
        "  ARTIFACT RESOLUTION AUDIT — read only, nothing was changed",
        "=" * 70,
        f"  projects scanned        : {s['projects_scanned']}",
        f"  files examined          : {s['files_examined']}",
        f"  artifacts resolved      : {s['artifacts_resolved']}",
        f"  projects with artifacts : {s['projects_with_artifacts']}",
        f"  total bytes             : {s['total_bytes']:,} "
        f"({s['total_bytes'] / 1048576:.2f} MB)",
        "",
        f"  package_id vs real path mismatches : {s['package_id_mismatches']}",
        f"  missing path pointers              : {s['missing_path_pointers']}",
        f"  key collisions                     : {s['collisions']}",
        f"  unresolved artifacts               : {s['unresolved']}",
        "",
    ]
    for pid, declared, dirs in report.package_id_mismatches[:10]:
        lines.append(f"    project {pid}: declares {declared[:18]}… but files live in {dirs[:2]}")
    if len(report.package_id_mismatches) > 10:
        lines.append(f"    … and {len(report.package_id_mismatches) - 10} more")
    lines.append("")
    for pid, declared, embedded in report.missing_path_pointers[:10]:
        lines.append(
            f"    project {pid}: no resolvable file "
            f"(package_id={declared[:18]}, pdf_bytes={'yes' if embedded else 'no'})"
        )
    lines.append("")
    lines.append("  NOTHING WAS COPIED. This is an audit.")
    lines.append("=" * 70)
    return "\n".join(lines)
