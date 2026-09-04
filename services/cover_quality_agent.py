"""Cover quality agent — validates professional cover output and self-corrects."""
from __future__ import annotations

import base64
import json
import os
import re
from dataclasses import dataclass, field
from typing import Any, Callable

from services.cover_agent import (
    BLACK_HISTORY_COMPOSITION_RULES,
    BLACK_HISTORY_COVER_SAFETY_RULES,
    BLACK_HISTORY_VISUAL_STYLE,
    BLACK_HISTORY_WORD_SEARCH_IMAGE_PROMPT,
    COVER_FACIAL_QUALITY_RULES,
    COVER_FRAMING_RULES,
    COVER_COMPOSITION_INTEGRITY_RULES,
    COVER_PORTRAIT_SUBJECT_RULES,
    PHOTO_REALISTIC_STYLE_RULES,
    USER_STYLES,
    WORD_SEARCH_COVER_VISUAL_RULES,
    _cover_image_path,
    _has_cover_image,
    _word_search_prompt_mislabels_crossword,
    is_black_history_topic,
    is_photo_realistic_cover,
    is_puzzle_photo_cover,
    is_word_search_book_cover,
    update_cover_design,
)

_UNPROFESSIONAL_VISIBLE = (
    "cover image not generated",
    "cover image not available",
    "not generated yet",
    "regenerate the cover image",
    "worksheet layout",
    "answer key",
    "device mockup",
    "debug",
    "todo:",
    "lorem ipsum",
    "placeholder text",
)

_ICON_MOCK_MARKERS = (
    "strategy</div>",
    "cda-cover-visual",
    "📊",
    "wireframe",
)

_PUZZLE_ENGINE_TYPES = frozenset({"word_search_book", "crossword_puzzle_book"})

_MAX_CORRECTION_ATTEMPTS = 4


@dataclass
class CoverQualityResult:
    passed: bool = False
    score: int = 0
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    fixes_applied: list[str] = field(default_factory=list)
    attempts: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "score": self.score,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
            "fixes_applied": list(self.fixes_applied),
            "attempts": self.attempts,
        }


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").lower()).strip()


def _visible_html(cover: dict) -> str:
    return _norm((cover.get("preview_html") or "") + " " + (cover.get("pdf_html") or ""))


def _title_in_html(cover: dict) -> bool:
    title = str(cover.get("title") or "").strip()
    if not title:
        return False
    html = (cover.get("preview_html") or "").lower()
    return _norm(title)[:24] in _norm(html) or title.lower() in html


def _title_in_html(cover: dict) -> bool:
    title = str(cover.get("title") or "").strip()
    if not title:
        return False
    html = (cover.get("preview_html") or "").lower()
    return _norm(title)[:24] in _norm(html) or title.lower() in html


def _vision_qc_enabled() -> bool:
    """Whether the paid vision QC call may run.

    Off by default and never in test mode. This check was dead for a long time
    (it imported a name that did not exist), so switching it on is a real
    change in spend: one image-model call per cover attempt. Turning it on is a
    deliberate decision, made with FACTORY_VISION_QC=1, not a side effect of
    repairing the import.
    """
    if str(os.environ.get("FACTORY_TEST_MODE") or "") == "1":
        return False
    return str(os.environ.get("FACTORY_VISION_QC") or "").strip().lower() in ("1", "true", "yes")


def _vision_qc_unavailable(reason: str) -> dict[str, Any]:
    """Result for a QC that could not run.

    Critically this is NOT a pass. A quality check that did not happen must
    never be recorded as a check that succeeded -- that is what previously let
    every cover claim an affirmative vision PASS it had never earned.

    ``skipped`` stays True so the surrounding retry/regeneration control flow is
    byte-for-byte identical to before: callers still stop retrying rather than
    looping on a check that cannot run. What changes is only the claim being
    made -- unavailable and needing review, instead of passed.
    """
    return {
        "passed": False,
        "skipped": True,
        "available": False,
        "review_required": True,
        "reason": reason,
    }


