"""Design-bound preview/PDF/ZIP export. No manuscript rewrite. No paid calls."""
from __future__ import annotations

import hashlib
import json
import os
import zipfile
from pathlib import Path
from typing import Any

from services.ebook_book_layout import (
    find_designed_chapter_pages,
    manuscript_text_fingerprint,
    numbered_chapters,
    render_designed_ebook_html,
)
from services.ebook_cover_local import cover_design_from_local
from services.ebook_design_preflight import (
    PREFLIGHT_PASS,
    run_design_preflight,
    verify_export_bytes,
)
from services.ebook_design_spec import EbookDesign, build_ebook_design, design_is_stale
from services.ebook_design_system import list_professional_themes, theme_sample_html
from services.ebook_manuscript_engine import QUALITY_PASS, validate_manuscript_quality

FIXTURE_EXPORT_DIRNAME = "ebook_design_fixture_pass_b"


def _sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data or b"").hexdigest()


def is_ebook_workspace(data: dict | None) -> bool:
    data = data or {}
    return bool(data.get("ebook_project_workspace") or data.get("ebook_workspace"))


def visual_manifest_from_manuscript(manuscript_md: str) -> dict[str, Any]:
    """Manuscript-derived visual slots only. Never paid images."""
    slots: list[dict[str, Any]] = []
    for i, (title, body) in enumerate(numbered_chapters(manuscript_md), start=1):
        kinds = []
        if "|" in (body or "") and "---" in (body or ""):
            kinds.append("table")
        if "checklist" in (body or "").lower():
            kinds.append("checklist")
        if any(line.strip()[:3].rstrip(".").isdigit() for line in (body or "").splitlines() if line.strip()[:3]):
            kinds.append("workflow")
        if kinds:
            slots.append({"chapter": i, "title": title, "kinds": kinds, "paid_image": False})
    payload = {"slots": slots, "paid_images": False, "source": "manuscript_derived"}
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    payload["digest"] = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return payload


def require_quality_pass(data: dict) -> None:
    md = str(data.get("content") or data.get("ebook") or "")
    quality = validate_manuscript_quality(data, manuscript_md=md)
    if quality.status != QUALITY_PASS:
        raise ValueError("Design is blocked until manuscript quality is PASS.")


def select_theme(data: dict, theme_id: str) -> dict:
    """Persist EbookDesign for a quality-PASS manuscript. Does not rewrite content."""
    from services.ebook_project_workspace import manuscript_digest

    require_quality_pass(data)
    md = str(data.get("content") or data.get("ebook") or "")
    before = manuscript_text_fingerprint(md)
    existing_plan = data.get("visual_plan") if isinstance(data.get("visual_plan"), dict) else None
    from services.ebook_visual_pipeline import manifest_from_plan, plan_is_valid, required_aids

    if plan_is_valid(existing_plan) and required_aids(existing_plan):
        visual = data.get("ebook_visual_manifest") if isinstance(data.get("ebook_visual_manifest"), dict) else None
        visual = visual if visual and visual.get("assets") else manifest_from_plan(existing_plan)
    else:
        visual = visual_manifest_from_manuscript(md)
    cover = data.get("cover_design") if isinstance(data.get("cover_design"), dict) else {}
    prev = data.get("ebook_design") if isinstance(data.get("ebook_design"), dict) else {}
    revision = int(prev.get("revision") or 0) + 1
    design = build_ebook_design(
        theme_id=theme_id,
        manuscript_digest=manuscript_digest(data),
        document_identity=str(data.get("artifact_id") or data.get("package_id") or ""),
        cover_digest=str(cover.get("cover_digest") or ""),
        visual_manifest_digest=str(visual.get("digest") or ""),
        visual_slot_placements=list(visual.get("slots") or []),
        cover_identity={
            "title": cover.get("title") or data.get("title"),
            "subtitle": cover.get("subtitle") or data.get("subtitle"),
            "author": cover.get("author") or data.get("author_brand"),
            "theme": cover.get("theme"),
            **(
                {
                    "image_digest": str(
                        cover.get("image_digest")
                        or (cover.get("source") or {}).get("sha256")
                        or ""
                    )
                }
                if (cover.get("image_digest") or (cover.get("source") or {}).get("sha256"))
                else {}
            ),
        },
        revision=revision,
    )
    data["ebook_design"] = design.to_dict()
    data["ebook_design_digest"] = design.digest
    data["design_theme"] = design.theme_id
    data["ebook_visual_manifest"] = visual
    data["ebook_visual_manifest_digest"] = visual["digest"]
    data["ebook_preview_html"] = ""
    data["ebook_export_identity"] = None
    data["ebook_design_preflight"] = None
    data["export_ready"] = False
    data["release_status"] = ""
    after = manuscript_text_fingerprint(str(data.get("content") or data.get("ebook") or ""))
    if after != before:
        raise RuntimeError("Design selection mutated manuscript content.")
    return data


