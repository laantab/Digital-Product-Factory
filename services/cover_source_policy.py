"""Global Cover Source Policy — Pexels first, paid AI fallback (2026-09-12).

The owner's required hierarchy for every Factory product that needs a cover:

    PEXELS FIRST -> quality/relevance gate -> PAID AI FALLBACK -> COVER QA
    -> APPROVE/LOCK

This module implements the PEXELS FIRST step and the gate that decides
whether a candidate photograph is genuinely good enough to use, or whether
the caller must fall back to the existing paid AI cover path. COVER QA
(``services/cover_quality_agent.py``) and APPROVE/LOCK (the existing
DRAFT/APPROVED/LOCKED artifact lifecycle) are unchanged — this module only
decides the *source* of the cover background image before those existing
steps run on whatever image was chosen.

Scope of this pass (read the 2026-09-12 audit before extending this further)
------------------------------------------------------------------------------
Wired into ``services.cover_agent.regenerate_cover_image``, gated to Ebook
only (``topic_analysis.product_type == "ebook"``). Word Search, Crossword,
and Coloring Book keep their existing AI-only cover behavior byte-for-byte
unchanged in this pass — their heavily-tuned, safety-critical AI prompts
(Black History subject-matter rules, no-crossword-mislabeling, facial-quality
retries, full-color scene requirements) are not something a generic Pexels
stock search can satisfy today, and turning this on for them would be a real
product redesign, not the "smallest safe shared policy" the owner asked for.
Extending Pexels-first to those products is a deliberate, separate decision.

Ebook's OWN primary cover path today is actually the separate guided
Pexels/upload flow in ``services/ebook_photo_cover.py`` (see
``services.ebook_package._collect_image_jobs``'s docstring: "Covers use the
photo-cover engine"), which has no AI fallback at all. This module does not
touch that flow. What it does improve is the older, still-reachable Cover
Editor route (``/cover/*``, ``services/cover_agent.py``), which was
previously AI-only with no Pexels attempt for any product, Ebook included.
Adding an AI fallback to the primary guided flow is a larger, separate
integration (it uses a structurally different PIL-raster rendering engine,
not this HTML/CSS one) and has not been attempted here.

Honesty about what the deterministic gate can and cannot check
------------------------------------------------------------------------------
Pexels does not return enough machine-checkable metadata to fully verify
"no watermark", "no logo", "no irrelevant text in the photograph", or "not a
generic stock cliché" without actually looking at the pixels. The always-on
deterministic gate below is a REAL check — resolution, orientation, and
topic-relevance keyword overlap against the photo's own alt text — but it is
narrower than full visual judgment, and it fails closed (rejects) whenever it
lacks enough signal to be confident, rather than assuming a photo is fine.

An optional, off-by-default paid vision check (``_evaluate_pexels_candidate_
vision``) can confirm the remaining checks the owner listed — watermark,
logo/advertising, irrelevant text, composition, negative space, generic
cliché — at real per-candidate cost. It reuses the exact same
``FACTORY_VISION_QC`` flag and AI client already used for the rendered-cover
vision QC in ``cover_quality_agent.py``, so it is off in every test and by
default in production, exactly like that check.

This module never makes a paid AI *image-generation* call itself; it only
decides whether the existing AI cover path in ``cover_agent.py`` should run
at all, and it only ever makes a live network call (Pexels search/download,
or the optional paid vision check) through the same test-mode-blocked
helpers ``services/ebook_pexels.py`` and ``services/cover_quality_agent.py``
already use.
"""
from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any

log = logging.getLogger(__name__)

MIN_PEXELS_SHORT_SIDE = 1200

# Alt-text markers that mean "reject" regardless of anything else -- this is
# the closest a deterministic, zero-cost check can get to "no watermark / no
# logo or advertising / not a generic stock cliché" without inspecting pixels.
_STOCK_CLICHE_ALT_MARKERS = (
    "stock photo", "watermark", "getty", "shutterstock", "istock", "alamy",
    "sample image", "royalty free", "royalty-free", "advertisement",
    "banner ad", "logo",
)


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").lower()).strip()


@dataclass
class PexelsCandidateEvaluation:
    """Result of the cover-appropriateness gate for one Pexels candidate.

    ``passed`` is only ever True when every check that could run actually
    passed — a candidate is never accepted merely because Pexels returned it.
    """

    passed: bool = False
    reasons: list[str] = field(default_factory=list)
    score: int = 0
    vision: dict[str, Any] | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "reasons": list(self.reasons),
            "score": self.score,
            "vision": self.vision,
        }