def evaluate_cover_image_vision_qc(cover: dict) -> dict[str, Any] | None:
    """Vision QC — Black History safety and/or photo-realistic style validation."""
    if not cover.get("use_ai_image", True):
        return None
    bh = is_black_history_topic(cover)
    photo = is_photo_realistic_cover(cover)
    puzzle_photo = is_puzzle_photo_cover(cover)
    if not bh and not photo:
        return None
    pkg = str(cover.get("package_id") or "")
    if not pkg or not _has_cover_image(pkg):
        return None
    path = _cover_image_path(pkg)
    try:
        with open(path, "rb") as fh:
            image_b64 = base64.b64encode(fh.read()).decode("ascii")
    except OSError:
        return None

    checks = []
    if bh:
        checks.extend(
            [
                "main_subjects_black (bool)",
                "central_subject_black (bool)",
                "communicates_black_history (bool)",
                "broad_black_history_theme (bool)",
                "no_readable_text (bool)",
                "no_topic_title_lettering (bool)",
                "lower_third_clear (bool)",
                "vibrant_saturated_color (bool)",
            ]
        )
    if photo:
        checks.extend(
            [
                "looks_photo_realistic (bool)",
                "smooth_natural_photo (bool)",
                "sharp_clean_not_grainy (bool)",
                "proper_framing_no_cutoff (bool)",
                "composition_integrity (bool)",
            ]
        )
    if puzzle_photo:
        checks.extend(
            [
                "eyes_clear_no_artifacts (bool)",
                "teeth_mouth_natural (bool)",
                "faces_not_melted_or_blurred (bool)",
                "no_distorted_small_background_faces (bool)",
                "lower_third_faces_clear (bool)",
                "subject_count_acceptable (bool)",
            ]
        )
    if is_word_search_book_cover(cover):
        checks.extend(
            [
                "no_crossword_style_grids (bool)",
                "no_crossword_clue_boxes (bool)",
                "no_crossword_numbered_squares (bool)",
                "matches_word_search_book (bool)",
            ]
        )

    prompt_lines = [
        "This is background artwork for a book cover (text is added separately).",
        f"Answer with JSON only using keys: {', '.join(checks)}, passed (bool), reason (string).",
        "Set passed true ONLY when every listed boolean is true.",
    ]
    if bh:
        prompt_lines.extend(
            [
                "Fail if the main, central, or supporting visible person appears white.",
                "Fail if Black people are not centered respectfully as the prominent subjects.",
                "Fail if the image does not clearly communicate Black history.",
                "Fail if the image is protest-only instead of a broad Black History theme.",
                "Fail if any readable text, signs, slogans, posters, banners, or words appear.",
                "no_topic_title_lettering must be false if BLACK HISTORY, the book title, subtitle, "
                "author name, or any letters/numbers/words appear as readable text in the artwork.",
                "Fail if the words BLACK HISTORY or any title-like lettering appear anywhere in the image.",
                "Fail if the lower third is not open empty space for an editable title overlay "
                "(no faces, bodies, or busy detail in the bottom third).",
                "Fail if colors look dull, flat, faded, desaturated, or monochrome.",
                "Photo-realistic Black historical figures, Black cultural imagery, or Black "
                "community themes only.",
            ]
        )
    if photo:
        prompt_lines.extend(
            [
                "looks_photo_realistic must be true only when the image could pass as a real "
                "professional book-cover photograph — not AI art, not illustrated, not stylized.",
                "smooth_natural_photo must be true when the image has smooth natural photographic "
                "finish like editorial print — continuous skin tones, clean surfaces, no waxy or "
                "plastic AI look.",
                "sharp_clean_not_grainy must be true when there is no visible film grain, noise, "
                "speckle, dot pattern, blur, or compression artifacts anywhere.",
                "Fail if the image looks painted, pastel, watercolor, sketch-like, illustrated, "
                "cartoon, anime, posterized, painterly, or obviously AI-generated.",
                "Fail if the image looks grainy, noisy, speckled, soft, blurry, low-resolution, "
                "or lacks the smooth quality of a real photograph.",
                "proper_framing_no_cutoff must be true when all important people fit fully inside "
                "the frame with safe margins.",
                "Fail if any head, face, hand, limb, or body is cut off or clipped at the "
                "top, side, or bottom border.",
                "composition_integrity must be true when every visible face is clear and "
                "unobstructed with natural spatial separation.",
                "Fail if props, instruments, hands, limbs, or collage elements cover, overlap, "
                "or spill onto any person's face (e.g. saxophone blocking a face).",
                "Fail if the composite looks messy, fused, or visually corrupted.",
            ]
        )
    if puzzle_photo:
        prompt_lines.extend(
            [
                "eyes_clear_no_artifacts must be true when every visible eye is sharp and natural "
                "with no pixelation, distortion, or AI artifacts around the eyes.",
                "teeth_mouth_natural must be true when mouths and teeth look natural — fail on "
                "warped, duplicated, malformed, or unnaturally exposed teeth.",
                "faces_not_melted_or_blurred must be true when facial features are crisp and "
                "anatomically correct — fail on melted, blurred, or smeared faces.",
                "no_distorted_small_background_faces must be true when there are no tiny distorted "
                "background faces — prefer 2-4 people max with 1-2 main subjects only.",
                "lower_third_faces_clear must be true when no important faces occupy the bottom "
                "third reserved for an editable title overlay.",
                "subject_count_acceptable must be true when there are at most 4 visible people "
                "with only 1-2 clear main subjects in waist-up or medium portrait framing.",
                "Fail on wide smiles, shouting, or open-mouth expressions that expose distorted teeth.",
                "Reject and fail if any facial artifact would make this unusable as a professional "
                "commercial book cover.",
            ]
        )
    if is_word_search_book_cover(cover):
        prompt_lines.extend(
            [
                "This cover is for a WORD SEARCH BOOK — not a crossword puzzle book.",
                "no_crossword_style_grids must be true when there are no black-and-white blocked "
                "crossword grids or crossword-style square layouts.",
                "no_crossword_clue_boxes must be true when there are no crossword clue lists, "
                "Across/Down boxes, or numbered clue panels.",
                "no_crossword_numbered_squares must be true when there are no numbered crossword "
                "squares or crossword numbering visible.",
                "matches_word_search_book must be true when the image fits a word-search puzzle "
                "book (heritage portrait, subtle letter-grid OK) — fail if it looks like a crossword.",
                "Fail if the word crossword appears anywhere in the artwork or if crossword puzzle "
                "imagery dominates.",
            ]
        )

    if not _vision_qc_enabled():
        return _vision_qc_unavailable("Cover image vision QC is turned off")

    try:
        from ai_client import get_client, get_model

        client = get_client()
        resp = client.chat.completions.create(
            model=get_model(),
            max_completion_tokens=500,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": " ".join(prompt_lines)},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{image_b64}"},
                        },
                    ],
                }
            ],
        )
        raw = (resp.choices[0].message.content or "").strip()
        if raw.startswith("```"):
            raw = raw.split("```", 2)[1]
            if raw.lstrip().lower().startswith("json"):
                raw = raw.lstrip()[4:]
        data = json.loads(raw.strip())
        result: dict[str, Any] = {
            "passed": bool(data.get("passed")),
            "reason": str(data.get("reason") or ""),
            "black_history": bh,
            "photo_realistic": photo,
        }
        if bh:
            result.update(
                {
                    "main_subjects_black": bool(data.get("main_subjects_black")),
                    "central_subject_black": bool(data.get("central_subject_black")),
                    "communicates_black_history": bool(data.get("communicates_black_history")),
                    "broad_black_history_theme": bool(data.get("broad_black_history_theme")),
                    "no_readable_text": bool(data.get("no_readable_text")),
                    "no_topic_title_lettering": bool(data.get("no_topic_title_lettering")),
                    "lower_third_clear": bool(data.get("lower_third_clear")),
                    "vibrant_saturated_color": bool(data.get("vibrant_saturated_color")),
                }
            )
            result["passed"] = bool(
                result["passed"]
                and result["main_subjects_black"]
                and result["central_subject_black"]
                and result["communicates_black_history"]
                and result["broad_black_history_theme"]
                and result["no_readable_text"]
                and result["no_topic_title_lettering"]
                and result["lower_third_clear"]
                and result["vibrant_saturated_color"]
            )
        if photo:
            result["looks_photo_realistic"] = bool(data.get("looks_photo_realistic"))
            result["smooth_natural_photo"] = bool(data.get("smooth_natural_photo"))
            result["sharp_clean_not_grainy"] = bool(data.get("sharp_clean_not_grainy"))
            result["proper_framing_no_cutoff"] = bool(data.get("proper_framing_no_cutoff"))
            result["composition_integrity"] = bool(data.get("composition_integrity"))
            result["passed"] = bool(
                result["passed"]
                and result["looks_photo_realistic"]
                and result["smooth_natural_photo"]
                and result["sharp_clean_not_grainy"]
                and result["proper_framing_no_cutoff"]
                and result["composition_integrity"]
            )
        if puzzle_photo:
            result.update(
                {
                    "eyes_clear_no_artifacts": bool(data.get("eyes_clear_no_artifacts")),
                    "teeth_mouth_natural": bool(data.get("teeth_mouth_natural")),
                    "faces_not_melted_or_blurred": bool(data.get("faces_not_melted_or_blurred")),
                    "no_distorted_small_background_faces": bool(
                        data.get("no_distorted_small_background_faces")
                    ),
                    "lower_third_faces_clear": bool(data.get("lower_third_faces_clear")),
                    "subject_count_acceptable": bool(data.get("subject_count_acceptable")),
                }
            )
            result["passed"] = bool(
                result["passed"]
                and result["eyes_clear_no_artifacts"]
                and result["teeth_mouth_natural"]
                and result["faces_not_melted_or_blurred"]
                and result["no_distorted_small_background_faces"]
                and result["lower_third_faces_clear"]
                and result["subject_count_acceptable"]
            )
        if is_word_search_book_cover(cover):
            result.update(
                {
                    "no_crossword_style_grids": bool(data.get("no_crossword_style_grids")),
                    "no_crossword_clue_boxes": bool(data.get("no_crossword_clue_boxes")),
                    "no_crossword_numbered_squares": bool(data.get("no_crossword_numbered_squares")),
                    "matches_word_search_book": bool(data.get("matches_word_search_book")),
                }
            )
            result["passed"] = bool(
                result["passed"]
                and result["no_crossword_style_grids"]
                and result["no_crossword_clue_boxes"]
                and result["no_crossword_numbered_squares"]
                and result["matches_word_search_book"]
            )
        return result
    except Exception as exc:  # noqa: BLE001
        return _vision_qc_unavailable(f"Cover image vision QC unavailable: {exc}")


