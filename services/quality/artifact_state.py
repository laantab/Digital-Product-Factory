"""Authoritative artifact state (DRAFT / APPROVED / LOCKED) and revision transitions.

Gate 10 primitives only — not wired into Generate / enhance / cover / packaging routes.

State resolution (no migration of saved projects)
-------------------------------------------------
1. Explicit valid ``artifact_state`` on the record, when present and consistent.
2. Verified lock evidence → LOCKED.
3. Verified approval evidence → APPROVED.
4. Otherwise → DRAFT.

Verified lock evidence (any one, non-destructive):
- ``book_locked`` is a true-like value, or
- ``lock_status`` equals ``LOCKED`` (case-insensitive), or
- ``package_id`` / ``artifact_id`` / ``export_package_id`` matches a package_id
  in a committed ``*PACKAGE_ACCEPTANCE_LOCK.json`` whose own lock fields verify
  LOCKED (read-only; files are never rewritten).

Verified approval evidence (when not LOCKED):
- Both ``content_digest`` and ``asset_manifest_digest`` are non-empty strings.
  This matches Gate 5+ ``stamp_artifact_identity`` semantics for an accepted
  preview/save identity stamp.

Conflicting evidence (e.g. explicit DRAFT with verified lock) raises
``ArtifactStateError`` rather than inventing a silent winner.

Transition contracts (documented; routes unchanged this gate)
-------------------------------------------------------------
- DRAFT content is editable under the current draft revision.
- DRAFT → APPROVED via ``approve_artifact_revision`` when digests (or equivalent
  approval evidence) are present — pure function, not route-wired.
- APPROVED cannot mutate content/assets in place; use
  ``transition_artifact_revision`` to open a new DRAFT revision.
- New revisions preserve a snapshot of the prior approved revision, clear
  approval/lock/export refs on the new revision, and retain lineage.
- LOCKED rejects new revisions (and content mutation helpers).
- Metadata-only updates must not change state or revision
  (``apply_metadata_fields``); existing ``enforce_artifact_immutability`` already
  covers PUT — route behavior is not changed here.
- Export rebuild / identity mismatch: when canonical digests match, rebuild
  must not create a new revision; mismatch must block. Export routes are not
  rewired in this gate — identity checks remain in ``artifact_identity``.
"""
from __future__ import annotations

import copy
import json
from enum import Enum
from pathlib import Path
from typing import Any, Mapping


class ArtifactState(str, Enum):
    DRAFT = "DRAFT"
    APPROVED = "APPROVED"
    LOCKED = "LOCKED"


class ArtifactStateError(ValueError):
    """Invalid or conflicting artifact state / illegal revision transition."""


_TRUE_LIKE = frozenset({"1", "true", "yes", "y", "on", "locked"})
_METADATA_ALLOWED_KEYS = frozenset(
    {
        "audience",
        "goal",
        "seller_notes",
        "publish_notes",
        "next_steps",
        "launch_notes",
        "listing_title",
        "listing_description",
        "keywords",
        "categories",
        "price",
        "subtitle",
        "author_name",
        "seller_metadata",
        "publish_metadata",
        "next_steps_metadata",
    }
)
_EXPORT_REF_KEYS = (
    "product_exports",
    "export_package_id",
    "exports",
)
_APPROVAL_CLEAR_KEYS = (
    "content_digest",
    "asset_manifest_digest",
    "qa_status",
)
_LOCK_CLEAR_KEYS = (
    "book_locked",
    "lock_status",
    "locked_at",
)

# Committed package-acceptance lock snapshots (repo root). Read-only.
_LOCK_JSON_GLOB = "*PACKAGE_ACCEPTANCE_LOCK.json"
_REPO_ROOT = Path(__file__).resolve().parents[2]
_lock_package_ids_cache: frozenset[str] | None = None


def _norm_state(value: Any) -> ArtifactState | None:
    if value is None or value == "":
        return None
    if isinstance(value, ArtifactState):
        return value
    text = str(value).strip().upper()
    if not text:
        return None
    try:
        return ArtifactState(text)
    except ValueError as exc:
        raise ArtifactStateError(
            f"Invalid artifact_state value: {value!r}. "
            f"Expected one of {[s.value for s in ArtifactState]}."
        ) from exc