def evaluate_pexels_candidate(
    photo: dict[str, Any],
    *,
    title: str,
    topic: str = "",
    min_short_side: int = MIN_PEXELS_SHORT_SIDE,
) -> PexelsCandidateEvaluation:
    """Deterministic, zero-cost cover-appropriateness gate for one candidate.

    Checks: resolution floor, portrait-suitable orientation, topic relevance
    (keyword overlap against the photo's own alt text), and an alt-text
    heuristic for obvious stock/watermark/advertising markers. When the
    deterministic gate passes, an optional off-by-default paid vision check
    may run for the checks alt text cannot answer (see module docstring).
    """
    from services.ebook_pexels import _query_tokens

    reasons: list[str] = []
    score = 100

    width = int(photo.get("width") or 0)
    height = int(photo.get("height") or 0)
    short_side = min(width, height) if width and height else 0
    if short_side < min_short_side:
        reasons.append(
            f"Resolution too low ({width}x{height}px; need at least "
            f"{min_short_side}px on the short side for a print-quality cover)."
        )
        score -= 45

    if width and height and width > height * 1.3:
        reasons.append("Photo is landscape-oriented and not suitable for a portrait book cover.")
        score -= 25

    alt = _norm(str(photo.get("alt") or photo.get("description") or ""))
    topic_terms = _query_tokens(topic or title, limit=6)
    if not alt:
        reasons.append("Photo has no descriptive alt text to confirm topic relevance.")
        score -= 20
    elif topic_terms and not any(term in alt for term in topic_terms):
        reasons.append(f"Photo does not appear to relate to the topic ('{title}').")
        score -= 35

    if alt and any(marker in alt for marker in _STOCK_CLICHE_ALT_MARKERS):
        reasons.append("Photo's own description flags it as a generic/watermarked/advertising stock image.")
        score -= 40

    passed = not reasons and score >= 70
    evaluation = PexelsCandidateEvaluation(passed=passed, reasons=reasons, score=max(0, score))

    if passed:
        vision = _evaluate_pexels_candidate_vision(photo, title=title, topic=topic)
        if vision is not None:
            evaluation.vision = vision
            if not vision.get("passed", True) and not vision.get("skipped"):
                evaluation.passed = False
                evaluation.reasons.append(vision.get("reason") or "Vision quality check failed.")

    return evaluation


def _evaluate_pexels_candidate_vision(
    photo: dict[str, Any], *, title: str, topic: str
) -> dict[str, Any] | None:
    """Optional, off-by-default paid check for what alt text cannot prove.

    Reuses the exact ``FACTORY_VISION_QC`` flag and the same
    ``_vision_qc_enabled``/``_vision_qc_unavailable`` helpers already used for
    the rendered-cover vision QC, so this stays off in every test and by
    default in production, and never claims a check ran when it did not.
    """
    from services.cover_quality_agent import _vision_qc_enabled, _vision_qc_unavailable

    if not _vision_qc_enabled():
        return _vision_qc_unavailable("Pexels candidate vision QC is turned off")

    url = str(photo.get("preview_url") or photo.get("original_url") or "")
    if not url:
        return _vision_qc_unavailable("No photo URL available to inspect")

    try:
        from ai_client import get_client, get_model

        client = get_client()
        checks = (
            "no_watermark",
            "no_logo_or_advertising",
            "no_irrelevant_text_in_photo",
            "professional_quality",
            "attractive_composition",
            "has_negative_space_for_title",
            "not_generic_stock_cliche",
            "strong_topic_relevance",
        )
        prompt = (
            "This photograph is a candidate for a professional book cover about "
            f"'{topic or title}'. Answer JSON only with keys: "
            f"{', '.join(f'{c} (bool)' for c in checks)}, passed (bool), reason (string). "
            "Set passed true only when every listed boolean is true."
        )
        resp = client.chat.completions.create(
            model=get_model(),
            max_completion_tokens=300,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": url}},
                    ],
                }
            ],
        )
        import json as _json

        raw = (resp.choices[0].message.content or "").strip()
        if raw.startswith("```"):
            raw = raw.split("```", 2)[1]
            if raw.lstrip().lower().startswith("json"):
                raw = raw.lstrip()[4:]
        data = _json.loads(raw.strip())
        passed = bool(data.get("passed")) and all(bool(data.get(c)) for c in checks)
        return {"passed": passed, "reason": str(data.get("reason") or ""), "skipped": False}
    except Exception as exc:  # noqa: BLE001
        return _vision_qc_unavailable(f"Pexels candidate vision QC unavailable: {exc}")


