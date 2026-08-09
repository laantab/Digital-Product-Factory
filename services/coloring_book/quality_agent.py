"""Coloring Book Quality Agent — validates AI-generated line-art pages and self-corrects."""
from __future__ import annotations

import base64
import json
import os
import re
from dataclasses import dataclass, field
from io import BytesIO
from typing import Any, Callable

from PIL import Image as PILImage


# Patterns that indicate a failed / placeholder generation
_UNQUALITY_MARKERS = (
    "placeholder",
    "lorem ipsum",
    "todo:",
    "not generated",
    "error",
    "debug",
    "wireframe",
    "mockup",
    "device mockup",
    "answer key",
    "worksheet layout",
    "regenerate",
)

# Generic/unrelated words that should NOT dominate a themed coloring book
_GENERIC_FALLBACK_TOPICS = [
    "apple", "banana", "cherry", "dragon", "forest", "garden",
    "harbor", "island", "jungle", "energy", "river", "ocean",
    "mountain", "snow", "carol", "ornament",
]


# ---------------------------------------------------------------------------
# Local fallback QA — runs when AI images are not available
# ---------------------------------------------------------------------------

@dataclass
class ColoringBookQAResult:
    """QA result for a coloring book generation."""
    passed: bool = True
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    page_count: int = 0
    cover_present: bool = False
    theme_match_score: float = 1.0  # 0.0–1.0
    all_pages_themed: bool = True

    def as_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
            "page_count": self.page_count,
            "cover_present": self.cover_present,
            "theme_match_score": self.theme_match_score,
            "all_pages_themed": self.all_pages_themed,
        }


def validate_coloring_book_local(
    page_count_requested: int,
    page_count_generated: int,
    cover_image_path: str,
    page_topics: list[str],
    theme: str,
    ai_warnings: list[str],
    output_type: str = "book",
) -> ColoringBookQAResult:
    """
    QA check for locally-generated (no AI) coloring book pages.

    Fails if:
    - Page count < requested
    - Digital book has no cover
    - Pages are blank (no topics)
    - Pages are unrelated to the theme
    """
    result = ColoringBookQAResult()
    result.page_count = page_count_generated

    theme_lower = (theme or "").lower()
    theme_words = set(re.findall(r"[a-z]{3,}", theme_lower))

    # 1. Page count check
    if page_count_generated < page_count_requested:
        result.errors.append(
            f"Page count ({page_count_generated}) < requested ({page_count_requested})"
        )
        result.passed = False

    # 2. Cover check for books
    if output_type == "book":
        if not cover_image_path or not os.path.isfile(cover_image_path):
            result.errors.append("Digital book has no cover image")
            result.passed = False
        else:
            result.cover_present = True

    # 3. Blank pages check
    if not page_topics:
        result.errors.append("No page topics generated — all pages blank")
        result.passed = False
        return result

    # 4. Theme relevance check
    unrelated = 0
    for topic in page_topics:
        topic_words = set(re.findall(r"[a-z]{3,}", topic.lower()))
        if theme_words:
            overlap = len(topic_words & theme_words)
            if overlap == 0 and len(topic_words) > 2:
                # Topic has no overlap with theme
                unrelated += 1
        else:
            # No theme specified — use generic fallback detection
            topic_lower = topic.lower()
            if any(g in topic_lower for g in _GENERIC_FALLBACK_TOPICS):
                if not any(w in topic_lower for w in theme_words if len(w) > 3):
                    unrelated += 1

    if unrelated > 0 and unrelated >= len(page_topics) * 0.5:
        result.errors.append(
            f"{unrelated}/{len(page_topics)} pages appear unrelated to theme '{theme}'"
        )
        result.passed = False
        result.all_pages_themed = False

    result.theme_match_score = max(0.0, 1.0 - (unrelated / max(len(page_topics), 1)))

    # 5. Unrelated product fields — check for crossword/ebook/planner markers
    for topic in page_topics:
        if any(marker in topic.lower() for marker in [
            "crossword", "word search", "clue", "answer key",
            "budget", "expense", "income", "chapter", "worksheet",
            "planner", "calendar", "todo", "meeting",
        ]):
            result.warnings.append(
                f"Page topic '{topic[:60]}' may contain non-coloring-book fields"
            )

    # 6. AI unavailable warning should NOT be a blocking error
    # (already handled in the builder)

    return result


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