def _truthy_lock_flag(value: Any) -> bool:
    if value is True:
        return True
    if value is False or value is None:
        return False
    if isinstance(value, (int, float)) and value == 1:
        return True
    text = str(value).strip().lower()
    return text in _TRUE_LIKE


def _lock_status_locked(value: Any) -> bool:
    if value is None or value == "":
        return False
    return str(value).strip().upper() == ArtifactState.LOCKED.value


def _nonempty_digest(value: Any) -> bool:
    return bool(str(value or "").strip())


def _record_package_ids(record: Mapping[str, Any]) -> set[str]:
    ids: set[str] = set()
    for key in ("package_id", "artifact_id", "export_package_id"):
        raw = str(record.get(key) or "").strip()
        if raw:
            ids.add(raw)
    return ids


def _load_committed_lock_package_ids(
    *,
    repo_root: Path | None = None,
    refresh: bool = False,
) -> frozenset[str]:
    """Read committed *PACKAGE_ACCEPTANCE_LOCK.json files (non-destructive)."""
    global _lock_package_ids_cache
    if _lock_package_ids_cache is not None and not refresh and repo_root is None:
        return _lock_package_ids_cache

    root = Path(repo_root) if repo_root is not None else _REPO_ROOT
    locked: set[str] = set()
    for path in sorted(root.glob(_LOCK_JSON_GLOB)):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict):
            continue
        pkg = str(payload.get("package_id") or "").strip()
        if not pkg:
            continue
        if _truthy_lock_flag(payload.get("book_locked")) or _lock_status_locked(
            payload.get("lock_status")
        ):
            locked.add(pkg)

    result = frozenset(locked)
    if repo_root is None:
        _lock_package_ids_cache = result
    return result


def has_verified_lock_evidence(
    record: Mapping[str, Any] | None,
    *,
    repo_root: Path | None = None,
    committed_lock_ids: frozenset[str] | None = None,
) -> bool:
    """True when project data carries or matches verified lock evidence."""
    if not isinstance(record, Mapping):
        return False
    if _truthy_lock_flag(record.get("book_locked")):
        return True
    if _lock_status_locked(record.get("lock_status")):
        return True
    ids = _record_package_ids(record)
    if not ids:
        return False
    registry = (
        committed_lock_ids
        if committed_lock_ids is not None
        else _load_committed_lock_package_ids(repo_root=repo_root)
    )
    return bool(ids & registry)


def has_verified_approval_evidence(record: Mapping[str, Any] | None) -> bool:
    """Gate 5+ digests: both content_digest and asset_manifest_digest present."""
    if not isinstance(record, Mapping):
        return False
    return _nonempty_digest(record.get("content_digest")) and _nonempty_digest(
        record.get("asset_manifest_digest")
    )


def resolve_artifact_state(
    record: Mapping[str, Any] | None,
    *,
    repo_root: Path | None = None,
    committed_lock_ids: frozenset[str] | None = None,
) -> ArtifactState:
    """Resolve DRAFT / APPROVED / LOCKED without migrating saved projects.

    Raises ArtifactStateError on invalid explicit state or conflicting evidence.
    """
    if not isinstance(record, Mapping):
        return ArtifactState.DRAFT

    explicit = _norm_state(record.get("artifact_state"))
    locked = has_verified_lock_evidence(
        record, repo_root=repo_root, committed_lock_ids=committed_lock_ids
    )
    approved = has_verified_approval_evidence(record)

    if explicit is not None:
        if explicit is ArtifactState.LOCKED and not locked:
            # Explicit LOCKED is authoritative runtime state even when legacy
            # boolean/registry markers were never copied onto the record.
            return ArtifactState.LOCKED
        if explicit is ArtifactState.DRAFT and locked:
            raise ArtifactStateError(
                "Conflicting artifact state evidence: artifact_state=DRAFT "
                "but verified lock evidence is present."
            )
        if explicit is ArtifactState.APPROVED and locked:
            raise ArtifactStateError(
                "Conflicting artifact state evidence: artifact_state=APPROVED "
                "but verified lock evidence is present (expected LOCKED)."
            )
        if explicit is ArtifactState.DRAFT:
            return ArtifactState.DRAFT
        if explicit is ArtifactState.APPROVED:
            return ArtifactState.APPROVED
        return ArtifactState.LOCKED

    if locked:
        return ArtifactState.LOCKED
    if approved:
        return ArtifactState.APPROVED
    return ArtifactState.DRAFT


