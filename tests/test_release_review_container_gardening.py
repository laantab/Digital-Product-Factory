"""v1.9.11 -- the Editor-in-Chief release review blocks Container Gardening's defects.

Each case builds a real PDF and ZIP (PyMuPDF, zero cost, no provider calls)
the way the Factory prints a book: cover, linked contents page, one chapter
per page with its visual at a measured printed width and an 8+ pt caption.
Each defect must be refused, and the corrected book must pass that check.
"""
from __future__ import annotations

import io
import os
import random
import zipfile

os.environ["FACTORY_TEST_MODE"] = "1"

import fitz  # noqa: E402
import pytest  # noqa: E402
from PIL import Image, ImageDraw, ImageFilter  # noqa: E402

from services import ebook_release_review as rr  # noqa: E402
from services.ebook_visual_pipeline import render_aid_png  # noqa: E402

FONT = os.path.join(os.path.dirname(os.path.dirname(__file__)), "services", "fonts",
                    "LiberationSerif-Regular.ttf")

CH = ["What Container Gardening Is and Why It Works",
      "Choose the Right Containers for the Crops You Want",
      "Pick Beginner-Friendly Plants That Match Your Conditions",
      "Watering and Feeding Without Guesswork",
      "Keep Plants Productive Through the Season"]

CH5_AS_SHIPPED = ["**Sun exposure**", "**Season and temperature**", "**Climate pattern**",
                  "**Container depth and size**", "**What you actually eat**",
                  "**How many hours of sun does this spot get?**",
                  "**Is the current season cool or warm?**",
                  "**How deep and wide are my containers?**"]
CH5_CORRECTED = ["Sun exposure: how many hours of direct sun does this spot get?",
                 "Season and temperature: is it the cool or warm season right now?",
                 "Climate pattern: what does your local growing season allow?",
                 "Container depth and size: how deep and wide are your containers?",
                 "What you actually eat: which of these crops will you really use?"]
CH7_AS_SHIPPED = ["This helps replace the old shallow watering habit with deep watering.",
                  "It also helps flush out some built-up salts from fertilizers.",
                  "This kind of routine is not complicated, but it is dependable.",
                  "A good watering habit starts with your finger.",
                  "This shallow watering wets only the surface.",
                  "Instead, replace shallow watering with deep watering."]
CH7_CORRECTED = ["Check the mix with your finger before you water.",
                 "Replace shallow watering with deep watering.",
                 "Shallow watering wets only the top layer of the pot.",
                 "Deep watering also flushes out some built-up fertilizer salts.",
                 "A simple routine is easy to keep, and it is dependable."]


def _photo(seed: int, tint=(90, 140, 70), size=(1600, 1067)) -> Image.Image:
    rnd = random.Random(seed)
    w, h = size
    img = Image.new("RGB", (w, h), tint)
    d = ImageDraw.Draw(img)
    for _ in range(26):
        cx, cy, r = rnd.randint(0, w), rnd.randint(0, h), rnd.randint(60, 320)
        d.ellipse((cx - r, cy - r, cx + r, cy + r),
                  fill=(rnd.randint(20, 240), rnd.randint(20, 240), rnd.randint(20, 240)))
    return img.filter(ImageFilter.GaussianBlur(3))


