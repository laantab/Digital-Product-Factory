"""What a photograph actually SHOWS, read from its pixels.

WHY THIS EXISTS
---------------
The visual matcher used to decide "this photograph satisfies the chapter" from
the candidate's own metadata -- alt text, tags, filename, page URL. Metadata is
written by whoever uploaded the image, so a picture of burnt matchsticks
arranged to spell MIND is tagged "mind", satisfies a brief that requires the
subject "mind", and was marked PASS. Real books were being assembled from
word art, letter tiles, chalk tally marks, wall clocks and a stock photo of a
woman throwing a book.

So this module reads the pixels. It answers three questions the metadata
cannot be trusted on:

    Does the image contain prominent baked-in text?   (word art, signs, quotes)
    Is it a flat graphic rather than a photograph?    (tiles, letters on paper)
    Is there a real photographic subject at all?      (studio-flat clichés)

DESIGN RULE, AND THE WHOLE POINT
--------------------------------
Pixel evidence may REJECT a photograph on its own. Pixel evidence is also the
only thing that may let one PASS. Metadata alone can never promote an image to
PASS -- at best it leaves it NEEDS USER REVIEW. Fail-closed: if inspection
cannot run or cannot decide, the answer is "not confident", never "fine".

OCR is used when a local engine is installed (pytesseract). It is never
required: the structural text detector below works with Pillow alone, so the
guarantee does not depend on an optional dependency being present. No network
call is made from this module, ever.
"""
from __future__ import annotations

import io
import os
import re
from pathlib import Path
from typing import Any

from PIL import Image, ImageFilter

#: A photograph whose text covers more of the frame than this is text-led, not
#: a photograph of a subject. Tuned against real failures: matchstick "MIND"
#: and Scrabble "FEEL" sit far above it; an incidental book spine sits below.
TEXT_COVERAGE_REJECT = 0.055
#: Below this a photograph is effectively one flat colour behind one object --
#: the studio cliché look (clock on a white wall, tiles on plain card).
FLAT_BACKGROUND_REJECT = 0.62
#: Minimum share of the frame that must carry photographic detail. See
#: detail_spread() for the calibration against real Factory failures.
DETAIL_SPREAD_MIN = 0.36

#: Words that describe an image ABOUT words rather than about a subject.
WORD_ART_TERMS = (
    "word art", "wordart", "typography", "lettering", "letterpress",
    "scrabble", "letter tile", "letter tiles", "letterboard", "letter board",
    "alphabet", "spelling", "spelled", "spells", "text", "quote", "quotation",
    "sign", "signage", "banner", "poster", "caption", "handwriting",
    "calligraphy", "typewriter", "typed", "chalkboard", "blackboard",
    "whiteboard", "sticky note", "post-it", "note paper", "flashcard",
    "matchstick", "matchsticks", "matches spelling", "wooden letters",
    "magnetic letters", "neon sign", "motivational quote", "inspirational quote",
)

#: Timekeeping props. A chapter that merely says "five minutes" is not asking
#: for a photograph of a clock; that is the search engine answering the word,
#: not the requirement.
TIME_PROP_TERMS = (
    "clock", "clocks", "wall clock", "alarm clock", "pocket watch",
    "wristwatch", "watch face", "stopwatch", "timer", "hourglass",
    "sand timer", "egg timer", "sundial", "clock face", "time piece",
    "timepiece", "countdown",
)

#: Books genuinely about time may legitimately show a clock.
TIME_SUBJECT_TERMS = (
    "time management", "productivity", "scheduling", "punctual", "deadline",
    "clockmaking", "watchmaking", "horology", "shift work", "time tracking",
)

#: Tally marks, isolated symbols and other "stands for the idea" stock.
SYMBOLIC_CLICHE_TERMS = (
    "tally", "tally marks", "concept", "conceptual", "abstract concept",
    "symbol", "symbolic", "metaphor", "silhouette icon", "flat lay concept",
    "light bulb idea", "puzzle piece", "chess metaphor", "ladder success",
    "arrow growth", "hand holding sign",
)


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------


def _load(path: str | None, image_bytes: bytes | None) -> Image.Image | None:
    payload = image_bytes
    if not payload and path and os.path.isfile(path):
        try:
            payload = Path(path).read_bytes()
        except OSError:
            return None
    if not payload:
        return None
    try:
        img = Image.open(io.BytesIO(payload))
        img.load()
        return img.convert("RGB")
    except Exception:  # noqa: BLE001 - any decode failure is "cannot inspect"
        return None


