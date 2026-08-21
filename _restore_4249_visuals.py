"""Restore stored #4249 visuals into the polished designed layout. No paid calls."""
from __future__ import annotations

import hashlib
import json
import os
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
os.chdir(ROOT)
os.environ["FACTORY_TEST_MODE"] = "1"

import database  # noqa: E402
from services.ebook_book_layout import (  # noqa: E402
    find_designed_chapter_pages,
    manuscript_text_fingerprint,
    numbered_chapters,
    render_designed_ebook_html,
)
from services.ebook_design_spec import EbookDesign  # noqa: E402
from services.ebook_project_workspace import manuscript_digest  # noqa: E402
from services.ebook_visual_pipeline import (  # noqa: E402
    merge_teaching_tables_into_plan,
    required_aids,
)
from services.pdf_export import (  # noqa: E402
    _apply_pdf_metadata,
    _html_to_pdf_xhtml2pdf,
    _prepend_pdf_bytes,
    _remove_accidental_blank_pages,
    _sanitize_pdf_local_link_uris,
)

OUT = ROOT / "exports" / "ebook_layout_polish_4249"
PKG = ROOT / "exports" / "ebook-ws-0f45e1eab3a0"
COVER_SHA = "465a3e10861cd056a98008a8131be157be9dc0d22ec93464fa831fcbb03367cd"


def _cover_pdf_bytes(data: dict) -> bytes:
    cover = data.get("cover_design") if isinstance(data.get("cover_design"), dict) else {}
    source = cover.get("source") if isinstance(cover.get("source"), dict) else {}
    assert source.get("sha256") == COVER_SHA, source.get("sha256")
    path = str(cover.get("local_cover_pdf") or "")
    if not path or not os.path.isfile(path):
        cand = PKG / "cover_local.pdf"
        path = str(cand) if cand.is_file() else ""
    if not path or not os.path.isfile(path):
        cand = PKG / "cover.pdf"
        path = str(cand) if cand.is_file() else ""
    assert path and os.path.isfile(path), "cover pdf missing"
    return Path(path).read_bytes()