def current_revision(record: Mapping[str, Any] | None) -> int:
    if not isinstance(record, Mapping):
        return 1
    rev = record.get("artifact_revision")
    try:
        rev_i = int(rev) if rev is not None else 1
    except (TypeError, ValueError):
        rev_i = 1
    return max(1, rev_i)


def assert_content_mutable(
    record: Mapping[str, Any] | None,
    *,
    repo_root: Path | None = None,
    committed_lock_ids: frozenset[str] | None = None,
) -> None:
    """Reject in-place content mutation for APPROVED / LOCKED artifacts."""
    state = resolve_artifact_state(
        record, repo_root=repo_root, committed_lock_ids=committed_lock_ids
    )
    if state is ArtifactState.LOCKED:
        raise ArtifactStateError(
            "LOCKED artifact cannot mutate content, regenerate, enhance, "
            "change cover, or open a new revision through ordinary transitions."
        )
    if state is ArtifactState.APPROVED:
        raise ArtifactStateError(
            "APPROVED artifact cannot mutate content or assets in place. "
            "Call transition_artifact_revision() to open a new DRAFT revision."
        )


def apply_metadata_fields(
    record: Mapping[str, Any],
    metadata: Mapping[str, Any],
    *,
    repo_root: Path | None = None,
    committed_lock_ids: frozenset[str] | None = None,
) -> dict[str, Any]:
    """Return a copy with metadata merged; state and revision unchanged.

    Does not mutate ``record``. Rejects attempts to smuggle identity/state keys
    through the metadata mapping. Does not call generation or export.
    """
    if not isinstance(record, Mapping):
        raise ArtifactStateError("metadata update requires a mapping record")
    if not isinstance(metadata, Mapping):
        raise ArtifactStateError("metadata must be a mapping")

    # Resolve once so conflicting evidence fails before any copy work.
    prior_state = resolve_artifact_state(
        record, repo_root=repo_root, committed_lock_ids=committed_lock_ids
    )
    prior_rev = current_revision(record)

    out = copy.deepcopy(dict(record))
    for key, value in metadata.items():
        key_s = str(key)
        if key_s not in _METADATA_ALLOWED_KEYS:
            raise ArtifactStateError(
                f"Metadata-only update cannot set non-metadata field {key_s!r}."
            )
        out[key_s] = copy.deepcopy(value)

    if out.get("artifact_state") != record.get("artifact_state"):
        raise ArtifactStateError("Metadata update must not change artifact_state.")
    if current_revision(out) != prior_rev:
        raise ArtifactStateError("Metadata update must not change artifact_revision.")
    after_state = resolve_artifact_state(
        out, repo_root=repo_root, committed_lock_ids=committed_lock_ids
    )
    if after_state is not prior_state:
        raise ArtifactStateError("Metadata update must not change resolved state.")
    return out


def approve_artifact_revision(
    record: Mapping[str, Any],
    *,
    reason: str,
    repo_root: Path | None = None,
    committed_lock_ids: frozenset[str] | None = None,
) -> dict[str, Any]:
    """Pure DRAFT → APPROVED when verified approval evidence is present.

    Does not mutate ``record``. Not wired to routes in Gate 10.
    """
    if not str(reason or "").strip():
        raise ArtifactStateError("approve_artifact_revision requires a transition reason")
    state = resolve_artifact_state(
        record, repo_root=repo_root, committed_lock_ids=committed_lock_ids
    )
    if state is ArtifactState.LOCKED:
        raise ArtifactStateError("LOCKED artifact cannot transition to APPROVED")
    if state is ArtifactState.APPROVED:
        raise ArtifactStateError("Artifact is already APPROVED")
    if not has_verified_approval_evidence(record):
        raise ArtifactStateError(
            "DRAFT → APPROVED requires verified approval evidence "
            "(both content_digest and asset_manifest_digest)."
        )
    out = copy.deepcopy(dict(record))
    out["artifact_state"] = ArtifactState.APPROVED.value
    out["artifact_revision"] = current_revision(record)
    out["approval_transition_reason"] = str(reason).strip()
    return out


