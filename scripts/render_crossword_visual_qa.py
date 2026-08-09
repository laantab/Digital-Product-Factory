"""Generate Gold Rush book, render pages, contact sheet, copy authority PDF."""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

import fitz
from PIL import Image, ImageDraw
from pypdf import PdfReader

from services.crossword.book import build_crossword_puzzles
from services.crossword.direct_pdf_renderer import build_crossword_book_pdf_bytes


def main() -> int:
    out = Path(os.environ.get("TEMP", ".")) / "crossword_visual_final"
    pages = out / "pages"
    pages.mkdir(parents=True, exist_ok=True)

    puzzles, _w, errors = build_crossword_puzzles(
        mode="topic",
        product_title="California Gold Rush Days",
        theme="California Gold Rush Days",
        difficulty="easy",
        grid_size=15,
        number_of_puzzles=12,
        words_per_puzzle=8,
        output_type="book",
        use_ai_words=False,
        seed=21,
    )
    if errors or len(puzzles) != 12:
        raise SystemExit(f"puzzle build failed: {errors}")

    pdf, layout = build_crossword_book_pdf_bytes(
        puzzles,
        product_title="California Gold Rush Days",
        subtitle="12 Crossword Puzzles - Easy Level",
        include_answer_key=True,
        cover_design={
            "title": "California Gold Rush Days",
            "subtitle": "12 Crossword Puzzles - Easy Level",
            "topic": "California Gold Rush Days",
            "audience": "Adults",
            "difficulty": "Easy",
            "use_ai_image": False,
        },
    )
    if layout.page_count != 25:
        raise SystemExit(f"expected 25 pages, got {layout.page_count}")

    pdf_path = out / "california_gold_rush_days.pdf"
    pdf_path.write_bytes(pdf)

    doc = fitz.open(stream=pdf, filetype="pdf")
    thumbs: list[Image.Image] = []
    for i in range(doc.page_count):
        pix = doc.load_page(i).get_pixmap(matrix=fitz.Matrix(1.55, 1.55), alpha=False)
        dest = pages / f"page_{i + 1:02d}.png"
        pix.save(str(dest))
        thumbs.append(Image.open(dest).convert("RGB"))

    cols, rows = 5, 5
    tw, th = 220, 286
    sheet = Image.new("RGB", (cols * tw + 20, rows * th + 40), (245, 241, 234))
    draw = ImageDraw.Draw(sheet)
    for idx, im in enumerate(thumbs):
        r, c = divmod(idx, cols)
        im2 = im.copy()
        im2.thumbnail((tw - 8, th - 24))
        x = 10 + c * tw + (tw - im2.width) // 2
        y = 30 + r * th
        sheet.paste(im2, (x, y))
        draw.text((10 + c * tw + 8, y + im2.height + 2), f"p{idx + 1}", fill=(60, 60, 60))
    contact = out / "contact_sheet_25.png"
    sheet.save(contact)

    meta = PdfReader(str(pdf_path))
    workspace = Path(__file__).resolve().parents[1] / "california_gold_rush_days.pdf"
    downloads = Path.home() / "Downloads" / "california_gold_rush_days.pdf"
    shutil.copy2(pdf_path, workspace)
    shutil.copy2(pdf_path, downloads)

    print("pages", len(meta.pages))
    print("subject", meta.metadata.subject if meta.metadata else None)
    print("size", pdf_path.stat().st_size)
    print("contact", contact)
    print("downloads", downloads)
    print("workspace", workspace)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