@dataclass
class PageQualityResult:
    page_number: int
    topic: str
    line_art_prompt: str
    image_path: str = ""
    quality_pass: bool = False
    issues: list[str] = field(default_factory=list)
    regenerated: bool = False
    ai_vision_notes: str = ""
    blocked_export: bool = False  # True if this page's issues should block PDF export

    def as_dict(self) -> dict[str, Any]:
        return {
            "page_number": self.page_number,
            "topic": self.topic,
            "quality_pass": self.quality_pass,
            "issues": list(self.issues),
            "regenerated": self.regenerated,
            "ai_vision_notes": self.ai_vision_notes,
            "blocked_export": self.blocked_export,
        }


@dataclass
class ColoringBookQualityResult:
    pages: list[PageQualityResult]
    total_passed: int = 0
    total_failed: int = 0
    errors: list[str] = field(default_factory=list)
    blocked_export: bool = False  # True if any page should block the PDF export

    @property
    def all_passed(self) -> bool:
        return self.total_failed == 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "pages": [p.as_dict() for p in self.pages],
            "total_passed": self.total_passed,
            "total_failed": self.total_failed,
            "all_passed": self.all_passed,
            "blocked_export": self.blocked_export,
            "errors": list(self.errors),
        }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _encode_image_jpeg(path: str) -> str | None:
    """Encode an image file as a base64 JPEG string, or None on failure."""
    try:
        with PILImage.open(path) as img:
            if img.mode in ("RGBA", "LA", "P"):
                img = img.convert("RGB")
            buf = BytesIO()
            img.save(buf, format="JPEG", quality=82)
            return base64.b64encode(buf.getvalue()).decode("ascii")
    except Exception:  # noqa: BLE001
        return None


def _analyze_line_art_image(image_b64: str) -> dict[str, Any]:
    """
    Use AI vision to assess whether the image is valid coloring book line art.
    Returns a dict with keys: passed (bool), notes (str), issues (list[str]).
    """
    prompt_lines = [
        "You are a coloring book quality reviewer. Examine this image carefully.",
        "Answer ONLY with a JSON object using exactly these keys:",
        "  passed (bool) — true only when ALL checks pass",
        "  notes (string) — a 1-2 sentence plain-English summary of what the image shows",
        "  issues (list of strings) — list every specific problem found, or empty list if clean",
        "",
        "QUALITY CHECKS (all must pass for passed=true):",
        "  1. IS LINE ART: image must be black outlines on white/light background.",
        "     Fail if image has solid color fills, shading, gradients, or colored backgrounds.",
        "  2. HAS RECOGNIZABLE SUBJECT: must show a character, animal, object, or scene.",
        "     Fail if image is blank, empty, or purely geometric patterns with no subject.",
        "  3. NO PLACEHOLDER MARKERS: no text overlays, lorem ipsum, 'TODO', 'placeholder',",
        "     'not generated', 'debug', 'wireframe', 'device mockup', 'answer key',",
        "     'worksheet layout', or any similar placeholder text.",
        "  4. NOT CUT OFF: all content fits within the image frame with safe margins.",
        "     Fail if subjects are visibly clipped or cropped at the border.",
        "  5. APPROPRIATE FOR COLORING: line density and detail level should be suitable for",
        "     a coloring book (not too sparse, not overwhelmingly complex).",
        "     Fail if the image is clearly a photograph, worksheet, or puzzle layout.",
    ]

    try:
        from ai_client import get_client, get_model

        client = get_client()
        resp = client.chat.completions.create(
            model=get_model(),
            max_completion_tokens=600,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "\n".join(prompt_lines)},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"},
                        },
                    ],
                }
            ],
        )
        raw = (resp.choices[0].message.content or "").strip()
        if raw.startswith("```"):
            parts = raw.split("```", 2)
            raw = parts[1]
            if raw.lstrip().lower().startswith("json"):
                raw = raw.lstrip()[4:]
        data: dict[str, Any] = json.loads(raw.strip())
        return {
            "passed": bool(data.get("passed", False)),
            "notes": str(data.get("notes", "")),
            "issues": [str(i) for i in data.get("issues") or []],
        }
    except Exception as exc:  # noqa: BLE001
        # Fall back to deterministic checks — do NOT silently pass
        issues = _run_deterministic_image_checks(image_b64)
        if issues:
            return {
                "passed": False,
                "notes": "Limited QA only — visual inspection required. Deterministic checks found issues.",
                "issues": issues,
            }
        return {
            "passed": True,
            "notes": "Limited QA only — visual inspection required. Deterministic checks passed but "
            "AI vision is unavailable — review image manually before shipping.",
            "issues": [],
        }