def _approved_snapshot(record: Mapping[str, Any], reason: str) -> dict[str, Any]:
    return {
        "artifact_revision": current_revision(record),
        "artifact_state": ArtifactState.APPROVED.value,
        "artifact_id": record.get("artifact_id"),
        "package_id": record.get("package_id"),
        "content_digest": record.get("content_digest"),
        "asset_manifest_digest": record.get("asset_manifest_digest"),
        "qa_status": record.get("qa_status"),
        "transition_reason": str(reason).strip(),
    }


def transition_artifact_revision(
    record: Mapping[str, Any],
    *,
    reason: str,
    repo_root: Path | None = None,
    committed_lock_ids: frozenset[str] | None = None,
) -> dict[str, Any]:
    """Open the next DRAFT revision from an APPROVED artifact.

    - Validates current state; rejects LOCKED and non-APPROVED sources.
    - Creates the next deterministic revision number (prior + 1).
    - Preserves the previous approved revision in lineage / snapshot fields.
    - Returns a new DRAFT record without mutating ``record``.
    - Clears approval, lock, and export references on the new revision.
    - Never calls generation, export, or external services.
    """
    if not isinstance(record, Mapping):
        raise ArtifactStateError("transition_artifact_revision requires a mapping record")
    if not str(reason or "").strip():
        raise ArtifactStateError("transition_artifact_revision requires a transition reason")

    state = resolve_artifact_state(
        record, repo_root=repo_root, committed_lock_ids=committed_lock_ids
    )
    if state is ArtifactState.LOCKED:
        raise ArtifactStateError(
            "LOCKED artifact cannot open a new revision, mutate, regenerate, "
            "enhance, or change cover through ordinary transitions."
        )
    if state is ArtifactState.DRAFT:
        raise ArtifactStateError(
            "DRAFT artifact is already editable under the current revision; "
            "transition_artifact_revision is only for APPROVED → new DRAFT."
        )
    if state is not ArtifactState.APPROVED:
        raise ArtifactStateError(f"Illegal revision transition from state {state.value}")

    prior_rev = current_revision(record)
    next_rev = prior_rev + 1
    snapshot = _approved_snapshot(record, reason)

    out = copy.deepcopy(dict(record))
    out["artifact_revision"] = next_rev
    out["artifact_state"] = ArtifactState.DRAFT.value

    lineage = list(out.get("artifact_lineage") or [])
    lineage.append(copy.deepcopy(snapshot))
    out["artifact_lineage"] = lineage
    out["prior_approved_revision"] = copy.deepcopy(snapshot)
    out["revision_transition_reason"] = str(reason).strip()

    for key in _APPROVAL_CLEAR_KEYS:
        out.pop(key, None)
    for key in _LOCK_CLEAR_KEYS:
        out.pop(key, None)
    out["book_locked"] = False
    for key in _EXPORT_REF_KEYS:
        out.pop(key, None)

    # New revision must not retain prior approval classification.
    if has_verified_approval_evidence(out):
        raise ArtifactStateError("internal error: approval digests not cleared")

    # Registry-linked package_ids that remain LOCKED cannot become DRAFT by
    # clearing local flags alone; those transitions are rejected at resolve
    # (LOCKED) before this point. Final resolve must be DRAFT.
    try:
        resolved = resolve_artifact_state(
            out, repo_root=repo_root, committed_lock_ids=committed_lock_ids
        )
    except ArtifactStateError as exc:
        raise ArtifactStateError(
            "New revision could not safely resolve to DRAFT after clearing "
            f"approval/lock/export refs: {exc}"
        ) from exc
    if resolved is not ArtifactState.DRAFT:
        raise ArtifactStateError(
            f"New revision must resolve to DRAFT, got {resolved.value}"
        )
    return out
