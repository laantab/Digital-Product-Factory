"""Customer-keep restore: visibility flags + existing-artifact PDF/ZIP wiring.

Does not call OpenAI, Tavily, Pexels, or image generation. Does not rewrite
manuscript, cover design, visuals, or stored preview HTML for #4249.
"""
from __future__ import annotations

import hashlib
import json
import os
import zipfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
EXPORTS = Path(os.environ.get("FACTORY_EXPORTS_DIR") or (ROOT / "exports"))

COVER_SHA_4249 = "465a3e10861cd056a98008a8131be157be9dc0d22ec93464fa831fcbb03367cd"
COVER_DIGEST_4249 = "55567b21e03e3d5734ff5c355c3f4771b4771480d88566ebbdabcbd0d970d016"
MANUSCRIPT_DIGEST_4249 = "cf08285598b6d7ac722844a97a5d54f89da2b37e8b11a5bd3df9768b8010cf98"
PREVIEW_DIGEST_4249 = "b853a69507da0c3a3e5d350f1160bb7675ac6ae076314ed76711de9cadf14126"


def _sha_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _download_url(package_id: str, name: str) -> str:
    return f"/download/{package_id}/{name}"


def _identity_4249(data: dict) -> dict[str, str]:
    cover = data.get("cover_design") if isinstance(data.get("cover_design"), dict) else {}
    source = cover.get("source") if isinstance(cover.get("source"), dict) else {}
    ident = (
        data.get("ebook_export_identity")
        if isinstance(data.get("ebook_export_identity"), dict)
        else {}
    )
    return {
        "cover_sha": str(source.get("sha256") or ""),
        "cover_digest": str(cover.get("cover_digest") or ident.get("cover_digest") or ""),
        "manuscript_digest": str(
            ident.get("manuscript_digest") or data.get("ebook_manuscript_digest") or ""
        ),
        "preview_digest": str(
            ident.get("preview_digest")
            or data.get("ebook_preview_digest")
            or ""
        ),
    }


def assert_4249_identity(data: dict) -> None:
    ident = _identity_4249(data)
    if ident["cover_sha"] != COVER_SHA_4249:
        raise RuntimeError("Refusing to continue: #4249 cover SHA changed")
    if ident["cover_digest"] != COVER_DIGEST_4249:
        raise RuntimeError("Refusing to continue: #4249 cover digest changed")
    if ident["manuscript_digest"] != MANUSCRIPT_DIGEST_4249:
        raise RuntimeError("Refusing to continue: #4249 manuscript digest changed")
    if ident["preview_digest"] != PREVIEW_DIGEST_4249:
        raise RuntimeError("Refusing to continue: #4249 preview digest changed")


def _cover_pdf_matching_digest(pkg_dir: Path, digest: str) -> Path | None:
    for path in pkg_dir.rglob("cover.pdf"):
        try:
            if path.is_file() and _sha_file(path) == digest:
                return path
        except OSError:
            continue
    return None


def _write_zip(pkg_dir: Path, files: dict[str, bytes]) -> Path:
    zip_path = pkg_dir / "package.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name, blob in files.items():
            zf.writestr(name, blob)
    return zip_path


def _export_bundle(package_id: str, *, has_pdf: bool, has_zip: bool) -> dict[str, Any]:
    files: dict[str, Any] = {}
    if has_pdf:
        files["pdf"] = {
            "name": "ebook.pdf",
            "url": _download_url(package_id, "ebook.pdf"),
        }
    if has_zip:
        files["zip"] = {
            "name": "package.zip",
            "url": _download_url(package_id, "package.zip"),
        }
    files["html"] = {
        "name": "ebook.html",
        "url": _download_url(package_id, "ebook.html"),
    }
    return {
        "package_id": package_id,
        "folder": str(EXPORTS / package_id),
        "pdf_available": has_pdf,
        "files": files,
    }


