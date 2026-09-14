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

KINDS = frozenset(
    {
        KIND_PDF,
        KIND_ZIP,
        KIND_COVER,
        KIND_PREVIEW,
        KIND_INTERIOR_IMAGE,
        KIND_MARKETING_IMAGE,
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
    """Key for an artifact that lives on disk today under EXPORTS_DIR.

    Mirrors the existing `exports/<package_id>/<filename>` layout so the
    mapping from a legacy path to its future key is obvious by eye and
    reversible without a lookup table.
    """
    return posixpath.join(
        project_prefix(project_id),
        "exports",
        _segment(package_id, label="package id"),
        _segment(filename, label="filename"),
    )


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
    }[_kind(kind)]
    return posixpath.join(
        project_prefix(project_id),
        "embedded",
        f"{_segment(field, label='field')}.{ext}",
    )


def is_valid_key(key: str) -> bool:
    """True when `key` is a well-formed, non-escaping storage key."""
    text = str(key or "")
    if not text or text.startswith("/") or text.endswith("/"):
        return False
    if "\\" in text or "//" in text:
        return False
    parts = text.split("/")
    if any(p in {"", ".", ".."} for p in parts):
        return False
    return all(_SAFE_SEGMENT.match(p) for p in parts)
