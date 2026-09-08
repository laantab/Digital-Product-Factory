"""Promote a designed verification ZIP to a customer-final package.

The design renderer may stamp ``verification_copy: true`` on a preflight /
preview archive. A customer download must never expose that flag.

Promotion copies every existing ZIP member byte-for-byte — including the
approved PDF — and rewrites only ``manifest.json``. It never re-renders the
PDF or manuscript.
"""
from __future__ import annotations

import hashlib
import io
import json
import zipfile
from pathlib import Path
from typing import Any


PACKAGE_STATUS_CUSTOMER_FINAL = "customer_final"
_PDF_MEMBER = "ebook.pdf"
_MANIFEST_MEMBER = "manifest.json"


def _sha_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload or b"").hexdigest()


def current_package_id(data: dict | None) -> str:
    data = data or {}
    return str(
        data.get("export_package_id")
        or data.get("package_id")
        or data.get("artifact_id")
        or ""
    ).strip()


def certified_pdf_sha256(data: dict | None) -> str:
    """Authoritative approved PDF digest. Prefer preview_digest (certified)."""
    data = data or {}
    ident = data.get("ebook_export_identity")
    ident = ident if isinstance(ident, dict) else {}
    return str(
        ident.get("preview_digest")
        or ident.get("pdf_sha256")
        or data.get("preview_digest")
        or data.get("ebook_preview_digest")
        or data.get("pdf_sha256")
        or ""
    ).strip().lower()


def is_customer_final_manifest(manifest: dict | None) -> bool:
    if not isinstance(manifest, dict):
        return False
    if manifest.get("verification_copy") is True:
        return False
    status = str(manifest.get("package_status") or "").strip().lower()
    if status == PACKAGE_STATUS_CUSTOMER_FINAL:
        return True
    return manifest.get("verification_copy") is False


def customer_final_manifest(manifest: dict | None, *, pdf_sha256: str) -> dict[str, Any]:
    out = dict(manifest) if isinstance(manifest, dict) else {}
    out["verification_copy"] = False
    out["package_status"] = PACKAGE_STATUS_CUSTOMER_FINAL
    if pdf_sha256:
        out["pdf_sha256"] = pdf_sha256
    # Inner archive must not claim a zip hash it cannot know yet.
    out.pop("zip_sha256", None)
    return out


def _read_zip_members(zip_bytes: bytes) -> tuple[list[zipfile.ZipInfo], dict[str, bytes]]:
    with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as zin:
        infos = list(zin.infolist())
        members = {info.filename: zin.read(info.filename) for info in infos}
    return infos, members


def _inner_pdf_bytes(members: dict[str, bytes]) -> tuple[str, bytes]:
    if _PDF_MEMBER in members:
        return _PDF_MEMBER, members[_PDF_MEMBER]
    for name, blob in members.items():
        if name.lower().endswith(".pdf") and blob.startswith(b"%PDF"):
            return name, blob
    raise ValueError("Customer package is missing ebook.pdf")