def reuse_existing_keep_export(project: dict) -> dict | None:
    """Return existing PDF/ZIP URLs without regenerating content."""
    data = project.get("data") if isinstance(project.get("data"), dict) else {}
    if data.get("customer_keep") is not True:
        return None
    package_id = str(data.get("package_id") or data.get("export_package_id") or "").strip()
    if not package_id:
        return None
    pkg_dir = EXPORTS / package_id
    pdf_path = pkg_dir / "ebook.pdf"
    zip_path = pkg_dir / "package.zip"
    has_pdf = pdf_path.is_file() and pdf_path.stat().st_size > 8
    has_zip = zip_path.is_file() and zip_path.stat().st_size > 0
    if not has_pdf and not has_zip:
        return None
    exports = _export_bundle(package_id, has_pdf=has_pdf, has_zip=has_zip)
    if has_pdf:
        exports["files"]["pdf"]["sha256"] = _sha_file(pdf_path)
    if has_zip:
        exports["files"]["zip"]["sha256"] = _sha_file(zip_path)
    return {"package_id": package_id, "exports": exports}


def package_4249_from_stored_preview(data: dict) -> dict[str, Any]:
    """Build ebook.pdf/package.zip from stored preview HTML + existing cover PDF.

    Does not mutate manuscript, cover_design, visuals, or preview HTML fields.
    """
    assert_4249_identity(data)
    package_id = str(data.get("package_id") or data.get("artifact_id") or "").strip()
    if not package_id:
        raise RuntimeError("#4249 has no package_id")
    pkg_dir = EXPORTS / package_id
    pkg_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = pkg_dir / "ebook.pdf"
    zip_path = pkg_dir / "package.zip"
    html = str(data.get("ebook_preview_html") or data.get("preview_html") or "")
    if not html.strip():
        raise RuntimeError("#4249 stored preview HTML is missing")

    html_path = pkg_dir / "ebook.html"
    if not html_path.exists():
        html_path.write_text(html, encoding="utf-8")

    rebuilt = False
    if not (pdf_path.is_file() and pdf_path.read_bytes()[:5] == b"%PDF"):
        cover_path = _cover_pdf_matching_digest(pkg_dir, COVER_DIGEST_4249)
        if cover_path is None:
            raise RuntimeError("#4249 cover PDF matching cover digest was not found")
        from services.pdf_export import (
            _html_to_pdf_xhtml2pdf,
            _prepend_pdf_bytes,
            _remove_accidental_blank_pages,
            _sanitize_pdf_local_link_uris,
        )

        interior = _remove_accidental_blank_pages(_html_to_pdf_xhtml2pdf(html))
        if not interior.startswith(b"%PDF"):
            raise RuntimeError("#4249 interior PDF conversion failed")
        cover_bytes = cover_path.read_bytes()
        pdf_bytes = _sanitize_pdf_local_link_uris(
            _remove_accidental_blank_pages(_prepend_pdf_bytes(cover_bytes, interior))
        )
        if not pdf_bytes.startswith(b"%PDF"):
            raise RuntimeError("#4249 merged PDF is not a real PDF")
        pdf_path.write_bytes(pdf_bytes)
        rebuilt = True

    if rebuilt or not zip_path.is_file() or zip_path.stat().st_size <= 0:
        zip_files = {
            "ebook.pdf": pdf_path.read_bytes(),
            "ebook.html": html.encode("utf-8"),
        }
        _write_zip(pkg_dir, zip_files)

    assert_4249_identity(data)
    return {
        "package_id": package_id,
        "pdf_path": str(pdf_path),
        "zip_path": str(zip_path),
        "pdf_size": pdf_path.stat().st_size,
        "zip_size": zip_path.stat().st_size,
        "rebuilt_pdf": rebuilt,
    }


def _stamp_keep_flags(data: dict) -> dict:
    payload = dict(data or {})
    payload["customer_keep"] = True
    payload["user_confirmed_save"] = True
    payload["user_saved"] = True
    payload["hidden_from_customer"] = False
    payload["internal_record"] = False
    payload["system_test"] = False
    payload["temporary"] = False
    return payload