def _save_pexels_cover_image(photo: dict[str, Any], package_id: str) -> str:
    """Download the Pexels original and save it as this package's cover PNG.

    Crops to fill the Factory's portrait cover canvas — the same file slot an
    AI-generated cover image occupies (``_cover_image_path``), so every
    downstream typography/QA/export step in ``cover_agent.py`` treats it
    identically regardless of source. This is what makes the deterministic
    Factory typography overlay (never AI-generated lettering) apply the same
    way to a Pexels-sourced cover as an AI-sourced one.
    """
    import io

    from PIL import Image

    from services.cover_agent import COVER_IMAGE_SIZE, _cover_image_path
    from services.ebook_pexels import download_pexels_original

    raw = download_pexels_original(photo)
    img = Image.open(io.BytesIO(raw))
    img.load()
    if img.mode != "RGB":
        img = img.convert("RGB")

    target_w, target_h = (int(v) for v in COVER_IMAGE_SIZE.split("x"))
    src_w, src_h = img.size
    scale = max(target_w / src_w, target_h / src_h)
    new_w, new_h = max(1, round(src_w * scale)), max(1, round(src_h * scale))
    img = img.resize((new_w, new_h), Image.LANCZOS)
    left = max(0, (new_w - target_w) // 2)
    top = max(0, (new_h - target_h) // 2)
    img = img.crop((left, top, left + target_w, top + target_h))

    path = _cover_image_path(package_id)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    img.save(path, "PNG")
    return path


def try_pexels_first_cover(
    cover: dict[str, Any], package_id: str
) -> tuple[dict[str, Any] | None, str | None]:
    """Attempt PEXELS FIRST for one cover. Returns (updated_cover, asset_url)
    on a genuinely acceptable match (cover annotated ``cover_source="pexels"``,
    ``paid_ai_used=False``), or (None, None) so the caller proceeds to the
    existing paid AI fallback. Never accepts a weak or irrelevant candidate
    merely because Pexels returned one — see ``evaluate_pexels_candidate``.
    """
    from services.cover_agent import _download_url, update_cover_design
    from services.ebook_pexels import cover_pexels_queries, pexels_configured, search_pexels

    if not package_id:
        return None, None
    if not pexels_configured():
        cover["cover_source_note"] = "Pexels is not configured; using paid AI image generation."
        return None, None

    title = str(cover.get("title") or "")
    prompt_text = str(cover.get("cover_prompt") or cover.get("image_prompt") or "")
    queries = cover_pexels_queries(title=title, topic=title, caption=prompt_text)

    attempts = 0
    for query in queries:
        try:
            result = search_pexels(query, per_page=8, orientation="portrait")
        except Exception as exc:  # noqa: BLE001
            log.warning("cover_source_policy: Pexels search %r failed: %s", query, exc)
            continue
        for photo in result.get("photos") or []:
            attempts += 1
            evaluation = evaluate_pexels_candidate(photo, title=title, topic=title)
            if not evaluation.passed:
                continue
            try:
                _save_pexels_cover_image(photo, package_id)
            except Exception as exc:  # noqa: BLE001
                log.warning("cover_source_policy: could not save Pexels candidate: %s", exc)
                continue
            updated = update_cover_design(
                cover, {"use_ai_image": True, "text_overlay": True}, package_id=package_id,
            )
            updated["cover_source"] = "pexels"
            updated["paid_ai_used"] = False
            updated["cover_source_note"] = (
                f"Cover photograph by {photo.get('photographer') or 'Unknown photographer'} via Pexels."
            )
            updated["cover_photo_attribution"] = photo.get("attribution") or ""
            updated["cover_photo_page_url"] = photo.get("page_url") or ""
            return updated, _download_url(package_id, "img_cover.png")

    cover["cover_source_note"] = (
        f"No Pexels photograph passed the cover quality/relevance gate "
        f"({attempts} candidate(s) checked); falling back to paid AI image generation."
        if attempts
        else "Pexels returned no candidates for this topic; falling back to paid AI image generation."
    )
    return None, None