def promote_zip_to_customer_final(
    zip_bytes: bytes,
    *,
    expected_pdf_sha256: str | None = None,
) -> dict[str, Any]:
    """Rebuild ``zip_bytes`` as a customer-final archive.

    All non-manifest members (including the approved PDF) are copied exactly.
    Returns ``zip_bytes``, ``zip_sha256``, ``pdf_sha256``, ``manifest``,
    ``sidecar_manifest``, and ``changed``.
    """
    if not zip_bytes:
        raise ValueError("Customer package ZIP is missing")

    infos, members = _read_zip_members(zip_bytes)
    pdf_name, pdf_bytes = _inner_pdf_bytes(members)
    pdf_sha = _sha_bytes(pdf_bytes)
    expected = str(expected_pdf_sha256 or "").strip().lower()
    if expected and pdf_sha != expected:
        raise ValueError(
            "Certified PDF hash mismatch; refusing to promote a different PDF."
        )

    raw_manifest = members.get(_MANIFEST_MEMBER, b"{}")
    try:
        loaded = json.loads(raw_manifest.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Customer package manifest.json is not valid JSON") from exc
    if loaded is not None and not isinstance(loaded, dict):
        raise ValueError("Customer package manifest.json must be an object")
    manifest = loaded if isinstance(loaded, dict) else {}

    if is_customer_final_manifest(manifest) and manifest.get("verification_copy") is not True:
        sidecar = dict(manifest)
        sidecar["verification_copy"] = False
        sidecar["package_status"] = PACKAGE_STATUS_CUSTOMER_FINAL
        sidecar["pdf_sha256"] = pdf_sha
        sidecar["zip_sha256"] = _sha_bytes(zip_bytes)
        return {
            "zip_bytes": zip_bytes,
            "zip_sha256": sidecar["zip_sha256"],
            "pdf_sha256": pdf_sha,
            "pdf_name": pdf_name,
            "manifest": dict(manifest),
            "sidecar_manifest": sidecar,
            "changed": False,
        }

    new_manifest = customer_final_manifest(manifest, pdf_sha256=pdf_sha)
    manifest_bytes = json.dumps(new_manifest, indent=2).encode("utf-8")

    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as zout:
        wrote_manifest = False
        for info in infos:
            payload = manifest_bytes if info.filename == _MANIFEST_MEMBER else members[info.filename]
            if info.filename == _MANIFEST_MEMBER:
                wrote_manifest = True
            cloned = zipfile.ZipInfo(filename=info.filename, date_time=info.date_time)
            cloned.compress_type = info.compress_type
            cloned.comment = info.comment
            cloned.extra = info.extra
            cloned.create_system = info.create_system
            cloned.create_version = info.create_version
            cloned.extract_version = info.extract_version
            cloned.flag_bits = info.flag_bits
            cloned.internal_attr = info.internal_attr
            cloned.external_attr = info.external_attr
            cloned.volume = info.volume
            zout.writestr(cloned, payload)
        if not wrote_manifest:
            zout.writestr(_MANIFEST_MEMBER, manifest_bytes)

    new_zip = out.getvalue()
    zip_sha = _sha_bytes(new_zip)
    sidecar = dict(new_manifest)
    sidecar["zip_sha256"] = zip_sha
    sidecar["pdf_sha256"] = pdf_sha
    sidecar["verification_copy"] = False
    sidecar["package_status"] = PACKAGE_STATUS_CUSTOMER_FINAL
    return {
        "zip_bytes": new_zip,
        "zip_sha256": zip_sha,
        "pdf_sha256": pdf_sha,
        "pdf_name": pdf_name,
        "manifest": new_manifest,
        "sidecar_manifest": sidecar,
        "changed": True,
    }


def apply_promoted_identity(data: dict, promoted: dict[str, Any]) -> dict:
    """Stamp ZIP identity after promotion. Never changes the PDF digest."""
    ident = dict(data.get("ebook_export_identity") or {}) if isinstance(data.get("ebook_export_identity"), dict) else {}
    pdf_sha = str(promoted.get("pdf_sha256") or "")
    zip_sha = str(promoted.get("zip_sha256") or "")
    if pdf_sha:
        ident["pdf_sha256"] = pdf_sha
        if not ident.get("preview_digest"):
            ident["preview_digest"] = pdf_sha
    if zip_sha:
        ident["zip_sha256"] = zip_sha
        data["zip_sha256"] = zip_sha
    ident["verification_copy"] = False
    ident["package_status"] = PACKAGE_STATUS_CUSTOMER_FINAL
    data["ebook_export_identity"] = ident
    return data


def load_reusable_workspace_export(data: dict | None, exports_dir: str | Path) -> dict[str, Any] | None:
    """Return on-disk PDF/ZIP when the PDF matches the certified digest.

    Used so packaging can promote the existing customer archive without
    re-rendering the approved PDF or manuscript.
    """
    data = data or {}
    package_id = current_package_id(data)
    certified = certified_pdf_sha256(data)
    if not package_id or not certified:
        return None
    pkg_dir = Path(exports_dir) / package_id
    pdf_path = pkg_dir / "ebook.pdf"
    zip_path = pkg_dir / "package.zip"
    if not pdf_path.is_file() or not zip_path.is_file():
        return None
    pdf_bytes = pdf_path.read_bytes()
    if not pdf_bytes.startswith(b"%PDF"):
        return None
    if _sha_bytes(pdf_bytes) != certified:
        return None
    zip_bytes = zip_path.read_bytes()
    try:
        _infos, members = _read_zip_members(zip_bytes)
        _name, inner_pdf = _inner_pdf_bytes(members)
    except ValueError:
        return None
    if _sha_bytes(inner_pdf) != certified:
        return None
    html = ""
    html_path = pkg_dir / "ebook.html"
    if html_path.is_file():
        html = html_path.read_text(encoding="utf-8")
    return {
        "package_id": package_id,
        "pdf_bytes": pdf_bytes,
        "zip_bytes": zip_bytes,
        "html": html,
        "package_dir": str(pkg_dir),
    }


def promote_package_dir(
    package_dir: str | Path,
    *,
    expected_pdf_sha256: str | None = None,
) -> dict[str, Any]:
    """Promote ``package.zip`` in an export folder. Leaves ``ebook.pdf`` untouched."""
    pkg = Path(package_dir)
    zip_path = pkg / "package.zip"
    pdf_path = pkg / "ebook.pdf"
    if not zip_path.is_file():
        raise ValueError(f"package.zip is missing under {pkg}")
    zip_bytes = zip_path.read_bytes()
    expected = str(expected_pdf_sha256 or "").strip().lower()
    if pdf_path.is_file():
        disk_pdf = pdf_path.read_bytes()
        disk_sha = _sha_bytes(disk_pdf)
        if expected and disk_sha != expected:
            raise ValueError(
                "On-disk ebook.pdf does not match the certified PDF hash."
            )
        expected = expected or disk_sha
    promoted = promote_zip_to_customer_final(zip_bytes, expected_pdf_sha256=expected or None)
    if promoted["changed"]:
        zip_path.write_bytes(promoted["zip_bytes"])
    sidecar_path = pkg / "manifest.json"
    sidecar_path.write_text(
        json.dumps(promoted["sidecar_manifest"], indent=2),
        encoding="utf-8",
    )
    if pdf_path.is_file():
        after_pdf = _sha_bytes(pdf_path.read_bytes())
        if after_pdf != promoted["pdf_sha256"]:
            raise RuntimeError("Promotion mutated ebook.pdf")
    return promoted
