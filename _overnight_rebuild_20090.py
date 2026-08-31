"""Rebuild UNAPPROVED #20090 test PDF/ZIP from local recovery assets.

Does not call OpenAI/Tavily/Pexels. Does not rewrite the manuscript.
Does not approve, lock, mark Ready, or write the production database.
"""
from __future__ import annotations

import hashlib
import json
import os
import zipfile
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
os.chdir(ROOT)
os.environ.pop("FACTORY_TEST_MODE", None)
os.environ["OPENAI_API_KEY"] = ""
os.environ["TAVILY_API_KEY"] = ""
os.environ["PEXELS_API_KEY"] = ""
os.environ["AI_INTEGRATIONS_OPENAI_API_KEY"] = ""

from services.ebook_package import render_preview_html  # noqa: E402
from services.ebook_qa_validator import validate_ebook_pdf  # noqa: E402
from services.pdf_export import generate_product_pdf  # noqa: E402

OLD_ROOT = Path(
    r"C:\Users\user\OneDrive\Desktop\Factory_Stabilized_Source_V2_20260809"
    r"\Factory_Stabilized_V2\flask_app"
)
OUT = ROOT / "overnight_work" / "unapproved_20090"
PAGES = OUT / "pages"
OUT.mkdir(parents=True, exist_ok=True)
PAGES.mkdir(parents=True, exist_ok=True)

EXPECTED_MS = "f3aee3ff8dbb753f87be8f2487954876c49ab4f7b6414a0112d7e2a6342da075"
EXPECTED_COVER_SRC = "82eabce680e9f5d45ffba0b3ee6c170f40fe60470f06c5d2f9714ad73bafe56d"
PACKAGE_ID = "a76d99d229864ca9b326dd26e0bee9fa"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str | None:
    if not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _rewrite_paths(obj):
    old = str(OLD_ROOT)
    new = str(ROOT)
    if isinstance(obj, str):
        return obj.replace(old, new)
    if isinstance(obj, list):
        return [_rewrite_paths(x) for x in obj]
    if isinstance(obj, dict):
        return {k: _rewrite_paths(v) for k, v in obj.items()}
    return obj


def _load_project() -> dict:
    candidates = [
        ROOT / "overnight_recovery_20090_20260830" / "project_20090.json",
        OLD_ROOT / "overnight_recovery_20090_20260830" / "project_20090.json",
    ]
    for path in candidates:
        if path.is_file():
            raw = json.loads(path.read_text(encoding="utf-8"))
            return _rewrite_paths(raw)
    raise SystemExit("project_20090.json not found in recovery")


proj = _load_project()
data = dict(proj.get("data") or {})
fields = dict(data.get("fields") or {})
cover = dict(data.get("cover_design") or {})
visual_plan = data.get("visual_plan") if isinstance(data.get("visual_plan"), dict) else {}
package_id = str(data.get("package_id") or cover.get("package_id") or PACKAGE_ID)
title = str(data.get("title") or fields.get("ebook_title") or proj.get("name") or "")
subtitle = str(data.get("subtitle") or fields.get("subtitle") or cover.get("subtitle") or "")
author = str(
    data.get("author")
    or data.get("author_brand")
    or fields.get("author_brand")
    or cover.get("author")
    or "Lonnie Brown"
)
content = str(data.get("content") or data.get("ebook") or data.get("manuscript") or "")
summary = str(data.get("product_summary") or "")
ms_sha = hashlib.sha256(content.encode("utf-8")).hexdigest()
if ms_sha != EXPECTED_MS:
    raise SystemExit(f"Manuscript hash mismatch; refusing to continue. got={ms_sha}")

pkg_dir = ROOT / "exports" / package_id
if not pkg_dir.is_dir():
    alt = OLD_ROOT / "exports" / package_id
    if alt.is_dir():
        pkg_dir = alt

cover_png = None
for cand in (
    str(cover.get("image_path") or ""),
    str(pkg_dir / "img_cover.png"),
):
    p = Path(cand) if cand else None
    if p and p.is_file() and p.stat().st_size > 20_000:
        cover_png = p
        break
if cover_png is None:
    raise SystemExit("No local cover PNG found for #20090")

cover["image_path"] = str(cover_png)
cover["package_id"] = package_id
if not cover.get("author"):
    cover["author"] = author

src_jpg = pkg_dir / "cover_photo" / "sources" / f"{EXPECTED_COVER_SRC}.jpg"
if src_jpg.is_file():
    got = sha256_file(src_jpg)
    if got != EXPECTED_COVER_SRC:
        raise SystemExit(f"Cover source jpg hash mismatch: {got}")

preview_html = render_preview_html(
    title,
    subtitle,
    content,
    list((visual_plan or {}).get("chapters") or []),
    package_id,
    summary,
    cover,
    topic=str(fields.get("topic") or title),
)

pdf = generate_product_pdf(
    doc_html=preview_html,
    title=title,
    subtitle=subtitle,
    author=author,
    content=content,
    summary=summary,
    visual_plan=visual_plan,
    preview_source="visual",
    cover_design=cover,
    topic=str(fields.get("topic") or title),
)
qa = validate_ebook_pdf(pdf)

pdf_path = OUT / "ebook.pdf"
pdf_path.write_bytes(pdf)
html_path = OUT / "ebook.html"
html_path.write_text(preview_html, encoding="utf-8")
txt_path = OUT / "ebook.txt"
txt_path.write_text(content, encoding="utf-8")
sum_path = OUT / "product_summary.txt"
sum_path.write_text(summary or "", encoding="utf-8")