def main() -> None:
    project = database.get_project(4249)
    assert project, "project 4249 missing from OneDrive Factory DB"
    data = dict(project.get("data") or {})
    md = str(data.get("content") or data.get("ebook") or "")
    before_fp = manuscript_text_fingerprint(md)
    before_digest = manuscript_digest(data)
    cover = data.get("cover_design") if isinstance(data.get("cover_design"), dict) else {}
    source = cover.get("source") if isinstance(cover.get("source"), dict) else {}
    cover_pdf = _cover_pdf_bytes(data)

    plan = merge_teaching_tables_into_plan(
        data.get("visual_plan") if isinstance(data.get("visual_plan"), dict) else {"chapters": []}
    )
    restored_ids = []
    added_ids = []
    for ch in plan.get("chapters") or []:
        for aid in ch.get("aids") or []:
            if not isinstance(aid, dict):
                continue
            vid = str(aid.get("visual_id") or "")
            if aid.get("html"):
                added_ids.append(vid)
            elif aid.get("asset_path") and os.path.isfile(str(aid.get("asset_path"))):
                restored_ids.append(vid)

    design = EbookDesign.from_dict(data.get("ebook_design") if isinstance(data.get("ebook_design"), dict) else {})
    title = str(data.get("title") or "From First Booking to On-Site Prints")
    subtitle = str(data.get("subtitle") or "")
    author = str(data.get("author_brand") or data.get("author") or "Lonnie Brown")
    audience = str(data.get("audience") or "")

    def _render(toc=None) -> str:
        return render_designed_ebook_html(
            title=title,
            subtitle=subtitle,
            author=author,
            manuscript_md=md,
            design=design,
            audience=audience,
            visual_plan=plan,
            toc_page_numbers=toc,
        )

    def _merge(html: str) -> bytes:
        interior = _remove_accidental_blank_pages(_html_to_pdf_xhtml2pdf(html))
        return _sanitize_pdf_local_link_uris(
            _remove_accidental_blank_pages(_prepend_pdf_bytes(cover_pdf, interior))
        )

    html = _render()
    pdf = _merge(html)
    titles = [t for t, _ in numbered_chapters(md)]
    pages = find_designed_chapter_pages(pdf, titles)
    if pages:
        html = _render(pages)
        pdf = _merge(html)
    pdf = _apply_pdf_metadata(pdf, title=title, author=author, subject=subtitle or title)

    assert manuscript_text_fingerprint(str(data.get("content") or "")) == before_fp
    assert manuscript_digest(data) == before_digest
    assert source.get("sha256") == COVER_SHA
    assert html.lower().count("<figure") >= 10
    assert html.lower().count("<img") >= 10

    zbuf_files = {
        "ebook.pdf": pdf,
        "ebook.html": html.encode("utf-8"),
        "visual_plan.json": json.dumps(plan, indent=2, ensure_ascii=False).encode("utf-8"),
    }
    for aid in required_aids(plan):
        path = str(aid.get("asset_path") or "")
        vid = str(aid.get("visual_id") or "visual")
        if path and os.path.isfile(path):
            zbuf_files[f"visuals/{vid}.png"] = Path(path).read_bytes()

    zip_bytes = None
    import io

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name, blob in zbuf_files.items():
            zf.writestr(name, blob)
    zip_bytes = buf.getvalue()

    for dest in (OUT, PKG):
        dest.mkdir(parents=True, exist_ok=True)
        (dest / "ebook.html").write_text(html, encoding="utf-8")
        (dest / "ebook.pdf").write_bytes(pdf)
        (dest / "package.zip").write_bytes(zip_bytes)

    # Preview HTML for workspace review. Do not rewrite manuscript or cover. Do not approve.
    data["ebook_preview_html"] = html
    data["preview_html"] = html
    data["pdf_path"] = str(PKG / "ebook.pdf")
    data["zip_path"] = str(PKG / "package.zip")
    exports = dict(data.get("exports") or {}) if isinstance(data.get("exports"), dict) else {}
    exports["package_id"] = str(data.get("package_id") or "ebook-ws-0f45e1eab3a0")
    exports["pdf_available"] = True
    exports["files"] = {
        "pdf": {"name": "ebook.pdf", "url": "/download/ebook-ws-0f45e1eab3a0/ebook.pdf"},
        "zip": {"name": "package.zip", "url": "/download/ebook-ws-0f45e1eab3a0/package.zip"},
        "html": {"name": "ebook.html", "url": "/download/ebook-ws-0f45e1eab3a0/ebook.html"},
    }
    data["exports"] = exports
    data["product_exports"] = {
        "package_id": exports["package_id"],
        "folder": str(PKG),
        "pdf_available": True,
        "files": exports["files"],
    }
    data["export_files"] = {
        "ebook.pdf": str(PKG / "ebook.pdf"),
        "package.zip": str(PKG / "package.zip"),
    }
    database.update_project(4249, None, data, user_confirmed_save=True)

    import fitz

    doc = fitz.open(stream=pdf, filetype="pdf")
    print("pdf_path", PKG / "ebook.pdf")
    print("polish_pdf_path", OUT / "ebook.pdf")
    print("zip_path", PKG / "package.zip")
    print("page_count", doc.page_count)
    total_imgs = 0
    pages_with = 0
    per_ch = {i: 0 for i in range(1, 11)}
    for i, page in enumerate(doc, 1):
        n = len(page.get_images())
        total_imgs += n
        if n:
            pages_with += 1
        text = page.get_text("text") or ""
        for ci in range(1, 11):
            if f"Chapter {ci}" in text:
                per_ch[ci] += n
        if n and i <= 8:
            print(f"page {i} images={n} {text[:70].replace(chr(10), ' ')}")
    print("total_images", total_imgs, "pages_with_images", pages_with)
    print("images_near_chapter_openers", per_ch)
    corpus = "\n".join(doc.load_page(i).get_text("text") or "" for i in range(doc.page_count))
    for needle in ("Chapter 1What", "ContentsWhat This Business", "[ ] Confirm"):
        print(f"jam {needle!r}", needle in corpus)
    doc.close()
    print("html_figures", html.lower().count("<figure"), "html_img", html.lower().count("<img"))
    print("restored_png_ids", restored_ids)
    print("added_table_ids", added_ids)
    print("cover_sha", source.get("sha256"))
    print("manuscript_digest", before_digest)
    print("manuscript_unchanged", manuscript_digest(database.get_project(4249)["data"]) == before_digest)
    print("cover_sha_unchanged", ((database.get_project(4249)["data"].get("cover_design") or {}).get("source") or {}).get("sha256") == COVER_SHA)


if __name__ == "__main__":
    main()
