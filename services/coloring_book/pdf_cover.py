"""Coloring Book cover merge helpers — reuse layout overlay, no AI calls."""
from __future__ import annotations

import io
import os
import zipfile

from pypdf import PdfReader, PdfWriter
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from services.coloring_book.renderer import ColoringBookLayoutInfo, draw_cover_page_on_canvas

EXPORTS_DIR = os.environ.get(
    "FLASK_EXPORTS_DIR",
    os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "exports"),
)


def render_cover_page_pdf_bytes(cover_design: dict) -> bytes:
    from services.coloring_book.prompt_engine import normalize_coloring_cover_design

    buf = io.BytesIO()
    pdf = canvas.Canvas(buf, pagesize=letter)
    layout = ColoringBookLayoutInfo()
    cover_design = normalize_coloring_cover_design(
        cover_design,
        author=str((cover_design or {}).get("author") or ""),
    )
    img = str(cover_design.get("local_image_path") or "")
    if not img:
        # Prefer shared editor asset when package_id is present
        pkg = str(cover_design.get("package_id") or "")
        if pkg:
            from services.cover_agent import _cover_image_path, _has_cover_image

            if _has_cover_image(pkg):
                img = _cover_image_path(pkg)
                cover_design["local_image_path"] = img
    draw_cover_page_on_canvas(
        pdf,
        cover_image_path=img,
        title=str(cover_design.get("title") or ""),
        subtitle=str(cover_design.get("subtitle") or ""),
        badge=str(cover_design.get("badge") or ""),
        cover_design=cover_design,
    )
    layout.cover_page_count = 1
    pdf.showPage()
    pdf.save()
    return buf.getvalue()


def merge_cover_into_coloring_book_pdf(
    pdf_bytes: bytes,
    cover_design: dict,
    *,
    replace_first_page: bool = False,
) -> bytes:
    if not pdf_bytes.startswith(b"%PDF"):
        raise ValueError("Existing Coloring Book PDF is invalid.")

    cover_bytes = render_cover_page_pdf_bytes(cover_design)
    source = PdfReader(io.BytesIO(pdf_bytes))
    cover_reader = PdfReader(io.BytesIO(cover_bytes))
    writer = PdfWriter()
    writer.add_page(cover_reader.pages[0])

    start_index = 1 if replace_first_page and len(source.pages) > 0 else 0
    for page in source.pages[start_index:]:
        writer.add_page(page)

    out = io.BytesIO()
    writer.write(out)
    merged = out.getvalue()
    if not merged.startswith(b"%PDF"):
        raise RuntimeError("Coloring Book cover merge produced invalid PDF output.")
    return merged


def write_coloring_cover_preview_png(pdf_bytes: bytes, package_id: str) -> str:
    """Rasterize PDF page 1 to cover_page_preview.png. No image-gen."""
    pkg = str(package_id or "").strip()
    if not pkg or not pdf_bytes.startswith(b"%PDF"):
        return ""
    try:
        import fitz
    except Exception:  # noqa: BLE001
        return ""
    out_dir = os.path.join(EXPORTS_DIR, pkg)
    os.makedirs(out_dir, exist_ok=True)
    preview_path = os.path.join(out_dir, "cover_page_preview.png")
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        if len(doc) < 1:
            doc.close()
            return ""
        pix = doc[0].get_pixmap(matrix=fitz.Matrix(1.8, 1.8), alpha=False)
        png_bytes = pix.tobytes("png")
        doc.close()
        with open(preview_path, "wb") as fh:
            fh.write(png_bytes)
        return preview_path
    except Exception:  # noqa: BLE001
        return ""


def _replace_zip_pdf_member(zip_path: str, pdf_bytes: bytes) -> None:
    if not zip_path or not os.path.isfile(zip_path) or not pdf_bytes.startswith(b"%PDF"):
        return
    tmp_path = zip_path + ".author_overlay.tmp"
    with zipfile.ZipFile(zip_path, "r") as src:
        names = src.namelist()
        pdf_names = [n for n in names if n.lower().endswith(".pdf")]
        if not pdf_names:
            return
        target = pdf_names[0]
        with zipfile.ZipFile(tmp_path, "w") as dst:
            for name in names:
                if name == target:
                    dst.writestr(name, pdf_bytes)
                else:
                    dst.writestr(name, src.read(name))
    os.replace(tmp_path, zip_path)