def generate_workspace_cover(data: dict, *, package_id: str = "") -> dict:
    """Deterministic local cover. No paid image generation."""
    require_quality_pass(data)
    title = str(data.get("title") or "")
    subtitle = str(data.get("subtitle") or "")
    author = str(data.get("author_brand") or data.get("author") or "")
    topic = str((data.get("fields") or {}).get("topic") or data.get("source") or title)
    audience = str(data.get("audience") or (data.get("fields") or {}).get("audience") or "")
    pkg = package_id or str(data.get("package_id") or data.get("artifact_id") or "ebook_design_local")
    cover = cover_design_from_local(
        title=title,
        subtitle=subtitle,
        author=author,
        package_id=pkg,
        topic=topic,
        audience=audience,
        fields=dict(data.get("fields") or {}),
    )
    data["cover_design"] = cover
    data["package_id"] = pkg
    data["ebook_cover_digest"] = cover.get("cover_digest")
    data["export_ready"] = False
    data["release_status"] = ""
    return data


def _html_to_pdf(html_doc: str, *, title: str, author: str, subtitle: str = "") -> bytes:
    from services.pdf_export import (
        _apply_pdf_metadata,
        _html_to_pdf_xhtml2pdf,
        _prepend_pdf_bytes,
        _remove_accidental_blank_pages,
    )

    body_pdf = _html_to_pdf_xhtml2pdf(html_doc)
    body_pdf = _remove_accidental_blank_pages(body_pdf)
    return _apply_pdf_metadata(
        body_pdf,
        title=title,
        author=author,
        subject=subtitle or title,
        keywords="ebook, designed interior",
    )