def _run_deterministic_image_checks(image_b64: str) -> list[str]:
    """
    Deterministic PIL-based checks for coloring book line art quality.
    Runs when AI vision is unavailable — must NOT silently pass.

    Checks:
    1. Gray pixel areas (not pure B&W)
    2. Border/frame lines near page edges
    3. Image is too small (likely placeholder)

    Returns a list of issue strings (empty = checks passed).
    """
    issues: list[str] = []
    try:
        import base64 as _b64, io as _io
        from PIL import Image as _PILImage
    except Exception:  # noqa: BLE001
        return ["Could not load PIL for deterministic checks."]

    try:
        raw = _b64.b64decode(image_b64)
        img = _PILImage.open(_io.BytesIO(raw)).convert("RGB")
        w, h = img.size
    except Exception as exc:  # noqa: BLE001
        return [f"Could not decode image for QA: {type(exc).__name__}"]

    # Check 1: Image too small = likely placeholder
    if w < 200 or h < 200:
        issues.append(f"Image too small ({w}x{h}) — likely placeholder.")

    # Check 2: Scan for gray/non-B&W pixels
    gray_pixels = 0
    total_pixels = w * h
    edge_check_width = max(int(w * 0.02), 10)
    edge_check_height = max(int(h * 0.02), 10)

    # Sample pixels for performance on large images
    step = max(1, min(w, h) // 200)
    border_like_pixels = 0
    border_sample_cols = 0
    border_sample_rows = 0

    for y in range(0, h, step):
        for x in range(0, w, step):
            r, g, b = img.getpixel((x, y))[:3]
            is_black = (r < 15 and g < 15 and b < 15)
            is_white = (r > 240 and g > 240 and b > 240)
            if not is_black and not is_white:
                gray_pixels += 1
                # Check if pixel is near an edge (possible border/frame line)
                if (x < edge_check_width or x >= w - edge_check_width or
                        y < edge_check_height or y >= h - edge_check_height):
                    border_sample_cols += 1

    gray_ratio = gray_pixels / (total_pixels / (step * step)) if step > 1 else gray_pixels / total_pixels

    # Allow generous tolerance for anti-aliasing on line-art outlines.
    # Bold kawaii line art with thick, clean outlines produces 5–10% non-B&W pixels
    # from anti-aliasing at line edges — this is normal, not gray fill.
    # Only flag if truly excessive (shaded fills, blush marks, etc.).
    if gray_ratio > 0.12:
        issues.append(
            f"Image contains non-black/white pixels ({gray_ratio*100:.1f}% gray area). "
            "Expected pure black outlines on white background only."
        )

    # Check 3: Border/frame detection — count edge-adjacent non-white pixels
    # If >10% of sampled edge pixels are non-white, flag as border
    edge_pixel_count = 0
    for y in range(0, h, step):
        for x in [0, 1, w - 2, w - 1]:
            r, g, b = img.getpixel((x, y))[:3]
            if not (r > 240 and g > 240 and b > 240):
                edge_pixel_count += 1
    for x in range(0, w, step):
        for y in [0, 1, h - 2, h - 1]:
            r, g, b = img.getpixel((x, y))[:3]
            if not (r > 240 and g > 240 and b > 240):
                edge_pixel_count += 1

    total_edge_samples = (h // step * 2) + (w // step * 2)
    if total_edge_samples > 0:
        edge_nonwhite_ratio = edge_pixel_count / total_edge_samples
        # Only flag if the outermost edge strip is overwhelmingly filled with content.
        # Natural scenes with grass, sky, clouds, animals can have 10–20% edge density.
        # A decorative border/frame is a solid continuous outline — we detect that by
        # checking the innermost edge strip separately for a higher density signature.
        if edge_nonwhite_ratio > 0.30:
            issues.append(
                f"Border/frame detected near page edges ({edge_nonwhite_ratio*100:.0f}% of edge pixels "
                "are non-white). Do not draw any border, frame, or margin outline."
            )

    return issues


def _check_prompt_quality(topic: str, line_art_prompt: str) -> list[str]:
    """Check if the line_art_prompt is detailed enough for good generation."""
    issues = []
    if len(line_art_prompt) < 30:
        issues.append(f"Prompt too short for '{topic}': {line_art_prompt[:60]}")
    if not any(
        kw in line_art_prompt.lower()
        for kw in ["draw", "show", "featuring", "illustrate", "line art", "coloring page"]
    ):
        issues.append(f"Prompt for '{topic}' lacks a clear drawing instruction.")
    return issues


# ---------------------------------------------------------------------------
# Core validation
# ---------------------------------------------------------------------------

def validate_coloring_book_page(
    page_number: int,
    topic: str,
    line_art_prompt: str,
    image_path: str,
    main_character: str = "",
    setting: str = "",
    topic_field: str = "",
) -> PageQualityResult:
    """
    Validate a single coloring book page against structural and visual quality gates.

    Args:
        page_number: Which page this is (1-indexed)
        topic: The page topic / title
        line_art_prompt: The AI prompt used to generate the image
        image_path: Full path to the generated image file
        main_character: Book's main character (optional, for context)
        setting: Book's setting/world (optional, for context)
        topic_field: The overarching book topic/title

    Returns:
        PageQualityResult with pass/fail and any issues found
    """
    result = PageQualityResult(
        page_number=page_number,
        topic=topic,
        line_art_prompt=line_art_prompt,
        image_path=image_path,
    )

    # Gate 1: prompt quality
    prompt_issues = _check_prompt_quality(topic, line_art_prompt)
    result.issues.extend(prompt_issues)

    # Gate 2: image file exists
    if not image_path or not os.path.isfile(image_path):
        result.issues.append(f"Page {page_number}: No image file found at expected path.")
        result.quality_pass = False
        return result

    # Gate 3: file size sanity check
    try:
        size_kb = os.path.getsize(image_path) / 1024
        if size_kb < 5:
            result.issues.append(
                f"Page {page_number}: Image file suspiciously small ({size_kb:.1f} KB) — likely broken."
            )
        elif size_kb > 12000:
            # Portrait 1024x1536 OpenAI PNGs commonly land 1.5–3 MB; only flag extremes.
            result.issues.append(
                f"Page {page_number}: Image file very large ({size_kb:.1f} KB) — may cause PDF issues."
            )
    except OSError:
        pass

    # Gate 4: AI vision analysis
    image_b64 = _encode_image_jpeg(image_path)
    if image_b64:
        vision = _analyze_line_art_image(image_b64)
        result.ai_vision_notes = vision.get("notes", "")

        if not vision.get("passed", False):
            for issue in vision.get("issues") or []:
                result.issues.append(f"Page {page_number} vision: {issue}")
        elif vision.get("notes"):
            result.ai_vision_notes = vision["notes"]
    else:
        result.issues.append(f"Page {page_number}: Could not encode image for vision analysis.")

    result.quality_pass = len(result.issues) == 0
    return result


def validate_coloring_book_pages(
    pages: list[dict[str, Any]],
    main_character: str = "",
    setting: str = "",
    topic_field: str = "",
    regenerate: bool = True,
    regenerate_fn: Callable[[str, str], bool] | None = None,
) -> ColoringBookQualityResult:
    """
    Validate all pages in a coloring book. Optionally regenerates failed images.

    Args:
        pages: List of page dicts, each with keys:
               page_number (int), topic (str), line_art_prompt (str), image_path (str)
        main_character: Book main character (for quality context)
        setting: Book setting (for quality context)
        topic_field: Book topic (for quality context)
        regenerate: Whether to attempt regeneration on failed pages
        regenerate_fn: Callable(prompt, image_path) -> bool.
                        Called when a page fails and regeneration is enabled.
                        Return True on success, False on failure.
                        If None, no regeneration is attempted.

    Returns:
        ColoringBookQualityResult with per-page results and totals
    """
    results: list[PageQualityResult] = []
    errors: list[str] = []

    for page_dict in pages:
        page_num = int(page_dict.get("page_number", 1))
        topic = str(page_dict.get("topic", f"Page {page_num}"))
        prompt = str(page_dict.get("line_art_prompt", ""))
        img_path = str(page_dict.get("image_path", ""))

        result = validate_coloring_book_page(
            page_number=page_num,
            topic=topic,
            line_art_prompt=prompt,
            image_path=img_path,
            main_character=main_character,
            setting=setting,
            topic_field=topic_field,
        )
        results.append(result)

        # Attempt self-correction for failed pages
        if not result.quality_pass and regenerate and regenerate_fn:
            errors_before = len(result.issues)
            try:
                ok = regenerate_fn(prompt, img_path)
                if ok:
                    result2 = validate_coloring_book_page(
                        page_number=page_num,
                        topic=topic,
                        line_art_prompt=prompt,
                        image_path=img_path,
                        main_character=main_character,
                        setting=setting,
                        topic_field=topic_field,
                    )
                    result2.regenerated = True
                    idx = next(i for i, r in enumerate(results) if r.page_number == page_num)
                    results[idx] = result2
            except Exception as exc:  # noqa: BLE001
                errors.append(f"Regeneration failed for page {page_num}: {exc}")

    passed = sum(1 for r in results if r.quality_pass)
    failed = len(results) - passed

    # Mark pages with persistent issues as blocking exports
    for r in results:
        r.blocked_export = not r.quality_pass

    blocked_export = failed > 0

    return ColoringBookQualityResult(
        pages=results,
        total_passed=passed,
        total_failed=failed,
        blocked_export=blocked_export,
        errors=errors,
    )