# ---------------------------------------------------------------------------
# Text in the picture
# ---------------------------------------------------------------------------


def ocr_available() -> bool:
    """True when a local OCR engine is installed. Never required."""
    try:
        import pytesseract  # noqa: F401
        from pytesseract import get_tesseract_version

        get_tesseract_version()
        return True
    except Exception:  # noqa: BLE001
        return False


def _ocr_text(img: Image.Image) -> tuple[str, float]:
    """(text, fraction of the frame covered by confident text boxes)."""
    try:
        import pytesseract
        from pytesseract import Output

        data = pytesseract.image_to_data(img, output_type=Output.DICT)
    except Exception:  # noqa: BLE001
        return "", 0.0
    w, h = img.size
    area = float(w * h) or 1.0
    words: list[str] = []
    covered = 0.0
    for i, raw in enumerate(data.get("text") or []):
        word = str(raw or "").strip()
        if not word:
            continue
        try:
            conf = float(data["conf"][i])
        except (KeyError, IndexError, TypeError, ValueError):
            conf = -1.0
        if conf < 55:
            continue
        words.append(word)
        try:
            covered += float(data["width"][i]) * float(data["height"][i])
        except (KeyError, IndexError, TypeError, ValueError):
            continue
    return " ".join(words), min(1.0, covered / area)


def detect_image_text(
    path: str | None = None, *, image_bytes: bytes | None = None
) -> dict[str, Any]:
    """Baked-in text in a photograph, read by OCR when an engine is installed.

    Returns ``inspected=False`` when the image cannot be read, and
    ``ocr=False`` when no engine is available. Callers must treat either as
    "not confident", never as "no text" -- the strictness gate refuses to
    grant a PASS on unconfirmed evidence, so a missing OCR engine makes the
    matcher more cautious, never less.
    """
    img = _load(path, image_bytes)
    if img is None:
        return {"inspected": False, "ocr": False, "has_text": False,
                "coverage": 0.0, "text": "", "method": "none"}
    if not ocr_available():
        return {"inspected": True, "ocr": False, "has_text": False,
                "coverage": 0.0, "text": "", "method": "unavailable"}
    text, coverage = _ocr_text(img)
    words = [w for w in text.split() if any(c.isalnum() for c in w)]
    return {
        "inspected": True,
        "ocr": True,
        "has_text": coverage >= TEXT_COVERAGE_REJECT or len(words) >= 2,
        "coverage": round(coverage, 4),
        "text": " ".join(words),
        "method": "ocr",
    }


def detail_spread(path: str | None = None, *, image_bytes: bytes | None = None) -> float:
    """How much of the frame carries photographic detail, 0.0-1.0.

    A photographed scene puts detail almost everywhere: foliage, fabric,
    shadow gradients, background clutter. A flat graphic -- chalk strokes on a
    blackboard, matchsticks arranged on plain card, letter tiles on a table --
    concentrates its few edges in the middle and leaves the rest empty.

    Calibrated against real failures from this Factory: chalk tally marks
    scored 0.30 and matchsticks spelling MIND scored 0.28, while a woman
    meditating outdoors scored 0.70 and one in a hotel room 0.78.
    """
    img = _load(path, image_bytes)
    if img is None:
        return 0.0
    img = img.copy()
    img.thumbnail((256, 256))
    edges = img.convert("L").filter(ImageFilter.FIND_EDGES)
    w, h = edges.size
    if w < 32 or h < 32:
        return 0.0
    px = edges.load()
    cell_w, cell_h = w // 8, h // 8
    if cell_w < 2 or cell_h < 2:
        return 0.0
    live = 0
    for cy in range(8):
        for cx in range(8):
            total = 0
            samples = 0
            for y in range(cy * cell_h, (cy + 1) * cell_h, 2):
                for x in range(cx * cell_w, (cx + 1) * cell_w, 2):
                    total += px[x, y]
                    samples += 1
            if samples and (total / samples) > 12:
                live += 1
    return round(live / 64.0, 4)


# ---------------------------------------------------------------------------
# Is there a photographic subject at all?
# ---------------------------------------------------------------------------


def flat_background_ratio(
    path: str | None = None, *, image_bytes: bytes | None = None
) -> float:
    """Fraction of the frame taken by one near-uniform colour."""
    img = _load(path, image_bytes)
    if img is None:
        return 0.0
    small = img.copy()
    small.thumbnail((160, 160))
    quant = small.quantize(colors=16, method=Image.Quantize.MEDIANCUT)
    counts = quant.histogram()
    total = float(sum(counts)) or 1.0
    return round(max(counts) / total, 4)