def render_designed_bundle(data: dict, *, output_dir: str | Path | None = None) -> dict[str, Any]:
    """Render preview HTML + PDF + ZIP for a quality-PASS manuscript and bound design."""
    from services.ebook_project_workspace import manuscript_digest

    require_quality_pass(data)
    md = str(data.get("content") or data.get("ebook") or "")
    before = manuscript_text_fingerprint(md)
    design = EbookDesign.from_dict(data.get("ebook_design") if isinstance(data.get("ebook_design"), dict) else {})
    if design_is_stale(design, manuscript_digest=manuscript_digest(data)):
        raise ValueError("Design is stale or missing. Select a theme after manuscript quality PASS.")

    title = str(data.get("title") or "Ebook")
    subtitle = str(data.get("subtitle") or "")
    author = str(data.get("author_brand") or data.get("author") or "")
    audience = str(data.get("audience") or "")
    html_doc = render_designed_ebook_html(
        title=title,
        subtitle=subtitle,
        author=author,
        manuscript_md=md,
        design=design,
        audience=audience,
        visual_plan=data.get("visual_plan") if isinstance(data.get("visual_plan"), dict) else None,
        # A separate designed cover PDF is always prepended below — an
        # interior title page here would duplicate it.
        include_title_page=False,
    )
    cover = data.get("cover_design") if isinstance(data.get("cover_design"), dict) else {}
    cover_pdf_path = str(cover.get("local_cover_pdf") or "")
    cover_pdf = b""
    if cover_pdf_path and os.path.isfile(cover_pdf_path):
        with open(cover_pdf_path, "rb") as fh:
            cover_pdf = fh.read()
    if not cover_pdf:
        if cover.get("workflow") == "photo_backed":
            raise ValueError("Photo-backed cover PDF is missing. Export cannot reconstruct the cover.")
        from services.ebook_cover_local import generate_local_cover_pdf_bytes

        cover_pdf = generate_local_cover_pdf_bytes(
            title, subtitle, author=author, topic=str(data.get("source") or title), audience=audience
        )

    from services.pdf_export import (
        _prepend_pdf_bytes,
        _remove_accidental_blank_pages,
        _sanitize_pdf_local_link_uris,
    )

    def _merge(html: str) -> bytes:
        interior = _html_to_pdf(html, title=title, author=author, subtitle=subtitle)
        return _sanitize_pdf_local_link_uris(
            _remove_accidental_blank_pages(_prepend_pdf_bytes(cover_pdf, interior))
        )

    pdf_bytes = _merge(html_doc)
    chapter_titles = [ctitle for ctitle, _body in numbered_chapters(md)]
    toc_pages = find_designed_chapter_pages(pdf_bytes, chapter_titles)
    if toc_pages:
        numbered_html = render_designed_ebook_html(
            title=title,
            subtitle=subtitle,
            author=author,
            manuscript_md=md,
            design=design,
            audience=audience,
            visual_plan=data.get("visual_plan") if isinstance(data.get("visual_plan"), dict) else None,
            toc_page_numbers=toc_pages,
            include_title_page=False,
        )
        numbered_pdf = _merge(numbered_html)
        html_doc = numbered_html
        pdf_bytes = numbered_pdf
    preview_digest = _sha_bytes(pdf_bytes)

    manifest = {
        "title": title,
        "subtitle": subtitle,
        "author": author,
        "manuscript_digest": manuscript_digest(data),
        "design_digest": design.digest,
        "cover_digest": str(cover.get("cover_digest") or _sha_bytes(cover_pdf)),
        "visual_manifest_digest": str(data.get("ebook_visual_manifest_digest") or ""),
        "pdf_sha256": preview_digest,
        "theme_id": design.theme_id,
        "paid_images": False,
        "verification_copy": True,
    }
    zip_buf_files = {
        "ebook.pdf": pdf_bytes,
        "ebook.html": html_doc.encode("utf-8"),
        "manifest.json": json.dumps(manifest, indent=2).encode("utf-8"),
    }
    from services.ebook_visual_pipeline import collect_zip_visual_files

    zip_buf_files.update(collect_zip_visual_files(data))
    import io

    zbuf = io.BytesIO()
    with zipfile.ZipFile(zbuf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name, blob in zip_buf_files.items():
            zf.writestr(name, blob)
    zip_bytes = zbuf.getvalue()
    manifest["zip_sha256"] = _sha_bytes(zip_bytes)
    identity = {
        "manuscript_digest": manifest["manuscript_digest"],
        "design_digest": manifest["design_digest"],
        "cover_digest": manifest["cover_digest"],
        "visual_manifest_digest": manifest["visual_manifest_digest"],
        "pdf_sha256": manifest["pdf_sha256"],
        "zip_sha256": manifest["zip_sha256"],
        "preview_digest": preview_digest,
    }
    preflight = run_design_preflight(
        data,
        pdf_bytes=pdf_bytes,
        zip_bytes=zip_bytes,
        preview_digest=preview_digest,
        html=html_doc,
        design=design,
    )
    identity.update(preflight.identity)
    # Keep zip hash from the actual zip
    identity["zip_sha256"] = manifest["zip_sha256"]
    identity["pdf_sha256"] = preview_digest
    identity["preview_digest"] = preview_digest

    if output_dir:
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        (out / "ebook.pdf").write_bytes(pdf_bytes)
        (out / "ebook.html").write_text(html_doc, encoding="utf-8")
        (out / "manifest.json").write_text(json.dumps({**manifest, **identity, "preflight": preflight.as_dict()}, indent=2), encoding="utf-8")
        (out / "package.zip").write_bytes(zip_bytes)

    after = manuscript_text_fingerprint(str(data.get("content") or data.get("ebook") or ""))
    if after != before:
        raise RuntimeError("Export mutated manuscript content.")

    data["ebook_preview_html"] = html_doc
    data["ebook_export_identity"] = identity
    data["ebook_design_preflight"] = preflight.as_dict()
    data["preview_html"] = html_doc
    if preflight.status == PREFLIGHT_PASS:
        data["export_ready"] = True
        data["release_status"] = "PASS"
    else:
        data["export_ready"] = False
        data["release_status"] = preflight.status
    return {
        "html": html_doc,
        "pdf_bytes": pdf_bytes,
        "zip_bytes": zip_bytes,
        "identity": identity,
        "preflight": preflight.as_dict(),
        "themes": list_professional_themes(),
    }


def rasterize_pdf_pages(pdf_bytes: bytes, output_dir: str | Path, *, dpi: int = 110) -> list[str]:
    import fitz

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    paths: list[str] = []
    zoom = dpi / 72.0
    try:
        for i, page in enumerate(doc):
            pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
            path = out / f"page-{i + 1:03d}.png"
            pix.save(str(path))
            paths.append(str(path))
    finally:
        doc.close()
    return paths


def write_contact_sheet(page_pngs: list[str], dest: str | Path, *, cols: int = 4) -> str:
    from PIL import Image

    dest = Path(dest)
    images = [Image.open(p).convert("RGB") for p in page_pngs]
    if not images:
        raise ValueError("No page rasters for contact sheet.")
    w, h = images[0].size
    thumb_w = 240
    thumb_h = int(h * (thumb_w / w))
    cols = max(1, cols)
    rows = (len(images) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * thumb_w, rows * thumb_h), (248, 250, 252))
    for i, im in enumerate(images):
        im = im.resize((thumb_w, thumb_h))
        r, c = divmod(i, cols)
        sheet.paste(im, (c * thumb_w, r * thumb_h))
    dest.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(dest, "PNG")
    for im in images:
        im.close()
    return str(dest)