zip_path = OUT / "package.zip"
with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
    zf.write(pdf_path, "ebook.pdf")
    zf.write(html_path, "ebook.html")
    zf.write(txt_path, "ebook.txt")
    zf.write(sum_path, "product_summary.txt")

import fitz
from PIL import Image, ImageDraw

doc = fitz.open(stream=pdf, filetype="pdf")
page_count = doc.page_count
page_records = []
fonts_all: Counter[str] = Counter()
img_inventory = []
seen_img = {}

for i in range(page_count):
    page = doc.load_page(i)
    text = page.get_text("text") or ""
    pix = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5), alpha=False)
    png_path = PAGES / f"page_{i + 1:02d}.png"
    pix.save(str(png_path))
    d = page.get_text("dict")
    sizes = []
    page_fonts: Counter[str] = Counter()
    for block in d.get("blocks") or []:
        for line in block.get("lines") or []:
            for span in line.get("spans") or []:
                page_fonts[str(span.get("font") or "?")] += 1
                fonts_all[str(span.get("font") or "?")] += 1
                sizes.append(round(float(span.get("size") or 0), 1))
    images = []
    for im in page.get_images(full=True):
        xref = im[0]
        try:
            info = doc.extract_image(xref)
            blob = info.get("image") or b""
            digest = sha256_bytes(blob)
            rec = {
                "xref": xref,
                "width": info.get("width"),
                "height": info.get("height"),
                "ext": info.get("ext"),
                "bytes": len(blob),
                "sha256": digest,
            }
            images.append(rec)
            seen_img.setdefault(digest, {"pages": [], **rec})
            seen_img[digest]["pages"].append(i + 1)
        except Exception as exc:
            images.append({"xref": xref, "error": str(exc)})
    corners = [
        pix.pixel(x, y)[:3]
        for x, y in (
            (0, 0),
            (pix.width - 1, 0),
            (0, pix.height - 1),
            (pix.width - 1, pix.height - 1),
        )
    ]
    page_records.append(
        {
            "page": i + 1,
            "chars": len(text.strip()),
            "preview": text.strip()[:400],
            "fonts": dict(page_fonts),
            "sizes": sorted(set(sizes)),
            "images": images,
            "png": str(png_path),
            "corner_rgb": corners,
            "has_markdown_link": "](#" in text or "](http" in text,
        }
    )

cover_pix = doc.load_page(0).get_pixmap(matrix=fitz.Matrix(0.45, 0.45), alpha=False)
cover_pix.save(str(OUT / "cover_thumbnail.png"))
doc.close()

thumbs = []
for rec in page_records:
    im = Image.open(rec["png"]).convert("RGB")
    im.thumbnail((180, 233))
    labeled = Image.new("RGB", (im.width, im.height + 18), (255, 255, 255))
    labeled.paste(im, (0, 0))
    draw = ImageDraw.Draw(labeled)
    draw.text((4, im.height + 2), f"p{rec['page']}", fill=(30, 30, 30))
    thumbs.append(labeled)
cols = 6
rows = (len(thumbs) + cols - 1) // cols
cell_w = max(t.width for t in thumbs) if thumbs else 180
cell_h = max(t.height for t in thumbs) if thumbs else 251
sheet = Image.new("RGB", (cols * cell_w + 16, rows * cell_h + 16), (245, 245, 245))
for idx, t in enumerate(thumbs):
    r, c = divmod(idx, cols)
    sheet.paste(t, (8 + c * cell_w, 8 + r * cell_h))
sheet_path = OUT / "contact_sheet.png"
sheet.save(sheet_path, "PNG")

inventory = {
    "unique_images": [
        {
            "sha256": digest,
            "pages": v["pages"],
            "width": v.get("width"),
            "height": v.get("height"),
            "ext": v.get("ext"),
            "bytes": v.get("bytes"),
        }
        for digest, v in seen_img.items()
    ]
}
body_fonts = set()
for r in page_records[1:]:
    body_fonts.update(r["fonts"].keys())
helv = {"Helvetica", "Helvetica-Bold", "Helvetica-Oblique", "Helvetica-BoldOblique"}
sparse = [r["page"] for r in page_records if r["page"] > 1 and r["chars"] < 360 and not r["images"]]

report = {
    "at": datetime.now().isoformat(timespec="seconds"),
    "title": title,
    "subtitle": subtitle,
    "author": author,
    "package_id": package_id,
    "manuscript_sha256": ms_sha,
    "cover_png": str(cover_png),
    "cover_png_sha256": sha256_file(cover_png),
    "cover_source_sha256": EXPECTED_COVER_SRC,
    "pdf_path": str(pdf_path),
    "zip_path": str(zip_path),
    "contact_sheet": str(sheet_path),
    "pdf_sha256": sha256_bytes(pdf),
    "zip_sha256": sha256_file(zip_path),
    "pdf_bytes": len(pdf),
    "page_count": page_count,
    "qa_passed": bool(qa.passed),
    "qa_errors": list(qa.errors or []),
    "fonts": dict(fonts_all),
    "body_fonts": sorted(body_fonts),
    "helvetica_only_body": bool(body_fonts) and body_fonts <= helv,
    "sparse_pages": sparse,
    "db_written": False,
    "approved": False,
    "locked": False,
    "ready": False,
    "paid_calls": 0,
}
(OUT / "inspect_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
(OUT / "visual_inventory.json").write_text(json.dumps(inventory, indent=2), encoding="utf-8")

print("PDF", pdf_path, len(pdf), "pages", page_count, "sha", report["pdf_sha256"][:16])
print("QA passed", qa.passed, "errors", qa.errors)
print("fonts", dict(fonts_all))
print("sparse", sparse)
print("OUT", OUT)
if not qa.passed:
    raise SystemExit(2)
