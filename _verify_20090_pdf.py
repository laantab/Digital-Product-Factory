"""Inspect 20090 PDF/ZIP for contamination and render a contact sheet."""
from __future__ import annotations

import hashlib
import io
import json
import os
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
os.chdir(ROOT)
import database  # noqa: E402

from PIL import Image, ImageDraw, ImageFont

TARGET = 20090
OUT = ROOT / "test-results"
OUT.mkdir(exist_ok=True)


def main() -> int:
    proj = database.get_project(TARGET)
    data = proj.get("data") or {}
    pdf_path = Path(str(data.get("pdf_path") or data.get("_pdf_path") or ""))
    files = data.get("export_files") or {}
    zip_path = Path(str(files.get("package.zip") or ""))
    report = {
        "pdf_exists": pdf_path.is_file(),
        "pdf_size": pdf_path.stat().st_size if pdf_path.is_file() else 0,
        "zip_exists": zip_path.is_file(),
        "zip_size": zip_path.stat().st_size if zip_path.is_file() else 0,
        "package_id": data.get("package_id"),
        "ebook_ready": data.get("ebook_ready"),
        "user_saved": proj.get("user_saved"),
        "type": proj.get("type"),
    }
    text = ""
    page_count = 0
    if pdf_path.is_file():
        import fitz

        doc = fitz.open(pdf_path)
        page_count = doc.page_count
        pages = []
        thumbs = []
        for i, page in enumerate(doc):
            page_text = page.get_text("text") or ""
            text += page_text + "\n"
            pix = page.get_pixmap(matrix=fitz.Matrix(1.2, 1.2), alpha=False)
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            pages.append(img)
            thumbs.append(img.copy())
        report["page_count"] = page_count
        report["has_127"] = "127.0.0.1" in text
        report["has_localhost"] = "localhost" in text.lower()
        report["has_retry"] = "retry missing image" in text.lower()
        report["has_factory"] = "digital product factory" in text.lower()
        report["has_pexels_api"] = "api.pexels.com" in text.lower()
        links = []
        for page in doc:
            for link in page.get_links() or []:
                uri = str(link.get("uri") or "")
                if uri:
                    links.append(uri)
        report["link_uris"] = links[:20]
        report["leaking_links"] = [u for u in links if "127.0.0.1" in u or "localhost" in u.lower()]
        # contact sheet: cover, thumb, toc-ish pages, chapter opens, last
        picks = []
        if pages:
            picks.append(("cover", pages[0]))
            cover_thumb = pages[0].copy()
            cover_thumb.thumbnail((220, 320))
            picks.append(("cover_thumb", cover_thumb))
        for idx in range(1, min(len(pages), 12)):
            picks.append((f"page_{idx+1}", pages[idx]))
        if len(pages) > 12:
            picks.append(("final", pages[-1]))
        cols = 4
        cell_w, cell_h = 280, 380
        rows = (len(picks) + cols - 1) // cols
        sheet = Image.new("RGB", (cols * cell_w + 40, rows * cell_h + 60), (248, 248, 246))
        draw = ImageDraw.Draw(sheet)
        draw.text((16, 12), "Project #20090 contact sheet — Beginner's Guide to Container Gardening", fill=(20, 20, 20))
        for n, (label, img) in enumerate(picks):
            r, c = divmod(n, cols)
            x, y = 20 + c * cell_w, 40 + r * cell_h
            thumb = img.copy()
            thumb.thumbnail((cell_w - 24, cell_h - 40))
            sheet.paste(thumb, (x + (cell_w - 24 - thumb.width) // 2, y))
            draw.text((x, y + cell_h - 28), label, fill=(40, 40, 40))
        sheet_path = OUT / "ebook_20090_contact_sheet.png"
        sheet.save(sheet_path)
        report["contact_sheet"] = str(sheet_path)
        # also dump first 8 pages as images
        page_dir = OUT / "ebook_20090_pages"
        page_dir.mkdir(exist_ok=True)
        for i, img in enumerate(pages[:16]):
            img.save(page_dir / f"page_{i+1:02d}.png")
        report["page_dir"] = str(page_dir)
        pdf_sha = hashlib.sha256(pdf_path.read_bytes()).hexdigest()
        report["pdf_sha"] = pdf_sha
        if zip_path.is_file():
            with zipfile.ZipFile(zip_path) as zf:
                names = zf.namelist()
                report["zip_names"] = names
                if "ebook.pdf" in names:
                    zpdf = zf.read("ebook.pdf")
                    report["zip_pdf_sha"] = hashlib.sha256(zpdf).hexdigest()
                    report["zip_matches_pdf"] = report["zip_pdf_sha"] == pdf_sha
        doc.close()
    (OUT / "ebook_20090_verify.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({k: report[k] for k in report if k not in {"link_uris"}}, indent=2))
    return 0 if report.get("pdf_exists") and not report.get("has_127") and not report.get("leaking_links") else 1


if __name__ == "__main__":
    raise SystemExit(main())