def inspect_raster_pages(page_pngs: list[str]) -> list[dict[str, Any]]:
    from PIL import Image, ImageStat

    rows: list[dict[str, Any]] = []
    for i, path in enumerate(page_pngs, start=1):
        im = Image.open(path).convert("L")
        stat = ImageStat.Stat(im)
        mean = float(stat.mean[0])
        extrema = im.getextrema()
        rows.append(
            {
                "page": i,
                "path": path,
                "width": im.size[0],
                "height": im.size[1],
                "mean_luma": round(mean, 2),
                "min_luma": extrema[0],
                "max_luma": extrema[1],
                "nearly_blank": mean > 248 and (extrema[1] - extrema[0]) < 8,
            }
        )
        im.close()
    return rows


def render_strong_fixture_bundle(output_dir: str | Path) -> dict[str, Any]:
    """Verification output for the Pass A strong fixture. Not a customer book."""
    from services.ebook_design_workspace import build_design_ready_fixture_data

    data = build_design_ready_fixture_data()
    bundle = render_designed_bundle(data, output_dir=output_dir)
    pages_dir = Path(output_dir) / "pages"
    pngs = rasterize_pdf_pages(bundle["pdf_bytes"], pages_dir)
    contact = write_contact_sheet(pngs, Path(output_dir) / "contact_sheet.png")
    inspection = inspect_raster_pages(pngs)
    report = {
        "page_count": len(pngs),
        "contact_sheet": contact,
        "pages": inspection,
        "preflight": bundle["preflight"],
        "identity": bundle["identity"],
        "pdf_path": str(Path(output_dir) / "ebook.pdf"),
        "zip_path": str(Path(output_dir) / "package.zip"),
    }
    (Path(output_dir) / "inspection.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    bundle["inspection"] = report
    bundle["data"] = data
    return bundle


def apply_workspace_design_to_export(project: dict) -> dict:
    """Packaging hook: use designed bytes; never rewrite manuscript."""
    data = dict(project.get("data") or {})
    if not is_ebook_workspace(data):
        return project
    require_quality_pass(data)
    bundle = render_designed_bundle(data)
    data = dict(data)
    pre = data.get("ebook_design_preflight") if isinstance(data.get("ebook_design_preflight"), dict) else {}
    if pre.get("status") != PREFLIGHT_PASS:
        raise ValueError(
            "Ebook design preflight blocked export: "
            + "; ".join(
                str(f.get("message") or f.get("code"))
                for f in (pre.get("findings") or [])[:8]
            )
            or "design preflight did not PASS"
        )
    reason = verify_export_bytes(
        data=data,
        pdf_bytes=bundle["pdf_bytes"],
        zip_bytes=bundle["zip_bytes"],
    )
    if reason:
        raise ValueError(f"Stale or tampered ebook export blocked: {reason}")
    project = dict(project)
    project["data"] = data
    project["_design_export_pdf"] = bundle["pdf_bytes"]
    project["_design_export_zip"] = bundle["zip_bytes"]
    return project


def theme_catalog_payload() -> dict[str, Any]:
    return {
        "themes": list_professional_themes(),
        "samples": {t["theme_id"]: theme_sample_html(t["theme_id"]) for t in list_professional_themes()},
        "paid_calls": False,
    }
