"""Editor-in-Chief release review of the exported ebook (v1.9.11).

Reviews the ACTUAL exported PDF and ZIP against the manuscript, the visual
plan, the approved assets and the project settings, before a book may be
approved. Written after Container Gardening for Beginners reached "Finished"
with 6 pt charts, a chart that mixed factors with questions, a chart of
sentence fragments, and repeated chapter photos -- none of which any check
looked at, because the one-click build never ran the Editor-in-Chief and the
Editor-in-Chief never opened the PDF.

Three kinds of result, never blurred together:

* HARD      -- blocks approval.
* EDITORIAL -- a proposed correction held for the owner's review.
* NOT_VERIFIED -- something this review could not inspect reliably. It is
  never counted as a pass: a book with any unverified hard check is not ready.

Measurable checks (file validity, dimensions, final rendered font size,
contrast, asset identity, PDF/ZIP consistency) are done here in code. Judgment
checks (relevance, accuracy against the chapter, repetition of meaning,
consistency) go to an AI reviewer that is only called when the owner has
authorized its stated cost; every AI finding must cite the page and the exact
content judged, or it is discarded and the check reported not verified.

Approved manuscript text is never rewritten here. Every finding carries a
specific correction for a person to apply.
"""
from __future__ import annotations

import hashlib
import io
import json
import re
import zipfile
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

from PIL import Image

HARD = "hard"
EDITORIAL = "editorial"
NOT_VERIFIED = "not_verified"

STATUS_READY = "Ready for approval"
STATUS_CHANGES = "Changes required"
STATUS_UNVERIFIED = "Not verified"

MIN_TEXT_PT = 8.0
MIN_CONTRAST = 4.5
MIN_PHOTO_DPI = 150.0
SAFE_MARGIN_PT = 18.0          # 0.25 in: nothing may print closer to the edge
DUP_HASH_BITS = 10             # dHash distance at or below: the same picture
SIMILAR_HASH_BITS = 22         # with near-identical colour: repeated composition

_FRAGMENT_OPENERS = ("this ", "it ", "its ", "these ", "those ", "that ", "they ",
                     "instead", "also ", "so ", "and ", "but ", "which ", "then ")
_STOP = set("a an the and or of to in on for with your you is are be it this that as at by "
            "from into than then so do does not no only just more most very can will".split())
_SERIF_THEMES = {"studio_clean", "editorial_professional"}


@dataclass
class Finding:
    code: str
    level: str                 # HARD / EDITORIAL / NOT_VERIFIED
    page: int | None           # 1-based PDF page, None when not page-specific
    chapter: str
    subject: str               # the affected text or image
    why: str
    fix: str
    group: str                 # the correction this belongs to

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Visual:
    page: int
    chapter: str
    kind: str                  # cover / photo / chart / unknown
    visual_id: str
    width: int
    height: int
    placed_width_pt: float
    status: str = "ok"         # ok / rejected / not_verified
    thumb_jpeg: bytes = b""

    def to_dict(self, *, with_thumb: bool = False) -> dict[str, Any]:
        d = asdict(self)
        d.pop("thumb_jpeg", None)
        if with_thumb and self.thumb_jpeg:
            import base64
            d["thumb"] = "data:image/jpeg;base64," + base64.b64encode(self.thumb_jpeg).decode("ascii")
        return d


@dataclass
class Review:
    status: str
    findings: list[Finding] = field(default_factory=list)
    visuals: list[Visual] = field(default_factory=list)
    pdf_sha256: str = ""
    zip_sha256: str = ""
    checks_run: list[str] = field(default_factory=list)
    ai: dict[str, Any] = field(default_factory=dict)
    reviewed_at: str = ""

    @property
    def ready(self) -> bool:
        return self.status == STATUS_READY

    def groups(self) -> list[dict[str, Any]]:
        order: list[str] = []
        by: dict[str, list[Finding]] = {}
        for f in self.findings:
            if f.group not in by:
                order.append(f.group)
                by[f.group] = []
            by[f.group].append(f)
        rank = {HARD: 0, NOT_VERIFIED: 1, EDITORIAL: 2}
        order.sort(key=lambda g: min(rank.get(f.level, 3) for f in by[g]))
        return [{"correction": g, "level": min((f.level for f in by[g]), key=lambda x: rank.get(x, 3)),
                 "findings": [f.to_dict() for f in by[g]]} for g in order]

    def to_dict(self, *, with_thumbs: bool = False) -> dict[str, Any]:
        return {
            "status": self.status, "ready": self.ready,
            "pdf_sha256": self.pdf_sha256, "zip_sha256": self.zip_sha256,
            "reviewed_at": self.reviewed_at, "checks_run": list(self.checks_run),
            "counts": {lvl: sum(1 for f in self.findings if f.level == lvl)
                       for lvl in (HARD, EDITORIAL, NOT_VERIFIED)},
            "groups": self.groups(),
            "visuals": [v.to_dict(with_thumb=with_thumbs) for v in self.visuals],
            "ai": dict(self.ai),
        }