def apply_author_overlay_to_existing_coloring_book(data: dict) -> dict:
    """Persist author and overlay it on the existing cover/PDF. No interior regen."""
    from services.coloring_book.prompt_engine import (
        coloring_cover_draws_author,
        normalize_coloring_cover_design,
        stamp_coloring_author_fields,
    )

    data = dict(data or {})
    if str(data.get("product_type") or "").strip().lower() != "coloring_book":
        return data

    fields = data.get("fields") if isinstance(data.get("fields"), dict) else {}
    cover = dict(data.get("cover_design") or {}) if isinstance(data.get("cover_design"), dict) else {}
    author = stamp_coloring_author_fields(data).get("author") or ""
    theme = str(fields.get("theme") or data.get("theme") or cover.get("theme") or "")
    cover = normalize_coloring_cover_design(
        cover,
        theme=theme,
        product_title=str(cover.get("title") or data.get("title") or ""),
        subtitle=str(cover.get("subtitle") or data.get("subtitle") or ""),
        author=author,
    )
    data = stamp_coloring_author_fields(data, author, overlay_style=str(cover.get("overlay_style") or ""))
    data["cover_design"] = cover
    if not coloring_cover_draws_author(str(cover.get("overlay_style") or "")):
        return data

    pkg = str(cover.get("package_id") or data.get("package_id") or "").strip()
    pkg_dir = os.path.join(EXPORTS_DIR, pkg) if pkg else ""
    if pkg_dir and not cover.get("local_image_path"):
        for name in ("img_cover.png", "cover.png"):
            candidate = os.path.join(pkg_dir, name)
            if os.path.isfile(candidate):
                cover["local_image_path"] = candidate
                break
        data["cover_design"] = cover

    interior_paths = _existing_interior_image_paths(pkg_dir, data)
    if interior_paths:
        merged = _rebuild_pdf_from_existing_images(data, cover, interior_paths)
    else:
        pdf_bytes = _load_existing_pdf_bytes(data, pkg_dir)
        if not pdf_bytes.startswith(b"%PDF"):
            return data
        had_cover = bool(data.get("pdf_has_cover_page", True))
        merged = merge_cover_into_coloring_book_pdf(
            pdf_bytes, cover, replace_first_page=had_cover
        )
    if pkg_dir:
        os.makedirs(pkg_dir, exist_ok=True)
        pdf_name = str(data.get("filename") or "coloring_book.pdf").strip() or "coloring_book.pdf"
        pdf_path = os.path.join(pkg_dir, pdf_name)
        with open(pdf_path, "wb") as fh:
            fh.write(merged)
        write_coloring_cover_preview_png(merged, pkg)
        _replace_zip_pdf_member(os.path.join(pkg_dir, "package.zip"), merged)
    data["pdf_has_cover_page"] = True
    data["cover_design"] = cover
    return data


def _existing_interior_image_paths(pkg_dir: str, data: dict) -> list[tuple[int, str, str]]:
    """Return (page_number, path, topic) for on-disk coloring_pNN.png files."""
    if not pkg_dir or not os.path.isdir(pkg_dir):
        return []
    found: dict[int, str] = {}
    for name in os.listdir(pkg_dir):
        low = name.lower()
        if not low.startswith("coloring_p") or not low.endswith(".png"):
            continue
        if "_print_" in low or "_original" in low:
            continue
        digits = "".join(ch for ch in name[len("coloring_p") :] if ch.isdigit())
        if not digits:
            continue
        found[int(digits)] = os.path.join(pkg_dir, name)
    if not found:
        return []
    pages_meta = data.get("pages") if isinstance(data.get("pages"), list) else []
    topics = {}
    for i, page in enumerate(pages_meta):
        if not isinstance(page, dict):
            continue
        try:
            n = int(page.get("page_number") or i + 1)
        except (TypeError, ValueError):
            n = i + 1
        topics[n] = str(page.get("topic") or f"Page {n}")
    return [
        (n, found[n], topics.get(n, f"Page {n}"))
        for n in sorted(found)
        if os.path.isfile(found[n])
    ]


def _load_existing_pdf_bytes(data: dict, pkg_dir: str) -> bytes:
    pdf_bytes = b""
    raw_b64 = data.get("pdf_bytes")
    if raw_b64:
        try:
            import base64

            pdf_bytes = base64.b64decode(raw_b64)
        except Exception:  # noqa: BLE001
            pdf_bytes = b""
    if pdf_bytes.startswith(b"%PDF"):
        return pdf_bytes
    if not pkg_dir or not os.path.isdir(pkg_dir):
        return b""
    preferred = str(data.get("filename") or "").strip()
    candidates = []
    if preferred:
        candidates.append(os.path.join(pkg_dir, preferred))
    try:
        for name in sorted(os.listdir(pkg_dir)):
            if name.lower().endswith(".pdf"):
                candidates.append(os.path.join(pkg_dir, name))
    except OSError:
        pass
    for cand in candidates:
        if cand and os.path.isfile(cand):
            try:
                with open(cand, "rb") as fh:
                    pdf_bytes = fh.read()
                if pdf_bytes.startswith(b"%PDF"):
                    if not data.get("filename"):
                        data["filename"] = os.path.basename(cand)
                    return pdf_bytes
            except OSError:
                continue
    return b""


def _rebuild_pdf_from_existing_images(
    data: dict, cover: dict, interior_paths: list[tuple[int, str, str]]
) -> bytes:
    """Cover overlay + existing interior PNGs. No paid image generation."""
    from types import SimpleNamespace

    from services.coloring_book.prompt_engine import pdf_metadata_for_theme
    from services.coloring_book.renderer import build_coloring_book_pdf_bytes

    pages = []
    for n, path, topic in interior_paths:
        pages.append(
            SimpleNamespace(
                page_number=n,
                topic=topic,
                line_art_prompt="",
                caption="",
                image_path=path,
            )
        )
    book = SimpleNamespace(
        product_title=str(cover.get("title") or data.get("title") or "Coloring Book"),
        subtitle=str(cover.get("subtitle") or data.get("subtitle") or ""),
        pages=pages,
        cover_prompt=str(cover.get("cover_prompt") or data.get("cover_prompt") or ""),
    )
    meta = pdf_metadata_for_theme(
        str(cover.get("theme") or (data.get("fields") or {}).get("theme") or ""),
        product_title=book.product_title,
        author=str(cover.get("author") or data.get("author") or ""),
    )
    pdf_bytes, _layout = build_coloring_book_pdf_bytes(
        book,
        cover_image_path=str(cover.get("local_image_path") or ""),
        cover_design=cover,
        pdf_metadata=meta,
    )
    return pdf_bytes