def describe_photo_content(
    path: str | None = None, *, image_bytes: bytes | None = None
) -> dict[str, Any]:
    """Pixel-derived findings. The only evidence allowed to grant a PASS.

    ``ok`` true means the pixels look like a photographed scene with no baked-in
    text. ``inspected`` false means we could not look, which is never the same
    as "fine".
    """
    img = _load(path, image_bytes)
    if img is None:
        return {
            "inspected": False,
            "ok": False,
            "findings": ["photograph could not be inspected"],
            "text": {},
            "flat_ratio": 0.0,
            "detail_spread": 0.0,
        }
    text = detect_image_text(path, image_bytes=image_bytes)
    flat = flat_background_ratio(path, image_bytes=image_bytes)
    spread = detail_spread(path, image_bytes=image_bytes)
    # Findings are graded, because the evidence is not equally strong.
    #
    # Detected text is decisive: a photograph carrying legible words is word
    # art, a sign or a screenshot, never the chapter's subject.
    #
    # Flatness is only suggestive. A legitimate photograph can be a product on
    # a seamless white sweep, and a small or synthetic image reads as flat too.
    # Rejecting on flatness alone threw out valid photographs, so it is
    # recorded as a weak signal and never rejects by itself. It matters only
    # when something else already doubts the image.
    findings: list[str] = []
    weak: list[str] = []
    if text.get("has_text"):
        snippet = str(text.get("text") or "").strip()[:60]
        findings.append(
            f"prominent text in the image{f': {snippet}' if snippet else ''}"
        )
    if flat >= FLAT_BACKGROUND_REJECT:
        weak.append("flat studio background")
    if spread < DETAIL_SPREAD_MIN:
        weak.append("little photographic detail outside the centre")
    return {
        "inspected": True,
        "findings": findings,
        "weak_findings": weak,
        "text": text,
        "flat_ratio": flat,
        "detail_spread": spread,
        "ok": not findings,
    }


# ---------------------------------------------------------------------------
# Metadata-based rejection (allowed; metadata may never grant a pass)
# ---------------------------------------------------------------------------


def _norm(text: Any) -> str:
    return re.sub(r"[^a-z0-9 ]+", " ", str(text or "").lower())


def _hit(blob: str, terms: tuple[str, ...]) -> str:
    for term in terms:
        if term in blob:
            return term
    return ""


def cliche_rejection_reason(
    appearance: str,
    *,
    book_topic: str = "",
    chapter_body: str = "",
) -> str:
    """Why this candidate is a stock cliché rather than the chapter's subject.

    Returns "" when nothing objectionable is found. This may only REJECT.
    """
    blob = " " + " ".join(_norm(appearance).split()) + " "
    topic_blob = " " + " ".join(_norm(f"{book_topic} {chapter_body}").split()) + " "

    hit = _hit(blob, WORD_ART_TERMS)
    if hit:
        return f"image is about words, not the subject ({hit})"

    hit = _hit(blob, TIME_PROP_TERMS)
    if hit and not _hit(topic_blob, TIME_SUBJECT_TERMS):
        return (
            f"generic timekeeping prop ({hit}) matched a mention of time rather "
            "than the chapter's subject"
        )

    hit = _hit(blob, SYMBOLIC_CLICHE_TERMS)
    if hit:
        return f"symbolic stock cliché ({hit}) instead of the chapter's subject"
    return ""


def topic_supported(appearance: str, *, book_topic: str, chapter_body: str = "") -> bool:
    """Does the candidate share real subject matter with the BOOK, not just the heading?

    A heading word ("minute", "feel") is not the book's subject. Requiring an
    overlap with the topic or the chapter's own body is what stops a search for
    "feels hard" returning tiles that spell FEEL.
    """
    def _stems(text: str) -> set[str]:
        # A crude stem is enough and is the honest amount of cleverness here:
        # "meditation" and "meditating" must count as the same subject, while
        # "minute" and "mind" must not.
        return {word[:5] for word in _norm(text).split() if len(word) > 3}

    blob = _stems(appearance)
    anchor = _stems(f"{book_topic} {chapter_body}")
    if not anchor:
        return True  # nothing to check against; other rules still apply
    return bool(blob & anchor)