def _png(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def _book(*, ch5=CH5_CORRECTED, ch7=CH7_CORRECTED, chart_width_pt=468.0, ch5_photo_repeats=False,
          small_photo=False, title="Grow Herbs and Greens in Small Pots"):
    """Build data, PDF bytes and ZIP bytes for a five-chapter test book."""
    import hashlib

    photos = {
        "v_ch1": _photo(1, (120, 90, 60)),
        "v_ch2": _photo(2, (60, 110, 140)),
        "v_ch5": _photo(5, (150, 70, 90)),
    }
    if ch5_photo_repeats:
        photos["v_ch5"] = photos["v_ch1"]
    if small_photo:
        photos["v_ch2"] = photos["v_ch2"].resize((400, 267))
    aids_by_ch = [
        [{"visual_id": "v_ch1", "type": "photo", "source": "pexels", "title": "Pots on a patio"}],
        [{"visual_id": "v_ch2", "type": "photo", "source": "pexels", "title": "Containers by size"}],
        [{"visual_id": "v_ch3", "type": "workflow", "title": "Pick Plants: five questions to ask",
          "items": list(ch5)}],
        [{"visual_id": "v_ch4", "type": "workflow", "title": "Watering and Feeding: key points",
          "items": list(ch7)}],
        [{"visual_id": "v_ch5", "type": "photo", "source": "pexels", "title": "Harvest basket"}],
    ]
    images: dict[str, bytes] = {}
    for idx, aids in enumerate(aids_by_ch, start=1):
        for aid in aids:
            aid["chapter"], aid["chapter_index"] = CH[idx - 1], idx
            if aid["type"] == "photo":
                images[aid["visual_id"]] = _png(photos[aid["visual_id"]])
                aid["sha256"] = hashlib.sha256(images[aid["visual_id"]]).hexdigest()
                aid["asset_path"] = f"/visuals/{aid['visual_id']}.png"
            else:
                images[aid["visual_id"]] = _png(render_aid_png(aid, scale=2.0).convert("RGB"))
    data = {"title": title, "ebook_design": {"theme_id": "studio_clean"},
            "content": "\n".join(f"# {t}\nChapter text for {t}." for t in CH),
            "visual_plan": {"chapters": [{"chapter": CH[i], "chapter_index": i + 1, "aids": aids_by_ch[i]}
                                         for i in range(5)]}}

    doc = fitz.open()
    cover = doc.new_page(width=612, height=792)
    cover.insert_image(cover.rect, stream=_png(_photo(99, (30, 40, 30), (1275, 1650))))
    toc = doc.new_page(width=612, height=792)
    toc.insert_font(fontname="LS", fontfile=FONT)
    toc.insert_text((72, 96), "Contents", fontname="LS", fontsize=20)
    for i, t in enumerate(CH):
        toc.insert_text((72, 140 + i * 24), f"{i + 1} {t}", fontname="LS", fontsize=11)
    for i, t in enumerate(CH):
        pg = doc.new_page(width=612, height=792)
        pg.insert_font(fontname="LS", fontfile=FONT)
        pg.insert_text((72, 96), f"Chapter {i + 1}", fontname="LS", fontsize=11)
        pg.insert_text((72, 124), t, fontname="LS", fontsize=16)
        aid = aids_by_ch[i][0]
        raw = images[aid["visual_id"]]
        im = Image.open(io.BytesIO(raw))
        w = chart_width_pt if aid["type"] != "photo" else 468.0
        h = w * im.height / im.width
        rect = fitz.Rect(72, 150, 72 + w, 150 + h)
        pg.insert_image(rect, stream=raw)
        pg.insert_text((72, 150 + h + 16), f"Figure for {t[:30]}", fontname="LS", fontsize=9)
    for i in range(len(CH)):
        doc[1].insert_link({"kind": fitz.LINK_GOTO, "page": i + 2,
                            "from": fitz.Rect(72, 128 + i * 24, 500, 144 + i * 24)})
    pdf = doc.tobytes()
    zbuf = io.BytesIO()
    with zipfile.ZipFile(zbuf, "w") as z:
        z.writestr("ebook.pdf", pdf)
        for vid, raw in images.items():
            z.writestr(f"visuals/{vid}.png", raw)
    return data, pdf, zbuf.getvalue()


def _codes(rev):
    return {f.code for f in rev.findings}


def _no_ai(req):
    return []


# ---------------------------------------------------------------- the good book
def test_a_corrected_book_is_ready_for_approval():
    data, pdf, z = _book()
    rev = rr.review_release(data, pdf, z, ai_reviewer=_no_ai)
    hard = [f for f in rev.findings if f.level != rr.EDITORIAL]
    assert rev.status == rr.STATUS_READY, [f.to_dict() for f in rev.findings]
    assert not hard
    assert [(v.page, v.kind) for v in rev.visuals] == [
        (1, "cover"), (3, "photo"), (4, "photo"), (5, "chart"), (6, "chart"), (7, "photo")]


def test_without_ai_the_book_is_not_verified_never_ready():
    data, pdf, z = _book()
    rev = rr.review_release(data, pdf, z, ai_reviewer=None)
    assert rev.status == rr.STATUS_UNVERIFIED
    assert "AI_REVIEW_NOT_RUN" in _codes(rev)


# ---------------------------------------------------------------- 6 pt chart
def test_a_6pt_chart_is_refused_and_a_full_width_chart_passes():
    data, pdf, z = _book(chart_width_pt=280)            # 30 px * 280 / 1400 = 6.0 pt
    rev = rr.review_release(data, pdf, z, ai_reviewer=_no_ai)
    small = [f for f in rev.findings if f.code == "CHART_TEXT_TOO_SMALL"]
    assert rev.status == rr.STATUS_CHANGES
    assert {f.page for f in small} == {5, 6}
    assert "6.0 pt" in small[0].why and small[0].fix
    data, pdf, z = _book(chart_width_pt=468)
    assert "CHART_TEXT_TOO_SMALL" not in _codes(rr.review_release(data, pdf, z, ai_reviewer=_no_ai))


# ------------------------------------------------------- chapter 5 mixed formats
def test_chapter_5_mixed_factors_and_questions_is_refused_and_the_rewrite_passes():
    data, pdf, z = _book(ch5=CH5_AS_SHIPPED)
    rev = rr.review_release(data, pdf, z, ai_reviewer=_no_ai)
    f = next(x for x in rev.findings if x.code == "CHART_MIXED_FORMATS")
    assert f.level == rr.HARD and f.page == 5 and f.chapter == CH[2]
    assert "Sun exposure" in f.subject and "?" in f.subject
    assert rev.status == rr.STATUS_CHANGES
    data, pdf, z = _book(ch5=CH5_CORRECTED)
    assert "CHART_MIXED_FORMATS" not in _codes(rr.review_release(data, pdf, z, ai_reviewer=_no_ai))


# ------------------------------------------------ chapter 7 repetitive fragments
def test_chapter_7_fragments_and_repeats_are_refused_and_the_rewrite_passes():
    data, pdf, z = _book(ch7=CH7_AS_SHIPPED)
    rev = rr.review_release(data, pdf, z, ai_reviewer=_no_ai)
    codes = _codes(rev)
    assert {"CHART_SENTENCE_FRAGMENTS", "CHART_REPEATED_POINTS"} <= codes
    frag = next(x for x in rev.findings if x.code == "CHART_SENTENCE_FRAGMENTS")
    assert frag.page == 6 and "This helps replace" in frag.subject
    data, pdf, z = _book(ch7=CH7_CORRECTED)
    codes = _codes(rr.review_release(data, pdf, z, ai_reviewer=_no_ai))
    assert not ({"CHART_SENTENCE_FRAGMENTS", "CHART_REPEATED_POINTS"} & codes)


# ------------------------------------------------------ weak or repeated photos
def test_a_repeated_chapter_photo_is_refused_and_a_distinct_photo_passes():
    data, pdf, z = _book(ch5_photo_repeats=True)
    rev = rr.review_release(data, pdf, z, ai_reviewer=_no_ai)
    f = next(x for x in rev.findings if x.code == "PHOTO_REPEATED")
    assert f.page == 7 and "page 3" in f.subject
    assert next(v for v in rev.visuals if v.page == 7).status == "rejected"
    data, pdf, z = _book()
    assert "PHOTO_REPEATED" not in _codes(rr.review_release(data, pdf, z, ai_reviewer=_no_ai))


def test_a_low_resolution_photo_is_refused():
    data, pdf, z = _book(small_photo=True)               # 400 px across 6.5 in = 62 dpi
    rev = rr.review_release(data, pdf, z, ai_reviewer=_no_ai)
    f = next(x for x in rev.findings if x.code == "PHOTO_LOW_RESOLUTION")
    assert f.page == 4 and "dpi" in f.why


def test_a_weak_photo_judged_by_ai_must_cite_its_page_to_count():
    data, pdf, z = _book()

    def ai(req):
        return [
            {"page": 7, "visual_id": "v_ch5", "level": "hard", "quote": "empty clay pots, no plants",
             "why": "Chapter is about keeping plants productive; the photo shows no plants.",
             "fix": "Choose a photo of healthy, producing container plants."},
            {"page": 99, "visual_id": "v_ch1", "level": "hard", "quote": "x", "why": "y", "fix": "z"},
            {"visual_id": "v_ch2", "level": "hard", "why": "no page or quote"},
        ]

    rev = rr.review_release(data, pdf, z, ai_reviewer=ai)
    ai_found = [f for f in rev.findings if f.code.startswith("AI_")]
    assert len(ai_found) == 1 and ai_found[0].page == 7 and ai_found[0].level == rr.HARD
    assert rev.status == rr.STATUS_CHANGES
    assert rev.ai["findings_received"] == 3 and rev.ai["findings_kept"] == 1


# ------------------------------------------------------------ files and identity
def test_zip_pdf_that_differs_is_refused():
    data, pdf, z = _book()
    zbuf = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(z)) as src, zipfile.ZipFile(zbuf, "w") as dst:
        for n in src.namelist():
            dst.writestr(n, src.read(n) + (b"%tampered" if n == "ebook.pdf" else b""))
    rev = rr.review_release(data, pdf, zbuf.getvalue(), ai_reviewer=_no_ai)
    assert "ZIP_PDF_DIFFERS" in _codes(rev) and rev.status == rr.STATUS_CHANGES