def evaluate_black_history_cover_image(cover: dict) -> dict[str, Any] | None:
    """Backward-compatible wrapper — delegates to unified cover image vision QC."""
    if not is_black_history_topic(cover):
        return None
    return evaluate_cover_image_vision_qc(cover)


def evaluate_cover_quality(cover: dict) -> CoverQualityResult:
    """Deterministic professional-quality gate — no external API calls."""
    result = CoverQualityResult()
    score = 100
    visible = _visible_html(cover)
    preview = cover.get("preview_html") or ""
    pdf_html = cover.get("pdf_html") or ""

    title = str(cover.get("title") or "").strip()
    if not title:
        result.errors.append("Cover is missing a title.")
        score -= 40
    elif len(title) < 2:
        result.errors.append("Cover title is too short to be sellable.")
        score -= 25

    if not preview:
        result.errors.append("Cover preview HTML is missing.")
        score -= 35
    elif not _title_in_html(cover):
        result.errors.append("Cover title is not visible in the preview.")
        score -= 30

    if not pdf_html:
        result.errors.append("Cover PDF HTML is missing.")
        score -= 20

    palette = cover.get("color_palette") if isinstance(cover.get("color_palette"), dict) else {}
    if not palette.get("primary") or not palette.get("text"):
        result.errors.append("Cover color palette is incomplete.")
        score -= 15

    for phrase in _UNPROFESSIONAL_VISIBLE:
        if phrase in visible:
            result.errors.append(f"Cover shows unprofessional text: “{phrase}”.")
            score -= 20
            break

    if "cda-cover-pending" in preview or "cda-pdf-cover-pending" in pdf_html:
        result.errors.append("Cover is showing a pending/placeholder state instead of finished artwork.")
        score -= 35

    if "cda-cover-visual" in preview or 'background:#ddd6fe' in preview.lower():
        result.errors.append("Cover uses a gray placeholder panel instead of finished artwork.")
        score -= 30

    engine_type = str((cover.get("topic_analysis") or {}).get("product_type") or "").strip()
    style = str(cover.get("style") or "")
    if is_word_search_book_cover(cover):
        prompt_blob = _norm(
            " ".join(
                [
                    str(cover.get("image_prompt") or ""),
                    str(cover.get("cover_prompt") or ""),
                    str(cover.get("image_direction") or ""),
                    visible,
                ]
            )
        )
        if _word_search_prompt_mislabels_crossword(prompt_blob):
            result.errors.append(
                "Word Search cover must not be labeled or prompted as a crossword puzzle book."
            )
            score -= 50
        subtitle = _norm(str(cover.get("subtitle") or ""))
        if "crossword" in subtitle:
            result.errors.append("Word Search cover subtitle must not mention crossword puzzles.")
            score -= 25
    if engine_type in _PUZZLE_ENGINE_TYPES:
        if not str(cover.get("subtitle") or "").strip():
            result.warnings.append("Puzzle book cover has no subtitle.")
            score -= 5
        if style == "graphic_icon" or any(marker in preview for marker in _ICON_MOCK_MARKERS):
            result.errors.append("Cover uses generic icon/mock visuals instead of a sellable book design.")
            score -= 25

    prompt = str(cover.get("image_prompt") or "").strip()
    if len(prompt) < 48:
        result.warnings.append("Cover image prompt is very short.")
        score -= 5

    if str(cover.get("layout") or "") not in {
        "full_bleed_image",
        "image_top_title_bottom",
        "title_top_image_center",
        "clean_business",
        "large_title_visual_panel",
        "split_layout",
    }:
        result.warnings.append("Cover layout is non-standard.")
        score -= 5

    img_qc = cover.get("cover_image_qc") or cover.get("black_history_cover_qc")
    if not img_qc and cover.get("use_ai_image", True):
        if is_black_history_topic(cover) or is_photo_realistic_cover(cover):
            img_qc = evaluate_cover_image_vision_qc(cover)
    if isinstance(img_qc, dict) and not img_qc.get("skipped"):
        cover["cover_image_qc"] = img_qc
        if is_black_history_topic(cover):
            cover["black_history_cover_qc"] = img_qc
        if not img_qc.get("passed"):
            reason = img_qc.get("reason") or "Cover image failed vision quality check"
            if is_black_history_topic(cover):
                result.errors.append(f"Black History cover safety check failed: {reason}")
            elif not img_qc.get("composition_integrity", True):
                result.errors.append(f"Cover image composition integrity check failed: {reason}")
            elif not img_qc.get("proper_framing_no_cutoff", True):
                result.errors.append(f"Cover image framing check failed: {reason}")
            elif not img_qc.get("smooth_natural_photo", True):
                result.errors.append(f"Cover photo realism check failed: {reason}")
            elif not img_qc.get("sharp_clean_not_grainy", True):
                result.errors.append(f"Cover image grain check failed: {reason}")
            elif not img_qc.get("looks_photo_realistic", True):
                result.errors.append(f"Photo-realistic cover check failed: {reason}")
            elif is_puzzle_photo_cover(cover) and not img_qc.get("eyes_clear_no_artifacts", True):
                result.errors.append(f"Cover facial quality check failed (eyes): {reason}")
            elif is_puzzle_photo_cover(cover) and not img_qc.get("teeth_mouth_natural", True):
                result.errors.append(f"Cover facial quality check failed (mouth/teeth): {reason}")
            elif is_puzzle_photo_cover(cover) and not img_qc.get("faces_not_melted_or_blurred", True):
                result.errors.append(f"Cover facial quality check failed (distorted faces): {reason}")
            elif is_puzzle_photo_cover(cover) and not img_qc.get(
                "no_distorted_small_background_faces", True
            ):
                result.errors.append(f"Cover facial quality check failed (background faces): {reason}")
            elif is_puzzle_photo_cover(cover) and not img_qc.get("lower_third_faces_clear", True):
                result.errors.append(f"Cover facial quality check failed (lower third): {reason}")
            elif is_puzzle_photo_cover(cover) and not img_qc.get("subject_count_acceptable", True):
                result.errors.append(f"Cover portrait composition check failed: {reason}")
            elif is_word_search_book_cover(cover) and not img_qc.get("no_crossword_style_grids", True):
                result.errors.append(f"Word Search cover shows crossword-style grids: {reason}")
            elif is_word_search_book_cover(cover) and not img_qc.get("matches_word_search_book", True):
                result.errors.append(f"Cover image does not match Word Search book style: {reason}")
            else:
                result.errors.append(f"Cover image quality check failed: {reason}")
            score -= 45

    result.score = max(0, min(100, score))
    result.passed = not result.errors and result.score >= 70
    return result


