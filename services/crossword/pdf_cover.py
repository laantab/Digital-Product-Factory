"""Merge shared cover artwork into Crossword PDFs — separate from Word Search."""
from __future__ import annotations

import io

from pypdf import PdfReader, PdfWriter

from services.crossword.direct_pdf_renderer import build_single_crossword_pdf_bytes


def render_cover_page_pdf_bytes(cover_design: dict) -> bytes:
    from services.crossword.direct_pdf_renderer import CrosswordPdfLayoutInfo, _draw_cover_page_from_design
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter)
    layout = CrosswordPdfLayoutInfo()
    _draw_cover_page_from_design(pdf, cover_design, layout)
    pdf.save()
    data = buffer.getvalue()
    if not data:
        raise RuntimeError("Crossword cover page render produced empty PDF output.")
    return data


def merge_cover_into_crossword_pdf(
    pdf_bytes: bytes,
    cover_design: dict,
    *,
    replace_first_page: bool = False,
) -> bytes:
    if not pdf_bytes.startswith(b"%PDF"):
        raise ValueError("Existing Crossword PDF is invalid.")

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
        raise RuntimeError("Crossword cover merge produced invalid PDF output.")
    return merged
