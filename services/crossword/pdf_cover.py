"""Merge shared cover artwork into Crossword PDFs — separate from Word Search."""
from __future__ import annotations

import io
import os

from pypdf import PdfReader, PdfWriter

from services.crossword.direct_pdf_renderer import build_single_crossword_pdf_bytes


def ensure_crossword_cover_png(
    cover_design: dict,
    package_id: str = "",
    *,
    force: bool = False,
) -> str:
    """Rasterize the local Crossword cover page to exports/<pkg>/img_cover.png.

    Zero paid APIs. Returns the PNG path when written, else "".
    Preserves a user-uploaded PNG unless force=True.
    """
    from services.ebook_package import EXPORTS_DIR

    pkg = str(package_id or (cover_design or {}).get("package_id") or "").strip()
    if not pkg:
        return ""
    out_dir = os.path.join(EXPORTS_DIR, pkg)
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "img_cover.png")
    keep_upload = bool((cover_design or {}).get("user_uploaded_cover")) and not force
    if (
        keep_upload
        and os.path.isfile(out_path)
        and os.path.getsize(out_path) > 5_000
    ):
        if cover_design is not None:
            cover_design["image_path"] = out_path
            cover_design["local_image_path"] = out_path
            cover_design["has_cover_image"] = True
            cover_design["cover_asset"] = "img_cover.png"
            cover_design["cover_asset_url"] = f"/download/{pkg}/img_cover.png"
        return out_path
    try:
        pdf_bytes = render_cover_page_pdf_bytes(cover_design or {})
        import fitz

        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        pix = doc[0].get_pixmap(matrix=fitz.Matrix(2.0, 2.0), alpha=False)
        pix.save(out_path)
        doc.close()
    except Exception:
        return ""
    if not (os.path.isfile(out_path) and os.path.getsize(out_path) > 100):
        return ""
    if cover_design is not None:
        cover_design["image_path"] = out_path
        cover_design["local_image_path"] = out_path
        cover_design["has_cover_image"] = True
        cover_design["cover_asset"] = "img_cover.png"
        cover_design["cover_asset_url"] = f"/download/{pkg}/img_cover.png"
    return out_path


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

    # Preserve document metadata (especially /Subject with puzzle count).
    # Losing Subject makes crossword_full_book_pdf_is_valid fail and Export
    # silently rebuilds a new puzzle book — which must never happen on cover apply.
    try:
        if source.metadata:
            meta = {
                str(k): str(v)
                for k, v in dict(source.metadata).items()
                if v is not None
            }
            # Prefer cover title/subtitle when present.
            title = str((cover_design or {}).get("title") or "").strip()
            subtitle = str((cover_design or {}).get("subtitle") or "").strip()
            if title:
                meta["/Title"] = title
            if subtitle:
                meta["/Subject"] = subtitle
            elif "/Subject" not in meta and meta.get("/subject"):
                meta["/Subject"] = meta["/subject"]
            writer.add_metadata(meta)
    except Exception:
        pass

    out = io.BytesIO()
    writer.write(out)
    merged = out.getvalue()
    if not merged.startswith(b"%PDF"):
        raise RuntimeError("Crossword cover merge produced invalid PDF output.")
    return merged