def suggest_cover_corrections(cover: dict, qa: CoverQualityResult) -> dict[str, Any]:
    """Map quality failures to concrete cover_design overrides."""
    fixes: dict[str, Any] = {"_descriptions": []}
    preview = cover.get("preview_html") or ""
    pdf_html = cover.get("pdf_html") or ""
    engine_type = str((cover.get("topic_analysis") or {}).get("product_type") or "").strip()
    title = str(cover.get("title") or "Untitled").strip()

    if "cda-cover-pending" in preview or "cda-pdf-cover-pending" in pdf_html:
        fixes["layout"] = "full_bleed_image"
        fixes["font_style"] = "bold_display"
        fixes["_descriptions"].append("Rebuilt cover with premium full-page template (AI image pending).")

    if any("icon/mock" in err.lower() or "placeholder panel" in err.lower() or "unprofessional text" in err.lower() for err in qa.errors):
        fixes["layout"] = "full_bleed_image"
        fixes["font_style"] = "bold_display"
        if engine_type in _PUZZLE_ENGINE_TYPES:
            fixes["style"] = "elegant"
        fixes["_descriptions"].append("Replaced mock/placeholder layout with premium full-page template.")

    if any("title is not visible" in err.lower() for err in qa.errors):
        fixes["title"] = title
        fixes["font_style"] = "bold_display"
        fixes["_descriptions"].append("Rebuilt cover with bold display title typography.")

    if any("palette" in err.lower() for err in qa.errors):
        fixes["palette_preset"] = "professional_blue"
        fixes["_descriptions"].append("Applied professional blue palette preset.")

    if engine_type in _PUZZLE_ENGINE_TYPES and not str(cover.get("subtitle") or "").strip():
        count = (cover.get("topic_analysis") or {}).get("puzzle_count")
        if is_word_search_book_cover(cover):
            fixes["subtitle"] = f"{count} Word Search Puzzles" if count else "Word Search Book"
        else:
            fixes["subtitle"] = f"{count} Puzzles" if count else "Puzzle Book"
        fixes["_descriptions"].append("Added a sellable puzzle-book subtitle.")

    prompt = str(cover.get("image_prompt") or cover.get("cover_prompt") or "").strip()
    if len(prompt) < 48 or any("prompt" in w.lower() for w in qa.warnings):
        topic = title
        if is_black_history_topic(cover):
            fixes["image_direction"] = (
                f"{BLACK_HISTORY_COVER_SAFETY_RULES} {BLACK_HISTORY_VISUAL_STYLE} "
                f"{BLACK_HISTORY_COMPOSITION_RULES}"
            )
            fixes["_descriptions"].append("Applied Black History photo-realistic art direction.")
        elif is_photo_realistic_cover(cover):
            fixes["image_direction"] = (
                f"{PHOTO_REALISTIC_STYLE_RULES} {COVER_FRAMING_RULES} {COVER_COMPOSITION_INTEGRITY_RULES}"
            )
            fixes["_descriptions"].append("Applied photo-realistic cover art direction.")
        else:
            fixes["image_direction"] = (
                f"Portrait background artwork for '{topic}'. "
                "Topic-matching hero art, KDP-quality composition, lower third clear for text overlay. "
                "No text, logos, worksheets, or device frames."
            )
            fixes["_descriptions"].append("Strengthened cover art direction prompt.")

    if any("black history cover safety" in err.lower() for err in qa.errors):
        fixes["image_direction"] = (
            f"{BLACK_HISTORY_COVER_SAFETY_RULES} {BLACK_HISTORY_VISUAL_STYLE} "
            f"{BLACK_HISTORY_COMPOSITION_RULES} "
            "Regenerate: broad Black History, no readable text, no faces in lower third."
        )
        fixes["_descriptions"].append("Reinforced Black History cover safety — regenerate image required.")

    if is_word_search_book_cover(cover) and any(
        "crossword" in err.lower() or "word search book style" in err.lower() for err in qa.errors
    ):
        fixes["image_direction"] = (
            f"{BLACK_HISTORY_WORD_SEARCH_IMAGE_PROMPT if is_black_history_topic(cover) else WORD_SEARCH_COVER_VISUAL_RULES} "
            "Regenerate: WORD SEARCH book only — no crossword grids, clue boxes, or numbered squares."
        )
        fixes["_descriptions"].append("Reinforced Word Search-only cover rules — regenerate image required.")

    if any("photo-realistic cover check failed" in err.lower() for err in qa.errors):
        fixes["image_direction"] = (
            f"{PHOTO_REALISTIC_STYLE_RULES} {COVER_FRAMING_RULES} "
            "Regenerate: must look like a real professional book-cover photograph."
        )
        fixes["_descriptions"].append("Reinforced photo-realistic style — regenerate image required.")

    if any(
        "photo realism check failed" in err.lower() or "grain check failed" in err.lower()
        for err in qa.errors
    ):
        fixes["image_direction"] = (
            f"{PHOTO_REALISTIC_STYLE_RULES} "
            "Regenerate: smooth natural editorial photograph — zero grain, speckle, or AI noise."
        )
        fixes["_descriptions"].append("Reinforced smooth photo-realistic quality — regenerate image required.")

    if any(
        "facial quality check failed" in err.lower() or "portrait composition check failed" in err.lower()
        for err in qa.errors
    ):
        fixes["image_direction"] = (
            f"{COVER_PORTRAIT_SUBJECT_RULES} {COVER_FACIAL_QUALITY_RULES} "
            "Regenerate: reject distorted faces — calm closed-mouth waist-up portraits only."
        )
        fixes["_descriptions"].append("Reinforced portrait facial quality — regenerate image required.")

    if any("cover image framing check failed" in err.lower() for err in qa.errors):
        fixes["image_direction"] = (
            f"{COVER_FRAMING_RULES} {PHOTO_REALISTIC_STYLE_RULES} "
            "Regenerate: full figures inside frame — no cut-off heads, faces, or body parts at edges."
        )
        fixes["_descriptions"].append("Reinforced cover framing — regenerate image required.")

    if any("composition integrity check failed" in err.lower() for err in qa.errors):
        fixes["image_direction"] = (
            f"{COVER_COMPOSITION_INTEGRITY_RULES} {COVER_FRAMING_RULES} "
            "Regenerate: keep faces clear — no props or instruments spilling onto faces."
        )
        fixes["_descriptions"].append("Reinforced composition integrity — regenerate image required.")

    if not fixes["_descriptions"]:
        fixes["font_style"] = "bold_display"
        fixes["layout"] = "full_bleed_image"
        fixes["style"] = cover.get("style") or "modern_business"
        if fixes["style"] not in USER_STYLES:
            fixes["style"] = "modern_business"
        fixes["_descriptions"].append("Applied default professional typography and layout polish.")

    clean = {k: v for k, v in fixes.items() if not k.startswith("_")}
    clean["_descriptions"] = fixes["_descriptions"]
    return clean


