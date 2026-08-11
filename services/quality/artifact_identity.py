"""Authoritative artifact identity for Preview → Save → PDF → ZIP.

Same-artifact identity is proven via the saved project record and canonical
content/asset digests — not by requiring PDF and ZIP binary hashes to match.
"""
from __future__ import annotations

import base64
import hashlib
import json
from typing import Any


_PDF_PRODUCT_TYPES = frozenset(
    {
        "math_worksheet",
        "spelling_worksheet",
        "word_search",
        "crossword",
        "coloring_book",
    }
)


def content_digest_from_pdf_bytes(pdf_bytes: bytes) -> str:
    return hashlib.sha256(pdf_bytes or b"").hexdigest()


def decode_pdf_bytes(data: dict) -> bytes:
    raw = data.get("pdf_bytes") or ""
    if not raw:
        return b""
    if isinstance(raw, bytes):
        return raw if raw.startswith(b"%PDF") else b""
    try:
        decoded = base64.b64decode(raw)
    except Exception:
        return b""
    return decoded if decoded.startswith(b"%PDF") else b""


def asset_manifest_payload(data: dict) -> dict[str, Any]:
    """Stable ordered content + approved asset references for digesting."""
    fields = data.get("fields") if isinstance(data.get("fields"), dict) else {}
    cover = data.get("cover_design") if isinstance(data.get("cover_design"), dict) else {}
    pages = data.get("pages") if isinstance(data.get("pages"), list) else None
    problems = data.get("problems") if isinstance(data.get("problems"), list) else None
    words = data.get("words") if isinstance(data.get("words"), list) else None
    challenge = (
        data.get("challenge_problems")
        if isinstance(data.get("challenge_problems"), list)
        else None
    )
    # Audience/goal are verified on the project record separately; they are not
    # part of the asset digest so Save can attach them without invalidating
    # the preview-stamped identity.
    _ = fields  # fields reserved for future cover/theme refs
    return {
        "product_type": data.get("product_type") or "",
        "title": data.get("title") or "",
        "package_id": str(data.get("package_id") or ""),
        "filename": str(data.get("filename") or ""),
        "cover_ref": str(
            cover.get("local_image_path")
            or cover.get("asset_url")
            or cover.get("image_url")
            or data.get("cover_image")
            or ""
        ),
        "ordered_content": {
            "problems": problems,
            "challenge_problems": challenge,
            "words": words,
            "pages": pages,
        },
        "approved_assets": list(data.get("image_jobs") or []),
    }


def asset_manifest_digest(data: dict) -> str:
    raw = json.dumps(
        asset_manifest_payload(data),
        sort_keys=True,
        ensure_ascii=False,
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def stamp_artifact_identity(data: dict, *, bump_revision: bool = False) -> dict:
    """Attach canonical digests + revision onto a product data dict (in place)."""
    if not isinstance(data, dict):
        return data
    product_type = str(data.get("product_type") or "")
    if product_type not in _PDF_PRODUCT_TYPES and not data.get("is_pdf"):
        return data

    pdf_bytes = decode_pdf_bytes(data)
    if pdf_bytes:
        data["content_digest"] = content_digest_from_pdf_bytes(pdf_bytes)
    data["asset_manifest_digest"] = asset_manifest_digest(data)

    rev = data.get("artifact_revision")
    try:
        rev_i = int(rev) if rev is not None else 1
    except (TypeError, ValueError):
        rev_i = 1
    if bump_revision:
        rev_i = max(1, rev_i) + 1
    elif rev is None:
        rev_i = 1
    data["artifact_revision"] = rev_i
    # Stable artifact id: generation package_id is authoritative when present.
    if data.get("package_id") and not data.get("artifact_id"):
        data["artifact_id"] = str(data.get("package_id"))
    return data


def verify_artifact_identity(data: dict) -> None:
    """Raise ValueError when saved digests disagree with stored PDF/content.

    Missing digests are allowed for legacy projects (no silent regen).
    Present digests that mismatch hard-fail instead of regenerating.
    """
    if not isinstance(data, dict):
        return
    product_type = str(data.get("product_type") or "")
    if product_type not in _PDF_PRODUCT_TYPES and not data.get("is_pdf"):
        return

    expected_content = str(data.get("content_digest") or "").strip()
    expected_assets = str(data.get("asset_manifest_digest") or "").strip()
    if not expected_content and not expected_assets:
        return

    pdf_bytes = decode_pdf_bytes(data)
    if expected_content:
        if not pdf_bytes:
            raise ValueError(
                "Artifact identity mismatch: content_digest is set but PDF bytes "
                "are missing. Export blocked — regenerate and re-save the product."
            )
        actual = content_digest_from_pdf_bytes(pdf_bytes)
        if actual != expected_content:
            raise ValueError(
                "Artifact identity mismatch: stored PDF does not match content_digest. "
                "Export blocked — will not silently regenerate a different artifact."
            )

    if expected_assets:
        actual_assets = asset_manifest_digest(data)
        if actual_assets != expected_assets:
            raise ValueError(
                "Artifact identity mismatch: ordered content/assets do not match "
                "asset_manifest_digest. Export blocked — will not silently regenerate."
            )


def package_belongs_to_project(data: dict, package_id: str) -> bool:
    """True when package_id is the generation or current export package."""
    pkg = str(package_id or "").strip()
    if not pkg or not isinstance(data, dict):
        return False
    if str(data.get("package_id") or "") == pkg:
        return True
    if str(data.get("export_package_id") or "") == pkg:
        return True
    if str(data.get("artifact_id") or "") == pkg:
        return True
    exports = data.get("product_exports") or {}
    if isinstance(exports, dict):
        for val in exports.values():
            if isinstance(val, dict) and str(val.get("package_id") or "") == pkg:
                return True
        files = exports.get("files") if isinstance(exports.get("files"), dict) else {}
        for meta in files.values():
            if not isinstance(meta, dict):
                continue
            url = str(meta.get("url") or "")
            if f"/download/{pkg}/" in url:
                return True
    return False
