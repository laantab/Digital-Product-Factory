"""Deterministic storage keys — Upgrade 0, Phase 0B-3A.

A key must be derivable from stable facts about the artifact alone, so
that retrying a migration, or re-running it after a crash, produces the
same key and therefore the same asset record rather than a duplicate.
Nothing here uses timestamps, randomness, or iteration order.
"""
from __future__ import annotations

import posixpath
import re

#: Artifact kinds. Deliberately small; extend when a real need appears.
KIND_PDF = "pdf"
KIND_ZIP = "zip"
KIND_COVER = "cover"
KIND_PREVIEW = "preview"
KIND_INTERIOR_IMAGE = "interior_image"
KIND_MARKETING_IMAGE = "marketing_image"
#: Anything else a product engine wrote into an export folder (.html,
#: .txt, .json). Real customer files, so they need a kind of their own
#: rather than being mislabelled as a PDF.
KIND_EXPORT_FILE = "export_file"

KINDS = frozenset(
    {
        KIND_PDF,
        KIND_ZIP,
        KIND_COVER,
        KIND_PREVIEW,
        KIND_INTERIOR_IMAGE,
        KIND_MARKETING_IMAGE,
        KIND_EXPORT_FILE,
    }
)

_SAFE_SEGMENT = re.compile(r"^[A-Za-z0-9._-]{1,200}$")


class InvalidStorageKey(ValueError):
    """A key segment was empty, oversized, or could escape its prefix."""


def _segment(value: object, *, label: str) -> str:
    text = str(value or "").strip().replace("\\", "/")
    text = text.strip("/")
    if not text or not _SAFE_SEGMENT.match(text):
        raise InvalidStorageKey(f"unsafe {label} segment: {value!r}")
    if text in {".", ".."}:
        raise InvalidStorageKey(f"unsafe {label} segment: {value!r}")
    return text


def _kind(kind: str) -> str:
    text = str(kind or "").strip().lower()
    if text not in KINDS:
        raise InvalidStorageKey(f"unknown asset kind: {kind!r}")
    return text


def project_prefix(project_id: int) -> str:
    """Everything belonging to one project lives under one prefix.

    Makes a project's assets listable and, later, deletable as a unit.
    """
    pid = int(project_id)
    if pid <= 0:
        raise InvalidStorageKey(f"invalid project id: {project_id!r}")
    return f"projects/{pid}"


def export_key(project_id: int, package_id: str, filename: str) -> str:
    """Key for an artifact addressed as `exports/<package_id>/<filename>`.

    DO NOT use this to plan a migration of an existing artifact. A
    project's `package_id` field is NOT reliably the directory its files
    actually live in -- 38 of 114 local projects disagree. Deriving a key
    from `package_id` would mis-key those artifacts and, worse, would not
    map back to a real file.

    Use `export_object_key()` instead, which is derived from the path the
    artifact is actually stored at. This function remains only for
    addressing an artifact whose directory genuinely is the package id
    (new writes, where the Factory chooses both).
    """
    return posixpath.join(
        project_prefix(project_id),
        "exports",
        _segment(package_id, label="package id"),
        _segment(filename, label="filename"),
    )


#: Marks the portion of an export key that is the verbatim relative path.
EXPORTS_INFIX = "exports"

# Export filenames are legacy data, not names the Factory gets to choose.
# One real customer file is "Thunder Volt.pdf", so spaces must survive. The
# rule is therefore permissive about content and strict about traversal:
# reject separators, control characters, empty and dot segments.
_FORBIDDEN_IN_SEGMENT = re.compile(r"[\x00-\x1f\x7f/\\]")


def _path_segment(value: str, *, label: str) -> str:
    text = str(value or "")
    if not text or len(text) > 255:
        raise InvalidStorageKey(f"unsafe {label} segment: {value!r}")
    if text in {".", ".."} or _FORBIDDEN_IN_SEGMENT.search(text):
        raise InvalidStorageKey(f"unsafe {label} segment: {value!r}")
    if text != text.strip() or text.endswith("."):
        # Trailing dots/spaces round-trip differently on Windows, which
        # would break the "key maps back to the exact file" guarantee.
        raise InvalidStorageKey(f"unsafe {label} segment: {value!r}")
    return text


def export_object_key(project_id: int, relative_path: str) -> str:
    """THE canonical key rule for an artifact that exists on disk today.

    `relative_path` is the artifact's path relative to the exports root,
    exactly as stored -- NOT anything derived from `package_id`.

        exports/8bc848.../flower_parts.pdf
          -> projects/369/exports/8bc848.../flower_parts.pdf

    The relative path is preserved verbatim, which is what makes the key
    reversible: `export_key_to_relpath()` returns the original path, so
    every proposed key can be proved to map back to the exact existing
    file before a single byte is copied.
    """
    rel = str(relative_path or "").replace("\\", "/")
    if rel.startswith("/"):
        # An absolute-looking path is rejected, not normalised. Silently
        # stripping the slash would let "/a.pdf" and "a.pdf" produce the
        # same key from different inputs, and the key rule has to be
        # one-to-one for reversibility to mean anything.
        raise InvalidStorageKey(f"export path must be relative: {relative_path!r}")
    rel = rel.rstrip("/")
    if not rel:
        raise InvalidStorageKey("empty export relative path")
    parts = [_path_segment(p, label="path") for p in rel.split("/")]
    return posixpath.join(project_prefix(project_id), EXPORTS_INFIX, *parts)


def export_key_to_relpath(key: str) -> str:
    """Invert `export_object_key()`. Raises when `key` is not an export key.

    Exists so a migration can prove reversibility rather than assert it.
    """
    text = str(key or "").replace("\\", "/")
    parts = text.split("/")
    if len(parts) < 4 or parts[0] != "projects" or parts[2] != EXPORTS_INFIX:
        raise InvalidStorageKey(f"not an export object key: {key!r}")
    if not parts[1].isdigit() or int(parts[1]) <= 0:
        raise InvalidStorageKey(f"not an export object key: {key!r}")
    rel = "/".join(parts[3:])
    if not rel:
        raise InvalidStorageKey(f"not an export object key: {key!r}")
    return rel


def embedded_key(project_id: int, field: str, kind: str) -> str:
    """Key for a binary currently embedded in `projects.data`.

    `field` is the JSON field it came from (e.g. "pdf_bytes"), which keeps
    the provenance of every migrated object visible in its own key.
    """
    ext = {
        KIND_PDF: "pdf",
        KIND_ZIP: "zip",
        KIND_COVER: "png",
        KIND_PREVIEW: "png",
        KIND_INTERIOR_IMAGE: "png",
        KIND_MARKETING_IMAGE: "png",
        KIND_EXPORT_FILE: "bin",
    }[_kind(kind)]
    return posixpath.join(
        project_prefix(project_id),
        "embedded",
        f"{_segment(field, label='field')}.{ext}",
    )


def is_valid_key(key: str) -> bool:
    """True when `key` is a well-formed, non-escaping storage key.

    Strict about traversal, permissive about content: legacy export
    filenames are customer data (one real file is "Thunder Volt.pdf"), so
    a space must not make a key invalid. What must never pass is anything
    that could resolve outside its prefix.
    """
    text = str(key or "")
    if not text or text.startswith("/") or text.endswith("/"):
        return False
    if "\\" in text or "//" in text:
        return False
    parts = text.split("/")
    if any(p in {"", ".", ".."} for p in parts):
        return False
    try:
        for part in parts:
            _path_segment(part, label="key")
    except InvalidStorageKey:
        return False
    return True