# --------------------------------------------------------------------------- helpers
def _sha(b: bytes) -> str:
    return hashlib.sha256(b or b"").hexdigest()


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(text or "").lower()).strip()


def _plain(text: Any) -> str:
    t = re.sub(r"\*\*|__|`", "", str(text or ""))
    t = re.sub(r"^\[\s*[xX ]?\s*\]\s*", "", t.strip())
    return re.sub(r"\s+", " ", t).strip()


def dhash(img: Image.Image, size: int = 8) -> int:
    g = img.convert("L").resize((size + 1, size), Image.LANCZOS)
    px = list(g.getdata())
    bits = 0
    for r in range(size):
        for c in range(size):
            bits = (bits << 1) | (1 if px[r * (size + 1) + c] > px[r * (size + 1) + c + 1] else 0)
    return bits


def hamming(a: int, b: int) -> int:
    return bin(int(a) ^ int(b)).count("1")


def _colour_signature(img: Image.Image) -> list[float]:
    small = img.convert("RGB").resize((32, 32))
    hist = small.histogram()
    out = []
    for ch in range(3):
        band = hist[ch * 256:(ch + 1) * 256]
        tot = float(sum(band)) or 1.0
        out += [sum(band[i:i + 32]) / tot for i in range(0, 256, 32)]
    return out


def _colour_similarity(a: list[float], b: list[float]) -> float:
    return 1.0 - 0.5 * sum(abs(x - y) for x, y in zip(a, b)) / 3.0


def _luminance(rgb: tuple[float, float, float]) -> float:
    def ch(c: float) -> float:
        c = c / 255.0
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = rgb
    return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b)


def text_contrast(img: Image.Image) -> float:
    """Contrast between the darkest ink (text) and the typical background."""
    g = img.convert("RGB").resize((min(700, img.width), max(1, int(img.height * min(700, img.width) / img.width))))
    px = sorted(g.getdata(), key=lambda p: _luminance(p))
    n = len(px)
    ink = px[max(0, int(n * 0.01))]
    bg = px[int(n * 0.6)]
    l1, l2 = _luminance(bg), _luminance(ink)
    hi, lo = max(l1, l2), min(l1, l2)
    return (hi + 0.05) / (lo + 0.05)


def _thumb(img: Image.Image, width: int = 260) -> bytes:
    h = max(1, int(img.height * width / max(1, img.width)))
    buf = io.BytesIO()
    img.convert("RGB").resize((width, h)).save(buf, "JPEG", quality=80)
    return buf.getvalue()


def plan_aids(data: dict) -> list[dict]:
    plan = data.get("visual_plan") if isinstance(data.get("visual_plan"), dict) else {}
    out = []
    for ch in plan.get("chapters") or []:
        for aid in ch.get("aids") or []:
            if isinstance(aid, dict):
                a = dict(aid)
                a.setdefault("chapter", ch.get("chapter"))
                a.setdefault("chapter_index", ch.get("chapter_index"))
                out.append(a)
    return out


def chapter_titles(data: dict) -> list[str]:
    plan = data.get("visual_plan") if isinstance(data.get("visual_plan"), dict) else {}
    titles = [str(c.get("chapter") or "").strip() for c in plan.get("chapters") or []]
    titles = [t for t in titles if t]
    if titles:
        return titles
    outline = data.get("outline") or (data.get("ebook_workspace") or {}).get("outline") or []
    if isinstance(outline, list):
        return [str(o.get("title") if isinstance(o, dict) else o).strip() for o in outline if o]
    return []


def _is_photo(aid: dict) -> bool:
    from services.ebook_visual_pipeline import is_photo_aid
    return bool(is_photo_aid(aid))


