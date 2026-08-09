"""Coloring Book cover merge helpers — reuse layout overlay, no AI calls."""
from __future__ import annotations

import io

from pypdf import PdfReader, PdfWriter
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from services.coloring_book.renderer import ColoringBookLayoutInfo, draw_cover_page_on_canvas


def render_cover_page_pdf_bytes(cover_design: dict) -> bytes:
    buf = io.BytesIO()
    pdf = canvas.Canvas(buf, pagesize=letter)
    layout = ColoringBookLayoutInfo()
    img = str(cover_design.get("local_image_path") or "")
    if not img:
        # Prefer shared editor asset when package_id is present
        pkg = str(cover_design.get("package_id") or "")
        if pkg:
            import os

            from services.cover_agent import _cover_image_path, _has_cover_image

            if _has_cover_image(pkg):
                img = _cover_image_path(pkg)
    draw_cover_page_on_canvas(
        pdf,
        cover_image_path=img,
        title=str(cover_design.get("title") or ""),
        subtitle=str(cover_design.get("subtitle") or ""),
        badge=str(cover_design.get("badge") or "Jumbo Coloring & Activity Book"),
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