def _wire_export_paths(data: dict, *, package_id: str, has_pdf: bool, has_zip: bool) -> dict:
    payload = dict(data)
    bundle = _export_bundle(package_id, has_pdf=has_pdf, has_zip=has_zip)
    pkg_dir = EXPORTS / package_id
    pdf_path = pkg_dir / "ebook.pdf"
    zip_path = pkg_dir / "package.zip"
    if has_pdf and pdf_path.is_file():
        bundle["files"]["pdf"]["sha256"] = _sha_file(pdf_path)
        payload["pdf_path"] = str(pdf_path)
        payload["export_files"] = dict(payload.get("export_files") or {})
        payload["export_files"]["ebook.pdf"] = str(pdf_path)
        payload["export_files"]["package.zip"] = str(zip_path)
    if has_zip and zip_path.is_file():
        bundle["files"]["zip"]["sha256"] = _sha_file(zip_path)
        payload["zip_path"] = str(zip_path)
    payload["package_id"] = package_id
    payload["product_exports"] = bundle
    existing = payload.get("exports") if isinstance(payload.get("exports"), dict) else {}
    merged = dict(existing)
    merged["package_id"] = package_id
    merged["files"] = dict(existing.get("files") or {})
    merged["files"].update(bundle["files"])
    if has_pdf:
        merged["pdf_available"] = True
    payload["exports"] = merged
    return payload


def restore_customer_keep_project(project_id: int) -> dict[str, Any]:
    import database

    project = database.get_project(project_id)
    if not project:
        return {"id": project_id, "ok": False, "error": "missing"}
    data = dict(project.get("data") or {})
    before_ident = _identity_4249(data) if project_id == 4249 else None
    data = _stamp_keep_flags(data)
    package_id = str(data.get("package_id") or data.get("artifact_id") or "").strip()
    report: dict[str, Any] = {
        "id": project_id,
        "name": project.get("name"),
        "title": data.get("title"),
        "package_id": package_id,
        "ok": True,
    }

    if project_id == 4249:
        packaged = package_4249_from_stored_preview(data)
        report.update(packaged)
        data = _wire_export_paths(
            data,
            package_id=packaged["package_id"],
            has_pdf=True,
            has_zip=True,
        )
        assert_4249_identity(data)
        if before_ident != _identity_4249(data):
            raise RuntimeError("Refusing to continue: #4249 identity fields changed")
    elif project_id == 14626:
        pkg_dir = EXPORTS / package_id if package_id else None
        pdf_path = pkg_dir / "ebook.pdf" if pkg_dir else None
        zip_path = pkg_dir / "package.zip" if pkg_dir else None
        has_pdf = bool(pdf_path and pdf_path.is_file() and pdf_path.stat().st_size > 8)
        has_zip = bool(zip_path and zip_path.is_file() and zip_path.stat().st_size > 0)
        if has_pdf:
            try:
                has_pdf = pdf_path.read_bytes()[:5] == b"%PDF"
            except OSError:
                has_pdf = False
        report["has_pdf"] = has_pdf
        report["has_zip"] = has_zip
        report["missing_photo"] = True
        report["pdf_blocker"] = (
            "Chapter photo Parent-Teen Social Media Check-In is missing, "
            "cover is not chosen, and referenced img_v2_0/img_v4_0/img_v6_0 "
            "files are not on disk. No honest complete PDF was packaged."
        )
        if package_id:
            data = _wire_export_paths(
                data, package_id=package_id, has_pdf=has_pdf, has_zip=has_zip
            )
    else:
        report["ok"] = False
        report["error"] = "not in customer-keep allowlist"
        return report

    updated = database.update_project(
        project_id,
        name=None,
        data=data,
        user_saved=True,
        system_test=False,
        temporary=False,
        user_confirmed_save=True,
    )
    if not updated:
        raise RuntimeError(f"Failed to persist customer_keep flags for #{project_id}")
    if project_id == 4249:
        assert_4249_identity(updated.get("data") or {})
    report["persisted"] = True
    return report


def restore_known_keep_projects() -> list[dict[str, Any]]:
    import database

    reports = []
    for pid in sorted(database.CUSTOMER_KEEP_PROJECT_IDS):
        reports.append(restore_customer_keep_project(pid))
    return reports


if __name__ == "__main__":
    os.environ.setdefault("FACTORY_TEST_MODE", "1")
    os.environ.setdefault("OPENAI_API_KEY", "")
    os.environ.setdefault("TAVILY_API_KEY", "")
    os.environ.setdefault("PEXELS_API_KEY", "")
    for item in restore_known_keep_projects():
        print(json.dumps(item, default=str))