# ------------------------------------------------------------- chart wording checks
def _content_words(text: str) -> set[str]:
    return {w for w in _norm(text).split() if w not in _STOP and len(w) > 2}


def chart_wording_findings(aid: dict, *, page: int | None, chapter: str) -> list[Finding]:
    """Deterministic chart-text checks: mixed formats, fragments, repetition."""
    items = [_plain(x) for x in (aid.get("items") or []) if _plain(x)]
    title = _plain(aid.get("title") or "chart")
    group = f"Rewrite the chart text in {chapter or 'this chapter'}"
    out: list[Finding] = []
    if len(items) < 2:
        return out
    questions = [i for i in items if i.rstrip().endswith("?")]
    statements = [i for i in items if not i.rstrip().endswith("?")]
    if questions and statements:
        out.append(Finding(
            "CHART_MIXED_FORMATS", HARD, page, chapter,
            f'"{title}": {len(statements)} items are labels or statements '
            f'("{statements[0][:60]}") and {len(questions)} are questions ("{questions[0][:70]}")',
            "A chart presented as one sequence mixes two formats, so the reader cannot tell what to do.",
            "Rewrite every item in one format (for example, each factor followed by its question), "
            "one item per idea, using the chapter's own wording.", group))
    frags = [i for i in items if i.lower().startswith(_FRAGMENT_OPENERS)]
    if frags:
        out.append(Finding(
            "CHART_SENTENCE_FRAGMENTS", HARD, page, chapter,
            f'"{title}": ' + "; ".join(f'"{f[:60]}"' for f in frags[:3]),
            "These items begin with a word that points back to text the chart does not show, "
            "so out of the chapter they are fragments, not instructions.",
            "Replace each with a complete instruction that stands on its own, taken from the chapter.",
            group))
    seen: list[tuple[str, set[str]]] = []
    repeats: list[tuple[str, str]] = []
    for it in items:
        cw = _content_words(it)
        for prev, pw in seen:
            if cw and pw and len(cw & pw) / len(cw | pw) >= 0.5:
                repeats.append((prev, it))
        seen.append((it, cw))
    if repeats:
        a, b = repeats[0]
        out.append(Finding(
            "CHART_REPEATED_POINTS", HARD, page, chapter,
            f'"{title}": "{a[:60]}" and "{b[:60]}"',
            "Two items say the same thing, which wastes the chart and reads as padding.",
            "Keep one of each repeated point and use the space for a different point from the chapter.",
            group))
    if re.search(r"\b(sequence|steps?|workflow)\b", title, re.I):
        imperative = [i for i in items if not i.endswith("?") and len(i.split()) >= 3]
        if len(imperative) < len(items) / 2:
            out.append(Finding(
                "CHART_NOT_A_SEQUENCE", HARD, page, chapter,
                f'"{title}"',
                "The heading promises steps, but most items are single labels or questions, not actions.",
                "Retitle the chart to what it lists (for example, 'questions to ask') or rewrite the "
                "items as actions in the order the chapter gives them.", group))
    return out