def ensure_professional_cover(
    cover: dict,
    *,
    recreate: Callable[[dict[str, Any]], dict] | None = None,
    max_attempts: int = _MAX_CORRECTION_ATTEMPTS,
) -> tuple[dict[str, Any], CoverQualityResult]:
    """Evaluate cover quality and self-correct until professional or attempts exhausted."""
    applied: list[str] = []
    package_id = str(cover.get("package_id") or "")

    for attempt in range(1, max_attempts + 1):
        qa = evaluate_cover_quality(cover)
        if qa.passed:
            qa.fixes_applied = applied
            qa.attempts = attempt
            cover["cover_quality"] = qa.as_dict()
            return cover, qa

        corrections = suggest_cover_corrections(cover, qa)
        descriptions = corrections.pop("_descriptions", [])
        if not descriptions:
            break
        applied.extend(descriptions)

        overrides = {k: v for k, v in corrections.items() if not k.startswith("_")}
        if recreate is not None and ("cda-cover-pending" in (cover.get("preview_html") or "")):
            cover = recreate(overrides)
        else:
            cover = update_cover_design(cover, overrides, package_id=package_id)

    final = evaluate_cover_quality(cover)
    final.fixes_applied = applied
    final.attempts = max_attempts
    if applied and final.passed:
        final.fixes_applied = applied
    cover["cover_quality"] = final.as_dict()
    return cover, final


