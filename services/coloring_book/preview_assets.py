"""Stable display URLs for coloring-book cover and interior images.

Preview must not require huge JSON base64. Files already on disk under
exports/<package_id>/ are served via /download or a project-scoped preview
route. This module does not generate or rewrite artwork.
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
EXPORTS_DIR = Path(os.environ.get("FACTORY_EXPORTS_DIR") or (ROOT / "exports"))

_PAGE_FILE_RE = re.compile(r"^coloring_p(\d{1,3})\.(png|jpe?g)$", re.IGNORECASE)
_COVER_FILES = (
    "cover_page_preview.png",
    "cover.png",
    "img_cover.png",
)


def is_coloring_preview_filename(filename: str) -> bool:
    """True for coloring interior/cover preview files only (basename, no path)."""
    raw = str(filename or "")
    if not raw or "/" in raw or "\\" in raw or ".." in raw:
        return False
    name = Path(raw).name
    if not name or name != raw:
        return False
    lowered = name.lower()
    if lowered in {item.lower() for item in _COVER_FILES}:
        return True
    return bool(_PAGE_FILE_RE.match(name))


def coloring_preview_missing_message(filename: str) -> str:
    name = Path(str(filename or "")).name
    if _PAGE_FILE_RE.match(name):
        return f"Interior page image missing: {name}"
    return f"Coloring cover preview image missing: {name}"


def _package_dir(package_id: str) -> Path | None:
    pkg = str(package_id or "").strip()
    if not pkg or "/" in pkg or "\\" in pkg or ".." in pkg:
        return None
    folder = EXPORTS_DIR / pkg
    if not folder.is_dir():
        return None
    return folder


def resolve_interior_preview_filename(
    pkg_dir: Path | None, page_number: int
) -> tuple[str, bool]:
    n = int(page_number)
    candidates = [
        f"coloring_p{n:02d}.png",
        f"coloring_p{n:02d}.jpg",
        f"coloring_p{n:02d}.jpeg",
        f"coloring_p{n}.png",
        f"coloring_p{n}.jpg",
    ]
    if pkg_dir is None:
        return candidates[0], False
    for name in candidates:
        if (pkg_dir / name).is_file():
            return name, True
    return candidates[0], False


def resolve_cover_preview_filename(pkg_dir: Path | None) -> tuple[str, bool]:
    if pkg_dir is None:
        return _COVER_FILES[0], False
    for name in _COVER_FILES:
        if (pkg_dir / name).is_file():
            return name, True
    return _COVER_FILES[0], False


def _preview_url(*, project_id: int | None, package_id: str, filename: str) -> str:
    name = Path(filename).name
    if not is_coloring_preview_filename(name):
        return ""
    if project_id is not None:
        try:
            pid = int(project_id)
        except (TypeError, ValueError):
            pid = None
        else:
            if pid > 0:
                return f"/projects/{pid}/coloring-preview/{name}"
    pkg = str(package_id or "").strip()
    if pkg:
        return f"/download/{pkg}/{name}"
    return ""


def attach_coloring_preview_urls(
    data: dict[str, Any], *, project_id: int | None = None
) -> dict[str, Any]:
    """Attach derived cover/interior preview URLs. Does not mutate page dicts."""
    if not isinstance(data, dict):
        return data
    if str(data.get("product_type") or "").strip().lower() != "coloring_book":
        return data
    pkg = str(data.get("package_id") or data.get("export_package_id") or "").strip()
    pkg_dir = _package_dir(pkg)
    pages = data.get("pages") if isinstance(data.get("pages"), list) else []
    previews: list[dict[str, Any]] = []
    for i, page in enumerate(pages):
        if not isinstance(page, dict):
            continue
        try:
            n = int(page.get("page_number") or i + 1)
        except (TypeError, ValueError):
            n = i + 1
        filename, exists = resolve_interior_preview_filename(pkg_dir, n)
        url = _preview_url(project_id=project_id, package_id=pkg, filename=filename)
        previews.append(
            {
                "page_number": n,
                "topic": str(page.get("topic") or f"Page {n}"),
                "filename": filename,
                "url": url,
                "missing": not exists,
            }
        )
    data["interior_previews"] = previews
    cover_name, cover_exists = resolve_cover_preview_filename(pkg_dir)
    data["cover_preview_url"] = _preview_url(
        project_id=project_id, package_id=pkg, filename=cover_name
    )
    data["cover_preview_missing"] = not cover_exists
    return data