# ---------------------------------------------------------------------- the review
def review_release(
    data: dict,
    pdf_bytes: bytes | None,
    zip_bytes: bytes | None,
    *,
    ai_reviewer: Callable[[dict], list[dict]] | None = None,
    ai_note: str = "",
) -> Review:
    """Review the exported book. Never raises; unexpected errors become NOT_VERIFIED."""
    rev = Review(status=STATUS_UNVERIFIED, reviewed_at=datetime.now(timezone.utc).isoformat(timespec="seconds"))
    F = rev.findings.append
    rev.pdf_sha256 = _sha(pdf_bytes or b"")
    rev.zip_sha256 = _sha(zip_bytes or b"")

    # 1. files open --------------------------------------------------------
    rev.checks_run.append("files_open")
    doc = None
    try:
        import fitz  # PyMuPDF

        if not pdf_bytes or not pdf_bytes.startswith(b"%PDF"):
            raise ValueError("not a PDF")
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        if doc.page_count < 1:
            raise ValueError("no pages")
    except Exception as exc:  # noqa: BLE001
        F(Finding("PDF_UNOPENABLE", HARD, None, "", "ebook.pdf", f"The PDF cannot be opened ({exc}).",
                  "Export the book again and review the new PDF.", "Re-export the PDF"))
    zf = None
    try:
        zf = zipfile.ZipFile(io.BytesIO(zip_bytes or b""))
        bad = zf.testzip()
        if bad:
            raise ValueError(f"damaged member {bad}")
    except Exception as exc:  # noqa: BLE001
        zf = None
        F(Finding("ZIP_UNOPENABLE", HARD, None, "", "package.zip", f"The ZIP cannot be opened ({exc}).",
                  "Export the book again and review the new ZIP.", "Re-export the ZIP"))

    # 2. PDF inside the ZIP --------------------------------------------------
    rev.checks_run.append("zip_pdf_identical")
    zip_visuals: dict[str, bytes] = {}
    if zf is not None:
        names = zf.namelist()
        if "ebook.pdf" not in names:
            F(Finding("ZIP_MISSING_PDF", HARD, None, "", "package.zip", "The ZIP has no ebook.pdf.",
                      "Export again so the ZIP contains the book's PDF.", "Re-export the ZIP"))
        elif pdf_bytes and _sha(zf.read("ebook.pdf")) != rev.pdf_sha256:
            F(Finding("ZIP_PDF_DIFFERS", HARD, None, "", "package.zip / ebook.pdf",
                      "The PDF inside the ZIP is not the same file as the downloadable PDF.",
                      "Export the PDF and ZIP together so they carry the same book.", "Re-export the ZIP"))
        for n in names:
            m = re.match(r"visuals/(.+)\.(png|jpe?g)$", n)
            if m:
                zip_visuals[m.group(1)] = zf.read(n)

    if doc is None:
        rev.status = STATUS_CHANGES
        return rev

    aids = plan_aids(data)
    titles = chapter_titles(data)

    # 3. chapters present, contents links -----------------------------------
    rev.checks_run.append("chapters_and_contents")
    page_text = [_norm(doc[i].get_text()) for i in range(doc.page_count)]
    chapter_page: dict[str, int] = {}
    for t in titles:
        nt = _norm(t)
        hits = [i for i, txt in enumerate(page_text) if nt and nt in txt]
        body_hits = [i for i in hits if sum(1 for o in titles if _norm(o) and _norm(o) in page_text[i]) < 3]
        if body_hits:
            chapter_page[t] = body_hits[0] + 1
        else:
            F(Finding("CHAPTER_MISSING", HARD, None, t, t, "This chapter's heading is not in the PDF.",
                      "Export the book again; the chapter must be present before approval.",
                      "Restore missing chapters"))
    toc_pages = [i for i, txt in enumerate(page_text)
                 if sum(1 for o in titles if _norm(o) and _norm(o) in txt) >= 3]
    if titles and toc_pages:
        links = [ln for ln in doc[toc_pages[0]].get_links() if ln.get("kind") in (1,)]  # LINK_GOTO
        outline = doc.get_toc(simple=True)
        if not links and not outline:
            F(Finding("CONTENTS_LINKS_NOT_VERIFIED", NOT_VERIFIED, toc_pages[0] + 1, "", "Contents",
                      "No working links or bookmarks were found for the contents page.",
                      "Export with a linked contents page or bookmarks.", "Fix the contents links"))
        for ln in links:
            target = int(ln.get("page", -1))
            if not (0 <= target < doc.page_count):
                F(Finding("CONTENTS_LINK_BROKEN", HARD, toc_pages[0] + 1, "", f"link to page {target + 1}",
                          "A contents link points outside the book.", "Export again to rebuild the contents.",
                          "Fix the contents links"))
    elif titles:
        F(Finding("CONTENTS_NOT_FOUND", NOT_VERIFIED, None, "", "Contents",
                  "No contents page listing the chapters was found.",
                  "Export with a contents page.", "Fix the contents links"))

    def chapter_for_page(p: int) -> str:
        best = ""
        for t, cp in sorted(chapter_page.items(), key=lambda kv: kv[1]):
            if cp <= p:
                best = t
        return best

    # 4. text clipped / outside safe margins / small captions ---------------
    rev.checks_run.append("margins_and_captions")
    for i in range(doc.page_count):
        page = doc[i]
        rect = page.rect
        d = page.get_text("dict")
        img_boxes = [im["bbox"] for im in page.get_image_info()]
        for block in d.get("blocks", []):
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    txt = (span.get("text") or "").strip()
                    if not txt:
                        continue
                    x0, y0, x1, y1 = span["bbox"]
                    if i > 0 and (x0 < rect.x0 + SAFE_MARGIN_PT - 1 or x1 > rect.x1 - SAFE_MARGIN_PT + 1
                                  or y0 < rect.y0 + SAFE_MARGIN_PT - 1 or y1 > rect.y1 - SAFE_MARGIN_PT + 1):
                        F(Finding("TEXT_OUTSIDE_SAFE_MARGIN", HARD, i + 1, chapter_for_page(i + 1), txt[:60],
                                  "Text prints within 0.25 in of the page edge or beyond it and can be cut off.",
                                  "Move the text inside the page margins and export again.",
                                  "Fix text outside the margins"))
                    size = float(span.get("size") or 0)
                    under_image = any(abs(y0 - b[3]) < 40 and x0 < b[2] and x1 > b[0] for b in img_boxes)
                    if under_image and 0 < size < MIN_TEXT_PT:
                        F(Finding("CAPTION_TOO_SMALL", HARD, i + 1, chapter_for_page(i + 1), txt[:60],
                                  f"The caption prints at {size:.1f} pt, below {MIN_TEXT_PT:.0f} pt.",
                                  "Set captions to at least 8 pt and export again.", "Enlarge captions"))

    # 5. every image in the PDF --------------------------------------------
    rev.checks_run.append("images_on_the_page")
    zip_hashes: dict[str, int] = {}
    for vid, raw in zip_visuals.items():
        try:
            zip_hashes[vid] = dhash(Image.open(io.BytesIO(raw)))
        except Exception:  # noqa: BLE001
            pass
    aid_by_id = {str(a.get("visual_id")): a for a in aids}
    matched: dict[str, Visual] = {}
    photos_seen: list[tuple[Visual, int, list[float]]] = []
    for i in range(doc.page_count):
        page = doc[i]
        for info in page.get_image_info(xrefs=True):
            xref = info.get("xref") or 0
            try:
                raw = doc.extract_image(xref)["image"] if xref else b""
                img = Image.open(io.BytesIO(raw))
                img.load()
            except Exception:  # noqa: BLE001
                F(Finding("IMAGE_UNREADABLE", NOT_VERIFIED, i + 1, chapter_for_page(i + 1), f"image on page {i + 1}",
                          "This image could not be read from the PDF.", "Export again.", "Re-export the PDF"))
                continue
            bbox = info["bbox"]
            placed_w = float(bbox[2] - bbox[0])
            h = dhash(img)
            best_vid, best_d = "", 99
            for vid, zh in zip_hashes.items():
                dist = hamming(h, zh)
                if dist < best_d:
                    best_vid, best_d = vid, dist
            if i == 0 and best_d > DUP_HASH_BITS:
                kind, vid = "cover", "cover"
            elif best_d <= DUP_HASH_BITS and best_vid in aid_by_id:
                vid = best_vid
                kind = "photo" if _is_photo(aid_by_id[vid]) else "chart"
            else:
                vid, kind = f"page{i + 1}", "unknown"
            chapter = chapter_for_page(i + 1)
            v = Visual(page=i + 1, chapter=chapter, kind=kind, visual_id=vid, width=img.width,
                       height=img.height, placed_width_pt=round(placed_w, 1), thumb_jpeg=_thumb(img))
            rev.visuals.append(v)
            if kind == "unknown":
                v.status = "rejected"
                F(Finding("IMAGE_NOT_APPROVED", HARD, i + 1, chapter, f"image on page {i + 1}",
                          "This image is not one of the book's approved visuals.",
                          "Replace it with the approved visual for this chapter, or approve this one.",
                          f"Replace the image on page {i + 1}"))
                continue
            if kind == "cover":
                continue
            matched[vid] = v
            aid = aid_by_id[vid]
            if kind == "chart":
                _check_chart(rev, aid, v, img, placed_w)
            else:
                _check_photo(rev, aid, v, img, placed_w, zip_visuals.get(vid))
                photos_seen.append((v, h, _colour_signature(img)))

    # 6. planned visuals that never reached the PDF ----------------------------
    rev.checks_run.append("planned_visuals_present")
    for aid in aids:
        vid = str(aid.get("visual_id") or "")
        if aid.get("required") is False:
            continue
        if vid and vid not in matched:
            ch = str(aid.get("chapter") or "")
            F(Finding("PLANNED_VISUAL_ABSENT", HARD, chapter_page.get(ch), ch, vid,
                      "A planned chapter visual is not in the PDF.",
                      "Add the approved visual to this chapter and export again.",
                      f"Restore the visual for {ch or vid}"))

    # 7. repeated photos -------------------------------------------------------
    rev.checks_run.append("photo_repetition")
    for a_idx in range(len(photos_seen)):
        for b_idx in range(a_idx + 1, len(photos_seen)):
            va, ha, ca = photos_seen[a_idx]
            vb, hb, cb = photos_seen[b_idx]
            dist = hamming(ha, hb)
            sim = _colour_similarity(ca, cb)
            if dist <= DUP_HASH_BITS:
                vb.status = "rejected"
                F(Finding("PHOTO_REPEATED", HARD, vb.page, vb.chapter,
                          f"photo on page {vb.page} repeats page {va.page}",
                          "The same picture appears twice.",
                          f"Replace the photo on page {vb.page} with a different picture of {vb.chapter}.",
                          f"Replace the photo on page {vb.page}"))
            elif dist <= SIMILAR_HASH_BITS and sim >= 0.85:
                F(Finding("PHOTO_REPEATED_COMPOSITION", EDITORIAL, vb.page, vb.chapter,
                          f"photo on page {vb.page} resembles page {va.page}",
                          "The two photos share the same subject, framing and colours, so the chapters look alike.",
                          f"Consider a different composition for page {vb.page} that shows {vb.chapter}.",
                          f"Replace the photo on page {vb.page}"))

    # 8. template ------------------------------------------------------------
    rev.checks_run.append("template_present")
    theme = str(((data.get("ebook_design") or {}).get("theme_id")) or data.get("design_theme") or "")
    fonts = {f[3].split("+")[-1] for p in doc for f in p.get_fonts()}
    if not theme:
        F(Finding("TEMPLATE_NOT_VERIFIED", NOT_VERIFIED, None, "", "template",
                  "The project records no selected template.", "Choose a template and export again.",
                  "Apply the selected template"))
    else:
        want = "LiberationSerif" if theme in _SERIF_THEMES else "LiberationSans"
        if not any(f.replace(" ", "").startswith(want) for f in fonts):
            F(Finding("TEMPLATE_MISSING", HARD, None, "", theme,
                      f"The PDF does not use the {theme} template's typeface ({want}).",
                      "Export again with the selected template.", "Apply the selected template"))

    # 9. cover line breaks (editorial) ----------------------------------------
    rev.checks_run.append("cover_line_breaks")
    _cover_breaks(rev, data)

    # 10. AI judgment -----------------------------------------------------------
    rev.checks_run.append("ai_judgment")
    _ai_judgment(rev, data, doc, aids, matched, chapter_page, ai_reviewer, ai_note)

    hard = any(f.level == HARD for f in rev.findings)
    unverified = any(f.level == NOT_VERIFIED for f in rev.findings)
    editorial = any(f.level == EDITORIAL for f in rev.findings)
    rev.status = STATUS_CHANGES if (hard or editorial) else (STATUS_UNVERIFIED if unverified else STATUS_READY)
    return rev