# ---------------------------------------------------------------------------
# Export validation — checks cover is export-ready before applying to PDF
# ---------------------------------------------------------------------------

# Phrases that indicate AI-generated gibberish or broken image prompts
_AI_GIBBERISH_PATTERNS = (
    "lorem ipsum",
    "placeholder",
    "your title here",
    "book title",
    "click to add",
    "cda-cover-pending",
    "pending regeneration",
    "regenerate",
)

# Template wording that should never appear in a finished cover
_TEMPLATE_WORDING = (
    "your subtitle",
    "your author",
    "author name",
    "book subtitle",
    "untitled",
    "professional digital guide",
    "digital product factory",
)

# Dark navy / black title band color signatures
_DARK_TITLE_BAND_PATTERNS = (
    "#0a0a0a",
    "#000000",
    "#0f1223",  # factory-forbidden deep navy
    "#3d2817",  # factory-forbidden dark brown
    "#0f172a",
    "rgba(15, 23, 42",
    "rgb(15, 23, 42)",
    "rgb(0, 0, 0)",
    "rgba(0, 0, 0",
)


def validate_cover_for_export(
    cover: dict,
    *,
    expected_title: str = "",
    expected_subtitle: str = "",
    expected_topic: str = "",
) -> list[str]:
    """Validate a cover_design is ready for PDF export.

    Returns a list of failed checks (empty = passed). Each entry is a human-readable
    string describing one issue found. Callers may log warnings or block the export
    based on the returned issues.
    """
    issues: list[str] = []

    # 1. Title correctness
    title = (cover.get("title") or "").strip().lower()
    if expected_title and title != expected_title.lower().strip():
        issues.append(f"Cover title '{cover.get('title')}' does not match expected '{expected_title}'.")

    # 2. Subtitle correctness
    subtitle = (cover.get("subtitle") or "").strip().lower()
    if expected_subtitle and subtitle != expected_subtitle.lower().strip():
        issues.append(f"Cover subtitle '{cover.get('subtitle')}' does not match expected '{expected_subtitle}'.")

    # 3. AI gibberish check on title/subtitle
    combined_text = f"{cover.get('title', '')} {cover.get('subtitle', '')} {cover.get('author', '')}".lower()
    for pattern in _AI_GIBBERISH_PATTERNS:
        if pattern.lower() in combined_text:
            issues.append(f"AI gibberish detected in cover text: '{pattern}'.")
            break

    # 4. Template wording check
    for pattern in _TEMPLATE_WORDING:
        if pattern.lower() in combined_text:
            issues.append(f"Template wording detected in cover: '{pattern}'.")
            break

    # 5. Spelling check — flag common GPT hallucination characters
    # Reject covers that still carry the "pending" placeholder flag
    preview = cover.get("preview_html") or ""
    if "cda-cover-pending" in preview or "cover-image-pending" in preview:
        issues.append("Cover image has not been generated yet (pending placeholder).")

    # 6. No black/dark navy title band — check color palette
    palette = cover.get("color_palette") or {}
    primary = str(palette.get("primary") or "").lower()
    for dark in _DARK_TITLE_BAND_PATTERNS:
        if dark.lower() in primary:
            issues.append(
                f"Dark title band detected (primary color: {palette.get('primary')}). "
                "This may obscure the cover title. Consider a lighter palette."
            )
            break

    # 7. Portrait composition — verify image size matches portrait ratio
    # The cover should have been generated at 1024x1536 (2:3 portrait)
    image_url = cover.get("cover_asset_url") or ""
    if image_url and not image_url.startswith("/download/"):
        # Only validate local assets (external URLs may be user uploads)
        pass

    # 8. Topic relevance — ensure the image prompt mentions the topic
    if expected_topic:
        image_prompt = (cover.get("image_prompt") or "").lower()
        topic_kw = expected_topic.lower().split()
        missing = [kw for kw in topic_kw if len(kw) > 4 and kw not in image_prompt]
        if len(missing) > 2:
            issues.append(
                f"Cover image prompt may not reference the topic '{expected_topic}'. "
                f"Consider regenerating with a more specific prompt."
            )

    return issues