def test_unopenable_files_are_refused():
    rev = rr.review_release({}, b"not a pdf", b"not a zip", ai_reviewer=_no_ai)
    assert {"PDF_UNOPENABLE", "ZIP_UNOPENABLE"} <= _codes(rev)


def test_a_missing_template_is_refused():
    data, pdf, z = _book()
    data["ebook_design"]["theme_id"] = "modern_practical"      # a sans template, PDF is serif
    assert "TEMPLATE_MISSING" in _codes(rr.review_release(data, pdf, z, ai_reviewer=_no_ai))


def test_the_cover_line_break_is_an_editorial_note_with_a_correction():
    data, pdf, z = _book(title="Container Gardening for Beginners")   # the live cover's wrap
    f = next(x for x in rr.review_release(data, pdf, z, ai_reviewer=_no_ai).findings
             if x.code == "COVER_LONE_WORD")
    assert f.level == rr.EDITORIAL and "for Beginners" in f.fix


def test_findings_are_grouped_by_correction():
    data, pdf, z = _book(ch7=CH7_AS_SHIPPED)
    groups = rr.review_release(data, pdf, z, ai_reviewer=_no_ai).groups()
    g = next(x for x in groups if "Watering" in x["correction"])
    assert {f["code"] for f in g["findings"]} >= {"CHART_SENTENCE_FRAGMENTS", "CHART_REPEATED_POINTS"}