def _check_chart(rev: Review, aid: dict, v: Visual, img: Image.Image, placed_w: float) -> None:
    from services.ebook_visual_pipeline import label_min_pt, render_aid_png

    F = rev.findings.append
    title = _plain(aid.get("title") or v.visual_id)
    group = f"Redraw the chart on page {v.page}"
    try:
        size = label_min_pt(render_aid_png(aid), column_pt=placed_w)
    except Exception:  # noqa: BLE001
        size = 0.0
    if size <= 0:
        v.status = "not_verified"
        F(Finding("CHART_TEXT_NOT_VERIFIED", NOT_VERIFIED, v.page, v.chapter, title,
                  "The chart's text size could not be measured.", "Redraw the chart with the current Factory.",
                  group))
    elif size < MIN_TEXT_PT:
        v.status = "rejected"
        F(Finding("CHART_TEXT_TOO_SMALL", HARD, v.page, v.chapter, title,
                  f"Its smallest label prints at {size:.1f} pt on the page, below {MIN_TEXT_PT:.0f} pt.",
                  "Redraw the chart with labels of at least 8 pt at the printed width.", group))
    expected_ratio = img.height / max(1, img.width)
    contrast = text_contrast(img)
    if contrast < MIN_CONTRAST:
        v.status = "rejected"
        F(Finding("CHART_LOW_CONTRAST", HARD, v.page, v.chapter, title,
                  f"Text contrast is {contrast:.1f}:1, below {MIN_CONTRAST}:1.",
                  "Use near-black text on a light background.", group))
    for f in chart_wording_findings(aid, page=v.page, chapter=v.chapter):
        v.status = "rejected"
        F(f)
    _ = expected_ratio


def _check_photo(rev: Review, aid: dict, v: Visual, img: Image.Image, placed_w: float,
                 zip_raw: bytes | None) -> None:
    F = rev.findings.append
    group = f"Replace the photo on page {v.page}"
    src = str(aid.get("source") or "").lower()
    if src == "local_render" or not (aid.get("asset_path") or aid.get("sha256") or zip_raw):
        v.status = "rejected"
        F(Finding("PHOTO_IS_A_TEXT_CARD", HARD, v.page, v.chapter, v.visual_id,
                  "The chapter photo is a drawn text card or placeholder, not a photograph.",
                  "Choose a real photograph for this chapter.", group))
    dpi = img.width / max(0.01, placed_w / 72.0)
    if dpi < MIN_PHOTO_DPI:
        v.status = "rejected"
        F(Finding("PHOTO_LOW_RESOLUTION", HARD, v.page, v.chapter, v.visual_id,
                  f"The photo prints at {dpi:.0f} dpi at its size on the page, below {MIN_PHOTO_DPI:.0f}.",
                  "Choose a larger version of this photo or a different photo.", group))
    want = str(aid.get("sha256") or "")
    if zip_raw is not None and want:
        if _sha(zip_raw) != want:
            v.status = "rejected"
            F(Finding("PHOTO_NOT_APPROVED_FILE", HARD, v.page, v.chapter, v.visual_id,
                      "The photo in the book is not the file that was approved.",
                      "Export again with the approved photo, or approve this one.", group))
    elif not want:
        F(Finding("PHOTO_IDENTITY_NOT_VERIFIED", NOT_VERIFIED, v.page, v.chapter, v.visual_id,
                  "No approved fingerprint is recorded for this photo, so its identity cannot be checked.",
                  "Approve this photo again so its fingerprint is recorded.", group))


def _cover_breaks(rev: Review, data: dict) -> None:
    title = str(data.get("title") or "").strip()
    if not title:
        return
    try:
        from PIL import ImageDraw

        from services.ebook_photo_cover import _fit_role

        d = ImageDraw.Draw(Image.new("RGB", (1275, 1650)))
        lines = _fit_role(d, title, bold=True, start_px=84, min_px=40, max_px=84, max_lines=3,
                          max_w=1275 - 2 * 95, line_gap=10)["lines"] or []
    except Exception:  # noqa: BLE001
        lines = []
    if len(lines) >= 2 and len(lines[-1].split()) == 1 and len(title.split()) >= 3:
        rev.findings.append(Finding(
            "COVER_LONE_WORD", EDITORIAL, 1, "Cover", " / ".join(lines),
            "The title's last line is a single word, which reads as an accident on a cover.",
            "Break the title so each line carries at least two words (for example '"
            + " ".join(title.split()[:-2]) + " / " + " ".join(title.split()[-2:]) + "').",
            "Rebalance the cover title"))


def ai_request(data: dict, doc, aids: list[dict], matched: dict[str, Visual],
               chapter_page: dict[str, int]) -> dict:
    """What the AI reviewer is shown: each visual with its page and the chapter text."""
    manuscript = str(data.get("content") or data.get("ebook") or "")
    items = []
    for aid in aids:
        vid = str(aid.get("visual_id") or "")
        v = matched.get(vid)
        ch = str(aid.get("chapter") or "")
        start = chapter_page.get(ch)
        excerpt = ""
        if ch and ch in manuscript:
            i = manuscript.index(ch)
            excerpt = manuscript[i:i + 3500]
        items.append({
            "visual_id": vid, "page": v.page if v else None, "chapter": ch, "chapter_page": start,
            "type": aid.get("type"), "title": _plain(aid.get("title")),
            "items": [_plain(x) for x in (aid.get("items") or [])],
            "caption": aid.get("caption") or "", "photo_description": aid.get("alt") or aid.get("description") or "",
            "chapter_text": excerpt,
        })
    return {"book_title": data.get("title"), "visuals": items}


AI_SYSTEM = (
    "You are the Editor-in-Chief of a publisher reviewing an ebook's visuals before sale. "
    "For each visual, judge it against its own chapter text only. Report problems as JSON: "
    '{"findings":[{"page":int,"visual_id":str,"level":"hard"|"editorial","quote":str,'
    '"why":str,"fix":str}]} . Hard: a chart heading, category, question or key point that '
    "misrepresents the chapter, contradicts it, makes an unsupported claim, or a photo unrelated "
    "to or misleading about its chapter. Editorial: weak or generic photo, chart wording that adds "
    "no information, a factual claim needing a source, inconsistent terms, tone or reading level. "
    "Every finding MUST quote the exact chart text or describe the exact photo you judged and give "
    "its page. Never rewrite the manuscript; propose a specific correction. If nothing is wrong, "
    'return {"findings":[]}.'
)


def _ai_judgment(rev: Review, data: dict, doc, aids, matched, chapter_page, ai_reviewer, ai_note) -> None:
    F = rev.findings.append
    if ai_reviewer is None:
        rev.ai = {"ran": False, "note": ai_note or "AI review not authorized."}
        F(Finding("AI_REVIEW_NOT_RUN", NOT_VERIFIED, None, "", "chart meaning, photo relevance, consistency",
                  "Whether each chart and photo truly fits its chapter was not checked. "
                  + (ai_note or "The AI review needs your authorization for its stated cost."),
                  "Authorize the AI review, or review each chart and photo yourself on this screen.",
                  "Run the AI review"))
        return
    req = ai_request(data, doc, aids, matched, chapter_page)
    try:
        raw = ai_reviewer(req)
    except Exception as exc:  # noqa: BLE001
        rev.ai = {"ran": False, "error": str(exc)[:200]}
        F(Finding("AI_REVIEW_FAILED", NOT_VERIFIED, None, "", "AI review",
                  f"The AI review did not complete ({str(exc)[:120]}).",
                  "Run the AI review again.", "Run the AI review"))
        return
    kept = 0
    pages_ok = {v.page for v in matched.values()}
    by_vid = {str(a.get("visual_id")): a for a in aids}
    for f in raw or []:
        try:
            page = int(f.get("page"))
            quote = str(f.get("quote") or "").strip()
            vid = str(f.get("visual_id") or "")
            level = HARD if str(f.get("level")) == "hard" else EDITORIAL
        except Exception:  # noqa: BLE001
            continue
        if page not in pages_ok or not quote or not f.get("fix"):
            continue          # uncited findings are discarded, never counted
        v = matched.get(vid) or next((x for x in matched.values() if x.page == page), None)
        if v and level == HARD:
            v.status = "rejected"
        chapter = v.chapter if v else str((by_vid.get(vid) or {}).get("chapter") or "")
        what = "chart" if v and v.kind == "chart" else "photo"
        F(Finding("AI_" + ("HARD" if level == HARD else "EDITORIAL"), level, page, chapter, quote[:160],
                  str(f.get("why") or "")[:300], str(f.get("fix") or "")[:300],
                  f"{'Rewrite' if what == 'chart' else 'Replace'} the {what} on page {page}"))
        kept += 1
    rev.ai = {"ran": True, "findings_kept": kept, "findings_received": len(raw or [])}


def estimate_ai_cost(data: dict) -> dict:
    """The stated cost of one AI review, shown before the owner authorizes it."""
    from services.ai_providers import select_provider

    prov = select_provider("editorial_review")
    unit = float(prov.estimate_cost("editorial_review") or 0.0) if prov.billable else 0.0
    if prov.billable and unit <= 0:
        size = len(json.dumps(plan_aids(data))) + len(str(data.get("content") or ""))
        unit = round(max(0.02, (size / 4) / 1000 * 0.005 + 0.01), 2)
    return {"provider": prov.name, "billable": bool(prov.billable), "estimated_usd": round(unit, 2), "calls": 1}


def make_provider_reviewer(max_tokens: int = 1800) -> Callable[[dict], list[dict]]:
    from services.ai_providers import select_provider

    prov = select_provider("editorial_review")

    def run(req: dict) -> list[dict]:
        res = prov.generate_text(AI_SYSTEM, json.dumps(req)[:60000], max_tokens)
        text = res.text.strip()
        m = re.search(r"\{.*\}", text, re.S)
        payload = json.loads(m.group(0)) if m else {}
        return list(payload.get("findings") or [])

    return run
